"""
End-to-end graph tests. These run the full pipeline and check that all
five output sections are present.

Run with: python tests/test_graph.py
"""
import sys
from dotenv import load_dotenv
load_dotenv()

from src.parser import parse_query
from src.state import empty_state
from src.runner import run_with_progress

QUERIES = [
    {
        "label": "Tokyo 5 days ¥80k",
        "query": "Plan a 5-day trip to Tokyo in October, ¥80,000 budget, I like temples and street food",
    },
    {
        "label": "Paris weekend €400",
        "query": "Weekend trip to Paris, budget €400, I love museums and pastries",
    },
    {
        "label": "Reykjavik 7 days $3k",
        "query": "7-day adventure trip to Reykjavik, $3,000 budget, hiking and hot springs",
    },
]

REQUIRED_STATE_KEYS = [
    "destination_info",
    "weather_data",
    "budget_breakdown",
    "itinerary",
    "packing_list",
]


def run_test(query_spec: dict) -> bool:
    label = query_spec["label"]
    raw = query_spec["query"]
    print(f"\n{'='*60}")
    print(f"TEST: {label}")
    print(f"Query: {raw}")
    print("=" * 60)

    # Parse
    parsed = parse_query(raw)
    state = empty_state(raw)
    state.update(parsed.model_dump())

    trip_id = label.replace(" ", "_").lower()
    final_state = None

    for event in run_with_progress(state, trip_id=trip_id):
        print(f"  [{event['type']}]", end="")
        if event["type"] == "agent_started":
            print(f" {event['agent']}", end="")
        elif event["type"] == "agent_completed":
            print(f" {event['agent']} ({event['status']}) — {event['summary']}", end="")
        elif event["type"] == "agent_retried":
            print(f" {event['agent']} attempt #{event['attempt']} — {event['feedback'][:80]}", end="")
        elif event["type"] == "plan_complete":
            print(f" {event['duration_ms']}ms", end="")
            final_state = event["final_state"]
        elif event["type"] == "plan_error":
            print(f" ERROR: {event['error']}", end="")
            return False
        print()

    if not final_state:
        print("FAIL: no final state received.")
        return False

    # Check all five sections
    passed = True
    for key in REQUIRED_STATE_KEYS:
        val = final_state.get(key)
        if val and (not isinstance(val, dict) or "error" not in val):
            print(f"  ✓ {key}")
        else:
            print(f"  ✗ {key}: {'missing' if not val else val.get('error', '?')}")
            passed = False

    # Print summary for the report
    if passed:
        bd = final_state.get("budget_breakdown") or {}
        print(f"\n  Budget: {bd.get('total_budget_local', 0):.0f} {bd.get('total_budget_local_currency', '')}")
        itin = final_state.get("itinerary") or {}
        print(f"  Itinerary days: {len(itin.get('days', []))}")
        pl = final_state.get("packing_list") or {}
        cats = pl.get("categories", [])
        print(f"  Packing categories: {[c['category'] for c in cats]}")

    return passed


if __name__ == "__main__":
    results = [run_test(q) for q in QUERIES]
    print(f"\n{'='*60}")
    print(f"Results: {sum(results)}/{len(results)} passed")
    if not all(results):
        sys.exit(1)
