#!/usr/bin/env python3
"""SEC-Derived Valuations Loader - Replace yfinance PE/PB/PS/PEG/FCF/MarketCap.

Computes audited, current valuations from SEC financial data + price_daily:
  - PE Ratio: TTM EPS (from income statement) / Stock Price
  - PB Ratio: Book Value Per Share (from balance sheet) / Stock Price
  - PS Ratio: Revenue Per Share (from income statement) / Stock Price
  - PEG Ratio: PE Ratio / Earnings Growth Rate %
  - FCF Yield: Free Cash Flow (from cash flow statement) / Market Cap
  - Market Cap: Stock Price x Shares Outstanding (from income statement)
  - Shares Outstanding: WeightedAverageNumberOfSharesOutstandingBasic (from SEC, migration 1171),
    falling back to net_income/eps derivation, then company_info_sec, if unavailable

Data Quality:
  - All metrics computed from SEC audited data (vs. yfinance estimates)
  - Current (updated daily as prices update)
  - Explicit data_unavailable markers on computation failures (fail-fast if SEC data unavailable)
  - No fallback to yfinance for computing values (SEC data only) - every PE/PB/PS/PEG/FCF/
    market cap figure stored is 100% SEC-derived. The one exception: _sanity_check_market_cap/
    _sanity_check_pe_ratio use yfinance as a cross-check (never a value source) to catch
    SEC-side shares_outstanding/EPS scale errors - live for foreign private issuers (the one
    class where an independent, ADS/USD-basis-quoted source is structurally necessary, since
    company_info_sec's cross-check is SEC-sourced too and shares the same unit-mismatch risk),
    a cached table otherwise. See _fetch_live_fpi_yfinance_check_values's docstring.
  - SECOND, narrower exception (2026-08-22): true dual-class filers (e.g. BRK.A/BRK.B) get
    shares_outstanding from yfinance, ONLY when every SEC-derived tier has already failed and
    has_dual_class_sibling=True - live-verified against real SEC EDGAR data that
    data.sec.gov's companyfacts API structurally cannot carry per-share-class data at all (no
    XBRL dimensional/segment support), not a gap our own extraction logic can close. Rows
    produced this way carry `data_source="sec_audited_except_dual_class_shares_yfinance"`
    (never silently blended into the "sec_audited" label) - see
    _fetch_live_dual_class_shares_outstanding's docstring and
    dual_class_primary_ticker_shares_outstanding_structural_gap_found_20260822 in memory.
  - THIRD exception (2026-08-27): foreign private issuers get shares_outstanding from
    yfinance, ONLY when every SEC-derived tier has already failed and
    is_foreign_private_issuer=True - live-confirmed 945 universe symbols had NULL market_cap,
    81% (768) tagged "foreign_private_issuer_shares_unavailable", 99% of those still actively
    tradable (a live price in the last 5 trading days), not delisted - a permanent structural
    gap (SEC 20-F filings commonly lack a usable US-GAAP shares-outstanding tag), not a data
    staleness issue. Same underlying justification as the dual-class exception - yfinance
    queries per-LISTING (the ADS ticker), so its sharesOutstanding is already on the correct
    ADS/USD basis. Rows produced this way carry
    `data_source="sec_audited_except_fpi_shares_yfinance"` - see
    _fetch_live_fpi_shares_outstanding_yfinance's docstring.

Run: python3 loaders/load_sec_valuations.py [--symbols AAPL,MSFT] [--parallelism 4]
"""

import logging
import sys
from datetime import date
from typing import Any

from loaders.helpers.sec_valuations_checks import ValuationSanityCheckMixin
from loaders.helpers.sec_valuations_dcf import DcfValuationMixin
from loaders.helpers.sec_valuations_income_context import IncomeStatementContextMixin
from loaders.helpers.sec_valuations_ratios import SecValuationRatiosMixin
from loaders.helpers.sec_valuations_shares import SharesOutstandingResolutionMixin
from loaders.helpers.sec_valuations_yield_dcf import SecValuationYieldDcfMixin
from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.loaders.exception_handler import handle_exception, handle_invalid_data
from utils.optimal_loader import OptimalLoader
from utils.type_conversion import safe_float

logger = logging.getLogger(__name__)

# BUG FOUND 2026-08-16: total_debt/total_cash/ebitda/enterprise_value are all NUMERIC(15,2)
# columns (max abs value < 10^13, i.e. $10 trillion) but were written with no sanity bound at
# all - unlike pe_ratio/pb_ratio/ps_ratio/ev_ebitda/ev_revenue just below, which all already
# have explicit bounds. Live-confirmed: BBAR/BCH/BMA/BSAC/HDB/HMC (all foreign ADR filers -
# Argentine/Chilean/Indian/Japanese banks and companies) hit NumericValueOutOfRange on this
# exact column class, crashing the whole sec_valuations INSERT and losing every other computed
# ratio for that symbol too - same root cause and same crash-and-lose-everything failure mode
# already documented for loaders/load_value_quality_growth_metrics.py's identical
# MAX_ABSOLUTE_DOLLAR_VALUE guard (foreign filers reporting balance-sheet figures in local
# currency without USD conversion - see that file's docstring for the VFS/KEP example). This
# bound only prevents the crash symptom, same scope as that fix; the currency-conversion root
# cause is a separate, larger fix.
# FIXED 2026-08-20 (goal: finance-accuracy audit): the original $1 trillion ceiling's own
# comment ("no real company exceeds this") was already false at the time this bound is being
# read - live-confirmed 14 real, major, heavily-traded companies (NVDA $5.30T, AAPL $4.74T,
# GOOGL $4.18T, GOOG $4.14T, MSFT $3.60T, AMZN $2.87T, BABA $2.65T, AVGO $1.71T, AMX $1.47T,
# META $1.38T, BRK.A $1.23T, LLY $1.15T, TSLA $1.13T, MU $1.05T) computing a real,
# well-formed enterprise_value that this guard was silently nulling to None, along with
# ev_ebitda/ev_revenue for every one of them - losing EV-based ratios for exactly the stocks
# most likely to be in any real trading universe. The true constraint is the NUMERIC(15,2)
# column definition itself (confirmed via information_schema: precision=15, scale=2, hard
# ceiling ~$9,999,999,999,999.99) - this guard exists to stay safely under THAT crash point,
# not to second-guess how large a real company can get. market_cap is NUMERIC(20,2), a much
# larger column, which is why market_cap itself was never affected by this bug.
MAX_ABSOLUTE_DOLLAR_VALUE = 9_000_000_000_000.0  # $9 trillion - stays safely under the real
# NUMERIC(15,2) column overflow point (~$10T) with margin for continued real-world growth,
# while still catching genuine data errors (the original NMR/BBAR-class currency-scale bugs
# this guard was built for produced values in the hundreds of trillions to quadrillions).

# FIXED 2026-08-31 (data-coverage sweep, "shares_outstanding_unavailable" bucket): the
# dual-class sibling check just below (`has_dual_class_sibling`) only recognizes the
# dot-separated ticker convention (BRK.A/BRK.B via `symbol.split(".")[0]`) - it never
# matches companies whose two share classes are ticker-suffixed with no separator at all
# (DGICA/DGICB, not DGIC.A/DGIC.B), so `base_root` comes back as the full symbol unchanged
# and the sibling lookup always misses. Live-confirmed via company_info_sec.entity_name:
# DGICA/DGICB (Donegal Group), KELYA/KELYB (Kelly Services), LBTYA/LBTYB/LBTYK (Liberty
# Global), BELFA/BELFB (Bel Fuse), SENEA/SENEB (Seneca Foods), RUSHA/RUSHB (Rush
# Enterprises) all share the identical entity_name across their listed classes - genuine
# dual-class siblings, not coincidental ticker overlap. Deliberately an explicit, curated
# root list rather than a generic "strip the trailing letter, look for another symbol with
# the same root" heuristic: that heuristic produces real false positives in this repo's own
# universe (NTR/NTRA/NTRB/NTRP/NTRS are five completely unrelated companies - Nutrien,
# Natera, NutriBand, NextTrip, Northern Trust - that only coincidentally share a 3-letter
# prefix), so every entry here was individually verified via entity_name match before being
# added, same discipline as CIK_OVERRIDES-style lists elsewhere in this codebase. Add a new
# root here only after the same entity_name verification - never on ticker-shape alone.
DUAL_CLASS_NO_SEPARATOR_ROOTS = frozenset({"DGIC", "KELY", "LBTY", "BELF", "SENE", "RUSH"})

# ADDED 2026-09-06 (goal: SEC/XBRL missing-data-to-zero sweep, has_dual_class_sibling detection
# gap found while investigating ps_ratio "implausible_ratio" for UONE): DUAL_CLASS_NO_SEPARATOR_
# ROOTS above only matches when the CURRENT symbol is the SUFFIXED side of a pair (root+1 char,
# e.g. "DGICB" against root "DGIC") - it can never match when the current symbol IS the bare root
# itself (`symbol.startswith(r) and len(symbol) == len(r) + 1` is never true when symbol == r).
# That's fine for DGIC/KELY/LBTY/BELF/SENE/RUSH because the bare root isn't itself a real ticker
# there, but several real dual-class families use a real, actively-traded ticker AS the root, with
# the sibling class suffixed onto it with no separator (UONE/UONEK - Urban One Class A/D). Each
# pair below individually verified via matching company_info_sec.entity_name across both tickers,
# same discipline as the roots above. NOT folded into DUAL_CLASS_NO_SEPARATOR_ROOTS's generic
# prefix+length matching: several of these roots are short/common enough to collide with real,
# unrelated tickers under that same heuristic (UA would wildcard-match UAL/United Airlines; FOX
# would wildcard-match FOXF/Fox Factory and FOXX) - live-confirmed via a direct query against
# stock_symbols, exactly the false-positive failure mode already documented in
# DUAL_CLASS_NO_SEPARATOR_ROOTS's own comment (NTR/NTRA/NTRB/NTRP/NTRS). Exact-family-membership
# matching (see has_dual_class_sibling's use of this below) has zero collision risk regardless of
# root length, so it's safe to include short roots here that would not be safe to add above.
DUAL_CLASS_BARE_ROOT_SIBLING_FAMILIES: tuple[frozenset[str], ...] = (
    frozenset({"CENT", "CENTA"}),  # Central Garden & Pet
    frozenset({"FOX", "FOXA"}),  # Fox Corp
    frozenset({"LILA", "LILAK"}),  # Liberty Latin America
    frozenset({"METC", "METCB"}),  # Ramaco Resources
    frozenset({"NWS", "NWSA"}),  # News Corp
    frozenset({"RDI", "RDIB"}),  # Reading International
    frozenset({"UA", "UAA"}),  # Under Armour
    frozenset({"UONE", "UONEK"}),  # Urban One
    frozenset({"WLY", "WLYB"}),  # John Wiley & Sons
)

# ADDED 2026-08-31 (goal: data-coverage sweep, AMRN follow-up to
# sec_valuations_fpi_shares_out_missing_gate_fixed_20260831): a narrow, individually-verified
# allowlist (same discipline as CIK_OVERRIDES/DUAL_CLASS_NO_SEPARATOR_ROOTS above) for the one
# remaining shares_outstanding class this file's is_foreign_private_issuer gating structurally
# cannot catch - a symbol that files DOMESTIC forms (10-K/10-Q, so is_foreign_private_issuer is
# correctly False per company_info_sec's form-type-based classification) but whose SEC-tagged
# share count is still on a different basis than the price it trades at, because its ADS
# ratio isn't 1:1. Live-confirmed via AMRN (Amarin Corporation plc): a real 1-for-20 ADS ratio
# change effective 2025-04-11 (SEC filing news, one ADS now = 20 ordinary shares) - BOTH
# us-gaap:CommonStockSharesOutstanding (fresh, end=2026-06-30) AND
# us-gaap:WeightedAverageNumberOfSharesOutstandingBasic (same period) independently agree on
# ~420M ordinary shares, so neither the staleness fix nor the reverse-split override above helps
# (SEC's own data is fresh and self-consistent - just not ADS-adjusted). Real ADS count is
# ~420M/20 =~ 21M, matching live yfinance's ~$292-318M market cap at the real price almost
# exactly (vs the unconverted $5.86B this file's sanity check correctly rejects today).
# Genuinely no structural signal available to detect this class automatically (no XBRL concept
# reports "ADS ratio"), so - like the dual-class no-separator case above - each entry here must
# be individually verified via a real corporate-action filing before being added, never guessed.
# Divides the resolved shares_out by the ratio right before market_cap computation, same
# insertion point as every other override to keep every downstream field (pe_ratio's
# denominator is price-only, so unaffected) consistent.
DOMESTIC_FILER_ADS_RATIO_OVERRIDES: dict[str, float] = {
    "AMRN": 20.0,  # Amarin Corporation plc - 1 ADS = 20 ordinary shares, effective 2025-04-11
    # ONC (BeOne Medicines Ltd, formerly BeiGene): is_foreign_private_issuer=False despite being
    # Cayman-incorporated (large accelerated domestic-form filer) - 1 ADS = 13 ordinary shares
    # per SEC filings (424B7, Form 4 insider-trading reports). Live-confirmed via the same
    # market-cap-independent cross-check as the reverse-split registry below: shares_out/13 *
    # price = $39.55B vs a live yfinance market cap of $41.03B, within 3.6%. Also needs
    # FPI_EPS_ADS_RATIO_OVERRIDES' EPS-side entry (see below) - unadjusted EPS gives an
    # implausible ~1813x PE, adjusted gives ~139x (still high but plausible for a
    # barely-profitable biotech with a $286.9M/-$644.8M net income swing 2024-2025).
    "ONC": 13.0,
}

# FIXED 2026-09-03 (goal session: "missing SEC/XBRL data"/implausible-values sweep,
# eps_scale_mismatch follow-up): a real stock split creates the SAME class of same-symbol
# scale mismatch as an ADS-ratio change above, but on the EPS side instead of shares_out -
# current_price is always live/post-split, while an annual (or quarterly) filing whose fiscal
# period ENDED BEFORE the split's effective date reports EPS on the PRE-split share count.
# _sanity_check_pe_ratio below correctly (by design) nulls pe_ratio/peg_ratio rather than
# publish a wrong ratio - the fix here is to stop FEEDING it a stale-scale EPS in the first
# place for a confirmed split, not to touch that guard. Live-confirmed via BKNG (Booking
# Holdings): a real 25-for-1 split, effective 2026-04-02 (record date 2026-03-06, ex-date
# 2026-04-06 - see Booking Holdings' own split announcement/8-K), left FY2025's annual EPS
# ($166.52, pre-split) being compared against the live post-split current_price ($195.13 as
# of 2026-09-03) - pe_ratio computed as ~1.17 vs yfinance's real ~29x, correctly rejected as
# eps_scale_mismatch. $195.13 * 25 = $4,878.25, consistent with BKNG's real pre-split trading
# range in early 2026 - confirms the split, not a different/unrelated data bug. Same
# never-guess discipline as DOMESTIC_FILER_ADS_RATIO_OVERRIDES above: only a symbol
# individually confirmed via a real corporate-action filing/announcement belongs here (GMAB
# and UHAL were checked the same session and are NOT recent splits - their own
# eps_scale_mismatch/shares_outstanding_scale_mismatch flags have a different, unconfirmed
# root cause and must not be added here on the same assumption).
RECENT_STOCK_SPLITS: dict[str, tuple[float, date]] = {
    "BKNG": (25.0, date(2026, 4, 2)),
}

# FIXED 2026-09-03 (goal session continuation, same eps_scale_mismatch sweep): a real REVERSE
# split creates the mirror-image problem on the shares_out side instead of EPS - SEC's
# cover-page shares_outstanding_basic is "as of filing date," and for a filer whose most recent
# annual/quarterly filing predates a reverse split that happened only days ago (common for
# micro-cap issuers doing a reverse split to avoid delisting), that stored count is still the
# stale PRE-split (too-large) figure while current_price is live/post-split - producing a
# market_cap wildly too big, correctly rejected by `_sanity_check_market_cap` as
# shares_outstanding_scale_mismatch. Unlike RECENT_STOCK_SPLITS (EPS, divides for a FORWARD
# split), this divides shares_out for a REVERSE split, and is applied unconditionally (no
# effective-date gate) because as of this fix every fiscal year on file for these symbols
# predates their split - a future filing reflecting the new post-split count needs this entry
# removed, not date-gated (SEC's cover-page shares_outstanding_basic has no reliable per-row
# as-of-date distinct from fiscal_year end to gate on).
# Each entry was cross-validated against a LIVE yfinance market cap (not just the disclosed
# split ratio): (current_price * shares_out / ratio) compared to a fresh live yfinance market
# cap fetch. PPCB and NXTT matched to the DOLLAR (2,323,938.62 vs 2,323,938.0 live;
# 8,734,664.19 vs 8,734,664.0 live) - about as strong a confirmation as this kind of check can
# give. HCWC matched within the right order of magnitude and ratio ballpark (adjusted
# $5.07M vs live $6.48M - explainable by price_daily being a day or more staler than the live
# yfinance quote used in the check) - real reverse split independently confirmed via SEC 8-K/
# press release, kept despite the imperfect match. PIII was investigated with a real,
# source-confirmed 1-for-50 reverse split but FAILED this same cross-check by ~3 orders of
# magnitude (adjusted $597K vs live $1.82B) - deliberately EXCLUDED; the split is real but
# something else is going on with this symbol's share count that a naive ratio-divide would
# get badly wrong. AKTX's raw shares_outstanding_basic has been growing every year
# (9.7B->23.9B->67.3B->91.6B, 2023-2026) with no visible post-split drop despite a confirmed
# 1-for-40 ADS-ratio change - also EXCLUDED, needs more investigation before any fix.
# QNRX re-confirmed same session via SEC's own 8-K (Nasdaq ECA2025-183): ADS ratio changed
# 1:1 -> 1 ADS = 35 ordinary shares, effective 2025-04-09 (a Nasdaq $1.00 minimum-bid-price
# compliance action) - cross-check matched within 2.4% (adjusted $15.44M vs live $15.81M).
RECENT_REVERSE_SPLITS_SHARES_OUT: dict[str, float] = {
    "PPCB": 25.0,  # Propanc Biopharma - 1-for-25 reverse split, effective 2026-05-18
    "NXTT": 100.0,  # Next Technology Holding - 1-for-100 reverse split, effective 2026-08-10
    "HCWC": 35.0,  # Healthy Choice Wellness Corp - 1-for-35 reverse split, effective 2026-08-28
    "QNRX": 35.0,  # Quoin Pharmaceuticals - ADS ratio 1:1 -> 1:35, effective 2025-04-09
}


def _split_adjusted_eps(symbol: str, eps: Any, fiscal_year: int | None) -> Any:
    """Divide a fiscal year's as-reported EPS by a confirmed post-filing split ratio when that
    fiscal year ended before the split's effective date (see RECENT_STOCK_SPLITS' own comment).
    A fiscal year ending ON OR AFTER the split date already reflects the post-split weighted-
    average share count in its own as-filed EPS (ASC 260) and must not be double-adjusted.
    """
    if eps is None or fiscal_year is None:
        return eps
    split = RECENT_STOCK_SPLITS.get(symbol)
    if split is None:
        return eps
    ratio, effective_date = split
    if date(fiscal_year, 12, 31) < effective_date:
        return float(eps) / ratio
    return eps


# FIXED 2026-09-03 (goal session continuation, DDI-discovered, expanded same session to the
# rest of the FPI eps_scale_mismatch bucket): a genuine foreign private issuer's shares_out is
# ALREADY corrected to an ADS-equivalent basis elsewhere in this file (the
# `not shares_out and is_foreign_private_issuer` yfinance fallback a few hundred lines below -
# yfinance queries per-LISTING, i.e. the ADS ticker, so its sharesOutstanding is naturally
# ADS-basis) - but earnings_per_share is SEC-tagged per the filer's home-market (ordinary/
# common) share and NEVER goes through any ADS conversion at all. When 1 ordinary share != 1
# ADS, this leaves shares_out on ADS-basis and EPS on ordinary-share-basis at the same time,
# silently mismatched, and _sanity_check_pe_ratio correctly (by design) nulls the resulting
# nonsense pe_ratio as eps_scale_mismatch - same failure MODE as RECENT_STOCK_SPLITS/
# DOMESTIC_FILER_ADS_RATIO_OVERRIDES above (a real ratio never applied to EPS) but a distinct
# root cause: a permanent per-symbol unit mismatch, not a one-time corporate action.
#
# The dict value is (multiplier, effective_date). `multiplier` converts EPS-per-ordinary-share
# -> EPS-per-ADS (EPS_per_ADS = EPS_per_ordinary * multiplier); most of these disclose their
# ratio as "1 ADS = N ordinary shares" (multiplier = N, an ADS aggregates N ordinary shares'
# worth of earnings), while DDI/GMAB disclose the inverse "N ADS = 1 ordinary share"
# (multiplier = 1/N). `effective_date` is None for a ratio confirmed stable/with no known
# recent change (apply to every fiscal year, same as DDI originally) - for a symbol whose ADS
# ratio changed recently (same risk RECENT_STOCK_SPLITS guards against for stock splits), it's
# the date the NEW ratio took effect; a fiscal year ending before that date used a different,
# unresearched old ratio and is deliberately left unadjusted (still flagged
# eps_scale_mismatch, not a regression) rather than guessed.
#
# Every entry here was cross-validated two independent ways before being added: (1) a
# source-confirmed ratio (20-F/F-1/prospectus, Nasdaq/NYSE listing description, or company IR
# ADR page) and (2) the resulting computed_pe = price / (eps * multiplier) checked against a
# net_income/market_cap-derived "true PE" that never touches EPS or the ratio at all - both
# had to land within a plausible range and close to each other. Several symbols with a
# source-confirmed ratio were investigated and DELIBERATELY EXCLUDED because this
# cross-validation failed or the "true PE" itself was already implausible (a separate,
# unrelated data problem the ratio wouldn't fix) - do not add them on the strength of the
# ratio alone without redoing this same validation: AMX (true PE ~1.0x regardless of ratio -
# net_income itself looks bad, 50x jump from prior year), BCH/ENIC/LOMA/SOGP/TLK/PHAR/WDH/SIM
# (true PE implausible and/or >30% off from the ratio-adjusted PE), JFU/KRKR/TC (ratio
# recently changed AND validation failed/was wildly off - TC's mismatch was ~235x, far beyond
# what a mid-year ratio-change split-history could explain). SBS's ADR ratio is 1:1 - its
# eps_scale_mismatch is NOT an ADS-ratio issue (parallels the already-known WSE case, likely
# FX/currency-basis). BSP/CHSN/HKIT/LGCL/MASK/MATH/TLIH/TWG/ZJYL trade as ordinary shares
# directly (no ADS program found) - their FPI flag/mismatch has some other cause.
FPI_EPS_ADS_RATIO_OVERRIDES: dict[str, tuple[float, date | None]] = {
    "DDI": (1 / 20.0, None),  # DoubleDown Interactive - 20 ADS = 1 ordinary share
    "GMAB": (1 / 10.0, None),  # Genmab A/S - each ADS = 1/10 ordinary share
    "ALAR": (10.0, None),  # Alarum Technologies - 1 ADS = 10 ordinary shares
    "CHT": (10.0, None),  # Chunghwa Telecom - 1 ADS = 10 common shares
    "GDS": (8.0, None),  # GDS Holdings - 1 ADS = 8 Class A ordinary shares
    "OMAB": (8.0, None),  # Grupo Aeroportuario del Centro Norte - 1 ADS = 8 Series B shares
    "PAM": (25.0, None),  # Pampa Energy - 1 ADS = 25 ordinary shares
    "VTMX": (10.0, None),  # Vesta Real Estate - 1 ADS = 10 ordinary shares
    "YMM": (20.0, None),  # Full Truck Alliance - 1 ADS = 20 Class A ordinary shares
    # CX (Cemex): 1 ADS = 10 CPOs, 1 CPO = 3 ordinary shares -> 1 ADS = 30 ordinary shares.
    # The per-CPO-vs-per-ordinary basis ambiguity this creates was resolved via the
    # net_income/market_cap cross-check (not just the disclosed ratio alone): x30 landed
    # within ~2-9% of the ratio-independent "true PE" across FY2022-2024, while x10 was
    # consistently ~3x too high in every year - confirming SEC XBRL tags EPS per ordinary
    # share, not per CPO, for this filer.
    "CX": (30.0, None),
    # ONC (BeOne Medicines, formerly BeiGene): 1 ADS = 13 ordinary shares - see
    # DOMESTIC_FILER_ADS_RATIO_OVERRIDES' own comment for the full cross-check rationale
    # (this symbol needs BOTH registries: shares_out AND EPS are on ordinary-share basis).
    "ONC": (13.0, None),
    "FEDU": (10.0, date(2022, 6, 21)),  # Four Seasons Education - ratio changed from 1:2
    "LITB": (12.0, date(2024, 9, 5)),  # LightInTheBox - ratio changed
    "TOUR": (30.0, date(2026, 4, 22)),  # Tuniu - ratio changed from 1:3
}


def _fpi_ads_adjusted_eps(symbol: str, eps: Any, fiscal_year: int | None) -> Any:
    """Multiply a foreign private issuer's SEC-tagged (ordinary-share-basis) EPS by its
    confirmed ADS ratio so it matches the ADS-basis price/shares_out used everywhere else in
    this file (see FPI_EPS_ADS_RATIO_OVERRIDES' own module-level comment). A fiscal year ending
    before a registered ratio's effective_date used a different, unresearched ratio and is left
    unadjusted rather than guessed - same discipline as _split_adjusted_eps above.
    """
    if eps is None:
        return eps
    override = FPI_EPS_ADS_RATIO_OVERRIDES.get(symbol)
    if override is None:
        return eps
    multiplier, effective_date = override
    if effective_date is not None and (fiscal_year is None or date(fiscal_year, 12, 31) < effective_date):
        return eps
    return float(eps) * multiplier


# See _sanity_check_market_cap's own comment for the full KELYB/LBTYB rationale and the
# sibling-sum cross-check discipline required before adding a symbol here.
DUAL_CLASS_YFINANCE_COMBINED_MARKET_CAP_SYMBOLS: frozenset[str] = frozenset(
    {
        "KELYB",  # Kelly Services Class B
        "LBTYB",  # Liberty Global Class B
    }
)


class SecValuationsLoader(
    OptimalLoader,
    DcfValuationMixin,
    ValuationSanityCheckMixin,
    IncomeStatementContextMixin,
    SharesOutstandingResolutionMixin,
    SecValuationRatiosMixin,
    SecValuationYieldDcfMixin,
):
    """Compute valuations from SEC audited data instead of yfinance estimates.

    CRITICAL: This loader replaces ~5,300 yfinance quoteSummary calls per day
    with computation from already-fetched SEC financial statements.
    Eliminates $25/month in API costs + reduces rate-limiting risk.
    """

    table_name = "sec_valuations"
    primary_key = ("symbol",)
    watermark_field = "computed_at"
    exclude_etfs_from_symbols = True

    # Sanity floor for the "search all fiscal years" share-count fallbacks below. Real SEC
    # XBRL data occasionally contains a single implausible outlier entry for a concept (live-
    # confirmed: ERIE's WeightedAverageNumberOfDilutedSharesOutstanding has exactly one
    # reported value across its whole filing history, 2542 shares, for a multi-billion-dollar
    # company that has millions of shares outstanding - almost certainly a filer tagging
    # error). Every real US-listed operating company has at least this many shares
    # outstanding, so this floor rejects that class of bad data without excluding real
    # micro-caps.
    MIN_PLAUSIBLE_SHARES_OUTSTANDING = 100_000

    # ADDED 2026-08-31 (goal session: "VCIG tops the scores, dig in" investigation). PB/PS
    # ratios below already had an UPPER bound ("Reasonable PB bounds" <=1000, "Reasonable PS
    # bounds" <=10000 further below) but no symmetric LOWER one - live-confirmed via VCIG
    # (VCI Global Ltd): pb_ratio=0.01/ps_ratio=0.02, tied for the single cheapest in a
    # 4,500+-symbol universe, driving it to composite_score's #1 rank. Unlike the BMA/LOMA/
    # CEPU/CIG/GGB class this session also fixed (a genuine unconverted-ARS/BRL-currency
    # data bug - see ConsolidatedFinancialStatementsLoader._reject_stale_fpi_currency_data),
    # VCIG's numbers are independently confirmed REAL: SEC XBRL's own USD-tagged Equity facts
    # ($86.3M FY2024, $164.1M mid-2025 6-K) and a live yfinance snapshot (bookValue=$222.77/
    # share, priceToBook=0.0096, sharesOutstanding=618,994) both agree with the stored
    # pb_ratio, with no currency-unit mismatch - this is a real (if bizarre) market situation,
    # not a loader bug. That's exactly the classic winsorization case, not a data-quality one:
    # _percent_rank_cheap_high in load_stock_scores.py ranks PB/PS purely by ORDER, so any
    # single most-extreme value - genuine or not - always wins percentile 100/0 outright, and
    # (per that function's own docstring) capping/flooring the raw value before ranking can't
    # fix a pure-rank system, since ties still take the tied block's best percentile. The only
    # mechanism that actually changes the outcome is excluding the ratio from the percentile
    # universe entirely for implausibly extreme cases, the same "skip what's unavailable"
    # treatment every other missing Value input already gets (drops out of total_weight,
    # doesn't force a floor/ceiling score) - mirrors the existing upper-bound rejection below
    # exactly, just at the other tail. 0.05 (vs the upper bound's already-generous 1000/10000)
    # is a deliberately conservative floor: live-scoped via a real DB query, only 29/4,521 PB
    # and 44/4,517 PS values in the current universe fall below it - real, if rare, deep-
    # distress cases (P/B 0.1-0.3) stay scored normally; only the single-most-extreme tail
    # this session found actually driving unwarranted #1 ranks gets excluded.
    MIN_PLAUSIBLE_PB_RATIO = 0.05
    MIN_PLAUSIBLE_PS_RATIO = 0.05

    # ADDED 2026-08-31 (same session, same-day follow-up): the PB/PS floor above did NOT
    # fully fix VCIG - live-confirmed after a full remediation + recompute cycle, VCIG's
    # value_score was STILL pinned at 100.00 because its pe_ratio is ALSO ~0.01, the same
    # tiny-share-count-inflates-every-per-share-metric effect (VCIG's 618,994 real shares
    # outstanding makes EPS AND book value both huge relative to its ~$2 price) driving PE
    # to also win percentile 100 in _percent_rank_cheap_high once PB/PS were excluded. Same
    # floor, same reasoning, applied consistently to every "cheap is good" percentile-
    # ranked multiple in Value - not just the two this session happened to check first.
    # forward_pe gets the equivalent floor too, but in load_value_quality_growth_metrics.py
    # (MIN_PLAUSIBLE_FORWARD_PE_RATIO there) - it's computed from analyst_earnings_estimates
    # in that file, not here, unlike pe_ratio/pb_ratio/ps_ratio which are this loader's own.
    MIN_PLAUSIBLE_PE_RATIO = 0.05

    # TIGHTENED 2026-09-01 (goal session, "get the missing data"/"bizarre results" audit):
    # the prior <=1.0 (100%) bound below was live-confirmed to still let through absurd
    # "dividend yields" of 63-95% for real going-concern companies - HVT.A (63.08%, and #1
    # on the entire Value factor's top list off this alone), JEM (95.17%), HTCR (95.12%),
    # LZM (92.22%), TASK (88.48%), among 30+ symbols above 30%. Root causes vary (a
    # shares_outstanding scale error deflating entity_market_cap for JEM/HTCR - same class
    # already fixed once for PARA, see this bound's own prior history below; a per-share XBRL
    # concept that turned out to carry a much larger, likely mis-scaled figure for AD's
    # dividends_paid) - different mechanisms, same symptom, same fix: a tighter output-level
    # plausibility bound, the same guard-rather-than-chase-every-mechanism pattern already
    # used for MIN_PLAUSIBLE_PB_RATIO/PS_RATIO above (also added after a loose bound was
    # found "driving unwarranted #1 ranks"). No real, live sample case checked this session
    # cleared 30%; genuine high-yield BDCs/CLO funds/mREITs (FSK 22.6%, XFLT 27.4%, GPMT
    # 20.4%) stay comfortably under it, so this isn't cutting off a real category, just the
    # tail that's actually a data error.
    MAX_PLAUSIBLE_DIVIDEND_YIELD_RATIO = 0.30

    # FIXED 2026-08-22 (goal session: "Missing SEC/XBRL data" coverage audit): depository
    # institutions never tag a "CapitalExpenditures" XBRL concept in any fiscal year -
    # live-confirmed via JPM, BAC, MS, WFC, PNC's real companyfacts JSON (capex NULL across
    # every year 2007-2026). Same SIC codes as the community-bank revenue fallback concepts
    # in sec_statements.py (national/state commercial banks 6020-6022/6029, savings
    # institutions 6035-6036, bank holding companies 6712) - without this, fcf_yield/
    # margin_of_safety/intrinsic_value_per_share/free_cash_flow are structurally
    # uncomputable forever for the entire banking sector (not a transient extraction gap
    # that a future fetch could fix), since both the direct fcf=ocf-capex calc AND the
    # multi-year avg_fcf_fallback below require a non-None capex on every year they use.
    # A bank's capital allocation is fundamentally different from an industrial filer's -
    # investing activity is dominated by loan/securities purchases, not PP&E - so treating
    # its (genuinely absent, not missing) capex as 0 and using OCF directly as FCF is the
    # standard equity-research convention for this sector, not a guess.
    DEPOSITORY_INSTITUTION_SIC_CODES = frozenset({6020, 6021, 6022, 6029, 6035, 6036, 6712})

    # FIXED 2026-08-24 (goal: "Margin of Safety (DCF) / Cash flow data unavailable" audit):
    # unlike depository institutions above, insurance SIC codes (6311/6321/6331/6351/6361/
    # 6399) are NOT uniformly capex-less - live-confirmed ALL (Allstate, $267M FY2023) and
    # HIG (Hartford, $215M FY2023) both tag standard "PaymentsToAcquirePropertyPlantAnd
    # Equipment" with real, material values, so a blanket SIC-based coercion (like
    # DEPOSITORY_INSTITUTION_SIC_CODES) would incorrectly zero out their real capex. This is
    # a small, individually-verified symbol allowlist instead (same "verified alias table"
    # pattern as the WAB/Wabtec 13F fix, not a SIC-code allowlist) - each symbol below was
    # live-checked against its full companyfacts JSON and confirmed to have ZERO of: any
    # PP&E-family concept, any REIT-family concept, any insurer investment-real-estate
    # concept (PaymentsToAcquireRealEstateAndRealEstateJointVentures/
    # PaymentsToAcquireRealEstateHeldForInvestment - see sec_statements.py's get_cash_flow()
    # comment), or any other Payments/Purchase/Acquisition concept naming PP&E or real
    # estate, across their ENTIRE filing history (not just the current interim year) as of
    # 2026-08-24. A structural gap for these specific filers, not a transient extraction
    # gap a future fetch could fix - same rationale as the depository-institution case,
    # verified per-symbol rather than by SIC code because this sector isn't uniform.
    INSURANCE_CAPEX_EXEMPT_SYMBOLS = frozenset(
        {
            "CRBG",
            "FG",
            "GNW",
            "JXN",
            "LNC",
            "PRU",
            "AFL",
            "CNO",
            "AFG",
            "AXS",
            "CB",
            "EG",
            "GBLI",
            "HG",
            "HMN",
            "KG",
            "RNR",
            "SPNT",
            "AGO",
            "ORI",
            "OSG",
        }
    )

    # FIXED 2026-09-04 (goal session: "missing SEC/XBRL data under 6k" sweep, capex_never_
    # tagged_in_recent_filings follow-up): mirrors INSURANCE_CAPEX_EXEMPT_SYMBOLS above, for
    # mortgage REITs, consumer/specialty finance companies, and mineral-royalty traders
    # instead - each symbol below was live-checked against its full companyfacts JSON and
    # confirmed to have ZERO PaymentsToAcquirePropertyPlantAndEquipment/
    # PaymentsToAcquireProductiveAssets/PaymentsForCapitalImprovements anywhere in filing
    # history. Deliberately NOT SIC-based: SIC 6798 also covers ordinary EQUITY REITs (AVB,
    # EQR, ...) which DO tag real, material capex - same "not uniformly capex-less" caution
    # as insurance SIC codes above. Keep in sync with loaders/helpers/sec_base.py's
    # _FINANCIAL_CAPEX_EXEMPT_SYMBOLS (same duplication convention already used for
    # DEPOSITORY_INSTITUTION_SIC_CODES/INSURANCE_CAPEX_EXEMPT_SYMBOLS between this file and
    # that one).
    FINANCIAL_CAPEX_EXEMPT_SYMBOLS = frozenset(
        {
            "NAVI",
            "OMF",
            "DX",
            "ARR",
            "ORC",
            "CIM",
            "RWT",
            "MFIN",
            "CHMI",
            "RGLD",
            "MSB",
        }
    )

    # FIXED 2026-09-06 (goal session: "SEC/XBRL missing data to zero" sweep,
    # capex_never_tagged_in_recent_filings/missing_cash_flow_data continuation): a much larger
    # batch than the hand-picked lists above, verified programmatically rather than one symbol
    # at a time - for each symbol below, every fetched fiscal year's companyfacts JSON (all
    # us-gaap concepts already fetched by utils/external/sec_cash_flow.py's CAPEX-family list:
    # PaymentsToAcquirePropertyPlantAndEquipment/ProductiveAssets/MachineryAndEquipment/
    # OtherProductiveAssets/OtherPropertyPlantAndEquipment, the Purchase.../Additions... PP&E
    # variants, the REIT PaymentsToAcquire/DevelopRealEstate family, PaymentsForCapitalImprovements,
    # PaymentsToAcquireEquipmentOnLease/Land, the oil&gas PaymentsToAcquire/CostsIncurred
    # concepts, and CapitalExpenditures) was live-fetched from data.sec.gov/api/xbrl/companyfacts
    # and checked directly - a symbol only qualifies if EVERY one of those concepts is either
    # entirely absent from its full filing history, or was last tagged in a stale (pre-2023)
    # fiscal year (the filer stopped disclosing it - the same "genuinely went to zero" pattern
    # already documented for VLO/COIN/AAON above, not a naming gap this file hasn't found yet).
    # Explicitly excluded from this batch (left for narrower, individually-verified fixes
    # instead): foreign private issuers (is_foreign_private_issuer=TRUE - IFRS filers use
    # different concept names this us-gaap-only scan can't see, e.g. MFC/CRESY/BBAR/IRSA -
    # a real gap, not a genuine absence, for that subset), closed-end funds/commodity ETFs/ETNs/
    # royalty trusts/SPAC shells (verified by security_name - RICs and commodity trusts file
    # N-CSR, not a 10-K cash-flow statement, so "no capex concept found" there means "wrong
    # form type", not "zero capex"), and equity REITs holding physical real estate (ALX/SKT/
    # NLOP/SELF/IOR/MKZR - live-spot-checked and found to have real capex under a concept this
    # scan didn't include, unlike the mortgage/commercial-finance REITs kept below whose
    # business model has no physical property to improve at all - same "not uniformly
    # capex-less" caution as INSURANCE_CAPEX_EXEMPT_SYMBOLS's own docstring warns about SIC
    # 6798 more broadly). Kept in sync with loaders/helpers/sec_base.py's mirror set, same
    # convention as DEPOSITORY_INSTITUTION_SIC_CODES/INSURANCE_CAPEX_EXEMPT_SYMBOLS.
    LARGE_BATCH_CAPEX_EXEMPT_SYMBOLS = frozenset(
        {
            "ACR",
            "ACT",
            "ACTU",
            "ACXP",
            "ADBT",
            "ADIL",
            "AFCG",
            "AFGB",
            "AFGC",
            "AFGD",
            "AFGE",
            "AGNC",
            "AIDX",
            "AISP",
            "AIXC",
            "ALISR",
            "AMCI",
            "AMRN",
            "AMZE",
            "ANIX",
            "ANTX",
            "ANVS",
            "AOMR",
            "APMD",
            "APO",
            "APVO",
            "AREC",
            "ARES",
            "ARX",
            "ASBP",
            "ATHS",
            "AUID",
            "AVAT",
            "AVBP",
            "AVIR",
            "AVXL",
            "BBDC",
            "BBLG",
            "BCSF",
            "BESS",
            "BFH",
            "BHF",
            "BHFAL",
            "BITW",
            "BIVI",
            "BXBL",
            "BXDC",
            "BXMT",
            "CAR",
            "CCAP",
            "CCXI",
            "CELZ",
            "CIIT",
            "CION",
            "CMII",
            "CNTN",
            "COPR",
            "COYA",
            "CREG",
            "CRIS",
            "CRVO",
            "CURX",
            "CWD",
            "CWH",
            "CYCN",
            "CYPH",
            "DCBG",
            "DFTX",
            "DRMA",
            "DWTX",
            "DYAI",
            "EARN",
            "EDSA",
            "ELDN",
            "ELOX",
            "ELWT",
            "EMAT",
            "EQS",
            "ESLA",
            "EVLV",
            "FENC",
            "FIGR",
            "FLD",
            "FRNM",
            "FSK",
            "GAIN",
            "GALT",
            "GEG",
            "GLND",
            "GLSI",
            "GNPX",
            "GOOD",
            "GRDX",
            "GRML",
            "GSBD",
            "GXAI",
            "HDRN",
            "HIT",
            "HODO",
            "HRZN",
            "ICMB",
            "ICU",
            "INDP",
            "INFQ",
            "INTS",
            "IQI",
            "IRD",
            "IVR",
            "KAPA",
            "KBDC",
            "KKR",
            "LABT",
            "LIEN",
            "LLYVA",
            "LLYVK",
            "LODE",
            "LTBR",
            "MACI",
            "MAIA",
            "MAIN",
            "MFA",
            "MIRA",
            "MITT",
            "MLCI",
            "MMTX",
            "MNPR",
            "MNTN",
            "MRKR",
            "NCDL",
            "NCPL",
            "NEOV",
            "NERV",
            "NEUP",
            "NG",
            "NIXX",
            "NMAD",
            "NMFC",
            "NOMA",
            "NP",
            "NTIP",
            "NUCL",
            "NVCT",
            "NXTT",
            "OBDC",
            "OGEN",
            "ONFO",
            "OSRH",
            "OTF",
            "OTLK",
            "PFLT",
            "PFX",
            "PHUN",
            "PLYX",
            "PMN",
            "PMT",
            "PNNT",
            "PPCB",
            "PRHI",
            "PSBD",
            "PURR",
            "PVLA",
            "QNRX",
            "RC",
            "REF",
            "REFI",
            "RIGL",
            "RITM",
            "RKTO",
            "RLMD",
            "RNTX",
            "ROC",
            "RPRX",
            "RWAY",
            "SAR",
            "SCM",
            "SCYX",
            "SEG",
            "SEGG",
            "SGMT",
            "SILO",
            "SLS",
            "SNYR",
            "SOR",
            "SPRO",
            "STRO",
            "SUIG",
            "SUNB",
            "SUNS",
            "SYF",
            "SYRE",
            "TAGS",
            "TELO",
            "TENX",
            "THM",
            "TMQ",
            "TMS",
            "TPVG",
            "TRIN",
            "TSLX",
            "TTRX",
            "TWAV",
            "TXMD",
            "USDE",
            "UUU",
            "VKTX",
            "VNOM",
            "VOGX",
            "VOYA",
            "VS",
            "VWAV",
            "WTM",
            "XBIO",
            "XCUR",
            "XERS",
            "YYAI",
            "ZSQR",
        }
    )

    # FIXED 2026-08-18 (goal session, currency-poisoned-row cleanup follow-up): live-crashed
    # via NMR (Nomura Holdings, a JPY-reporting IFRS filer - JPY is FX-CONVERTED not rejected
    # outright, unlike KRW/VND above, since it's in MAJOR_CURRENCIES): the derived-shares-out
    # fallback (`shares = net_income / eps`, just below) computed 2,942,280,410,000,000 shares
    # - a currency-scale mismatch between net_income (converted) and eps (apparently not
    # converted the same way, or converted with a different effective scale) produced an
    # absurd ratio. NUMERIC(15,0) couldn't even hold the value, aborting the whole COPY batch
    # (1 bad symbol out of 15 failed the whole run's 5% error threshold, rolling back all 15 -
    # not just NMR). The existing MIN floor above catches implausibly-small outliers; nothing
    # caught implausibly-LARGE ones. No real company (even the most share-heavy real large-caps
    # after multiple splits) has anywhere near 100 billion shares outstanding - this ceiling is
    # generous enough to never reject a genuine value while catching this and any similar
    # future currency/scale-mismatch derivation error before it ever reaches the DB.
    MAX_PLAUSIBLE_SHARES_OUTSTANDING = 100_000_000_000

    # FIXED 2026-08-25 (goal: "fix all the things"/finance-accuracy follow-up audit): lowered
    # from 20x. The 20x threshold below was tuned specifically for per-filing XBRL scale-
    # tagging errors (LARK/RPAY, ~1000x) - live-verified against real SEC EDGAR data
    # (data.sec.gov/api/xbrl/companyconcept, dei:EntityCommonStockSharesOutstanding) that
    # WHLR (Wheeler REIT, a serial reverse-splitter/heavily-diluting distressed micro-cap)
    # has a GENUINE, correctly-reported ~18x swing in shares outstanding between its FY2025
    # 10-K (106,902) and its most recent 10-Q cover page (1,931,568, filed 2026-08-06) - not a
    # tagging bug, just annual-frequency data going stale fast for a company whose float
    # changes this much quarter to quarter. That 18x sat just under the old 20x bar, so the
    # cross-check below never corrected it, leaving a $39K "market cap" paired with today's
    # price. The underlying fix is the same either way (prefer company_info_sec, the more
    # current/independently-extracted source) regardless of whether the disagreement's root
    # cause is a tagging error or genuine share-count churn. Checked before lowering: live
    # DB-wide, 44 symbols sit in the newly-covered 10x-20x band (out of 4,105 with both
    # sources available) - spot-checked, overwhelmingly distressed/micro-cap tickers of the
    # same character as WHLR (reverse-split/heavy-dilution candidates), not stable large-caps
    # that would be wrongly flipped; FUBO (30.0M resolved vs 342.4M company_info_sec, 11.4x)
    # is a real live example of exactly this pattern being CORRECTED, not broken, by the
    # lower threshold (fuboTV's real share count is ~330-350M, not ~30M).
    #
    # FIXED 2026-08-31 (goal session: continuation of the UROY ~2.6x discrepancy flagged open
    # in sec_valuations_pl_row_coupled_stale_shares_hbio_fixed_20260831): lowered again, from
    # 10x to 2x. Live-verified UROY's resolved shares_out (126.8M, from FY2025
    # shares_outstanding_basic) vs company_info_sec (381.1M, ~3.0x) against a FRESH live
    # yfinance fetch (not the 7-week-stale yfinance_snapshot row that made an earlier same-day
    # check look deceptively close) - yfinance's sharesOutstanding=381,067,318 matches
    # company_info_sec EXACTLY, confirming company_info_sec correct and the SEC-derived value
    # stale/wrong, the same pattern as every fix above, just at a lower multiple this dataset
    # hadn't been checked at yet.
    #
    # Verified this generalizes, not a UROY one-off, via a DB-wide scan + live yfinance
    # cross-check on BOTH directions of the 2x-10x band (not just "company_info_sec bigger" -
    # the existing cross-check below is direction-agnostic, so both needed checking):
    # - company_info_sec LARGER (235 symbols DB-wide in this band): 7/7 spot-checked confirmed
    #   correct via live yfinance, including COKE (Coca-Cola Consolidated, a real ~$13B
    #   company, 7.9x) - not just distressed micro-caps this time. The lower end of this band
    #   clusters suspiciously tight at ~2.00-2.04x across many unrelated tickers (ARTV/DCH/
    #   RNAZ/LIDR/TNXP/MLI/NRXP/NKTR/JBIO/PTHS/...), consistent with an unadjusted 2-for-1
    #   stock split signature.
    # - `sv.shares_outstanding` LARGER (86 symbols DB-wide): 4/4 spot-checked ALSO confirmed
    #   company_info_sec correct via live yfinance - including HON (Honeywell) and FOX (Fox
    #   Corp), real large/mega-cap names. This one surprised the initial assumption ("a big
    #   company's bigger number is probably right") - trust the live check, not company
    #   familiarity: yfinance's real current sharesOutstanding matched company_info_sec exactly
    #   for both, not the larger stored value.
    # 11/11 live-verified correct in company_info_sec's favor, 0 counterexamples found in
    # either direction - unlike the 20x->10x lowering's "spot-checked, overwhelmingly
    # distressed/micro-cap" caveat, this evidence run deliberately included large/well-known
    # names specifically to stress-test for a false-positive risk at this lower threshold, and
    # found none.
    SHARES_OUTSTANDING_SCALE_MISMATCH_RATIO = 2

    # Per-run cache for _get_risk_free_rate() below - a plain class attribute (rather than an
    # __init__ override) since every real instantiation of this loader only ever runs once
    # per process; test fixtures construct via __new__ (bypassing __init__ entirely) and never
    # call _get_risk_free_rate, so this default is never touched by them.
    _risk_free_rate_cache: float | None = None
    # Per-run cache for _get_equity_risk_premium() below - same rationale as
    # _risk_free_rate_cache immediately above.
    _equity_risk_premium_cache: float | None = None

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Compute SEC-derived valuations for one symbol.

        Returns:
            List with single valuation dict or data_unavailable marker
        """
        # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero"): entity types that
        # structurally cannot file 10-K/10-Q (CEF/BDC/ETF/post-2024 banks) have no annual
        # financial statements data at all - return early with categorized unavailable reason
        # instead of trying to extract valuations from non-existent income statements.
        # Direct query check (not via mixin, SecValuationsLoader doesn't inherit
        # vqg_symbol_gates) - mirrors SymbolGateMixin._get_structural_entity_type_exemptions
        # (see its docstring: no `company_profile.entity_type` column exists in this schema;
        # an earlier version of this query referenced one and raised UndefinedColumn).
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT 1 FROM stock_symbols s WHERE s.symbol = %s AND s.active = TRUE
                  AND (
                    s.symbol IN (SELECT symbol FROM etf_symbols)
                    OR s.symbol IN (
                      SELECT c.symbol FROM company_info_sec c
                      WHERE COALESCE(c.sic_code, 0) = 0
                        AND COALESCE(c.entity_type, 'operating') IN ('other', 'investment')
                        AND c.symbol != 'OZK'
                    )
                  )
                """,
                (symbol,),
            )
            if cur.fetchone():
                return [
                    self._unavailable_marker(
                        symbol,
                        "entity_type_structurally_exempt_10k_filing",
                    )
                ]

        try:
            # Fetch latest financial data for symbol
            with DatabaseContext("read") as cur:
                # Income-statement fetch/derivation (revenue/EPS anchor-row fallbacks, EBITDA,
                # total_cash/total_debt, PEG's prior_year_eps, dcf_eps_cagr_pct) extracted
                # verbatim to IncomeStatementContextMixin._fetch_income_statement_context
                # (2026-09-05, file-size ratchet decomposition) - see that method's own
                # docstring for the full per-field rationale/history, all preserved there
                # unchanged. Returns a data_unavailable marker list to return immediately on
                # either of the two early-exit paths it used to hit inline, or the full
                # derived-context tuple on success.
                income_ctx = self._fetch_income_statement_context(cur, symbol)
                if isinstance(income_ctx, list):
                    return income_ctx
                (
                    income_rows,
                    is_foreign_private_issuer,
                    sic_code,
                    ttm_fiscal_year,
                    ttm_revenue,
                    _ttm_net_income,
                    ttm_eps_basic,
                    prior_year_eps,
                    eps_substituted_from_row1,
                    dcf_eps_cagr_pct,
                    total_cash,
                    total_debt,
                    ebitda,
                    reported_shares_outstanding,
                ) = income_ctx
                # Shares-outstanding tiered resolution (reported basic -> derived net_income/
                # eps -> older fiscal year -> company_info_sec -> diluted -> dei cover-page ->
                # scale-mismatch cross-check -> dual-class/FPI yfinance) extracted verbatim to
                # SharesOutstandingResolutionMixin._resolve_shares_outstanding (2026-09-05,
                # file-size ratchet decomposition) - see that method's own docstring for the
                # full per-tier rationale/history, all preserved there unchanged.
                (
                    shares_out,
                    has_dual_class_sibling,
                    shares_out_from_dual_class_yfinance,
                    shares_out_from_fpi_yfinance,
                ) = self._resolve_shares_outstanding(
                    cur,
                    symbol,
                    income_rows,
                    ttm_fiscal_year,
                    ttm_eps_basic,
                    _ttm_net_income,
                    eps_substituted_from_row1,
                    is_foreign_private_issuer,
                    reported_shares_outstanding,
                )

                # Cross-check the multi-year DCF growth driver against a dual-class sibling's
                # own EPS for the same two endpoint years - see
                # _validate_dual_class_eps_cagr's docstring for the live BRK.A/BRK.B evidence
                # (FY2020-2022 EPS scaled ~2715:1 instead of the real, fixed 1500:1) that
                # motivated this guard.
                dcf_eps_cagr_pct = self._validate_dual_class_eps_cagr(
                    cur, symbol, has_dual_class_sibling, income_rows, dcf_eps_cagr_pct
                )

                # Fail if still no shares outstanding available.
                # FIXED 2026-08-22 (goal session: "Ownership data unresolved" bucket audit):
                # every SEC-sourced tier above that could resolve a foreign private issuer's
                # shares outstanding is deliberately gated off (home-market-units risk - see
                # the tier comments above) - UPDATED 2026-08-27: the yfinance FPI tier just
                # above now recovers most of these live (768 of 945 previously-NULL
                # market_cap symbols were tagged this reason), so reaching this branch now
                # means yfinance ALSO had no usable value for this symbol (fetch failure,
                # rate limit, or a genuinely untracked ticker), not just "is an FPI." Still the
                # same fact load_short_interest_finra.py/load_institutional_holdings_13f.py already
                # label "foreign_private_issuer_shares_unavailable" (root-caused to this
                # exact method's 2026-08-19 FPI unit-mismatch fix per their own comments).
                # This method itself still used the generic "shares_outstanding_unavailable"
                # for its own output, which value_metrics's _build_value_metrics propagates
                # verbatim to ~10 downstream fields (market_cap/pe_ratio/pb_ratio/ps_ratio/
                # peg_ratio/dividend_yield/fcf_yield/ev_ebitda/ev_revenue/intrinsic_value/
                # margin_of_safety) - live-confirmed 763 of 799 universe symbols carrying
                # this reason (95.5%) are real FPIs, cascading into ~7,600 of the 14,339
                # "Ownership data unresolved" coverage-report rows.
                if not shares_out or shares_out <= 0:
                    reason = (
                        "foreign_private_issuer_shares_unavailable"
                        if is_foreign_private_issuer
                        else "shares_outstanding_unavailable"
                    )
                    return [
                        self._unavailable_marker(
                            symbol,
                            reason,
                            total_debt=total_debt,
                            total_cash=total_cash,
                            ebitda=ebitda,
                        )
                    ]

                # FIXED 2026-08-25 (goal: "margin of safety results look wrong" audit):
                # shares_out above is deliberately CLASS-SPECIFIC whenever has_dual_class_sibling
                # is True - correct for market_cap/pe_ratio/pb_ratio/ps_ratio, which must reflect
                # THIS class's own price x share count. But annual_cash_flow.operating_cash_flow/
                # capex (fcf, used below for fcf_yield and the DCF) is entity-wide: data.sec.gov's
                # companyfacts API collapses every concept to ONE value per CIK+period (see the
                # dual-class shares_outstanding comments above) and that collapsed OCF/CapEx row
                # is duplicated verbatim onto every sibling ticker's annual_cash_flow rows - live-
                # confirmed identical operating_cash_flow/capex for TAP and TAP.A across all 19
                # fiscal years on file. Dividing that entity-wide FCF by a minority class's tiny
                # class-specific share count (e.g. TAP.A's 2.56M vs TAP's ~188M combined)
                # overstated TAP.A's DCF intrinsic value by ~500x (fcf_yield 936%, margin of
                # safety 99.8% on a stock priced normally) - the exact "results look wrong"
                # symptom reported this session, not a modeling-methodology problem.
                #
                # Trigger is has_dual_class_sibling, NOT the narrower
                # shares_out_from_dual_class_yfinance flag: live-confirmed TAP.A's shares_out
                # actually resolves via the UNGATED company_info_sec fallback a few tiers above
                # (not the yfinance tier) - company_info_sec.shares_outstanding is independently,
                # deliberately class-specific per ticker too (see
                # test_company_info_sec_dual_class_shares_dimensional_resolution.py), so
                # data_source stays "sec_audited" and shares_out_from_dual_class_yfinance never
                # gets set even though shares_out is still class-specific here. Any tier reachable
                # when has_dual_class_sibling=True is class-specific by construction - every
                # entity-wide (SEC-collapsed) tier is explicitly gated off for exactly that reason
                # (see each tier's own has_dual_class_sibling comment above).
                #
                # reported_shares_outstanding (extracted above, unconditionally, before any
                # has_dual_class_sibling gate) is that same entity-wide collapsed SEC figure -
                # exactly the correct denominator to pair with entity-wide FCF, and it's what the
                # filer's own reported per-share figures (ttm_eps, book value/share) are already
                # implicitly built on. The `>= shares_out` floor guards against pairing a
                # class-specific numerator with a smaller/unrelated "entity" figure (e.g. a
                # per-filer XBRL scale-tagging error on reported_shares_outstanding itself,
                # unrelated to the dual-class issue this fix targets) - a real combined entity
                # total can never be smaller than any single class's own share count.
                # ADDED 2026-09-06 (goal: "implausible values" audit, live regression of the
                # fix above): reported_shares_outstanding comes from THIS symbol's OWN
                # annual_income_statement.shares_outstanding_basic, which is None for any
                # dual-class filer that tags fully separate per-class EPS/share figures
                # rather than one blended entity-wide count - unlike BRK.A/BRK.B (one
                # blended A-equivalent share count, satisfies the check below directly),
                # Molson Coors (TAP/TAP.A) tags distinct "Basic EPS - Class A"/"...Class B"
                # facts with no combined figure ever reported, so reported_shares_outstanding
                # is unconditionally None for TAP.A and the override below never fires.
                # Live-confirmed: TAP.A's fcf_yield was 840.20% and intrinsic_value_per_share
                # $15,181.55 (vs a real $47.96 price) from dividing TAP/TAP.A's shared
                # entity-wide FCF by TAP.A's own 2,563,034-share class-specific market cap.
                # Extracted to _resolve_separate_class_entity_shares (below) to keep this
                # method's cyclomatic complexity under the ruff C901 cap.
                reported_shares_outstanding = self._resolve_separate_class_entity_shares(
                    cur,
                    symbol,
                    has_dual_class_sibling,
                    reported_shares_outstanding,
                    shares_out,
                    ttm_fiscal_year,
                )

                entity_shares_out_for_fcf = shares_out
                if (
                    has_dual_class_sibling
                    and reported_shares_outstanding
                    and self.MIN_PLAUSIBLE_SHARES_OUTSTANDING
                    < reported_shares_outstanding
                    < self.MAX_PLAUSIBLE_SHARES_OUTSTANDING
                    and float(reported_shares_outstanding) >= shares_out
                ):
                    entity_shares_out_for_fcf = float(reported_shares_outstanding)
                    logger.debug(
                        f"[{symbol}] Using entity-wide reported_shares_outstanding "
                        f"({entity_shares_out_for_fcf:,.0f}) instead of class-specific shares_out "
                        f"({shares_out:,.0f}) for FCF-based ratios (fcf_yield, DCF intrinsic "
                        f"value) - dual-class sibling with entity-wide FCF numerator."
                    )

                # Get current price for valuation computations
                cur.execute(
                    """
                    SELECT close FROM price_daily
                    WHERE symbol = %s AND close IS NOT NULL AND close > 0
                    ORDER BY date DESC LIMIT 1
                    """,
                    (symbol,),
                )
                price_row = cur.fetchone()
                if not price_row or not price_row[0]:
                    return [
                        self._unavailable_marker(
                            symbol, "no_recent_price", total_debt=total_debt, total_cash=total_cash, ebitda=ebitda
                        )
                    ]

                current_price = safe_float(price_row[0], f"{symbol}.close", allow_none=False)
                if current_price <= 0:
                    return [
                        self._unavailable_marker(
                            symbol, "invalid_price", total_debt=total_debt, total_cash=total_cash, ebitda=ebitda
                        )
                    ]

                # Get latest balance sheet (book value - optional, may not exist for all companies)
                # NOTE: Removed data_unavailable = FALSE filter to allow fallback computation
                # FIXED 2026-08-17: added "AND fiscal_year IS NOT NULL" - Postgres's DESC
                # ordering defaults to NULLS FIRST, so a stray NULL-fiscal_year row (e.g. a
                # crash-marker placeholder - see load_financial_statements.py's 2026-08-17 fix
                # comment for how one of these got written 4,948 times in a single bad run)
                # would silently outrank real, recent data here. Defensive: this loader doesn't
                # write such rows itself, but every "latest fiscal year" query reading a table
                # another loader also writes to should not trust that no NULL key ever lands
                # there.
                # FIXED 2026-08-18 (goal: "no SEC data"/loader audit): this was still a plain
                # `ORDER BY fiscal_year DESC LIMIT 1` with no regard for whether that year's
                # stockholders_equity was actually populated - the exact "latest year is empty"
                # bug class already fixed in this same file for the debt/income-statement/
                # shares_outstanding queries (see test_sec_valuations_debt_query_prefers_
                # populated_fiscal_year.py), just never applied here. Live-confirmed: AA has real
                # stockholders_equity=$5.157B for FY2024 but NULL for FY2025/FY2026 (in-progress/
                # unfiled years); ADM/AAON are NULL across every year on file for a different
                # reason (NCI-inclusive equity concept, separately fixed) but would hit this same
                # blind-latest-year trap once backfilled. pb_ratio silently went "missing_sec_data"
                # for 1,225 symbols as a result. Same CASE-based prioritization as the debt query:
                # prefer a fiscal year with a real reported value, only falling back to the bare
                # latest year (still correctly NULL) for companies with no balance sheet history.
                # FIXED 2026-08-20 (goal: finance-accuracy audit): added data_unavailable IS NOT
                # TRUE - same bug class as the income-statement/cash/debt queries above (a
                # reason='incomplete_sec_filing_balance' row's stockholders_equity, if non-NULL,
                # is not reliable and was silently poisoning pb_ratio).
                cur.execute(
                    """
                    SELECT stockholders_equity
                    FROM annual_balance_sheet
                    WHERE symbol = %s AND fiscal_year IS NOT NULL AND data_unavailable IS NOT TRUE
                    ORDER BY (CASE WHEN stockholders_equity IS NOT NULL THEN 0 ELSE 1 END), fiscal_year DESC
                    LIMIT 1
                    """,
                    (symbol,),
                )
                balance_row = cur.fetchone()
                book_value = balance_row[0] if balance_row else None
                # Note: book_value can be None for companies without balance sheets - PB ratio will be NULL

                # Get latest cash flow (for FCF - optional, may not exist for all companies)
                # See the fiscal_year IS NOT NULL comment on the balance sheet query above.
                # FIXED 2026-08-18 (goal: DCF/margin-of-safety coverage): also fetch the prior
                # 2 fiscal years' OCF/CapEx so the DCF can fall back to a 3-year average FCF
                # when the latest year alone is negative - a single capex-heavy or cash-flow-
                # lumpy year (common for cyclical/capital-intensive real businesses) was
                # unconditionally killing the DCF even when the company is normally FCF-
                # positive. Live-confirmed: of the 2,305 universe symbols with
                # margin_of_safety_unavailable_reason='negative_free_cash_flow', 443 have a
                # positive 3yr-average FCF despite a negative latest year. fcf_yield (below)
                # deliberately keeps using only the latest year - that metric is meant to
                # reflect current cash generation, not a smoothed figure; only the DCF's
                # normalization changes.
                #
                # FIXED 2026-08-20 (goal: finance-accuracy audit): data_unavailable=TRUE rows
                # were being read anyway (a 2026-08-xx change removed the `data_unavailable =
                # FALSE` filter here to stop it excluding legitimate rows where the column is
                # simply unset/NULL - see git blame). But `data_unavailable=TRUE` with
                # reason='incomplete_sec_filing_cashflow' means the filer's cash-flow section
                # itself is incomplete/inconsistent, not merely unset - the non-NULL numbers on
                # those rows can be raw, unconverted foreign-currency magnitudes (e.g. KT/Korea
                # Telecom FY2025: operating_cash_flow=4.94e12, still-untranslated KRW) or other
                # known-bad values, and downstream has no NULL to catch since the column IS
                # populated. Live-confirmed 13 universe symbols (BAP, DLB, PHG, GLDG, GTN,
                # GTN.A, OLP, PAL, REA, RUM, VS, WYFI, APC) currently computing fcf_yield in the
                # hundreds-to-thousands-of-percent range (e.g. BAP=40.81, DLB=4.80, PHG=3.52 -
                # i.e. 4081%/480%/352%) purely from this. `data_unavailable IS NOT TRUE` (not
                # `= FALSE`) keeps admitting NULL-flag rows exactly as before while excluding
                # only the confirmed-bad ones, falling back to the next real fiscal year (or to
                # the existing None-handling below) instead of a fabricated number.
                cur.execute(
                    """
                    SELECT operating_cash_flow, capex, dividends_paid, stock_based_compensation,
                           common_stock_repurchased
                    FROM annual_cash_flow
                    WHERE symbol = %s AND fiscal_year IS NOT NULL AND data_unavailable IS NOT TRUE
                    ORDER BY fiscal_year DESC LIMIT 3
                    """,
                    (symbol,),
                )
                cash_rows = cur.fetchall()
                ocf, capex, dividends_paid, stock_based_compensation, common_stock_repurchased = (
                    cash_rows[0] if cash_rows else (None, None, None, None, None)
                )
                # Note: None values here mean FCF yield/dividend yield will be NULL (not available)
                # Depository institutions never report capex at all (see
                # DEPOSITORY_INSTITUTION_SIC_CODES above) - treat it as 0 rather than
                # unknowable, for both the latest year and every year in the multi-year
                # average below. Same treatment for the small, individually-verified
                # INSURANCE_CAPEX_EXEMPT_SYMBOLS/FINANCIAL_CAPEX_EXEMPT_SYMBOLS allowlists
                # above (symbol-based, not SIC-based - neither sector is uniformly
                # capex-less the way banking is).
                is_capex_exempt = (
                    sic_code in self.DEPOSITORY_INSTITUTION_SIC_CODES
                    or symbol in self.INSURANCE_CAPEX_EXEMPT_SYMBOLS
                    or symbol in self.FINANCIAL_CAPEX_EXEMPT_SYMBOLS
                    or symbol in self.LARGE_BATCH_CAPEX_EXEMPT_SYMBOLS
                )
                if is_capex_exempt and capex is None:
                    capex = 0
                avg_fcf_fallback = self._compute_avg_fcf_fallback(cash_rows, is_capex_exempt)

                # Beta (stability_metrics, 60-day covariance vs SPY - see load_risk_metrics_daily.py's
                # _get_beta_from_db) + the live 10Y Treasury yield + the live VIX-scaled equity
                # risk premium (2026-08-25, goal: DCF audit follow-up - dynamic ERP, see
                # DCF_MIN_EQUITY_RISK_PREMIUM's docstring) feed the DCF's CAPM discount rate
                # below (see _compute_discount_rate) - replaces the old flat 10%/yr rate.
                cur.execute("SELECT beta FROM stability_metrics WHERE symbol = %s", (symbol,))
                beta_row = cur.fetchone()
                beta = float(beta_row[0]) if beta_row and beta_row[0] is not None else None
                risk_free_rate = self._get_risk_free_rate(cur)
                equity_risk_premium = self._get_equity_risk_premium(cur)
                # Net borrowing (2026-08-25, goal: DCF audit follow-up - true FCFE via net
                # borrowing, see _get_net_borrowing_for_dcf's docstring) - additive DCF-only
                # correction toward a true FCFE instead of the zero-net-borrowing-assumed
                # OCF-CapEx-SBC proxy.
                net_borrowing = self._get_net_borrowing_for_dcf(cur, symbol)

                # FIXED 2026-08-20 (goal: finance-accuracy audit): fetched here, still inside
                # the `with DatabaseContext("read") as cur:` block - _sanity_check_market_cap()
                # itself runs after this block closes (it needs valuation_row, only available
                # once _compute_valuations() has run), so the query must happen while cur is
                # still open. See that method's own docstring for the full rationale.
                cur.execute("SELECT market_cap, pe_ratio FROM yfinance_snapshot WHERE symbol = %s", (symbol,))
                yf_row = cur.fetchone()
                yf_market_cap = float(yf_row[0]) if yf_row and yf_row[0] is not None and yf_row[0] > 0 else None
                yf_pe_ratio = float(yf_row[1]) if yf_row and yf_row[1] is not None and yf_row[1] > 0 else None

            # FIXED 2026-08-20 (goal: finance-accuracy audit, part 2): yfinance_snapshot is
            # frozen (no writer since Session 275, 39 days stale as of this fix) and this
            # sanity check is the PRIMARY defense for foreign private issuers specifically
            # (company_info_sec is deliberately skipped for FPIs above - see
            # is_foreign_private_issuer usage - because it carries the same home-market-vs-
            # ADS unit-mismatch risk as the primary data). Overriding with a live fetch only
            # for FPIs, outside the `with DatabaseContext` block above (cur already released -
            # don't hold a pooled connection open across a network call). Fails open to the
            # (likely-stale-but-better-than-nothing) table value on any live-fetch error.
            yf_market_cap_is_live = False
            if is_foreign_private_issuer:
                live_mcap, live_pe, _live_shares_out = self._fetch_live_fpi_yfinance_check_values(symbol)
                if live_mcap is not None:
                    yf_market_cap = live_mcap
                    yf_market_cap_is_live = True
                if live_pe is not None:
                    yf_pe_ratio = live_pe

            # ADDED 2026-08-31: see DOMESTIC_FILER_ADS_RATIO_OVERRIDES' own module-level comment
            # for the full AMRN rationale/evidence - applied here, after every other tier
            # (including the FPI live-fetch, which never fires for AMRN since it's correctly
            # classified domestic) has finished resolving shares_out, and before it's used for
            # market_cap/pb_ratio/ps_ratio/etc below.
            ads_ratio = DOMESTIC_FILER_ADS_RATIO_OVERRIDES.get(symbol)
            if ads_ratio and shares_out:
                logger.debug(f"[{symbol}] Applying ADS ratio override: {shares_out:,.0f} / {ads_ratio:g}")
                shares_out = shares_out / ads_ratio

            # See RECENT_REVERSE_SPLITS_SHARES_OUT' own module-level comment (PPCB/NXTT/HCWC).
            reverse_split_ratio = RECENT_REVERSE_SPLITS_SHARES_OUT.get(symbol)
            if reverse_split_ratio and shares_out:
                logger.debug(
                    f"[{symbol}] Applying reverse-split shares_out override: "
                    f"{shares_out:,.0f} / {reverse_split_ratio:g}"
                )
                shares_out = shares_out / reverse_split_ratio

            # Compute valuations (convert all values to float)
            # CRITICAL: Don't convert None to 0.0 - need to preserve None for PS ratio computation
            # If revenue is None, _compute_valuations will skip PS ratio (but that's OK)
            # FIXED 2026-08-20 (goal: finance-accuracy audit): ocf/capex were still using the
            # `if x else 0.0` pattern this same comment warns against - the exact "AA
            # live-confirmed" bug class fixed for total_debt just below, never applied here.
            # `_compute_valuations` already has a correct `if ocf and capex is not None:` guard
            # (skip fcf_yield when capex is genuinely unknown) but it never saw a real None:
            # capex=NULL (not yet tagged for the latest fiscal year - common when a filer's OCF
            # posts before its capex line is separately broken out) was coerced to 0.0 here,
            # producing a fake "free cash flow" = full OCF with nothing deducted. Live-confirmed:
            # AAL (American Airlines) FY2026 operating_cash_flow=$4.694B, capex=NULL -> computed
            # fcf_yield=51.32% (vs a real few-percent figure); same pattern hit HMY, CSAN, DXC,
            # GT, WD and others. Preserving None lets the existing guard correctly skip fcf_yield
            # for that year instead of fabricating one from an implicit zero-capex assumption.
            valuation_row = self._compute_valuations(
                symbol,
                float(current_price),
                float(shares_out),
                float(ttm_eps_basic) if ttm_eps_basic else None,
                float(ttm_revenue) if ttm_revenue else None,  # Changed from 0.0 to None
                float(book_value) if book_value else None,
                float(ocf) if ocf is not None else None,
                float(capex) if capex is not None else None,
                float(prior_year_eps) if prior_year_eps else None,
                float(dividends_paid) if dividends_paid else None,
                # FIXED 2026-08-18 (AA live-confirmed): `if total_debt else None` treated a
                # genuine 0.0 (a real, fully zero-debt fiscal year) as falsy, silently
                # discarding it the same way a missing value would be - `is not None` is the
                # correct check here, same fix class as the SQL tier change just above.
                float(total_debt) if total_debt is not None else None,
                float(total_cash) if total_cash else None,
                float(ebitda) if ebitda else None,
                avg_fcf_fallback,
                beta,
                risk_free_rate,
                shares_out_from_dual_class_yfinance,
                entity_shares_out_for_fcf,
                float(stock_based_compensation) if stock_based_compensation is not None else None,
                dcf_eps_cagr_pct,
                equity_risk_premium,
                net_borrowing,
                shares_out_from_fpi_yfinance,
                float(common_stock_repurchased) if common_stock_repurchased is not None else None,
            )
            # FIXED 2026-08-30 (goal: full-data audit, AKTX follow-up): yfinance_snapshot has
            # zero coverage for 645 active-universe symbols (the table's own writer has been
            # frozen since Session 275 - see the "39 days stale" comment above), leaving
            # _sanity_check_market_cap with nothing to compare against for any of them - a
            # wrong computed market_cap sails through completely unprotected, not just for
            # FPIs (which already get their own live-fetch override above). Live-confirmed via
            # AKTX (Akari Therapeutics, a $10.70 micro-cap biotech, NOT an FPI - see
            # load_company_info_sec.py's is_foreign_private_issuer recency fix, same session):
            # a genuinely-tagged-but-context-implausible share count computed
            # market_cap=$720.4B with zero cross-check available. An ABSOLUTE ceiling can't
            # fix this - the same query that found AKTX also surfaced SKHY ($1.14T, same
            # shape) alongside BRK.B ($701.75B, a REAL value at nearly the same magnitude as
            # AKTX's wrong one) - only a company-specific independent source can tell them
            # apart. Gated to market_cap > $50B (not all 645) purely to bound live-fetch
            # volume on a full-universe run - live-confirmed only 29 of the 645 clear this
            # bar. Reuses the same live-fetch helper the FPI tier above already relies on;
            # nothing about it is actually FPI-specific internally.
            if yf_market_cap is None and not is_foreign_private_issuer:
                computed_market_cap = valuation_row.get("market_cap")
                if computed_market_cap is not None and computed_market_cap > 50_000_000_000:
                    live_mcap, _live_pe, _live_shares_out = self._fetch_live_fpi_yfinance_check_values(symbol)
                    if live_mcap is not None:
                        yf_market_cap = live_mcap
                        yf_market_cap_is_live = True

            self._sanity_check_market_cap(symbol, valuation_row, yf_market_cap, yf_market_cap_is_live)
            self._sanity_check_pe_ratio(symbol, valuation_row, yf_pe_ratio, yf_market_cap_is_live)
            self._recategorize_ric_dcf_fcf_reason(symbol, valuation_row)
            self._recategorize_unsupported_currency_dcf_fcf_reason(symbol, valuation_row)
            self._recategorize_royalty_trust_dcf_fcf_reason(symbol, valuation_row)
            self._recategorize_capex_never_tagged_dcf_fcf_reason(symbol, valuation_row)
            self._recategorize_blank_check_dcf_fcf_reason(symbol, valuation_row)
            # Deliberately LAST DB-touching call in this method (after every _recategorize_*
            # above, each of which opens its own cursor) - see that method's own docstring for
            # why, plus a test-fixture-brittleness note: this is the only ordering under which
            # every existing hand-scripted fetchone_results test fixture (30+ files, none of
            # which could have anticipated this later addition) safely exhausts at the true end
            # of its scripted sequence instead of shifting every later scripted value by one
            # position - the latter silently corrupts assertions rather than raising, which is
            # worse than the crash it replaces. Do not move this earlier without auditing every
            # such fixture again.
            with DatabaseContext("read") as cur:
                self._sanity_check_shares_outstanding_vs_volume(symbol, valuation_row, cur)

            return [valuation_row]

        except TimeoutError as e:
            marker = handle_exception(symbol, e, "querying SEC financial data")
            return [marker]
        except (KeyError, IndexError) as e:
            # Schema or data structure issue
            marker = handle_exception(symbol, e, "parsing SEC financial data")
            return [marker]
        except ValueError as e:
            # Data validation or conversion error
            marker = handle_invalid_data(symbol, e, "computing valuations")
            return [marker]
        except Exception as e:
            # Try to classify and handle, or fail-fast if truly unexpected
            marker = handle_exception(symbol, e, "computing valuations")
            return [marker]

    def _resolve_separate_class_entity_shares(
        self,
        cur: Any,
        symbol: str,
        has_dual_class_sibling: bool,
        reported_shares_outstanding: float | None,
        shares_out: float,
        ttm_fiscal_year: int,
    ) -> float | None:
        """Fallback source for reported_shares_outstanding when the primary path (this
        symbol's own annual_income_statement.shares_outstanding_basic) comes up empty.

        ADDED 2026-09-06 (goal: "implausible values" audit): the 2026-08-25 dual-class
        entity-wide-FCF fix (see fetch_incremental's call site) pairs entity-wide FCF with
        an entity-wide share count via reported_shares_outstanding - this works for filers
        like BRK.A/BRK.B that tag one blended A-equivalent share count, but is
        unconditionally NULL for filers that tag fully separate per-class EPS/share figures
        with no combined figure ever reported (Molson Coors TAP/TAP.A: distinct "Basic EPS -
        Class A"/"...Class B" XBRL facts). For those, the override's own precondition was
        never met, so it silently never fired.

        Live-confirmed real, financially material impact before this fix: TAP.A fcf_yield
        840.20%, intrinsic_value_per_share $15,181.55 vs a real $47.96 price; GTN.A 260.79%/
        $829.25 vs $5.97; HVT.A 73.03% vs HVT's 6.02%; BH.A 18.81% vs BH's ~5-10% range.

        Falls back to this symbol's own resolved shares_out PLUS its sibling's own
        class-specific shares_outstanding_basic for the nearest fiscal year at or before the
        anchor year (not an exact-year match: live-confirmed GTN.A's own anchor fiscal_year,
        2026, is a placeholder row with revenue/shares_outstanding_basic both NULL - GTN's
        own most recent REAL row is FY2025, one year back, same "latest year can be an empty
        placeholder" shape _fetch_income_statement_context's own ORDER BY already works
        around for this symbol's own income_rows). Summing is only safe here (not
        double-counting) because this fallback exclusively targets the
        separate-class-reporting case - BRK-style blended reporting already succeeds via the
        untouched primary path, so this fallback never runs for it.

        Live-verified via SecValuationsLoader.fetch_incremental called directly (not mocked):
        TAP.A fcf_yield 840.20% -> 10.68%, intrinsic $15,181.55 -> $192.95 (TAP itself:
        12.81%, broadly consistent); GTN.A 260.79% -> 24.84% (GTN: 16.86%); HVT.A 73.03% ->
        3.2% (HVT: 2.18%); BH.A 18.81% -> 1.74% (BH: 4.81%). Regression check: BRK.A/BRK.B
        unchanged at 2.29% both, AAPL/OZK (no dual-class sibling) unaffected.
        """
        if (
            reported_shares_outstanding
            and self.MIN_PLAUSIBLE_SHARES_OUTSTANDING
            < reported_shares_outstanding
            < self.MAX_PLAUSIBLE_SHARES_OUTSTANDING
            and float(reported_shares_outstanding) >= shares_out
        ) or not has_dual_class_sibling:
            return reported_shares_outstanding

        sibling_base_root = symbol.split(".")[0]
        sibling_no_sep_root = next(
            (r for r in DUAL_CLASS_NO_SEPARATOR_ROOTS if symbol.startswith(r) and len(symbol) == len(r) + 1),
            None,
        )
        cur.execute(
            """
            SELECT ais.shares_outstanding_basic
            FROM annual_income_statement ais
            JOIN stock_symbols s ON s.symbol = ais.symbol AND s.active = TRUE
            WHERE ais.symbol != %s
              AND (
                ais.symbol = %s OR ais.symbol LIKE %s
                OR (%s::text IS NOT NULL AND ais.symbol LIKE %s AND length(ais.symbol) = %s)
              )
              AND ais.fiscal_year <= %s
              AND ais.shares_outstanding_basic IS NOT NULL
            ORDER BY ais.fiscal_year DESC
            LIMIT 1
            """,
            (
                symbol,
                sibling_base_root,
                f"{sibling_base_root}.%",
                sibling_no_sep_root,
                f"{sibling_no_sep_root}%" if sibling_no_sep_root else "__no_such_root__",
                len(symbol),
                ttm_fiscal_year,
            ),
        )
        sibling_row = cur.fetchone()
        if not (sibling_row and sibling_row[0]):
            return reported_shares_outstanding

        combined_shares = float(sibling_row[0]) + shares_out
        if not (self.MIN_PLAUSIBLE_SHARES_OUTSTANDING < combined_shares < self.MAX_PLAUSIBLE_SHARES_OUTSTANDING):
            return reported_shares_outstanding

        logger.debug(
            f"[{symbol}] No blended reported_shares_outstanding available - combining own "
            f"shares_out ({shares_out:,.0f}) with sibling's class-specific "
            f"shares_outstanding_basic ({float(sibling_row[0]):,.0f}) for FY{ttm_fiscal_year} "
            f"= {combined_shares:,.0f} entity-wide total."
        )
        return combined_shares

    def _recategorize_ric_dcf_fcf_reason(self, symbol: str, valuation_row: dict[str, Any]) -> None:
        """Overrides a generic dcf_fcf_unavailable_reason with a specific one for a registered
        investment company. Mutates `valuation_row` in place.

        FIXED 2026-09-05 (goal: "SEC/XBRL missing data to zero" follow-up): a registered
        investment company (closed-end fund/investment trust) files a "Statement of Changes in
        Net Assets" with no conventional cash-flow-statement concepts to tag at all, so
        dcf_fcf_base always comes back None and _compute_yield_and_dcf_fields's own generic
        "missing_cash_flow_data" fallback fires - same root fact already established for
        fcf_margin/fcf_yield/accruals_ratio/ocf_to_net_income/roic_pct/debt_to_equity in
        loaders/helpers/vqg_quality.py and vqg_value.py, just not recognized here since this
        mixin has no access to ValueQualityGrowthMetricsLoader's
        _get_registered_investment_company_symbols() gate (different class hierarchy) - a small
        inline query instead. Live-confirmed EVN/BSTZ/CEV/BTX/BUI/JHI/PMO (7 universe symbols).
        Only overrides the generic fallback reason, never a real computed value or a more
        specific reason (negative_free_cash_flow/implausible_dcf_result).
        """
        if valuation_row.get("dcf_fcf_unavailable_reason") != "missing_cash_flow_data":
            return
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT 1
                FROM company_info_sec c
                WHERE c.symbol = %s AND c.entity_type = 'other' AND c.sic_code IS NULL
                  AND EXISTS (
                      SELECT 1 FROM annual_balance_sheet b
                      WHERE b.symbol = c.symbol AND b.data_unavailable = FALSE
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM annual_cash_flow f
                      WHERE f.symbol = c.symbol AND f.free_cash_flow IS NOT NULL
                        AND f.data_unavailable IS NOT TRUE
                  )
                """,
                (symbol,),
            )
            if cur.fetchone() is not None:
                valuation_row["dcf_fcf_unavailable_reason"] = "registered_investment_company_no_xbrl"

    def _recategorize_unsupported_currency_dcf_fcf_reason(self, symbol: str, valuation_row: dict[str, Any]) -> None:
        """Overrides a generic dcf_fcf_unavailable_reason with "unsupported_currency_no_fx_rate"
        for a foreign private issuer whose annual_cash_flow row was already tagged that way.
        Mutates `valuation_row` in place.

        ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, same-day follow-up to
        the has_unsupported_currency_only_fact fix in load_financial_statements.py /
        utils/external/sec_statements_shared.py): a foreign private issuer that tags
        operating_cash_flow only under a hyperinflationary/unsupported local currency (e.g.
        ARS - GGAL/BBAR/CRESY/LOMA/IRS and more, live-confirmed via real SEC companyfacts) has
        a real, non-fabricatable ocf=None, so dcf_fcf_base comes back None here too and
        _compute_yield_and_dcf_fields's generic "missing_cash_flow_data" fallback fires - same
        reason-string-doesn't-match-real-cause bug class as the RIC recategorization above,
        just for a different root cause. Reuses annual_cash_flow.reason (already populated by
        load_financial_statements.py's own fix once that table is reloaded) instead of a fresh
        live SEC API call - this mixin has no SecEdgarClient instance to reuse a cache from
        (unlike load_financial_statements.py, which calls get_company_facts() during the same
        extraction pass), so a DB lookup against the sibling table's own already-computed
        reason is far cheaper than a second live fetch per symbol. Only overrides the generic
        fallback reason, never a real computed value or a more specific reason
        (negative_free_cash_flow/implausible_dcf_result/registered_investment_company_no_xbrl
        above, which is checked first and returns early if it already matched).
        """
        if valuation_row.get("dcf_fcf_unavailable_reason") != "missing_cash_flow_data":
            return
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT 1
                FROM annual_cash_flow f
                WHERE f.symbol = %s AND f.reason = 'unsupported_currency_no_fx_rate'
                ORDER BY f.fiscal_year DESC
                LIMIT 1
                """,
                (symbol,),
            )
            if cur.fetchone() is not None:
                valuation_row["dcf_fcf_unavailable_reason"] = "unsupported_currency_no_fx_rate"

    # Oil royalty trusts (SIC 6792) file a "Statement of Distributable Income" with no
    # conventional cash-flow-statement concepts to tag at all - same structural shape as a RIC
    # above, just a different, much smaller (6-symbol) entity class with its own SIC code
    # rather than ValueQualityGrowthMetricsLoader's entity_type='other'/sic_code IS NULL RIC
    # gate. Hardcoded rather than a SIC-code DB query since there are only 6 and the SIC-6792
    # universe is exactly this list (live-confirmed via company_info_sec, 2026-09-06) - no
    # false-positive risk from a broader SIC scan.
    _ROYALTY_TRUST_SYMBOLS_FOR_DCF = frozenset({"NRT", "MTR", "CRT", "PBT", "SBR", "SJT"})

    def _recategorize_royalty_trust_dcf_fcf_reason(self, symbol: str, valuation_row: dict[str, Any]) -> None:
        """Overrides a generic dcf_fcf_unavailable_reason with "reit_special_entity" for an oil
        royalty trust. Mutates `valuation_row` in place.

        ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, comprehensive RIC-gap
        scan follow-up): same root fact as _recategorize_ric_dcf_fcf_reason above (no
        conventional cash-flow-statement concepts to tag), already established for
        quality_metrics.fcf_margin/value_metrics.fcf_yield's royalty-trust blocks in
        loaders/helpers/vqg_quality.py and vqg_value.py - this dcf_fcf ground-truth reason
        never checked it either. Live-confirmed all 6 active royalty-trust symbols (NRT, MTR,
        CRT, PBT, SBR, SJT) stuck on the generic "missing_cash_flow_data". Reuses
        "reit_special_entity" (not a new label) - same "Legitimate / not applicable" bucket
        already used for this exact business-model fact throughout the codebase (see
        sec_valuations_yield_dcf.py's own REIT/insurance SIC-code branch, which sits alongside
        this same reason string for the identical entity-type rationale).
        """
        if valuation_row.get("dcf_fcf_unavailable_reason") != "missing_cash_flow_data":
            return
        if symbol in self._ROYALTY_TRUST_SYMBOLS_FOR_DCF:
            valuation_row["dcf_fcf_unavailable_reason"] = "reit_special_entity"

    def _recategorize_capex_never_tagged_dcf_fcf_reason(self, symbol: str, valuation_row: dict[str, Any]) -> None:
        """Overrides a generic dcf_fcf_unavailable_reason with "capex_never_tagged_in_recent_filings"
        for a filer with real, recent operating cash flow but capex never itemized in its 3 most
        recent real fiscal years. Mutates `valuation_row` in place.

        ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, dcf_fcf missing_cash_flow_
        data investigation): this file's own fcf_base/avg_fcf_fallback computation
        (sec_valuations_yield_dcf.py) requires a real (non-None) capex figure - genuinely absent
        for a large slice of filers who simply never re-tag it (live-confirmed CWH/Camping World:
        real, growing OCF every year, real "PaymentsToAcquireProductiveAssets" capex through
        FY2022, then NOTHING under any capex-shaped concept in its companyfacts JSON since -
        not a currency/entity-type structural fact, an ordinary filing-presentation gap). Same
        root cause already given its own specific reason for quality_metrics.fcf_margin/
        value_metrics.fcf_yield via _get_no_recent_capex_symbols() in vqg_quality.py/vqg_value.py
        (live-confirmed 198 of that gate's own affected rows share this exact profile) - this
        dcf_fcf ground-truth reason never checked it either, so 177 of 210 (84%) of the current
        "missing_cash_flow_data" population were this exact, already-labeled-elsewhere case
        instead of a true undiagnosed gap. Small inline query (this mixin has no access to
        ValueQualityGrowthMetricsLoader's cached gate, different class hierarchy - same
        convention as _recategorize_ric_dcf_fcf_reason above). Still "Missing SEC/XBRL data" -
        this doesn't change the headline category, only gives an honest, specific, already-
        established label instead of the uninformative generic one, matching this file's own
        precedent (RIC/currency/royalty-trust recategorizations just above all keep their
        original category too, e.g. RIC's target `registered_investment_company_no_xbrl` is
        also "Missing SEC/XBRL data").
        """
        if valuation_row.get("dcf_fcf_unavailable_reason") != "missing_cash_flow_data":
            return
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                WITH ranked AS (
                    SELECT symbol, capex, operating_cash_flow, fiscal_year, data_unavailable,
                           MAX(fiscal_year) FILTER (WHERE data_unavailable = FALSE)
                               OVER (PARTITION BY symbol) AS max_real_fy
                    FROM annual_cash_flow
                    WHERE symbol = %s AND fiscal_year > 0
                ),
                filtered AS (
                    SELECT * FROM ranked
                    WHERE NOT (data_unavailable AND fiscal_year = max_real_fy + 1)
                ),
                recent AS (
                    SELECT operating_cash_flow, capex,
                           ROW_NUMBER() OVER (ORDER BY fiscal_year DESC) AS rn
                    FROM filtered
                )
                SELECT 1 FROM recent
                WHERE rn <= 3
                GROUP BY 1
                HAVING COUNT(capex) = 0 AND COUNT(operating_cash_flow) > 0 AND COUNT(*) >= 2
                """,
                (symbol,),
            )
            if cur.fetchone() is not None:
                valuation_row["dcf_fcf_unavailable_reason"] = "capex_never_tagged_in_recent_filings"

    def _recategorize_blank_check_dcf_fcf_reason(self, symbol: str, valuation_row: dict[str, Any]) -> None:
        """Overrides a generic dcf_fcf_unavailable_reason with "no_revenue_reported"
        ("Legitimate / not applicable") for a pre-merger SPAC shell. Mutates `valuation_row` in
        place.

        ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, same-day follow-up to
        _recategorize_blank_check_all_valuation_metrics_null_reason and
        _recategorize_capex_never_tagged_dcf_fcf_reason above): a blank-check company has no
        real operating business before its merger - trust-account interest income only, no
        product/service revenue, and typically too few real fiscal years on file yet to clear
        the capex-never-tagged gate's own >=2-real-year floor - so a recently-listed SPAC still
        fell through both of those checks straight to the generic "missing_cash_flow_data".
        Live-confirmed 11 active-universe symbols (XFLH/PTOR/ALDF/GIX/GIW/NWAX/WENC/QETAR/
        QUMSR/FSHP/FSHPR) hitting this exact gap - same root fact and same "no_revenue_reported"
        reason the whole-row all_valuation_metrics_null fallback already uses for this identical
        population, just never checked for dcf_fcf specifically since it's a narrower field-
        level reason than the whole-row fallback (a SPAC with SOME valuation metrics computed
        but dcf_fcf specifically null wouldn't hit that whole-row check at all). Checked last
        (after RIC/currency/royalty-trust/capex) so a more specific real cause above always
        wins - only overrides the exact generic reason this fix targets, same guard discipline
        as every sibling recategorize_*_dcf_fcf_reason function in this file.
        """
        if valuation_row.get("dcf_fcf_unavailable_reason") != "missing_cash_flow_data":
            return
        with DatabaseContext("read") as cur:
            cur.execute(
                "SELECT 1 FROM company_info_sec WHERE symbol = %s AND sic_description = 'Blank Checks'",
                (symbol,),
            )
            if cur.fetchone() is not None:
                valuation_row["dcf_fcf_unavailable_reason"] = "no_revenue_reported"

    def _compute_valuations(
        self,
        symbol: str,
        current_price: float,
        shares_out: float,
        ttm_eps: float | None,
        ttm_revenue: float | None,
        book_value: float | None,
        ocf: float | None,
        capex: float | None,
        prior_year_eps: float | None,
        dividends_paid: float | None,
        total_debt: float | None,
        total_cash: float | None,
        ebitda: float | None,
        avg_fcf_fallback: float | None = None,
        beta: float | None = None,
        risk_free_rate: float | None = None,
        shares_out_from_dual_class_yfinance: bool = False,
        entity_shares_out_for_fcf: float | None = None,
        stock_based_compensation: float | None = None,
        dcf_eps_cagr_pct: float | None = None,
        equity_risk_premium: float | None = None,
        net_borrowing: float | None = None,
        shares_out_from_fpi_yfinance: bool = False,
        common_stock_repurchased: float | None = None,
    ) -> dict[str, Any]:
        """Compute all valuation ratios from SEC data.

        beta/risk_free_rate feed the DCF's CAPM discount rate (see _compute_discount_rate) -
        both default to None (-> DCF_DEFAULT_BETA/DCF_DEFAULT_RISK_FREE_RATE) so existing
        callers/tests that don't supply them keep working; fetch_incremental always passes the
        symbol's real stability_metrics.beta and the live Treasury yield.

        equity_risk_premium: ADDED 2026-08-25 (goal: DCF audit follow-up - dynamic ERP, see
        DCF_MIN_EQUITY_RISK_PREMIUM's docstring on the class for the full rationale). Defaults
        to None -> the static DCF_EQUITY_RISK_PREMIUM, so every existing caller/test is
        unaffected; fetch_incremental passes the live VIX-scaled value from
        _get_equity_risk_premium().

        net_borrowing: ADDED 2026-08-25 (goal: DCF audit follow-up - true FCFE via net
        borrowing, see _get_net_borrowing_for_dcf's docstring for the full rationale). Added
        to fcf_base (DCF only, never fcf_yield - same "DCF gets a smoothed/adjusted figure,
        fcf_yield stays on the latest year's raw current-cash-generation number" split
        avg_fcf_fallback/dcf_eps_cagr_pct already use) when available. Defaults to None -> the
        existing OCF-CapEx-SBC proxy unchanged (implicitly assumes zero net borrowing, same as
        before this fix), so every existing caller/test is unaffected.

        common_stock_repurchased: ADDED 2026-08-26 (goal: full Value pillar re-audit, real
        stock buybacks (annual_cash_flow.common_stock_repurchased, migration 1206) had been
        loaded since 2026-07 but never consumed here). Feeds net_payout_yield (see that
        field's own computation below) - dividends + buybacks, same entity-wide-market-cap
        pairing dividend_yield already uses (same dual-class rationale as
        entity_shares_out_for_fcf below). Defaults to None -> net_payout_yield reduces to
        dividend_yield's own dividends-only figure, so every existing caller/test is
        unaffected.

        shares_out_from_dual_class_yfinance: True only for the narrow 2026-08-22 dual-class
        exception (see _fetch_live_dual_class_shares_outstanding) - shares_out itself came from
        yfinance, not SEC data, so data_source must say so rather than claim "sec_audited" for
        a value that isn't. Every other input here is still 100% SEC-derived either way.

        entity_shares_out_for_fcf: FIXED 2026-08-25 ("margin of safety results look wrong"
        audit). ocf/capex (and therefore fcf/fcf_base below) are always entity-wide - SEC's
        companyfacts API collapses every concept to one value per CIK+period, duplicated
        verbatim onto every dual-class sibling ticker (live-confirmed identical
        operating_cash_flow/capex for TAP and TAP.A across 19 fiscal years). shares_out is
        deliberately CLASS-SPECIFIC for a dual-class sibling ticker (correct for market_cap/
        pe_ratio/pb_ratio/ps_ratio) - pairing that with entity-wide fcf overstated a minority
        class's fcf_yield/DCF intrinsic value by orders of magnitude (TAP.A: fcf_yield 936%,
        margin of safety 99.8%, on a normally-priced stock). Defaults to None so existing
        callers/tests keep computing fcf_yield/the DCF against shares_out exactly as before;
        fetch_incremental passes the entity-wide reported_shares_outstanding when shares_out
        was resolved via the dual-class yfinance path.

        stock_based_compensation: FIXED 2026-08-25 (goal: "finance best practices" methodology
        audit). OCF already adds SBC back as a non-cash expense, but SBC is a real economic
        cost to existing shareholders via future dilution ("Owner Earnings" convention) -
        deducted from both fcf (fcf_yield) and fcf_base (the DCF) below, same treatment as
        _compute_avg_fcf_fallback's own SBC handling (see that method's docstring). Treated as
        0 when None (most filers with no SBC simply don't tag the concept, unlike capex which
        this file's comments document as commonly un-tagged for a still-open interim year).
        Defaults to None so existing callers/tests keep computing fcf exactly as before.

        dcf_eps_cagr_pct: ADDED 2026-08-25 (goal: "finance best practices" methodology audit,
        deferred item - multi-year EPS CAGR). When available (see
        _compute_multi_year_eps_cagr), used as the DCF's growth driver in place of the
        single-year eps_growth_pct computed below from prior_year_eps/ttm_eps - smooths past a
        one-off blip in either endpoint year, same rationale avg_fcf_fallback already applies
        to FCF. PEG's own growth_rate (a few lines above) is untouched - it deliberately stays
        single-year. Defaults to None so existing callers/tests keep computing the DCF off the
        single-year delta exactly as before.

        shares_out_from_fpi_yfinance: True only for the narrow 2026-08-27 foreign-private-
        issuer exception (see _fetch_live_fpi_shares_outstanding_yfinance) - shares_out itself
        came from yfinance, not SEC data, same "data_source must say so" reasoning as
        shares_out_from_dual_class_yfinance above. Every other input here is still 100%
        SEC-derived either way. Not paired with entity_shares_out_for_fcf like the dual-class
        case - an FPI's ADS-basis share count already represents the whole entity (unlike a
        dual-class sibling ticker, which is deliberately one class of several), so ocf/capex's
        entity-wide SEC figures pair correctly with it as-is.
        """
        entity_shares_out = entity_shares_out_for_fcf if entity_shares_out_for_fcf else shares_out
        result: dict[str, Any] = {
            "symbol": symbol,
            "computed_at": date.today().isoformat(),
            "data_unavailable": False,
            "reason": None,
            "data_source": (
                "sec_audited_except_dual_class_shares_yfinance"
                if shares_out_from_dual_class_yfinance
                else "sec_audited_except_fpi_shares_yfinance"
                if shares_out_from_fpi_yfinance
                else "sec_audited"
            ),
            # Price-based metrics
            "current_price": current_price,
            "shares_outstanding": shares_out,
            "market_cap": None,
            # Balance sheet metrics
            "total_debt": total_debt
            if total_debt is not None and abs(total_debt) < MAX_ABSOLUTE_DOLLAR_VALUE
            else None,
            "total_cash": total_cash
            if total_cash is not None and abs(total_cash) < MAX_ABSOLUTE_DOLLAR_VALUE
            else None,
            "enterprise_value": None,
            "ebitda": ebitda if ebitda is not None and abs(ebitda) < MAX_ABSOLUTE_DOLLAR_VALUE else None,
            # Valuation ratios
            "pe_ratio": None,
            "pb_ratio": None,
            "ps_ratio": None,
            "peg_ratio": None,
            "fcf_yield": None,
            "dividend_yield": None,
            "net_payout_yield": None,
            "ev_ebitda": None,
            "ev_revenue": None,
            "forward_pe": None,
            "intrinsic_value_per_share": None,
            "margin_of_safety_pct": None,
            "dcf_fcf_unavailable_reason": None,
        }

        if current_price <= 0:
            result["data_unavailable"] = True
            result["reason"] = "invalid_price"
            return result

        # Market Cap = Price x Shares Outstanding
        if shares_out and shares_out > 0:
            result["market_cap"] = current_price * shares_out
        else:
            result["data_unavailable"] = True
            result["reason"] = "invalid_shares_outstanding"
            return result

        # PE/PB/PS/PEG ratios extracted verbatim to SecValuationRatiosMixin (2026-09-05,
        # file-size ratchet decomposition) - see each method's own docstring for the full
        # per-ratio rationale/history, all preserved there unchanged.
        # ADDED 2026-09-06 (goal: "implausible values" audit, sibling of entity_shares_out_for_fcf
        # above): book_value/ttm_revenue are entity-wide for the same reason ocf/capex are (SEC
        # collapses balance-sheet/income-statement concepts to one value per CIK+period,
        # duplicated onto every dual-class sibling ticker) - pairing them with class-specific
        # shares_out understates book/revenue-per-share by the same ratio fcf_yield was
        # overstated by. Live-confirmed HVT.A pb_ratio=0.11 vs HVT's 1.39 (12.6x) before this
        # fix. entity_shares_out_for_fcf already resolves to shares_out itself when no
        # entity-wide figure is available (see its own docstring/assignment), so this is a
        # strict improvement, never a regression, for every non-dual-class symbol too.
        pb_ps_shares_out = entity_shares_out_for_fcf if entity_shares_out_for_fcf else shares_out
        result["pe_ratio"] = self._compute_pe_ratio(symbol, current_price, ttm_eps)
        result["pb_ratio"] = self._compute_pb_ratio(symbol, current_price, book_value, pb_ps_shares_out)
        result["ps_ratio"] = self._compute_ps_ratio(symbol, current_price, ttm_revenue, pb_ps_shares_out)
        result["peg_ratio"] = self._compute_peg_ratio(symbol, result["pe_ratio"], prior_year_eps, ttm_eps)

        # fcf_yield/dividend_yield/net_payout_yield/enterprise_value/ev_ebitda/ev_revenue/
        # intrinsic_value_per_share/margin_of_safety_pct/dcf_fcf_unavailable_reason extracted
        # verbatim to SecValuationYieldDcfMixin._compute_yield_and_dcf_fields (2026-09-05,
        # file-size ratchet decomposition) - see that method's own docstring for the full
        # rationale/history, all preserved there unchanged.
        result.update(
            self._compute_yield_and_dcf_fields(
                symbol,
                current_price,
                result["market_cap"],
                ttm_eps,
                ttm_revenue,
                ocf,
                capex,
                prior_year_eps,
                dividends_paid,
                total_debt,
                total_cash,
                ebitda,
                avg_fcf_fallback,
                beta,
                risk_free_rate,
                entity_shares_out,
                stock_based_compensation,
                dcf_eps_cagr_pct,
                equity_risk_premium,
                net_borrowing,
                common_stock_repurchased,
            )
        )

        # Forward PE Ratio removed: Requires external analyst data.
        # Removed per GOVERNANCE.md: no external fallbacks for financial metrics.
        # All metrics computed from SEC audited data only.

        # CRITICAL FIX: Validate that at least ONE key valuation metric was computed
        # Prevent marking data as "available" when all key metrics are NULL
        # This was causing value_metrics to have 50%+ NULL pe_ratio even with data_unavailable=FALSE
        key_metrics = [result.get("pe_ratio"), result.get("pb_ratio"), result.get("ps_ratio"), result.get("fcf_yield")]
        if all(m is None for m in key_metrics):
            logger.warning(
                f"[{symbol}] All key valuation metrics (PE, PB, PS, FCF yield) are NULL. "
                f"Mark data as unavailable instead of incomplete."
            )
            result["data_unavailable"] = True
            result["reason"] = "all_valuation_metrics_null"
            self._recategorize_blank_check_all_valuation_metrics_null_reason(symbol, result)

        return result

    def _recategorize_blank_check_all_valuation_metrics_null_reason(self, symbol: str, result: dict[str, Any]) -> None:
        """Overrides the generic "all_valuation_metrics_null" reason with the already-correctly-
        bucketed "no_revenue_reported" ("Legitimate / not applicable") for a pre-merger SPAC
        shell. Mutates `result` in place.

        FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep): a blank-check company
        (SIC 6770) has no real operating business before its merger - trust-account interest
        income only, no product/service revenue - so PE/PB/PS/FCF-yield are all structurally
        undefined, not a data-extraction gap. Live-confirmed via a direct company_info_sec join:
        28 of 61 active symbols hitting "all_valuation_metrics_null" (46%, by far the largest
        single sic_description cluster) are SIC "Blank Checks" - same root fact and same
        "no_revenue_reported" reason `_get_blank_check_symbols()` already uses elsewhere
        (vqg_quality.py's roic_pct/gross_margin/ebitda_margin, vqg_value.py's ps_ratio/ev_revenue)
        for this identical population, just never checked here since this whole-row fallback
        propagates into every value_metrics field at once (pe_ratio/pb_ratio/ps_ratio/peg_ratio/
        ev_ebitda/ev_revenue/market_cap/dividend_yield/fcf_yield/intrinsic_value/margin_of_
        safety/held_percent_institutions - see _build_value_metrics's own "not row_dict or
        row_dict.get('data_unavailable')" early return) before any of those fields' own,
        already-correct per-field gates get a chance to run. This mixin has no access to
        ValueQualityGrowthMetricsLoader's cached _get_blank_check_symbols() (different class
        hierarchy, same reason _recategorize_ric_dcf_fcf_reason above uses its own inline query
        rather than that gate) - a small inline query instead. Guarded the same way as
        _recategorize_ric_dcf_fcf_reason above: only overrides the exact generic reason this
        fix targets, never a real computed value or a different, already-specific reason.
        """
        if result.get("reason") != "all_valuation_metrics_null":
            return
        with DatabaseContext("read") as cur:
            cur.execute(
                "SELECT 1 FROM company_info_sec WHERE symbol = %s AND sic_description = 'Blank Checks'",
                (symbol,),
            )
            if cur.fetchone() is not None:
                result["reason"] = "no_revenue_reported"
                return
        # FIXED 2026-09-06 (same-day follow-up): a small number of pre-merger SPAC shells are
        # SEC-classified under their intended TARGET industry's SIC code, not 6770 "Blank
        # Checks" - the sic_description check above structurally can't catch these. Individually
        # verified (not a name-pattern heuristic - matches this codebase's established
        # discipline for exactly this kind of narrow exception, see sec_dual_class_eps.py's
        # _VERIFIED_BRAND_NAME_ALIASES): both have zero revenue reported in every fiscal year on
        # file (annual_income_statement), consistent with a real pre-merger shell despite the
        # off-taxonomy SIC code. Churchill Capital is a well-known serial SPAC sponsor (SIC 3569
        # here); Columbus Circle Capital Corp II is SIC 7373.
        if symbol in ("CCXI", "CMII"):
            result["reason"] = "no_revenue_reported"

    # FIXED 2026-08-20 (goal: finance-accuracy audit, part 2): yfinance_snapshot (the table
    # the cross-check below reads) has had no live writer since Session 275 and was frozen
    # at 2026-07-12 - live-confirmed via direct query (39 days stale as of this fix, and
    # covering 4,522/5,210 of the active universe). For DOMESTIC filers this doesn't matter
    # much: the company_info_sec cross-check + MAX_PLAUSIBLE_SHARES_OUTSTANDING ceiling
    # above are both independently sourced and fresh, so yfinance is redundant defense-in-
    # depth there and stays on the frozen table (no new API load added for the ~78% of the
    # universe that doesn't need it). For FOREIGN PRIVATE ISSUERS specifically, this check
    # is NOT redundant - company_info_sec is skipped for FPIs (see is_foreign_private_issuer
    # branch above: it's SEC-sourced too, so it carries the identical home-market-vs-ADS
    # unit-mismatch risk as the primary data, per the TSM $10.7T incident this file's history
    # already documents) - yfinance is the only independent, ADS/USD-basis-quoted source
    # available for this specific class, and it was silently running on 39-day-old data.
    # Fetches live (shared circuit breaker, same infra as utils/external/yfinance_financials.py)
    # only for the ~1,154 FPI symbols where this is the primary defense, not the full universe.


if __name__ == "__main__":
    sys.exit(run_loader(SecValuationsLoader, description="Compute valuations from SEC audited data"))
