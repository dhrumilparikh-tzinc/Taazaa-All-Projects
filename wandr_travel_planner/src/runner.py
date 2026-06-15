"""
runner.py — graph execution wrapper that emits progress events.

Usage:
    from src.runner import run_with_progress

    for event in run_with_progress(initial_state, trip_id="abc123"):
        print(event)           # dict with "type" key
        if event["type"] == "plan_complete":
            final_state = event["final_state"]
            break
"""
from __future__ import annotations

import time
from collections.abc import Generator
from typing import Any

from .graph import travel_graph
from .logger import get_logger
from .state import AgentState

log = get_logger("supervisor")


def run_with_progress(
    initial_state: AgentState, trip_id: str
) -> Generator[dict[str, Any], None, None]:
    """
    Run the travel planning graph and yield progress events.

    Each yield is a dict with at minimum a 'type' key.
    The final yield has type='plan_complete' and contains the full final_state.
    """
    config = {"configurable": {"thread_id": trip_id}}
    start_ms = time.time()

    # Track which agents have started so we can emit started/completed events.
    # LangGraph doesn't give us per-step streaming in sync mode without
    # using .stream() — we use that here.
    previous_agents_done: set[str] = set()
    previous_retry_counts: dict[str, int] = {}
    previous_statuses: dict[str, str] = {}

    try:
        for step in travel_graph.stream(initial_state, config=config, stream_mode="values"):
            last = step.get("last_agent")
            retry_counts = step.get("retry_count") or {}
            v_status = step.get("validation_status") or {}

            if last is None:
                continue

            cur_retries = retry_counts.get(last, 0)
            prev_retries = previous_retry_counts.get(last, 0)
            cur_status = v_status.get(last, "pending")
            prev_status = previous_statuses.get(last, "pending")

            # Has this agent just been dispatched for the first time?
            if last not in previous_agents_done and cur_retries == 0:
                yield {"type": "agent_started", "agent": last, "attempt": 1}
                log.info("EVENT agent_started: %s", last)

            # Has it been retried?
            if cur_retries > prev_retries:
                feedback = (step.get("validation_feedback") or {}).get(last, "")
                yield {
                    "type": "agent_retried",
                    "agent": last,
                    "attempt": cur_retries + 1,
                    "feedback": feedback,
                }
                log.info("EVENT agent_retried: %s attempt=%d", last, cur_retries + 1)

            # Has it just completed (valid or invalid_accepted)?
            if cur_status in ("valid", "invalid_accepted") and prev_status not in ("valid", "invalid_accepted"):
                summary = _summarise_agent_output(last, step)
                yield {
                    "type": "agent_completed",
                    "agent": last,
                    "status": cur_status,
                    "summary": summary,
                }
                previous_agents_done.add(last)
                log.info("EVENT agent_completed: %s status=%s", last, cur_status)

            previous_retry_counts = dict(retry_counts)
            previous_statuses = dict(v_status)

        # All steps consumed — graph has ended.
        elapsed = int((time.time() - start_ms) * 1000)
        # Get the final state from the checkpointer
        final_state = travel_graph.get_state(config).values
        yield {
            "type": "plan_complete",
            "trip_id": trip_id,
            "duration_ms": elapsed,
            "final_state": dict(final_state),
        }
        log.info("EVENT plan_complete: trip_id=%s elapsed=%dms", trip_id, elapsed)

    except Exception as e:  # noqa: BLE001
        log.error("Graph execution failed: %s", e, exc_info=True)
        yield {
            "type": "plan_error",
            "trip_id": trip_id,
            "error": str(e),
        }


def _summarise_agent_output(agent: str, state: dict) -> str:
    """One-line summary of what the agent produced, for the UI progress list."""
    if agent == "destination":
        info = state.get("destination_info") or {}
        return f"{info.get('country_name', 'Unknown')} — {info.get('capital', '')}"
    if agent == "weather":
        wd = state.get("weather_data") or {}
        days = wd.get("daily_forecast", [])
        if days:
            avg = sum(d["temp_max_c"] for d in days) / len(days)
            return f"{len(days)}-day forecast, avg high {avg:.0f}°C"
        return "Forecast loaded"
    if agent == "budget":
        bd = state.get("budget_breakdown") or {}
        return (
            f"{bd.get('total_budget_local', 0):.0f} {bd.get('total_budget_local_currency', '')} "
            f"over {bd.get('duration_days', 0)} days"
        )
    if agent == "itinerary":
        itin = state.get("itinerary") or {}
        return f"{len(itin.get('days', []))} days planned"
    if agent == "packing":
        pl = state.get("packing_list") or {}
        cats = pl.get("categories", [])
        total_items = sum(len(c.get("items", [])) for c in cats)
        return f"{total_items} items across {len(cats)} categories"
    return "Completed"
