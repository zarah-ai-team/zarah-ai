# Full-Day Itinerary Enhancement

## Changes Made

Updated the LLM system and user prompts in `app.py` to ensure leisure itineraries cover the FULL DAY with specific time slots:

### Time Blocks Added:
- **Morning (7:00 AM - 11:00 AM)**: Breakfast + early sightseeing or relaxation
- **Afternoon (12:00 PM - 5:00 PM)**: Main attractions, cultural sites, shopping, adventure activities  
- **Evening (6:00 PM - 9:00 PM)**: Dinner, local restaurants, evening strolls, entertainment, shows
- **Night (9:00 PM - 11:00 PM)**: Optional nightlife, bars, lounges, night markets, or hotel relaxation

### Specific Requirements Added:
✓ For each activity, specify exact TIME with format (e.g., '10:00 AM - 12:00 PM')
✓ Include dinner recommendations and evening entertainment
✓ Include cultural performances, shows, lounges, night markets
✓ Full-day itineraries for each day of the trip
✓ Prices in INR (₹) for all activities

### Impact:
- Leisure itineraries will now include 8-10 activities per day instead of 4-5
- Evening and night activities explicitly required
- Better utilization of guest time
- More realistic and comprehensive travel plans

### Testing:
Send a leisure request (e.g., Oman trip) and verify the itinerary includes:
- Morning breakfast/activity (7-11am)
- Afternoon main attractions (12-5pm)
- Evening dinner/entertainment (6-9pm)
- Night activities or relaxation (9-11pm)

Each with specific times and prices.
