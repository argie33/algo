"""Regression test for a 2026-08-10 fix in algo/trading/position_sizer.py::
_calculate_with_external_cursor(): the max_position_size_pct cap could round the share
count down to 0 (a stock priced above max_position_size_pct * portfolio_value - e.g.
entry_price=$600 with a $10k portfolio and a 5% cap, max_position_value=$500), and unlike
its two sibling scaling branches (concentration-limit scale-down, total-risk-limit
scale-down - both of which explicitly return a "no room" status when their own scale-down
rounds to 0 shares), this cap never re-checked `shares < 1` after rounding down. The
0-share result fell through every remaining check (concentration/total-invested/total-risk
all trivially pass at position_value=0) to the function's own final
`return {..., "status": "ok"}` - a 0-share result reported as success, violating this
function's own documented status contract.

Not previously causing a live bad order - every one of Phase 8's 3 call sites already
independently re-checks `shares < 1` regardless of `status` before using the result - but
that safety was accidental (each caller happening to defensively re-check the raw share
count), not a contract this function itself upheld. Fixed by returning an explicit
status="no_room" result, matching the pattern already used by the sibling scaling branches.
"""

from decimal import Decimal
from unittest.mock import patch

from algo.trading.position_sizer import PositionSizer

CONFIG = {
    "base_risk_pct": 1.0,
    "max_positions": 15,
    "min_risk_pct_floor": 0.5,
    "max_position_size_pct": 5.0,
    "max_concentration_pct": 20.0,
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
        patch.object(sizer, "get_active_positions_value", return_value=Decimal("0")),
        patch.object(sizer, "get_risk_adjustment", return_value=Decimal("1.0")),
        patch.object(sizer, "get_market_exposure_multiplier", return_value=Decimal("1.0")),
        patch.object(sizer, "get_phase_size_multiplier", return_value=1.0),
        patch.object(sizer, "get_vix_caution_multiplier", return_value=Decimal("1.0")),
        patch.object(sizer, "get_position_size_multiplier_from_regime", return_value=1.0),
    )


class TestMaxPositionPctZeroShareCap:
    def test_high_priced_stock_below_cap_returns_no_room_not_ok(self):
        """$10k portfolio, 5% cap -> max_position_value=$500. A $600 stock can't buy even
        1 share within that cap - must be rejected with status='no_room', not reported as
        a fake 'ok' success at shares=0."""
        sizer = _make_sizer()
        patches = _patched(sizer)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            result = sizer._calculate_with_external_cursor(
                symbol="EXPENSIVE",
                entry_price=Decimal("600"),
                stop_loss_price=Decimal("580"),
                portfolio_value=Decimal("10000"),
                enforce_total_risk_limit=False,
            )

        assert result["shares"] == 0
        assert result["status"] != "ok", (
            f"A 0-share result must never report status='ok' - callers that trust the "
            f"status field without independently re-checking shares would silently treat "
            f"this as a valid position. Got: {result}"
        )
        assert result["status"] == "no_room"

    def test_normal_priced_stock_still_sizes_correctly(self):
        """Sanity check: the fix must not affect the normal (cap not binding) path."""
        sizer = _make_sizer()
        patches = _patched(sizer)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            result = sizer._calculate_with_external_cursor(
                symbol="AAPL",
                entry_price=Decimal("100"),
                stop_loss_price=Decimal("90"),
                portfolio_value=Decimal("100000"),
                enforce_total_risk_limit=False,
            )

        assert result["status"] == "ok"
        assert result["shares"] >= 1

    def test_borderline_one_share_still_fits_within_cap(self):
        """$10k portfolio, 5% cap -> max_position_value=$500. A $499 stock can afford
        exactly 1 share within the cap - must NOT be incorrectly rejected."""
        sizer = _make_sizer()
        patches = _patched(sizer)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            result = sizer._calculate_with_external_cursor(
                symbol="BORDERLINE",
                entry_price=Decimal("499"),
                stop_loss_price=Decimal("480"),
                portfolio_value=Decimal("10000"),
                enforce_total_risk_limit=False,
            )

        assert result["shares"] >= 1
        assert result["status"] == "ok"
