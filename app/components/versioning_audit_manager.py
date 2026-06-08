"""
Versioning & Audit Manager — Flow 4 publish path from Diagram 1.

Maps to Diagram 1:
  AM → VA (4b: approved -> publish)
  VA → PG (4c: write bullet/KB + provenance)
  VA → PG (4d: append immutable audit)
  VA → QD (4e: project to retrieval index)

Maps to Diagram 2:
  AMD → KB (supervisor approves → KB schema)
  KB → QD (projects chunk vectors + content)
"""

import logging
import uuid

from qdrant_client.models import PointStruct
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateways.llm_gateway import llm_gateway
from app.infra import qdrant
from app.models.amendments import CompanyCandidate
from app.models.memory import Bullet
from app.models.kb import Document, Chunk
from app.models.audit import ChangeLog

logger = logging.getLogger(__name__)

COMPANY_COLLECTION = "company_shared"


class VersioningAuditManager:
    """Publishes approved company facts with provenance and audit trail."""

    async def publish_approved(
        self,
        candidate: CompanyCandidate,
        reviewer_id: str,
        session: AsyncSession,
    ) -> None:
        """
        Steps 4c + 4d + 4e: Publish an approved company fact.
        Also writes to KB schema (AMD → KB from Diagram 2)
        and projects KB chunk vectors to Qdrant (KB → QD from Diagram 2).
        """

        # Step 4c: Write bullet with provenance to memory.bullets (Postgres)
        bullet = Bullet(
            user_id=candidate.submitter,
            content=candidate.content,
            type=candidate.type,
            tier="company",
            confidence=candidate.confidence or 4,
            status="active",
            authored_by=f"approved_by:{reviewer_id}",
            source=f"candidate:{candidate.id}",
        )
        session.add(bullet)
        await session.flush()
        logger.info(f"VersioningAuditManager: Published bullet {bullet.id}")

        # AMD → KB (Diagram 2): Write approved fact to KB schema as document + chunk
        document = Document(
            title=f"Approved fact: {candidate.content[:80]}",
            blob_uri=None,  # Auto-distilled/user-submitted facts have no raw blob
            permissions="company_all",
            version=1,
        )
        session.add(document)
        await session.flush()

        chunk = Chunk(
            document_id=document.id,
            content=candidate.content,
            version=1,
        )
        session.add(chunk)
        await session.flush()
        logger.info(f"VersioningAuditManager: Created KB document {document.id} + chunk {chunk.id}")

        # Step 4d: Append immutable audit record
        audit = ChangeLog(
            actor=reviewer_id,
            action="candidate.approved",
            target_type="company_candidate",
            target_id=candidate.id,
            before={"state": "pending"},
            after={
                "state": "approved",
                "bullet_id": str(bullet.id),
                "kb_document_id": str(document.id),
                "kb_chunk_id": str(chunk.id),
                "content": candidate.content,
            },
        )
        session.add(audit)
        logger.info(f"VersioningAuditManager: Appended audit record")

        # Step 4e + KB → QD (Diagram 2): Project to Qdrant retrieval index
        # Projects both the bullet vector and the KB chunk vector
        vectors = llm_gateway.embed([candidate.content])

        # Project bullet to company_shared
        bullet_point = PointStruct(
            id=bullet.id.hex,
            vector=vectors[0],
            payload={
                "content": candidate.content,
                "type": "company_fact",
                "source_id": str(bullet.id),
                "tier": "company",
                "bullet_type": candidate.type,
            },
        )
        qdrant.upsert_points(COMPANY_COLLECTION, [bullet_point])

        # KB → QD: Project KB chunk vector to company_shared
        chunk_point = PointStruct(
            id=chunk.id.hex,
            vector=vectors[0],
            payload={
                "content": candidate.content,
                "type": "kb_chunk",
                "source_id": str(chunk.id),
                "document_id": str(document.id),
                "tier": "company",
            },
        )
        qdrant.upsert_points(COMPANY_COLLECTION, [chunk_point])
        logger.info(f"VersioningAuditManager: Projected bullet + KB chunk to Qdrant {COMPANY_COLLECTION}")

    async def record_rejection(
        self,
        candidate: CompanyCandidate,
        reviewer_id: str,
        session: AsyncSession,
    ) -> None:
        """Record a rejection in the audit log."""
        audit = ChangeLog(
            actor=reviewer_id,
            action="candidate.rejected",
            target_type="company_candidate",
            target_id=candidate.id,
            before={"state": "pending"},
            after={
                "state": "rejected",
                "decision": candidate.decision,
            },
        )
        session.add(audit)
        logger.info(f"VersioningAuditManager: Recorded rejection audit")


# Singleton
versioning_audit_manager = VersioningAuditManager()
