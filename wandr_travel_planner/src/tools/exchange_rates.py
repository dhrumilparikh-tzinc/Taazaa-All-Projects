"""
Tool: Open Exchange Rates (free tier, USD base, no key).
https://www.exchangerate-api.com/docs/free
"""
from __future__ import annotations

import httpx
from langchain_core.tools import tool

from ..logger import get_logger

log = get_logger("budget")

URL = "https://open.er-api.com/v6/latest/USD"


@tool("fetch_exchange_rates", parse_docstring=True)
def fetch_exchange_rates() -> dict:
    """Fetch current FX rates with USD as base.

    Returns:
        Dict with base ('USD'), date, and rates (ISO code -> float).
        On failure returns {"error": "..."}.
    """
    log.info("Fetching FX rates from open.er-api.com")
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(URL)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:  # noqa: BLE001
        log.error("Exchange rates HTTP error: %s", e)
        return {"error": f"FX fetch failed: {e}"}

    if payload.get("result") != "success":
        msg = payload.get("error-type", "unknown error")
        log.error("Exchange rates API said: %s", msg)
        return {"error": f"FX API error: {msg}"}

    rates = payload.get("rates") or {}
    log.info("FX rates OK: %d currencies", len(rates))
    return {
        "base": payload.get("base_code", "USD"),
        "date": payload.get("time_last_update_utc", ""),
        "rates": rates,
    }


def convert(amount: float, from_ccy: str, to_ccy: str, rates: dict[str, float]) -> float:
    """Convert via USD: amount[from] -> USD -> to.

    Raises KeyError if either currency is not in `rates`.
    """
    from_ccy = (from_ccy or "USD").upper()
    to_ccy = (to_ccy or "USD").upper()
    if from_ccy == to_ccy:
        return float(amount)
    if from_ccy not in rates:
        raise KeyError(f"Unknown source currency: {from_ccy}")
    if to_ccy not in rates:
        raise KeyError(f"Unknown target currency: {to_ccy}")
    usd_amount = float(amount) / float(rates[from_ccy])
    return usd_amount * float(rates[to_ccy])


@tool("convert_currency", parse_docstring=True)
def convert_currency(amount: float, from_currency: str, to_currency: str) -> dict:
    """Convert a monetary amount from one currency to another using live FX rates.

    Args:
        amount: The amount to convert.
        from_currency: ISO 4217 source currency code (e.g. USD, JPY, EUR).
        to_currency: ISO 4217 target currency code.

    Returns:
        Dict with converted_amount, exchange_rate, from_currency, to_currency.
        On failure returns {"error": "..."}.
    """
    fx = fetch_exchange_rates.invoke({})
    if "error" in fx:
        return {"error": fx["error"]}
    try:
        rates = fx["rates"]
        result = convert(amount, from_currency, to_currency, rates)
        rate = result / amount if amount else 0.0
        return {
            "converted_amount": round(result, 2),
            "exchange_rate": round(rate, 6),
            "from_currency": from_currency.upper(),
            "to_currency": to_currency.upper(),
        }
    except KeyError as e:
        return {"error": str(e)}
