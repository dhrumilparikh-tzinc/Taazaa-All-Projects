"""Verify the parser turns free text into structured fields."""
from dotenv import load_dotenv
load_dotenv()

from src.parser import parse_query

QUERIES = [
    "Plan a 5-day trip to Tokyo in October, ¥80,000 budget, I like temples and food.",
    "weekend in Paris on a tight budget around €400, museums and pastries",
    "7 days in Reykjavik, $3000, hiking and waterfalls",
]

for q in QUERIES:
    print("\n---")
    print("Query:", q)
    parsed = parse_query(q)
    print(parsed.model_dump_json(indent=2))
