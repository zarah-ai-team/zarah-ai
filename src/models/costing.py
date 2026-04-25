from __future__ import annotations
from pydantic import BaseModel
from typing import Optional, List, Dict
from enum import Enum


class SourceType(str, Enum):
    KB_EXACT = "kb_exact"
    KB_ESTIMATED = "kb_estimated"
    WEB_REFERENCE = "web_reference"
    FALLBACK_RULE = "fallback_rule"
    NOT_AVAILABLE = "not_available"


class CostLine(BaseModel):
    category: str
    description: str
    unit_cost: float
    quantity: float = 1.0
    total_cost: float
    currency: str = "USD"
    source_type: SourceType
    source_ref: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None


class CostBreakdown(BaseModel):
    accommodation: List[CostLine] = []
    transport: List[CostLine] = []
    sightseeing: List[CostLine] = []
    guide_fees: List[CostLine] = []
    meals: List[CostLine] = []
    miscellaneous: List[CostLine] = []

    @property
    def total(self) -> float:
        all_lines = (
            self.accommodation + self.transport + self.sightseeing
            + self.guide_fees + self.meals + self.miscellaneous
        )
        return round(sum(line.total_cost for line in all_lines), 2)

    def to_summary(self) -> Dict[str, float]:
        return {
            "accommodation": round(sum(l.total_cost for l in self.accommodation), 2),
            "transport": round(sum(l.total_cost for l in self.transport), 2),
            "sightseeing": round(sum(l.total_cost for l in self.sightseeing), 2),
            "guide_fees": round(sum(l.total_cost for l in self.guide_fees), 2),
            "meals": round(sum(l.total_cost for l in self.meals), 2),
            "miscellaneous": round(sum(l.total_cost for l in self.miscellaneous), 2),
            "total": self.total,
        }

    def all_lines(self) -> List[CostLine]:
        return (
            self.accommodation + self.transport + self.sightseeing
            + self.guide_fees + self.meals + self.miscellaneous
        )
