#!/usr/bin/env python3
"""
Value scoring architecture test: current live ABSOLUTE fixed-threshold curves vs
CROSS-SECTIONAL (peer-relative) and TIME-SERIES (own-history-relative) z-scoring, and the
HYBRID of the two - following MSCI's own documented factor-index methodology (fetched live this
session, https://www.msci.com/research-and-insights/blog-post/the-theory-of-value-relativity):
"z-score: zi = (xi - mu) / sigma ... across the universe" for the cross-sectional leg, "compares
a stock against its own 5-year history using z-scoring" for the time-series leg, and "a combined
approach may provide a more comprehensive valuation measure ... One Plus One May Equal More than
Two" for the recommended hybrid.

Built 2026-08-28 (goal: user directive "what does IBD/the best and brightest do... rethink what
we're doing and do it that way"). Prior sessions' research (fama_macbeth_composite_weights.py,
sector_relative_scoring_test_20260828.py) approximated the live Value pillar with a
CROSS-SECTIONAL z-score proxy for research convenience - but a direct read of
loaders/load_stock_scores.py::_score_value found the ACTUAL live formula uses fixed, hand-set
PIECEWISE ABSOLUTE THRESHOLDS (e.g. P/E<=10 -> one formula, <=20 -> another, <=35 -> another,
else another) with NO cross-sectional or time-series component at all - a materially different,
and per MSCI's own documented view, less complete construction than either research proxy
already tested. This script closes that gap: builds all FOUR variants side by side and tests
which actually predicts forward returns best, on the same live-formula PE/PB/PS inputs
(12%/30%/27% weights, renormalized to sum to 1 for this 3-component-only comparison - PEG/FCF/
dividend/margin-of-safety are unaffected by this question and excluded here).

Variants:
  (a) LIVE_CURVE: the EXACT piecewise absolute-threshold formulas copied from
      loaders/load_stock_scores.py::_score_value (pe_score/pb_score/ps_score blocks) - the
      CURRENT production behavior, not an approximation.
  (b) CROSS_SECTIONAL: universe-wide winsorize+z-score each month (MSCI's cross-sectional leg).
  (c) TIME_SERIES: each stock's OWN trailing 60-month (5yr) rolling z-score of that same raw
      ratio (MSCI's time-series leg) - min 24 months of history required, else falls back to
      that month's cross-sectional z-score (a stock needs enough of its own history before a
      time-series baseline means anything; this fallback keeps the sample from shrinking to
      only long-tenured names, same "don't manufacture bias via a stricter requirement than
      necessary" principle already used elsewhere in this repo's research scripts).
  (d) HYBRID: simple average of (b) and (c), per MSCI's own "combined approach" finding.

Controls: same 5 non-Value pillar proxies (growth/quality/stability/momentum/size) this repo's
composite-weights research already validates, rebuilt inline here to keep this script
self-contained (matches the CURRENT live formulas, not fama_macbeth_composite_weights.py's own
stale docstring - growth_proxy uses revenue_growth_1y).

Usage:
    python -m algo.research.value_absolute_curve_vs_relative_ranking_20260828 [options]
"""

import argparse
import logging
from datetime import datetime

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

logger = logging.getLogger(__name__)

CONTROL_COLS = ["growth_proxy", "quality_proxy", "stability_proxy", "momentum_proxy", "size_proxy"]
VALUE_VARIANT_COLS = ["value_live_curve", "value_cross_sectional", "value_time_series", "value_hybrid"]
TS_WINDOW = 60  # months (5yr)
TS_MIN_PERIODS = 24  # min months of own history before trusting a time-series z-score


def _zwinsor(s: pd.Series) -> pd.Series:
    s = s.replace([np.inf, -np.inf], np.nan)
    lo, hi = s.quantile([0.01, 0.99])
    s = s.clip(lo, hi)
    std = s.std()
    return (s - s.mean()) / std if std and std > 0 else s * 0.0


def _pe_score(pe: pd.Series) -> pd.Series:
    """Exact copy of _score_value's live P/E piecewise curve."""
    out = pd.Series(np.nan, index=pe.index)
    m1 = pe <= 10
    m2 = (pe > 10) & (pe <= 20)
    m3 = (pe > 20) & (pe <= 35)
    m4 = pe > 35
    out[m1] = 40 + pe[m1] * 2
    out[m2] = 60 + (pe[m2] - 10) * 4
    out[m3] = 100 - (pe[m3] - 20) * 2
    out[m4] = (70 - (pe[m4] - 35) * 1.4).clip(lower=0)
    return out


def _pb_score(pb: pd.Series) -> pd.Series:
    """Exact copy of _score_value's live P/B piecewise curve."""
    out = pd.Series(np.nan, index=pb.index)
    m1 = pb <= 1.0
    m2 = (pb > 1.0) & (pb <= 3.0)
    m3 = (pb > 3.0) & (pb <= 7.0)
    m4 = pb > 7.0
    out[m1] = 100.0
    out[m2] = 100 - ((pb[m2] - 1.0) / 2.0) * 30
    out[m3] = 70 - ((pb[m3] - 3.0) / 4.0) * 40
    out[m4] = (30 - (pb[m4] - 7.0) * 3).clip(lower=0)
    return out


def _ps_score(ps: pd.Series) -> pd.Series:
    """Exact copy of _score_value's live P/S piecewise curve."""
    out = pd.Series(np.nan, index=ps.index)
    m1 = ps <= 2.0
    m2 = (ps > 2.0) & (ps <= 6.0)
    m3 = (ps > 6.0) & (ps <= 15.0)
    m4 = ps > 15.0
    out[m1] = 100.0
    out[m2] = 100 - ((ps[m2] - 2.0) / 4.0) * 30
    out[m3] = 70 - ((ps[m3] - 6.0) / 9.0) * 40
    out[m4] = (30 - (ps[m4] - 15.0) * 1.5).clip(lower=0)
    return out


def _rolling_own_history_zscore(matrix: pd.DataFrame) -> pd.DataFrame:
    """Each cell -> z-score of that value against the SAME symbol's own trailing TS_WINDOW-month
    history (inclusive of the current month), min TS_MIN_PERIODS. NaN where insufficient history
    - caller fills that with the cross-sectional z-score for the same month (see module
    docstring's TIME_SERIES variant note)."""
    roll_mean = matrix.rolling(window=TS_WINDOW, min_periods=TS_MIN_PERIODS).mean()
    roll_std = matrix.rolling(window=TS_WINDOW, min_periods=TS_MIN_PERIODS).std()
    z = (matrix - roll_mean) / roll_std
    return z.replace([np.inf, -np.inf], np.nan)


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

    # Pass 1: build raw PE/PB/PS matrices (months x symbols) so the TIME_SERIES variant can
    # roll a window across each symbol's own column.
    logger.info("Pass 1: building raw PE/PB/PS matrices for the time-series leg")
    pe_raw = pd.DataFrame(index=months, columns=px.columns, dtype=float)
    pb_raw = pd.DataFrame(index=months, columns=px.columns, dtype=float)
    ps_raw = pd.DataFrame(index=months, columns=px.columns, dtype=float)
    for i, month in enumerate(months):
        v = value_monthly.get(month)
        if v is None or v.empty:
            continue
        price = px.iloc[i].reindex(v.index)
        pe = pd.Series(np.where(v["eps"] > 0, price / v["eps"], np.nan), index=v.index).clip(upper=200)
        pb = pd.Series(
            np.where(v["book_value_per_share"] > 0, price / v["book_value_per_share"], np.nan), index=v.index
        ).clip(upper=50)
        ps = pd.Series(np.where(v["sales_per_share"] > 0, price / v["sales_per_share"], np.nan), index=v.index).clip(
            upper=50
        )
        pe_raw.loc[month, pe.index] = pe.values
        pb_raw.loc[month, pb.index] = pb.values
        ps_raw.loc[month, ps.index] = ps.values

    logger.info("Computing rolling own-history z-scores (5yr window)")
    pe_ts_z = _rolling_own_history_zscore(pe_raw)
    pb_ts_z = _rolling_own_history_zscore(pb_raw)
    ps_ts_z = _rolling_own_history_zscore(ps_raw)
    # PE/PB "cheap" = LOW ratio, but z-score is signed so that HIGH raw value = HIGH z. Negate
    # so higher z consistently means "cheaper" in every variant, matching the live curve's
    # higher-score-is-cheaper convention.
    pe_ts_z = -pe_ts_z
    pb_ts_z = -pb_ts_z
    ps_ts_z = -ps_ts_z

    beta_window = 24
    vol_window = 12
    records: list[tuple[pd.Timestamp, pd.DataFrame]] = []

    logger.info("Pass 2: building full cross-sectional records")
    for i in range(beta_window, len(months) - 1):
        month = months[i]
        g = growth_monthly.get(month)
        v = value_monthly.get(month)
        q = quality_monthly.get(month)
        if g is None or v is None or q is None or g.empty or v.empty or q.empty:
            continue

        growth_proxy = -_zwinsor(g["revenue_growth_1y"])

        pe = pe_raw.loc[month].astype(float)
        pb = pb_raw.loc[month].astype(float)
        ps = ps_raw.loc[month].astype(float)

        # (a) LIVE_CURVE: exact production formulas, PE12/PB30/PS27 renormalized to sum to 1
        # for this 3-component-only comparison (12+30+27=69).
        pe_c, pb_c, ps_c = _pe_score(pe), _pb_score(pb), _ps_score(ps)
        value_live_curve = (12.0 / 69.0) * pe_c + (30.0 / 69.0) * pb_c + (27.0 / 69.0) * ps_c

        # (b) CROSS_SECTIONAL: universe z-score each month (MSCI's cross-sectional leg).
        value_cross_sectional = (
            (12.0 / 69.0) * _zwinsor(-pe) + (30.0 / 69.0) * _zwinsor(-pb) + (27.0 / 69.0) * _zwinsor(-ps)
        )

        # (c) TIME_SERIES: own 5yr-history z-score, fallback to cross-sectional z-score where
        # a symbol doesn't yet have TS_MIN_PERIODS of its own history.
        pe_ts = pe_ts_z.loc[month].astype(float) if month in pe_ts_z.index else pd.Series(np.nan, index=pe.index)
        pb_ts = pb_ts_z.loc[month].astype(float) if month in pb_ts_z.index else pd.Series(np.nan, index=pb.index)
        ps_ts = ps_ts_z.loc[month].astype(float) if month in ps_ts_z.index else pd.Series(np.nan, index=ps.index)
        pe_ts_filled = pe_ts.combine_first(_zwinsor(-pe))
        pb_ts_filled = pb_ts.combine_first(_zwinsor(-pb))
        ps_ts_filled = ps_ts.combine_first(_zwinsor(-ps))
        value_time_series = (12.0 / 69.0) * pe_ts_filled + (30.0 / 69.0) * pb_ts_filled + (27.0 / 69.0) * ps_ts_filled

        value_hybrid = 0.5 * (value_cross_sectional + value_time_series)

        market_cap = px.iloc[i].reindex(v.index) * v["shares_diluted"]
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
                "value_live_curve": value_live_curve,
                "value_cross_sectional": value_cross_sectional,
                "value_time_series": value_time_series,
                "value_hybrid": value_hybrid,
                "growth_proxy": growth_proxy,
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
        complete = raw.dropna(subset=[*VALUE_VARIANT_COLS, *CONTROL_COLS])
        if len(complete) < min_cross_section:
            continue
        complete = complete.copy()
        # value_live_curve is already 0-100 scale (not z-scored) by construction - z-score it
        # too so its regression coefficient is on the same standardized scale as the other 3
        # variants (a fair apples-to-apples t-stat comparison, not a units artifact).
        for col in [*VALUE_VARIANT_COLS, *CONTROL_COLS]:
            complete[col] = _zwinsor(complete[col])
        records.append((month, complete))

    if not records:
        raise RuntimeError("No usable complete-case cross-sectional months")

    sizes = [len(f) for _, f in records]
    print(f"Usable complete-case cross-sectional months: {len(records)}  ({records[0][0]} to {records[-1][0]})")
    print(f"Median cross-section size: {int(np.median(sizes))}\n")

    split = len(records) // 2
    eras = {"FULL": records, "ERA1": records[:split], "ERA2": records[split:]}

    print("=== Multivariate Fama-MacBeth (each Value variant + 5 pillar controls), by era ===")
    print(f"{'variant':22s} {'era':6s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
    for variant in VALUE_VARIANT_COLS:
        for era_label, era_records in eras.items():
            result = _fama_macbeth(era_records, [variant, *CONTROL_COLS])
            mean, t = result[variant]
            print(f"{variant:22s} {era_label:6s} {mean:10.5f} {t:8.2f} {len(era_records):9d}")
        print()

    print("=== Univariate Fama-MacBeth (each Value variant alone), by era ===")
    print(f"{'variant':22s} {'era':6s} {'mean_coef':>10s} {'t_stat':>8s}")
    for variant in VALUE_VARIANT_COLS:
        for era_label, era_records in eras.items():
            mean, t = _fama_macbeth(era_records, [variant])[variant]
            print(f"{variant:22s} {era_label:6s} {mean:10.5f} {t:8.2f}")
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
