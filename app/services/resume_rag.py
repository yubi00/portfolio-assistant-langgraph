from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ResumeChunk:
    source: str
    chunk_index: int
    content: str
    content_hash: str


def chunk_resume(content: str, *, source: str, max_chars: int = 1200) -> list[ResumeChunk]:
    """Split resume Markdown/text into deterministic chunks for vector indexing."""
    normalized = semantic_resume_markdown(normalize_resume_text(content))
    if not normalized:
        return []

    chunks: list[str] = []
    for section in _split_markdown_sections(normalized):
        chunks.extend(_split_large_section(section, max_chars=max_chars))

    return [
        ResumeChunk(
            source=source,
            chunk_index=index,
            content=chunk,
            content_hash=hash_text(chunk),
        )
        for index, chunk in enumerate(chunks)
    ]


def normalize_resume_text(content: str) -> str:
    lines = [line.rstrip() for line in content.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    normalized_lines: list[str] = []
    previous_blank = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if not previous_blank:
                normalized_lines.append("")
            previous_blank = True
            continue
        normalized_lines.append(stripped)
        previous_blank = False
    return "\n".join(normalized_lines).strip()


def semantic_resume_markdown(content: str) -> str:
    """Promote common resume labels into Markdown headings for better retrieval chunks."""
    lines = content.splitlines()
    output: list[str] = []
    current_section: str | None = None
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            output.append("")
            continue
        if _is_page_heading(line):
            continue
        if line.startswith("#"):
            output.append(line)
            continue
        if section_heading := _semantic_section_heading(line):
            current_section = section_heading
            output.extend(_with_heading_spacing(output, f"## {section_heading}"))
            continue
        if subsection_heading := _semantic_subsection_heading(line, current_section):
            output.extend(_with_heading_spacing(output, f"### {subsection_heading}"))
            continue
        output.append(line)

    return normalize_resume_text("\n".join(output))


def hash_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _split_markdown_sections(content: str) -> list[str]:
    sections: list[list[str]] = []
    current: list[str] = []
    for line in content.splitlines():
        if line.startswith("#") and current:
            sections.append(current)
            current = [line]
            continue
        current.append(line)
    if current:
        sections.append(current)
    return ["\n".join(section).strip() for section in sections if "\n".join(section).strip()]


SECTION_LABELS = {
    "PROFILE": "Profile",
    "CORE SKILLS": "Core Skills",
    "SELECTED AI PROJECTS": "Selected AI Projects",
    "EXPERIENCE": "Experience",
    "EDUCATION": "Education",
    "CERTIFICATIONS": "Certifications",
}
SUBSECTION_SECTIONS = {"Selected AI Projects", "Experience"}
SUBSECTION_PATTERNS = {
    "Selected AI Projects": re.compile(r"^[A-Z][A-Za-z0-9 .()/+-]+(?:—|-|–|â€”|â€“)\s+[A-Za-z0-9].+"),
    "Experience": re.compile(r"^[A-Z][A-Za-z0-9 .()/+-]+(?:—|-|–|â€”|â€“)\s+[A-Za-z0-9].+"),
}


def _is_page_heading(line: str) -> bool:
    return bool(re.fullmatch(r"##\s+Page\s+\d+", line, flags=re.IGNORECASE))


def _semantic_section_heading(line: str) -> str | None:
    return SECTION_LABELS.get(line.upper())


def _semantic_subsection_heading(line: str, current_section: str | None) -> str | None:
    if current_section not in SUBSECTION_SECTIONS or ":" in line:
        return None
    pattern = SUBSECTION_PATTERNS[current_section]
    if pattern.match(line):
        return line
    return None


def _with_heading_spacing(existing_lines: list[str], heading: str) -> list[str]:
    spacing = []
    if existing_lines and existing_lines[-1] != "":
        spacing.append("")
    spacing.append(heading)
    spacing.append("")
    return spacing


def _split_large_section(section: str, *, max_chars: int) -> list[str]:
    if len(section) <= max_chars:
        return [section]

    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", section) if paragraph.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if not current:
            current = paragraph
            continue
        candidate = f"{current}\n\n{paragraph}"
        if len(candidate) <= max_chars:
            current = candidate
            continue
        chunks.extend(_split_oversized_text(current, max_chars=max_chars))
        current = paragraph
    if current:
        chunks.extend(_split_oversized_text(current, max_chars=max_chars))
    return chunks


def _split_oversized_text(text: str, *, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    words = text.split()
    current_words: list[str] = []
    for word in words:
        candidate_words = [*current_words, word]
        candidate = " ".join(candidate_words)
        if len(candidate) <= max_chars:
            current_words = candidate_words
            continue
        if current_words:
            chunks.append(" ".join(current_words))
        current_words = [word]
    if current_words:
        chunks.append(" ".join(current_words))
    return chunks
