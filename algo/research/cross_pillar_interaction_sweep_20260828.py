#!/usr/bin/env python3
"""
Cross-pillar interaction sweep: all 15 pairs among the 6 stock_scores pillars.

Built 2026-08-28 (goal: user's standing directive to "understand all the relationships between
all the inputs across all the factors in all the ways they all interact" before deciding whether
weighting is even the right lever). Two pairs were already tested in isolation this session
(momentum_risk_interaction_effects_20260828.py: mom_12_1 x vol_60d and mom_12_1 x str_1m, both
raw-input-level, both null on era-robustness) - this script covers the remaining structure at the
PILLAR-PROXY level (the same 6 proxies fama_macbeth_composite_weights.py already builds and
validates), testing whether the top-level composite is missing a genuine pillar x pillar
interaction term, not just additive weights.

Method: build ONE complete-case (strict dropna, no imputation - the same discipline
composite_weights_rebuilt_size_evidence_collapses_complete_case_20260827 established as the
trustworthy regime) panel of all 6 pillar proxies + fwd_ret, matching the CURRENT live formula
(growth_proxy uses revenue_growth_1y, the uncommitted-but-current live field - see
stock_scores_pillar_formulas_uncommitted_churn_20260828 in memory - not the stale book_value_growth
still in fama_macbeth_composite_weights.py's own docstring). Then for each of the 15 pillar pairs,
run a pairwise Fama-MacBeth regression with both main effects + their interaction term, full-sample
and half-split, using this repo's own established "must clear |t|>2 in BOTH halves" bar (the same
standard applied everywhere else - PEG, Piotroski, the momentum/risk interaction tests above).

Usage:
    python -m algo.research.cross_pillar_interaction_sweep_20260828 [options]
"""

import argparse
import itertools
import logging
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_composite_weights import _zwinsor, build_value_panel_raw
from algo.research.fama_macbeth_growth_factors import (
    build_growth_panel,
    fetch_annual_fundamentals,
    merge_asof_monthly,
)
from algo.research.fama_macbeth_momentum_factors import build_month_end_panel, compute_daily_indicators
from algo.research.fama_macbeth_momentum_factors import fetch_daily_prices as fetch_daily_close
from algo.research.fama_macbeth_price_factors import _fama_macbeth, _trailing_cumret, fetch_month_end_prices
from algo.research.fama_macbeth_quality_factors import build_quality_panel, fetch_annual_quality_fundamentals

logger = logging.getLogger(__name__)

PILLAR_COLS = ["growth_proxy", "value_proxy", "quality_proxy", "stability_proxy", "momentum_proxy", "size_proxy"]
MIN_T = 2.0


def build_complete_case_records(
    start_date: str, end_date: str, min_cross_section: int
) -> list[tuple[pd.Timestamp, pd.DataFrame]]:
    logger.info("Building fundamentals panels (growth/value/quality)")
    growth_fund = build_growth_panel(fetch_annual_fundamentals())
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

    growth_monthly = merge_asof_monthly(months, growth_fund, cols=["revenue_growth_1y"])
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

        # growth_proxy: revenue_growth_1y, sign-flipped - matches CURRENT (uncommitted) live
        # _score_growth formula, not the stale book_value_growth this file's sibling script uses.
        growth_proxy = -_zwinsor(g["revenue_growth_1y"])

        price = px.iloc[i].reindex(v.index)
        pe = np.where(v["eps"] > 0, price / v["eps"], np.nan)
        pb = np.where(v["book_value_per_share"] > 0, price / v["book_value_per_share"], np.nan)
        ps = np.where(v["sales_per_share"] > 0, price / v["sales_per_share"], np.nan)
        fcf_yield = v["fcf_per_share"] / price
        value_proxy = (
            (12.0 / 78.0) * _zwinsor(-pd.Series(pe, index=v.index))
            + (30.0 / 78.0) * _zwinsor(-pd.Series(pb, index=v.index))
            + (27.0 / 78.0) * _zwinsor(-pd.Series(ps, index=v.index))
            + (9.0 / 78.0) * _zwinsor(fcf_yield)
        )

        market_cap = price * v["shares_diluted"]
        log_mc = np.where((market_cap >= 1e6) & (market_cap <= 1e13), np.log10(market_cap), np.nan)
        size_proxy = _zwinsor(-pd.Series(log_mc, index=v.index))

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
                "growth_proxy": growth_proxy,
                "value_proxy": value_proxy,
                "quality_proxy": quality_proxy,
                "stability_proxy": stability_proxy,
                "momentum_proxy": momentum_proxy,
                "size_proxy": size_proxy,
                "fwd_ret": fwd_ret,
            }
        )
        raw = raw.replace([np.inf, -np.inf], np.nan)
        raw = raw.dropna(subset=["fwd_ret"])
        raw = raw[(raw["fwd_ret"] > -0.95) & (raw["fwd_ret"] < 5.0)]
        complete = raw.dropna(subset=PILLAR_COLS)
        if len(complete) < min_cross_section:
            continue
        complete = complete.copy()
        for col in PILLAR_COLS:
            complete[col] = _zwinsor(complete[col])
        records.append((month, complete))

    if not records:
        raise RuntimeError("No usable complete-case cross-sectional months")
    return records


def run(start_date: str, end_date: str, min_cross_section: int) -> None:
    records = build_complete_case_records(start_date, end_date, min_cross_section)
    sizes = [len(f) for _, f in records]
    print(f"Usable complete-case cross-sectional months: {len(records)}  ({records[0][0]} to {records[-1][0]})")
    print(f"Median cross-section size: {int(np.median(sizes))}\n")

    split = len(records) // 2
    eras = {"FULL": records, "ERA1": records[:split], "ERA2": records[split:]}

    results = []
    for a, b in itertools.combinations(PILLAR_COLS, 2):
        inter_col = f"{a}_x_{b}"
        for _month, frame in records:
            frame[inter_col] = frame[a] * frame[b]

        row: dict[str, Any] = {"pair": f"{a} x {b}"}
        for era_label, recs in eras.items():
            fm = _fama_macbeth(recs, [a, b, inter_col])
            row[f"t_{era_label}"] = fm[inter_col][1]
            row[f"coef_{era_label}"] = fm[inter_col][0]
        results.append(row)

    print(f"{'pair':30s} {'coef_FULL':>10s} {'t_FULL':>7s} {'t_ERA1':>7s} {'t_ERA2':>7s} {'robust?':>8s}")
    for row in sorted(results, key=lambda r: -abs(r["t_FULL"])):
        robust = (
            abs(row["t_FULL"]) >= MIN_T
            and abs(row["t_ERA1"]) >= MIN_T
            and abs(row["t_ERA2"]) >= MIN_T
            and (row["t_ERA1"] > 0) == (row["t_ERA2"] > 0)
        )
        flag = "YES" if robust else ""
        print(
            f"{row['pair']:30s} {row['coef_FULL']:10.5f} {row['t_FULL']:7.2f} "
            f"{row['t_ERA1']:7.2f} {row['t_ERA2']:7.2f} {flag:>8s}"
        )


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
