"""Smoke tests for tool functions. These hit live free APIs.

Skip them if you're offline.
"""
import os
import pytest
from dotenv import load_dotenv
load_dotenv()

from src.tools.rest_countries import fetch_country_info
from src.tools.open_meteo import geocode_city, fetch_weather_forecast
from src.tools.exchange_rates import fetch_exchange_rates, convert


def test_country_japan():
    r = fetch_country_info.invoke({"country_name": "Japan"})
    assert r.get("country_name") == "Japan"
    assert r.get("capital") == "Tokyo"
    assert r.get("currency_code") == "JPY"
    assert "Japanese" in r.get("languages", [])


def test_country_404():
    r = fetch_country_info.invoke({"country_name": "definitelynotacountry"})
    assert "error" in r


def test_geocode_tokyo():
    r = geocode_city.invoke({"city": "Tokyo"})
    assert r.get("country") == "Japan"
    assert 35 < r["latitude"] < 36
    assert 139 < r["longitude"] < 140


def test_forecast_shape():
    r = fetch_weather_forecast.invoke({"latitude": 35.68, "longitude": 139.69})
    assert "daily_forecast" in r
    assert len(r["daily_forecast"]) == 7
    day = r["daily_forecast"][0]
    assert set(day.keys()) == {"date", "temp_max_c", "temp_min_c", "precipitation_mm", "wind_max_kmh"}


def test_fx_rates_load():
    r = fetch_exchange_rates.invoke({})
    assert "rates" in r
    assert r["rates"]["JPY"] > 50  # JPY/USD has been > 50 for decades


def test_fx_convert():
    rates = fetch_exchange_rates.invoke({})["rates"]
    jpy = convert(100, "USD", "JPY", rates)
    assert 5000 < jpy < 25000  # 100 USD to JPY (historical USD/JPY range: 75-160)
    back = convert(jpy, "JPY", "USD", rates)
    assert abs(back - 100) < 0.01  # round trip
