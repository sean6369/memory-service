"""
KB schema — approved company knowledge.

Maps to Diagram 2: "schema: kb — approved company knowledge,
document, chunk, permissions, version"
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Text, Integer, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infra.postgres import Base


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = {"schema": "kb"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    blob_uri: Mapped[str | None] = mapped_column(String(500))
    permissions: Mapped[str | None] = mapped_column(String(255))  # e.g. "company_all"
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    chunks: Mapped[list["Chunk"]] = relationship(back_populates="document", lazy="selectin")


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = {"schema": "kb"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kb.documents.id"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)

    document: Mapped["Document"] = relationship(back_populates="chunks")
