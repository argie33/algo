#!/usr/bin/env python3
"""
Fama-MacBeth test of the TOP-LEVEL composite_score combination (Quality/Growth/Value/Risk/
Momentum pillar weights).

Built 2026-08-25, REBUILT 2026-08-27, REBUILT AGAIN 2026-08-31 (composite-score research
session - this script had drifted stale/BROKEN against main's live pillar formulas yet again,
same recurring failure mode as the 2026-08-27 rebuild's own opening paragraph describes).
Concretely, as of this rebuild: (1) Size was retired ENTIRELY from BASE_PILLAR_WEIGHTS on
2026-08-28 (5 keys now: quality/growth/value/risk/momentum) - the pre-rebuild script still
mapped size_proxy -> BASE_PILLAR_WEIGHTS["size"], which KeyErrors on the current dict, i.e. this
script could not even RUN before this rebuild. (2) growth_proxy was a single input
(-book_value_growth) from a since-abandoned single-input Growth design; Growth was restored to
an 11-field equal-weighted blend on 2026-08-28 (explicit user override of that same session's
own evidence - see GROWTH_SCORE_FIELDS in loaders/load_stock_scores.py). (3) stability_proxy
(Risk) still included downside_vol_60d (removed from live scoring 2026-08-28) and omitted
vol_252d (added this same session, 2026-08-31, alongside beta's no-longer-clipped-to-0 fix from
2026-08-28/29) at the wrong weights entirely. (4) value_proxy's PE/PB/PS weights (12/30/27) are
several reweights stale (live is currently 12/39/34). Bottom line: the evidence that justified
today's BASE_PILLAR_WEIGHTS (quality=0.20/growth=0.24/value=0.27/risk=0.19/momentum=0.10) was
generated against pillar formulas that have since changed multiple times - this rebuild exists
to re-derive that evidence honestly against what's ACTUALLY live on main right now, verified
directly against loaders/load_stock_scores.py line-by-line before writing a single proxy below
(not copied from any docstring's prose, several of which were themselves found stale mid-verify -
see MEMORY.md's stock_scores section for the broader pattern: multiple pillar formulas described
there as "current" turned out to only exist in an uncommitted worktree, not on main).

Pillar proxies (z-scored components combined at each pillar's LIVE weight ratios - NOT
independently re-derived per-component weights, since that's what the per-pillar scripts already
tested; this script answers the separate top-level question), verified against
loaders/load_stock_scores.py directly on 2026-08-31:

- growth_proxy: equal-weighted average of z-scored [eps_growth_1y, eps_growth_3y, eps_growth_5y,
  revenue_growth_1y, revenue_growth_3y, revenue_growth_5y, sustainable_growth_rate,
  quarterly_growth_momentum, earnings_growth_4q_avg] - 9 of the live 12-field
  GROWTH_SCORE_FIELDS blend (75% coverage of the live equal-weight formula).

  CORRECTED 2026-09-01 (goal session: "understand our data gaps before resuming Fama-MacBeth" -
  live-verified against loaders/load_stock_scores.py's GROWTH_SCORE_FIELDS directly, which is
  now 12 fields, not the 11 this docstring previously claimed - a further instance of this
  exact script drifting stale, caught while trying to act on a PRIOR correction attempt).
  net_income_growth_yoy/fcf_growth_yoy were DROPPED from GROWTH_PROXY_COLS entirely - neither
  is in the live 12-field list anymore (both were removed from production in a later
  2026-08-31 pass than this script's own last verify), so testing them was testing fields that
  don't exist in production - not a partial-coverage gap, a stale-test bug.

  SAME-DAY LATER PASS: quarterly_growth_momentum/earnings_growth_4q_avg ADDED - both are
  derived from QUARTERLY EPS/revenue history and already have a working point-in-time
  reconstruction in algo/research/growth_quarterly_earnings_quality_candidates.py (built
  2026-08-27 for an isolated per-field FM test), reused here rather than rebuilt. Only 3 of
  the original 5 untested fields remain excluded now (forward_eps_growth_current_fy,
  forward_eps_growth_next_fy, forward_revenue_growth_next_fy) - genuinely not buildable:
  `analyst_earnings_estimates` currently spans only 2026-08-03 to 2026-08-31 (25 distinct
  dates, live-queried), a single snapshot, not history; cannot be reconstructed at all yet, let
  alone as a "proxy-code fix only" (a prior version of this same correction mistakenly claimed
  otherwise in MEMORY.md - corrected there too). This is now an irreducible data-depth gap, not
  an unstarted-project gap - closing it requires waiting for analyst_earnings_estimates to
  accumulate real history over time, not more engineering effort today.

  sustainable_growth_rate IS newly reconstructed here (not in the pre-2026-08-31 version
  of this script) via the same ROE x retention-ratio formula
  load_value_quality_growth_metrics.py uses (net_income/stockholders_equity x
  (1 - dividends_paid/|net_income|)), sourced from annual_balance_sheet.stockholders_equity and
  annual_cash_flow.dividends_paid (NULL dividends_paid treated as 0, i.e. full retention - a
  simplification of production's dividend_data-table fallback logic for genuinely-never-paid
  dividends, disclosed here not hidden). NOT sign-flipped anywhere - matches live's plain
  "higher growth = higher score" convention exactly (2026-08-28 user override of this file's own
  prior growth-reversal research, see _score_growth's docstring).

- value_proxy: P/E (12%) + P/B (39%) + P/S (34%), renormalized over 85 of the live 100
  (Forward P/E's 4% and Dividend Yield's 11% EXCLUDED - forward_pe has ~4 weeks of real
  analyst-estimate history in this DB, not enough for any point-in-time panel; a monthly
  point-in-time dividend history reconstruction is a materially separate research effort not
  attempted here). Live PE/PB/PS are now scored via a POST-RUN CROSS-SECTIONAL PERCENTILE rank
  (update_value_multiples_percentiles()), not fixed curves - a cross-sectional z-score of
  -PE/-PB/-PS (lower ratio = better) is this proxy's analogue of that percentile rank, same
  z-score convention this script already uses for every other pillar.

- quality_proxy: ROE 11% + ROA 18% + ROCE 18% + FCF Margin 15% + (-Debt/Equity) 18% +
  (-Margin Volatility 3Y) 7% + Asset Turnover 7% + Gross Profitability 7% (nominal 101, matches
  _score_quality's current 8-component live weights exactly, unchanged from the 2026-08-27
  rebuild - re-verified against the live docstring this pass, still accurate). Altman Z
  excluded, computed/persisted but deliberately unscored as a discrete distress classifier, not
  part of the live weighted formula either.

- stability_proxy (maps to live BASE_PILLAR_WEIGHTS["risk"]): (-vol_60d)*0.45 + (-vol_252d)*0.20
  + (-|beta-1|)*0.20 + max_dd_1y*0.15 - matches the Risk pillar's 2026-08-31 rework exactly
  (downside_vol_60d fully removed from live scoring; vol_252d added; beta is NOT clipped to a
  floor of 0 here, matching the live 2026-08-28/29 fix that removed that clip since beta is a
  signed regression coefficient, not a floor-0 metric). FIDELITY UPGRADE this rebuild: vol_60d/
  vol_252d/max_dd_1y are now computed from the DAILY price panel already fetched for Momentum
  (60/252 actual trading days), not the prior version's 12-MONTH rolling-monthly-return
  approximation (which was silently a ~3-month-vs-12-month mismatch for what was meant to proxy
  a 60-trading-day window - a real, previously undisclosed fidelity gap in every prior version
  of this script, not just a stale-weights problem). Beta is LEFT on the monthly 24-month
  regression window (not upgraded to a matching daily window) - a known, disclosed
  approximation carried over from every prior version of this script, not attempted to fix here
  to keep this rebuild's scope to the weight/formula staleness it was written to address.

- momentum_proxy: mom_3m*0.20 + mom_12_1*0.35 + avg(rsi_14, macd_sign)*0.37 +
  avg(price_vs_sma_50, price_vs_sma_200)*0.08 - unchanged from the 2026-08-27 rebuild,
  re-verified against _score_momentum's actual code (not just its docstring prose) this pass:
  RSI/MACD are score-then-averaged in production (two 0-100 sub-scores), but macd_sign is
  ALREADY a sign-only extraction here (np.sign(macd_line) in
  fama_macbeth_momentum_factors.py's compute_daily_indicators), so z-scoring these two
  components and averaging them is a faithful linear analogue of production's "average the two
  0-100 sub-scores" treatment, not a mismatched approximation.

Each raw component is winsorized/z-scored the same way as its origin script BEFORE being
combined into the pillar proxy, then the resulting pillar proxies are z-scored AGAIN at the top
level before the final regression - so the final coefficients are directly comparable "how much
does a 1-std move in this whole pillar's current formula predict forward return, controlling for
the others" numbers.

Same dual-regime discipline as the 2026-08-27 rebuild (COMPLETE-CASE strict dropna vs
PARTIAL-AVAILABILITY 0-imputed) - a pillar weight is only evidence-backed here if directionally
consistent across BOTH regimes AND both half-split eras.

Usage:
    python -m algo.research.fama_macbeth_composite_weights [options]
"""

import argparse
import logging
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Lasso, Ridge

from algo.research.fama_macbeth_growth_factors import REPORTING_LAG_DAYS, build_growth_panel, merge_asof_monthly
from algo.research.fama_macbeth_momentum_factors import (
    build_month_end_panel,
    compute_daily_indicators,
)
from algo.research.fama_macbeth_momentum_factors import (
    fetch_daily_prices as fetch_daily_close,
)
from algo.research.fama_macbeth_price_factors import (
    _fama_macbeth,
    _trailing_cumret,
    fetch_month_end_prices,
)
from algo.research.fama_macbeth_quality_factors import build_quality_panel, fetch_annual_quality_fundamentals
from algo.research.growth_quarterly_earnings_quality_candidates import (
    build_panel as build_quarterly_earnings_panel,
)
from algo.research.growth_quarterly_earnings_quality_candidates import (
    fetch_quarterly_panel,
)
from loaders.load_stock_scores import BASE_PILLAR_WEIGHTS
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

# 5 pillars, matching loaders/load_stock_scores.py's CURRENT BASE_PILLAR_WEIGHTS keys exactly
# (quality/growth/value/risk/momentum). No size_proxy - Size was retired entirely 2026-08-28,
# BASE_PILLAR_WEIGHTS has no "size" key any more (the pre-2026-08-31 version of this script
# still had one, which is why it could not run - see module docstring).
PILLAR_COLS = ["growth_proxy", "value_proxy", "quality_proxy", "stability_proxy", "momentum_proxy"]

PILLAR_TO_LIVE_KEY = {
    "growth_proxy": "growth",
    "value_proxy": "value",
    "quality_proxy": "quality",
    "stability_proxy": "risk",
    "momentum_proxy": "momentum",
}

GROWTH_PROXY_COLS = [
    "eps_growth_1y",
    "eps_growth_3y",
    "eps_growth_5y",
    "revenue_growth_1y",
    "revenue_growth_3y",
    "revenue_growth_5y",
    "sustainable_growth_rate",
    "quarterly_growth_momentum",
    "earnings_growth_4q_avg",
]
# quarterly_growth_momentum/earnings_growth_4q_avg ADDED 2026-09-01 (same /goal session as the
# value_proxy/stability_proxy fix in dfdb110e7 - "make sure we have the full dataset before
# resuming FM"). These 2 of the 5 previously-excluded live GROWTH_SCORE_FIELDS turned out to
# already have a working point-in-time reconstruction -
# algo/research/growth_quarterly_earnings_quality_candidates.py (built 2026-08-27 to
# isolated-FM-test them individually) - reused here rather than rebuilt, closing this proxy from
# 7/12 (58%) to 9/12 (75%) of the live 12-field blend. The other 3 (forward_eps_growth_current_fy/
# next_fy, forward_revenue_growth_next_fy) remain excluded - genuinely not buildable yet,
# analyst_earnings_estimates still has only ~1 month of real snapshot history, not a point-in-time
# panel. Note: quarterly_growth_momentum was already isolated-tested and found a clean null
# (t=-1.41) and earnings_growth_4q_avg failed this project's own both-eras-robust bar (see
# growth_quarterly_earnings_quality_candidates_tested_20260827 in memory) - live production
# still scores both anyway per the user's standing "match published Growth methodology, not just
# whichever field last won an isolated FM test" override (GROWTH_SCORE_FIELDS RESTORED
# 2026-08-28). Including them here even though they didn't clear the isolated bar is deliberate:
# this proxy's job is to test the LIVE formula as-is, not to re-litigate which fields belong in
# it.


def _zwinsor(s: pd.Series) -> pd.Series:
    s = s.replace([np.inf, -np.inf], np.nan)
    lo, hi = s.quantile([0.01, 0.99])
    s = s.clip(lo, hi)
    std = s.std()
    return (s - s.mean()) / std if std and std > 0 else s * 0.0


def build_value_panel_raw() -> pd.DataFrame:
    fund = fetch_annual_value_fundamentals()
    shares = fund["shares_diluted"]
    out = fund[["symbol", "fiscal_year"]].copy()
    out["eps"] = fund["eps"]
    out["book_value_per_share"] = fund["stockholders_equity"] / shares
    out["sales_per_share"] = fund["revenue"] / shares
    out["shares_diluted"] = shares
    out["known_date"] = pd.to_datetime(fund["fiscal_year"].astype(str) + "-12-31") + pd.Timedelta(
        days=REPORTING_LAG_DAYS
    )
    return out.dropna(subset=["known_date"])


def fetch_annual_value_fundamentals() -> pd.DataFrame:
    """Point-in-time PE/PB/PS inputs - eps, stockholders_equity, revenue, shares_diluted."""
    sql = """
        SELECT i.symbol, i.fiscal_year,
               COALESCE(i.diluted_eps, i.eps) AS eps,
               i.revenue,
               b.stockholders_equity,
               i.shares_outstanding_diluted AS shares_diluted
        FROM annual_income_statement i
        LEFT JOIN annual_balance_sheet b ON b.symbol = i.symbol AND b.fiscal_year = i.fiscal_year
        WHERE i.fiscal_year BETWEEN 2000 AND 2026
          AND COALESCE(i.data_unavailable, false) = false
          AND i.shares_outstanding_diluted > 0
        ORDER BY i.symbol, i.fiscal_year
    """
    with DatabaseContext("read") as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    df = pd.DataFrame(
        rows, columns=["symbol", "fiscal_year", "eps", "revenue", "stockholders_equity", "shares_diluted"]
    )
    for col in ["eps", "revenue", "stockholders_equity", "shares_diluted"]:
        df[col] = df[col].astype(float)
    return df


def fetch_growth_and_sgr_fundamentals() -> pd.DataFrame:
    """Annual fundamentals panel for growth_proxy: reuses fama_macbeth_growth_factors'
    fetch_annual_fundamentals() columns (revenue/eps/net_income/operating_income/fcf/ocf/
    total_assets) PLUS stockholders_equity and dividends_paid, needed only for
    sustainable_growth_rate (production: net_income/stockholders_equity x
    (1 - dividends_paid/|net_income|) x 100). Extra columns are ignored by
    build_growth_panel() (it only reads its own known column set), so this is a strict superset
    safe to pass through unchanged.
    """
    sql = """
        SELECT i.symbol, i.fiscal_year,
               i.revenue, COALESCE(i.diluted_eps, i.eps) AS eps,
               i.net_income, i.operating_income,
               c.free_cash_flow, c.operating_cash_flow, c.dividends_paid,
               b.total_assets, b.stockholders_equity
        FROM annual_income_statement i
        LEFT JOIN annual_cash_flow c ON c.symbol = i.symbol AND c.fiscal_year = i.fiscal_year
        LEFT JOIN annual_balance_sheet b ON b.symbol = i.symbol AND b.fiscal_year = i.fiscal_year
        WHERE i.fiscal_year BETWEEN 2000 AND 2026
          AND COALESCE(i.data_unavailable, false) = false
        ORDER BY i.symbol, i.fiscal_year
    """
    with DatabaseContext("read") as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    df = pd.DataFrame(
        rows,
        columns=[
            "symbol",
            "fiscal_year",
            "revenue",
            "eps",
            "net_income",
            "operating_income",
            "fcf",
            "ocf",
            "dividends_paid",
            "total_assets",
            "stockholders_equity",
        ],
    )
    for col in [
        "revenue",
        "eps",
        "net_income",
        "operating_income",
        "fcf",
        "ocf",
        "dividends_paid",
        "total_assets",
        "stockholders_equity",
    ]:
        df[col] = df[col].astype(float)
    return df


def _compute_sgr(fund: pd.DataFrame) -> pd.Series:
    """Sustainable growth rate = ROE x retention ratio x 100, same formula as
    load_value_quality_growth_metrics.py. dividends_paid NULL -> 0 (full retention) - a
    simplification of production's dividend_data-table fallback for genuinely-never-paid
    dividends, disclosed not hidden. Only defined where stockholders_equity > 0 and
    net_income != 0, matching production's own guard."""
    se = fund["stockholders_equity"]
    ni = fund["net_income"]
    div = fund["dividends_paid"].fillna(0.0)
    valid = (se > 0) & (ni != 0)
    out = pd.Series(np.nan, index=fund.index)
    roe = ni[valid] / se[valid]
    retention = 1.0 - (div[valid] / ni[valid].abs())
    out[valid] = roe * retention * 100.0
    return out


def build_growth_and_sgr_panel(fund: pd.DataFrame) -> pd.DataFrame:
    growth_panel = build_growth_panel(fund)  # eps/revenue/ni/fcf growth + known_date
    sgr = _compute_sgr(fund)
    sgr_panel = fund[["symbol", "fiscal_year"]].copy()
    sgr_panel["sustainable_growth_rate"] = sgr
    return growth_panel.merge(sgr_panel, on=["symbol", "fiscal_year"], how="left")


def build_pillar_proxy_records(
    start_date: str, end_date: str, min_cross_section: int
) -> tuple[
    list[tuple[pd.Timestamp, pd.DataFrame]],
    list[tuple[pd.Timestamp, pd.DataFrame]],
    list[tuple[pd.Timestamp, pd.DataFrame]],
]:
    """Builds the monthly pillar-proxy panel once. Returns (records_partial, records_complete,
    records_raw) - records_raw is the SAME per-month frame as records_complete's source before
    the top-level per-month z-score/winsorize/impute step, added 2026-08-31 (composite-score
    research session, Question B) so downstream scripts (e.g. a percentile-rank-vs-z-score
    comparison) can derive an alternative per-month normalization from the identical underlying
    data instead of re-running this same expensive DB fetch + panel-build a second time. Each
    pillar proxy in records_raw is still a weighted average of z-scored SUB-components (e.g.
    growth_proxy = average of 7 individually z-scored growth fields) - only the top-level
    per-month cross-sectional normalization of the PILLAR proxy itself is skipped here, matching
    exactly what records_complete/records_partial do next.
    """
    logger.info("Building fundamentals panels (growth/value/quality)")
    growth_fund = fetch_growth_and_sgr_fundamentals()
    growth_panel = build_growth_and_sgr_panel(growth_fund)
    quarterly_fund = fetch_quarterly_panel()
    quarterly_panel = build_quarterly_earnings_panel(quarterly_fund)
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
    daily_wide = daily_close.pivot(index="date", columns="symbol", values="px").sort_index()
    daily_ret = daily_wide.pct_change(fill_method=None)
    daily_dates = daily_wide.index

    daily_close = compute_daily_indicators(daily_close)
    _px_daily, indicators = build_month_end_panel(daily_close)
    for key in indicators:
        indicators[key] = (
            indicators[key].set_axis(pd.PeriodIndex(indicators[key].index, freq="M")).reindex(months_period)
        )

    growth_monthly = merge_asof_monthly(
        months,
        growth_panel,
        cols=[c for c in GROWTH_PROXY_COLS if c not in ("quarterly_growth_momentum", "earnings_growth_4q_avg")],
    )
    quarterly_monthly = merge_asof_monthly(
        months, quarterly_panel, cols=["quarterly_growth_momentum", "earnings_growth_4q_avg"]
    )
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

    beta_window = 24  # months - beta left on the monthly window, see module docstring
    # Map each month-end to the closest actual trading day <= that month-end in the DAILY
    # panel, so vol_60d/vol_252d/max_dd_1y can be computed from real 60/252 TRADING-DAY windows
    # instead of the prior version's 12-month rolling-monthly-return approximation.
    month_to_daily_idx: dict[pd.Timestamp, int | None] = {}
    for month in months:
        cutoff = pd.Timestamp(month) + pd.offsets.MonthEnd(0)
        pos = int(daily_dates.searchsorted(cutoff, side="right")) - 1
        month_to_daily_idx[month] = pos if pos >= 0 else None

    records_partial: list[tuple[pd.Timestamp, pd.DataFrame]] = []
    records_complete: list[tuple[pd.Timestamp, pd.DataFrame]] = []
    records_raw: list[tuple[pd.Timestamp, pd.DataFrame]] = []

    for i in range(beta_window, len(months) - 1):
        month = months[i]
        daily_idx = month_to_daily_idx.get(month)

        g = growth_monthly.get(month)
        v = value_monthly.get(month)
        q = quality_monthly.get(month)
        if g is None or v is None or q is None or g.empty or v.empty or q.empty or daily_idx is None:
            continue
        if daily_idx < 251:  # need a full 252-trading-day window
            continue

        qtr = quarterly_monthly.get(month)
        g = (
            g.join(qtr, how="left")
            if qtr is not None
            else g.assign(quarterly_growth_momentum=np.nan, earnings_growth_4q_avg=np.nan)
        )

        growth_cols_z = [_zwinsor(g[c]) for c in GROWTH_PROXY_COLS]
        growth_proxy = sum(growth_cols_z) / len(growth_cols_z)

        price = px.iloc[i].reindex(v.index)
        pe = np.where(v["eps"] > 0, price / v["eps"], np.nan)
        pb = np.where(v["book_value_per_share"] > 0, price / v["book_value_per_share"], np.nan)
        ps = np.where(v["sales_per_share"] > 0, price / v["sales_per_share"], np.nan)
        # value_proxy: PE27/PB27/PS27 (equal-weighted, live-verified 2026-09-01 - see module
        # docstring's CORRECTED note) renormalized over 81 (live's remaining 19 - ForwardPE9/
        # DividendYield10 - excluded). CORRECTED 2026-09-01: this was PE12/PB39/PS34/85 (stale
        # since before the 2026-09-01 equal-weight reweight - see
        # value_equal_weight_and_pe_reason_bug_fixed_20260901 in memory).
        value_proxy = (
            (27.0 / 81.0) * _zwinsor(-pd.Series(pe, index=v.index))
            + (27.0 / 81.0) * _zwinsor(-pd.Series(pb, index=v.index))
            + (27.0 / 81.0) * _zwinsor(-pd.Series(ps, index=v.index))
        )

        # quality_proxy: ROE11/ROA18/ROCE18/FCFmargin15/(-D2E)18/(-marginvol)7/assetturnover7/
        # grossprofitability7, nominal 101 - matches _score_quality's current 8-component live
        # weights exactly (re-verified 2026-08-31, unchanged from 2026-08-27).
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

        # Risk (stability_proxy): vol_60d/vol_252d/max_dd_1y from the DAILY panel (real
        # 60/252-trading-day windows), beta from the monthly 24-month window (unchanged
        # approximation - see module docstring).
        win60 = daily_ret.iloc[daily_idx - 59 : daily_idx + 1]
        win252 = daily_ret.iloc[daily_idx - 251 : daily_idx + 1]
        vol_60d = win60.std() * np.sqrt(252)
        vol_252d = win252.std() * np.sqrt(252)
        px_window_252 = daily_wide.iloc[daily_idx - 251 : daily_idx + 1]
        max_dd_1y = (px_window_252 / px_window_252.cummax() - 1.0).min()

        winb = ret.iloc[i - beta_window + 1 : i + 1]
        mkt_win = mkt.iloc[i - beta_window + 1 : i + 1]
        mkt_var = mkt_win.var()
        beta = (
            winb.apply(lambda col, m=mkt_win: col.cov(m)) / mkt_var
            if mkt_var and mkt_var > 0
            else pd.Series(np.nan, index=winb.columns)
        )
        beta = beta.reindex(vol_60d.index)
        # CORRECTED 2026-09-01 (live-reverified in loaders/load_stock_scores.py's _score_risk):
        # live weights are now vol_60d 45 + vol_252d 15 + beta 15 + max_dd_1y 10 + Liquidity 15
        # (Liquidity added 2026-09-01, avg_dollar_volume_20d-based - not reconstructed here, no
        # point-in-time dollar-volume panel built yet, same "disclosed exclusion" convention as
        # value_proxy's forward_pe/dividend_yield). Renormalized over the remaining 85.
        stability_proxy = (
            (45.0 / 85.0) * _zwinsor(-vol_60d)
            + (15.0 / 85.0) * _zwinsor(-vol_252d)
            + (15.0 / 85.0) * _zwinsor(-(beta - 1.0).abs())
            + (10.0 / 85.0) * _zwinsor(max_dd_1y)
        )

        mom_3m = _trailing_cumret(px, i, 3)
        mom_12_1 = _trailing_cumret(px, i - 1, 11)
        rsi = indicators["rsi_14"].iloc[i]
        macd_sign = indicators["macd_sign"].iloc[i]
        tech_trend = (_zwinsor(rsi) + _zwinsor(macd_sign)) / 2.0
        sma_avg = (
            _zwinsor(indicators["price_vs_sma_50"].iloc[i]) + _zwinsor(indicators["price_vs_sma_200"].iloc[i])
        ) / 2.0
        momentum_proxy = 0.20 * _zwinsor(mom_3m) + 0.35 * _zwinsor(mom_12_1) + 0.37 * tech_trend + 0.08 * sma_avg

        fwd_ret = ret.iloc[i + 1]

        raw = pd.DataFrame(
            {
                "growth_proxy": growth_proxy,
                "value_proxy": value_proxy,
                "quality_proxy": quality_proxy,
                "stability_proxy": stability_proxy,
                "momentum_proxy": momentum_proxy,
                "fwd_ret": fwd_ret,
            }
        )
        raw = raw.replace([np.inf, -np.inf], np.nan)
        raw = raw.dropna(subset=["fwd_ret"])
        raw = raw[(raw["fwd_ret"] > -0.95) & (raw["fwd_ret"] < 5.0)]
        if len(raw) < min_cross_section:
            continue

        records_raw.append((month, raw.copy()))

        complete = raw.dropna(subset=PILLAR_COLS)
        if len(complete) >= min_cross_section:
            complete = complete.copy()
            for col in PILLAR_COLS:
                complete[col] = _zwinsor(complete[col])
            records_complete.append((month, complete))

        partial = raw.copy()
        for col in PILLAR_COLS:
            partial[col] = _zwinsor(partial[col]).fillna(0.0)
        records_partial.append((month, partial))

    if not records_partial:
        raise RuntimeError("No usable cross-sectional months - pillars may not overlap enough symbols")
    if not records_complete:
        logger.warning("No complete-case months cleared min_cross_section - skipping that comparison")

    return records_partial, records_complete, records_raw


def run(start_date: str, end_date: str, min_cross_section: int) -> None:
    records_partial, records_complete, _records_raw = build_pillar_proxy_records(
        start_date, end_date, min_cross_section
    )

    def _report(records: list[tuple[pd.Timestamp, pd.DataFrame]], label: str) -> None:
        sizes = [len(f) for _, f in records]
        print(f"\n########## {label} ##########")
        print(f"Usable cross-sectional months: {len(records)}  ({records[0][0]} to {records[-1][0]})")
        print(f"Median cross-section size: {int(np.median(sizes))}\n")

        pooled = pd.concat([f for _, f in records], ignore_index=True)
        print("=== Pooled pillar-proxy pairwise correlations (multicollinearity diagnostic) ===")
        print(pooled[PILLAR_COLS].corr().round(2).to_string())

        print(f"\n=== Multivariate Fama-MacBeth: {label} ===")
        print(f"{'pillar':18s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
        multi = _fama_macbeth(records, PILLAR_COLS)
        for name, (mean, t) in multi.items():
            print(f"{name:18s} {mean:10.5f} {t:8.2f} {len(records):9d}")

        print(f"\n=== Univariate Fama-MacBeth: {label} ===")
        print(f"{'pillar':18s} {'mean_coef':>10s} {'t_stat':>8s}")
        for c in PILLAR_COLS:
            uni = _fama_macbeth(records, [c])
            mean, t = uni[c]
            print(f"{c:18s} {mean:10.5f} {t:8.2f}")

        split_idx = len(records) // 2
        first_half, second_half = records[:split_idx], records[split_idx:]
        for half_label, half in (
            (f"FIRST HALF ({first_half[0][0]} to {first_half[-1][0]})", first_half),
            (f"SECOND HALF ({second_half[0][0]} to {second_half[-1][0]})", second_half),
        ):
            if not half:
                continue
            print(f"\n=== Half-split robustness ({label}), {half_label} ===")
            print(f"{'pillar':18s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
            half_multi = _fama_macbeth(half, PILLAR_COLS)
            for name, (mean, t) in half_multi.items():
                print(f"{name:18s} {mean:10.5f} {t:8.2f} {len(half):9d}")

    _report(records_partial, "PARTIAL-AVAILABILITY (0-imputed missing pillars, larger sample)")
    if records_complete:
        _report(records_complete, "COMPLETE-CASE (strict dropna, no imputation, smaller sample)")

        multi_partial = _fama_macbeth(records_partial, PILLAR_COLS)
        multi_complete = _fama_macbeth(records_complete, PILLAR_COLS)
        print("\n########## AGREEMENT CHECK: partial-availability vs complete-case ##########")
        print(f"{'pillar':18s} {'t_partial':>10s} {'t_complete':>11s} {'agree?':>8s}")
        for c in PILLAR_COLS:
            t_p = multi_partial[c][1]
            t_c = multi_complete[c][1]
            same_sign = (t_p > 0) == (t_c > 0)
            both_sig = abs(t_p) > 2.0 and abs(t_c) > 2.0
            verdict = "ROBUST" if (same_sign and both_sig) else ("same-sign" if same_sign else "DISAGREE")
            print(f"{c:18s} {t_p:10.2f} {t_c:11.2f} {verdict:>8s}")
        print(
            "\nOnly a pillar marked ROBUST here (significant AND same-signed in both the imputed"
            " and the strict-complete-case regime) should be treated as evidence for a"
            " BASE_PILLAR_WEIGHTS change. 'same-sign'-only or DISAGREE means the imputed sample's"
            " larger size is likely doing the work, not a real relationship."
        )
    else:
        print("\n(No complete-case comparison available - see warning above.)")

    live_weights = " ".join(f"{k}={v}" for k, v in BASE_PILLAR_WEIGHTS.items())
    print(f"\nCurrent live BASE_PILLAR_WEIGHTS: {live_weights}")

    print("\n=== ML vs LIVE-LINEAR composite: walk-forward OOS head-to-head (partial-availability sample) ===")
    panel_rows = []
    for month, frame in records_partial:
        f = frame.copy()
        f["month"] = month
        panel_rows.append(f)
    panel = pd.concat(panel_rows, ignore_index=True)
    panel["year"] = pd.to_datetime(panel["month"]).dt.year
    years = sorted(panel["year"].unique())
    first_test_idx = max(1, int(len(years) * 0.6))
    test_years = years[first_test_idx:]

    live_weight_map = {c: BASE_PILLAR_WEIGHTS[k] for c, k in PILLAR_TO_LIVE_KEY.items()}

    ridge_alphas = [1.0, 10.0, 100.0]
    lasso_alphas = [1e-5, 1e-4, 1e-3, 1e-2]
    model_preds: dict[str, list[float]] = {
        "ml_tree(d4,l2=1)": [],
        **{f"ridge_a{a:g}": [] for a in ridge_alphas},
        **{f"lasso_a{a:g}": [] for a in lasso_alphas},
    }
    lasso_coefs: dict[float, list[np.ndarray[Any, Any]]] = {a: [] for a in lasso_alphas}
    live_pred, actual = [], []

    for test_year in test_years:
        train = panel[panel["year"] < test_year]
        test = panel[panel["year"] == test_year]
        if train.empty or len(test) < min_cross_section:
            continue
        x_train, y_train = train[PILLAR_COLS], train["fwd_ret"]
        x_test = test[PILLAR_COLS]

        tree = HistGradientBoostingRegressor(
            max_iter=200, max_depth=4, learning_rate=0.05, l2_regularization=1.0, random_state=0
        )
        tree.fit(x_train, y_train)
        model_preds["ml_tree(d4,l2=1)"].extend(tree.predict(x_test).tolist())

        for a in ridge_alphas:
            ridge = Ridge(alpha=a)
            ridge.fit(x_train, y_train)
            model_preds[f"ridge_a{a:g}"].extend(ridge.predict(x_test).tolist())

        for a in lasso_alphas:
            lasso = Lasso(alpha=a, max_iter=5000)
            lasso.fit(x_train, y_train)
            model_preds[f"lasso_a{a:g}"].extend(lasso.predict(x_test).tolist())
            lasso_coefs[a].append(lasso.coef_.copy())

        live_linear = sum(test[c] * w for c, w in live_weight_map.items())
        live_pred.extend(live_linear.tolist())
        actual.extend(test["fwd_ret"].tolist())
        logger.info(f"{test_year}: train_rows={len(train)} test_rows={len(test)} done")

    if live_pred:
        live_s = pd.Series(live_pred)
        act_s = pd.Series(actual)
        print(f"OOS symbol-months: {len(live_pred)}, test years: {test_years}")
        print(f"{'method':30s} {'Spearman':>10s} {'Pearson':>10s}")
        print(
            f"{'live_linear_fixed_pct':30s} {live_s.corr(act_s, method='spearman'):10.4f} {live_s.corr(act_s, method='pearson'):10.4f}"
        )
        for name, preds in model_preds.items():
            s = pd.Series(preds)
            print(f"{name:30s} {s.corr(act_s, method='spearman'):10.4f} {s.corr(act_s, method='pearson'):10.4f}")
        print("\n=== Lasso: which pillars got zeroed out (>50% of walk-forward folds)? ===")
        for a in lasso_alphas:
            coefs = np.array(lasso_coefs[a])
            zero_frac = (coefs == 0).mean(axis=0)
            zeroed = [PILLAR_COLS[i] for i in range(len(PILLAR_COLS)) if zero_frac[i] > 0.5]
            kept = [PILLAR_COLS[i] for i in range(len(PILLAR_COLS)) if zero_frac[i] <= 0.5]
            print(f"alpha={a:g}: zeroed={zeroed or 'none'}  kept={kept}")
    else:
        print("No usable walk-forward test years - min_cross_section too high?")


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
