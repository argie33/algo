#!/usr/bin/env python3
"""Regression test for ExitEngine._chandelier_or_ema_stop's chandelier branch (days_held <
switch_to_21ema_after_days), found via the 2026-09-09 real-money-readiness audit as the
sibling bug to test_exit_engine_ema_stop_split_adjustment_20260909.py.

price_daily.high was previously read via a raw SQL MAX(high) with zero split adjustment,
while technical_data_daily.atr (fixed earlier the same session, commit 256b71db7) IS already
split-adjusted at the source. Mixing a raw pre-split highest-high with a split-adjusted ATR
produces stop_value = hh - mult*atr far above the real post-split current price - a false
stop-out waiting to fire on a real open position right after a legitimate split, in the
highest-frequency stop window (the first ~10 days of a position). Fixed by running the same
detect_and_adjust_splits() used by the 21-EMA branch on the fetched high/close series before
taking the max.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from algo.trading.exit_engine import ExitEngine

CONFIG = {
    "switch_to_21ema_after_days": 10,
    "chandelier_atr_mult": 3.0,
}


def _fake_self():
    return SimpleNamespace(config=dict(CONFIG))


def _mock_cursor_chandelier(rows):
    """rows: list of (close, high, atr) ascending by date (oldest first)."""
    cur = MagicMock()
    n = len(rows)
    cur.fetchall.return_value = [(c, h, a, n - i) for i, (c, h, a) in enumerate(rows)]
    return cur


class TestChandelierHighestHighAdjustsForSplits:
    def test_split_mid_window_does_not_produce_stop_above_market(self):
        """5-row window: 2 pre-split rows around ~150-160, then a clean 2:1 split down to
        ~80 for the remaining 3 rows. Post-split ATR (already split-adjusted upstream) is
        ~1.5. Without adjusting `high`, MAX(high) would stay ~160 (pre-split), producing
        stop_value = 160 - 3*1.5 = 155.5 - far above the real post-split price of ~85.
        With adjustment, the stop must land below the current price."""
        rows = [
            (150.0, 152.0, None),
            (160.0, 162.0, None),  # prior_close 160.0 -> next close 80.0 = exact 2:1 split ratio
            (80.0, 83.0, 1.5),
            (84.0, 85.0, 1.6),
            (85.0, 86.0, 1.5),  # most recent (rn=1) - atr used is this row's
        ]
        current_price = 85.0

        cur = _mock_cursor_chandelier(rows)
        stop = ExitEngine._chandelier_or_ema_stop(_fake_self(), cur, "SPLITSYM", None, days_held=5)

        assert stop is not None
        assert stop < current_price, (
            f"split-adjusted chandelier stop ({stop}) must be below the post-split current "
            f"price ({current_price}) - a stop above current price means the position would "
            f"be stopped out immediately on a legitimate split, not a real decline"
        )
        assert 70.0 < stop < 90.0

    def test_no_split_still_computes_normally(self):
        """No split in the window - detect_and_adjust_splits() must be a no-op, matching
        pre-fix behavior exactly for the common case."""
        rows = [
            (100.0, 101.0, None),
            (100.5, 101.5, None),
            (101.0, 102.0, 1.2),
            (101.5, 102.5, 1.2),
            (102.0, 103.0, 1.3),
        ]
        cur = _mock_cursor_chandelier(rows)
        stop = ExitEngine._chandelier_or_ema_stop(_fake_self(), cur, "NOSPLITSYM", None, days_held=5)
        assert stop is not None
        # MAX(high) = 103.0, atr (most recent row) = 1.3, mult = 3.0 -> 103 - 3.9 = 99.1
        assert stop == 99.1
