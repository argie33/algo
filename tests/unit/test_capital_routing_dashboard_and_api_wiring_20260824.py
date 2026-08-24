"""Tests for the capital-routing dashboard/API wiring layers (2026-08-24, user-directed
/goal) - the TUI panel, the dashboard fetcher, and the lambda markets-API SQL block that
sit on top of algo/risk/capital_routing.py's compute engine (already covered by
tests/unit/test_capital_routing_20260824.py). These layers had zero coverage: the compute
engine's unit tests only exercise CapitalRouting directly, never the plumbing that gets a
capital_routing_daily row from Postgres into the /api/algo/markets response and from there
into dashboard.fetchers_market.fetch_capital_routing and dashboard.panels.exposure's
panel_capital_routing.
"""

from unittest.mock import patch

from dashboard.panels.exposure import panel_capital_routing


def _valid_cr() -> dict[str, object]:
    return {
        "data_unavailable": False,
        "uninvested_capital_pct": 35.0,
        "gld_trend_up": True,
        "gld_weight": 0.6,
        "ief_trend_up": False,
        "ief_weight": 0.0,
        "dbc_trend_up": True,
        "dbc_weight": 0.4,
        "cash_weight": 0.0,
        "move_index": 95.0,
        "move_veto": False,
        "timestamp": None,
    }


class TestPanelCapitalRouting:
    """dashboard.panels.exposure.panel_capital_routing"""

    def test_renders_with_valid_data(self) -> None:
        result = panel_capital_routing(_valid_cr())
        assert result is not None

    def test_handles_none(self) -> None:
        result = panel_capital_routing(None)
        assert result is not None

    def test_handles_empty_dict(self) -> None:
        result = panel_capital_routing({})
        assert result is not None

    def test_data_unavailable_shows_reason(self) -> None:
        result = panel_capital_routing({"data_unavailable": True, "reason": "no rows yet"})
        assert result is not None

    def test_move_veto_flag_does_not_crash_ief_row(self) -> None:
        cr = _valid_cr()
        cr["ief_trend_up"] = True
        cr["ief_weight"] = 0.3
        cr["move_veto"] = True
        result = panel_capital_routing(cr)
        assert result is not None

    def test_missing_weight_fields_render_as_dashes_not_crash(self) -> None:
        cr = {
            "data_unavailable": False,
            "uninvested_capital_pct": None,
            "gld_trend_up": None,
            "gld_weight": None,
            "ief_trend_up": None,
            "ief_weight": None,
            "dbc_trend_up": None,
            "dbc_weight": None,
            "cash_weight": None,
            "move_index": None,
            "move_veto": False,
        }
        result = panel_capital_routing(cr)
        assert result is not None


class TestFetchCapitalRouting:
    """dashboard.fetchers_market.fetch_capital_routing"""

    def test_returns_capital_routing_payload_from_markets_response(self) -> None:
        from dashboard.fetchers_market import fetch_capital_routing

        cr_payload = {
            "data_unavailable": False,
            "uninvested_capital_pct": 20.0,
            "gld_weight": 1.0,
        }
        with patch(
            "dashboard.fetchers_market._get_markets_cached",
            return_value={"capital_routing": cr_payload, "data_freshness": {"fresh": True}},
        ):
            result = fetch_capital_routing(None)
        assert result["data_unavailable"] is False
        assert result["uninvested_capital_pct"] == 20.0
        assert "timestamp" in result

    def test_missing_capital_routing_key_degrades_gracefully(self) -> None:
        from dashboard.fetchers_market import fetch_capital_routing

        with patch(
            "dashboard.fetchers_market._get_markets_cached",
            return_value={"exposure_pct": 50.0},
        ):
            result = fetch_capital_routing(None)
        assert result["data_unavailable"] is True

    def test_upstream_data_unavailable_propagates_reason(self) -> None:
        from dashboard.fetchers_market import fetch_capital_routing

        with patch(
            "dashboard.fetchers_market._get_markets_cached",
            return_value={"capital_routing": {"data_unavailable": True, "reason": "stale"}},
        ):
            result = fetch_capital_routing(None)
        assert result["data_unavailable"] is True
        assert result["reason"] == "stale"

    def test_api_error_response_does_not_crash(self) -> None:
        from dashboard.fetchers_market import fetch_capital_routing

        with patch(
            "dashboard.fetchers_market._get_markets_cached",
            return_value={"_error": "timeout"},
        ):
            result = fetch_capital_routing(None)
        assert result is not None
