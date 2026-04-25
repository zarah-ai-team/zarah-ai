from __future__ import annotations
from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class MealPlan(BaseModel):
    breakfast: Optional[str] = None
    lunch: Optional[str] = None
    dinner: Optional[str] = None


class TransportDetail(BaseModel):
    type: str
    description: str
    duration: Optional[str] = None
    notes: Optional[str] = None


class HotelSuggestion(BaseModel):
    name: Optional[str] = None
    area: str
    category: str
    check_in: Optional[str] = None
    check_out: Optional[str] = None
    notes: Optional[str] = None


class DayItinerary(BaseModel):
    day_number: int
    date: Optional[str] = None
    city: str
    title: str
    morning: str
    afternoon: str
    evening: str
    meals: MealPlan = MealPlan()
    transport: Optional[TransportDetail] = None
    walking_level: str = "minimal"
    senior_friendly_notes: Optional[str] = None
    hotel: Optional[HotelSuggestion] = None
    estimated_day_cost: Optional[float] = None
    inclusions: List[str] = []
    exclusions: List[str] = []


class OptionalExperience(BaseModel):
    name: str
    city: str
    description: str
    duration: str
    estimated_cost: Optional[float] = None
    suitable_for_seniors: bool = True
    walking_level: str = "minimal"
    booking_notes: Optional[str] = None


class ConfidenceSummary(BaseModel):
    overall: float
    costing: float
    routing: float
    hotel_suggestions: float
    sightseeing: float
    notes: List[str] = []


class ItineraryOutput(BaseModel):
    title: str
    trip_overview: str
    assumptions: List[str]
    total_estimated_cost: float
    cost_per_person: float
    currency: str = "USD"
    cost_breakdown_summary: Dict[str, float]
    days: List[Any] = []
    optional_experiences: List[Any] = []
    important_notes: List[str] = []
    missing_information: List[str] = []
    confidence_summary: ConfidenceSummary
    sources_summary: List[str] = []


class ApiResponse(BaseModel):
    request_id: str
    status: str = "success"
    normalized_input: Dict[str, Any]
    itinerary: ItineraryOutput
    cost_breakdown: Dict[str, float]
    assumptions: List[str]
    missing_fields: List[str]
    research_sources: List[str]
    kb_sources: List[str]
    generated_at: str
    processing_time_ms: int
    pipeline_stages: Dict[str, int]
