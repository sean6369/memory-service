"""
Memory API Controller — single entry point for the Memory Service.

Maps to Diagram 1: "Memory API Controller" component.
All external requests (from API Gateway) enter through this controller.
"""

import asyncio
import json as json_mod

from fastapi import APIRouter, Depends, Query
from starlette.responses import StreamingResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel

from app.infra import qdrant, redis_store
from app.infra.event_bus import event_bus
from app.infra.pipeline_progress import pipeline_progress
from app.infra.postgres import engine, get_session
from app.components.retrieval_engine import retrieval_engine
from app.components.conversation_persister import conversation_persister
from app.components.amendment_service import amendment_service
from app.components.governance_query_service import governance_query_service
from app.components.structural_event_handler import structural_event_handler
from app.models.amendments import CompanyCandidate
from app.models.kb import Document, Chunk
from app.schemas.retrieval import QueryRequest, QueryResponse
from app.schemas.conversation import (
    TurnRequest, TurnResponse, EndSessionRequest, EndSessionResponse,
    ChatRequest, ChatResponse, RetrievalDetail,
)
from app.gateways.llm_gateway import llm_gateway
from app.prompts.chat_system_prompt import build_messages
from app.schemas.amendments import (
    CreateAmendmentRequest,
    ApproveAmendmentRequest,
    RejectAmendmentRequest,
    AmendmentResponse,
    AmendmentListResponse,
)

router = APIRouter()


# ── Health ───────────────────────────────────────────────────────────────────

@router.get("/health")
async def health():
    """Health check — confirms Postgres, Qdrant, and Redis connectivity."""
    pg_ok = False
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            pg_ok = True
    except Exception:
        pass

    qd_ok = qdrant.health_check()
    redis_ok = redis_store.health_check()

    status = "ok" if (pg_ok and qd_ok and redis_ok) else "degraded"
    return {
        "status": status,
        "postgres": pg_ok,
        "qdrant": qd_ok,
        "redis": redis_ok,
    }


# ── Flow 1: Retrieval ───────────────────────────────────────────────────────

@router.post("/query", response_model=QueryResponse)
async def query_memory(
    req: QueryRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Flow 1: Query the memory service.
    AG → MAC → RE → LG (1a reasoning) → PG (1b permissions) → QD (1c search)
    """
    resolved, items, permitted = await retrieval_engine.retrieve(
        user_id=req.user_id,
        query=req.query,
        session=session,
        semantic_context=req.semantic_context,
    )
    return QueryResponse(
        original_query=req.query,
        resolved_query=resolved,
        items=items,
        permitted_collections=permitted,
    )


# ── Flow 2: Conversation Persistence ────────────────────────────────────────

@router.post("/turns", response_model=TurnResponse)
async def add_turn(req: TurnRequest):
    """
    Flow 2, Step 2a: Append a live turn to Redis.
    AG → MAC (2: turns) → REDIS (2a: append live turn)
    """
    turn_index = conversation_persister.append_turn(
        session_id=req.session_id,
        user_id=req.user_id,
        participant=req.participant,
        content=req.content,
    )
    return TurnResponse(
        session_id=req.session_id,
        turn_index=turn_index,
        participant=req.participant,
        content=req.content,
    )


@router.post("/session/{session_id}/end", response_model=EndSessionResponse)
async def end_session(
    session_id: str,
    req: EndSessionRequest,
    db_session: AsyncSession = Depends(get_session),
):
    """
    Flow 2, Steps 2b+2c: Flush Redis → persist to Postgres → publish event.
    CP → REDIS (2b: flush) → PG (2c: persist) → EventBus (agent.run.completed)
    """
    conversation_id, turns_count = await conversation_persister.end_session(
        session_id=session_id,
        user_id=req.user_id,
        db_session=db_session,
    )
    return EndSessionResponse(
        session_id=session_id,
        conversation_id=conversation_id,
        turns_persisted=turns_count,
        event_published=True,
    )


# ── Chat (auto-generated assistant responses) ─────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Chat endpoint: record user turn → retrieve memories → generate assistant
    response via LLM → record assistant turn → return response.
    """
    # 1. Record user turn to Redis
    redis_store.append_turn(req.session_id, req.user_id, "user", req.message)

    # 2. Retrieve relevant memories (reuses Flow 1 with permission checks)
    resolved, items, permitted = await retrieval_engine.retrieve(
        user_id=req.user_id,
        query=req.message,
        session=session,
    )

    # 3. Get conversation history from Redis (includes the user turn just added)
    history = redis_store.get_turns(req.session_id)

    # 4. Build LLM messages with memory context
    retrieved_dicts = [
        {"content": item.content, "type": item.type, "score": item.score,
         "collection": item.collection, "source_id": item.source_id,
         "authored_by": item.authored_by, "source": item.source,
         "confidence": item.confidence, "status": item.status}
        for item in items
    ]
    messages = build_messages(req.message, retrieved_dicts, history)

    # 5. Generate assistant response
    assistant_response = llm_gateway.chat(messages, temperature=0.7)

    # 6. Record assistant turn to Redis
    redis_store.append_turn(req.session_id, req.user_id, "assistant", assistant_response)

    # 7. Return response with retrieval details
    return ChatResponse(
        session_id=req.session_id,
        assistant_message=assistant_response,
        retrieved_items=retrieved_dicts,
        retrieval=RetrievalDetail(
            resolved_query=resolved.resolved_query,
            query_type=resolved.query_type,
            reasoning_notes=resolved.notes,
            permitted_collections=permitted,
        ),
    )


# ── Distillation Pipeline Streaming (SSE) ─────────────────────────────────────

@router.get("/distillation/{conversation_id}/stream")
async def stream_distillation(conversation_id: str):
    """
    SSE endpoint: stream distillation pipeline progress in real time.
    The frontend connects after ending a session to watch S1-S5 execute.
    """
    async def event_generator():
        cursor = 0
        timeout = 60.0  # max wait time in seconds
        elapsed = 0.0
        poll_interval = 0.5

        while elapsed < timeout:
            updates = pipeline_progress.get_updates(conversation_id, after=cursor)
            for update in updates:
                yield f"data: {json_mod.dumps(update)}\n\n"
                cursor += 1
                if update.get("done"):
                    pipeline_progress.cleanup(conversation_id)
                    return
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        # Timeout — send a done event so the client doesn't hang
        yield f"data: {json_mod.dumps({'step': 'timeout', 'detail': 'Stream timed out', 'data': {}, 'done': True})}\n\n"
        pipeline_progress.cleanup(conversation_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Flow 4: Amendment Workflow ───────────────────────────────────────────────

def _candidate_to_response(c: CompanyCandidate) -> AmendmentResponse:
    return AmendmentResponse(
        id=str(c.id),
        content=c.content,
        type=c.type,
        proposed_scope=c.proposed_scope,
        state=c.state,
        submitter=str(c.submitter),
        reviewer=str(c.reviewer) if c.reviewer else None,
        decision=c.decision,
        source=c.source,
        confidence=c.confidence,
        created_at=c.created_at,
        decided_at=c.decided_at,
    )


@router.get("/amendments", response_model=AmendmentListResponse)
async def list_amendments(
    state: str | None = Query(None, description="Filter by state: pending, approved, rejected"),
    session: AsyncSession = Depends(get_session),
):
    """List company fact candidates, optionally filtered by state."""
    stmt = select(CompanyCandidate).order_by(CompanyCandidate.created_at.desc())
    if state:
        stmt = stmt.where(CompanyCandidate.state == state)
    result = await session.execute(stmt)
    candidates = result.scalars().all()
    return AmendmentListResponse(
        candidates=[_candidate_to_response(c) for c in candidates],
        total=len(candidates),
    )


@router.post("/amendments", response_model=AmendmentResponse)
async def create_amendment(
    req: CreateAmendmentRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Flow 4: Submit a user-authored company fact candidate.
    AG → MAC (4: submit amendment) → AM → AS
    """
    candidate = await amendment_service.create_user_submitted_candidate(
        content=req.content,
        type=req.type,
        proposed_scope=req.proposed_scope,
        submitter_id=req.submitter_id,
        session=session,
    )
    return _candidate_to_response(candidate)


@router.post("/amendments/{candidate_id}/approve", response_model=AmendmentResponse)
async def approve_amendment(
    candidate_id: str,
    req: ApproveAmendmentRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Flow 4, Step 4a+4b: Approve a pending candidate.
    AS (4a: check permissions) → VA (4b: approved → publish)
    """
    candidate = await amendment_service.approve(
        candidate_id=candidate_id,
        reviewer_id=req.reviewer_id,
        session=session,
    )
    return _candidate_to_response(candidate)


@router.post("/amendments/{candidate_id}/reject", response_model=AmendmentResponse)
async def reject_amendment(
    candidate_id: str,
    req: RejectAmendmentRequest,
    session: AsyncSession = Depends(get_session),
):
    """Flow 4: Reject a pending candidate with a reason."""
    candidate = await amendment_service.reject(
        candidate_id=candidate_id,
        reviewer_id=req.reviewer_id,
        decision=req.decision,
        session=session,
    )
    return _candidate_to_response(candidate)


# ── Flow 5: Event-Driven Invalidation ───────────────────────────────────────

class StructuralEventRequest(BaseModel):
    event_type: str  # "user.role_changed", "permission.revoked", "team.changed"
    payload: dict


@router.post("/events/structural")
async def emit_structural_event(
    req: StructuralEventRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Flow 5: Emit a structural event for testing/demo.
    SE → KAFKA (5) → ESub → EH → AM (5a: flag affected)

    Also fires on the EventBus for any subscribers.
    """
    result = await structural_event_handler.handle_event(
        event_type=req.event_type,
        payload=req.payload,
        session=session,
    )
    # Also publish on EventBus for any other subscribers
    event_bus.publish(req.event_type, req.payload)
    return result


# ── Flow 6: Governance Reads ────────────────────────────────────────────────

@router.get("/governance/users/{user_id}/profile")
async def governance_user_profile(
    user_id: str,
    session: AsyncSession = Depends(get_session),
):
    """
    Flow 6: Get user memory profile with provenance.
    AG → MAC (6) → GQ → PG (6a)
    """
    return await governance_query_service.get_user_profile(user_id, session)


@router.get("/governance/audit")
async def governance_audit_trail(
    limit: int = Query(50, ge=1, le=200),
    action: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """
    Flow 6: Get audit trail with optional filters.
    AG → MAC (6) → GQ → PG (6a)
    """
    return await governance_query_service.get_audit_trail(
        session=session,
        limit=limit,
        action_filter=action,
    )


@router.get("/governance/conflicts")
async def governance_conflicts(
    session: AsyncSession = Depends(get_session),
):
    """Flow 6: Get detected conflicts and flagged items."""
    return await governance_query_service.get_conflicts(session)


# ── Flow 7: Semantic Engine Direct KB Read ──────────────────────────────────

@router.get("/semantic-engine/kb")
async def semantic_engine_kb(
    session: AsyncSession = Depends(get_session),
):
    """
    Flow 7: Direct KB read — bypasses retrieval/permission reasoning.
    SE → PG (7: read approved KB)
    """
    result = await session.execute(
        select(Document).order_by(Document.created_at.desc())
    )
    docs = result.scalars().all()

    # Also include approved company bullets as KB items
    from app.models.memory import Bullet
    bullet_result = await session.execute(
        select(Bullet).where(
            Bullet.tier == "company",
            Bullet.status == "active",
        ).order_by(Bullet.created_at.desc())
    )
    bullets = bullet_result.scalars().all()

    return {
        "documents": [
            {
                "id": str(d.id),
                "title": d.title,
                "blob_uri": d.blob_uri,
                "version": d.version,
                "created_at": d.created_at.isoformat() if d.created_at else "",
            }
            for d in docs
        ],
        "company_facts": [
            {
                "id": str(b.id),
                "content": b.content,
                "type": b.type,
                "confidence": b.confidence,
                "source": b.source or "",
                "authored_by": b.authored_by,
                "created_at": b.created_at.isoformat() if b.created_at else "",
            }
            for b in bullets
        ],
    }


@router.get("/semantic-engine/kb/documents/{document_id}/blob")
async def semantic_engine_kb_document_blob(
    document_id: str,
    session: AsyncSession = Depends(get_session),
):
    """
    KB → BLOB (Diagram 2): Read raw KB document by URI from Blob Storage.
    Fetches the document's blob_uri from Postgres, then retrieves the raw
    payload from the BlobStore.
    """
    import uuid as _uuid
    from fastapi.responses import Response
    from app.infra.blob_store import blob_store

    doc_uuid = _uuid.UUID(document_id)
    result = await session.execute(
        select(Document).where(Document.id == doc_uuid)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        return {"error": f"Document {document_id} not found"}
    if not doc.blob_uri:
        return {"error": f"Document {document_id} has no blob URI (text-only entry)"}

    try:
        raw_bytes = blob_store.get(doc.blob_uri)
        return Response(
            content=raw_bytes,
            media_type="application/octet-stream",
            headers={"X-Blob-URI": doc.blob_uri},
        )
    except FileNotFoundError:
        return {"error": f"Blob not found: {doc.blob_uri}"}


@router.get("/semantic-engine/kb/vectors")
async def semantic_engine_kb_vectors():
    """
    Flow 7: Read KB chunk vectors from Qdrant.
    SE → QD (7a: read KB vectors)
    """
    try:
        from qdrant_client.models import ScrollRequest
        results = qdrant.client.scroll(
            collection_name="company_shared",
            limit=100,
            with_payload=True,
            with_vectors=False,
        )
        points, _next_offset = results
        return {
            "collection": "company_shared",
            "points": [
                {
                    "id": str(p.id),
                    "content": p.payload.get("content", "") if p.payload else "",
                    "type": p.payload.get("type", "") if p.payload else "",
                    "source_id": p.payload.get("source_id", "") if p.payload else "",
                }
                for p in points
            ],
            "total": len(points),
        }
    except Exception as e:
        return {"collection": "company_shared", "points": [], "total": 0, "error": str(e)}
