#!/usr/bin/env python3
"""
Quality formula comparison: current live 8-component composite vs. industry-leader-style
simplified constructions (MSCI Quality Index's 3-variable formula, S&P Quality Index's
3-variable formula, and an AQR QMJ-lite profitability+safety blend).

Built 2026-08-28 (goal session: user's "it is bloated right now, we need to see what the
industry best is and do like that" - direct follow-up to researching MSCI/S&P/FTSE
Russell/AQR QMJ methodology this same session). Read-only research script - does NOT touch
loaders/load_stock_scores.py or loaders/load_value_quality_growth_metrics.py (Growth/Value
are being edited in parallel elsewhere this session; this script is fully additive).

Variants tested, each a z-scored, equal/weighted average of its own inputs (winsorized 1st/99th
pctile, mean/std z-score, same _zwinsor convention as every other script in this directory):

- CURRENT: the live 8-component weighted composite exactly as shipped in
  loaders/load_value_quality_growth_metrics.py (roe 11 + roa 18 + roce 18 + fcf_margin 15 +
  debt_to_equity(inverted) 18 + margin_volatility_3y(inverted) 7 + asset_turnover 7 +
  gross_profitability 7, /101).

- MSCI_3: ROE, -Debt-to-Equity, -Earnings Variability (equal-weighted z-score average, per
  MSCI Quality Indexes Methodology - https://www.msci.com/eqb/methodology/meth_docs/
  MSCI_Quality_Indexes_Meth_June2017.pdf). "Earnings Variability" there is stdev of YoY EPS
  growth over 5 years; this pipeline's closest real proxy is `eps_growth_stability` (stdev of
  trailing-4-quarter QoQ EPS growth, from growth_quarterly_earnings_quality_candidates.py) -
  quarterly not annual, a real construction difference from MSCI's own definition, noted not
  hidden.

- SP_3: ROE, -Debt-to-Equity (proxy for S&P's Financial Leverage Ratio = total debt/book
  value - same numerator/denominator shape as this repo's debt_to_equity), -Accruals Ratio
  (per S&P Quality Indices Methodology - https://www.spglobal.com/spdji/en/documents/
  methodologies/methodology-sp-quality-indices.pdf - S&P's own accruals ratio is a
  balance-sheet NOA-change construction; this pipeline only has the Sloan cash-flow-based
  accruals_ratio = (NI-OCF)/Assets, a related but not identical construction, noted not
  hidden).

- QMJ_LITE: AQR Quality-Minus-Junk-style profitability+safety blend (no growth/payout legs -
  this pipeline lacks clean 5yr-growth-of-profitability and net-issuance data at the quality
  needed) - 50/50 average of a profitability cluster (ROE, ROA, Gross Profitability, FCF
  Margin - all z-scored then averaged) and a safety cluster (-Debt-to-Equity, -Margin
  Volatility 3Y - z-scored then averaged), per Asness/Frazzini/Pedersen 2013 "Quality Minus
  Junk" (http://www.econ.yale.edu/~shiller/behfin/2013_04-10/asness-frazzini-pedersen.pdf).

Tested exactly like every other formula-comparison script in this directory: multivariate
Fama-MacBeth (variant + 5 other pillar controls, reusing fama_macbeth_composite_weights.py's
proxy machinery), univariate Fama-MacBeth, and Spearman IC sliced to Financial Services /
Real Estate / everyone else (per sector_relative_scoring_test_20260828.py's sector map and
methodology) - full sample + half-split era robustness throughout, this repo's standard bar.

Usage:
    python -m algo.research.quality_industry_leader_formula_comparison_20260828 [options]
"""

import argparse
import logging
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_composite_weights import _zwinsor, build_value_panel_raw
from algo.research.fama_macbeth_growth_factors import merge_asof_monthly
from algo.research.fama_macbeth_momentum_factors import build_month_end_panel, compute_daily_indicators
from algo.research.fama_macbeth_momentum_factors import fetch_daily_prices as fetch_daily_close
from algo.research.fama_macbeth_price_factors import _fama_macbeth, fetch_month_end_prices
from algo.research.fama_macbeth_quality_factors import build_quality_panel, fetch_annual_quality_fundamentals
from algo.research.growth_quarterly_earnings_quality_candidates import build_panel as build_quarterly_panel
from algo.research.growth_quarterly_earnings_quality_candidates import fetch_quarterly_panel
from algo.research.growth_reinvestment_book_value_candidates import build_panel as build_book_value_panel
from algo.research.growth_reinvestment_book_value_candidates import fetch_panel_raw as fetch_book_value_fundamentals
from algo.research.sector_relative_scoring_test_20260828 import UNCLASSIFIED, fetch_sector_map

logger = logging.getLogger(__name__)

QUALITY_VARIANT_COLS = [
    "q_current",
    "q_equal8",
    "q_msci3",
    "q_sp3",
    "q_qmj_lite",
    "q_qmj_full8",
    "q_qmj_drop_roce_only",
    "q_qmj_drop_at_only",
]
CONTROL_COLS = ["growth_proxy", "value_proxy", "stability_proxy", "momentum_proxy", "size_proxy"]
FOCUS_SECTORS = ["Financial Services", "Real Estate"]
MIN_SECTOR_SLICE = 10


def _renorm_weighted_avg(components: list[tuple[pd.Series, float]], min_weight_frac: float = 0.0) -> pd.Series:
    """Row-wise renormalized weighted average, matching loaders/load_value_quality_growth_metrics.py's
    live `_weighted_avg` semantics exactly - NOT a naive weighted sum. A naive
    `sum(w_i * zwinsor(x_i))` NaNs out an entire row the instant ANY single input is missing
    (NaN propagates through addition), which a later blanket `.fillna(0.0)` then silently scores
    as "exactly average quality" - discarding every other real input that WAS available for that
    row. This is the bug this function fixes: skip missing components per-row, renormalize the
    weighted average over whichever inputs ARE present, and only return NaN when the available
    weight fraction is below `min_weight_frac` (mirroring the live formula's 40/101 completeness
    floor) - not whenever a single input is missing. Critical for Financial Services (only 15.5%
    gross_profitability coverage) / Real Estate (34.9%) specifically: under the naive-sum
    construction, ~85%/~65% of those sectors' rows would get artificially zeroed to "average"
    every single month, which would mechanically crush any sector's measured Spearman IC/FM
    t-stat regardless of whether the underlying formula actually carries real signal there."""
    total_nominal = sum(w for _, w in components)
    idx = components[0][0].index
    weighted_sum = pd.Series(0.0, index=idx)
    weight_avail = pd.Series(0.0, index=idx)
    for s, w in components:
        mask = s.notna()
        weighted_sum = weighted_sum + s.where(mask, 0.0) * w
        weight_avail = weight_avail + mask.astype(float) * w
    result = weighted_sum / weight_avail.replace(0.0, np.nan)
    return result.where(weight_avail >= min_weight_frac * total_nominal)


def _fm_variant(
    records: list[tuple[pd.Timestamp, pd.DataFrame]], variant: str, controls: list[str]
) -> tuple[dict[str, tuple[float, float]], int]:
    """_fama_macbeth wrapper that drops rows where `variant` is NaN per month BEFORE regressing -
    np.linalg.lstsq silently returns garbage on a NaN-containing design matrix, so this is
    required now that quality variant columns carry real (not zero-imputed) NaN for
    insufficient-data rows. Controls are assumed already NaN-free (fillna'd upstream). Returns
    (result, n_months_actually_used) - the latter can be lower than len(records) since a month
    can drop below MIN_SECTOR_SLICE once NaN rows for this specific variant are removed."""
    filtered = [(m, f[f[variant].notna()]) for m, f in records]
    filtered = [(m, f) for m, f in filtered if len(f) >= MIN_SECTOR_SLICE]
    return _fama_macbeth(filtered, [variant, *controls]), len(filtered)


def _spearman_ic_series(
    records: list[tuple[pd.Timestamp, pd.DataFrame]], col: str
) -> tuple[np.ndarray[Any, np.dtype[np.float64]], list[int]]:
    ics, ns = [], []
    for _month, frame in records:
        if len(frame) < MIN_SECTOR_SLICE:
            continue
        ic = frame[col].corr(frame["fwd_ret"], method="spearman")
        if ic is not None and not np.isnan(ic):
            ics.append(ic)
            ns.append(len(frame))
    return np.array(ics), ns


def _ic_mean_t(ics: np.ndarray[Any, np.dtype[np.float64]]) -> tuple[float, float, int]:
    if len(ics) < 2:
        return (float("nan"), float("nan"), len(ics))
    se = ics.std(ddof=1) / np.sqrt(len(ics))
    t = ics.mean() / se if se > 0 else float("nan")
    return (ics.mean(), t, len(ics))


def run(start_date: str, end_date: str, min_cross_section: int) -> None:
    logger.info("Fetching sector map + fundamentals panels")
    sector_map = fetch_sector_map()

    growth_fund = build_book_value_panel(fetch_book_value_fundamentals())
    value_fund = build_value_panel_raw()
    quality_raw = fetch_annual_quality_fundamentals()
    quality_fund = build_quality_panel(quality_raw)
    quality_fund = quality_fund.merge(
        quality_raw[["symbol", "fiscal_year", "revenue", "total_assets"]], on=["symbol", "fiscal_year"], how="left"
    )
    quality_fund["asset_turnover"] = np.where(
        quality_fund["total_assets"] > 0, quality_fund["revenue"] / quality_fund["total_assets"], np.nan
    )

    quarterly_fund = build_quarterly_panel(fetch_quarterly_panel())

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

    growth_monthly = merge_asof_monthly(months, growth_fund, cols=["book_value_growth"])
    value_monthly = merge_asof_monthly(
        months, value_fund, cols=["eps", "book_value_per_share", "sales_per_share", "fcf_per_share", "shares_diluted"]
    )
    quality_monthly = merge_asof_monthly(
        months,
        quality_fund,
        cols=[
            "roe",
            "roa",
            "roce",
            "fcf_margin",
            "debt_to_equity",
            "margin_volatility_3y",
            "asset_turnover",
            "gross_profitability",
            "accruals_ratio",
        ],
    )
    quarterly_monthly = merge_asof_monthly(months, quarterly_fund, cols=["eps_growth_stability"])

    beta_window = 24
    vol_window = 12
    records: list[tuple[pd.Timestamp, pd.DataFrame]] = []

    for i in range(beta_window, len(months) - 1):
        month = months[i]
        g = growth_monthly.get(month)
        v = value_monthly.get(month)
        q = quality_monthly.get(month)
        eqs = quarterly_monthly.get(month)
        if g is None or v is None or q is None or g.empty or v.empty or q.empty:
            continue

        growth_proxy = -_zwinsor(g["book_value_growth"])

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

        sectors_here = sector_map.reindex(v.index).fillna(UNCLASSIFIED)

        eps_gs = (
            eqs["eps_growth_stability"].reindex(q.index)
            if eqs is not None and not eqs.empty
            else pd.Series(np.nan, index=q.index)
        )

        # CURRENT: live 8-component formula, PROPERLY renormalized over available inputs
        # (matches loaders/load_value_quality_growth_metrics.py's `_weighted_avg` + 40/101
        # completeness floor exactly) - NOT a naive weighted sum. See _renorm_weighted_avg's
        # own docstring for why the distinction matters, especially for FS/RE.
        q_current = _renorm_weighted_avg(
            [
                (_zwinsor(q["roe"]), 11.0),
                (_zwinsor(q["roa"]), 18.0),
                (_zwinsor(q["roce"]), 18.0),
                (_zwinsor(q["fcf_margin"]), 15.0),
                (_zwinsor(-q["debt_to_equity"]), 18.0),
                (_zwinsor(-q["margin_volatility_3y"]), 7.0),
                (_zwinsor(q["asset_turnover"]), 7.0),
                (_zwinsor(q["gross_profitability"]), 7.0),
            ],
            min_weight_frac=40.0 / 101.0,
        )

        # EQUAL_8: the same 8 inputs as CURRENT, but equal-weighted instead of magnitude-tiered
        # (11/18/18/15/18/7/7/7) - MSCI/S&P/AQR all equal-weight their z-scores, none use
        # hand-calibrated t-stat-tier weights. Tests whether CURRENT's tiering is actually
        # earning its extra complexity over the industry-standard equal-weight convention,
        # holding the INPUT SET identical so this isolates the weighting scheme specifically.
        q_equal8 = _renorm_weighted_avg(
            [
                (_zwinsor(q["roe"]), 1.0),
                (_zwinsor(q["roa"]), 1.0),
                (_zwinsor(q["roce"]), 1.0),
                (_zwinsor(q["fcf_margin"]), 1.0),
                (_zwinsor(-q["debt_to_equity"]), 1.0),
                (_zwinsor(-q["margin_volatility_3y"]), 1.0),
                (_zwinsor(q["asset_turnover"]), 1.0),
                (_zwinsor(q["gross_profitability"]), 1.0),
            ],
            min_weight_frac=40.0 / 101.0,
        )

        # MSCI_3: ROE, -Debt-to-Equity, -Earnings Variability - renormalized over whichever of
        # the 3 are available (no floor - any 1 of 3 present is enough to score, same
        # "score what's available" convention as this repo's own Growth pillar).
        q_msci3 = _renorm_weighted_avg(
            [(_zwinsor(q["roe"]), 1.0), (_zwinsor(-q["debt_to_equity"]), 1.0), (_zwinsor(-eps_gs), 1.0)]
        )

        # SP_3: ROE, -Debt-to-Equity (leverage proxy), -Accruals Ratio - renormalized.
        q_sp3 = _renorm_weighted_avg(
            [(_zwinsor(q["roe"]), 1.0), (_zwinsor(-q["debt_to_equity"]), 1.0), (_zwinsor(-q["accruals_ratio"]), 1.0)]
        )

        # QMJ_LITE: 50/50 profitability cluster (ROE/ROA/GP/FCF margin) + safety cluster
        # (-D/E, -margin vol), each cluster itself renormalized over its own available inputs,
        # then the two cluster scores combined (only when at least one cluster has data).
        profitability_cluster = _renorm_weighted_avg(
            [
                (_zwinsor(q["roe"]), 1.0),
                (_zwinsor(q["roa"]), 1.0),
                (_zwinsor(q["gross_profitability"]), 1.0),
                (_zwinsor(q["fcf_margin"]), 1.0),
            ]
        )
        safety_cluster = _renorm_weighted_avg(
            [(_zwinsor(-q["debt_to_equity"]), 1.0), (_zwinsor(-q["margin_volatility_3y"]), 1.0)]
        )
        q_qmj_lite = _renorm_weighted_avg([(profitability_cluster, 1.0), (safety_cluster, 1.0)])

        # QMJ_FULL8: same two-cluster QMJ structure as QMJ_LITE, but folds in the 2 inputs
        # QMJ_LITE left out (ROCE, Asset Turnover) so every current-8 input is represented -
        # isolates whether QMJ_LITE's edge over CURRENT/EQUAL_8 comes from its hierarchical
        # cluster structure (profitability cluster + safety cluster, THEN 50/50 blended) rather
        # than from simply dropping ROCE/Asset Turnover. ROCE joins the profitability cluster
        # (another return-on-capital measure); Asset Turnover joins it too (DuPont efficiency
        # leg, not a safety measure) rather than inventing a 3rd cluster with no clear analogue
        # in the QMJ paper.
        profitability_cluster_full = _renorm_weighted_avg(
            [
                (_zwinsor(q["roe"]), 1.0),
                (_zwinsor(q["roa"]), 1.0),
                (_zwinsor(q["roce"]), 1.0),
                (_zwinsor(q["gross_profitability"]), 1.0),
                (_zwinsor(q["fcf_margin"]), 1.0),
                (_zwinsor(q["asset_turnover"]), 1.0),
            ]
        )
        q_qmj_full8 = _renorm_weighted_avg([(profitability_cluster_full, 1.0), (safety_cluster, 1.0)])

        # Isolate which of ROCE/Asset Turnover actually drives QMJ_LITE's FS/RE edge over
        # QMJ_FULL8 - "nothing more or less" means we shouldn't drop both if only one is the
        # real culprit. Each keeps exactly one of the two, otherwise identical to QMJ_LITE.
        profitability_cluster_plus_roce = _renorm_weighted_avg(
            [
                (_zwinsor(q["roe"]), 1.0),
                (_zwinsor(q["roa"]), 1.0),
                (_zwinsor(q["roce"]), 1.0),
                (_zwinsor(q["gross_profitability"]), 1.0),
                (_zwinsor(q["fcf_margin"]), 1.0),
            ]
        )
        q_qmj_drop_roce_only = _renorm_weighted_avg(
            [(profitability_cluster_plus_roce, 1.0), (safety_cluster, 1.0)]
        )  # keeps ROCE, still drops Asset Turnover
        profitability_cluster_plus_at = _renorm_weighted_avg(
            [
                (_zwinsor(q["roe"]), 1.0),
                (_zwinsor(q["roa"]), 1.0),
                (_zwinsor(q["gross_profitability"]), 1.0),
                (_zwinsor(q["fcf_margin"]), 1.0),
                (_zwinsor(q["asset_turnover"]), 1.0),
            ]
        )
        q_qmj_drop_at_only = _renorm_weighted_avg(
            [(profitability_cluster_plus_at, 1.0), (safety_cluster, 1.0)]
        )  # keeps Asset Turnover, still drops ROCE

        market_cap = price * v["shares_diluted"]
        log_mc = np.where((market_cap >= 1e6) & (market_cap <= 1e13), np.log10(market_cap), np.nan)
        size_proxy = _zwinsor(-pd.Series(log_mc, index=v.index))

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

        raw = pd.DataFrame(
            {
                "q_current": q_current,
                "q_equal8": q_equal8,
                "q_msci3": q_msci3,
                "q_sp3": q_sp3,
                "q_qmj_lite": q_qmj_lite,
                "q_qmj_full8": q_qmj_full8,
                "q_qmj_drop_roce_only": q_qmj_drop_roce_only,
                "q_qmj_drop_at_only": q_qmj_drop_at_only,
                "growth_proxy": growth_proxy,
                "value_proxy": value_proxy,
                "stability_proxy": stability_proxy,
                "momentum_proxy": momentum_proxy,
                "size_proxy": size_proxy,
                "fwd_ret": fwd_ret,
            }
        )
        raw["sector"] = sectors_here.reindex(raw.index)
        raw = raw.replace([np.inf, -np.inf], np.nan)
        raw = raw.dropna(subset=["fwd_ret"])
        raw = raw[(raw["fwd_ret"] > -0.95) & (raw["fwd_ret"] < 5.0)]
        if len(raw) < min_cross_section:
            continue

        frame = raw.copy()
        for col in CONTROL_COLS:
            frame[col] = _zwinsor(frame[col]).fillna(0.0)
        for col in QUALITY_VARIANT_COLS:
            # Deliberately NOT fillna(0.0) here - these are already-renormalized composites
            # (via _renorm_weighted_avg) where remaining NaN means genuinely insufficient data
            # (below the completeness floor), not "average quality". Zero-imputing here would
            # reintroduce the exact bug _renorm_weighted_avg was built to fix. _fm_variant()
            # drops NaN rows per-variant before regressing; Spearman .corr() drops them natively.
            frame[col] = _zwinsor(frame[col])
        records.append((month, frame))

    if not records:
        raise RuntimeError("No usable cross-sectional months")

    sizes = [len(f) for _, f in records]
    print(f"Usable cross-sectional months: {len(records)}  ({records[0][0]} to {records[-1][0]})")
    print(f"Median cross-section size: {int(np.median(sizes))}")
    for focus in FOCUS_SECTORS:
        focus_sizes = [int((f["sector"] == focus).sum()) for _, f in records]
        print(
            f"  {focus}: median {int(np.median(focus_sizes))} symbols/month (min {min(focus_sizes)}, max {max(focus_sizes)})"
        )
    print()

    print("=== Coverage: % of each sector's monthly rows with a non-NaN variant score (post-renorm) ===")
    print(f"{'variant':12s} {'sector':20s} {'pct_covered':>11s}")
    for variant in QUALITY_VARIANT_COLS:
        for focus in [*FOCUS_SECTORS, "Everyone else"]:
            pct_list = []
            for _m, f in records:
                sub = f[f["sector"] == focus] if focus != "Everyone else" else f[~f["sector"].isin(FOCUS_SECTORS)]
                if len(sub) > 0:
                    pct_list.append(100.0 * sub[variant].notna().sum() / len(sub))
            avg_pct = np.mean(pct_list) if pct_list else float("nan")
            print(f"{variant:12s} {focus:20s} {avg_pct:10.1f}%")
        print()

    split_idx = len(records) // 2
    halves = {"FULL": records, "ERA1": records[:split_idx], "ERA2": records[split_idx:]}

    print("=== Multivariate Fama-MacBeth (each quality variant + 5 other-pillar controls), by era ===")
    print(f"{'variant':12s} {'era':6s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
    for variant in QUALITY_VARIANT_COLS:
        for era_label, era_records in halves.items():
            if not era_records:
                continue
            result, n_used = _fm_variant(era_records, variant, CONTROL_COLS)
            mean, t = result[variant]
            print(f"{variant:12s} {era_label:6s} {mean:10.5f} {t:8.2f} {n_used:9d}")
        print()

    print("=== Univariate Fama-MacBeth (each quality variant alone), by era ===")
    print(f"{'variant':12s} {'era':6s} {'mean_coef':>10s} {'t_stat':>8s}")
    for variant in QUALITY_VARIANT_COLS:
        for era_label, era_records in halves.items():
            if not era_records:
                continue
            result, _n_used = _fm_variant(era_records, variant, [])
            mean, t = result[variant]
            print(f"{variant:12s} {era_label:6s} {mean:10.5f} {t:8.2f}")
        print()

    print("=== Spearman IC, sliced to Financial Services / Real Estate / everyone else ===")
    print(f"{'variant':12s} {'sector':20s} {'mean_ic':>9s} {'t_stat':>8s} {'n_months':>9s}")
    for variant in QUALITY_VARIANT_COLS:
        for focus in [*FOCUS_SECTORS, "Everyone else"]:
            if focus == "Everyone else":
                sliced = [(m, f[~f["sector"].isin(FOCUS_SECTORS)]) for m, f in records]
            else:
                sliced = [(m, f[f["sector"] == focus]) for m, f in records]
            sliced = [(m, f) for m, f in sliced if len(f) >= MIN_SECTOR_SLICE]
            ics, _ns = _spearman_ic_series(sliced, variant)
            mean_ic, t, n = _ic_mean_t(ics)
            print(f"{variant:12s} {focus:20s} {mean_ic:9.4f} {t:8.2f} {n:9d}")
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
