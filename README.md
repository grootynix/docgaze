# DocGaze

Local **document RAG chat**: upload PDFs or text, ask questions, get streaming answers grounded in your files.

**Stack:** React (Vite) · FastAPI · SQLite · OpenAI (embeddings + chat) · optional Ollama fallback · [Langfuse](https://langfuse.com) observability

## Features

- Upload PDF, `.txt`, or `.md` and ingest into chunked embeddings
- Per-document chat sessions with SSE streaming
- Retrieval-augmented generation (top-k cosine similarity)
- Traces for ingest, retrieval, and chat (Langfuse SDK v3)

## Prerequisites

- Python 3.9+
- Node.js 20+
- [OpenAI API key](https://platform.openai.com/api-keys) (recommended)
- Optional: [Ollama](https://ollama.com/) when `LLM_PROVIDER=auto`

## Quick start (local)

### 1. Backend

```bash
cd backend
cp ../.env.example .env
# Edit .env: OPENAI_API_KEY, optional LANGFUSE_* for cloud tracing
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

API docs: http://127.0.0.1:8000/docs  
Health: http://127.0.0.1:8000/api/health

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 (or the port Vite prints, e.g. 5175 if 5173 is in use).

The dev server proxies `/api` to the backend on port 8000.

## Configuration

Copy `.env.example` to `backend/.env`.

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | Required for OpenAI-only mode |
| `LLM_PROVIDER` | `openai` (Docker / prod) or `auto` (OpenAI first, Ollama fallback) |
| `OPENAI_CHAT_MODEL` | Default `gpt-4o-mini` |
| `OPENAI_EMBED_MODEL` | Default `text-embedding-3-small` |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | Optional; enables traces |
| `LANGFUSE_HOST` or `LANGFUSE_BASE_URL` | e.g. `https://us.cloud.langfuse.com` or local Langfuse |
| `LOG_LEVEL` | `INFO` recommended for ingest/chat timing in logs |

**Re-upload documents** after switching embedding provider (vector dimensions differ).

### Ollama fallback (`LLM_PROVIDER=auto`)

```bash
ollama pull nomic-embed-text
ollama pull llama3.2
```

## Langfuse (observability)

With keys in `backend/.env`, the API sends traces for:

- `document-ingest` — chunking and embedding usage
- `rag-retrieval` — query and chunk scores
- `chat-turn` — RAG messages, latency, token usage

Use **Langfuse Python SDK v3+** (included in `requirements.txt`). On Langfuse Cloud, prefer v3 OTEL ingestion; legacy v2 ingestion can be delayed.

In the UI: **Tracing** → filter by name `chat-turn` or `document-ingest`.

## Docker (OpenAI + self-hosted Langfuse)

```bash
cp .env.docker.example .env.docker
# Set OPENAI_API_KEY and Langfuse init keys
docker compose --env-file .env.docker up --build
```

| URL | Service |
|-----|---------|
| http://localhost:8080 | DocGaze UI |
| http://localhost:3000 | Langfuse |
| http://localhost:8000 | API (direct) |

Sign in with `LANGFUSE_INIT_USER_EMAIL` / `LANGFUSE_INIT_USER_PASSWORD` from `.env.docker`.

For production-like deploys, generate `ENCRYPTION_KEY`: `openssl rand -hex 32`

## API overview

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Database and LLM status |
| POST | `/api/documents` | Upload document (`multipart` field `file`) |
| GET | `/api/documents` | List documents |
| DELETE | `/api/documents/{id}` | Delete document and data |
| POST | `/api/documents/{id}/sessions` | Start chat session |
| GET | `/api/sessions/{id}/messages` | Message history |
| POST | `/api/sessions/{id}/chat` | Stream chat (SSE) |

## Project layout

```
backend/app/          FastAPI routers, SQLAlchemy models, RAG services
frontend/src/         React UI
docs/ARCHITECTURE_HLD.md   High-level design
docker-compose.yml    App + Langfuse stack
```

Runtime data: `backend/data/` (SQLite + uploads; gitignored).

## Limits (MVP)

- Sequential embedding during ingest (large PDFs are slow)
- All chunk vectors loaded per query (fine for small/medium docs)
- One document per session; no auth (local single-user)

## License

MIT — use and modify freely; no warranty.
