"""Smoke-test the packing agent in isolation."""
from dotenv import load_dotenv
load_dotenv()
import json

from src.agents.packing import packing_agent
from src.agents.weather import weather_agent
from src.state import empty_state

state = empty_state("Plan 5 days in Reykjavik")
state["destination_city"] = "Reykjavik"
state["destination_country"] = "Iceland"
state["trip_duration_days"] = 5
state["interests"] = ["hiking", "hot springs"]

state.update(weather_agent(state))
state.update(packing_agent(state))

print(json.dumps(state["packing_list"], indent=2))
