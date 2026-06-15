"""
Tool: REST Countries — fetch country metadata.
Free, no key. https://restcountries.com/
"""
from __future__ import annotations

import httpx
from langchain_core.tools import tool

from ..logger import get_logger

log = get_logger("destination")

BASE = "https://restcountries.com/v3.1"


@tool("fetch_country_info", parse_docstring=True)
def fetch_country_info(country_name: str) -> dict:
    """Look up a country and return its basic metadata.

    Args:
        country_name: Full or partial country name (e.g. "Japan", "United States").

    Returns:
        A dict with country_name, capital, currency_code, currency_name,
        languages, timezone, region, flag. On failure, returns
        {"error": "..."} so the agent can decide what to do.
    """
    log.info("REST Countries lookup: %s", country_name)
    url = f"{BASE}/name/{country_name}"
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, params={"fullText": "false"})
        if resp.status_code == 404:
            log.warning("REST Countries: no match for %s", country_name)
            return {"error": f"No country found matching '{country_name}'."}
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as e:
        log.error("REST Countries HTTP error: %s", e)
        return {"error": f"HTTP error: {e}"}
    except Exception as e:  # noqa: BLE001
        log.error("REST Countries unexpected error: %s", e)
        return {"error": f"Unexpected error: {e}"}

    if not data:
        return {"error": "Empty response."}

    # Pick the best match (first result is usually the right one).
    c = data[0]
    currencies = c.get("currencies", {}) or {}
    cc, cinfo = next(iter(currencies.items()), ("", {}))
    languages = list((c.get("languages") or {}).values())
    timezones = c.get("timezones") or []

    result = {
        "country_name": (c.get("name") or {}).get("common", country_name),
        "official_name": (c.get("name") or {}).get("official", ""),
        "capital": (c.get("capital") or [""])[0],
        "currency_code": cc,
        "currency_name": cinfo.get("name", ""),
        "currency_symbol": cinfo.get("symbol", ""),
        "languages": languages,
        "timezone": timezones[0] if timezones else "",
        "region": c.get("region", ""),
        "subregion": c.get("subregion", ""),
        "flag": c.get("flag", ""),
    }
    log.info(
        "REST Countries OK: %s capital=%s currency=%s",
        result["country_name"], result["capital"], result["currency_code"],
    )
    return result
