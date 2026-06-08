"""
Pydantic schemas for the Distillation Pipeline (Flow 3 / Diagram 3).

Each step (S1-S5) has its own output schema, used as structured LLM output.
"""

from pydantic import BaseModel


# ── S1: Signal Detection ─────────────────────────────────────────────────────

class Signal(BaseModel):
    """A detected signal from the conversation."""
    content: str
    category: str
    # Categories: "preference", "workflow_pattern", "tacit_heuristic",
    # "domain_fact", "constraint", "user_goal", "relationship"
    confidence_band: str  # "high", "medium", "low"
    evidence: str  # quote or reference from conversation


class S1Output(BaseModel):
    """Output of Step 1: Signal Detection."""
    signals: list[Signal]


# ── S2: Knowledge Extraction ─────────────────────────────────────────────────

class CandidateItem(BaseModel):
    """A candidate knowledge item extracted from a signal."""
    content: str
    type: str  # same categories as Signal.category
    provisional_scope: str  # "personal" or "team" or "company"


class S2Output(BaseModel):
    """Output of Step 2: Knowledge Extraction."""
    candidates: list[CandidateItem]


# ── S3: Personal vs Company ──────────────────────────────────────────────────

class TierClassification(BaseModel):
    """Tier classification for a candidate item."""
    content: str
    tier: str  # "user" or "company"
    reasoning: str


class S3Output(BaseModel):
    """Output of Step 3: Personal vs Company classification."""
    classifications: list[TierClassification]


# ── S4: Conflict Judgment ────────────────────────────────────────────────────

class ConflictJudgment(BaseModel):
    """Conflict judgment for a candidate vs existing items."""
    candidate_content: str
    judgment: str  # "conflict", "complement", "duplicate"
    explanation: str
    affected_item_id: str | None = None


class S4Output(BaseModel):
    """Output of Step 4: Conflict Judgment."""
    judgments: list[ConflictJudgment]


# ── S5: Confidence Finalization ──────────────────────────────────────────────

class ConfidenceScore(BaseModel):
    """Final confidence for a candidate item."""
    content: str
    tier: str  # "user" or "company"
    type: str
    final_confidence: int  # 1-5
    reasoning: str
    conflict_status: str  # "no_conflict", "complement", "conflict", "duplicate"


class S5Output(BaseModel):
    """Output of Step 5: Confidence Finalization."""
    scores: list[ConfidenceScore]
