"""
Structural Event Handler — Flow 5 from Diagram 1.

Maps to Diagram 1:
  SE → KAFKA (5) → ESub → EH → AM (5a: flag affected memories)

Type-aware reaction: when structural changes occur (role change,
permission revoked, team change), identify affected bullets/candidates
and flag them for review. Flagged items are routed through the
Amendment Service (EH → AM) for review tracking.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Bullet
from app.models.amendments import CompanyCandidate
from app.models.audit import ChangeLog

logger = logging.getLogger(__name__)


class StructuralEventHandler:
    """Type-aware handler for structural events."""

    async def handle_event(
        self,
        event_type: str,
        payload: dict,
        session: AsyncSession,
    ) -> dict:
        """
        Route structural events to the appropriate handler.
        Returns a summary of actions taken.
        """
        handlers = {
            "user.role_changed": self._handle_role_changed,
            "permission.revoked": self._handle_permission_revoked,
            "team.changed": self._handle_team_changed,
        }

        handler = handlers.get(event_type)
        if not handler:
            logger.warning(f"Unknown structural event type: {event_type}")
            return {"event_type": event_type, "status": "unknown_type", "affected": 0}

        result = await handler(payload, session)

        # Record audit
        audit = ChangeLog(
            actor=payload.get("actor", "system"),
            action=f"structural_event.{event_type}",
            target_type="structural_event",
            target_id=uuid.uuid4(),
            before={"event_type": event_type, "payload": payload},
            after=result,
        )
        session.add(audit)
        await session.commit()

        return result

    async def _handle_role_changed(
        self, payload: dict, session: AsyncSession
    ) -> dict:
        """
        When a user's role changes, flag their personal bullets for review.
        Role-dependent memories may no longer be accurate.
        Flagged items are routed through Amendment Service (EH → AM).
        """
        user_id = uuid.UUID(payload["user_id"])
        old_role = payload.get("old_role", "")
        new_role = payload.get("new_role", "")

        # Flag active personal bullets that might be role-dependent
        result = await session.execute(
            select(Bullet).where(
                Bullet.user_id == user_id,
                Bullet.status == "active",
                Bullet.tier == "personal",
            )
        )
        bullets = result.scalars().all()

        flagged_bullets = []
        for bullet in bullets:
            # Flag bullets that reference the old role or role-specific content
            if old_role.lower() in bullet.content.lower() or bullet.type in (
                "workflow_pattern",
                "constraint",
            ):
                bullet.status = "flagged_for_review"
                flagged_bullets.append(bullet)

        # EH → AM (5a): Route flagged items through Amendment Service for review
        await self._route_to_amendment_service(
            flagged_bullets, user_id, event_type="user.role_changed", session=session
        )

        logger.info(
            f"StructuralEventHandler: role_changed for {user_id}, "
            f"flagged {len(flagged_bullets)}/{len(bullets)} bullets"
        )
        return {
            "event_type": "user.role_changed",
            "user_id": str(user_id),
            "old_role": old_role,
            "new_role": new_role,
            "total_bullets": len(bullets),
            "flagged": len(flagged_bullets),
        }

    async def _handle_permission_revoked(
        self, payload: dict, session: AsyncSession
    ) -> dict:
        """
        When a permission is revoked, flag memories sourced from
        the now-inaccessible collection.
        Flagged items are routed through Amendment Service (EH → AM).
        """
        user_id = uuid.UUID(payload["user_id"])
        collection = payload.get("collection", "")

        # Find bullets that were sourced from the revoked collection
        result = await session.execute(
            select(Bullet).where(
                Bullet.user_id == user_id,
                Bullet.status == "active",
            )
        )
        bullets = result.scalars().all()

        flagged_bullets = []
        for bullet in bullets:
            # Flag if the source references the revoked collection
            if collection in (bullet.source or ""):
                bullet.status = "flagged_for_review"
                flagged_bullets.append(bullet)

        # Also flag any pending company candidates from this user
        cand_result = await session.execute(
            select(CompanyCandidate).where(
                CompanyCandidate.submitter == user_id,
                CompanyCandidate.state == "pending",
            )
        )
        candidates = cand_result.scalars().all()
        flagged_candidates = 0
        for cand in candidates:
            cand.state = "flagged_for_review"
            flagged_candidates += 1

        # EH → AM (5a): Route flagged items through Amendment Service for review
        await self._route_to_amendment_service(
            flagged_bullets, user_id, event_type="permission.revoked", session=session
        )

        total_flagged = len(flagged_bullets) + flagged_candidates
        logger.info(
            f"StructuralEventHandler: permission_revoked for {user_id} "
            f"(collection={collection}), flagged {total_flagged} items"
        )
        return {
            "event_type": "permission.revoked",
            "user_id": str(user_id),
            "collection": collection,
            "flagged": total_flagged,
        }

    async def _handle_team_changed(
        self, payload: dict, session: AsyncSession
    ) -> dict:
        """
        When team composition changes, flag relationship-type bullets.
        Flagged items are routed through Amendment Service (EH → AM).
        """
        user_id = uuid.UUID(payload["user_id"])

        result = await session.execute(
            select(Bullet).where(
                Bullet.user_id == user_id,
                Bullet.status == "active",
                Bullet.type == "relationship",
            )
        )
        bullets = result.scalars().all()

        flagged_bullets = []
        for bullet in bullets:
            bullet.status = "flagged_for_review"
            flagged_bullets.append(bullet)

        # EH → AM (5a): Route flagged items through Amendment Service for review
        await self._route_to_amendment_service(
            flagged_bullets, user_id, event_type="team.changed", session=session
        )

        logger.info(
            f"StructuralEventHandler: team_changed for {user_id}, "
            f"flagged {len(flagged_bullets)} relationship bullets"
        )
        return {
            "event_type": "team.changed",
            "user_id": str(user_id),
            "flagged": len(flagged_bullets),
        }

    async def _route_to_amendment_service(
        self,
        flagged_bullets: list[Bullet],
        user_id: uuid.UUID,
        event_type: str,
        session: AsyncSession,
    ) -> None:
        """
        EH → AM (5a from Diagram 1): Route flagged items to the Amendment
        Service for review tracking. Creates review candidates for each
        flagged bullet so they appear in the review queue.
        """
        if not flagged_bullets:
            return

        # Lazy import to avoid circular dependency
        from app.components.amendment_service import amendment_service

        for bullet in flagged_bullets:
            await amendment_service.create_review_candidate(
                content=bullet.content,
                type=bullet.type,
                source_bullet_id=str(bullet.id),
                reason=event_type,
                submitter_id=str(user_id),
                session=session,
            )

        logger.info(
            f"StructuralEventHandler: Routed {len(flagged_bullets)} flagged "
            f"items to Amendment Service for review"
        )


# Singleton
structural_event_handler = StructuralEventHandler()
