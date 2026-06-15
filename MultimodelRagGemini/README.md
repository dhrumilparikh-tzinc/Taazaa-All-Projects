# GeminiRAG — Multimodal Document Intelligence

A production-ready document Q&A platform powered entirely by **Google Gemini**. Upload any file — PDF, Word doc, spreadsheet, image, audio, or video — and ask questions about it in natural language. Answers are cited back to the exact source chunks.

This was the **first production-scale RAG project** of the internship, built to handle real-world document variety with enterprise-grade infrastructure (async job queue, user auth, RAGAS quality metrics, React dashboard).

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        UPLOAD FLOW                          │
│                                                             │
│  File Upload ──► Celery Task ──► Processor                  │
│                                  │                          │
│                    ┌─────────────┴──────────────┐           │
│                    │  PDF / DOCX / XLSX          │           │
│                    │  Image (Gemini Vision OCR)  │           │
│                    │  Audio (Gemini transcribe)  │           │
│                    │  Video (frames + audio)     │           │
│                    └─────────────┬──────────────┘           │
│                                  ▼                          │
│                     Hierarchical Chunker                    │
│                     (600-word parent / 150-word child)      │
│                                  ▼                          │
│                     Gemini Embeddings (768-dim)             │
│                                  ▼                          │
│                           ChromaDB                          │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                        QUERY FLOW                           │
│                                                             │
│  Question ──► Embed ──► ChromaDB search                     │
│                              ▼                              │
│                     Gemini reranker + RRF                   │
│                              ▼                              │
│                     Confidence gate (≥ 0.35)                │
│                              ▼                              │
│               Gemini 2.5 Flash ──► Cited answer             │
│                              ▼                              │
│                     Async RAGAS evaluation                  │
└─────────────────────────────────────────────────────────────┘
```

---

## Supported File Types

| Category | Formats | Processing |
|---|---|---|
| Documents | PDF | Gemini File API (native understanding) |
| Documents | DOCX | python-docx (paragraphs + tables) |
| Spreadsheets | XLSX, CSV | openpyxl (multi-sheet) |
| Images | PNG, JPG, JPEG, WEBP | Gemini Vision (OCR + classification) |
| Audio | MP3, WAV, M4A | Gemini audio transcription + speaker diarization |
| Video | MP4, MOV, AVI, MKV | Key-frame analysis + audio transcription |

---

## Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI + Uvicorn |
| LLM (all) | Google Gemini 2.5 Flash |
| Embeddings | Gemini `text-embedding-001` (768-dim) |
| Vector Store | ChromaDB (cosine similarity) |
| Database | PostgreSQL (SQLModel ORM, Alembic migrations) |
| Task Queue | Celery + Redis |
| Auth | JWT (python-jose + bcrypt) |
| Rate Limiting | slowapi |
| Quality Metrics | RAGAS (faithfulness, relevancy, context precision/recall) |
| Frontend | React 18 + Vite + Tailwind CSS |
| Observability | structlog + OpenTelemetry |
| Deployment | Docker + docker-compose |

---

## Project Structure

```
MultimodelRagGemini/
├── app/
│   ├── main.py               # FastAPI factory + startup hooks
│   ├── config.py             # Pydantic settings (P0 validation on startup)
│   ├── llm_provider.py       # Gemini client with rate limiting
│   ├── security.py           # JWT creation + password hashing
│   ├── api/                  # Route handlers
│   │   ├── auth.py           # Register + login
│   │   ├── files.py          # File upload (500 MB limit)
│   │   ├── jobs.py           # Job status polling
│   │   ├── query.py          # RAG query + SSE streaming
│   │   ├── documents.py      # Document listing + summaries
│   │   ├── agent.py          # Multi-turn chat agent
│   │   └── admin.py          # Usage analytics + RAGAS dashboard
│   ├── models/db.py          # User, Job, UsageLog, QueryHistory tables
│   ├── processors/           # Per-format extraction (PDF, DOCX, XLSX, image, audio, video)
│   ├── rag/                  # Embedder, chunker, vectorstore, reranker, engine
│   ├── workers/              # Celery tasks (process_file, compute_ragas, cleanup)
│   ├── evaluation/           # RAGAS metric computation
│   └── observability/        # structlog + OpenTelemetry setup
├── frontend/                 # React + TypeScript dashboard
├── alembic/                  # Database migrations
├── scripts/                  # Seed admin, run RAGAS baseline, debug utilities
├── tests/                    # pytest suite
├── docker-compose.yml        # Full local stack
└── Dockerfile
```

---

## Quick Start (Docker)

```bash
# 1. Configure
cp .env.example .env
# Edit .env — fill in GEMINI_API_KEY and SECRET_KEY

# 2. Start all services
docker compose up -d

# 3. Create admin user
docker compose exec api python scripts/seed_admin.py \
  --email admin@example.com --password YourPass!

# 4. Open the dashboard
open http://localhost:5173
```

Services:
- **API** → `http://localhost:8000`
- **Frontend** → `http://localhost:5173`
- **ChromaDB** → `http://localhost:8001`
- **PostgreSQL** → port 5432
- **Redis** → port 6379

---

## Manual Setup (without Docker)

```bash
pip install -e .
cp .env.example .env   # Fill in GEMINI_API_KEY, DATABASE_URL, REDIS_URL, SECRET_KEY

createdb geminirag
alembic upgrade head

python scripts/start_chromadb.py       # Terminal 1 — ChromaDB on port 8001
uvicorn app.main:app --reload --port 8000  # Terminal 2 — API
celery -A app.workers.celery_app worker --loglevel=info --pool=solo  # Terminal 3 — Worker
cd frontend && npm install && npm run dev  # Terminal 4 — Frontend
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register` | Create user account |
| POST | `/auth/token` | Login → JWT |
| POST | `/v1/files/upload` | Upload document (returns `job_id`) |
| GET | `/v1/jobs/{job_id}` | Poll processing status |
| POST | `/v1/query` | Ask a question → cited answer |
| GET | `/v1/query/stream` | Streaming query (SSE) |
| GET | `/v1/documents/` | List processed documents |
| GET | `/v1/documents/{job_id}/summary` | AI-generated document summary |
| POST | `/v1/agent/chat` | Multi-turn document chat |
| GET | `/v1/admin/usage` | Token + latency stats |
| GET | `/v1/admin/ragas` | Answer quality trends |
| GET | `/health` | Service health check |

---

## Configuration

**Required:**

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | Google AI Studio API key |
| `DATABASE_URL` | PostgreSQL: `postgresql://user:pass@host:5432/db` |
| `REDIS_URL` | Redis: `redis://localhost:6379/0` |
| `SECRET_KEY` | JWT signing secret (min 32 chars) |

**Optional (with defaults):**

| Variable | Default | Description |
|---|---|---|
| `GEMINI_MODEL` | `gemini-2.5-flash` | Generation model |
| `GEMINI_EMBEDDING_MODEL` | `models/gemini-embedding-001` | Embedding model |
| `RAG_TOP_K` | `8` | Chunks retrieved per query |
| `CONFIDENCE_THRESHOLD` | `0.35` | Min cosine similarity to answer |
| `CHUNK_SIZE` | `600` | Parent chunk size (words) |
| `CHILD_CHUNK_SIZE` | `150` | Child chunk size for embedding |

---

## Quality Evaluation (RAGAS)

RAGAS metrics are computed asynchronously after every query and stored in `query_history`.

```bash
# Generate baseline
python scripts/ragas_baseline.py
cp /tmp/ragas_baseline.json docs/ragas_baseline.json

# Check for regressions (last 7 days)
python scripts/ragas_regression_check.py --days 7
```

**Targets:** Faithfulness ≥ 0.80, Answer Relevancy ≥ 0.70, Context Precision ≥ 0.70

---

## Database Schema

- **users** — email, bcrypt password, role (admin/user), active flag
- **jobs** — filename, type, status (PENDING → COMPLETED/FAILED), processing step, retry count, chunk count
- **usage_logs** — endpoint, model, token counts, latency per request
- **query_history** — question, answer, citations, similarity scores, RAGAS scores
