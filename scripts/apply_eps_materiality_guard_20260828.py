#!/usr/bin/env python3
"""Standalone patch script #4: materiality guard for EPS growth (1Y/3Y/5Y).

WHY: same class of bug as apply_growth_materiality_guard_20260828.py (net_income_growth_yoy
etc), found the same way - measured directly against real annual EPS data (not assumed):
102 symbols show EPS growth swings >200% (up to -7200%, +5150%) purely from a near-zero
prior-year EPS base (<$0.10/share), currently uncaught by anything except the loose 2000%
plausibility bound, which most of these stay under. _compute_period_growth (shared by
revenue/eps 1Y/3Y/5Y and book_value_growth) already has a sign-change guard but no
materiality floor. Adds an optional min_abs_target parameter, applied only to the 3 EPS
calls (revenue and book-value-per-share don't have this problem at this company's scale -
not measured, so not touched).

Run from the main checkout:
    python scripts/apply_eps_materiality_guard_20260828.py [--file PATH] [--dry-run]
"""

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPLACEMENTS: list[tuple[str, str, str]] = [
    (
        "_compute_period_growth: add min_abs_target/immaterial_base_metrics params",
        (
            "        split_discontinuity_metrics: set[str] | None = None,\n"
            "        shares_by_year: dict[int, float] | None = None,\n"
            "    ) -> None:"
        ),
        (
            "        split_discontinuity_metrics: set[str] | None = None,\n"
            "        shares_by_year: dict[int, float] | None = None,\n"
            "        *,\n"
            "        min_abs_target: float = 0.0,\n"
            "        immaterial_base_metrics: set[str] | None = None,\n"
            "    ) -> None:"
        ),
    ),
    (
        "_compute_period_growth: apply the materiality check after the sign-change check",
        (
            "        if (latest_val > 0 and target_val < 0) or (latest_val < 0 and target_val > 0):\n"
            "            failed_metrics.append(metric_key)\n"
            "            sign_change_metrics.add(metric_key)\n"
            "            return\n"
            "\n"
            "        if shares_by_year:"
        ),
        (
            "        if (latest_val > 0 and target_val < 0) or (latest_val < 0 and target_val > 0):\n"
            "            failed_metrics.append(metric_key)\n"
            "            sign_change_metrics.add(metric_key)\n"
            "            return\n"
            "\n"
            "        # ADDED 2026-08-28 (goal: Growth-formula quality pass) - live-measured: 102\n"
            "        # symbols show EPS growth swings >200% (up to -7200%/+5150%) purely from a\n"
            "        # near-zero prior-year EPS base, the same 'prior-year base too small to trust'\n"
            "        # fragility already fixed for net_income_growth_yoy/fcf_growth_yoy/etc.\n"
            "        if min_abs_target > 0 and abs(target_val) < min_abs_target:\n"
            "            failed_metrics.append(metric_key)\n"
            "            if immaterial_base_metrics is not None:\n"
            "                immaterial_base_metrics.add(metric_key)\n"
            "            return\n"
            "\n"
            "        if shares_by_year:"
        ),
    ),
    (
        "_compute_growth_metrics: initialize immaterial_base_metrics tracking set",
        (
            "        failed_metrics: list[str] = []\n"
            "        sign_change_metrics: set[str] = set()\n"
            "        split_discontinuity_metrics: set[str] = set()"
        ),
        (
            "        failed_metrics: list[str] = []\n"
            "        sign_change_metrics: set[str] = set()\n"
            "        split_discontinuity_metrics: set[str] = set()\n"
            "        immaterial_base_metrics: set[str] = set()"
        ),
    ),
    (
        "eps_growth_1y call: pass min_abs_target=0.10",
        (
            "        self._compute_period_growth(\n"
            "            symbol,\n"
            "            eps_values,\n"
            "            1,\n"
            '            "eps_growth_1y",\n'
            "            metrics,\n"
            "            failed_metrics,\n"
            "            sign_change_metrics,\n"
            "            split_discontinuity_metrics,\n"
            "            shares_by_year,\n"
            "        )"
        ),
        (
            "        self._compute_period_growth(\n"
            "            symbol,\n"
            "            eps_values,\n"
            "            1,\n"
            '            "eps_growth_1y",\n'
            "            metrics,\n"
            "            failed_metrics,\n"
            "            sign_change_metrics,\n"
            "            split_discontinuity_metrics,\n"
            "            shares_by_year,\n"
            "            min_abs_target=0.10,\n"
            "            immaterial_base_metrics=immaterial_base_metrics,\n"
            "        )"
        ),
    ),
    (
        "eps_growth_3y call: pass min_abs_target=0.10",
        (
            "        self._compute_period_growth(\n"
            "            symbol,\n"
            "            eps_values,\n"
            "            3,\n"
            '            "eps_growth_3y",\n'
            "            metrics,\n"
            "            failed_metrics,\n"
            "            sign_change_metrics,\n"
            "            split_discontinuity_metrics,\n"
            "            shares_by_year,\n"
            "        )"
        ),
        (
            "        self._compute_period_growth(\n"
            "            symbol,\n"
            "            eps_values,\n"
            "            3,\n"
            '            "eps_growth_3y",\n'
            "            metrics,\n"
            "            failed_metrics,\n"
            "            sign_change_metrics,\n"
            "            split_discontinuity_metrics,\n"
            "            shares_by_year,\n"
            "            min_abs_target=0.10,\n"
            "            immaterial_base_metrics=immaterial_base_metrics,\n"
            "        )"
        ),
    ),
    (
        "eps_growth_5y call: pass min_abs_target=0.10",
        (
            "        self._compute_period_growth(\n"
            "            symbol,\n"
            "            eps_values,\n"
            "            5,\n"
            '            "eps_growth_5y",\n'
            "            metrics,\n"
            "            failed_metrics,\n"
            "            sign_change_metrics,\n"
            "            split_discontinuity_metrics,\n"
            "            shares_by_year,\n"
            "        )"
        ),
        (
            "        self._compute_period_growth(\n"
            "            symbol,\n"
            "            eps_values,\n"
            "            5,\n"
            '            "eps_growth_5y",\n'
            "            metrics,\n"
            "            failed_metrics,\n"
            "            sign_change_metrics,\n"
            "            split_discontinuity_metrics,\n"
            "            shares_by_year,\n"
            "            min_abs_target=0.10,\n"
            "            immaterial_base_metrics=immaterial_base_metrics,\n"
            "        )"
        ),
    ),
    (
        "_growth_reason: check immaterial_base_metrics",
        (
            "        def _growth_reason(metric_key: str) -> str | None:\n"
            "            if metric_key in sign_change_metrics:\n"
            '                return "growth_undefined_sign_change"\n'
            "            if metric_key in split_discontinuity_metrics:\n"
            '                return "growth_undefined_share_count_discontinuity"\n'
            "            if metric_key in failed_metrics:\n"
            '                return "insufficient_history"\n'
            "            return None"
        ),
        (
            "        def _growth_reason(metric_key: str) -> str | None:\n"
            "            if metric_key in sign_change_metrics:\n"
            '                return "growth_undefined_sign_change"\n'
            "            if metric_key in split_discontinuity_metrics:\n"
            '                return "growth_undefined_share_count_discontinuity"\n'
            "            if metric_key in immaterial_base_metrics:\n"
            '                return "immaterial_prior_year_base"\n'
            "            if metric_key in failed_metrics:\n"
            '                return "insufficient_history"\n'
            "            return None"
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
