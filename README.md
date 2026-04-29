# MediGuideAI

**AI-powered Medical Symptom Triage and Guidance Assistant for Rural / Low-Resource Areas**

MediGuideAI is a production-oriented MVP that helps patients in low-resource areas describe their symptoms and receive structured, safety-reviewed triage guidance — in their own language. It deliberately avoids providing diagnoses or prescriptions, and always defers to clinical professionals for final decisions.

---

## Table of Contents

- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Environment Variables](#environment-variables)
- [Quickstart](#quickstart)
- [API Reference](#api-reference)
- [Agent Pipeline](#agent-pipeline)
- [Known Issues](#known-issues)
- [Roadmap](#roadmap)

---

## Architecture

```
┌─────────────────────────────────────────────┐
│                  Browser                    │
│           React + Vite Frontend             │
│                (port 3000)                  │
└────────────────────┬────────────────────────┘
                     │ HTTP /chat (multi-turn)
┌────────────────────▼────────────────────────┐
│           FastAPI Backend (port 8000)       │
│                                             │
│  ┌──────────────────────────────────────┐   │
│  │            Agent Pipeline            │   │
│  │                                      │   │
│  │  Language Agent --> Triage Agent --> │   │
│  │  Escalation Agent --> Safety Agent   │   │
│  └──────────────────────────────────────┘   │
│                                             │
│  ┌───────────────┐   ┌───────────────────┐  │
│  │  Chroma       │   │   In-memory       │  │
│  │  RAG + Mem0   │   │  session store    │  │
│  │  agent memory │   │  (TTL: 30 min)    │  │
│  └───────────────┘   └───────────────────┘  │
└─────────────────────────────────────────────┘
```

LLM inference is handled via any **OpenAI-compatible API** (configurable via `LLM_API_URL`; defaults to Groq). The model name is set with `MODEL_NAME`. When no API key is set the system falls back to a deterministic keyword-based heuristic so the MVP remains functional for local testing.

Agent memory is provided by **Mem0 OSS** (`Memory.from_config`) backed by the Docker-hosted **Chroma** server (dedicated `mem0_agent_memory` collection). Active consultation sessions are held in an **in-memory session store** (TTL: 30 minutes); no data survives a server restart.

---

## Project Structure

```
MediGuideAI/
├── backend/
│   ├── agents/              # Pydantic-AI agents (triage, safety, escalation, language)
│   ├── data/                # clinical guidelines seed data (clinical_guideline.json)
│   ├── routes/              # FastAPI route handlers
│   ├── schemas/             # Pydantic request/response models
│   ├── services/
│   │   ├── agent_memory.py      # Mem0 OSS agent memory (Chroma-backed)
│   │   ├── session_store.py     # In-memory multi-turn session store (TTL 30 min)
│   │   ├── rag_service.py       # Chroma RAG over clinical guidelines
│   │   └── llm_client.py        # OpenAI-compatible LLM HTTP client (UTF-8 safe)
│   ├── utils/               # Prompt builders
│   ├── config.py            # Settings loaded from environment variables
│   ├── main.py              # FastAPI application entry point
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/      # Chat UI component
│   │   └── services/        # Axios API client
│   ├── nginx.conf           # nginx config (listens on port 3000)
│   ├── index.html
│   ├── vite.config.js
│   └── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## Prerequisites

| Tool | Minimum version | Purpose |
|------|----------------|---------|
| Docker | 24+ | Run all services |
| Docker Compose | v2 (`docker compose`) | Orchestrate services |
| Node.js | 18+ | Frontend development |
| Python | 3.11+ | Backend development |

---

## Environment Variables

Create a `.env` file in the project root before starting the services. All variables are optional unless marked **required**.

```dotenv
# Copy to .env and update values

# ── LLM ──────────────────────────────────────────────────────────────────────
# Required for live LLM inference. Without this the heuristic fallback is used.
LLM_API_KEY=<YOUR_API_KEY_HERE>

# OpenAI-compatible base URL. Defaults to Groq; override to use any compatible provider.
# Examples:
#   Groq:      https://api.groq.com/openai/v1
#   OpenAI:    https://api.openai.com/v1
#   Ollama:    http://localhost:11434/v1
LLM_API_URL=https://api.groq.com/openai/v1

# Model name supported by the configured provider.
# Examples: llama-3.1-8b-instant  |  llama-3.3-70b-versatile
MODEL_NAME=llama-3.1-8b-instant

# ── Vector DB (Chroma) ────────────────────────────────────────────────────────
# Set automatically by docker-compose. Override when pointing to an external server.
CHROMA_SERVER_HOST=chroma
CHROMA_SERVER_HTTP_PORT=8000
CHROMA_COLLECTION_NAME=clinical_guidelines

# ── Agent Memory (Mem0 OSS) ───────────────────────────────────────────────────
# Mem0 OSS runs locally; no cloud API key is required.
#
# LLM used by Mem0 for fact extraction. Defaults to MODEL_NAME if not set.
MEM0_LLM_MODEL=<YOUR_API_KEY_HERE>

# Embedder for vectorising memories. Groq does not provide an embeddings
# endpoint, so configure a separate OpenAI-compatible provider here.
# Examples:
#   OpenAI:   https://api.openai.com/v1  +  text-embedding-3-small
#   Gemini:   https://api.gemini.com/v1  +  models/gemini-2.0-pro-embed-text-001
#   Ollama:   http://localhost:11434/v1  +  nomic-embed-text
MEM0_EMBED_API_URL=https://api.gemini.com/v1
MEM0_EMBED_API_KEY=<YOUR_API_KEY_HERE>
MEM0_EMBED_MODEL=models/gemini-2.0-pro-embed-text-001


# ── RAG ───────────────────────────────────────────────────────────────────────
RAG_TOP_K=3

# ── CORS ──────────────────────────────────────────────────────────────────────
# Comma-separated list of allowed origins. Defaults to wildcard (*) if omitted.
ALLOWED_ORIGINS=http://localhost:5173,http://localhost

# ── Localisation ─────────────────────────────────────────────────────────────
DEFAULT_LANGUAGE=en
```

> **Security note:** Never commit your `.env` file. Add it to `.gitignore`.

---

## Quickstart

### Using Docker Compose 

```bash
# 1. Clone and enter the repository
git clone <repository-url>
cd MediGuideAI

# 2. Configure the environment
cp .env.example .env
# Edit .env and set at minimum LLM_API_KEY

# 3. Build and start all services
docker compose up --build

# 4. Open the UI
#    Frontend:  http://localhost:3000
#    API docs:  http://localhost:8000/docs

# 5. Stop and remove containers
docker compose down
```

Services started by Docker Compose:

| Service | Host port | Description |
|---------|-----------|-------------|
| `backend` | `8000` | FastAPI application |
| `frontend` | `3000` | React/Nginx UI |
| `chroma` | `8001` | Chroma vector DB (RAG + Mem0 agent memory) |

---

## API Reference

All consultation interactions go through a **session-based multi-turn API**. Each session is identified by a `session_id` UUID returned on the first request and is held in memory for 30 minutes of inactivity.

### `POST /chat`

Unified endpoint for all interaction types, distinguished by the `type` field.

#### `type: "initial"` — Start a new consultation

**Request body**

```json
{
  "type": "initial",
  "age": 45,
  "gender": "male",
  "symptoms": ["chest pain", "shortness of breath"],
  "duration": "2 hours",
  "existing_conditions": ["hypertension"],
  "language": "en"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `"initial"` | Yes | Interaction type |
| `age` | integer (0-120) | Yes | Patient age |
| `gender` | string | No | Patient gender |
| `symptoms` | string[] (min 1) | Yes | List of symptom phrases |
| `duration` | string | Yes | How long symptoms have been present |
| `existing_conditions` | string[] | No | Pre-existing conditions |
| `language` | string (ISO 639-1) | No | Patient language; auto-detected if omitted |

#### `type: "answer"` — Reply to a clarifying question

```json
{
  "type": "answer",
  "session_id": "<uuid>",
  "message": "It started suddenly after climbing stairs."
}
```

#### `type: "followup"` — Ask a follow-up question after a result

```json
{
  "type": "followup",
  "session_id": "<uuid>",
  "message": "What warning signs should I watch for?"
}
```

**Response** (all types)

The `type` field in the response indicates which fields are populated:

| Response `type` | Meaning | Populated fields |
|----------------|---------|------------------|
| `question` | Agent needs one more clarification | `session_id`, `question` |
| `result` | Triage result ready | `session_id`, `severity`, `possible_conditions`, `recommended_action`, `urgency`, `notes`, `safety` |
| `answer` | Follow-up answer | `session_id`, `answer` |

**Example `result` response**

```json
{
  "type": "result",
  "session_id": "3f8a1b2c-...",
  "severity": "high",
  "possible_conditions": ["may suggest acute cardiac event"],
  "recommended_action": "Seek immediate medical help at the nearest emergency facility.",
  "urgency": "immediate",
  "notes": null,
  "safety": {
    "is_safe": true,
    "risk_flags": [],
    "override_message": null
  }
}
```

**Severity levels**

| Value | Meaning |
|-------|---------|
| `low` | Self-monitor; home care appropriate |
| `medium` | Consult a clinician within 24 hours |
| `high` | Seek emergency medical care immediately |

### `DELETE /session/{session_id}`

Explicitly end a session and clear its Mem0 memory. Called automatically by the frontend when starting a new consultation.

Returns `{"ok": true}`.

### `GET /`

Health check. Returns `{"ok": true, "service": "MediGuideAI"}`.

---

## Agent Pipeline

Each `POST /chat` request passes through a sequential agent pipeline. The triage agent may ask up to 3 clarifying questions before producing a result, maintaining full conversation history across turns within the session.

```
PatientInput
    │
    ▼
┌─────────────────┐   Detects and translates non-English symptoms to English
│  Language Agent │   before downstream processing.
└────────┬────────┘
         │
         ▼
┌─────────────────┐   Queries Chroma for relevant clinical guideline context,
│   RAG Retrieval │   then passes top-K documents to the triage agent.
└────────┬────────┘
         │
         ▼
┌─────────────────┐   Produces TriageOutput: severity, possible_conditions,
│   Triage Agent  │   recommended_action, urgency.
└────────┬────────┘
         │
    ┌────┴─────────────────────────────────────┐
    ▼                                          ▼
┌──────────────────┐               ┌───────────────────┐
│ Escalation Agent │               │   Safety Agent    │
│                  │               │                   │
│ Detects red-flag │               │ Audits triage for │
│ emergency signs. │               │ unsafe advice;    │
│ Forces severity  │               │ applies override  │
│ = "high" when    │               │ if needed.        │
│ triggered.       │               └───────────────────┘
└──────────────────┘
         │
         ▼
  Final JSON response
```

All agents are built with **Pydantic-AI** and share the model configured via `MODEL_NAME`. The agents are provider-agnostic; switching models requires only an environment variable change.

---

## Disclaimer

MediGuideAI is a decision-support tool, not a substitute for professional medical advice, diagnosis, or treatment. All triage outputs should be reviewed by a qualified health worker before acting on them. The system is intentionally conservative and will always recommend clinical review when uncertain.
