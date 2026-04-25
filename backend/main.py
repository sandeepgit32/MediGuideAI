"""
MediGuideAI Backend: FastAPI Application Entry Point

This module initializes and configures the FastAPI application for the MediGuideAI
symptom triage system. It sets up:
  - Lifespan event handlers for graceful service initialization
  - CORS middleware for cross-origin requests
  - Request routing to the consultation endpoint
  - Health check endpoint

The application is provider-agnostic and configurable via environment variables
(LLM_API_KEY, LLM_API_URL, MODEL_NAME, etc.). All configuration is loaded from
the settings module.
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routes.consult import router as consult_router
from .services.agent_memory import memory_service
from .services.consultation_store import consultation_store
from .services.rag_service import rag_service

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.

    Handles startup and shutdown events for the FastAPI application.

    **Startup (before yield):**
      - Initializes the RAG (Retrieval-Augmented Generation) service with
        Chroma vector database connection and WHO guideline embeddings.
      - Initializes the memory service (Mem0 OSS agent memory backed by Chroma).
      - Initializes the consultation store (MongoDB raw record storage).

    **Shutdown (after yield):**
      - Gracefully closes all service connections.

    Both initialization calls are idempotent; if services are already initialized,
    they return quickly without causing errors.

    Args:
        app: The FastAPI application instance.

    Yields:
        None
    """
    logger.info("MediGuideAI starting up — initializing services")
    try:
        await rag_service.initialize()
        logger.info("RAG service initialized")
    except Exception:
        logger.exception("RAG service initialization failed")
    try:
        await memory_service.initialize()
        logger.info("Agent memory service initialized")
    except Exception:
        logger.exception("Agent memory service initialization failed")
    try:
        await consultation_store.initialize()
        logger.info("Consultation store initialized")
    except Exception:
        logger.exception("Consultation store initialization failed")
    logger.info(
        "MediGuideAI startup complete (model=%s, allowed_origins=%s)",
        settings.MODEL_NAME,
        settings.ALLOWED_ORIGINS,
    )
    yield
    logger.info("MediGuideAI shutting down")


app = FastAPI(
    title="MediGuideAI: Symptom Triage MVP",
    description="AI-powered symptom triage and guidance for rural/low-resource settings.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every incoming HTTP request with method, path, and elapsed time."""
    start = time.perf_counter()
    logger.info("Request started: %s %s", request.method, request.url.path)
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "Request finished: %s %s → %d (%.1f ms)",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


# Configure CORS middleware to allow cross-origin requests from specified origins.
# Defaults to wildcard (*) if ALLOWED_ORIGINS is not set.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the consultation routes (POST /consult, etc.)
app.include_router(consult_router)


@app.get("/", tags=["Health"])
async def root():
    """
    Health check endpoint.

    Returns a simple JSON response to verify that the API is alive and responding.
    This endpoint can be used for load balancer health checks or deployment monitoring.

    Returns:
        dict: A simple response with status {"ok": true, "service": "MediGuideAI"}
    """
    logger.debug("Health check endpoint called")
    return {"ok": True, "service": "MediGuideAI"}


if __name__ == "__main__":
    """
    Entry point for local development.

    Runs Uvicorn with hot-reload enabled on localhost:8000.
    For production, use Gunicorn or similar with: gunicorn backend.main:app
    """
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
