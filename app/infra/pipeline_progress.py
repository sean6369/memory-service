"""
Pipeline Progress — thread-safe in-memory progress store for distillation streaming.

Tracks pipeline events per conversation_id so the SSE endpoint can stream
them to the frontend in real time.
"""

import threading
import time


class PipelineProgress:
    """Thread-safe store for pipeline progress events."""

    def __init__(self):
        self._progress: dict[str, list[dict]] = {}
        self._lock = threading.Lock()

    def start(self, conversation_id: str) -> None:
        """Initialize progress tracking for a conversation."""
        with self._lock:
            self._progress[conversation_id] = []

    def update(self, conversation_id: str, step: str, detail: str, data: dict | None = None) -> None:
        """Append a progress event."""
        with self._lock:
            if conversation_id in self._progress:
                self._progress[conversation_id].append({
                    "step": step,
                    "detail": detail,
                    "data": data or {},
                    "done": False,
                    "ts": time.time(),
                })

    def complete(self, conversation_id: str, data: dict | None = None) -> None:
        """Mark pipeline as complete."""
        with self._lock:
            if conversation_id in self._progress:
                self._progress[conversation_id].append({
                    "step": "complete",
                    "detail": "Pipeline finished",
                    "data": data or {},
                    "done": True,
                    "ts": time.time(),
                })

    def error(self, conversation_id: str, message: str) -> None:
        """Record a pipeline error."""
        with self._lock:
            if conversation_id in self._progress:
                self._progress[conversation_id].append({
                    "step": "error",
                    "detail": message,
                    "data": {},
                    "done": True,
                    "ts": time.time(),
                })

    def get_updates(self, conversation_id: str, after: int = 0) -> list[dict]:
        """Get events after a given cursor position."""
        with self._lock:
            events = self._progress.get(conversation_id, [])
            return events[after:]

    def cleanup(self, conversation_id: str) -> None:
        """Remove progress data for a conversation."""
        with self._lock:
            self._progress.pop(conversation_id, None)


# Singleton
pipeline_progress = PipelineProgress()
