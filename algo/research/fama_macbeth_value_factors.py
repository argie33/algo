#!/usr/bin/env python3
"""
Fama-MacBeth cross-sectional regression harness for the Value pillar.

Built 2026-08-25 (goal: re-audit ALL stock_scores inputs without bias toward what already
shipped). Reconstructs point-in-time per-share fundamentals from
annual_income_statement/annual_balance_sheet/annual_cash_flow (same tables and same
calendar-FYE + 90-day-lag point-in-time approximation as
algo/research/fama_macbeth_growth_factors.py - see that module's docstring for the caveat),
merges onto the monthly price panel, and tests P/E, P/B, P/S, FCF yield, dividend yield,
EV/EBITDA, and EV/Revenue jointly. PEG (needs a growth-rate cross-term) and margin-of-safety/
DCF discount (a full valuation model, not a single ratio, and already under separate active
audit per DCF-related fixes landed 2026-08-25) are OUT OF SCOPE here - not tested.

UPDATED 2026-08-25 (same day, later pass - goal: check whether Value's OWN internal weighting
combines its inputs efficiently, following up on
[[composite_weights_reweighted_size_factor_reconfirmed_20260825]]'s side-finding that
value_proxy at live weights scored notably weaker than a standalone Size test). EV/EBITDA and
EV/Revenue REMOVED from VALUE_FACTOR_COLS - already confirmed as PE/PS duplicates and removed
from the live formula the same day (r=1.00/0.93, see load_stock_scores.py's Value docstring),
so re-testing them here would just restate an already-closed finding. Size (log10 market cap,
same point-in-time price*shares_diluted reconstruction as
algo/research/fama_macbeth_composite_weights.py, same sanity bound against the known
shares_diluted scale-error outliers) ADDED, since it's now a live Value input (20% weight) that
this script predates. VALUE_FACTOR_COLS now matches the CURRENT live Value formula's testable
inputs exactly: PE/PB/PS/FCF-yield/dividend-yield/Size (PEG/margin-of-safety still out of scope
per the reasons above).

UPDATED 2026-08-26 (goal: full Value pillar re-audit - user explicitly asked not to just accept
the inherited PE/PB/PS/PEG/FCF/Div/MoS/Amihud list, but to re-derive the best inputs from
literature + our own validation, same rigor as the Quality pillar's re-audit; also flagged two
specific doubts: whether Amihud illiquidity belongs in Value at all, and whether DCF margin of
safety double-counts the other multiples). Closes the two "out of scope" gaps from the original
build:

(1) PEG now computed: `peg = pe / eps_growth_pct` (Peter Lynch convention, growth expressed as
whole percentage points e.g. 20.0 for 20%, matching load_sec_valuations.py's own convention) -
only defined when both pe (needs eps>0) and eps_growth_pct>0 are meaningful, same "not
well-defined off a negative/zero base" rule fama_macbeth_growth_factors.py already uses.
eps_growth_pct itself is a new column: YoY EPS growth from the prior fiscal year's reported EPS,
reconstructed the same point-in-time way as every other fundamental here.

(2) Margin of safety now computed via a REPLICATION of load_sec_valuations.py's real two-stage
FCFE DCF (_compute_dcf_intrinsic_value): same 5-year linear growth-fade to
DCF_TERMINAL_GROWTH_RATE (2.5%), same DCF_GROWTH_FLOOR/CEILING clamp (-10%/+15%), same Gordon
Growth terminal value, same $1M/share plausibility ceiling. KNOWN SIMPLIFICATIONS vs. the real
pipeline (flagged, not hidden): (a) discount rate uses the CAPM formula's flat DEFAULT inputs
(beta=1.0, risk_free_rate=4.5%, equity_risk_premium=5.0% -> always 9.5%) rather than each
symbol's live beta and the VIX-scaled dynamic ERP - this script has no historical
beta/risk-free-rate/VIX panel to draw on, so cross-sectional variation in the reconstructed
margin_of_safety here comes entirely from FCF/growth/price differences, not risk-adjustment
differences; this likely understates how the real pipeline differentiates high- vs low-risk
names, but should still be a fair test of whether "discount to a model intrinsic value" per se
carries information. (b) fcf_base uses `annual_cash_flow.free_cash_flow` directly (the same
field fcf_yield is built from) rather than production's OCF-CapEx-SBC+net_borrowing FCFE
refinement (see load_sec_valuations.py's dcf_fcf_base construction, landed across the
2026-08-25 DCF audit passes) - the SBC deduction and net-borrowing data aren't available in this
script's existing fetch, and replicating them was judged out of proportion to what this specific
question (does a DCF-style signal add information beyond the multiples?) needs. Both
simplifications bias toward UNDERSTATING the real pipeline's discriminating power, not
overstating it - a meaningful multivariate t-stat here is a lower bound on the live MoS input's
real signal, not an inflated one.

Amihud illiquidity: monthly per-symbol Amihud (same |daily return|/dollar-volume construction as
algo/research/fama_macbeth_liquidity_factor.py, reused here via that module's
fetch_daily_panel/compute_monthly_amihud) merged onto this script's monthly cross-sections.
Tested two ways: (i) LIVE_VALUE_FACTOR_COLS - alongside PE/PB/PS/PEG/FCF/Div/MoS, matching the
current live 8-input Value formula exactly, to see whether it earns its keep against the
fundamentals-to-price ratios it currently sits beside; (ii) a diagnostic-only variant that also
controls for `size` (log market cap) directly, since Amihud's own dedicated validation script
(fama_macbeth_liquidity_factor.py) only controlled for log(dollar volume) as a liquidity-family
size proxy, not real market cap, and this script already reconstructs real point-in-time size -
answers "does Amihud survive controlling for the actual size factor the user already rejected as
a live scored input" more directly than the original validation could.

Ratio convention: every ratio computed from PER-SHARE fundamentals (book value/share, sales/
share, FCF/share, dividend/share, EBITDA/share, net-debt/share) merged with price at scoring
time, so no separate share-count series needs re-joining - e.g. P/B = price / book_value_per_
share, EV/EBITDA = (price + net_debt_per_share) / ebitda_per_share. EBITDA is approximated as
operating_income + depreciation_expense + amortization_expense (this repo's annual_income_
statement schema has no direct EBITDA field). Ratios only computed when both price and the
per-share denominator are positive/defined - a P/E off negative earnings isn't a meaningful
"cheap vs expensive" signal, so those are left NaN rather than guessed, matching
fama_macbeth_growth_factors.py's growth-rate convention.

UPDATED 2026-08-26 (3rd pass, same day - user asked two follow-up questions after the input-list
and missing-input passes above: (a) does the actual BLENDED formula work, not just each input's
own coefficient in isolation, and (b) is Fama-MacBeth itself trustworthy here, or could the
method be skewing the results). Added:

(3) COMPOSITE SCORE BACKTEST: `_replicate_live_composite_score`/`_equal_weighted_composite_score`
replicate load_stock_scores.py._score_value's exact piecewise curves and real production weights
(LIVE_VALUE_WEIGHTS) from this script's raw (pre-z-score) ratios, then test the BLENDED output -
quintile spread, FM regression, and Spearman rank IC - against forward returns. Result: strong
and robust (full sample t=5.9-6.0 across all three methods; sub-periods t=3.2-4.0 first half,
t=5.2-5.6 second half) - the pillar's actual output does what it's supposed to. Equal-weighting
the same 7 inputs performs statistically indistinguishably from the live percentages (differences
smaller than the noise) in every window tested - honest finding: input SELECTION is what's
carrying this pillar's performance, not the specific weight percentages. Those percentages are a
reasoned, evidence-directed allocation, not a proven-optimal one; a formal optimization (e.g.
ridge regression against forward returns) is the real next step if squeezing out that residual
is wanted, not assumed already done here.

(4) METHODOLOGY CROSS-CHECK: added Spearman rank IC (Information Coefficient) alongside the
existing quintile-spread and FM-regression checks on the composite score - a statistic that
shares nothing with FM/OLS (no linearity assumption, no z-scoring, rank-based instead of
regression-based). All three methods converge tightly in every window tested (see (3) above) -
this is triangulation from independent methods, not one method's assumptions read back as
confirmation. Fama-MacBeth itself is the standard tool for this exact question (Fama & MacBeth
1973; see fama_macbeth_price_factors.py's own docstring for why it's used here over a pooled
panel specifically - pooled panels treat every symbol-month as independent, understating
same-month correlation and overstating significance, which this repo's own history already
caught doing exactly that on the PE-vs-PB/PS ranking question, see
value_pe_pb_ps_ranking_reversed_selection_bias_fix_20260825 memory) - not a novel or risky
choice, and now independently corroborated on this pillar's own composite output specifically,
not just asserted as generically sound.

Usage:
    python -m algo.research.fama_macbeth_value_factors [options]
    (same --start-date/--end-date/--min-cross-section/--horizon-months args as the growth harness)
"""

import argparse
import logging
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_growth_factors import compute_known_dates, merge_asof_monthly
from algo.research.fama_macbeth_liquidity_factor import compute_monthly_amihud, fetch_daily_panel
from algo.research.fama_macbeth_price_factors import _fama_macbeth, fetch_month_end_prices
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

# Replicated from load_sec_valuations.py's SecValuationsLoader class constants - see this
# module's docstring, point (2), for what this replication does and doesn't match exactly.
DCF_TERMINAL_GROWTH_RATE = 0.025
DCF_GROWTH_FLOOR = -0.10
DCF_GROWTH_CEILING = 0.15
DCF_FORECAST_YEARS = 5
DCF_FLAT_DISCOUNT_RATE = 0.095  # rfr=4.5% + Blume-adjusted beta(1.0)=1.0 * erp=5.0%, this
# script's fixed approximation (see docstring) for load_sec_valuations.py's real per-symbol,
# per-day CAPM rate.
DCF_MAX_INTRINSIC_PER_SHARE = 1_000_000.0

# "size" kept here for backward comparability with this script's own PE/PB/PS ranking history
# (its multivariate spec controls for size the same way live _score_value used to, back when
# Size was a sub-component of Value) - it no longer represents a live Value input as of
# 2026-08-26, when Size was promoted to its own top-level pillar and then REMOVED ENTIRELY on
# user directive the same day (see loaders/load_stock_scores.py's BASE_PILLAR_WEIGHTS and
# size_pillar_removed_entirely_20260826 memory - market_cap must not be reintroduced as a live
# scored input, pillar or sub-component, without new explicit user direction). Kept here ONLY as
# a diagnostic control column (see docstring's Amihud section) - never added back to
# LIVE_VALUE_FACTOR_COLS.
SIZE_CONTROL_COL = "size"
# UPDATED 2026-08-26 (2nd pass, same day): reflects the TRUE current live formula after both
# passes landed - amihud REMOVED (see AMIHUD ILLIQUIDITY docstring section), dividend_yield
# REPLACED by net_payout_yield (see MISSING-INPUT CHECK section). This is now exactly the 7
# inputs load_stock_scores.py._score_value actually weights (12/30/27/7/9/8/7).
LIVE_VALUE_FACTOR_COLS = ["pe", "pb", "ps", "peg", "fcf_yield", "net_payout_yield", "margin_of_safety"]
VALUE_FACTOR_COLS = LIVE_VALUE_FACTOR_COLS  # backward-compat alias for existing callers/tests
# Production weights, same order as LIVE_VALUE_FACTOR_COLS - used by _replicate_live_composite_score
# below for the composite-score backtest (see run()'s "COMPOSITE SCORE BACKTEST" section).
LIVE_VALUE_WEIGHTS = {
    "pe": 0.12,
    "pb": 0.30,
    "ps": 0.27,
    "peg": 0.07,
    "fcf_yield": 0.09,
    "net_payout_yield": 0.08,
    "margin_of_safety": 0.07,
}

# CANDIDATE inputs NOT currently live - checked 2026-08-26 (goal: "have we identified every
# literature-established value input, not just weighted the ones we already have") alongside
# the Amihud/PEG/MoS work above. net_payout_yield (originally tested here) is now LIVE - see
# LIVE_VALUE_FACTOR_COLS above - only ocf_yield remains a candidate:
# - ocf_yield: operating cash flow / price - O'Shaughnessy's "What Works on Wall Street"
#   price-to-cash-flow value composite input. Distinct from fcf_yield (OCF minus CapEx) - less
#   sensitive to one lumpy CapEx year. Flagged (not acted on) - tangled with fcf_yield's own
#   already-flagged wrong-sign concern, see load_stock_scores.py's _score_value docstring.
CANDIDATE_COLS = ["ocf_yield"]


def fetch_annual_value_fundamentals() -> pd.DataFrame:
    sql = """
        SELECT i.symbol, i.fiscal_year,
               COALESCE(i.diluted_eps, i.eps) AS eps,
               i.revenue, i.operating_income,
               i.depreciation_expense, i.amortization_expense,
               i.shares_outstanding_diluted,
               b.stockholders_equity, b.long_term_debt, b.short_term_debt, b.cash_and_equivalents,
               c.free_cash_flow, c.dividends_paid, c.operating_cash_flow, c.common_stock_repurchased
        FROM annual_income_statement i
        LEFT JOIN annual_balance_sheet b ON b.symbol = i.symbol AND b.fiscal_year = i.fiscal_year
        LEFT JOIN annual_cash_flow c ON c.symbol = i.symbol AND c.fiscal_year = i.fiscal_year
        WHERE i.fiscal_year BETWEEN 2000 AND 2026
          AND COALESCE(i.data_unavailable, false) = false
          AND i.shares_outstanding_diluted > 0
        ORDER BY i.symbol, i.fiscal_year
    """
    with DatabaseContext("read") as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    cols = [
        "symbol",
        "fiscal_year",
        "eps",
        "revenue",
        "operating_income",
        "depreciation_expense",
        "amortization_expense",
        "shares_diluted",
        "stockholders_equity",
        "long_term_debt",
        "short_term_debt",
        "cash_and_equivalents",
        "free_cash_flow",
        "dividends_paid",
        "operating_cash_flow",
        "common_stock_repurchased",
    ]
    df = pd.DataFrame(rows, columns=cols)
    for c in cols:
        if c not in ("symbol", "fiscal_year"):
            df[c] = df[c].astype(float)
    return df


def build_value_panel(fund: pd.DataFrame) -> pd.DataFrame:
    shares = fund["shares_diluted"]
    # See fama_macbeth_quality_factors.py's build_quality_panel() comment on net_debt_to_ebitda
    # (2026-08-27) - COALESCE(...,0)-in-SQL treatment for D&A silently scores ~50-70% of
    # firm-years as zero D&A. ev_ebitda is currently dead (removed from VALUE_FACTOR_COLS, see
    # this file's own comment near line 197) but fixed here too for correctness if ever revived.
    da_reported = fund["depreciation_expense"].notna() & fund["amortization_expense"].notna()
    ebitda = np.where(
        da_reported,
        fund["operating_income"] + fund["depreciation_expense"].fillna(0) + fund["amortization_expense"].fillna(0),
        np.nan,
    )
    net_debt = (
        fund["long_term_debt"].fillna(0) + fund["short_term_debt"].fillna(0) - fund["cash_and_equivalents"].fillna(0)
    )

    out = fund[["symbol", "fiscal_year"]].copy()
    out["eps"] = fund["eps"]
    out["book_value_per_share"] = fund["stockholders_equity"] / shares
    out["sales_per_share"] = fund["revenue"] / shares
    out["fcf_per_share"] = fund["free_cash_flow"] / shares
    out["dividend_per_share"] = fund["dividends_paid"].abs() / shares
    out["ocf_per_share"] = fund["operating_cash_flow"] / shares
    out["buyback_per_share"] = fund["common_stock_repurchased"].abs() / shares
    out["ebitda_per_share"] = ebitda / shares
    out["net_debt_per_share"] = net_debt / shares
    out["shares_diluted"] = shares  # for the size factor (market_cap = price * shares_diluted)

    # eps_growth_pct: YoY growth off the PRIOR fiscal year's reported EPS, same "only well-defined
    # off a positive base" rule as fama_macbeth_growth_factors.py's eps_growth_1y - feeds both PEG
    # and the replicated DCF's growth input (see module docstring).
    out = out.sort_values(["symbol", "fiscal_year"])
    prior_eps = out.groupby("symbol")["eps"].shift(1)
    out["eps_growth_pct"] = np.where(prior_eps > 0, (out["eps"] / prior_eps - 1.0) * 100.0, np.nan)

    out["known_date"] = compute_known_dates(out)
    return out.dropna(subset=["known_date"])


def _dcf_intrinsic_per_share(
    fcf_per_share: "np.ndarray[Any, Any]", eps_growth_pct: "np.ndarray[Any, Any]"
) -> "np.ndarray[Any, Any]":
    """Vectorized replication of load_sec_valuations.py's _compute_dcf_intrinsic_value, per-share
    (skips the total-FCF/shares_out round trip since the input is already per-share) - see this
    module's docstring for the known simplifications (flat discount rate, unrefined fcf_base)."""
    growth = np.where(np.isnan(eps_growth_pct), 0.0, eps_growth_pct / 100.0)
    growth = np.clip(growth, DCF_GROWTH_FLOOR, DCF_GROWTH_CEILING)

    fcf_year = fcf_per_share.astype(float).copy()
    pv_explicit = np.zeros_like(fcf_year)
    for year in range(1, DCF_FORECAST_YEARS + 1):
        fade_frac = (year - 1) / (DCF_FORECAST_YEARS - 1) if DCF_FORECAST_YEARS > 1 else 1.0
        year_growth = growth - (growth - DCF_TERMINAL_GROWTH_RATE) * fade_frac
        fcf_year = fcf_year * (1 + year_growth)
        pv_explicit += fcf_year / ((1 + DCF_FLAT_DISCOUNT_RATE) ** year)

    terminal_value = (fcf_year * (1 + DCF_TERMINAL_GROWTH_RATE)) / (DCF_FLAT_DISCOUNT_RATE - DCF_TERMINAL_GROWTH_RATE)
    pv_terminal = terminal_value / ((1 + DCF_FLAT_DISCOUNT_RATE) ** DCF_FORECAST_YEARS)
    intrinsic = pv_explicit + pv_terminal
    return np.where((intrinsic > 0) & (intrinsic < DCF_MAX_INTRINSIC_PER_SHARE), intrinsic, np.nan)


def compute_ratios(gframe: pd.DataFrame, price: pd.Series) -> pd.DataFrame:
    df = gframe.join(price.rename("price"), how="inner")
    df = df[df["price"] > 0]

    ratios = pd.DataFrame(index=df.index)
    ratios["pe"] = np.where(df["eps"] > 0, df["price"] / df["eps"], np.nan)
    ratios["pb"] = np.where(df["book_value_per_share"] > 0, df["price"] / df["book_value_per_share"], np.nan)
    ratios["ps"] = np.where(df["sales_per_share"] > 0, df["price"] / df["sales_per_share"], np.nan)
    ratios["fcf_yield"] = np.where(df["fcf_per_share"].notna(), df["fcf_per_share"] / df["price"], np.nan)
    ratios["dividend_yield"] = np.where(
        df["dividend_per_share"].notna(), df["dividend_per_share"] / df["price"], np.nan
    )
    ev_per_share = df["price"] + df["net_debt_per_share"]
    ratios["ev_ebitda"] = np.where(df["ebitda_per_share"] > 0, ev_per_share / df["ebitda_per_share"], np.nan)
    ratios["ev_revenue"] = np.where(df["sales_per_share"] > 0, ev_per_share / df["sales_per_share"], np.nan)

    # OCF yield: operating cash flow / price - O'Shaughnessy's "What Works on Wall Street"
    # price-to-cash-flow value composite input, distinct from fcf_yield (OCF - CapEx): doesn't
    # subtract capex, so it's less sensitive to a single lumpy capex year than FCF yield is -
    # candidate check for a 2026-08-26 "are we missing a literature-established input" pass.
    ratios["ocf_yield"] = np.where(df["ocf_per_share"].notna(), df["ocf_per_share"] / df["price"], np.nan)

    # Net payout (shareholder) yield: (dividends + buybacks) / price - Boudoukh/Michaely/
    # Richardson/Roberts 2007 "total payout yield", O'Shaughnessy's "Shareholder Yield". Real
    # SEC XBRL buyback data (annual_cash_flow.common_stock_repurchased, migration 1206) has been
    # fetched/loaded since 2026-07 but never consumed by any scoring path - candidate check for
    # the same "are we missing a literature-established input" pass, motivated directly by this
    # pillar's own dividend_yield finding (weak/inconsistent, t=1.55 full/2.04/0.63 halves) -
    # dividend-only payout is exactly the measure the total-payout literature argues is
    # incomplete since most large-cap US firms shifted toward buybacks post-1980s. Each channel
    # treated as 0 (not NaN) when unreported and the other channel IS reported - a company that
    # discloses dividends but not buybacks almost certainly just didn't buy back that year, not
    # "unknown"; NaN only when BOTH are missing.
    div_ps = df["dividend_per_share"]
    buyback_ps = df["buyback_per_share"]
    both_missing = div_ps.isna() & buyback_ps.isna()
    net_payout_ps = div_ps.fillna(0.0) + buyback_ps.fillna(0.0)
    ratios["net_payout_yield"] = np.where(~both_missing, net_payout_ps / df["price"], np.nan)

    # PEG: Peter Lynch convention, PE / growth-in-whole-percentage-points - only defined off a
    # positive PE (needs eps>0, see above) and positive growth (a "cheap relative to growth"
    # signal isn't meaningful for a shrinking or newly-profitable company), matching
    # load_sec_valuations.py's own peg_ratio convention.
    eps_growth = df["eps_growth_pct"]
    ratios["peg"] = np.where((ratios["pe"] > 0) & (eps_growth > 0), ratios["pe"] / eps_growth, np.nan)

    # Margin of safety: replicated DCF, see _dcf_intrinsic_per_share and module docstring point
    # (2) for the formula and its known simplifications. Gated the same way the real pipeline
    # gates fcf (fcf<=0 -> DCF skipped entirely, not just fcf_yield) - a negative/zero starting
    # FCF has no meaningful growth-and-discount projection.
    fcf_ps = df["fcf_per_share"].to_numpy()
    intrinsic = np.where(fcf_ps > 0, _dcf_intrinsic_per_share(fcf_ps, eps_growth.to_numpy()), np.nan)
    price_arr = df["price"].to_numpy()
    mos = np.where(intrinsic > 0, (intrinsic - price_arr) / intrinsic * 100.0, np.nan)
    ratios["margin_of_safety"] = np.where((mos >= -1000) & (mos <= 1000), mos, np.nan)

    # Size: log10(market_cap), sanity-bounded to a real-world plausible range ($1M-$10T) before
    # taking the log - shares_diluted has known scale-error outliers (observed up to 3.5e15,
    # see SHARES_OUTSTANDING_SCALE_MISMATCH_RATIO / composite_weights_reweighted_size_factor_
    # reconfirmed_20260825 memory), so a handful of corrupted rows can't distort a whole month's
    # z-score via the winsorization quantile boundaries below. Not negated here (unlike the
    # composite script's value_proxy, which flips sign so "higher = better" for every
    # component) - this script reports raw ratios and lets the regression coefficient's own
    # sign show direction, same convention as pe/pb/ps above.
    market_cap = df["price"] * df["shares_diluted"]
    ratios["size"] = np.where((market_cap >= 1e6) & (market_cap <= 1e13), np.log10(market_cap), np.nan)
    return ratios


def _pe_score(pe: float) -> float:
    if pe <= 10:
        return 40 + pe * 2
    if pe <= 20:
        return 60 + (pe - 10) * 4
    if pe <= 35:
        return 100 - (pe - 20) * 2
    return max(0.0, 70 - (pe - 35) * 1.4)


def _pb_score(pb: float) -> float:
    if pb <= 1.0:
        return 100.0
    if pb <= 3.0:
        return 100 - ((pb - 1.0) / 2.0) * 30
    if pb <= 7.0:
        return 70 - ((pb - 3.0) / 4.0) * 40
    return max(0.0, 30 - (pb - 7.0) * 3)


def _ps_score(ps: float) -> float:
    if ps <= 2.0:
        return 100.0
    if ps <= 6.0:
        return 100 - ((ps - 2.0) / 4.0) * 30
    if ps <= 15.0:
        return 70 - ((ps - 6.0) / 9.0) * 40
    return max(0.0, 30 - (ps - 15.0) * 1.5)


def _peg_score(peg: float) -> float:
    if peg <= 1.0:
        return 100.0
    if peg <= 2.0:
        return 100 - (peg - 1.0) * 40
    if peg <= 4.0:
        return 60 - (peg - 2.0) * 20
    return max(0.0, 20 - (peg - 4.0) * 5)


def _fcf_score(fcf_yield_decimal: float) -> float:
    fcf_pct = fcf_yield_decimal * 100  # this script's fcf_yield is a decimal fraction; live
    # sec_valuations.fcf_yield is already stored as a percentage - convert to match production.
    return min(100.0, fcf_pct * 20)


def _payout_score(net_payout_yield_decimal: float) -> float:
    payout_pct = min(net_payout_yield_decimal * 100, 10)
    return min(100.0, payout_pct * 10)


def _mos_score(mos: float) -> float:
    if mos >= 50:
        return 100.0
    if mos >= 0:
        return 60 + mos * 0.8
    if mos >= -50:
        return 60 + mos * 1.2
    return 0.0


def _replicate_live_composite_score(row: "pd.Series[Any]") -> float | None:
    """Replicates load_stock_scores.py._score_value's exact weighted-average formula (same
    piecewise curves, same weights - LIVE_VALUE_WEIGHTS above) from this script's raw
    (non-z-scored) reconstructed ratios. Same gating as production: PE/PB/PS/FCF/payout
    require > 0 (production skips non-positive values as not meaningful), MoS/PEG use their
    own production gates. Returns None (no score) only if every single input is unavailable -
    matches _score_value's own "no scoreable fields" marker-dict behavior, just as a sentinel
    here since this script has no marker-dict convention.

    Used for the COMPOSITE SCORE BACKTEST in run() - every other test in this file checks
    individual inputs' marginal predictive power; this checks whether the actual PRODUCTION
    formula, blended exactly as coded, produces the "higher score -> higher forward return"
    relationship the whole pillar exists to deliver."""
    weighted_sum = 0.0
    total_weight = 0.0
    pe, pb, ps, peg = row.get("pe"), row.get("pb"), row.get("ps"), row.get("peg")
    fcf_yield, payout, mos = row.get("fcf_yield"), row.get("net_payout_yield"), row.get("margin_of_safety")

    if pe is not None and not np.isnan(pe) and pe > 0:
        weighted_sum += _pe_score(pe) * LIVE_VALUE_WEIGHTS["pe"]
        total_weight += LIVE_VALUE_WEIGHTS["pe"]
    if pb is not None and not np.isnan(pb) and pb > 0:
        weighted_sum += _pb_score(pb) * LIVE_VALUE_WEIGHTS["pb"]
        total_weight += LIVE_VALUE_WEIGHTS["pb"]
    if ps is not None and not np.isnan(ps) and ps > 0:
        weighted_sum += _ps_score(ps) * LIVE_VALUE_WEIGHTS["ps"]
        total_weight += LIVE_VALUE_WEIGHTS["ps"]
    if peg is not None and not np.isnan(peg) and peg > 0:
        weighted_sum += _peg_score(peg) * LIVE_VALUE_WEIGHTS["peg"]
        total_weight += LIVE_VALUE_WEIGHTS["peg"]
    if fcf_yield is not None and not np.isnan(fcf_yield) and fcf_yield > 0:
        weighted_sum += _fcf_score(fcf_yield) * LIVE_VALUE_WEIGHTS["fcf_yield"]
        total_weight += LIVE_VALUE_WEIGHTS["fcf_yield"]
    if payout is not None and not np.isnan(payout) and payout > 0:
        weighted_sum += _payout_score(payout) * LIVE_VALUE_WEIGHTS["net_payout_yield"]
        total_weight += LIVE_VALUE_WEIGHTS["net_payout_yield"]
    if mos is not None and not np.isnan(mos):
        weighted_sum += _mos_score(mos) * LIVE_VALUE_WEIGHTS["margin_of_safety"]
        total_weight += LIVE_VALUE_WEIGHTS["margin_of_safety"]

    return weighted_sum / total_weight if total_weight > 0 else None


def _equal_weighted_composite_score(row: "pd.Series[Any]") -> float | None:
    """Same 7 sub-scores as _replicate_live_composite_score, but equal-weighted (1/7 each) -
    the standard baseline this file's own composite backtest is checked against: does the
    reasoned, evidence-informed weighting scheme actually beat naive equal-weighting, or is
    the ranking doing all the work and the exact percentages barely matter?"""
    scores = []
    pe, pb, ps, peg = row.get("pe"), row.get("pb"), row.get("ps"), row.get("peg")
    fcf_yield, payout, mos = row.get("fcf_yield"), row.get("net_payout_yield"), row.get("margin_of_safety")
    if pe is not None and not np.isnan(pe) and pe > 0:
        scores.append(_pe_score(pe))
    if pb is not None and not np.isnan(pb) and pb > 0:
        scores.append(_pb_score(pb))
    if ps is not None and not np.isnan(ps) and ps > 0:
        scores.append(_ps_score(ps))
    if peg is not None and not np.isnan(peg) and peg > 0:
        scores.append(_peg_score(peg))
    if fcf_yield is not None and not np.isnan(fcf_yield) and fcf_yield > 0:
        scores.append(_fcf_score(fcf_yield))
    if payout is not None and not np.isnan(payout) and payout > 0:
        scores.append(_payout_score(payout))
    if mos is not None and not np.isnan(mos):
        scores.append(_mos_score(mos))
    return sum(scores) / len(scores) if scores else None


def _load_monthly_amihud(start_date: str, end_date: str, min_days_per_month: int = 10) -> dict[Any, pd.Series]:
    """Reuses fama_macbeth_liquidity_factor.py's own daily-panel fetch and monthly-Amihud
    construction, keyed by month-START datetime.date to match this script's px.index convention
    - fetch_month_end_prices' "month" column comes straight off a psycopg2 DATE column (no
    pd.to_datetime cast), so px.index holds plain datetime.date objects, NOT pd.Timestamp
    (confirmed live: Index dtype='object', element type datetime.date) - keying this dict by
    Timestamp instead silently missed every month (Timestamp/date hash differently even at
    midnight), which is exactly what happened on the first pass here: amihud came back an
    all-NaN/all-zero column with a nan t-stat, not a real "no signal" result."""
    logger.info(f"Pulling daily price/volume panel for Amihud {start_date}..{end_date}")
    daily = fetch_daily_panel(start_date, end_date)
    monthly = compute_monthly_amihud(daily, min_days_per_month)
    monthly = monthly.copy()
    monthly["month_start"] = monthly["month"].dt.to_timestamp(how="start").dt.date
    return {m: g.set_index("symbol")["amihud"] for m, g in monthly.groupby("month_start")}


def run(  # noqa: C901 -- a research/reporting script's linear sequence of print sections
    # (multivariate, univariate, diagnostic, candidate check, correlations, composite backtest,
    # IC cross-check), not production scoring logic - splitting it up would trade readability
    # of the report generation for a lower complexity number, not a real risk reduction.
    start_date: str,
    end_date: str,
    min_cross_section: int,
    horizon_months: int = 1,
) -> None:
    logger.info("Fetching annual value fundamentals (point-in-time reconstruction)")
    fund = fetch_annual_value_fundamentals()
    logger.info(f"{len(fund)} symbol-fiscal-year rows")
    value_panel = build_value_panel(fund)

    logger.info(f"Pulling month-end price panel {start_date}..{end_date}")
    price_df = fetch_month_end_prices(start_date, end_date)
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    months = px.index

    amihud_by_month = _load_monthly_amihud(start_date, end_date)

    fundamentals_cols = [
        "eps",
        "book_value_per_share",
        "sales_per_share",
        "fcf_per_share",
        "dividend_per_share",
        "ocf_per_share",
        "buyback_per_share",
        "ebitda_per_share",
        "net_debt_per_share",
        "shares_diluted",
        "eps_growth_pct",
    ]
    monthly_fund = merge_asof_monthly(months, value_panel, cols=fundamentals_cols)

    all_cols = [*LIVE_VALUE_FACTOR_COLS, SIZE_CONTROL_COL, *CANDIDATE_COLS]
    records: list[tuple[pd.Timestamp, pd.DataFrame]] = []
    composite_records: list[tuple[pd.Timestamp, pd.DataFrame]] = []
    for i in range(len(months) - horizon_months):
        month = months[i]
        gframe = monthly_fund.get(month)
        if gframe is None or gframe.empty:
            continue
        ratios = compute_ratios(gframe, px.iloc[i])
        amihud_month = amihud_by_month.get(month)
        ratios = (
            ratios.join(amihud_month.rename("amihud"), how="left")
            if amihud_month is not None
            else ratios.assign(amihud=np.nan)
        )
        fwd_ret = px.iloc[i + horizon_months] / px.iloc[i] - 1.0
        frame = ratios.join(fwd_ret.rename("fwd_ret"), how="inner")
        frame = frame.replace([np.inf, -np.inf], np.nan)
        # RELAXED PANEL CONSTRUCTION (2026-08-25, later pass - goal: fix the residual selection
        # bias this script still had even after removing ev_ebitda/ev_revenue from
        # VALUE_FACTOR_COLS above). Requiring PE specifically means requiring POSITIVE EARNINGS
        # (PE is undefined for eps<=0) - a strict row-wise .dropna() across all 6 active columns
        # meant every symbol-month needed positive earnings just to test PB/PS/size, which
        # systematically excludes unprofitable/small/distressed firms - exactly the population
        # several of these effects (especially size, and it turns out PB) concentrate in. Only
        # fwd_ret is required now; each factor is winsorized+z-scored over its OWN available
        # population first (below), then missing values are zero-imputed (neutral, post-z-score)
        # rather than dropping the whole row - this IS the fix that reversed the PE/PB/PS
        # ranking, see [[value_pe_pb_ps_ranking_reversed_selection_bias_fix_20260825]].
        frame = frame.dropna(subset=["fwd_ret"])
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        if len(frame) < min_cross_section:
            continue

        # COMPOSITE SCORE BACKTEST (goal: "are we actually seeing the expected results" - every
        # other test in this file checks individual inputs' marginal t-stats, not whether the
        # real blended production formula, applied exactly as coded, produces higher scores for
        # stocks that go on to do better). Computed from the RAW (pre-z-score) ratios, before
        # the winsorize/z-score loop below overwrites them.
        live_composite = frame.apply(_replicate_live_composite_score, axis=1)
        eq_composite = frame.apply(_equal_weighted_composite_score, axis=1)
        composite_frame = pd.DataFrame(
            {"live_composite": live_composite, "eq_composite": eq_composite, "fwd_ret": frame["fwd_ret"]}
        ).dropna(subset=["live_composite", "eq_composite"])
        if len(composite_frame) >= min_cross_section:
            composite_records.append((month, composite_frame))

        for col in all_cols:
            lo, hi = frame[col].quantile([0.01, 0.99])
            frame[col] = frame[col].clip(lo, hi)
            std = frame[col].std()
            frame[col] = (frame[col] - frame[col].mean()) / std if std and std > 0 else frame[col] * 0.0
        frame[all_cols] = frame[all_cols].fillna(0.0)
        records.append((month, frame))

    if not records:
        raise RuntimeError("No usable cross-sectional months")

    sizes = [len(f) for _, f in records]
    print(f"Usable cross-sectional months: {len(records)}  ({records[0][0]} to {records[-1][0]})")
    print(f"Median cross-section size: {int(np.median(sizes))}\n")

    print("=== Multivariate Fama-MacBeth (LIVE 7-input Value formula, jointly) ===")
    print(f"{'factor':16s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
    multi = _fama_macbeth(records, LIVE_VALUE_FACTOR_COLS)
    for name, (mean, t) in multi.items():
        print(f"{name:16s} {mean:10.5f} {t:8.2f} {len(records):9d}")

    print("\n=== Univariate Fama-MacBeth (each input alone) ===")
    print(f"{'factor':16s} {'mean_coef':>10s} {'t_stat':>8s}")
    for c in LIVE_VALUE_FACTOR_COLS:
        uni = _fama_macbeth(records, [c])
        mean, t = uni[c]
        print(f"{c:16s} {mean:10.5f} {t:8.2f}")

    print("\n=== DIAGNOSTIC: same 8 inputs + size (log market cap) as an added control ===")
    print("(size is NOT a live scored input - see SIZE_CONTROL_COL's docstring note - this is")
    print(" purely to check whether amihud/margin_of_safety's effect survives controlling for")
    print(" real point-in-time size, not just log(dollar volume) as the original Amihud")
    print(" validation did)")
    diagnostic_cols = [*LIVE_VALUE_FACTOR_COLS, SIZE_CONTROL_COL]
    print(f"{'factor':16s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
    multi_sz = _fama_macbeth(records, diagnostic_cols)
    for name, (mean, t) in multi_sz.items():
        print(f"{name:16s} {mean:10.5f} {t:8.2f} {len(records):9d}")

    print("\n=== CANDIDATE CHECK: are we missing a literature-established input? ===")
    print("(ocf_yield, net_payout_yield - see CANDIDATE_COLS docstring note. NOT live inputs -")
    print(" this tests whether they'd earn a place alongside the 8 that already are)")
    print(f"{'factor':16s} {'mean_coef':>10s} {'t_stat':>8s}")
    for c in CANDIDATE_COLS:
        uni = _fama_macbeth(records, [c])
        mean, t = uni[c]
        print(f"{c:16s} {mean:10.5f} {t:8.2f}  (univariate)")
    live_plus_candidates = [*LIVE_VALUE_FACTOR_COLS, *CANDIDATE_COLS]
    multi_cand = _fama_macbeth(records, live_plus_candidates)
    print(f"{'factor':16s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}  (multivariate, jointly with the live 8)")
    for name, (mean, t) in multi_cand.items():
        print(f"{name:16s} {mean:10.5f} {t:8.2f} {len(records):9d}")

    print("\n=== Pooled cross-sectional correlations (redundancy check) ===")
    pooled = pd.concat([f[all_cols] for _, f in records])
    corr = pooled.corr()
    print(corr.round(2).to_string())

    if not composite_records:
        print("\n=== COMPOSITE SCORE BACKTEST: no usable months, skipped ===")
        return

    print("\n=== COMPOSITE SCORE BACKTEST (the actual blended production formula) ===")
    print("(does load_stock_scores.py._score_value's REAL weighted-average output, not just")
    print(" each input's own coefficient, actually rank stocks the way the pillar promises?)")
    print(f"Usable months: {len(composite_records)}")

    for label, col in [
        ("LIVE weights (12/30/27/7/9/8/7)", "live_composite"),
        ("Equal weights (1/7 each)", "eq_composite"),
    ]:
        print(f"\n--- {label} ---")
        # Quintile spread: rank each month's cross-section into 5 buckets by the RAW composite
        # score, average each bucket's forward return, spread = top bucket - bottom bucket.
        # Reported both as the average monthly spread and as a t-stat on that monthly series
        # (same two-pass Fama-MacBeth-style significance test as every other result in this
        # file, just applied to a bucketed spread instead of a regression coefficient).
        spreads = []
        for _month, cframe in composite_records:
            try:
                q = pd.qcut(cframe[col], 5, labels=False, duplicates="drop")
            except ValueError:
                continue
            if q.max() != 4:  # fewer than 5 distinct buckets that month - skip, not comparable
                continue
            means = cframe.groupby(q)["fwd_ret"].mean()
            spreads.append(means[4] - means[0])
        if spreads:
            arr = np.array(spreads)
            se = arr.std(ddof=1) / np.sqrt(len(arr))
            t = arr.mean() / se if se > 0 else float("nan")
            print(
                f"Top-minus-bottom quintile spread: {arr.mean() * 100:+.2f}% avg monthly return, "
                f"t={t:.2f}, n_months={len(arr)}"
            )
        else:
            print("Top-minus-bottom quintile spread: no usable months")

        # Formal FM t-stat on the z-scored composite score itself (same methodology as every
        # other coefficient in this file).
        z_records = []
        for _month, cframe in composite_records:
            std = cframe[col].std()
            if not std or std <= 0:
                continue
            z = (cframe[col] - cframe[col].mean()) / std
            z_records.append((_month, pd.DataFrame({col: z, "fwd_ret": cframe["fwd_ret"]})))
        if z_records:
            mean, t = _fama_macbeth(z_records, [col])[col]
            print(f"Fama-MacBeth (z-scored composite vs fwd_ret): mean_coef={mean:.5f}, t={t:.2f}")

        # METHODOLOGY CROSS-CHECK (2026-08-26, later same day - goal: user asked directly
        # whether Fama-MacBeth itself might be skewing these results, not just whether the
        # inputs/weights are right). Monthly Spearman rank correlation (Information
        # Coefficient) between the composite score and forward return, averaged with its own
        # t-stat - the standard practitioner sanity check for exactly this question. It shares
        # nothing with the FM regression above except the underlying data: no OLS, no z-scoring,
        # no linearity assumption (rank-based, robust to outliers/nonlinear relationships an OLS
        # regression coefficient could be distorted by) - if THIS disagrees with the FM t-stat
        # above, that's a real sign the regression specification is doing something the raw
        # ranking data doesn't support. If they agree, that's triangulation from two
        # independent, unrelated statistical methods, not one method's assumptions colored by
        # data snooping.
        ics = [cframe[col].corr(cframe["fwd_ret"], method="spearman") for _month, cframe in composite_records]
        ics_arr = np.array([x for x in ics if x is not None and not np.isnan(x)])
        if len(ics_arr) > 1:
            ic_se = ics_arr.std(ddof=1) / np.sqrt(len(ics_arr))
            ic_t = ics_arr.mean() / ic_se if ic_se > 0 else float("nan")
            print(
                f"Spearman rank IC (independent of FM/OLS entirely): mean={ics_arr.mean():.4f}, "
                f"t={ic_t:.2f}, n_months={len(ics_arr)}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start-date", default="2014-01-01")
    parser.add_argument("--end-date", default=datetime.now(tz=None).date().isoformat())
    parser.add_argument("--min-cross-section", type=int, default=100)
    parser.add_argument("--horizon-months", type=int, default=1)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.start_date, args.end_date, args.min_cross_section, args.horizon_months)


if __name__ == "__main__":
    main()
