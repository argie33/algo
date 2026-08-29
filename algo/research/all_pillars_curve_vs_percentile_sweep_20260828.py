#!/usr/bin/env python3
"""
Repo-wide fixed-curve vs cross-sectional-percentile sweep: Quality (8), Risk (3, excludes
beta), Momentum (3, excludes MACD), Growth (1), Size (1) - every remaining pillar component
after Value's P/E/P/B/P/S already shipped this way
(algo/research/value_absolute_curve_vs_relative_ranking_20260828.py,
value_pe_pb_ps_switched_to_cross_sectional_percentile_20260828 in memory).

Built 2026-08-28 (goal: user directive "not just for REIT... make sure we account for all the
things we need to do all over for getting all the scores right" - i.e. the Value fix wasn't a
one-off, it's a symptom of a repo-wide pattern; confirmed by direct code read: EVERY numeric
scoring component in this file (Quality's `_margin_curve` family in
load_value_quality_growth_metrics.py, Growth's `_score_single_growth`, Risk's
`_vol_curve_score`/`_max_drawdown_curve_score`, Momentum's `_pct_to_score`/`_rsi_to_score`,
Size's log-bucket curve) uses a fixed, hand-set absolute threshold, never cross-sectional
ranking - the same architecture already shown to lose to percentile ranking for Value.

EXCLUDED from this sweep, deliberately: Beta (this pillar's own design target is "close to
1.0", not "more extreme = better/worse" - percentile ranking doesn't map onto that goal without
an entirely different transform, out of scope) and MACD-sign (a discrete bull/bear flag, not a
continuous magnitude a percentile rank would meaningfully reorder).

UNIT-SCALE CARE (this exact bug class - a raw fraction fed into a percentage-point curve - has
already bitten this repo once, see quality_roa_conditioned_interaction_feature_validated_not_shipped_20260827
in memory): every raw candidate below is scaled to MATCH the live curve's own input convention,
verified by inline comment + a printed describe() sanity check before any regression runs -
- roe/roa/roce/fcf_margin/margin_volatility_3y/asset_turnover/gross_profitability: build_quality_panel()
  returns raw fractions (e.g. 0.15 for 15%) - `_margin_curve`'s breakpoints (e.g. ROE's
  [(10.0,50.0)...]) are percentage-POINT scaled, so these are all multiplied by 100 here.
- debt_to_equity: NOT scaled - production's own curve (`100 - (d2e/2.0)*100`) uses the raw
  ratio directly (d2e=2.0 is a real, unscaled Debt/Equity value).
- volatility_60d/downside_volatility_60d: NOT scaled - production's curve compares against
  0.15/0.30/0.60, i.e. it already expects a raw fraction (15% = 0.15), matching this script's
  own `win.std()*sqrt(12)` construction directly.
- max_drawdown_1y: `_trailing`-style drawdown here is a raw fraction (-0.35 for -35%) but
  production's curve compares against 10/25/50 (percentage POINTS, per _score_risk's own
  docstring example "-34.63 = a 34.63% decline") - multiplied by 100 here.
- mom_3m/mom_12_1: `_pct_to_score`'s own docstring is explicit - "pct_return is a percentage
  NUMBER (e.g. 20.0 for +20%)" - this script's `_trailing_cumret` returns a raw fraction, so
  multiplied by 100 here.
- rsi_14: already 0-100 scale in both places, no scaling.
- market_cap: raw dollars in both places, no scaling (log10 threshold breakpoints already
  dollar-denominated).

Usage:
    python -m algo.research.all_pillars_curve_vs_percentile_sweep_20260828 [options]
"""

import argparse
import itertools
import logging
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_growth_factors import (
    REPORTING_LAG_DAYS,
    build_growth_panel,
    fetch_annual_fundamentals,
    merge_asof_monthly,
)
from algo.research.fama_macbeth_momentum_factors import build_month_end_panel, compute_daily_indicators
from algo.research.fama_macbeth_momentum_factors import fetch_daily_prices as fetch_daily_close
from algo.research.fama_macbeth_price_factors import _fama_macbeth, _trailing_cumret, fetch_month_end_prices
from algo.research.fama_macbeth_quality_factors import build_quality_panel, fetch_annual_quality_fundamentals
from algo.research.fama_macbeth_value_factors import fetch_annual_value_fundamentals
from loaders.load_stock_scores import StockScoresLoader

logger = logging.getLogger(__name__)

CONTROL_COLS = ["growth_proxy", "value_proxy", "quality_proxy", "stability_proxy", "momentum_proxy", "size_proxy"]
PILLAR_TO_PROXY = {
    "growth": "growth_proxy",
    "value": "value_proxy",
    "quality": "quality_proxy",
    "risk": "stability_proxy",
    "momentum": "momentum_proxy",
    "size": "size_proxy",
}


def _zwinsor(s: pd.Series) -> pd.Series:
    s = s.replace([np.inf, -np.inf], np.nan)
    lo, hi = s.quantile([0.01, 0.99])
    s = s.clip(lo, hi)
    std = s.std()
    return (s - s.mean()) / std if std and std > 0 else s * 0.0


def _percent_rank_higher_is_better(values: pd.Series) -> pd.Series:
    """Cross-sectional percentile in [0,100], HIGHER raw value = HIGHER percentile (for
    metrics where more is better: ROE, ROA, ROCE, FCF margin, asset_turnover,
    gross_profitability, mom_3m, mom_12_1, rsi_14, market_cap-for-size... - Size's own curve
    reward SMALLER cap, so that one is negated before calling this, same convention as every
    other -metric this file already inverts before z-scoring)."""
    n = values.notna().sum()
    if n == 0:
        return pd.Series(np.nan, index=values.index)
    if n == 1:
        return pd.Series(np.where(values.notna(), 50.0, np.nan), index=values.index)
    ranks = values.rank(method="min", ascending=True, na_option="keep")
    return (ranks - 1) / (n - 1) * 100.0


def build_value_panel_raw() -> pd.DataFrame:
    fund = fetch_annual_value_fundamentals()
    shares = fund["shares_diluted"]
    out = fund[["symbol", "fiscal_year"]].copy()
    out["eps"] = fund["eps"]
    out["book_value_per_share"] = fund["stockholders_equity"] / shares
    out["sales_per_share"] = fund["revenue"] / shares
    out["fcf_per_share"] = fund["free_cash_flow"] / shares
    out["shares_diluted"] = shares
    out["known_date"] = pd.to_datetime(fund["fiscal_year"].astype(str) + "-12-31") + pd.Timedelta(
        days=REPORTING_LAG_DAYS
    )
    return out.dropna(subset=["known_date"])


CANDIDATES = [
    # (label, pillar, higher_is_better, weight_in_pillar)
    ("roe", "quality", True, 0.11),
    ("roa", "quality", True, 0.18),
    ("roce", "quality", True, 0.18),
    ("fcf_margin", "quality", True, 0.15),
    ("debt_to_equity", "quality", False, 0.18),
    ("margin_volatility_3y", "quality", False, 0.07),
    ("asset_turnover", "quality", True, 0.07),
    ("gross_profitability", "quality", True, 0.07),
    ("revenue_growth_1y", "growth", False, 1.0),  # sign-flipped live (growth-reversal)
    ("volatility_60d", "risk", False, 0.45),
    ("downside_volatility_60d", "risk", False, 0.15),
    ("max_drawdown_pct", "risk", False, 0.20),
    ("mom_3m_pct", "momentum", True, 0.20),
    ("mom_12_1_pct", "momentum", True, 0.35),
    ("rsi_14", "momentum", True, 0.37),
    ("log_market_cap", "size", False, 1.0),  # smaller = higher size_score
]


def curve_score(label: str, val: float) -> float | None:
    """Exact production curve for `label`, given its value in THIS script's own units (see
    module docstring's unit-scale table - callers must pre-scale before calling this)."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    if label == "roe":
        return _margin_curve(val, [(10.0, 50.0), (20.0, 85.0), (40.0, 100.0)])
    if label == "roa":
        return _margin_curve(val, [(3.0, 40.0), (8.0, 80.0), (15.0, 100.0)])
    if label == "roce":
        return _margin_curve(val, [(8.0, 40.0), (15.0, 75.0), (25.0, 100.0)])
    if label == "fcf_margin":
        return _margin_curve(val, [(5.0, 40.0), (15.0, 75.0), (30.0, 100.0)])
    if label == "debt_to_equity":
        return max(0.0, min(100.0, 100.0 - (val / 2.0) * 100.0))
    if label == "margin_volatility_3y":
        return 100.0 - _margin_curve(val, [(5.0, 20.0), (15.0, 60.0), (30.0, 100.0)])
    if label == "asset_turnover":
        return _margin_curve(val, [(30.0, 40.0), (80.0, 75.0), (150.0, 100.0)])
    if label == "gross_profitability":
        return _margin_curve(val, [(10.0, 40.0), (25.0, 75.0), (50.0, 100.0)])
    if label == "revenue_growth_1y":
        # `val` here is the RAW (un-flipped) revenue_growth_1y - production's _score_growth
        # negates it before applying _score_single_growth's curve (growth-reversal effect,
        # lower growth scores higher) via `-metrics["revenue_growth_1y"]`. Do that negation
        # HERE, not at the caller, so this function's contract matches every other curve_score
        # branch (raw value in, correctly-signed 0-100 score out).
        flipped = -val
        if flipped <= 0:
            return max(0.0, 40 + (flipped / 50) * 40)
        return min(100.0, 40 + (flipped / 30) * 60)
    if label == "volatility_60d" or label == "downside_volatility_60d":
        return StockScoresLoader._vol_curve_score(max(0.0, val))
    if label == "max_drawdown_pct":
        return StockScoresLoader._max_drawdown_curve_score(val)
    if label in ("mom_3m_pct", "mom_12_1_pct"):
        return StockScoresLoader._pct_to_score(val)
    if label == "rsi_14":
        return StockScoresLoader._rsi_to_score(val)
    if label == "log_market_cap":
        if val <= 8.48:
            return 100.0
        if val <= 9.30:
            return 100 - (val - 8.48) / (9.30 - 8.48) * 20
        if val <= 10.0:
            return 80 - (val - 9.30) / (10.0 - 9.30) * 20
        if val <= 11.3:
            return 60 - (val - 10.0) / (11.3 - 10.0) * 30
        return max(10.0, 30 - (val - 11.3) * 15)
    raise ValueError(f"unknown candidate label {label}")


def _margin_curve(value: float, breakpoints: list[tuple[float, float]]) -> float:
    """Verbatim copy of load_value_quality_growth_metrics.py's `_margin_curve` (line ~3627) -
    piecewise-linear, value<x0 ramps 0->y0, value>=last x holds at last y."""
    if value < 0:
        return 0.0
    if value < breakpoints[0][0]:
        x1, y1 = breakpoints[0]
        return (value / x1) * y1 if x1 > 0 else y1
    for (x0, y0), (x1, y1) in itertools.pairwise(breakpoints):
        if value < x1:
            return y0 + (value - x0) / (x1 - x0) * (y1 - y0)
    return breakpoints[-1][1]


def run(start_date: str, end_date: str, min_cross_section: int) -> None:
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
    raw_records: list[tuple[pd.Timestamp, pd.DataFrame]] = []

    logger.info("Building per-month raw-candidate + control-proxy panel")
    for i in range(beta_window, len(months) - 1):
        month = months[i]
        g = growth_monthly.get(month)
        v = value_monthly.get(month)
        q = quality_monthly.get(month)
        if g is None or v is None or q is None or g.empty or v.empty or q.empty:
            continue

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
        log_mc = pd.Series(
            np.where((market_cap >= 1e6) & (market_cap <= 1e13), np.log10(market_cap), np.nan), index=v.index
        )
        size_proxy = _zwinsor(-log_mc)

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
        max_dd_frac = (win_px / win_px.cummax() - 1.0).min()  # negative fraction, e.g. -0.35
        stability_proxy = (
            0.45 * _zwinsor(-vol)
            + 0.20 * _zwinsor(-(beta - 1.0).abs())
            + 0.15 * _zwinsor(-downside_vol)
            + 0.20 * _zwinsor(max_dd_frac)
        )

        mom_3m_frac = _trailing_cumret(px, i, 3)
        mom_12_1_frac = _trailing_cumret(px, i - 1, 11)
        rsi = indicators["rsi_14"].iloc[i]
        macd_sign = indicators["macd_sign"].iloc[i]
        sma_avg = (indicators["price_vs_sma_50"].iloc[i] + indicators["price_vs_sma_200"].iloc[i]) / 2.0
        momentum_proxy = (
            0.20 * _zwinsor(mom_3m_frac)
            + 0.35 * _zwinsor(mom_12_1_frac)
            + 0.21 * _zwinsor(rsi)
            + 0.16 * _zwinsor(macd_sign)
            + 0.08 * _zwinsor(sma_avg)
        )

        growth_proxy = -_zwinsor(g["revenue_growth_1y"])
        fwd_ret = ret.iloc[i + 1]

        frame = pd.DataFrame(index=v.index)
        frame["roe"] = q["roe"].reindex(v.index) * 100.0
        frame["roa"] = q["roa"].reindex(v.index) * 100.0
        frame["roce"] = q["roce"].reindex(v.index) * 100.0
        frame["fcf_margin"] = q["fcf_margin"].reindex(v.index) * 100.0
        frame["debt_to_equity"] = q["debt_to_equity"].reindex(v.index)  # NOT scaled, see docstring
        frame["margin_volatility_3y"] = q["margin_volatility_3y"].reindex(v.index) * 100.0
        frame["asset_turnover"] = q["asset_turnover"].reindex(v.index) * 100.0
        frame["gross_profitability"] = q["gross_profitability"].reindex(v.index) * 100.0
        frame["revenue_growth_1y"] = g["revenue_growth_1y"].reindex(v.index) * 100.0
        frame["volatility_60d"] = vol.reindex(v.index)  # NOT scaled
        frame["downside_volatility_60d"] = downside_vol.reindex(v.index)  # NOT scaled
        frame["max_drawdown_pct"] = (max_dd_frac.reindex(v.index).abs()) * 100.0
        frame["mom_3m_pct"] = mom_3m_frac.reindex(v.index) * 100.0
        frame["mom_12_1_pct"] = mom_12_1_frac.reindex(v.index) * 100.0
        frame["rsi_14"] = rsi.reindex(v.index)  # NOT scaled
        frame["log_market_cap"] = log_mc

        frame["growth_proxy"] = growth_proxy.reindex(v.index)
        frame["value_proxy"] = value_proxy.reindex(v.index)
        frame["quality_proxy"] = quality_proxy.reindex(v.index)
        frame["stability_proxy"] = stability_proxy.reindex(v.index)
        frame["momentum_proxy"] = momentum_proxy.reindex(v.index)
        frame["size_proxy"] = size_proxy.reindex(v.index)
        frame["fwd_ret"] = fwd_ret.reindex(v.index)

        frame = frame.replace([np.inf, -np.inf], np.nan)
        frame = frame.dropna(subset=["fwd_ret"])
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        if len(frame) < min_cross_section:
            continue
        raw_records.append((month, frame))

    if not raw_records:
        raise RuntimeError("No usable cross-sectional months")

    # --- SANITY CHECK: print describe() for every raw candidate before trusting any curve ---
    pooled_raw = pd.concat([f for _m, f in raw_records], ignore_index=True)
    print("=== UNIT-SCALE SANITY CHECK (describe() of each raw candidate, pre-curve) ===")
    print(pooled_raw[[c[0] for c in CANDIDATES]].describe().T[["mean", "std", "min", "50%", "max"]].round(2))
    print()

    sizes = [len(f) for _, f in raw_records]
    print(f"Usable cross-sectional months: {len(raw_records)}  ({raw_records[0][0]} to {raw_records[-1][0]})")
    print(f"Median cross-section size: {int(np.median(sizes))}\n")

    results = []
    for label, pillar, higher_is_better, _weight in CANDIDATES:
        # CRITICAL: exclude THIS candidate's own pillar proxy from the control set - it's
        # either an exact duplicate (Growth/Size, single-input pillars: growth_proxy/size_proxy
        # ARE this candidate, up to a sign flip) or a partial blend containing this exact
        # candidate (Quality/Risk/Momentum: e.g. quality_proxy is 11% built from `roe` itself).
        # Regressing a candidate against a control that already contains it is severe/exact
        # collinearity - caught live this session (revenue_growth_1y's first run showed a
        # nonsensical, wrong-signed coefficient purely from this bug, not a real finding).
        own_proxy = PILLAR_TO_PROXY[pillar]
        controls = [c for c in CONTROL_COLS if c != own_proxy]

        records_curve: list[tuple[pd.Timestamp, pd.DataFrame]] = []
        records_pct: list[tuple[pd.Timestamp, pd.DataFrame]] = []
        for month, frame in raw_records:
            raw_col = frame[label]
            curve_col = raw_col.apply(lambda v, _label=label: curve_score(_label, v) if pd.notna(v) else np.nan)
            pct_col = (
                _percent_rank_higher_is_better(raw_col)
                if higher_is_better
                else 100.0 - _percent_rank_higher_is_better(raw_col)
            )
            sub_curve = frame[[*controls, "fwd_ret"]].copy()
            sub_curve["candidate"] = _zwinsor(curve_col)
            sub_curve = sub_curve.dropna(subset=["candidate", *controls, "fwd_ret"])
            if len(sub_curve) >= min_cross_section:
                records_curve.append((month, sub_curve))

            sub_pct = frame[[*controls, "fwd_ret"]].copy()
            sub_pct["candidate"] = _zwinsor(pct_col)
            sub_pct = sub_pct.dropna(subset=["candidate", *controls, "fwd_ret"])
            if len(sub_pct) >= min_cross_section:
                records_pct.append((month, sub_pct))

        if not records_curve or not records_pct:
            print(f"{label}: insufficient data, skipped")
            continue

        for variant_name, records in (("curve", records_curve), ("percentile", records_pct)):
            eras = {"FULL": records, "ERA1": records[: len(records) // 2], "ERA2": records[len(records) // 2 :]}
            row: dict[str, Any] = {"label": label, "pillar": pillar, "variant": variant_name}
            for era_label, recs in eras.items():
                fm = _fama_macbeth(recs, ["candidate", *controls])
                row[f"t_{era_label}"] = fm["candidate"][1]
            results.append(row)

    print(f"{'label':22s} {'pillar':10s} {'variant':11s} {'t_FULL':>7s} {'t_ERA1':>7s} {'t_ERA2':>7s} {'winner?':>8s}")
    by_label: dict[str, dict[str, dict[str, Any]]] = {}
    for r in results:
        by_label.setdefault(r["label"], {})[r["variant"]] = r
    for label, variants in by_label.items():
        pillar = variants["curve"]["pillar"] if "curve" in variants else variants["percentile"]["pillar"]
        for variant_name in ("curve", "percentile"):
            if variant_name not in variants:
                continue
            r = variants[variant_name]
            flag = ""
            if "curve" in variants and "percentile" in variants:
                if variant_name == "percentile" and abs(r["t_FULL"]) > abs(variants["curve"]["t_FULL"]):
                    flag = "PCT BETTER"
                elif variant_name == "curve" and abs(r["t_FULL"]) >= abs(variants["percentile"]["t_FULL"]):
                    flag = "CURVE OK"
            print(
                f"{label:22s} {pillar:10s} {variant_name:11s} "
                f"{r['t_FULL']:7.2f} {r['t_ERA1']:7.2f} {r['t_ERA2']:7.2f} {flag:>8s}"
            )
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
