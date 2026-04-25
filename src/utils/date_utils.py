from datetime import date, timedelta
from typing import List


def get_trip_dates(start: date, total_nights: int) -> List[date]:
    return [start + timedelta(days=i) for i in range(total_nights + 1)]


def format_display(d: date) -> str:
    return d.strftime("%A, %d %B %Y")


def days_between(start: date, end: date) -> int:
    return (end - start).days


def is_peak_season(d: date, destination: str) -> bool:
    dest = destination.lower()
    if dest in ("prague", "vienna", "budapest"):
        return d.month in (6, 7, 8) or (d.month == 12 and d.day >= 20)
    return False
