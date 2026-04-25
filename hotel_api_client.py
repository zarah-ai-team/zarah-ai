"""hotel_api_client.py
Optional placeholder for integrating an external hotel API (e.g., RapidAPI / Booking.com).
By default the code is commented to avoid requiring API keys.
"""
import os
import requests
from typing import List, Dict, Any


class HotelAPIClient:
    """Flexible hotel API client.

    Behavior:
    - If HOTEL_API_PROVIDER=rapidapi and RAPIDAPI_KEY + RAPIDAPI_HOST + RAPIDAPI_HOTELS_URL are set, use RapidAPI booking endpoint.
    - Otherwise fall back to a local heuristic/mock provider that fabricates reasonable per-night prices based on budget.
    """

    def __init__(self, provider: str | None = None, api_key: str | None = None, rapidapi_host: str | None = None, rapidapi_url: str | None = None):
        # Do not default to any mock provider. To use live hotels set HOTEL_API_PROVIDER=rapidapi
        self.provider = provider or os.getenv("HOTEL_API_PROVIDER")
        self.api_key = api_key or os.getenv("RAPIDAPI_KEY")
        self.rapidapi_host = rapidapi_host or os.getenv("RAPIDAPI_HOST")
        self.rapidapi_url = rapidapi_url or os.getenv("RAPIDAPI_HOTELS_URL")

    def _call_rapidapi(
        self,
        destination: str = None,
        checkin: str = None,
        checkout: str = None,
        adults: int = 2,
        children: int | None = None,
        children_ages: str | None = None,
        units: str = "metric",
        page_number: int = 0,
        categories_filter_ids: str | None = None,
        dest_type: str | None = None,
        dest_id: int | None = None,
        order_by: str = "popularity",
        include_adjacency: bool | None = None,
        room_number: int = 1,
        filter_by_currency: str | None = None,
        locale: str = "en-gb",
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        # Ensure API credentials are present
        if not (self.api_key and self.rapidapi_host and self.rapidapi_url):
            return []
        headers = {"X-RapidAPI-Key": self.api_key, "X-RapidAPI-Host": self.rapidapi_host}

        # Build params according to the endpoint's documented query params
        params: Dict[str, Any] = {
            "adults_number": int(adults) if adults is not None else 2,
            "units": units or "metric",
            "page_number": int(page_number) if page_number is not None else 0,
            "checkin_date": checkin,
            "checkout_date": checkout,
            "room_number": int(room_number) if room_number is not None else 1,
            "order_by": order_by or "popularity",
            "dest_type": dest_type,
            "dest_id": int(dest_id) if dest_id is not None else None,
            "rows": int(limit),
            "children_number": int(children) if children is not None else None,
            "children_ages": children_ages,
            "categories_filter_ids": categories_filter_ids,
            "include_adjacency": ("true" if include_adjacency else "false") if include_adjacency is not None else None,
            "filter_by_currency": filter_by_currency,
            "locale": locale or "en-gb",
        }

        # Remove None values to keep query string clean
        params = {k: v for k, v in params.items() if v is not None}

        # If the endpoint expects a textual destination name instead of dest_id, include it
        if destination and "dest_id" not in params:
            params["destination"] = destination

        import logging
        logger = logging.getLogger("uvicorn.error")
        hotels: List[Dict[str, Any]] = []
        try:
            r = requests.get(self.rapidapi_url, headers=headers, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            logger.info(f"[HotelAPIClient] RapidAPI raw response: {str(data)[:2000]}")

            # Parse hotels with all required details
            if isinstance(data, dict):
                for key in ["result", "hotels", "search_results", "data"]:
                    items = data.get(key)
                    if isinstance(items, list):
                        for it in items[:limit]:
                            price = it.get("min_total_price")
                            if not price or price == 0:
                                price = (
                                    it.get("composite_price_breakdown", {})
                                    .get("gross_amount_hotel_currency", {})
                                    .get("value")
                                )
                            currency = it.get("currencycode") or (
                                it.get("composite_price_breakdown", {})
                                .get("gross_amount_hotel_currency", {})
                                .get("currency")
                            )
                            hotels.append({
                                "name": it.get("hotel_name_trans") or it.get("hotel_name"),
                                "address": it.get("address_trans") or it.get("address"),
                                "city": it.get("city_trans") or it.get("city"),
                                "district": it.get("district") or it.get("district_id"),
                                "review_score": it.get("review_score"),
                                "review_score_word": it.get("review_score_word"),
                                "price": price,
                                "currency": currency,
                                "photo_url": it.get("main_photo_url") or it.get("max_photo_url"),
                                "booking_url": it.get("url"),
                                "distance_to_center": it.get("distance_to_cc_formatted"),
                                "free_cancellation": bool(it.get("is_free_cancellable")),
                                "no_prepayment": bool(it.get("is_no_prepayment_block")),
                                "breakfast_included": it.get("ribbon_text"),
                                "badges": it.get("badges", []),
                                "accommodation_type": it.get("accommodation_type_name"),
                                "review_count": it.get("review_nr"),
                            })
                        if hotels:
                            break
            logger.info(f"[HotelAPIClient] Parsed hotels: {hotels}")
            return hotels[:limit]
        except Exception as e:
            logger.error(f"[HotelAPIClient] RapidAPI call failed: {e}")
            return []

    # Removed mock/fallback hotel generation — live API required for hotel results.
    # If you need an offline mode, implement a separate adapter explicitly and opt-in.

    def search_hotels(
        self,
        destination: str = None,
        checkin: str = None,
        checkout: str = None,
        adults: int = 2,
        limit: int = 5,
        budget_per_person: float | None = None,
        # advanced query params supported by some RapidAPI hotel endpoints
        children: int | None = None,
        children_ages: str | None = None,
        units: str = "metric",
        page_number: int = 0,
        categories_filter_ids: str | None = None,
        dest_type: str | None = None,
        dest_id: int | None = None,
        order_by: str = "popularity",
        include_adjacency: bool | None = None,
        room_number: int = 1,
        filter_by_currency: str | None = None,
        locale: str = "en-gb",
    ) -> List[Dict[str, Any]]:
        """Search for hotels. Returns a list of hotels with name, price_per_night and currency.

        This wrapper keeps backward compatibility but also exposes the common
        RapidAPI query params (dest_id/dest_type, children, children_ages, checkin/checkout, etc.).
        """
        if not (self.provider and self.provider.lower() == "rapidapi"):
            raise RuntimeError("Hotel API provider not configured. Set HOTEL_API_PROVIDER=rapidapi and RAPIDAPI_* env vars to enable live hotel searches.")
        # Proceed with RapidAPI call
        if self.provider and self.provider.lower() == "rapidapi":
            # The RapidAPI endpoint supports many query params. For backward compatibility
            # we pass the basic ones here. Callers may call _call_rapidapi directly for advanced searches.
            results = self._call_rapidapi(
                destination=destination,
                checkin=checkin,
                checkout=checkout,
                adults=adults,
                children=children,
                children_ages=children_ages,
                units=units,
                page_number=page_number,
                categories_filter_ids=categories_filter_ids,
                dest_type=dest_type,
                dest_id=dest_id,
                order_by=order_by,
                include_adjacency=include_adjacency,
                room_number=room_number,
                filter_by_currency=filter_by_currency,
                locale=locale,
                limit=limit,
            )
            if results:
                return results
            # If no results returned from the provider treat as an error in live-only mode
            raise RuntimeError("Hotel API call returned no results")


__all__ = ["HotelAPIClient"]
