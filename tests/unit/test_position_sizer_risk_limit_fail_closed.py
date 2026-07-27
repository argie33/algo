#!/usr/bin/env python3
"""Regression test for a 2026-07-27 fix in algo/trading/position_sizer.py::
_calculate_with_external_cursor(): when enforce_total_risk_limit=True and the aggregate
open-risk query (SUM across algo_positions/algo_trades) fails for any reason, the code used
to log a warning and silently fall through to the UNSCALED position size computed before the
risk-limit check ever ran - the comment justified this as "circuit breaker will catch it",
but Phase 2 (circuit breakers) runs BEFORE Phase 8 (entry execution) in every orchestrator
cycle, so it cannot retroactively catch an aggregate-risk breach created by that same cycle's
own entries - only the NEXT cycle's Phase 2 run would see it, after the oversized positions
are already open.

This was the one fail-OPEN exception in an otherwise entirely fail-CLOSED function (every
other validation failure here - missing config, invalid portfolio value, bad prices - blocks
the trade). Fixed to return status="risk_check_unavailable" (blocking just this one symbol's
entry, not the whole batch - matching how Phase 8 already handles per-symbol failures)
instead of silently proceeding with an unenforced aggregate-risk limit.
"""

from decimal import Decimal
from unittest.mock import patch

from algo.trading.position_sizer import PositionSizer

CONFIG = {
    "base_risk_pct": 1.0,
    "max_positions": 15,
    "min_risk_pct_floor": 0.5,
    "max_position_size_pct": 10.0,
    "max_concentration_pct": 15.0,
    "max_total_invested_pct": 90.0,
    "max_total_risk_pct": 4.0,
    "risk_reduction_at_minus_5": 0.75,
    "risk_reduction_at_minus_10": 0.5,
    "risk_reduction_at_minus_15": 0.25,
    "risk_reduction_at_minus_20": 0.0,
    "vix_caution_threshold": 25.0,
    "vix_max_threshold": 35.0,
    "vix_caution_risk_reduction": 0.5,
}


def _make_sizer():
    return PositionSizer(config=dict(CONFIG))


def _patched(sizer):
    return (
        patch.object(sizer, "get_position_count", return_value=1),
        patch.object(sizer, "get_active_positions_value", return_value=Decimal("10000")),
        patch.object(sizer, "get_risk_adjustment", return_value=Decimal("1.0")),
        patch.object(sizer, "get_market_exposure_multiplier", return_value=Decimal("1.0")),
        patch.object(sizer, "get_phase_size_multiplier", return_value=1.0),
        patch.object(sizer, "get_vix_caution_multiplier", return_value=Decimal("1.0")),
        patch.object(sizer, "get_position_size_multiplier_from_regime", return_value=1.0),
    )


def _call_with_broken_risk_query(sizer, **kwargs):
    defaults = dict(
        symbol="AAPL",
        entry_price=Decimal("100"),
        stop_loss_price=Decimal("90"),
        portfolio_value=Decimal("100000"),
        enforce_total_risk_limit=True,
    )
    defaults.update(kwargs)
    patches = _patched(sizer)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patch(
        "algo.trading.position_sizer.DatabaseContext", side_effect=RuntimeError("DB unavailable")
    ):
        return sizer._calculate_with_external_cursor(**defaults)


class TestPositionSizerRiskLimitFailsClosed:
    def test_risk_limit_query_failure_blocks_entry_not_silently_proceeds(self):
        sizer = _make_sizer()
        result = _call_with_broken_risk_query(sizer)

        assert result["shares"] == 0, (
            f"Expected a blocked entry (0 shares) when the aggregate open-risk check itself "
            f"fails, not the unscaled pre-risk-limit share count. Got: {result}"
        )
        assert result["status"] == "risk_check_unavailable"

    def test_healthy_risk_query_still_returns_normal_sizing(self):
        """Sanity check: the fix must not break the normal (query succeeds) path."""
        sizer = _make_sizer()
        defaults = dict(
            symbol="AAPL",
            entry_price=Decimal("100"),
            stop_loss_price=Decimal("90"),
            portfolio_value=Decimal("100000"),
            enforce_total_risk_limit=True,
        )
        patches = _patched(sizer)
        mock_cur = patch("algo.trading.position_sizer.DatabaseContext")
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], mock_cur as MockDB:
            MockDB.return_value.__enter__.return_value.fetchone.return_value = (Decimal("500"),)
            result = sizer._calculate_with_external_cursor(**defaults)

        assert result["status"] == "ok"
        assert result["shares"] > 0
