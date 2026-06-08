"""
Pydantic schemas for Conversation Persistence (Flow 2).
"""

from pydantic import BaseModel


class TurnRequest(BaseModel):
    user_id: str
    session_id: str
    participant: str  # "user" or "agent"
    content: str


class TurnResponse(BaseModel):
    session_id: str
    turn_index: int
    participant: str
    content: str


class EndSessionRequest(BaseModel):
    user_id: str


class EndSessionResponse(BaseModel):
    session_id: str
    conversation_id: str
    turns_persisted: int
    event_published: bool


# ── Chat (auto-generated assistant responses) ────────────────────────────────

class ChatRequest(BaseModel):
    user_id: str
    session_id: str
    message: str


class RetrievalDetail(BaseModel):
    """Metadata about the retrieval step during chat."""
    resolved_query: str
    query_type: str  # "episodic" or "semantic"
    reasoning_notes: str
    permitted_collections: list[str]


class ChatResponse(BaseModel):
    session_id: str
    assistant_message: str
    retrieved_items: list[dict]
    retrieval: RetrievalDetail | None = None
