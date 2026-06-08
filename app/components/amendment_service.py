"""
Amendment Service — Flow 4 from Diagram 1.

Maps to Diagram 1:
  AG → MAC (4: submit amendment) → AM → AS (4a: check permissions) → VA (4b: approved)
  CU → AM (3d: company fact candidate — auto-distilled)
  EH → AM (5a: flag affected → review)

Three entry points:
1. Auto-distilled candidates from the distillation pipeline (Flow 3)
2. User-submitted candidates (Flow 4)
3. Review candidates from structural event handler (Flow 5, EH → AM)

Permission check delegates to the Approval Service interface (AM → AS, 4a).
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.amendments import CompanyCandidate
from app.models.identity import Permission

logger = logging.getLogger(__name__)


class ApprovalServiceInterface:
    """
    Approval Service interface (AS from Diagram 1).
    Step 4a: check permissions — is the reviewer authorized for the given scope?

    In production, this would call an external Approval Service peer container.
    For the MVP, we check against identity.permissions in Postgres.
    """

    async def check_reviewer_authorized(
        self, reviewer_id: str, scope: str, session: AsyncSession
    ) -> bool:
        """
        AM → AS (4a): Check if the reviewer has permission to approve
        items in the given scope.
        """
        uid = uuid.UUID(reviewer_id)
        result = await session.execute(
            select(Permission).where(
                Permission.user_id == uid,
                Permission.qdrant_collection == "company_shared",
                Permission.access == "read",
            )
        )
        permission = result.scalar_one_or_none()
        if not permission:
            logger.warning(
                f"ApprovalService: Reviewer {reviewer_id} not authorized for scope '{scope}'"
            )
            return False
        return True


# Singleton for the Approval Service interface
approval_service = ApprovalServiceInterface()


class AmendmentService:
    """Manages company fact candidates — auto-distilled, user-submitted, and review items."""

    async def create_auto_distilled_candidate(
        self,
        content: str,
        type: str,
        confidence: int,
        submitter_id: str,
        session: AsyncSession,
    ) -> CompanyCandidate:
        """Create a company candidate from the distillation pipeline (auto-distilled)."""
        candidate = CompanyCandidate(
            content=content,
            type=type,
            proposed_scope="company",
            state="pending",
            submitter=uuid.UUID(submitter_id),
            source="auto_distilled",
            confidence=confidence,
        )
        session.add(candidate)
        await session.commit()
        logger.info(f"AmendmentService: Created auto-distilled candidate {candidate.id}")
        return candidate

    async def create_user_submitted_candidate(
        self,
        content: str,
        type: str,
        proposed_scope: str,
        submitter_id: str,
        session: AsyncSession,
    ) -> CompanyCandidate:
        """Create a company candidate submitted directly by a user."""
        candidate = CompanyCandidate(
            content=content,
            type=type,
            proposed_scope=proposed_scope,
            state="pending",
            submitter=uuid.UUID(submitter_id),
            source="user_submitted",
        )
        session.add(candidate)
        await session.commit()
        logger.info(f"AmendmentService: Created user-submitted candidate {candidate.id}")
        return candidate

    async def create_review_candidate(
        self,
        content: str,
        type: str,
        source_bullet_id: str,
        reason: str,
        submitter_id: str,
        session: AsyncSession,
    ) -> CompanyCandidate:
        """
        EH → AM (5a from Diagram 1): Create a review candidate from a
        structural event. These are flagged items that need supervisor review.
        """
        candidate = CompanyCandidate(
            content=f"[REVIEW NEEDED: {reason}] {content}",
            type=type,
            proposed_scope="review",
            state="pending",
            submitter=uuid.UUID(submitter_id),
            source=f"structural_event:{reason}:bullet:{source_bullet_id}",
        )
        session.add(candidate)
        # Don't commit here — the caller (structural_event_handler) handles commit
        logger.info(
            f"AmendmentService: Created review candidate for bullet {source_bullet_id} "
            f"(reason: {reason})"
        )
        return candidate

    async def approve(
        self,
        candidate_id: str,
        reviewer_id: str,
        session: AsyncSession,
    ) -> CompanyCandidate:
        """
        Approve a candidate. Delegates publishing to VersioningAuditManager.
        Step 4a: AM → AS — check permissions via Approval Service interface.
        """
        from app.components.versioning_audit_manager import versioning_audit_manager

        cid = uuid.UUID(candidate_id)
        result = await session.execute(
            select(CompanyCandidate).where(CompanyCandidate.id == cid)
        )
        candidate = result.scalar_one_or_none()

        if not candidate:
            raise ValueError(f"Candidate {candidate_id} not found")
        if candidate.state != "pending":
            raise ValueError(f"Candidate {candidate_id} is not pending (state={candidate.state})")

        # Step 4a: AM → AS — Check reviewer permissions via Approval Service
        authorized = await approval_service.check_reviewer_authorized(
            reviewer_id=reviewer_id,
            scope=candidate.proposed_scope or "company",
            session=session,
        )
        if not authorized:
            raise PermissionError(
                f"Reviewer {reviewer_id} is not authorized to approve "
                f"candidates in scope '{candidate.proposed_scope}'"
            )

        # Update candidate state
        candidate.state = "approved"
        candidate.reviewer = uuid.UUID(reviewer_id)
        candidate.decided_at = datetime.now(timezone.utc)

        # Delegate publishing to VersioningAuditManager
        await versioning_audit_manager.publish_approved(candidate, reviewer_id, session)

        await session.commit()
        logger.info(f"AmendmentService: Approved candidate {candidate_id}")
        return candidate

    async def reject(
        self,
        candidate_id: str,
        reviewer_id: str,
        decision: str,
        session: AsyncSession,
    ) -> CompanyCandidate:
        """Reject a candidate."""
        from app.components.versioning_audit_manager import versioning_audit_manager

        cid = uuid.UUID(candidate_id)
        result = await session.execute(
            select(CompanyCandidate).where(CompanyCandidate.id == cid)
        )
        candidate = result.scalar_one_or_none()

        if not candidate:
            raise ValueError(f"Candidate {candidate_id} not found")
        if candidate.state != "pending":
            raise ValueError(f"Candidate {candidate_id} is not pending (state={candidate.state})")

        candidate.state = "rejected"
        candidate.reviewer = uuid.UUID(reviewer_id)
        candidate.decision = decision
        candidate.decided_at = datetime.now(timezone.utc)

        # Record audit
        await versioning_audit_manager.record_rejection(candidate, reviewer_id, session)

        await session.commit()
        logger.info(f"AmendmentService: Rejected candidate {candidate_id}")
        return candidate


# Singleton
amendment_service = AmendmentService()
