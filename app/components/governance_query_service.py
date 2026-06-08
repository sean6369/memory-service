"""
Governance Query Service — Flow 6 from Diagram 1.

Maps to Diagram 1:
  AG → MAC (6) → GQ → PG (6a: read-only reporting)

Read-only endpoints for inspecting:
- User memory profiles (active bullets + provenance)
- Audit trail with filters
- Detected conflicts
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import User
from app.models.memory import Bullet
from app.models.audit import ChangeLog

logger = logging.getLogger(__name__)


class GovernanceQueryService:
    """Read-only reporting for governance and inspection."""

    async def get_user_profile(
        self, user_id: str, session: AsyncSession
    ) -> dict:
        """Get a user's memory profile: active bullets + provenance."""
        uid = uuid.UUID(user_id)

        # Get user info
        user_result = await session.execute(
            select(User).where(User.id == uid)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            raise ValueError(f"User {user_id} not found")

        # Get all bullets for this user
        bullet_result = await session.execute(
            select(Bullet)
            .where(Bullet.user_id == uid)
            .order_by(Bullet.created_at.desc())
        )
        bullets = bullet_result.scalars().all()

        return {
            "user_id": str(user.id),
            "display_name": user.display_name,
            "job_function": user.job_function or "",
            "department": user.department or "",
            "bullets": [
                {
                    "id": str(b.id),
                    "user_id": str(b.user_id),
                    "content": b.content,
                    "type": b.type,
                    "tier": b.tier,
                    "confidence": b.confidence,
                    "status": b.status,
                    "authored_by": b.authored_by,
                    "source": b.source or "",
                    "created_at": b.created_at.isoformat() if b.created_at else "",
                }
                for b in bullets
            ],
        }

    async def get_audit_trail(
        self,
        session: AsyncSession,
        limit: int = 50,
        action_filter: str | None = None,
    ) -> dict:
        """Get the audit trail, optionally filtered by action."""
        stmt = select(ChangeLog).order_by(ChangeLog.ts.desc()).limit(limit)
        if action_filter:
            stmt = stmt.where(ChangeLog.action == action_filter)

        result = await session.execute(stmt)
        entries = result.scalars().all()

        return {
            "entries": [
                {
                    "id": str(e.id),
                    "actor": e.actor,
                    "action": e.action,
                    "target_type": e.target_type,
                    "target_id": str(e.target_id),
                    "before": e.before,
                    "after": e.after,
                    "ts": e.ts.isoformat() if e.ts else "",
                }
                for e in entries
            ],
            "total": len(entries),
        }

    async def get_conflicts(self, session: AsyncSession) -> dict:
        """Get bullets with conflict or flagged status."""
        result = await session.execute(
            select(Bullet).where(
                Bullet.status.in_(["flagged_for_review", "candidate"])
            ).order_by(Bullet.created_at.desc())
        )
        bullets = result.scalars().all()

        return {
            "conflicts": [
                {
                    "id": str(b.id),
                    "user_id": str(b.user_id),
                    "content": b.content,
                    "type": b.type,
                    "tier": b.tier,
                    "status": b.status,
                    "confidence": b.confidence,
                    "source": b.source or "",
                }
                for b in bullets
            ],
            "total": len(bullets),
        }


# Singleton
governance_query_service = GovernanceQueryService()
