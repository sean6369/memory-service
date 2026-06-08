"""
Merge & Refine Worker — dedup + persist personal memory from Diagram 1.

Maps to Diagram 1:
  CU → MR (3c: personal memory)
  MR → PG (3e: persist bullets + provenance)
  MR → QD (3f: project vectors + content)

Responsibilities:
- Dedup/housekeeping before persist
- Write bullet to memory.bullets (Postgres)
- Project vector + content to user's Qdrant collection
"""

import logging
import uuid

from qdrant_client.models import PointStruct
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateways.llm_gateway import llm_gateway
from app.infra import qdrant
from app.models.memory import Bullet

logger = logging.getLogger(__name__)


def _user_collection(user_id: str) -> str:
    return f"user_{uuid.UUID(user_id).hex[:8]}"


class MergeRefineWorker:
    """Persists personal memory bullets to Postgres and Qdrant."""

    async def process(
        self,
        content: str,
        type: str,
        tier: str,
        confidence: int,
        status: str,
        user_id: str,
        source: str,
        session: AsyncSession,
    ) -> Bullet:
        """
        Steps 3e + 3f: Persist bullet to Postgres, project to Qdrant.
        """
        uid = uuid.UUID(user_id)

        # Step 3e: Persist bullet + provenance to memory.bullets (Postgres)
        bullet = Bullet(
            user_id=uid,
            content=content,
            type=type,
            tier=tier,
            confidence=confidence,
            status=status,
            authored_by="system",
            source=source,
        )
        session.add(bullet)
        await session.flush()

        logger.info(f"MergeRefineWorker: Persisted bullet {bullet.id} to Postgres")

        # Step 3f: Project vector + content to Qdrant
        collection = _user_collection(user_id)
        vectors = llm_gateway.embed([content])
        point = PointStruct(
            id=bullet.id.hex,
            vector=vectors[0],
            payload={
                "content": content,
                "type": "personal_bullet",
                "source_id": str(bullet.id),
                "user_id": user_id,
                "tier": tier,
                "bullet_type": type,
            },
        )
        qdrant.upsert_points(collection, [point])
        logger.info(f"MergeRefineWorker: Projected to Qdrant collection {collection}")

        await session.commit()
        return bullet


# Singleton
merge_refine_worker = MergeRefineWorker()
