"""Change detection stays quiet on idle polling and distinguishes reports from status changes."""
from copy import deepcopy
from uuid import uuid4

from streamlit.testing.v1 import AppTest

import infrastructure as db


def test_live_activity_baseline_changes_and_unchanged_polls(monkeypatch):
    pipes = [dict(id=uuid4(), name='Demo <school> & pump', village='Fictional Alero',
        status='operational', status_observed_at=None, latest_report_id=None,
        needs_verification=True, latitude=None, longitude=None, description='Synthetic asset.', report_count=1)]
    monkeypatch.setattr(db, 'get_pipes', lambda: deepcopy(pipes))
    monkeypatch.setattr(db, 'get_pipe_history', lambda key: [])
    app = AppTest.from_file('../dashboard.py').run()
    assert not app.exception
    assert app.session_state['infrastructure_activity'] == []
    pipes[0]['status'] = 'broken'
    pipes[0]['report_count'] = 2
    app.run()
    assert not app.exception
    events = app.session_state['infrastructure_activity']
    assert len(events) == 1 and events[0]['before'] == 'operational' and events[0]['after'] == 'broken'
    event_id = events[0]['id']
    assert [m.value for m in app.metric] == ['1', '0', '1', '1']
    app.run()
    assert len(app.session_state['infrastructure_activity']) == 1
    assert app.session_state['infrastructure_activity'][0]['id'] == event_id
    # An older report can increase history while leaving current status untouched.
    pipes[0]['report_count'] = 3
    app.run()
    event = app.session_state['infrastructure_activity'][0]
    assert event['new_report'] and event['before'] == event['after'] == 'broken'
    # User-controlled asset names remain text, not HTML markup.
    html = '\n'.join(element.proto.body for element in app.get('html'))
    assert 'Demo &lt;school&gt; &amp; pump' in html and '<school>' not in html
