"""Regression test for the 2026-09-15 fix to scripts/fix_missing_stock_splits.py's
apply_split_adjustment(): the NUMERIC(12,4) overflow guard originally checked only
GREATEST(open, high, low, close) against the split adjustment factor, missing that
price_daily's adj_close column can hold a LARGER historical value than the raw OHLC columns
(live-confirmed on FXHO: adj_close max $597,500 vs close max $112,500 pre-split) and is
multiplied by the same UPDATE. That caused the UPDATE itself to raise NumericValueOutOfRange
mid-transaction (crashing the whole symbol, including its already-applied earlier splits)
instead of the guard cleanly excluding the offending row up front.
"""

from unittest.mock import MagicMock

from scripts.fix_missing_stock_splits import _NUMERIC_12_4_MAX, apply_split_adjustment


class TestApplySplitAdjustmentOverflowGuard:
    def test_price_daily_bounds_check_includes_adj_close(self):
        cur = MagicMock()
        cur.fetchone.return_value = (0,)
        cur.rowcount = 5

        apply_split_adjustment(cur, "FXHO", "2026-02-17", ratio=0.2)

        select_calls = [c for c in cur.execute.call_args_list if "SELECT count(*)" in c.args[0]]
        price_daily_select = next(c for c in select_calls if "price_daily" in c.args[0])
        assert "adj_close" in price_daily_select.args[0]
        assert "GREATEST(open, high, low, close, adj_close)" in price_daily_select.args[0]

        update_calls = [c for c in cur.execute.call_args_list if "UPDATE" in c.args[0]]
        price_daily_update = next(c for c in update_calls if "price_daily" in c.args[0])
        assert "adj_close" in price_daily_update.args[0]

    def test_weekly_monthly_bounds_check_excludes_adj_close(self):
        cur = MagicMock()
        cur.fetchone.return_value = (0,)
        cur.rowcount = 0

        apply_split_adjustment(cur, "FXHO", "2026-02-17", ratio=0.2)

        select_calls = [c for c in cur.execute.call_args_list if "SELECT count(*)" in c.args[0]]
        for table in ("price_weekly", "price_monthly"):
            select_call = next(c for c in select_calls if table in c.args[0])
            assert "GREATEST(open, high, low, close)" in select_call.args[0]
            assert "adj_close" not in select_call.args[0]

    def test_overflowing_row_excluded_from_update_not_crashed(self):
        """A row whose adj_close * adjust_factor would exceed NUMERIC(12,4)'s cap must be
        reported via the skip count, not left to the UPDATE to discover via a DB exception."""
        cur = MagicMock()
        # price_daily: 1 row over the cap; price_weekly/monthly: none.
        cur.fetchone.side_effect = [(1,), (0,), (0,)]
        cur.rowcount = 100

        counts = apply_split_adjustment(cur, "FXHO", "2026-02-17", ratio=0.2)

        assert counts["price_daily"] == 100
        select_calls = [c for c in cur.execute.call_args_list if "SELECT count(*)" in c.args[0]]
        params = select_calls[0].args[1]
        assert params[-1] == _NUMERIC_12_4_MAX
        assert params[-2] == 5.0  # adjust_factor = 1/ratio = 1/0.2
