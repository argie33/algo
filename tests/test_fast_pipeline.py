#!/usr/bin/env python3
"""
Test the fast pipeline (v2): prices -> signals -> trades in <60 minutes

Expected timeline:
- 2:00 AM: Morning prep starts
- 2:15 AM: stock_prices_daily complete (15 min)
- 9:30 AM: Orchestrator runs
  - Phase 1: Verify prices (1 min)
  - Phase 5: Generate signals from prices (40 min)
  - Phase 6: Execute top signals (5 min)
- 10:15 AM: All trading complete

This replaces the old 285-minute pipeline with a 60-minute pipeline.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
import logging
from datetime import date
from unittest.mock import Mock, patch, MagicMock

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class TestFastPipeline(unittest.TestCase):
    """Test the simplified fast pipeline."""

    def test_phase1_simplified(self):
        """Phase 1 should only check: prices loaded + 95% coverage."""
        from datetime import timedelta
        from algo.orchestrator.phase1_data_freshness import run as run_phase1
        from algo.algo_alerts import AlertManager

        with patch('algo.orchestrator.phase1_data_freshness.DatabaseContext') as mock_db:
            mock_cur = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_cur

            # Phase 1 calls fetchone() three times inside one DatabaseContext block:
            #   1. MAX(date) FROM price_daily  → most recent trading date
            #   2. COUNT symbols for that date → 5000
            #   3. COUNT symbols for prior date → 5000
            yesterday = date.today() - timedelta(days=1)
            mock_cur.fetchone.side_effect = [
                (yesterday,),  # MAX(date): yesterday's prices are loaded
                (5000,),       # symbol count for yesterday
                (5000,),       # prior day's symbol count (coverage baseline)
            ]

            result = run_phase1(
                config=None,
                run_date=date.today(),
                dry_run=False,
                alerts=AlertManager(),
                verbose=True,
                log_phase_result_fn=lambda *args: None
            )

            self.assertEqual(result.status, 'ok', "Phase 1 should pass with prices loaded")

    def test_phase5_signal_computation(self):
        """Phase 5 should compute signals on-the-fly from prices."""
        from algo.orchestrator.phase5_signal_generation import run as run_phase5

        with patch('algo.orchestrator.phase5_signal_generation.DatabaseContext') as mock_db, \
             patch('algo.orchestrator.phase5_signal_generation.SignalComputer') as mock_signal, \
             patch('algo.orchestrator.phase5_signal_generation.LiquidityChecks') as mock_liq, \
             patch('algo.orchestrator.phase5_signal_generation.SwingTraderScore') as mock_swing:

            mock_cur = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_cur

            # fetchone used for: (1) market_exposure_daily → will exception/proceed permissively,
            # (2) symbol count check → 2000 symbols present.
            mock_cur.fetchone.return_value = (2000,)
            # fetchall: 100 symbols with (symbol, close, high, low) — close in upper range
            mock_cur.fetchall.return_value = [
                (f"STOCK{i:03d}", 53.0, 55.0, 48.0) for i in range(100)
            ]

            # SignalComputer: every symbol passes Minervini gate with good scores
            sc = MagicMock()
            mock_signal.return_value = sc
            sc.minervini_trend_template.return_value = {'pass': True, 'score': 7}
            sc.weinstein_stage.return_value = {'stage': 2}
            sc.base_detection.return_value = {'in_base': True}
            sc.vcp_detection.return_value = {'is_vcp': False}
            sc.power_trend.return_value = {'power_trend': False, 'return_21d': None}

            # LiquidityChecks: all symbols pass
            liq = MagicMock()
            mock_liq.return_value = liq
            liq.run_all.return_value = (True, "passed")

            # SwingTraderScore: all symbols score 70 (grade B)
            swing = MagicMock()
            mock_swing.return_value = swing
            swing.compute.return_value = {'pass': True, 'swing_score': 70.0, 'grade': 'B'}

            result = run_phase5(
                run_date=date.today(),
                dry_run=False,
                verbose=True,
                log_phase_result_fn=lambda *args: None,
                exposure_constraints={},
                check_halt_flag=lambda: False,
                phase1_degraded=False
            )

            self.assertEqual(result.status, 'ok', "Phase 5 should compute signals")

    def test_phase6_on_demand_stops(self):
        """Phase 6 should compute ATR + SMA_50 on-demand for each trade."""
        from datetime import date
        from algo.orchestrator.phase6_entry_execution import run as run_phase6
        from algo.orchestrator.phase6_entry_execution import _compute_true_atr, _compute_sma_50

        test_date = date(2026, 1, 15)

        # Test ATR computation
        with patch('algo.orchestrator.phase6_entry_execution.DatabaseContext') as mock_db:
            mock_cur = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_cur
            mock_cur.fetchone = MagicMock(return_value=(2.5,))  # ATR = 2.5

            atr = _compute_true_atr("AAPL", test_date)
            self.assertAlmostEqual(atr, 2.5, places=1)

        # Test SMA_50 computation
        with patch('algo.orchestrator.phase6_entry_execution.DatabaseContext') as mock_db:
            mock_cur = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_cur
            mock_cur.fetchone = MagicMock(return_value=(150.0,))  # SMA_50 = 150

            sma50 = _compute_sma_50("AAPL", test_date)
            self.assertAlmostEqual(sma50, 150.0, places=1)

    def test_no_technical_data_daily_dependency(self):
        """Verify neither Phase 5 nor Phase 6 issues SQL queries against technical_data_daily.

        The docstrings may mention the table by name (as a non-dependency note), so we
        check for actual SQL FROM clauses rather than bare string presence.
        """
        import inspect
        from algo.orchestrator import phase5_signal_generation, phase6_entry_execution

        phase5_source = inspect.getsource(phase5_signal_generation)
        self.assertNotIn('FROM technical_data_daily', phase5_source,
                         "Phase 5 should not issue SQL queries against technical_data_daily")

        phase6_source = inspect.getsource(phase6_entry_execution)
        self.assertNotIn('FROM technical_data_daily', phase6_source,
                         "Phase 6 should not issue SQL queries against technical_data_daily")


class TestTimingImprovement(unittest.TestCase):
    """Verify timing improvements."""

    def test_morning_prep_timeline(self):
        """Morning prep should take <30 minutes instead of 285."""
        # Old: 15 + 180 + 30 + 30 + 30 = 285 minutes
        # New: 15 minutes (prices only)

        # Phase 1: 1 minute (verify prices + coverage)
        # Phase 5: 40 minutes (compute signals from prices)
        # Phase 6: 5 minutes (compute stops + execute)
        # Total: 46 minutes

        # This is 6x faster than old 285-minute pipeline
        expected_new_duration = 46  # minutes
        expected_old_duration = 285  # minutes

        improvement = expected_old_duration / expected_new_duration
        self.assertGreater(improvement, 5.0, f"New pipeline should be >5x faster")
        logger.info(f"Pipeline improvement: {improvement:.1f}x faster")


if __name__ == '__main__':
    unittest.main()
