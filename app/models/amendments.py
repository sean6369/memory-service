"""
Amendments schema — proposed company facts awaiting review.

Maps to Diagram 2: "schema: amendments — proposed company facts,
state, submitter, reviewer, decision"
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.postgres import Base


class CompanyCandidate(Base):
    __tablename__ = "company_candidates"
    __table_args__ = {"schema": "amendments"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    proposed_scope: Mapped[str | None] = mapped_column(String(255))
    state: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    # "pending", "approved", "rejected"
    submitter: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reviewer: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decision: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    # "user_submitted" or "auto_distilled"
    confidence: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
