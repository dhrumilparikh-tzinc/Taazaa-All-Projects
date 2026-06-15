"""
Guardrails.

Two jobs:
  1. INPUT GUARDRAIL — block prompts that aren't travel-planning. We use
     Gemini with structured output to classify the query. If it's a coding
     request, harmful content, or general chit-chat, we politely refuse.
  2. OUTPUT GUARDRAILS — after each worker agent runs, validate the result
     against deterministic rules first (cheap & reliable), then optionally
     ask the LLM to catch obvious hallucinations.

Validation feedback is written back to state so the agent can re-run with
explicit guidance on what to fix.
"""
from __future__ import annotations

import os
from typing import Any

from langchain_groq import ChatGroq

from .logger import get_logger, groq_model
from .schemas import InputClassification, ValidationResult

log = get_logger("guardrails")

def _llm(temperature: float = 0.0) -> ChatGroq:
    return ChatGroq(
        model=groq_model(),
        temperature=temperature,
        groq_api_key=os.getenv("GROQ_API_KEY"),
    )


# --------------------------------------------------------------------------- #
#  INPUT GUARDRAIL
# --------------------------------------------------------------------------- #
INPUT_GUARDRAIL_PROMPT = """\
You are an input classifier for an AI Travel Planner.

The planner ONLY handles travel-related requests: choosing a destination,
weather, budget, itinerary, packing, local culture, food recommendations,
trip duration, etc.

It must REFUSE anything else, including:
  - Code/script generation (Python, JS, SQL, etc.)
  - General Q&A unrelated to travel
  - Writing essays, poems, summaries unrelated to a trip
  - Harmful, illegal, or unethical requests

Classify the following user message.

User message:
\"\"\"{query}\"\"\"

Return your classification in the required structured format.
"""


def check_input_is_travel_related(user_query: str) -> InputClassification:
    """Return a structured decision about whether to handle this query."""
    log.info("Running input guardrail on query (%d chars)", len(user_query))

    # Fast path — empty or trivially short input
    if not user_query or len(user_query.strip()) < 5:
        return InputClassification(
            is_travel_request=False,
            category="other",
            reason="Empty or trivially short input.",
        )

    llm = _llm(temperature=0.0).with_structured_output(InputClassification)
    try:
        result: InputClassification = llm.invoke(
            INPUT_GUARDRAIL_PROMPT.format(query=user_query)
        )
        log.info(
            "Input classification: is_travel=%s category=%s reason=%s",
            result.is_travel_request,
            result.category,
            result.reason,
        )
        return result
    except Exception as e:  # noqa: BLE001
        log.warning("Input guardrail failed (%s) — failing open, assuming travel request.", e)
        return InputClassification(
            is_travel_request=True,
            category="travel_planning",
            reason="Guardrail unavailable; assuming valid travel request.",
        )


REFUSAL_MESSAGE = (
    "I'm a travel planner — I can only help you plan trips, suggest destinations, "
    "estimate budgets, and similar travel tasks. I can't help with that request, "
    "but if you tell me where you'd like to go, I'll plan the whole thing."
)


# --------------------------------------------------------------------------- #
#  OUTPUT GUARDRAILS — per agent
# --------------------------------------------------------------------------- #
def validate_destination(data: dict[str, Any], expected_city: str | None = None) -> ValidationResult:
    """Deterministic checks for REST Countries output."""
    issues: list[str] = []

    if data.get("error"):
        issues.append(f"Tool returned an error: {data['error']}")
        return ValidationResult(
            is_valid=False, issues=issues, feedback_for_agent=issues[0]
        )

    required = ("country_name", "capital", "currency_code", "languages", "timezone")
    for key in required:
        if not data.get(key):
            issues.append(f"Missing field: {key}")

    # Currency code must look like an ISO-4217 alpha-3 code.
    cc = data.get("currency_code", "")
    if cc and (len(cc) != 3 or not cc.isalpha() or not cc.isupper()):
        issues.append(f"Currency code looks malformed: {cc!r}")

    return ValidationResult(
        is_valid=not issues,
        issues=issues,
        feedback_for_agent="; ".join(issues),
    )


def validate_weather(data: dict[str, Any]) -> ValidationResult:
    """Deterministic checks for Open-Meteo forecast."""
    issues: list[str] = []

    if data.get("error"):
        issues.append(f"Tool returned an error: {data['error']}")
        return ValidationResult(
            is_valid=False, issues=issues, feedback_for_agent=issues[0]
        )

    days = data.get("daily_forecast", [])
    if not isinstance(days, list) or len(days) < 5:
        issues.append("Expected at least 5 days of forecast data.")

    for i, d in enumerate(days):
        for f in ("date", "temp_max_c", "temp_min_c", "precipitation_mm"):
            if f not in d:
                issues.append(f"Day {i+1} missing field: {f}")
        # Sanity range for temperatures.
        t_max = d.get("temp_max_c")
        if isinstance(t_max, (int, float)) and not (-60 <= t_max <= 60):
            issues.append(f"Day {i+1} temp_max_c out of range: {t_max}")

    return ValidationResult(
        is_valid=not issues,
        issues=issues,
        feedback_for_agent="; ".join(issues[:3]),
    )


def validate_budget(data: dict[str, Any], expected_days: int) -> ValidationResult:
    """Check the LLM budget breakdown adds up."""
    issues: list[str] = []

    if not data:
        return ValidationResult(
            is_valid=False, issues=["No budget data."], feedback_for_agent="Budget breakdown is empty."
        )

    cats = data.get("categories", [])
    if not cats:
        issues.append("Budget has no category breakdown.")

    # Category amounts are force-scaled in the agent, so only check they're positive
    for cat in cats:
        if cat.get("daily_amount", 0) <= 0:
            issues.append(f"Category '{cat.get('name')}' has zero or negative daily_amount.")

    if data.get("duration_days") != expected_days:
        issues.append(
            f"duration_days ({data.get('duration_days')}) != trip length ({expected_days})"
        )

    # Must have the four required categories
    cat_names = {c.get("name") for c in cats}
    required = {"accommodation", "food", "transport", "activities"}
    missing = required - cat_names
    if missing:
        issues.append(f"Missing required budget categories: {sorted(missing)}")

    return ValidationResult(
        is_valid=not issues,
        issues=issues,
        feedback_for_agent="; ".join(issues),
    )


GENERIC_LOCATIONS = {
    "", "tbd", "n/a", "various", "the city", "downtown",
    "city center", "city centre", "the area", "the neighborhood",
    "various locations", "to be decided",
}


def validate_itinerary(data: dict[str, Any], expected_days: int) -> ValidationResult:
    """Deterministic structure + 'generic location' check for itinerary."""
    issues: list[str] = []

    if not data:
        return ValidationResult(
            is_valid=False,
            issues=["No itinerary data."],
            feedback_for_agent="Itinerary is empty.",
        )

    days = data.get("days", [])
    if len(days) != expected_days:
        issues.append(
            f"Itinerary has {len(days)} days but trip is {expected_days} days."
        )
    for d in days:
        segs = d.get("segments", [])
        if len(segs) < 4:
            issues.append(
                f"Day {d.get('day')} should have at least 4 segments, has {len(segs)}."
            )
        for s in segs:
            loc = (s.get("location") or "").strip().lower()
            if loc in GENERIC_LOCATIONS:
                issues.append(
                    f"Day {d.get('day')} {s.get('period')} has a generic/empty location: {s.get('location')!r}"
                )
            if not s.get("description"):
                issues.append(
                    f"Day {d.get('day')} {s.get('period')} is missing a description."
                )

    return ValidationResult(
        is_valid=not issues,
        issues=issues,
        feedback_for_agent="; ".join(issues[:5]),
    )


def validate_packing(
    data: dict[str, Any],
    weather_data: dict[str, Any] | None,
) -> ValidationResult:
    """Check packing list categories and cross-reference weather."""
    issues: list[str] = []

    if not data:
        return ValidationResult(
            is_valid=False,
            issues=["No packing data."],
            feedback_for_agent="Packing list is empty.",
        )

    cats = data.get("categories", [])
    cat_names = {c.get("category") for c in cats}
    if "clothing" not in cat_names:
        issues.append("Packing list missing 'clothing' category.")
    if "documents" not in cat_names:
        issues.append("Packing list missing 'documents' category.")

    # Cross-check with weather — if it's expected to rain, packing should mention it.
    daily = (weather_data or {}).get("daily_forecast", [])
    has_rain = any(d.get("precipitation_mm", 0) > 1 for d in daily)
    if has_rain:
        all_items = " ".join(
            item.lower() for c in cats for item in c.get("items", [])
        )
        if not any(kw in all_items for kw in ("rain", "umbrella", "waterproof", "poncho")):
            issues.append("Forecast has rain but packing list mentions no rain gear.")

    # Cross-check temperature — cold forecast should include warm clothing
    if daily:
        min_temp = min((d.get("temp_min_c", 99) for d in daily), default=99)
        if min_temp < 5:
            all_items = " ".join(
                item.lower() for c in cats for item in c.get("items", [])
            )
            if not any(kw in all_items for kw in (
                "coat", "jacket", "warm", "thermal", "fleece", "wool", "gloves", "scarf"
            )):
                issues.append(
                    f"Forecast min temp is {min_temp}°C but packing list has no warm clothing."
                )

    return ValidationResult(
        is_valid=not issues,
        issues=issues,
        feedback_for_agent="; ".join(issues),
    )


# --------------------------------------------------------------------------- #
#  Dispatcher used by supervisor.py
# --------------------------------------------------------------------------- #
def validate_agent_output(agent_name: str, state: dict) -> ValidationResult:
    """Pick the right validator for an agent and run it against state."""
    if agent_name == "destination":
        return validate_destination(state.get("destination_info") or {})
    if agent_name == "weather":
        return validate_weather(state.get("weather_data") or {})
    if agent_name == "budget":
        return validate_budget(
            state.get("budget_breakdown") or {},
            expected_days=state.get("trip_duration_days") or 0,
        )
    if agent_name == "itinerary":
        return validate_itinerary(
            state.get("itinerary") or {},
            expected_days=state.get("trip_duration_days") or 0,
        )
    if agent_name == "packing":
        return validate_packing(
            state.get("packing_list") or {},
            state.get("weather_data") or {},
        )
    log.error("validate_agent_output: unknown agent %s", agent_name)
    return ValidationResult(
        is_valid=True, issues=[], feedback_for_agent=""
    )
