#!/usr/bin/env python3
"""
Tests the 3 hand-calibrated industry-conditional Quality curves added this morning
(loaders/helpers/vqg_quality.py, commits 5b6921d9a/56faea426/5994b4d31/b8a6ee5e3 - ROA/ROCE/
debt-to-equity breakpoints for DEPOSITORY_BANK_INDUSTRIES/INSURANCE_UNDERWRITER_INDUSTRIES/
UTILITY_INDUSTRIES) against real forward returns, for each industry group separately, comparing
THREE alternatives per metric:
  (a) the current live hand-set curve (exact breakpoints copied verbatim below)
  (b) a within-industry-group cross-sectional percentile rank
  (c) a within-industry-group cross-sectional z-score

Built 2026-09-07 (direct follow-up to barra_style_neutralized_composite_20260907.py and the new
weight-revision governance policy in loaders/stock_scores/pillar_weights.py - these 3 curve sets
are the one piece of the live scoring system hand-calibrated off 10-16 symbol spot-checks with
NO forward-return validation at all, unlike every other component in this pipeline).

Exact live breakpoints (verbatim from loaders/helpers/vqg_quality.py, read directly, not
approximated - live-verified 2026-09-07):
  ROA (metrics["roa"], a percentage e.g. 1.29 for 1.29%):
    depository_bank:  [(0.5, 40.0), (1.0, 75.0), (1.5, 100.0)]
    insurance_underwriter: [(1.0, 40.0), (2.5, 75.0), (5.0, 100.0)]
    utility: [(2.0, 40.0), (3.0, 75.0), (4.5, 100.0)]
  ROCE (roce_pct, a percentage):
    depository_bank:  [(3.0, 40.0), (6.0, 75.0), (10.0, 100.0)]
    insurance_underwriter: [(2.0, 40.0), (5.0, 75.0), (10.0, 100.0)]
    utility: [(3.0, 40.0), (6.0, 75.0), (9.0, 100.0)]
  Debt-to-Equity (a plain ratio, e.g. 10.25 for JPM), score = 100 - (de / K) * 100, clamped [0,100]:
    depository_bank:  K=20.0
    insurance_underwriter: K=12.0
    utility: K=4.0

DISCLOSED APPROXIMATION (same one barra_style_neutralized_composite_20260907.py already made and
disclosed): this script's ROCE input reuses fama_macbeth_quality_factors.py's build_quality_panel()
ROCE = operating_income / (stockholders_equity + total_debt) - a plain textbook capital-employed
denominator, NOT live's debt_for_roic override (total_liabilities for banks/insurers, which makes
a bank's live capital_employed ~its entire deposit-funded balance sheet). Reproducing that exactly
would require rebuilding capital_employed from raw balance-sheet lines this research panel doesn't
carry. ROA and Debt-to-Equity ARE exact reconstructions - both apply directly to values this panel
already carries in the same units/definition the live curve consumes. This means the ROCE curve
numbers below are being fed a DIFFERENT (unscaled) input than production actually uses for
banks/insurers specifically - treat the ROCE result here as a directional check on curve-shape,
not a byte-exact validation of the live ROCE score.

Universes are small (task explicitly calls this out) - depository banks are maybe a few hundred
symbols, insurers/utilities far fewer. Every reported result includes the actual median/min
cross-sectional n so a thin-sample result cannot be mistaken for a robust one. Same fit/holdout
split as barra_style_neutralized_composite_20260907.py: FIT 2017-2021, TRUE HOLDOUT 2022-2026,
never touched until reported here. |t|>=2 in BOTH periods is the bar per the new governance
policy in loaders/stock_scores/pillar_weights.py; a group too thin to reach that bar honestly
says so rather than forcing a verdict.

Usage:
    python -m algo.research.bank_insurer_utility_curve_vs_percentile_20260907 [options]
"""

import argparse
import itertools
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_growth_factors import merge_asof_monthly
from algo.research.fama_macbeth_price_factors import fetch_month_end_prices
from algo.research.fama_macbeth_quality_factors import build_quality_panel, fetch_annual_quality_fundamentals
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

# Verbatim from loaders/load_value_quality_growth_metrics.py (the frozensets loaders/helpers/
# vqg_quality.py's _owner() resolves to) - live-verified 2026-09-07, not reinvented.
DEPOSITORY_BANK_INDUSTRIES = frozenset(
    {
        "State Commercial Banks",
        "National Commercial Banks",
        "Commercial Banks, NEC",
        "Savings Institution, Federally Chartered",
        "Savings Institutions, Not Federally Chartered",
        "Functions Related To Depository Banking, NEC",
    }
)
INSURANCE_UNDERWRITER_INDUSTRIES = frozenset(
    {
        "Fire, Marine & Casualty Insurance",
        "Life Insurance",
        "Accident & Health Insurance",
        "Surety Insurance",
        "Title Insurance",
        "Insurance Carriers, NEC",
    }
)
UTILITY_INDUSTRIES = frozenset(
    {
        "Electric Services",
        "Electric & Other Services Combined",
        "Water Supply",
        "Natural Gas Distribution",
    }
)

GROUPS: dict[str, frozenset[str]] = {
    "depository_bank": DEPOSITORY_BANK_INDUSTRIES,
    "insurance_underwriter": INSURANCE_UNDERWRITER_INDUSTRIES,
    "utility": UTILITY_INDUSTRIES,
}

# Exact live breakpoints, copied verbatim from loaders/helpers/vqg_quality.py 2026-09-07.
ROA_BREAKPOINTS = {
    "depository_bank": [(0.5, 40.0), (1.0, 75.0), (1.5, 100.0)],
    "insurance_underwriter": [(1.0, 40.0), (2.5, 75.0), (5.0, 100.0)],
    "utility": [(2.0, 40.0), (3.0, 75.0), (4.5, 100.0)],
}
ROCE_BREAKPOINTS = {
    "depository_bank": [(3.0, 40.0), (6.0, 75.0), (10.0, 100.0)],
    "insurance_underwriter": [(2.0, 40.0), (5.0, 75.0), (10.0, 100.0)],
    "utility": [(3.0, 40.0), (6.0, 75.0), (9.0, 100.0)],
}
DEBT_TO_EQUITY_K = {
    "depository_bank": 20.0,
    "insurance_underwriter": 12.0,
    "utility": 4.0,
}


def _margin_curve(value: float, breakpoints: list[tuple[float, float]]) -> float:
    """Verbatim copy of load_value_quality_growth_metrics.py's `_margin_curve`."""
    if value < 0:
        return 0.0
    if value < breakpoints[0][0]:
        x1, y1 = breakpoints[0]
        return (value / x1) * y1 if x1 > 0 else y1
    for (x0, y0), (x1, y1) in itertools.pairwise(breakpoints):
        if value < x1:
            return y0 + (value - x0) / (x1 - x0) * (y1 - y0)
    return breakpoints[-1][1]


def _de_score(de: float, k: float) -> float:
    return max(0.0, min(100.0, 100.0 - (de / k) * 100.0))


def fetch_symbol_industry() -> pd.Series:
    with DatabaseContext("read") as cur:
        cur.execute("SELECT symbol, industry FROM company_profile WHERE industry IS NOT NULL")
        rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["symbol", "industry"]).set_index("symbol")["industry"]


def build_group_panel(group: str, industry_map: pd.Series) -> pd.DataFrame:
    fund = fetch_annual_quality_fundamentals()
    q = build_quality_panel(fund)
    q["industry"] = q["symbol"].map(industry_map)
    q = q[q["industry"].isin(GROUPS[group])].copy()

    roa_pct = q["roa"] * 100.0
    roce_pct = q["roce"] * 100.0
    de = q["debt_to_equity"]

    q["roa_curve"] = [_margin_curve(v, ROA_BREAKPOINTS[group]) if pd.notna(v) else np.nan for v in roa_pct]
    q["roce_curve"] = [_margin_curve(v, ROCE_BREAKPOINTS[group]) if pd.notna(v) else np.nan for v in roce_pct]
    q["debt_to_equity_curve"] = [_de_score(v, DEBT_TO_EQUITY_K[group]) if pd.notna(v) else np.nan for v in de]
    return q


def _pct_rank_within_month(s: pd.Series) -> pd.Series:
    return s.rank(pct=True, na_option="keep") * 100.0


def _zscore_within_month(s: pd.Series) -> pd.Series:
    lo, hi = s.quantile([0.01, 0.99])
    clipped = s.clip(lo, hi)
    std = clipped.std()
    return (clipped - clipped.mean()) / std if std and std > 0 else pd.Series(0.0, index=s.index)


def run(start_date: str, end_date: str, min_cross_section: int) -> None:
    logger.info("Fetching symbol->industry map")
    industry_map = fetch_symbol_industry()

    logger.info(f"Pulling month-end price panel {start_date}..{end_date}")
    price_df = fetch_month_end_prices(start_date, end_date)
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    months = px.index

    for group in GROUPS:
        print(f"\n{'=' * 90}\nGROUP: {group}\n{'=' * 90}")
        panel = build_group_panel(group, industry_map)
        n_symbols = panel["symbol"].nunique()
        print(f"Distinct symbols with any usable fundamentals row: {n_symbols}")
        if n_symbols == 0:
            print("  NO SYMBOLS - industry list did not match any company_profile.industry value. Skipping.")
            continue

        for raw_col, curve_col, invert in (
            ("roa", "roa_curve", False),
            ("roce", "roce_curve", False),
            ("debt_to_equity", "debt_to_equity_curve", True),
        ):
            sub = panel[["symbol", "known_date", raw_col, curve_col]].dropna(subset=[raw_col, curve_col])
            monthly = merge_asof_monthly(months, sub, cols=[raw_col, curve_col])

            records: list[tuple[pd.Timestamp, pd.DataFrame]] = []
            for i in range(len(months) - 1):
                month = months[i]
                mframe = monthly.get(month)
                if mframe is None or mframe.empty:
                    continue
                fwd_ret = px.iloc[i + 1] / px.iloc[i] - 1.0
                frame = mframe.join(fwd_ret.rename("fwd_ret"), how="inner")
                frame = frame.replace([np.inf, -np.inf], np.nan).dropna()
                frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
                if len(frame) < 5:  # absolute floor just to avoid n=1/2 degenerate correlations
                    continue

                raw_for_rank = -frame[raw_col] if invert else frame[raw_col]
                frame["alt_curve"] = frame[curve_col]
                frame["alt_percentile"] = _pct_rank_within_month(raw_for_rank)
                frame["alt_zscore"] = _zscore_within_month(raw_for_rank)
                records.append((month, frame))

            if not records:
                print(f"\n  [{raw_col}] NO usable cross-sectional months at all (n>=5 floor). Skipping.")
                continue

            sizes = [len(f) for _, f in records]
            print(
                f"\n  [{raw_col}] {len(records)} usable months ({records[0][0]} to "
                f"{records[-1][0]}), cross-section n: median={int(np.median(sizes))} "
                f"min={min(sizes)} max={max(sizes)}"
            )
            below_min = sum(1 for s in sizes if s < min_cross_section)
            if below_min:
                print(
                    f"    NOTE: {below_min}/{len(sizes)} months have n<{min_cross_section} "
                    f"(--min-cross-section) - included anyway, interpret thin months with extra caution."
                )

            def _ic_series(recs: list[tuple[pd.Timestamp, pd.DataFrame]], col: str) -> list[float]:
                out = []
                for _m, f in recs:
                    if len(f) < 5:
                        continue
                    c = f[col].corr(f["fwd_ret"], method="spearman")
                    if not np.isnan(c):
                        out.append(c)
                return out

            def _report(label: str, corrs: list[float]) -> None:
                arr = np.array(corrs)
                if len(arr) == 0:
                    print(f"    {label:16s}  no usable months")
                    return
                mean = arr.mean()
                se = arr.std(ddof=1) / np.sqrt(len(arr)) if len(arr) > 1 else float("nan")
                t = mean / se if se and se > 0 else float("nan")
                print(f"    {label:16s}  mean_IC={mean:8.4f}  t={t:7.2f}  n_months={len(arr):4d}")

            fit = [(m, f) for m, f in records if m.year <= 2021]
            holdout = [(m, f) for m, f in records if m.year >= 2022]

            print("    -- FULL SAMPLE --")
            for alt in ("alt_curve", "alt_percentile", "alt_zscore"):
                _report(alt, _ic_series(records, alt))
            print(f"    -- FIT 2017-2021 ({len(fit)} months) --")
            for alt in ("alt_curve", "alt_percentile", "alt_zscore"):
                _report(alt, _ic_series(fit, alt))
            print(f"    -- HOLDOUT 2022-2026 ({len(holdout)} months, never touched above) --")
            for alt in ("alt_curve", "alt_percentile", "alt_zscore"):
                _report(alt, _ic_series(holdout, alt))

    print("\n=== Current live stock_scores top-200 Financial Services concentration ===")
    with DatabaseContext("read") as cur:
        cur.execute(
            """
            SELECT cp.sector
            FROM stock_scores s
            JOIN company_profile cp ON cp.symbol = s.symbol
            WHERE s.date = (SELECT MAX(date) FROM stock_scores)
              AND s.composite_score IS NOT NULL
            ORDER BY s.composite_score DESC
            LIMIT 200
            """
        )
        top200 = cur.fetchall()
        cur.execute("SELECT MAX(date) FROM stock_scores")
        max_date = cur.fetchone()[0]
    top200_df = pd.DataFrame(top200, columns=["sector"])
    total = len(top200)
    print(f"stock_scores date: {max_date}, top-200 rows returned: {total}")
    if total:
        by_sector = top200_df["sector"].value_counts()
        for sector, n in by_sector.items():
            print(f"  {sector:28s} {n:4d}  ({n / total:6.1%})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start-date", default="2015-06-01")
    parser.add_argument("--end-date", default=datetime.now(tz=None).date().isoformat())
    parser.add_argument("--min-cross-section", type=int, default=15)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.start_date, args.end_date, args.min_cross_section)


if __name__ == "__main__":
    main()
