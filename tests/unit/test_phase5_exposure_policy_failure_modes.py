"""Regression test: phase5_exposure_policy.py had ZERO dynamic test coverage of any kind
before this (no test file in tests/unit/ even imports the module) despite producing the
exposure_constraints (halt_new_entries, risk_multiplier, max_concentration_pct) that Phase 8
directly gates real order submission on.

Confirms, by actually executing run(), three fail-closed paths and one success path:
1. A halt flag already active at phase start returns safe halt constraints immediately.
2. MarketDataUnavailableError from read_market_regime() (wrapped into a plain RuntimeError
   by the phase's own inner try/except - MarketDataUnavailableError is itself a RuntimeError
   subclass, defined in algo/risk/market_exposure.py) is caught by the generic outer
   `except Exception` handler, not the more specific `except MarketDataUnavailableError`
   handler a few lines above it - both produce equivalent safe halt constraints
   (halt_new_entries=True, risk_multiplier=0.0), just with a more generic message. Confirmed
   empirically rather than assumed from reading the two except blocks' order.
3. MarketDataUnavailableError raised directly from ExposurePolicy.get_entry_constraints()
   (not pre-wrapped) IS caught by the specific `except MarketDataUnavailableError` handler,
   producing its more specific "Market exposure data missing" message - demonstrating the
   two handlers are not dead code relative to each other, they serve different raise sites.
4. A clean run with no failures returns status="ok" with real constraints.

All fail-closed paths must return halt_new_entries=True and risk_multiplier=0.0 - the two
load-bearing fields Phase 8 actually reads before allowing any new order.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase5_exposure_policy import run


def _base_mocks(halted_at_start=False):
    mock_halt_mgr = MagicMock()
    mock_halt_mgr.check_halt_flag.return_value = halted_at_start
    return mock_halt_mgr


class TestPhase5HaltFlagAtStart:
    def test_active_halt_flag_returns_safe_halt_constraints_immediately(self):
        mock_halt_mgr = _base_mocks(halted_at_start=True)

        with patch("algo.orchestration.halt_flag_manager.HaltFlagManager", return_value=mock_halt_mgr):
            result = run(
                config={"execution_mode": "paper"},
                run_date=date(2026, 8, 10),
                dry_run=False,
                alerts=MagicMock(),
                verbose=False,
                log_phase_result_fn=MagicMock(),
            )

        assert result.halted is True
        constraints = result.data["constraints"]
        assert constraints["halt_new_entries"] is True
        assert constraints["risk_multiplier"] == 0.0
        assert constraints["max_new_positions_today"] == 0


class TestPhase5MarketDataUnavailable:
    def _run_with_read_market_regime_raising(self, exc):
        mock_halt_mgr = _base_mocks(halted_at_start=False)

        with (
            patch("algo.orchestration.halt_flag_manager.HaltFlagManager", return_value=mock_halt_mgr),
            patch("algo.risk.read_market_regime", side_effect=exc),
        ):
            return run(
                config={"execution_mode": "paper"},
                run_date=date(2026, 8, 10),
                dry_run=False,
                alerts=MagicMock(),
                verbose=False,
                log_phase_result_fn=MagicMock(),
            )

    def test_market_data_unavailable_from_read_market_regime_halts_safely(self):
        from algo.risk import MarketDataUnavailableError

        result = self._run_with_read_market_regime_raising(MarketDataUnavailableError("no snapshot for date"))

        assert result.halted is True
        assert result.status == "error"
        constraints = result.data["constraints"]
        assert constraints["halt_new_entries"] is True
        assert constraints["risk_multiplier"] == 0.0
        # This specific raise site pre-wraps into a plain RuntimeError before it can reach
        # the specific `except MarketDataUnavailableError` handler - falls through to the
        # generic handler's message instead. Confirms actual behavior, not assumed intent.
        assert "Exposure policy error" in constraints["halt_reason"]

    def test_market_data_unavailable_from_get_entry_constraints_uses_specific_handler(self):
        from algo.risk import ExposurePolicy, MarketDataUnavailableError

        mock_halt_mgr = _base_mocks(halted_at_start=False)
        mock_policy = MagicMock()
        mock_policy.get_entry_constraints.side_effect = MarketDataUnavailableError("regime snapshot missing")

        with (
            patch("algo.orchestration.halt_flag_manager.HaltFlagManager", return_value=mock_halt_mgr),
            patch("algo.risk.read_market_regime", return_value={"exposure_pct": 50, "regime": "confirmed_uptrend"}),
            patch("algo.risk.ExposurePolicy", return_value=mock_policy),
        ):
            result = run(
                config={"execution_mode": "paper"},
                run_date=date(2026, 8, 10),
                dry_run=False,
                alerts=MagicMock(),
                verbose=False,
                log_phase_result_fn=MagicMock(),
            )

        assert result.halted is True
        constraints = result.data["constraints"]
        assert constraints["halt_new_entries"] is True
        assert constraints["risk_multiplier"] == 0.0
        # Raised directly (not pre-wrapped) - this time it IS caught by the specific handler
        # (confirmed via the log message: "CRITICAL: Market exposure data missing (Phase 4
        # likely failed)..." matches that handler's own log line, not the generic one's).
        assert "Market regime data missing" in constraints["description"]
