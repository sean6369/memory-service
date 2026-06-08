"""
Reset and reseed the database + Qdrant.

Drops all tables, recreates schemas, and runs the seed script.
Usage: python reset_and_seed.py
"""

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
from app.db.seed import seed_all

SCHEMAS = ["identity", "episodic", "memory", "amendments", "kb", "audit"]


async def reset_and_seed():
    print("Dropping all tables...")
    engine = create_async_engine(settings.postgres_dsn)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        for schema in SCHEMAS:
            await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print("Tables reset.\n")

    print("Seeding data...")
    await seed_all()


if __name__ == "__main__":
    asyncio.run(reset_and_seed())
