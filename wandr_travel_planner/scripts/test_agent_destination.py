"""Smoke-test the destination agent in isolation."""
from dotenv import load_dotenv
load_dotenv()

from src.agents.destination import destination_agent
from src.state import empty_state

state = empty_state("Plan 5 days in Tokyo, ¥80000")
state["destination_city"] = "Tokyo"
state["destination_country"] = "Japan"
state["travel_month"] = "October"
state["interests"] = ["temples", "food"]

result = destination_agent(state)
info = result["destination_info"]
print("country_name:", info.get("country_name"))
print("capital:", info.get("capital"))
print("currency_code:", info.get("currency_code"))
print("flag:", info.get("flag"))
print("\noverview p1:\n", info.get("overview_paragraph_1"))
print("\noverview p2:\n", info.get("overview_paragraph_2"))
