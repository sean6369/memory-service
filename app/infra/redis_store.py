import json

import redis

from app.config import settings

_redis = redis.Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    decode_responses=True,
)


def _session_key(session_id: str) -> str:
    return f"session:{session_id}:turns"


def _session_meta_key(session_id: str) -> str:
    return f"session:{session_id}:meta"


def append_turn(session_id: str, user_id: str, participant: str, content: str) -> int:
    """Append a turn to a live session in Redis. Returns the turn index."""
    turn = json.dumps({
        "participant": participant,
        "content": content,
    })
    # Store session metadata (user_id) if not set yet
    meta_key = _session_meta_key(session_id)
    if not _redis.exists(meta_key):
        _redis.hset(meta_key, mapping={"user_id": user_id})
    return _redis.rpush(_session_key(session_id), turn)


def get_turns(session_id: str) -> list[dict]:
    """Get all turns for a session."""
    raw = _redis.lrange(_session_key(session_id), 0, -1)
    return [json.loads(t) for t in raw]


def get_session_meta(session_id: str) -> dict | None:
    """Get session metadata."""
    meta = _redis.hgetall(_session_meta_key(session_id))
    return meta if meta else None


def flush_session(session_id: str) -> list[dict]:
    """Retrieve all turns and delete the session from Redis."""
    turns = get_turns(session_id)
    _redis.delete(_session_key(session_id))
    _redis.delete(_session_meta_key(session_id))
    return turns


def health_check() -> bool:
    """Check Redis connectivity."""
    try:
        return _redis.ping()
    except Exception:
        return False
