# Multimodal RAG — Free Stack (Method 1)

> **This is one half of a comparative study.** Two complete multimodal RAG pipelines were built from scratch and evaluated head-to-head using RAGAS to give a grounded production recommendation for Taazaa's internal document search problem. This repo is **Method 1 — the Free Stack**. Method 2 (Gemini Stack) is in [`MultimodelRagGemini/`](../MultimodelRagGemini/).

---

## The Problem

Sales teams at Taazaa generate thousands of unsearchable files daily — call recordings, contracts, business cards, slide decks. The goal: let anyone query all of it in natural language and get a cited answer.

**The question: which AI stack should power it?**

---

## This Approach — Free Stack

Open-source and free-tier components stitched together: Groq for inference, local fastembed for embeddings, BM25 for sparse search, SpeechBrain for speaker diarization. 14 components, $0 cost.

**Cost:** $0  
**Components:** 14

```
┌─────────────────────────────────────────────────────────────┐
│                        UPLOAD FLOW                          │
│                                                             │
│  File Upload ──► Celery Task ──► Processor                  │
│                    ┌────────────────────────────┐           │
│                    │  PDF (pdfplumber)            │           │
│                    │  DOCX (python-docx)          │           │
│                    │  XLSX (openpyxl)             │           │
│                    │  Image (Groq llama-4-scout)  │           │
│                    │  Audio (Whisper + SpeechBrain)│           │
│                    │  Video (frames + audio)      │           │
│                    └─────────────┬──────────────┘           │
│                                  ▼                          │
│               Hierarchical Chunker (600w parent / 150w child)│
│                                  ▼                          │
│               fastembed BAAI/bge-small-en-v1.5 (384-dim)    │
│                       — local, $0 cost —                    │
│                                  ▼                          │
│                           ChromaDB                          │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                     HYBRID QUERY FLOW                       │
│                                                             │
│  Question                                                   │
│      ├──► Dense vector search (ChromaDB cosine)             │
│      └──► BM25 sparse search (Redis-cached)                 │
│                    ▼                                        │
│           Reciprocal Rank Fusion (RRF, k=60)                │
│                    ▼                                        │
│           Cross-encoder reranker (ms-marco-MiniLM)          │
│                    ▼                                        │
│           Confidence gate (cosine ≥ 0.4)                   │
│                    ▼                                        │
│           Groq llama-3.3-70b ──► Cited answer               │
│                    ▼                                        │
│           Async RAGAS evaluation (Celery)                   │
└─────────────────────────────────────────────────────────────┘
```

---

## RAGAS Results vs Gemini Stack

Evaluated on 12 questions. Full results in the [main README](../README.md).

| Metric | This (Free Stack) | Gemini Stack |
|---|---|---|
| Faithfulness | 0.757 | **0.931** |
| Context Recall | 0.698 | **0.931** |
| Exact-phrase recall | **Better** | Weaker |
| Speaker diarization | **Better** | N/A |

**Free Stack won on exact-phrase recall and speaker diarization. Lost 4/5 RAGAS metrics overall.**  
**Recommendation: use Gemini ingestion with this stack's BM25 + RRF + confidence gate retrieval logic.**

---

## Supported File Types

| Category | Formats | Processing |
|---|---|---|
| Documents | PDF | pdfplumber (text + tables + page numbers) |
| Documents | DOCX | python-docx |
| Spreadsheets | XLSX, CSV | openpyxl (multi-sheet) |
| Images | PNG, JPG, JPEG, WEBP | Groq llama-4-scout Vision (OCR) |
| Audio | MP3, WAV, M4A, AAC, FLAC | Whisper large-v3 + SpeechBrain ECAPA diarization |
| Video | MP4, MOV, AVI, MKV, WebM | Key-frame extraction + audio pipeline |

---

## Tech Stack

| Layer | Technology |
|---|---|
| LLM (answers) | Groq `llama-3.3-70b-versatile` |
| LLM (summaries) | Groq `llama-3.1-8b-instant` |
| LLM (vision/OCR) | Groq `llama-4-scout-17b-16e-instruct` |
| Speech-to-text | Whisper large-v3 (Groq API) |
| Speaker diarization | SpeechBrain ECAPA |
| Embeddings | fastembed `BAAI/bge-small-en-v1.5` (384-dim, local) |
| Sparse search | rank-bm25 (Redis-cached, TTL 24h) |
| Reranker | `ms-marco-MiniLM-L-6-v2` cross-encoder |
| Vector Store | ChromaDB (cosine) |
| Database | PostgreSQL (SQLModel ORM, Alembic) |
| Task Queue | Celery + Redis |
| Auth | JWT (python-jose + bcrypt) |
| Agent | Intent-classifying Groq agent + Google ADK |
| Quality Metrics | RAGAS |
| Frontend | React 18 + Vite + Tailwind CSS |
| Deployment | Docker + docker-compose |

---

## Project Structure

```
MultimodelRagGroq/
├── app/
│   ├── main.py               # FastAPI factory + fastembed warmup
│   ├── config.py             # Pydantic settings
│   ├── llm_provider.py       # Provider factory: Groq or Gemini (switchable)
│   ├── api/                  # auth, files, jobs, query, documents, admin, agent
│   ├── models/db.py          # User, Job, UsageLog, QueryHistory
│   ├── processors/           # PDF, DOCX, XLSX, image, audio, audio_utils, video
│   ├── rag/
│   │   ├── engine.py         # Hybrid search + confidence gate
│   │   ├── bm25_index.py     # BM25 sparse search (Redis cache)
│   │   ├── reranker.py       # Cross-encoder reranking
│   │   └── vectorstore.py    # ChromaDB + RRF merge
│   ├── agent/                # Intent classifier + Groq agent + Google ADK agent
│   └── workers/              # Celery: process_file, compute_ragas, cleanup
├── frontend/                 # React + TypeScript dashboard
├── alembic/                  # Database migrations
├── scripts/                  # Seed admin, RAGAS baseline, utilities
├── tests/                    # pytest suite
└── docker-compose.yml
```

---

## Quick Start

```bash
cp .env.example .env
# Required: GROQ_API_KEY, SECRET_KEY, DATABASE_URL, REDIS_URL

pip install -e .
createdb geminirag
alembic upgrade head
python scripts/seed_admin.py --email admin@example.com --password YourPass!

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
| `GROQ_API_KEY` | Groq API key (free at console.groq.com) |
| `SECRET_KEY` | JWT secret (min 32 chars) |
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |

**Key optional settings:**

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `groq` | Switch to `gemini` to use Gemini for all calls |
| `GEMINI_API_KEY` | — | Required only for streaming + ADK agent |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Local embedding model |
| `RAG_TOP_K` | `8` | Base retrieval count |
| `CONFIDENCE_THRESHOLD` | `0.4` | Min cosine similarity gate |

> **Provider switch note:** Changing `LLM_PROVIDER` from `groq` to `gemini` changes embedding dimensions (384 → 768) and requires re-ingesting all documents via `python reset_and_reprocess.py`.

---

## Known Limitations

- Cross-encoder reranker disabled on Python 3.13+ (tokenizer crash); set `GEMINIRAG_RERANKER=1` to override
- Video files > 500 MB rejected at upload
- Streaming query requires a Gemini API key
- Speaker diarization works best with mono audio and clearly distinct voices
