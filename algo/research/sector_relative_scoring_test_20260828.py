#!/usr/bin/env python3
"""
Sector-relative scoring test.

Built 2026-08-28 (goal: user's cross-sector comparability concern - "a bank doesn't use
metrics the way other companies do, neither does a REIT, how do we get them on a level
playing field"). Two live-confirmed gaps motivate this script:

(1) Value pillar's PE/PB/PS are z-scored/percentiled against the FULL universe (5,194 symbols,
    all sectors pooled) in both the live formula (loaders/load_stock_scores.py._score_value)
    and its own validation research (algo/research/fama_macbeth_value_factors.py). Live query
    this session: average P/E ranges 19.0 (Financial Services) to 32.4 (Technology), average
    P/B ranges 1.9 (Real Estate) to 5.3 (Technology) - persistent, not noise. GICS sector
    classification already exists (company_profile.sector, an SIC->GICS map built for position
    sizing in loaders/load_company_profile.py) but has NEVER been joined into stock_scores or
    any Fama-MacBeth pillar research, which is why this was never caught.

(2) Quality pillar's gross_profitability (COGS-based) has only 15.5% coverage for Financial
    Services and 34.9% for Real Estate vs 83%+ elsewhere - structurally absent, not a data
    gap. Today it's handled by renormalizing Quality's weight over whatever components ARE
    available (same mechanism used for ordinary missing-data gaps) - no distinction between
    "doesn't apply to this business" and "we're missing this."

This script builds THREE variants of Value's PE/PB/PS-driven proxy per month - (a) UNIVERSE:
current live behavior, winsorize+z-score against the whole cross-section; (b) SECTOR: winsorize
+z-score within company_profile.sector groups only (NULL/'Unknown'/'Other' folded into one
'Unclassified' residual group, per this session's explicit scope - not dropped); (c) BLEND:
simple average of (a) and (b) - and tests all three with this repo's own established
methodology (Fama-MacBeth two-pass regression, Spearman rank IC, half-split era robustness),
reusing algo/research/fama_macbeth_composite_weights.py's exact panel-building machinery
(growth/quality/stability/momentum/size proxies, same weights) as multivariate controls so this
is an apples-to-apples extension of that script, not a new methodology.

REGIME: partial-availability only (0-imputed missing pillars, matching the live composite's
own tolerance) - NOT run in both partial/complete-case regimes like composite_weights.py does,
to keep this time-boxed. This is a fair simplification here specifically because the 3-way
UNIVERSE/SECTOR/BLEND comparison is a relative one (same regime applied identically to all
three variants each month), unlike composite_weights.py's own dual-regime question (does
imputation itself manufacture a relationship), which isn't what's being tested here.

DATA CONSTRAINT FOUND (changes how "Question 2" from the parent task is answered): live-checked
this session - `stock_scores` has exactly ONE date (2026-08-28) for all 5,103 rows
(`SELECT count(*), count(distinct date)` -> 5103, 1). It is a single current snapshot, not a
history - the parent task's literal ask ("pull the live quality_score, compute Spearman IC vs
forward returns over time") is not possible; a single cross-section can't produce a real
multi-month IC series (n=1 is not a statistic). Substituted the best available real-history
stand-in that answers the same underlying question: quality_proxy, the SAME point-in-time
monthly reconstruction (from annual_income_statement/annual_balance_sheet history) already used
as this script's own multivariate control, built and validated in
algo/research/fama_macbeth_composite_weights.py to match _score_quality's live 8-component
weights exactly. Its per-sector Spearman IC (Financial Services / Real Estate / everyone else)
answers "is Quality's construction equally predictive for sectors missing gross_profitability"
just as directly as the live column would have, with real multi-year history behind it.

Usage:
    python -m algo.research.sector_relative_scoring_test_20260828 [options]
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
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

UNCLASSIFIED = "Unclassified"
VALUE_VARIANT_COLS = ["value_uni", "value_sector", "value_blend"]
CONTROL_COLS = ["growth_proxy", "quality_proxy", "stability_proxy", "momentum_proxy", "size_proxy"]
FOCUS_SECTORS = ["Financial Services", "Real Estate"]
MIN_SECTOR_SLICE = 10  # minimum rows in a sector-only monthly slice to trust its Spearman IC


def fetch_sector_map() -> pd.Series:
    """symbol -> GICS sector, NULL/'Unknown'/'Other' folded into one 'Unclassified' residual
    group per this test's explicit scope (not dropped - see module docstring)."""
    sql = """
        SELECT symbol,
               CASE WHEN sector IS NULL OR sector IN ('Unknown', 'Other') THEN %s ELSE sector END AS sector
        FROM company_profile
    """
    with DatabaseContext("read") as cur:
        cur.execute(sql, (UNCLASSIFIED,))
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["symbol", "sector"])
    return df.set_index("symbol")["sector"]


def _zwinsor_by_group(values: pd.Series, groups: pd.Series) -> pd.Series:
    """Winsorize+z-score `values` independently within each `groups` label, then reassemble in
    the original index order. A group with too few non-null observations to winsorize
    meaningfully (<5) falls back to the full-population zwinsor for just that group's rows,
    rather than emitting NaN/degenerate zeros that would silently penalize thin sectors."""
    out = pd.Series(np.nan, index=values.index)
    aligned_groups = groups.reindex(values.index)
    for _label, idx in aligned_groups.groupby(aligned_groups).groups.items():
        sub = values.loc[idx]
        if sub.notna().sum() < 5:
            continue  # filled by the fallback pass below
        out.loc[idx] = _zwinsor(sub)
    missing = out.isna() & values.notna()
    if missing.any():
        out.loc[missing] = _zwinsor(values.loc[missing])
    return out


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
    # BIT-ROT FIX 2026-09-04: build_value_panel_raw() (fama_macbeth_composite_weights.py) no
    # longer returns fcf_per_share - it was dropped when FCF yield was removed from live Value
    # scoring (see loaders/load_stock_scores.py._score_value's "FCF YIELD - RESOLVED" note).
    # This script's own docstring already scopes fcf_term as deliberately universe-wide/
    # identical in both UNIVERSE and SECTOR variants (out of scope for the PE/PB/PS test), so
    # dropping it (fcf_term=0.0 below) doesn't affect the comparison this script exists to make.
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

        # (a) UNIVERSE: PE/PB/PS equal-weighted (1/3 each) - matches the CURRENT live
        # _score_value equal-weighting of the 3 core multiples (27/27/27, see that method's
        # "EQUAL-WEIGHTED 2026-09-01" docstring note), not the 12/30/27-plus-FCF weights this
        # script originally used on 2026-08-28 (FCF yield has since been removed from live Value
        # scoring entirely - see BIT-ROT FIX note above).
        value_uni = (1.0 / 3.0) * (_zwinsor(-pe) + _zwinsor(-pb) + _zwinsor(-ps))

        # (b) SECTOR: identical weights, PE/PB/PS z-scored WITHIN sector group instead of the
        # whole universe.
        value_sector = (1.0 / 3.0) * (
            _zwinsor_by_group(-pe, sectors_here)
            + _zwinsor_by_group(-pb, sectors_here)
            + _zwinsor_by_group(-ps, sectors_here)
        )

        # (c) BLEND: simple average.
        value_blend = 0.5 * (value_uni + value_sector)

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
                "value_uni": value_uni,
                "value_sector": value_sector,
                "value_blend": value_blend,
                "growth_proxy": growth_proxy,
                "quality_proxy": quality_proxy,
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

        numeric_cols = [*VALUE_VARIANT_COLS, *CONTROL_COLS]
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

    print("########## Q1: Value pillar PE/PB/PS - universe-wide vs sector-relative ranking ##########\n")
    print("=== Multivariate Fama-MacBeth (each value variant + 5 pillar controls), by era ===")
    print(f"{'variant':14s} {'era':6s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
    for variant in VALUE_VARIANT_COLS:
        for era_label, era_records in halves.items():
            if not era_records:
                continue
            result = _fama_macbeth(era_records, [variant, *CONTROL_COLS])
            mean, t = result[variant]
            print(f"{variant:14s} {era_label:6s} {mean:10.5f} {t:8.2f} {len(era_records):9d}")
        print()

    print("=== Univariate Fama-MacBeth (each value variant alone), by era ===")
    print(f"{'variant':14s} {'era':6s} {'mean_coef':>10s} {'t_stat':>8s}")
    for variant in VALUE_VARIANT_COLS:
        for era_label, era_records in halves.items():
            if not era_records:
                continue
            mean, t = _fama_macbeth(era_records, [variant])[variant]
            print(f"{variant:14s} {era_label:6s} {mean:10.5f} {t:8.2f}")
        print()

    print("=== Spearman IC, sliced to Financial Services / Real Estate only, by variant ===")
    print(f"{'variant':14s} {'sector':20s} {'mean_ic':>9s} {'t_stat':>8s} {'n_months':>9s}")
    for variant in VALUE_VARIANT_COLS:
        for focus in FOCUS_SECTORS:
            sliced = [(m, f[f["sector"] == focus]) for m, f in records]
            sliced = [(m, f) for m, f in sliced if len(f) >= MIN_SECTOR_SLICE]
            ics, _ns = _spearman_ic_series(sliced, variant)
            mean_ic, t, n = _ic_mean_t(ics)
            print(f"{variant:14s} {focus:20s} {mean_ic:9.4f} {t:8.2f} {n:9d}")
        print()

    print("########## Q2 (adapted - see module docstring DATA CONSTRAINT): quality_proxy IC by sector ##########\n")
    all_others = [(m, f[~f["sector"].isin(FOCUS_SECTORS)]) for m, f in records]
    slices = {
        "Financial Services": [(m, f[f["sector"] == "Financial Services"]) for m, f in records],
        "Real Estate": [(m, f[f["sector"] == "Real Estate"]) for m, f in records],
        "Everyone else": all_others,
    }
    print(f"{'sector-slice':20s} {'mean_ic':>9s} {'t_stat':>8s} {'n_months':>9s}")
    for label, sliced in slices.items():
        sliced = [(m, f) for m, f in sliced if len(f) >= MIN_SECTOR_SLICE]
        ics, _ns = _spearman_ic_series(sliced, "quality_proxy")
        mean_ic, t, n = _ic_mean_t(ics)
        print(f"{label:20s} {mean_ic:9.4f} {t:8.2f} {n:9d}")


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
