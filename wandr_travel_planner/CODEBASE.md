# Wandr — Complete Codebase Reference

This document explains every file in the project, how the multi-agent system works, how LangGraph and the supervisor orchestrate the agents, and how to read the logs when things break.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Directory Structure](#2-directory-structure)
3. [End-to-End Request Flow](#3-end-to-end-request-flow)
4. [Core Source Files (`src/`)](#4-core-source-files-src)
5. [The Five Agents](#5-the-five-agents)
6. [LangGraph & Supervisor Architecture](#6-langgraph--supervisor-architecture)
7. [Tools (External APIs)](#7-tools-external-apis)
8. [Web Layer (`web/`)](#8-web-layer-web)
9. [Frontend JavaScript](#9-frontend-javascript)
10. [Logging System — How to Debug](#10-logging-system--how-to-debug)
11. [Configuration & Environment](#11-configuration--environment)
12. [Tests & Scripts](#12-tests--scripts)
13. [Key Design Decisions](#13-key-design-decisions)

---

## 1. Project Overview

Wandr is a **multi-agent AI travel planner**. The user types a natural-language request like *"5 days in Tokyo, ¥80,000, temples and food"* and gets back a complete trip brief: destination overview, 7-day weather forecast, currency-converted budget breakdown, detailed day-by-day itinerary, and a packing list.

**Stack:**
- **LangGraph** — Orchestrates the 5 worker agents via a supervisor graph
- **Groq (llama-3.3-70b-versatile)** — LLM for parsing, classification, and all agent generation
- **FastAPI + SSE** — Web server with real-time streaming progress
- **Free public APIs** — REST Countries, Open-Meteo, Open Exchange Rates (no API keys needed)

---

## 2. Directory Structure

```
wandr_travel_planner/
│
├── app.py                    # CLI entry point
├── requirements.txt          # Python dependencies
├── .env                      # Secrets (GROQ_API_KEY etc.) — not committed
├── .env.example              # Template showing what vars are needed
├── Dockerfile                # Docker build for HuggingFace Spaces
├── README.md                 # Project README
│
├── src/                      # All Python backend logic
│   ├── state.py              # LangGraph shared state (TypedDict)
│   ├── schemas.py            # Pydantic models for LLM I/O
│   ├── logger.py             # Centralized logging infrastructure
│   ├── parser.py             # Natural language → structured ParsedQuery
│   ├── guardrails.py         # Input filter + per-agent output validators
│   ├── supervisor.py         # Deterministic routing between agents
│   ├── graph.py              # LangGraph StateGraph assembly
│   ├── runner.py             # Graph executor + SSE event emitter
│   │
│   ├── agents/
│   │   ├── destination.py    # Country info + LLM travel overview
│   │   ├── weather.py        # Geocoding + 7-day forecast
│   │   ├── budget.py         # FX conversion + budget allocation
│   │   ├── itinerary.py      # Day-by-day itinerary (batched)
│   │   └── packing.py        # Context-aware packing list
│   │
│   └── tools/
│       ├── rest_countries.py # @tool — REST Countries API
│       ├── open_meteo.py     # @tool — Geocoding + weather
│       └── exchange_rates.py # @tool — Live FX rates + conversion
│
├── web/                      # FastAPI web application
│   ├── server.py             # Routes, SSE endpoint, background tasks
│   ├── sessions.py           # In-memory session store (threading.Queue)
│   ├── templates/            # Jinja2 HTML templates (4 screens)
│   └── static/js/            # Vanilla JS (4 modules, one per screen)
│
├── logs/                     # Auto-created at runtime
│   ├── master.log            # Full trace of every run
│   ├── supervisor.log        # Routing decisions only
│   ├── destination.log       # Destination agent only
│   ├── weather.log           # Weather agent only
│   ├── budget.log            # Budget agent only
│   ├── itinerary.log         # Itinerary agent only
│   ├── packing.log           # Packing agent only
│   ├── guardrails.log        # Guardrail input/output
│   ├── parser.log            # Query parsing
│   └── web.log               # HTTP request/response layer
│
├── tests/
│   ├── test_graph.py         # End-to-end integration tests
│   └── test_tools.py         # Tool smoke tests (live APIs)
│
└── scripts/                  # One-off sanity-check scripts
    ├── test_gemini.py         # Verify Groq API key works
    ├── test_rest_countries.py
    ├── test_open_meteo.py
    ├── test_exchange_rates.py
    ├── test_parser.py
    ├── test_agent_*.py        # Per-agent manual test runners
    ├── test_input_guardrail.py
    └── test_output_validators.py
```

---

## 3. End-to-End Request Flow

### Web flow (browser)

```
User types query → clicks Plan
        │
        ▼
POST /api/parse
  ├─ Input guardrail check  (Groq classifies: is this travel-related?)
  │     If rejected → 403 → show refusal message on landing page
  │     If guardrail fails (API error) → fail open, assume travel request
  └─ Query parser  (Groq extracts: city, days, budget, interests, month)
        │
        ▼
Redirect to /confirm?city=...&days=...&budget=...
  User reviews and edits parsed fields
        │
        ▼
POST /api/plan  (confirm.js submits final fields)
  └─ Server creates trip_id (UUID), creates session, fires background thread
        │
        ▼
Redirect to /planning?id={trip_id}
  Browser opens SSE: GET /api/plan/{trip_id}/stream
        │
        ▼
Background thread runs LangGraph graph:
  supervisor → destination → supervisor → weather → supervisor
            → budget → supervisor → itinerary → supervisor → packing → END
  Each step pushes an event to the session queue
  SSE endpoint drains the queue and sends JSON events to browser
        │
        ▼
planning.js receives plan_complete event
  Redirects to /brief/{trip_id}
        │
        ▼
brief.js fetches GET /api/plan/{trip_id}/result
  Renders all 5 sections
```

### CLI flow

```
python app.py "5 days in Tokyo, ¥80,000"
  │
  ├─ Input guardrail check
  ├─ Query parser
  ├─ stdout confirmation prompt (human-in-loop)
  ├─ run_with_progress() streams events to terminal
  └─ Pretty-print 5 sections to stdout
```

---

## 4. Core Source Files (`src/`)

### `src/state.py` — Shared LangGraph State

Every agent reads from and writes to a single shared dictionary called `AgentState`. It is a TypedDict (typed Python dict) that LangGraph passes through the graph.

**Key fields:**

| Field | Type | Set by |
|---|---|---|
| `user_query` | str | Initial setup |
| `destination_city` | str | Parser |
| `destination_country` | str | Parser |
| `trip_duration_days` | int | Parser |
| `budget_amount` | float | Parser |
| `budget_currency` | str | Parser |
| `interests` | list[str] | Parser |
| `travel_month` | str | Parser |
| `destination_info` | dict | Destination agent |
| `weather_data` | dict | Weather agent |
| `budget_breakdown` | dict | Budget agent |
| `itinerary` | dict | Itinerary agent |
| `packing_list` | dict | Packing agent |
| `validation_status` | dict | Supervisor (per agent: pending/valid/invalid/invalid_accepted) |
| `retry_count` | dict | Supervisor (how many retries each agent has used) |
| `validation_feedback` | dict | Supervisor (feedback string injected into agent prompt on retry) |
| `last_agent` | str | Each agent (which agent just ran) |
| `next_agent` | str | Supervisor (which agent to run next) |

`empty_state(user_query)` is a factory function that creates a fresh state with all agents set to `"pending"`.

---

### `src/schemas.py` — Pydantic Models

All LLM inputs and outputs are validated through Pydantic v2 models. These are the "contracts" between the LLM responses and the Python code.

**Models:**

- **`ParsedQuery`** — What the parser extracts from the user's text. Fields: destination_city, destination_country, trip_duration_days (1–60), budget_amount, budget_currency (ISO 4217), interests, travel_month.

- **`InputClassification`** — What the guardrail decides. Fields: is_travel_request (bool), category (one of: travel_planning / code_request / general_chat / harmful / off_topic / other), reason.

- **`BudgetCategory`** — One spending category. Fields: name (one of: accommodation / food / transport / activities / buffer), daily_amount, description.

- **`BudgetBreakdown`** — Full budget plan. Contains total_budget_native, total_budget_local, exchange_rate_used, duration_days, daily_budget_local, categories (4–5 required), notes.

- **`DaySegment`** — One time slot in an itinerary day. Fields: time (e.g. "9:00 AM – 11:30 AM"), period (one of: early morning / morning / late morning / lunch / afternoon / late afternoon / evening), activity (3–6 words), location (must be a real named place), description (2–3 vivid sentences), tips (optional), cost_note (optional).

- **`ItineraryDay`** — One full day. Fields: day (int), theme (title), highlights (2–4 standout moments), segments (3–6 DaySegments), transport_note.

- **`Itinerary`** — Complete trip. Fields: destination, days (list of ItineraryDay), summary.

- **`PackingCategory`** — One packing category. Fields: category (one of: clothing / documents / gear / toiletries / electronics), items (list of strings).

- **`PackingList`** — Complete packing list. Fields: destination, duration_days, weather_summary, categories (min 3).

- **`ValidationResult`** — Guardrail verdict on agent output. Fields: is_valid, issues (list of problem descriptions), feedback_for_agent (string injected into the prompt on retry).

- **`DestinationOverview`** — Two-paragraph LLM-written travel intro. Fields: overview_paragraph_1, overview_paragraph_2.

---

### `src/parser.py` — Query Parser

Converts the user's free-text query into a structured `ParsedQuery`.

```python
def parse_query(user_query: str) -> ParsedQuery
```

Uses Groq with `with_structured_output(ParsedQuery)` which forces the model to return valid JSON matching the schema. The prompt (`PARSE_PROMPT`) instructs the model on edge cases:
- "weekend" → 2 days, "long weekend" → 3 days, "week" → 7 days
- `$` → USD, `€` → EUR, `£` → GBP, `¥` → JPY, `₹` → INR
- Interests should be lowercase noun phrases (e.g. "temples", "street food", "hiking")
- Infer country from city if not provided

If the LLM call throws an exception, it is re-raised so `server.py` can return a proper error to the browser.

---

### `src/guardrails.py` — Input & Output Validation

**Two responsibilities:**

#### 1. Input Guardrail

```python
def check_input_is_travel_related(user_query: str) -> InputClassification
```

Before any planning starts, this function classifies whether the query is actually a travel request. It prevents users from asking the planner to write code, generate essays, etc.

- Uses Groq with `with_structured_output(InputClassification)`
- Fast path: empty or trivially short queries are immediately rejected
- If the Groq call fails for any reason (rate limit, network error, API key issue), it **fails open** — returns `is_travel_request=True` — so users are never blocked by infrastructure problems

The refusal message shown to users when rejected:
> "I'm a travel planner — I can only help you plan trips, suggest destinations, estimate budgets, and similar travel tasks. I can't help with that request, but if you tell me where you'd like to go, I'll plan the whole thing."

#### 2. Output Validators (one per agent)

After each agent runs, the supervisor calls `validate_agent_output(agent_name, state)` which dispatches to the correct validator.

| Validator | What it checks |
|---|---|
| `validate_destination` | Required fields present, currency code is 3-char ISO alpha |
| `validate_weather` | At least 5 forecast days, all required fields per day, temperature sanity (-60°C to 60°C) |
| `validate_budget` | Categories not empty, all daily_amounts positive, duration_days matches trip, all 4 required categories present |
| `validate_itinerary` | Correct number of days, at least 4 segments per day, no generic locations (TBD / downtown / the city), all segments have descriptions |
| `validate_packing` | Has both "clothing" and "documents" categories, no empty category item lists |

When a validator finds problems, it returns a `ValidationResult` with `is_valid=False` and a `feedback_for_agent` string. The supervisor injects this string back into the agent's prompt on retry so the agent knows exactly what to fix.

---

### `src/supervisor.py` — Routing Logic

The supervisor is the brain of the system. It runs between every agent call and decides what to do next.

```python
def supervisor_route(state: AgentState) -> str
```

**Decision algorithm:**

```
1. Read last_agent from state — which agent just finished
2. If last_agent is set:
   a. Run validate_agent_output(last_agent, state)
   b. If valid:
        - Set validation_status[last_agent] = "valid"
        - Log: "ROUTE destination -> weather (valid)"
   c. If invalid AND retry_count[last_agent] < MAX_RETRIES:
        - Increment retry_count[last_agent]
        - Write feedback to validation_feedback[last_agent]
        - Return the same agent name again (retry)
        - Log: "ROUTE destination -> destination (retry 1/2: Missing field: capital)"
   d. If invalid AND retry cap hit:
        - Set validation_status[last_agent] = "invalid_accepted"
        - Log: "ROUTE destination -> weather (invalid_accepted, moving on)"
3. Find next pending agent (in order: destination → weather → budget → itinerary → packing)
4. If no pending agents → return END
5. Return next agent name
```

`MAX_RETRIES` defaults to 2 (set via `MAX_AGENT_RETRIES` env var). This means each agent can run at most 3 times (1 initial + 2 retries) before the supervisor gives up and accepts whatever it produced.

The order `AGENT_ORDER` is fixed: destination must run before weather (needs country), budget must run before itinerary (needs budget tier).

---

### `src/graph.py` — LangGraph Graph Assembly

This file builds and compiles the LangGraph `StateGraph`.

**Topology:**

```
START
  │
  ▼
supervisor  ──conditional edges──►  destination
                                    weather
                                    budget
                                    itinerary
                                    packing
                                    END

destination ──unconditional──► supervisor
weather     ──unconditional──► supervisor
budget      ──unconditional──► supervisor
itinerary   ──unconditional──► supervisor
packing     ──unconditional──► supervisor
```

Every agent always returns to the supervisor. The supervisor decides where to go next. This is why the supervisor is a **conditional edge** (it evaluates `supervisor_route()` to decide the target), while the agent edges are **unconditional** (they always go back to supervisor).

The graph is compiled with `MemorySaver` as the checkpointer — this allows the graph state to be inspected or replayed at any step.

**Module-level singletons:**
```python
travel_graph, memory_checkpointer = build_graph()
```
These are imported by `runner.py` and reused across all requests (no rebuild per trip).

---

### `src/runner.py` — Graph Executor

```python
def run_with_progress(initial_state: AgentState, trip_id: str) -> Generator[dict, None, None]
```

Runs the compiled graph and yields **progress events** that the SSE endpoint streams to the browser.

It uses LangGraph's `.stream(mode="values")` which yields the full state after every node execution. By comparing the previous and current state, the runner detects:

| Event type | When emitted | Frontend effect |
|---|---|---|
| `agent_started` | Supervisor dispatches an agent | Row icon: spinning |
| `agent_retried` | Supervisor retries an agent | Row icon: spinning + attempt count |
| `agent_completed` | Supervisor validates and accepts output | Row icon: green check or orange warning |
| `plan_complete` | Graph reaches END | Redirects to trip brief |
| `plan_error` | Unhandled exception | Shows error message |

Each event is a dict with a `type` field plus agent-specific data. The SSE endpoint serializes them as `data: {...}\n\n`.

---

## 5. The Five Agents

Each agent is a plain Python function that takes `AgentState` and returns a partial state dict:

```python
def some_agent(state: AgentState) -> dict:
    # read from state
    # call API / LLM
    # return {"some_key": result, "last_agent": "some_agent"}
```

LangGraph merges the returned dict into the shared state automatically.

---

### `src/agents/destination.py` — Destination Agent

**What it does:**
1. Infers the destination country from the city name using a hardcoded map (`_CITY_COUNTRY_MAP`, 100+ cities). Falls back to asking the user or using destination_country from state.
2. Calls `fetch_country_info(country_name)` → gets capital, currency, languages, timezone, region, flag.
3. Calls Groq (temp=0.7) with `OVERVIEW_PROMPT` to write two vivid travel paragraphs about the city.
4. Merges country metadata + LLM overview paragraphs into `destination_info` dict.

**Output written to state:** `destination_info` — used by budget agent (currency code), itinerary agent (country name), packing agent (region).

**Retry behavior:** If the REST Countries API returns an error or required fields are missing, the validator flags it and the agent retries. On retry, `feedback_for_agent` is injected into the prompt.

---

### `src/agents/weather.py` — Weather Agent

**What it does:**
1. Calls `geocode_city(destination_city)` → gets latitude, longitude, timezone.
2. Calls `fetch_weather_forecast(latitude, longitude)` → gets 7-day daily forecast.
3. Returns `weather_data` dict with city name, country, timezone, and 7 days of: date, temp_max_c, temp_min_c, precipitation_mm, wind_max_kmh.

**No LLM involved** — this agent is entirely deterministic API calls.

**Output written to state:** `weather_data` — used by packing agent (rain/cold/hot clothing suggestions) and itinerary agent (weather summary in prompt).

---

### `src/agents/budget.py` — Budget Agent

**What it does:**
1. Reads `budget_amount` + `budget_currency` from state.
2. Calls `fetch_exchange_rates()` to get live FX rates.
3. Converts user's budget to the destination's local currency using a two-leg USD conversion.
4. Computes the **exact** daily budget: `local_amount / trip_duration_days`.
5. Classifies the budget into a tier based on USD-equivalent daily spend:

| Tier | USD/day |
|---|---|
| budget | < $50 |
| mid-range | $50 – $150 |
| comfortable | $150 – $400 |
| upscale | $400 – $1,000 |
| luxury | > $1,000 |

6. Calls Groq (temp=0.0) with tier-specific category guidance to get proportional allocations across: accommodation, food, transport, activities, buffer.
7. **Force-scales** all category `daily_amount` values so they sum exactly to the real daily budget — the LLM only provides proportions, never the final numbers.
8. Stamps all authoritative fields (total, daily, currency, rate) directly in code — never from LLM output.

**Why force-scaling?** LLMs are bad at arithmetic. They often produce amounts that don't sum correctly. By treating the LLM output as proportions and rescaling in code, the math is always exact.

**Output written to state:** `budget_breakdown` — includes `budget_tier` which the itinerary agent uses to calibrate recommendation style.

---

### `src/agents/itinerary.py` — Itinerary Agent

**What it does:**
1. Reads budget tier from `state["budget_breakdown"]["budget_tier"]`.
2. Selects a tier-specific style guide (`_TIER_STYLE` dict) that tells the LLM what level of hotel, restaurant, transport, and activity to recommend.
3. Generates the itinerary in **batches of 4 days** to avoid hitting token limits on long trips:
   - 1–4 days: 1 batch
   - 5–8 days: 2 batches (days 1–4, then 5–8)
   - 9–12 days: 3 batches, etc.
4. Each batch calls Groq (temp=0.7, max_tokens=4096) with `ITINERARY_PROMPT` which requires:
   - Exactly 4–5 segments per day
   - Specific real location names (never "downtown" or "TBD")
   - 2 vivid descriptive sentences per segment
   - Realistic clock-time ranges
   - Budget-tier-appropriate pricing and venues
5. Assembles all batches, sorts by day number, wraps into a single `Itinerary` Pydantic model.

**Budget tier influence examples:**

| Tier | Accommodation | Food | Transport |
|---|---|---|---|
| budget | Hostel dorms | Street food stalls | Metro/bus only |
| mid-range | 3-star hotels | Casual restaurants | Mix public + taxi |
| comfortable | 4-star hotels | Quality restaurants + fine dining | Taxis + transfers |
| upscale | 5-star hotels | Fine dining, wine pairings | Private car hire |
| luxury | Palace hotels, villas | Michelin-starred only | Helicopter, yacht |

**Output written to state:** `itinerary`

---

### `src/agents/packing.py` — Packing Agent

**What it does:**
1. Reads `destination_city`, `trip_duration_days`, `interests`, `travel_month`, and `weather_data`.
2. Summarizes the weather forecast into a one-line string (avg highs/lows, rain days, wind days).
3. Calls Groq (temp=0.5) with `PACKING_PROMPT` which asks for 5 categories:
   - **clothing** — Must match the travel month's typical climate (NOT live forecast)
   - **documents** — Passport, insurance, booking copies, visa if needed
   - **toiletries** — Essentials + climate-appropriate (sunscreen for hot, lip balm for cold)
   - **gear** — Activity-specific (hiking boots, camera, swimsuit)
   - **electronics** — Phone, charger, adapter + activity-specific devices
4. The prompt uses temperature bands to guide clothing recommendations:
   - Below 5°C → heavy coat, thermals, gloves, wool socks
   - 5–12°C → warm jacket, fleece, long trousers
   - 12–20°C → light jacket, layers, mix of long/short
   - 20–28°C → breathable fabrics, thin evening layer
   - Above 28°C → lightweight fabrics, sun hat, UV shirt
   - Rainy season → waterproof jacket, compact umbrella, waterproof shoes

**Why travel month, not live forecast?** If someone is planning a trip to Norway in December but checking the app in May, the live forecast (warm) is irrelevant. The packing list must reflect what December in Norway is actually like. The live forecast is provided as supplementary context only.

**Output written to state:** `packing_list`

---

## 6. LangGraph & Supervisor Architecture

### What is LangGraph?

LangGraph is a library for building **stateful multi-agent workflows** as a directed graph. Each node in the graph is a Python function that reads from a shared state dict and writes partial updates back. The graph manages state transitions, persistence, and streaming.

### How the graph is structured

```
                     ┌──────────────────────────────────────────────┐
                     │                 StateGraph                   │
                     │                                              │
START ──────────────►│  supervisor_node                             │
                     │     │                                        │
                     │     │ conditional_edge                       │
                     │     │ (calls supervisor_route())             │
                     │     ▼                                        │
                     │  ┌──────────────────────────────────────┐   │
                     │  │  destination_node  weather_node  ...  │   │
                     │  │  budget_node  itinerary_node          │   │
                     │  │  packing_node  END                    │   │
                     │  └──────────────────────────────────────┘   │
                     │     │                                        │
                     │     │ unconditional_edge (always ─► supervisor)
                     │     ▼                                        │
                     │  supervisor_node (again)                     │
                     │                                              │
                     └──────────────────────────────────────────────┘
```

**Key insight:** The supervisor is NOT an LLM. It is a plain Python function with deterministic routing logic. This is a core design choice — LLM-based routing is unpredictable and hard to debug. Deterministic routing means you can always trace exactly why agent X ran before agent Y.

### How LangGraph state works

When a node (agent) runs, it returns a partial dict. LangGraph **merges** this dict into the full state. So if the weather agent returns `{"weather_data": {...}, "last_agent": "weather"}`, only those two keys are updated — everything else stays the same.

```python
# Agent returns partial update
def weather_agent(state: AgentState) -> dict:
    ...
    return {
        "weather_data": forecast,
        "last_agent": "weather",
    }

# LangGraph merges this into state automatically
# state["destination_info"] is unchanged
# state["weather_data"] = forecast
# state["last_agent"] = "weather"
```

### How the retry loop works

The supervisor implements the retry loop in `supervisor_route()`:

```python
# After "destination" agent ran:
result = validate_agent_output("destination", state)

if result.is_valid:
    state["validation_status"]["destination"] = "valid"
    return "weather"  # next agent

elif state["retry_count"]["destination"] < MAX_RETRIES:
    state["retry_count"]["destination"] += 1
    state["validation_feedback"]["destination"] = result.feedback_for_agent
    return "destination"  # retry same agent

else:
    state["validation_status"]["destination"] = "invalid_accepted"
    return "weather"  # give up, move on
```

The agent reads the feedback on retry:
```python
def destination_agent(state: AgentState) -> dict:
    feedback = state.get("validation_feedback", {}).get("destination", "")
    if feedback:
        # Inject feedback into prompt so LLM knows what to fix
        prompt = f"IMPORTANT — previous attempt failed: {feedback}\n\n" + base_prompt
```

### The `last_agent` handshake

Every agent sets `"last_agent": "agent_name"` in its return dict. The supervisor reads `state["last_agent"]` to know which agent just finished and therefore which output to validate. This is how the supervisor knows the graph just came from the destination agent vs the weather agent.

---

## 7. Tools (External APIs)

Tools are decorated with LangChain's `@tool` decorator which makes them callable as structured LangChain tools. They are invoked directly (not via LLM tool-use) with `.invoke({...})`.

### `src/tools/rest_countries.py`

**API:** `https://restcountries.com/v3.1/name/{country}` — Free, no key

**Function:** `fetch_country_info(country_name: str) → dict`

Returns: country_name, official_name, capital, currency_code, currency_name, currency_symbol, languages (list), timezone, region, subregion, flag (emoji).

On 404 or network error: returns `{"error": "..."}` — the validator will catch this.

---

### `src/tools/open_meteo.py`

**APIs:** `https://geocoding-api.open-meteo.com` and `https://api.open-meteo.com` — Free, no key

**Functions:**

`geocode_city(city: str) → dict` — Returns latitude, longitude, country, timezone for a city name.

`fetch_weather_forecast(latitude, longitude) → dict` — Returns 7 days of: date, temp_max_c, temp_min_c, precipitation_mm, wind_max_kmh.

`get_city_timezone(city: str) → dict` — Geocodes city + extracts timezone. Used internally.

---

### `src/tools/exchange_rates.py`

**API:** `https://open.er-api.com/v6/latest/USD` — Free, no key

**Functions:**

`fetch_exchange_rates() → dict` — Returns all exchange rates with USD as base.

`convert_currency(amount, from_currency, to_currency) → dict` — Two-leg conversion via USD (from → USD → to).

`convert(amount, from_ccy, to_ccy, rates) → float` — Synchronous helper used directly by budget agent (raises `KeyError` for unknown currencies).

---

## 8. Web Layer (`web/`)

### `web/server.py` — FastAPI App

The web server has 4 HTML page routes and 4 API routes.

**Page routes** (return HTML via Jinja2 templates):
- `GET /` → `landing.html`
- `GET /confirm` → `confirm.html`
- `GET /planning` → `planning.html`
- `GET /brief/{trip_id}` → `brief.html`

**API routes:**

`POST /api/parse`
- Receives `{ "query": "..." }`
- Runs input guardrail → if rejected, raises `HTTPException(403)` with the refusal message
- Runs query parser → returns structured `ParseResponse` (city, country, days, budget, currency, month, interests, original_query)
- Frontend uses this to pre-fill the confirm form

`POST /api/plan`
- Receives `PlanRequest` (all confirmed fields)
- Creates a `TripSession` in the sessions store
- Launches `_run_graph_background()` in a `ThreadPoolExecutor` (4 workers)
- Returns `{ "trip_id": "..." }` immediately (non-blocking)

`GET /api/plan/{trip_id}/stream` (SSE)
- Streams events from the session's `threading.Queue` as Server-Sent Events
- Format: `data: {"type": "agent_started", "agent": "destination", ...}\n\n`
- Polls queue with 30s timeout, sends `keep-alive` comments to prevent timeout
- Ends when `plan_complete` or `plan_error` sentinel is dequeued

`GET /api/plan/{trip_id}/result`
- Returns the final state dict once planning is complete
- Returns 202 if still in progress
- Returns 500 with error detail if planning failed

**Background execution:**

```python
async def _run_graph_background(trip_id: str, state: AgentState):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        _executor,
        _run_graph_sync,  # synchronous graph execution
        trip_id, state
    )
```

The graph is synchronous (blocking LLM calls). It runs in a thread pool so it doesn't block the async FastAPI event loop.

---

### `web/sessions.py` — In-Memory Session Store

Each trip has a `TripSession` dataclass:

```python
@dataclass
class TripSession:
    trip_id: str
    initial_state: dict
    event_queue: queue.Queue   # thread-safe queue for SSE events
    is_complete: bool
    final_state: Optional[dict]
    error: Optional[str]
```

**Thread coordination:**
- Background thread (graph execution) pushes events to `event_queue`
- Async SSE handler reads from `event_queue`
- `threading.Queue` is thread-safe — no locks needed for the queue itself
- A `threading.Lock` protects `is_complete` and `final_state` writes

Sessions are kept in an in-memory dict — they are lost on server restart. This is intentional (no database needed for a stateless demo).

---

### Templates

| Template | Screen | Purpose |
|---|---|---|
| `base.html` | — | Shared: Tailwind CSS, Google Fonts, Material Symbols icons, color palette |
| `landing.html` | Screen 1 | Query textarea + Plan button + example chips |
| `confirm.html` | Screen 2 | Editable form for all parsed fields |
| `planning.html` | Screen 3 | 5 agent rows with live status icons |
| `brief.html` | Screen 4 | Full trip brief (destination / weather / budget / itinerary / packing) |

**Styling:**
- Framework: Tailwind CSS (CDN)
- Fonts: Playfair Display (headings, serif), DM Sans (body, sans-serif)
- Icons: Material Symbols (outlined)
- Color: Purple primary (`#4f378a`), light lavender surface (`#fdf7ff`)

---

## 9. Frontend JavaScript

### `landing.js`

- Handles the Plan button click and Ctrl+Enter shortcut
- `POST /api/parse` → on success, redirects to `/confirm?city=...&days=...&budget=...&...`
- On 403 (guardrail rejection): shows the refusal message in the error box
- On any other error: shows generic "Something went wrong" message
- `fillExample(btn)` — copies example text from chip into textarea

### `confirm.js`

- Reads all URL params and pre-fills the form fields on page load
- On form submit: validates city + days are non-empty, then `POST /api/plan`
- On success: redirects to `/planning?id={trip_id}`
- Disables button during submission to prevent double-clicks

### `planning.js`

Opens `EventSource` to `/api/plan/{trip_id}/stream` and listens for events:

| Event type | What happens in UI |
|---|---|
| `agent_started` | Target row: hide pending icon, show spinning icon |
| `agent_retried` | Target row: update attempt count in summary |
| `agent_completed` (valid) | Target row: show green check icon + summary text |
| `agent_completed` (invalid_accepted) | Target row: show orange warning icon |
| `plan_complete` | Update status line → after 800ms redirect to `/brief/{trip_id}` |
| `plan_error` | Show error message, close SSE |

Each agent row in `planning.html` has `data-agent="destination"` etc. attributes. The JS selects them with `document.querySelector('[data-agent="destination"]')`.

### `brief.js`

Fetches `/api/plan/{trip_id}/result` and renders all 5 sections:

- `renderOverview(info)` — Country metadata cards (capital, currency, languages, timezone, region) + 2 overview paragraphs
- `renderWeather(wd)` — 7-day grid: each day shows max/min temp + rain drop icon if precipitation > 0
- `renderBudget(bd)` — 3 summary cards (original budget, local currency, daily budget) + category table (name / per day / notes)
- `renderItinerary(itin)` — Day cards: purple header (day number + theme), highlight badges, time segments (with period icon, activity, location, description, tip callout, cost badge), transport note footer
- `renderPacking(pl)` — Multi-column category grid with bullet items

`periodIcon(period)` maps time-of-day labels to Material Symbols icons: morning → `wb_sunny`, evening → `nights_stay`, lunch → `restaurant`, etc.

If any section's data is missing or contains an `error` key, the section is silently skipped (hidden).

---

## 10. Logging System — How to Debug

### Log file locations

All logs are written to the `logs/` directory (auto-created). Each logger writes to **two places simultaneously**: its own file AND `logs/master.log`.

| File | What's in it |
|---|---|
| `logs/master.log` | Everything — full trace of every run in chronological order |
| `logs/supervisor.log` | Only routing decisions (ROUTE lines) |
| `logs/destination.log` | Only destination agent calls |
| `logs/weather.log` | Only weather agent calls |
| `logs/budget.log` | Only budget agent calls |
| `logs/itinerary.log` | Only itinerary agent calls |
| `logs/packing.log` | Only packing agent calls |
| `logs/guardrails.log` | Guardrail classifications + validation results |
| `logs/parser.log` | Query parsing results |
| `logs/web.log` | HTTP requests + session events |

### Log format

Every line follows this format:
```
2024-01-15 14:23:01 | INFO    | supervisor   | ROUTE  destination ->   weather       (valid)
│                     │          │               │
timestamp             level      logger name    message
```

### Reading the logs — what each message means

**Supervisor routing:**
```
ROUTE  destination ->   weather       (valid)
ROUTE  destination ->   destination   (retry: Missing field: capital)
ROUTE       budget ->   budget        (retry 2/2: Budget has no category breakdown.)
ROUTE  itinerary   ->   itinerary     (invalid_accepted, moving on)
ROUTE      packing ->   END           (all agents done)
```
- `valid` — Output passed validation, moving to next agent
- `retry: <reason>` — Output failed, retrying with feedback
- `retry 2/2` — Second retry (final attempt)
- `invalid_accepted` — Hit retry cap, accepting bad output and continuing
- `all agents done` — All 5 agents finished, graph ending

**Agent start/retry:**
```
INFO | budget    | Budget agent attempt #1
INFO | budget    | Budget agent attempt #2
INFO | budget    | Retry feedback: Budget has no category breakdown; Missing required budget categories: ['activities']
```
- Attempt #1 is the first run, #2 is first retry, #3 is second retry
- The retry feedback line shows exactly what the validator told the agent to fix

**Validation failures:**
```
INFO  | guardrails | Validating budget output: is_valid=False issues=['Budget has no category breakdown.']
INFO  | guardrails | Validating itinerary output: is_valid=False issues=["Day 2 afternoon has a generic/empty location: 'the city'", "Day 3 morning is missing a description."]
```

**Guardrail input classification:**
```
INFO  | guardrails | Running input guardrail on query (31 chars)
INFO  | guardrails | Input classification: is_travel=True category=travel_planning reason=The user is planning a trip to Paris with a specific budget
WARNING | guardrails | Input guardrail failed (429 rate limit) — failing open, assuming travel request.
```
- `is_travel=False` + `category=other` means the request was blocked
- The WARNING "failing open" means the API call failed but we're letting it through anyway

**LLM errors:**
```
ERROR | itinerary | Itinerary LLM call failed (days 1-4): tool_use_failed — the model failed to produce valid tool call JSON
ERROR | budget    | Budget LLM call failed after retries: Error code: 429 - Rate limit reached
```
- `tool_use_failed` — Groq's structured output mechanism returned malformed JSON. Usually transient.
- `Error code: 429` — Rate limit hit. On free tier: 100,000 tokens/day. Wait or use new API key.
- `Error code: 401` — Invalid API key. Check `.env` file.

**Successful agent completion:**
```
INFO | destination | Destination OK: France (Paris) — flag: 🇫🇷
INFO | weather     | Weather OK: 7 days for Paris (avg 12°C / 7°C, 3 rainy days)
INFO | budget      | Budget OK: 400.00 EUR -> 200.00 EUR/day | tier=mid-range | 5 categories
INFO | itinerary   | Itinerary OK: 2 days for Paris [tier=mid-range]
INFO | packing     | Packing OK: 5 categories for Paris (2 days)
```

**HTTP layer:**
```
INFO  | web | POST /api/parse query_len=31
INFO  | web | Input classification: is_travel=True
INFO  | web | Plan started: trip_id=abc123
WARNING | web | Input rejected: Guardrail error: ...
```

### Common debug scenarios

**"This section could not be generated"** shown on brief page:
→ Open `logs/master.log`, find the relevant trip, look for `ERROR` lines for that agent. Usually `tool_use_failed` (Groq malformed response) or `LLM call failed after retries`. If the validator rejected it 3 times, look for `invalid_accepted`.

**All sections blank / "Something went wrong" on landing:**
→ Check `logs/guardrails.log` for `Input guardrail crashed` and `logs/parser.log` for parser errors. Usually a rate limit (429) or invalid API key (401).

**Only overview + weather work, others fail:**
→ Complex schemas (BudgetBreakdown, Itinerary, PackingList) trigger Groq's `tool_use_failed` more than simple ones. Check `logs/budget.log` for the exact error. May need to wait for rate limit reset or use a fresh API key.

**Agent stuck / planning hangs:**
→ LangGraph `.stream()` will block on a hung LLM call. Check `logs/master.log` — the last `agent attempt #N` line shows where it's stuck. The Groq free tier can have high latency under load.

**Budget numbers are wrong:**
→ The budget agent force-scales LLM output — LLM arithmetic errors are always corrected in code. If numbers are still wrong, check `logs/budget.log` for the FX conversion step: `Currency conversion failed: 'XYZ'` means an unknown currency code.

**Itinerary has generic locations ("downtown", "the area"):**
→ The `validate_itinerary` validator catches these and flags them. Check `logs/supervisor.log` for retry lines on the itinerary agent. If it hits the retry cap, `invalid_accepted` means the bad output was accepted.

### Log rotation

Each log file rotates at 2 MB with 3 backups (`master.log`, `master.log.1`, `master.log.2`, `master.log.3`). This prevents the logs directory from growing unbounded.

---

## 11. Configuration & Environment

### `.env` file

```
GROQ_API_KEY=gsk_...              # Required — get from console.groq.com/keys
GROQ_MODEL=llama-3.3-70b-versatile  # Optional, default shown
MAX_AGENT_RETRIES=2               # Optional — max retries per agent (default 2)
LOG_TO_CONSOLE=1                  # Optional — set to 0 to suppress stdout logging
```

`python-dotenv` loads this file automatically when the app starts (`load_dotenv()` is called at the top of `app.py` and `web/server.py`).

**Important:** Changing `.env` while the server is running requires a **restart** — the server reads env vars once at startup. The `--reload` flag only watches Python file changes, not `.env` changes.

### External API keys

No keys are needed for REST Countries, Open-Meteo, or Open Exchange Rates. Only Groq requires a key.

### Groq free tier limits

| Limit | Value |
|---|---|
| Tokens per day | 100,000 |
| Tokens per minute | 6,000 |
| Requests per minute | 30 |

A single full trip plan (5 agents) uses approximately 8,000–15,000 tokens. The daily limit allows roughly 7–12 full trips per day on the free tier.

---

## 12. Tests & Scripts

### `tests/test_tools.py` — Tool Smoke Tests

Run with `pytest tests/test_tools.py -v`. Tests each external API once:
- REST Countries lookup for Japan
- REST Countries 404 handling
- Open-Meteo geocoding for Tokyo
- 7-day forecast structure validation
- Exchange rates load
- USD ↔ JPY round-trip conversion

These tests make live API calls and require internet access. They do NOT require the Groq API key.

### `tests/test_graph.py` — End-to-End Integration Tests

Run with `pytest tests/test_graph.py -v`. Runs 3 full trip plans through the graph:
- Tokyo, 5 days, ¥80,000
- Paris, 2 days, €400
- Reykjavik, 7 days, $3,000

Validates all 5 sections present, no errors, budget math correct, itinerary day count matches duration. **Requires Groq API key and uses ~30,000–45,000 tokens total.**

### `scripts/` — Manual Test Scripts

One script per component. Run individually to diagnose a specific part:

```bash
python scripts/test_gemini.py           # Verify Groq API key works
python scripts/test_rest_countries.py   # Test REST Countries API
python scripts/test_open_meteo.py       # Test geocoding + forecast
python scripts/test_exchange_rates.py   # Test FX rates
python scripts/test_parser.py           # Test query parser with sample inputs
python scripts/test_agent_budget.py     # Run just the budget agent
python scripts/test_input_guardrail.py  # Test travel vs non-travel classification
```

---

## 13. Key Design Decisions

### 1. Supervisor is code, not LLM

The supervisor (`supervisor.py`) is a plain Python function with no LLM calls. Routing decisions are deterministic: validate output → pass or retry or accept.

Using an LLM to route would mean the system could make unpredictable routing decisions, hallucinate agent names, or behave inconsistently. Deterministic routing means every routing decision is logged and reproducible.

### 2. Force-scaled budget math

The budget agent asks the LLM only for proportions (40% accommodation, 25% food, etc.). All actual money amounts are computed in Python. The LLM's numbers are thrown away and rescaled to match the authoritative daily budget.

This prevents the common LLM arithmetic failure where category amounts don't sum to the daily budget.

### 3. Batched itinerary generation

Generating a 10-day itinerary in a single LLM call would require ~8,000+ output tokens, exceeding Groq's token limits and causing truncated/malformed JSON. Instead, itineraries are generated in 3-day batches, assembled in Python, and validated as a whole.

### 4. Validation feedback loop

When an agent's output fails validation, the specific issues are written back into `state["validation_feedback"][agent_name]`. On retry, the agent reads this string and injects it into the prompt. This means the LLM is told exactly what was wrong ("Day 2 morning has a generic location: 'the city'") rather than just asked to try again blindly.

### 5. Fail-open input guardrail

If the Groq API is unavailable (rate limit, network error, invalid key), the input guardrail returns `is_travel_request=True` and lets the request through. The alternative — blocking all users when the guardrail fails — is worse than the risk of processing a non-travel request.

### 6. Thread pool + async SSE

The LangGraph graph uses blocking (synchronous) LLM calls. FastAPI is asynchronous. Running the graph in the async event loop would block all other requests.

Solution: the graph runs in a `ThreadPoolExecutor` (4 workers). It pushes events into a `threading.Queue`. The async SSE endpoint reads from the queue without blocking. This bridges the sync/async boundary cleanly.

### 7. Per-agent logging

Every agent writes to its own log file AND the master log. This means:
- When a specific agent is misbehaving, open `logs/itinerary.log` to see only itinerary calls
- When debugging the full flow, open `logs/master.log` to see everything in order
- The supervisor's `logs/supervisor.log` gives a clean routing summary with no LLM output noise

### 8. Travel month vs live forecast in packing

The live weather forecast reflects current conditions, not travel-month conditions. A user planning a December trip in May gets a May forecast which is useless for packing warm clothes. The packing agent uses `travel_month` as the primary climate signal, and treats the live forecast as a secondary reference only. The prompt explicitly tells the LLM this distinction.
