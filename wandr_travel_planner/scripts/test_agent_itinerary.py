"""Smoke-test the itinerary agent in isolation."""
from dotenv import load_dotenv
load_dotenv()
import json

from src.agents.itinerary import itinerary_agent
from src.agents.weather import weather_agent
from src.state import empty_state

state = empty_state("Plan 5 days in Tokyo")
state["destination_city"] = "Tokyo"
state["destination_country"] = "Japan"
state["trip_duration_days"] = 5
state["travel_month"] = "October"
state["interests"] = ["temples", "food", "photography"]

state.update(weather_agent(state))
state.update(itinerary_agent(state))

print(json.dumps(state["itinerary"], indent=2))
