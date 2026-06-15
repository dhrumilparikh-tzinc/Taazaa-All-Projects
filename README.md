# AI/ML Engineering Internship — Project Portfolio

Five production-grade AI projects built during my internship at **Taazaa Tech Pvt Ltd**. Each project builds on the previous one — starting with a foundational RAG system and culminating in a multi-agent LangGraph orchestration system.

---

## Projects at a Glance

| # | Project | What it is | Key Tech |
|---|---|---|---|
| 1 | [Medical RAG API](#1-medical-rag-api) | REST API for medical Q&A using FAISS + Gemini | FAISS · Gemini · FastAPI |
| 2 | [LLM Fine-Tuning](#2-llm-fine-tuning) | Fine-tune Mistral-7B with QLoRA on Dolly-15k | QLoRA · PEFT · TRL · Mistral-7B |
| 3 | [Multimodal RAG — Gemini](#3-multimodal-rag--gemini-edition) | Full-stack document Q&A for PDF/DOCX/XLSX/images/audio/video | Gemini · ChromaDB · Celery · React |
| 4 | [Multimodal RAG — Groq](#4-multimodal-rag--groq-edition) | Same system, provider-agnostic with hybrid search | Groq · fastembed · BM25 · RRF |
| 5 | [Wandr Travel Planner](#5-wandr-travel-planner) | Multi-agent travel planner with LangGraph | LangGraph · Groq · FastAPI · SSE |

---

## Learning Arc

These projects follow a deliberate progression from fundamentals to production architecture:

```
Project 1 — Understand RAG at its simplest
  Single document type (CSV), local embeddings, FAISS, one LLM call per query

Project 2 — Understand how LLMs actually learn
  QLoRA fine-tuning: only 0.36% of parameters need to update to shift model behavior

Project 3 — Scale RAG to the real world
  6 file types, async processing, user auth, quality metrics, React UI — all on Gemini

Project 4 — Make it production-hardened and provider-agnostic
  Hybrid search (vector + BM25 + RRF + reranker), local embeddings, Groq ↔ Gemini switching

Project 5 — Build a multi-agent system from scratch
  LangGraph orchestration, 5 specialized agents, deterministic supervisor, real-time SSE UI
```

---

## 1. Medical RAG API

> **[basic-rag-main/](basic-rag-main/)** — [README](basic-rag-main/readme.md)

A FastAPI service that answers medical questions using retrieval-augmented generation. Questions are embedded locally, matched against 61,886 chunks from the MedQuAD dataset via FAISS, and answered by Gemini.

**The core RAG loop in its purest form:** embed → retrieve → generate.

```
Question → SentenceTransformer embed → FAISS search → Gemini answer
```

| What | Detail |
|---|---|
| Dataset | MedQuAD (16,407 medical Q&As from NIH) |
| Embeddings | `all-MiniLM-L6-v2` — runs locally, zero API cost |
| Vector search | FAISS L2 index (61,886 chunks) |
| LLM | Google Gemini 2.5 Flash |
| API | `POST /ask`, `POST /ask/simple` |
| Logging | PostgreSQL (SQLAlchemy) — best-effort, non-blocking |

**Run it:**
```bash
cd basic-rag-main
pip install -r requirements.txt
cp .env.example .env   # add GEMINI_API_KEY
uvicorn api:app --port 8000
```

---

## 2. LLM Fine-Tuning

> **[LLM FINE TUNING/](LLM%20FINE%20TUNING/)** — [README](LLM%20FINE%20TUNING/README.md)

Fine-tuning **Mistral-7B-v0.1** on the Databricks Dolly-15k instruction dataset using **QLoRA** (4-bit quantization + Low-Rank Adaptation). Only 13.6M of 3.7B parameters are updated — 0.36% — yet the model improves dramatically on instruction-following tasks.

**Key insight:** you don't need to retrain the whole model to change its behavior.

| Metric | Base | Fine-tuned | Improvement |
|---|---|---|---|
| BLEU-1 | 0.177 | 0.428 | +142% |
| BLEU-2 | 0.047 | 0.176 | +277% |
| ROUGE-L | 0.143 | 0.333 | +133% |

| What | Detail |
|---|---|
| Base model | `mistralai/Mistral-7B-v0.1` |
| Dataset | Dolly-15k (14,260 train / 751 test) |
| Trainable params | 13.6M / 3.7B = **0.36%** |
| Training time | ~80 min on NVIDIA L40S |
| Framework | `peft` + `trl` (SFTTrainer) + `bitsandbytes` |

**Run it:** Open `LLM_FineTuning.ipynb` in Lightning AI Studio with an L40S or A100 GPU.

---

## 3. Multimodal RAG — Gemini Edition

> **[MultimodelRagGemini/](MultimodelRagGemini/)** — [README](MultimodelRagGemini/README.md)

A production-ready document intelligence platform powered entirely by Google Gemini. Upload any file type; ask questions; get cited answers. Includes user authentication, async job processing, a React admin dashboard, and automatic RAGAS quality evaluation.

**The jump from Project 1:** 6 file types, async Celery pipeline, PostgreSQL audit trail, JWT auth, React UI, and RAGAS metrics.

```
Upload → Celery → Processor (PDF/DOCX/XLSX/image/audio/video)
       → Hierarchical chunker (600-word parent / 150-word child)
       → Gemini embeddings (768-dim) → ChromaDB

Query → Embed → ChromaDB search → Gemini reranker → Gemini answer → RAGAS eval
```

| What | Detail |
|---|---|
| LLM | Gemini 2.5 Flash (all operations) |
| Embeddings | Gemini `text-embedding-001` (768-dim, API) |
| Vector store | ChromaDB (cosine) |
| File types | PDF, DOCX, XLSX, PNG/JPG, MP3/WAV, MP4/MOV |
| Database | PostgreSQL + Alembic migrations |
| Queue | Celery + Redis |
| Frontend | React 18 + Vite + Tailwind CSS |
| Quality | RAGAS (faithfulness, relevancy, context precision/recall) |

**Run it:**
```bash
cd MultimodelRagGemini
cp .env.example .env   # add GEMINI_API_KEY
docker compose up -d
```

---

## 4. Multimodal RAG — Groq Edition

> **[MultimodelRagGroq/](MultimodelRagGroq/)** — [README](MultimodelRagGroq/README.md)

The same multimodal document intelligence platform, rebuilt with Groq as the primary LLM and local fastembed for embeddings (zero embedding cost). Adds **hybrid search** — dense vector retrieval, BM25 sparse search, Reciprocal Rank Fusion, and cross-encoder reranking — and a provider-switching architecture.

**The advance over Project 3:** better retrieval (hybrid), cheaper embeddings (local), faster inference (Groq), and full provider-agnosticism.

```
Query
  ├── Dense: fastembed → ChromaDB (cosine)
  └── Sparse: BM25 (Redis-cached)
        ↓
   RRF merge → Cross-encoder rerank → Confidence gate → Groq answer
```

| What | Detail |
|---|---|
| LLM | Groq `llama-3.3-70b-versatile` (answers), `llama-3.1-8b-instant` (summaries) |
| LLM (vision) | Groq `llama-4-scout-17b-16e-instruct` |
| Embeddings | `BAAI/bge-small-en-v1.5` via fastembed — **local, free** |
| Sparse search | rank-bm25 (cached in Redis) |
| Reranker | `ms-marco-MiniLM-L-6-v2` cross-encoder |
| Agent | Intent-classifying Groq agent + Google ADK autonomous agent |
| Provider switch | `LLM_PROVIDER=groq` or `gemini` via `.env` |

**Run it:**
```bash
cd MultimodelRagGroq
cp .env.example .env   # add GROQ_API_KEY + DB/Redis credentials
pip install -e .
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

---

## 5. Wandr Travel Planner

> **[wandr_travel_planner/](wandr_travel_planner/)** — [README](wandr_travel_planner/README.md)

An AI travel planner that converts a natural-language trip request into a complete plan — destination overview, 7-day weather forecast, currency-converted budget, day-by-day itinerary, and packing list — in 30–90 seconds.

Built with **LangGraph**: 5 specialized agents coordinated by a deterministic supervisor that validates every output and retries on failure.

**The architecture shift from Projects 3–4:** instead of one LLM call per query, this is an orchestrated pipeline of 5 sequential agents with inter-agent state sharing and retry logic.

```
User query
  → Input guardrail → Parser
  → [Human confirms]
  → supervisor → Destination Agent (REST Countries + LLM)
  → supervisor → Weather Agent (Open-Meteo)
  → supervisor → Budget Agent (FX rates + tier-aware allocation)
  → supervisor → Itinerary Agent (day-by-day, batched)
  → supervisor → Packing Agent (weather-aware)
  → Trip plan
```

| What | Detail |
|---|---|
| Orchestration | LangGraph StateGraph + MemorySaver |
| LLM | Groq `llama-3.3-70b-versatile` |
| External data | REST Countries, Open-Meteo, Open Exchange Rates — all free + keyless |
| UI options | Web (FastAPI + Jinja2 + SSE), CLI, REST API |
| No database | All state in LangGraph AgentState + in-memory sessions |
| Supervisor | Deterministic Python — validates, routes, retries (no LLM overhead) |

**Run it:**
```bash
cd wandr_travel_planner
pip install -r requirements.txt
cp .env.example .env   # add GROQ_API_KEY
uvicorn web.server:app --port 8000
# or CLI: python app.py "5-day Tokyo trip, ¥80,000, temples and food"
```

---

## Technology Ecosystem

### LLMs & AI Providers
| Provider | Used in | Models |
|---|---|---|
| **Groq** | Projects 4, 5 | llama-3.3-70b-versatile, llama-3.1-8b-instant, llama-4-scout, Whisper |
| **Google Gemini** | Projects 1, 3, 4 | Gemini 2.5 Flash, text-embedding-001 |
| **Mistral** | Project 2 | Mistral-7B-v0.1 (fine-tuned) |
| **HuggingFace** | Projects 1, 4 | all-MiniLM-L6-v2, BAAI/bge-small-en-v1.5 |

### Core Frameworks
| Framework | Used in | Purpose |
|---|---|---|
| **FastAPI** | Projects 1, 3, 4, 5 | REST API + SSE |
| **LangGraph** | Project 5 | Multi-agent orchestration |
| **LangChain** | Project 5 | Tool abstractions |
| **PEFT + TRL** | Project 2 | QLoRA fine-tuning |
| **Celery + Redis** | Projects 3, 4 | Async job queue |
| **ChromaDB** | Projects 3, 4 | Vector store |
| **FAISS** | Project 1 | Vector index |
| **React + Vite** | Projects 3, 4 | Admin frontend |
| **RAGAS** | Projects 3, 4 | RAG quality evaluation |

### Infrastructure
| Tool | Used in | Purpose |
|---|---|---|
| **PostgreSQL + SQLModel** | Projects 3, 4 | Relational DB + ORM |
| **Alembic** | Projects 3, 4 | Database migrations |
| **Docker + docker-compose** | Projects 3, 4 | Containerized deployment |
| **structlog + OpenTelemetry** | Projects 3, 4 | Observability |

---

## Repository Structure

```
Taazaa All Projects/
├── README.md                     ← you are here
├── .gitignore                    ← covers all projects
│
├── basic-rag-main/               ← Project 1: Medical RAG API
├── LLM FINE TUNING/              ← Project 2: Mistral-7B QLoRA
├── MultimodelRagGemini/          ← Project 3: Multimodal RAG (Gemini)
├── MultimodelRagGroq/            ← Project 4: Multimodal RAG (Groq + hybrid search)
└── wandr_travel_planner/         ← Project 5: Multi-agent travel planner
```

---

## Prerequisites by Project

| Project | Required API Keys | Services |
|---|---|---|
| basic-rag-main | `GEMINI_API_KEY` | PostgreSQL |
| LLM FINE TUNING | HuggingFace token (optional) | L40S / A100 GPU |
| MultimodelRagGemini | `GEMINI_API_KEY` | PostgreSQL, Redis, ChromaDB |
| MultimodelRagGroq | `GROQ_API_KEY` | PostgreSQL, Redis, ChromaDB |
| wandr_travel_planner | `GROQ_API_KEY` | None |

Wandr is the easiest to run — one API key, no external services, no database.
