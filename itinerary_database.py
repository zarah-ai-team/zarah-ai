"""itinerary_database.py
Real-world itinerary templates and sample data for various destinations and trip types.
"""
from typing import Dict, List, Any

# Real-world itinerary templates by destination
ITINERARY_TEMPLATES = {
    "Dubai": {
        "3-day": {
            "title": "Dubai 3-Day Business & Leisure Mix",
            "destination": "Dubai, UAE",
            "duration_days": 3,
            "hotel_suggestions": [
                {"name": "JW Marriott Marquis", "type": "luxury", "price_range": "$250-350/night"},
                {"name": "Conrad Dubai", "type": "luxury", "price_range": "$200-300/night"},
                {"name": "Hilton Dubai Creek Harbour", "type": "mid-range", "price_range": "$120-180/night"},
                {"name": "Rove Downtown Dubai", "type": "budget", "price_range": "$60-100/night"},
            ],
            "days": [
                {
                    "day": 1,
                    "summary": "Arrival & Downtown Dubai exploration",
                    "activities": [
                        {"time": "14:00", "activity": "Check-in and rest at hotel", "price_inr": "₹0 (included)"},
                        {
                            "time": "18:00",
                            "activity": "Visit Burj Khalifa (At the Top: 148th floor)",
                            "price_inr": "₹4,500 per person",
                        },
                        {
                            "time": "20:00",
                            "activity": "Dinner at Noodle House or Emirates Lounge Restaurant",
                            "price_inr": "₹2,500-4,000 per person",
                        },
                    ],
                },
                {
                    "day": 2,
                    "summary": "Adventure & Beach Day",
                    "activities": [
                        {"time": "08:00", "activity": "Desert Safari with quad bike and dune bashing", "price_inr": "₹3,500 per person"},
                        {"time": "12:00", "activity": "Lunch at camp (BBQ)", "price_inr": "₹1,500 per person"},
                        {"time": "14:00", "activity": "Rest and beach time at Jumeirah Public Beach", "price_inr": "₹500 (parking)"},
                        {
                            "time": "18:00",
                            "activity": "Visit Dubai Mall and shopping",
                            "price_inr": "₹2,000 (estimated shopping)",
                        },
                    ],
                },
                {
                    "day": 3,
                    "summary": "Departure Day & Last-Minute Activities",
                    "activities": [
                        {"time": "09:00", "activity": "Breakfast at hotel", "price_inr": "₹500 per person"},
                        {"time": "10:00", "activity": "Gold Souk and Spice Market tour", "price_inr": "₹1,000 (guided tour)"},
                        {
                            "time": "13:00",
                            "activity": "Lunch at local restaurant in Al Fahidi district",
                            "price_inr": "₹1,500 per person",
                        },
                        {"time": "15:00", "activity": "Depart for airport", "price_inr": "₹1,500 (taxi)"},
                    ],
                },
            ],
            "cost_breakdown": {
                "accommodation": {"range": "₹6,000-21,000 per night (3 nights)"},
                "activities": "₹19,500-26,000",
                "food": "₹8,000-12,000",
                "transport": "₹3,000-5,000",
                "total_estimated": "₹36,500-64,000 (per pax)",
            },
        },
        "5-day": {
            "title": "Dubai 5-Day Premium Experience",
            "destination": "Dubai, UAE",
            "duration_days": 5,
            "hotel_suggestions": [
                {"name": "Burj Al Arab", "type": "ultra-luxury", "price_range": "$500-800/night"},
                {"name": "Emirates Palace", "type": "luxury", "price_range": "$300-500/night"},
            ],
            "days": [
                {
                    "day": 1,
                    "summary": "Arrival & Iconic Landmarks",
                    "activities": [
                        {"time": "14:00", "activity": "Arrival and hotel check-in", "price_inr": "₹0"},
                        {"time": "18:00", "activity": "Burj Khalifa viewing (dinner option)", "price_inr": "₹5,000-8,000"},
                        {"time": "20:30", "activity": "Welcome dinner at hotel", "price_inr": "₹3,000-5,000"},
                    ],
                },
                {
                    "day": 2,
                    "summary": "Beach & Water Sports",
                    "activities": [
                        {"time": "09:00", "activity": "Jetski or Parasailing at Jumeirah Beach", "price_inr": "₹4,500 per person"},
                        {"time": "12:30", "activity": "Lunch at beachfront restaurant", "price_inr": "₹2,500 per person"},
                        {"time": "14:30", "activity": "Aquarium and Underwater Zoo", "price_inr": "₹2,000 per person"},
                        {"time": "19:00", "activity": "Dhow Cruise with dinner", "price_inr": "₹3,500 per person"},
                    ],
                },
                {
                    "day": 3,
                    "summary": "Cultural Immersion",
                    "activities": [
                        {"time": "08:00", "activity": "Sheikh Mohammed Centre for Cultural Understanding tour", "price_inr": "₹1,500"},
                        {"time": "10:00", "activity": "Al Fahidi Heritage District walking tour", "price_inr": "₹800"},
                        {"time": "12:00", "activity": "Lunch at traditional Emirati restaurant", "price_inr": "₹2,000"},
                        {"time": "15:00", "activity": "Dubai Museum visit", "price_inr": "₹500 per person"},
                        {"time": "18:00", "activity": "Evening at Gold Souk and Spice Market", "price_inr": "₹1,500"},
                    ],
                },
                {
                    "day": 4,
                    "summary": "Shopping & Relaxation",
                    "activities": [
                        {"time": "09:00", "activity": "Dubai Shopping Festival (seasonal) or Dubai Mall", "price_inr": "₹3,000-5,000"},
                        {"time": "13:00", "activity": "Lunch at upscale mall restaurant", "price_inr": "₹2,500"},
                        {"time": "15:00", "activity": "Spa at hotel or Talise Spa", "price_inr": "₹3,000-4,000 per person"},
                        {"time": "19:00", "activity": "Fine Dining at 3 Michelin-star restaurant", "price_inr": "₹6,000-8,000"},
                    ],
                },
                {
                    "day": 5,
                    "summary": "Departure",
                    "activities": [
                        {"time": "09:00", "activity": "Hotel checkout and light breakfast", "price_inr": "₹500"},
                        {"time": "10:00", "activity": "Last-minute shopping or spa", "price_inr": "₹1,000"},
                        {"time": "14:00", "activity": "Airport transfer", "price_inr": "₹1,500"},
                    ],
                },
            ],
            "cost_breakdown": {
                "accommodation": {"range": "₹30,000-60,000 per night (5 nights)"},
                "activities": "₹25,000-40,000",
                "food": "₹15,000-25,000",
                "transport": "₹3,000-5,000",
                "total_estimated": "₹73,000-130,000 (per pax)",
            },
        },
    },
    "Abu Dhabi": {
        "3-day": {
            "title": "Abu Dhabi 3-Day Iconic Experience",
            "destination": "Abu Dhabi, UAE",
            "duration_days": 3,
            "hotel_suggestions": [
                {"name": "Emirates Palace", "type": "ultra-luxury", "price_range": "$300-500/night"},
                {"name": "Park Hyatt Abu Dhabi", "type": "luxury", "price_range": "$200-350/night"},
                {"name": "Radisson Blu", "type": "mid-range", "price_range": "$100-150/night"},
            ],
            "days": [
                {
                    "day": 1,
                    "summary": "Arrival & Grand Mosque",
                    "activities": [
                        {"time": "14:00", "activity": "Hotel check-in", "price_inr": "₹0"},
                        {"time": "16:00", "activity": "Sheikh Zayed Grand Mosque tour (evening light show)", "price_inr": "₹1,500"},
                        {"time": "19:00", "activity": "Dinner at traditional Emirati restaurant", "price_inr": "₹2,500 per person"},
                    ],
                },
                {
                    "day": 2,
                    "summary": "Culture & Heritage",
                    "activities": [
                        {"time": "09:00", "activity": "Emirates Heritage Society & Palace tour", "price_inr": "₹2,000"},
                        {"time": "11:30", "activity": "Qasr Al Watan (Presidential Palace)", "price_inr": "₹2,500"},
                        {
                            "time": "13:00",
                            "activity": "Lunch at Corniche restaurant",
                            "price_inr": "₹2,000 per person",
                        },
                        {"time": "15:00", "activity": "Ferrari World Abu Dhabi (optional)", "price_inr": "₹4,500 per person"},
                    ],
                },
                {
                    "day": 3,
                    "summary": "Beach & Shopping",
                    "activities": [
                        {"time": "09:00", "activity": "Breakfast at hotel", "price_inr": "₹500"},
                        {
                            "time": "10:00",
                            "activity": "Saadiyat Beach Club or Public Beach visit",
                            "price_inr": "₹1,500",
                        },
                        {"time": "12:00", "activity": "Lunch at beach shack", "price_inr": "₹1,500 per person"},
                        {"time": "14:00", "activity": "Abu Dhabi Mall shopping", "price_inr": "₹2,000 (estimated)"},
                    ],
                },
            ],
            "cost_breakdown": {
                "accommodation": {"range": "₹9,000-30,000 per night (3 nights)"},
                "activities": "₹10,500-17,500",
                "food": "₹8,000-12,000",
                "transport": "₹2,000-3,000",
                "total_estimated": "₹29,500-62,500 (per pax)",
            },
        },
    },
    "London": {
        "4-day": {
            "title": "London 4-Day Classic Tour",
            "destination": "London, UK",
            "duration_days": 4,
            "hotel_suggestions": [
                {"name": "The Ritz London", "type": "ultra-luxury", "price_range": "$400-600/night"},
                {"name": "Claridge's", "type": "luxury", "price_range": "$300-450/night"},
                {"name": "Premier Inn Central", "type": "budget", "price_range": "$80-120/night"},
            ],
            "days": [
                {
                    "day": 1,
                    "summary": "Arrival & Westminster",
                    "activities": [
                        {"time": "14:00", "activity": "Hotel check-in", "price_inr": "₹0"},
                        {"time": "15:30", "activity": "Westminster Abbey tour", "price_inr": "₹2,500"},
                        {"time": "17:00", "activity": "Big Ben & Houses of Parliament viewing", "price_inr": "₹0 (external view)"},
                        {"time": "19:00", "activity": "Thames River cruise with dinner", "price_inr": "₹4,000 per person"},
                    ],
                },
                {
                    "day": 2,
                    "summary": "Royal London",
                    "activities": [
                        {
                            "time": "10:00",
                            "activity": "Buckingham Palace & Changing of the Guard ceremony",
                            "price_inr": "₹1,500 per person",
                        },
                        {"time": "12:00", "activity": "Royal Parks walk (St. James's Park)", "price_inr": "₹0"},
                        {"time": "13:00", "activity": "Lunch at traditional pub", "price_inr": "₹2,000 per person"},
                        {"time": "14:30", "activity": "Tower of London & Crown Jewels", "price_inr": "₹3,500 per person"},
                        {"time": "18:00", "activity": "Tower Bridge visit", "price_inr": "₹1,500"},
                    ],
                },
                {
                    "day": 3,
                    "summary": "Museums & Culture",
                    "activities": [
                        {"time": "10:00", "activity": "British Museum (highlights tour)", "price_inr": "₹1,500"},
                        {"time": "12:30", "activity": "Lunch at Covent Garden", "price_inr": "₹2,500 per person"},
                        {
                            "time": "14:00",
                            "activity": "National Gallery or Tate Modern art museums",
                            "price_inr": "₹1,000 per person",
                        },
                        {"time": "18:00", "activity": "West End Theatre show (dinner & show)", "price_inr": "₹6,000-10,000 per person"},
                    ],
                },
                {
                    "day": 4,
                    "summary": "Shopping & Departure",
                    "activities": [
                        {"time": "09:00", "activity": "Breakfast at hotel", "price_inr": "₹500"},
                        {"time": "10:00", "activity": "Oxford Street or Harrods shopping", "price_inr": "₹3,000-5,000"},
                        {"time": "13:00", "activity": "Farewell lunch", "price_inr": "₹2,500"},
                        {"time": "15:00", "activity": "Airport transfer", "price_inr": "₹2,000"},
                    ],
                },
            ],
            "cost_breakdown": {
                "accommodation": {"range": "₹9,000-45,000 per night (4 nights)"},
                "activities": "₹18,000-29,000",
                "food": "₹10,000-16,000",
                "transport": "₹4,000-6,000",
                "total_estimated": "₹41,000-96,000 (per pax)",
            },
        },
    },
    "Paris": {
        "3-day": {
            "title": "Paris 3-Day Romantic Getaway",
            "destination": "Paris, France",
            "duration_days": 3,
            "hotel_suggestions": [
                {"name": "Ritz Paris", "type": "ultra-luxury", "price_range": "$500-800/night"},
                {"name": "Four Seasons Paris", "type": "luxury", "price_range": "$400-600/night"},
                {"name": "Hotel des Invalides", "type": "mid-range", "price_range": "$100-180/night"},
            ],
            "days": [
                {
                    "day": 1,
                    "summary": "Arrival & Eiffel Tower",
                    "activities": [
                        {"time": "14:00", "activity": "Hotel check-in in Marais or near Louvre", "price_inr": "₹0"},
                        {"time": "16:00", "activity": "Eiffel Tower summit visit with sunset views", "price_inr": "₹4,500 per person"},
                        {"time": "19:00", "activity": "Dinner at Michelin-starred bistro", "price_inr": "₹5,000 per person"},
                    ],
                },
                {
                    "day": 2,
                    "summary": "Art & Culture",
                    "activities": [
                        {"time": "09:00", "activity": "Louvre Museum (skip-the-line Mona Lisa tour)", "price_inr": "₹3,500 per person"},
                        {"time": "12:30", "activity": "Lunch at traditional French café", "price_inr": "₹2,500 per person"},
                        {
                            "time": "14:00",
                            "activity": "Notre-Dame Cathedral & Sainte-Chapelle",
                            "price_inr": "₹2,000 per person",
                        },
                        {"time": "17:00", "activity": "Montmartre & Sacré-Cœur walking tour", "price_inr": "₹1,500"},
                        {"time": "19:30", "activity": "Dinner & Moulin Rouge show", "price_inr": "₹6,000-8,000 per person"},
                    ],
                },
                {
                    "day": 3,
                    "summary": "Versailles Day Trip",
                    "activities": [
                        {"time": "08:00", "activity": "Train to Palace of Versailles", "price_inr": "₹300"},
                        {"time": "09:00", "activity": "Palace & gardens full day tour", "price_inr": "₹4,000 per person"},
                        {"time": "13:00", "activity": "Lunch at Versailles restaurant", "price_inr": "₹2,500 per person"},
                        {"time": "16:00", "activity": "Return to Paris", "price_inr": "₹300"},
                    ],
                },
            ],
            "cost_breakdown": {
                "accommodation": {"range": "₹9,000-60,000 per night (3 nights)"},
                "activities": "₹17,300-24,000",
                "food": "₹10,000-15,000",
                "transport": "₹1,000-2,000",
                "total_estimated": "₹37,300-101,000 (per pax)",
            },
        },
    },
}


def get_itinerary_template(destination: str, duration: str = None) -> Dict[str, Any]:
    """Get an itinerary template for a destination."""
    dest_lower = destination.lower()
    for dest_key in ITINERARY_TEMPLATES.keys():
        if dest_lower in dest_key.lower():
            if duration:
                dur_key = f"{duration}-day"
                if dur_key in ITINERARY_TEMPLATES[dest_key]:
                    return ITINERARY_TEMPLATES[dest_key][dur_key]
            # Return first available template for destination
            return next(iter(ITINERARY_TEMPLATES[dest_key].values()))
    return {}


def list_available_destinations() -> List[str]:
    """List all destinations with templates."""
    return list(ITINERARY_TEMPLATES.keys())


def list_durations_for_destination(destination: str) -> List[str]:
    """List available durations for a destination."""
    dest_lower = destination.lower()
    for dest_key in ITINERARY_TEMPLATES.keys():
        if dest_lower in dest_key.lower():
            return [k.replace("-day", "") for k in ITINERARY_TEMPLATES[dest_key].keys()]
    return []
