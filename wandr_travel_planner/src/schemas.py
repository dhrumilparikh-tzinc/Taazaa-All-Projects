"""
Pydantic models used for structured LLM output and for shape-checking
the data passing between agents.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
#  Query parsing (parser.py — runs before the graph)
# --------------------------------------------------------------------------- #
class ParsedQuery(BaseModel):
    """Structured extraction of the user's natural-language travel request."""

    destination_city: str = Field(..., description="The city the user wants to visit")
    destination_country: Optional[str] = Field(
        None, description="Country name if user provided one; else infer from city"
    )
    trip_duration_days: int = Field(..., ge=1, le=60, description="Number of days")
    budget_amount: Optional[float] = Field(
        None, description="Total trip budget as a number, if provided"
    )
    budget_currency: Optional[str] = Field(
        None, description="ISO 4217 code (USD, JPY, INR, EUR, ...). None if unclear."
    )
    interests: list[str] = Field(
        default_factory=list, description="User's stated interests/themes"
    )
    travel_month: Optional[str] = Field(
        None, description="Month of travel if mentioned, else None"
    )


# --------------------------------------------------------------------------- #
#  Input guardrail (guardrails.py)
# --------------------------------------------------------------------------- #
class InputClassification(BaseModel):
    """Decision from the input guardrail about whether to proceed."""

    is_travel_request: bool = Field(
        ..., description="True only if the prompt is a genuine travel-planning request"
    )
    category: Literal[
        "travel_planning",
        "code_request",
        "general_chat",
        "harmful",
        "off_topic",
        "other",
    ] = Field(..., description="Best-guess category of the user's intent")
    reason: str = Field(..., description="One short sentence explaining the decision")


# --------------------------------------------------------------------------- #
#  Budget agent
# --------------------------------------------------------------------------- #
class BudgetCategory(BaseModel):
    name: Literal["accommodation", "food", "transport", "activities", "buffer"]
    daily_amount: float = Field(..., ge=0)
    description: str


class BudgetBreakdown(BaseModel):
    total_budget_native: float = Field(..., description="User's original budget")
    total_budget_native_currency: str
    total_budget_local: float = Field(..., description="Converted to destination currency")
    total_budget_local_currency: str
    exchange_rate_used: float
    duration_days: int
    daily_budget_local: float
    categories: list[BudgetCategory] = Field(..., min_length=4, max_length=5)
    notes: str = Field(..., description="One-line realism note for this destination")


# --------------------------------------------------------------------------- #
#  Itinerary agent
# --------------------------------------------------------------------------- #
class DaySegment(BaseModel):
    time: str = Field(..., description="Time range e.g. '9:00 AM – 11:30 AM'")
    period: Literal["early morning", "morning", "late morning", "lunch", "afternoon", "late afternoon", "evening"]
    activity: str = Field(..., description="What you're doing, 3-6 words")
    location: str = Field(..., description="A real, named place — not generic")
    description: str = Field(
        ..., description="2-3 rich sentences: what to see, what to do, what makes it special"
    )
    tips: Optional[str] = Field(None, description="Insider tip or practical advice for this stop")
    cost_note: Optional[str] = Field(None, description="Entry fee, meal cost, or 'Free'")


class ItineraryDay(BaseModel):
    day: int = Field(..., ge=1)
    theme: str = Field(..., description="Short evocative title for the day")
    highlights: list[str] = Field(
        ..., min_length=2, max_length=4,
        description="2-4 standout experiences of the day in one sentence each"
    )
    segments: list[DaySegment] = Field(..., min_length=3, max_length=6)
    transport_note: Optional[str] = Field(
        None, description="How to move between spots today (metro line, taxi, walking, etc.)"
    )


class Itinerary(BaseModel):
    destination: str
    days: list[ItineraryDay]
    summary: str


# --------------------------------------------------------------------------- #
#  Packing agent
# --------------------------------------------------------------------------- #
class PackingCategory(BaseModel):
    category: Literal["clothing", "documents", "gear", "toiletries", "electronics"]
    items: list[str] = Field(..., min_length=1)


class PackingList(BaseModel):
    destination: str
    duration_days: int
    weather_summary: str = Field(..., description="One-line summary of expected weather")
    categories: list[PackingCategory] = Field(..., min_length=3)


# --------------------------------------------------------------------------- #
#  Output guardrail — used to sanity-check LLM agent output
# --------------------------------------------------------------------------- #
class ValidationResult(BaseModel):
    is_valid: bool
    issues: list[str] = Field(default_factory=list)
    feedback_for_agent: str = Field(
        "", description="Short note the agent can use to fix its output on retry"
    )


# --------------------------------------------------------------------------- #
#  Destination overview written by the LLM (consumed by Trip Brief)
# --------------------------------------------------------------------------- #
class DestinationOverview(BaseModel):
    """A 2-paragraph LLM-written travel intro for the destination."""
    overview_paragraph_1: str
    overview_paragraph_2: str
