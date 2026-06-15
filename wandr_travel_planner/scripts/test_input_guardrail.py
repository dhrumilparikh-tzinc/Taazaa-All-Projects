"""Verify the input guardrail rejects non-travel queries and accepts travel ones."""
from dotenv import load_dotenv
load_dotenv()

from src.guardrails import check_input_is_travel_related, REFUSAL_MESSAGE

SHOULD_ACCEPT = [
    "Plan a 5-day trip to Tokyo in October, ¥80,000, I like temples and food",
    "weekend in Paris on a budget, museums and pastries",
    "Where should I go in Europe in summer for cool weather?",
    "Help me plan a 10-day road trip through Iceland",
]

SHOULD_REJECT = [
    "Write me a Python script that scrapes Wikipedia",
    "What's 17 times 23?",
    "Tell me a joke about cats",
    "How do I bypass a paywall on the New York Times?",
    "Summarise the plot of Hamlet for me",
    "",
]

print("=== ACCEPT ===")
for q in SHOULD_ACCEPT:
    r = check_input_is_travel_related(q)
    status = "✓" if r.is_travel_request else "✗ FAIL"
    print(f"{status}  [{r.category}]  {q[:60]}")

print("\n=== REJECT ===")
for q in SHOULD_REJECT:
    r = check_input_is_travel_related(q)
    status = "✓" if not r.is_travel_request else "✗ FAIL"
    print(f"{status}  [{r.category}]  {q[:60] or '(empty)'}")

print("\nRefusal message that would be shown to the user:")
print(" ", REFUSAL_MESSAGE)
