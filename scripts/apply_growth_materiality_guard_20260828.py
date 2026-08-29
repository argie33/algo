#!/usr/bin/env python3
"""Standalone patch script #3: materiality guard for the *_growth_yoy fields.

WHY: face-validity check found CRWD (real hypergrowth company, ~22% revenue growth) scoring
BELOW KO (real slow-growth blue chip) - traced to net_income_growth_yoy = -966%, computed from
a real loss that widened from -$15.2M to -$162.5M (both negative - NOT a sign flip, so
apply_growth_sign_change_guard_20260828.py's fix doesn't touch this case). A prior-year base
that's small relative to the size of the business produces a technically-real but economically
misleading growth percentage - the well-known reason professional growth investors avoid
bottom-line earnings growth for pre-profitability companies. This adds a materiality floor:
the prior-year base must be at least 1% of that year's revenue (a plausible minimum margin/
cash-flow-to-revenue ratio) before a *_growth_yoy percentage is computed at all; below that,
mark it unavailable ("immaterial_prior_year_base") and let the equal-weighted blend
renormalize over the remaining fields, same principle Quality's floor-renormalization and this
pillar's own partial-availability blend already use elsewhere.

Applies to net_income_growth_yoy, operating_income_growth_yoy, fcf_growth_yoy,
ocf_growth_yoy - all four share the identical "prior-year base too small" fragility.
revenue/prior_year_revenue are already in scope in _compute_quality_metrics (used a few lines
below for margin trends).

Run from the main checkout:
    python scripts/apply_growth_materiality_guard_20260828.py [--file PATH] [--dry-run]
"""

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

MATERIALITY_THRESHOLD_COMMENT = (
    "            # ADDED 2026-08-28 (goal: Growth-formula quality pass, face-validity check found\n"
    "            # CRWD scoring below KO - net_income_growth_yoy=-966% from a real loss widening\n"
    "            # -$15.2M -> -$162.5M, no sign flip so the sign-change guard above doesn't catch\n"
    "            # it). A prior-year base under 1% of that year's revenue is too small to produce\n"
    "            # a meaningful growth percentage - mark unavailable rather than compute a\n"
    "            # technically-real but misleading number, same principle as the sign-change guard.\n"
    "            immaterial_base_yoy_metrics: list[str] = []\n\n"
)

REPLACEMENTS: list[tuple[str, str, str]] = [
    (
        "Add immaterial_base_yoy_metrics tracking list",
        (
            "            # ADDED 2026-08-28 (goal: Growth-formula quality pass, face-validity check found\n"
            "            # CRWD scoring below KO - see the 4 sign-change guards below for the fix this\n"
            "            # tracks the reason for).\n"
            "            sign_change_yoy_metrics: list[str] = []\n\n"
            "            # ROE = Net Income / Shareholders' Equity"
        ),
        (
            "            # ADDED 2026-08-28 (goal: Growth-formula quality pass, face-validity check found\n"
            "            # CRWD scoring below KO - see the 4 sign-change guards below for the fix this\n"
            "            # tracks the reason for).\n"
            "            sign_change_yoy_metrics: list[str] = []\n"
            + MATERIALITY_THRESHOLD_COMMENT
            + "            # ROE = Net Income / Shareholders' Equity"
        ),
    ),
    (
        "net_income_growth_yoy: materiality guard",
        (
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
        (
            "                    # Profit<->loss sign flip - growth % is mathematically undefined here,\n"
            "                    # same treatment _cagr()/_compute_period_growth already give this exact\n"
            "                    # condition (root cause of CRWD's -966% net_income_growth_yoy despite\n"
            "                    # genuinely strong ~22% revenue growth).\n"
            '                    sign_change_yoy_metrics.append("net_income_growth_yoy")\n'
            "                elif (\n"
            "                    prior_year_revenue is not None\n"
            "                    and prior_year_revenue > 0\n"
            "                    and abs(prior_year_net_income) < 0.01 * prior_year_revenue\n"
            "                ):\n"
            '                    immaterial_base_yoy_metrics.append("net_income_growth_yoy")\n'
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
        "operating_income_growth_yoy: materiality guard",
        (
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
        (
            '                    sign_change_yoy_metrics.append("operating_income_growth_yoy")\n'
            "                elif (\n"
            "                    prior_year_revenue is not None\n"
            "                    and prior_year_revenue > 0\n"
            "                    and abs(prior_year_operating_income_for_trend) < 0.01 * prior_year_revenue\n"
            "                ):\n"
            '                    immaterial_base_yoy_metrics.append("operating_income_growth_yoy")\n'
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
        "fcf_growth_yoy: materiality guard",
        (
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
        (
            '                    sign_change_yoy_metrics.append("fcf_growth_yoy")\n'
            "                elif (\n"
            "                    prior_year_revenue is not None\n"
            "                    and prior_year_revenue > 0\n"
            "                    and abs(prior_year_free_cash_flow) < 0.01 * prior_year_revenue\n"
            "                ):\n"
            '                    immaterial_base_yoy_metrics.append("fcf_growth_yoy")\n'
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
        "ocf_growth_yoy: materiality guard",
        (
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
        (
            '                    sign_change_yoy_metrics.append("ocf_growth_yoy")\n'
            "                elif (\n"
            "                    prior_year_revenue is not None\n"
            "                    and prior_year_revenue > 0\n"
            "                    and abs(prior_year_operating_cash_flow) < 0.01 * prior_year_revenue\n"
            "                ):\n"
            '                    immaterial_base_yoy_metrics.append("ocf_growth_yoy")\n'
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
        "Reason-assignment loop: check immaterial_base_yoy_metrics",
        (
            "                    elif _trend_field in sign_change_yoy_metrics:\n"
            '                        metrics[f"{_trend_field}_unavailable_reason"] = "growth_undefined_sign_change"\n'
            "                    elif _trend_field in implausible_ratio_metrics:\n"
        ),
        (
            "                    elif _trend_field in sign_change_yoy_metrics:\n"
            '                        metrics[f"{_trend_field}_unavailable_reason"] = "growth_undefined_sign_change"\n'
            "                    elif _trend_field in immaterial_base_yoy_metrics:\n"
            '                        metrics[f"{_trend_field}_unavailable_reason"] = "immaterial_prior_year_base"\n'
            "                    elif _trend_field in implausible_ratio_metrics:\n"
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
