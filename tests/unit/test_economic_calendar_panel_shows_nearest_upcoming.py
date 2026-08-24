"""Regression: the ECONOMIC panel's calendar section showed the wrong 6 events.

BUG FOUND 2026-08-24 (real-money-readiness goal, dashboard.py sweep): the API
(lambda/api/routes/economic.py::_get_calendar) returns events `ORDER BY event_date DESC`
(furthest-future date first) over a default window spanning the last 90 days through
unbounded future. `_build_calendar_rows()` (dashboard/panels/economic.py) took the first 6
items of whatever order the API gave it - trusting DESC order meant it showed the 6
furthest-out events, not the 6 actually coming up next, even though the panel is titled
"ECONOMIC CALENDAR (UPCOMING)" and its own `when` labels ("TODAY"/"+Nd"/"YST") assume a
near-to-far chronological display. Invisible while economic_calendar only held 13 stale
June rows with no loader; became a real display bug the moment the loader (built the same
session) started writing real forward-looking events across the next year.

Fix: filter to yesterday-forward, then sort ascending, before truncating to 6.
"""

from rich.console import Console

from dashboard.panels.economic import panel_economic_pulse


def _render(panel) -> str:
    console = Console(width=120, record=True)
    console.print(panel)
    return console.export_text()


def _event(days_from_today: int, name: str) -> dict:
    from datetime import date, timedelta

    return {
        "event_date": (date.today() + timedelta(days=days_from_today)).isoformat(),
        "event_name": name,
        "importance": "HIGH",
    }


def test_nearest_upcoming_events_shown_not_furthest_out():
    # API-order simulation: furthest-future date first (DESC), matching the real endpoint.
    far_future_events = [_event(300 - i, f"Event+{300 - i}d") for i in range(0, 60, 10)]
    near_events = [_event(1, "CPI"), _event(3, "NFP"), _event(7, "FOMC")]
    econ_cal = {"items": far_future_events + near_events}

    eco = {"fed_funds": 5.25}
    panel = panel_economic_pulse(eco, econ_cal)
    assert panel is not None

    rendered = _render(panel)
    assert "CPI" in rendered, f"nearest event (CPI, +1d) missing from rendered calendar: {rendered}"
    assert "NFP" in rendered, f"nearest event (NFP, +3d) missing from rendered calendar: {rendered}"
    # The furthest-out event (+300d) must NOT crowd out the near-term ones in the 6-slot window.
    assert "Event+300d" not in rendered, "furthest-out event should not appear ahead of near-term events"


def test_falls_back_to_all_events_when_none_are_upcoming():
    # All events are in the past (older than the 1-day grace window) - should still render
    # something (sorted fallback) rather than an empty calendar.
    past_events = [_event(-30, "OldCPI"), _event(-10, "OldNFP")]
    econ_cal = {"items": past_events}

    eco = {"fed_funds": 5.25}
    panel = panel_economic_pulse(eco, econ_cal)
    assert panel is not None
    rendered = _render(panel)
    assert "OldNFP" in rendered or "OldCPI" in rendered
