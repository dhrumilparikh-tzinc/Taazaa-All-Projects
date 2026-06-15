"""
Tools: Open-Meteo Geocoding + Forecast.
Both free, no key. https://open-meteo.com/
"""
from __future__ import annotations

import httpx
from langchain_core.tools import tool

from ..logger import get_logger

log = get_logger("weather")

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


@tool("geocode_city", parse_docstring=True)
def geocode_city(city: str) -> dict:
    """Convert a city name to lat/lng + country.

    Args:
        city: City name (e.g. "Tokyo", "Reykjavik").

    Returns:
        Dict with latitude, longitude, country, name, country_code, timezone.
        On failure returns {"error": "..."}.
    """
    log.info("Geocoding city: %s", city)
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(GEO_URL, params={"name": city, "count": 1})
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:  # noqa: BLE001
        log.error("Geocoding HTTP error: %s", e)
        return {"error": f"Geocoding failed: {e}"}

    results = payload.get("results") or []
    if not results:
        log.warning("Geocoding: no result for %s", city)
        return {"error": f"No geocoding result for '{city}'."}

    r = results[0]
    out = {
        "name": r.get("name"),
        "latitude": r.get("latitude"),
        "longitude": r.get("longitude"),
        "country": r.get("country", ""),
        "country_code": r.get("country_code", ""),
        "timezone": r.get("timezone", ""),
    }
    log.info("Geocoded %s -> (%.3f, %.3f) %s",
             city, out["latitude"], out["longitude"], out["country"])
    return out


@tool("fetch_weather_forecast", parse_docstring=True)
def fetch_weather_forecast(latitude: float, longitude: float) -> dict:
    """Fetch 7-day weather forecast for the given coordinates.

    Args:
        latitude: Decimal latitude.
        longitude: Decimal longitude.

    Returns:
        Dict with daily_forecast list. Each entry has date, temp_max_c,
        temp_min_c, precipitation_mm, wind_max_kmh.
    """
    log.info("Forecast for (%.3f, %.3f)", latitude, longitude)
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max",
        "forecast_days": 7,
        "timezone": "auto",
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(FORECAST_URL, params=params)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:  # noqa: BLE001
        log.error("Forecast HTTP error: %s", e)
        return {"error": f"Forecast failed: {e}"}

    daily = payload.get("daily") or {}
    dates = daily.get("time") or []
    if not dates:
        return {"error": "No daily data in forecast response."}

    out_days = []
    for i, date in enumerate(dates):
        out_days.append(
            {
                "date": date,
                "temp_max_c": daily["temperature_2m_max"][i],
                "temp_min_c": daily["temperature_2m_min"][i],
                "precipitation_mm": daily["precipitation_sum"][i],
                "wind_max_kmh": daily["windspeed_10m_max"][i],
            }
        )
    log.info("Forecast OK: %d days", len(out_days))
    return {
        "timezone": payload.get("timezone", ""),
        "daily_forecast": out_days,
    }


@tool("get_city_timezone", parse_docstring=True)
def get_city_timezone(city: str) -> dict:
    """Look up the IANA timezone identifier for a city.

    Args:
        city: City name (e.g. "Paris", "Bangkok").

    Returns:
        Dict with timezone (IANA string), utc_offset_seconds, and city_name.
        On failure returns {"error": "..."}.
    """
    geo = geocode_city.invoke({"city": city})
    if "error" in geo:
        return {"error": geo["error"]}
    tz = geo.get("timezone", "")
    if not tz:
        return {"error": f"No timezone found for '{city}'."}
    params = {
        "latitude": geo["latitude"],
        "longitude": geo["longitude"],
        "forecast_days": 1,
        "timezone": "auto",
        "daily": "temperature_2m_max",
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(FORECAST_URL, params=params)
        resp.raise_for_status()
        payload = resp.json()
        utc_offset = payload.get("utc_offset_seconds", 0)
    except Exception:  # noqa: BLE001
        utc_offset = 0
    return {
        "city_name": geo.get("name", city),
        "timezone": tz,
        "utc_offset_seconds": utc_offset,
    }
