"""
Database initialization — creates all schemas and tables.

Uses raw SQL to create the 6 PostgreSQL schemas, then lets SQLAlchemy
create the tables. This approach is simpler than Alembic for the MVP
while still creating the exact schema structure from Diagram 2.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.infra.postgres import Base

# Import all models so Base.metadata knows about them
from app.models import (  # noqa: F401
    User, TeamRelationship, Permission,
    Conversation, Turn,
    Bullet,
    CompanyCandidate,
    Document, Chunk,
    ChangeLog,
)

SCHEMAS = ["identity", "episodic", "memory", "amendments", "kb", "audit"]


async def init_db() -> None:
    """Create all schemas and tables."""
    engine = create_async_engine(settings.postgres_dsn, echo=True)

    async with engine.begin() as conn:
        # Create schemas
        for schema in SCHEMAS:
            await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))

        # Create all tables
        await conn.run_sync(Base.metadata.create_all)

    await engine.dispose()
    print("Database initialized successfully.")


if __name__ == "__main__":
    asyncio.run(init_db())
