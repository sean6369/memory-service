"""
Memory schema (provenance) — bullet metadata.

Maps to Diagram 2: "schema: memory (provenance) — bullet metadata: authored_by,
source, supersession chain, confidence, status + helpful/harmful counts"
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Text, Integer, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.postgres import Base


class Bullet(Base):
    __tablename__ = "bullets"
    __table_args__ = {"schema": "memory"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    # "preference", "workflow_pattern", "tacit_heuristic", "domain_fact",
    # "constraint", "user_goal", "relationship"
    tier: Mapped[str] = mapped_column(String(50), nullable=False)  # "personal" or "company"
    confidence: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    # "active", "candidate", "dropped", "flagged_for_review"
    authored_by: Mapped[str] = mapped_column(String(255), nullable=False)  # "system" or user display
    source: Mapped[str | None] = mapped_column(Text)  # conversation id or "manual"
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("memory.bullets.id")
    )
    helpful_count: Mapped[int] = mapped_column(Integer, default=0)
    harmful_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
