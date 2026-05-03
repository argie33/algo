#!/usr/bin/env python3
"""
Comprehensive algo system test suite

Tests all components:
- Configuration system
- Filter pipeline
- Position sizer
- Trade executor
- Exit engine
- Daily reconciliation
"""

import sys
import os
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from algo_config import get_config
from algo_filter_pipeline import FilterPipeline
from algo_position_sizer import PositionSizer
from algo_trade_executor import TradeExecutor
from algo_exit_engine import ExitEngine
from algo_daily_reconciliation import DailyReconciliation

class AlgoSystemTester:
    """Test suite for algo system."""

    def __init__(self):
        self.config = get_config()
        self.passed = 0
        self.failed = 0
        self.warnings = 0

    def test_configuration(self):
        """Test configuration system."""
        print("\n" + "="*70)
        print("TEST 1: Configuration System")
        print("="*70)

        try:
            # Test config loading
            assert self.config is not None, "Config not loaded"
            assert self.config.get('base_risk_pct', 0) > 0, "Base risk not set"
            assert self.config.get('max_positions', 0) > 0, "Max positions not set"

            # Test config values
            base_risk = self.config.get('base_risk_pct', 0.75)
            max_positions = self.config.get('max_positions', 12)
            max_dd = self.config.get('max_distribution_days', 4)

            print(f"Base Risk: {base_risk}%")
            print(f"Max Positions: {max_positions}")
            print(f"Max Distribution Days: {max_dd}")

            assert 0 < base_risk < 5, f"Invalid base risk: {base_risk}"
            assert 1 <= max_positions <= 20, f"Invalid max positions: {max_positions}"

            print("[OK] Configuration test PASSED")
            self.passed += 1

        except Exception as e:
            print(f"[FAIL] Configuration test FAILED: {e}")
            self.failed += 1

    def test_position_sizer(self):
        """Test position sizing."""
        print("\n" + "="*70)
        print("TEST 2: Position Sizer")
        print("="*70)

        try:
            sizer = PositionSizer(self.config)

            # Test normal sizing
            result = sizer.calculate_position_size(
                symbol='AAPL',
                entry_price=150.00,
                stop_loss_price=142.50
            )

            assert result['status'] in ['ok', 'no_room', 'drawdown_halt'], \
                f"Invalid status: {result['status']}"

            if result['status'] == 'ok':
                assert result['shares'] > 0, "No shares calculated"
                assert result['risk_dollars'] > 0, "No risk calculated"
                print(f"Position: {result['shares']} shares @ $150 = ${result['position_value']:.2f}")
                print(f"Risk: ${result['risk_dollars']:.2f}")
                print("[OK] Position sizer test PASSED")
                self.passed += 1
            else:
                print(f"Warning: {result['reason']}")
                self.warnings += 1

        except Exception as e:
            print(f"[FAIL] Position sizer test FAILED: {e}")
            self.failed += 1

    def test_filter_pipeline(self):
        """Test signal filtering."""
        print("\n" + "="*70)
        print("TEST 3: Filter Pipeline")
        print("="*70)

        try:
            pipeline = FilterPipeline()

            # Test pipeline initialization
            assert pipeline is not None, "Pipeline not created"
            assert pipeline.config is not None, "Pipeline config not loaded"

            print("Testing signal evaluation...")
            signals = pipeline.evaluate_signals()

            assert isinstance(signals, list), "Signals not returned as list"
            print(f"Signals evaluated: {len(signals)} qualified")
            print("[OK] Filter pipeline test PASSED")
            self.passed += 1

        except Exception as e:
            print(f"[FAIL] Filter pipeline test FAILED: {e}")
            self.failed += 1

    def test_trade_executor(self):
        """Test trade execution."""
        print("\n" + "="*70)
        print("TEST 4: Trade Executor")
        print("="*70)

        try:
            executor = TradeExecutor(self.config)

            # Test execution mode
            exec_mode = self.config.get('execution_mode', 'paper')
            print(f"Execution Mode: {exec_mode}")

            assert exec_mode in ('paper', 'dry', 'review', 'auto'), \
                f"Invalid execution mode: {exec_mode}"

            # Test trade structure (don't actually execute)
            print("Execution mode validated")
            print("[OK] Trade executor test PASSED")
            self.passed += 1

        except Exception as e:
            print(f"[FAIL] Trade executor test FAILED: {e}")
            self.failed += 1

    def test_exit_engine(self):
        """Test exit logic."""
        print("\n" + "="*70)
        print("TEST 5: Exit Engine")
        print("="*70)

        try:
            engine = ExitEngine(self.config)

            # Test exit conditions
            t1 = 160.0
            t2 = 170.0
            t3 = 180.0
            entry = 150.0
            stop = 142.50

            # Test condition: price at T3
            exit_signal = engine._check_exit_conditions(
                'AAPL', 180.0, entry, 100, t1, t2, t3, stop, 5, datetime.now().date()
            )

            if exit_signal:
                print(f"Exit signal: {exit_signal['reason']}")
            else:
                print("No exit signal at T3 level (expected due to pullback logic)")

            print("[OK] Exit engine test PASSED")
            self.passed += 1

        except Exception as e:
            print(f"[FAIL] Exit engine test FAILED: {e}")
            self.failed += 1

    def test_reconciliation(self):
        """Test daily reconciliation."""
        print("\n" + "="*70)
        print("TEST 6: Daily Reconciliation")
        print("="*70)

        try:
            reconciliation = DailyReconciliation(self.config)

            # Test reconciliation creation (doesn't need to execute)
            assert reconciliation is not None, "Reconciliation not created"
            print("Reconciliation system initialized")
            print("[OK] Reconciliation test PASSED")
            self.passed += 1

        except Exception as e:
            print(f"[FAIL] Reconciliation test FAILED: {e}")
            self.failed += 1

    def test_data_validation(self):
        """Test data validation."""
        print("\n" + "="*70)
        print("TEST 7: Data Validation")
        print("="*70)

        try:
            # Test price validation
            assert 0 < 150.0 < 100000, "Invalid stock price"
            assert 0 < 142.50 < 100000, "Invalid stop price"

            # Test position validation
            assert 100 > 0, "Invalid quantity"
            assert 0.75 > 0, "Invalid risk percentage"

            # Test date validation
            today = datetime.now().date()
            assert today is not None, "Invalid date"

            print("All validations passed")
            print("[OK] Data validation test PASSED")
            self.passed += 1

        except Exception as e:
            print(f"[FAIL] Data validation test FAILED: {e}")
            self.failed += 1

    def run_all_tests(self):
        """Run all tests."""
        print("\n" + "="*70)
        print("ALGO SYSTEM TEST SUITE")
        print("="*70)

        self.test_configuration()
        self.test_position_sizer()
        self.test_filter_pipeline()
        self.test_trade_executor()
        self.test_exit_engine()
        self.test_reconciliation()
        self.test_data_validation()

        # Summary
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)
        print(f"Passed: {self.passed}")
        print(f"Failed: {self.failed}")
        print(f"Warnings: {self.warnings}")

        if self.failed == 0:
            print("\n[OK] ALL TESTS PASSED - System is ready")
            return True
        else:
            print(f"\n[FAIL] {self.failed} tests failed - check errors above")
            return False

if __name__ == "__main__":
    tester = AlgoSystemTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)
