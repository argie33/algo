#!/usr/bin/env python3
"""Regression test for the 2026-07-28 fix: Phase 2 never checked whether Alpaca itself had
frozen the trading account (trading_blocked/account_blocked) or flagged it pattern_day_trader.
Same-day stop-loss exits are intentional (see exit_engine.py's hard-stop-overrides-min_hold_days
comment), so this system can and does generate real day trades. Before this fix, an account
Alpaca froze for any reason (PDT violation, compliance hold, negative balance) gave zero
proactive signal - every subsequent entry would just fail with a generic per-symbol 403 from
order_manager.py, indistinguishable from an ordinary rejection.

The check is gated on execution_mode=="auto" (the only mode that submits real orders - see
reconciliation.py's identical gate) so it must be a complete no-op for paper/dry-run/local dev.
"""

from unittest.mock import MagicMock, patch

from algo.orchestrator.phase2_circuit_breakers import run as phase2_run


def _clean_cb_result():
    # BLOCKER #5 FIX: checks dict must not be empty. Include at least one circuit breaker result
    # Each check must have at minimum a "halted" field (state dict) per circuit_breaker.py line 238
    return {
        "halted": False,
        "halt_reasons": [],
        "checks": {
            "vix": {"halted": False, "reason": "VIX ok"},
        },
    }


def _auto_config():
    return {"execution_mode": "auto"}


def _paper_config():
    return {"execution_mode": "paper"}


class TestPhase2AccountBlockCheck:
    def test_trading_blocked_halts_phase_in_auto_mode(self):
        with (
            patch("algo.risk.CircuitBreaker") as MockCB,
            patch("algo.infrastructure.MarketEventHandler") as MockMEH,
            patch("algo.infrastructure.alpaca_broker_adapter.AlpacaBrokerAdapter") as MockBroker,
        ):
            MockCB.return_value.check_all.return_value = _clean_cb_result()
            MockMEH.return_value.check_market_circuit_breaker.return_value = None
            MockBroker.return_value.fetch_account.return_value = {
                "trading_blocked": True,
                "account_blocked": False,
                "pattern_day_trader": False,
                "daytrade_count": 0,
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

        assert result.halted is True, "A trading_blocked Alpaca account must halt Phase 2"
        assert "trading_blocked" in result.error or "blocked" in (result.error or "").lower()
        alerts.send_position_alert.assert_called_once()
        assert alerts.send_position_alert.call_args[0][1] == "ACCOUNT_BLOCKED"

    def test_account_blocked_halts_phase_in_auto_mode(self):
        with (
            patch("algo.risk.CircuitBreaker") as MockCB,
            patch("algo.infrastructure.MarketEventHandler") as MockMEH,
            patch("algo.infrastructure.alpaca_broker_adapter.AlpacaBrokerAdapter") as MockBroker,
        ):
            MockCB.return_value.check_all.return_value = _clean_cb_result()
            MockMEH.return_value.check_market_circuit_breaker.return_value = None
            MockBroker.return_value.fetch_account.return_value = {
                "trading_blocked": False,
                "account_blocked": True,
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

        assert result.halted is True, "An account_blocked Alpaca account must halt Phase 2"

    def test_pattern_day_trader_flag_warns_but_does_not_halt(self):
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
                "pattern_day_trader": True,
                "daytrade_count": 4,
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

        assert result.halted is False, "pattern_day_trader alone (not blocked) must not halt trading"
        assert result.status == "ok"

    def test_daytrade_count_at_threshold_logs_even_when_flag_still_false(self):
        """FIXED 2026-08-31: pattern_day_trader is a trailing flag Alpaca only sets True after
        a 4th day trade has already landed - the pre-breach window (daytrade_count==3, flag
        still False) is exactly the scenario Phase 8's proactive block (ddd778e04) exists to
        catch, and this diagnostic log must not stay silent for it either."""
        with (
            patch("algo.risk.CircuitBreaker") as MockCB,
            patch("algo.infrastructure.MarketEventHandler") as MockMEH,
            patch("algo.infrastructure.alpaca_broker_adapter.AlpacaBrokerAdapter") as MockBroker,
            patch("algo.orchestrator.phase2_circuit_breakers.logger") as mock_logger,
        ):
            MockCB.return_value.check_all.return_value = _clean_cb_result()
            MockMEH.return_value.check_market_circuit_breaker.return_value = None
            MockBroker.return_value.fetch_account.return_value = {
                "trading_blocked": False,
                "account_blocked": False,
                "pattern_day_trader": False,
                "daytrade_count": 3,
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
        warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
        assert any("daytrade_count=3" in c for c in warning_calls), (
            "must log daytrade_count>=3 even before pattern_day_trader flips True"
        )

    def test_credential_error_halts_in_auto_mode(self):
        with (
            patch("algo.risk.CircuitBreaker") as MockCB,
            patch("algo.infrastructure.MarketEventHandler") as MockMEH,
            patch("algo.infrastructure.alpaca_broker_adapter.AlpacaBrokerAdapter") as MockBroker,
        ):
            MockCB.return_value.check_all.return_value = _clean_cb_result()
            MockMEH.return_value.check_market_circuit_breaker.return_value = None
            MockBroker.return_value.fetch_account.side_effect = RuntimeError("credentials not available")

            result = phase2_run(
                config=_auto_config(),
                run_date=None,
                dry_run=False,
                alerts=MagicMock(),
                verbose=False,
                log_phase_result_fn=MagicMock(),
            )

        assert result.halted is True, "execution_mode=auto must halt if account status can't be verified before trading"

    def test_paper_mode_never_calls_broker_at_all(self):
        """Sanity check: the account check must be a complete no-op outside execution_mode=auto -
        it must not even construct a broker adapter (which would require live credentials)."""
        with (
            patch("algo.risk.CircuitBreaker") as MockCB,
            patch("algo.infrastructure.MarketEventHandler") as MockMEH,
            patch("algo.infrastructure.alpaca_broker_adapter.AlpacaBrokerAdapter") as MockBroker,
        ):
            MockCB.return_value.check_all.return_value = _clean_cb_result()
            MockMEH.return_value.check_market_circuit_breaker.return_value = None

            result = phase2_run(
                config=_paper_config(),
                run_date=None,
                dry_run=True,
                alerts=MagicMock(),
                verbose=False,
                log_phase_result_fn=MagicMock(),
            )

        assert result.halted is False
        assert result.status == "ok"
        MockBroker.assert_not_called()
