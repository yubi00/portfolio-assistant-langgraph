import logging
import unicodedata
from pathlib import Path
from typing import Protocol
import base64

import httpx
from pydantic import BaseModel
from pypdf import PdfReader

from app.config import Settings
from app.graph.constants import RetrievalSource


logger = logging.getLogger("app.services.retrieval")


class RetrievalResult(BaseModel):
    source: RetrievalSource
    content: str = ""
    error: str | None = None


class PortfolioRetrievalService(Protocol):
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
        self._configured_resume_result = _load_default_resume_source()

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

                selected_repos = repos[: self._settings.github_projects_limit]
                readmes = await _fetch_repository_readmes(
                    client=client,
                    api_base_url=self._settings.github_api_base_url,
                    owner=self._settings.github_owner,
                    headers=headers,
                    repos=selected_repos,
                    max_chars=self._settings.github_readme_max_chars,
                )
        except httpx.HTTPError as exc:
            return RetrievalResult(
                source=RetrievalSource.PROJECTS,
                error=f"GitHub project retrieval failed: {exc}",
            )

        return RetrievalResult(
            source=RetrievalSource.PROJECTS,
            content=_format_repositories(selected_repos, readmes),
        )

    async def retrieve_resume(self, path_override: str | None = None) -> RetrievalResult:
        if path_override:
            return _read_text_source(RetrievalSource.RESUME, path_override, "resume path override")
        return self._configured_resume_result

    async def retrieve_docs(self, path_override: str | None = None) -> RetrievalResult:
        return _read_text_source(RetrievalSource.DOCS, path_override or self._settings.docs_path, "DOCS_PATH")


def _read_text_source(source: RetrievalSource, configured_path: str | None, env_name: str) -> RetrievalResult:
    if not configured_path:
        return RetrievalResult(source=source, error=f"{env_name} is not configured, so {source.value} retrieval was skipped.")

    path = Path(configured_path)
    if not path.exists() or not path.is_file():
        return RetrievalResult(source=source, error=f"{env_name} points to a missing file: {configured_path}")

    try:
        if path.suffix.lower() == ".pdf":
            return RetrievalResult(source=source, content=_extract_pdf_text(path))
        return RetrievalResult(source=source, content=_normalize_text_content(path.read_text(encoding="utf-8")))
    except OSError as exc:
        return RetrievalResult(source=source, error=f"Could not read {source.value} file: {exc}")


def _load_default_resume_source() -> RetrievalResult:
    for candidate in (Path("data/resume.md"), Path("data/resume.pdf")):
        if candidate.exists() and candidate.is_file():
            logger.info("resume preload | source=%s", candidate)
            result = _read_text_source(RetrievalSource.RESUME, str(candidate), "default resume source")
            _log_resume_preload_result(str(candidate), result)
            return result

    result = RetrievalResult(
        source=RetrievalSource.RESUME,
        error="No resume source was found. Add data/resume.md or data/resume.pdf.",
    )
    _log_resume_preload_result("none", result)
    return result


def _extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    raw_text = "\n\n".join(page.strip() for page in pages if page.strip())
    return _normalize_text_content(raw_text)


def _normalize_text_content(content: str) -> str:
    cleaned = "".join(
        char
        for char in content
        if char in {"\n", "\r", "\t"} or not unicodedata.category(char).startswith("C")
    )
    return cleaned.strip()


def _log_resume_preload_result(source: str, result: RetrievalResult) -> None:
    if result.content:
        logger.info("resume preload complete | source=%s | chars=%s", source, len(result.content))
        return
    logger.warning("resume preload skipped | source=%s | reason=%s", source, result.error)


async def _fetch_repository_readmes(
    client: httpx.AsyncClient,
    api_base_url: str,
    owner: str,
    headers: dict[str, str],
    repos: list[dict],
    max_chars: int,
) -> dict[str, str]:
    readmes: dict[str, str] = {}
    for repo in repos:
        name = repo.get("name")
        if not name:
            continue
        readme = await _fetch_repository_readme(
            client=client,
            api_base_url=api_base_url,
            owner=owner,
            repo=name,
            headers=headers,
            max_chars=max_chars,
        )
        if readme:
            readmes[name] = readme
    return readmes


async def _fetch_repository_readme(
    client: httpx.AsyncClient,
    api_base_url: str,
    owner: str,
    repo: str,
    headers: dict[str, str],
    max_chars: int,
) -> str:
    url = f"{api_base_url.rstrip('/')}/repos/{owner}/{repo}/readme"
    try:
        response = await client.get(url, headers=headers)
        if response.status_code == 404:
            return ""
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.debug("GitHub README retrieval skipped | repo=%s | reason=%s", repo, exc)
        return ""

    payload = response.json()
    encoded_content = payload.get("content")
    if not isinstance(encoded_content, str):
        return ""

    try:
        decoded = base64.b64decode(encoded_content, validate=False).decode("utf-8", errors="replace")
    except ValueError:
        return ""

    normalized = _normalize_text_content(decoded)
    if len(normalized) <= max_chars:
        return normalized
    return normalized[:max_chars].rstrip()


def _format_repositories(repos: list[dict], readmes: dict[str, str] | None = None) -> str:
    readmes = readmes or {}
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
        if readme := readmes.get(name):
            sections.append(f"  README excerpt:\n{_indent_readme_excerpt(readme)}")

    return "\n".join(sections)


def _indent_readme_excerpt(readme: str) -> str:
    return "\n".join(f"    {line}" for line in readme.splitlines())
