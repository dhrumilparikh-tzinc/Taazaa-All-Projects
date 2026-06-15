# Wandr — AI Travel Planner

An AI-powered travel planner that converts a natural-language request into a complete, personalized trip plan in 30–90 seconds. Type something like *"5-day Tokyo trip, ¥80,000, temples and food"* and receive a full destination overview, 7-day weather forecast, currency-converted budget breakdown, day-by-day itinerary, and a weather-aware packing list.

Built with **LangGraph** multi-agent orchestration — the most architecturally complex project of the internship.

---

## How It Works

Five specialized agents run in sequence, each validated before the next begins. A **deterministic supervisor** (pure Python, no LLM) routes between agents and retries on failed validation.

```
User query
    │
    ▼
Input guardrail (is this a travel request?)
    │
    ▼
Parser (free text → structured fields via Groq)
    │
    ▼
[Human confirms parsed fields]
    │
    ▼
START ──► supervisor ──► destination ──► supervisor ──► weather
                  └──► supervisor ──► budget ──► supervisor ──► itinerary
                              └──► supervisor ──► packing ──► END
```

### The Five Agents

| Agent | What it does |
|---|---|
| **Destination** | REST Countries API metadata + Groq-written 2-paragraph travel overview |
| **Weather** | Open-Meteo geocoding + 7-day forecast (temperature, precipitation, wind) |
| **Budget** | FX conversion via Open Exchange Rates + tier-aware category allocation |
| **Itinerary** | Day-by-day plan with exact venues, time blocks, tips, cost notes — batched for trips > 4 days |
| **Packing** | Weather-aware packing list by category, cross-referenced against forecast |

### Supervisor Pattern
The supervisor is **deterministic code** — not an LLM. After each agent it:
1. Runs validation checks (field presence, value ranges, logical consistency)
2. If valid → dispatches the next pending agent
3. If invalid → injects feedback into state, retries same agent (up to `MAX_AGENT_RETRIES`)
4. If retries exhausted → accepts result, continues to next agent
5. When all agents done → returns END

---

## Modes

### Web UI
4-screen flow: query input → confirm parsed fields → live agent progress (SSE) → final trip brief.

```bash
uvicorn web.server:app --port 8000
```
Open `http://localhost:8000`

### CLI
```bash
python app.py "5-day trip to Tokyo, ¥80,000, temples and food"
```

### REST API (single synchronous call)
```bash
curl -X POST http://localhost:8000/api/trip \
  -H "Content-Type: application/json" \
  -d '{"query": "7-day Paris trip, €2000, art and food"}'
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Agent orchestration | LangGraph (StateGraph + MemorySaver checkpointing) |
| LLM | Groq `llama-3.3-70b-versatile` |
| Web API | FastAPI + Uvicorn |
| Templating | Jinja2 |
| Real-time streaming | SSE (sse-starlette) |
| Data validation | Pydantic v2 |
| HTTP client | httpx |
| Country data | REST Countries v3.1 (free, keyless) |
| Weather data | Open-Meteo (free, keyless) |
| Currency data | Open Exchange Rates (free, keyless) |

Only **Groq** requires an API key.

---

## Project Structure

```
wandr_travel_planner/
├── app.py                    # CLI entry point + rich terminal output
├── requirements.txt
├── .env.example
├── Dockerfile
│
├── src/
│   ├── state.py              # AgentState TypedDict — single shared graph state
│   ├── schemas.py            # Pydantic models for all agent outputs
│   ├── parser.py             # Free text → ParsedQuery (Groq structured output)
│   ├── guardrails.py         # Input guardrail + per-agent output validators
│   ├── supervisor.py         # Deterministic routing — validates, routes, retries
│   ├── graph.py              # LangGraph StateGraph assembly (92 lines)
│   ├── runner.py             # Graph executor + SSE event emitter
│   ├── logger.py             # Per-agent rotating file loggers
│   │
│   ├── agents/
│   │   ├── destination.py    # REST Countries + LLM overview
│   │   ├── weather.py        # Open-Meteo geocoding + forecast
│   │   ├── budget.py         # FX conversion + tier-aware allocation + force scaling
│   │   ├── itinerary.py      # Day-by-day plan (batched for long trips)
│   │   └── packing.py        # Weather-aware packing list
│   │
│   └── tools/
│       ├── rest_countries.py # @tool — country metadata
│       ├── open_meteo.py     # @tool — geocoding + 7-day forecast
│       └── exchange_rates.py # @tool — live FX rates
│
├── web/
│   ├── server.py             # FastAPI routes + SSE + background thread runner
│   ├── sessions.py           # Thread-safe in-memory session store
│   ├── templates/            # Jinja2: landing, confirm, planning, brief
│   └── static/js/            # Vanilla JS: landing, confirm, planning, brief
│
└── tests/
    ├── test_graph.py         # End-to-end integration (Tokyo, Paris, Reykjavik)
    └── test_tools.py         # External API smoke tests
```

---

## Setup

### Prerequisites
- Python 3.10+
- Groq API key ([free at console.groq.com](https://console.groq.com))

### Install

```bash
cd wandr_travel_planner
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
```

Edit `.env`:
```env
GROQ_API_KEY=gsk_your_key_here
GROQ_MODEL=llama-3.3-70b-versatile   # optional
MAX_AGENT_RETRIES=2                   # optional, default 2
LOG_TO_CONSOLE=1                      # optional, set to 0 to silence
```

### Run (Web UI)

```bash
uvicorn web.server:app --port 8000
```

### Run (CLI)

```bash
python app.py "5-day trip to Bali, $1500, surfing and temples"
```

---

## Web API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Landing page |
| GET | `/confirm` | Confirm extracted trip fields |
| GET | `/planning?id=<trip_id>` | Real-time agent progress dashboard |
| GET | `/brief/<trip_id>` | Final rendered trip brief |
| POST | `/api/parse` | Guardrail + parser only (returns extracted fields) |
| POST | `/api/plan` | Start background planning → returns `trip_id` |
| GET | `/api/plan/<trip_id>/stream` | SSE event stream (agent progress) |
| GET | `/api/plan/<trip_id>/result` | Final `TripPlan` once complete |
| POST | `/api/trip` | Single-call synchronous REST API |
| GET | `/health` | Health check |

---

## Real-Time SSE Events

The planning page subscribes to `/api/plan/<trip_id>/stream` and receives:

| Event | When |
|---|---|
| `agent_started` | Agent dispatched |
| `agent_retried` | Validation failed — retry #N with feedback |
| `agent_completed` | Agent done (valid / invalid_accepted) |
| `plan_complete` | All 5 agents done — includes duration_ms |
| `plan_error` | Unrecoverable error |

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `GROQ_API_KEY` | **Required** | Groq API key |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | LLM model |
| `MAX_AGENT_RETRIES` | `2` | Max retries per agent on validation failure |
| `LOG_TO_CONSOLE` | `1` | Print logs to stdout |

---

## Key Design Decisions

**Supervisor is code, not LLM** — deterministic routing means predictable behaviour, zero extra LLM calls, and easy debugging via log files.

**Force-scaled budget** — the LLM provides proportional category allocations; the budget agent then rescales all values so they sum exactly to the daily budget, eliminating LLM arithmetic errors.

**Batched itinerary generation** — trips longer than 4 days split into batches of 4 to stay within Groq context limits; each batch is aware of prior batches.

**Tier-aware prompts** — daily USD spend maps to a budget tier (budget / mid-range / comfortable / upscale / luxury) which adjusts prompts for both budget allocation and itinerary recommendations (street food vs. Michelin; hostel vs. 5-star).

**No database** — all state lives in the LangGraph `AgentState` TypedDict and in-memory web sessions. Trips are stateless and ephemeral.

**All free external APIs** — REST Countries, Open-Meteo, and Open Exchange Rates require no API key, so only one credential is needed to run the entire system.

---

## Running Tests

```bash
pytest tests/ -v
```

The integration test fires 3 full queries (Tokyo, Paris, Reykjavik) and asserts all 5 agent output sections are populated correctly.
