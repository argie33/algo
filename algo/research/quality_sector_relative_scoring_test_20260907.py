#!/usr/bin/env python3
"""
Quality-pillar sector-relative scoring test.

Built 2026-09-07 (goal session: "companies we'd expect to be higher... are not" in cross-
sector Quality leaderboards - dig in and fix per finance best practice, don't guess).

MOTIVATING FINDING (live-checked this session): unlike Value - whose PE/PB/PS/Forward-PE were
proven sector-relative-beats-universe-wide and shipped 2026-09-04 (commit `40cfb1710`, see
memory sector_relative_scoring_investigated_never_shipped_20260904) - Quality's 8-component
blend (ROE/ROA/ROCE/FCF margin/Debt-to-Equity/Margin Volatility/Asset Turnover/Gross
Profitability, weights below from `get_live_quality_weights()`) is STILL ranked/scored on raw
absolute values, universe-wide, with only a different FORMULA VARIANT swapped in for Financial
Services/Real Estate (not a percentile-within-sector normalization). Live stock_scores query
this session: avg quality_score by sector ranges 32.3 (Healthcare, n=1,003, the largest sector -
dragged down by its structurally pre-revenue clinical-stage-biotech population) to 50.6
(Financial Services) - an 18-point spread, next to Value's much flatter 29.8-51.5 post-fix.
That's the same "persistent sector-level base-rate gap, not noise" pattern the 2026-08-28 Value
test found for PE/PB/PS, just never re-tested for Quality's components.

This is the DIRECT analogue of algo/research/sector_relative_scoring_test_20260828.py - same
data sources, same econometric machinery (Fama-MacBeth two-pass, Spearman IC, half-split era
robustness), same _zwinsor/_zwinsor_by_group helpers - just testing Quality's 8 components
sector-relative instead of Value's 3. Reused verbatim where possible rather than duplicated
logic drifting from the proven original.

REGIME: partial-availability only (0-imputed missing components after zwinsor, matching the
live composite's own tolerance), matching the original script's own documented simplification.

Usage:
    python -m algo.research.quality_sector_relative_scoring_test_20260907 [options]
"""

import argparse
import logging
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_composite_weights import PROXY_QUALITY_NUMERATORS, _zwinsor, build_value_panel_raw
from algo.research.fama_macbeth_growth_factors import merge_asof_monthly
from algo.research.fama_macbeth_momentum_factors import build_month_end_panel, compute_daily_indicators
from algo.research.fama_macbeth_momentum_factors import fetch_daily_prices as fetch_daily_close
from algo.research.fama_macbeth_price_factors import _fama_macbeth, fetch_month_end_prices
from algo.research.fama_macbeth_quality_factors import build_quality_panel, fetch_annual_quality_fundamentals
from algo.research.growth_reinvestment_book_value_candidates import build_panel as build_book_value_panel
from algo.research.growth_reinvestment_book_value_candidates import fetch_panel_raw as fetch_book_value_fundamentals
from algo.research.sector_relative_scoring_test_20260828 import UNCLASSIFIED, _zwinsor_by_group, fetch_sector_map

logger = logging.getLogger(__name__)

QUALITY_VARIANT_COLS = ["quality_uni", "quality_sector", "quality_blend"]
CONTROL_COLS = ["value_proxy", "growth_proxy", "stability_proxy", "momentum_proxy", "size_proxy"]
MIN_SECTOR_SLICE = 10
# Largest population sectors most likely to carry a real structural gap - Healthcare (huge,
# biotech-heavy per this session's live finding), Financial Services + Real Estate (already
# known to need special handling), Utilities (regulated-return ROE ceiling).
FOCUS_SECTORS = ["Healthcare", "Financial Services", "Real Estate", "Utilities"]

QUALITY_TOTAL_WEIGHT = sum(PROXY_QUALITY_NUMERATORS.values())


def _weighted_quality(components: dict[str, pd.Series], zwinsor_fn: Any) -> pd.Series:
    """Sum of PROXY_QUALITY_NUMERATORS-weighted zwinsored components. `debt_to_equity` is
    sign-flipped (lower leverage = better) matching the live formula's convention."""
    total = None
    for key, numerator in PROXY_QUALITY_NUMERATORS.items():
        series = components[key]
        if key == "debt_to_equity":
            series = -series
        term = (numerator / QUALITY_TOTAL_WEIGHT) * zwinsor_fn(series)
        total = term if total is None else total + term
    assert total is not None
    return total


def run(start_date: str, end_date: str, min_cross_section: int) -> None:  # noqa: C901 -- research script, not production
    logger.info("Fetching sector map (company_profile)")
    sector_map = fetch_sector_map()
    logger.info(f"{len(sector_map)} symbols mapped, {sector_map.value_counts().get(UNCLASSIFIED, 0)} unclassified")

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

        sectors_here = sector_map.reindex(v.index).fillna(UNCLASSIFIED)

        # Value control uses the SECTOR-relative variant - matches what's actually live today
        # (shipped 2026-09-04), not the pre-fix universe-wide behavior.
        value_proxy = (1.0 / 3.0) * (
            _zwinsor_by_group(-pe, sectors_here)
            + _zwinsor_by_group(-pb, sectors_here)
            + _zwinsor_by_group(-ps, sectors_here)
        )

        components = {
            "roe": q["roe"],
            "roa": q["roa"],
            "roce": q["roce"],
            "fcf_margin": q["fcf_margin"],
            "debt_to_equity": q["debt_to_equity"],
            "margin_volatility": q["margin_volatility_3y"],
            "asset_turnover": q["asset_turnover"],
            "gross_profitability": q["gross_profitability"],
        }
        sectors_q = sector_map.reindex(q.index).fillna(UNCLASSIFIED)

        # (a) UNIVERSE: current live behavior - every component zwinsored against the whole
        # cross-section.
        quality_uni = _weighted_quality(components, _zwinsor)

        # (b) SECTOR: identical weights, every component zwinsored WITHIN sector group instead.
        quality_sector = _weighted_quality(components, lambda s, sec=sectors_q: _zwinsor_by_group(s, sec))

        # (c) BLEND: simple average.
        quality_blend = 0.5 * (quality_uni + quality_sector)

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
                "quality_uni": quality_uni,
                "quality_sector": quality_sector,
                "quality_blend": quality_blend,
                "value_proxy": value_proxy,
                "growth_proxy": growth_proxy,
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

        numeric_cols = [*QUALITY_VARIANT_COLS, *CONTROL_COLS]
        frame = raw.copy()
        for col in numeric_cols:
            frame[col] = _zwinsor(frame[col]).fillna(0.0)
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

    split_idx = len(records) // 2
    halves = {"FULL": records, "ERA1": records[:split_idx], "ERA2": records[split_idx:]}

    print("########## Quality pillar components - universe-wide vs sector-relative ranking ##########\n")
    print("=== Multivariate Fama-MacBeth (each quality variant + 5 pillar controls), by era ===")
    print(f"{'variant':16s} {'era':6s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
    for variant in QUALITY_VARIANT_COLS:
        for era_label, era_records in halves.items():
            if not era_records:
                continue
            result = _fama_macbeth(era_records, [variant, *CONTROL_COLS])
            mean, t = result[variant]
            print(f"{variant:16s} {era_label:6s} {mean:10.5f} {t:8.2f} {len(era_records):9d}")
        print()

    print("=== Univariate Fama-MacBeth (each quality variant alone), by era ===")
    print(f"{'variant':16s} {'era':6s} {'mean_coef':>10s} {'t_stat':>8s}")
    for variant in QUALITY_VARIANT_COLS:
        for era_label, era_records in halves.items():
            if not era_records:
                continue
            mean, t = _fama_macbeth(era_records, [variant])[variant]
            print(f"{variant:16s} {era_label:6s} {mean:10.5f} {t:8.2f}")
        print()

    print("=== Spearman IC, sliced per focus sector, by variant ===")
    print(f"{'variant':16s} {'sector':20s} {'mean_ic':>9s} {'t_stat':>8s} {'n_months':>9s}")

    def _spearman_ic_series(records_in: list[tuple[pd.Timestamp, pd.DataFrame]], col: str) -> np.ndarray[Any, Any]:
        ics = []
        for _month, frame in records_in:
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

    for variant in QUALITY_VARIANT_COLS:
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
