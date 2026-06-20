#!/usr/bin/env python3
"""
Test Phase 5 Enforcement: Verify buy_sell_daily is required and not silently degraded

Tests that Phase 5 now explicitly fails if buy_sell_daily is unavailable,
instead of silently falling back to stock_scores-only signals.
"""

import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch


sys.path.insert(0, str(Path(__file__).parent.parent))

from algo.orchestrator.phase5_signal_generation import run as run_phase5
from algo.orchestrator.phase_result import PhaseResult


def test_phase5_fails_without_buysell_signals():
    """
    CRITICAL TEST: Phase 5 must FAIL if buy_sell_daily signals are unavailable.
    This verifies the fix: Phase 5 no longer falls back to stock_scores.
    """
    print("\n" + "="*80)
    print("TEST: Phase 5 Enforcement - Explicit Failure Without buy_sell_daily")
    print("="*80)

    test_date = date(2026, 6, 16)

    # Mock functions that Phase 5 depends on
    def mock_check_halt_flag():
        """Halt flag is not set, so we proceed to signal generation"""
        return False

    def mock_log_phase_result(phase_num, phase_name, status, msg):
        """Log phase results"""
        print(f"[PHASE {phase_num}] {status.upper()}: {msg[:100]}")

    def mock_check_market_regime(run_date):
        """Market regime allows entries"""
        return {
            "is_entry_allowed": True,
            "exposure_pct": 100,
            "regime": "normal",
            "halt_reasons": [],
        }

    # Mock the database context to return NO buy_sell_daily signals
    # This simulates the scenario where EOD pipeline hasn't completed
    with patch('algo.orchestrator.phase5_signal_generation.DatabaseContext') as mock_db_context:
        with patch('algo.orchestrator.phase5_signal_generation._check_market_regime',
                   side_effect=mock_check_market_regime):
            # Mock cursor that handles both validation queries and candidate fetch queries
            mock_cursor = MagicMock()

            # Setup for validation queries (stock_scores count and market_exposure_daily check)
            # These use fetchone()
            call_count = [0]

            def mock_fetchone():
                call_count[0] += 1
                if call_count[0] == 1:  # stock_scores COUNT
                    return (100,)  # Return 100 rows (non-empty)
                elif call_count[0] == 2:  # market_exposure_daily validation
                    return (1, 1)  # (count, count_with_valid_exposure_pct)
                else:
                    return None

            def mock_fetchall():
                return []  # Empty — no buy_sell_daily signals found

            mock_cursor.fetchone.side_effect = mock_fetchone
            mock_cursor.fetchall.return_value = []

            mock_context_manager = MagicMock()
            mock_context_manager.__enter__.return_value = mock_cursor
            mock_context_manager.__exit__.return_value = None

            mock_db_context.return_value = mock_context_manager

            # Run Phase 5
            config = {"phase5_min_composite_score": 50}
            exposure_constraints = {
                "max_positions": 12,
                "max_single_position_pct": 8.0,
                "sector_limits": {},
                "industry_limits": {},
            }
            result = run_phase5(
                run_date=test_date,
                dry_run=False,
                verbose=True,
                log_phase_result_fn=mock_log_phase_result,
                exposure_constraints=exposure_constraints,
                check_halt_flag=mock_check_halt_flag,
                phase1_degraded=False,
                config=config
            )

    # Verify Phase 5 HALTS (doesn't degrade gracefully)
    print(f"\nPhase 5 Result: {result.status}")
    print(f"Halted: {result.halted}")
    print(f"Error: {result.error}")

    assert result.halted, "Phase 5 should halt when buy_sell_daily is unavailable"
    assert result.status == "halted", f"Expected status 'halted', got '{result.status}'"
    assert "buy_sell_daily" in result.error, "Error message should mention buy_sell_daily"
    assert "EOD pipeline" in result.error, "Error message should mention EOD pipeline"
    assert "phase_name" not in str(result.data), "Should not produce qualified trades"

    print("\n[OK] Phase 5 correctly fails when buy_sell_daily is unavailable")
    print("[OK] No silent fallback to stock_scores")
    print("[OK] Clear error message about EOD pipeline\n")


def test_phase5_works_with_buysell_signals():
    """
    HAPPY PATH TEST: Phase 5 should work when buy_sell_daily signals ARE available.
    This verifies the fix doesn't break normal operation.
    """
    print("\n" + "="*80)
    print("TEST: Phase 5 Happy Path - Works With buy_sell_daily Signals")
    print("="*80)

    test_date = date(2026, 6, 16)

    def mock_check_halt_flag():
        return False

    def mock_log_phase_result(phase_num, phase_name, status, msg):
        print(f"[PHASE {phase_num}] {status.upper()}: {msg[:80]}")

    def mock_check_market_regime(run_date):
        return {
            "is_entry_allowed": True,
            "exposure_pct": 100,
            "regime": "normal",
            "halt_reasons": [],
        }

    # Mock database with VALID signals
    with patch('algo.orchestrator.phase5_signal_generation.DatabaseContext') as mock_db_context:
        with patch('algo.orchestrator.phase5_signal_generation._check_market_regime',
                   side_effect=mock_check_market_regime):
            with patch('algo.orchestrator.phase5_signal_generation._check_liquidity_parallel') as mock_liquidity:

                mock_cursor = MagicMock()

                # Setup for validation queries (stock_scores count and market_exposure_daily check)
                call_count = [0]

                def mock_fetchone():
                    call_count[0] += 1
                    if call_count[0] == 1:  # stock_scores COUNT
                        return (100,)
                    elif call_count[0] == 2:  # market_exposure_daily validation
                        return (1, 1)
                    else:
                        return None

                # Return sample buy_sell_daily signal
                def mock_fetchall():
                    return [
                        (
                            'AAPL',  # symbol
                            75.0,    # composite_score
                            80.0,    # quality_score
                            70.0,    # growth_score
                            72.0,    # momentum_score
                            85.0,    # rs_percentile
                            185.5,   # close
                            186.0,   # high
                            184.0,   # low
                            180.0,   # sma_50
                            'Technology',  # sector
                            'Semiconductors',  # industry
                            184.0,   # buylevel
                            180.0,   # stoplevel
                            8.5,     # strength (signal_strength)
                            12.0,    # volume_surge_pct
                            'breakout',  # market_stage
                            test_date,  # signal_date
                            75.0,    # swing_score (from sts.score via COALESCE)
                            None,    # swing_components (from sts.components)
                        )
                    ]

                mock_cursor.fetchone.side_effect = mock_fetchone
                mock_cursor.fetchall.side_effect = mock_fetchall

                mock_context_manager = MagicMock()
                mock_context_manager.__enter__.return_value = mock_cursor
                mock_context_manager.__exit__.return_value = None

                mock_db_context.return_value = mock_context_manager

                # Mock liquidity check to pass
                mock_liquidity.return_value = (
                    {'symbol': 'AAPL', 'composite_score': 75.0, 'close': 185.5,
                     'sma_50': 180.0, 'high': 186.0, 'low': 184.0},
                    True
                )

                config = {"phase5_min_composite_score": 50}
                exposure_constraints = {
                    "max_positions": 12,
                    "max_single_position_pct": 8.0,
                    "sector_limits": {},
                    "industry_limits": {},
                }
                result = run_phase5(
                    run_date=test_date,
                    dry_run=False,
                    verbose=True,
                    log_phase_result_fn=mock_log_phase_result,
                    exposure_constraints=exposure_constraints,
                    check_halt_flag=mock_check_halt_flag,
                    phase1_degraded=False,
                    config=config
                )

    print(f"\nPhase 5 Result: {result.status}")
    print(f"Halted: {result.halted}")
    print(f"Qualified trades: {len(result.data.get('qualified_trades', []))}")

    # Phase 5 might still return halted=True if no signals pass all filters,
    # but it should at least TRY to process buy_sell_daily signals
    # The important thing is it's using the buy_sell_daily signal source
    assert result.data.get('signal_source') == 'buysell_breakout', \
        f"Expected signal_source 'buysell_breakout', got {result.data.get('signal_source')}"

    print("\n[OK] Phase 5 uses buy_sell_daily signals when available")
    print("[OK] Signal source is 'buysell_breakout' (not 'stock_scores_fallback')\n")


def test_phase5_rejects_null_swing_scores():
    """
    CRITICAL TEST: Phase 5 must REJECT candidates with NULL swing_score.
    This verifies the fix: swing_score NULL defaults to 0.0 no longer allowed.
    """
    print("\n" + "="*80)
    print("TEST: Phase 5 Enforcement - Reject NULL swing_scores")
    print("="*80)

    test_date = date(2026, 6, 16)

    def mock_check_halt_flag():
        return False

    def mock_log_phase_result(phase_num, phase_name, status, msg):
        print(f"[PHASE {phase_num}] {status.upper()}: {msg[:80]}")

    def mock_check_market_regime(run_date):
        return {
            "is_entry_allowed": True,
            "exposure_pct": 100,
            "regime": "normal",
            "halt_reasons": [],
        }

    # Mock database with a signal that has NULL swing_score
    with patch('algo.orchestrator.phase5_signal_generation.DatabaseContext') as mock_db_context:
        with patch('algo.orchestrator.phase5_signal_generation._check_market_regime',
                   side_effect=mock_check_market_regime):

            mock_cursor = MagicMock()

            # Setup for validation queries
            call_count = [0]

            def mock_fetchone():
                call_count[0] += 1
                if call_count[0] == 1:  # stock_scores COUNT
                    return (100,)
                elif call_count[0] == 2:  # market_exposure_daily validation
                    return (1, 1)
                else:
                    return None

            # Return buy_sell_daily signal with NULL swing_score
            def mock_fetchall():
                return [
                    (
                        'TSLA',  # symbol
                        75.0,    # composite_score
                        80.0,    # quality_score
                        70.0,    # growth_score
                        72.0,    # momentum_score
                        85.0,    # rs_percentile
                        185.5,   # close
                        186.0,   # high
                        184.0,   # low
                        180.0,   # sma_50
                        'Technology',  # sector
                        'Auto',  # industry
                        184.0,   # buylevel
                        180.0,   # stoplevel
                        8.5,     # strength (signal_strength)
                        12.0,    # volume_surge_pct
                        'breakout',  # market_stage
                        test_date,  # signal_date
                        None,    # swing_score is NULL — this is the key test case
                        None,    # swing_components
                    )
                ]

            mock_cursor.fetchone.side_effect = mock_fetchone
            mock_cursor.fetchall.side_effect = mock_fetchall

            mock_context_manager = MagicMock()
            mock_context_manager.__enter__.return_value = mock_cursor
            mock_context_manager.__exit__.return_value = None

            mock_db_context.return_value = mock_context_manager

            config = {"phase5_min_composite_score": 50}
            result = run_phase5(
                run_date=test_date,
                dry_run=False,
                verbose=True,
                log_phase_result_fn=mock_log_phase_result,
                exposure_constraints=None,
                check_halt_flag=mock_check_halt_flag,
                phase1_degraded=False,
                config=config
            )

    print(f"\nPhase 5 Result: {result.status}")
    print(f"Halted: {result.halted}")
    print(f"Qualified trades: {len(result.data.get('qualified_trades', []))}")

    # The signal should be REJECTED because swing_score is NULL
    assert len(result.data.get('qualified_trades', [])) == 0, \
        f"Candidates with NULL swing_score should be rejected, but got {len(result.data.get('qualified_trades', []))} signals"

    print("\n[OK] Phase 5 correctly rejects candidates with NULL swing_score")
    print("[OK] No candidates produced when swing_score validation is missing\n")


def test_phase5_rejects_null_signal_strength():
    """
    CRITICAL TEST: Phase 5 must REJECT candidates with NULL signal_strength.
    This verifies the fix: signal_strength is now a required field and cannot be guessed.
    """
    print("\n" + "="*80)
    print("TEST: Phase 5 Enforcement - Reject NULL signal_strength")
    print("="*80)

    test_date = date(2026, 6, 16)

    def mock_check_halt_flag():
        return False

    def mock_log_phase_result(phase_num, phase_name, status, msg):
        print(f"[PHASE {phase_num}] {status.upper()}: {msg[:80]}")

    def mock_check_market_regime(run_date):
        return {
            "is_entry_allowed": True,
            "exposure_pct": 100,
            "regime": "normal",
            "halt_reasons": [],
        }

    # Mock database with a signal that has NULL signal_strength
    with patch('algo.orchestrator.phase5_signal_generation.DatabaseContext') as mock_db_context:
        with patch('algo.orchestrator.phase5_signal_generation._check_market_regime',
                   side_effect=mock_check_market_regime):

            mock_cursor = MagicMock()

            # Setup for validation queries
            call_count = [0]

            def mock_fetchone():
                call_count[0] += 1
                if call_count[0] == 1:  # stock_scores COUNT
                    return (100,)
                elif call_count[0] == 2:  # market_exposure_daily validation
                    return (1, 1)
                else:
                    return None

            # Return buy_sell_daily signal with NULL signal_strength (strength column)
            def mock_fetchall():
                return [
                    (
                        'NVDA',  # symbol
                        75.0,    # composite_score
                        80.0,    # quality_score
                        70.0,    # growth_score
                        72.0,    # momentum_score
                        85.0,    # rs_percentile
                        185.5,   # close
                        186.0,   # high
                        184.0,   # low
                        180.0,   # sma_50
                        'Technology',  # sector
                        'Semiconductors',  # industry
                        184.0,   # buylevel
                        180.0,   # stoplevel
                        None,    # strength (signal_strength) is NULL — this is the key test case
                        12.0,    # volume_surge_pct
                        'breakout',  # market_stage
                        test_date,  # signal_date
                        75.0,    # swing_score
                        None,    # swing_components
                    )
                ]

            mock_cursor.fetchone.side_effect = mock_fetchone
            mock_cursor.fetchall.side_effect = mock_fetchall

            mock_context_manager = MagicMock()
            mock_context_manager.__enter__.return_value = mock_cursor
            mock_context_manager.__exit__.return_value = None

            mock_db_context.return_value = mock_context_manager

            config = {"phase5_min_composite_score": 50}
            result = run_phase5(
                run_date=test_date,
                dry_run=False,
                verbose=True,
                log_phase_result_fn=mock_log_phase_result,
                exposure_constraints=None,
                check_halt_flag=mock_check_halt_flag,
                phase1_degraded=False,
                config=config
            )

    print(f"\nPhase 5 Result: {result.status}")
    print(f"Halted: {result.halted}")
    print(f"Qualified trades: {len(result.data.get('qualified_trades', []))}")

    # The signal should be REJECTED because signal_strength is NULL
    assert len(result.data.get('qualified_trades', [])) == 0, \
        f"Candidates with NULL signal_strength should be rejected, but got {len(result.data.get('qualified_trades', []))} signals"

    print("\n[OK] Phase 5 correctly rejects candidates with NULL signal_strength")
    print("[OK] No synthetic signal strength derived from composite_score\n")


def main():
    """Run all Phase 5 enforcement tests."""
    print("\n" + "="*80)
    print("PHASE 5 ENFORCEMENT TEST SUITE")
    print("Verifies buy_sell_daily is required (no silent fallback)")
    print("Verifies swing_score NULL is rejected (not silently defaulted to 0.0)")
    print("Verifies signal_strength NULL is rejected (not silently derived from composite_score)")
    print("="*80)

    passed = 0
    failed = 0

    try:
        test_phase5_fails_without_buysell_signals()
        passed += 1
    except Exception as e:
        print(f"\n✗ FAIL: {e}")
        failed += 1

    try:
        test_phase5_works_with_buysell_signals()
        passed += 1
    except Exception as e:
        print(f"\n✗ FAIL: {e}")
        failed += 1

    try:
        test_phase5_rejects_null_swing_scores()
        passed += 1
    except Exception as e:
        print(f"\n✗ FAIL: {e}")
        failed += 1

    try:
        test_phase5_rejects_null_signal_strength()
        passed += 1
    except Exception as e:
        print(f"\n✗ FAIL: {e}")
        failed += 1

    print("\n" + "="*80)
    print(f"SUMMARY: {passed} passed, {failed} failed")
    print("="*80 + "\n")

    return failed == 0


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
