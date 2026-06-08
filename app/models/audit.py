"""
Audit schema — append-only change log.

Maps to Diagram 2: "schema: audit — append-only change log,
who / when / before / after"

CRITICAL: This table is NEVER updated or deleted. Only INSERT operations.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.postgres import Base


class ChangeLog(Base):
    __tablename__ = "change_log"
    __table_args__ = {"schema": "audit"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    # e.g. "bullet.created", "candidate.approved", "candidate.rejected", "bullet.flagged"
    target_type: Mapped[str] = mapped_column(String(100), nullable=False)
    # e.g. "bullet", "company_candidate", "document"
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
