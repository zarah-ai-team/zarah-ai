from __future__ import annotations
from pydantic import BaseModel, validator
from typing import Optional, List, Dict, Any
from datetime import date
from enum import Enum


class HotelCategory(str, Enum):
    THREE_STAR = "3_star"
    FOUR_STAR = "4_star"
    FOUR_STAR_DELUXE = "4_star_deluxe"
    FIVE_STAR = "5_star"


class TransportPreference(str, Enum):
    PRIVATE_VAN = "private_van"
    PRIVATE_CAR = "private_car"
    SHARED_TRANSFER = "shared_transfer"
    SIC = "sic"


class Pace(str, Enum):
    RELAXED = "relaxed"
    MODERATE = "moderate"
    ACTIVE = "active"


class WalkingTolerance(str, Enum):
    MINIMAL = "minimal"
    MODERATE = "moderate"
    HIGH = "high"


class RoomConfig(BaseModel):
    double_rooms: int = 0
    twin_rooms: int = 0
    triple_rooms: int = 0
    single_rooms: int = 0

    @property
    def total_rooms(self) -> int:
        return self.double_rooms + self.twin_rooms + self.triple_rooms + self.single_rooms


class TravelerProfile(BaseModel):
    total_adults: int
    seniors_count: int = 0
    children_count: int = 0
    has_mobility_issues: bool = False

    @property
    def non_senior_adults(self) -> int:
        return self.total_adults - self.seniors_count

    @property
    def is_senior_group(self) -> bool:
        return self.seniors_count > 0


class RouteSegment(BaseModel):
    from_city: str
    to_city: str
    travel_mode: str = "private_van"
    estimated_duration_hours: Optional[float] = None
    distance_km: Optional[float] = None


class TripRequest(BaseModel):
    """Raw, unvalidated client input — can be free text or partial structured fields."""
    client_name: Optional[str] = None
    raw_text: Optional[str] = None

    origin: Optional[str] = None
    destinations: Optional[List[str]] = None
    route: Optional[str] = None
    trip_start_date: Optional[str] = None
    total_nights: Optional[int] = None

    adults: Optional[int] = None
    seniors: Optional[int] = None
    children: Optional[int] = None

    room_config: Optional[Dict[str, int]] = None
    hotel_category: Optional[str] = None

    transport_preference: Optional[str] = None
    driver_preference: Optional[str] = None

    pace: Optional[str] = None
    walking_tolerance: Optional[str] = None
    guide_required: Optional[bool] = None
    meal_preferences: Optional[List[str]] = None
    budget_preference: Optional[str] = None

    mandatory_sightseeing: Optional[List[str]] = None
    optional_excursions: Optional[List[str]] = None
    departure_details: Optional[str] = None

    session_id: Optional[str] = None

    class Config:
        extra = "allow"


class TripRequirements(BaseModel):
    """Canonical, normalized trip requirements produced by the normalization layer."""
    request_id: str
    client_name: Optional[str] = None

    origin: str
    destinations: List[str]
    route_segments: List[RouteSegment] = []

    trip_start_date: Optional[date] = None
    trip_end_date: Optional[date] = None
    total_nights: int

    traveler_profile: TravelerProfile
    room_config: RoomConfig

    hotel_category: HotelCategory = HotelCategory.FOUR_STAR_DELUXE
    hotel_preference_notes: List[str] = []

    transport_preference: TransportPreference = TransportPreference.PRIVATE_VAN
    vehicle_type: str = "Mercedes Viano or similar"
    driver_preference: Optional[str] = None

    pace: Pace = Pace.RELAXED
    walking_tolerance: WalkingTolerance = WalkingTolerance.MINIMAL
    guide_required: bool = False
    meal_preferences: List[str] = []
    budget_level: str = "mid-high"

    mandatory_sightseeing: List[str] = []
    optional_excursions: List[str] = []

    needs_senior_friendly: bool = False
    needs_minimal_walking: bool = False
    needs_private_transport: bool = True
    needs_city_centre_hotel: bool = False

    raw_input: Optional[str] = None
    confidence: float = 1.0
    missing_fields: List[str] = []
    assumptions_made: List[str] = []
