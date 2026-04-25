"""
Consultation Store Service

Uses MongoDB (Motor async driver) purely as a raw-record storage layer.  Every
completed consultation is written as a structured document containing the original
patient input, the triage result, safety assessment, and emergency flags.  This
provides a durable, queryable audit trail that is completely independent of the
agent memory layer.
"""

import asyncio
import logging
from typing import Optional

from ..config import settings

logger = logging.getLogger(__name__)


class ConsultationStore:
    """
    MongoDB storage layer for raw patient consultation records.

    Persists a complete, structured record of every consultation:
      - Original patient input (age, gender, symptoms, duration, existing conditions)
      - Triage result (severity, possible conditions, recommended action, urgency)
      - Safety assessment (risk flags, override message)
      - Emergency escalation flags
      - Timestamp

    Uses Motor (async MongoDB driver) so writes never block the event loop.
    This layer is entirely independent of agent memory; it exists for auditability,
    analytics, and potential clinician review workflows.

    Attributes:
        _client: Motor ``AsyncIOMotorClient`` instance.
        _db: MongoDB database handle.
        _collection: MongoDB collection handle for ``consultations``.
    """

    def __init__(self):
        """Create the store in an uninitialised state. Call ``initialize()`` before use."""
        self._client = None
        self._db = None
        self._collection = None

    async def initialize(self) -> None:
        """
        Connect to MongoDB and prepare the consultations collection.

        Reads connection details from environment via ``settings``:
          - ``MONGODB_URI``: MongoDB connection string (default: ``mongodb://mongo:27017``)
          - ``MONGODB_DB``: Database name (default: ``mguide``)
          - ``MONGODB_CONSULTATIONS_COLLECTION``: Collection name (default: ``consultations``)

        Creates a unique index on ``consultation_id`` for efficient lookups.

        Raises:
            RuntimeError: If ``MONGODB_URI`` is not configured.
        """
        uri = settings.MONGODB_URI
        if not uri:
            raise RuntimeError("MONGODB_URI is not configured")
        from motor.motor_asyncio import AsyncIOMotorClient

        self._client = AsyncIOMotorClient(uri)
        self._db = self._client[settings.MONGODB_DB]
        self._collection = self._db[settings.MONGODB_CONSULTATIONS_COLLECTION]
        await self._collection.create_index("consultation_id", unique=True)
        logger.info(
            "Connected to MongoDB consultation store: %s/%s",
            settings.MONGODB_URI,
            settings.MONGODB_DB,
        )

    async def save(self, consultation_id: str, data: dict) -> None:
        """
        Persist or overwrite a consultation record.

        Performs a MongoDB upsert keyed on ``consultation_id``.  If a document with
        that ID already exists it is replaced in-place; otherwise a new document is
        inserted.

        Args:
            consultation_id (str): Unique identifier for this consultation (UUID).
            data (dict): Full consultation payload including patient input, triage
                         result, safety assessment, and emergency flags.

        Raises:
            RuntimeError: If ``initialize()`` has not been called.
        """
        if not self._collection:
            raise RuntimeError("ConsultationStore not initialized")
        logger.info("Saving consultation id=%s", consultation_id)
        await self._collection.update_one(
            {"consultation_id": consultation_id},
            {
                "$set": {
                    "data": data,
                    "updated_at": asyncio.get_running_loop().time(),
                }
            },
            upsert=True,
        )
        logger.info("Consultation id=%s saved to MongoDB", consultation_id)

    async def get(self, consultation_id: str) -> Optional[dict]:
        """
        Retrieve a consultation record by ID.

        Args:
            consultation_id (str): Unique identifier for the consultation.

        Returns:
            dict or None: The stored consultation data, or ``None`` if not found.
        """
        if not self._collection:
            logger.warning("get called but ConsultationStore not initialized")
            return None
        logger.debug("Fetching consultation id=%s", consultation_id)
        doc = await self._collection.find_one({"consultation_id": consultation_id})
        if doc:
            logger.debug("Consultation id=%s found", consultation_id)
        else:
            logger.debug("Consultation id=%s not found", consultation_id)
        return doc.get("data") if doc else None


# Module-level singleton — I/O is deferred to initialize(), called from main.py lifespan.
consultation_store = ConsultationStore()
