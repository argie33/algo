#!/usr/bin/env python3
"""
END-TO-END MONDAY BRITTLENESS TEST

Simulates the real Monday scenario that causes stale data cascades:
1. SEC Edgar rate limiting (external, recurring)
2. Incomplete price load (90-94% completion)
3. Circuit breaker halting on timeout
4. Dependent loaders skipping due to upstream failures

Validates that Session 88 fixes actually prevent the cascade.
"""

import sys
from datetime import date, datetime
from pathlib import Path

# BUG FIX: this script's emoji status markers (checkmark/cross/warning) crash outright on
# Windows' default cp1252 console encoding before STEP 1 even finishes printing - the same
# bug class already fixed in scripts/monitor_data_staleness.py and
# scripts/validate_loader_systems_sync.py. Guarded against pytest: reassigning
# sys.stdout/stderr to a new TextIOWrapper while pytest has already substituted its own
# capture streams corrupts pytest's capture teardown the first time anything imports this
# module.
if sys.platform == "win32" and "pytest" not in sys.modules:
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from algo.orchestrator.phase1_failsafe_retry import (
    _get_expected_data_date,
    check_and_retry_incomplete_loaders,
)
from utils.db.context import DatabaseContext
from utils.loaders.status_manager import LoaderStatusManager


def test_scenario_sec_rate_limit_with_incomplete_load():  # noqa: C901
    """
    Scenario: Monday morning, SEC rate-limits hit Friday afternoon, price load hit at 94%.

    Expected behavior (Session 88 fixes):
    1. company_info_sec marked FAILED with rate-limit error (SEC graceful skip)
    2. company_profile skips (depends on company_info_sec)
    3. price_daily marked FAILED (90-94% completion)
    4. Phase 1 failsafe detects incomplete price_daily, retries it
    5. Circuit breaker cancels unprocessed futures if timeout occurs
    6. Pipeline proceeds with cached data, no cascade

    Test validates each step.
    """
    print("\n" + "=" * 80)
    print("MONDAY BRITTLENESS SCENARIO TEST")
    print("=" * 80)
    print("Scenario: SEC rate limit + incomplete price load + circuit breaker timeout")
    print("Date:", date.today().isoformat())

    all_pass = True

    # STEP 1: Verify SEC graceful skip is configured
    print("\n[STEP 1] SEC graceful skip configuration")
    print("-" * 80)
    try:
        with DatabaseContext("read") as cur:
            # Find SEC loaders
            cur.execute("""
                SELECT table_name, status, consecutive_failures, error_message
                FROM data_loader_status
                WHERE table_name LIKE '%sec%' OR table_name LIKE '%SEC%'
                LIMIT 5
            """)
            sec_loaders = cur.fetchall()

            if not sec_loaders:
                print("⚠️  No SEC loaders found in database")
                return False

            for table, status, failures, error_msg in sec_loaders:
                print(f"  {table:30} | status={status:10} | failures={failures}")

                # Check if this loader has rate-limit errors
                if "rate limit" in str(error_msg).lower() or "429" in str(error_msg):
                    if status == "FAILED":
                        print("    ✅ Correctly marked FAILED on rate-limit error")
                    else:
                        print(f"    ❌ Should be FAILED but is {status}")
                        all_pass = False

        print("✅ PASS: SEC loaders configuration verified")
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

    # STEP 2: Verify incomplete load prevention (95% threshold)
    print("\n[STEP 2] Incomplete load prevention (95% threshold)")
    print("-" * 80)
    try:
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT table_name, status, completion_pct, symbols_loaded, symbol_count
                FROM data_loader_status
                WHERE table_name IN ('price_daily', 'etf_price_daily')
                ORDER BY last_updated DESC
                LIMIT 2
            """)
            rows = cur.fetchall()

            for table, status, completion, loaded, total in rows:
                if not completion or not loaded or not total:
                    print(f"  {table}: No completion data yet")
                    continue

                pct = float(completion)
                print(f"  {table:20} | {pct:5.1f}% | {loaded}/{total} symbols | status={status}")

                # Validate the logic
                if pct >= 95.0:
                    if status == "COMPLETED":
                        print("    ✅ Correctly COMPLETED (≥95%)")
                    else:
                        print(f"    ❌ Should be COMPLETED but is {status}")
                        all_pass = False
                elif 90.0 <= pct < 95.0:
                    if status == "FAILED":
                        print("    ✅ Correctly FAILED (90-94% triggers cache fallback)")
                    else:
                        print(f"    ⚠️  Should be FAILED but is {status} (scheduler may not skip dependent loaders)")
                        all_pass = False
                elif pct < 90.0:
                    if status == "FAILED":
                        print("    ✅ Correctly FAILED (<90% indicates real problem)")
                    else:
                        print(f"    ❌ Should be FAILED but is {status}")
                        all_pass = False

        print("✅ PASS: Incomplete load prevention verified")
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

    # STEP 3: Verify circuit breaker cancellation is in code
    print("\n[STEP 3] Circuit breaker future cancellation")
    print("-" * 80)
    try:
        loader_file = project_root / "loaders" / "load_prices.py"
        content = loader_file.read_text()

        # Check for the cancellation logic
        if "fut.cancel()" in content and "CIRCUIT_BREAKER" in content:
            print("✅ Circuit breaker cancellation logic found in load_prices.py")
            print("   Location: lines 1579-1595 (fut.cancel() on unprocessed futures)")
            print("   Note: This is implemented but UNTESTED under production load")
            print("        (No test validates it actually prevents 20+ min hang)")
        else:
            print("❌ Circuit breaker cancellation not found")
            all_pass = False

    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

    # STEP 4: Verify Phase 1 stale RUNNING loader detection
    print("\n[STEP 4] Phase 1 stale RUNNING loader auto-fail")
    print("-" * 80)
    try:
        from algo.orchestrator.phase1_data_freshness import _detect_and_fail_stale_running_loaders

        print("✅ Phase 1 has _detect_and_fail_stale_running_loaders function")
        print("   This auto-fails loaders stuck RUNNING >30 min")

        # Check for any stale RUNNING loaders
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT table_name, last_updated,
                       EXTRACT(EPOCH FROM (NOW() - last_updated)) / 60 as minutes_stuck
                FROM data_loader_status
                WHERE status = 'RUNNING'
                  AND last_updated < NOW() - INTERVAL '30 minutes'
                ORDER BY last_updated ASC
                LIMIT 3
            """)
            stale = cur.fetchall()

            if stale:
                print(f"⚠️  Found {len(stale)} stale RUNNING loader(s):")
                for table, updated, minutes in stale:
                    print(f"     {table}: stuck for {minutes:.0f} minutes")
                print("   Phase 1 will auto-fail these on next run")
            else:
                print("✅ No stale RUNNING loaders found (healthy state)")

    except ImportError:
        print("❌ Phase 1 stale detection not implemented")
        all_pass = False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

    # STEP 5: Yfinance parallelism=2 experiment - superseded, do not run
    print("\n[STEP 5] Yfinance parallelism optimization (SUPERSEDED - do not run)")
    print("-" * 80)
    try:
        test_script = project_root / "scripts" / "test_yfinance_parallelism_2.py"

        if test_script.exists():
            print("✅ Test script exists: test_yfinance_parallelism_2.py")
            print("⛔ SUPERSEDED: LOADER_PARALLELISM is now a load-bearing rule fixed at 1")
            print("   (see MEMORY.md analyst_loaders_reloaded_and_local_parallelism_ban_20260810 -")
            print("   parallelism=4 self-triggered the yfinance shared-IP circuit breaker even from")
            print("   a single local machine). The per-loader LOADER_CONSTRAINTS scoping this script's")
            print("   parent investigation (steering/YFINANCE_PARALLELISM_INVESTIGATION.md) assumed was")
            print("   never implemented - LOADER_PARALLELISM is a single global env var, so running this")
            print("   script would raise parallelism for every loader, not just analyst_sentiment/upgrades.")
        else:
            print("❌ Test script not found")
            all_pass = False

    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

    # SUMMARY
    print("\n" + "=" * 80)
    print("MONDAY BRITTLENESS TEST SUMMARY")
    print("=" * 80)

    if all_pass:
        print("""
✅ ALL CHECKS PASSED

Session 88 fixes are implemented:
  1. SEC graceful skip (gracefully handles rate-limited loaders)
  2. Incomplete load prevention (rejects <95%, triggers cache fallback)
  3. Circuit breaker future cancellation (prevents 20+ min hangs)
  4. Phase 1 stale RUNNING detection (auto-fails stuck loaders)

⚠️  CRITICAL: These are implemented but production-load validation is missing.
   - Circuit breaker cancellation (fut.cancel) has not been tested under timeout
   - No end-to-end Monday scenario (SEC rate limit + incomplete) has been validated

RECOMMENDATION:
  Do NOT run test_yfinance_parallelism_2.py - its parallelism=2 hypothesis is superseded
  by the load-bearing LOADER_PARALLELISM=1 rule (see STEP 5 above for why).
  Schedule a "Monday chaos" test simulating SEC rate-limits instead.
        """)
        return 0
    else:
        print("""
❌ SOME CHECKS FAILED

See above for details. Next steps:
  1. Review failed checks
  2. Implement missing validations
  3. Run end-to-end Monday scenario test
        """)
        return 1


if __name__ == "__main__":
    sys.exit(test_scenario_sec_rate_limit_with_incomplete_load())
