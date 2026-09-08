#!/usr/bin/env python3
"""
Validates the specific recalibrated ROA/ROCE breakpoints proposed in this session's
real-money-readiness audit (see memory:
quality_curve_calibration_level_shift_evidenced_not_validated_20260907) for
DEPOSITORY_BANK/INSURANCE_UNDERWRITER/UTILITY industries, against real forward returns,
BEFORE shipping them - this codebase's own governance requires FM/IC backtest validation
before any Quality/Value scoring-formula change, not a level-matching heuristic alone.

QUESTION: the current hand-set curves put a bank/insurer/utility's MEDIAN institution at a
Quality-cluster score of ~55-80 (DB-confirmed, see the memory note above) vs Industrials'
own median of ~55-58 on ITS curve. Recalibrating the breakpoints to anchor the median nearer
40-50 (a rank-preserving, purely monotonic rescale within each metric) is a LEVEL fix - it
provably cannot change within-industry-group Spearman IC at all (Spearman correlation is
invariant to any monotonic transform of one side of the pair), so
bank_insurer_utility_curve_vs_percentile_20260907.py's per-group methodology is structurally
incapable of testing this specific question. What actually needs checking is whether
recalibrating the LEVEL (not the shape) changes UNIVERSE-WIDE (cross-sector) ranking quality
- i.e. does it hurt overall Quality-proxy predictive power once financial-sector symbols are
newly competing on a level playing field with non-financial ones for the same rank position.

METHOD: builds a full-universe simplified Quality "profitability+safety cluster" proxy
(0.69*avg(roa_curve, roce_curve) + 0.25*debt_to_equity_curve, weight-renormalized on missing
components - approximating vqg_quality.py's real weighting) for EVERY symbol with usable
fundamentals: bank/insurer/utility symbols get their industry-conditional curve (OLD = current
live breakpoints, NEW = recalibrated candidate breakpoints; the DISCLOSED APPROXIMATION on
ROCE input from bank_insurer_utility_curve_vs_percentile_20260907.py applies identically
here), every other symbol gets the standard industrial curve, held IDENTICAL across both
scenarios (isolates the effect of the financial-sector recalibration alone). Compares
UNIVERSE-WIDE (all sectors together, not within-group) monthly cross-sectional Spearman IC
vs 1-month-forward returns between OLD and NEW, same FIT 2017-2021 / HOLDOUT 2022-2026 split
and |t|>=2-in-both-eras bar as every other scoring-formula validation in this codebase.

Usage:
    python -m algo.research.quality_curve_recalibration_validation_20260907 [options]
"""

import argparse
import itertools
import logging
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_growth_factors import merge_asof_monthly
from algo.research.fama_macbeth_price_factors import fetch_month_end_prices
from algo.research.fama_macbeth_quality_factors import build_quality_panel, fetch_annual_quality_fundamentals
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

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

# OLD = exact live breakpoints (loaders/helpers/vqg_quality.py, verbatim).
OLD_ROA_BREAKPOINTS = {
    "depository_bank": [(0.5, 40.0), (1.0, 75.0), (1.5, 100.0)],
    "insurance_underwriter": [(1.0, 40.0), (2.5, 75.0), (5.0, 100.0)],
    "utility": [(2.0, 40.0), (3.0, 75.0), (4.5, 100.0)],
}
OLD_ROCE_BREAKPOINTS = {
    "depository_bank": [(3.0, 40.0), (6.0, 75.0), (10.0, 100.0)],
    "insurance_underwriter": [(2.0, 40.0), (5.0, 75.0), (10.0, 100.0)],
    "utility": [(3.0, 40.0), (6.0, 75.0), (9.0, 100.0)],
}
# NEW = recalibrated candidate breakpoints proposed this session (p50~40/p75~80/p90~100
# against each group's own live DB distribution - see the memory note in this module's
# docstring for the source query). Bank ROCE left unchanged (already well-calibrated).
NEW_ROA_BREAKPOINTS = {
    "depository_bank": [(0.85, 40.0), (1.3, 80.0), (1.7, 100.0)],
    "insurance_underwriter": [(2.5, 40.0), (5.5, 80.0), (10.0, 100.0)],
    "utility": [(2.2, 40.0), (3.3, 80.0), (5.0, 100.0)],
}
NEW_ROCE_BREAKPOINTS = {
    "depository_bank": [(3.0, 40.0), (6.0, 75.0), (10.0, 100.0)],  # unchanged
    "insurance_underwriter": [(3.5, 40.0), (7.0, 80.0), (12.0, 100.0)],
    "utility": [(5.2, 40.0), (8.0, 80.0), (13.0, 100.0)],
}
DEBT_TO_EQUITY_K = {"depository_bank": 20.0, "insurance_underwriter": 12.0, "utility": 4.0}
# Standard "industrial" curve (loaders/helpers/vqg_quality.py's else-branch), held IDENTICAL
# across both OLD/NEW scenarios - isolates the effect of the financial-sector recalibration.
INDUSTRIAL_ROA_BREAKPOINTS = [(3.0, 40.0), (8.0, 80.0), (15.0, 100.0)]
INDUSTRIAL_ROCE_BREAKPOINTS = [(8.0, 40.0), (15.0, 75.0), (25.0, 100.0)]
INDUSTRIAL_DEBT_TO_EQUITY_K = 2.0

PROFITABILITY_WEIGHT = 0.69
SAFETY_WEIGHT = 0.25


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


def _group_for(industry: str | float) -> str | None:
    if industry in DEPOSITORY_BANK_INDUSTRIES:
        return "depository_bank"
    if industry in INSURANCE_UNDERWRITER_INDUSTRIES:
        return "insurance_underwriter"
    if industry in UTILITY_INDUSTRIES:
        return "utility"
    return None


def _quality_proxy(row: pd.Series, roa_bp: dict[str, Any], roce_bp: dict[str, Any]) -> float:
    """0.69*avg(roa_curve, roce_curve) + 0.25*de_curve, weight-renormalized on missing
    components - approximates vqg_quality.py's real profitability_cluster+safety_cluster
    blend without needing FCF-margin/gross-profitability/margin-volatility (usually absent
    for banks/insurers anyway, per the earlier investigation)."""
    group = row["group"]
    roa, roce, de = row["roa"], row["roce"], row["debt_to_equity"]

    if group is not None:
        roa_score = _margin_curve(roa * 100.0, roa_bp[group]) if pd.notna(roa) else None
        roce_score = _margin_curve(roce * 100.0, roce_bp[group]) if pd.notna(roce) else None
        de_score = _de_score(de, DEBT_TO_EQUITY_K[group]) if pd.notna(de) else None
    else:
        roa_score = _margin_curve(roa * 100.0, INDUSTRIAL_ROA_BREAKPOINTS) if pd.notna(roa) else None
        roce_score = _margin_curve(roce * 100.0, INDUSTRIAL_ROCE_BREAKPOINTS) if pd.notna(roce) else None
        de_score = _de_score(de, INDUSTRIAL_DEBT_TO_EQUITY_K) if pd.notna(de) else None

    profitability_inputs = [s for s in (roa_score, roce_score) if s is not None]
    profitability = float(np.mean(profitability_inputs)) if profitability_inputs else None

    components: list[tuple[float, float]] = []
    if profitability is not None:
        components.append((profitability, PROFITABILITY_WEIGHT))
    if de_score is not None:
        components.append((de_score, SAFETY_WEIGHT))
    if not components:
        return np.nan
    total_w = sum(w for _, w in components)
    return sum(v * w for v, w in components) / total_w


def fetch_symbol_industry_sector() -> pd.DataFrame:
    with DatabaseContext("read") as cur:
        cur.execute("SELECT symbol, industry, sector FROM company_profile")
        rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["symbol", "industry", "sector"]).set_index("symbol")


def _ic_series(recs: list[tuple[pd.Timestamp, pd.DataFrame]], col: str) -> list[float]:
    out = []
    for _m, f in recs:
        if len(f) < 30:  # universe-wide floor, much higher than the per-group script's 5
            continue
        c = f[col].corr(f["fwd_ret"], method="spearman")
        if not np.isnan(c):
            out.append(c)
    return out


def _report(label: str, corrs: list[float]) -> None:
    arr = np.array(corrs)
    if len(arr) == 0:
        print(f"    {label:20s}  no usable months")
        return
    mean = arr.mean()
    se = arr.std(ddof=1) / np.sqrt(len(arr)) if len(arr) > 1 else float("nan")
    t = mean / se if se and se > 0 else float("nan")
    print(f"    {label:20s}  mean_IC={mean:8.4f}  t={t:7.2f}  n_months={len(arr):4d}")


def run(start_date: str, end_date: str) -> None:
    logger.info("Fetching symbol->industry/sector map")
    meta = fetch_symbol_industry_sector()

    logger.info("Fetching annual fundamentals + building quality panel")
    fund = fetch_annual_quality_fundamentals()
    panel = build_quality_panel(fund)
    panel = panel.join(meta, on="symbol")
    panel["group"] = panel["industry"].map(_group_for)

    n_financial = panel[panel["group"].notna()]["symbol"].nunique()
    n_total = panel["symbol"].nunique()
    print(f"Universe: {n_total} symbols total, {n_financial} in a recalibrated financial group")

    panel["proxy_old"] = panel.apply(lambda r: _quality_proxy(r, OLD_ROA_BREAKPOINTS, OLD_ROCE_BREAKPOINTS), axis=1)
    panel["proxy_new"] = panel.apply(lambda r: _quality_proxy(r, NEW_ROA_BREAKPOINTS, NEW_ROCE_BREAKPOINTS), axis=1)

    print("\n=== Level check: median/mean proxy score BY GROUP, latest fiscal year per symbol ===")
    latest = panel.sort_values(["symbol", "fiscal_year"]).groupby("symbol", as_index=False).last()
    for group in (*GROUPS.keys(), None):
        sub = latest[latest["group"] == group] if group is not None else latest[latest["group"].isna()]
        label = group or "industrial/other (unchanged baseline)"
        if len(sub) == 0:
            continue
        print(
            f"  {label:38s} n={len(sub):5d}  "
            f"OLD median={sub['proxy_old'].median():6.1f} mean={sub['proxy_old'].mean():6.1f}   "
            f"NEW median={sub['proxy_new'].median():6.1f} mean={sub['proxy_new'].mean():6.1f}"
        )

    logger.info(f"Pulling month-end price panel {start_date}..{end_date}")
    price_df = fetch_month_end_prices(start_date, end_date)
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    months = px.index

    sub = panel[["symbol", "known_date", "proxy_old", "proxy_new"]].dropna(subset=["proxy_old", "proxy_new"])
    monthly = merge_asof_monthly(months, sub, cols=["proxy_old", "proxy_new"])

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
        if len(frame) < 30:
            continue
        records.append((month, frame))

    if not records:
        print("\nNO usable universe-wide cross-sectional months. Aborting IC comparison.")
        return

    sizes = [len(f) for _, f in records]
    print(
        f"\n=== Universe-wide monthly cross-sectional IC: OLD vs NEW curves ===\n"
        f"{len(records)} usable months ({records[0][0]} to {records[-1][0]}), "
        f"cross-section n: median={int(np.median(sizes))} min={min(sizes)} max={max(sizes)}"
    )

    fit = [(m, f) for m, f in records if m.year <= 2021]
    holdout = [(m, f) for m, f in records if m.year >= 2022]

    print("  -- FULL SAMPLE --")
    _report("proxy_old", _ic_series(records, "proxy_old"))
    _report("proxy_new", _ic_series(records, "proxy_new"))
    print(f"  -- FIT 2017-2021 ({len(fit)} months) --")
    _report("proxy_old", _ic_series(fit, "proxy_old"))
    _report("proxy_new", _ic_series(fit, "proxy_new"))
    print(f"  -- HOLDOUT 2022-2026 ({len(holdout)} months, never touched above) --")
    _report("proxy_old", _ic_series(holdout, "proxy_old"))
    _report("proxy_new", _ic_series(holdout, "proxy_new"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start-date", default="2015-06-01")
    parser.add_argument("--end-date", default=datetime.now(tz=None).date().isoformat())
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.start_date, args.end_date)


if __name__ == "__main__":
    main()
