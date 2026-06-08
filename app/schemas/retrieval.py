"""
Pydantic schemas for the Retrieval Engine (Flow 1).
"""

from pydantic import BaseModel


class QueryRequest(BaseModel):
    user_id: str
    query: str
    semantic_context: str | None = None  # Injected by Semantic Engine (SE → RE sync)


class ResolvedQuery(BaseModel):
    """Output schema for the LLM reasoning step (1a)."""
    query_type: str  # "episodic" or "semantic"
    resolved_query: str
    notes: str


class RetrievedItem(BaseModel):
    content: str
    score: float
    type: str  # "personal_bullet", "company_fact", "episodic", "kb_chunk"
    source_id: str | None = None
    collection: str | None = None
    # Provenance fields (from on-demand provenance lookup: RET → MEM)
    authored_by: str | None = None
    source: str | None = None
    confidence: int | None = None
    status: str | None = None


class QueryResponse(BaseModel):
    original_query: str
    resolved_query: ResolvedQuery
    items: list[RetrievedItem]
    permitted_collections: list[str]
