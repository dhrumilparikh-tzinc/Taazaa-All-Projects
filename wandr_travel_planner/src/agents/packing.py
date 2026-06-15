"""Packing Agent — pure Gemini, structured output."""
from __future__ import annotations

import os

from langchain_groq import ChatGroq

from ..logger import get_logger, groq_model
from ..schemas import PackingList
from ..state import AgentState

log = get_logger("packing")


PACKING_PROMPT = """\
You are a packing advisor. Build a focused packing list for a traveller
visiting {city} for {duration} days.

Conditions:
- Weather forecast: {weather_summary}
- Activities/interests: {interests}

Rules:
1. Include AT LEAST these categories: clothing, documents.
2. Other categories you may include: gear, toiletries, electronics.
3. Each category must have at least one item.
4. Reflect the weather:
   - If rain is expected: include rain jacket, umbrella, or waterproof shoes.
   - If cold (min temp < 5°C): include warm layers (coat, thermal, gloves).
   - If hot (max temp > 30°C): include sun protection (hat, sunscreen, sunglasses).
5. Reflect the activities. Hiking interests → hiking boots, daypack.
   Photography → camera/extra batteries. Beach → swimsuit.
6. Keep items practical, not exhaustive. ~5-10 items per category.
7. `weather_summary` is a one-line sentence summarising what the traveller
   should expect (e.g. "Mostly mild with two rainy days, evenings cool").

{feedback_block}

Return your answer in the required structured format.
"""

FEEDBACK_TEMPLATE = """\
IMPORTANT: a previous attempt at this packing list was rejected. Fix these issues:
{feedback}
"""


def _summarise_weather(weather_data: dict) -> tuple[str, float, float, int]:
    daily = weather_data.get("daily_forecast", [])
    if not daily:
        return "weather data unavailable", 99.0, -99.0, 0
    avg_max = sum(d["temp_max_c"] for d in daily) / len(daily)
    avg_min = sum(d["temp_min_c"] for d in daily) / len(daily)
    min_t = min(d["temp_min_c"] for d in daily)
    max_t = max(d["temp_max_c"] for d in daily)
    rainy = sum(1 for d in daily if d.get("precipitation_mm", 0) > 1)
    summary = (
        f"highs around {avg_max:.0f}°C, lows around {avg_min:.0f}°C, "
        f"{rainy} of {len(daily)} days with rain"
    )
    return summary, min_t, max_t, rainy


def packing_agent(state: AgentState) -> dict:
    """Produce a packing list shaped by weather + interests."""
    attempt = state.get("retry_count", {}).get("packing", 0) + 1
    feedback = state.get("validation_feedback", {}).get("packing", "")
    log.info("Packing agent attempt #%d", attempt)
    if feedback:
        log.info("Retry feedback to apply: %s", feedback)

    duration = state.get("trip_duration_days") or 1
    city = state.get("destination_city") or "the destination"
    interests = state.get("interests") or []
    weather_summary, _min, _max, _rain = _summarise_weather(state.get("weather_data") or {})

    feedback_block = FEEDBACK_TEMPLATE.format(feedback=feedback) if feedback else ""
    prompt = PACKING_PROMPT.format(
        city=city,
        duration=duration,
        interests=", ".join(interests) if interests else "general travel",
        weather_summary=weather_summary,
        feedback_block=feedback_block,
    )

    llm = ChatGroq(
        model=groq_model(),
        temperature=0.5,
        groq_api_key=os.getenv("GROQ_API_KEY"),
    ).with_structured_output(PackingList)

    try:
        result: PackingList = llm.invoke(prompt)
    except Exception as e:  # noqa: BLE001
        log.error("Packing LLM call failed: %s", e)
        return {
            "packing_list": {"error": f"LLM call failed: {e}"},
            "last_agent": "packing",
        }

    payload = result.model_dump()
    # The schema requires duration_days and destination at the top level,
    # but the LLM may put placeholders there. Overwrite with truth.
    payload["destination"] = city
    payload["duration_days"] = duration
    log.info(
        "Packing OK: %d categories for %s (%d days)",
        len(payload.get("categories", [])), city, duration,
    )
    return {
        "packing_list": payload,
        "last_agent": "packing",
    }
