"""Regression test for the 2026-08-11 fix: when today's put/call ratio has no fresh value
(common pre-market - SPY options open interest is a lagging figure and often reads 0 before
the session gets going), the dashboard showed a bare "⚠ N/A" with no information, even though
a perfectly good value from the last day it WAS available almost always exists one row away in
market_health_daily. The backend now falls back to that last-known-good value (using the same
"only trust a row NOT flagged unavailable" guard already established in
algo/risk/market_factor_calculator.py for the same column), and the dashboard renders it
distinctly (dimmed, with its source date) instead of a bare N/A.
"""

from rich.console import Console

from dashboard.fetchers_market import fetch_market
from dashboard.panels.market import panel_header_market, panel_market_expanded, panel_market_full


def _render(panel) -> str:
    console = Console(width=120, record=True)
    console.print(panel)
    return console.export_text()


def _base_current(**overrides: object) -> dict:
    row = {
        "exposure_pct": 50.0,
        "regime": "confirmed_uptrend",
        "halt_reasons": [],
        "distribution_days": 2,
        "spy_close": 550.0,
    }
    row.update(overrides)
    return row


def _base_market_health(**overrides: object) -> dict:
    row = {
        "vix_level": 18.5,
        "market_stage": 2,
        "market_trend": "uptrend",
    }
    row.update(overrides)
    return row


class TestFetchMarketStaleFallback:
    def test_pcr_stale_parsed_when_fresh_value_unavailable(self, monkeypatch):
        monkeypatch.setattr(
            "dashboard.fetchers_market._get_markets_cached",
            lambda: {
                "current": _base_current(),
                "market_health": _base_market_health(
                    put_call_ratio_data_unavailable=True,
                    put_call_ratio_unavailable_reason="No call open interest reported by yfinance",
                    put_call_ratio_stale_value=0.8674,
                    put_call_ratio_stale_date="2026-08-10",
                ),
            },
        )
        result = fetch_market(None)
        assert result.get("pcr") is None
        assert result.get("pcr_stale") == 0.8674
        assert result.get("pcr_stale_date") == "2026-08-10"

    def test_pcr_stale_ignored_when_fresh_value_present(self, monkeypatch):
        monkeypatch.setattr(
            "dashboard.fetchers_market._get_markets_cached",
            lambda: {
                "current": _base_current(),
                "market_health": _base_market_health(
                    put_call_ratio_data_unavailable=False,
                    put_call_ratio=0.95,
                    # Backend only ever populates these when today's value is unavailable, but
                    # the fetcher should ignore them defensively even if somehow both are set.
                    put_call_ratio_stale_value=0.8674,
                    put_call_ratio_stale_date="2026-08-10",
                ),
            },
        )
        result = fetch_market(None)
        assert result.get("pcr") == 0.95
        assert result.get("pcr_stale") is None

    def test_no_stale_fallback_available_leaves_pcr_stale_unset(self, monkeypatch):
        monkeypatch.setattr(
            "dashboard.fetchers_market._get_markets_cached",
            lambda: {
                "current": _base_current(),
                "market_health": _base_market_health(put_call_ratio_data_unavailable=True),
            },
        )
        result = fetch_market(None)
        assert result.get("pcr") is None
        assert result.get("pcr_stale") is None


class TestMarketPanelsRenderStaleFallback:
    def test_panel_market_full_shows_stale_value_not_bare_omission(self):
        mkt = {
            "vix": 18.5,
            "spy": 550.0,
            "tier": "confirmed_uptrend",
            "halts": [],
            "pcr_stale": 0.8674,
            "pcr_stale_date": "2026-08-10",
        }
        panel = panel_market_full(mkt)
        rendered = _render(panel)
        assert "0.867" in rendered
        assert "2026-08-10" in rendered

    def test_panel_market_expanded_shows_stale_value_not_n_a(self):
        mkt = {
            "vix": 18.5,
            "spy": 550.0,
            "tier": "confirmed_uptrend",
            "halts": [],
            "pcr_stale": 0.8674,
            "pcr_stale_date": "2026-08-10",
        }
        panel = panel_market_expanded(mkt)
        rendered = _render(panel)
        assert "⚠ N/A" not in rendered
        assert "0.867" in rendered
        assert "2026-08-10" in rendered

    def test_panel_market_expanded_still_shows_n_a_with_no_fallback(self):
        mkt = {"vix": 18.5, "spy": 550.0, "tier": "confirmed_uptrend", "halts": []}
        panel = panel_market_expanded(mkt)
        rendered = _render(panel)
        assert "⚠ N/A" in rendered

    def test_panel_header_market_shows_stale_value_not_n_a(self):
        mkt = {
            "vix": 18.5,
            "spy": 550.0,
            "tier": "confirmed_uptrend",
            "halts": [],
            "pcr_stale": 0.8674,
            "pcr_stale_date": "2026-08-10",
        }
        panel = panel_header_market(mkt, sentiment=None, ts="12:00:00", mkt_s="[green]Bull[/]", elapsed=0.1)
        rendered = _render(panel)
        assert "⚠ N/A" not in rendered
        assert "0.867" in rendered
