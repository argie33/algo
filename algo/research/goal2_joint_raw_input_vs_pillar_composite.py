#!/usr/bin/env python3
"""
Direct test of "Goal 2": regardless of pillar structure, does a joint model over ALL raw
inputs at once (no pillar pre-aggregation, no pillar boundaries) beat the live pillar-then-
combine architecture at the actual job - ranking stocks by forward return, OOS?

REBUILT 2026-08-31 (composite-score research session, re-raised via /goal - "instead of factor
pillar weights, the input relationship in whole" - the exact question this script answers).
The 2026-08-27 version's *_LIVE_W dicts had drifted stale against 5 real pillar reworks since
then (Size retired entirely 2026-08-28; Quality rebuilt to an 8-component blend incl.
asset_turnover; Growth rebuilt to an 11-field equal-weight blend; Value reworked to
PE12/PB39/PS34/ForwardPE4/DividendYield11, no PEG/FCF-yield/Margin-of-Safety/Net-Payout-Yield;
Risk reworked to Vol60D45/Vol252D20/Beta20/MaxDrawdown15) - the exact same staleness class
already caught and fixed at the pillar-SUMMARY level in fama_macbeth_composite_weights.py this
same session (see that file's own "RE-VERIFIED 2026-08-31" docstring note). Per this project's
own standing rule (memory feedback_verify_specific_quantitative_claims_before_trusting_20260831),
a quantitative claim from a prior session must be reproduced against current code before being
re-cited, not assumed still true.

Changes in this rebuild, verified directly against loaders/load_stock_scores.py's current
_score_quality/_score_growth/_score_value/_score_risk/_score_momentum (not against any memory
file's description of them):
- PILLAR_W now imports BASE_PILLAR_WEIGHTS directly from loaders/load_stock_scores.py instead
  of a hardcoded, renormalized copy - the exact fix that would have prevented this file's own
  staleness. quality=0.20/growth=0.24/value=0.27/risk=0.19/momentum=0.10, all 5 live pillars
  present in this panel, sums to 1.00 already - no renormalization needed (Size/Positioning are
  fully retired, there's nothing left to renormalize around).
- QUALITY_LIVE_W: ROA18/ROCE18/(-DebtToEquity)18/FCFMargin15/ROE11/(-MarginVolatility3Y)7/
  AssetTurnover7/GrossProfitability7 (nominal 101, matches _score_quality's live 8-component
  weights exactly). asset_turnover (revenue/total_assets) ADDED to QUALITY_COLS and the quality
  panel build below - it wasn't fetched or scored at all in the 2026-08-27 version. Interest
  Coverage and Payout Ratio DROPPED (removed from live scoring 2026-08-27, this script never
  caught up).
- GROWTH_LIVE_W: equal-weight (100/9 each) over revenue_growth_1y/eps_growth_1y/
  revenue_growth_3y/eps_growth_3y/revenue_growth_5y/eps_growth_5y/ni_growth_yoy/
  sustainable_growth_rate_approx/fcf_growth_yoy - matches live GROWTH_SCORE_FIELDS' 11 fields
  minus quarterly_growth_momentum/earnings_growth_4q_avg (need a point-in-time quarterly panel
  this repo's research scripts don't build - same disclosed exclusion
  composite_weights_regression_rebuilt_null_reweight_result_20260831 already made at the
  pillar-summary level, 9 of 11). oi_growth_yoy/ocf_growth_yoy/asset_growth_yoy_flipped DROPPED
  from the live-linear reconstruction (removed from live scoring 2026-08-28) but left in
  ALL_COLS/GROWTH_COLS as extra candidate features available to the joint model - not scored by
  live_linear, still fair game for tree/ridge/lasso to use if they carry independent signal.
- VALUE_LIVE_W: PE12/PB39/PS34/DividendYield11 renormalized to 100 after dropping Forward P/E
  (analyst_earnings_estimates has only 24 distinct days of real history as of 2026-08-31, live-
  checked - not usable for a point-in-time monthly panel, same reason the original script never
  had it) - 12/96*100=12.5, 39/96*100=40.625, 34/96*100=35.417, 11/96*100=11.458. fcf_yield
  DROPPED (removed from live scoring 2026-08-28) but left in VALUE_COLS as an extra candidate
  feature, same treatment as Growth's 3 removed fields above.
- RISK_LIVE_W: Vol60D45/Vol252D20/MaxDrawdown15 renormalized to 100 after dropping Beta (20%) -
  45/80*100=56.25, 20/80*100=25.0, 15/80*100=18.75. Beta stays excluded from the live-linear
  reconstruction for the same reason the 2026-08-27 version already disclosed: its live scoring
  target is closeness to 1.0, not "lower is better" - can't be captured by a simple negative-
  linear z-score weight without the raw level. vol_60d/vol_252d/max_dd_1y are NEW real
  60/252-TRADING-DAY daily-window constructions (the 2026-08-27 version approximated Risk with
  fama_macbeth_price_factors.py's 12-MONTH rolling-monthly-return vol/downside_vol/max_dd, a
  fidelity gap already caught and fixed at the pillar-summary level in
  composite_weights_regression_rebuilt_null_reweight_result_20260831 - fixed here the same way,
  reusing fama_macbeth_composite_weights.py's own daily-panel construction rather than
  reinventing it). The old monthly-window vol/downside_vol/beta/max_dd stay in ALL_COLS as
  extra candidate features (PRICE_COLS), not used in live_linear.
- MOMENTUM_LIVE_W: mom_12_1(35)/mom_3m(20)/rsi_14(18.5)/macd_sign(18.5)/price_vs_sma_50(4)/
  price_vs_sma_200(4) - RSI+MACD (37% combined) and SMA50+SMA200 (8% combined) are each
  AVERAGED into one sub-score in live production before weighting (CONSOLIDATED 2026-08-28,
  see _score_momentum's docstring), not independently weighted as the 2026-08-27 version had
  them (rsi_14=21/macd_sign=16 separately) - approximated here by splitting each combined
  weight evenly across its two raw inputs, disclosed as an approximation of the true
  averaged-sub-score treatment, same convention this file already uses for every other
  consolidated pair.

Not changed: the 65-raw-input ALL_COLS set the JOINT model gets to choose freely from is
still a superset of what live_linear uses (plus the 3 new vol_60d/vol_252d/max_dd_1y and 1 new
asset_turnover column, now 69 total) - only the *_LIVE_W dicts that reconstruct the live
pillar-then-combine composite for comparison needed correcting. If the joint model ends up
with MORE raw inputs available than before while still losing, that's evidence AGAINST it, not
a handicap for it.

Extends algo/research/unified_input_clustering_and_importance.py's 54-input pillar-agnostic
panel (325,723 symbol-months, 2018-01 to 2026-07) with today's additional tested candidates,
reusing each source script's exact formula/construction:
- ev_ebit, owner_earnings_yield (value_ev_ebit_owner_earnings_candidates.py)
- reinvestment_rate, book_value_growth (growth_reinvestment_book_value_candidates.py)
- rd_intensity (growth_rd_intensity_mohanram_gscore_candidates.py) - sparse by design (27.9%
  universe-wide, most sectors don't report R&D)
- ev, revenue_log, total_assets_log (size_ev_float_assets_revenue_candidates.py) - Size-family,
  included for analytical completeness per explicit user instruction; does NOT reopen the
  standing live-scoring exclusion of Size
- net_debt_issuance_yoy (quality_roic_wacc_net_debt_issuance_candidates.py's simpler half only)
- idio_vol, downside_beta (risk_idio_vol_downside_beta_operating_leverage_candidates.py) -
  monthly-return-based, cheap to fold into this panel's existing monthly structure
(share_issuance_yoy and str_1m are ALREADY in the base 54-input panel - not re-added.)

EXPLICITLY DROPPED, disclosed not hidden:
- roic_minus_wacc: real construction complexity (point-in-time DGS10/VIX/beta chain) for a
  candidate ALREADY found unreliable (clean sign-flip across the half-split in its own dedicated
  test) - low marginal value for the engineering cost in the time available.
- mohanram_g_score: complex industry-relative composite (sector x fiscal-year median splits)
  for a candidate ALREADY confirmed a clean null with a half-split sign-flip - same reasoning.
- idio_skew, coskew, cvar_5pct, high_52w_proximity, industry_mom_6m: all require a SEPARATE
  daily-price panel (252-trading-day rolling windows over ~5000 symbols) - the most expensive
  construction in this whole task - and ALL FIVE were already tested individually and REJECTED
  (clean nulls or sign-flips) in risk_skewness_coskewness_cvar_candidates.py and
  momentum_52wk_industry_residual_reversal_candidates.py. Adding known-null, expensive-to-build
  daily-granularity features to a joint model doesn't change the Goal-2 answer meaningfully and
  wasn't worth the build cost in the time available for this single pass.

Final count: 54 base + 11 new = 65 raw inputs.

Live-linear composite reconstruction: BASE_PILLAR_WEIGHTS (loaders/load_stock_scores.py) is
quality=0.25/growth=0.12/value=0.21/positioning=0.12/risk=0.18/momentum=0.12. This panel has no
positioning inputs (institutional ownership/short interest aren't in any research script's
panel) - renormalized over the 5 available pillars (quality/growth/value/risk/momentum,
combined weight 0.88, each divided by 0.88). Within each pillar, uses that pillar's live
per-component weights (approximated where a component isn't in this panel, e.g. Value's
PEG/NetPayout/MoS aren't available - renormalized over what IS available, same "don't fabricate
a missing input" discipline as everywhere else in this project). This is a disclosed
approximation of the live composite, not a byte-exact reproduction - same caveat
fama_macbeth_composite_weights.py's own pillar-proxy construction already carries.
"""

import argparse
import logging
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Lasso, Ridge

from algo.research.fama_macbeth_growth_factors import (
    REPORTING_LAG_DAYS,
    build_growth_panel,
    fetch_annual_fundamentals,
    merge_asof_monthly,
)
from algo.research.fama_macbeth_momentum_factors import compute_daily_indicators, fetch_daily_prices
from algo.research.fama_macbeth_price_factors import build_monthly_cross_sections, fetch_month_end_prices
from algo.research.fama_macbeth_quality_factors import build_quality_panel, fetch_annual_quality_fundamentals
from algo.research.fama_macbeth_value_factors import build_value_panel, compute_ratios, fetch_annual_value_fundamentals
from loaders.load_stock_scores import BASE_PILLAR_WEIGHTS
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

QUALITY_COLS = [
    "roe",
    "roa",
    "operating_margin",
    "net_margin",
    "debt_to_assets",
    "interest_coverage",
    "gross_profitability",
    "operating_profitability",
    "accruals_ratio",
    "payout_ratio",
    "roic_pct",
    "altman_z_score",
    "roce",
    "fcf_margin",
    "debt_to_equity",
    "current_ratio",
    "share_issuance_yoy",
    "debt_issuance_yoy",
    "margin_volatility_3y",
    "fcf_to_net_income",
    "net_debt_to_ebitda",
    "net_debt_to_fcf",
    "asset_turnover",  # ADDED 2026-08-31 rebuild - live _score_quality's 8th component (7%), missing entirely before
]
VALUE_COLS = ["pe", "pb", "ps", "fcf_yield", "dividend_yield", "ev_ebitda", "ev_revenue", "size"]
GROWTH_COLS = [
    "eps_growth_1y",
    "eps_growth_3y",
    "eps_growth_5y",
    "revenue_growth_1y",
    "revenue_growth_3y",
    "revenue_growth_5y",
    "ni_growth_yoy",
    "oi_growth_yoy",
    "fcf_growth_yoy",
    "ocf_growth_yoy",
    "asset_growth_yoy_flipped",
    "sustainable_growth_rate_approx",
]
PRICE_COLS = ["mom_12_1", "mom_6m", "mom_3m", "str_1m", "vol", "downside_vol", "beta", "max_dd"]
TECH_COLS = ["rsi_14", "macd_sign", "price_vs_sma_50", "price_vs_sma_200"]

# DAILY_RISK_COLS: real 60/252-TRADING-DAY windows from actual daily prices (ADDED 2026-08-31
# rebuild), replacing PRICE_COLS' 12-month rolling-monthly-return vol/downside_vol/max_dd as
# what live_linear's Risk reconstruction actually uses - see module docstring. PRICE_COLS stays
# in ALL_COLS unchanged as extra candidate features for the joint model.
DAILY_RISK_COLS = ["vol_60d", "vol_252d", "max_dd_1y"]

NEW_ANNUAL_COLS = [
    "ev_ebit",
    "owner_earnings_yield",
    "reinvestment_rate",
    "book_value_growth",
    "rd_intensity",
    "ev",
    "revenue_log",
    "total_assets_log",
    "net_debt_issuance_yoy",
]
NEW_MONTHLY_COLS = ["idio_vol", "downside_beta"]

ALL_COLS = (
    QUALITY_COLS
    + VALUE_COLS
    + GROWTH_COLS
    + PRICE_COLS
    + TECH_COLS
    + NEW_ANNUAL_COLS
    + NEW_MONTHLY_COLS
    + DAILY_RISK_COLS
)

PILLAR_OF = (
    dict.fromkeys(QUALITY_COLS, "Quality")
    | dict.fromkeys(VALUE_COLS, "Value")
    | dict.fromkeys(GROWTH_COLS, "Growth")
    | dict.fromkeys(PRICE_COLS, "Momentum/Risk (price, monthly-window)")
    | dict.fromkeys(TECH_COLS, "Momentum (technical)")
    | dict.fromkeys(DAILY_RISK_COLS, "Risk (daily-window, live)")
    | {
        "ev_ebit": "Value",
        "owner_earnings_yield": "Value",
        "reinvestment_rate": "Growth",
        "book_value_growth": "Growth",
        "rd_intensity": "Growth",
        "ev": "Size(analytical only)",
        "revenue_log": "Size(analytical only)",
        "total_assets_log": "Size(analytical only)",
        "net_debt_issuance_yoy": "Quality",
        "idio_vol": "Risk",
        "downside_beta": "Risk",
    }
)

# Live BASE_PILLAR_WEIGHTS, imported directly (not a hardcoded copy - the exact fix that would
# have prevented this file's own 2026-08-27 -> 2026-08-31 staleness). All 5 keys present in this
# panel (Size/Positioning fully retired) - sums to 1.00 already, no renormalization needed.
PILLAR_W = dict(BASE_PILLAR_WEIGHTS)

# Within-pillar live weights, approximated where a live component isn't in this panel
# (renormalized over what's available - disclosed, not fabricated). SIGN MATTERS: several live
# components score HIGHER when the raw ratio is LOWER (P/E, P/B, P/S, debt-to-equity, volatility,
# margin-volatility all invert in the live scoring curves) - negative weight here, matching
# fama_macbeth_composite_weights.py's own -pe/-pb/-ps/-size convention for its pillar proxies.
# REBUILT 2026-08-31 against current live formulas - see module docstring for the full
# per-pillar reasoning and exact renormalization arithmetic behind every number below.
QUALITY_LIVE_W = {
    "roa": 18.0,
    "roce": 18.0,
    "debt_to_equity": -18.0,
    "fcf_margin": 15.0,
    "roe": 11.0,
    "margin_volatility_3y": -7.0,
    "asset_turnover": 7.0,
    "gross_profitability": 7.0,
}
_VALUE_BASE = {"pe": -12.0, "pb": -39.0, "ps": -34.0, "dividend_yield": 11.0}  # ForwardPE 4% dropped, no history
_VALUE_SCALE = 100.0 / sum(abs(v) for v in _VALUE_BASE.values())
VALUE_LIVE_W = {k: v * _VALUE_SCALE for k, v in _VALUE_BASE.items()}
_GROWTH_FIELDS_LIVE = [
    "revenue_growth_1y",
    "eps_growth_1y",
    "revenue_growth_3y",
    "eps_growth_3y",
    "revenue_growth_5y",
    "eps_growth_5y",
    "ni_growth_yoy",
    "sustainable_growth_rate_approx",
    "fcf_growth_yoy",
]  # equal-weight (9 of live GROWTH_SCORE_FIELDS' 11 - quarterly_growth_momentum/
# earnings_growth_4q_avg need a point-in-time quarterly panel not built here, see docstring)
GROWTH_LIVE_W = {c: 100.0 / len(_GROWTH_FIELDS_LIVE) for c in _GROWTH_FIELDS_LIVE}
_RISK_BASE = {"vol_60d": -45.0, "vol_252d": -20.0, "max_dd_1y": 15.0}  # beta(20%) dropped, see docstring
_RISK_SCALE = 100.0 / sum(abs(v) for v in _RISK_BASE.values())
RISK_LIVE_W = {k: v * _RISK_SCALE for k, v in _RISK_BASE.items()}
MOMENTUM_LIVE_W = {
    "mom_12_1": 35.0,
    "mom_3m": 20.0,
    "rsi_14": 18.5,
    "macd_sign": 18.5,
    "price_vs_sma_50": 4.0,
    "price_vs_sma_200": 4.0,
}


def _zwinsor(s: pd.Series) -> pd.Series:
    lo, hi = s.quantile([0.01, 0.99])
    s = s.clip(lo, hi)
    std = s.std()
    return (s - s.mean()) / std if std and std > 0 else s * 0.0


def fetch_tech_and_daily_returns(start_date: str, end_date: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Fetches the daily price panel ONCE and derives both the month-end technical-indicator
    frame (RSI/MACD/SMA) and the daily return/price matrices used for real 60/252-TRADING-DAY
    vol_60d/vol_252d/max_dd_1y windows (ADDED 2026-08-31 rebuild - see module docstring).
    Avoids a second expensive price_daily fetch: fama_macbeth_composite_weights.py's
    build_pillar_proxy_records() already established the live Risk formula needs the DAILY
    panel, not the 12-month rolling-monthly-return approximation this script used before."""
    daily = fetch_daily_prices(start_date, end_date)
    daily_ind = compute_daily_indicators(daily)
    daily_ind["month"] = daily_ind["date"].dt.to_period("M").dt.to_timestamp()
    idx = daily_ind.groupby(["symbol", "month"])["date"].idxmax()
    tech_monthly = daily_ind.loc[idx, ["symbol", "month", *TECH_COLS]].reset_index(drop=True)

    daily_wide = daily.pivot(index="date", columns="symbol", values="px").sort_index()
    daily_ret = daily_wide.pct_change(fill_method=None)
    return tech_monthly, daily_wide, daily_ret


def fetch_extended_annual() -> pd.DataFrame:
    """Everything needed for the 9 NEW_ANNUAL_COLS, in one query - reuses the same tables the
    base panel's fetchers already hit (annual_income_statement/annual_balance_sheet/annual_cash_flow)."""
    sql = """
        SELECT i.symbol, i.fiscal_year,
               i.revenue, i.operating_income, i.net_income,
               i.research_development_expense,
               COALESCE(i.depreciation_expense, 0) AS depreciation_expense,
               COALESCE(i.amortization_expense, 0) AS amortization_expense,
               i.income_tax_expense, i.pretax_income,
               COALESCE(i.shares_outstanding_diluted, i.shares_outstanding_basic, i.shares_outstanding_dei) AS shares,
               b.stockholders_equity, b.long_term_debt, b.short_term_debt, b.cash_and_equivalents,
               b.current_assets, b.current_liabilities, b.total_assets,
               c.capex
        FROM annual_income_statement i
        LEFT JOIN annual_balance_sheet b ON b.symbol = i.symbol AND b.fiscal_year = i.fiscal_year
        LEFT JOIN annual_cash_flow c ON c.symbol = i.symbol AND c.fiscal_year = i.fiscal_year
        WHERE i.fiscal_year BETWEEN 2000 AND 2026
          AND COALESCE(i.data_unavailable, false) = false
          AND COALESCE(i.shares_outstanding_diluted, i.shares_outstanding_basic, i.shares_outstanding_dei) > 0
        ORDER BY i.symbol, i.fiscal_year
    """
    with DatabaseContext("read") as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    cols = [
        "symbol",
        "fiscal_year",
        "revenue",
        "operating_income",
        "net_income",
        "rd_expense",
        "depreciation_expense",
        "amortization_expense",
        "income_tax_expense",
        "pretax_income",
        "shares",
        "stockholders_equity",
        "long_term_debt",
        "short_term_debt",
        "cash_and_equivalents",
        "current_assets",
        "current_liabilities",
        "total_assets",
        "capex",
    ]
    df = pd.DataFrame(rows, columns=cols)
    for c in cols:
        if c not in ("symbol", "fiscal_year"):
            df[c] = df[c].astype(float)
    return df


def build_extended_annual_panel(fund: pd.DataFrame) -> pd.DataFrame:
    fund = fund.sort_values(["symbol", "fiscal_year"]).reset_index(drop=True)
    g = fund.groupby("symbol", group_keys=False)
    shares = fund["shares"]

    net_debt = (
        fund["long_term_debt"].fillna(0) + fund["short_term_debt"].fillna(0) - fund["cash_and_equivalents"].fillna(0)
    )
    prior_net_debt = g.apply(
        lambda d: (
            d["long_term_debt"].fillna(0) + d["short_term_debt"].fillna(0) - d["cash_and_equivalents"].fillna(0)
        ).shift(1)
    ).reset_index(level=0, drop=True)
    prior_total_assets = g["total_assets"].shift(1)

    prior_ca = g["current_assets"].shift(1)
    prior_cl = g["current_liabilities"].shift(1)
    delta_nwc = (fund["current_assets"] - prior_ca) - (fund["current_liabilities"] - prior_cl)

    tax_rate = (fund["income_tax_expense"] / fund["pretax_income"]).clip(0.0, 1.0)
    tax_rate = tax_rate.where(fund["pretax_income"] > 0)
    nopat = fund["operating_income"] * (1.0 - tax_rate)
    da = fund["depreciation_expense"].fillna(0) + fund["amortization_expense"].fillna(0)

    bvps = fund["stockholders_equity"] / shares
    bvps = bvps.where((shares > 0) & (fund["stockholders_equity"] > 0))
    prior_bvps = g["stockholders_equity"].shift(1) / g["shares"].shift(1)

    owner_earnings = fund["net_income"] + da - fund["capex"].abs() - delta_nwc

    out = fund[["symbol", "fiscal_year"]].copy()
    out["ebit_per_share"] = fund["operating_income"] / shares
    out["owner_earnings_per_share"] = owner_earnings / shares
    out["net_debt_per_share"] = net_debt / shares
    out["shares_diluted"] = shares
    out["reinvestment_rate"] = np.where(nopat > 0, (fund["capex"].abs() - da + delta_nwc) / nopat, np.nan)
    out["book_value_growth"] = np.where((prior_bvps > 0) & (bvps > 0), bvps / prior_bvps - 1.0, np.nan)
    out["rd_intensity"] = np.where(fund["revenue"] > 0, fund["rd_expense"] / fund["revenue"], np.nan)
    out["net_debt_issuance_yoy"] = np.where(
        prior_total_assets > 0, (net_debt - prior_net_debt) / prior_total_assets, np.nan
    )
    market_cap_free_fields = fund["total_assets"]
    out["total_assets_for_log"] = market_cap_free_fields
    out["revenue_for_log"] = fund["revenue"]
    out["net_debt_for_ev"] = net_debt

    out["known_date"] = pd.to_datetime(fund["fiscal_year"].astype(str) + "-12-31") + pd.Timedelta(
        days=REPORTING_LAG_DAYS
    )
    return out.dropna(subset=["known_date"])


def compute_price_dependent_new_cols(gframe: pd.DataFrame, price: pd.Series) -> pd.DataFrame:
    df = gframe.join(price.rename("price"), how="inner")
    df = df[df["price"] > 0]
    ratios = pd.DataFrame(index=df.index)
    ev_per_share = df["price"] + df["net_debt_per_share"]
    ratios["ev_ebit"] = np.where(df["ebit_per_share"] > 0, ev_per_share / df["ebit_per_share"], np.nan)
    ratios["owner_earnings_yield"] = np.where(
        df["owner_earnings_per_share"].notna(), df["owner_earnings_per_share"] / df["price"], np.nan
    )
    market_cap = df["price"] * df["shares_diluted"]
    ev_total = market_cap + df["net_debt_for_ev"]
    ratios["ev"] = np.where((ev_total >= 1e6) & (ev_total <= 1e13), np.log10(ev_total), np.nan)
    ratios["revenue_log"] = np.where(
        (df["revenue_for_log"] > 0) & (df["revenue_for_log"] <= 1e13), np.log10(df["revenue_for_log"]), np.nan
    )
    ratios["total_assets_log"] = np.where(
        (df["total_assets_for_log"] >= 1e5) & (df["total_assets_for_log"] <= 1e13),
        np.log10(df["total_assets_for_log"]),
        np.nan,
    )
    ratios["reinvestment_rate"] = df["reinvestment_rate"]
    ratios["book_value_growth"] = df["book_value_growth"]
    ratios["rd_intensity"] = df["rd_intensity"]
    ratios["net_debt_issuance_yoy"] = df["net_debt_issuance_yoy"]
    return ratios


def live_linear_score(frame: pd.DataFrame) -> pd.Series:
    """Reconstructs the live pillar-then-combine composite from this panel's own z-scored raw
    inputs, at live BASE_PILLAR_WEIGHTS (renormalized over the 5 available pillars) and each
    pillar's live within-pillar weights (renormalized over available components). Disclosed
    approximation, not byte-exact - see module docstring."""

    def pillar_score(weights: dict[str, float]) -> pd.Series:
        """Renormalizes PER ROW over whichever components are actually non-NaN for that row -
        matches production's _weighted_avg semantics (loaders/load_value_quality_growth_metrics.py)
        exactly. A naive column-present-only check (no row-level masking) silently NaNs out any
        row missing even one field, biasing the effective sample toward fuller-coverage
        symbol-months - caught live in this script's first run (live_linear scored ~0, an
        obvious red flag against the ~0.07 the same reconstruction style got in
        fama_macbeth_composite_weights.py's own careful per-pillar proxies)."""
        cols = [c for c in weights if c in frame.columns]
        w = pd.Series({c: weights[c] for c in cols})
        sub = frame[cols]
        avail = sub.notna()
        weighted_sum = sub.fillna(0.0).mul(w, axis=1).sum(axis=1)
        total_w = avail.mul(w.abs(), axis=1).sum(axis=1)
        return (weighted_sum / total_w).where(total_w > 0)

    quality = pillar_score(QUALITY_LIVE_W)
    value = pillar_score(VALUE_LIVE_W)
    growth = pillar_score(GROWTH_LIVE_W)
    risk = pillar_score(RISK_LIVE_W)
    momentum = pillar_score(MOMENTUM_LIVE_W)
    return (
        quality * PILLAR_W["quality"]
        + value * PILLAR_W["value"]
        + growth * PILLAR_W["growth"]
        + risk * PILLAR_W["risk"]
        + momentum * PILLAR_W["momentum"]
    )


def _compute_daily_risk_windows(
    daily_idx: int | None, daily_ret: pd.DataFrame, daily_wide: pd.DataFrame, index: pd.Index
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Real 60/252-TRADING-DAY vol_60d/vol_252d/max_dd_1y for one month's daily-panel position
    (ADDED 2026-08-31 rebuild - see module docstring; extracted out of `run()` to keep that
    function's own branching complexity in check). NaN series when there isn't a full 252-day
    trailing window yet (daily_idx is None or < 251)."""
    if daily_idx is None or daily_idx < 251:
        nan = pd.Series(np.nan, index=index)
        return nan, nan, nan
    win60 = daily_ret.iloc[daily_idx - 59 : daily_idx + 1]
    win252 = daily_ret.iloc[daily_idx - 251 : daily_idx + 1]
    vol_60d = (win60.std() * np.sqrt(252)).reindex(index)
    vol_252d = (win252.std() * np.sqrt(252)).reindex(index)
    px_window_252 = daily_wide.iloc[daily_idx - 251 : daily_idx + 1]
    max_dd_1y = ((px_window_252 / px_window_252.cummax() - 1.0).min()).reindex(index)
    return vol_60d, vol_252d, max_dd_1y


def run(start_date: str, end_date: str, min_cross_section: int) -> None:
    logger.info("Fetching base fundamentals panels (quality/growth/value)")
    quality_fund = fetch_annual_quality_fundamentals()
    quality_panel = build_quality_panel(quality_fund)
    # asset_turnover ADDED 2026-08-31 rebuild - live _score_quality's 8th component (7%),
    # matching fama_macbeth_composite_weights.py's own construction (revenue/total_assets).
    quality_panel = quality_panel.merge(
        quality_fund[["symbol", "fiscal_year", "revenue", "total_assets"]], on=["symbol", "fiscal_year"], how="left"
    )
    quality_panel["asset_turnover"] = np.where(
        quality_panel["total_assets"] > 0, quality_panel["revenue"] / quality_panel["total_assets"], np.nan
    )

    growth_fund = fetch_annual_fundamentals()
    growth_panel = build_growth_panel(growth_fund)
    sgr_src = quality_panel[["symbol", "fiscal_year", "roe", "payout_ratio"]].copy()
    sgr_src["sustainable_growth_rate_approx"] = sgr_src["roe"] * (1.0 - sgr_src["payout_ratio"].fillna(0).clip(0, 1))
    growth_panel = growth_panel.merge(
        sgr_src[["symbol", "fiscal_year", "sustainable_growth_rate_approx"]], on=["symbol", "fiscal_year"], how="left"
    )

    value_fund = fetch_annual_value_fundamentals()
    value_panel_raw = build_value_panel(value_fund)

    logger.info("Fetching extended annual fundamentals for 9 new candidate columns")
    ext_fund = fetch_extended_annual()
    ext_panel = build_extended_annual_panel(ext_fund)

    logger.info(f"Pulling month-end prices {start_date}..{end_date}")
    px_df = fetch_month_end_prices(start_date, end_date)
    px = px_df.pivot(index="month", columns="symbol", values="px").sort_index()
    ret = px.pct_change(fill_method=None)
    mkt = ret["SPY"] if "SPY" in ret.columns else None

    logger.info("Building price-factor monthly cross-sections (mom/vol/beta/drawdown)")
    price_records = build_monthly_cross_sections(
        px, ret, beta_window=24, vol_window=12, min_cross_section=min_cross_section
    )
    if not price_records:
        raise RuntimeError("No usable price cross-sections")
    months = pd.DatetimeIndex([m for m, _ in price_records])

    logger.info("Fetching daily prices for RSI/MACD/SMA technical indicators + vol_60d/vol_252d/max_dd_1y")
    tech_monthly, daily_wide, daily_ret = fetch_tech_and_daily_returns(start_date, end_date)
    daily_dates = daily_wide.index
    # Map each month-end to the closest actual trading day <= that month-end in the DAILY panel
    # (same approach as fama_macbeth_composite_weights.py's build_pillar_proxy_records), so
    # vol_60d/vol_252d/max_dd_1y are real 60/252-TRADING-DAY windows, not a monthly approximation.
    month_to_daily_idx: dict[Any, int | None] = {}
    for month_raw, _ in price_records:
        cutoff = pd.Timestamp(month_raw) + pd.offsets.MonthEnd(0)
        pos = int(daily_dates.searchsorted(cutoff, side="right")) - 1
        month_to_daily_idx[month_raw] = pos if pos >= 0 else None

    logger.info("As-of merging fundamentals onto the price panel's months")
    quality_monthly = merge_asof_monthly(months, quality_panel, cols=QUALITY_COLS)
    growth_monthly = merge_asof_monthly(months, growth_panel, cols=GROWTH_COLS)
    value_monthly = merge_asof_monthly(
        months,
        value_panel_raw,
        cols=[c for c in value_panel_raw.columns if c not in ("symbol", "fiscal_year", "known_date")],
    )
    ext_cols = [
        "ebit_per_share",
        "owner_earnings_per_share",
        "net_debt_per_share",
        "shares_diluted",
        "reinvestment_rate",
        "book_value_growth",
        "rd_intensity",
        "net_debt_issuance_yoy",
        "total_assets_for_log",
        "revenue_for_log",
        "net_debt_for_ev",
    ]
    ext_monthly = merge_asof_monthly(months, ext_panel, cols=ext_cols)

    pooled_frames: list[pd.DataFrame] = []
    for i, (month_raw, price_frame) in enumerate(price_records):
        month = pd.Timestamp(month_raw)
        q = quality_monthly.get(month)
        gm = growth_monthly.get(month)
        v_raw = value_monthly.get(month)
        e_raw = ext_monthly.get(month)
        if any(x is None or x.empty for x in (q, gm, v_raw, e_raw)):
            continue
        if month_raw not in px.index:
            continue
        price_at_month = px.loc[month_raw]
        v = compute_ratios(v_raw, price_at_month)[VALUE_COLS]
        e_new = compute_price_dependent_new_cols(e_raw, price_at_month)
        tech = tech_monthly[tech_monthly["month"] == month].set_index("symbol")[TECH_COLS]

        frame = (
            price_frame.join(q, how="inner")
            .join(gm, how="inner")
            .join(v, how="inner")
            .join(tech, how="inner")
            .join(e_new, how="left")
        )

        # idio_vol / downside_beta: monthly-return local-beta residualization, same construction
        # as risk_idio_vol_downside_beta_operating_leverage_candidates.py.
        if mkt is not None and i >= 12:
            win = ret.iloc[i - 11 : i + 1]
            mkt_win = mkt.iloc[i - 11 : i + 1]
            mkt_var = mkt_win.var()
            local_beta = (
                win.apply(lambda col, m=mkt_win: col.cov(m)) / mkt_var
                if mkt_var and mkt_var > 0
                else pd.Series(np.nan, index=win.columns)
            )
            resid = win - pd.DataFrame(
                np.outer(mkt_win.values, local_beta.values), index=win.index, columns=win.columns
            )
            idio_vol = (resid.std() * np.sqrt(12)).reindex(frame.index)
        else:
            idio_vol = pd.Series(np.nan, index=frame.index)
        frame["idio_vol"] = idio_vol

        if mkt is not None and i >= 36:
            win_db = ret.iloc[i - 35 : i + 1]
            mkt_db = mkt.iloc[i - 35 : i + 1]
            down_mask = mkt_db < 0
            if down_mask.sum() >= 8:
                mkt_down = mkt_db[down_mask]
                win_down = win_db[down_mask]
                mkt_down_var = mkt_down.var()
                downside_beta = (
                    (win_down.apply(lambda col, m=mkt_down: col.cov(m)) / mkt_down_var).reindex(frame.index)
                    if mkt_down_var and mkt_down_var > 0
                    else pd.Series(np.nan, index=frame.index)
                )
            else:
                downside_beta = pd.Series(np.nan, index=frame.index)
        else:
            downside_beta = pd.Series(np.nan, index=frame.index)
        frame["downside_beta"] = downside_beta

        # vol_60d/vol_252d/max_dd_1y: real 60/252-TRADING-DAY daily windows (ADDED 2026-08-31
        # rebuild - see module docstring). Same construction as
        # fama_macbeth_composite_weights.py's build_pillar_proxy_records().
        daily_idx = month_to_daily_idx.get(month_raw)
        vol_60d, vol_252d, max_dd_1y = _compute_daily_risk_windows(daily_idx, daily_ret, daily_wide, frame.index)
        frame["vol_60d"] = vol_60d
        frame["vol_252d"] = vol_252d
        frame["max_dd_1y"] = max_dd_1y

        frame = frame.replace([np.inf, -np.inf], np.nan)
        if len(frame) < min_cross_section:
            continue

        for col in (
            QUALITY_COLS + GROWTH_COLS + VALUE_COLS + TECH_COLS + NEW_ANNUAL_COLS + NEW_MONTHLY_COLS + DAILY_RISK_COLS
        ):
            frame[col] = _zwinsor(frame[col].astype(float))

        frame["live_linear"] = live_linear_score(frame)
        frame["month"] = month
        frame["year"] = month.year
        pooled_frames.append(frame)

    if not pooled_frames:
        raise RuntimeError("No usable joint-panel months")

    panel = pd.concat(pooled_frames, ignore_index=True)
    print(
        f"\nExtended joint panel: {len(panel)} symbol-months across {panel['month'].nunique()} months, {len(ALL_COLS)} raw inputs"
    )
    print(f"Months: {panel['month'].min()} to {panel['month'].max()}")
    for c in (
        NEW_ANNUAL_COLS + NEW_MONTHLY_COLS + DAILY_RISK_COLS + ["asset_turnover", "sustainable_growth_rate_approx"]
    ):
        cov = panel[c].notna().mean()
        print(f"  coverage {c:24s}: {cov:.1%}")

    panel[ALL_COLS] = panel[ALL_COLS].fillna(0.0)

    years = sorted(panel["year"].unique())
    test_years = years[max(1, int(len(years) * 0.6)) :]
    print(f"\nOOS test years: {test_years} ({len(test_years)} independent years)")

    results: dict[str, list[Any]] = {
        "live_linear": [],
        "actual": [],
        "joint_tree": [],
        "joint_ridge": [],
        "joint_lasso_naive": [],
    }
    lasso_alphas = [1e-5, 1e-4, 1e-3, 1e-2]
    lasso_by_alpha: dict[float, list[Any]] = {a: [] for a in lasso_alphas}

    for test_year in test_years:
        train = panel[panel["year"] < test_year]
        test = panel[panel["year"] == test_year]
        if train.empty or len(test) < min_cross_section:
            continue

        tree = HistGradientBoostingRegressor(
            max_iter=200, max_depth=4, learning_rate=0.05, l2_regularization=1.0, random_state=0
        )
        tree.fit(train[ALL_COLS], train["fwd_ret"])
        results["joint_tree"].extend(tree.predict(test[ALL_COLS]).tolist())

        ridge = Ridge(alpha=10.0)
        ridge.fit(train[ALL_COLS], train["fwd_ret"])
        results["joint_ridge"].extend(ridge.predict(test[ALL_COLS]).tolist())

        for a in lasso_alphas:
            lasso = Lasso(alpha=a, max_iter=5000)
            lasso.fit(train[ALL_COLS], train["fwd_ret"])
            lasso_by_alpha[a].extend(lasso.predict(test[ALL_COLS]).tolist())

        results["live_linear"].extend(test["live_linear"].tolist())
        results["actual"].extend(test["fwd_ret"].tolist())
        logger.info(f"{test_year}: train={len(train)} test={len(test)} done")

    actual = pd.Series(results["actual"])
    print("\n=== GOAL-2 COMPARISON: joint raw-input model vs live pillar-then-combine composite ===")
    print(f"OOS symbol-months: {len(actual)}")
    print(f"{'method':24s} {'Spearman':>10s} {'Pearson':>10s}")
    for name in ("live_linear", "joint_tree", "joint_ridge"):
        s = pd.Series(results[name])
        print(f"{name:24s} {s.corr(actual, method='spearman'):10.4f} {s.corr(actual, method='pearson'):10.4f}")
    print("\nnaive post-hoc lasso by alpha (HINDSIGHT BIAS - best-of-grid, not honestly selected, reference only):")
    for a in lasso_alphas:
        s = pd.Series(lasso_by_alpha[a])
        print(f"  alpha={a:<8g} {s.corr(actual, method='spearman'):10.4f} {s.corr(actual, method='pearson'):10.4f}")

    print("\n=== Joint tree feature importance (permutation-free proxy via built-in, top 20) ===")
    last_train = panel[panel["year"] < test_years[-1]] if test_years else panel
    final_tree = HistGradientBoostingRegressor(
        max_iter=200, max_depth=4, learning_rate=0.05, l2_regularization=1.0, random_state=0
    )
    final_tree.fit(last_train[ALL_COLS], last_train["fwd_ret"])
    try:
        from sklearn.inspection import permutation_importance

        sample = last_train.sample(n=min(5000, len(last_train)), random_state=0)
        pi = permutation_importance(
            final_tree, sample[ALL_COLS], sample["fwd_ret"], n_repeats=3, random_state=0, n_jobs=-1
        )
        order = np.argsort(-pi.importances_mean)
        print(f"{'rank':4s} {'input':28s} {'pillar':24s} {'importance':>10s}")
        for rank, idx in enumerate(order[:20], 1):
            col = ALL_COLS[idx]
            print(f"{rank:4d} {col:28s} {PILLAR_OF.get(col, '?'):24s} {pi.importances_mean[idx]:10.5f}")
    except Exception as exc:
        print(f"permutation_importance failed: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start-date", default="2014-01-01")
    parser.add_argument("--end-date", default=datetime.now(tz=None).date().isoformat())
    parser.add_argument("--min-cross-section", type=int, default=300)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.start_date, args.end_date, args.min_cross_section)


if __name__ == "__main__":
    main()
