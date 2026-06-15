"""
Supervisor routing function for the LangGraph graph.

The supervisor is code, not an LLM. It:
  1. Reads which agent last ran (state["last_agent"])
  2. Validates that agent's output via guardrails.validate_agent_output()
  3. Decides: "valid → next agent" | "retry → same agent" | "cap hit → accept & continue" | "all done → END"

Every routing decision is logged via log_state_transition().
"""
from __future__ import annotations

import os

from langgraph.graph import END

from .guardrails import validate_agent_output
from .logger import get_logger, log_state_transition
from .state import AGENT_ORDER, AgentState

log = get_logger("supervisor")

MAX_RETRIES = int(os.getenv("MAX_AGENT_RETRIES", "2"))


def supervisor_route(state: AgentState) -> str:
    """
    Determine which node to run next.

    Returns the name of the next node (string matching a node name in the
    graph) or the special sentinel END from langgraph.graph.
    """
    last = state.get("last_agent")
    v_status = state.get("validation_status") or {}
    r_count = state.get("retry_count") or {}

    # ---- FIRST PASS: no agent has run yet ----
    if last is None:
        next_agent = _first_pending(v_status)
        log_state_transition("START", next_agent or "END", "first dispatch")
        return next_agent or END

    # ---- VALIDATE last agent's output ----
    log.info("Validating output from '%s'", last)
    result = validate_agent_output(last, state)

    if result.is_valid:
        new_status = {**v_status, last: "valid"}
        # Mutate in place — supervisor is a routing function so it can't
        # return state updates.  We update the mutable dicts directly.
        v_status.update(new_status)
        log.info("'%s' output is VALID.", last)
        next_agent = _first_pending(v_status)
        if next_agent:
            log_state_transition(last, next_agent, "valid → next")
            return next_agent
        else:
            log_state_transition(last, "END", "all agents valid")
            return END

    else:
        # ---- Output was invalid ----
        current_retries = r_count.get(last, 0)
        log.warning(
            "'%s' output INVALID (attempt %d/%d). Issues: %s",
            last, current_retries + 1, MAX_RETRIES + 1, result.issues,
        )
        if current_retries < MAX_RETRIES:
            # Retry: increment counter and inject feedback
            r_count[last] = current_retries + 1
            feedback = state.get("validation_feedback") or {}
            feedback[last] = result.feedback_for_agent
            log_state_transition(
                last, last,
                f"retry {current_retries + 1}/{MAX_RETRIES}: {result.feedback_for_agent[:60]}"
            )
            return last
        else:
            # Cap hit: accept what we have and move on
            log.error(
                "'%s' hit retry cap after %d attempts — accepting invalid output and continuing.",
                last, MAX_RETRIES + 1,
            )
            v_status[last] = "invalid_accepted"
            next_agent = _first_pending(v_status)
            if next_agent:
                log_state_transition(last, next_agent, "cap hit → accept & continue")
                return next_agent
            else:
                log_state_transition(last, "END", "cap hit, all done")
                return END


def _first_pending(v_status: dict) -> str | None:
    """Return the first agent in AGENT_ORDER whose status is 'pending'."""
    for agent in AGENT_ORDER:
        if (v_status.get(agent) or "pending") == "pending":
            return agent
    return None
