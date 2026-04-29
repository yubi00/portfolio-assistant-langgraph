from app.services.resume_rag import chunk_resume, hash_text, normalize_resume_text


def test_normalize_resume_text_collapses_repeated_blank_lines():
    content = "# Resume\r\n\r\n\r\n  Backend engineer  \r\n\n\nAI systems"

    assert normalize_resume_text(content) == "# Resume\n\nBackend engineer\n\nAI systems"


def test_chunk_resume_splits_markdown_sections_deterministically():
    content = """# Resume

Yuba Raj Khadka

## Experience

Built AI systems.

## Education

Master of Information Technology.
"""

    chunks = chunk_resume(content, source="data/resume.md", max_chars=1200)

    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2]
    assert chunks[0].source == "data/resume.md"
    assert chunks[0].content.startswith("# Resume")
    assert chunks[1].content.startswith("## Experience")
    assert chunks[2].content.startswith("## Education")
    assert chunks[1].content_hash == hash_text(chunks[1].content)


def test_chunk_resume_splits_large_sections_without_losing_words():
    content = "# Resume\n\n" + " ".join(f"word{i}" for i in range(80))

    chunks = chunk_resume(content, source="resume", max_chars=120)

    assert len(chunks) > 1
    joined = " ".join(chunk.content for chunk in chunks)
    assert "word0" in joined
    assert "word79" in joined
