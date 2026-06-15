"""Smoke test for REST Countries tool."""
from dotenv import load_dotenv
load_dotenv()

from src.tools.rest_countries import fetch_country_info

CITIES = ["Japan", "France", "Iceland", "Brazil", "definitelynotacountry"]

for name in CITIES:
    print("\n---", name)
    result = fetch_country_info.invoke({"country_name": name})
    if "error" in result:
        print("ERROR:", result["error"])
    else:
        for k in ("country_name", "capital", "currency_code", "languages", "timezone", "flag"):
            print(f"  {k}: {result[k]}")
