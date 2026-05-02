from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.errors import AppError
from app.graph.state import ConversationTurnState


class SessionStoreError(AppError):
    """Base session store error."""


class SessionNotFoundError(SessionStoreError):
    """Raised when a session id is unknown or expired."""

    status_code = 404
    code = "SESSION_NOT_FOUND"
    default_message = "Session was not found or has expired."


@dataclass
class SessionRecord:
    history: list[ConversationTurnState] = field(default_factory=list)
    last_accessed_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class InMemorySessionStore:
    """Small in-memory session store for Phase 6 API memory."""

    def __init__(self, max_history_turns: int, ttl_minutes: int) -> None:
        self._max_history_turns = max_history_turns
        self._ttl = timedelta(minutes=ttl_minutes)
        self._sessions: dict[str, SessionRecord] = {}

    def create_session(self) -> str:
        self._evict_expired_sessions()
        session_id = str(uuid4())
        self._sessions[session_id] = SessionRecord()
        return session_id

    def get_history(self, session_id: str) -> list[ConversationTurnState]:
        session = self._get_session(session_id)
        return [turn.copy() for turn in session.history]

    def append_turn(self, session_id: str, user: str, assistant: str) -> None:
        session = self._get_session(session_id)
        session.history.append({"user": user, "assistant": assistant})
        if len(session.history) > self._max_history_turns:
            session.history = session.history[-self._max_history_turns :]

    def set_history(self, session_id: str, history: list[ConversationTurnState]) -> None:
        session = self._get_session(session_id)
        session.history = list(history)[-self._max_history_turns :]

    def _get_session(self, session_id: str) -> SessionRecord:
        self._evict_expired_sessions()
        session = self._sessions.get(session_id)
        if session is None:
            raise SessionNotFoundError(f"Session {session_id!r} was not found or has expired.")

        session.last_accessed_at = datetime.now(UTC)
        return session

    def _evict_expired_sessions(self) -> None:
        now = datetime.now(UTC)
        expired_session_ids = [
            session_id
            for session_id, session in self._sessions.items()
            if now - session.last_accessed_at > self._ttl
        ]
        for session_id in expired_session_ids:
            del self._sessions[session_id]
