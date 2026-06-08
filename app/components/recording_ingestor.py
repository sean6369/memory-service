"""
Recording Ingestor — Flow 3 entry point from Diagram 1/3.

Maps to Diagram 1: KAFKA → RI (3: agent.run.completed)
Maps to Diagram 3: Trigger → Recording Ingestor → Conversation context

Subscribes to agent.run.completed events, fetches the conversation
(from Redis if warm, else from Postgres episodic), assembles context
including retrieved bullets used (Diagram 3: CONV node),
and hands it to the Reflector.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateways.llm_gateway import llm_gateway
from app.infra.postgres import async_session_factory
from app.infra import redis_store, qdrant
from app.models.episodic import Conversation
from app.models.identity import User, Permission
from app.components.reflector import reflector
from app.components.curator import curator
from app.infra.pipeline_progress import pipeline_progress
from app.schemas.distillation import ConfidenceScore

logger = logging.getLogger(__name__)


def _user_collection(user_id: str) -> str:
    return f"user_{uuid.UUID(user_id).hex[:8]}"


class RecordingIngestor:
    """Fetches conversation context and triggers the distillation pipeline."""

    async def process_completed_run(self, event: dict) -> list[ConfidenceScore]:
        """
        Handle an agent.run.completed event.
        Fetches conversation, assembles context (including retrieved bullets),
        runs the reflector pipeline, then routes results through the curator.
        """
        conversation_id = event.get("conversation_id")
        user_id = event.get("user_id")
        logger.info(f"RecordingIngestor: Processing conversation {conversation_id} for user {user_id}")

        # Initialize pipeline progress tracking
        pipeline_progress.start(conversation_id)

        try:
            async with async_session_factory() as session:
                # RF → PG (3a): Read conversation from Postgres episodic
                conversation_text = await self._fetch_conversation(conversation_id, session)
                if not conversation_text:
                    logger.warning(f"No conversation found for {conversation_id}")
                    pipeline_progress.complete(conversation_id, {"result": "no_conversation"})
                    return []

                # Assemble user context (role, scope, etc.)
                user_context = await self._get_user_context(user_id, session)

                # Get permitted collections for vector pre-check
                permitted = await self._get_permitted_collections(user_id, session)

                # Diagram 3 CONV context: "retrieved bullets used"
                # Fetch bullets that were likely retrieved during this conversation
                retrieved_bullets = self._get_retrieved_bullets(conversation_text, user_id, permitted)
                pipeline_progress.update(conversation_id, "context", f"Assembled context: {len(retrieved_bullets)} retrieved bullets", {
                    "user_context": user_context,
                    "retrieved_bullets_count": len(retrieved_bullets),
                })

                # Build progress callback for the Reflector
                def on_progress(step: str, detail: str, data: dict) -> None:
                    pipeline_progress.update(conversation_id, step, detail, data)

                # Run the 5-step Reflector pipeline
                scores = reflector.run_pipeline(
                    conversation_text=conversation_text,
                    user_id=user_id,
                    user_context=user_context,
                    permitted_collections=permitted,
                    retrieved_bullets=retrieved_bullets,
                    on_progress=on_progress,
                )

                if not scores:
                    logger.info("No items produced by the distillation pipeline.")
                    pipeline_progress.complete(conversation_id, {"result": "no_items", "scores": []})
                    return []

                # Route through Curator
                await curator.route(scores, user_id, conversation_id, session)

                pipeline_progress.update(conversation_id, "routing", f"Routed {len(scores)} items through Curator", {
                    "items_routed": len(scores),
                })
                pipeline_progress.complete(conversation_id, {
                    "result": "success",
                    "scores": [s.model_dump() for s in scores],
                })

                return scores

        except Exception as e:
            logger.error(f"RecordingIngestor: Pipeline failed: {e}")
            pipeline_progress.error(conversation_id, str(e))
            raise

    async def _fetch_conversation(
        self, conversation_id: str, session: AsyncSession
    ) -> str:
        """RF → PG (3a): Fetch conversation text from Postgres episodic."""
        conv_uuid = uuid.UUID(conversation_id)
        result = await session.execute(
            select(Conversation).where(Conversation.id == conv_uuid)
        )
        conversation = result.scalar_one_or_none()

        if not conversation:
            return ""

        lines = []
        for turn in conversation.turns:
            lines.append(f"{turn.participant}: {turn.content}")
        return "\n".join(lines)

    async def _get_user_context(self, user_id: str, session: AsyncSession) -> str:
        """Build user context string for the pipeline."""
        uid = uuid.UUID(user_id)
        result = await session.execute(select(User).where(User.id == uid))
        user = result.scalar_one_or_none()

        if not user:
            return ""

        parts = [f"User: {user.display_name}"]
        if user.job_function:
            parts.append(f"Role: {user.job_function}")
        if user.department:
            parts.append(f"Department: {user.department}")
        return ", ".join(parts)

    async def _get_permitted_collections(
        self, user_id: str, session: AsyncSession
    ) -> list[str]:
        """Get user's permitted Qdrant collections for vector pre-check."""
        uid = uuid.UUID(user_id)
        result = await session.execute(
            select(Permission.qdrant_collection).where(
                Permission.user_id == uid,
                Permission.access == "read",
            )
        )
        return [row[0] for row in result.all()]

    def _get_retrieved_bullets(
        self,
        conversation_text: str,
        user_id: str,
        permitted_collections: list[str],
    ) -> list[dict]:
        """
        Diagram 3 CONV context: "retrieved bullets used".
        Retrieves the bullets that were likely used/relevant during this
        conversation by doing a vector search against the conversation content.
        These provide context to the Reflector about what the agent already knew.
        """
        if not permitted_collections:
            return []

        try:
            # Embed a summary of the conversation to find relevant bullets
            vectors = llm_gateway.embed([conversation_text[:4000]])
            query_vector = vectors[0]

            retrieved = []
            for collection in permitted_collections:
                try:
                    results = qdrant.search_collection(
                        collection=collection,
                        vector=query_vector,
                        limit=10,
                        score_threshold=0.5,
                    )
                    for hit in results:
                        payload = hit.payload or {}
                        # Skip episodic vectors — these are conversation snapshots
                        # projected by ConversationPersister (EPI → QD). Including
                        # them causes S1 to see the current conversation text as
                        # "already known" and incorrectly skip all signals.
                        if payload.get("type") == "episodic":
                            continue
                        retrieved.append({
                            "content": payload.get("content", ""),
                            "type": payload.get("type", "unknown"),
                            "source_id": payload.get("source_id", ""),
                            "score": hit.score,
                            "collection": collection,
                        })
                except Exception:
                    continue

            logger.info(
                f"RecordingIngestor: Retrieved {len(retrieved)} bullets "
                f"as conversation context"
            )
            return retrieved

        except Exception as e:
            logger.error(f"RecordingIngestor: Failed to retrieve bullets context: {e}")
            return []


# Singleton
recording_ingestor = RecordingIngestor()
