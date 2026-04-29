from app.services.resume_rag import chunk_resume, hash_text, normalize_resume_text, semantic_resume_markdown


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


def test_semantic_resume_markdown_promotes_plain_resume_labels():
    content = """# Resume

## Page 1

PROFILE
Backend engineer.
CORE SKILLS
Languages: TypeScript, Python
SELECTED AI PROJECTS
MatchCast — AI Audio Analysis System
Built audio analysis.

## Page 2

EXPERIENCE
AI Engineer — Future Secure AI (Apr 2026 – Present)
Built agent systems.
EDUCATION
Master of Information Technology — La Trobe University
CERTIFICATIONS
AWS Certified Developer – Associate
"""

    markdown = semantic_resume_markdown(normalize_resume_text(content))

    assert "## Page 1" not in markdown
    assert "## Profile" in markdown
    assert "## Core Skills" in markdown
    assert "## Selected AI Projects" in markdown
    assert "### MatchCast — AI Audio Analysis System" in markdown
    assert "## Experience" in markdown
    assert "### AI Engineer — Future Secure AI (Apr 2026 – Present)" in markdown
    assert "## Education" in markdown
    assert "### Master of Information Technology" not in markdown
    assert "## Certifications" in markdown


def test_chunk_resume_uses_semantic_sections_for_raw_resume_text():
    content = """# Resume

PROFILE
Backend engineer.
EXPERIENCE
AI Engineer — Future Secure AI (Apr 2026 – Present)
Built agent systems.
EDUCATION
Master of Information Technology — La Trobe University
"""

    chunks = chunk_resume(content, source="data/resume.md", max_chars=1200)

    assert any(chunk.content.startswith("## Profile") for chunk in chunks)
    assert any(chunk.content.startswith("## Experience") for chunk in chunks)
    assert any(chunk.content.startswith("### AI Engineer") for chunk in chunks)
    education_chunk = next(chunk for chunk in chunks if chunk.content.startswith("## Education"))
    assert "Master of Information Technology" in education_chunk.content
