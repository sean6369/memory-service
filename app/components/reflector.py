"""
Reflector — the 5-step LLM distillation pipeline from Diagram 3.

Maps to the full pipeline:
  S1 Signal Detection → Gate 1 → S2 Knowledge Extraction → S3 Personal vs Company
  → S4-pre Vector Pre-check → Gate 2 → S4 Conflict Judgment → S5 Confidence Finalization

Each step is a SEPARATE LLM call with a versioned prompt.
No collapsing — all 5 steps preserved as per user requirement.

S4 has its own Qdrant tool query for additional context (separate from S4-pre).
"""

import json
import logging
from typing import Callable

from app.gateways.llm_gateway import llm_gateway
from app.infra import qdrant
from app.prompts import (
    s1_signal_detection,
    s2_knowledge_extraction,
    s3_personal_vs_company,
    s4_conflict_judgment,
    s5_confidence_finalization,
)
from app.schemas.distillation import (
    S1Output,
    S2Output,
    S3Output,
    S4Output,
    S5Output,
    ConfidenceScore,
    ConflictJudgment,
)

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.8  # Gate 2 threshold for vector pre-check
S4_CONTEXT_THRESHOLD = 0.6  # Lower threshold for S4's broader context query


class Reflector:
    """
    The 5-step LLM distillation pipeline.
    Reads a conversation and extracts structured knowledge items.
    """

    def run_pipeline(
        self,
        conversation_text: str,
        user_id: str,
        user_context: str = "",
        permitted_collections: list[str] | None = None,
        retrieved_bullets: list[dict] | None = None,
        on_progress: Callable[[str, str, dict], None] | None = None,
    ) -> list[ConfidenceScore]:
        """
        Execute the full 5-step pipeline.
        Returns a list of ConfidenceScore items with final scores and tiers.

        retrieved_bullets: Bullets that were retrieved during the conversation
        (included in context per Diagram 3: "retrieved bullets used").
        on_progress: Optional callback(step, detail, data) for live progress reporting.
        """
        def _progress(step: str, detail: str, data: dict | None = None) -> None:
            if on_progress:
                on_progress(step, detail, data or {})

        # ── S1: Signal Detection (LLM call) ─────────────────────
        logger.info("S1: Signal detection...")
        # Include retrieved bullets in context if available (Diagram 3: CONV context)
        enriched_context = user_context
        if retrieved_bullets:
            bullets_text = "\n".join(
                f"- [{b.get('type', 'unknown')}] {b.get('content', '')}"
                for b in retrieved_bullets
            )
            enriched_context += f"\n\nPreviously retrieved bullets used in this conversation:\n{bullets_text}"

        s1_messages = s1_signal_detection.build_messages(conversation_text, enriched_context)
        s1_result: S1Output = llm_gateway.structured(s1_messages, S1Output)
        logger.info(f"S1: Detected {len(s1_result.signals)} signals (prompt v{s1_signal_detection.VERSION})")
        _progress("s1", f"Detected {len(s1_result.signals)} signals", {
            "signals": [s.model_dump() for s in s1_result.signals],
            "debug": {
                "prompt_version": s1_signal_detection.VERSION,
                "conversation_text_length": len(conversation_text),
                "conversation_text_preview": conversation_text[:500],
                "enriched_context_length": len(enriched_context),
                "enriched_context_preview": enriched_context[:500],
            },
        })

        # ── Gate 1: Any signals detected? ────────────────────────
        if not s1_result.signals:
            logger.info("Gate 1: No signals detected. Stopping pipeline.")
            _progress("gate1", "No signals detected — stopping pipeline", {})
            return []

        # ── S2: Knowledge Extraction (LLM call) ─────────────────
        _progress("gate1", f"Passed — {len(s1_result.signals)} signals", {})
        logger.info("S2: Knowledge extraction...")
        signals_json = json.dumps([s.model_dump() for s in s1_result.signals], indent=2)
        s2_messages = s2_knowledge_extraction.build_messages(signals_json, conversation_text)
        s2_result: S2Output = llm_gateway.structured(s2_messages, S2Output)
        logger.info(f"S2: Extracted {len(s2_result.candidates)} candidate items")
        _progress("s2", f"Extracted {len(s2_result.candidates)} candidates", {
            "candidates": [c.model_dump() for c in s2_result.candidates],
        })

        if not s2_result.candidates:
            logger.info("S2: No candidates extracted. Stopping pipeline.")
            return []

        # ── S3: Personal vs Company (LLM call) ──────────────────
        logger.info("S3: Personal vs Company classification...")
        candidates_json = json.dumps([c.model_dump() for c in s2_result.candidates], indent=2)
        s3_messages = s3_personal_vs_company.build_messages(candidates_json)
        s3_result: S3Output = llm_gateway.structured(s3_messages, S3Output)
        logger.info(f"S3: Classified {len(s3_result.classifications)} items")
        _progress("s3", f"Classified {len(s3_result.classifications)} items", {
            "classifications": [c.model_dump() for c in s3_result.classifications],
        })

        # ── S4-pre: Vector Similarity Pre-check (Qdrant) ────────
        logger.info("S4-pre: Vector similarity pre-check...")
        collections_to_search = permitted_collections or []
        conflict_map: dict[str, list[ConflictJudgment]] = {}

        for classification in s3_result.classifications:
            similar_items = self._vector_precheck(
                classification.content,
                collections_to_search,
            )

            # ── Gate 2: Similar items found? ─────────────────────
            if similar_items:
                logger.info(f"Gate 2: Found {len(similar_items)} similar items for '{classification.content[:40]}...'")
                _progress("s4_pre", f"Found {len(similar_items)} similar items for: {classification.content[:50]}", {
                    "similar_count": len(similar_items),
                })
                _progress("gate2", "Similar items found — running conflict judgment", {})

                # S4 tool: Additional Qdrant query for broader context (Diagram 3)
                # This is SEPARATE from S4-pre — fetches more context at a lower threshold
                additional_context = self._s4_qdrant_tool_query(
                    classification.content,
                    collections_to_search,
                )
                logger.info(f"S4 tool: Retrieved {len(additional_context)} additional context items")

                # ── S4: Conflict Judgment (LLM call) ─────────────
                logger.info("S4: Conflict judgment...")
                candidate_json = json.dumps({
                    "content": classification.content,
                    "tier": classification.tier,
                })
                similar_json = json.dumps(similar_items, indent=2)
                additional_json = json.dumps(additional_context, indent=2) if additional_context else "[]"
                s4_messages = s4_conflict_judgment.build_messages(
                    candidate_json, similar_json, additional_json
                )
                s4_result: S4Output = llm_gateway.structured(s4_messages, S4Output)
                conflict_map[classification.content] = s4_result.judgments
                _progress("s4", f"Conflict judgment for: {classification.content[:50]}", {
                    "judgments": [j.model_dump() for j in s4_result.judgments],
                })
            else:
                logger.info(f"Gate 2: No similar items for '{classification.content[:40]}...' — skipping S4")
                _progress("s4_pre", f"No similar items for: {classification.content[:50]}", {})
                _progress("gate2", "No similar items — skipping S4", {})
                conflict_map[classification.content] = []

        # ── S5: Confidence Finalization (LLM call) ───────────────
        logger.info("S5: Confidence finalization...")
        items_for_scoring = []
        for classification in s3_result.classifications:
            conflicts = conflict_map.get(classification.content, [])
            conflict_status = "no_conflict"
            if conflicts:
                # Use the most significant judgment
                for j in conflicts:
                    if j.judgment == "duplicate":
                        conflict_status = "duplicate"
                        break
                    elif j.judgment == "conflict":
                        conflict_status = "conflict"
                    elif j.judgment == "complement" and conflict_status == "no_conflict":
                        conflict_status = "complement"

            items_for_scoring.append({
                "content": classification.content,
                "tier": classification.tier,
                "type": self._find_type_for_content(classification.content, s2_result),
                "conflict_status": conflict_status,
                "conflicts": [j.model_dump() for j in conflicts] if conflicts else [],
            })

        items_json = json.dumps(items_for_scoring, indent=2)
        s5_messages = s5_confidence_finalization.build_messages(items_json)
        s5_result: S5Output = llm_gateway.structured(s5_messages, S5Output)
        logger.info(f"S5: Finalized {len(s5_result.scores)} confidence scores")
        _progress("s5", f"Finalized {len(s5_result.scores)} confidence scores", {
            "scores": [s.model_dump() for s in s5_result.scores],
        })

        return s5_result.scores

    def _vector_precheck(
        self,
        content: str,
        collections: list[str],
    ) -> list[dict]:
        """
        S4-pre: Query Qdrant for similar existing items.
        Returns items above the similarity threshold (0.8).
        """
        if not collections:
            return []

        vectors = llm_gateway.embed([content])
        query_vector = vectors[0]

        similar = []
        for collection in collections:
            try:
                results = qdrant.search_collection(
                    collection=collection,
                    vector=query_vector,
                    limit=5,
                    score_threshold=SIMILARITY_THRESHOLD,
                )
                for hit in results:
                    payload = hit.payload or {}
                    similar.append({
                        "content": payload.get("content", ""),
                        "score": hit.score,
                        "source_id": payload.get("source_id", ""),
                        "collection": collection,
                        "type": payload.get("type", "unknown"),
                    })
            except Exception:
                continue

        return similar

    def _s4_qdrant_tool_query(
        self,
        content: str,
        collections: list[str],
    ) -> list[dict]:
        """
        S4 tool: Qdrant query for more context (Diagram 3).
        This is a SEPARATE Qdrant call from S4-pre, used during S4 Conflict Judgment.
        Uses a lower threshold to gather broader context for the conflict analysis.
        """
        if not collections:
            return []

        vectors = llm_gateway.embed([content])
        query_vector = vectors[0]

        context_items = []
        for collection in collections:
            try:
                results = qdrant.search_collection(
                    collection=collection,
                    vector=query_vector,
                    limit=10,  # More results for broader context
                    score_threshold=S4_CONTEXT_THRESHOLD,  # Lower threshold
                )
                for hit in results:
                    payload = hit.payload or {}
                    # Skip items already caught by S4-pre (above 0.8)
                    if hit.score >= SIMILARITY_THRESHOLD:
                        continue
                    context_items.append({
                        "content": payload.get("content", ""),
                        "score": hit.score,
                        "source_id": payload.get("source_id", ""),
                        "collection": collection,
                        "type": payload.get("type", "unknown"),
                    })
            except Exception:
                continue

        return context_items

    def _find_type_for_content(self, content: str, s2_result: S2Output) -> str:
        """Find the type for a content string from S2 results."""
        for candidate in s2_result.candidates:
            if candidate.content == content:
                return candidate.type
        return "unknown"


# Singleton
reflector = Reflector()
