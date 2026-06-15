"""
In-memory session store for trip planning runs.

Each session has a unique trip_id. The SSE endpoint reads from the
session's event queue. The background task writes to it.

Thread-safety: we use threading.Lock for all mutations. The background
task (run_with_progress) runs in a thread via run_in_executor; the SSE
endpoint reads from the queue from the async event loop via asyncio.
We use a threading.Queue so both sides can access it safely.
"""
from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class TripSession:
    trip_id: str
    initial_state: dict[str, Any]
    event_queue: queue.Queue = field(default_factory=queue.Queue)
    is_complete: bool = False
    final_state: Optional[dict[str, Any]] = None
    error: Optional[str] = None


_store: dict[str, TripSession] = {}
_lock = threading.Lock()


def create_session(trip_id: str, initial_state: dict[str, Any]) -> TripSession:
    """Create and register a new session."""
    session = TripSession(trip_id=trip_id, initial_state=initial_state)
    with _lock:
        _store[trip_id] = session
    return session


def get_session(trip_id: str) -> Optional[TripSession]:
    """Retrieve a session by ID."""
    with _lock:
        return _store.get(trip_id)


def mark_complete(trip_id: str, final_state: dict[str, Any]) -> None:
    """Mark a session as complete and store the final state."""
    with _lock:
        s = _store.get(trip_id)
        if s:
            s.final_state = final_state
            s.is_complete = True
            s.event_queue.put({"type": "__done__"})  # sentinel


def mark_error(trip_id: str, error: str) -> None:
    """Mark a session as failed with an error message."""
    with _lock:
        s = _store.get(trip_id)
        if s:
            s.error = error
            s.is_complete = True
            s.event_queue.put({"type": "__done__"})


def push_event(trip_id: str, event: dict[str, Any]) -> None:
    """Push a progress event into the session's queue."""
    with _lock:
        s = _store.get(trip_id)
    if s:
        s.event_queue.put(event)
