"""Regression: fetch_scores() dropped the API's real data_freshness field.

BUG FOUND 2026-08-10 (frontend/dashboard audit pass): fetch_scores() stamped "timestamp"
with the client's own fetch time (datetime.now(ET)) - always "just fetched", never able to
reflect real staleness - and never read the API's server-computed data_freshness field
(from stock_scores.updated_at via check_data_freshness in _get_dashboard_scores), even
though it was present in every response. Unlike positions/portfolio, the SCORES panel had
no way to warn a trader that scores were actually stale. Fixed by threading data_freshness
through into the returned dict, same as fetch_positions/fetch_portfolio already do.
"""

import dashboard.fetchers_signals as fetchers_signals
from dashboard.fetchers_signals import fetch_scores


def test_fetch_scores_propagates_data_freshness_from_wrapped_response(monkeypatch):
    api_response = {
        "statusCode": 200,
        "data": {
            "top": [{"symbol": "AAPL", "composite_score": 75.0}],
            "universe_total": 500,
            "avg_composite": 60.0,
            "grades": {"a": 10, "b": 20, "c": 15, "d": 5},
        },
        "data_freshness": {"is_stale": True, "warning": "3 days old", "data_age_days": 3},
    }
    monkeypatch.setattr(fetchers_signals, "api_call", lambda *a, **k: api_response)

    result = fetch_scores(None)

    assert result["data_freshness"] == {"is_stale": True, "warning": "3 days old", "data_age_days": 3}
    assert result["top"] == [{"symbol": "AAPL", "composite_score": 75.0}]


def test_fetch_scores_data_freshness_none_when_absent(monkeypatch):
    api_response = {
        "statusCode": 200,
        "data": {"top": [], "universe_total": 0, "avg_composite": None, "grades": None},
    }
    monkeypatch.setattr(fetchers_signals, "api_call", lambda *a, **k: api_response)

    result = fetch_scores(None)

    assert result.get("data_freshness") is None
