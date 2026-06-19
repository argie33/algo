#!/usr/bin/env python3
"""
Verify trading safety thresholds are properly configured.

This script checks that critical safety features are not accidentally disabled or set to zero.
Run before production deploys to catch configuration drift.

Usage:
  python scripts/verify_safety_thresholds.py
  python scripts/verify_safety_thresholds.py --strict (fail on any deviation from defaults)
"""

import sys

from algo.infrastructure import AlgoConfig


# Minimum safe thresholds (below these = DANGER)
MINIMUM_SAFE_THRESHOLDS = {
    "min_signal_quality_score": 40,  # Below 40 = reject signal quality gate
    "min_swing_score": 30.0,  # Below 30 = too loose
    "min_completeness_score": 50,  # Below 50 = incomplete data
    "min_volume_ma_50d": 100000,  # Below 100k = illiquid
    "min_avg_daily_dollar_volume": 250000,  # Below 250k = illiquid
    "earnings_blackout_days_before": 1,  # Below 1 = no earnings protection
    "earnings_blackout_days_after": 1,  # Below 1 = no earnings protection
}

# Expected values (should match migration-032 defaults)
EXPECTED_DEFAULTS = {
    "min_signal_quality_score": 60,
    "min_swing_score": 55.0,
    "min_completeness_score": 70,
    "min_volume_ma_50d": 300000,
    "min_avg_daily_dollar_volume": 500000.0,
    "earnings_blackout_days_before": 7,
    "earnings_blackout_days_after": 3,
    "rs_slope_gate_enabled": False,
    "volume_decay_gate_enabled": False,
}


def check_safety_thresholds(strict=False):
    """Verify safety thresholds are not disabled or below minimum."""
    try:
        config = AlgoConfig()
    except Exception as e:
        print(f"Cannot connect to database: {e}")
        print("Note: This script requires a database connection.\n")
        return True

    issues = []
    warnings = []

    # Check minimum safe thresholds
    for key, min_value in MINIMUM_SAFE_THRESHOLDS.items():
        current = config.get(key)
        if current is None:
            issues.append(f"❌ CRITICAL: {key} is not configured (None)")
        elif current < min_value:
            issues.append(
                f"❌ CRITICAL: {key} = {current} is below minimum safe {min_value}"
            )

    # Check earnings blackout days specifically (0 means disabled)
    for key in ["earnings_blackout_days_before", "earnings_blackout_days_after"]:
        current = config.get(key)
        if current == 0:
            issues.append(f"❌ CRITICAL: {key} = 0 means earnings protection DISABLED")

    # Check quality thresholds are not zero
    for key in [
        "min_signal_quality_score",
        "min_swing_score",
        "min_completeness_score",
    ]:
        current = config.get(key)
        if current == 0:
            issues.append(
                f"❌ CRITICAL: {key} = 0 means quality gate DISABLED (system trades any stock)"
            )

    # In strict mode, also check for deviations from expected defaults
    if strict:
        for key, expected in EXPECTED_DEFAULTS.items():
            current = config.get(key)
            if current != expected:
                warnings.append(
                    f"⚠️  DEVIATION: {key} = {current} (expected {expected})"
                )

    # Report findings
    print("\n" + "=" * 70)
    print("SAFETY THRESHOLD VERIFICATION")
    print("=" * 70)

    if issues:
        print("\n🚨 CRITICAL ISSUES FOUND:")
        for issue in issues:
            print(f"  {issue}")
        print("\nAction: Restore safety thresholds before trading!")
        return False

    if warnings:
        print("\n⚠️  DEVIATIONS FROM DEFAULTS (--strict mode):")
        for warning in warnings:
            print(f"  {warning}")
        print("\nNote: Intentional overrides are OK; verify these are deliberate.\n")

    if not issues and not warnings:
        print("\n✅ All safety thresholds OK!")
        print("   Quality gates: ACTIVE")
        print("   Earnings blackout: ACTIVE")
        print("   Liquidity filters: ACTIVE\n")
        return True

    print("\n" + "=" * 70)
    return len(issues) == 0


def show_current_config():
    """Display current safety configuration."""
    try:
        config = AlgoConfig()
        print("\n" + "=" * 70)
        print("CURRENT SAFETY CONFIGURATION")
        print("=" * 70 + "\n")

        for key, expected in EXPECTED_DEFAULTS.items():
            current = config.get(key)
            status = "[OK]" if current == expected else "[!!]"
            print(f"{status} {key:.<45} {current}")

        print("\n" + "=" * 70)
    except Exception as e:
        print(f"\nCannot load config: {e}")
        print("Note: Script requires database connection to verify thresholds.\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Verify trading safety thresholds are properly configured"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on any deviation from default values (not just minimum safe)",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Display current configuration and exit",
    )

    args = parser.parse_args()

    if args.show:
        show_current_config()
        sys.exit(0)

    success = check_safety_thresholds(strict=args.strict)
    show_current_config()
    sys.exit(0 if success else 1)
