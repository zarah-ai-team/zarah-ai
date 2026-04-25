from conversation_manager import ConversationManager


def test_existing_session_does_not_ask_client_status():
    cm = ConversationManager()
    # fields similar to the user's stuck session
    fields = {
        "duration": 4,
        "nights": 3,
        "pax": 4,
        "budget_per_person": 85000.0,
        "budget_currency": "INR",
        "event_type": "anniversary",
        "activities": ["Sightseeing"],
        "hotel_type": "luxury",
        "meal_preference": "vegetarian",
        "checkin_date": "March 2026",
        "checkout_date": "March 2026",
        "destination": "Singapore",
        "transport_private": True,
        "client_industry": "other",
        "client_type": "dmc",
    }
    assert cm.next_missing_field(fields) is None
