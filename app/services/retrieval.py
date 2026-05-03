import logging
import unicodedata
from time import monotonic
from pathlib import Path
from typing import Protocol
import base64
from difflib import SequenceMatcher
import re

import httpx
from langchain_openai import OpenAIEmbeddings
from pydantic import BaseModel
from pypdf import PdfReader

from app.config import Settings
from app.graph.constants import RetrievalSource
from app.services.featured_projects import FeaturedProject, find_featured_project, load_featured_projects
from app.services.resume_vector_store import RetrievedChunk, ResumeVectorStore


logger = logging.getLogger("app.services.retrieval")

CacheEntry = tuple[float, object]


class RetrievalResult(BaseModel):
    source: RetrievalSource
    content: str = ""
    error: str | None = None


class PortfolioRetrievalService(Protocol):
    async def retrieve_projects(self, query: str | None = None) -> RetrievalResult:
        ...

    async def retrieve_resume(self, path_override: str | None = None, query: str | None = None) -> RetrievalResult:
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
        self._configured_resume_result = (
            RetrievalResult(source=RetrievalSource.RESUME)
            if settings.neon_database_url_string
            else _load_default_resume_source()
        )
        self._featured_projects = load_featured_projects(settings.featured_projects_path)
        self._github_repos_cache: CacheEntry | None = None
        self._github_readme_cache: dict[tuple[str, int], CacheEntry] = {}

    async def retrieve_projects(self, query: str | None = None) -> RetrievalResult:
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
            "per_page": 100,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                repos = await self._fetch_github_repositories(client, url, headers, params)
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

                target_repo = _find_target_repository(query, repos)
                if target_repo:
                    readmes = await self._fetch_repository_readmes_cached(
                        client=client,
                        api_base_url=self._settings.github_api_base_url,
                        owner=self._settings.github_owner,
                        headers=headers,
                        repos=[target_repo],
                        max_chars=self._settings.github_target_readme_max_chars,
                    )
                    return RetrievalResult(
                        source=RetrievalSource.PROJECTS,
                        content=_format_repositories(
                            [target_repo],
                            readmes,
                            focused=True,
                            featured_projects=self._featured_projects,
                            query=query,
                        ),
                    )

                selected_repos = _select_repositories(
                    repos=repos,
                    featured_projects=self._featured_projects,
                    limit=self._settings.github_projects_limit,
                    query=query,
                )
                readmes = await self._fetch_repository_readmes_cached(
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
            content=_format_repositories(
                selected_repos,
                readmes,
                featured_projects=self._featured_projects,
                query=query,
            ),
        )

    async def _fetch_github_repositories(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str],
        params: dict[str, object],
    ) -> list[dict]:
        cached = self._get_cache_value(self._github_repos_cache)
        if isinstance(cached, list):
            logger.debug("GitHub repositories cache hit | owner=%s", self._settings.github_owner)
            return cached

        logger.debug("GitHub repositories cache miss | owner=%s", self._settings.github_owner)
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        repos = response.json()
        if isinstance(repos, list):
            self._github_repos_cache = self._new_cache_entry(repos)
        return repos

    async def _fetch_repository_readmes_cached(
        self,
        *,
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
            cache_key = (str(name), max_chars)
            cached = self._get_cache_value(self._github_readme_cache.get(cache_key))
            if isinstance(cached, str):
                logger.debug("GitHub README cache hit | repo=%s | max_chars=%s", name, max_chars)
                readme = cached
            else:
                logger.debug("GitHub README cache miss | repo=%s | max_chars=%s", name, max_chars)
                readme = await _fetch_repository_readme(
                    client=client,
                    api_base_url=api_base_url,
                    owner=owner,
                    repo=str(name),
                    headers=headers,
                    max_chars=max_chars,
                )
                self._github_readme_cache[cache_key] = self._new_cache_entry(readme)
            if readme:
                readmes[str(name)] = readme
        return readmes

    def _get_cache_value(self, entry: CacheEntry | None) -> object | None:
        if not entry:
            return None
        expires_at, value = entry
        if expires_at <= monotonic():
            return None
        return value

    def _new_cache_entry(self, value: object) -> CacheEntry:
        ttl_seconds = max(0, self._settings.github_cache_ttl_seconds)
        return (monotonic() + ttl_seconds, value)

    async def retrieve_resume(self, path_override: str | None = None, query: str | None = None) -> RetrievalResult:
        if path_override:
            return _read_text_source(RetrievalSource.RESUME, path_override, "resume path override")
        if self._settings.neon_database_url_string:
            return await self._retrieve_resume_vectors(query)
        return self._configured_resume_result

    async def retrieve_docs(self, path_override: str | None = None) -> RetrievalResult:
        return _read_text_source(RetrievalSource.DOCS, path_override or self._settings.docs_path, "DOCS_PATH")

    async def _retrieve_resume_vectors(self, query: str | None) -> RetrievalResult:
        if not query or not query.strip():
            return RetrievalResult(source=RetrievalSource.RESUME, error="Resume vector retrieval requires a query.")
        if not self._settings.openai_api_key:
            return RetrievalResult(source=RetrievalSource.RESUME, error="OPENAI_API_KEY is required for resume vector retrieval.")

        logger.info(
            "resume vector retrieval | namespace=%s | top_k=%s",
            self._settings.resume_vector_namespace,
            self._settings.resume_vector_top_k,
        )
        try:
            embedding_client = OpenAIEmbeddings(
                model=self._settings.openai_embedding_model,
                api_key=self._settings.openai_api_key,
            )
            query_embedding = await embedding_client.aembed_query(query)
            store = ResumeVectorStore(self._settings.neon_database_url_string)
            chunks = store.search(
                namespace=self._settings.resume_vector_namespace,
                query_embedding=query_embedding,
                limit=self._settings.resume_vector_top_k,
            )
        except Exception as exc:
            logger.warning("resume vector retrieval failed | reason=%s", exc)
            return RetrievalResult(source=RetrievalSource.RESUME, error=f"Resume vector retrieval failed: {exc}")

        logger.info(
            "resume vector retrieval complete | namespace=%s | chunks=%s",
            self._settings.resume_vector_namespace,
            len(chunks),
        )
        if not chunks:
            return RetrievalResult(
                source=RetrievalSource.RESUME,
                error="No indexed resume chunks were found. Run portfolio-index-resume before serving resume queries.",
            )

        return RetrievalResult(source=RetrievalSource.RESUME, content=_format_resume_chunks(chunks))


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


def _format_resume_chunks(chunks: list[RetrievedChunk]) -> str:
    sections = ["Resume vector chunks:"]
    for chunk in chunks:
        sections.append(
            f"- Source: {chunk.source} | chunk_index: {chunk.chunk_index} | distance: {chunk.distance:.4f}\n"
            f"{_indent_readme_excerpt(chunk.content)}"
        )
    return "\n".join(sections)


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


def _find_target_repository(query: str | None, repos: list[dict]) -> dict | None:
    if not query:
        return None

    normalized_query = _normalize_repo_match_text(query)
    matches: list[dict] = []
    for repo in repos:
        name = repo.get("name")
        if not isinstance(name, str) or not name:
            continue
        normalized_name = _normalize_repo_match_text(name)
        if name.lower() in query.lower() or normalized_name in normalized_query:
            matches.append(repo)

    if not matches:
        return _find_fuzzy_target_repository(normalized_query, repos)

    matches.sort(key=lambda repo: len(repo.get("name", "")), reverse=True)
    if len(matches) == 1:
        return matches[0]

    longest = len(matches[0].get("name", ""))
    second_longest = len(matches[1].get("name", ""))
    if longest > second_longest:
        return matches[0]
    return None


def _find_fuzzy_target_repository(normalized_query: str, repos: list[dict]) -> dict | None:
    query_tokens = normalized_query.split()
    if not query_tokens:
        return None

    scored_matches: list[tuple[float, dict]] = []
    for repo in repos:
        name = repo.get("name")
        if not isinstance(name, str) or not name:
            continue
        normalized_name = _normalize_repo_match_text(name)
        score = _best_repo_name_similarity(normalized_name, query_tokens)
        if score >= 0.85:
            scored_matches.append((score, repo))

    if not scored_matches:
        return None

    scored_matches.sort(key=lambda item: item[0], reverse=True)
    best_score, best_repo = scored_matches[0]
    if len(scored_matches) == 1:
        return best_repo

    second_score = scored_matches[1][0]
    if best_score - second_score >= 0.08:
        return best_repo
    return None


def _best_repo_name_similarity(normalized_name: str, query_tokens: list[str]) -> float:
    name_tokens = normalized_name.split()
    if not name_tokens:
        return 0.0

    token_count = len(name_tokens)
    query_text = " ".join(query_tokens)
    candidates = [query_text]
    if len(query_tokens) >= token_count:
        candidates.extend(
            " ".join(query_tokens[index : index + token_count])
            for index in range(0, len(query_tokens) - token_count + 1)
        )

    return max(SequenceMatcher(None, normalized_name, candidate).ratio() for candidate in candidates)


SUBJECTIVE_PROJECT_QUERY_PATTERN = re.compile(
    r"\b(proud|favorite|favourite|flagship|best|standout|highlight|impressive)\b",
    re.IGNORECASE,
)


def _select_repositories(
    *,
    repos: list[dict],
    featured_projects: dict[str, FeaturedProject],
    limit: int,
    query: str | None,
) -> list[dict]:
    if not _is_subjective_project_query(query) or not featured_projects:
        return repos[:limit]

    featured_repos = [
        repo
        for repo in repos
        if isinstance(repo.get("name"), str) and find_featured_project(repo["name"], featured_projects)
    ]
    selected = [*featured_repos]
    selected_names = {repo.get("name") for repo in selected}
    for repo in repos:
        if len(selected) >= limit:
            break
        if repo.get("name") in selected_names:
            continue
        selected.append(repo)
    return selected[:limit]


def _is_subjective_project_query(query: str | None) -> bool:
    return bool(query and SUBJECTIVE_PROJECT_QUERY_PATTERN.search(query))


def _normalize_repo_match_text(value: str) -> str:
    return " ".join(token for token in _split_repo_match_text(value) if token)


def _split_repo_match_text(value: str) -> list[str]:
    return value.lower().replace("-", " ").replace("_", " ").replace(".", " ").split()


def _format_repositories(
    repos: list[dict],
    readmes: dict[str, str] | None = None,
    focused: bool = False,
    featured_projects: dict[str, FeaturedProject] | None = None,
    query: str | None = None,
) -> str:
    readmes = readmes or {}
    featured_projects = featured_projects or {}
    sections = ["Focused GitHub project:" if focused else "GitHub projects:"]
    if _is_subjective_project_query(query) and featured_projects:
        sections.append(
            "Selection guidance: prefer projects marked as featured, flagship, or most proud when answering subjective project preference questions."
        )
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
        if featured_project := find_featured_project(name, featured_projects):
            sections.append(_format_featured_project_note(featured_project))
        if readme := readmes.get(name):
            sections.append(f"  README excerpt:\n{_indent_readme_excerpt(readme)}")

    return "\n".join(sections)


def _format_featured_project_note(project: FeaturedProject) -> str:
    lines = ["  Featured project metadata:"]
    if project.title:
        lines.append(f"    Title: {project.title}")
    if project.labels:
        lines.append(f"    Labels: {', '.join(project.labels)}")
    if project.summary:
        lines.append(f"    Summary: {project.summary}")
    if project.proud_reason:
        lines.append(f"    Proud reason: {project.proud_reason}")
    if project.impact:
        lines.append(f"    Impact: {project.impact}")
    return "\n".join(lines)


def _indent_readme_excerpt(readme: str) -> str:
    return "\n".join(f"    {line}" for line in readme.splitlines())
