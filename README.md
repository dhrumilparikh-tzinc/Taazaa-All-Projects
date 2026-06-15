# AI Engineering Internship — Dhrumil Parikh

**Taazaa.inc · May – June 2026**

Four projects built during my AI engineering internship, in the order they were built. Each one extended the mental model from the last, culminating in a head-to-head evaluation of two complete multimodal RAG architectures as the capstone project.

---

## The Story

> Sales teams at Taazaa generate thousands of unsearchable files daily — call recordings, contracts, business cards, slide decks. The goal: build a system that lets anyone query all of it in natural language and get a cited answer.

The path to that system:

```
Basic RAG          →  LLM Fine-Tuning      →  Wandr Travel Planner   →  Multimodal RAG Evaluation
(understand the       (understand how          (multi-agent            (capstone: build TWO
 retrieve-then-        models learn)            orchestration)          complete pipelines,
 generate loop)                                                         measure both, recommend one)
```

---

## Projects

### 1. Basic RAG — FAISS + Gemini
**[basic-rag-main/](basic-rag-main/) · [README](basic-rag-main/readme.md)**

Foundation project. Chunked a medical Q&A dataset (~16K docs, ~64K chunks), embedded with SentenceTransformers, indexed in FAISS, retrieved top-k chunks per query, passed context to Gemini, logged everything to PostgreSQL.

Built the mental model that every later project extended: **embed → retrieve → generate**.

| | |
|---|---|
| Dataset | MedQuAD — 16,407 medical Q&As (NIH) |
| Embeddings | `all-MiniLM-L6-v2` — local, zero API cost |
| Vector search | FAISS L2 index (61,886 chunks) |
| LLM | Google Gemini 2.5 Flash |
| API | FastAPI — `POST /ask` |

---

### 2. LLM Fine-Tuning — Mistral-7B with QLoRA
**[LLM FINE TUNING/](LLM%20FINE%20TUNING/) · [README](LLM%20FINE%20TUNING/README.md)**

Fine-tuned Mistral-7B on Dolly-15k using QLoRA — 4-bit quantization + LoRA adapters on attention layers — training only **0.36% of parameters** on a single GPU. Base model rambles and hallucinates structure; fine-tuned model follows instructions cleanly.

Key insight: you don't need to retrain the whole model to shift its behaviour.

| Metric | Base | Fine-tuned | Improvement |
|---|---|---|---|
| BLEU-2 | 0.047 | 0.176 | **+277%** |
| ROUGE-2 | 0.069 | 0.208 | **+204%** |
| ROUGE-L | 0.143 | 0.333 | **+133%** |

| | |
|---|---|
| Base model | Mistral-7B-v0.1 |
| Dataset | Dolly-15k (14,260 train / 751 test) |
| Trainable params | 13.6M / 3.7B = 0.36% |
| Training time | ~80 min on NVIDIA L40S |

---

### 3. Wandr — Multi-Agent AI Travel Planner
**[wandr_travel_planner/](wandr_travel_planner/) · [README](wandr_travel_planner/README.md)**

Built a multi-agent system on LangGraph StateGraph: 5 specialised agents (Destination, Weather, Budget, Itinerary, Packing) sharing an `AgentState` TypedDict. A deterministic Supervisor node — **pure Python, no LLM** — validates each agent's output and injects specific feedback on failure before retrying. All 3 end-to-end test runs clean.

Key architectural lesson: **deterministic code beats LLMs for control logic** — instant debugging, auditable routing, zero extra API calls.

| | |
|---|---|
| Orchestration | LangGraph StateGraph + MemorySaver |
| LLM | Groq llama-3.3-70b-versatile |
| External APIs | REST Countries, Open-Meteo, Open Exchange Rates (all free, keyless) |
| UI | Web (FastAPI + SSE), CLI, REST API |
| No database | All state in AgentState TypedDict |

---

### 4. Multimodal RAG — Free Stack vs Gemini (Capstone)
**[MultimodelRagGroq/](MultimodelRagGroq/) · [MultimodelRagGemini/](MultimodelRagGemini/)**

The main project. Sales teams at Taazaa generate thousands of unsearchable files daily. Rather than picking one AI stack and hoping, I built **both approaches completely** and ran a head-to-head RAGAS evaluation to give a grounded production recommendation.

#### Method 1 — Free Stack (`MultimodelRagGroq/`)
Groq Whisper (transcription) + SpeechBrain ECAPA (speaker diarization) + Groq llama-4-scout Vision (OCR) + fastembed BAAI/bge 384-dim + BM25 + ChromaDB hybrid search + cross-encoder reranker + Groq Llama-3.3-70b. **$0 cost, 14 components.**

#### Method 2 — Gemini Stack (`MultimodelRagGemini/`)
All file types into Gemini File API natively (PDF, audio, video, images). Gemini Embedding-2 3072-dim + query expansion (4 rephrasings) + entity boosting + Gemini 2.5 Flash for reranking and generation. **~$0.002/query, 2 AI components.**

#### RAGAS Results (12 questions)

| Metric | Free Stack (Groq) | Gemini Stack | Winner |
|---|---|---|---|
| Faithfulness | 0.757 | **0.931** | Gemini |
| Context Recall | 0.698 | **0.931** | Gemini |
| Answer Relevancy | — | — | Gemini |
| Context Precision | — | — | Gemini |
| Exact-phrase recall | **Better** | Weaker | Free Stack |
| Speaker diarization | **Better** | N/A | Free Stack |

**Gemini won 4/5 metrics. Free Stack won on exact-phrase retrieval and speaker diarization.**

#### Recommendation
> Deploy Gemini's ingestion pipeline with Method 1's BM25 + RRF + confidence gate for exact-phrase queries. Neither system alone is the right answer — the head-to-head is what revealed this.

Both systems share the same infrastructure: FastAPI, Celery + Redis, PostgreSQL, ChromaDB, React frontend, RAGAS evaluation, JWT auth, admin dashboard.

---

## What I Learned

**Benchmarking taught me that intuition about AI tools is unreliable without measurement.** I assumed the free stack would be clearly worse. It wasn't — it won on exact-phrase recall and speaker diarization. RAGAS gave a language for failure modes: low context recall means retrieval missed content; low faithfulness means the LLM fabricated. Without metrics, both just look like "wrong answers."

**Deterministic code beats LLMs for control logic.** The Wandr Supervisor is pure Python — no LLM calls, instant debugging, auditable routing. The same principle applies to the confidence gate in the RAG pipelines — a simple cosine threshold that stops the LLM being called on bad retrieval.

**Building two systems instead of one was the best decision.** The comparison revealed gaps neither system had alone. The real recommendation wasn't "pick Gemini" — it was "use Gemini's ingestion with Method 1's retrieval logic." That nuance only exists because both were built and measured.

---

## Repository Structure

```
Taazaa All Projects/
├── README.md                     ← you are here
├── docs/
│   └── Dhrumil_Parikh_Internship_OnePager.pdf
│
├── basic-rag-main/               ← Project 1: Foundation RAG
├── LLM FINE TUNING/              ← Project 2: Mistral-7B QLoRA
├── wandr_travel_planner/         ← Project 3: Multi-agent travel planner
├── MultimodelRagGroq/            ← Project 4a: Free Stack pipeline
└── MultimodelRagGemini/          ← Project 4b: Gemini Stack pipeline
```

---

## Tech Stack Summary

| Provider | Used for |
|---|---|
| **Groq** | llama-3.3-70b (answers), llama-4-scout (vision), Whisper (speech), llama-3.1-8b (summaries) |
| **Google Gemini** | File API ingestion, Embedding-2, 2.5 Flash generation, Gemini stack evaluation |
| **Mistral** | Base model for QLoRA fine-tuning |
| **LangGraph** | Multi-agent orchestration (Wandr) |
| **FastAPI + Celery** | API + async job processing (both multimodal systems) |
| **ChromaDB + FAISS** | Vector stores |
| **RAGAS** | Automated RAG quality evaluation |
| **React + Vite** | Admin dashboards (both multimodal systems) |
