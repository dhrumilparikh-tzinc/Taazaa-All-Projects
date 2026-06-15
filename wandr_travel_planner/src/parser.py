"""
Parse the user's free-text travel request into structured fields.

This runs BEFORE the LangGraph supervisor — its output populates the
"Does this look right?" confirmation screen, where the user can edit
city, country, duration, budget, and interests before planning starts.
"""
from __future__ import annotations

import os

from langchain_groq import ChatGroq

from .logger import get_logger, groq_model
from .schemas import ParsedQuery

log = get_logger("parser")

PARSE_PROMPT = """\
You are a query parser for a travel planner. Extract structured travel
intent from the user's free-text request.

Rules:
- destination_city: the specific city the user wants to visit (required).
- destination_country: country name. If the user didn't say, infer from
  the city (e.g. "Tokyo" -> "Japan"). If genuinely ambiguous, leave null.
- trip_duration_days: integer days. If the user says "weekend" use 2,
  "long weekend" use 3, "a week" use 7.
- budget_amount: numeric amount only. Strip commas and currency symbols.
- budget_currency: ISO 4217 code (USD, JPY, INR, EUR, GBP, ...). Infer
  from the symbol: $ -> USD, ¥ -> JPY, ₹ -> INR, € -> EUR, £ -> GBP.
  If the user used a symbol that fits multiple currencies (e.g. $) and
  context doesn't disambiguate, pick the most likely one given the
  destination country.
- interests: short noun phrases the user mentioned, e.g. ["temples",
  "food", "photography"]. Lowercase. Empty list if none mentioned.
- travel_month: month name if mentioned, else null.

User request:
\"\"\"{query}\"\"\"

Return your answer in the required structured format.
"""


def parse_query(user_query: str) -> ParsedQuery:
    """Run Gemini with structured output to extract trip parameters."""
    log.info("Parsing query (%d chars)", len(user_query))

    llm = ChatGroq(
        model=groq_model(),
        temperature=0.0,
        groq_api_key=os.getenv("GROQ_API_KEY"),
    ).with_structured_output(ParsedQuery)

    parsed: ParsedQuery = llm.invoke(PARSE_PROMPT.format(query=user_query))
    log.info(
        "Parsed: city=%s country=%s days=%s budget=%s %s interests=%s",
        parsed.destination_city,
        parsed.destination_country,
        parsed.trip_duration_days,
        parsed.budget_amount,
        parsed.budget_currency,
        parsed.interests,
    )
    return parsed
