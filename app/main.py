"""
FastAPI application — Memory Service.

Wires routes from the Memory API Controller, applies CORS,
and subscribes components to the EventBus at startup.
"""

import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.controllers.memory_api_controller import router as api_router
from app.infra.event_bus import event_bus
from app.components.recording_ingestor import recording_ingestor
from app.components.event_subscriber import subscribe_structural_events

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Memory Service",
    description="AI Agent Memory & Knowledge Management Service",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


# ── EventBus subscriptions ───────────────────────────────────────────────────

def _on_agent_run_completed(event: dict):
    """
    Flow 3 entry: When a conversation ends, trigger distillation.
    KAFKA → RI (agent.run.completed)
    """
    # Run the async ingestor in a background task
    loop = asyncio.get_running_loop()
    loop.create_task(
        recording_ingestor.process_completed_run(event)
    )


# Subscribe at module load — the bus is in-process so this is immediate
event_bus.subscribe("agent.run.completed", _on_agent_run_completed)

# Flow 5: Subscribe to structural events (user.role_changed, permission.revoked, team.changed)
subscribe_structural_events()
