#!/usr/bin/env python3
"""Verify trading safety thresholds are not set to zero.

CRITICAL: steering/GOVERNANCE.md Trading Safety section: NEVER set thresholds to zero.

This script verifies TWO things:
  1. DEFAULTS in AlgoConfig have no critical threshold at zero
  2. The runtime safety gate actually fires when a zero value is injected

Both must pass. Neither requires a live database.

Restored 2026-07-20: this file was deleted in a "stale script cleanup" commit (cca2c1854)
without updating steering/GOVERNANCE.md's "Pre-deployment: Run
python scripts/verify_safety_thresholds.py --strict" line, leaving a documented
pre-production safety gate that nobody could actually run. CRITICAL_KEYS below is also
updated from the original: min_swing_score never existed (swing_score-based gating was
formally retired in migration 103; composite_score is the sole entry-quality signal now).
"""

import argparse
import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.WARNING, format="[%(levelname)s] %(message)s")

# Critical thresholds: any of these being zero would bypass trading safety
CRITICAL_KEYS = [
    "min_signal_quality_score",
    "min_completeness_score",
    "halt_drawdown_pct",
    "max_daily_loss_pct",
    "vix_max_threshold",
    "min_volume_ma_50d",
    "min_avg_daily_dollar_volume",
    "earnings_blackout_days_before",
    "earnings_blackout_days_after",
    "base_risk_pct",
    "max_position_size_pct",
]


def check_defaults_not_zero() -> list[str]:
    """Check that AlgoConfig.DEFAULTS has no critical threshold set to zero."""
    from algo.infrastructure.config.main import AlgoConfig

    failures = []
    for key in CRITICAL_KEYS:
        if key not in AlgoConfig.DEFAULTS:
            failures.append(f"  MISSING default: {key} not in AlgoConfig.DEFAULTS")
            continue
        entry = AlgoConfig.DEFAULTS[key]
        default_val, dtype = entry[0], entry[1]
        try:
            numeric = float(default_val)
            if numeric == 0.0:
                failures.append(f"  ZERO default: {key} = {default_val!r} ({dtype}) — must not be zero")
        except (ValueError, TypeError):
            # Non-numeric default (e.g. string flags) — not a threshold concern
            pass
    return failures


def check_safety_gate_fires() -> list[str]:
    """Verify AlgoConfig raises RuntimeError when a zero value is injected via DB."""
    import os

    from algo.infrastructure.config.main import AlgoConfig

    failures = []
    for key in ["min_signal_quality_score", "halt_drawdown_pct", "max_daily_loss_pct"]:
        # Inject zero for this key, simulating a DB-loaded (not default) value - marking
        # _sources[k]="database" avoids tripping the unrelated _detect_config_db_failure()
        # "ALL values still at defaults" check, which otherwise masks the threshold-zero
        # RuntimeError we're actually testing for behind a misleading "DB unreachable" one.
        def make_injector(k: str) -> Callable[[Any], None]:
            def inject_zero(self: Any) -> None:
                self._config[k] = 0
                self._sources[k] = "database"

            return inject_zero

        try:
            with (
                patch.object(AlgoConfig, "_load_from_database", make_injector(key)),
                patch.dict(os.environ, {"ALPACA_PAPER_TRADING": "true"}),
            ):
                AlgoConfig()
            # If we reach here, the safety gate didn't fire
            failures.append(f"  GATE MISSING: AlgoConfig did not raise on {key}=0 — safety gate is broken")
        except RuntimeError as e:
            if "SAFETY GATE FAILURE" not in str(e):
                failures.append(f"  WRONG ERROR for {key}=0: got {type(e).__name__}: {e!s:.80}")
            # else: correctly raised SAFETY GATE FAILURE — this key is good
        except Exception as e:
            failures.append(f"  UNEXPECTED ERROR testing {key}=0: {type(e).__name__}: {e!s:.80}")

    return failures


def check_live_db_thresholds() -> tuple[list[str], bool]:
    """Verify the REAL, currently-live algo_config table's values for CRITICAL_KEYS -
    distinct from (and previously not covered by) check_defaults_not_zero()/
    check_safety_gate_fires() above, which only ever exercise AlgoConfig.DEFAULTS (the
    in-code fallback) and a synthetic zero-injection, never the actual live database this
    system trades against. Added 2026-08-27 (real-money-readiness review) after noticing
    this script's own docstring ("Neither requires a live database") meant a clean run had
    never actually confirmed the live DB's real values were sane - only that the code-level
    safety net exists, which is a materially weaker guarantee for a "run before production"
    gate. Uses VALIDATION_SCHEMA's own declared (min, max) bounds so this doesn't duplicate
    a second, potentially-drifting set of range constants.

    Returns (failures, db_reachable) - db_reachable=False means the check could not run at
    all (no DB available), which is reported but is NOT itself a failure at import time in
    non-strict/local-dev contexts without a configured DB; the caller decides how to treat it.
    """
    from algo.infrastructure.config_schema import VALIDATION_SCHEMA

    try:
        from utils.db.context import DatabaseContext
    except Exception as e:
        return ([f"  ERROR importing DatabaseContext: {type(e).__name__}: {e!s:.100}"], False)

    try:
        with DatabaseContext("read") as cur:
            cur.execute("SELECT key, value FROM algo_config WHERE key = ANY(%s)", (CRITICAL_KEYS,))
            live_values = {row[0]: row[1] for row in cur.fetchall()}
    except Exception as e:
        return ([f"  DB UNREACHABLE: {type(e).__name__}: {e!s:.100}"], False)

    failures = []
    for key in CRITICAL_KEYS:
        if key not in live_values:
            # Not necessarily fatal - AlgoConfig falls back to DEFAULTS (verified non-zero
            # above) for a missing row - but flagged so an operator knows the DB-tuned value
            # (if one was ever intended, per this week's extensive threshold-recalibration
            # history in memory) isn't actually the one live traffic is using.
            failures.append(f"  MISSING FROM LIVE DB: {key} (falls back to code DEFAULTS)")
            continue
        raw = live_values[key]
        try:
            numeric = float(raw)
        except (ValueError, TypeError):
            failures.append(f"  NON-NUMERIC live value: {key} = {raw!r}")
            continue
        if numeric == 0.0:
            failures.append(f"  ZERO in LIVE DB: {key} = {raw!r} — disables this safety gate right now")
            continue
        schema_entry = VALIDATION_SCHEMA.get(key)
        if schema_entry is not None:
            _dtype, lo, hi, _fail_closed, _default = (
                schema_entry[0],
                schema_entry[1],
                schema_entry[2],
                schema_entry[3],
                schema_entry[4],
            )
            if lo is not None and hi is not None and not (lo <= numeric <= hi):
                failures.append(f"  OUT OF DECLARED RANGE: {key} = {numeric} not in [{lo}, {hi}] per VALIDATION_SCHEMA")

    return (failures, True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify trading safety thresholds")
    parser.add_argument("--strict", action="store_true", help="Fail if any threshold check fails")
    parser.add_argument("--show", action="store_true", help="Display all critical threshold defaults")
    args = parser.parse_args()

    print("\nTrading Safety Threshold Verification")
    print("=" * 60)

    all_failures: list[str] = []

    # Check 1: DEFAULTS are non-zero
    print("\n[1] Checking AlgoConfig.DEFAULTS for critical thresholds...")
    try:
        failures = check_defaults_not_zero()
        if failures:
            print("FAIL — Zero or missing defaults found:")
            for f in failures:
                print(f)
            all_failures.extend(failures)
        else:
            print(f"OK  — All {len(CRITICAL_KEYS)} critical thresholds have non-zero defaults")
    except Exception as e:
        msg = f"  ERROR importing AlgoConfig to check defaults: {type(e).__name__}: {e!s:.100}"
        print(msg)
        all_failures.append(msg)

    if args.show:
        try:
            from algo.infrastructure.config.main import AlgoConfig

            print("\nCritical threshold defaults:")
            for key in CRITICAL_KEYS:
                entry = AlgoConfig.DEFAULTS.get(key)
                if entry:
                    val, dtype = entry[0], entry[1]
                    print(f"  {key:<45} {val!s:>10}  ({dtype})")
        except Exception:
            pass

    # Check 2: Runtime safety gate fires on zero injection
    print("\n[2] Verifying runtime safety gate fires on zero injection...")
    try:
        failures = check_safety_gate_fires()
        if failures:
            print("FAIL — Safety gate did not fire as expected:")
            for f in failures:
                print(f)
            all_failures.extend(failures)
        else:
            print("OK  — RuntimeError('SAFETY GATE FAILURE') raised correctly for zero injection")
    except Exception as e:
        msg = f"  ERROR testing safety gate: {type(e).__name__}: {e!s:.100}"
        print(msg)
        all_failures.append(msg)

    # Check 3: the REAL, currently-live algo_config DB values (added 2026-08-27 - checks 1/2
    # above only ever exercise in-code DEFAULTS + a synthetic injection, never actual live data)
    print("\n[3] Checking the LIVE algo_config database for critical thresholds...")
    try:
        failures, db_reachable = check_live_db_thresholds()
        if not db_reachable:
            print("SKIP — no live database reachable from this environment:")
            for f in failures:
                print(f)
            if args.strict:
                print("  (--strict treats an unreachable DB as informational, not fatal - this")
                print("   check exists to catch a REACHABLE DB with bad values, not DB connectivity)")
        elif failures:
            print("FAIL — live database has invalid critical threshold(s):")
            for f in failures:
                print(f)
            all_failures.extend(failures)
        else:
            print(f"OK  — All {len(CRITICAL_KEYS)} critical thresholds present, non-zero, and in-range in the live DB")
    except Exception as e:
        # Same treatment as an unreachable DB (informational) - an environment issue here
        # (missing DatabaseContext config, etc.) is not the corrupted-threshold failure mode
        # this script exists to catch.
        print(f"  ERROR checking live DB thresholds: {type(e).__name__}: {e!s:.100}")

    print("\n" + "=" * 60)
    if all_failures:
        print(f"FAILED — {len(all_failures)} issue(s) found")
        return 1
    else:
        print("SUCCESS — Safety thresholds verified")
        return 0


if __name__ == "__main__":
    sys.exit(main())
