from app.config import Settings
from app.graph.constants import RetrievalSource
from app.services import retrieval as retrieval_module
from app.services.retrieval import ConfiguredPortfolioRetrievalService
import base64


async def test_resume_retrieval_reads_configured_text_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    resume_path = tmp_path / "resume.md"
    resume_path.write_text("# Resume\n\nBackend engineer with AI experience.", encoding="utf-8")
    service = ConfiguredPortfolioRetrievalService(
        Settings(_env_file=None, OPENAI_API_KEY="test", ASSISTANT_SUBJECT="Alex")
    )

    result = await service.retrieve_resume(str(resume_path))

    assert result.source == RetrievalSource.RESUME
    assert result.content == "# Resume\n\nBackend engineer with AI experience."
    assert result.error is None


async def test_resume_retrieval_strips_control_characters(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    resume_path = tmp_path / "resume.md"
    resume_path.write_text("# Resume\x7f\n\nBackend engineer\twith AI experience.", encoding="utf-8")
    service = ConfiguredPortfolioRetrievalService(
        Settings(_env_file=None, OPENAI_API_KEY="test", ASSISTANT_SUBJECT="Alex")
    )

    result = await service.retrieve_resume(str(resume_path))

    assert result.source == RetrievalSource.RESUME
    assert result.content == "# Resume\n\nBackend engineer\twith AI experience."
    assert result.error is None


async def test_resume_retrieval_reports_missing_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    service = ConfiguredPortfolioRetrievalService(
        Settings(_env_file=None, OPENAI_API_KEY="test", ASSISTANT_SUBJECT="Alex")
    )

    result = await service.retrieve_resume()

    assert result.source == RetrievalSource.RESUME
    assert result.content == ""
    assert result.error == "No resume source was found. Add data/resume.md or data/resume.pdf."


async def test_resume_retrieval_uses_vector_store_when_configured(tmp_path, monkeypatch, caplog):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(retrieval_module, "OpenAIEmbeddings", FakeEmbeddings)
    monkeypatch.setattr(retrieval_module, "ResumeVectorStore", FakeResumeVectorStore)
    caplog.set_level("INFO", logger="app.services.retrieval")
    service = ConfiguredPortfolioRetrievalService(
        Settings(
            _env_file=None,
            OPENAI_API_KEY="test",
            ASSISTANT_SUBJECT="Alex",
            NEON_DATABASE_URL_STRING="postgresql://example",
            RESUME_VECTOR_NAMESPACE="test",
            RESUME_VECTOR_TOP_K=2,
        )
    )

    result = await service.retrieve_resume(query="tell me about education")

    assert result.source == RetrievalSource.RESUME
    assert result.error is None
    assert result.content.startswith("Resume vector chunks:")
    assert "Master of Information Technology" in result.content
    assert "resume vector retrieval complete" in caplog.text


async def test_resume_path_override_keeps_local_file_retrieval_when_vectors_are_configured(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(retrieval_module, "OpenAIEmbeddings", FakeEmbeddings)
    monkeypatch.setattr(retrieval_module, "ResumeVectorStore", FakeResumeVectorStore)
    resume_path = tmp_path / "resume.md"
    resume_path.write_text("# Resume\n\nLocal override.", encoding="utf-8")
    service = ConfiguredPortfolioRetrievalService(
        Settings(
            _env_file=None,
            OPENAI_API_KEY="test",
            ASSISTANT_SUBJECT="Alex",
            NEON_DATABASE_URL_STRING="postgresql://example",
        )
    )

    result = await service.retrieve_resume(query="anything", path_override=str(resume_path))

    assert result.source == RetrievalSource.RESUME
    assert result.content == "# Resume\n\nLocal override."
    assert result.error is None


async def test_resume_vector_retrieval_reports_missing_index(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(retrieval_module, "OpenAIEmbeddings", FakeEmbeddings)
    monkeypatch.setattr(retrieval_module, "ResumeVectorStore", EmptyResumeVectorStore)
    service = ConfiguredPortfolioRetrievalService(
        Settings(
            _env_file=None,
            OPENAI_API_KEY="test",
            ASSISTANT_SUBJECT="Alex",
            NEON_DATABASE_URL_STRING="postgresql://example",
        )
    )

    result = await service.retrieve_resume(query="tell me about education")

    assert result.source == RetrievalSource.RESUME
    assert result.content == ""
    assert result.error == "No indexed resume chunks were found. Run portfolio-index-resume before serving resume queries."


async def test_project_retrieval_reports_missing_github_owner(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    service = ConfiguredPortfolioRetrievalService(
        Settings(_env_file=None, OPENAI_API_KEY="test", ASSISTANT_SUBJECT="Alex")
    )

    result = await service.retrieve_projects()

    assert result.source == RetrievalSource.PROJECTS
    assert result.content == ""
    assert result.error == "GITHUB_OWNER is not configured, so project retrieval was skipped."


async def test_project_retrieval_enriches_repositories_with_readme(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(retrieval_module.httpx, "AsyncClient", lambda timeout: FakeGitHubClient())
    service = ConfiguredPortfolioRetrievalService(
        Settings(
            _env_file=None,
            OPENAI_API_KEY="test",
            ASSISTANT_SUBJECT="Alex",
            GITHUB_OWNER="alex",
            GITHUB_README_MAX_CHARS=80,
        )
    )

    result = await service.retrieve_projects()

    assert result.source == RetrievalSource.PROJECTS
    assert result.error is None
    assert "- project-with-readme" in result.content
    assert "README excerpt:" in result.content
    assert "This project uses LangGraph and OpenAI" in result.content
    assert "- project-without-readme" in result.content


async def test_project_retrieval_uses_in_memory_github_cache(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fake_client = FakeGitHubClient()
    monkeypatch.setattr(retrieval_module.httpx, "AsyncClient", lambda timeout: fake_client)
    service = ConfiguredPortfolioRetrievalService(
        Settings(
            _env_file=None,
            OPENAI_API_KEY="test",
            ASSISTANT_SUBJECT="Alex",
            GITHUB_OWNER="alex",
            GITHUB_README_MAX_CHARS=80,
            GITHUB_CACHE_TTL_SECONDS=900,
        )
    )

    first_result = await service.retrieve_projects()
    second_result = await service.retrieve_projects()

    assert first_result.error is None
    assert second_result.error is None
    assert first_result.content == second_result.content
    assert fake_client.get_calls.count("repos") == 1
    assert fake_client.get_calls.count("readme:project-with-readme") == 1
    assert fake_client.get_calls.count("readme:project-with-readme-api") == 1
    assert fake_client.get_calls.count("readme:project-without-readme") == 1


async def test_project_retrieval_cache_can_be_disabled_with_zero_ttl(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fake_client = FakeGitHubClient()
    monkeypatch.setattr(retrieval_module.httpx, "AsyncClient", lambda timeout: fake_client)
    service = ConfiguredPortfolioRetrievalService(
        Settings(
            _env_file=None,
            OPENAI_API_KEY="test",
            ASSISTANT_SUBJECT="Alex",
            GITHUB_OWNER="alex",
            GITHUB_README_MAX_CHARS=80,
            GITHUB_CACHE_TTL_SECONDS=0,
        )
    )

    await service.retrieve_projects()
    await service.retrieve_projects()

    assert fake_client.get_calls.count("repos") == 2
    assert fake_client.get_calls.count("readme:project-with-readme") == 2


async def test_project_retrieval_keeps_metadata_when_readme_is_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(retrieval_module.httpx, "AsyncClient", lambda timeout: FakeGitHubClient(readme_status=404))
    service = ConfiguredPortfolioRetrievalService(
        Settings(
            _env_file=None,
            OPENAI_API_KEY="test",
            ASSISTANT_SUBJECT="Alex",
            GITHUB_OWNER="alex",
        )
    )

    result = await service.retrieve_projects()

    assert result.source == RetrievalSource.PROJECTS
    assert result.error is None
    assert "- project-with-readme" in result.content
    assert "README excerpt:" not in result.content


async def test_project_retrieval_focuses_on_named_repository(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(retrieval_module.httpx, "AsyncClient", lambda timeout: FakeGitHubClient())
    service = ConfiguredPortfolioRetrievalService(
        Settings(
            _env_file=None,
            OPENAI_API_KEY="test",
            ASSISTANT_SUBJECT="Alex",
            GITHUB_OWNER="alex",
            GITHUB_TARGET_README_MAX_CHARS=200,
        )
    )

    result = await service.retrieve_projects("Tell me about project-with-readme architecture")

    assert result.source == RetrievalSource.PROJECTS
    assert result.error is None
    assert result.content.startswith("Focused GitHub project:")
    assert "- project-with-readme" in result.content
    assert "This project uses LangGraph and OpenAI" in result.content
    assert "- project-without-readme" not in result.content


async def test_project_retrieval_prefers_longest_repository_name(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(retrieval_module.httpx, "AsyncClient", lambda timeout: FakeGitHubClient())
    service = ConfiguredPortfolioRetrievalService(
        Settings(
            _env_file=None,
            OPENAI_API_KEY="test",
            ASSISTANT_SUBJECT="Alex",
            GITHUB_OWNER="alex",
        )
    )

    result = await service.retrieve_projects("Tell me about project-with-readme-api")

    assert result.source == RetrievalSource.PROJECTS
    assert result.error is None
    assert result.content.startswith("Focused GitHub project:")
    assert "- project-with-readme-api" in result.content
    assert "- project-with-readme\n" not in result.content


async def test_project_retrieval_focuses_on_clear_typo_match(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(retrieval_module.httpx, "AsyncClient", lambda timeout: FakeMatchCastGitHubClient())
    service = ConfiguredPortfolioRetrievalService(
        Settings(
            _env_file=None,
            OPENAI_API_KEY="test",
            ASSISTANT_SUBJECT="Alex",
            GITHUB_OWNER="alex",
            GITHUB_TARGET_README_MAX_CHARS=200,
        )
    )

    result = await service.retrieve_projects("Tell me about mathcast project")

    assert result.source == RetrievalSource.PROJECTS
    assert result.error is None
    assert result.content.startswith("Focused GitHub project:")
    assert "- matchcast" in result.content
    assert "AI-powered match analysis" in result.content
    assert "- portfolio-assistant-langgraph" not in result.content


async def test_project_retrieval_avoids_fuzzy_focus_when_match_is_not_clear(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(retrieval_module.httpx, "AsyncClient", lambda timeout: AmbiguousFuzzyGitHubClient())
    service = ConfiguredPortfolioRetrievalService(
        Settings(
            _env_file=None,
            OPENAI_API_KEY="test",
            ASSISTANT_SUBJECT="Alex",
            GITHUB_OWNER="alex",
        )
    )

    result = await service.retrieve_projects("Tell me about matcast project")

    assert result.source == RetrievalSource.PROJECTS
    assert result.error is None
    assert result.content.startswith("GitHub projects:")
    assert "- matchcast" in result.content
    assert "- mathcast" in result.content


async def test_project_retrieval_prioritizes_featured_metadata_for_subjective_questions(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    metadata_path = tmp_path / "featured_projects.json"
    metadata_path.write_text(
        """[
  {
    "name": "project-without-readme",
    "title": "Flagship Project",
    "summary": "Curated flagship project summary.",
    "proud_reason": "This project best represents the portfolio owner's product and engineering taste.",
    "impact": "It combines frontend, backend, and AI delivery.",
    "labels": ["featured", "most proud"]
  }
]""",
        encoding="utf-8",
    )
    monkeypatch.setattr(retrieval_module.httpx, "AsyncClient", lambda timeout: FakeGitHubClient())
    service = ConfiguredPortfolioRetrievalService(
        Settings(
            _env_file=None,
            OPENAI_API_KEY="test",
            ASSISTANT_SUBJECT="Alex",
            GITHUB_OWNER="alex",
            FEATURED_PROJECTS_PATH=str(metadata_path),
        )
    )

    result = await service.retrieve_projects("What project are you most proud of?")

    assert result.source == RetrievalSource.PROJECTS
    assert result.error is None
    assert result.content.index("- project-without-readme") < result.content.index("- project-with-readme")
    assert "Selection guidance: prefer projects marked as featured" in result.content
    assert "Proud reason: This project best represents" in result.content
    assert "Labels: featured, most proud" in result.content


async def test_resume_preload_logs_selected_source(tmp_path, caplog, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    resume_path = data_dir / "resume.md"
    resume_path.write_text("# Resume\n\nAI engineer.", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    caplog.set_level("INFO", logger="app.services.retrieval")
    ConfiguredPortfolioRetrievalService(
        Settings(
            _env_file=None,
            OPENAI_API_KEY="test",
            ASSISTANT_SUBJECT="Alex",
        )
    )

    assert "resume preload | source=data\\resume.md" in caplog.text
    assert "resume preload complete" in caplog.text


async def test_resume_preload_logs_missing_source(tmp_path, caplog, monkeypatch):
    monkeypatch.chdir(tmp_path)
    caplog.set_level("INFO", logger="app.services.retrieval")
    ConfiguredPortfolioRetrievalService(
        Settings(_env_file=None, OPENAI_API_KEY="test", ASSISTANT_SUBJECT="Alex")
    )

    assert "resume preload skipped | source=none" in caplog.text


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise retrieval_module.httpx.HTTPStatusError(
                "request failed",
                request=None,
                response=None,
            )


class FakeGitHubClient:
    def __init__(self, readme_status=200):
        self._readme_status = readme_status
        self.get_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def get(self, url, headers=None, params=None):
        if url.endswith("/users/alex/repos"):
            self.get_calls.append("repos")
            return FakeResponse(
                [
                    {
                        "name": "project-with-readme",
                        "description": "Project with README.",
                        "language": "Python",
                        "stargazers_count": 3,
                        "html_url": "https://github.com/alex/project-with-readme",
                        "topics": ["ai"],
                        "archived": False,
                        "fork": False,
                    },
                    {
                        "name": "project-with-readme-api",
                        "description": "Longer matching project.",
                        "language": "Python",
                        "stargazers_count": 2,
                        "html_url": "https://github.com/alex/project-with-readme-api",
                        "topics": ["api"],
                        "archived": False,
                        "fork": False,
                    },
                    {
                        "name": "project-without-readme",
                        "description": "Project without README.",
                        "language": "TypeScript",
                        "stargazers_count": 1,
                        "html_url": "https://github.com/alex/project-without-readme",
                        "topics": [],
                        "archived": False,
                        "fork": False,
                    },
                ]
            )
        if url.endswith("/repos/alex/project-with-readme/readme"):
            self.get_calls.append("readme:project-with-readme")
            encoded = base64.b64encode(
                b"# Project\n\nThis project uses LangGraph and OpenAI for assistant orchestration."
            ).decode("utf-8")
            return FakeResponse({"content": encoded}, status_code=self._readme_status)
        if url.endswith("/repos/alex/project-without-readme/readme"):
            self.get_calls.append("readme:project-without-readme")
            return FakeResponse({}, status_code=404)
        if url.endswith("/repos/alex/project-with-readme-api/readme"):
            self.get_calls.append("readme:project-with-readme-api")
            encoded = base64.b64encode(
                b"# Project API\n\nThis project exposes a focused API for portfolio questions."
            ).decode("utf-8")
            return FakeResponse({"content": encoded}, status_code=self._readme_status)
        return FakeResponse({}, status_code=404)


class FakeMatchCastGitHubClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def get(self, url, headers=None, params=None):
        if url.endswith("/users/alex/repos"):
            return FakeResponse(
                [
                    {
                        "name": "portfolio-assistant-langgraph",
                        "description": "LangGraph portfolio assistant.",
                        "language": "Python",
                        "stargazers_count": 3,
                        "html_url": "https://github.com/alex/portfolio-assistant-langgraph",
                        "topics": ["ai"],
                        "archived": False,
                        "fork": False,
                    },
                    {
                        "name": "matchcast",
                        "description": "AI-powered match analysis.",
                        "language": "TypeScript",
                        "stargazers_count": 2,
                        "html_url": "https://github.com/alex/matchcast",
                        "topics": ["ai", "football"],
                        "archived": False,
                        "fork": False,
                    },
                ]
            )
        if url.endswith("/repos/alex/matchcast/readme"):
            encoded = base64.b64encode(b"# MatchCast\n\nAI-powered match analysis.").decode("utf-8")
            return FakeResponse({"content": encoded})
        return FakeResponse({}, status_code=404)


class AmbiguousFuzzyGitHubClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def get(self, url, headers=None, params=None):
        if url.endswith("/users/alex/repos"):
            return FakeResponse(
                [
                    {
                        "name": "matchcast",
                        "description": "AI-powered match analysis.",
                        "language": "TypeScript",
                        "stargazers_count": 2,
                        "html_url": "https://github.com/alex/matchcast",
                        "topics": ["ai"],
                        "archived": False,
                        "fork": False,
                    },
                    {
                        "name": "mathcast",
                        "description": "Math content project.",
                        "language": "TypeScript",
                        "stargazers_count": 1,
                        "html_url": "https://github.com/alex/mathcast",
                        "topics": ["math"],
                        "archived": False,
                        "fork": False,
                    },
                ]
            )
        return FakeResponse({}, status_code=404)


class FakeEmbeddings:
    def __init__(self, model, api_key):
        self.model = model
        self.api_key = api_key

    async def aembed_query(self, query):
        return [0.1] * 1536


class FakeResumeVectorStore:
    def __init__(self, database_url):
        self.database_url = database_url

    def search(self, *, namespace, query_embedding, limit):
        assert namespace == "test"
        assert len(query_embedding) == 1536
        assert limit == 2
        return [
            retrieval_module.RetrievedChunk(
                content="## Education\n\nMaster of Information Technology.",
                source="data/resume.md",
                chunk_index=4,
                distance=0.12,
            )
        ]


class EmptyResumeVectorStore:
    def __init__(self, database_url):
        self.database_url = database_url

    def search(self, *, namespace, query_embedding, limit):
        return []
