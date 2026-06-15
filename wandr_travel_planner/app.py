#!/usr/bin/env python3
"""
Wandr — AI Travel Planner
Command-line interface

Usage:
    python app.py "Plan a 5-day trip to Tokyo in October, 80000 yen, temples and food"

Or run without arguments to be prompted interactively.
"""
from __future__ import annotations

import sys
import textwrap
import uuid
from dotenv import load_dotenv

# Ensure UTF-8 output on Windows (handles box-drawing and emoji chars)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()  # Must be before any src imports so GEMINI_API_KEY is set

from src.guardrails import REFUSAL_MESSAGE, check_input_is_travel_related
from src.logger import get_logger
from src.parser import parse_query
from src.runner import run_with_progress
from src.state import empty_state

log = get_logger("supervisor")

LINE = "─" * 66


def _hr(title: str = "") -> str:
    if title:
        pad = max(0, (66 - len(title) - 2) // 2)
        return f"\n{'─' * pad} {title} {'─' * pad}\n"
    return f"\n{LINE}\n"


def _wrap(text: str, indent: int = 2) -> str:
    prefix = " " * indent
    return textwrap.fill(text or "", width=66, initial_indent=prefix, subsequent_indent=prefix)


def _section_header(n: int, title: str) -> None:
    print(f"\n{'═' * 66}")
    print(f"  {n}. {title.upper()}")
    print(f"{'═' * 66}")


def render_destination(info: dict) -> None:
    _section_header(1, "Destination Overview")
    print(f"\n  Country      : {info.get('country_name')} {info.get('flag', '')}")
    print(f"  Official name: {info.get('official_name', '')}")
    print(f"  Capital      : {info.get('capital', '')}")
    print(f"  Currency     : {info.get('currency_code')} — {info.get('currency_name')} ({info.get('currency_symbol', '')})")
    langs = ", ".join(info.get("languages") or [])
    print(f"  Languages    : {langs}")
    print(f"  Timezone     : {info.get('timezone', '')}")
    print(f"  Region       : {info.get('region', '')}, {info.get('subregion', '')}")
    p1 = info.get("overview_paragraph_1", "")
    p2 = info.get("overview_paragraph_2", "")
    if p1 or p2:
        print()
        if p1:
            print(_wrap(p1))
        if p2:
            print(_wrap(p2))


def render_weather(wd: dict) -> None:
    _section_header(2, "7-Day Weather Forecast")
    city = wd.get("city", "")
    tz = wd.get("timezone", "")
    print(f"\n  {city}  ({tz})\n")
    print(f"  {'Date':<12} {'Max°C':>6} {'Min°C':>6} {'Precip mm':>9} {'Wind km/h':>9}")
    print(f"  {'─'*12} {'─'*6} {'─'*6} {'─'*9} {'─'*9}")
    for d in wd.get("daily_forecast", []):
        print(
            f"  {d['date']:<12} {d['temp_max_c']:>6.1f} {d['temp_min_c']:>6.1f} "
            f"{d['precipitation_mm']:>9.1f} {d['wind_max_kmh']:>9.1f}"
        )


def render_budget(bd: dict) -> None:
    _section_header(3, "Budget Breakdown")
    print(f"\n  Original budget : {bd.get('total_budget_native', 0):,.0f} {bd.get('total_budget_native_currency', '')}")
    print(f"  Local currency  : {bd.get('total_budget_local', 0):,.0f} {bd.get('total_budget_local_currency', '')}")
    print(f"  Exchange rate   : 1 {bd.get('total_budget_native_currency', '')} = {bd.get('exchange_rate_used', 0):.4f} {bd.get('total_budget_local_currency', '')}")
    print(f"  Trip duration   : {bd.get('duration_days', 0)} days")
    print(f"  Daily budget    : {bd.get('daily_budget_local', 0):,.0f} {bd.get('total_budget_local_currency', '')}")
    print()
    print(f"  {'Category':<18} {'Daily':>10}  Description")
    print(f"  {'─'*18} {'─'*10}  {'─'*28}")
    for cat in bd.get("categories", []):
        print(
            f"  {cat.get('name', ''):18} {cat.get('daily_amount', 0):>10,.0f}  {cat.get('description', '')}"
        )
    notes = bd.get("notes", "")
    if notes:
        print()
        print(_wrap(f"Note: {notes}"))


def render_itinerary(itin: dict) -> None:
    """Print the detailed day-by-day itinerary to stdout."""
    _section_header(4, "Day-by-Day Itinerary")
    summary = itin.get("summary", "")
    if summary:
        print()
        print(_wrap(summary))
    print()
    for day in itin.get("days", []):
        highlights = day.get("highlights") or []
        hl_str = "  |  ".join(highlights[:3]) if highlights else ""
        print(f"  Day {day['day']:>2}  {day.get('theme', '').upper()}")
        if hl_str:
            print(f"  {_wrap(hl_str, indent=4)}")
        for seg in day.get("segments", []):
            time_str = seg.get("time", "")
            period = seg.get("period", "").capitalize()
            activity = seg.get("activity", "")
            location = seg.get("location", "")
            description = seg.get("description", "")
            tips = seg.get("tips", "")
            cost = seg.get("cost_note", "")
            time_label = f" {time_str}" if time_str else ""
            cost_label = f"  [{cost}]" if cost else ""
            print(f"    [{period}{time_label}]{cost_label}")
            print(f"      {activity} @ {location}")
            if description:
                print(_wrap(description, indent=6))
            if tips:
                print(_wrap(f"Tip: {tips}", indent=6))
        transport = day.get("transport_note", "")
        if transport:
            print(f"    Getting around: {transport}")
        print()


def render_packing(pl: dict) -> None:
    _section_header(5, "Packing List")
    print(f"\n  Destination  : {pl.get('destination', '')}")
    print(f"  Duration     : {pl.get('duration_days', 0)} days")
    ws = pl.get("weather_summary", "")
    if ws:
        print(f"  Weather      : {ws}")
    print()
    for cat in pl.get("categories", []):
        print(f"  {cat.get('category', '').upper()}")
        for item in cat.get("items", []):
            print(f"    • {item}")
        print()


def main() -> int:
    # 1. Get query
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    else:
        print("Wandr — AI Travel Planner")
        print(LINE)
        query = input("Where would you like to go? ").strip()
        if not query:
            print("No query provided. Exiting.")
            return 1

    print(f"\n{LINE}")
    print(f"  Query received: {query[:70]}{'...' if len(query) > 70 else ''}")
    print(LINE)

    # 2. Input guardrail
    print("\n▶ Checking query...")
    classification = check_input_is_travel_related(query)
    if not classification.is_travel_request:
        print()
        print(f"  {REFUSAL_MESSAGE}")
        print()
        return 1

    # 3. Parse query
    print("▶ Parsing travel intent...")
    parsed = parse_query(query)

    print("\n  Extracted details:")
    print(f"    City       : {parsed.destination_city}")
    print(f"    Country    : {parsed.destination_country or '(will infer)'}")
    print(f"    Duration   : {parsed.trip_duration_days} days")
    if parsed.budget_amount:
        print(f"    Budget     : {parsed.budget_amount:,} {parsed.budget_currency or ''}")
    if parsed.travel_month:
        print(f"    Month      : {parsed.travel_month}")
    if parsed.interests:
        print(f"    Interests  : {', '.join(parsed.interests)}")

    # 4. Human-in-loop confirmation (FR-15)
    print()
    confirm = input("  Does this look right? (y/n) ").strip().lower()
    if confirm not in ("y", "yes", ""):
        print("  Cancelled. Please re-run with a clearer query.")
        return 0

    # 5. Build initial state
    state = empty_state(query)
    state.update(parsed.model_dump())

    # 6. Run the graph with live progress
    print(f"\n{'━' * 66}")
    print("  PLANNING YOUR TRIP")
    print(f"{'━' * 66}\n")

    trip_id = str(uuid.uuid4())[:8]
    final_state: dict | None = None

    _agent_labels = {
        "destination": "Destination & Overview",
        "weather": "Weather Forecast",
        "budget": "Budget Breakdown",
        "itinerary": "Day-by-Day Itinerary",
        "packing": "Packing List",
    }

    for event in run_with_progress(state, trip_id=trip_id):
        t = event.get("type")
        agent = event.get("agent", "")
        label = _agent_labels.get(agent, agent)

        if t == "agent_started":
            print(f"  [ ] {label}...", end="", flush=True)
        elif t == "agent_retried":
            print(f"\r  ↻  {label} retrying (attempt #{event['attempt']})...", end="", flush=True)
        elif t == "agent_completed":
            status_icon = "✓" if event.get("status") == "valid" else "⚠"
            print(f"\r  {status_icon}  {label:<30}  {event.get('summary', '')}")
        elif t == "agent_failed":
            print(f"\r  ✗  {label}")
        elif t == "plan_complete":
            final_state = event.get("final_state")
        elif t == "plan_error":
            print(f"\n  ERROR: {event.get('error')}")
            return 1

    if not final_state:
        print("\n  Planning failed — no final state received.")
        return 1

    # 7. Render the plan
    dest_info = final_state.get("destination_info") or {}
    weather_data = final_state.get("weather_data") or {}
    budget_data = final_state.get("budget_breakdown") or {}
    itinerary_data = final_state.get("itinerary") or {}
    packing_data = final_state.get("packing_list") or {}

    if not any([dest_info, weather_data, budget_data, itinerary_data, packing_data]):
        print("\n  No output sections were produced. Check logs for errors.")
        return 1

    print(f"\n{'═' * 66}")
    print(f"  WANDR TRAVEL PLAN  —  Trip ID: {trip_id}")
    print(f"{'═' * 66}")

    if dest_info and "error" not in dest_info:
        render_destination(dest_info)
    else:
        print("\n  (Destination overview unavailable)")

    if weather_data and "error" not in weather_data:
        render_weather(weather_data)
    else:
        print("\n  (Weather forecast unavailable)")

    if budget_data and "error" not in budget_data:
        render_budget(budget_data)
    else:
        print("\n  (Budget breakdown unavailable)")

    if itinerary_data and "error" not in itinerary_data:
        render_itinerary(itinerary_data)
    else:
        print("\n  (Itinerary unavailable)")

    if packing_data and "error" not in packing_data:
        render_packing(packing_data)
    else:
        print("\n  (Packing list unavailable)")

    print(f"\n{'═' * 66}")
    print("  Plan complete. Logs saved to logs/master.log")
    print(f"{'═' * 66}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
