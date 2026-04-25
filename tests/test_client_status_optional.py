from conversation_manager import ConversationManager


def test_client_status_not_required():
    cm = ConversationManager()
    fields = {
        'destination':'Oman',
        'duration':3,
        'pax':2,
        'event_type':'leisure',
        'hotel_type':'mid-range',
        'client_industry':'technology',
        'client_type':'corporate'
    }
    assert cm.next_missing_field(fields) is None


def test_update_does_not_prompt_client_status():
    cm = ConversationManager()
    session = {'fields': {}, 'history': []}
    # Fill everything except client_status via message
    msg = "Destination: Oman\nDuration: 3 days\nPax: 2\nEvent_type: leisure\nHotel_type: mid-range\nClient_industry: technology\nClient_type: corporate"
    res = cm.update(session, msg)
    assert res.get('need_more') in (False, None)
    assert 'client_status' not in session['fields']
