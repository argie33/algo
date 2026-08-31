"""Coverage test for algo/risk/liquidity_checks.py - found 2026-08-31 via an objective
coverage-analysis pass to have only 12.73% statement coverage despite being real, live trading
logic: called from algo/trading/executor_exit_handler.py and algo/orchestration/position_sync.py.
Every failure path in this class is deliberately fail-closed (blocks the trade on any missing
data or DB error) rather than fail-open - these tests exist to lock that contract in, not just
raise the coverage number.
"""

from datetime import date
from unittest.mock import patch

import psycopg2
import pytest

from algo.risk.liquidity_checks import LiquidityChecks

CONFIG = {
    "min_adv_shares": 300000,
    "min_adv_dollars": 500000.0,
    "min_price_history_days": 200,
}


def _checks():
    return LiquidityChecks(dict(CONFIG))


class TestLiquidityChecksInit:
    def test_raises_when_min_adv_shares_missing(self):
        with pytest.raises(ValueError, match="min_adv_shares"):
            LiquidityChecks({"min_adv_dollars": 1.0, "min_price_history_days": 200})

    def test_raises_when_min_adv_dollars_missing(self):
        with pytest.raises(ValueError, match="min_adv_dollars"):
            LiquidityChecks({"min_adv_shares": 1, "min_price_history_days": 200})


class TestRunAll:
    def test_blocks_when_signal_date_missing(self):
        checks = _checks()
        passed, reason = checks.run_all("AAPL", 100.0, signal_date=None)
        assert passed is False
        assert "no signal_date" in reason

    def test_passes_when_all_three_sub_checks_pass(self):
        checks = _checks()
        with (
            patch.object(checks, "_check_price_history_age", return_value=(True, "ok")),
            patch.object(checks, "_check_adv", return_value=(True, "ok")),
            patch.object(checks, "_check_dollar_volume", return_value=(True, "ok")),
        ):
            passed, reason = checks.run_all("AAPL", 100.0, signal_date=date(2026, 1, 15))
        assert passed is True

    def test_blocks_when_age_check_fails(self):
        checks = _checks()
        with (
            patch.object(checks, "_check_price_history_age", return_value=(False, "too new")),
            patch.object(checks, "_check_adv", return_value=(True, "ok")),
            patch.object(checks, "_check_dollar_volume", return_value=(True, "ok")),
        ):
            passed, reason = checks.run_all("AAPL", 100.0, signal_date=date(2026, 1, 15))
        assert passed is False
        assert "IPO age check failed" in reason

    def test_blocks_when_adv_check_fails(self):
        checks = _checks()
        with (
            patch.object(checks, "_check_price_history_age", return_value=(True, "ok")),
            patch.object(checks, "_check_adv", return_value=(False, "too thin")),
            patch.object(checks, "_check_dollar_volume", return_value=(True, "ok")),
        ):
            passed, reason = checks.run_all("AAPL", 100.0, signal_date=date(2026, 1, 15))
        assert passed is False
        assert "ADV check failed" in reason

    def test_blocks_when_dollar_volume_check_fails(self):
        checks = _checks()
        with (
            patch.object(checks, "_check_price_history_age", return_value=(True, "ok")),
            patch.object(checks, "_check_adv", return_value=(True, "ok")),
            patch.object(checks, "_check_dollar_volume", return_value=(False, "too thin")),
        ):
            passed, reason = checks.run_all("AAPL", 100.0, signal_date=date(2026, 1, 15))
        assert passed is False
        assert "Dollar volume check failed" in reason

    def test_blocks_on_database_error_fail_closed(self):
        checks = _checks()
        with patch.object(checks, "_check_price_history_age", side_effect=psycopg2.OperationalError("connection lost")):
            passed, reason = checks.run_all("AAPL", 100.0, signal_date=date(2026, 1, 15))
        assert passed is False
        assert "blocking as safety measure" in reason


class TestCheckAdv:
    def test_passes_when_volume_above_minimum(self):
        checks = _checks()
        with patch("algo.risk.liquidity_checks.DatabaseContext") as MockDB:
            MockDB.return_value.__enter__.return_value.fetchone.return_value = (500000.0,)
            passed, reason = checks._check_adv("AAPL", date(2026, 1, 15))
        assert passed is True

    def test_fails_when_volume_below_minimum(self):
        checks = _checks()
        with patch("algo.risk.liquidity_checks.DatabaseContext") as MockDB:
            MockDB.return_value.__enter__.return_value.fetchone.return_value = (1000.0,)
            passed, reason = checks._check_adv("AAPL", date(2026, 1, 15))
        assert passed is False
        assert "minimum" in reason

    def test_fails_closed_when_no_volume_data(self):
        checks = _checks()
        with patch("algo.risk.liquidity_checks.DatabaseContext") as MockDB:
            MockDB.return_value.__enter__.return_value.fetchone.return_value = None
            passed, reason = checks._check_adv("AAPL", date(2026, 1, 15))
        assert passed is False
        assert "No volume data" in reason

    def test_fails_closed_when_avg_vol_is_none(self):
        checks = _checks()
        with patch("algo.risk.liquidity_checks.DatabaseContext") as MockDB:
            MockDB.return_value.__enter__.return_value.fetchone.return_value = (None,)
            passed, reason = checks._check_adv("AAPL", date(2026, 1, 15))
        assert passed is False


class TestCheckDollarVolume:
    def test_passes_when_dollar_volume_above_minimum(self):
        checks = _checks()
        with patch("algo.risk.liquidity_checks.DatabaseContext") as MockDB:
            MockDB.return_value.__enter__.return_value.fetchone.return_value = (1000000.0,)
            passed, reason = checks._check_dollar_volume("AAPL", date(2026, 1, 15))
        assert passed is True

    def test_fails_when_dollar_volume_below_minimum(self):
        checks = _checks()
        with patch("algo.risk.liquidity_checks.DatabaseContext") as MockDB:
            MockDB.return_value.__enter__.return_value.fetchone.return_value = (100.0,)
            passed, reason = checks._check_dollar_volume("AAPL", date(2026, 1, 15))
        assert passed is False

    def test_fails_closed_when_no_price_data(self):
        checks = _checks()
        with patch("algo.risk.liquidity_checks.DatabaseContext") as MockDB:
            MockDB.return_value.__enter__.return_value.fetchone.return_value = None
            passed, reason = checks._check_dollar_volume("AAPL", date(2026, 1, 15))
        assert passed is False
        assert "No price data" in reason


class TestCheckPriceHistoryAge:
    def test_passes_when_enough_trading_days(self):
        checks = _checks()
        with patch("algo.risk.liquidity_checks.DatabaseContext") as MockDB:
            MockDB.return_value.__enter__.return_value.fetchone.return_value = (250, date(2025, 1, 1))
            passed, reason = checks._check_price_history_age("AAPL", date(2026, 1, 15))
        assert passed is True

    def test_fails_when_too_few_trading_days(self):
        checks = _checks()
        with patch("algo.risk.liquidity_checks.DatabaseContext") as MockDB:
            MockDB.return_value.__enter__.return_value.fetchone.return_value = (50, date(2025, 11, 1))
            passed, reason = checks._check_price_history_age("AAPL", date(2026, 1, 15))
        assert passed is False
        assert "50 trading days" in reason

    def test_fails_closed_when_no_price_history_at_all(self):
        checks = _checks()
        with patch("algo.risk.liquidity_checks.DatabaseContext") as MockDB:
            MockDB.return_value.__enter__.return_value.fetchone.return_value = (0, None)
            passed, reason = checks._check_price_history_age("AAPL", date(2026, 1, 15))
        assert passed is False
        assert "No price history" in reason

    def test_raises_when_min_price_history_days_config_missing(self):
        checks = LiquidityChecks({"min_adv_shares": 1, "min_adv_dollars": 1.0})
        with patch("algo.risk.liquidity_checks.DatabaseContext"):
            passed, reason = checks._check_price_history_age("AAPL", date(2026, 1, 15))
        assert passed is False
        assert "blocking as safety measure" in reason


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
