"""Regression test for the 2026-09-05 fix (real-money-readiness,
portfolio_leverage_concentration_audit_20260904): every exposure/concentration/position-sizing
cap in this system (market_exposure.py, exposure_policy.py, position_sizer.py) is expressed as
a percentage of equity - none of them clamp against buying_power. If the Alpaca account were
ever margin-enabled (accidentally, or via an Alpaca-side account upgrade), buying_power itself
would legitimately exceed equity, and nothing would stop those caps from deploying leveraged
capital. Phase 2 now fails closed on any multiplier != 1.0 (cash account).
"""

from unittest.mock import MagicMock, patch

from algo.orchestrator.phase2_circuit_breakers import run as phase2_run


def _clean_cb_result():
    return {
        "halted": False,
        "halt_reasons": [],
        "checks": {
            "vix": {"halted": False, "reason": "VIX ok"},
        },
    }


def _auto_config():
    return {"execution_mode": "auto"}


class TestPhase2MarginAccountHalt:
    def test_margin_enabled_account_halts_phase_in_auto_mode(self):
        with (
            patch("algo.risk.CircuitBreaker") as MockCB,
            patch("algo.infrastructure.MarketEventHandler") as MockMEH,
            patch("algo.infrastructure.alpaca_broker_adapter.AlpacaBrokerAdapter") as MockBroker,
        ):
            MockCB.return_value.check_all.return_value = _clean_cb_result()
            MockMEH.return_value.check_market_circuit_breaker.return_value = None
            MockBroker.return_value.fetch_account.return_value = {
                "trading_blocked": False,
                "account_blocked": False,
                "pattern_day_trader": False,
                "daytrade_count": 0,
                "multiplier": 2.0,
            }
            alerts = MagicMock()

            result = phase2_run(
                config=_auto_config(),
                run_date=None,
                dry_run=False,
                alerts=alerts,
                verbose=False,
                log_phase_result_fn=MagicMock(),
            )

        assert result.halted is True, "A margin-enabled (multiplier != 1.0) account must halt Phase 2"
        alerts.send_position_alert.assert_called_once()
        assert alerts.send_position_alert.call_args[0][1] == "ACCOUNT_MARGIN_ENABLED"

    def test_cash_account_does_not_halt(self):
        with (
            patch("algo.risk.CircuitBreaker") as MockCB,
            patch("algo.infrastructure.MarketEventHandler") as MockMEH,
            patch("algo.infrastructure.alpaca_broker_adapter.AlpacaBrokerAdapter") as MockBroker,
        ):
            MockCB.return_value.check_all.return_value = _clean_cb_result()
            MockMEH.return_value.check_market_circuit_breaker.return_value = None
            MockBroker.return_value.fetch_account.return_value = {
                "trading_blocked": False,
                "account_blocked": False,
                "pattern_day_trader": False,
                "daytrade_count": 0,
                "multiplier": 1.0,
            }

            result = phase2_run(
                config=_auto_config(),
                run_date=None,
                dry_run=False,
                alerts=MagicMock(),
                verbose=False,
                log_phase_result_fn=MagicMock(),
            )

        assert result.halted is False
        assert result.status == "ok"

    def test_missing_multiplier_field_halts(self):
        with (
            patch("algo.risk.CircuitBreaker") as MockCB,
            patch("algo.infrastructure.MarketEventHandler") as MockMEH,
            patch("algo.infrastructure.alpaca_broker_adapter.AlpacaBrokerAdapter") as MockBroker,
        ):
            MockCB.return_value.check_all.return_value = _clean_cb_result()
            MockMEH.return_value.check_market_circuit_breaker.return_value = None
            MockBroker.return_value.fetch_account.return_value = {
                "trading_blocked": False,
                "account_blocked": False,
                "pattern_day_trader": False,
                "daytrade_count": 0,
            }

            result = phase2_run(
                config=_auto_config(),
                run_date=None,
                dry_run=False,
                alerts=MagicMock(),
                verbose=False,
                log_phase_result_fn=MagicMock(),
            )

        assert result.halted is True, "Missing multiplier field must fail closed, not assume cash account"
