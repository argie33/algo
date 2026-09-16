"""Regression test: a KeyError from pretrade_checks.run_all() (missing/misspelled
algo_config field) must be rejected as a clean validation failure, not raise uncaught.

BUG FOUND 2026-09-10 (/goal pre-live-money audit, order-execution re-audit): pretrade_checks.py
deliberately raises a bare KeyError (not ValueError) for a missing required algo_config field
(max_position_correlation, sector caps, VaR/beta thresholds, etc - ~8 call sites) - correct
fail-fast design at that layer. But validate_entry_preconditions() here only caught ValueError
around the run_all() call, so the KeyError propagated uncaught. phase8_entry_execution.py's
per-signal loop (at the time) also didn't catch KeyError, so a single missing config key would
silently abort entry processing for every remaining signal that day, not just the one being
checked - same bug class as test_trade_validator_nan_invalid_operation_isolates_signal.py's
decimal.InvalidOperation gap, and test_phase8_trade_result_missing_status_key_no_keyerror_
20260906.py's sibling KeyError gap at a different call site.
"""

from decimal import Decimal
from unittest.mock import MagicMock

from algo.trading.trade_validator import TradeValidator


def _make_validator(pretrade_checks):
    config = {
        "t1_target_r_multiple": 2.0,
        "t2_target_r_multiple": 3.0,
        "t3_target_r_multiple": 4.0,
        "max_reentries_per_name": 3,
        "min_days_before_reentry_same_symbol": 8,
        "wash_sale_cooldown_days": 31,
    }
    return TradeValidator(config, pretrade_checks=pretrade_checks)


def test_pretrade_check_keyerror_returns_clean_failure_not_raises():
    pretrade_checks = MagicMock()
    pretrade_checks.run_all.side_effect = KeyError("max_position_correlation")
    validator = _make_validator(pretrade_checks)

    valid, error_msg, result = validator.validate_entry_preconditions(
        symbol="TESTSYM",
        entry_price=100.0,
        stop_loss_price=90.0,
        shares=10,
        portfolio_value=Decimal("100000"),
    )

    assert valid is False
    assert error_msg is not None
    assert "Pre-trade check failed" in error_msg
    assert result == {}
