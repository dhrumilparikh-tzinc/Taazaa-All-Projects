"""
The shared graph state.

Every agent reads from this dict and writes into it. The supervisor uses
the `validation_status` and `retry_count` fields to drive its routing
decisions, which is what implements the "agent runs -> supervisor verifies
-> retry or move on" loop.
"""
from __future__ import annotations

from typing import Any, Optional, TypedDict


AGENT_ORDER = ["destination", "weather", "budget", "itinerary", "packing"]


class AgentState(TypedDict, total=False):
    # ---- input ----
    user_query: str

    # ---- parsed query (filled before the graph runs) ----
    destination_city: Optional[str]
    destination_country: Optional[str]
    trip_duration_days: Optional[int]
    budget_amount: Optional[float]
    budget_currency: Optional[str]
    interests: list[str]
    travel_month: Optional[str]

    # ---- per-agent outputs ----
    destination_info: Optional[dict[str, Any]]
    weather_data: Optional[dict[str, Any]]
    budget_breakdown: Optional[dict[str, Any]]
    itinerary: Optional[dict[str, Any]]
    packing_list: Optional[dict[str, Any]]

    # ---- supervisor bookkeeping ----
    validation_status: dict[str, str]    # agent_name -> "pending" | "valid" | "invalid_accepted"
    retry_count: dict[str, int]          # agent_name -> attempts so far
    validation_feedback: dict[str, str]  # agent_name -> last feedback for retry
    last_agent: Optional[str]            # which worker just ran
    next_agent: Optional[str]            # supervisor's routing decision

    # ---- guardrail outcome ----
    input_allowed: Optional[bool]
    input_rejection_reason: Optional[str]

    # ---- final rendered output ----
    final_plan: Optional[str]
    error: Optional[str]


def empty_state(user_query: str) -> AgentState:
    """Factory for a fresh state object."""
    return AgentState(
        user_query=user_query,
        interests=[],
        validation_status={a: "pending" for a in AGENT_ORDER},
        retry_count={a: 0 for a in AGENT_ORDER},
        validation_feedback={a: "" for a in AGENT_ORDER},
    )
