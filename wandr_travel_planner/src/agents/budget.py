"""
Budget Agent — fetches live FX rates, converts the user's budget into the
destination currency, asks the LLM to split it proportionally across categories,
then force-scales all amounts to the real computed daily budget so the math
is always correct regardless of what the LLM produced.
"""
from __future__ import annotations

import os

from langchain_groq import ChatGroq

from ..logger import get_logger, groq_model
from ..schemas import BudgetBreakdown
from ..state import AgentState
from ..tools.exchange_rates import convert, fetch_exchange_rates

log = get_logger("budget")

# Daily USD thresholds for budget tier classification
_TIER_THRESHOLDS = [
    (50,    "budget"),
    (150,   "mid-range"),
    (400,   "comfortable"),
    (1000,  "upscale"),
    (float("inf"), "luxury"),
]

_TIER_NOTES = {
    "budget": (
        "This is a tight budget for {city} — expect hostels or guesthouses, "
        "street food and local eateries, free or low-cost attractions, and careful spending."
    ),
    "mid-range": (
        "This is a solid mid-range budget for {city} — expect comfortable hotels, "
        "sit-down restaurant meals, and most standard activities with a little room to splurge."
    ),
    "comfortable": (
        "This is a generous budget for {city} — expect quality hotels, "
        "fine dining, premium experiences, and plenty of flexibility."
    ),
    "upscale": (
        "This is an upscale budget for {city} — expect 5-star hotels, "
        "fine dining restaurants, private guides, and exclusive experiences."
    ),
    "luxury": (
        "This is an ultra-luxury budget for {city} — expect the finest suites, "
        "Michelin-starred restaurants, private tours, helicopter transfers, and VIP everything."
    ),
}

_TIER_CATEGORY_GUIDANCE = {
    "budget": (
        "accommodation: hostels, guesthouses, or budget hotels; "
        "food: street food stalls and cheap local restaurants; "
        "transport: public metro/bus; "
        "activities: mostly free or very cheap attractions; "
        "buffer: small emergency fund."
    ),
    "mid-range": (
        "accommodation: 3-star hotels or boutique guesthouses; "
        "food: casual sit-down restaurants, occasional nicer meal; "
        "transport: mix of public transport and occasional taxi; "
        "activities: paid museums, tours, and experiences; "
        "buffer: moderate contingency."
    ),
    "comfortable": (
        "accommodation: 4-star hotels; "
        "food: quality restaurants and one or two fine dining meals; "
        "transport: taxis and private transfers; "
        "activities: premium guided tours, cooking classes, spa; "
        "buffer: comfortable contingency."
    ),
    "upscale": (
        "accommodation: 5-star hotels; "
        "food: fine dining restaurants, wine pairings, tasting menus; "
        "transport: private car hire, business class transfers; "
        "activities: private guided tours, exclusive experiences, VIP access; "
        "buffer: generous contingency."
    ),
    "luxury": (
        "accommodation: ultra-luxury suites, villa rentals, or palace hotels; "
        "food: Michelin-starred restaurants, private chef experiences, wine cellars; "
        "transport: private car, helicopter, yacht, or charter flights; "
        "activities: fully private tours, exclusive access, bespoke experiences; "
        "buffer: substantial contingency for spontaneous splurges."
    ),
}

BUDGET_PROMPT = """\
You are a luxury/travel budget planner. Allocate a daily spend breakdown
for the trip below. All amounts MUST be in the LOCAL destination currency.

Trip:
- Destination: {city}, {country}
- Duration: {duration} days
- Budget tier: {tier} ({tier_description})
- EXACT daily budget to allocate: {actual_daily:.2f} {local_currency}
  (This is {local_amount:.2f} {local_currency} total ÷ {duration} days)
- Original budget: {orig_amount} {orig_currency}
- Interests: {interests}

Category guidance for a {tier} budget in this destination:
{category_guidance}

CRITICAL RULES:
1. Use EXACTLY these category names: accommodation, food, transport, activities, buffer.
2. The daily_amount values you produce are PROPORTIONS only — they will be scaled.
   Focus on getting the RATIOS right (e.g. accommodation 40%, food 25%, etc.).
3. daily_budget_local = {actual_daily:.2f} (use this exact number, no expressions).
4. duration_days = {duration} (use this exact integer).
5. total_budget_local = {local_amount:.2f} (use this exact number).
6. total_budget_local_currency = "{local_currency}" (use this exact string).
7. total_budget_native = {orig_amount} (use this exact number).
8. total_budget_native_currency = "{orig_currency}" (use this exact string).
9. exchange_rate_used = {rate:.6f} (use this exact decimal number — DO NOT write a formula or expression).
10. notes = leave this as a single empty string ""; it will be filled in automatically.

{feedback_block}

Return your answer in the required structured format.
"""

FEEDBACK_TEMPLATE = "IMPORTANT — a previous attempt was rejected. Fix these issues:\n{feedback}"


def _budget_tier(daily_usd: float) -> str:
    """Classify budget into a named tier based on USD-equivalent daily spend."""
    for threshold, tier in _TIER_THRESHOLDS:
        if daily_usd < threshold:
            return tier
    return "luxury"


def _llm_breakdown(prompt: str) -> BudgetBreakdown | None:
    """Run LLM with structured output. Returns None on failure."""
    llm = ChatGroq(
        model=groq_model(),
        temperature=0.0,
        groq_api_key=os.getenv("GROQ_API_KEY"),
    ).with_structured_output(BudgetBreakdown)
    try:
        return llm.invoke(prompt)
    except Exception as e:  # noqa: BLE001
        log.error("Budget LLM call failed: %s", e)
        return None


def budget_agent(state: AgentState) -> dict:
    """Compute the budget breakdown, scaled to the real daily budget."""
    attempt = state.get("retry_count", {}).get("budget", 0) + 1
    feedback = state.get("validation_feedback", {}).get("budget", "")
    log.info("Budget agent attempt #%d", attempt)
    if feedback:
        log.info("Retry feedback: %s", feedback)

    amount = state.get("budget_amount")
    src_ccy = (state.get("budget_currency") or "USD").upper()
    duration = state.get("trip_duration_days") or 1
    city = state.get("destination_city") or ""
    dest_info = state.get("destination_info") or {}
    country = dest_info.get("country_name") or state.get("destination_country") or ""
    local_ccy = (dest_info.get("currency_code") or src_ccy).upper()
    interests = state.get("interests") or []

    if amount is None:
        return {"budget_breakdown": {"error": "No budget amount provided"}, "last_agent": "budget"}

    # 1. Fetch FX rates
    fx = fetch_exchange_rates.invoke({})
    if "error" in fx:
        return {"budget_breakdown": {"error": f"FX fetch failed: {fx['error']}"}, "last_agent": "budget"}
    rates = fx["rates"]

    # 2. Convert to local currency
    try:
        local_amount = convert(amount, src_ccy, local_ccy, rates)
        rate = local_amount / amount if amount else 1.0
    except KeyError as e:
        log.error("Currency conversion failed: %s — using native.", e)
        local_amount = amount
        local_ccy = src_ccy
        rate = 1.0

    # 3. Compute the REAL daily budget — this is authoritative, never overridden by LLM
    actual_daily = local_amount / duration

    # 4. Determine budget tier using USD-equivalent daily spend
    try:
        daily_usd = convert(actual_daily, local_ccy, "USD", rates)
    except KeyError:
        daily_usd = actual_daily if local_ccy == "USD" else actual_daily / rate
    tier = _budget_tier(daily_usd)
    log.info("Budget tier: %s (%.2f USD/day)", tier, daily_usd)

    # 5. Build prompt with tier guidance
    feedback_block = FEEDBACK_TEMPLATE.format(feedback=feedback) if feedback else ""
    prompt = BUDGET_PROMPT.format(
        city=city or "the destination",
        country=country,
        duration=duration,
        tier=tier,
        tier_description=_TIER_NOTES[tier].format(city=city or "this destination"),
        actual_daily=actual_daily,
        local_currency=local_ccy,
        local_amount=local_amount,
        orig_amount=amount,
        orig_currency=src_ccy,
        rate=rate,
        interests=", ".join(interests) if interests else "general travel",
        category_guidance=_TIER_CATEGORY_GUIDANCE[tier],
        feedback_block=feedback_block,
    )

    # 6. Get category proportions from LLM
    result = _llm_breakdown(prompt)
    if result is None:
        return {"budget_breakdown": {"error": "LLM call failed"}, "last_agent": "budget"}

    payload = result.model_dump()

    # 7. Force-scale all category amounts so they sum to the REAL daily budget.
    #    The LLM only needs to get proportions right — we own the totals.
    categories = payload.get("categories", [])
    llm_sum = sum(c.get("daily_amount", 0) for c in categories)
    if llm_sum > 0:
        scale = actual_daily / llm_sum
        for cat in categories:
            cat["daily_amount"] = round(cat["daily_amount"] * scale, 2)
        # Fix rounding drift on the last category
        rounding_diff = round(actual_daily - sum(c["daily_amount"] for c in categories), 2)
        if categories and rounding_diff != 0:
            categories[-1]["daily_amount"] = round(categories[-1]["daily_amount"] + rounding_diff, 2)

    # 8. Stamp all authoritative numeric fields — never trust LLM for these
    payload["total_budget_native"] = float(amount)
    payload["total_budget_native_currency"] = src_ccy
    payload["total_budget_local"] = round(local_amount, 2)
    payload["total_budget_local_currency"] = local_ccy
    payload["exchange_rate_used"] = round(rate, 6)
    payload["duration_days"] = duration
    payload["daily_budget_local"] = round(actual_daily, 2)
    payload["categories"] = categories

    # 9. Generate notes from tier — don't trust LLM for this
    payload["notes"] = _TIER_NOTES[tier].format(city=city or "this destination")

    # 10. Store tier for downstream agents (itinerary adapts recommendations)
    payload["budget_tier"] = tier
    payload["daily_budget_usd"] = round(daily_usd, 2)

    log.info(
        "Budget OK: %.2f %s -> %.2f %s/day | tier=%s | %d categories",
        amount, src_ccy, actual_daily, local_ccy, tier, len(categories),
    )
    return {"budget_breakdown": payload, "last_agent": "budget"}
