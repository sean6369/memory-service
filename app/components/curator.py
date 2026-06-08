"""
Curator — routes distilled items by tier from Diagram 1/3.

Maps to Diagram 1: RF → CU → MR (3c: personal) / AM (3d: company candidate)
Maps to Diagram 3: ROUTE → OUT_MEM (personal) / OUT_AMD (company)

Two routing paths:
- tier="user" → MergeRefineWorker → memory.bullets (PG) + Qdrant projection
- tier="company" → AmendmentService as auto-distilled candidate
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.components.merge_refine_worker import merge_refine_worker
from app.schemas.distillation import ConfidenceScore

logger = logging.getLogger(__name__)


class Curator:
    """Routes items by tier and applies status gating based on confidence."""

    async def route(
        self,
        scores: list[ConfidenceScore],
        user_id: str,
        conversation_id: str,
        session: AsyncSession,
    ) -> None:
        """
        Route each scored item to the appropriate handler.

        Status gating (on final confidence):
          5 or 4 → active immediately
          3 or 2 → candidate (needs corroboration)
          1 → drop (unless corroborated)
        """
        for score in scores:
            # Determine status from confidence
            if score.final_confidence >= 4:
                status = "active"
            elif score.final_confidence >= 2:
                status = "candidate"
            else:
                status = "dropped"
                logger.info(f"Curator: Dropping item (confidence=1): {score.content[:50]}...")
                continue

            # Skip duplicates
            if score.conflict_status == "duplicate":
                logger.info(f"Curator: Skipping duplicate: {score.content[:50]}...")
                continue

            if score.tier == "user":
                # Personal → Merge & Refine Worker
                logger.info(f"Curator: Routing personal item (conf={score.final_confidence}, status={status}): {score.content[:50]}...")
                await merge_refine_worker.process(
                    content=score.content,
                    type=score.type,
                    tier="personal",
                    confidence=score.final_confidence,
                    status=status,
                    user_id=user_id,
                    source=conversation_id,
                    session=session,
                )
            elif score.tier == "company":
                # Company → Amendment Service (lazy import to avoid circular)
                logger.info(f"Curator: Routing company candidate (conf={score.final_confidence}): {score.content[:50]}...")
                from app.components.amendment_service import amendment_service
                await amendment_service.create_auto_distilled_candidate(
                    content=score.content,
                    type=score.type,
                    confidence=score.final_confidence,
                    submitter_id=user_id,
                    session=session,
                )


# Singleton
curator = Curator()
