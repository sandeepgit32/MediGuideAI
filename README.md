# MediGuideAI

**AI-powered Medical Symptom Triage and Guidance Assistant for Rural / Low-Resource Areas**

MediGuideAI is a production-oriented MVP that helps patients in low-resource areas describe their symptoms and receive structured, safety-reviewed triage guidance — in their own language. It deliberately avoids providing diagnoses or prescriptions, and always defers to clinical professionals for final decisions.

Patients register and sign in to receive a persistent identity across multiple consultations. The system uses this identity to build a cross-session memory of reported conditions, allergies, and past triage outcomes, which it feeds back into future consultations to provide personalised, context-aware triage.

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
                     │ HTTP (JWT Bearer token required for /chat)
┌────────────────────▼────────────────────────┐
│           FastAPI Backend (port 8000)       │
│                                             │
│  ┌──────────────────────────────────────┐   │
│  │         Auth Routes (/auth/*)        │   │
│  │  register · login · change-password  │   │
│  └──────────────────────────────────────┘   │
│                                             │
│  ┌──────────────────────────────────────┐   │
│  │            Agent Pipeline            │   │
│  │  (protected — JWT required)          │   │
│  │                                      │   │
│  │  Language Agent --> Triage Agent --> │   │
│  │               Safety Agent           │   │
│  └──────────────────────────────────────┘   │
│                                             │
│  ┌──────────────┐  ┌───────────────────┐    │
│  │  Chroma      │  │   In-memory       │    │
│  │  RAG + Mem0  │  │  session store    │    │
│  │  (per-user)  │  │  (TTL: 30 min)    │    │
│  └──────────────┘  └───────────────────┘    │
└─────────────────────────────────────────────┘
         │                   │
         ▼                   ▼
  ┌────────────┐      ┌─────────────┐
  │   MySQL    │      │   Chroma    │
  │  (port     │      │  (port      │
  │   3307)    │      │   8001)     │
  └────────────┘      └─────────────┘
```

LLM inference is handled via any **OpenAI-compatible API** (configurable via `LLM_API_URL`; defaults to Groq). The model name is set with `MODEL_NAME`. When no API key is set the system falls back to a deterministic keyword-based heuristic so the MVP remains functional for local testing.

User accounts (email + bcrypt-hashed password) are stored in **MySQL**. Authentication uses **JWT Bearer tokens** (HS256, 7-day expiry). All chat endpoints require a valid token.

Agent memory is provided by **Mem0 OSS** (`Memory.from_config`) backed by the Docker-hosted **Chroma** server (dedicated `mem0_agent_memory` collection). Memory is keyed by the authenticated **user ID** (not the session ID), so facts extracted from previous consultations persist across all future sessions for the same user. This enables smart follow-ups, awareness of chronic conditions, and allergy safety checks. Active consultation sessions are held in an **in-memory session store** (TTL: 30 minutes); session data does not survive a server restart, but Mem0 memories are durable.

---

## Project Structure

```
MediGuideAI/
├── backend/
│   ├── agents/              # Pydantic-AI agents (triage, safety, language)
│   ├── data/                # clinical guidelines seed data (clinical_guideline.json)
│   ├── database/
│   │   ├── database.py          # SQLAlchemy engine and session factory
│   │   ├── models.py            # User ORM model
│   │   └── __init__.py          # init_db() — creates tables on startup
│   ├── routes/
│   │   ├── auth.py              # /auth/register, /auth/login, /auth/change-password
│   │   └── chat.py              # /chat (protected), /session/{id}
│   ├── schemas/             # Pydantic request/response models
│   │   └── user.py              # UserCreate, UserResponse, Token, PasswordChange
│   ├── services/
│   │   ├── agent_memory.py      # Mem0 OSS agent memory (Chroma-backed, user-scoped)
│   │   ├── session_store.py     # In-memory multi-turn session store (TTL 30 min)
│   │   ├── rag_service.py       # Chroma RAG over clinical guidelines
│   │   └── llm_client.py        # OpenAI-compatible LLM HTTP client (UTF-8 safe)
│   ├── utils/
│   │   ├── prompts.py           # Prompt builders (includes patient history injection)
│   │   └── security.py          # JWT creation/verification + bcrypt helpers
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
MEM0_LLM_MODEL=<YOUR_MODEL_NAME_HERE>

# Embedder for vectorising memories. Groq does not provide an embeddings
# endpoint, so configure a separate OpenAI-compatible provider here.
# Examples:
#   OpenAI:   https://api.openai.com/v1  +  text-embedding-3-small
#   Gemini:   https://api.gemini.com/v1  +  models/gemini-2.0-pro-embed-text-001
#   Ollama:   http://localhost:11434/v1  +  nomic-embed-text
MEM0_EMBED_API_URL=https://api.gemini.com/v1
MEM0_EMBED_API_KEY=<YOUR_API_KEY_HERE>
MEM0_EMBED_MODEL=models/gemini-2.0-pro-embed-text-001

# ── MySQL (User Accounts) ─────────────────────────────────────────────────────
# Set automatically by docker-compose. Override when using an external MySQL server.
MYSQL_HOST=mysql
MYSQL_PORT=3306
MYSQL_USER=mediguide
MYSQL_PASSWORD=password
MYSQL_DATABASE=mediguideai
MYSQL_ROOT_PASSWORD=root

# ── JWT Authentication ────────────────────────────────────────────────────────
# Secret key used to sign JWT tokens. CHANGE THIS in production.
SECRET_KEY=<YOUR_RANDOM_SECRET_HERE>

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
# Edit .env and set at minimum LLM_API_KEY and SECRET_KEY

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
| `mysql` | `3307` | MySQL 8.0 (user account storage) |

> MySQL includes a health check. The backend will wait until MySQL is fully ready before accepting requests.

---

## API Reference

### Authentication

All consultation endpoints (`/chat`, `/session/{id}`) require a **JWT Bearer token** in the `Authorization` header:

```
Authorization: Bearer <access_token>
```

Sign out is handled client-side by discarding the token. There is no server-side token revocation.

#### `POST /auth/register` — Create a new account

```json
{
  "email": "patient@example.com",
  "password": "mysecurepassword"
}
```

Returns `201 Created` with `{ "id": "...", "email": "..." }`.

#### `POST /auth/login` — Obtain a JWT token

Uses `application/x-www-form-urlencoded` (OAuth2 standard form):

```
username=patient@example.com&password=mysecurepassword
```

Returns:

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer"
}
```

#### `POST /auth/change-password` — Change password

Requires a valid Bearer token.

```json
{
  "old_password": "mysecurepassword",
  "new_password": "mynewpassword"
}
```

Returns `{ "message": "Password updated successfully" }`.

---

### Chat (protected — JWT required)

All consultation interactions go through a **session-based multi-turn API**. Each session is identified by a `session_id` UUID returned on the first request and is held in memory for 30 minutes of inactivity.

#### `POST /chat`

Unified endpoint for all interaction types, distinguished by the `type` field.

##### `type: "initial"` — Start a new consultation

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

##### `type: "answer"` — Reply to a clarifying question

```json
{
  "type": "answer",
  "session_id": "<uuid>",
  "message": "It started suddenly after climbing stairs."
}
```

##### `type: "followup"` — Ask a follow-up question after a result

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

#### `DELETE /session/{session_id}`

Explicitly end a consultation session and clear its in-memory state. Mem0 memories are **not** deleted on session teardown — they are preserved permanently for the user to benefit future consultations.

Returns `{"ok": true}`.

### `GET /`

Health check. Returns `{"ok": true, "service": "MediGuideAI"}`.

---

## Agent Pipeline

Each `POST /chat` request first verifies the JWT token, then passes through a sequential agent pipeline. Before triage begins, the system retrieves relevant memories from the user's previous consultations stored in Mem0. The triage agent may ask up to 3 clarifying questions before producing a result, maintaining full conversation history across turns within the session.

```
JWT Verification (401 if invalid)
    │
    ▼
Mem0 History Retrieval (search past consultations for this user)
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
┌──────────────────────────────────────────────────────┐
│   Triage Agent                                       │
│                                                      │
│   Receives: demographics + symptoms + RAG contexts   │
│           + conversation history                     │
│           + Patient Memory (from Mem0)               │
│                                                      │
│   Uses patient memory for:                          │
│   • Smart Follow-ups — recognises recurring or       │
│     worsening symptoms from past consultations       │
│   • Chronic Conditions — accounts for stored         │
│     conditions (e.g. asthma, diabetes) in severity  │
│   • Allergy Safety — calls out known allergies in    │
│     notes and avoids suggesting that substance       │
└────────┬─────────────────────────────────────────────┘
         │
         ▼
┌───────────────────┐
│   Safety Agent    │
│                   │
│ Audits triage for │
│ unsafe advice;    │
│ applies override  │
│ if needed.        │
└────────┬──────────┘
         │
         ▼
Language Agent translates response back to patient's language
         │
         ▼
Mem0 Write (stores this turn permanently under the user's ID)
         │
         ▼
  Final JSON response
```

All agents are built with **Pydantic-AI** and share the model configured via `MODEL_NAME`. The agents are provider-agnostic; switching models requires only an environment variable change.

---

## Known Issues

- **No token revocation**: JWT tokens are valid until expiry (7 days). There is no server-side logout or blacklist.
- **In-memory sessions**: Active consultation sessions are held in RAM. All sessions are lost on server restart; users must start a new consultation after a restart.
- **Chroma dependency at startup**: If Chroma is not reachable when the backend starts, the RAG service will fail. Restart the backend after Chroma is healthy.
- **Static guideline corpus**: The clinical guideline data (`clinical_guideline.json`) must be manually updated to reflect new clinical evidence.
- **Frontend sends plain-text passwords**: The frontend prototype does not enforce HTTPS. Deploy behind TLS in any real environment.

---

## Roadmap

- HTTPS termination in the Docker Compose stack (e.g., Caddy reverse proxy)
- Durable session store (Redis or database-backed) to survive server restarts
- Password reset via email
- Full multilingual intake form (structured fields in patient's language)
- Dynamic guideline corpus updates
- Prospective clinical validation study with community health workers
- On-device inference support for low-connectivity environments (smaller open-weight models)

---

## Disclaimer

MediGuideAI is a decision-support tool, not a substitute for professional medical advice, diagnosis, or treatment. All triage outputs should be reviewed by a qualified health worker before acting on them. The system is intentionally conservative and will always recommend clinical review when uncertain.
