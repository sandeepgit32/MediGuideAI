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
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routes.consult import router as consult_router
from .services.agent_memory import memory_service
from .services.consultation_store import consultation_store
from .services.rag_service import rag_service


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
    # Initialize RAG index and memory on startup (idempotent).
    await rag_service.initialize()
    await memory_service.initialize()
    await consultation_store.initialize()
    yield


app = FastAPI(
    title="MediGuideAI: Symptom Triage MVP",
    description="AI-powered symptom triage and guidance for rural/low-resource settings.",
    version="0.1.0",
    lifespan=lifespan,
)

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
    return {"ok": True, "service": "MediGuideAI"}


if __name__ == "__main__":
    """
    Entry point for local development.

    Runs Uvicorn with hot-reload enabled on localhost:8000.
    For production, use Gunicorn or similar with: gunicorn backend.main:app
    """
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
