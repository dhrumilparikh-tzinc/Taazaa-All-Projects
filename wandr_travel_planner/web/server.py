"""
Wandr FastAPI server.

REST API (single endpoint):
  POST /api/trip  → send a natural-language query; receive the full trip plan
  GET  /health    → health check

Web UI (browser):
  GET  /                          → landing page
  GET  /confirm                   → confirm page
  GET  /planning?id=<trip_id>     → real-time planning page
  GET  /brief/<trip_id>           → final trip brief

  POST /api/parse                 → guardrail + parser (used by the web UI)
  POST /api/plan                  → start background graph (used by the web UI)
  GET  /api/plan/<trip_id>/stream → SSE progress stream (used by the web UI)
  GET  /api/plan/<trip_id>/result → final result (used by the web UI)

Run with:
    uvicorn web.server:app --reload
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from src.guardrails import REFUSAL_MESSAGE, check_input_is_travel_related
from src.logger import get_logger
from src.parser import parse_query
from src.runner import run_with_progress
from src.state import empty_state

import web.sessions as sessions

log = get_logger("web")

# ---- App setup ----
app = FastAPI(title="Wandr — AI Travel Planner", version="1.0.0")

# Static files and templates
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(_BASE_DIR, "templates"))
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(_BASE_DIR, "static")),
    name="static",
)

# Thread pool for running the sync graph in background
_executor = ThreadPoolExecutor(max_workers=4)


# ---- Pydantic request/response models ----

class ParseRequest(BaseModel):
    query: str


class ParseResponse(BaseModel):
    destination_city: str
    destination_country: str | None
    trip_duration_days: int
    budget_amount: float | None
    budget_currency: str | None
    interests: list[str]
    travel_month: str | None


class PlanRequest(BaseModel):
    """Confirmed trip parameters from the Confirm screen."""
    destination_city: str
    destination_country: str | None = None
    trip_duration_days: int
    budget_amount: float | None = None
    budget_currency: str | None = None
    interests: list[str] = []
    travel_month: str | None = None
    original_query: str = ""


class PlanResponse(BaseModel):
    trip_id: str


class TripRequest(BaseModel):
    """Single-call API request — natural-language query only."""
    query: str


class TripPlan(BaseModel):
    """Complete trip plan returned once all agents have finished."""
    trip_id: str
    query: str
    destination_city: str
    destination_country: str | None
    trip_duration_days: int
    budget_amount: float | None
    budget_currency: str | None
    interests: list[str]
    travel_month: str | None
    destination_info: dict | None
    weather_data: dict | None
    budget_breakdown: dict | None
    itinerary: dict | None
    packing_list: dict | None


# ---- Page routes ----

@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    log.info("GET /")
    return templates.TemplateResponse(request, "landing.html")


@app.get("/confirm", response_class=HTMLResponse)
async def confirm(request: Request):
    log.info("GET /confirm")
    return templates.TemplateResponse(request, "confirm.html")


@app.get("/planning", response_class=HTMLResponse)
async def planning(request: Request):
    trip_id = request.query_params.get("id", "")
    log.info("GET /planning?id=%s", trip_id)
    return templates.TemplateResponse(request, "planning.html", {"trip_id": trip_id})


@app.get("/brief/{trip_id}", response_class=HTMLResponse)
async def brief(request: Request, trip_id: str):
    log.info("GET /brief/%s", trip_id)
    session = sessions.get_session(trip_id)
    if not session or not session.is_complete:
        raise HTTPException(status_code=404, detail="Trip not found or not yet complete.")
    return templates.TemplateResponse(request, "brief.html", {"trip_id": trip_id})


# ---- API routes ----

@app.post("/api/parse", response_model=ParseResponse)
async def api_parse(body: ParseRequest):
    """Run guardrail + parser. Returns structured ParsedQuery or 403."""
    query = body.query.strip()
    log.info("POST /api/parse query_len=%d", len(query))

    # Guardrail
    loop = asyncio.get_event_loop()
    classification = await loop.run_in_executor(
        _executor, check_input_is_travel_related, query
    )
    if not classification.is_travel_request:
        log.warning("Input rejected: %s", classification.reason)
        raise HTTPException(
            status_code=403,
            detail={"message": REFUSAL_MESSAGE, "reason": classification.reason},
        )

    # Parse
    parsed = await loop.run_in_executor(_executor, parse_query, query)
    log.info("Parsed: city=%s days=%s", parsed.destination_city, parsed.trip_duration_days)
    return ParseResponse(**parsed.model_dump())


@app.post("/api/plan", response_model=PlanResponse)
async def api_plan(body: PlanRequest):
    """Start the graph in the background. Returns trip_id immediately."""
    trip_id = str(uuid.uuid4())
    log.info("POST /api/plan -> trip_id=%s", trip_id)

    state = empty_state(body.original_query or "")
    state["destination_city"] = body.destination_city
    state["destination_country"] = body.destination_country
    state["trip_duration_days"] = body.trip_duration_days
    state["budget_amount"] = body.budget_amount
    state["budget_currency"] = body.budget_currency
    state["interests"] = body.interests or []
    state["travel_month"] = body.travel_month

    sessions.create_session(trip_id, initial_state=dict(state))

    # Start background task
    asyncio.get_event_loop().run_in_executor(
        _executor, _run_graph_background, trip_id, dict(state)
    )

    return PlanResponse(trip_id=trip_id)


@app.post("/api/trip", response_model=TripPlan)
async def api_trip(body: TripRequest):
    """
    Single-call endpoint: send a natural-language travel query, receive the
    complete trip plan once all agents have finished.

    Flow (fully synchronous from the caller's perspective):
      1. Guardrail — rejects non-travel / harmful queries with 403
      2. Parser  — extracts city, duration, budget, interests, month
      3. Agents  — destination → weather → budget → itinerary → packing
      4. Returns the full plan in one response (no polling required)

    Typical response time: 30–90 seconds depending on trip length.
    """
    query = body.query.strip()
    log.info("POST /api/trip query_len=%d", len(query))

    loop = asyncio.get_event_loop()

    # 1 — guardrail
    classification = await loop.run_in_executor(
        _executor, check_input_is_travel_related, query
    )
    if not classification.is_travel_request:
        log.warning("Input rejected: %s", classification.reason)
        raise HTTPException(
            status_code=403,
            detail={"message": REFUSAL_MESSAGE, "reason": classification.reason},
        )

    # 2 — parse
    parsed = await loop.run_in_executor(_executor, parse_query, query)
    log.info("Parsed: city=%s days=%s", parsed.destination_city, parsed.trip_duration_days)

    # 3 — build initial state
    trip_id = str(uuid.uuid4())
    state = empty_state(query)
    state["destination_city"] = parsed.destination_city
    state["destination_country"] = parsed.destination_country
    state["trip_duration_days"] = parsed.trip_duration_days
    state["budget_amount"] = parsed.budget_amount
    state["budget_currency"] = parsed.budget_currency
    state["interests"] = parsed.interests or []
    state["travel_month"] = parsed.travel_month

    # 4 — run all agents synchronously; block until plan_complete
    from src.state import AgentState
    agent_state = AgentState(**state)
    try:
        final = await loop.run_in_executor(
            _executor, _run_graph_sync, agent_state, trip_id
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return TripPlan(
        trip_id=trip_id,
        query=query,
        destination_city=final.get("destination_city") or parsed.destination_city,
        destination_country=final.get("destination_country") or parsed.destination_country,
        trip_duration_days=final.get("trip_duration_days") or parsed.trip_duration_days,
        budget_amount=final.get("budget_amount") or parsed.budget_amount,
        budget_currency=final.get("budget_currency") or parsed.budget_currency,
        interests=final.get("interests") or parsed.interests,
        travel_month=final.get("travel_month") or parsed.travel_month,
        destination_info=final.get("destination_info"),
        weather_data=final.get("weather_data"),
        budget_breakdown=final.get("budget_breakdown"),
        itinerary=final.get("itinerary"),
        packing_list=final.get("packing_list"),
    )


def _run_graph_sync(state: "AgentState", trip_id: str) -> dict:
    """Run the agent graph to completion; return the final state dict."""
    for event in run_with_progress(state, trip_id=trip_id):
        if event["type"] == "plan_complete":
            return event["final_state"]
        if event["type"] == "plan_error":
            raise RuntimeError(event.get("error", "Planning failed"))
    raise RuntimeError("Graph ended without a plan_complete event")


def _run_graph_background(trip_id: str, state: dict) -> None:
    """Blocking function that runs the graph and pushes events to the session."""
    log.info("Background graph run starting: trip_id=%s", trip_id)
    try:
        from src.state import AgentState
        agent_state = AgentState(**state)
        for event in run_with_progress(agent_state, trip_id=trip_id):
            sessions.push_event(trip_id, event)
            if event.get("type") == "plan_complete":
                sessions.mark_complete(trip_id, event.get("final_state") or {})
                break
            elif event.get("type") == "plan_error":
                sessions.mark_error(trip_id, event.get("error", "Unknown error"))
                break
    except Exception as e:  # noqa: BLE001
        log.error("Background graph run crashed: %s", e, exc_info=True)
        sessions.mark_error(trip_id, str(e))


@app.get("/api/plan/{trip_id}/stream")
async def api_stream(request: Request, trip_id: str):
    """
    SSE endpoint. Streams events from the session's queue until plan_complete
    or plan_error.
    """
    session = sessions.get_session(trip_id)
    if not session:
        raise HTTPException(status_code=404, detail="Trip not found.")
    log.info("SSE connected: trip_id=%s", trip_id)

    async def event_generator():
        while True:
            if await request.is_disconnected():
                log.info("SSE client disconnected: %s", trip_id)
                break
            try:
                event = session.event_queue.get_nowait()
                if event.get("type") == "__done__":
                    break
                data = json.dumps(event)
                yield {"data": data}
                log.debug("SSE event sent: %s -> %s", trip_id, event.get("type"))
            except Exception:  # noqa: BLE001
                # Queue empty — wait and try again
                await asyncio.sleep(0.2)

    return EventSourceResponse(event_generator())


@app.get("/api/plan/{trip_id}/result")
async def api_result(trip_id: str) -> dict[str, Any]:
    """Return the full final state once planning is complete."""
    session = sessions.get_session(trip_id)
    if not session:
        raise HTTPException(status_code=404, detail="Trip not found.")
    if not session.is_complete:
        raise HTTPException(status_code=202, detail="Planning not yet complete.")
    if session.error:
        raise HTTPException(status_code=500, detail=session.error)
    if not session.final_state:
        raise HTTPException(status_code=500, detail="No final state available.")
    return session.final_state


# ---- Health check ----

@app.get("/health")
async def health():
    return {"status": "ok"}
