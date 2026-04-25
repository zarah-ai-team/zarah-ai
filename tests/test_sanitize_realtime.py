import app


def test_sanitize_empty():
    out = app.sanitize_realtime_payload(None)
    assert isinstance(out, dict)
    assert out["wikipedia"] == {}
    assert out["attractions"] == []
    assert out["news"] == []


def test_sanitize_partial():
    raw = {
        "wikipedia": {"title": "Oman", "extract": "A" * 2000},
        "attractions": [{"name": "Mutrah Souq", "category": "market", "description": "Old souq"}],
        "news": [{"title": "Event", "url": "http://example.com"}]
    }
    out = app.sanitize_realtime_payload(raw)
    assert len(out["wikipedia"].get("extract", "")) <= 800
    assert len(out["attractions"]) == 1
    assert "Mutrah" in out["attractions"][0]
    assert len(out["news"]) == 1
