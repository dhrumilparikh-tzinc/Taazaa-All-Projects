"""Smoke-test the budget agent in isolation."""
from dotenv import load_dotenv
load_dotenv()
import json

from src.agents.budget import budget_agent
from src.agents.destination import destination_agent
from src.state import empty_state

state = empty_state("Plan 5 days in Tokyo, ¥80000")
state["destination_city"] = "Tokyo"
state["destination_country"] = "Japan"
state["trip_duration_days"] = 5
state["budget_amount"] = 80000
state["budget_currency"] = "JPY"
state["interests"] = ["temples", "food"]

# Need destination_info first so budget has the local currency code
state.update(destination_agent(state))
state.update(budget_agent(state))

print(json.dumps(state["budget_breakdown"], indent=2))
