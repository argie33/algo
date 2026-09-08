#!/usr/bin/env python3
"""
Value pillar percentile-RANK winsorization test.

Built 2026-09-07 (direct follow-up to the scoring-methodology audit, see
loaders/stock_scores/value_metrics.py:404-412's "NOTE (separate, NOT fixed by this pass)").

MOTIVATING FINDING: `_percent_rank_cheap_high`/`_percent_rank_cheap_high_sector_relative` (the
LIVE, shipped mechanism for PE/PB/PS/Forward-PE, sector-relative since 2026-09-04) rank the raw
ratio with NO winsorization first - the single cheapest raw P/E, P/B or P/S in the sector always
wins percentile 100 alone, even when that extremeness is a data/accounting artifact rather than
genuine mispricing (live-confirmed: VCIG pb_ratio=0.01/ps_ratio=0.02 wins 100/99.8 outright).

KEY SUBTLETY this test exists to check: this is percentile RANK, not z-score. Winsorizing the
raw ratio before a pure rank-order transform does NOT change relative order AT ALL except where
clipping pulls multiple distinct extreme values down to the SAME boundary, causing them to TIE
(the live rank function already does RANK()-style tie-sharing). So winsorizing-before-ranking's
only possible effect is: instead of one arbitrary "most extreme" symbol monopolizing percentile
100, a cluster of near-tied genuinely-cheap peers now SHARE the top percentile equally. This
script tests whether that specific change helps, hurts, or is neutral for forward-return
predictiveness - reusing this repo's own established methodology bar exactly (Fama-MacBeth
two-pass + Spearman IC, sector_relative_scoring_test_20260828.py's panel construction) rather
than a z-score proxy for it (that script's own value_uni/value_sector variants already zwinsor,
which is a DIFFERENT construction than what's actually live).

GOVERNANCE: fit era 2017-2021 decides, holdout era 2022-2026 (never touched while iterating)
confirms - same discipline as barra_style_neutralized_composite_20260907.py. Winsorization
bound fixed at [1st, 99th] percentile BEFORE running either era (matching `_zwinsor`'s own
convention elsewhere in this codebase, not tuned against this test's own results).

Usage:
    python -m algo.research.value_percentile_rank_winsorization_test_20260907 [options]
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
from algo.research.growth_reinvestment_book_value_candidates import build_panel as build_book_value_panel
from algo.research.growth_reinvestment_book_value_candidates import fetch_panel_raw as fetch_book_value_fundamentals
from algo.research.sector_relative_scoring_test_20260828 import UNCLASSIFIED, fetch_sector_map

logger = logging.getLogger(__name__)

VALUE_VARIANT_COLS = ["value_rank_raw", "value_rank_winsorized"]
CONTROL_COLS = ["growth_proxy", "quality_proxy", "stability_proxy", "momentum_proxy", "size_proxy"]
FOCUS_SECTORS = ["Financial Services", "Real Estate"]
MIN_SECTOR_SLICE = 10  # minimum rows in a sector-only monthly slice to trust its Spearman IC
_MIN_RANK_SECTOR_SLICE = 20  # matches live _percent_rank_cheap_high_sector_relative._MIN_SECTOR_SLICE


def _rank_cheap_high(values: pd.Series) -> pd.Series:
    """Byte-for-byte behavioral match of value_metrics.py's `_percent_rank_cheap_high`: lowest
    raw value -> highest percentile [0, 100], RANK()-style ties share the same percentile.
    Operates on non-null entries of `values` only; returns a Series indexed the same way."""
    values = values.dropna()
    n = len(values)
    if n == 0:
        return pd.Series(dtype=float)
    if n == 1:
        return pd.Series(50.0, index=values.index)
    order = values.sort_values()
    ranks = order.rank(method="min", ascending=True)  # 1 = cheapest
    pct = 100.0 * (n - ranks) / (n - 1)
    return pct.reindex(values.index)


def _rank_cheap_high_sector_relative(values: pd.Series, sectors: pd.Series) -> pd.Series:
    """Byte-for-byte behavioral match of `_percent_rank_cheap_high_sector_relative`: rank within
    sector only; sectors with <_MIN_RANK_SECTOR_SLICE members (among non-null `values`), or no
    sector at all, pool into one residual group ranked universe-wide instead."""
    values = values.dropna()
    aligned_sectors = sectors.reindex(values.index)
    result = pd.Series(np.nan, index=values.index)
    residual_idx = []
    for sector, idx in (
        aligned_sectors.fillna(UNCLASSIFIED).groupby(aligned_sectors.fillna(UNCLASSIFIED)).groups.items()
    ):
        if sector == UNCLASSIFIED or len(idx) < _MIN_RANK_SECTOR_SLICE:
            residual_idx.extend(idx)
            continue
        result.loc[idx] = _rank_cheap_high(values.loc[idx])
    if residual_idx:
        result.loc[residual_idx] = _rank_cheap_high(values.loc[residual_idx])
    return result


def _winsorize_cross_section(values: pd.Series, sectors: pd.Series) -> pd.Series:
    """[1st, 99th] percentile clip, computed WITHIN each sector group (matching the same
    grouping the rank function itself uses), matching `_zwinsor`'s bound convention elsewhere in
    this codebase - fixed a priori, not tuned against this test's own results."""
    values = values.dropna()
    aligned_sectors = sectors.reindex(values.index).fillna(UNCLASSIFIED)
    out = values.copy()
    for _sector, idx in aligned_sectors.groupby(aligned_sectors).groups.items():
        sub = values.loc[idx]
        if len(sub) < 5:
            continue
        lo, hi = sub.quantile([0.01, 0.99])
        out.loc[idx] = sub.clip(lo, hi)
    return out


def _value_rank_variant(pe: pd.Series, pb: pd.Series, ps: pd.Series, sectors: pd.Series, winsorize: bool) -> pd.Series:
    """Equal-weighted (1/3 each, matching live _score_value) sector-relative percentile rank of
    PE/PB/PS - raw (current-live) or pre-rank-winsorized, per `winsorize`. A symbol missing some
    of the 3 metrics is still scored on whatever's available (average of available components),
    matching live's own partial-availability normalization."""
    parts = []
    for raw in (pe, pb, ps):
        s = raw.copy()
        if winsorize:
            s = _winsorize_cross_section(s, sectors)
        parts.append(_rank_cheap_high_sector_relative(s, sectors))
    stacked = pd.concat(parts, axis=1)
    return stacked.mean(axis=1, skipna=True)


def _spearman_ic_series(records: list[tuple[pd.Timestamp, pd.DataFrame]], col: str) -> np.ndarray[Any, Any]:
    ics = []
    for _month, frame in records:
        if len(frame) < MIN_SECTOR_SLICE:
            continue
        ic = frame[col].corr(frame["fwd_ret"], method="spearman")
        if ic is not None and not np.isnan(ic):
            ics.append(ic)
    return np.array(ics)


def _ic_mean_t(ics: np.ndarray[Any, Any]) -> tuple[float, float, int]:
    if len(ics) < 2:
        return (float("nan"), float("nan"), len(ics))
    se = ics.std(ddof=1) / np.sqrt(len(ics))
    t = ics.mean() / se if se > 0 else float("nan")
    return (ics.mean(), t, len(ics))


def run(start_date: str, end_date: str, min_cross_section: int) -> None:  # noqa: C901 -- research script, not production
    logger.info("Fetching sector map (company_profile)")
    sector_map = fetch_sector_map()

    logger.info("Building fundamentals panels (growth/value/quality)")
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
        months, value_fund, cols=["eps", "book_value_per_share", "sales_per_share", "shares_diluted"]
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
        ],
    )

    beta_window = 24
    vol_window = 12
    records: list[tuple[pd.Timestamp, pd.DataFrame]] = []

    for i in range(beta_window, len(months) - 1):
        month = months[i]
        g = growth_monthly.get(month)
        v = value_monthly.get(month)
        q = quality_monthly.get(month)
        if g is None or v is None or q is None or g.empty or v.empty or q.empty:
            continue

        growth_proxy = -_zwinsor(g["book_value_growth"])

        price = px.iloc[i].reindex(v.index)
        pe = pd.Series(np.where(v["eps"] > 0, price / v["eps"], np.nan), index=v.index)
        pb = pd.Series(
            np.where(v["book_value_per_share"] > 0, price / v["book_value_per_share"], np.nan), index=v.index
        )
        ps = pd.Series(np.where(v["sales_per_share"] > 0, price / v["sales_per_share"], np.nan), index=v.index)

        sectors_here = sector_map.reindex(v.index)

        value_rank_raw = _value_rank_variant(pe, pb, ps, sectors_here, winsorize=False)
        value_rank_winsorized = _value_rank_variant(pe, pb, ps, sectors_here, winsorize=True)

        quality_proxy = (
            (11.0 / 101.0) * _zwinsor(q["roe"])
            + (18.0 / 101.0) * _zwinsor(q["roa"])
            + (18.0 / 101.0) * _zwinsor(q["roce"])
            + (15.0 / 101.0) * _zwinsor(q["fcf_margin"])
            + (18.0 / 101.0) * _zwinsor(-q["debt_to_equity"])
            + (7.0 / 101.0) * _zwinsor(-q["margin_volatility_3y"])
            + (7.0 / 101.0) * _zwinsor(q["asset_turnover"])
            + (7.0 / 101.0) * _zwinsor(q["gross_profitability"])
        )

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
                "value_rank_raw": value_rank_raw,
                "value_rank_winsorized": value_rank_winsorized,
                "growth_proxy": growth_proxy,
                "quality_proxy": quality_proxy,
                "stability_proxy": stability_proxy,
                "momentum_proxy": momentum_proxy,
                "size_proxy": size_proxy,
                "fwd_ret": fwd_ret,
            }
        )
        raw["sector"] = sectors_here.reindex(raw.index).fillna(UNCLASSIFIED)
        raw = raw.replace([np.inf, -np.inf], np.nan)
        raw = raw.dropna(subset=["fwd_ret"])
        raw = raw[(raw["fwd_ret"] > -0.95) & (raw["fwd_ret"] < 5.0)]
        if len(raw) < min_cross_section:
            continue

        frame = raw.copy()
        # value_rank_* are already on a native [0,100] percentile scale - z-score them the same
        # way the template script z-scores its own value_uni/value_sector for FM comparability,
        # but leave them un-winsorized a second time (already winsorized upstream where relevant).
        for col in VALUE_VARIANT_COLS:
            s = frame[col].replace([np.inf, -np.inf], np.nan)
            std = s.std()
            frame[col] = ((s - s.mean()) / std if std and std > 0 else s * 0.0).fillna(0.0)
        for col in CONTROL_COLS:
            frame[col] = _zwinsor(frame[col]).fillna(0.0)
        records.append((month, frame))

    if not records:
        raise RuntimeError("No usable cross-sectional months")

    sizes = [len(f) for _, f in records]
    print(f"Usable cross-sectional months: {len(records)}  ({records[0][0]} to {records[-1][0]})")
    print(f"Median cross-section size: {int(np.median(sizes))}")
    print()

    split_idx = len(records) // 2
    fit_records = records[:split_idx]
    holdout_records = records[split_idx:]
    print(f"FIT era: {fit_records[0][0]} to {fit_records[-1][0]}  ({len(fit_records)} months)")
    print(f"HOLDOUT era: {holdout_records[0][0]} to {holdout_records[-1][0]}  ({len(holdout_records)} months)")
    halves = {"FULL": records, "FIT": fit_records, "HOLDOUT": holdout_records}

    print("\n########## Value PE/PB/PS percentile-RANK: raw vs pre-rank-winsorized ##########\n")
    print("=== Multivariate Fama-MacBeth (each variant + 5 pillar controls), by era ===")
    print(f"{'variant':22s} {'era':8s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
    for variant in VALUE_VARIANT_COLS:
        for era_label, era_records in halves.items():
            if not era_records:
                continue
            result = _fama_macbeth(era_records, [variant, *CONTROL_COLS])
            mean, t = result[variant]
            print(f"{variant:22s} {era_label:8s} {mean:10.5f} {t:8.2f} {len(era_records):9d}")
        print()

    print("=== Univariate Fama-MacBeth (each variant alone), by era ===")
    print(f"{'variant':22s} {'era':8s} {'mean_coef':>10s} {'t_stat':>8s}")
    for variant in VALUE_VARIANT_COLS:
        for era_label, era_records in halves.items():
            if not era_records:
                continue
            mean, t = _fama_macbeth(era_records, [variant])[variant]
            print(f"{variant:22s} {era_label:8s} {mean:10.5f} {t:8.2f}")
        print()

    print("=== Spearman IC, full universe + focus sectors, by variant/era ===")
    print(f"{'variant':22s} {'slice':20s} {'era':8s} {'mean_ic':>9s} {'t_stat':>8s} {'n_months':>9s}")
    for variant in VALUE_VARIANT_COLS:
        for era_label, era_records in halves.items():
            if not era_records:
                continue
            ics = _spearman_ic_series(era_records, variant)
            mean_ic, t, n = _ic_mean_t(ics)
            print(f"{variant:22s} {'ALL':20s} {era_label:8s} {mean_ic:9.4f} {t:8.2f} {n:9d}")
        for focus in FOCUS_SECTORS:
            for era_label, era_records in halves.items():
                if not era_records:
                    continue
                sliced = [(m, f[f["sector"] == focus]) for m, f in era_records]
                ics = _spearman_ic_series(sliced, variant)
                mean_ic, t, n = _ic_mean_t(ics)
                print(f"{variant:22s} {focus:20s} {era_label:8s} {mean_ic:9.4f} {t:8.2f} {n:9d}")
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
