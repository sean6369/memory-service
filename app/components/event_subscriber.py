"""
Event Subscriber — Flow 5 from Diagram 1.

Maps to Diagram 1:
  SE → KAFKA (5) → ESub → EH

Subscribes to structural events on the EventBus and delegates
to the StructuralEventHandler.
"""

import asyncio
import logging

from app.infra.event_bus import event_bus
from app.infra.postgres import async_session_factory
from app.components.structural_event_handler import structural_event_handler

logger = logging.getLogger(__name__)

STRUCTURAL_EVENTS = [
    "user.role_changed",
    "permission.revoked",
    "team.changed",
]


def _make_handler(event_type: str):
    """Create a sync handler that spawns an async task for the structural event."""

    def handler(event: dict):
        loop = asyncio.get_running_loop()
        loop.create_task(_process_structural_event(event_type, event))

    return handler


async def _process_structural_event(event_type: str, event: dict):
    """Process a structural event in an async context."""
    logger.info(f"EventSubscriber: Received {event_type}")
    try:
        async with async_session_factory() as session:
            result = await structural_event_handler.handle_event(
                event_type=event_type,
                payload=event,
                session=session,
            )
            logger.info(f"EventSubscriber: {event_type} result: {result}")
    except Exception as e:
        logger.error(f"EventSubscriber: Error handling {event_type}: {e}")


def subscribe_structural_events():
    """Subscribe to all structural event types on the EventBus."""
    for event_type in STRUCTURAL_EVENTS:
        event_bus.subscribe(event_type, _make_handler(event_type))
        logger.info(f"EventSubscriber: Subscribed to {event_type}")
