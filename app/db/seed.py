"""
Seed data for the Memory Service MVP demo.

Creates 3 users with differing permissions and ~25 hand-authored
personal bullets + company facts, projected into the correct Qdrant collections.
"""

import asyncio
import uuid

from qdrant_client.models import PointStruct
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings
from app.gateways.llm_gateway import llm_gateway
from app.infra import qdrant
from app.infra.postgres import Base
from app.models.identity import User, TeamRelationship, Permission
from app.models.memory import Bullet
from app.models.kb import Document, Chunk

# Fixed UUIDs for reproducibility
USER_A_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
USER_B_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
USER_C_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")  # supervisor

COMPANY_COLLECTION = "company_shared"


def _user_collection(user_id: uuid.UUID) -> str:
    return f"user_{user_id.hex[:8]}"


# ── Personal bullets for User A ──────────────────────────────────────────────
USER_A_BULLETS = [
    {"content": "Prefers oat milk latte from Bean Counter cafe", "type": "preference", "confidence": 5},
    {"content": "Always uses dark mode in all applications", "type": "preference", "confidence": 5},
    {"content": "Writes Python code with type hints; prefers FastAPI over Flask", "type": "workflow_pattern", "confidence": 4},
    {"content": "Starts the day by reviewing Jira board before standup", "type": "workflow_pattern", "confidence": 4},
    {"content": "Prefers bullet-point summaries over paragraph form", "type": "preference", "confidence": 5},
    {"content": "Working on the Memory Service project for Q3 deadline", "type": "user_goal", "confidence": 5},
    {"content": "Reports to Charlie (supervisor) in the AI Platform team", "type": "relationship", "confidence": 5},
    {"content": "Allergic to shellfish — relevant for team lunch orders", "type": "constraint", "confidence": 5},
    {"content": "Uses VS Code with Vim keybindings", "type": "preference", "confidence": 4},
    {"content": "Prefers async/await patterns over threading for concurrency", "type": "tacit_heuristic", "confidence": 4},
]

# ── Personal bullets for User B ──────────────────────────────────────────────
USER_B_BULLETS = [
    {"content": "Drinks black coffee, no sugar", "type": "preference", "confidence": 5},
    {"content": "Frontend developer specializing in React and TypeScript", "type": "domain_fact", "confidence": 5},
    {"content": "Prefers Figma links over verbal design descriptions", "type": "workflow_pattern", "confidence": 4},
    {"content": "Works from home on Wednesdays and Fridays", "type": "constraint", "confidence": 5},
    {"content": "Currently focused on the admin dashboard redesign", "type": "user_goal", "confidence": 4},
    {"content": "Supervised by Charlie in the AI Platform team", "type": "relationship", "confidence": 5},
    {"content": "Prefers morning meetings, avoids afternoons for deep work", "type": "preference", "confidence": 4},
    {"content": "Uses a standing desk setup with ultrawide monitor", "type": "preference", "confidence": 3},
]

# ── Company knowledge (approved facts in KB) ─────────────────────────────────
COMPANY_FACTS = [
    {"content": "Company uses PostgreSQL as the primary database for all production services", "type": "domain_fact"},
    {"content": "Deployment pipeline: GitHub PR → CI/CD → staging → production with manual approval gate", "type": "workflow_pattern"},
    {"content": "Team standup is daily at 10:00 AM SGT in the #standup Slack channel", "type": "constraint"},
    {"content": "AI Platform team consists of 8 engineers across backend, frontend, and ML", "type": "domain_fact"},
    {"content": "All API endpoints must use JWT authentication with the company auth service", "type": "constraint"},
    {"content": "Code reviews require at least one approval from a senior engineer before merge", "type": "constraint"},
    {"content": "The company holiday party is in December; team budget is $50 per person", "type": "domain_fact"},
]


async def seed_all():
    """Run the full seed: users, permissions, bullets, KB, Qdrant projections."""
    engine = create_async_engine(settings.postgres_dsn)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        async with session.begin():
            # ── Users ────────────────────────────────────────────
            alice = User(id=USER_A_ID, display_name="Alice", job_function="Backend Engineer", department="AI Platform")
            bob = User(id=USER_B_ID, display_name="Bob", job_function="Frontend Engineer", department="AI Platform")
            charlie = User(id=USER_C_ID, display_name="Charlie", job_function="Engineering Manager", department="AI Platform")
            session.add_all([alice, bob, charlie])
            await session.flush()  # commit users before FK references

            # ── Team relationships ───────────────────────────────
            session.add(TeamRelationship(user_id=USER_A_ID, related_user_id=USER_C_ID, relationship="supervisor"))
            session.add(TeamRelationship(user_id=USER_B_ID, related_user_id=USER_C_ID, relationship="supervisor"))
            await session.flush()  # commit relationships before permissions

            # ── Permissions ──────────────────────────────────────
            # Alice can read her own collection + company shared
            session.add(Permission(user_id=USER_A_ID, qdrant_collection=_user_collection(USER_A_ID), access="read"))
            session.add(Permission(user_id=USER_A_ID, qdrant_collection=COMPANY_COLLECTION, access="read"))

            # Bob can read his own collection + company shared
            session.add(Permission(user_id=USER_B_ID, qdrant_collection=_user_collection(USER_B_ID), access="read"))
            session.add(Permission(user_id=USER_B_ID, qdrant_collection=COMPANY_COLLECTION, access="read"))

            # Charlie (supervisor) can read all collections
            session.add(Permission(user_id=USER_C_ID, qdrant_collection=_user_collection(USER_A_ID), access="read"))
            session.add(Permission(user_id=USER_C_ID, qdrant_collection=_user_collection(USER_B_ID), access="read"))
            session.add(Permission(user_id=USER_C_ID, qdrant_collection=COMPANY_COLLECTION, access="read"))

            # ── Personal bullets ─────────────────────────────────
            a_bullets = []
            for b in USER_A_BULLETS:
                bullet = Bullet(
                    user_id=USER_A_ID,
                    content=b["content"],
                    type=b["type"],
                    tier="personal",
                    confidence=b["confidence"],
                    status="active",
                    authored_by="seed",
                    source="manual",
                )
                session.add(bullet)
                a_bullets.append(bullet)

            b_bullets = []
            for b in USER_B_BULLETS:
                bullet = Bullet(
                    user_id=USER_B_ID,
                    content=b["content"],
                    type=b["type"],
                    tier="personal",
                    confidence=b["confidence"],
                    status="active",
                    authored_by="seed",
                    source="manual",
                )
                session.add(bullet)
                b_bullets.append(bullet)

            # ── KB documents + chunks (company facts) ─────────────
            doc = Document(title="Company Knowledge Base", permissions="company_all")
            session.add(doc)
            await session.flush()  # get doc.id

            kb_chunks = []
            for fact in COMPANY_FACTS:
                chunk = Chunk(document_id=doc.id, content=fact["content"])
                session.add(chunk)
                kb_chunks.append(chunk)

            await session.flush()  # get all IDs

    # ── Project to Qdrant ────────────────────────────────────────
    print("Embedding and projecting to Qdrant...")

    # Embed all content
    all_texts = (
        [b.content for b in a_bullets]
        + [b.content for b in b_bullets]
        + [c.content for c in kb_chunks]
    )
    all_vectors = llm_gateway.embed(all_texts)

    idx = 0

    # User A personal bullets → user_A collection
    a_collection = _user_collection(USER_A_ID)
    qdrant.delete_collection(a_collection)
    a_points = []
    for bullet in a_bullets:
        a_points.append(PointStruct(
            id=bullet.id.hex,
            vector=all_vectors[idx],
            payload={
                "content": bullet.content,
                "type": f"personal_bullet",
                "source_id": str(bullet.id),
                "user_id": str(USER_A_ID),
                "tier": "personal",
                "bullet_type": bullet.type,
            },
        ))
        idx += 1
    qdrant.upsert_points(a_collection, a_points)
    print(f"  → {len(a_points)} points in {a_collection}")

    # User B personal bullets → user_B collection
    b_collection = _user_collection(USER_B_ID)
    qdrant.delete_collection(b_collection)
    b_points = []
    for bullet in b_bullets:
        b_points.append(PointStruct(
            id=bullet.id.hex,
            vector=all_vectors[idx],
            payload={
                "content": bullet.content,
                "type": f"personal_bullet",
                "source_id": str(bullet.id),
                "user_id": str(USER_B_ID),
                "tier": "personal",
                "bullet_type": bullet.type,
            },
        ))
        idx += 1
    qdrant.upsert_points(b_collection, b_points)
    print(f"  → {len(b_points)} points in {b_collection}")

    # Company facts → company_shared collection
    qdrant.delete_collection(COMPANY_COLLECTION)
    c_points = []
    for chunk in kb_chunks:
        c_points.append(PointStruct(
            id=chunk.id.hex,
            vector=all_vectors[idx],
            payload={
                "content": chunk.content,
                "type": "company_fact",
                "source_id": str(chunk.id),
                "tier": "company",
            },
        ))
        idx += 1
    qdrant.upsert_points(COMPANY_COLLECTION, c_points)
    print(f"  → {len(c_points)} points in {COMPANY_COLLECTION}")

    await engine.dispose()
    print("\nSeed completed successfully!")
    print(f"  Users: Alice ({USER_A_ID}), Bob ({USER_B_ID}), Charlie ({USER_C_ID})")
    print(f"  Alice bullets: {len(a_bullets)}, Bob bullets: {len(b_bullets)}, Company facts: {len(kb_chunks)}")


if __name__ == "__main__":
    asyncio.run(seed_all())
