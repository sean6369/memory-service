"""
Episodic schema — conversations stored wholesale at session end.

Maps to Diagram 2: "schema: episodic — conversations stored wholesale,
turns, participants, timestamps, keyed by user + time + topic"
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Text, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infra.postgres import Base


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = {"schema": "episodic"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    topic: Mapped[str | None] = mapped_column(String(500))

    turns: Mapped[list["Turn"]] = relationship(
        back_populates="conversation", lazy="selectin", order_by="Turn.ts"
    )


class Turn(Base):
    __tablename__ = "turns"
    __table_args__ = {"schema": "episodic"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("episodic.conversations.id"), nullable=False
    )
    participant: Mapped[str] = mapped_column(String(100), nullable=False)  # "user" or "agent"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped["Conversation"] = relationship(back_populates="turns")
