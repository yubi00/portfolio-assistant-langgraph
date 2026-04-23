from pydantic import BaseModel, Field


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
