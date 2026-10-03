from pydantic import BaseModel, Field, field_validator


API_PROMPT_MAX_CHARS = 4000
API_HISTORY_MAX_TURNS = 10
API_HISTORY_MAX_CHARS = 24000
API_ASSISTANT_SUBJECT_MAX_CHARS = 120


class ConversationTurn(BaseModel):
    user: str
    assistant: str


class PromptRequest(BaseModel):
    prompt: str = Field(min_length=1)
    session_id: str | None = None
    history: list[ConversationTurn] = Field(default_factory=list)
    assistant_subject: str | None = None
    portfolio_context: str | None = None
    resume_path: str | None = None
    docs_path: str | None = None


class ApiPromptRequest(PromptRequest):
    """Public API input bounds; CLI requests retain their existing contract."""

    prompt: str = Field(min_length=1, max_length=API_PROMPT_MAX_CHARS)
    history: list[ConversationTurn] = Field(default_factory=list, max_length=API_HISTORY_MAX_TURNS)
    assistant_subject: str | None = Field(default=None, max_length=API_ASSISTANT_SUBJECT_MAX_CHARS)

    @field_validator("history")
    @classmethod
    def limit_history_text(cls, history: list[ConversationTurn]) -> list[ConversationTurn]:
        if sum(len(turn.user) + len(turn.assistant) for turn in history) > API_HISTORY_MAX_CHARS:
            raise ValueError(f"History text must not exceed {API_HISTORY_MAX_CHARS} characters.")
        return history


class PromptResponse(BaseModel):
    answer: str
    session_id: str | None = None
    history: list[ConversationTurn] = Field(default_factory=list)
    is_relevant: bool
    intent: str | None = None
    route: str | None = None
    retrieval_sources: list[str] = Field(default_factory=list)
    retrieval_reason: str | None = None
    retrieval_errors: list[str] = Field(default_factory=list)
    rewritten_query: str
    node_trace: list[str]
    suggested_prompts: list[str] = Field(default_factory=list)


class AuthSessionRequest(BaseModel):
    turnstile_token: str = Field(min_length=1)


class AuthSessionResponse(BaseModel):
    authenticated: bool
    refresh_expires_in: int


class AuthTokenResponse(BaseModel):
    access_token: str
    expires_in: int
