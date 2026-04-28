"""In-memory session store for MediGuideAI multi-turn chat sessions.

Each session is keyed by a UUID and holds the full conversation history,
patient data, RAG context, and triage result for one consultation.

Sessions expire after SESSION_TTL_SECONDS of inactivity (default 30 minutes).
A background asyncio task (started from main.py lifespan) evicts stale sessions
every EVICTION_INTERVAL_SECONDS.

No data survives a server restart — consistent with the no-persistent-storage
design requirement.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

logger = logging.getLogger(__name__)

SESSION_TTL_SECONDS: int = 30 * 60  # 30 minutes
EVICTION_INTERVAL_SECONDS: int = 5 * 60  # check every 5 minutes
MAX_CLARIFICATIONS: int = 3


@dataclass
class SessionData:
    """All state for a single multi-turn consultation session."""

    session_id: str
    language: str  # ISO-639-1 code of patient's language
    symptoms_en: List[str]  # English-translated symptoms
    rag_contexts: List[str]  # RAG excerpts retrieved at session start
    conversation: List[Dict]  # [{role, content}] in English
    clarification_count: int = 0  # number of clarifying questions asked
    phase: Literal["clarifying", "result_shown"] = "clarifying"
    triage_result: Optional[Dict] = None  # dict copy of TriageOutput once produced
    created_at: float = field(default_factory=time.monotonic)
    last_used: float = field(default_factory=time.monotonic)

    # Original patient demographics (stored so the triage prompt always has them)
    age: int = 0
    gender: Optional[str] = None
    duration: str = ""
    existing_conditions: List[str] = field(default_factory=list)

    def touch(self) -> None:
        """Update last-used timestamp to extend the session TTL."""
        self.last_used = time.monotonic()

    def is_expired(self) -> bool:
        """Return True if the session has been idle longer than SESSION_TTL_SECONDS."""
        return (time.monotonic() - self.last_used) > SESSION_TTL_SECONDS


# ---------------------------------------------------------------------------
# Module-level session registry
# ---------------------------------------------------------------------------

_sessions: Dict[str, SessionData] = {}
_eviction_task: Optional[asyncio.Task] = None


def create_session(
    language: str,
    symptoms_en: List[str],
    rag_contexts: List[str],
    age: int,
    gender: Optional[str],
    duration: str,
    existing_conditions: Optional[List[str]] = None,
) -> SessionData:
    """Create a new session and register it in the store.

    Returns the newly created :class:`SessionData` instance.
    """
    session_id = str(uuid.uuid4())
    session = SessionData(
        session_id=session_id,
        language=language,
        symptoms_en=symptoms_en,
        rag_contexts=rag_contexts,
        conversation=[],
        age=age,
        gender=gender,
        duration=duration,
        existing_conditions=existing_conditions or [],
    )
    _sessions[session_id] = session
    logger.info("Session created: %s (language=%s)", session_id, language)
    return session


def get_session(session_id: str) -> Optional[SessionData]:
    """Retrieve a session by ID, refreshing its TTL.  Returns None if not found."""
    session = _sessions.get(session_id)
    if session is None:
        return None
    if session.is_expired():
        logger.info("Session %s accessed but already expired; removing", session_id)
        del _sessions[session_id]
        return None
    session.touch()
    return session


def delete_session(session_id: str) -> bool:
    """Delete a session by ID.  Returns True if it existed, False otherwise."""
    existed = session_id in _sessions
    _sessions.pop(session_id, None)
    if existed:
        logger.info("Session deleted: %s", session_id)
    return existed


# ---------------------------------------------------------------------------
# Background TTL eviction
# ---------------------------------------------------------------------------


async def _eviction_loop() -> None:
    """Background coroutine that removes expired sessions every EVICTION_INTERVAL_SECONDS."""
    while True:
        await asyncio.sleep(EVICTION_INTERVAL_SECONDS)
        expired = [sid for sid, s in list(_sessions.items()) if s.is_expired()]
        if expired:
            logger.info("TTL eviction: removing %d expired session(s)", len(expired))
            for sid in expired:
                _sessions.pop(sid, None)
                # Best-effort: notify memory service to clean up mem0 vectors
                try:
                    from .agent_memory import memory_service

                    await memory_service.delete_session_memory(sid)
                except Exception:
                    logger.debug(
                        "Could not delete mem0 memories for evicted session %s", sid
                    )


def start_eviction_task() -> asyncio.Task:
    """Spawn the background eviction coroutine and return the task handle."""
    global _eviction_task
    _eviction_task = asyncio.create_task(_eviction_loop())
    logger.info(
        "Session eviction task started (TTL=%ds, interval=%ds)",
        SESSION_TTL_SECONDS,
        EVICTION_INTERVAL_SECONDS,
    )
    return _eviction_task


def stop_eviction_task() -> None:
    """Cancel the background eviction task on shutdown."""
    global _eviction_task
    if _eviction_task and not _eviction_task.done():
        _eviction_task.cancel()
        logger.info("Session eviction task stopped")
    _eviction_task = None
