"""Smoke test for exchange rates tool."""
from dotenv import load_dotenv
load_dotenv()

from src.tools.exchange_rates import fetch_exchange_rates, convert

result = fetch_exchange_rates.invoke({})
if "error" in result:
    print("ERROR:", result["error"])
else:
    rates = result["rates"]
    print(f"Got {len(rates)} currencies as of {result['date']}")

    # Test conversions
    cases = [
        (100, "USD", "JPY"),
        (10000, "JPY", "USD"),
        (500, "EUR", "INR"),
        (100, "GBP", "EUR"),
    ]
    for amount, src, dst in cases:
        try:
            converted = convert(amount, src, dst, rates)
            print(f"  {amount} {src} = {converted:.2f} {dst}")
        except KeyError as e:
            print(f"  ERROR: {e}")
