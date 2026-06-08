# Memory Service MVP

AI agent memory and knowledge management service. Gives an AI agent the ability to **remember** things about users and the company, with a 5-step LLM distillation pipeline, permission-based retrieval, and a human-in-the-loop approval workflow for company knowledge.

## Prerequisites

- **Docker Desktop** (for PostgreSQL, Qdrant, Redis)
- **Python 3.11+**
- **Node.js 18+** (for the admin UI)
- **OpenAI API key** (uses GPT-4o-mini + text-embedding-3-small)

## Quick Start

### 1. Start infrastructure services

```bash
docker-compose up -d
```

This starts PostgreSQL 16, Qdrant (vector DB), and Redis. Wait for all containers to be healthy:

```bash
docker-compose ps
```

### 2. Set up the Python backend

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .

# Copy env file and add your OpenAI API key
cp .env.example .env
# Edit .env and set OPENAI_API_KEY=sk-your-key-here
```

### 3. Initialize the database and seed demo data

```bash
# Create all schemas and tables
python -m app.db.init_db

# Seed demo data (3 users, ~25 personal bullets, 7 company facts)
python -m app.db.seed
```

### 4. Start the backend server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. Start the admin UI

```bash
cd admin-ui
npm install
npm run dev
```

The UI will be available at **http://localhost:5173** (Vite default).

### 6. Verify everything works

Open the browser to http://localhost:5173 and navigate to the **Demo Console**. Select a user and try:

1. **Query Memory** (left panel): Type "dark mode" and click Query
2. **Conversation** (right panel): Type "I'm allergic to peanuts" and press Send, then click "End Session"
3. Watch the **Distillation Pipeline** panel show S1-S5 executing in real time

## Resetting Data

To clear all data and reseed from scratch:

```bash
source .venv/bin/activate
python reset_and_seed.py
```

## Architecture

The system implements 7 flows from 3 architecture diagrams:

| Flow | Description | Key Endpoints |
|---|---|---|
| 1 | **Retrieval** — permission-checked memory lookup | `POST /query`, `POST /chat` |
| 2 | **Conversation Persistence** — live turns in Redis, persist to PG at session end | `POST /turns`, `POST /session/{id}/end` |
| 3 | **Distillation** — 5-step LLM pipeline (S1-S5) extracts knowledge from conversations | Triggered automatically on session end |
| 4 | **Amendment Workflow** — company knowledge approval with human-in-the-loop | `POST /amendments`, `POST /amendments/{id}/approve` |
| 5 | **Event-Driven Invalidation** — structural changes flag affected memories | `POST /events/structural` |
| 6 | **Governance** — read-only reporting (user profiles, audit trail, conflicts) | `GET /governance/*` |
| 7 | **Semantic Engine KB Read** — direct KB access bypassing retrieval | `GET /semantic-engine/kb/*` |

### Distillation Pipeline (Flow 3)

When a conversation ends, a 5-step LLM pipeline extracts knowledge:

1. **S1: Signal Detection** — detect signals from user messages (7 categories)
2. **S2: Knowledge Extraction** — extract candidate knowledge items
3. **S3: Personal vs Company** — classify tier (personal auto-applies, company requires approval)
4. **S4: Conflict Judgment** — check against existing knowledge (conflict/complement/duplicate)
5. **S5: Confidence Finalization** — score 1-5 (4-5 active, 2-3 candidate, 1 dropped)

### Two Trust Tiers

- **Personal memory** (low trust cost) — auto-applied after distillation
- **Company knowledge** (high trust cost) — requires supervisor approval via Review Queue

## Demo Users

| User | Role | Can Read |
|---|---|---|
| Alice | Backend Engineer | Her own memories + company shared |
| Bob | Frontend Engineer | His own memories + company shared |
| Charlie | Engineering Manager | All collections (supervisor) |

## Admin UI Pages

- **Demo Console** — end-to-end demo: query, converse, distill
- **Review Queue** — approve/reject company knowledge candidates
- **Governance** — user profiles, provenance, audit trail

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/query` | Query memory (Flow 1) |
| POST | `/chat` | Chat with auto-retrieval |
| POST | `/turns` | Append turn to Redis |
| POST | `/session/{id}/end` | End session, trigger distillation |
| GET | `/distillation/{id}/stream` | SSE pipeline progress |
| GET | `/amendments` | List company candidates |
| POST | `/amendments` | Submit company fact |
| POST | `/amendments/{id}/approve` | Approve candidate |
| POST | `/amendments/{id}/reject` | Reject candidate |
| POST | `/events/structural` | Emit structural event |
| GET | `/governance/users/{id}/profile` | User memory profile |
| GET | `/governance/audit` | Audit trail |
| GET | `/governance/conflicts` | Flagged items |
| GET | `/semantic-engine/kb` | Direct KB read |
| GET | `/semantic-engine/kb/documents/{id}/blob` | Document blob |
| GET | `/semantic-engine/kb/vectors` | KB vectors from Qdrant |

## Tech Stack

| Concern | Choice |
|---|---|
| Backend | Python 3.12, FastAPI |
| Database | PostgreSQL 16 (6 schemas) |
| Vector DB | Qdrant |
| Session Store | Redis |
| LLM | OpenAI GPT-4o-mini |
| Embeddings | OpenAI text-embedding-3-small |
| Frontend | React + Vite + TypeScript |
| ORM | SQLAlchemy (async) |
