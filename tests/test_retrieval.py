from app.config import Settings
from app.graph.constants import RetrievalSource
from app.services.retrieval import ConfiguredPortfolioRetrievalService


async def test_resume_retrieval_reads_configured_text_file(tmp_path):
    resume_path = tmp_path / "resume.md"
    resume_path.write_text("# Resume\n\nBackend engineer with AI experience.", encoding="utf-8")
    service = ConfiguredPortfolioRetrievalService(
        Settings(_env_file=None, OPENAI_API_KEY="test", RESUME_PATH=str(resume_path))
    )

    result = await service.retrieve_resume()

    assert result.source == RetrievalSource.RESUME
    assert result.content == "# Resume\n\nBackend engineer with AI experience."
    assert result.error is None


async def test_resume_retrieval_reports_missing_config():
    service = ConfiguredPortfolioRetrievalService(Settings(_env_file=None, OPENAI_API_KEY="test"))

    result = await service.retrieve_resume()

    assert result.source == RetrievalSource.RESUME
    assert result.content == ""
    assert result.error == "RESUME_PATH is not configured, so resume retrieval was skipped."


async def test_project_retrieval_reports_missing_github_owner():
    service = ConfiguredPortfolioRetrievalService(Settings(_env_file=None, OPENAI_API_KEY="test"))

    result = await service.retrieve_projects()

    assert result.source == RetrievalSource.PROJECTS
    assert result.content == ""
    assert result.error == "GITHUB_OWNER is not configured, so project retrieval was skipped."
