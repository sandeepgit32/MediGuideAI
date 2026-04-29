"""RAG (Retrieval-Augmented Generation) Service Module.

This module provides a Retrieval-Augmented Generation service that leverages a Docker-hosted
Chroma vector database server for semantic search over medical guidelines. The service loads
clinical guidelines from a JSON data file and enables similarity-based retrieval of relevant
documents for medical consultation queries.

The RAGService class handles:
- Loading and managing clinical guidelines documents
- Connecting to a Docker-hosted Chroma server via REST API
- Creating and managing vector database collections
- Performing semantic similarity search queries

Key Features:
- Asynchronous initialization to avoid blocking operations
- Server-side embedding computation via Chroma for reduced local resource usage
- Graceful error handling with fallback to empty results on failures
- Singleton pattern for application-wide access

Requirements:
- A running Chroma server (Docker-hosted, configured via CHROMA_SERVER_HOST)
- clinical guidelines data in JSON format (backend/data/clinical_guideline.json)
- chromadb Python package for Chroma client

Example:
    Initialize and use the RAG service in an async context:

    >>> from services.rag_service import rag_service
    >>> await rag_service.initialize()
    >>> results = rag_service.query("symptoms of pneumonia", top_k=5)
"""

import os
import json
import asyncio
import logging
from typing import List

from ..config import settings

logger = logging.getLogger(__name__)


class RAGService:
    """RAG service backed by a Docker-hosted Chroma server (REST API).

    This service requires a running Chroma server (configure `CHROMA_SERVER_HOST`
    in the environment or via `backend/config.py`). The Chroma server will
    compute embeddings server-side; local embedding models are intentionally
    removed to keep the image small and rely on the Docker-hosted vector DB.
    """

    def __init__(self):
        """Initialize the RAG service.

        Sets up instance variables for the Chroma client, collection, and loaded documents.
        The service is not initialized until `initialize()` is called.
        """
        self.client = None
        self.collection = None
        self.docs: List[str] = []
        self._initialized = False
        # default data path
        self.data_path = os.path.join(
            os.path.dirname(__file__), "..", "data", "clinical_guideline.json"
        )

    async def initialize(self):
        """Initialize the Chroma collection asynchronously.

        Loads clinical guidelines documents from the data file and sets up the Chroma
        vector database collection. This method only executes once; subsequent calls
        are no-ops if already initialized.

        Raises:
            RuntimeError: If CHROMA_SERVER_HOST is not configured.
            Exception: If chromadb import fails or if document loading fails.
        """
        if self._initialized:
            return
        # Run the synchronous initialization in a thread to avoid blocking the event loop.
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._sync_build)
        self._initialized = True

    def _sync_build(self):
        """Synchronously build and initialize the Chroma collection.

        Loads clinical guidelines documents from the JSON data file, connects to the
        Docker-hosted Chroma server, and creates/retrieves the collection. If the
        collection is empty, adds documents with server-side embedding computation.

        Raises:
            RuntimeError: If CHROMA_SERVER_HOST environment variable is not set.
            Exception: If chromadb import or Chroma operations fail.
        """
        # Load docs
        try:
            data_file = os.path.abspath(
                os.path.join(
                    os.path.dirname(__file__), "..", "data", "clinical_guideline.json"
                )
            )
            logger.info("Loading clinical guidelines from %s", data_file)
            with open(data_file, "r", encoding="utf-8") as f:
                items = json.load(f)
            self.docs = [it.get("text", "") for it in items]
            logger.info("Loaded %d clinical guideline document(s)", len(self.docs))
        except Exception:
            logger.exception("Failed to load RAG docs; using empty list")
            self.docs = []

        if not self.docs:
            self.collection = None
            return

        try:
            import chromadb
        except Exception as exc:
            logger.exception("Failed to import chromadb: %s", exc)
            raise

        # Require a Docker-hosted Chroma server for embeddings.
        if not settings.CHROMA_SERVER_HOST:
            raise RuntimeError(
                "CHROMA_SERVER_HOST is not configured. This deployment requires a Docker-hosted Chroma server (set CHROMA_SERVER_HOST to 'chroma' when using docker-compose)."
            )

        logger.info(
            "Connecting to Chroma server at %s:%d",
            settings.CHROMA_SERVER_HOST,
            settings.CHROMA_SERVER_HTTP_PORT,
        )
        client = chromadb.HttpClient(
            host=settings.CHROMA_SERVER_HOST,
            port=settings.CHROMA_SERVER_HTTP_PORT,
        )
        collection = client.get_or_create_collection(
            name=settings.CHROMA_COLLECTION_NAME
        )
        logger.info("Using Chroma collection: %r", settings.CHROMA_COLLECTION_NAME)

        # If collection empty, add documents (server will compute embeddings)
        try:
            info = collection.get(limit=1)
            has_docs = bool(info and info.get("ids"))
        except Exception:
            has_docs = False
        if not has_docs and self.docs:
            logger.info("Collection is empty; indexing %d document(s)", len(self.docs))
            ids = [f"doc-{i}" for i in range(len(self.docs))]
            metadatas = [
                {"source": "clinical_guidelines", "idx": i} for i in range(len(self.docs))
            ]
            collection.add(ids=ids, documents=self.docs, metadatas=metadatas)
            logger.info("Indexed %d document(s) into Chroma", len(self.docs))
        else:
            logger.info("Chroma collection already populated; skipping indexing")

        self.client = client
        self.collection = collection
        logger.info(
            "Initialized Chroma collection '%s' with %d documents",
            settings.CHROMA_COLLECTION_NAME,
            len(self.docs),
        )

    def query(self, query_text: str, top_k: int = None) -> List[str]:
        """Query the Chroma collection for relevant documents.

        Performs a semantic search on the clinical guidelines documents using the provided
        query text and returns the top-k most relevant documents.

        Args:
            query_text (str): The search query text to find relevant documents.
            top_k (int, optional): Maximum number of results to return. If None, uses
                the default value from settings.RAG_TOP_K.

        Returns:
            List[str]: A list of up to top_k document texts ranked by relevance.
                Returns an empty list if the collection is not initialized or if the
                query fails.
        """
        if top_k is None:
            top_k = settings.RAG_TOP_K
        if not self.collection:
            logger.warning("RAG query skipped: collection not initialized")
            return []
        logger.debug("RAG query: top_k=%d text=%r", top_k, query_text[:120])
        try:
            res = self.collection.query(query_texts=[query_text], n_results=top_k)
            # result format: dict with keys like 'ids','documents','distances'
            docs = []
            if isinstance(res, dict):
                docs = res.get("documents", [[]])[0]
            logger.info("RAG query returned %d document(s)", len(docs or []))
            return docs or []
        except Exception:
            logger.exception("Chroma query failed")
            return []


# module-level singleton used by app
rag_service = RAGService()
