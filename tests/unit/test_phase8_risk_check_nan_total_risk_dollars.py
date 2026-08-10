#!/usr/bin/env python3
"""Regression test: Phase 8's _calculate_current_total_risk_pct() silently let a NaN/Infinity
total_risk_dollars bypass its own out-of-range detection entirely (algo/orchestrator/
phase8_entry_execution.py).

Same NaN-propagation bug class found and fixed repeatedly this session (position_sizer.py,
financial.py, phase8's stop-loss calc, exit_engine.py, order_manager.py, phase7_signal_
generation.py, market_factor_calculator.py) - but a distinct, worse manifestation here: the
existing guard is written as `if current_risk_pct < 0 or current_risk_pct > 100: ... clamp`.
Every comparison against NaN is False, so with NaN input BOTH branches of that condition are
False - the anomaly is never logged AND the value is never clamped. A NaN total_risk_dollars
(e.g. from a corrupted stop-loss/entry-price feeding SUM(GREATEST(0, ...))) would silently
reach available_risk_pct and the real-money entry decision as raw NaN, undetected.

Fixed by rejecting non-finite total_risk_dollars immediately after the SUM query, before any
comparison can silently swallow it.
"""

import math
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase8_entry_execution import _calculate_current_total_risk_pct


class TestRiskCheckRejectsNonFiniteTotalRiskDollars(unittest.TestCase):
    def _run_with_total_risk(self, total_risk_dollars):
        with patch("algo.orchestrator.phase8_entry_execution.DatabaseContext") as mock_db:
            mock_cur = MagicMock()
            mock_cur.fetchone.side_effect = [
                (0, None),  # incomplete_count check: no incomplete rows
                (total_risk_dollars, 3),  # total_risk_dollars, open_count
                (100_000.0,),  # portfolio value
            ]
            mock_db.return_value.__enter__.return_value = mock_cur
            return _calculate_current_total_risk_pct(max_risk_limit_pct=4.0, run_date=date(2026, 8, 10))

    def test_nan_total_risk_dollars_raises_instead_of_bypassing_range_check(self):
        # Without the fix: `nan < 0 or nan > 100` is False (NaN fails every comparison), so
        # the anomaly branch that would normally log+clamp never fires - NaN flows through
        # to available_risk_pct completely undetected.
        assert not (float("nan") < 0 or float("nan") > 100)
        with self.assertRaises(RuntimeError) as ctx:
            self._run_with_total_risk(float("nan"))
        self.assertIn("non-finite", str(ctx.exception).lower())

    def test_infinity_total_risk_dollars_raises(self):
        with self.assertRaises(RuntimeError) as ctx:
            self._run_with_total_risk(float("inf"))
        self.assertIn("non-finite", str(ctx.exception).lower())

    def test_finite_total_risk_dollars_still_works(self):
        current_risk_pct, available_risk_pct = self._run_with_total_risk(2000.0)
        self.assertAlmostEqual(current_risk_pct, 2.0)
        self.assertAlmostEqual(available_risk_pct, 2.0)
        self.assertFalse(math.isnan(current_risk_pct))


if __name__ == "__main__":
    unittest.main()
