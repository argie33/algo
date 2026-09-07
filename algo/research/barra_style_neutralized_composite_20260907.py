#!/usr/bin/env python3
"""
Barra-style winsorized-z-score + sector/size-neutralized composite vs the current live
architecture vs the naive within-sector-percentile approach, with TRUE (non-overlapping)
out-of-sample validation.

Built 2026-09-07 (goal session: "find all the stupid shit" scoring audit, direct follow-up to
sector_neutral_composite_test_20260907.py). That script found naive within-sector percentile
ranking underperforms the current universe-wide architecture, but used sector_neutral's
quality_proxy from build_pillar_proxy_records() (fama_macbeth_composite_weights.py), which
implements Quality's "universal" 8-field curve set from BEFORE this session's bank/insurer/
utility ROA/ROCE/debt-to-equity curve fixes (5b6921d9a, 56faea426, 5994b4d31, b8a6ee5e3) landed
this morning. So the naive-percentile-is-worse finding never actually tested against
today's live Quality formula - it tested a stale one. This script closes that gap AND tests the
more principled alternative the user actually asked about: regression-residual neutralization
(Barra/Axioma/MSCI-style - regress each pillar on sector dummies + log market cap, score the
RESIDUAL) instead of naive within-sector percentile rank.

quality_proxy_v2 construction: reuses fama_macbeth_quality_factors.py's build_quality_panel() for
roe/roa/roce/fcf_margin/debt_to_equity/margin_volatility_3y/gross_profitability, adds
asset_turnover the same way build_pillar_proxy_records() does (revenue/total_assets), then applies
the LIVE industry-conditional curves (verbatim-copied breakpoints, live-verified against
loaders/helpers/vqg_quality.py 2026-09-07) for roa_score/roce_score/debt_to_equity_score only -
the 3 components the morning's bank/insurer/utility fix actually touched. The other 5 components
keep this project's existing z-score treatment (unchanged from fama_macbeth_composite_weights.py).
DISCLOSED SIMPLIFICATION: roce's capital_employed here is the research panel's plain
total_debt+equity definition, NOT live's debt_for_roic override (total_liabilities for
banks/insurers) - reproducing that exactly would require rebuilding capital_employed from raw
balance-sheet lines not currently in this fundamentals panel. This makes quality_proxy_v2 a
best-effort, not byte-exact, reconstruction of the live fix for ROCE specifically (ROA and
Debt/Equity ARE exact reconstructions - both breakpoint dimensions apply directly to values this
panel already carries in the same units the live curve consumes).

Sector + log-market-cap neutralization: for each pillar, in each monthly cross-section, fits
OLS(pillar ~ C(sector) + log_mktcap) and keeps the RESIDUAL as that month's neutralized pillar
value (then re-z-scores the residual, matching this project's "everything comparable on the same
scale" convention). log_mktcap = ln(price * shares_diluted), same shares_diluted value_proxy
already fetches.

Out-of-sample discipline: unlike a WEIGHT-FITTING exercise (where a fit/holdout split guards
against picking weights that overfit noise), sector/size regression-residual neutralization has
no free parameters carried across time - it is re-estimated fresh in every monthly cross-section,
same as the naive percentile-rank alternative already in this repo. There is nothing to overfit
temporally here. The FIT (2017-2021) vs HOLDOUT (2022-2026) split below is therefore run and
reported for era-robustness (does the same relationship hold in an earlier vs a later, entirely
disjoint regime), not leakage-avoidance - reported honestly as exactly that, not dressed up as a
train/test split with parameters at stake.

Usage:
    python -m algo.research.barra_style_neutralized_composite_20260907 [options]
"""

import argparse
import itertools
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_composite_weights import (
    PILLAR_COLS,
    PILLAR_TO_LIVE_KEY,
    _zwinsor,
    build_pillar_proxy_records,
)
from algo.research.fama_macbeth_price_factors import fetch_month_end_prices
from algo.research.fama_macbeth_quality_factors import build_quality_panel, fetch_annual_quality_fundamentals
from loaders.stock_scores.pillar_weights import BASE_PILLAR_WEIGHTS
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

# Verbatim-copied from loaders/load_value_quality_growth_metrics.py, live-verified 2026-09-07.
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


def _margin_curve(value: float, breakpoints: list[tuple[float, float]]) -> float:
    """Verbatim copy of load_value_quality_growth_metrics.py's `_margin_curve` (same precedent
    as algo/research/all_pillars_curve_vs_percentile_sweep_20260828.py's own verbatim copy)."""
    if value < 0:
        return 0.0
    if value < breakpoints[0][0]:
        x1, y1 = breakpoints[0]
        return (value / x1) * y1 if x1 > 0 else y1
    for (x0, y0), (x1, y1) in itertools.pairwise(breakpoints):
        if value < x1:
            return y0 + (value - x0) / (x1 - x0) * (y1 - y0)
    return breakpoints[-1][1]


def fetch_symbol_industry_and_sector() -> pd.DataFrame:
    with DatabaseContext("read") as cur:
        cur.execute("SELECT symbol, sector, industry FROM company_profile WHERE sector IS NOT NULL")
        rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["symbol", "sector", "industry"]).set_index("symbol")


def _roa_score(roa_pct: float, industry: str | None) -> float:
    if industry in DEPOSITORY_BANK_INDUSTRIES:
        bp = [(0.5, 40.0), (1.0, 75.0), (1.5, 100.0)]
    elif industry in INSURANCE_UNDERWRITER_INDUSTRIES:
        bp = [(1.0, 40.0), (2.5, 75.0), (5.0, 100.0)]
    elif industry in UTILITY_INDUSTRIES:
        bp = [(2.0, 40.0), (3.0, 75.0), (4.5, 100.0)]
    else:
        bp = [(3.0, 40.0), (8.0, 80.0), (15.0, 100.0)]
    return _margin_curve(roa_pct, bp)


def _roce_score(roce_pct: float, industry: str | None) -> float:
    # NOTE: live's capital_employed for banks/insurers uses total_liabilities (debt_for_roic
    # override) - this proxy's capital_employed does not (see module docstring). Breakpoints
    # below are still the live, industry-conditional ones; only the input's exact numerator
    # differs for banks/insurers specifically. Disclosed approximation, not byte-exact.
    if industry in DEPOSITORY_BANK_INDUSTRIES:
        bp = [(2.5, 40.0), (5.0, 75.0), (8.0, 100.0)]
    elif industry in INSURANCE_UNDERWRITER_INDUSTRIES:
        bp = [(2.5, 40.0), (6.0, 75.0), (10.0, 100.0)]
    elif industry in UTILITY_INDUSTRIES:
        bp = [(3.0, 40.0), (5.5, 75.0), (8.0, 100.0)]
    else:
        bp = [(8.0, 40.0), (15.0, 75.0), (25.0, 100.0)]
    return _margin_curve(roce_pct, bp)


def _de_score(de: float, industry: str | None) -> float:
    if industry in DEPOSITORY_BANK_INDUSTRIES:
        return max(0.0, min(100.0, 100.0 - (de / 20.0) * 100.0))
    if industry in INSURANCE_UNDERWRITER_INDUSTRIES:
        return max(0.0, min(100.0, 100.0 - (de / 12.0) * 100.0))
    if industry in UTILITY_INDUSTRIES:
        return max(0.0, min(100.0, 100.0 - (de / 4.0) * 100.0))
    return max(0.0, min(100.0, 100.0 - (de / 2.0) * 100.0))


def build_quality_v2_annual(industry_map: pd.Series) -> pd.DataFrame:
    """Annual quality_v2 panel: same 8 components as build_pillar_proxy_records()'s
    quality_proxy, but roa/roce/debt_to_equity go through the LIVE industry-conditional curves
    (0-100), everything else keeps the existing raw-ratio z-score treatment. known_date carried
    through for merge_asof_monthly reuse."""
    quality_raw = fetch_annual_quality_fundamentals()
    q = build_quality_panel(quality_raw)
    q = q.merge(
        quality_raw[["symbol", "fiscal_year", "revenue", "total_assets"]], on=["symbol", "fiscal_year"], how="left"
    )
    q["asset_turnover"] = np.where(q["total_assets"] > 0, q["revenue"] / q["total_assets"], np.nan)
    q["industry"] = q["symbol"].map(industry_map)

    q["roa_score"] = [
        _roa_score(v * 100.0, ind) if pd.notna(v) else np.nan for v, ind in zip(q["roa"], q["industry"], strict=True)
    ]
    q["roce_score"] = [
        _roce_score(v * 100.0, ind) if pd.notna(v) else np.nan for v, ind in zip(q["roce"], q["industry"], strict=True)
    ]
    q["de_score"] = [
        _de_score(v, ind) if pd.notna(v) else np.nan for v, ind in zip(q["debt_to_equity"], q["industry"], strict=True)
    ]
    from algo.research.fama_macbeth_growth_factors import REPORTING_LAG_DAYS

    q["known_date"] = pd.to_datetime(q["fiscal_year"].astype(str) + "-12-31") + pd.Timedelta(days=REPORTING_LAG_DAYS)
    return q.dropna(subset=["known_date"])


def _quality_proxy_v2_from_monthly(qm: pd.DataFrame) -> pd.Series:
    """Combines quality_v2's 8 components at the SAME live nominal weights
    build_pillar_proxy_records() uses (11/18/18/15/18/7/7/7 over 101). roa/roce/debt_to_equity use
    their curve-scored (0-100) value z-scored for comparability; the other 5 keep raw-ratio
    z-scoring."""
    return (
        (11.0 / 101.0) * _zwinsor(qm["roe"])
        + (18.0 / 101.0) * _zwinsor(qm["roa_score"])
        + (18.0 / 101.0) * _zwinsor(qm["roce_score"])
        + (15.0 / 101.0) * _zwinsor(qm["fcf_margin"])
        + (18.0 / 101.0) * _zwinsor(-qm["de_score"])  # de_score already "higher=safer"; -curve keeps sign
        + (7.0 / 101.0) * _zwinsor(-qm["margin_volatility_3y"])
        + (7.0 / 101.0) * _zwinsor(qm["asset_turnover"])
        + (7.0 / 101.0) * _zwinsor(qm["gross_profitability"])
    )


def _neutralize(df: pd.DataFrame, col: str, sector_col: str, size_col: str) -> pd.Series:
    """Barra-style: OLS(col ~ C(sector) + size_col) via plain np.linalg.lstsq (statsmodels is
    not a project dependency - not adding one for this single research script), returns the
    residual (NaN-safe: rows with any missing input are excluded from the fit and get NaN
    residual)."""
    sub = df[[col, sector_col, size_col]].dropna()
    if len(sub) < 20 or sub[sector_col].nunique() < 2:
        return pd.Series(np.nan, index=df.index)
    dummies = pd.get_dummies(sub[sector_col], drop_first=True, dtype=float)
    x = pd.concat([dummies, sub[[size_col]]], axis=1)
    x.insert(0, "const", 1.0)
    x_mat = x.to_numpy(dtype=float)
    y_vec = sub[col].to_numpy(dtype=float)
    coefs, _residuals, _rank, _sv = np.linalg.lstsq(x_mat, y_vec, rcond=None)
    fitted = x_mat @ coefs
    resid = pd.Series(np.nan, index=df.index)
    resid.loc[sub.index] = y_vec - fitted
    return resid


def _pct_rank(s: pd.Series) -> pd.Series:
    return s.rank(pct=True, na_option="keep")


def run(start_date: str, end_date: str, min_cross_section: int, min_sector_size: int) -> None:
    logger.info("Building base pillar-proxy panel (growth/value/risk/momentum + OLD quality)")
    _rp, _rc, records_raw = build_pillar_proxy_records(start_date, end_date, min_cross_section)

    logger.info("Building quality_v2 (live industry-conditional ROA/ROCE/D2E curves)")
    prof = fetch_symbol_industry_and_sector()
    q_annual = build_quality_v2_annual(prof["industry"])

    from algo.research.fama_macbeth_growth_factors import merge_asof_monthly

    months = pd.DatetimeIndex(sorted({m for m, _ in records_raw}))
    q_monthly = merge_asof_monthly(
        months,
        q_annual,
        cols=[
            "roe",
            "roa_score",
            "roce_score",
            "de_score",
            "fcf_margin",
            "margin_volatility_3y",
            "asset_turnover",
            "gross_profitability",
        ],
    )

    logger.info("Fetching prices for market cap + rebuilding merged panel with sector/size")
    price_df = fetch_month_end_prices(start_date, end_date)
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    # fetch_month_end_prices' "month" column comes back as plain datetime.date - normalize to
    # pd.Timestamp so `month in px.index` / `px.loc[month]` below actually match the Timestamp
    # keys used everywhere else in this script (same date-vs-Timestamp mismatch fixed for
    # q_monthly/shares_monthly above).
    px.index = pd.to_datetime(px.index)

    from algo.research.fama_macbeth_composite_weights import build_value_panel_raw

    shares_panel = build_value_panel_raw()[["symbol", "fiscal_year", "shares_diluted", "known_date"]]
    shares_monthly = merge_asof_monthly(months, shares_panel, cols=["shares_diluted"])

    live_weight_map = {c: BASE_PILLAR_WEIGHTS[k] for c, k in PILLAR_TO_LIVE_KEY.items()}

    merged: list[tuple[pd.Timestamp, pd.DataFrame]] = []
    for month_raw, raw in records_raw:
        # records_raw's month key is a plain datetime.date (from px.index in
        # fama_macbeth_composite_weights.py), while months/q_monthly/shares_monthly/px here are
        # all keyed by pd.Timestamp - normalize once so every .get()/`.loc[]` lookup below
        # actually hits (a bare `datetime.date` != `pd.Timestamp` even for the same calendar day,
        # so every lookup silently missed before this normalization was added).
        month = pd.Timestamp(month_raw)
        df = raw.copy()
        qm = q_monthly.get(month)
        if qm is None or qm.empty:
            continue
        qv2 = _quality_proxy_v2_from_monthly(qm)
        df["quality_proxy"] = qv2.reindex(df.index)  # OVERWRITES old quality_proxy with v2

        df["sector"] = df.index.map(prof["sector"])
        sh = shares_monthly.get(month)
        shares = sh["shares_diluted"].reindex(df.index) if sh is not None else pd.Series(np.nan, index=df.index)
        price_row = px.loc[month].reindex(df.index) if month in px.index else pd.Series(np.nan, index=df.index)
        mktcap = price_row * shares
        df["log_mktcap"] = np.log(mktcap.where(mktcap > 0))

        df = df.dropna(subset=["sector", "log_mktcap", "fwd_ret", *PILLAR_COLS])
        if len(df) < min_cross_section:
            continue

        for col in PILLAR_COLS:
            df[col] = _zwinsor(df[col])

        df["composite_current"] = sum(df[c] * w for c, w in live_weight_map.items())

        sec_sizes = df.groupby("sector")[PILLAR_COLS[0]].transform("count")
        sector_pct = df.groupby("sector")[PILLAR_COLS].transform(_pct_rank)
        sector_composite = sum(sector_pct[c] * w for c, w in live_weight_map.items())
        df["composite_sector_naive"] = sector_composite.where(sec_sizes >= min_sector_size)

        resid_cols = {}
        for c in PILLAR_COLS:
            resid = _neutralize(df, c, "sector", "log_mktcap")
            resid_cols[c] = _zwinsor(resid)
        resid_df = pd.DataFrame(resid_cols, index=df.index)
        df["composite_neutral"] = sum(resid_df[c] * w for c, w in live_weight_map.items())

        merged.append((month, df))

    if not merged:
        raise RuntimeError("No usable months after merge - check date range / min_cross_section")

    logger.info(f"{len(merged)} usable months: {merged[0][0]} to {merged[-1][0]}")

    def _ic_series(records: list[tuple[pd.Timestamp, pd.DataFrame]], col: str) -> list[float]:
        out = []
        for _m, f in records:
            g = f.dropna(subset=[col, "fwd_ret"])
            if len(g) < 20:
                continue
            out.append(g[col].corr(g["fwd_ret"], method="spearman"))
        return [c for c in out if not np.isnan(c)]

    def _report(label: str, corrs: list[float]) -> None:
        arr = np.array(corrs)
        if len(arr) == 0:
            print(f"  {label:30s}  no usable months")
            return
        mean = arr.mean()
        se = arr.std(ddof=1) / np.sqrt(len(arr)) if len(arr) > 1 else float("nan")
        t = mean / se if se and se > 0 else float("nan")
        print(f"  {label:30s}  mean_IC={mean:8.4f}  t={t:7.2f}  n_months={len(arr):4d}")

    composites = ["composite_current", "composite_sector_naive", "composite_neutral"]

    fit_period = [(m, f) for m, f in merged if m.year <= 2021]
    holdout_period = [(m, f) for m, f in merged if m.year >= 2022]

    print(f"\n########## FULL SAMPLE ({merged[0][0]} to {merged[-1][0]}, {len(merged)} months) ##########")
    for c in composites:
        _report(c, _ic_series(merged, c))

    print(f"\n########## FIT PERIOD 2017-2021 ({len(fit_period)} months) - honest, not cherry-picked ##########")
    for c in composites:
        _report(c, _ic_series(fit_period, c))

    print(f"\n########## TRUE HOLDOUT 2022-2026 ({len(holdout_period)} months) - NEVER touched above ##########")
    for c in composites:
        _report(c, _ic_series(holdout_period, c))

    print("\n=== Financial Services concentration in top-decile, per composite, LAST MONTH ===")
    last_month, last_frame = merged[-1]
    print(f"({last_month})")
    for c in composites:
        f = last_frame.dropna(subset=[c])
        if f.empty:
            continue
        top_decile = f.nlargest(max(1, len(f) // 10), c)
        share = (top_decile["sector"] == "Financial Services").mean()
        universe_share = (f["sector"] == "Financial Services").mean()
        print(f"  {c:24s}  FinServ top-decile share={share:6.1%}  (universe share={universe_share:6.1%})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start-date", default="2015-06-01")
    parser.add_argument("--end-date", default=datetime.now(tz=None).date().isoformat())
    parser.add_argument("--min-cross-section", type=int, default=100)
    parser.add_argument("--min-sector-size", type=int, default=15)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.start_date, args.end_date, args.min_cross_section, args.min_sector_size)


if __name__ == "__main__":
    main()
