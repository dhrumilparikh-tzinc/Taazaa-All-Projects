"""Smoke-test the weather agent in isolation."""
from dotenv import load_dotenv
load_dotenv()

from src.agents.weather import weather_agent
from src.state import empty_state

state = empty_state("test")
state["destination_city"] = "Tokyo"
result = weather_agent(state)
wd = result["weather_data"]
print(f"city={wd['city']} country={wd['country']} tz={wd['timezone']}")
print(f"days={len(wd['daily_forecast'])}")
for d in wd["daily_forecast"]:
    print(f"  {d['date']}  {d['temp_min_c']}–{d['temp_max_c']}°C  precip={d['precipitation_mm']}mm")
