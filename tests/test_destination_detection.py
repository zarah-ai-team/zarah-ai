from conversation_manager import ConversationManager


def test_does_not_pick_meal_as_destination():
    cm = ConversationManager()
    res = cm.detect_fields_in_text("Meal for 2, please arrange")
    assert "destination" not in res


def test_picks_known_country_oman():
    cm = ConversationManager()
    res = cm.detect_fields_in_text("We want to travel to Oman next month")
    assert res.get("destination") and "oman" in res.get("destination").lower()


def test_picks_multiword_city_new_york():
    cm = ConversationManager()
    res = cm.detect_fields_in_text("I want to go to New York for a conference")
    assert res.get("destination") and "new york" in res.get("destination").lower()
