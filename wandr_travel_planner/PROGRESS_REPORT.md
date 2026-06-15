# Wandr — AI Travel Planner
## Progress Report

**Project:** Wandr — AI Travel Planner  
**Date:** May 2026  
**Stack:** LangGraph · Groq (llama-3.3-70b-versatile) · FastAPI · Vanilla JS

---

## Section 1: System Architecture

### Overview

Wandr is a multi-agent travel planning system built on LangGraph's `StateGraph`. A single user query flows through an input guardrail, a natural-language parser, a human-in-the-loop confirmation step, and then a five-agent pipeline coordinated by a deterministic Supervisor node.

```
User query (CLI or Web UI)
        │
        ▼
┌───────────────────┐
│  Input Guardrail  │  ← Groq LLM; rejects non-travel queries (exit code 1)
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│     Parser        │  ← Groq with_structured_output(ParsedQuery)
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  Confirm Screen   │  ← Human-in-loop: user edits city/days/budget/interests
└────────┬──────────┘
         │
         ▼
┌────────────────────────────────────────────────────────────────┐
│                    LangGraph StateGraph                        │
│                                                                │
│   START → supervisor ──────────────────────────────┐          │
│                │                                   │          │
│          route to next                        validation       │
│          pending agent                        loop (retry)     │
│                │                                   │          │
│     ┌──────────┼───────────────────┐               │          │
│     ▼          ▼          ▼        ▼               │          │
│ destination  weather   budget  itinerary  packing   │          │
│     │          │          │        │        │       │          │
│     └──────────┴──────────┴────────┴────────┘       │          │
│                │                                   │          │
│           supervisor ──── VALID ──── next ─────────┘          │
│                │                                              │
│            all done → END                                     │
└────────────────────────────────────────────────────────────────┘
         │
         ▼
   Final state → CLI render / Web Trip Brief
```

### Supervisor + 5 Worker Agents

The Supervisor node is a pure Python routing function (`supervisor_route` in `src/supervisor.py`). It reads `state["last_agent"]`, calls the appropriate output validator from `src/guardrails.py`, and returns one of:

- The name of the **next agent** (when the last one passed validation)
- The **same agent name** (for a retry, up to `MAX_AGENT_RETRIES`)
- `END` (when all five agents have been validated)

The five worker agents run in a fixed order: **Destination → Weather → Budget → Itinerary → Packing**. Each writes its results into shared `AgentState` and sets `last_agent` to its own name so the supervisor can identify who just ran.

### Validation Loop

After each agent completes, the supervisor calls `validate_agent_output(agent_name, state)`. This runs deterministic checks first (field presence, type checks, value ranges, cross-field consistency), not an LLM. Examples:

- **Budget validator:** checks that per-category daily totals sum within 5% of `daily_budget_local`; checks that all four required categories are present
- **Itinerary validator:** checks that each day has ≥4 segments, each segment has a non-generic `location` (not "downtown", "the city", etc.) and a non-empty `description`
- **Weather validator:** checks for ≥5 forecast days and valid temperature ranges (−60°C to 60°C)

If validation fails and the retry count is below the cap, the supervisor increments `retry_count[agent]`, writes structured feedback into `validation_feedback[agent]`, and routes back to the same agent. The agent's prompt includes a `FEEDBACK_TEMPLATE` block on retry so the LLM knows what to fix.

If the retry cap is hit, the supervisor sets `validation_status[agent] = "invalid_accepted"` and continues to the next agent rather than stalling forever.

### MemorySaver Checkpointing

`MemorySaver` is configured at graph compile time:

```python
checkpointer = MemorySaver()
graph = builder.compile(checkpointer=checkpointer)
```

Every graph invocation is keyed by `thread_id` (the `trip_id` UUID). This means any step can be resumed from the last checkpoint if the process restarts mid-run. It also allows `travel_graph.get_state(config)` to retrieve the final state after streaming completes, which is how the web server serves the `/api/plan/{id}/result` endpoint.

### Why Parsing Runs Outside the Graph

Parsing happens before the LangGraph graph starts, not inside it. This is the human-in-the-loop pattern: the user sees the parsed parameters (city, days, budget, interests) on the Confirm screen and can edit them before planning begins. If parsing were inside the graph, there would be no clean point to pause, show the user the extracted data, accept edits, and then resume.

---

## Section 2: API Tools

### REST Countries v3.1
**URL:** `https://restcountries.com/v3.1/name/{country_name}`  
**Returns:** Country metadata — official name, capital, currencies, languages, timezone, region, flag emoji.  
**Used by:** Destination Agent — fetches the country info object that populates the Trip Brief Overview section.  
**Interesting detail:** The `capital` field is a list (e.g. `["Tokyo"]`), not a string. The tool explicitly takes `capital[0]` to get the string form.

### Open-Meteo Geocoding
**URL:** `https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1`  
**Returns:** Latitude, longitude, timezone, and country name for the top result.  
**Used by:** Weather Agent — resolves the city name to coordinates before calling the forecast API.  
**Interesting detail:** The API can return multiple results for ambiguous city names. The tool always takes `results[0]`, which works well in practice since results are ranked by population.

### Open-Meteo Forecast
**URL:** `https://api.open-meteo.com/v1/forecast?latitude=...&longitude=...&daily=...`  
**Returns:** 7-day daily forecast — max/min temperature, precipitation sum, wind speed max.  
**Used by:** Weather Agent — combined with geocoding output to produce the weather section.  
**Interesting detail:** The API returns parallel arrays (dates, max temps, min temps, etc.) rather than a list of day objects. The tool zips these arrays into a `daily_forecast` list of dicts for easier downstream consumption.

### Open Exchange Rates
**URL:** `https://open.er-api.com/v6/latest/USD`  
**Returns:** Exchange rates for 166 currencies relative to USD.  
**Used by:** Budget Agent — converts the user's budget from their currency to the destination's local currency using a two-step USD pivot (`amount × (1/from_rate) × to_rate`).  
**Interesting detail:** The free tier is keyed to USD as the base currency, so all conversions go through a USD pivot. This is slightly less precise than a direct conversion but the error is negligible for budget estimates.

---

## Section 3: Sample Outputs

### Run 1 — Tokyo, 5 days, ¥80,000

**Query:** `"Plan a 5-day trip to Tokyo in October, 80000 yen, temples and food"`

**Parsed:** city=Tokyo, country=Japan, 5 days, ¥80,000 JPY, interests=[temples, food], month=October

**Supervisor log (excerpt):**
```
ROUTE         START -> destination   (first dispatch)
ROUTE   destination -> weather       (valid → next)
ROUTE       weather -> budget        (valid → next)
ROUTE        budget -> itinerary     (valid → next)
ROUTE     itinerary -> packing       (valid → next)
ROUTE       packing -> END           (all agents valid)
```

**Output (5 sections):**
- Destination: Japan 🇯🇵, Tokyo, JPY — Japanese yen, UTC+09:00, 2-paragraph editorial intro
- Weather: 7-day forecast with avg high ~27°C in May (actual forecast date), no rain
- Budget: ¥80,000 total → ¥16,000/day across 5 categories
- Itinerary: 5 days, 4-5 segments each — Tsukiji market, Senso-ji, Shibuya crossing, Ghibli Museum, Meiji Shrine
- Packing: 5 categories, 18 items total, weather-appropriate

---

### Run 2 — Paris, 2 days, €400

**Query:** `"Weekend trip to Paris, budget 400 euros, I love museums and pastries"`

**Parsed:** city=Paris, country=France, 2 days, €400, interests=[museums, pastries]

**Supervisor log (excerpt):**
```
ROUTE         START -> destination   (first dispatch)
ROUTE   destination -> weather       (valid → next)
ROUTE       weather -> budget        (valid → next)
ROUTE        budget -> itinerary     (valid → next)
ROUTE     itinerary -> packing       (valid → next)
ROUTE       packing -> END           (all agents valid)
```

**Output highlights:**
- Budget: €400 / 2 days = €200/day; accommodation takes 50%, leaving €100/day for food and activities
- Itinerary Day 1 "Museum Marvels": Louvre (9–11:30 AM, €18), lunch at Café Marly (€25), Musée d'Orsay (2–4:30 PM, €12), Seine evening walk
- Itinerary Day 2 "Pastry Delights": Ladurée (8–10 AM, €10), Montmartre (Free), Boulangerie lunch, Sainte-Chapelle (€10)

---

### Run 3 — Reykjavik, 7 days, $3,000

**Query:** `"7-day adventure trip to Reykjavik, 3000 USD budget, hiking and hot springs"`

**Parsed:** city=Reykjavik, country=Iceland, 7 days, $3,000 USD, interests=[hiking, hot springs]

**Supervisor log (excerpt):**
```
ROUTE         START -> destination   (first dispatch)
ROUTE   destination -> weather       (valid → next)
ROUTE       weather -> budget        (valid → next)
ROUTE        budget -> itinerary     (valid → next)
ROUTE     itinerary -> packing       (valid → next)
ROUTE       packing -> END           (all agents valid)
```

**Output highlights:**
- Weather: 7-day forecast avg 9°C, 3 days with rain — packing validator correctly added rain gear
- Budget: $3,000 → ~418,350 ISK at the conversion rate, ~59,764 ISK/day
- Itinerary: Days themed as "City Introduction", "Nature Escape", "Cultural Experience", "Geothermal Adventure", "Rainy Day Culture" (indoor activities auto-scheduled for the rainy forecast day), "Hiking Adventure", "Geothermal Wonders"
- Packing: rain gear included because forecast showed precipitation > 1mm on 3 days

---

## Section 4: Issues Encountered and Solutions

### 1. Starlette 1.0.0 Breaking Change — TemplateResponse API

**Problem:** All four page routes returned HTTP 500 immediately after the web server started. The error was `TypeError: cannot use 'tuple' as a dict key (unhashable type: 'dict')` deep inside Jinja2's template cache.

**Root cause:** Starlette 1.0.0 changed the `TemplateResponse` signature. The old API was `TemplateResponse("name.html", {"request": request, ...})` — the template name as the first argument. The new API is `TemplateResponse(request, "name.html", context)`. With the old call, Starlette was passing the context dict as the template name to Jinja2, which then tried to use it as a cache key.

**Fix:** Updated all four page routes in `web/server.py` to the new API.

### 2. Groq Structured Output Token Limit on Long Itineraries

**Problem:** For trips longer than 4-5 days, the itinerary LLM call failed with `tool_use_failed: Failed to call a function`. Groq's structured output (function-calling mode) was truncating the response mid-JSON when the itinerary grew too long.

**Root cause:** Detailed itineraries with 5 segments × 4-6 rich fields each can exceed 4,000 tokens per response. Groq's structured output tool-call mode has tighter limits than the base completion endpoint.

**Fix:** Implemented batched generation in `src/agents/itinerary.py`. Trips are split into batches of 4 days. Each batch is a separate LLM call returning an `Itinerary` object with just those days. The results are merged and sorted into the final `Itinerary`. This keeps each call well within token limits and also allows partial results to survive if one batch needs a retry.

### 3. LLM Using Unlisted Period Values

**Problem:** The `DaySegment.period` field was a strict `Literal` enum. The LLM occasionally produced `"late morning"` as a period value, which caused a schema validation error on Groq's side and returned an empty itinerary.

**Fix:** Added `"late morning"` to the `Literal` type in `src/schemas.py` and to the prompt's period list. The frontend's `periodIcon()` function was also updated with a matching Material Symbols icon.

### 4. Windows cp1252 Unicode Encoding Error in CLI

**Problem:** Running `app.py` on Windows caused `UnicodeEncodeError: 'charmap' codec can't encode characters` because the CLI uses box-drawing characters (─, ═), checkmarks (✓), and currency symbols (¥) that aren't representable in Windows' default cp1252 console encoding.

**Fix:** Added `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` at the top of `app.py`. This is a no-op on macOS/Linux (which default to UTF-8) and switches Windows PowerShell to UTF-8 output.

### 5. Budget Validator 5% Tolerance False Positives

**Problem:** The budget validator flagged outputs as invalid when the LLM rounded category amounts, because the sum of rounded integers didn't exactly match the `daily_budget_local` field.

**Fix:** The validator uses a 5% tolerance (`abs(daily_sum - daily_claimed) > daily_claimed * 0.05`) rather than requiring exact equality. This allows for reasonable rounding while still catching genuinely wrong breakdowns.

---

## Section 5: Lessons Learned

### What worked well: Deterministic Supervisor + Validation Loop

The decision to make the Supervisor pure Python rather than an LLM was the right call. The routing logic is fast, predictable, and debuggable — the logs show exactly why each routing decision was made. When an agent produces bad output, the feedback injected on retry is precise (e.g. "Day 4 afternoon has a generic location: 'the area'") and the agent almost always fixes it on the first retry.

An LLM-based supervisor would have been slower, more expensive, and harder to debug. The validation logic is also easy to extend — adding a new check to `validate_itinerary` is a one-line code change.

### Tradeoff: Deterministic Routing vs LLM Routing

Deterministic routing requires encoding domain knowledge upfront (what fields must exist, what ranges are valid). This is a real maintenance cost. An LLM supervisor could potentially catch subtler issues (e.g. "the restaurant recommended doesn't exist") but would be inconsistent and expensive to run on every step. For a structured planning pipeline with known output shapes, deterministic validation is the right choice.

### MemorySaver vs External Checkpointer in Production

`MemorySaver` stores all state in RAM, which is fine for development and single-server deployments. For production with multiple server instances, you'd need a shared external checkpointer (Redis, PostgreSQL via `langgraph-checkpoint-postgres`, etc.). The thread-ID-keyed interface is the same regardless of checkpointer, so the migration would be a one-line change.

### What I'd do differently

- **Parallel agent execution:** Destination, Weather, and Budget are independent — they could run in parallel using LangGraph's fan-out/fan-in pattern, cutting total planning time by ~60%.
- **Streaming LLM output:** Groq supports streaming. Batching the itinerary in parallel and streaming each batch would feel much more responsive in the UI.
- **Richer output validators:** The current validators catch structural issues but not semantic ones (e.g. a restaurant that doesn't exist, or a temple that's in the wrong city). A second-pass LLM validator for the itinerary could catch these.
- **Persistent sessions:** The in-memory session store (`web/sessions.py`) loses all trip data on server restart. A Redis or SQLite backend would make the Trip Brief URLs permanent.
