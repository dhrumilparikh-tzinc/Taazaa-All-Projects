"""
Destination Agent — fetches country metadata from REST Countries and asks
Gemini for a short travel-overview blurb (the prose that appears on the
Trip Brief "Travel Overview" panel).
"""
from __future__ import annotations

import os

from langchain_groq import ChatGroq

from ..logger import get_logger, groq_model
from ..schemas import DestinationOverview
from ..state import AgentState
from ..tools.rest_countries import fetch_country_info

log = get_logger("destination")


OVERVIEW_PROMPT = """\
You are a travel editor writing a two-paragraph overview for a traveller
visiting {city}, {country} in {month}.

Paragraph 1 (3-4 sentences): describe what makes {city} distinctive —
neighbourhoods, food, atmosphere, what visitors notice first. Be specific
and evocative; name 2-3 real places by name.

Paragraph 2 (2-3 sentences): comment specifically on visiting in {month}
— weather, seasonal events or food, what to expect, what NOT to miss
that month.

The traveller's interests are: {interests}. Bias the writing toward
those interests where it's natural.

Do NOT include a headline. Do NOT mention dates. Do NOT use bullet points.
"""


def _write_overview(city: str, country: str, month: str, interests: list[str]) -> dict:
    """Generate the 2-paragraph overview via Gemini."""
    llm = ChatGroq(
        model=groq_model(),
        temperature=0.7,
        groq_api_key=os.getenv("GROQ_API_KEY"),
    ).with_structured_output(DestinationOverview)

    prompt = OVERVIEW_PROMPT.format(
        city=city,
        country=country,
        month=month or "the user's chosen month",
        interests=", ".join(interests) if interests else "general travel",
    )
    try:
        result: DestinationOverview = llm.invoke(prompt)
        return result.model_dump()
    except Exception as e:  # noqa: BLE001
        log.error("Overview LLM call failed: %s", e)
        return {
            "overview_paragraph_1": f"A visit to {city} offers a memorable mix of culture, food, and discovery.",
            "overview_paragraph_2": "",
        }


_CITY_COUNTRY_MAP = {
    "tokyo": "Japan", "osaka": "Japan", "kyoto": "Japan",
    "paris": "France", "lyon": "France", "nice": "France",
    "london": "United Kingdom", "manchester": "United Kingdom", "edinburgh": "United Kingdom",
    "new york": "United States", "los angeles": "United States", "chicago": "United States",
    "san francisco": "United States", "miami": "United States", "las vegas": "United States",
    "bangkok": "Thailand", "chiang mai": "Thailand", "phuket": "Thailand",
    "rome": "Italy", "milan": "Italy", "florence": "Italy", "venice": "Italy",
    "barcelona": "Spain", "madrid": "Spain", "seville": "Spain",
    "berlin": "Germany", "munich": "Germany", "hamburg": "Germany",
    "amsterdam": "Netherlands", "rotterdam": "Netherlands",
    "dubai": "United Arab Emirates", "abu dhabi": "United Arab Emirates",
    "singapore": "Singapore",
    "sydney": "Australia", "melbourne": "Australia", "brisbane": "Australia",
    "toronto": "Canada", "vancouver": "Canada", "montreal": "Canada",
    "mumbai": "India", "delhi": "India", "bangalore": "India", "kolkata": "India",
    "beijing": "China", "shanghai": "China", "hong kong": "China",
    "seoul": "South Korea", "busan": "South Korea",
    "istanbul": "Turkey", "ankara": "Turkey",
    "cairo": "Egypt", "reykjavik": "Iceland",
    "rio de janeiro": "Brazil", "sao paulo": "Brazil",
    "mexico city": "Mexico", "cancun": "Mexico",
    "buenos aires": "Argentina", "lima": "Peru",
    "nairobi": "Kenya", "cape town": "South Africa", "johannesburg": "South Africa",
    "lisbon": "Portugal", "porto": "Portugal",
    "prague": "Czech Republic", "vienna": "Austria", "zurich": "Switzerland",
    "stockholm": "Sweden", "oslo": "Norway", "copenhagen": "Denmark", "helsinki": "Finland",
    "warsaw": "Poland", "budapest": "Hungary", "athens": "Greece",
    "jakarta": "Indonesia", "bali": "Indonesia",
    "kuala lumpur": "Malaysia", "penang": "Malaysia",
    "manila": "Philippines", "ho chi minh city": "Vietnam", "hanoi": "Vietnam",
    "kathmandu": "Nepal", "colombo": "Sri Lanka", "dhaka": "Bangladesh",
    "lahore": "Pakistan", "karachi": "Pakistan",
    "moscow": "Russia", "saint petersburg": "Russia",
    "tel aviv": "Israel", "jerusalem": "Israel",
    "casablanca": "Morocco", "marrakech": "Morocco",
}


def _infer_country(city: str) -> str | None:
    """Return country name for well-known cities, else None."""
    return _CITY_COUNTRY_MAP.get(city.lower().strip())


def destination_agent(state: AgentState) -> dict:
    """Look up the destination country and write a travel overview."""
    city = state.get("destination_city") or ""
    country = state.get("destination_country") or _infer_country(city) or city
    month = state.get("travel_month") or ""
    interests = state.get("interests") or []

    attempt = state.get("retry_count", {}).get("destination", 0) + 1
    feedback = state.get("validation_feedback", {}).get("destination", "")
    log.info("Destination agent attempt #%d for country=%s city=%s", attempt, country, city)
    if feedback:
        log.info("Retry feedback to apply: %s", feedback)

    if not country:
        return {
            "destination_info": {"error": "No country/city provided"},
            "last_agent": "destination",
        }

    # 1. Tool call — REST Countries.
    info = fetch_country_info.invoke({"country_name": country})

    # If city-as-country failed, try the fallback map one more time
    if "error" in info and country == city:
        guessed = _infer_country(city)
        if guessed and guessed != country:
            log.info("Retrying REST Countries with inferred country: %s", guessed)
            info = fetch_country_info.invoke({"country_name": guessed})

    # 2. If the tool succeeded, ask the LLM for the overview.
    if "error" not in info:
        overview = _write_overview(city, info.get("country_name") or country, month, interests)
        info["overview_paragraph_1"] = overview.get("overview_paragraph_1", "")
        info["overview_paragraph_2"] = overview.get("overview_paragraph_2", "")

    return {
        "destination_info": info,
        "last_agent": "destination",
    }
