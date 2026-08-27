#!/usr/bin/env python3
"""
Fama-MacBeth test of the TOP-LEVEL composite_score combination (Quality/Growth/Value/
Positioning/Stability/Momentum pillar weights).

Built 2026-08-25 (goal: figure out the right weightings for the FULL combined score, not just
each pillar in isolation). loaders/load_stock_scores.py's `base_weights` (quality=0.25,
growth=0.12, value=0.20, positioning=0.14, stability=0.14, momentum=0.15) have NO documented
empirical basis anywhere in the file - just a comment explaining the no-redistribution rule,
nothing about where the specific percentages came from. Grinold & Kahn's "Active Portfolio
Management" (the standard practitioner reference for combining multiple alpha signals) treats
this as a regression/IC-weighting problem: combine signals in proportion to their REALIZED
predictive power controlling for correlation among them - exactly what a multivariate
Fama-MacBeth regression does, which is why this script builds one pillar-level proxy per
pillar (using only the components each pillar-specific fama_macbeth_*.py script in this
directory found to carry real signal, or the live formula where nothing better is known yet)
and regresses forward return on all 6 jointly.

Pillar proxies (z-scored components combined at each pillar's LIVE weight ratios - NOT
independently re-derived per-component weights, since that's what the per-pillar scripts
already tested; this script answers the separate top-level question):
- growth_proxy: eps_growth_1y*0.25 + (-asset_growth_yoy)*0.30 + revenue_growth_1y*0.20 +
  sustainable_growth_rate*0.20 (matches _score_growth's live post-reweight weights, see
  [[growth_pillar_reweighted_horizon_matched_20260825]])
- value_proxy: -pe*0.10 -pb*0.22 -ps*0.21 + fcf_yield*0.10 + dividend_yield*0.03 -size*0.20
  (matches _score_value's CURRENT live weights, including the 2026-08-25 EV/EBITDA+EV/Revenue
  removal, Size-factor addition, AND the later same-day PE/PB/PS reversal - see
  [[value_pe_pb_ps_ranking_reversed_selection_bias_fix_20260825]]; PEG/margin-of-safety still
  excluded, not computed here - PEG needs a growth cross-term, margin-of-safety is a full DCF
  model, neither is a single point-in-time ratio like the rest of this panel)
- quality_proxy: REBUILT 2026-08-26 (was stale, still the pre-audit base-6 formula) - roe*0.122
  + roa*0.20 + roce*0.20 + fcf_margin*0.167 + (-debt_to_equity)*0.20 + interest_coverage*0.056
  + payout_ratio*0.056 (matches _score_quality's current 8-component live weights, Altman Z
  excluded and the rest renormalized - see quality_proxy's own inline comment for why)
- stability_proxy: (-vol_60d)*0.45 + (-|beta-1|)*0.20 + (-downside_vol_60d)*0.15 + max_dd*0.20
  (matches this session's ALREADY-SHIPPED stability reweight)
- momentum_proxy: mom_3m*0.20 + mom_12_1*0.35 + rsi_14*0.21 + macd_sign*0.16 +
  avg(price_vs_sma_50,price_vs_sma_200)*0.08 (matches _score_momentum's live POST-12-1-REDESIGN
  weights, see [[fama_macbeth_momentum_collinearity_found_20260825]] - mom_6m/mom_12m were
  replaced by the derived Jegadeesh 1990 skip-month construction; this script previously still
  used the pre-redesign stale split, which re-introduced the exact mom_6m/mom_12m r=0.83
  collinearity that construction was built to fix)
- positioning_proxy: ad_rating only (institutional_ownership/short_interest confirmed
  untestable - see fama_macbeth_positioning_ad_rating_null memory)
- size_proxy: -log10(market_cap), tested as an OPTIONAL 7th factor (SEVEN_COLS), not part of
  the core 6-pillar PILLAR_COLS regression - see "SIZE AS 7TH PILLAR" note below.

Each raw component is winsorized/z-scored the same way as its origin script BEFORE being
combined into the pillar proxy (so no single outlier component dominates the weighted sum),
then the resulting pillar proxies are z-scored AGAIN at the top level before the final
regression - so the final coefficients are directly comparable "how much does a 1-std move in
this whole pillar's current formula predict forward return, controlling for the others"
numbers.

PARTIAL-AVAILABILITY REDESIGN 2026-08-25 (same day, later pass - goal: fix the original
version's underpowered test rather than leave it flagged as inconclusive). The original
version required ALL 6 pillar proxies non-null per symbol-month (a strict dropna()), which
only kept the intersection of annual-fundamentals coverage (growth/value/quality, ~5,700
symbols) AND full price-history coverage (stability/momentum/positioning, up to 10,982
symbols) - 109 months, median 850 symbols, likely biased toward larger/more-established
names, and underpowered enough that the resulting coefficients were all short of conventional
significance. Now: missing pillar proxies are z-scored over whatever's available that month,
then imputed to 0 (the z-scored mean - "no extra information" for that stock-month) rather
than dropping the row, matching the live composite_score's own tolerance for partial pillar
availability (loaders/load_stock_scores.py's base_weights loop skips unavailable metrics and
renormalizes over what's present, rather than requiring every metric). Also fixed two
staleness bugs found while rebuilding value_proxy/momentum_proxy to match the live formulas
(they still used pre-2026-08-25-redesign weights) - see those proxies' inline comments.
Result: median cross-section jumped from 850 to ~6,500 symbols.

SIZE AS 7TH PILLAR - reconciled 2026-08-25 (concurrent-session merge). A separate pass
(landed on main as commit 92b685119, based on the ORIGINAL pre-redesign version of this
script) independently asked the same question this file's docstring already flagged as
underpowered: does log(market_cap) retain independent significance as a 7th top-level factor,
controlling for all 6 real pillars jointly? That pass found t=0.47 (not significant) but
reasoned analytically that this was likely a sample-selection artifact (the same
strict-all-6-required bias this redesign pass fixes empirically) rather than fixing the bias
and re-measuring. SEVEN_COLS/size_proxy from that pass are kept here, now running on the
properly-repowered partial-availability sample instead of the original underpowered one - see
the run() output for the actual (not theoretical) answer this produces.

ACTED ON 2026-08-26: after 4 independent measurements across 2 days all found size_proxy
dramatically stronger than every other pillar (t=-5.37 standalone genesis test, t=4.42
independent re-confirmation, t=8.86 double-counted, t=7.62/7.63 clean corrected, reproduced
live one more time immediately before acting), Size was promoted from a Value sub-component to
its own real top-level 7th pillar in loaders/load_stock_scores.py (BASE_PILLAR_WEIGHTS now has
a "size": 0.20 key; the other 6 weights scaled x0.8). This means `value_proxy` below (which
still includes a `-size*0.20` term to match the OLD live formula for historical/comparison
purposes) no longer matches _score_value's CURRENT live weights - `value_proxy_nosize` is now
the accurate live decomposition of what "value" means in the composite, and `size_proxy` is a
real top-level factor, not merely an optional SEVEN_COLS add-on. Left the regression code
itself unchanged (both proxies were already computed every run, just re-labeled in
interpretation) rather than rewriting this diagnostic script's internals - the two docstring
notes above are kept as historical narrative of how the promotion question was investigated.

Usage:
    python -m algo.research.fama_macbeth_composite_weights [options]
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_growth_factors import (
    REPORTING_LAG_DAYS,
    fetch_annual_fundamentals,
    merge_asof_monthly,
)
from algo.research.fama_macbeth_momentum_factors import (
    build_month_end_panel,
    compute_daily_indicators,
)
from algo.research.fama_macbeth_momentum_factors import (
    fetch_daily_prices as fetch_daily_close,
)
from algo.research.fama_macbeth_positioning_factors import (
    compute_ad_rating_series,
    fetch_daily_ohlcv,
)
from algo.research.fama_macbeth_price_factors import (
    _fama_macbeth,
    _trailing_cumret,
    fetch_month_end_prices,
)
from algo.research.fama_macbeth_quality_factors import build_quality_panel, fetch_annual_quality_fundamentals
from algo.research.fama_macbeth_value_factors import fetch_annual_value_fundamentals
from loaders.load_stock_scores import BASE_PILLAR_WEIGHTS

logger = logging.getLogger(__name__)

PILLAR_COLS = ["growth_proxy", "value_proxy", "quality_proxy", "stability_proxy", "momentum_proxy", "positioning_proxy"]

# ADDED 2026-08-25 (goal: real-money-readiness follow-up, landed on main as commit 92b685119)
# to answer a specific open question: does log(market_cap) (the Size factor, t=-5.37 standalone
# per stock_scores_size_factor_missing_and_composite_weights_tested_20260825) retain independent
# significance when controlling for ALL SIX existing pillar proxies jointly, not just alone?
# If yes, that's real evidence Size carries information the other 6 pillars don't already
# capture between them - the right bar for "does this deserve its own top-level composite
# slot" per Grinold & Kahn's IC-weighting framework, same standard this whole script applies
# to the other 6. Uses "value_proxy_nosize" (PE/PB/PS/FCF/Div only) instead of the real
# value_proxy for this one test - value_proxy already has Size baked in at 20% internal
# weight, so testing it alongside a separate size_proxy double-counts Size's contribution
# (confirmed directly: doing so gives size_proxy t=8.86 and value_proxy t=-5.46, a
# double-counting collinearity artifact, not a clean read). Kept as a strict ADDITION
# (SEVEN_COLS) rather than replacing PILLAR_COLS, so the original 6-pillar run (which
# correctly uses the real, Size-inclusive value_proxy, matching the live formula) stays
# reproducible unchanged - this augments it, doesn't replace it.
SEVEN_COLS = [
    "growth_proxy",
    "value_proxy_nosize",
    "quality_proxy",
    "stability_proxy",
    "momentum_proxy",
    "positioning_proxy",
    "size_proxy",
]


def _zwinsor(s: pd.Series) -> pd.Series:
    s = s.replace([np.inf, -np.inf], np.nan)
    lo, hi = s.quantile([0.01, 0.99])
    s = s.clip(lo, hi)
    std = s.std()
    return (s - s.mean()) / std if std and std > 0 else s * 0.0


def build_growth_and_sgr_panel() -> pd.DataFrame:
    fund = fetch_annual_fundamentals()
    fund = fund.sort_values(["symbol", "fiscal_year"]).reset_index(drop=True)
    g = fund.groupby("symbol", group_keys=False)

    def growth(col: str, n: int = 1) -> pd.Series:
        prior = g[col].shift(n)
        valid = (prior > 0) & (fund[col] > 0)
        out = pd.Series(np.nan, index=fund.index)
        out[valid] = (fund[col][valid] / prior[valid]) ** (1.0 / n) - 1.0
        return out

    out = fund[["symbol", "fiscal_year"]].copy()
    out["eps_growth_1y"] = growth("eps")
    out["revenue_growth_1y"] = growth("revenue")
    out["asset_growth_yoy"] = growth("total_assets")
    out["known_date"] = pd.to_datetime(fund["fiscal_year"].astype(str) + "-12-31") + pd.Timedelta(
        days=REPORTING_LAG_DAYS
    )
    return out.dropna(subset=["known_date"])


def build_sgr_panel() -> pd.DataFrame:
    """Sustainable growth rate = ROE * retention ratio, from quality fundamentals.

    FIXED 2026-08-26 (found while rebuilding quality_proxy - this script had never actually
    run since fama_macbeth_quality_factors.py's fetch_annual_quality_fundamentals() gained its
    own dividends_paid column, 2026-08-26's payout_ratio work): previously merged in
    dividends_paid from fetch_annual_value_fundamentals() even though the quality fetch already
    carries the same annual_cash_flow-sourced column - the merge silently suffixed both to
    dividends_paid_x/_y, and the plain "dividends_paid" lookup below raised a bare KeyError.
    Quality's own dividends_paid is the same underlying data; the value-side merge was
    redundant, not a second source of truth - dropped it.
    """
    q = fetch_annual_quality_fundamentals()
    roe = np.where(q["stockholders_equity"] > 0, q["net_income"] / q["stockholders_equity"], np.nan)
    retention = np.where(q["net_income"] > 0, 1.0 - q["dividends_paid"].abs() / q["net_income"], np.nan)
    out = q[["symbol", "fiscal_year"]].copy()
    out["sustainable_growth_rate"] = roe * retention
    out["known_date"] = pd.to_datetime(q["fiscal_year"].astype(str) + "-12-31") + pd.Timedelta(days=REPORTING_LAG_DAYS)
    return out.dropna(subset=["known_date"])


def build_value_panel_raw() -> pd.DataFrame:
    fund = fetch_annual_value_fundamentals()
    shares = fund["shares_diluted"]
    out = fund[["symbol", "fiscal_year"]].copy()
    out["eps"] = fund["eps"]
    out["book_value_per_share"] = fund["stockholders_equity"] / shares
    out["sales_per_share"] = fund["revenue"] / shares
    out["fcf_per_share"] = fund["free_cash_flow"] / shares
    out["dividend_per_share"] = fund["dividends_paid"].abs() / shares
    out["shares_diluted"] = shares
    out["known_date"] = pd.to_datetime(fund["fiscal_year"].astype(str) + "-12-31") + pd.Timedelta(
        days=REPORTING_LAG_DAYS
    )
    return out.dropna(subset=["known_date"])


def run(start_date: str, end_date: str, min_cross_section: int) -> None:
    logger.info("Building fundamentals panels (growth/value/quality/SGR)")
    growth_fund = build_growth_and_sgr_panel()
    sgr_fund = build_sgr_panel()
    value_fund = build_value_panel_raw()
    # REBUILT 2026-08-26 (goal: answer "does Quality's CURRENT formula still hold up combined
    # with the other 5 pillars" - this proxy was stale, still built from the ORIGINAL base-6
    # equal-weighted formula (roe/roa/operating_margin/net_margin/debt_to_assets/
    # interest_coverage) from before ANY of 2026-08-26's three quality rebuilds (cluster-9,
    # Altman Z added, then the current ROCE/FCF-Margin/D2E 8-component composite). Reuses
    # fama_macbeth_quality_factors.py's own build_quality_panel() instead of re-deriving the
    # same ratios a second time here - that module is the source of truth for these formulas.
    quality_fund = build_quality_panel(fetch_annual_quality_fundamentals())

    logger.info("Fetching price panel + momentum/stability indicators")
    price_df = fetch_month_end_prices(start_date, end_date)
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    ret = px.pct_change(fill_method=None)
    mkt = ret["SPY"]
    months = px.index

    # NOTE: indicators/ad_panel are built from independent daily pulls, so their own month
    # indices can differ in dtype (datetime64[M] vs px's plain `date` objects) and coverage
    # from px's `months`. Reindex everything to px's own month sequence (by calendar-month
    # label, via PeriodIndex, which is dtype-agnostic) before any positional .iloc[i] access -
    # mixing dtypes here previously caused a silent "month in ad_panel.index" false-negative
    # that made positioning_proxy always empty and killed every cross-section.
    months_period = pd.PeriodIndex(months, freq="M")

    daily_close = fetch_daily_close(start_date, end_date)
    daily_close = compute_daily_indicators(daily_close)
    _px_daily, indicators = build_month_end_panel(daily_close)
    for key in indicators:
        indicators[key] = (
            indicators[key].set_axis(pd.PeriodIndex(indicators[key].index, freq="M")).reindex(months_period)
        )

    daily_ohlcv = fetch_daily_ohlcv(start_date, end_date)
    ad_rating = compute_ad_rating_series(daily_ohlcv)
    daily_ohlcv = daily_ohlcv.set_index(["symbol", "date"])
    daily_ohlcv["ad_rating"] = ad_rating
    daily_ohlcv = daily_ohlcv.reset_index()
    daily_ohlcv["month"] = daily_ohlcv["date"].values.astype("datetime64[M]")
    ad_monthly = daily_ohlcv.sort_values("date").groupby(["symbol", "month"], as_index=False).last()
    ad_panel = ad_monthly.pivot(index="month", columns="symbol", values="ad_rating").sort_index()
    ad_panel = ad_panel.set_axis(pd.PeriodIndex(ad_panel.index, freq="M")).reindex(months_period)

    growth_monthly = merge_asof_monthly(
        months, growth_fund, cols=["eps_growth_1y", "revenue_growth_1y", "asset_growth_yoy"]
    )
    sgr_monthly = merge_asof_monthly(months, sgr_fund, cols=["sustainable_growth_rate"])
    value_monthly = merge_asof_monthly(
        months,
        value_fund,
        cols=[
            "eps",
            "book_value_per_share",
            "sales_per_share",
            "fcf_per_share",
            "dividend_per_share",
            "shares_diluted",
        ],
    )
    quality_monthly = merge_asof_monthly(
        months,
        quality_fund,
        cols=["roe", "roa", "roce", "fcf_margin", "debt_to_equity", "interest_coverage", "payout_ratio"],
    )

    beta_window = 24
    vol_window = 12
    records: list[tuple[pd.Timestamp, pd.DataFrame]] = []

    for i in range(beta_window, len(months) - 1):
        month = months[i]

        g = growth_monthly.get(month)
        s = sgr_monthly.get(month)
        v = value_monthly.get(month)
        q = quality_monthly.get(month)
        if g is None or s is None or v is None or q is None or g.empty or v.empty or q.empty:
            continue

        growth_proxy = (
            0.25 * _zwinsor(g["eps_growth_1y"])
            + 0.30 * _zwinsor(-g["asset_growth_yoy"])
            + 0.20 * _zwinsor(g["revenue_growth_1y"])
            + 0.20 * _zwinsor(s["sustainable_growth_rate"])
        )

        price = px.iloc[i].reindex(v.index)
        pe = np.where(v["eps"] > 0, price / v["eps"], np.nan)
        pb = np.where(v["book_value_per_share"] > 0, price / v["book_value_per_share"], np.nan)
        ps = np.where(v["sales_per_share"] > 0, price / v["sales_per_share"], np.nan)
        fcf_yield = v["fcf_per_share"] / price
        dividend_yield = v["dividend_per_share"] / price
        # Known data-quality issue (see SHARES_OUTSTANDING_SCALE_MISMATCH_RATIO in
        # load_value_quality_growth_metrics.py / memory's shares-outstanding-scale-error
        # findings): a small number of symbols have corrupted shares_diluted values (observed
        # up to 3.5e15 - no real company has ever had anywhere near that many shares
        # outstanding). Sanity-bound market cap to a real-world plausible range ($1M-$10T,
        # covering everything from micro-caps to the largest companies in history) before
        # taking log10, so a handful of corrupted rows can't distort a whole month's z-score
        # via the winsorization quantile boundaries. Outside this range, treat as missing
        # (NaN) rather than a garbage extreme - it gets zero-imputed downstream like any other
        # unavailable pillar input. Reused below for size_proxy too (SEVEN_COLS test), so the
        # 7-factor run gets the same sanity guard as value_proxy's own Size sub-component.
        market_cap = price * v["shares_diluted"]
        log_mc = np.where((market_cap >= 1e6) & (market_cap <= 1e13), np.log10(market_cap), np.nan)
        # PE/PB/PS weights REVERSED 2026-08-25 (later same day, following
        # value_pe_pb_ps_ranking_reversed_selection_bias_fix_20260825): the original
        # fama_macbeth_value_factors.py test (and this proxy's own earlier weights) shared a
        # selection-bias flaw requiring all inputs simultaneously non-null - implicitly
        # requiring positive earnings, excluding unprofitable/small/distressed firms. A
        # bias-corrected rerun reversed the ranking: PB is now the strongest of the three
        # multiples, PE the weakest.
        # value_proxy_nosize: same PE/PB/PS/FCF/Div weights, Size term dropped - used ONLY for
        # the SEVEN_COLS test below, alongside a separate size_proxy. Testing value_proxy
        # (which already has Size baked in at 20%) next to a standalone size_proxy double-
        # counts Size's contribution - confirmed directly: doing so gave size_proxy t=8.86 and
        # value_proxy t=-5.46, the same "counted twice" collinearity artifact already caught
        # elsewhere in this codebase (Momentum's redundant windows, Value's own EV/EBITDA/PE
        # duplication). value_proxy_nosize + size_proxy avoids that overlap.
        value_proxy_nosize = (
            0.10 * _zwinsor(-pd.Series(pe, index=v.index))
            + 0.22 * _zwinsor(-pd.Series(pb, index=v.index))
            + 0.21 * _zwinsor(-pd.Series(ps, index=v.index))
            + 0.10 * _zwinsor(fcf_yield)
            + 0.03 * _zwinsor(dividend_yield)
        )
        value_proxy = value_proxy_nosize + 0.20 * _zwinsor(-pd.Series(log_mc, index=v.index))

        # REBUILT 2026-08-26 to match _score_quality's CURRENT live weights (ROA/ROCE/D2E 18%
        # each, FCF Margin 15%, ROE 11%, Altman Z 10%, Interest Coverage/Payout 5% each - see
        # quality_fund's own comment). Altman Z is deliberately EXCLUDED here and the remaining
        # 7 weights renormalized to sum to 1.0 (11/18/18/15/18/5/5 = 90 -> /0.90): unlike every
        # other component, Altman Z's retained_earnings input has ~23% overall coverage and is
        # effectively 0% before 2023-03 (see quality_pillar_altman_z_added_and_reweighted_20260826
        # in MEMORY.md) - since this proxy is a plain additive sum (one NaN term nukes the whole
        # row, unlike production's per-symbol renormalize-over-available), including it would
        # make quality_proxy NaN for most of 2014-2023 and get zero-imputed as "no information"
        # by this script's own pillar-level fallback - understating Quality's real signal for
        # the 7 well-covered components across most of the panel. Same "isolate the sparse
        # candidate" precedent fama_macbeth_quality_factors.py itself already applies
        # (ALTMAN_CANDIDATE_COLS's own dropna-poisoning fix).
        quality_proxy = (
            (11.0 / 90.0) * _zwinsor(q["roe"])
            + (18.0 / 90.0) * _zwinsor(q["roa"])
            + (18.0 / 90.0) * _zwinsor(q["roce"])
            + (15.0 / 90.0) * _zwinsor(q["fcf_margin"])
            + (18.0 / 90.0) * _zwinsor(-q["debt_to_equity"])
            + (5.0 / 90.0) * _zwinsor(q["interest_coverage"])
            + (5.0 / 90.0) * _zwinsor(q["payout_ratio"])
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
        mom_12_1 = _trailing_cumret(px, i - 1, 11)  # skip most-recent month (Jegadeesh 1990)
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

        positioning_proxy = _zwinsor(ad_panel.iloc[i])

        # SIZE PROXY (SEVEN_COLS test, see module docstring "SIZE AS 7TH PILLAR"): oriented
        # like every other proxy here (higher = better/more bullish forward-return signal), so
        # sign-flipped from the sanity-bounded log_mc computed above - smaller companies showed
        # the positive forward-return premium (Banz 1981 / t=-5.37 on raw log(market_cap) vs
        # return, i.e. return falls as size rises).
        size_proxy = _zwinsor(-pd.Series(log_mc, index=v.index))

        fwd_ret = ret.iloc[i + 1]

        # RELAXED PANEL CONSTRUCTION (2026-08-25, reconstructed 2026-08-25 after this session's
        # own composite-weights redesign was lost to an uncommitted-work race - see
        # [[composite_weights_reweighted_size_factor_reconfirmed_20260825]]): pd.DataFrame({...})
        # from a dict of Series already aligns on the UNION of all 7 proxy indices plus
        # fwd_ret's own (broadest - every symbol with price data), not their intersection.
        # Previously this frame went straight into .dropna() with no subset=, which silently
        # required all 6 pillars (+size) simultaneously non-null per symbol-month - the same
        # "underpowered, tilts toward larger/more-established names" sample-selection bias this
        # file's own base_weights docstring note already flags (850-symbol median vs ~2,600 for
        # a single-pillar test). Only fwd_ret is required now; each pillar proxy is ALREADY
        # z-scored at construction (mean~0/std~1 over its own available sub-universe), so a
        # missing pillar is filled with 0 (the neutral/average value after z-scoring) instead of
        # dropping the whole symbol-month row - matching the live composite formula's own
        # "skip unavailable, renormalize over what's present" tolerance.
        frame = pd.DataFrame(
            {
                "growth_proxy": growth_proxy,
                "value_proxy": value_proxy,
                "value_proxy_nosize": value_proxy_nosize,
                "quality_proxy": quality_proxy,
                "stability_proxy": stability_proxy,
                "momentum_proxy": momentum_proxy,
                "positioning_proxy": positioning_proxy,
                "size_proxy": size_proxy,
                "fwd_ret": fwd_ret,
            }
        )
        # REDESIGNED 2026-08-25 (goal: fix the underpowered original test - see module
        # docstring "PARTIAL-AVAILABILITY REDESIGN" note). Previously required all 6 pillar
        # proxies non-null (dropna() on the whole frame), which only kept symbol-months where
        # a stock had BOTH full annual-fundamentals coverage (growth/value/quality, ~5,700
        # symbols) AND full price-history coverage (stability/momentum/positioning, up to
        # 10,982 symbols) - shrinking the sample to 109 months/850 symbols and likely biasing
        # toward larger, more-established names. Now: only fwd_ret is mandatory (can't test
        # without an outcome); each pillar proxy is z-scored over whatever's actually
        # available that month, THEN missing pillars are imputed to 0 (the z-scored mean -
        # "no extra information beyond average" for that stock-month, not zero return) rather
        # than dropping the row. This mirrors the live composite_score's own "skip
        # unavailable, renormalize over what's present" tolerance (loaders/load_stock_scores.py
        # base_weights loop) instead of an artificially strict all-6-required test that
        # doesn't match how the production formula actually combines partial data.
        # value_proxy_nosize/size_proxy (built off value_monthly's narrower index) need the
        # same post-alignment treatment as PILLAR_COLS - loop over the union of both column
        # sets (PILLAR_COLS already contains "value_proxy"; SEVEN_COLS adds
        # "value_proxy_nosize" and "size_proxy") so every column actually used by either test
        # gets z-scored/imputed, not just whichever list happens to be iterated last.
        frame = frame.replace([np.inf, -np.inf], np.nan)
        frame = frame.dropna(subset=["fwd_ret"])
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        if len(frame) < min_cross_section:
            continue

        for col in dict.fromkeys([*PILLAR_COLS, *SEVEN_COLS]):
            frame[col] = _zwinsor(frame[col]).fillna(0.0)

        records.append((month, frame))

    if not records:
        raise RuntimeError("No usable cross-sectional months - pillars may not overlap enough symbols")

    sizes = [len(f) for _, f in records]
    print(f"Usable cross-sectional months: {len(records)}  ({records[0][0]} to {records[-1][0]})")
    print(f"Median cross-section size: {int(np.median(sizes))}\n")

    # ADDED 2026-08-26 (goal: diagnose quality_proxy's multivariate sign once it was rebuilt to
    # match the current live formula - a negative/flipped multivariate coefficient next to a
    # positive univariate one is the classic signature of multicollinearity between regressors,
    # not necessarily a real reversal; check the actual pairwise correlations before trusting
    # either sign at face value).
    pooled = pd.concat([f for _, f in records], ignore_index=True)
    corr_cols = [*dict.fromkeys([*PILLAR_COLS, "size_proxy"])]
    print("=== Pooled pillar-proxy pairwise correlations (multicollinearity diagnostic) ===")
    print(pooled[corr_cols].corr().round(2).to_string())
    print()

    print("=== Multivariate Fama-MacBeth: TOP-LEVEL pillar combination (6 pillars) ===")
    print(f"{'pillar':18s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
    multi = _fama_macbeth(records, PILLAR_COLS)
    for name, (mean, t) in multi.items():
        print(f"{name:18s} {mean:10.5f} {t:8.2f} {len(records):9d}")

    print("\n=== Univariate Fama-MacBeth (each pillar's current formula, alone) ===")
    print(f"{'pillar':18s} {'mean_coef':>10s} {'t_stat':>8s}")
    for c in PILLAR_COLS:
        uni = _fama_macbeth(records, [c])
        mean, t = uni[c]
        print(f"{c:18s} {mean:10.5f} {t:8.2f}")

    # ADDED 2026-08-25 (commit 92b685119, now run on the fixed partial-availability sample
    # instead of the original underpowered one): does Size retain independent significance
    # once it has to compete with ALL 6 existing pillars in the SAME multivariate regression?
    print("\n=== Multivariate Fama-MacBeth: TOP-LEVEL pillar combination + SIZE (7 factors) ===")
    print(f"{'pillar':18s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
    multi7 = _fama_macbeth(records, SEVEN_COLS)
    for name, (mean, t) in multi7.items():
        print(f"{name:18s} {mean:10.5f} {t:8.2f} {len(records):9d}")

    print("\n=== Univariate Fama-MacBeth: SIZE alone (same sample as above) ===")
    uni_size = _fama_macbeth(records, ["size_proxy"])
    mean, t = uni_size["size_proxy"]
    print(f"{'size_proxy':18s} {mean:10.5f} {t:8.2f}")

    live_weights = " ".join(f"{k}={v}" for k, v in BASE_PILLAR_WEIGHTS.items())
    print(
        f"\nCurrent live base_weights: {live_weights}"
        " (size_proxy has no top-level slot - it's a 20% sub-component inside value_proxy's live"
        " formula only, effective top-level weight ~4%)"
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
