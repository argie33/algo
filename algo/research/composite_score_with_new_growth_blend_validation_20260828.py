#!/usr/bin/env python3
"""
Composite-level validation of the new 5-input Growth blend (growth_multi_input_blend_test_
20260828.py's "EQUAL" variant) versus the OLD single-input Growth (revenue_growth_1y alone,
the live/uncommitted formula that script was built to test) - answering the question the
per-pillar tests didn't: does substituting the new Growth formula into the FULL 6-pillar
composite_score improve, harm, or leave unchanged the composite's own predictive power and
cross-sector fairness (Financial Services / Real Estate), and does Growth's own coverage gain
(89.4% -> 95.4%) actually raise COMPOSITE coverage.

Reuses (no re-derivation): fama_macbeth_composite_weights.py's exact quality_proxy (8-component)/
value_proxy/stability_proxy/momentum_proxy/size_proxy construction and BASE_PILLAR_WEIGHTS import;
growth_multi_input_blend_test_20260828.py's exact growth_single/growth_equal construction and
_renormalized_blend helper; sector_relative_scoring_test_20260828.py's fetch_sector_map.

Composite = 0-imputed partial-availability weighted sum at live BASE_PILLAR_WEIGHTS, matching
the live composite_score's own "renormalize/skip-unavailable" tolerance (this repo's existing
composite-weights script's own documented simplification for this kind of relative comparison).
"""

import argparse
import logging
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_composite_weights import _zwinsor, build_value_panel_raw
from algo.research.fama_macbeth_growth_factors import build_growth_panel, fetch_annual_fundamentals
from algo.research.fama_macbeth_growth_factors import merge_asof_monthly as merge_asof_monthly_growth
from algo.research.fama_macbeth_momentum_factors import build_month_end_panel, compute_daily_indicators
from algo.research.fama_macbeth_momentum_factors import fetch_daily_prices as fetch_daily_close
from algo.research.fama_macbeth_price_factors import _fama_macbeth, fetch_month_end_prices
from algo.research.fama_macbeth_quality_factors import build_quality_panel, fetch_annual_quality_fundamentals
from algo.research.growth_multi_input_blend_test_20260828 import CANDIDATE_COLS, _renormalized_blend
from algo.research.growth_reinvestment_book_value_candidates import build_panel as build_book_value_panel
from algo.research.growth_reinvestment_book_value_candidates import fetch_panel_raw as fetch_book_value_fundamentals
from algo.research.sector_relative_scoring_test_20260828 import fetch_sector_map
from loaders.load_stock_scores import BASE_PILLAR_WEIGHTS

logger = logging.getLogger(__name__)

UNCLASSIFIED = "Unclassified"
FOCUS_SECTORS = ["Financial Services", "Real Estate"]
MIN_SECTOR_SLICE = 10


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


def run(start_date: str, end_date: str, min_cross_section: int) -> None:
    logger.info("Fetching sector map")
    sector_map = fetch_sector_map()

    logger.info("Building fundamentals panels (growth candidates, quality (full 8), value)")
    growth_raw = fetch_annual_fundamentals()
    growth_panel = build_growth_panel(growth_raw)  # revenue_growth_1y, eps_growth_1y, ocf_growth_yoy
    bv_panel = build_book_value_panel(fetch_book_value_fundamentals())  # book_value_growth

    quality_raw = fetch_annual_quality_fundamentals()
    quality_fund = build_quality_panel(quality_raw)
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
            "roce",
            "fcf_margin",
            "debt_to_equity",
            "margin_volatility_3y",
            "asset_turnover",
            "gross_profitability",
            "sustainable_growth_rate",
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

        z_growth = pd.DataFrame(index=idx)
        for col in CANDIDATE_COLS:
            z_growth[col] = -_zwinsor(cand[col])
        growth_single_raw = z_growth["revenue_growth_1y"]
        growth_equal_raw = _renormalized_blend(z_growth, dict.fromkeys(CANDIDATE_COLS, 1.0))

        price = px.iloc[i].reindex(v.index)
        pe = pd.Series(np.where(v["eps"] > 0, price / v["eps"], np.nan), index=v.index)
        pb = pd.Series(
            np.where(v["book_value_per_share"] > 0, price / v["book_value_per_share"], np.nan), index=v.index
        )
        ps = pd.Series(np.where(v["sales_per_share"] > 0, price / v["sales_per_share"], np.nan), index=v.index)
        fcf_yield = v["fcf_per_share"] / price
        value_proxy_raw = (
            (12.0 / 78.0) * _zwinsor(-pe)
            + (30.0 / 78.0) * _zwinsor(-pb)
            + (27.0 / 78.0) * _zwinsor(-ps)
            + (9.0 / 78.0) * _zwinsor(fcf_yield)
        )

        market_cap = price * v["shares_diluted"]
        log_mc = np.where((market_cap >= 1e6) & (market_cap <= 1e13), np.log10(market_cap), np.nan)
        size_proxy_raw = _zwinsor(-pd.Series(log_mc, index=v.index))

        quality_proxy_raw = (
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
        stability_proxy_raw = (
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
        momentum_proxy_raw = (
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
                "growth_single_raw": growth_single_raw.reindex(idx),
                "growth_equal_raw": growth_equal_raw.reindex(idx),
                "value_proxy_raw": value_proxy_raw.reindex(idx),
                "quality_proxy_raw": quality_proxy_raw.reindex(idx),
                "stability_proxy_raw": stability_proxy_raw.reindex(idx),
                "momentum_proxy_raw": momentum_proxy_raw.reindex(idx),
                "size_proxy_raw": size_proxy_raw.reindex(idx),
                "fwd_ret": fwd_ret.reindex(idx),
            }
        )
        frame["sector"] = sectors_here
        frame = frame.replace([np.inf, -np.inf], np.nan)
        frame = frame.dropna(subset=["fwd_ret"])
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        if len(frame) < min_cross_section:
            continue
        raw_records.append((month, frame))

    if not raw_records:
        raise RuntimeError("No usable cross-sectional months")

    print(f"Usable cross-sectional months: {len(raw_records)}  ({raw_records[0][0]} to {raw_records[-1][0]})")
    sizes = [len(f) for _, f in raw_records]
    print(f"Median cross-section size: {int(np.median(sizes))}\n")

    w = BASE_PILLAR_WEIGHTS  # quality/growth/value/risk/momentum/size

    # --- Coverage: at-least-1-of-6-pillars-required rule (matches live GOVERNANCE.md minimum) ---
    print("########## Composite coverage: >=1 of 6 pillars real (matches live 'min 1/6' rule) ##########\n")

    def _pillar_available(frame: pd.DataFrame, growth_col: str) -> pd.Series:
        return (
            frame[growth_col].notna()
            | frame["value_proxy_raw"].notna()
            | frame["quality_proxy_raw"].notna()
            | frame["stability_proxy_raw"].notna()
            | frame["momentum_proxy_raw"].notna()
            | frame["size_proxy_raw"].notna()
        )

    cov_old = np.mean([_pillar_available(f, "growth_single_raw").mean() for _, f in raw_records])
    cov_new = np.mean([_pillar_available(f, "growth_equal_raw").mean() for _, f in raw_records])
    print(f"{'variant':30s} {'coverage':>10s}")
    print(f"{'OLD (growth_single)':30s} {cov_old * 100:9.2f}%")
    print(f"{'NEW (growth_equal)':30s} {cov_new * 100:9.2f}%")
    for focus in FOCUS_SECTORS:
        sub_frames = [(f[f["sector"] == focus]) for _, f in raw_records]
        cov_old_f = np.mean([_pillar_available(sf, "growth_single_raw").mean() for sf in sub_frames if len(sf) > 0])
        cov_new_f = np.mean([_pillar_available(sf, "growth_equal_raw").mean() for sf in sub_frames if len(sf) > 0])
        print(f"  {focus:28s} OLD {cov_old_f * 100:6.2f}%   NEW {cov_new_f * 100:6.2f}%")
    print()

    # --- Build 0-imputed partial-availability composite (OLD and NEW) ---
    records: list[tuple[pd.Timestamp, pd.DataFrame]] = []
    for m, f in raw_records:
        f = f.copy()
        gs = _zwinsor(f["growth_single_raw"]).fillna(0.0)
        ge = _zwinsor(f["growth_equal_raw"]).fillna(0.0)
        vp = _zwinsor(f["value_proxy_raw"]).fillna(0.0)
        qp = _zwinsor(f["quality_proxy_raw"]).fillna(0.0)
        sp = _zwinsor(f["stability_proxy_raw"]).fillna(0.0)
        mp = _zwinsor(f["momentum_proxy_raw"]).fillna(0.0)
        zp = _zwinsor(f["size_proxy_raw"]).fillna(0.0)
        f["composite_old"] = (
            w["growth"] * gs
            + w["value"] * vp
            + w["quality"] * qp
            + w["risk"] * sp
            + w["momentum"] * mp
            + w["size"] * zp
        )
        f["composite_new"] = (
            w["growth"] * ge
            + w["value"] * vp
            + w["quality"] * qp
            + w["risk"] * sp
            + w["momentum"] * mp
            + w["size"] * zp
        )
        records.append((m, f))

    split_idx = len(records) // 2
    halves = {"FULL": records, "ERA1": records[:split_idx], "ERA2": records[split_idx:]}

    print("########## Composite Fama-MacBeth (univariate, OLD vs NEW growth) ##########\n")
    print(f"{'variant':16s} {'era':6s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
    for variant in ("composite_old", "composite_new"):
        for era_label, era_records in halves.items():
            if not era_records:
                continue
            mean, t = _fama_macbeth(era_records, [variant])[variant]
            print(f"{variant:16s} {era_label:6s} {mean:10.5f} {t:8.2f} {len(era_records):9d}")
        print()

    print("########## Composite Spearman IC, overall and sliced to Financial Services / Real Estate ##########\n")
    print(f"{'variant':16s} {'scope':20s} {'mean_ic':>9s} {'t_stat':>8s} {'n_months':>9s}")
    for variant in ("composite_old", "composite_new"):
        ics = _spearman_ic_series(records, variant)
        mean_ic, t, n = _ic_mean_t(ics)
        print(f"{variant:16s} {'ALL':20s} {mean_ic:9.4f} {t:8.2f} {n:9d}")
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
