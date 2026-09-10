"""Regression tests for algo/risk/intraday_risk_monitor.py (2026-09-06, real-money-readiness
audit, halt-wiring added 2026-09-10): closes the documented
`intraday_monitoring_architecture_gap` by re-checking portfolio beta / top-5 concentration
against LIVE broker state between full orchestrator runs. A breach now also sets a
HaltFlagManager halt (blocks NEW entries only, per the user's explicit direction - existing
positions still exit only through their own configured stop/exit logic) in addition to
alerting; a clean recheck self-clears only a halt this module itself previously set. See
that module's own docstring for the full design rationale.
"""

from unittest.mock import MagicMock, patch

from algo.risk.intraday_risk_monitor import check_intraday_risk


def _config(**overrides):
    base = {"max_portfolio_beta": 2.0, "max_top5_concentration_pct": 30.0}
    base.update(overrides)
    return base


def _halt_manager(current_trigger=None):
    hm = MagicMock()
    hm.get_halt_triggered_by.return_value = current_trigger
    return hm


class _FakeCursor:
    def __init__(self, beta_rows):
        self._beta_rows = beta_rows

    def execute(self, query, params=None):
        assert "FROM stability_metrics" in query

    def fetchall(self):
        return self._beta_rows


class _FakeDbContext:
    def __init__(self, beta_rows):
        self._cur = _FakeCursor(beta_rows)

    def __enter__(self):
        return self._cur

    def __exit__(self, *a):
        return False


def _patched(positions, account, beta_rows):
    broker = MagicMock()
    broker.fetch_account.return_value = account
    broker.fetch_positions.return_value = positions
    return (
        patch("algo.risk.intraday_risk_monitor.AlpacaBrokerAdapter", return_value=broker),
        patch("algo.risk.intraday_risk_monitor.DatabaseContext", return_value=_FakeDbContext(beta_rows)),
    )


class TestIntradayRiskMonitor:
    def test_no_open_positions_reports_zero_exposure_no_alert(self):
        alerts = MagicMock()
        halt_manager = _halt_manager()
        p1, p2 = _patched([], {"portfolio_value": 100_000.0}, [])
        with p1, p2:
            result = check_intraday_risk(_config(), alerts=alerts, halt_manager=halt_manager)
        assert result["portfolio_beta"] == 0.0
        assert result["top5_concentration_pct"] == 0.0
        assert result["beta_breach"] is False
        alerts.send_position_alert.assert_not_called()
        halt_manager.set_halt_flag.assert_not_called()
        halt_manager.clear_halt_flag.assert_not_called()

    def test_no_open_positions_self_clears_its_own_prior_halt(self):
        # The book went flat (positions closed via their own stop/exit logic) since the last
        # breach - nothing left to be over-cap on, so this check's own halt should release.
        alerts = MagicMock()
        halt_manager = _halt_manager(current_trigger="intraday_risk_monitor")
        p1, p2 = _patched([], {"portfolio_value": 100_000.0}, [])
        with p1, p2:
            check_intraday_risk(_config(), alerts=alerts, halt_manager=halt_manager)
        halt_manager.clear_halt_flag.assert_called_once()
        assert halt_manager.clear_halt_flag.call_args.kwargs["allowed_triggers"] == frozenset({"intraday_risk_monitor"})

    def test_beta_drift_past_cap_from_price_movement_alone_triggers_alert_and_halt(self):
        # Regression shape for the exact gap this module closes: no NEW entry here, just an
        # existing position (HELD) whose live market_value now dominates the book (e.g. it
        # ran up hard intraday) at beta 3.0 - portfolio beta = (80000*3.0)/100000 = 2.4 > 2.0.
        alerts = MagicMock()
        halt_manager = _halt_manager()
        positions = [{"symbol": "HELD", "qty": 400.0, "market_value": 80_000.0, "current_price": 200.0}]
        account = {"portfolio_value": 100_000.0}
        beta_rows = [("HELD", 3.0)]
        p1, p2 = _patched(positions, account, beta_rows)
        with p1, p2:
            result = check_intraday_risk(_config(), alerts=alerts, halt_manager=halt_manager)
        assert result["beta_breach"] is True
        assert abs(result["portfolio_beta"] - 2.4) < 1e-9
        alerts.send_position_alert.assert_called_once()
        call_args = alerts.send_position_alert.call_args
        assert call_args[0][0] == "PORTFOLIO"
        assert call_args[0][1] == "INTRADAY_RISK_BREACH"
        halt_manager.set_halt_flag.assert_called_once()
        halt_set_args = halt_manager.set_halt_flag.call_args
        assert halt_set_args.kwargs["triggered_by"] == "intraday_risk_monitor"
        halt_manager.clear_halt_flag.assert_not_called()

    def test_concentration_breach_triggers_alert_and_halt(self):
        alerts = MagicMock()
        halt_manager = _halt_manager()
        positions = [
            {"symbol": s, "qty": 100.0, "market_value": 20_000.0, "current_price": 200.0}
            for s in ["A", "B", "C", "D", "E", "F"]
        ]
        account = {"portfolio_value": 100_000.0}  # top5 = 100,000 -> 100% > 30% cap
        beta_rows = [(s, 1.0) for s in ["A", "B", "C", "D", "E", "F"]]
        p1, p2 = _patched(positions, account, beta_rows)
        with p1, p2:
            result = check_intraday_risk(_config(), alerts=alerts, halt_manager=halt_manager)
        assert result["concentration_breach"] is True
        alerts.send_position_alert.assert_called_once()
        halt_manager.set_halt_flag.assert_called_once()
        assert halt_manager.set_halt_flag.call_args.kwargs["triggered_by"] == "intraday_risk_monitor"

    def test_within_caps_no_alert_no_halt(self):
        alerts = MagicMock()
        halt_manager = _halt_manager()
        positions = [{"symbol": "HELD", "qty": 100.0, "market_value": 10_000.0, "current_price": 100.0}]
        account = {"portfolio_value": 100_000.0}
        beta_rows = [("HELD", 1.0)]
        p1, p2 = _patched(positions, account, beta_rows)
        with p1, p2:
            result = check_intraday_risk(_config(), alerts=alerts, halt_manager=halt_manager)
        assert result["beta_breach"] is False
        assert result["concentration_breach"] is False
        alerts.send_position_alert.assert_not_called()
        halt_manager.set_halt_flag.assert_not_called()
        halt_manager.clear_halt_flag.assert_not_called()

    def test_within_caps_self_clears_its_own_prior_halt(self):
        alerts = MagicMock()
        halt_manager = _halt_manager(current_trigger="intraday_risk_monitor")
        positions = [{"symbol": "HELD", "qty": 100.0, "market_value": 10_000.0, "current_price": 100.0}]
        account = {"portfolio_value": 100_000.0}
        beta_rows = [("HELD", 1.0)]
        p1, p2 = _patched(positions, account, beta_rows)
        with p1, p2:
            check_intraday_risk(_config(), alerts=alerts, halt_manager=halt_manager)
        halt_manager.clear_halt_flag.assert_called_once()
        assert halt_manager.clear_halt_flag.call_args.kwargs["allowed_triggers"] == frozenset({"intraday_risk_monitor"})

    def test_within_caps_never_clears_a_halt_set_by_another_origin(self):
        # A Phase 2 circuit-breaker halt (or Phase 1/Phase 9/manual) must never be released
        # just because THIS check happens to be clean right now.
        alerts = MagicMock()
        halt_manager = _halt_manager(current_trigger="phase2_circuit_breaker")
        positions = [{"symbol": "HELD", "qty": 100.0, "market_value": 10_000.0, "current_price": 100.0}]
        account = {"portfolio_value": 100_000.0}
        beta_rows = [("HELD", 1.0)]
        p1, p2 = _patched(positions, account, beta_rows)
        with p1, p2:
            check_intraday_risk(_config(), alerts=alerts, halt_manager=halt_manager)
        halt_manager.clear_halt_flag.assert_not_called()

    def test_missing_beta_symbol_conservatively_assumed_and_reported(self):
        # REAL-MONEY-READINESS FIX (2026-09-06 audit): a missing-beta position used to be
        # excluded entirely from the weighted sum - its dollar value still counted in the
        # denominator but contributed nothing to the numerator, equivalent to silently
        # assuming beta=0.0 for it and understating true portfolio beta. It's now weighted at
        # a conservative assumed beta=1.0 instead, while still being reported separately via
        # symbols_missing_beta.
        alerts = MagicMock()
        halt_manager = _halt_manager()
        positions = [
            {"symbol": "KNOWN", "qty": 100.0, "market_value": 50_000.0, "current_price": 500.0},
            {"symbol": "UNKNOWN", "qty": 100.0, "market_value": 50_000.0, "current_price": 500.0},
        ]
        account = {"portfolio_value": 100_000.0}
        beta_rows = [("KNOWN", 1.0)]  # UNKNOWN has no stability_metrics row
        p1, p2 = _patched(positions, account, beta_rows)
        with p1, p2:
            result = check_intraday_risk(_config(), alerts=alerts, halt_manager=halt_manager)
        # KNOWN contributes 50000*1.0, UNKNOWN conservatively assumed at beta=1.0 contributes
        # 50000*1.0 too: (50000*1.0 + 50000*1.0)/100000 = 1.0
        assert abs(result["portfolio_beta"] - 1.0) < 1e-9
        assert result["symbols_missing_beta"] == ["UNKNOWN"]

    def test_non_positive_portfolio_value_with_open_positions_raises(self):
        # Same "never report a fake safe reading against a bad denominator" discipline as
        # pretrade_checks.py/var.py - a broker-reported zero/negative equity with real open
        # positions is a data integrity failure, not "zero exposure."
        alerts = MagicMock()
        halt_manager = _halt_manager()
        positions = [{"symbol": "HELD", "qty": 100.0, "market_value": 10_000.0, "current_price": 100.0}]
        account = {"portfolio_value": 0.0}
        p1, p2 = _patched(positions, account, [])
        with p1, p2:
            try:
                check_intraday_risk(_config(), alerts=alerts, halt_manager=halt_manager)
                raise AssertionError("expected RuntimeError")
            except RuntimeError:
                pass
        alerts.send_position_alert.assert_not_called()
        halt_manager.set_halt_flag.assert_not_called()

    def test_missing_config_key_raises(self):
        alerts = MagicMock()
        halt_manager = _halt_manager()
        positions = [{"symbol": "HELD", "qty": 100.0, "market_value": 10_000.0, "current_price": 100.0}]
        account = {"portfolio_value": 100_000.0}
        beta_rows = [("HELD", 1.0)]
        p1, p2 = _patched(positions, account, beta_rows)
        with p1, p2:
            try:
                check_intraday_risk(
                    {"max_portfolio_beta": 2.0}, alerts=alerts, halt_manager=halt_manager
                )  # missing top5 key
                raise AssertionError("expected KeyError")
            except KeyError:
                pass
