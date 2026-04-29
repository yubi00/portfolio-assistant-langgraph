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
    normalized = normalize_resume_text(content)
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
