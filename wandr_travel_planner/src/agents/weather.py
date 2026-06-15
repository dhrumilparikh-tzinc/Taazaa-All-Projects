"""Weather Agent — geocodes the city, then fetches a 7-day forecast."""
from __future__ import annotations

from ..logger import get_logger
from ..state import AgentState
from ..tools.open_meteo import fetch_weather_forecast, geocode_city

log = get_logger("weather")


def weather_agent(state: AgentState) -> dict:
    """Geocode + forecast."""
    city = state.get("destination_city")
    attempt = state.get("retry_count", {}).get("weather", 0) + 1
    feedback = state.get("validation_feedback", {}).get("weather", "")
    log.info("Weather agent attempt #%d for city=%s", attempt, city)
    if feedback:
        log.info("Retry feedback to apply: %s", feedback)

    if not city:
        return {
            "weather_data": {"error": "No city provided"},
            "last_agent": "weather",
        }

    geo = geocode_city.invoke({"city": city})
    if "error" in geo:
        log.error("Geocoding failed: %s", geo["error"])
        return {
            "weather_data": {"error": geo["error"]},
            "last_agent": "weather",
        }

    forecast = fetch_weather_forecast.invoke({
        "latitude": geo["latitude"],
        "longitude": geo["longitude"],
    })
    if "error" in forecast:
        log.error("Forecast failed: %s", forecast["error"])
        return {
            "weather_data": {"error": forecast["error"]},
            "last_agent": "weather",
        }

    combined = {
        "city": geo.get("name") or city,
        "country": geo.get("country", ""),
        "latitude": geo["latitude"],
        "longitude": geo["longitude"],
        "timezone": forecast.get("timezone", geo.get("timezone", "")),
        "daily_forecast": forecast["daily_forecast"],
    }
    log.info("Weather agent OK: %d days for %s", len(combined["daily_forecast"]), city)
    return {
        "weather_data": combined,
        "last_agent": "weather",
    }
