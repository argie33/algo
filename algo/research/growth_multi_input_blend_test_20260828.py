#!/usr/bin/env python3
"""
Growth multi-input blend test.

Built 2026-08-28 (goal: user pushback on Growth pillar's single-input architecture -
loaders/load_stock_scores.py._score_growth has been rebuilt 3 times in 2 days, each time
collapsing to ONE scored input via isolated Fama-MacBeth "winner take all" testing: the
original 11-input blend -> book_value_growth alone -> revenue_growth_1y alone (current
uncommitted working-tree state). User's objection is legitimate on its own terms independent of
raw predictive power: a single-input pillar is fragile to that one field's own data-coverage gaps
(book_value_growth's 72.9% coverage silently starved ~27% of the universe of any Growth score at
all) and unstable across reruns/re-tests. This script tests whether a genuinely diversified
multi-input blend can match the current single-input's predictive power while being more robust
on coverage - a different question than "which single factor has the highest t-stat," which is
what killed every previous multi-input attempt in this repo.

Reuses this repo's own established point-in-time reconstruction machinery directly, no
re-derivation: fama_macbeth_growth_factors.py (revenue_growth_1y, eps_growth_1y, ni_growth_yoy,
ocf_growth_yoy - all already correctly signed/lagged), growth_reinvestment_book_value_candidates.py
(book_value_growth), fama_macbeth_quality_factors.py (roe + payout_ratio, combined here into
sustainable_growth_rate = roe * (1 - payout_ratio), the standard textbook definition - not
computed as a standalone candidate anywhere else in this repo).

Candidate set (5 fields, chosen for genuinely distinct growth angles, not time-window duplicates
of the same signal - explicitly excludes eps_growth_3y/5y and revenue_growth_3y/5y, which this
repo's own prior audit already found redundant with the 1y versions):
- revenue_growth_1y   (top-line)
- eps_growth_1y       (bottom-line, per-share)
- ocf_growth_yoy      (cash-generation - chosen over ni_growth_yoy: OCF is less accrual-sensitive
                        and this repo's own fama_macbeth_quality_factors.py accruals_ratio work
                        already treats OCF as the more trustworthy cash-flow signal)
- book_value_growth   (balance-sheet-driven, the most recent single "winner")
- sustainable_growth_rate (ROE x retention - quality-adjusted growth, a genuinely distinct
                        construction from the other 4, which are all raw YoY growth rates)

All 5 (and revenue_growth_1y, the CURRENT live scored field) use the SAME sign-flip convention
already established in _score_growth's live docstring (Cooper/Gulen/Schill 2008 growth-reversal -
LOWER growth scores HIGHER) - z-scored then negated, consistent with every other growth candidate
this repo has ever tested.

Three variants tested:
(a) SINGLE  - revenue_growth_1y alone (exact replica of the CURRENT live/uncommitted formula)
(b) EQUAL   - simple average of the 5 candidates' individual z-scores, each independently
              winsorized+z-scored first, averaged over whatever subset is non-null per
              symbol-month (partial-availability renormalization - same principle as Quality's
              floor-renormalization, not a joint-dropna that would re-introduce the exact
              coverage fragility being tested against)
(c) WEIGHTED - each candidate weighted by its own isolated full-sample univariate |t-stat|
              (computed once, in the SAME data before any FULL/ERA split, to avoid a lookahead/
              overfitting the split itself) - a middle ground between (a) and (b)

Regime: partial-availability only (0-imputed on the composite side via CONTROL_COLS' existing
fillna(0.0) pattern, matching algo/research/sector_relative_scoring_test_20260828.py's own
documented simplification for a relative 3-way comparison).

Usage:
    python -m algo.research.growth_multi_input_blend_test_20260828 [options]
"""

import argparse
import logging
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_composite_weights import _zwinsor, build_value_panel_raw
from algo.research.fama_macbeth_growth_factors import (
    build_growth_panel,
    fetch_annual_fundamentals,
)
from algo.research.fama_macbeth_growth_factors import (
    merge_asof_monthly as merge_asof_monthly_growth,
)
from algo.research.fama_macbeth_momentum_factors import build_month_end_panel, compute_daily_indicators
from algo.research.fama_macbeth_momentum_factors import fetch_daily_prices as fetch_daily_close
from algo.research.fama_macbeth_price_factors import _fama_macbeth, fetch_month_end_prices
from algo.research.fama_macbeth_quality_factors import build_quality_panel, fetch_annual_quality_fundamentals
from algo.research.growth_reinvestment_book_value_candidates import build_panel as build_book_value_panel
from algo.research.growth_reinvestment_book_value_candidates import fetch_panel_raw as fetch_book_value_fundamentals
from algo.research.sector_relative_scoring_test_20260828 import fetch_sector_map

logger = logging.getLogger(__name__)

UNCLASSIFIED = "Unclassified"
CANDIDATE_COLS = [
    "revenue_growth_1y",
    "eps_growth_1y",
    "ocf_growth_yoy",
    "book_value_growth",
    "sustainable_growth_rate",
]
VARIANT_COLS = ["growth_single", "growth_equal", "growth_weighted"]
CONTROL_COLS = ["value_proxy", "quality_proxy", "stability_proxy", "momentum_proxy", "size_proxy"]
FOCUS_SECTORS = ["Financial Services", "Real Estate"]
MIN_SECTOR_SLICE = 10


def _pct_available(frame: pd.DataFrame, cols: list[str]) -> pd.Series:
    """Per-row count of non-null candidate columns, as a fraction of len(cols)."""
    return frame[cols].notna().sum(axis=1) / len(cols)


def _renormalized_blend(z: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """Weighted average over whatever subset of z's columns is non-null per row, renormalizing
    weights to sum to 1 over the available subset (Quality-floor-style partial availability)."""
    w = pd.Series(weights)
    avail = z.notna()
    w_matrix = avail.mul(w, axis=1)
    row_weight_sum = w_matrix.sum(axis=1)
    weighted = (z.fillna(0.0) * w_matrix).sum(axis=1)
    out = pd.Series(np.nan, index=z.index)
    valid = row_weight_sum > 0
    out.loc[valid] = weighted.loc[valid] / row_weight_sum.loc[valid]
    return out


def run(start_date: str, end_date: str, min_cross_section: int) -> None:  # noqa: C901 -- research/reporting script's linear sequence of print sections
    logger.info("Fetching sector map (company_profile)")
    sector_map = fetch_sector_map()

    logger.info("Building fundamentals panels (growth candidates, value, quality)")
    growth_raw = fetch_annual_fundamentals()
    growth_panel = build_growth_panel(growth_raw)  # revenue_growth_1y, eps_growth_1y, ocf_growth_yoy, ...

    bv_panel = build_book_value_panel(fetch_book_value_fundamentals())  # book_value_growth

    quality_raw = fetch_annual_quality_fundamentals()
    quality_fund = build_quality_panel(quality_raw)  # roe, payout_ratio, ... (+ known_date)
    quality_fund["sustainable_growth_rate"] = np.where(
        quality_fund["payout_ratio"].notna(),
        quality_fund["roe"] * (1.0 - quality_fund["payout_ratio"].clip(0.0, 1.0)),
        np.nan,
    )
    quality_fund = quality_fund.merge(
        quality_raw[["symbol", "fiscal_year", "revenue", "total_assets"]], on=["symbol", "fiscal_year"], how="left"
    )
    quality_fund["asset_turnover"] = np.where(
        quality_fund["total_assets"] > 0, quality_fund["revenue"] / quality_fund["total_assets"], np.nan
    )

    value_fund = build_value_panel_raw()

    logger.info("Fetching price panel + momentum/stability indicators")
    price_df = fetch_month_end_prices(start_date, end_date)
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    ret = px.pct_change(fill_method=None)
    mkt = ret["SPY"]
    months = px.index
    months_period = pd.PeriodIndex(months, freq="M")

    daily_close = fetch_daily_close(start_date, end_date)
    daily_close = compute_daily_indicators(daily_close)
    _px_daily, indicators = build_month_end_panel(daily_close)
    for key in indicators:
        indicators[key] = (
            indicators[key].set_axis(pd.PeriodIndex(indicators[key].index, freq="M")).reindex(months_period)
        )

    growth_monthly = merge_asof_monthly_growth(
        months, growth_panel, cols=["revenue_growth_1y", "eps_growth_1y", "ocf_growth_yoy"]
    )
    bv_monthly = merge_asof_monthly_growth(months, bv_panel, cols=["book_value_growth"])
    quality_monthly = merge_asof_monthly_growth(
        months,
        quality_fund,
        cols=[
            "roe",
            "roa",
            "roce" if "roce" in quality_fund.columns else "roe",
            "fcf_margin" if "fcf_margin" in quality_fund.columns else "roe",
            "debt_to_assets",
            "sustainable_growth_rate",
            "asset_turnover",
            "gross_profitability" if "gross_profitability" in quality_fund.columns else "roe",
        ],
    )
    value_monthly = merge_asof_monthly_growth(
        months, value_fund, cols=["eps", "book_value_per_share", "sales_per_share", "fcf_per_share", "shares_diluted"]
    )

    beta_window = 24
    vol_window = 12
    raw_records: list[tuple[pd.Timestamp, pd.DataFrame]] = []

    for i in range(beta_window, len(months) - 1):
        month = months[i]
        gr = growth_monthly.get(month)
        bv = bv_monthly.get(month)
        q = quality_monthly.get(month)
        v = value_monthly.get(month)
        if gr is None or bv is None or q is None or v is None or gr.empty or bv.empty or q.empty or v.empty:
            continue

        idx = gr.index.union(bv.index).union(q.index).union(v.index)
        cand = pd.DataFrame(index=idx)
        cand["revenue_growth_1y"] = gr["revenue_growth_1y"].reindex(idx)
        cand["eps_growth_1y"] = gr["eps_growth_1y"].reindex(idx)
        cand["ocf_growth_yoy"] = gr["ocf_growth_yoy"].reindex(idx)
        cand["book_value_growth"] = bv["book_value_growth"].reindex(idx)
        cand["sustainable_growth_rate"] = q["sustainable_growth_rate"].reindex(idx)

        # Sign-flip convention: lower growth = higher score (Cooper/Gulen/Schill reversal),
        # matching _score_growth's live docstring. Winsorize+z-score each candidate independently.
        z = pd.DataFrame(index=idx)
        for col in CANDIDATE_COLS:
            z[col] = -_zwinsor(cand[col])

        growth_single = z["revenue_growth_1y"]
        growth_equal = _renormalized_blend(z, dict.fromkeys(CANDIDATE_COLS, 1.0))

        price = px.iloc[i].reindex(v.index)
        pe = pd.Series(np.where(v["eps"] > 0, price / v["eps"], np.nan), index=v.index)
        pb = pd.Series(
            np.where(v["book_value_per_share"] > 0, price / v["book_value_per_share"], np.nan), index=v.index
        )
        ps = pd.Series(np.where(v["sales_per_share"] > 0, price / v["sales_per_share"], np.nan), index=v.index)
        fcf_yield = v["fcf_per_share"] / price
        value_proxy = (
            (12.0 / 78.0) * _zwinsor(-pe)
            + (30.0 / 78.0) * _zwinsor(-pb)
            + (27.0 / 78.0) * _zwinsor(-ps)
            + (9.0 / 78.0) * _zwinsor(fcf_yield)
        )

        market_cap = price * v["shares_diluted"]
        log_mc = np.where((market_cap >= 1e6) & (market_cap <= 1e13), np.log10(market_cap), np.nan)
        size_proxy = _zwinsor(-pd.Series(log_mc, index=v.index))

        quality_proxy = (
            (11.0 / 101.0) * _zwinsor(q["roe"])
            + (18.0 / 101.0) * _zwinsor(q["roa"])
            + (18.0 / 101.0) * _zwinsor(-q["debt_to_assets"])
            + (7.0 / 101.0) * _zwinsor(q["asset_turnover"])
        )

        win = ret.iloc[i - vol_window + 1 : i + 1]
        vol = win.std() * np.sqrt(12)
        downside_vol = win.where(win < 0).std() * np.sqrt(12)
        winb = ret.iloc[i - beta_window + 1 : i + 1]
        mkt_win = mkt.iloc[i - beta_window + 1 : i + 1]
        mkt_var = mkt_win.var()
        beta = (
            winb.apply(lambda col, m=mkt_win: col.cov(m)) / mkt_var
            if mkt_var and mkt_var > 0
            else pd.Series(np.nan, index=winb.columns)
        )
        win_px = px.iloc[i - vol_window + 1 : i + 1]
        max_dd = (win_px / win_px.cummax() - 1.0).min()
        stability_proxy = (
            0.45 * _zwinsor(-vol)
            + 0.20 * _zwinsor(-(beta - 1.0).abs())
            + 0.15 * _zwinsor(-downside_vol)
            + 0.20 * _zwinsor(max_dd)
        )

        def _trailing_cumret(px_frame: pd.DataFrame, end_idx: int, n_months: int) -> pd.Series:
            if end_idx - n_months < 0:
                return pd.Series(np.nan, index=px_frame.columns)
            start = px_frame.iloc[end_idx - n_months]
            end = px_frame.iloc[end_idx]
            with np.errstate(divide="ignore", invalid="ignore"):
                return end / start - 1.0

        mom_3m = _trailing_cumret(px, i, 3)
        mom_12_1 = _trailing_cumret(px, i - 1, 11)
        rsi = indicators["rsi_14"].iloc[i]
        macd_sign = indicators["macd_sign"].iloc[i]
        sma_avg = (indicators["price_vs_sma_50"].iloc[i] + indicators["price_vs_sma_200"].iloc[i]) / 2.0
        momentum_proxy = (
            0.20 * _zwinsor(mom_3m)
            + 0.35 * _zwinsor(mom_12_1)
            + 0.21 * _zwinsor(rsi)
            + 0.16 * _zwinsor(macd_sign)
            + 0.08 * _zwinsor(sma_avg)
        )

        fwd_ret = ret.iloc[i + 1]
        sectors_here = sector_map.reindex(idx).fillna(UNCLASSIFIED)

        frame = pd.DataFrame(
            {
                "growth_single": growth_single,
                "growth_equal": growth_equal,
                "value_proxy": value_proxy.reindex(idx),
                "quality_proxy": quality_proxy.reindex(idx),
                "stability_proxy": stability_proxy.reindex(idx),
                "momentum_proxy": momentum_proxy.reindex(idx),
                "size_proxy": size_proxy.reindex(idx),
                "fwd_ret": fwd_ret.reindex(idx),
                "n_candidates_available": z[CANDIDATE_COLS].notna().sum(axis=1),
            }
        )
        for col in CANDIDATE_COLS:
            frame[f"raw_{col}"] = z[col]
        frame["sector"] = sectors_here
        frame = frame.replace([np.inf, -np.inf], np.nan)
        frame = frame.dropna(subset=["fwd_ret"])
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        if len(frame) < min_cross_section:
            continue
        raw_records.append((month, frame))

    if not raw_records:
        raise RuntimeError("No usable cross-sectional months")

    # --- Coverage, computed BEFORE any imputation, on the raw candidate/single availability ---
    print(f"Usable cross-sectional months: {len(raw_records)}  ({raw_records[0][0]} to {raw_records[-1][0]})")
    sizes = [len(f) for _, f in raw_records]
    print(f"Median cross-section size: {int(np.median(sizes))}\n")

    print("########## Coverage: % of universe with a real (non-null) Growth score ##########\n")
    single_cov = np.mean([f["growth_single"].notna().mean() for _, f in raw_records])
    equal_cov = np.mean([(f["n_candidates_available"] >= 1).mean() for _, f in raw_records])
    print(f"{'variant':16s} {'mean_coverage':>14s}")
    print(f"{'SINGLE (rev1y)':16s} {single_cov * 100:13.1f}%")
    print(f"{'EQUAL (>=1 of 5)':16s} {equal_cov * 100:13.1f}%")
    avail_dist = pd.concat([f["n_candidates_available"] for _, f in raw_records])
    print("\nDistribution of # candidates available per symbol-month (of 5):")
    print(avail_dist.value_counts(normalize=True).sort_index().mul(100).round(1).to_string())
    print()

    # --- Compute WEIGHTED variant using full-sample isolated univariate |t-stats| as weights ---
    full_frame_for_weights = [(m, f) for m, f in raw_records]
    raw_z_cols = [f"raw_{c}" for c in CANDIDATE_COLS]
    uni_ts: dict[str, float] = {}
    for col, raw_col in zip(CANDIDATE_COLS, raw_z_cols, strict=True):
        tmp_records = []
        for m, f in full_frame_for_weights:
            sub = f[[raw_col, "fwd_ret"]].dropna()
            if len(sub) < min_cross_section:
                continue
            sub = sub.rename(columns={raw_col: col})
            tmp_records.append((m, sub))
        if len(tmp_records) < 2:
            uni_ts[col] = 0.0
            continue
        _mean, t = _fama_macbeth(tmp_records, [col])[col]
        uni_ts[col] = abs(t) if not np.isnan(t) else 0.0
    print("########## Isolated univariate |t-stat| used as WEIGHTED-variant weights ##########\n")
    for col, t in uni_ts.items():
        print(f"  {col:26s} |t|={t:.2f}")
    weight_sum = sum(uni_ts.values())
    weighted_weights = {
        c: (uni_ts[c] / weight_sum if weight_sum > 0 else 1.0 / len(CANDIDATE_COLS)) for c in CANDIDATE_COLS
    }
    print()

    records: list[tuple[pd.Timestamp, pd.DataFrame]] = []
    for m, f in raw_records:
        z = f[raw_z_cols].rename(columns=dict(zip(raw_z_cols, CANDIDATE_COLS, strict=True)))
        f = f.copy()
        f["growth_weighted"] = _renormalized_blend(z, weighted_weights)
        for col in [*VARIANT_COLS, *CONTROL_COLS]:
            f[col] = _zwinsor(f[col]).fillna(0.0)
        records.append((m, f))

    split_idx = len(records) // 2
    halves = {"FULL": records, "ERA1": records[:split_idx], "ERA2": records[split_idx:]}

    print(
        "########## Multivariate Fama-MacBeth (each Growth variant + value/quality/stability/momentum/size controls) ##########\n"
    )
    print(f"{'variant':16s} {'era':6s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
    for variant in VARIANT_COLS:
        for era_label, era_records in halves.items():
            if not era_records:
                continue
            mean, t = _fama_macbeth(era_records, [variant, *CONTROL_COLS])[variant]
            print(f"{variant:16s} {era_label:6s} {mean:10.5f} {t:8.2f} {len(era_records):9d}")
        print()

    print("########## Univariate Fama-MacBeth (each Growth variant alone) ##########\n")
    print(f"{'variant':16s} {'era':6s} {'mean_coef':>10s} {'t_stat':>8s}")
    for variant in VARIANT_COLS:
        for era_label, era_records in halves.items():
            if not era_records:
                continue
            mean, t = _fama_macbeth(era_records, [variant])[variant]
            print(f"{variant:16s} {era_label:6s} {mean:10.5f} {t:8.2f}")
        print()

    def _ic_mean_t(ics: "np.ndarray[Any, Any]") -> tuple[float, float, int]:
        if len(ics) < 2:
            return (float("nan"), float("nan"), len(ics))
        se = ics.std(ddof=1) / np.sqrt(len(ics))
        t = ics.mean() / se if se > 0 else float("nan")
        return (ics.mean(), t, len(ics))

    def _spearman_ic_series(recs: list[tuple[pd.Timestamp, pd.DataFrame]], col: str) -> "np.ndarray[Any, Any]":
        ics = []
        for _m, f in recs:
            if len(f) < MIN_SECTOR_SLICE:
                continue
            ic = f[col].corr(f["fwd_ret"], method="spearman")
            if ic is not None and not np.isnan(ic):
                ics.append(ic)
        return np.array(ics)

    print("########## Stability check: per-half-era IC swing (mean IC, era1 vs era2) ##########\n")
    print(f"{'variant':16s} {'era1_ic':>9s} {'era2_ic':>9s} {'abs_swing':>10s}")
    for variant in VARIANT_COLS:
        ic1 = _spearman_ic_series(halves["ERA1"], variant)
        ic2 = _spearman_ic_series(halves["ERA2"], variant)
        m1, _t1, _n1 = _ic_mean_t(ic1)
        m2, _t2, _n2 = _ic_mean_t(ic2)
        print(f"{variant:16s} {m1:9.4f} {m2:9.4f} {abs(m1 - m2):10.4f}")
    print()

    print("########## Spearman IC, sliced to Financial Services / Real Estate only ##########\n")
    print(f"{'variant':16s} {'sector':20s} {'mean_ic':>9s} {'t_stat':>8s} {'n_months':>9s}")
    for variant in VARIANT_COLS:
        for focus in FOCUS_SECTORS:
            sliced = [(m, f[f["sector"] == focus]) for m, f in records]
            ics = _spearman_ic_series(sliced, variant)
            mean_ic, t, n = _ic_mean_t(ics)
            print(f"{variant:16s} {focus:20s} {mean_ic:9.4f} {t:8.2f} {n:9d}")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start-date", default="2015-06-01")
    parser.add_argument("--end-date", default=datetime.now(tz=None).date().isoformat())
    parser.add_argument("--min-cross-section", type=int, default=100)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.start_date, args.end_date, args.min_cross_section)


if __name__ == "__main__":
    main()
