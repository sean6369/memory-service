"""
Identity schema — users, team relationships, permissions.

Maps to Diagram 2: "schema: identity — users, job_function, department,
team relationships, supervisor links, permissions: which Qdrant collections"
"""

import uuid
from datetime import datetime

from sqlalchemy import String, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infra.postgres import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "identity"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    job_function: Mapped[str | None] = mapped_column(String(255))
    department: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    permissions: Mapped[list["Permission"]] = relationship(back_populates="user", lazy="selectin")


class TeamRelationship(Base):
    __tablename__ = "team_relationships"
    __table_args__ = {"schema": "identity"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False
    )
    related_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False
    )
    relationship: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "supervisor"


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = {"schema": "identity"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False
    )
    qdrant_collection: Mapped[str] = mapped_column(String(255), nullable=False)
    access: Mapped[str] = mapped_column(String(50), default="read")

    user: Mapped["User"] = relationship(back_populates="permissions")
