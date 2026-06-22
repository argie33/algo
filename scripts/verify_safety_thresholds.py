#!/usr/bin/env python3
"""Verify trading safety thresholds are not set to zero.

CRITICAL: CLAUDE.md Rule #5: NEVER set thresholds to zero

This script is called by CI (lint-and-type job). It verifies TWO things:
  1. DEFAULTS in AlgoConfig have no critical threshold at zero
  2. The runtime safety gate actually fires when a zero value is injected

Both must pass. Neither requires a live database.
"""

import argparse
import logging
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.WARNING, format="[%(levelname)s] %(message)s")

# Critical thresholds: any of these being zero would bypass trading safety
CRITICAL_KEYS = [
    "min_signal_quality_score",
    "min_swing_score",
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
    from algo.infrastructure.config.main import AlgoConfig

    failures = []
    for key in ["min_signal_quality_score", "halt_drawdown_pct", "max_daily_loss_pct"]:
        # Inject zero for this key via _load_from_database
        def make_injector(k):
            def inject_zero(self):
                self._config[k] = 0

            return inject_zero

        try:
            with patch.object(AlgoConfig, "_load_from_database", make_injector(key)):
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

    print("\n" + "=" * 60)
    if all_failures:
        print(f"FAILED — {len(all_failures)} issue(s) found")
        return 1
    else:
        print("SUCCESS — Safety thresholds verified")
        return 0


if __name__ == "__main__":
    sys.exit(main())
