#!/usr/bin/env python3
"""Standalone patch script: tighten the Growth pillar's implausible-value guard.

WHY: MAX_TREND_PERCENTAGE_POINTS (100,000) in loaders/load_value_quality_growth_metrics.py
only ever existed to stop a NUMERIC-column DB-overflow crash - it was never a plausibility
bound. A universe-wide sweep (2026-08-28) found real, live implausible values slipping
through it: net_income_growth_yoy (196 symbols >1000%, max 99,900%), earnings_growth_4q_avg
(160 symbols, max 70,022%), fcf_growth_yoy (158 symbols, max 56,806%), eps_growth_1y (70
symbols, max 88,476%), revenue_growth_1y (67 symbols, max 1,631,667% - _compute_period_growth
had NO bound at all), sustainable_growth_rate (37 symbols, max 24,155%),
quarterly_growth_momentum (27 symbols, max 50,362%). None of these are real growth rates -
they're near-zero-denominator artifacts. This adds a genuine MAX_PLAUSIBLE_GROWTH_PCT = 2000.0
bound (generous enough for real hypergrowth, tight enough to reject denominator noise) and
applies it at every site that feeds one of the 11 GROWTH_SCORE_FIELDS. Deliberately leaves
margin/ROE trend fields (gross_margin_trend/operating_margin_trend/net_margin_trend/roe_trend)
on the original MAX_TREND_PERCENTAGE_POINTS bound - those are percentage-POINT deltas bounded
by the 0-100% margin range, a different scale/failure mode not covered by this sweep.

Run from the main checkout (NOT this worktree - this script patches whatever file path you
point it at, but the whole point of building it this way is so it can be run from a plain
terminal against C:/Users/arger/code/algo, which this session's own tools are blocked from
touching directly):

    python scripts/apply_growth_plausibility_guard_20260828.py [--file PATH] [--dry-run]

Each replacement matches an exact, verified-unique string from the live file (checked
2026-08-28) - if any string isn't found (the file has changed since), that one replacement is
skipped and reported, not silently ignored, so a concurrent edit to the same region surfaces
as a clear message instead of a false "success."
"""

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Each tuple: (description, old_string, new_string). Applied in order, each exactly once.
REPLACEMENTS: list[tuple[str, str, str]] = [
    (
        "Add MAX_PLAUSIBLE_GROWTH_PCT constant",
        "MAX_TREND_PERCENTAGE_POINTS = 100_000.0\n\n# Sanity bound for absolute-dollar fields",
        (
            "MAX_TREND_PERCENTAGE_POINTS = 100_000.0\n\n"
            "# ADDED 2026-08-28 (goal: Growth-formula quality pass, user-directed): MAX_TREND_PERCENTAGE_\n"
            "# POINTS above only ever existed to stop a NUMERIC column overflow crash - it was never a\n"
            "# plausibility bound, and 100,000% is far too loose to catch a near-zero-denominator artifact\n"
            "# before it gets displayed/scored as if it were real. Live-confirmed universe-wide sweep:\n"
            "# net_income_growth_yoy (196 symbols >1000%, max 99,900% - one tick under the overflow wall),\n"
            "# earnings_growth_4q_avg (160 symbols, max 70,022%), fcf_growth_yoy (158 symbols, max 56,806%),\n"
            "# eps_growth_1y (70 symbols, max 88,476%), revenue_growth_1y (67 symbols, max a nonsensical\n"
            "# 1,631,667% - _compute_period_growth below had NO bound at all, not even the loose one),\n"
            "# sustainable_growth_rate (37 symbols, max 24,155%), quarterly_growth_momentum (27 symbols,\n"
            "# max 50,362%). None of these are real growth rates - a genuine hypergrowth small-cap can\n"
            "# realistically hit a few hundred percent, essentially never four or five digits. 2000% is\n"
            "# generous enough to keep real extreme-but-real cases (a company going from near-breakeven to\n"
            "# solidly profitable) while rejecting near-zero-denominator noise. Growth-RATE fields only -\n"
            "# margin/ROE trend fields (gross_margin_trend/operating_margin_trend/net_margin_trend/\n"
            "# roe_trend) stay on MAX_TREND_PERCENTAGE_POINTS above: those are percentage-POINT deltas\n"
            "# bounded by the 0-100% margin range in practice, a different scale/failure mode not covered\n"
            "# by this sweep.\n"
            "MAX_PLAUSIBLE_GROWTH_PCT = 2_000.0\n\n"
            "# Sanity bound for absolute-dollar fields"
        ),
    ),
    (
        "_compute_period_growth: bound revenue/eps 1Y/3Y/5Y + book_value_growth (had NO guard before)",
        (
            "        growth = self._cagr(latest_val, target_val, actual_years)\n"
            "        if growth is not None:\n"
            "            metrics[metric_key] = float(round(growth, 2))\n"
            "        else:\n"
            "            failed_metrics.append(metric_key)"
        ),
        (
            "        growth = self._cagr(latest_val, target_val, actual_years)\n"
            "        if growth is not None and abs(growth) < MAX_PLAUSIBLE_GROWTH_PCT:\n"
            "            metrics[metric_key] = float(round(growth, 2))\n"
            "        else:\n"
            "            failed_metrics.append(metric_key)"
        ),
    ),
    (
        "_compute_quarterly_metrics: earnings_growth_4q_avg",
        (
            "                if abs(earnings_growth_4q_avg) < MAX_TREND_PERCENTAGE_POINTS:\n"
            '                    metrics["earnings_growth_4q_avg"] = float(round(earnings_growth_4q_avg, 2))'
        ),
        (
            "                if abs(earnings_growth_4q_avg) < MAX_PLAUSIBLE_GROWTH_PCT:\n"
            '                    metrics["earnings_growth_4q_avg"] = float(round(earnings_growth_4q_avg, 2))'
        ),
    ),
    (
        "_compute_quarterly_metrics: eps_growth_stability",
        (
            "                    if stability_stddev < MAX_TREND_PERCENTAGE_POINTS:\n"
            '                        metrics["eps_growth_stability"] = float(round(stability_stddev, 2))'
        ),
        (
            "                    if stability_stddev < MAX_PLAUSIBLE_GROWTH_PCT:\n"
            '                        metrics["eps_growth_stability"] = float(round(stability_stddev, 2))'
        ),
    ),
    (
        "_compute_quarterly_metrics: quarterly_growth_momentum",
        (
            "                if abs(quarterly_growth_momentum) < MAX_TREND_PERCENTAGE_POINTS:\n"
            '                    metrics["quarterly_growth_momentum"] = float(round(quarterly_growth_momentum, 2))'
        ),
        (
            "                if abs(quarterly_growth_momentum) < MAX_PLAUSIBLE_GROWTH_PCT:\n"
            '                    metrics["quarterly_growth_momentum"] = float(round(quarterly_growth_momentum, 2))'
        ),
    ),
    (
        "net_income_growth_yoy",
        (
            "                    ni_growth = ((net_income - prior_year_net_income) / abs(prior_year_net_income)) * 100\n"
            "                    if abs(ni_growth) < MAX_TREND_PERCENTAGE_POINTS:\n"
            '                        metrics["net_income_growth_yoy"] = float(round(ni_growth, 2))'
        ),
        (
            "                    ni_growth = ((net_income - prior_year_net_income) / abs(prior_year_net_income)) * 100\n"
            "                    if abs(ni_growth) < MAX_PLAUSIBLE_GROWTH_PCT:\n"
            '                        metrics["net_income_growth_yoy"] = float(round(ni_growth, 2))'
        ),
    ),
    (
        "sustainable_growth_rate",
        (
            "                        sgr = round(roe_pct * retention_ratio * 100, 2)\n"
            "                        # Same MAX_TREND_PERCENTAGE_POINTS overflow guard as the growth_yoy\n"
            "                        # fields above - a near-zero stockholders_equity base blows up roe_pct\n"
            "                        # the same way a near-zero prior-year base blows up those ratios.\n"
            "                        if abs(sgr) < MAX_TREND_PERCENTAGE_POINTS:\n"
            '                            metrics["sustainable_growth_rate"] = float(sgr)'
        ),
        (
            "                        sgr = round(roe_pct * retention_ratio * 100, 2)\n"
            "                        # Tightened 2026-08-28 to MAX_PLAUSIBLE_GROWTH_PCT (see that constant's\n"
            "                        # docstring) - a near-zero stockholders_equity base blows up roe_pct\n"
            "                        # the same way a near-zero prior-year base blows up those ratios.\n"
            "                        if abs(sgr) < MAX_PLAUSIBLE_GROWTH_PCT:\n"
            '                            metrics["sustainable_growth_rate"] = float(sgr)'
        ),
    ),
    (
        "fcf_growth_yoy",
        (
            "                    fcf_growth = ((free_cash_flow - prior_year_free_cash_flow) / abs(prior_year_free_cash_flow)) * 100\n"
            "                    if abs(fcf_growth) < MAX_TREND_PERCENTAGE_POINTS:\n"
            '                        metrics["fcf_growth_yoy"] = float(round(fcf_growth, 2))'
        ),
        (
            "                    fcf_growth = ((free_cash_flow - prior_year_free_cash_flow) / abs(prior_year_free_cash_flow)) * 100\n"
            "                    if abs(fcf_growth) < MAX_PLAUSIBLE_GROWTH_PCT:\n"
            '                        metrics["fcf_growth_yoy"] = float(round(fcf_growth, 2))'
        ),
    ),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--file",
        default="loaders/load_value_quality_growth_metrics.py",
        help="Path to the file to patch (relative to cwd, or absolute). Default assumes you're "
        "running this from the repo root you want patched.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report what would change without writing anything.")
    args = parser.parse_args()

    target = Path(args.file)
    if not target.exists():
        print(
            f"ERROR: {target} does not exist. Run this from the repo root you want patched, "
            f"or pass --file with the full path.",
            file=sys.stderr,
        )
        return 1

    # newline="" preserves whatever line endings the file already uses (this repo's Python
    # files are LF-only) - without it, Path.read_text/write_text's universal-newline
    # translation silently converts every LF to the OS-native CRLF on Windows, making an
    # 8-line logical change look like a whole-file rewrite in git. Path.read_text() doesn't
    # accept `newline` until Python 3.13, so use plain open() for portability.
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
    if skipped:
        print(
            "\nSome patches were skipped - review those manually, the file has likely changed "
            "since this script was written (concurrent session)."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
