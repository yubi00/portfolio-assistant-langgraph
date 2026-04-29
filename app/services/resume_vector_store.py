from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterable
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from app.services.resume_rag import ResumeChunk, hash_text


EMBEDDING_DIMENSIONS = 1536


SCHEMA_SQL = f"""
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS resume_documents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    namespace text NOT NULL,
    source text NOT NULL,
    content_hash text NOT NULL,
    indexed_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (namespace, source)
);

CREATE TABLE IF NOT EXISTS resume_chunks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id uuid NOT NULL REFERENCES resume_documents(id) ON DELETE CASCADE,
    namespace text NOT NULL,
    source text NOT NULL,
    chunk_index integer NOT NULL,
    content text NOT NULL,
    content_hash text NOT NULL,
    embedding vector({EMBEDDING_DIMENSIONS}) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (namespace, source, chunk_index)
);

CREATE INDEX IF NOT EXISTS resume_chunks_namespace_source_idx
ON resume_chunks (namespace, source);

CREATE INDEX IF NOT EXISTS resume_chunks_embedding_idx
ON resume_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
"""


@dataclass(frozen=True)
class IndexStats:
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    deleted: int = 0
    document_changed: bool = False


@dataclass(frozen=True)
class RetrievedChunk:
    content: str
    source: str
    chunk_index: int
    distance: float


class ResumeVectorStore:
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(SCHEMA_SQL)

    def index_is_current(
        self,
        *,
        namespace: str,
        source: str,
        full_content: str,
        chunks: list[ResumeChunk],
    ) -> bool:
        document_hash = hash_text(full_content)
        with self._connect() as conn:
            document = _get_document(conn, namespace=namespace, source=source)
            if document is None or document["content_hash"] != document_hash:
                return False

            existing_hashes = _get_chunk_hashes(conn, namespace=namespace, source=source)
            return _all_chunks_unchanged(chunks, existing_hashes)

    def index_chunks(
        self,
        *,
        namespace: str,
        source: str,
        full_content: str,
        chunks: list[ResumeChunk],
        embeddings: list[list[float]],
        force: bool = False,
        dry_run: bool = False,
    ) -> IndexStats:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length.")

        document_hash = hash_text(full_content)
        now = datetime.now(UTC)

        with self._connect() as conn:
            with conn.transaction():
                document = _get_document(conn, namespace=namespace, source=source)
                document_changed = document is None or document["content_hash"] != document_hash

                if document and not document_changed and not force:
                    existing_hashes = _get_chunk_hashes(conn, namespace=namespace, source=source)
                    if _all_chunks_unchanged(chunks, existing_hashes):
                        return IndexStats(skipped=len(chunks), document_changed=False)

                if dry_run:
                    existing_hashes = _get_chunk_hashes(conn, namespace=namespace, source=source)
                    return _dry_run_stats(
                        chunks=chunks,
                        existing_hashes=existing_hashes,
                        document_changed=document_changed,
                    )

                document_id = _upsert_document(
                    conn,
                    namespace=namespace,
                    source=source,
                    content_hash=document_hash,
                    indexed_at=now,
                )

                stats = IndexStats(document_changed=document_changed)
                seen_indexes: set[int] = set()
                existing_hashes = _get_chunk_hashes(conn, namespace=namespace, source=source)

                for chunk, embedding in zip(chunks, embeddings, strict=True):
                    seen_indexes.add(chunk.chunk_index)
                    existing_hash = existing_hashes.get(chunk.chunk_index)
                    if existing_hash == chunk.content_hash and not force:
                        stats = _add_stats(stats, skipped=1)
                        continue

                    vector = _format_vector(embedding)
                    _upsert_chunk(
                        conn,
                        document_id=document_id,
                        namespace=namespace,
                        source=source,
                        chunk=chunk,
                        vector=vector,
                    )
                    if existing_hash is None:
                        stats = _add_stats(stats, inserted=1)
                    else:
                        stats = _add_stats(stats, updated=1)

                deleted = _delete_stale_chunks(
                    conn,
                    namespace=namespace,
                    source=source,
                    active_indexes=seen_indexes,
                )
                return _add_stats(stats, deleted=deleted)

    def search(self, *, namespace: str, query_embedding: list[float], limit: int = 5) -> list[RetrievedChunk]:
        vector = _format_vector(query_embedding)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT content, source, chunk_index, embedding <=> %s::vector AS distance
                FROM resume_chunks
                WHERE namespace = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (vector, namespace, vector, limit),
            ).fetchall()

        return [
            RetrievedChunk(
                content=row["content"],
                source=row["source"],
                chunk_index=row["chunk_index"],
                distance=float(row["distance"]),
            )
            for row in rows
        ]

    def _connect(self):
        return psycopg.connect(self._database_url, row_factory=dict_row)


def _get_document(conn, *, namespace: str, source: str) -> dict | None:
    return conn.execute(
        """
        SELECT id, content_hash
        FROM resume_documents
        WHERE namespace = %s AND source = %s
        """,
        (namespace, source),
    ).fetchone()


def _upsert_document(conn, *, namespace: str, source: str, content_hash: str, indexed_at: datetime) -> UUID:
    row = conn.execute(
        """
        INSERT INTO resume_documents (namespace, source, content_hash, indexed_at, updated_at)
        VALUES (%s, %s, %s, %s, now())
        ON CONFLICT (namespace, source)
        DO UPDATE SET content_hash = EXCLUDED.content_hash, indexed_at = EXCLUDED.indexed_at, updated_at = now()
        RETURNING id
        """,
        (namespace, source, content_hash, indexed_at),
    ).fetchone()
    return row["id"]


def _get_chunk_hashes(conn, *, namespace: str, source: str) -> dict[int, str]:
    rows = conn.execute(
        """
        SELECT chunk_index, content_hash
        FROM resume_chunks
        WHERE namespace = %s AND source = %s
        """,
        (namespace, source),
    ).fetchall()
    return {row["chunk_index"]: row["content_hash"] for row in rows}


def _upsert_chunk(
    conn,
    *,
    document_id: UUID,
    namespace: str,
    source: str,
    chunk: ResumeChunk,
    vector: str,
) -> None:
    conn.execute(
        """
        INSERT INTO resume_chunks (
            document_id, namespace, source, chunk_index, content, content_hash, embedding, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s::vector, now())
        ON CONFLICT (namespace, source, chunk_index)
        DO UPDATE SET
            document_id = EXCLUDED.document_id,
            content = EXCLUDED.content,
            content_hash = EXCLUDED.content_hash,
            embedding = EXCLUDED.embedding,
            updated_at = now()
        """,
        (
            document_id,
            namespace,
            source,
            chunk.chunk_index,
            chunk.content,
            chunk.content_hash,
            vector,
        ),
    )


def _delete_stale_chunks(conn, *, namespace: str, source: str, active_indexes: Iterable[int]) -> int:
    active_indexes = list(active_indexes)
    if not active_indexes:
        result = conn.execute(
            "DELETE FROM resume_chunks WHERE namespace = %s AND source = %s",
            (namespace, source),
        )
        return result.rowcount or 0

    result = conn.execute(
        """
        DELETE FROM resume_chunks
        WHERE namespace = %s AND source = %s AND NOT (chunk_index = ANY(%s))
        """,
        (namespace, source, active_indexes),
    )
    return result.rowcount or 0


def _all_chunks_unchanged(chunks: list[ResumeChunk], existing_hashes: dict[int, str]) -> bool:
    if len(chunks) != len(existing_hashes):
        return False
    return all(existing_hashes.get(chunk.chunk_index) == chunk.content_hash for chunk in chunks)


def _dry_run_stats(
    *,
    chunks: list[ResumeChunk],
    existing_hashes: dict[int, str],
    document_changed: bool,
) -> IndexStats:
    inserted = 0
    updated = 0
    skipped = 0
    seen_indexes: set[int] = set()
    for chunk in chunks:
        seen_indexes.add(chunk.chunk_index)
        existing_hash = existing_hashes.get(chunk.chunk_index)
        if existing_hash is None:
            inserted += 1
        elif existing_hash == chunk.content_hash:
            skipped += 1
        else:
            updated += 1
    deleted = len(set(existing_hashes) - seen_indexes)
    return IndexStats(
        inserted=inserted,
        updated=updated,
        skipped=skipped,
        deleted=deleted,
        document_changed=document_changed,
    )


def _add_stats(
    stats: IndexStats,
    *,
    inserted: int = 0,
    updated: int = 0,
    skipped: int = 0,
    deleted: int = 0,
) -> IndexStats:
    return IndexStats(
        inserted=stats.inserted + inserted,
        updated=stats.updated + updated,
        skipped=stats.skipped + skipped,
        deleted=stats.deleted + deleted,
        document_changed=stats.document_changed,
    )


def _format_vector(values: list[float]) -> str:
    if len(values) != EMBEDDING_DIMENSIONS:
        raise ValueError(f"Expected embedding dimension {EMBEDDING_DIMENSIONS}, got {len(values)}.")
    return "[" + ",".join(str(value) for value in values) + "]"
