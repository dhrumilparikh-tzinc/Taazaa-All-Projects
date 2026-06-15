"""
LangGraph StateGraph for the travel planner.

Topology:
  __start__ -> supervisor -> destination -> supervisor -> weather ->
  supervisor -> budget -> supervisor -> itinerary -> supervisor ->
  packing -> supervisor -> __end__

The supervisor handles both routing AND the validation loop. Each worker
runs, returns to the supervisor, which validates and either retries or
dispatches to the next worker.
"""
from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from .agents.budget import budget_agent
from .agents.destination import destination_agent
from .agents.itinerary import itinerary_agent
from .agents.packing import packing_agent
from .agents.weather import weather_agent
from .logger import get_logger
from .state import AGENT_ORDER, AgentState
from .supervisor import supervisor_route

log = get_logger("supervisor")

# ---- Worker node wrappers ----
# We need to satisfy LangGraph's requirement that nodes are callables
# returning a dict. The agents already do this.

_AGENT_NODES: dict[str, callable] = {
    "destination": destination_agent,
    "weather": weather_agent,
    "budget": budget_agent,
    "itinerary": itinerary_agent,
    "packing": packing_agent,
}


def build_graph() -> tuple[object, MemorySaver]:
    """Construct and compile the StateGraph. Returns (compiled_graph, checkpointer)."""
    checkpointer = MemorySaver()
    builder = StateGraph(AgentState)

    # ---- Add the supervisor node ----
    # The supervisor node is a no-op node — it is the routing function itself.
    # We add it as a proper node that just passes state through, because
    # the conditional_edges must be attached to a node.
    def supervisor_node(state: AgentState) -> dict:
        """Supervisor node — does nothing to state; routing is in conditional_edges."""
        return {}

    builder.add_node("supervisor", supervisor_node)

    # ---- Add all five worker nodes ----
    for name, fn in _AGENT_NODES.items():
        builder.add_node(name, fn)

    # ---- Edges ----
    # START -> supervisor (always)
    builder.add_edge(START, "supervisor")

    # supervisor -> {destination|weather|budget|itinerary|packing|END}
    # using the routing function
    builder.add_conditional_edges(
        "supervisor",
        supervisor_route,
        {
            "destination": "destination",
            "weather": "weather",
            "budget": "budget",
            "itinerary": "itinerary",
            "packing": "packing",
            END: END,
        },
    )

    # Every worker -> supervisor (unconditional)
    for agent_name in AGENT_ORDER:
        builder.add_edge(agent_name, "supervisor")

    graph = builder.compile(checkpointer=checkpointer)
    log.info("StateGraph compiled. Nodes: %s", list(_AGENT_NODES.keys()) + ["supervisor"])
    return graph, checkpointer


# ---- Module-level singleton ----
# Build once at import time. Calling code uses this directly.
travel_graph, memory_checkpointer = build_graph()
