from app.config import Settings
from app.graph.constants import RetrievalSource
from app.services.retrieval import ConfiguredPortfolioRetrievalService


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
