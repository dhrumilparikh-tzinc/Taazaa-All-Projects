"""Unit tests for the output validators."""
from src.guardrails import (
    validate_destination,
    validate_weather,
    validate_budget,
    validate_itinerary,
    validate_packing,
)


def expect(label, result, should_be_valid):
    status = "✓" if result.is_valid == should_be_valid else "✗ FAIL"
    print(f"{status}  {label}")
    if not result.is_valid:
        print(f"     issues: {result.issues}")


# --- destination ---
good_dest = {
    "country_name": "Japan", "capital": "Tokyo", "currency_code": "JPY",
    "currency_name": "Yen", "languages": ["Japanese"], "timezone": "UTC+09:00",
    "region": "Asia", "flag": "🇯🇵",
}
expect("destination: good", validate_destination(good_dest), True)

bad_dest = {**good_dest, "currency_code": "yen"}
expect("destination: bad currency code", validate_destination(bad_dest), False)

expect("destination: error", validate_destination({"error": "not found"}), False)


# --- weather ---
good_weather = {"daily_forecast": [
    {"date": f"2026-05-{14+i}", "temp_max_c": 22.0, "temp_min_c": 14.0,
     "precipitation_mm": 0.0, "wind_max_kmh": 10.0}
    for i in range(7)
]}
expect("weather: good", validate_weather(good_weather), True)

short_weather = {"daily_forecast": good_weather["daily_forecast"][:3]}
expect("weather: too few days", validate_weather(short_weather), False)


# --- budget ---
good_budget = {
    "total_budget_native": 1000.0, "total_budget_native_currency": "USD",
    "total_budget_local": 154000.0, "total_budget_local_currency": "JPY",
    "exchange_rate_used": 154.0, "duration_days": 5,
    "daily_budget_local": 30800.0,
    "categories": [
        {"name": "accommodation", "daily_amount": 12000, "description": "hostel"},
        {"name": "food", "daily_amount": 8000, "description": "ramen"},
        {"name": "transport", "daily_amount": 4800, "description": "metro"},
        {"name": "activities", "daily_amount": 6000, "description": "museums"},
    ],
    "notes": "Realistic for Tokyo on a moderate budget.",
}
expect("budget: good", validate_budget(good_budget, expected_days=5), True)

mismatched = {**good_budget, "duration_days": 7}
expect("budget: wrong duration", validate_budget(mismatched, expected_days=5), False)


# --- itinerary ---
good_itin = {"destination": "Tokyo", "summary": "great trip", "days": [
    {"day": i+1, "theme": "explore", "segments": [
        {"period": "morning", "activity": "visit", "location": "Sensoji Temple"},
        {"period": "afternoon", "activity": "lunch", "location": "Tsukiji Outer Market"},
        {"period": "evening", "activity": "stroll", "location": "Shibuya Crossing"},
    ]} for i in range(5)
]}
expect("itinerary: good", validate_itinerary(good_itin, expected_days=5), True)

generic = {"destination": "Tokyo", "summary": "x", "days": [
    {"day": 1, "theme": "x", "segments": [
        {"period": "morning", "activity": "x", "location": "downtown"},
        {"period": "afternoon", "activity": "x", "location": "the city"},
        {"period": "evening", "activity": "x", "location": "various"},
    ]}
]}
expect("itinerary: generic locations", validate_itinerary(generic, expected_days=1), False)


# --- packing ---
weather_rainy = {"daily_forecast": [
    {"temp_min_c": 12, "temp_max_c": 18, "precipitation_mm": 5.0} for _ in range(5)
]}
no_rain_gear = {"categories": [
    {"category": "clothing", "items": ["t-shirts", "shorts"]},
    {"category": "documents", "items": ["passport"]},
    {"category": "gear", "items": ["sunglasses"]},
]}
expect("packing: rain but no rain gear", validate_packing(no_rain_gear, weather_rainy), False)

with_rain_gear = {"categories": [
    {"category": "clothing", "items": ["t-shirts", "rain jacket"]},
    {"category": "documents", "items": ["passport"]},
    {"category": "gear", "items": ["umbrella"]},
]}
expect("packing: with rain gear", validate_packing(with_rain_gear, weather_rainy), True)
