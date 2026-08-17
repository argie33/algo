"""Regression: the ECONOMIC panel's stale-data warning was dead code.

BUG FOUND 2026-08-17: panel_economic_pulse/panel_economic_expanded diffed eco.get("timestamp")
against datetime.now() to detect staleness - but that "timestamp" is always
fetch_economic_pulse()'s own datetime.now(ET) at fetch time (dashboard/fetchers_external.py), so
the diff was always ~0 seconds regardless of how stale the underlying FRED economic_data actually
is. Same bug class as the now-fixed MARKET/TRADES/SIGNALS/SCORES/EXPOSURE/SECTORS panels. FRED
data (rates, credit spreads, inflation breakevens) directly feeds market exposure scoring, so
stale data with zero warning is a real risk.

Root cause fixed in lambda/api/routes/economic.py (_get_leading_indicators/_get_yield_curve_full
now compute a real data_freshness signal) and wired through fetch_economic_pulse(); this panel
now reads that server-computed signal instead of self-computing a fetch-time no-op.
"""

from unittest.mock import patch

from dashboard.fetchers_external import fetch_economic_pulse
from dashboard.panels.economic import panel_economic_expanded, panel_economic_pulse


def _eco(data_freshness: dict | None = None) -> dict:
    row: dict = {"fed_funds": 5.25, "t10": 4.2, "t2": 4.0}
    if data_freshness is not None:
        row["data_freshness"] = data_freshness
    return row


def _title(panel) -> str:
    title = panel.title
    return title if isinstance(title, str) else str(title)


def test_stale_economic_data_produces_warning_in_compact_title():
    eco = _eco({"is_stale": True, "data_age_days": 10, "warning": "10 days old"})
    panel = panel_economic_pulse(eco)
    assert panel is not None
    assert "STALE" in _title(panel), f"expected a STALE badge in title, got: {_title(panel)}"


def test_fresh_economic_data_no_warning_in_compact_title():
    eco = _eco({"is_stale": False})
    panel = panel_economic_pulse(eco)
    assert panel is not None
    assert "STALE" not in _title(panel)


def test_missing_data_freshness_no_crash_no_warning():
    eco = _eco()  # no data_freshness key at all
    panel = panel_economic_pulse(eco)
    assert panel is not None
    assert "STALE" not in _title(panel)


def test_stale_economic_data_produces_warning_in_expanded_title():
    eco = _eco({"is_stale": True, "data_age_days": 10, "warning": "10 days old"})
    panel = panel_economic_expanded(eco)
    assert panel is not None
    assert "STALE" in _title(panel), f"expected a STALE badge in title, got: {_title(panel)}"


def test_fresh_economic_data_no_warning_in_expanded_title():
    eco = _eco({"is_stale": False})
    panel = panel_economic_expanded(eco)
    assert panel is not None
    assert "STALE" not in _title(panel)


def test_fetch_economic_pulse_propagates_data_freshness_from_indicators_endpoint():
    """The fetcher must forward the real server-computed data_freshness, not drop it."""
    yc_response = {
        "currentCurve": {"10Y": 4.2, "2Y": 4.0, "3M": 5.0, "6M": 4.9},
        "spreads": {"T10Y2Y": 0.2, "T10Y3M": -0.8},
        "credit": {"currentSpreads": {"BAMLH0A0HYM2": 350.0, "BAMLH0A0IG": 150.0}},
    }
    ind_response = {
        "indicators": [
            {"series_id": "SOFR", "rawValue": 5.3},
            {"series_id": "ANFCI", "rawValue": -0.1},
        ],
        "data_freshness": {"is_stale": True, "data_age_days": 10, "warning": "10 days old"},
    }

    with patch("dashboard.fetchers_external.api_call") as mock_api:
        mock_api.side_effect = [yc_response, ind_response]
        result = fetch_economic_pulse(None)

    assert "_error" not in result, f"unexpected fetcher error: {result}"
    assert result.get("data_freshness") == ind_response["data_freshness"]
