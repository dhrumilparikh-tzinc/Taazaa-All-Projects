# GeminiRAG (Groq Edition) — Provider-Agnostic Multimodal RAG

A production-ready multimodal document intelligence platform built as an evolution of the Gemini-only version. The primary LLM is **Groq** (fast inference, free tier) with **Google Gemini** available as an optional provider for streaming queries and the ADK agent. Embeddings run **locally** via `fastembed` — zero embedding API cost.

The key advancement over the Gemini version: **hybrid search** (dense vector + BM25 sparse + RRF fusion + cross-encoder reranking), a **provider-switching architecture**, and a **Google ADK autonomous agent**.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        UPLOAD FLOW                          │
│                                                             │
│  File Upload ──► Celery Task ──► Processor                  │
│                                  │                          │
│                    ┌─────────────┴──────────────┐           │
│                    │  PDF (pdfplumber)            │           │
│                    │  DOCX (python-docx)          │           │
│                    │  XLSX (openpyxl)             │           │
│                    │  Image (Groq Vision OCR)     │           │
│                    │  Audio (Whisper + diarize)   │           │
│                    │  Video (frames + audio)      │           │
│                    └─────────────┬──────────────┘           │
│                                  ▼                          │
│                     Hierarchical Chunker                    │
│                     (600-word parent / 150-word child)      │
│                                  ▼                          │
│               fastembed (BAAI/bge-small-en-v1.5, 384-dim)  │
│                       — local, zero API cost —              │
│                                  ▼                          │
│                           ChromaDB                          │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                     HYBRID QUERY FLOW                       │
│                                                             │
│  Question                                                   │
│      ├──► Dense vector search (ChromaDB cosine)             │
│      └──► BM25 sparse search (Redis-cached index)           │
│                         ▼                                   │
│              Reciprocal Rank Fusion (RRF, k=60)             │
│                         ▼                                   │
│         Cross-encoder reranker (ms-marco-MiniLM-L-6-v2)    │
│                         ▼                                   │
│            Confidence gate (cosine ≥ 0.4)                  │
│                         ▼                                   │
│       Groq llama-3.3-70b-versatile ──► Cited answer        │
│                         ▼                                   │
│                Async RAGAS evaluation                       │
└─────────────────────────────────────────────────────────────┘
```

---

## Supported File Types

| Category | Formats | Processing |
|---|---|---|
| Documents | PDF | pdfplumber (text + tables + page numbers) |
| Documents | DOCX | python-docx (paragraphs + tables) |
| Spreadsheets | XLSX, CSV | openpyxl (multi-sheet) |
| Images | PNG, JPG, JPEG, WEBP | Groq llama-4-scout Vision (OCR + classification) |
| Audio | MP3, WAV, M4A, AAC, FLAC | Whisper large-v3 + SpeechBrain diarization |
| Video | MP4, MOV, AVI, MKV, WebM | Key-frame extraction + audio pipeline |

---

## Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI + Uvicorn |
| LLM (answers) | Groq `llama-3.3-70b-versatile` |
| LLM (summaries/RAGAS) | Groq `llama-3.1-8b-instant` |
| LLM (vision) | Groq `llama-4-scout-17b-16e-instruct` |
| LLM (streaming/ADK) | Google Gemini 2.0 Flash (optional) |
| Speech-to-text | Whisper large-v3 (via Groq API) |
| Embeddings | fastembed `BAAI/bge-small-en-v1.5` (384-dim, local) |
| Sparse search | rank-bm25 (Redis-cached, TTL 24h) |
| Reranker | sentence-transformers `ms-marco-MiniLM-L-6-v2` |
| Vector Store | ChromaDB (cosine similarity) |
| Database | PostgreSQL (SQLModel ORM, Alembic migrations) |
| Task Queue | Celery + Redis |
| Auth | JWT (python-jose + bcrypt) |
| Agent Framework | Google ADK (autonomous tool chaining) |
| Quality Metrics | RAGAS (faithfulness, relevancy, context precision/recall) |
| Frontend | React 18 + Vite + Tailwind CSS |
| Observability | structlog + OpenTelemetry |
| Deployment | Docker + docker-compose |

---

## Project Structure

```
MultimodelRagGroq/
├── app/
│   ├── main.py               # FastAPI factory + fastembed warmup
│   ├── config.py             # Pydantic settings — P0 required, P1 optional
│   ├── llm_provider.py       # Provider factory: Groq or Gemini, unified interface
│   ├── api/                  # Route handlers (auth, files, jobs, query, documents, admin, agent)
│   ├── models/db.py          # User, Job, UsageLog, QueryHistory ORM tables
│   ├── processors/           # PDF, DOCX, XLSX, image, audio, audio_utils, video
│   ├── rag/
│   │   ├── engine.py         # Hybrid search pipeline + confidence gate
│   │   ├── chunker.py        # Parent/child hierarchical chunking
│   │   ├── embedder.py       # fastembed wrapper
│   │   ├── bm25_index.py     # BM25 sparse search with Redis cache
│   │   ├── reranker.py       # Cross-encoder reranking
│   │   └── vectorstore.py    # ChromaDB + RRF merge
│   ├── agent/
│   │   ├── agent.py          # Intent classifier + Groq synthesis
│   │   ├── adk_agent.py      # Google ADK autonomous agent
│   │   └── tools.py          # Agent tools: ingest, status, query, list, summarize
│   ├── workers/              # Celery tasks (process_file, compute_ragas, cleanup)
│   └── evaluation/           # RAGAS async evaluation
├── frontend/                 # React + TypeScript dashboard
├── alembic/                  # Database migrations
├── scripts/                  # Admin seeding, RAGAS baseline, debug utilities
├── tests/                    # pytest suite
├── docker-compose.yml
└── Dockerfile
```

---

## Quick Start

### Prerequisites
- Python 3.11 or 3.12 (3.13+ disables the cross-encoder reranker due to a tokenizer limitation)
- PostgreSQL and Redis (or use Docker)
- Groq API key ([free at console.groq.com](https://console.groq.com))

### 1 — Configure

```bash
cp .env.example .env
```

Required values:
```env
GROQ_API_KEY=gsk_your_key_here
SECRET_KEY=change_me_to_a_long_random_string_min_32_chars
DATABASE_URL=postgresql://geminirag:geminirag@localhost:5432/geminirag
REDIS_URL=redis://localhost:6379/0
```

### 2 — Database & admin

```bash
pip install -e .
createdb geminirag
alembic upgrade head
python scripts/seed_admin.py --email admin@example.com --password YourPass!
```

### 3 — Start services

```bash
# Terminal 1 — ChromaDB
python scripts/start_chromadb.py

# Terminal 2 — API
uvicorn app.main:app --reload --port 8000

# Terminal 3 — Celery worker
celery -A app.workers.celery_app worker --loglevel=info --pool=solo

# Terminal 4 — Frontend (optional)
cd frontend && npm install && npm run dev
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register` | Register new user |
| POST | `/auth/token` | Login → JWT |
| POST | `/v1/files/upload` | Upload any file (async, returns `job_id`) |
| GET | `/v1/jobs/{job_id}` | Poll processing status + step |
| POST | `/v1/query` | Ask question → cited answer + RAGAS |
| GET | `/v1/query/stream` | Streaming query SSE (requires Gemini key) |
| GET | `/v1/documents/` | List processed documents |
| GET | `/v1/documents/{job_id}/summary` | AI-generated summary |
| POST | `/v1/agent/chat` | Multi-turn Groq agent (session-aware) |
| POST | `/v1/agent/adk` | Google ADK autonomous agent |
| DELETE | `/v1/agent/session/{id}` | Clear chat session |
| GET | `/v1/admin/usage` | Token + latency stats |
| GET | `/v1/admin/ragas` | Quality metrics + baseline comparison |
| GET | `/v1/admin/users` | User management |
| GET | `/health` | DB + ChromaDB connectivity check |

---

## Configuration

**Required:**

| Variable | Description |
|---|---|
| `GROQ_API_KEY` | Groq API key |
| `SECRET_KEY` | JWT secret (min 32 chars) |
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |

**Key optional settings:**

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `groq` | Switch to `gemini` to use Gemini for all LLM calls |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Answer generation model |
| `GROQ_VISION_MODEL` | `meta-llama/llama-4-scout-17b-16e-instruct` | Image/video analysis |
| `GEMINI_API_KEY` | — | Required for streaming query + ADK agent |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Local embedding model |
| `RAG_TOP_K` | `8` | Base retrieval count (doubled for broad queries) |
| `CONFIDENCE_THRESHOLD` | `0.4` | Min cosine similarity gate |

> **Provider switch note:** Switching `LLM_PROVIDER` from `groq` to `gemini` changes embedding dimensions (384 → 768) and requires re-ingesting all documents:
> ```bash
> python reset_and_reprocess.py
> ```

---

## Comparison: Groq vs Gemini Edition

| Feature | Gemini Version | Groq Version (this) |
|---|---|---|
| Primary LLM | Gemini 2.5 Flash | Groq llama-3.3-70b |
| Embeddings | Gemini API (768-dim) | Local fastembed (384-dim, free) |
| Search | Vector + Gemini reranker | Vector + BM25 + RRF + cross-encoder |
| Agent | Google ADK only | Groq intent agent + Google ADK |
| Provider switching | Gemini-only | Groq ↔ Gemini (env var) |
| Streaming | Gemini SSE | Gemini SSE (Groq queued) |

---

## Quality Evaluation (RAGAS)

```bash
python scripts/ragas_baseline.py
cp /tmp/ragas_baseline.json docs/ragas_baseline.json
python scripts/ragas_regression_check.py --days 7
```

**Targets:** Faithfulness ≥ 0.80, all others ≥ 0.70

---

## Known Limitations

- Cross-encoder reranker is disabled on Python 3.13+ (tokenizer crash); set `GEMINIRAG_RERANKER=1` to override
- Video files > 500 MB are rejected at upload
- Streaming query requires a Gemini API key
- Switching embedding providers requires full re-ingestion (`python reset_and_reprocess.py`)
- Speaker diarization works best with mono audio and clearly distinct voices
