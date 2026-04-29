from __future__ import annotations

import argparse
from pathlib import Path

from langchain_openai import OpenAIEmbeddings

from app.config import require_settings
from app.services.resume_rag import chunk_resume
from app.services.resume_vector_store import ResumeVectorStore


DEFAULT_RESUME_PATHS = (Path("data/resume.md"), Path("data/resume.pdf"))


def main() -> None:
    args = _parse_args()
    settings = require_settings()

    if not settings.neon_database_url_string:
        raise SystemExit("NEON_DATABASE_URL_STRING is required for offline resume indexing.")
    if not settings.openai_api_key:
        raise SystemExit("OPENAI_API_KEY is required for offline resume indexing.")

    resume_path = Path(args.resume_path) if args.resume_path else _find_default_resume_path()
    if not resume_path.exists() or not resume_path.is_file():
        raise SystemExit(f"Resume file not found: {resume_path}")
    if resume_path.suffix.lower() != ".md":
        raise SystemExit("Offline vector indexing currently expects a Markdown resume. Convert PDF first.")

    content = resume_path.read_text(encoding="utf-8")
    source = args.source or resume_path.as_posix()
    chunks = chunk_resume(
        content,
        source=source,
        max_chars=settings.resume_chunk_max_chars,
    )
    if not chunks:
        raise SystemExit("No resume chunks were produced.")

    print(f"resume index | source={source} | namespace={settings.resume_vector_namespace} | chunks={len(chunks)}")

    store = ResumeVectorStore(settings.neon_database_url_string)
    if not args.dry_run:
        store.ensure_schema()
        if not args.force and store.index_is_current(
            namespace=settings.resume_vector_namespace,
            source=source,
            full_content=content,
            chunks=chunks,
        ):
            print(
                "resume index complete | "
                f"inserted=0 | updated=0 | skipped={len(chunks)} | deleted=0 | document_changed=False"
            )
            return

    if args.dry_run:
        embeddings = [[0.0] * 1536 for _ in chunks]
    else:
        embedding_client = OpenAIEmbeddings(
            model=settings.openai_embedding_model,
            api_key=settings.openai_api_key,
        )
        embeddings = embedding_client.embed_documents([chunk.content for chunk in chunks])

    stats = store.index_chunks(
        namespace=settings.resume_vector_namespace,
        source=source,
        full_content=content,
        chunks=chunks,
        embeddings=embeddings,
        force=args.force,
        dry_run=args.dry_run,
    )
    mode = "dry-run" if args.dry_run else "complete"
    print(
        "resume index "
        f"{mode} | inserted={stats.inserted} | updated={stats.updated} | "
        f"skipped={stats.skipped} | deleted={stats.deleted} | "
        f"document_changed={stats.document_changed}"
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline index resume chunks into pgvector.")
    parser.add_argument("--resume-path", help="Markdown resume path. Defaults to data/resume.md.")
    parser.add_argument("--source", help="Stable source identifier stored with vector chunks.")
    parser.add_argument("--dry-run", action="store_true", help="Show expected DB changes without embedding or writing chunks.")
    parser.add_argument("--force", action="store_true", help="Re-embed and upsert all chunks even when hashes match.")
    return parser.parse_args()


def _find_default_resume_path() -> Path:
    for path in DEFAULT_RESUME_PATHS:
        if path.exists() and path.is_file():
            return path
    return DEFAULT_RESUME_PATHS[0]


if __name__ == "__main__":
    main()
