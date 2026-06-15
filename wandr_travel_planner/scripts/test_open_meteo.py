"""Smoke test for Open-Meteo geocoding + forecast."""
from dotenv import load_dotenv
load_dotenv()

from src.tools.open_meteo import geocode_city, fetch_weather_forecast

for city in ["Tokyo", "Reykjavik", "Cairo"]:
    print("\n===", city)
    geo = geocode_city.invoke({"city": city})
    print("Geo:", geo)
    if "error" in geo:
        continue
    fc = fetch_weather_forecast.invoke(
        {"latitude": geo["latitude"], "longitude": geo["longitude"]}
    )
    if "error" in fc:
        print("Forecast ERROR:", fc["error"])
        continue
    print(f"Forecast tz: {fc['timezone']}, days: {len(fc['daily_forecast'])}")
    for d in fc["daily_forecast"]:
        print(f"  {d['date']}  max={d['temp_max_c']}°C  min={d['temp_min_c']}°C  precip={d['precipitation_mm']}mm")
