"""
Retrieval Engine — Flow 1 from Diagram 1.

Maps to: AG → MAC → RE → LG (1a reasoning) → PG (1b permissions) → QD (1c search)
Also: SE → RE (semantic context inject sync)
Also: RET → MEM (on-demand provenance lookup)

Four ordered steps:
1. Permissions (1b): look up which Qdrant collections this user may read
2. Reasoning (1a): LLM classifies query as episodic vs semantic, resolves vague references
3. Search (1c): embed resolved_query, search only permitted collections, return top-k
4. Provenance (RET → MEM): on-demand provenance lookup for retrieved items
"""

import uuid
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateways.llm_gateway import llm_gateway
from app.infra import qdrant
from app.models.identity import Permission
from app.models.memory import Bullet
from app.schemas.retrieval import ResolvedQuery, RetrievedItem

logger = logging.getLogger(__name__)


class RetrievalEngine:

    async def retrieve(
        self,
        user_id: str,
        query: str,
        session: AsyncSession,
        top_k: int = 10,
        semantic_context: str | None = None,
    ) -> tuple[ResolvedQuery, list[RetrievedItem], list[str]]:
        """
        Execute the full retrieval flow.
        Returns: (resolved_query, retrieved_items, permitted_collections)

        semantic_context: Optional context injected synchronously by the
        Semantic Engine (SE → RE arrow in Diagram 1).
        """

        # Step 1b: Permissions — which Qdrant collections can this user read?
        permitted = await self._get_permitted_collections(user_id, session)

        if not permitted:
            return (
                ResolvedQuery(
                    query_type="semantic",
                    resolved_query=query,
                    notes="No collections permitted for this user.",
                ),
                [],
                [],
            )

        # Step 1a: Reasoning — LLM classifies and resolves the query
        # SE → RE: semantic_context injected into reasoning if provided
        resolved = self._reason_about_query(query, semantic_context)

        # Step 1c: Search — embed and search permitted collections
        items = self._search_collections(resolved.resolved_query, permitted, top_k)

        # On-demand provenance lookup (RET → MEM from Diagram 2)
        items = await self._enrich_with_provenance(items, session)

        return resolved, items, permitted

    async def _get_permitted_collections(
        self, user_id: str, session: AsyncSession
    ) -> list[str]:
        """Step 1b: Query identity.permissions for this user's readable collections."""
        uid = uuid.UUID(user_id)
        result = await session.execute(
            select(Permission.qdrant_collection).where(
                Permission.user_id == uid,
                Permission.access == "read",
            )
        )
        return [row[0] for row in result.all()]

    def _reason_about_query(
        self, query: str, semantic_context: str | None = None
    ) -> ResolvedQuery:
        """
        Step 1a: LLM reasons about the query.
        Classifies as episodic vs semantic, resolves vague references
        like 'the usual' or 'last time' into concrete search queries.

        If semantic_context is provided (from Semantic Engine), it is
        included in the reasoning prompt for richer context.
        """
        system_content = (
            "You are a memory retrieval reasoning engine. Given a user query, "
            "you must classify it and resolve any vague references.\n\n"
            "1. Classify the query as 'episodic' (about past events/conversations, "
            "e.g. 'what did I discuss last time', 'remember when...') or 'semantic' "
            "(about facts/preferences/knowledge, e.g. 'what's my usual order', "
            "'what do I prefer').\n\n"
            "2. Resolve vague references into concrete search terms. For example:\n"
            "   - 'the usual' → 'preferred order / routine preference'\n"
            "   - 'last time' → 'most recent conversation / previous session'\n"
            "   - 'that thing I mentioned' → 'recently discussed topic'\n\n"
            "3. If the query is already specific, keep it as-is.\n\n"
            "Respond with the classification and resolved query."
        )

        # SE → RE: Inject semantic context from the Semantic Engine
        if semantic_context:
            system_content += (
                f"\n\nAdditional context from the Semantic Engine:\n{semantic_context}"
            )

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": query},
        ]

        return llm_gateway.structured(messages, ResolvedQuery)

    def _search_collections(
        self,
        resolved_query: str,
        collections: list[str],
        top_k: int,
    ) -> list[RetrievedItem]:
        """
        Step 1c: Embed the resolved query and search all permitted Qdrant collections.
        Returns combined results sorted by score.
        """
        vectors = llm_gateway.embed([resolved_query])
        query_vector = vectors[0]

        all_results = []
        for collection_name in collections:
            try:
                results = qdrant.search_collection(
                    collection=collection_name,
                    vector=query_vector,
                    limit=top_k,
                )
                for hit in results:
                    payload = hit.payload or {}
                    all_results.append(
                        RetrievedItem(
                            content=payload.get("content", ""),
                            score=hit.score,
                            type=payload.get("type", "unknown"),
                            source_id=payload.get("source_id"),
                            collection=collection_name,
                        )
                    )
            except Exception:
                # Collection may not exist yet — skip gracefully
                continue

        # Sort by score descending, take top_k overall
        all_results.sort(key=lambda x: x.score, reverse=True)
        return all_results[:top_k]

    async def _enrich_with_provenance(
        self, items: list[RetrievedItem], session: AsyncSession
    ) -> list[RetrievedItem]:
        """
        On-demand provenance lookup (RET → MEM from Diagram 2).
        For each retrieved item with a source_id, look up the corresponding
        bullet in memory.bullets to enrich with provenance metadata.
        """
        for item in items:
            if not item.source_id:
                continue
            try:
                bullet_id = uuid.UUID(item.source_id)
                result = await session.execute(
                    select(Bullet).where(Bullet.id == bullet_id)
                )
                bullet = result.scalar_one_or_none()
                if bullet:
                    item.authored_by = bullet.authored_by
                    item.source = bullet.source
                    item.confidence = bullet.confidence
                    item.status = bullet.status
            except (ValueError, Exception):
                # source_id might not be a valid UUID or bullet may not exist
                continue
        return items


# Singleton
retrieval_engine = RetrievalEngine()
