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

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def get(self, url, headers=None, params=None):
        if url.endswith("/users/alex/repos"):
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
            encoded = base64.b64encode(
                b"# Project\n\nThis project uses LangGraph and OpenAI for assistant orchestration."
            ).decode("utf-8")
            return FakeResponse({"content": encoded}, status_code=self._readme_status)
        if url.endswith("/repos/alex/project-without-readme/readme"):
            return FakeResponse({}, status_code=404)
        return FakeResponse({}, status_code=404)
