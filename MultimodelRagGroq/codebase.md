# GeminiRAG — Codebase Reference
**Every file, what it does, and how they connect.**

---

## Directory Tree

```
geminirag/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── deps.py
│   ├── security.py
│   ├── limiter.py
│   ├── api/
│   │   ├── auth.py
│   │   ├── files.py
│   │   ├── jobs.py
│   │   ├── documents.py
│   │   ├── query.py
│   │   ├── admin.py
│   │   └── agent.py
│   ├── models/
│   │   └── db.py
│   ├── processors/
│   │   ├── base.py
│   │   ├── pdf.py
│   │   ├── docx_proc.py
│   │   ├── xlsx_proc.py
│   │   ├── image.py
│   │   └── video.py
│   ├── rag/
│   │   ├── engine.py
│   │   ├── chunker.py
│   │   ├── embedder.py
│   │   └── vectorstore.py
│   ├── workers/
│   │   ├── celery_app.py
│   │   └── tasks.py
│   ├── agent/
│   │   ├── agent.py
│   │   └── tools.py
│   ├── evaluation/
│   │   └── ragas_eval.py
│   └── observability/
│       ├── logging.py
│       └── tracing.py
├── frontend/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── index.css
│   │   ├── vite-env.d.ts
│   │   ├── api/
│   │   │   └── client.ts
│   │   ├── context/
│   │   │   ├── AuthContext.tsx
│   │   │   └── ToastContext.tsx
│   │   ├── components/
│   │   │   ├── NavBar.tsx
│   │   │   └── PrivateRoute.tsx
│   │   ├── hooks/
│   │   │   └── useToast.ts
│   │   └── pages/
│   │       ├── LoginPage.tsx
│   │       ├── RegisterPage.tsx
│   │       ├── UploadPage.tsx
│   │       ├── QueryPage.tsx
│   │       ├── JobsPage.tsx
│   │       ├── AdminPage.tsx
│   │       └── AgentPage.tsx
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   └── index.html
├── scripts/
│   ├── seed_admin.py
│   ├── ragas_baseline.py
│   └── download_ragas_datasets.py
├── tests/
│   ├── conftest.py
│   ├── test_api.py
│   ├── test_processors.py
│   ├── test_rag.py
│   ├── test_query.py
│   └── test_agent.py
├── migrations/             ← Alembic migration versions
├── Data set/
│   └── ragas_eval/
│       ├── ms_marco_samples.json
│       └── natural_questions_samples.json
├── .env                    ← gitignored
├── .env.example
├── pyproject.toml
├── docker-compose.yml
├── docker-compose.prod.yml
├── Dockerfile
├── alembic.ini
├── README.md
├── HANDOVER.md
├── DEMO_SCRIPT.md
├── context.md              ← this project's session context
└── codebase.md             ← this file
```

---

## Backend Files (`app/`)

---

### `app/main.py` — App Factory

**What it does:** Creates the FastAPI application, wires up all middleware and routers, exposes `/health`.

**Key contents:**
- `create_app() → FastAPI` — the factory function
- CORS middleware using `settings.allowed_origins_list` (env-configurable)
- slowapi rate limiter exception handler
- HTTP request logging middleware — logs `request_id`, `user_id`, `endpoint`, `method`, `status_code`, `latency_ms` for every request
- `/health` GET — pings PostgreSQL (`SELECT 1`) and ChromaDB (`heartbeat()`); returns `{"status":"ok","database":"ok","chromadb":"ok"}` or 503 if either is down
- Registers 7 routers: `auth`, `files`, `jobs`, `documents`, `query`, `admin`, `agent`
- `app = create_app()` — singleton used by uvicorn

**Connects to:** `config.py`, `limiter.py`, `observability/logging.py`, `observability/tracing.py`, all `api/` modules, `models/db.py`, `rag/vectorstore.py`

---

### `app/config.py` — Settings

**What it does:** Loads and validates all environment variables. The app crashes on startup if P0 vars are missing or still set to placeholder values.

**Key contents:**
- `class Settings(BaseSettings)` — Pydantic settings model
- P0 fields (required, app exits if missing): `GEMINI_API_KEY`, `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`
- P1 fields (have defaults): `CHROMA_HOST/PORT/COLLECTION`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `ALGORITHM`, `UPLOAD_DIR`, `GEMINI_MODEL`, `GEMINI_EMBEDDING_MODEL`, `CHUNK_SIZE` (800), `CHUNK_OVERLAP` (100), `RAG_TOP_K` (5), `CONFIDENCE_THRESHOLD` (0.65), `CELERY_MAX_RETRIES`, `CELERY_RETRY_BACKOFF`, `OTEL_*`, `ALLOWED_ORIGINS`
- `allowed_origins_list` property — splits `ALLOWED_ORIGINS` by comma for CORS
- `model_post_init()` — validates no placeholder values remain
- `settings` singleton — imported everywhere via `from app.config import settings`

**Connects to:** imported by virtually every other module

---

### `app/deps.py` — FastAPI Dependencies

**What it does:** Provides reusable dependency-injected objects for route handlers.

**Key contents:**
- `oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")`
- `get_db()` — yields a `Session(get_engine())`, used as `Depends(get_db)` in routes
- `get_current_user(token, db)` — decodes JWT, loads `User` from DB, checks `is_active`, updates `last_active_at`, raises 401 if anything fails
- `require_admin(current_user)` — checks `current_user.role == UserRole.admin`, raises 403 if not

**Connects to:** `security.py` (decode_token), `models/db.py` (User, get_engine)

---

### `app/security.py` — Auth Utilities

**What it does:** Password hashing and JWT encoding/decoding. No FastAPI dependencies — pure utility functions.

**Key contents:**
- `hash_password(password) → str` — bcrypt hash via passlib
- `verify_password(plain, hashed) → bool` — bcrypt comparison
- `create_access_token(data, expires_minutes) → str` — JWT encode with `exp` claim, signed with `settings.SECRET_KEY`
- `decode_token(token) → dict` — JWT decode, raises HTTP 401 on JWTError or expired token

**Connects to:** `config.py` (SECRET_KEY, ALGORITHM), used by `api/auth.py` and `deps.py`

---

### `app/limiter.py` — Rate Limiter

**What it does:** Single module that instantiates the slowapi `Limiter` so it can be imported without circular dependencies.

**Key contents:**
- `limiter = Limiter(key_func=get_remote_address)`

**Connects to:** `main.py` (registers exception handler), `api/auth.py` (decorates /login)

---

## API Route Handlers (`app/api/`)

---

### `app/api/auth.py` — Authentication

**Routes:**
- `POST /auth/register` — creates User record with hashed password
- `POST /auth/login` (rate limit: 10/min) — verifies credentials, returns JWT `access_token`

**Connects to:** `security.py`, `limiter.py`, `models/db.py` (User), `deps.py` (get_db)

---

### `app/api/files.py` — File Upload

**Routes:**
- `POST /v1/files/upload` — multipart upload, validates type/size, creates Job (PENDING), saves file to disk, enqueues Celery task

**Key logic:**
- `EXTENSION_MAP` — maps file extensions to internal type strings (pdf, docx, xlsx, csv, image, video, audio)
- `MAX_FILE_SIZE_BYTES = 500 * 1024 * 1024` (500 MB)
- Saves file to `UPLOAD_DIR/{job_id}/{original_filename}`
- Creates `Job` in `PENDING` state
- Calls `process_file.delay(str(job.id))`
- Returns 202 immediately with `{job_id, filename, file_type, status: "PENDING"}`

**Connects to:** `models/db.py` (Job, JobStatus), `workers/tasks.py` (process_file), `deps.py`, `observability/logging.py`

---

### `app/api/jobs.py` — Job Management

**Routes:**
- `GET /v1/jobs/{job_id}` — fetch single job (owner or admin)
- `GET /v1/jobs` — list jobs (user sees own, admin sees all)
- `POST /v1/jobs/{job_id}/reprocess` — reset error fields, re-queue via `process_file.delay()`

**Connects to:** `models/db.py` (Job, JobStatus, UserRole), `workers/tasks.py` (process_file), `deps.py`

---

### `app/api/documents.py` — Document Retrieval

**Routes:**
- `GET /v1/documents` — list COMPLETED jobs (these are "documents")
- `GET /v1/documents/{job_id}/summary` — return `job.result` parsed as JSON

**Connects to:** `models/db.py` (Job, JobStatus, UserRole), `deps.py`

---

### `app/api/query.py` — RAG Queries

**Routes:**
- `POST /v1/query` — standard RAG query, waits for full answer
- `POST /v1/query/stream` — same RAG retrieval, but streams answer token-by-token via SSE

**Key logic:**
- `_resolve_chunks_and_context()` — shared helper: embeds question, searches ChromaDB, applies confidence gate, returns `{early_return: bool, payload: ..., chunks: [...], user_prompt: str}`
- Streaming uses `StreamingResponse(event_stream(), media_type="text/event-stream")` — yields `data: {json}\n\n` events of type `chunk` (text fragment) and `done` (final answer + citations)
- Frontend uses `fetch` + `ReadableStream` (not `EventSource`) to handle auth headers

**Connects to:** `rag/engine.py`, `rag/embedder.py`, `rag/vectorstore.py`, `models/db.py`, `deps.py`, `google-genai` SDK

---

### `app/api/admin.py` — Admin Analytics

**Routes:**
- `GET /v1/admin/usage` — token counts, latency trends, per-user breakdown
- `GET /v1/admin/ragas` — RAGAS averages + low-scoring queries
- `GET /v1/admin/users` — user list with stats; `PATCH` to toggle `is_active`
- `GET /v1/admin/logs` — paginated raw UsageLog entries

**Connects to:** `models/db.py` (UsageLog, QueryHistory, User, UserRole), `deps.py` (require_admin)

---

### `app/api/agent.py` — Agent Chat

**Routes:**
- `POST /v1/agent/chat` — sends message to ADK agent, returns `{response, tool_calls_made, session_id, prompt_tokens, completion_tokens}`

**Connects to:** `agent/agent.py` (run_agent), `deps.py`

---

## Database Models (`app/models/`)

---

### `app/models/db.py` — ORM Tables

**What it does:** Defines all four database tables using SQLModel (SQLAlchemy under the hood).

**Tables:**

| Table | Primary Fields |
|---|---|
| `users` | id (UUID), email (unique), hashed_password, role (admin/user), is_active, created_at, last_active_at |
| `jobs` | id (UUID), user_id (FK), filename, file_type, file_path, status, step, retry_count, error_type, error_message, result (JSON str), chunk_count, created_at, updated_at |
| `usage_logs` | id (UUID), user_id, job_id, endpoint, model, prompt/completion/total_tokens, latency_ms, query_text, llm_response_preview, created_at |
| `query_history` | id (UUID), user_id, question, answer, citations (JSON), job_ids_queried (JSON), chunk_count_retrieved, avg_similarity_score, confidence_gate_passed, prompt/completion_tokens, latency_ms, ragas_scores (JSON), ragas_computed_at, created_at |

**Key functions:**
- `get_engine()` — lazy singleton with `pool_size=10, max_overflow=20, pool_pre_ping=True`
- `create_db_and_tables()` — creates all tables (used in startup or tests)

**Connects to:** everything — all API handlers, tasks, and scripts import from here

---

## File Processors (`app/processors/`)

All processors follow the same pattern: extend `BaseProcessor`, implement `extract()` and `summarise()`, call via `processor.run(db)`.

---

### `app/processors/base.py` — Abstract Base

**What it does:** Defines the interface all processors must implement, and provides the Gemini API call wrappers.

**Key contents:**
- `RateLimitError`, `InvalidInputError` — custom exceptions for error classification
- `BaseProcessor(ABC)` abstract class:
  - `extract() → str` — abstract, extract raw text from file
  - `summarise(text, db) → dict` — abstract, call Gemini and return JSON summary
  - `run(db) → (str, dict)` — template method: calls extract(), summarise(), stores JSON in `job.result`, returns both
  - `_call_gemini_json(prompt, db)` — calls Gemini with `response_mime_type="application/json"`, handles 429/400/503, logs to UsageLog
  - `_call_gemini_vision_json(prompt, image_data, mime_type, db)` — multimodal Gemini call (image + text)

**Connects to:** `observability/logging.py` (log_llm_call), `config.py` (settings), `google-genai` SDK

---

### `app/processors/pdf.py` — PDF Processor

- **extract():** pdfplumber → page text + tables → `[Page N]` prefixed concatenation
- **summarise():** Gemini JSON → `{title, document_type, summary, key_points, risks, entities, tables_found}`
- **Library:** pdfplumber

---

### `app/processors/docx_proc.py` — DOCX Processor

- **extract():** python-docx → paragraphs + tables → markdown
- **summarise():** Gemini JSON → `{title, document_type, summary, key_points, risks, sections, entities}`
- **Library:** python-docx

---

### `app/processors/xlsx_proc.py` — XLSX/CSV Processor

- **extract():** openpyxl (XLSX) or csv.reader (CSV) → markdown tables, `[Sheet: name]` prefixed, capped at 500 rows
- **summarise():** Gemini JSON → `{title, summary, sheets, column_descriptions, key_insights, row_count}`
- **Libraries:** openpyxl, csv

---

### `app/processors/image.py` — Image Processor

- **extract():** returns `""` — no text extraction step
- **summarise():** reads file as bytes → `_call_gemini_vision_json()` → `{image_type, ocr_text, language, business_card: {name, title, company, email, phone, address, website}, summary}`
- **Supported MIME types:** image/png, image/jpeg, image/webp

---

### `app/processors/video.py` — Audio/Video Processor

- **extract():** uploads file to Gemini Files API, polls until ACTIVE (300s timeout), stores `uploaded_file` reference
- **summarise():** multimodal Gemini call with diarization prompt → `{duration_seconds, speaker_count, speakers, segments: [{speaker, timestamp, text}], full_transcript, summary, action_items, key_decisions, topics_discussed}`
- **Note:** Handles both audio (.mp3/.wav/.m4a) and video (.mp4/.mov). Diarization accuracy depends on audio quality.

---

## RAG Layer (`app/rag/`)

---

### `app/rag/engine.py` — RAG Orchestration

**What it does:** The core query brain. Connects all RAG components together.

**Key contents:**
- `RAG_SYSTEM_PROMPT` — instructs Gemini to only answer from context, cite sources as [1][2], and refuse out-of-scope questions
- `_resolve_chunks_and_context(question, job_ids, settings)` — shared by both `/query` and `/query/stream`: embed question → search ChromaDB → confidence gate → format user prompt. Returns `{early_return, payload}` or `{chunks, user_prompt}`
- `query(question, job_ids, user_id, db, settings)` — full pipeline: call `_resolve_chunks_and_context()`, call Gemini for answer, parse citations, log to UsageLog + QueryHistory, enqueue `compute_ragas.delay()`, return result dict

**Confidence gate:** If `avg_similarity_score < CONFIDENCE_THRESHOLD (0.65)` → returns canned "I don't have enough information" answer without calling Gemini.

**Connects to:** `rag/embedder.py` (embed_query), `rag/vectorstore.py` (search), `observability/logging.py` (log_llm_call), `models/db.py` (QueryHistory), `workers/tasks.py` (compute_ragas.delay), `google-genai` SDK

---

### `app/rag/chunker.py` — Text Chunking

**What it does:** Splits extracted text into overlapping chunks suitable for embedding.

**Key functions:**
- `chunk_text(text, job_id, filename, file_type, chunk_size=800, overlap=100)` — splits on whitespace, sliding window (800 words, 100-word overlap), extracts `[Page N]` markers, skips chunks < 50 words. Returns list of `{text, job_id, filename, file_type, chunk_index, metadata: {page_or_segment}}`
- `chunk_video_segments(segments, job_id, filename)` — converts `[{speaker, timestamp, text}]` from Gemini diarization output into chunks with speaker/timestamp metadata

**Connects to:** `workers/tasks.py` (called during CHUNKING step)

---

### `app/rag/embedder.py` — Embedding Generation

**What it does:** Converts text chunks and queries into 768-dimensional vectors using Gemini.

**Key functions:**
- `embed_chunks(chunks, user_id, job_id, settings, db)` — batches 100 chunks at a time, calls `genai.embed_content()` with `task_type="RETRIEVAL_DOCUMENT"`, retries on 429 with delays [60, 120, 240]s, logs each batch to UsageLog
- `embed_query(question, settings)` — embeds single query with `task_type="RETRIEVAL_QUERY"`, returns 768-dim vector

**Connects to:** `observability/logging.py` (log_llm_call), `config.py` (GEMINI_EMBEDDING_MODEL), `google-genai` SDK

---

### `app/rag/vectorstore.py` — ChromaDB Operations

**What it does:** All interactions with ChromaDB vector database.

**Key functions:**
- `get_chroma_client(settings)` → `chromadb.HttpClient(host, port)`
- `get_or_create_collection(client, settings)` → cosine-distance collection named `settings.CHROMA_COLLECTION`
- `add_chunks(collection, chunks, embeddings)` — upserts with 3x retry + 5s backoff. IDs: `{job_id}_{chunk_index}`. Stores text, embeddings, metadata (job_id, filename, file_type, chunk_index, page_or_segment, speaker, timestamp)
- `search(collection, query_embedding, top_k=5, job_ids=None)` → list of `{text, score, filename, page_or_segment, job_id}`, similarity = 1 - cosine_distance
- `delete_job_chunks(collection, job_id)` — removes all chunks for a job (called on reprocess)

**Connects to:** `config.py` (CHROMA_HOST/PORT/COLLECTION), ChromaDB client library

---

## Celery Workers (`app/workers/`)

---

### `app/workers/celery_app.py` — Celery Configuration

**What it does:** Creates and configures the Celery application instance.

**Key configuration:**
- broker: `settings.REDIS_URL` (Redis)
- backend: `settings.DATABASE_URL` (PostgreSQL)
- `task_serializer / result_serializer`: `"json"`
- `worker_prefetch_multiplier: 1` — process one task at a time
- beat_schedule: `cleanup_old_uploads` runs every 86400 seconds (daily)

**Connects to:** `config.py` (REDIS_URL, DATABASE_URL)

---

### `app/workers/tasks.py` — Task Definitions

**What it does:** The three Celery task functions that do the actual background work.

**Key functions:**

`process_file(self, job_id)` — max_retries=3, bound task:
1. Dispatches to correct processor by `job.file_type`
2. Calls `processor.run(db)` → `(extracted_text, summary)`
3. `chunk_text()` or `chunk_video_segments()`
4. `embed_chunks()` → vectors
5. `add_chunks()` to ChromaDB
6. Updates job to COMPLETED
7. On error: `classify_error()` → retry if retryable (max 3 times, exponential backoff), else FAILED_PERMANENT + push to Redis `geminirag:dead_letter` list

`compute_ragas(query_history_id)` — max_retries=2:
- Re-embeds question, re-searches ChromaDB
- Calls `compute_ragas_scores()`
- Saves scores to `QueryHistory.ragas_scores`

`cleanup_old_uploads()` — scheduled daily:
- Finds COMPLETED/FAILED_PERMANENT jobs older than 7 days
- Deletes upload directories from `UPLOAD_DIR`

**Helper functions:**
- `update_job_state(db, job_id, status, step, ...)` — atomic DB update with logging
- `classify_error(exc) → (error_type_str, is_retryable)` — "429"/"quota"/"rate" → RATE_LIMIT (retryable), "400"/"invalid" → INVALID_INPUT (not retryable), else UNKNOWN (retryable)

**Connects to:** all processors, all rag modules, `models/db.py`, `celery_app.py`, `observability/logging.py`, `observability/tracing.py`

---

## ADK Agent (`app/agent/`)

---

### `app/agent/agent.py` — Agent Runner

**What it does:** Creates and runs the Google ADK conversational agent.

**Key contents:**
- `AGENT_SYSTEM_PROMPT` — instructs agent on capabilities (process files, check status, query RAG, cite sources)
- `_agent = Agent(model="gemini-2.0-flash", tools=[ingest_file, get_job_status, query_rag, list_documents, summarize_document])`
- `_session_service = InMemorySessionService()` — conversation history (resets on restart)
- `_runner = Runner(app_name="geminirag", agent=_agent, session_service=_session_service)`
- `run_agent(message, user_id, session_id?) → dict` — sets user context, calls runner, collects tool_calls and final text, returns `{response, tool_calls_made, session_id, prompt_tokens, completion_tokens}`

**Connects to:** `agent/tools.py` (5 tools), `google.adk` library, `observability/logging.py`

---

### `app/agent/tools.py` — MCP Tools

**What it does:** Implements the 5 tools the agent can call.

**Context:** `_current_user_id: ContextVar[str]` — set by `run_agent()` so tools know which user is calling.

**Tools:**

| Tool | Input | What it does | Returns |
|---|---|---|---|
| `ingest_file` | file_path: str | Creates Job, copies file to upload dir, queues process_file | {job_id, status, message} |
| `get_job_status` | job_id: str | Looks up Job in DB | {job_id, status, step, chunk_count, error_message} |
| `query_rag` | question, job_ids?, use_job_context | Calls engine.query() | {answer, citations, confidence_gate_passed, scores} |
| `list_documents` | — | Returns all COMPLETED jobs | {documents: [{job_id, filename, file_type, chunk_count}]} |
| `summarize_document` | job_id: str | Returns job.result JSON | {job_id, filename, summary: {...}} |

**Connects to:** `rag/engine.py` (query_rag), `workers/tasks.py` (ingest_file queues process_file), `models/db.py` (Job, User), `observability/logging.py`

---

## Evaluation (`app/evaluation/`)

---

### `app/evaluation/ragas_eval.py` — RAGAS Metrics

**What it does:** Computes 5 RAG quality metrics using the RAGAS library.

**Key functions:**
- `get_ragas_llm(settings)` → `ChatGoogleGenerativeAI` — LangChain wrapper for Gemini
- `get_ragas_embeddings(settings)` → `GoogleGenerativeAIEmbeddings`
- `compute_ragas_scores(question, answer, contexts, ground_truth, settings) → dict` — runs RAGAS evaluation:
  - Always: Faithfulness, AnswerRelevancy, ContextPrecision
  - If ground_truth provided: ContextRecall, AnswerCorrectness
  - Returns `{faithfulness, answer_relevancy, context_precision, context_recall, answer_correctness}` or `{error: str}`

**RAGAS target scores:** Faithfulness ≥ 0.80, Context Precision ≥ 0.60

**Connects to:** `config.py` (GEMINI_MODEL, GEMINI_EMBEDDING_MODEL), ragas library, langchain-google-genai

---

## Observability (`app/observability/`)

---

### `app/observability/logging.py` — Structured Logging

**What it does:** Configures structlog and provides the `log_llm_call()` helper that writes to both structlog and the `usage_logs` database table.

**Key functions:**
- `configure_logging()` — structlog setup with JSONRenderer, TimeStamper, StackInfoRenderer
- `get_logger()` → structlog bound logger
- `log_llm_call(user_id, job_id, endpoint, model, prompt_tokens, completion_tokens, latency_ms, query_text, llm_response_preview, db)` — creates `UsageLog` record in DB + logs to structlog

**Used by:** processors (every Gemini call), embedder, rag/engine, agent/tools

---

### `app/observability/tracing.py` — OpenTelemetry

**What it does:** Configures OpenTelemetry distributed tracing.

**Usage:** `from app.observability.tracing import tracer` then `with tracer.start_as_current_span("process_file") as span: span.set_attribute("job_id", ...)`

**Exporter:** stdout (configurable via `OTEL_EXPORTER` env var)

**Connected to:** `workers/tasks.py` (`process_file` task uses spans with job_id, file_type, user_id attributes), `main.py` (configures on startup)

---

## Frontend (`frontend/src/`)

---

### `frontend/src/main.tsx` — Entry Point

Renders `<App />` into `#root` DOM element. No logic here.

---

### `frontend/src/App.tsx` — Router

**What it does:** Sets up React Router with 7 lazy-loaded pages, wrapped in providers.

**Structure:**
```tsx
<AuthProvider>
  <ToastProvider>
    <BrowserRouter>
      <Suspense fallback={<PageLoader />}>
        <Routes> … </Routes>
      </Suspense>
    </BrowserRouter>
  </ToastProvider>
</AuthProvider>
```

**Pages (all lazy-loaded):** LoginPage, RegisterPage, UploadPage, QueryPage, AgentPage, JobsPage, AdminPage  
**Guards:** `<PrivateRoute>` wraps authenticated routes; `<PrivateRoute requireAdmin>` for /admin

**Connects to:** All page components, `context/AuthContext.tsx`, `context/ToastContext.tsx`, `components/PrivateRoute.tsx`

---

### `frontend/src/api/client.ts` — HTTP Client

**What it does:** Axios instance pre-configured for the API with JWT auth injection.

**Key exports:**
- `api` — default Axios instance with `baseURL = VITE_API_URL || "http://localhost:8000"`
- Request interceptor: attaches `Authorization: Bearer <token>` from `_getToken()`
- Response interceptor: catches 401 → calls `_onUnauthorized()` (logout + redirect)
- `setTokenGetter(fn)` / `setUnauthorizedHandler(fn)` — called by AuthContext to inject token source and logout callback

**Connects to:** `context/AuthContext.tsx` (calls setters on login/logout), used by every page

---

### `frontend/src/context/AuthContext.tsx` — Auth State

**What it does:** Global JWT authentication context. Manages logged-in user state.

**Key exports:**
- `AuthProvider` — wraps app, persists token in localStorage
- `useAuth()` → `{user: AuthUser | null, login(email, password), logout}`
- `AuthUser` = `{id, email, role, token}`

**Login flow:** POST /auth/login → decode JWT payload (base64 split on ".") → extract {sub, role} → store `AuthUser` in state + localStorage

**Connects to:** `api/client.ts` (injects token getter + unauthorized handler), `components/NavBar.tsx`, `components/PrivateRoute.tsx`, all pages

---

### `frontend/src/context/ToastContext.tsx` — Toast Notifications

**What it does:** App-wide toast notification system (no external library).

**Key exports:**
- `ToastProvider` — renders toast container fixed bottom-right, manages queue
- `useToastContext()` → `{addToast(message, type: "success"|"error"|"info"|"warning")}`

**Connects to:** `hooks/useToast.ts` (uses internal hook), used by all pages for success/error feedback

---

### `frontend/src/hooks/useToast.ts` — Toast Hook

**What it does:** Manages the toast array state, auto-removes after 4000ms.

**Key exports:**
- `useToast()` → `{toasts, addToast(message, type), removeToast(id)}`
- Each toast: `{id: number, message: string, type: ToastType}`

**Connects to:** `context/ToastContext.tsx` (used internally)

---

### `frontend/src/components/NavBar.tsx` — Navigation Bar

**What it does:** Top navigation bar with links to all pages and logout button.

**Active link:** Uses `useLocation()` to highlight current page (`border-b-2 border-white`)

**Connects to:** `context/AuthContext.tsx` (logout), React Router (useLocation, Link)

---

### `frontend/src/components/PrivateRoute.tsx` — Route Guard

**What it does:** Wraps routes that require authentication (or admin role).

**Logic:** If `!user` → redirect to `/login`. If `requireAdmin && user.role !== "admin"` → redirect to `/upload`.

**Connects to:** `context/AuthContext.tsx` (useAuth)

---

### `frontend/src/pages/LoginPage.tsx`

Email + password form → `useAuth().login()` → redirect to `/upload` on success.

---

### `frontend/src/pages/RegisterPage.tsx`

Email + password form → `POST /auth/register` → redirect to `/login`.

---

### `frontend/src/pages/UploadPage.tsx` — Upload & Job Management

**What it does:** The main file upload page and job status dashboard.

**Features:**
- Drag-and-drop zone + file input button
- `EXT_TO_TYPE` map for client-side validation before upload
- Polls `GET /v1/jobs/{job_id}` every 3 seconds until COMPLETED or FAILED
- Job cards with color-coded status badges
- Expandable card shows document summary (from `GET /v1/documents/{id}/summary`)
- Retry button re-uploads file via `POST /v1/files/upload` with stored File reference
- Empty state when no jobs exist
- Toast notifications on upload success/failure

**Connects to:** `api/client.ts`, `context/ToastContext.tsx`

---

### `frontend/src/pages/QueryPage.tsx` — RAG Query Interface

**What it does:** The primary user interface for asking questions against uploaded documents.

**Features:**
- Loads document list from `GET /v1/documents` for document selector
- Multi-select documents to scope query (or query all)
- Toggle between standard and streaming mode
- Standard: `POST /v1/query` → displays full answer when ready
- Streaming: `POST /v1/query/stream` via Fetch API + ReadableStream → streams tokens as they arrive
- Citation rendering: `[1]`, `[2]` superscripts in answer text → clickable → highlights citation card
- RAGAS score badges (green ≥ 0.8, amber 0.6–0.8, red < 0.6)
- Copy-to-clipboard button on answer
- Query history sidebar

**Why Fetch not EventSource:** EventSource API doesn't support POST or custom headers. The streaming endpoint needs both (POST body + JWT Bearer token).

**Connects to:** `api/client.ts`, `context/ToastContext.tsx`

---

### `frontend/src/pages/JobsPage.tsx` — Jobs Table

**What it does:** Full table view of all jobs with detailed status and re-process capability.

**Features:**
- `GET /v1/jobs` → table with all columns (filename, type, status, step, chunks, timestamps)
- Expandable rows with error details
- Re-process button → `POST /v1/jobs/{id}/reprocess` for failed jobs
- Horizontal scroll for wide table on mobile

**Connects to:** `api/client.ts`, `context/ToastContext.tsx`

---

### `frontend/src/pages/AdminPage.tsx` — Admin Dashboard

**What it does:** Three-tab analytics dashboard for administrators only.

**Tabs:**
1. **Usage** — today's tokens, avg latency, 7-day token trend chart (Recharts LineChart), endpoint breakdown, per-user table
2. **RAGAS** — metric averages with pass/fail indicators, 7-day RAGAS trend chart, low-scoring queries table (faith < 0.8 or relevance < 0.7)
3. **Users** — all users with query/token/job counts, last_active_at, toggle is_active button (guards self-deactivation)

**Connects to:** `api/client.ts` (admin endpoints), `context/AuthContext.tsx` (useAuth for self-deactivation guard), Recharts

---

### `frontend/src/pages/AgentPage.tsx` — Agent Chat

**What it does:** Conversational UI for the ADK agent with tool call visibility.

**Features:**
- Chat messages (user on right, agent on left with avatar)
- `POST /v1/agent/chat` with `{message, session_id}` for multi-turn conversation
- Left sidebar shows tool calls made in each response (name + icon from TOOL_ICONS map)
- Shift+Enter = newline, Enter = submit
- Markdown rendering in responses (bold, inline code, citation links)
- Token count footer
- Clear conversation button (resets session_id)

**Tool icons:** ingest_file 📎, get_job_status 🔍, query_rag 💬, list_documents 📋, summarize_document 📄

**Connects to:** `api/client.ts`, `context/ToastContext.tsx`

---

## Scripts (`scripts/`)

---

### `scripts/seed_admin.py`

```bash
py scripts/seed_admin.py --email admin@test.com --password Admin1234!
```
Creates an admin user in PostgreSQL. Exits gracefully if email already exists.

**Connects to:** `app/config.py`, `app/models/db.py` (User, UserRole), `app/security.py` (hash_password)

---

### `scripts/ragas_baseline.py`

```bash
py scripts/ragas_baseline.py --test-set C:/tmp/ragas_test_set.json
```
**Input:** JSON array of `{question, ground_truth, job_id}` (default: `C:/tmp/ragas_test_set.json`)  
**Process:** Runs RAG engine for each Q&A pair → computes RAGAS scores → prints table → saves to `C:/tmp/ragas_baseline.json`  
**Output:** Table with columns: Question | Faith | AnswRel | CtxPrec | CtxRec | AnsCorr; plus averages vs targets.

**Connects to:** `app/config.py`, `app/rag/engine.py`, `app/evaluation/ragas_eval.py`, `app/models/db.py`

---

### `scripts/download_ragas_datasets.py`

```bash
py scripts/download_ragas_datasets.py
```
Downloads 50 Q&A pairs from MS MARCO v1.1 validation and Natural Questions dev via HuggingFace `datasets` (streaming mode — does not download full dataset).

**Output:**
- `Data set/ragas_eval/ms_marco_samples.json` — 50 × `{question, ground_truth}`
- `Data set/ragas_eval/natural_questions_samples.json` — 50 × `{question, ground_truth}`

**Next step after downloading:** Add `job_id` to entries matching uploaded documents, then run `ragas_baseline.py`.

---

## Tests (`tests/`)

---

### `tests/conftest.py`

**Fixtures:**
- `engine` — SQLite `test_geminirag.db`, creates all tables, drops after session
- `db` — `Session(engine)` per test
- `client` — `TestClient(app)` with dependency override to inject test DB engine, rate limiter reset

---

### `tests/test_api.py`

Tests for authentication and file upload routes. Includes:
- `test_register_and_login` — register user, login, get token
- `test_upload_unsupported_type` — upload .xyz file → 415 error
- `test_upload_file_too_large` — upload >500MB → 413 error
- `test_get_job_wrong_user_403` — user A cannot see user B's job
- `test_login_inactive_user` — deactivated user gets 401
- `test_health` — accepts 200 or 503 (depends on ChromaDB/DB availability in test env)

---

### `tests/test_processors.py`

Tests for all 5 processor classes with mocked Gemini API calls.

---

### `tests/test_rag.py`

Tests for `chunk_text()`, `embed_chunks()` (mocked), and `vectorstore` operations.

---

### `tests/test_query.py`

Tests for `/v1/query` endpoint including confidence gate behavior and citation format.

---

### `tests/test_agent.py`

Tests for ADK agent tool invocations and response format.

---

## Top-Level Config Files

| File | Purpose |
|---|---|
| `.env` | Secrets — gitignored. Contains GEMINI_API_KEY, DB/Redis/Secret credentials |
| `.env.example` | Template for .env — committed to repo |
| `pyproject.toml` | Python 3.11+ project metadata and all dependencies |
| `alembic.ini` | Alembic migration config — points to `DATABASE_URL` env var |
| `docker-compose.yml` | Dev orchestration — 5 services (api, worker, postgres, redis, chromadb) |
| `docker-compose.prod.yml` | Production variant — no --reload, resource limits, ALLOWED_ORIGINS from env |
| `Dockerfile` | python:3.11-slim, installs deps, exposes 8000 |
| `README.md` | Full project documentation — architecture, setup, API reference, observability |
| `HANDOVER.md` | Client handover doc — setup, admin seed, RAGAS baseline, limitations, key files |
| `DEMO_SCRIPT.md` | 10-min demo guide with timing, talking points, and "if something goes wrong" table |
| `codebase.md` | This file |

---

## Data Flow Summary

```
Browser (localhost:5173)
  │
  ├── POST /auth/login ──────────────────→ api/auth.py → security.py → DB (users)
  │                                        ← JWT token
  │
  ├── POST /v1/files/upload ─────────────→ api/files.py → DB (jobs) → Redis → Celery
  │   (multipart, JWT)                     ← {job_id, status: "PENDING"}
  │
  │                                        Celery worker: process_file()
  │                                          → processors/*.py → Gemini API
  │                                          → rag/chunker.py
  │                                          → rag/embedder.py → Gemini embeddings
  │                                          → rag/vectorstore.py → ChromaDB
  │                                          → DB (jobs.status = COMPLETED)
  │
  ├── GET /v1/jobs/{id} (poll) ──────────→ api/jobs.py → DB (jobs)
  │                                        ← {status, step, chunk_count}
  │
  ├── POST /v1/query ────────────────────→ api/query.py → rag/engine.py
  │   (JWT, {question, job_ids?})              → embedder.py → Gemini
  │                                            → vectorstore.py → ChromaDB
  │                                            → Gemini RAG call
  │                                            → DB (query_history)
  │                                            → Redis → Celery (compute_ragas)
  │                                        ← {answer, citations, scores}
  │
  └── POST /v1/agent/chat ─────────────→ api/agent.py → agent/agent.py (ADK)
      (JWT, {message, session_id})            → agent/tools.py (5 tools)
                                          ← {response, tool_calls_made}
```

---

## Import Graph (simplified)

```
config.py ←────────────── everything
models/db.py ←─────────── api/, workers/, scripts/, agent/tools.py
security.py ←──────────── api/auth.py, deps.py
deps.py ←──────────────── all api/ route handlers
observability/logging.py ← processors/, rag/embedder.py, rag/engine.py, agent/tools.py
rag/engine.py ←──────────  api/query.py, agent/tools.py, scripts/ragas_baseline.py
rag/vectorstore.py ←─────  rag/engine.py, workers/tasks.py
rag/embedder.py ←────────  workers/tasks.py, rag/engine.py (via compute_ragas)
processors/base.py ←─────  processors/pdf.py, docx_proc.py, xlsx_proc.py, image.py, video.py
workers/tasks.py ←───────  api/files.py (.delay()), api/jobs.py (.delay()), rag/engine.py (.delay())
evaluation/ragas_eval.py ← workers/tasks.py (compute_ragas), scripts/ragas_baseline.py
agent/tools.py ←─────────  agent/agent.py
```


