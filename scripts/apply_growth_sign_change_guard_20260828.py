#!/usr/bin/env python3
"""Standalone patch script #2: add profit<->loss sign-change guard to the *_growth_yoy fields.

WHY: live-confirmed root cause of CRWD (a well-known hypergrowth company) scoring LOWER than
KO (a well-known slow-growth blue chip) in a face-validity check - CRWD's net_income_growth_yoy
computed as -966% despite genuinely strong ~22% revenue growth. That's not noise, it's a
profit-to-loss (or loss-to-profit) swing: net_income_growth_yoy/operating_income_growth_yoy/
fcf_growth_yoy/ocf_growth_yoy compute a raw (curr-prior)/|prior|*100 percentage with NO
sign-change guard, even though this exact repo's OWN CAGR-based fields (_cagr() /
_compute_period_growth(), used for revenue/eps_growth_1y/3y/5y and book_value_growth) already
correctly treat a sign flip as mathematically undefined and report
"growth_undefined_sign_change" instead of a misleading number. This patch gives the 4 simple-
YoY fields the same treatment already proven correct elsewhere in this file, rather than
inventing a new convention - reuses the exact "growth_undefined_sign_change" reason string
the frontend already has a label for ("Growth undefined (profit/loss swing)").

Run from the main checkout:
    python scripts/apply_growth_sign_change_guard_20260828.py [--file PATH] [--dry-run]

Same exact-string-match safety as apply_growth_plausibility_guard_20260828.py - any pattern
not found is reported and skipped, not silently ignored.
"""

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPLACEMENTS: list[tuple[str, str, str]] = [
    (
        "Add sign_change_yoy_metrics tracking list",
        "            implausible_ratio_metrics: list[str] = []\n\n            # ROE = Net Income / Shareholders' Equity",
        (
            "            implausible_ratio_metrics: list[str] = []\n"
            "            # ADDED 2026-08-28 (goal: Growth-formula quality pass, face-validity check found\n"
            "            # CRWD scoring below KO - see the 4 sign-change guards below for the fix this\n"
            "            # tracks the reason for).\n"
            "            sign_change_yoy_metrics: list[str] = []\n\n"
            "            # ROE = Net Income / Shareholders' Equity"
        ),
    ),
    (
        "net_income_growth_yoy: sign-change guard",
        (
            "            if net_income is not None and prior_year_net_income is not None and prior_year_net_income != 0:\n"
            "                try:\n"
            "                    ni_growth = ((net_income - prior_year_net_income) / abs(prior_year_net_income)) * 100\n"
            "                    if abs(ni_growth) < MAX_PLAUSIBLE_GROWTH_PCT:\n"
            '                        metrics["net_income_growth_yoy"] = float(round(ni_growth, 2))\n'
            "                    else:\n"
            '                        implausible_ratio_metrics.append("net_income_growth_yoy")\n'
            "                except (ValueError, TypeError, ZeroDivisionError) as e:\n"
            "                    logger.warning(\n"
            '                        f"[{symbol}] Failed to calculate net_income_growth_yoy: {type(e).__name__}. "\n'
            '                        f"Metric marked data_unavailable."\n'
            "                    )"
        ),
        (
            "            if net_income is not None and prior_year_net_income is not None and prior_year_net_income != 0:\n"
            "                if (net_income > 0 and prior_year_net_income < 0) or (\n"
            "                    net_income < 0 and prior_year_net_income > 0\n"
            "                ):\n"
            "                    # Profit<->loss sign flip - growth % is mathematically undefined here,\n"
            "                    # same treatment _cagr()/_compute_period_growth already give this exact\n"
            "                    # condition (root cause of CRWD's -966% net_income_growth_yoy despite\n"
            "                    # genuinely strong ~22% revenue growth).\n"
            '                    sign_change_yoy_metrics.append("net_income_growth_yoy")\n'
            "                else:\n"
            "                    try:\n"
            "                        ni_growth = ((net_income - prior_year_net_income) / abs(prior_year_net_income)) * 100\n"
            "                        if abs(ni_growth) < MAX_PLAUSIBLE_GROWTH_PCT:\n"
            '                            metrics["net_income_growth_yoy"] = float(round(ni_growth, 2))\n'
            "                        else:\n"
            '                            implausible_ratio_metrics.append("net_income_growth_yoy")\n'
            "                    except (ValueError, TypeError, ZeroDivisionError) as e:\n"
            "                        logger.warning(\n"
            '                            f"[{symbol}] Failed to calculate net_income_growth_yoy: {type(e).__name__}. "\n'
            '                            f"Metric marked data_unavailable."\n'
            "                        )"
        ),
    ),
    (
        "operating_income_growth_yoy: sign-change guard",
        (
            "            if (\n"
            "                operating_income_for_margin is not None\n"
            "                and prior_year_operating_income_for_trend is not None\n"
            "                and prior_year_operating_income_for_trend != 0\n"
            "            ):\n"
            "                try:\n"
            "                    oi_growth = (\n"
            "                        (operating_income_for_margin - prior_year_operating_income_for_trend)\n"
            "                        / abs(prior_year_operating_income_for_trend)\n"
            "                    ) * 100\n"
            "                    if abs(oi_growth) < MAX_TREND_PERCENTAGE_POINTS:\n"
            '                        metrics["operating_income_growth_yoy"] = float(round(oi_growth, 2))\n'
            "                    else:\n"
            '                        implausible_ratio_metrics.append("operating_income_growth_yoy")\n'
            "                except (ValueError, TypeError, ZeroDivisionError):\n"
            "                    pass"
        ),
        (
            "            if (\n"
            "                operating_income_for_margin is not None\n"
            "                and prior_year_operating_income_for_trend is not None\n"
            "                and prior_year_operating_income_for_trend != 0\n"
            "            ):\n"
            "                if (operating_income_for_margin > 0 and prior_year_operating_income_for_trend < 0) or (\n"
            "                    operating_income_for_margin < 0 and prior_year_operating_income_for_trend > 0\n"
            "                ):\n"
            '                    sign_change_yoy_metrics.append("operating_income_growth_yoy")\n'
            "                else:\n"
            "                    try:\n"
            "                        oi_growth = (\n"
            "                            (operating_income_for_margin - prior_year_operating_income_for_trend)\n"
            "                            / abs(prior_year_operating_income_for_trend)\n"
            "                        ) * 100\n"
            "                        if abs(oi_growth) < MAX_TREND_PERCENTAGE_POINTS:\n"
            '                            metrics["operating_income_growth_yoy"] = float(round(oi_growth, 2))\n'
            "                        else:\n"
            '                            implausible_ratio_metrics.append("operating_income_growth_yoy")\n'
            "                    except (ValueError, TypeError, ZeroDivisionError):\n"
            "                        pass"
        ),
    ),
    (
        "fcf_growth_yoy: sign-change guard",
        (
            "            if free_cash_flow is not None and prior_year_free_cash_flow is not None and prior_year_free_cash_flow != 0:\n"
            "                try:\n"
            "                    fcf_growth = ((free_cash_flow - prior_year_free_cash_flow) / abs(prior_year_free_cash_flow)) * 100\n"
            "                    if abs(fcf_growth) < MAX_PLAUSIBLE_GROWTH_PCT:\n"
            '                        metrics["fcf_growth_yoy"] = float(round(fcf_growth, 2))\n'
            "                    else:\n"
            '                        implausible_ratio_metrics.append("fcf_growth_yoy")\n'
            "                except (ValueError, TypeError, ZeroDivisionError):\n"
            "                    pass"
        ),
        (
            "            if free_cash_flow is not None and prior_year_free_cash_flow is not None and prior_year_free_cash_flow != 0:\n"
            "                if (free_cash_flow > 0 and prior_year_free_cash_flow < 0) or (\n"
            "                    free_cash_flow < 0 and prior_year_free_cash_flow > 0\n"
            "                ):\n"
            '                    sign_change_yoy_metrics.append("fcf_growth_yoy")\n'
            "                else:\n"
            "                    try:\n"
            "                        fcf_growth = (\n"
            "                            (free_cash_flow - prior_year_free_cash_flow) / abs(prior_year_free_cash_flow)\n"
            "                        ) * 100\n"
            "                        if abs(fcf_growth) < MAX_PLAUSIBLE_GROWTH_PCT:\n"
            '                            metrics["fcf_growth_yoy"] = float(round(fcf_growth, 2))\n'
            "                        else:\n"
            '                            implausible_ratio_metrics.append("fcf_growth_yoy")\n'
            "                    except (ValueError, TypeError, ZeroDivisionError):\n"
            "                        pass"
        ),
    ),
    (
        "ocf_growth_yoy: sign-change guard",
        (
            "            if (\n"
            "                operating_cash_flow is not None\n"
            "                and prior_year_operating_cash_flow is not None\n"
            "                and prior_year_operating_cash_flow != 0\n"
            "            ):\n"
            "                try:\n"
            "                    ocf_growth = (\n"
            "                        (operating_cash_flow - prior_year_operating_cash_flow) / abs(prior_year_operating_cash_flow)\n"
            "                    ) * 100\n"
            "                    if abs(ocf_growth) < MAX_TREND_PERCENTAGE_POINTS:\n"
            '                        metrics["ocf_growth_yoy"] = float(round(ocf_growth, 2))\n'
            "                    else:\n"
            '                        implausible_ratio_metrics.append("ocf_growth_yoy")\n'
            "                except (ValueError, TypeError, ZeroDivisionError):\n"
            "                    pass"
        ),
        (
            "            if (\n"
            "                operating_cash_flow is not None\n"
            "                and prior_year_operating_cash_flow is not None\n"
            "                and prior_year_operating_cash_flow != 0\n"
            "            ):\n"
            "                if (operating_cash_flow > 0 and prior_year_operating_cash_flow < 0) or (\n"
            "                    operating_cash_flow < 0 and prior_year_operating_cash_flow > 0\n"
            "                ):\n"
            '                    sign_change_yoy_metrics.append("ocf_growth_yoy")\n'
            "                else:\n"
            "                    try:\n"
            "                        ocf_growth = (\n"
            "                            (operating_cash_flow - prior_year_operating_cash_flow)\n"
            "                            / abs(prior_year_operating_cash_flow)\n"
            "                        ) * 100\n"
            "                        if abs(ocf_growth) < MAX_TREND_PERCENTAGE_POINTS:\n"
            '                            metrics["ocf_growth_yoy"] = float(round(ocf_growth, 2))\n'
            "                        else:\n"
            '                            implausible_ratio_metrics.append("ocf_growth_yoy")\n'
            "                    except (ValueError, TypeError, ZeroDivisionError):\n"
            "                        pass"
        ),
    ),
    (
        "Reason-assignment loop: check sign_change_yoy_metrics before implausible_ratio",
        (
            "                if metrics.get(_trend_field) is None:\n"
            '                    if _trend_field == "gross_margin_trend" and no_gross_profit_concept:\n'
            '                        metrics[f"{_trend_field}_unavailable_reason"] = "reit_special_entity"\n'
            "                    elif _trend_field in implausible_ratio_metrics:\n"
            '                        metrics[f"{_trend_field}_unavailable_reason"] = "implausible_ratio"\n'
            "                    else:\n"
            '                        metrics[f"{_trend_field}_unavailable_reason"] = "insufficient_prior_year_data"'
        ),
        (
            "                if metrics.get(_trend_field) is None:\n"
            '                    if _trend_field == "gross_margin_trend" and no_gross_profit_concept:\n'
            '                        metrics[f"{_trend_field}_unavailable_reason"] = "reit_special_entity"\n'
            "                    elif _trend_field in sign_change_yoy_metrics:\n"
            '                        metrics[f"{_trend_field}_unavailable_reason"] = "growth_undefined_sign_change"\n'
            "                    elif _trend_field in implausible_ratio_metrics:\n"
            '                        metrics[f"{_trend_field}_unavailable_reason"] = "implausible_ratio"\n'
            "                    else:\n"
            '                        metrics[f"{_trend_field}_unavailable_reason"] = "insufficient_prior_year_data"'
        ),
    ),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--file", default="loaders/load_value_quality_growth_metrics.py")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    target = Path(args.file)
    if not target.exists():
        print(f"ERROR: {target} does not exist.", file=sys.stderr)
        return 1

    with open(target, encoding="utf-8", newline="") as f:
        original = f.read()
    content = original
    applied, skipped = [], []

    for description, old, new in REPLACEMENTS:
        count = content.count(old)
        if count == 0:
            skipped.append((description, "pattern not found - file may have changed since this script was written"))
            continue
        if count > 1:
            skipped.append((description, f"pattern found {count} times (expected exactly 1) - refusing to guess"))
            continue
        content = content.replace(old, new, 1)
        applied.append(description)

    print(f"Target: {target}")
    print(f"Applied: {len(applied)}/{len(REPLACEMENTS)}")
    for d in applied:
        print(f"  [OK] {d}")
    if skipped:
        print(f"Skipped: {len(skipped)}")
        for d, reason in skipped:
            print(f"  [SKIP] {d} - {reason}")

    if not applied:
        print("\nNothing to apply. No changes made.")
        return 1 if skipped else 0

    if args.dry_run:
        print("\n--dry-run: no file was written.")
        return 0

    backup = target.with_suffix(target.suffix + f".bak-{datetime.now():%Y%m%d%H%M%S}")
    shutil.copy2(target, backup)
    with open(target, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    print(f"\nBackup saved to: {backup}")
    print(f"Wrote {len(applied)} change(s) to {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
