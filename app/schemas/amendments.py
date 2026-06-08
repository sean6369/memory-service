"""
Pydantic schemas for the Amendment Workflow (Flow 4).
"""

from datetime import datetime
from pydantic import BaseModel


class CreateAmendmentRequest(BaseModel):
    """User-submitted company fact candidate."""
    content: str
    type: str
    proposed_scope: str = "company"
    submitter_id: str


class ApproveAmendmentRequest(BaseModel):
    """Approve a pending candidate."""
    reviewer_id: str


class RejectAmendmentRequest(BaseModel):
    """Reject a pending candidate."""
    reviewer_id: str
    decision: str  # reason for rejection


class AmendmentResponse(BaseModel):
    """Response for a single company candidate."""
    id: str
    content: str
    type: str
    proposed_scope: str
    state: str
    submitter: str
    reviewer: str | None = None
    decision: str | None = None
    source: str
    confidence: int | None = None
    created_at: datetime | None = None
    decided_at: datetime | None = None


class AmendmentListResponse(BaseModel):
    """Response for listing candidates."""
    candidates: list[AmendmentResponse]
    total: int
