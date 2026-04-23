from pathlib import Path
from typing import Protocol

import httpx
from pydantic import BaseModel

from app.config import Settings
from app.graph.constants import RetrievalSource


class RetrievalResult(BaseModel):
    source: RetrievalSource
    content: str = ""
    error: str | None = None


class PortfolioRetrievalService(Protocol):
    async def retrieve_profile(
        self,
        assistant_subject: str,
        path_override: str | None = None,
        inline_context: str = "",
    ) -> RetrievalResult:
        ...

    async def retrieve_projects(self) -> RetrievalResult:
        ...

    async def retrieve_resume(self, path_override: str | None = None) -> RetrievalResult:
        ...

    async def retrieve_docs(self, path_override: str | None = None) -> RetrievalResult:
        ...


class ConfiguredPortfolioRetrievalService:
    """Retrieves portfolio data from configured sources.

    Phase 3 keeps source internals deliberately simple: GitHub for projects and
    local text/markdown files for resume-like data. RAG can replace the local
    file methods later without changing graph node contracts.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def retrieve_profile(
        self,
        assistant_subject: str,
        path_override: str | None = None,
        inline_context: str = "",
    ) -> RetrievalResult:
        content_parts = [f"Portfolio subject: {assistant_subject}"]
        if inline_context.strip():
            content_parts.append(inline_context.strip())

        resume_result = await self.retrieve_resume(path_override)
        if resume_result.content:
            content_parts.append(resume_result.content)
        elif resume_result.error:
            return RetrievalResult(source=RetrievalSource.PROFILE, content="\n\n".join(content_parts), error=resume_result.error)

        return RetrievalResult(source=RetrievalSource.PROFILE, content="\n\n".join(content_parts))

    async def retrieve_projects(self) -> RetrievalResult:
        if not self._settings.github_owner:
            return RetrievalResult(
                source=RetrievalSource.PROJECTS,
                error="GITHUB_OWNER is not configured, so project retrieval was skipped.",
            )

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._settings.github_token:
            headers["Authorization"] = f"Bearer {self._settings.github_token}"

        url = f"{self._settings.github_api_base_url.rstrip('/')}/users/{self._settings.github_owner}/repos"
        params = {
            "sort": "updated",
            "direction": "desc",
            "per_page": min(self._settings.github_projects_limit, 100),
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            return RetrievalResult(
                source=RetrievalSource.PROJECTS,
                error=f"GitHub project retrieval failed: {exc}",
            )

        repos = response.json()
        if not isinstance(repos, list) or not repos:
            return RetrievalResult(
                source=RetrievalSource.PROJECTS,
                content=f"No public repositories were found for GitHub owner {self._settings.github_owner}.",
            )

        if not self._settings.github_include_forks:
            repos = [repo for repo in repos if not repo.get("fork", False)]

        if not repos:
            return RetrievalResult(
                source=RetrievalSource.PROJECTS,
                content=f"No non-fork repositories were found for GitHub owner {self._settings.github_owner}.",
            )

        return RetrievalResult(
            source=RetrievalSource.PROJECTS,
            content=_format_repositories(repos[: self._settings.github_projects_limit]),
        )

    async def retrieve_resume(self, path_override: str | None = None) -> RetrievalResult:
        return _read_text_source(RetrievalSource.RESUME, path_override, "resume path")

    async def retrieve_docs(self, path_override: str | None = None) -> RetrievalResult:
        return _read_text_source(RetrievalSource.DOCS, path_override or self._settings.docs_path, "DOCS_PATH")


def _read_text_source(source: RetrievalSource, configured_path: str | None, env_name: str) -> RetrievalResult:
    if not configured_path:
        return RetrievalResult(source=source, error=f"{env_name} is not configured, so {source.value} retrieval was skipped.")

    path = Path(configured_path)
    if not path.exists() or not path.is_file():
        return RetrievalResult(source=source, error=f"{env_name} points to a missing file: {configured_path}")

    try:
        return RetrievalResult(source=source, content=path.read_text(encoding="utf-8").strip())
    except OSError as exc:
        return RetrievalResult(source=source, error=f"Could not read {source.value} file: {exc}")


def _format_repositories(repos: list[dict]) -> str:
    sections = ["GitHub projects:"]
    for repo in repos:
        name = repo.get("name") or "unnamed"
        description = repo.get("description") or "No description provided."
        language = repo.get("language") or "Unknown"
        stars = repo.get("stargazers_count", 0)
        url = repo.get("html_url") or ""
        topics = repo.get("topics") or []
        archived = repo.get("archived", False)
        fork = repo.get("fork", False)

        metadata = [
            f"language: {language}",
            f"stars: {stars}",
            f"archived: {archived}",
            f"fork: {fork}",
        ]
        if topics:
            metadata.append(f"topics: {', '.join(topics)}")

        sections.append(
            f"- {name}\n"
            f"  Description: {description}\n"
            f"  Metadata: {'; '.join(metadata)}\n"
            f"  URL: {url}"
        )

    return "\n".join(sections)
