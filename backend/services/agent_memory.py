"""
Agent Memory Service

Uses Mem0 OSS (``Memory.from_config``) backed by the Docker-hosted Chroma server
as the vector store.  Mem0 extracts structured facts from patient-agent conversations,
embeds them, and stores them in Chroma under a dedicated ``mem0_agent_memory``
collection.  On subsequent consultations the same patient's past memories are
retrieved as additional context, enabling personalised triage over time.

The Mem0 LLM and embedder are each individually configurable via environment
variables, so any OpenAI-compatible provider (Groq, OpenAI, Ollama, …) can be used.
"""

import asyncio
import logging
from typing import Dict, List

from ..config import settings

logger = logging.getLogger(__name__)


class AgentMemoryService:
    """
    Self-hosted Mem0 agent memory backed by Chroma.

    Wraps the Mem0 OSS ``Memory`` class (``mem0ai`` package) configured with:
      - An OpenAI-compatible LLM for fact extraction (``LLM_API_URL`` / ``LLM_API_KEY``).
      - An OpenAI-compatible embedder for vectorising memories
        (``MEM0_EMBED_API_URL`` / ``MEM0_EMBED_API_KEY`` / ``MEM0_EMBED_MODEL``).
      - Chroma as the vector store, connecting to the Docker-hosted Chroma server
        under a dedicated ``mem0_agent_memory`` collection (separate from RAG data).

    All Mem0 SDK calls are synchronous; they are executed in a thread-pool executor
    so the FastAPI async event loop is never blocked.

    Attributes:
        _memory: Initialised ``mem0.Memory`` instance (set after ``initialize()``).
    """

    def __init__(self):
        """Create the service in an uninitialised state. Call ``initialize()`` before use."""
        self._memory = None

    async def initialize(self) -> None:
        """
        Build and connect the Mem0 Memory instance.

        Constructs a ``Memory.from_config`` with the following components, all
        driven by environment variables via ``settings``:
          - ``llm``     → ``LLM_API_URL`` / ``LLM_API_KEY`` / ``MEM0_LLM_MODEL``
          - ``embedder`` → ``MEM0_EMBED_API_URL`` / ``MEM0_EMBED_API_KEY`` / ``MEM0_EMBED_MODEL``
          - ``vector_store`` → Chroma at ``CHROMA_SERVER_HOST``:``CHROMA_SERVER_HTTP_PORT``

        The initialisation is run in a thread-pool executor to avoid blocking
        the async event loop.

        Raises:
            RuntimeError: If Mem0 cannot connect to Chroma or the configured LLM endpoint.
        """
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._sync_init)
        logger.info("Initialized AgentMemoryService (Mem0 OSS + Chroma)")

    def _sync_init(self) -> None:
        """
        Synchronous Mem0 initialisation — intended to be called from a thread-pool executor.

        Builds the ``Memory.from_config`` dict and instantiates the ``Memory`` object.
        Separated from ``initialize()`` so it can safely perform blocking I/O.
        """
        from mem0 import Memory

        if settings.MEM0_EMBED_API_URL == settings.LLM_API_URL:
            logger.warning(
                "MEM0_EMBED_API_URL (%s) is the same as LLM_API_URL. "
                "Many providers (e.g. Groq) do not expose a /v1/embeddings endpoint. "
                "Set MEM0_EMBED_API_URL and MEM0_EMBED_API_KEY to a provider that "
                "supports embeddings (e.g. OpenAI, a local Ollama instance).",
                settings.MEM0_EMBED_API_URL,
            )

        config = {
            "llm": {
                "provider": "openai",
                "config": {
                    "model": settings.MEM0_LLM_MODEL,
                    "openai_base_url": settings.LLM_API_URL,
                    "api_key": settings.LLM_API_KEY or "not-set",
                    "temperature": 0.1,
                    "max_tokens": 2000,
                },
            },
            "embedder": {
                "provider": "openai",
                "config": {
                    "model": settings.MEM0_EMBED_MODEL,
                    "openai_base_url": settings.MEM0_EMBED_API_URL,
                    "api_key": settings.MEM0_EMBED_API_KEY or "not-set",
                },
            },
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": "mem0_agent_memory",
                    "host": settings.CHROMA_SERVER_HOST or "localhost",
                    "port": settings.CHROMA_SERVER_HTTP_PORT,
                },
            },
        }
        self._memory = Memory.from_config(config)

    async def add_memory(self, user_id: str, messages: List[Dict[str, str]]) -> None:
        """
        Ingest a consultation conversation into Mem0 agent memory for a given patient.

        Mem0 processes the message list, extracts structured facts (e.g. reported
        symptoms, existing conditions, past triage outcomes) and stores them as
        vector embeddings in Chroma.  These facts are retrieved on future calls
        to ``search_memory`` to provide personalised triage context.

        Args:
            user_id (str): Stable identifier for the patient (e.g. a patient UUID).
            messages (list[dict]): OpenAI-style message list, e.g.:
                ``[{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]``

        Raises:
            RuntimeError: If ``initialize()`` has not been called.
        """
        if not self._memory:
            raise RuntimeError("AgentMemoryService not initialized")
        logger.info(
            "Storing memory for user_id=%r (%d message(s))", user_id, len(messages)
        )
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, lambda: self._memory.add(messages, user_id=user_id)
        )
        logger.info("Memory stored for user_id=%r", user_id)

    async def search_memory(self, user_id: str, query: str) -> List[str]:
        """
        Retrieve relevant memories for a patient from Mem0.

        Performs a semantic search over all memories stored for ``user_id`` using
        the provided query string (typically the patient's reported symptoms).

        Args:
            user_id (str): Stable identifier for the patient.
            query (str): Natural-language query, e.g. ``"chest pain shortness of breath"``.

        Returns:
            list[str]: Recalled memory strings ordered by relevance.  Returns an
                       empty list if no memories exist or the service is uninitialised.
        """
        if not self._memory:
            logger.warning(
                "search_memory called but service not initialized; returning []"
            )
            return []
        logger.info("Searching memory for user_id=%r query=%r", user_id, query[:80])
        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(
            None,
            lambda: self._memory.search(query, filters={"user_id": user_id}),
        )
        # Mem0 search returns {"results": [{"memory": "...", "score": ...}, ...]}
        memories: List[str] = []
        if isinstance(results, dict):
            for entry in results.get("results", []):
                if isinstance(entry, dict) and "memory" in entry:
                    memories.append(entry["memory"])
        logger.info(
            "Memory search returned %d result(s) for user_id=%r", len(memories), user_id
        )
        return memories

    async def delete_session_memory(self, user_id: str) -> None:
        """Delete all Mem0 memories associated with *user_id* (session_id).

        Called when a session is explicitly deleted (``DELETE /session/{id}``)
        or evicted by the background TTL task.  Failures are silently logged so
        they never block the caller.

        Args:
            user_id: The session UUID used as the Mem0 ``user_id``.
        """
        if not self._memory:
            logger.warning(
                "delete_session_memory called but service not initialized; skipping"
            )
            return
        logger.info("Deleting mem0 memories for user_id=%r", user_id)
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(
                None, lambda: self._memory.delete_all(user_id=user_id)
            )
            logger.info("Mem0 memories deleted for user_id=%r", user_id)
        except Exception:
            logger.exception(
                "Failed to delete mem0 memories for user_id=%r (non-blocking)", user_id
            )


# Module-level singleton — I/O is deferred to initialize(), called from main.py lifespan.
memory_service = AgentMemoryService()
