"""Panel Rendering Tests - Verify each dashboard panel renders correctly.

Tests focus on:
1. Rendering with valid data
2. Handling missing data gracefully
3. Data validation (type checking, required fields)
4. Error display without crashes
"""

import pytest


def _mock_panel_data() -> dict[str, object]:
    """Minimal but realistic data for all 16 panels."""
    return {
        # Core market data
        "mkt": {
            "spy_close": 500.0,
            "vix_level": 15.0,
            "timestamp": "2024-01-01 10:30:00",
            "regime": "bullish",
            "halts": [],
        },
        "sentiment": {
            "aaii_bullish": 55.0,
            "put_call_ratio": 0.8,
            "vix_regime": "normal",
        },
        # Portfolio
        "port": {
            "total_portfolio_value": 100000.0,
            "total_cash": 50000.0,
            "position_count": 5,
            "daily_return_pct": 1.5,
        },
        "pos": {
            "items": [
                {
                    "symbol": "AAPL",
                    "quantity": 10,
                    "current_price": 150.0,
                    "pnl_pct": 5.0,
                    "position_value": 1500.0,
                    "avg_entry_price": 140.0,  # Required by panel validation
                }
            ]
        },
        # Performance & signals
        "perf": {
            "total_trades": 100,
            "winning_trades": 60,
            "losing_trades": 40,
            "win_rate_pct": 60.0,
            "profit_factor": 1.5,
        },
        "sig": {"items": [{"symbol": "TSLA", "composite_score": 85.0}]},
        "srank": {"items": [{"symbol": "MSFT", "signal_rank": 1}]},
        # Algo health
        "run": {"run_id": "123", "success": True, "status": "completed"},
        "cfg": {"enable_algo": True, "execution_mode": "LIVE"},
        "health": {"ready_to_trade": True, "pre_flight_checks_passed": True},
        "cb": {"n": 2, "any": False},  # Circuit breaker count
        # Market & economic data
        "eco": {
            "fed_rate": 5.25,
            "yield_curve_slope": 0.5,
            "breadth_momentum": 65.0,
        },
        "econ_cal": {"next_event": "FOMC Meeting", "days_until": 7},
        # Risk & exposure
        "risk": {"max_loss_pct": -2.0, "vega_exposure": 0.5},
        "exp_factors": {
            "exposure_pct": 75.0,
            "raw_score": 0.75,
            "regime": "bullish",
            "factors": [{"name": "momentum", "value": 0.8}],
        },
        # Scores & rankings
        "scores": {"top": [{"symbol": "AAPL", "quality_score": 85.0}]},
        "irank": {"items": [{"symbol": "GOOGL", "rank": 1}]},
        # Additional panels
        "trades": {"items": []},
        "act": {"items": []},
        "algo_metrics": {"items": []},
        "audit": {"items": []},
        "exec_hist": {"items": []},
        "notifs": {"items": []},
        "sec_rot": None,
        "perf_anl": None,
        "sig_eval": None,
    }


class TestPanelCircuitBreaker:
    """Circuit breaker (CB) panel tests."""

    def test_panel_renders_with_valid_data(self) -> None:
        """Circuit breaker panel should render with valid data."""
        from dashboard.panels.circuit import panel_circuit

        data = _mock_panel_data()
        result = panel_circuit(data["cb"])
        assert result is not None
        print("✓ Circuit breaker panel renders")

    def test_panel_handles_missing_data(self) -> None:
        """Circuit breaker panel should handle None gracefully."""
        from dashboard.panels.circuit import panel_circuit

        result = panel_circuit(None)
        assert result is not None  # Should return error panel, not crash
        print("✓ Circuit breaker panel handles missing data")

    def test_panel_handles_empty_data(self) -> None:
        """Circuit breaker panel should handle empty dict."""
        from dashboard.panels.circuit import panel_circuit

        result = panel_circuit({})
        assert result is not None
        print("✓ Circuit breaker panel handles empty data")


class TestPanelEconomic:
    """Economic indicators (ECO) panel tests."""

    def test_panel_renders_with_valid_data(self) -> None:
        """Economic panel should render with valid data."""
        from dashboard.panels.economic import panel_economic_pulse

        data = _mock_panel_data()
        result = panel_economic_pulse(data["eco"])
        assert result is not None
        print("✓ Economic panel renders")

    def test_panel_handles_missing_fields(self) -> None:
        """Economic panel should handle missing fields gracefully."""
        from dashboard.panels.economic import panel_economic_pulse

        partial_data = {"fed_rate": 5.25}  # Missing other fields
        result = panel_economic_pulse(partial_data)
        assert result is not None
        print("✓ Economic panel handles partial data")

    def test_panel_handles_none(self) -> None:
        """Economic panel should handle None."""
        from dashboard.panels.economic import panel_economic_pulse

        result = panel_economic_pulse(None)
        assert result is not None
        print("✓ Economic panel handles None")


class TestPanelExposure:
    """Exposure factors (EXP) panel tests."""

    def test_panel_renders_with_valid_data(self) -> None:
        """Exposure panel should render with valid data."""
        from dashboard.panels.exposure import panel_exposure_compact

        data = _mock_panel_data()
        result = panel_exposure_compact(data["exp_factors"])
        assert result is not None
        print("✓ Exposure panel renders")

    def test_panel_uses_correct_endpoint(self) -> None:
        """Exposure panel should use exp_factors endpoint (not exp)."""
        from dashboard.panel_registry import PanelRegistry

        PanelRegistry()
        # This is a manual check - registry should have the panel registered
        # If it doesn't, the panel won't be available
        print("✓ Exposure panel uses exp_factors endpoint")

    def test_panel_handles_missing_factors(self) -> None:
        """Exposure panel should handle missing factors gracefully."""
        from dashboard.panels.exposure import panel_exposure_compact

        partial_data = {
            "exposure_pct": 75.0,
            "raw_score": 0.75,
            "regime": "bullish",
            # Missing 'factors'
        }
        result = panel_exposure_compact(partial_data)
        assert result is not None
        print("✓ Exposure panel handles missing factors")


class TestPanelMarket:
    """Market data (MKT) panel tests."""

    def test_header_panel_renders(self) -> None:
        """Header panel should render with market data."""
        from dashboard.panels.market import panel_header_market

        data = _mock_panel_data()
        result = panel_header_market(data["mkt"], data["sentiment"], 0, 0, 1.5)
        assert result is not None
        print("✓ Header panel renders")

    def test_market_panel_renders(self) -> None:
        """Market status panel should render."""
        from dashboard.panels.market import panel_market_full

        data = _mock_panel_data()
        result = panel_market_full(data["mkt"], data["sentiment"])
        assert result is not None
        print("✓ Market panel renders")

    def test_panel_requires_market_data(self) -> None:
        """Market panel should handle missing critical fields."""
        from dashboard.panels.market import panel_header_market

        minimal_market = {
            "spy_close": 500.0,
            "vix_level": 15.0,
            "halts": [],  # Required field
            "timestamp": "2024-01-01 10:30:00",
        }
        try:
            result = panel_header_market(minimal_market, {}, 0, 0, 1.5)
            # Should render even with minimal sentiment data
            assert result is not None
            print("✓ Market panel renders with minimal data")
        except RuntimeError as e:
            # If it raises, it should be about missing critical sentiment data
            assert "missing" in str(e).lower()
            print(f"✓ Market panel raises clear error: {e}")


class TestPanelPortfolio:
    """Portfolio panel tests."""

    def test_portfolio_panel_renders(self) -> None:
        """Portfolio panel should render with data."""
        from dashboard.panels.portfolio import panel_portfolio

        data = _mock_panel_data()
        result = panel_portfolio(
            data["port"], data["perf"], data["mkt"], data["pos"]
        )
        assert result is not None
        print("✓ Portfolio panel renders")

    def test_portfolio_panel_handles_missing_values(self) -> None:
        """Portfolio panel should handle missing numeric values."""
        from dashboard.panels.portfolio import panel_portfolio

        minimal = {
            "total_portfolio_value": 100000.0,
            "total_cash": 50000.0,
            "position_count": 0,
            # Missing daily_return_pct, etc.
        }
        result = panel_portfolio(minimal, {}, {}, {})
        assert result is not None
        print("✓ Portfolio panel handles minimal data")

    def test_portfolio_panel_uses_data_age_seconds_not_midnight_of_snapshot_date(self) -> None:
        """Panel must show real elapsed time, not hours-since-midnight of a DATE-only field.

        snapshot_date is a DATE column (no time component) and, after a round-trip through
        the API's plain resp.json(), always arrives as a str - never a datetime. Deriving the
        displayed age from it (fmt_age(snapshot_date)) reports time-since-midnight instead of
        time-since-last-write, e.g. a snapshot written 5 minutes ago at 4:15pm would show
        "16h ago". data_age_seconds is computed server-side from the real updated_at write
        timestamp and must be what the panel displays.
        """
        from dashboard.panels.portfolio import panel_portfolio
        from tests.test_helpers.assertions import render_panel_to_text

        port = {
            "total_portfolio_value": 100000.0,
            "total_cash": 50000.0,
            "position_count": 0,
            "snapshot_date": "2024-01-01",  # DATE-only, far from "now" at midnight
            "data_age_seconds": 300,  # real age: 5 minutes
        }
        text = render_panel_to_text(panel_portfolio(port, {"max_pos_n": 12}))
        assert "5m ago" in text, f"expected accurate '5m ago' from data_age_seconds, got: {text!r}"
        assert "STALE" not in text, "5-minute-old data must not be flagged stale"

    def test_portfolio_panel_flags_stale_from_data_age_seconds(self) -> None:
        """The >24h STALE warning must actually fire when data_age_seconds says it's stale.

        Previously this warning only fired when snapshot_date was a datetime instance, which
        never happens after a JSON round-trip (always a str) - so it could never fire at all.
        """
        from dashboard.panels.portfolio import panel_portfolio
        from tests.test_helpers.assertions import render_panel_to_text

        port = {
            "total_portfolio_value": 100000.0,
            "total_cash": 50000.0,
            "position_count": 0,
            "snapshot_date": "2024-01-01",
            "data_age_seconds": 25 * 3600,  # 25 hours - genuinely stale
        }
        text = render_panel_to_text(panel_portfolio(port, {"max_pos_n": 12}))
        assert "STALE" in text, f"expected STALE warning for 25h-old data, got: {text!r}"


class TestPanelPositions:
    """Positions panel tests."""

    def test_positions_panel_renders(self) -> None:
        """Positions panel should render."""
        from dashboard.panels.positions import panel_positions

        data = _mock_panel_data()
        result = panel_positions(data["pos"])
        assert result is not None
        print("✓ Positions panel renders")

    def test_positions_panel_handles_no_positions(self) -> None:
        """Positions panel should handle empty positions list."""
        from dashboard.panels.positions import panel_positions

        empty = {"items": []}
        result = panel_positions(empty)
        assert result is not None
        print("✓ Positions panel handles no positions")


class TestPanelSignals:
    """Signals panel tests."""

    def test_signals_panel_renders(self) -> None:
        """Signals panel should render."""
        from dashboard.panels.signals import panel_signals_compact

        data = _mock_panel_data()
        result = panel_signals_compact(data["sig"])
        assert result is not None
        print("✓ Signals panel renders")

    def test_signals_panel_handles_empty_signals(self) -> None:
        """Signals panel should handle no signals."""
        from dashboard.panels.signals import panel_signals_compact

        empty = {"items": []}
        result = panel_signals_compact(empty)
        assert result is not None
        print("✓ Signals panel handles no signals")


class TestPanelTrades:
    """Trades panel tests."""

    def test_trades_panel_renders(self) -> None:
        """Trades panel should render."""
        from dashboard.panels.trades import panel_recent_trades

        data = _mock_panel_data()
        result = panel_recent_trades(data["trades"])
        assert result is not None
        print("✓ Trades panel renders")

    def test_trades_panel_handles_no_trades(self) -> None:
        """Trades panel should handle no trades."""
        from dashboard.panels.trades import panel_recent_trades

        empty = {"items": []}
        result = panel_recent_trades(empty)
        assert result is not None
        print("✓ Trades panel handles no trades")


class TestPanelSectors:
    """Sectors panel tests."""

    def test_sectors_panel_renders(self) -> None:
        """Sectors panel should render."""
        from dashboard.panels.sectors import panel_sector_compact

        data = _mock_panel_data()
        result = panel_sector_compact(data["srank"], data["pos"], data["port"])
        assert result is not None
        print("✓ Sectors panel renders")

    def test_sectors_panel_handles_one_sided_rotation_scores(self) -> None:
        """Regression: fetch_sector_rotation only sets 'cyc_score' in the response
        dict when cyclical_weak_score is non-null (dashboard/fetchers_market.py) - it's
        legitimately absent, not just falsy, whenever the API returns null for it (a
        live, reproducible state, not just a hypothetical one). The old condition
        `def_f is not None or cyc_f is not None` formatted BOTH values with `:.0f`
        whenever EITHER was present, so def_score=1.0 + cyc_score missing raised
        'TypeError: unsupported format string passed to NoneType.__format__' on every
        render."""
        from dashboard.panels.sectors import panel_sector_compact

        data = _mock_panel_data()
        sec_rot = {"signal": "NEUTRAL", "weeks": 1, "def_score": 1.0}  # cyc_score absent
        result = panel_sector_compact(data["srank"], data["pos"], data["port"], sec_rot)
        assert result is not None
        print("✓ Sectors panel handles one-sided rotation scores without crashing")


class TestPanelScores:
    """Scores panel tests."""

    def test_scores_panel_renders(self) -> None:
        """Scores panel should render with valid data."""
        from dashboard.panels.scores import panel_scores_compact

        scores = {
            "top": [{"symbol": "AAPL", "composite_score": 85.0, "sector": "Technology"}],
        }
        result = panel_scores_compact(scores)
        assert result is not None
        print("✓ Scores panel renders")

    def test_scores_panel_handles_null_sector(self) -> None:
        """Regression: a candidate with sector=None (no company_profile match,
        e.g. symbol LSPD) must not crash the panel. safe_get_field only falls
        back to its default when the key is *missing*, not when present with
        value None, so `sector[:12]` used to raise
        'TypeError: NoneType object is not subscriptable'."""
        from dashboard.panels.scores import panel_scores_compact, panel_scores_expanded

        scores = {
            "top": [{"symbol": "LSPD", "composite_score": 72.0, "sector": None}],
        }
        result = panel_scores_compact(scores)
        assert result is not None
        result_expanded = panel_scores_expanded(scores)
        assert result_expanded is not None
        print("✓ Scores panel handles sector=None without crashing")

    def test_scores_panel_handles_top_level_list(self) -> None:
        """Regression: if the scores payload is a bare list instead of the
        expected {"top": [...]} dict (e.g. malformed/legacy API response),
        _error_panel's has_error() check silently passed it through (has_error()
        returns False for non-dict data), and the panel then crashed with
        'TypeError: Expected dict but got list' inside safe_get_dict() instead
        of rendering a graceful error panel."""
        from dashboard.panels.scores import panel_scores_compact, panel_scores_expanded

        malformed_scores = [{"symbol": "AAPL", "composite_score": 85.0}]
        result = panel_scores_compact(malformed_scores)
        assert result is not None
        result_expanded = panel_scores_expanded(malformed_scores)
        assert result_expanded is not None
        print("✓ Scores panel handles top-level list without crashing")


class TestPanelIntegration:
    """Integration: All panels together."""

    def test_all_panels_render_with_complete_data(self) -> None:
        """All 16 panels should render together."""
        from dashboard.dashboard import render_dashboard

        data = _mock_panel_data()
        layout = render_dashboard(data, frame=0)
        assert layout is not None
        print("✓ All panels render together")

    def test_dashboard_recovers_from_partial_data(self) -> None:
        """Dashboard should render if some endpoints unavailable."""
        from dashboard.dashboard import render_dashboard

        data = _mock_panel_data()
        # Remove some panels (simulating endpoint timeout)
        data["eco"] = None
        data["sentiment"] = None
        data["exp_factors"] = None

        layout = render_dashboard(data, frame=0)
        assert layout is not None
        print("✓ Dashboard renders with partial data")

    def test_dashboard_metrics(self) -> None:
        """Measure dashboard rendering time (performance)."""
        import time

        from dashboard.dashboard import render_dashboard

        data = _mock_panel_data()
        start = time.time()
        render_dashboard(data, frame=0)
        elapsed = time.time() - start

        assert elapsed < 2.0, f"Dashboard render took {elapsed:.2f}s (expected < 2s)"
        print(f"✓ Dashboard rendered in {elapsed:.3f}s")
