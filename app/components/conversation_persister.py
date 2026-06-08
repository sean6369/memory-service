"""
Conversation Persister — Flow 2 from Diagram 1.

Maps to:
  AG → MAC (2: turns) → REDIS (2a: append live turn)
  CP → REDIS (2b: flush session at end) → PG (2c: persist conversation wholesale)
  EPI → QD (projects conversation vectors — from Diagram 2)

Two operations:
1. Append turn: live turns accumulate in Redis during a session
2. End session: flush Redis → persist to episodic.conversations + episodic.turns (PG)
   → project conversation vector to Qdrant (EPI → QD)
   → publish agent.run.completed event on EventBus
"""

import logging
import uuid
from datetime import datetime, timezone

from qdrant_client.models import PointStruct
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateways.llm_gateway import llm_gateway
from app.infra import redis_store, qdrant
from app.infra.event_bus import event_bus
from app.models.episodic import Conversation, Turn

logger = logging.getLogger(__name__)


def _user_collection(user_id: str) -> str:
    return f"user_{uuid.UUID(user_id).hex[:8]}"


class ConversationPersister:

    def append_turn(
        self,
        session_id: str,
        user_id: str,
        participant: str,
        content: str,
    ) -> int:
        """
        Step 2a: Append a live turn to Redis.
        Returns the turn index (1-based).
        """
        return redis_store.append_turn(session_id, user_id, participant, content)

    async def end_session(
        self,
        session_id: str,
        user_id: str,
        db_session: AsyncSession,
    ) -> tuple[str, int]:
        """
        Steps 2b + 2c: Flush session from Redis, persist to Postgres,
        project conversation vector to Qdrant (EPI → QD),
        publish agent.run.completed event.

        Returns: (conversation_id, turns_persisted)
        """
        # Step 2b: Flush all turns from Redis
        turns = redis_store.flush_session(session_id)

        if not turns:
            raise ValueError(f"No turns found for session {session_id}")

        # Step 2c: Persist conversation wholesale to episodic schema
        uid = uuid.UUID(user_id)
        conversation = Conversation(
            id=uuid.UUID(session_id) if len(session_id) == 36 else uuid.uuid4(),
            user_id=uid,
            started_at=datetime.now(timezone.utc),
            ended_at=datetime.now(timezone.utc),
            topic=None,  # Could be extracted by LLM later
        )
        db_session.add(conversation)
        await db_session.flush()

        for turn_data in turns:
            turn = Turn(
                conversation_id=conversation.id,
                participant=turn_data["participant"],
                content=turn_data["content"],
            )
            db_session.add(turn)

        await db_session.commit()

        # EPI → QD: Project conversation vectors to Qdrant (Diagram 2)
        self._project_conversation_vector(conversation.id, user_id, turns)

        # Publish agent.run.completed event on EventBus
        event_bus.publish("agent.run.completed", {
            "conversation_id": str(conversation.id),
            "user_id": user_id,
            "session_id": session_id,
            "turns_count": len(turns),
        })

        return str(conversation.id), len(turns)

    def _project_conversation_vector(
        self,
        conversation_id: uuid.UUID,
        user_id: str,
        turns: list[dict],
    ) -> None:
        """
        EPI → QD (Diagram 2): Project conversation vectors to Qdrant.
        Embeds the full conversation text and stores it in the user's
        Qdrant collection as an episodic vector.
        """
        conversation_text = "\n".join(
            f"{t['participant']}: {t['content']}" for t in turns
        )

        try:
            vectors = llm_gateway.embed([conversation_text])
            collection = _user_collection(user_id)
            point = PointStruct(
                id=conversation_id.hex,
                vector=vectors[0],
                payload={
                    "content": conversation_text[:2000],  # Truncate for payload
                    "type": "episodic",
                    "source_id": str(conversation_id),
                    "user_id": user_id,
                    "tier": "personal",
                },
            )
            qdrant.upsert_points(collection, [point])
            logger.info(
                f"ConversationPersister: Projected conversation {conversation_id} "
                f"vector to Qdrant collection {collection}"
            )
        except Exception as e:
            logger.error(f"ConversationPersister: Failed to project conversation vector: {e}")


# Singleton
conversation_persister = ConversationPersister()
