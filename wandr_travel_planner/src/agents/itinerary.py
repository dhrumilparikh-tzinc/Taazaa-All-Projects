"""Itinerary Agent — detailed structured day-by-day plan, batched for long trips.
Adapts recommendations to the budget tier set by the budget agent."""
from __future__ import annotations

import os

from langchain_groq import ChatGroq

from ..logger import get_logger, groq_model
from ..schemas import Itinerary, ItineraryDay
from ..state import AgentState

log = get_logger("itinerary")

_BATCH_SIZE = 4

# Per-tier style guides injected into the prompt
_TIER_STYLE = {
    "budget": """\
BUDGET TIER: budget/backpacker
- Accommodation: hostels, guesthouses, budget hotels
- Food: street food stalls, night markets, cheap local eateries — name specific stalls/markets
- Transport: public metro, local buses, walking — no taxis
- Activities: free parks, free temples, free viewpoints, low-cost museums
- cost_note: keep all prices very low (street food ₹50–200, free or <$5 entry fees)
- Tone: adventurous, resourceful, local-feeling""",

    "mid-range": """\
BUDGET TIER: mid-range
- Accommodation: 3-star hotels, boutique guesthouses, well-reviewed B&Bs
- Food: casual sit-down restaurants, local speciality spots — name specific restaurants
- Transport: mix of public transport and occasional taxi/Uber
- Activities: standard paid museums, group tours, cooking classes
- cost_note: moderate prices (mid-range restaurant meals, standard entry fees)
- Tone: comfortable, well-rounded, value-conscious""",

    "comfortable": """\
BUDGET TIER: comfortable/premium
- Accommodation: 4-star hotels, design hotels, premium stays
- Food: quality restaurants, one or two fine-dining meals per day — name specific restaurants
- Transport: taxis, private transfers, Uber Premium
- Activities: premium guided tours, spa treatments, cultural performances with best seats
- cost_note: higher prices (quality restaurants, premium entry or private access)
- Tone: relaxed, premium, indulgent without being ostentatious""",

    "upscale": """\
BUDGET TIER: upscale/luxury
- Accommodation: 5-star hotels, heritage palace hotels, luxury resorts
- Food: fine-dining and Michelin-starred restaurants exclusively — name specific restaurants
- Transport: private car hire, luxury transfers
- Activities: private guided tours (no groups), exclusive after-hours museum access,
  helicopter/boat charters, VIP experiences
- cost_note: luxury prices (fine dining per person, private tour rates, premium entry)
- Tone: exclusive, indulgent, bespoke""",

    "luxury": """\
BUDGET TIER: ultra-luxury
- Accommodation: ultra-luxury suites, private villas, palace hotels — name the specific property
- Food: Michelin-starred restaurants, private chef dinners, exclusive tastings — name each restaurant
- Transport: private car, helicopter transfers, yacht charters, chartered flights
- Activities: fully private exclusive access, bespoke cultural immersions, once-in-a-lifetime
  experiences (private sunrise at a monument, behind-the-scenes tours, personal artisan workshops)
- cost_note: ultra-luxury prices reflecting the exclusivity
- Tone: extraordinary, once-in-a-lifetime, no-compromise""",
}

ITINERARY_PROMPT = """\
You are an expert travel writer crafting a detailed, immersive day-by-day itinerary.

Destination: {city}, {country}
Month: {month}
Interests: {interests}
Forecast: {weather_summary}
Daily budget: {daily_budget} {budget_currency}/day

{tier_style}

Generate EXACTLY days {start_day} through {end_day} (day numbers {start_day}..{end_day}).

STRUCTURE PER DAY:
Each day MUST have EXACTLY 4 or 5 time segments — never fewer than 4, even for a single day.
Use these period labels (pick what fits):
  early morning, morning, late morning, lunch, afternoon, late afternoon, evening

REQUIRED FIELDS PER SEGMENT:
- time: specific clock range e.g. "9:00 AM – 11:30 AM"
- period: one of the labels above
- activity: 3-6 words describing the action
- location: the EXACT real name of the place (hotel name, restaurant name, temple name, tour company)
  NEVER use "downtown", "the city", "various", "TBD", or vague placeholders
- description: 2 vivid sentences — what to see, experience, taste, or feel there.
  For the budget tier above, describe the APPROPRIATE level of experience.
- tips: one practical insider tip matching the budget tier
- cost_note: realistic price in local currency matching the budget tier

REQUIRED FIELDS PER DAY:
- theme: 3-5 word evocative title
- highlights: 2-4 one-sentence standout moments of the day
- transport_note: how to move between today's spots — matching the budget tier

QUALITY RULES:
1. Every location must be a real, specific named place.
2. ALL recommendations (hotels, restaurants, transport, activities) MUST match the budget tier.
3. Descriptions must be vivid and specific — mention the dish name, the view, the architectural detail.
4. Spread locations geographically across the trip.
5. If heavy rain is forecast, prefer indoor venues that day.
6. Time allocations must be realistic.

{feedback_block}

Return ONLY days {start_day}–{end_day} in the required structured format.
The top-level `destination` field should be "{city}, {country}".
The `summary` field: write it only for the FIRST batch (days 1+); otherwise leave it as an empty string.
"""

FEEDBACK_TEMPLATE = "IMPORTANT — a previous attempt was rejected. Fix these issues:\n{feedback}"


def _summarise_weather(weather_data: dict) -> str:
    """One-line weather summary for the itinerary prompt."""
    daily = weather_data.get("daily_forecast", [])
    if not daily:
        return "weather data unavailable"
    avg_max = sum(d["temp_max_c"] for d in daily) / len(daily)
    avg_min = sum(d["temp_min_c"] for d in daily) / len(daily)
    rainy = sum(1 for d in daily if d.get("precipitation_mm", 0) > 1)
    return (
        f"avg high {avg_max:.0f}°C, avg low {avg_min:.0f}°C, "
        f"{rainy} of {len(daily)} days with rain"
    )


def _make_llm() -> ChatGroq:
    """Create the Groq LLM with structured output."""
    return ChatGroq(
        model=groq_model(),
        temperature=0.7,
        max_tokens=4096,
        groq_api_key=os.getenv("GROQ_API_KEY"),
    ).with_structured_output(Itinerary)


def _generate_batch(
    llm: ChatGroq,
    city: str,
    country: str,
    month: str,
    interests: str,
    weather_summary: str,
    daily_budget: str,
    budget_currency: str,
    tier_style: str,
    start_day: int,
    end_day: int,
    feedback_block: str,
) -> tuple[list[ItineraryDay], str]:
    """Generate one batch of days and return (days, summary)."""
    prompt = ITINERARY_PROMPT.format(
        city=city,
        country=country,
        month=month,
        interests=interests,
        weather_summary=weather_summary,
        daily_budget=daily_budget,
        budget_currency=budget_currency,
        tier_style=tier_style,
        start_day=start_day,
        end_day=end_day,
        feedback_block=feedback_block,
    )
    result: Itinerary = llm.invoke(prompt)
    return result.days, result.summary


def itinerary_agent(state: AgentState) -> dict:
    """Produce a detailed day-by-day plan adapted to the budget tier."""
    attempt = state.get("retry_count", {}).get("itinerary", 0) + 1
    feedback = state.get("validation_feedback", {}).get("itinerary", "")
    log.info("Itinerary agent attempt #%d", attempt)
    if feedback:
        log.info("Retry feedback: %s", feedback)

    duration = state.get("trip_duration_days") or 1
    city = state.get("destination_city") or "the destination"
    dest_info = state.get("destination_info") or {}
    country = dest_info.get("country_name") or state.get("destination_country") or ""
    weather_summary = _summarise_weather(state.get("weather_data") or {})
    interests = ", ".join(state.get("interests") or []) or "general travel"
    month = state.get("travel_month") or "the chosen month"
    feedback_block = FEEDBACK_TEMPLATE.format(feedback=feedback) if feedback else ""

    # Read budget context set by the budget agent
    budget_breakdown = state.get("budget_breakdown") or {}
    tier = budget_breakdown.get("budget_tier", "mid-range")
    daily_budget = budget_breakdown.get("daily_budget_local", 0)
    budget_currency = budget_breakdown.get("total_budget_local_currency", "")
    daily_budget_str = f"{daily_budget:,.0f}" if daily_budget else "unspecified"
    tier_style = _TIER_STYLE.get(tier, _TIER_STYLE["mid-range"])

    log.info("Itinerary using budget tier: %s (%.0f %s/day)", tier, daily_budget, budget_currency)

    llm = _make_llm()
    all_days: list[ItineraryDay] = []
    trip_summary = ""

    batch_start = 1
    while batch_start <= duration:
        batch_end = min(batch_start + _BATCH_SIZE - 1, duration)
        log.info("Generating days %d-%d for %s [tier=%s]", batch_start, batch_end, city, tier)
        try:
            days, summary = _generate_batch(
                llm, city, country, month, interests, weather_summary,
                daily_budget_str, budget_currency, tier_style,
                batch_start, batch_end, feedback_block,
            )
        except Exception as e:  # noqa: BLE001
            log.error("Itinerary LLM call failed (days %d-%d): %s", batch_start, batch_end, e)
            return {"itinerary": {"error": f"LLM call failed: {e}"}, "last_agent": "itinerary"}

        valid = [d for d in days if batch_start <= d.day <= batch_end]
        if not valid:
            log.warning("Batch days %d-%d returned no valid days", batch_start, batch_end)
            return {
                "itinerary": {"error": f"No valid days for batch {batch_start}-{batch_end}"},
                "last_agent": "itinerary",
            }
        all_days.extend(valid)
        if batch_start == 1 and summary:
            trip_summary = summary
        batch_start = batch_end + 1

    all_days.sort(key=lambda d: d.day)

    payload = Itinerary(
        destination=f"{city}, {country}",
        days=all_days,
        summary=trip_summary,
    ).model_dump()

    log.info("Itinerary OK: %d days for %s [tier=%s]", len(all_days), city, tier)
    return {"itinerary": payload, "last_agent": "itinerary"}
