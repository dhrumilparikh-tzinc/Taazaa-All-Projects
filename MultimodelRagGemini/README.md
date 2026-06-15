# Multimodal RAG — Gemini Stack (Method 2)

> **This is one half of a comparative study.** Two complete multimodal RAG pipelines were built from scratch and evaluated head-to-head using RAGAS to give a grounded production recommendation for Taazaa's internal document search problem. This repo is **Method 2 — the Gemini Stack**. Method 1 (Free Stack) is in [`MultimodelRagGroq/`](../MultimodelRagGroq/).

---

## The Problem

Sales teams at Taazaa generate thousands of unsearchable files daily — call recordings, contracts, business cards, slide decks. The goal: let anyone query all of it in natural language and get a cited answer.

**The question: which AI stack should power it?**

---

## This Approach — Gemini Stack

All file types go into the **Gemini File API** natively. Gemini handles extraction, embedding, reranking, and generation — the whole pipeline is 2 AI components.

**Cost:** ~$0.002/query  
**Components:** 2 AI (Gemini File API + Gemini 2.5 Flash)

```
┌─────────────────────────────────────────────────────────────┐
│                        UPLOAD FLOW                          │
│                                                             │
│  File Upload ──► Celery Task ──► Gemini File API            │
│                                  │                          │
│                    ┌─────────────┴──────────────┐           │
│                    │  PDF / DOCX / XLSX          │           │
│                    │  Image (Gemini Vision OCR)  │           │
│                    │  Audio (Gemini transcribe)  │           │
│                    │  Video (frames + audio)     │           │
│                    └─────────────┬──────────────┘           │
│                                  ▼                          │
│               Hierarchical Chunker (600w parent / 150w child)│
│                                  ▼                          │
│               Gemini Embedding-2 (3072-dim)                 │
│                                  ▼                          │
│                           ChromaDB                          │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                        QUERY FLOW                           │
│                                                             │
│  Question ──► Query expansion (4 rephrasings)               │
│                    ▼                                        │
│              ChromaDB search + entity boosting              │
│                    ▼                                        │
│              Gemini reranker + RRF                          │
│                    ▼                                        │
│              Confidence gate (cosine ≥ 0.35)                │
│                    ▼                                        │
│              Gemini 2.5 Flash ──► Cited answer              │
│                    ▼                                        │
│              Async RAGAS evaluation (Celery)                │
└─────────────────────────────────────────────────────────────┘
```

---

## RAGAS Results vs Free Stack

Evaluated on 12 questions. Full results in the [main README](../README.md).

| Metric | This (Gemini) | Free Stack (Groq) |
|---|---|---|
| Faithfulness | **0.931** | 0.757 |
| Context Recall | **0.931** | 0.698 |
| Exact-phrase recall | Weaker | **Better** |
| Speaker diarization | N/A | **Better** |

**Gemini won 4/5 metrics. Recommendation: use Gemini ingestion with the Free Stack's BM25 + RRF retrieval logic.**

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
│   ├── api/                  # auth, files, jobs, query, documents, agent, admin
│   ├── models/db.py          # User, Job, UsageLog, QueryHistory tables
│   ├── processors/           # PDF, DOCX, XLSX, image, audio, video
│   ├── rag/                  # Embedder, chunker, vectorstore, reranker, engine
│   ├── workers/              # Celery: process_file, compute_ragas, cleanup
│   └── evaluation/           # RAGAS metric computation
├── frontend/                 # React + TypeScript dashboard
├── alembic/                  # Database migrations
├── scripts/                  # Seed admin, RAGAS baseline, utilities
├── tests/                    # pytest suite
├── docker-compose.yml
└── Dockerfile
```

---

## Quick Start (Docker)

```bash
cp .env.example .env
# Fill in GEMINI_API_KEY and SECRET_KEY

docker compose up -d

docker compose exec api python scripts/seed_admin.py \
  --email admin@example.com --password YourPass!
```

Open `http://localhost:5173`.

---

## Manual Setup

```bash
pip install -e .
cp .env.example .env   # GEMINI_API_KEY, DATABASE_URL, REDIS_URL, SECRET_KEY

createdb geminirag
alembic upgrade head

python scripts/start_chromadb.py          # Terminal 1
uvicorn app.main:app --reload --port 8000 # Terminal 2
celery -A app.workers.celery_app worker --loglevel=info --pool=solo  # Terminal 3
cd frontend && npm install && npm run dev  # Terminal 4
```

---

## Configuration

**Required:**

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | Google AI Studio API key |
| `DATABASE_URL` | `postgresql://user:pass@host:5432/db` |
| `REDIS_URL` | `redis://localhost:6379/0` |
| `SECRET_KEY` | JWT signing secret (min 32 chars) |

**Key optional settings:**

| Variable | Default | Description |
|---|---|---|
| `GEMINI_MODEL` | `gemini-2.5-flash` | Generation model |
| `RAG_TOP_K` | `8` | Chunks retrieved per query |
| `CONFIDENCE_THRESHOLD` | `0.35` | Min cosine similarity to answer |
| `CHUNK_SIZE` | `600` | Parent chunk size (words) |

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register` | Create user |
| POST | `/auth/token` | Login → JWT |
| POST | `/v1/files/upload` | Upload file (returns `job_id`) |
| GET | `/v1/jobs/{job_id}` | Poll processing status |
| POST | `/v1/query` | Ask question → cited answer |
| GET | `/v1/query/stream` | Streaming query (SSE) |
| POST | `/v1/agent/chat` | Multi-turn chat |
| GET | `/v1/admin/ragas` | Quality metrics dashboard |
| GET | `/health` | Health check |
