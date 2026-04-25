from typing import List, Optional
import os


class Settings:
    """Load configuration from environment variables using `os.environ`.

    The `.env` file should be provided by the runtime environment (for example
    by `docker-compose`), so this module does not load any env-file itself.
    """

    def __init__(self):
        self.LLM_API_KEY: Optional[str] = os.environ.get("LLM_API_KEY")
        self.LLM_API_URL: str = os.environ.get("LLM_API_URL", "https://api.groq.com/openai/v1")
        self.MODEL_NAME: str = os.environ.get("MODEL_NAME", "llama3-8b-8192")

        # MongoDB settings (used as consultation storage layer)
        self.MONGODB_URI: Optional[str] = os.environ.get("MONGODB_URI", "mongodb://mongo:27017")
        self.MONGODB_DB: str = os.environ.get("MONGODB_DB", "mguide")
        self.MONGODB_CONSULTATIONS_COLLECTION: str = os.environ.get(
            "MONGODB_CONSULTATIONS_COLLECTION", "consultations"
        )

        # RAG
        rag_top_k = os.environ.get("RAG_TOP_K")
        try:
            self.RAG_TOP_K: int = int(rag_top_k) if rag_top_k is not None else 3
        except ValueError:
            self.RAG_TOP_K = 3

        # Mem0 (memory layer) configuration — local OSS, backed by Chroma
        # LLM used by Mem0 internally for fact extraction.
        # Defaults to the same model as the application LLM.
        self.MEM0_LLM_MODEL: str = os.environ.get("MEM0_LLM_MODEL") or self.MODEL_NAME

        # Embedder used by Mem0 to vectorise memories.
        # Groq does not expose an embeddings endpoint, so configure a separate
        # provider via MEM0_EMBED_API_URL / MEM0_EMBED_API_KEY / MEM0_EMBED_MODEL.
        # Defaults to OpenAI text-embedding-3-small.
        self.MEM0_EMBED_API_URL: str = os.environ.get(
            "MEM0_EMBED_API_URL", "https://api.openai.com/v1"
        )
        self.MEM0_EMBED_API_KEY: Optional[str] = (
            os.environ.get("MEM0_EMBED_API_KEY") or self.LLM_API_KEY
        )
        self.MEM0_EMBED_MODEL: str = os.environ.get("MEM0_EMBED_MODEL", "text-embedding-3-small")

        # Chroma (vector DB) configuration
        self.CHROMA_COLLECTION_NAME: str = os.environ.get("CHROMA_COLLECTION_NAME", "who_guidelines")
        self.CHROMA_SERVER_HOST: Optional[str] = os.environ.get("CHROMA_SERVER_HOST")
        chroma_port = os.environ.get("CHROMA_SERVER_HTTP_PORT")
        try:
            self.CHROMA_SERVER_HTTP_PORT: int = int(chroma_port) if chroma_port is not None else 8000
        except ValueError:
            self.CHROMA_SERVER_HTTP_PORT = 8000

        # CORS / localization
        allowed = os.environ.get("ALLOWED_ORIGINS")
        if allowed:
            self.ALLOWED_ORIGINS: List[str] = [s.strip() for s in allowed.split(",") if s.strip()]
        else:
            self.ALLOWED_ORIGINS = ["*"]

        self.DEFAULT_LANGUAGE: str = os.environ.get("DEFAULT_LANGUAGE", "en")

    def get_llm_model(self):
        """Return a pydantic-ai ``OpenAIChatModel`` configured from env vars.

        This constructs a model pointing at the OpenAI-compatible endpoint
        configured via ``LLM_API_URL`` / ``LLM_API_KEY`` / ``MODEL_NAME``, so
        any OpenAI-compatible provider (Groq, OpenAI, Ollama, …) works without
        code changes.
        """
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        return OpenAIChatModel(
            self.MODEL_NAME,
            provider=OpenAIProvider(
                base_url=self.LLM_API_URL,
                api_key=self.LLM_API_KEY or "not-set",
            ),
        )


settings = Settings()
