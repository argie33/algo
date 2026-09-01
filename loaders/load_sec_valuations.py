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
}


class SecValuationsLoader(OptimalLoader):
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

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:  # noqa: C901 -- pre-existing complexity debt, not introduced by this change; CI ruff-gate cleanup pass 2026-08-11
        """Compute SEC-derived valuations for one symbol.

        Returns:
            List with single valuation dict or data_unavailable marker
        """
        try:
            # Fetch latest financial data for symbol
            with DatabaseContext("read") as cur:
                # Get income statement data from most recent annual filing
                # CRITICAL: Use NULL checks instead of COALESCE(col, 0) to detect missing financial data
                # Defaulting to 0 for revenue/EPS would cause wrong valuations (zero division, phantom metrics)
                # FIXED 2026-08-20 (goal: finance-accuracy audit): the `data_unavailable = FALSE`
                # filter removed below (see old NOTE) was dropped to stop excluding legitimate rows
                # where the flag is simply unset - but data_unavailable=TRUE with
                # reason='incomplete_sec_filing_income' means the filer's income-statement section
                # is itself incomplete/inconsistent, not merely unset, and its non-NULL
                # revenue/net_income/EPS values are known-unreliable, not just missing. Live-
                # confirmed 113 universe symbols with a valid current_price currently computing
                # pe_ratio/ps_ratio in the hundreds (e.g. ASBP pe_ratio=1649.85, AVLN=1535.70,
                # BOBS=922.50, ALMR=808.37) purely from this. `data_unavailable IS NOT TRUE` (not
                # `= FALSE`) keeps admitting NULL-flag rows exactly as before while excluding only
                # the confirmed-bad ones, falling back to the next real fiscal year within the
                # LIMIT 2 window (or the existing no_income_statement/*_null unavailable paths)
                # instead of a fabricated ratio.
                # FIXED: plain `ORDER BY fiscal_year DESC` picked the latest fiscal year even when
                # it's a partial/estimate-stage filing with NULL revenue AND NULL EPS, while an
                # older year has real data - same "latest year is empty" bug class as the FCF fix
                # in load_value_quality_growth_metrics.py. Live-confirmed: MC (Moelis), CLSK
                # (CleanSpark), FRD (Friedman Industries) all have real revenue/net_income one
                # fiscal year back but were failing "income_statement_revenue_and_eps_null" on the
                # latest year alone. Prioritizing rows with revenue or EPS present, then by
                # fiscal_year DESC, still returns two genuinely consecutive fiscal years for the
                # prior_year_eps growth-rate calc below (whichever two are most recent AND usable).
                # ADDED 2026-08-19 (migration 1211, goal: "no SEC data"/missing factor inputs
                # audit): is_foreign_private_issuer folded in via LEFT JOIN (not a separate
                # round-trip) so it's available on income_rows[0] without disturbing the call
                # sequence every other query in this method relies on. See the shares_out tier
                # gating below for the full story - foreign private issuers (20-F/40-F/6-K)
                # report revenue/net_income/EPS/share-count figures in their home-market
                # security's units, which for ADR-structured filers (e.g. TSM, 1 ADS = 5
                # ordinary shares) differ from the US-registered security current_price is
                # quoted in.
                cur.execute(
                    """
                    SELECT
                        ais.fiscal_year,
                        ais.revenue,
                        ais.net_income,
                        ais.earnings_per_share,
                        ais.operating_income,
                        ais.pretax_income,
                        ais.depreciation_expense,
                        ais.amortization_expense,
                        ais.shares_outstanding_basic,
                        ais.income_tax_expense,
                        cis.is_foreign_private_issuer,
                        cis.sic_code
                    FROM annual_income_statement ais
                    LEFT JOIN company_info_sec cis ON cis.symbol = ais.symbol
                    WHERE ais.symbol = %s AND ais.data_unavailable IS NOT TRUE
                    ORDER BY (CASE WHEN ais.revenue IS NOT NULL OR ais.earnings_per_share IS NOT NULL OR ais.net_income IS NOT NULL THEN 0 ELSE 1 END), ais.fiscal_year DESC
                    LIMIT 6
                    """,
                    (symbol,),
                )
                # LIMIT raised from 2 to 6 on 2026-08-25 (goal: "finance best practices"
                # methodology audit, deferred item - multi-year EPS CAGR for the DCF): purely
                # additive - every fallback below still only ever reads income_rows[0]/[1],
                # exactly as before. Rows 2-5 exist solely to give
                # _compute_multi_year_eps_cagr below a few more fiscal years of EPS history
                # without a second query - same tier/fiscal_year-DESC ordering as before, so
                # income_rows[0]/[1]'s selection is unchanged.
                income_rows = cur.fetchall()
                if not income_rows:
                    return [self._unavailable_marker(symbol, "no_income_statement")]

                # len() guard: pre-existing tests mock income_rows as plain 10-element
                # tuples (this method's own pre-2026-08-19 shape) - default to False
                # (unchanged prior behavior) rather than requiring every one of those
                # fixtures to be updated for a column real production queries always return.
                is_foreign_private_issuer = bool(income_rows[0][10]) if len(income_rows[0]) > 10 else False
                # FIXED 2026-08-22 (goal session: "Missing SEC/XBRL data" coverage audit):
                # depository institutions (banks) never tag a "CapitalExpenditures" XBRL
                # concept, ever, in any fiscal year - live-confirmed via JPM, BAC, MS, WFC,
                # PNC's real companyfacts JSON (capex NULL across every year 2007-2026, not
                # just the current interim year). See the capex-fallback comment below and
                # in sec_base.py's free_cash_flow computation for the full rationale.
                sic_code = income_rows[0][11] if len(income_rows[0]) > 11 else None

                (
                    ttm_fiscal_year,
                    ttm_revenue,
                    _ttm_net_income,
                    ttm_eps_basic,
                    operating_income,
                    pretax_income,
                    depreciation_expense,
                    amortization_expense,
                    reported_shares_outstanding,
                    income_tax_expense,
                ) = income_rows[0][:10]

                # FIXED 2026-08-18 (goal: "no SEC data" audit): the ORDER BY above ranks a row
                # tier-0 if ANY of revenue/EPS/net_income is present - not specifically revenue -
                # so a filer whose latest fiscal year has a real net_income but a not-yet-tagged
                # revenue figure (common for a just-filed/preliminary period) wins the tiebreak
                # over an older row that has real, complete revenue. ttm_revenue then comes back
                # None even though a usable figure exists one row back, silently killing
                # ev_revenue/ps_ratio. Live-confirmed CRAI (CRA International, ~$750M/year real
                # revenue): FY2026 row has net_income=$54.8M but revenue=NULL and won tier 0,
                # masking FY2025's real revenue=$751.58M sitting in income_rows[1]. A universe-
                # wide scan found 723 symbols where the anchor row has this exact NULL-revenue-
                # but-real-EPS-or-net-income shape. Only income_rows[1] (already fetched, no
                # extra query) is checked - same small-window "same-year-substitute" fallback
                # already used elsewhere in this codebase (e.g. roic_pct's long_term_debt
                # fallback), not an unbounded historical search.
                if ttm_revenue is None and len(income_rows) > 1 and income_rows[1][1] is not None:
                    ttm_revenue = income_rows[1][1]

                # FIXED 2026-08-18: earnings_per_share suffers the identical "premature fiscal
                # year stub" gap as revenue just above - same anchor row, same root cause (a
                # filer whose latest fiscal year has real net_income but EPS not yet tagged).
                # Live-confirmed HG (Hamilton Insurance Group): FY2026 row has real
                # net_income=$217.032M but earnings_per_share=NULL, while FY2025 one row back
                # has a real earnings_per_share=$5.75 - pe_ratio/peg_ratio came back "SEC data
                # not available" even though growth_metrics elsewhere in the pipeline computes
                # EPS growth fine from the same underlying annual_income_statement data.
                # Track which fiscal year actually supplied ttm_eps_basic - prior_year_eps below
                # must come from a year OLDER than that one, never the same year twice (see the
                # PEG double-counting bug this exact shape caused once already, warned about in
                # the comment right below).
                ttm_eps_fiscal_year = ttm_fiscal_year
                eps_substituted_from_row1 = False
                if ttm_eps_basic is None and len(income_rows) > 1 and income_rows[1][3] is not None:
                    ttm_eps_basic = income_rows[1][3]
                    ttm_eps_fiscal_year = income_rows[1][0]
                    eps_substituted_from_row1 = True

                # FIXED 2026-08-18: operating_income/pretax_income suffer the identical anchor-row
                # stub gap as revenue and earnings_per_share above. Live-confirmed HG (Hamilton
                # Insurance Group): FY2026 (anchor) has BOTH operating_income=NULL and
                # pretax_income=NULL (neither tagged yet in the premature filing), while FY2025
                # one row back has a real pretax_income=$824.905M. Neither of the two existing
                # operating_income fallbacks just below can help here - both depend on THIS row's
                # own pretax_income/income_tax_expense, which are equally missing. This was
                # previously mis-diagnosed (see missing_factor_inputs_audit_20260818 memory) as
                # "not an independent bug, a downstream cascade of genuine per-fiscal-year gaps" -
                # it's actually the same anchor-row-timing bug already fixed for revenue/EPS above,
                # just not yet recognized as such. Substitute the WHOLE income_rows[1] set together
                # (operating_income, pretax_income, D&A) rather than mixing fields from two
                # different fiscal years, which would produce an internally inconsistent EBITDA.
                # Only fires when BOTH anchor-row income-statement figures are missing - a filer
                # with a real anchor-row pretax_income but genuinely no operating_income tag (the
                # normal financial-services case the fallback below already handles) is untouched.
                if operating_income is None and pretax_income is None and len(income_rows) > 1:
                    operating_income = income_rows[1][4]
                    pretax_income = income_rows[1][5]
                    depreciation_expense = income_rows[1][6]
                    amortization_expense = income_rows[1][7]

                # FIXED 2026-08-06: Financial services companies (banks, insurance, investment firms)
                # don't report operating_income - they report pretax_income instead. Use pretax_income
                # as fallback for EBITDA calculation in these cases. This recovers ~22% of missing
                # operating_income in the universe (e.g. JPM, BAC, PNC all have pretax_income but no
                # operating_income). Live-confirmed: JPMorgan FY2024 pretax_income=75.08B, uses this
                # fallback to compute EBITDA for EV/EBITDA ratio.
                if operating_income is None and pretax_income is not None:
                    operating_income = pretax_income
                    logger.debug(
                        f"[{symbol}] Using pretax_income as operating_income fallback (financial services company)"
                    )
                elif operating_income is None and income_tax_expense is not None and _ttm_net_income is not None:
                    # Fallback #2: Compute operating_income from net_income + taxes if available
                    # Some insurance/financial companies report net_income and taxes but not pretax_income
                    try:
                        computed_oi = _ttm_net_income + income_tax_expense
                        if computed_oi > 0:
                            operating_income = computed_oi
                            logger.debug(
                                f"[{symbol}] Computed operating_income from net_income + taxes (insurance company fallback)"
                            )
                    except (TypeError, ValueError):
                        pass  # If computation fails, leave operating_income=None
                # PEG's growth-rate leg needs a genuinely prior-year EPS, not the same TTM
                # value used twice - GOVERNANCE: this used to set `latest_eps = ttm_eps_basic`
                # (comment literally said "Use same EPS for both TTM and latest"), which made
                # _compute_valuations()'s growth_rate = (ttm_eps - latest_eps)/abs(latest_eps)
                # always exactly 0 for every symbol, so peg_ratio silently never populated
                # anywhere in the system with no marker flagging PEG specifically as broken.
                # A missing second fiscal year (new filer, gap) leaves it None, which
                # _compute_valuations already handles by leaving peg_ratio NULL.
                if len(income_rows) > 1 and not eps_substituted_from_row1:
                    prior_year_eps = income_rows[1][3]  # Index 3 = earnings_per_share
                elif eps_substituted_from_row1:
                    # income_rows[1] was itself consumed above as the ttm_eps substitute (the
                    # premature-stub case) - re-fetch a genuinely older year rather than reuse it.
                    cur.execute(
                        """
                        SELECT earnings_per_share FROM annual_income_statement
                        WHERE symbol = %s AND fiscal_year < %s AND earnings_per_share IS NOT NULL
                        ORDER BY fiscal_year DESC LIMIT 1
                        """,
                        (symbol, ttm_eps_fiscal_year),
                    )
                    older_eps_row = cur.fetchone()
                    prior_year_eps = older_eps_row[0] if older_eps_row else None
                else:
                    prior_year_eps = None

                # ADDED 2026-08-25 (goal: "finance best practices" methodology audit,
                # deferred item - "multi-year EPS CAGR instead of single-year growth"): the
                # DCF's growth driver (eps_growth_pct in _compute_valuations below) was a bare
                # TTM-vs-prior-year EPS delta - noisy for any symbol whose single prior year had
                # a one-off blip (impairment, tax item, etc), the same "one bad year distorts
                # the whole figure" problem already solved for FCF via the 3-year
                # avg_fcf_fallback. Uses the same income_rows list (now fetched with LIMIT 6, see
                # above) rather than PEG's prior_year_eps/ttm_eps - PEG deliberately stays
                # single-year (see peg_ratio's own comment; it's a conventionally
                # single-year-forward metric, changing it would be a different, unrequested
                # methodology change).
                dcf_eps_cagr_pct = self._compute_multi_year_eps_cagr(income_rows)

                # MOVED 2026-08-19 (goal session continuation - "which factor inputs are
                # missing the most" audit): total_debt/total_cash/ebitda used to live after the
                # shares_outstanding and current_price gates below, even though none of the
                # three actually depend on shares outstanding or price - they're pure balance-
                # sheet/income-statement dollar figures. That put them behind an early `return`
                # they had no real dependency on: any symbol failing the shares_outstanding gate
                # (771 active symbols, overwhelmingly foreign private issuers - see
                # load_company_info_sec.py's domestic-forms-only guard) or the price gate lost
                # total_debt/total_cash/ebitda too, purely as a control-flow accident, not a real
                # data gap. Computed here, before every gate below, so
                # load_value_quality_growth_metrics.py's `SELECT total_debt, total_cash, ebitda
                # FROM sec_valuations` (which reads these three columns directly, with no
                # data_unavailable=FALSE filter) gets real values via the unavailable-marker path
                # too, not just the full-success path. cash_per_share is unaffected - it still
                # needs shares_outstanding and correctly stays gated.
                # FIXED 2026-08-20 (goal: finance-accuracy audit): added data_unavailable IS NOT
                # TRUE - same bug class as the income-statement query above. reason=
                # 'incomplete_sec_filing_balance' rows can carry a non-NULL but unreliable
                # cash_and_equivalents; live-confirmed 253 universe symbols with a valid
                # current_price were picking one up as "the" cash figure.
                cur.execute(
                    """
                    SELECT cash_and_equivalents
                    FROM annual_balance_sheet
                    WHERE symbol = %s AND fiscal_year IS NOT NULL AND data_unavailable IS NOT TRUE
                    ORDER BY (CASE WHEN cash_and_equivalents IS NOT NULL THEN 0 ELSE 1 END), fiscal_year DESC
                    LIMIT 1
                    """,
                    (symbol,),
                )
                cash_row2 = cur.fetchone()
                total_cash = cash_row2[0] if cash_row2 else None

                # Debt = long_term_debt + short_term_debt + operating/finance lease liabilities
                # (S&P/Moody's "adjusted debt" convention; NOT total_liabilities, which
                # overstates debt ~3x by including accounts payable/deferred revenue/pensions -
                # see git history for the AAPL/MSFT/GOOGL/F live-confirmed fix). NULL only when
                # ALL FOUR components are absent across every fiscal year on file; a fiscal year
                # whose components sum to a real nonzero value is preferred over one that's
                # merely non-NULL (a lone real `short_term_debt=0` on an in-progress year must
                # not outrank a fuller prior year), which in turn is preferred over a bare
                # `ORDER BY fiscal_year DESC` for genuinely zero-debt companies.
                #
                # TIER 0 ADDED 2026-09-01 (goal-mode factor-usage review, category-leaders spot
                # check): the "any nonzero sum" tier above couldn't distinguish a COMPLETE year
                # from a PARTIAL one - a stray small short_term_debt/lease-liability figure on an
                # in-progress fiscal year (real, but missing the dominant long_term_debt line
                # because a mid-year 10-Q simply doesn't re-disclose the full debt schedule the
                # way an annual 10-K's footnotes do) counted as "nonzero" exactly like a genuinely
                # complete prior year - and being MORE RECENT, won the tiebreak outright. Live-
                # confirmed via COF (Capital One): FY2026 has short_term_debt=$1.626B alone
                # (long_term_debt NULL) while FY2025 has the real, complete long_term_debt=
                # $49.913B - old logic picked FY2026's $1.626B "total debt" for one of the
                # largest, most leveraged banks in the market. Same root cause as JCAP's
                # near-zero debt_to_equity found the same session (a $3.891M operating-lease-only
                # FY2026 figure beating FY2025's real $1.754B long_term_debt). Universe-wide sweep:
                # 477 symbols (incl. GE, GS, TD, COF, TMUS, DUK, SO, PCG) had their most recent
                # nonzero year measure under 5% of their own historical max debt-sum - not a
                # financials-only issue, a general "incomplete current year" issue. Fix: a year
                # where long_term_debt ITSELF is present (the single most information-dense,
                # hardest-to-accidentally-populate component - no filing accidentally reports a
                # multi-billion-dollar long-term debt figure) now wins over any year that only has
                # the smaller components, tiebroken by fiscal_year DESC among long_term_debt-real
                # years so the freshest COMPLETE year still wins. Falls through unchanged to the
                # existing tiers for companies that never report long_term_debt at all (genuinely
                # short-term-debt-only or lease-only capital structures aren't penalized - they
                # simply never populate tier 0, same as before this fix).
                cur.execute(
                    """
                    SELECT
                        long_term_debt,
                        short_term_debt,
                        operating_lease_liability,
                        finance_lease_liability
                    FROM annual_balance_sheet
                    WHERE symbol = %s AND fiscal_year IS NOT NULL AND data_unavailable IS NOT TRUE
                    ORDER BY (CASE
                                WHEN long_term_debt IS NOT NULL
                                THEN 0
                                WHEN COALESCE(long_term_debt, 0) + COALESCE(short_term_debt, 0)
                                     + COALESCE(operating_lease_liability, 0)
                                     + COALESCE(finance_lease_liability, 0) != 0
                                THEN 1
                                WHEN long_term_debt IS NOT NULL OR short_term_debt IS NOT NULL
                                     OR operating_lease_liability IS NOT NULL
                                     OR finance_lease_liability IS NOT NULL
                                THEN 2
                                ELSE 3
                              END), fiscal_year DESC
                    LIMIT 1
                    """,
                    (symbol,),
                )
                debt_row = cur.fetchone()
                if debt_row:
                    debt_components = debt_row
                    if all(c is None for c in debt_components):
                        total_debt = None
                    else:
                        total_debt = sum(c or 0 for c in debt_components)
                else:
                    total_debt = None

                # EBITDA = Operating Income + Depreciation + Amortization (Session 398)
                ebitda = None
                oi = safe_float(operating_income, f"{symbol}.operating_income", allow_none=True)
                if oi is not None:
                    dep_exp = safe_float(depreciation_expense, f"{symbol}.depreciation_expense", allow_none=True)
                    amort_exp = safe_float(amortization_expense, f"{symbol}.amortization_expense", allow_none=True)
                    ebitda_val = oi
                    if dep_exp:
                        ebitda_val += dep_exp
                    if amort_exp:
                        ebitda_val += amort_exp
                    ebitda = ebitda_val

                # Same overflow guard _compute_valuations applies to these three below (see
                # MAX_ABSOLUTE_DOLLAR_VALUE's module docstring - foreign ADR filers reporting
                # balance-sheet figures in local currency without USD conversion, live-crashed
                # NumericValueOutOfRange on BBAR/BCH/BMA/BSAC/HDB/HMC) - applied here too since
                # the unavailable-marker return paths below use these values directly, bypassing
                # _compute_valuations' own guard entirely.
                if total_debt is not None and abs(total_debt) >= MAX_ABSOLUTE_DOLLAR_VALUE:
                    total_debt = None
                if total_cash is not None and abs(total_cash) >= MAX_ABSOLUTE_DOLLAR_VALUE:
                    total_cash = None
                if ebitda is not None and abs(ebitda) >= MAX_ABSOLUTE_DOLLAR_VALUE:
                    ebitda = None

                # Validate critical fields are not NULL (fail-fast if SEC data incomplete)
                # Allow revenue-only companies: can compute PS ratio even without EPS. Also
                # allow net_income-only companies (live-confirmed: PFLT/PennantPark - a BDC
                # reporting NetInvestmentIncome instead of Revenue/EPS under an entirely
                # separate XBRL taxonomy; TRAX/FRNM - pre-revenue biotechs with real
                # net_income but no EPS tagged) to proceed: _compute_valuations already
                # handles ttm_revenue=None (skips PS) and ttm_eps=None (skips PE)
                # gracefully per-field, and PB/EV/FCF-yield don't depend on either at all -
                # the only real requirement is SOME income-statement signal to work with.
                if ttm_revenue is None and ttm_eps_basic is None and _ttm_net_income is None:
                    return [
                        self._unavailable_marker(
                            symbol,
                            "income_statement_revenue_and_eps_null",
                            total_debt=total_debt,
                            total_cash=total_cash,
                            ebitda=ebitda,
                        )
                    ]

                # Prefer the real, officially-reported weighted-average basic share count
                # (SEC XBRL WeightedAverageNumberOfSharesOutstandingBasic, migration 1171)
                # over the derived net_income/eps proxy below - EPS is reported rounded to
                # 2 decimals, so back-computing shares from it loses real precision (material
                # for large-caps with billions of shares). FIXED 2026-07-28: this concept was
                # fetched from SEC every run but silently discarded (see sec_statements.py),
                # so the derived proxy ran unconditionally despite this docstring's own claim
                # (line 11 above) that the real concept was already the source.
                # Apply the same plausibility floor as the fallback tiers below (see
                # MIN_PLAUSIBLE_SHARES_OUTSTANDING) - live-confirmed AIAI reports a real,
                # non-NULL shares_outstanding_basic of 1000 for its latest fiscal year (a
                # pre-float/shell-stage founder-share figure, not a data-fetch bug), which
                # produced a nonsensical ~$4,900 market cap when trusted directly. The
                # fallback tiers already guard against this class of bad data; the primary
                # reported value needs the same guard.
                # FIXED 2026-08-19 (migration 1211, goal: "no SEC data"/missing factor inputs
                # audit): live-confirmed TSM (Taiwan Semiconductor, 1 ADS = 5 ordinary
                # shares) showed market_cap=$10.7 TRILLION and pe_ratio=304 (both ~5x too
                # high, independently cross-checked against yfinance's live sharesOutstanding/
                # marketCap/trailingPE) because tiers 1-3/5 below all read
                # shares_outstanding_basic/diluted or derive a share count from net_income/EPS
                # - for a foreign private issuer these are real, correctly-filed figures, just
                # on the filer's home-market ordinary-share basis, not the ADS-equivalent basis
                # current_price is quoted in. Only tiers 4 (company_info_sec) and 6
                # (shares_outstanding_dei) are independently guarded to domestic forms only
                # (see load_company_info_sec.py and utils/external/sec_statements.py
                # respectively) - skip straight to those for a foreign private issuer rather
                # than risk the same unit mismatch in a tier nobody had separately audited.
                shares_out = None
                # Default False so this is always defined for the FPI-agnostic tiers
                # below (dei cover-page, diluted) even when is_foreign_private_issuer is
                # True and the block below never executes to compute a real value.
                has_dual_class_sibling = False
                if not is_foreign_private_issuer:
                    # FIXED 2026-08-21 (goal session - "is BRK.B handled the right way"
                    # end-to-end re-check): every tier in this block reads
                    # annual_income_statement.shares_outstanding_basic/diluted (directly, or
                    # derives from net_income/eps_basic which is equally class-specific) -
                    # all four are vulnerable to the same dual-class ambiguity, not just the
                    # net_income/eps proxy this was first found on. Live-confirmed: BRK.A's
                    # 2021-2026 shares_outstanding_basic is correctly NULL (both prior fixes
                    # this session), but the "older fiscal year" tier below reaches all the
                    # way back to a real, pre-existing 2014 row (shares_outstanding_basic=
                    # 1,643,456 - written years before any fix here existed, never
                    # retroactively touched since those fixes only guard NEW writes) and
                    # produced the identical wrong value for both BRK.A and BRK.B again.
                    # Compute the sibling check once, up front, and gate every tier on it -
                    # not just the one where this was first caught.
                    base_root = symbol.split(".")[0]
                    cur.execute(
                        "SELECT 1 FROM stock_symbols WHERE active = true AND symbol != %s "
                        "AND (symbol = %s OR symbol LIKE %s) LIMIT 1",
                        (symbol, base_root, f"{base_root}.%"),
                    )
                    has_dual_class_sibling = cur.fetchone() is not None
                    if not has_dual_class_sibling:
                        # See DUAL_CLASS_NO_SEPARATOR_ROOTS' own module-level comment for the
                        # curated-list rationale (DGICA/DGICB etc. - no "." separator, so the
                        # dot-split check above never fires for them).
                        no_sep_root = next(
                            (
                                r
                                for r in DUAL_CLASS_NO_SEPARATOR_ROOTS
                                if symbol.startswith(r) and len(symbol) == len(r) + 1
                            ),
                            None,
                        )
                        if no_sep_root:
                            cur.execute(
                                "SELECT 1 FROM stock_symbols WHERE active = true AND symbol != %s "
                                "AND symbol LIKE %s AND length(symbol) = %s LIMIT 1",
                                (symbol, f"{no_sep_root}%", len(symbol)),
                            )
                            has_dual_class_sibling = cur.fetchone() is not None
                    if (
                        not has_dual_class_sibling
                        and reported_shares_outstanding
                        and self.MIN_PLAUSIBLE_SHARES_OUTSTANDING
                        < reported_shares_outstanding
                        < self.MAX_PLAUSIBLE_SHARES_OUTSTANDING
                    ):
                        shares_out = float(reported_shares_outstanding)
                        logger.debug(f"[{symbol}] Using reported shares_outstanding_basic: {shares_out:,.0f}")

                        # FIXED 2026-08-31 (goal: data-coverage sweep, HBIO follow-up to
                        # sec_valuations_fpi_shares_out_missing_gate_fixed_20260831): the query
                        # above that produced `reported_shares_outstanding` orders by "has
                        # revenue/EPS/net_income" FIRST, fiscal_year DESC second - so
                        # `income_rows[0]` (and the shares_outstanding_basic riding along with
                        # it) is tied to whichever fiscal year has usable P&L data, not
                        # necessarily the most recent fiscal year on file. A real stock split
                        # correctly updates the LATEST year's share count immediately, but if
                        # that latest year's P&L hasn't posted yet (a fresh partial filing),
                        # this tier silently uses an OLDER, pre-split share count instead - the
                        # same "stale share count" failure mode already fixed elsewhere in this
                        # session (FUBO/GPUS/IHRT), just via a different mechanism (row
                        # selection, not concept staleness). Live-confirmed via HBIO (Harvard
                        # Bioscience): its FY2026 row has shares_outstanding_basic=4,552,305
                        # (matching real ~4.55M shares) but no revenue yet, so the query above
                        # picked FY2025's row instead - shares_outstanding_basic=44,391,000 (a
                        # real, ~10x-larger PRE-split figure) - producing market_cap=$352.0M vs
                        # real ~$34.4M. FY2026's row doesn't even appear in `income_rows` (LIMIT
                        # 6, already exhausted by 6 revenue-bearing years) so this can't be
                        # solved by scanning already-fetched data - one bounded extra query for
                        # the single most recent fiscal year with ANY usable share count (not
                        # gated on revenue). Only overrides when it's both a later fiscal_year
                        # than the row already selected AND meaningfully different (>=1.3x, same
                        # threshold as the reverse-split override in load_company_info_sec.py),
                        # so ordinary dilution/buybacks between two adjacent years don't trigger
                        # it.
                        cur.execute(
                            """
                            SELECT shares_outstanding_basic, fiscal_year FROM annual_income_statement
                            WHERE symbol = %s AND shares_outstanding_basic > %s AND shares_outstanding_basic < %s
                            ORDER BY fiscal_year DESC LIMIT 1
                            """,
                            (symbol, self.MIN_PLAUSIBLE_SHARES_OUTSTANDING, self.MAX_PLAUSIBLE_SHARES_OUTSTANDING),
                        )
                        freshest_row = cur.fetchone()
                        if freshest_row and freshest_row[0] and freshest_row[1] and freshest_row[1] > ttm_fiscal_year:
                            freshest_shares = float(freshest_row[0])
                            larger, smaller = max(shares_out, freshest_shares), min(shares_out, freshest_shares)
                            if smaller > 0 and larger / smaller >= 1.3:
                                logger.warning(
                                    f"[{symbol}] shares_outstanding_basic from FY{ttm_fiscal_year} "
                                    f"(the P&L-bearing row)={shares_out:,.0f} is staler than FY{freshest_row[1]}'s "
                                    f"{freshest_shares:,.0f} (ratio {larger / smaller:.1f}x) - likely a stock "
                                    "split/major share event between the two years; using the more recent count"
                                )
                                shares_out = freshest_shares

                    # Fallback: compute shares outstanding from SEC financial data: shares = net_income / eps.
                    # If both net_income and eps are available, we can compute shares directly from SEC audited data.
                    # This mathematically reconstructs whatever share count the filer itself used
                    # to compute EPS - if that was the same implausible pre-float figure rejected
                    # above (live-confirmed: AIAI's derived value is ~1000, matching its rejected
                    # reported shares_outstanding_basic exactly), the same floor must apply here too.
                    #
                    # FIXED 2026-08-21 (goal session - "is BRK.B handled the right way"
                    # end-to-end re-check, same bug class as the dual-class shares_outstanding
                    # fixes in load_company_info_sec.py/load_financial_statements.py): net_income
                    # is a single whole-company figure shared by every share class, but eps_basic
                    # is class-specific (BRK.A's EPS is ~1,500x BRK.B's) - this proxy silently
                    # reconstructs whichever class's EPS our extraction happened to expose,
                    # producing the SAME wrong shares_out for every sibling class regardless of
                    # which ticker asked. Gated on has_dual_class_sibling (computed once, above,
                    # alongside every other tier in this block).
                    # FIXED 2026-08-31 (goal: data-coverage sweep, UROY follow-up to
                    # sec_valuations_pl_row_coupled_stale_shares_hbio_fixed_20260831): this
                    # "shares = net_income / eps" identity only holds when both operands come
                    # from the SAME fiscal year - `ttm_eps_basic` can be silently substituted
                    # from `income_rows[1]` (a DIFFERENT, older fiscal year) by the
                    # `eps_substituted_from_row1` fallback above (added 2026-08-18 for a
                    # different purpose - recovering pe_ratio/PEG when the anchor row's own EPS
                    # isn't tagged yet), while `_ttm_net_income` stays the anchor row's own
                    # value. Combining the two produces a mathematically meaningless number, not
                    # a real share count. Live-confirmed via UROY (Uranium Royalty Corp): anchor
                    # FY2026 has net_income=$40.249M but EPS not yet tagged, so EPS was
                    # substituted from FY2025's -$0.04 - derived_shares_out =
                    # 40,249,000/0.04 = 1,006,225,000 (a fabricated number, not UROY's real
                    # ~381M shares per company_info_sec) - producing market_cap=$4.28B vs real
                    # ~$1.6-1.67B. The PEG calculation elsewhere in this method already guards
                    # against this exact cross-year mismatch via `ttm_eps_fiscal_year` - this
                    # tier never had the same guard. Gated the same way: skip when EPS came from
                    # a different fiscal year than net_income, same discipline as the
                    # dual-class-sibling gate immediately below.
                    if (
                        not has_dual_class_sibling
                        and not eps_substituted_from_row1
                        and not shares_out
                        and ttm_eps_basic
                        and ttm_eps_basic != 0
                        and _ttm_net_income
                        and _ttm_net_income != 0
                    ):
                        try:
                            # Shares = Net Income / EPS (mathematical identity from SEC financial statements)
                            derived_shares_out = abs(float(_ttm_net_income) / float(ttm_eps_basic))
                            if (
                                self.MIN_PLAUSIBLE_SHARES_OUTSTANDING
                                < derived_shares_out
                                < self.MAX_PLAUSIBLE_SHARES_OUTSTANDING
                            ):
                                shares_out = derived_shares_out
                                logger.debug(
                                    f"[{symbol}] Computed shares_outstanding from income_statement: {shares_out:,.0f}"
                                )
                        except (ValueError, ZeroDivisionError):
                            pass  # If computation fails, shares_out stays None and we fail below

                    # Fallback: the LIMIT 2 rows above are the two most recent fiscal years, but
                    # the most recent one is often a partial/estimate-stage filing with NULL
                    # shares_outstanding_basic even though an older year has the real reported
                    # value (same "latest year is empty" issue fixed for free_cash_flow in
                    # load_value_quality_growth_metrics.py - live-confirmed for GPRO/JOUT/CWH/etc,
                    # where FY2026 is NULL but FY2025 has a real share count). Search all fiscal
                    # years, not just the two most recent, before falling back to company_info_sec.
                    if not shares_out and not has_dual_class_sibling:
                        cur.execute(
                            """
                            SELECT shares_outstanding_basic FROM annual_income_statement
                            WHERE symbol = %s AND shares_outstanding_basic > %s AND shares_outstanding_basic < %s
                            ORDER BY fiscal_year DESC LIMIT 1
                            """,
                            (symbol, self.MIN_PLAUSIBLE_SHARES_OUTSTANDING, self.MAX_PLAUSIBLE_SHARES_OUTSTANDING),
                        )
                        prior_shares_row = cur.fetchone()
                        if prior_shares_row and prior_shares_row[0]:
                            shares_out = float(prior_shares_row[0])
                            logger.debug(
                                f"[{symbol}] Using shares_outstanding_basic from an older fiscal year: {shares_out:,.0f}"
                            )

                # If computation didn't work, try fetching from company_info_sec as fallback.
                # FIXED 2026-08-31 (goal: data-coverage sweep, PHAR/IONR/JZXN/MI follow-up to
                # sec_valuations_frozen_yfinance_snapshot_live_recheck_fixed_20260831): this tier
                # was the ONE domestic-SEC-sourced share-count tier in this whole cascade NOT
                # gated on `not is_foreign_private_issuer` - every sibling tier above/below it
                # (reported/derived/older-year/diluted) is explicitly gated for exactly the
                # ADS/home-market unit-mismatch risk this file's module docstring and dual-class
                # comments describe at length. `company_info_sec.shares_outstanding`'s OWN
                # extraction (load_company_info_sec.py) is *supposed* to already be restricted to
                # domestic forms, but that restriction has real gaps - live-confirmed via MI
                # (Marchex/similar micro-cap FPI): company_info_sec.shares_outstanding=5,065,150
                # landed here unguarded, producing market_cap=$12.46M vs yfinance's real live
                # $584,756 (21x too high) - correctly caught by the sanity check ONLY when its own
                # live-fetch succeeds; a batch run where that live-fetch transiently failed (rate
                # limit/circuit breaker) let this wrong value through completely unchecked, since
                # `_sanity_check_market_cap` has nothing to compare against when yf_market_cap is
                # None. Relying solely on "already guarded upstream" isn't enough defense-in-depth
                # for a value this consequential - this tier needs its own explicit gate too.
                if not shares_out and not is_foreign_private_issuer:
                    cur.execute(
                        """
                        SELECT shares_outstanding FROM company_info_sec
                        WHERE symbol = %s AND shares_outstanding > %s AND shares_outstanding < %s
                        ORDER BY filing_date DESC LIMIT 1
                        """,
                        (symbol, self.MIN_PLAUSIBLE_SHARES_OUTSTANDING, self.MAX_PLAUSIBLE_SHARES_OUTSTANDING),
                    )
                    shares_row = cur.fetchone()
                    if shares_row and shares_row[0]:
                        shares_out = safe_float(shares_row[0], f"{symbol}.shares_outstanding", allow_none=False)
                        logger.debug(f"[{symbol}] Fetched shares_outstanding from company_info_sec: {shares_out:,.0f}")

                # Last-resort fallback: the diluted share count (migration 1192). Some real
                # operating companies (live-confirmed: JOUT/Johnson Outdoors, 44 real 10-K
                # entries) only ever tag WeightedAverageNumberOfDilutedSharesOutstanding in
                # SEC XBRL, never the basic variant - every fallback above depends on basic
                # (directly or via the company_info_sec/net_income/eps proxies) and comes up
                # empty for these filers. Diluted is a real reported count, just not the
                # exact same measure as basic (differs by dilutive securities outstanding).
                # Gated the same as tiers 1-3 above - a foreign private issuer's diluted
                # count carries the identical home-market-units risk. Also gated on
                # has_dual_class_sibling (2026-08-21) - diluted shares are exactly as
                # class-specific as basic, so a dual-class filer's stale/ambiguous diluted
                # count is just as unsafe to trust.
                if not shares_out and not is_foreign_private_issuer and not has_dual_class_sibling:
                    cur.execute(
                        """
                        SELECT shares_outstanding_diluted FROM annual_income_statement
                        WHERE symbol = %s AND shares_outstanding_diluted > %s AND shares_outstanding_diluted < %s
                        ORDER BY fiscal_year DESC LIMIT 1
                        """,
                        (symbol, self.MIN_PLAUSIBLE_SHARES_OUTSTANDING, self.MAX_PLAUSIBLE_SHARES_OUTSTANDING),
                    )
                    diluted_shares_row = cur.fetchone()
                    if diluted_shares_row and diluted_shares_row[0]:
                        shares_out = float(diluted_shares_row[0])
                        logger.debug(
                            f"[{symbol}] Using shares_outstanding_diluted (no basic count reported): {shares_out:,.0f}"
                        )

                # Final fallback: the SEC cover-page share count (migration 1195). Some real
                # operating companies (live-confirmed: GEF/Greif 19yrs, DGICA/Donegal Group
                # 18yrs, MC/Moelis 15yrs of real net_income) tag NO weighted-average or
                # CommonStockShares* concept at all in their us-gaap facts - the only
                # share-count data SEC XBRL has for them is the universal
                # dei:EntityCommonStockSharesOutstanding cover-page fact. Restricted to
                # domestic filing forms only inside sec_statements.py's _aggregate_concepts
                # (foreign 20-F/40-F filers report this in local/home-market units with no
                # ADS-ratio conversion - see that file's removed-IFRS-concept comment for the
                # exact 100-1000x-wrong-market-cap trap this avoids repeating).
                #
                # FIXED 2026-08-21: also gated on has_dual_class_sibling - live-confirmed
                # BRK.A/BRK.B both resolved to the identical 941,481 "shares" from this
                # exact tier once the three tiers above it were fixed, since
                # shares_outstanding_dei is populated by a separate extraction path
                # (sec_statements.py) never covered by those fixes. The cover-page fact is
                # exactly as class-specific as basic/diluted, so the same ambiguity applies.
                #
                # FIXED 2026-08-31, two independent same-day gaps in this same tier:
                #
                # (1) No recency bound (goal session: "VCIG tops the scores" follow-up into FPI
                # shares_outstanding - same bug class as load_company_info_sec.py's
                # _latest_shares_value() 2026-08-20 fix). This tier picked whatever fiscal year
                # had the MOST RECENT non-null shares_outstanding_dei with no check on how old
                # that fiscal year actually is - and since a foreign private issuer skips every
                # fresher SEC tier above (basic/diluted, current fiscal years), this was often the
                # ONLY SEC-sourced path reached. Live-confirmed: ENIC resolved to its FY2017 dei
                # value (8 years stale, 49.09B shares) with FY2018-2024 all NULL; CEPU to FY2019
                # (6 years stale, 1.51B shares); AIFU to FY2022 (1.07B shares) despite FY2023-2025
                # basic/diluted showing a real, much smaller, current count (~2.6M-10.1M - AIFU
                # genuinely restructured/consolidated its share count since FY2022, making the
                # FY2022 dei figure doubly wrong: stale AND pre-restructuring). All three fed
                # sec_valuations.shares_outstanding with data_source='sec_audited', silently
                # implying SEC-audited-and-current when it was neither. Fixed the same way as the
                # company_info_sec precedent: the query below rejects a candidate more than 2
                # years (fiscal_year >= this year - 2) older than today, falling through to the
                # FPI-yfinance live-fetch tier instead of trusting a stale figure. Same live class
                # separately confirmed via GENI (Genius Sports): its ONLY shares_outstanding_dei
                # entry across all fiscal years is FY2021's 18,500,000 (a SPAC-de-merger-year
                # founder/sponsor-share figure) against ~254.76M real current shares - a ~14x
                # UNDERcount (mirror image of the FUBO/GPUS/IHRT OVERcounts fixed elsewhere),
                # closed by this same bound.
                #
                # (2) Missing the `not is_foreign_private_issuer` gate every other domestic-SEC-
                # sourced tier in this cascade has (PHAR/IONR/JZXN follow-up - see the
                # company_info_sec fallback tier's own comment above for the full rationale).
                # Live-confirmed via IONR (ioneer Ltd, ADS)/JZXN/PHAR (Pharming, 1 ADS = 10
                # ordinary shares): all three genuine FPIs whose shares_outstanding_dei
                # nonetheless holds a plain ordinary-share count (2,325,614,708 / 11,011,389 /
                # 701,680,440 respectively - sec_statements.py's "domestic forms only"
                # restriction on this concept has a real gap for these filers), producing market
                # caps 10-30x too high. Correctly caught by the sanity check ONLY when its live
                # yfinance re-check succeeds - a batch run where that transiently failed (rate
                # limit/circuit breaker) let all three through unchecked. Gating here too (not
                # relying solely on the upstream restriction) means these symbols now correctly
                # fall through to the FPI live-yfinance tier below instead, live-tested as
                # accurate for PHAR (yfinance sharesOutstanding=70,778,124, correctly
                # ADS-adjusted).
                if not shares_out and not has_dual_class_sibling and not is_foreign_private_issuer:
                    cur.execute(
                        """
                        SELECT shares_outstanding_dei, fiscal_year FROM annual_income_statement
                        WHERE symbol = %s AND shares_outstanding_dei > %s AND shares_outstanding_dei < %s
                        AND fiscal_year >= %s
                        ORDER BY fiscal_year DESC LIMIT 1
                        """,
                        (
                            symbol,
                            self.MIN_PLAUSIBLE_SHARES_OUTSTANDING,
                            self.MAX_PLAUSIBLE_SHARES_OUTSTANDING,
                            date.today().year - 2,
                        ),
                    )
                    dei_shares_row = cur.fetchone()
                    if dei_shares_row and dei_shares_row[0]:
                        most_recent_fiscal_year = income_rows[0][0]
                        dei_fiscal_year = dei_shares_row[1]
                        if most_recent_fiscal_year - dei_fiscal_year > 2:
                            logger.debug(
                                f"[{symbol}] shares_outstanding_dei cover-page count from fiscal_year "
                                f"{dei_fiscal_year} is too stale (symbol has data through "
                                f"{most_recent_fiscal_year}) - skipping rather than trusting a "
                                f"multi-year-old figure, same bound as load_company_info_sec.py's "
                                f"_latest_shares_value() staleness fix"
                            )
                        else:
                            shares_out = float(dei_shares_row[0])
                            logger.debug(
                                f"[{symbol}] Using shares_outstanding_dei cover-page count (no us-gaap "
                                f"share concept reported): {shares_out:,.0f}"
                            )

                # FIXED 2026-08-20 (goal: finance-accuracy audit): MAX_PLAUSIBLE_SHARES_OUTSTANDING
                # (100 billion) is calibrated to catch truly absurd derived values (see
                # test_sec_valuations_shares_outstanding_ceiling.py's NMR case, ~2.94e15) but is
                # far too generous to catch a per-filing 1000x XBRL scale error for a small/mid-cap
                # filer - a value like 6.07 billion or 82.5 billion passes the ceiling untouched
                # even though it's still wrong by 3-4 orders of magnitude for that specific
                # company. Live-confirmed: LARK (Landmark Bancorp)'s FY2025
                # shares_outstanding_basic=6,070,662,000 (real count ~6.1M - LARK's OWN FY2026 row
                # and its own shares_outstanding_dei both independently agree on ~6.1M, proving the
                # FY2025 tag itself is what's mis-scaled); RPAY (Repay Holdings) mis-scaled the same
                # way across every fiscal year on file (82.5B/85.6B/89.9B vs company_info_sec's
                # independently-extracted 6.47M). Both fed sec_valuations.market_cap in the
                # hundreds of billions (LARK $195.5B, RPAY $304.5B) for real small-caps, corrupting
                # ps_ratio/fcf_yield. company_info_sec.shares_outstanding comes from a separate
                # extraction path (see load_company_info_sec.py) - when it's available and
                # disagrees with the resolved shares_out by more than
                # SHARES_OUTSTANDING_SCALE_MISMATCH_RATIO in either direction, that's a much
                # stronger signal of a stale/mis-scaled value than the bare ceiling catches, so
                # prefer it (see that constant's own comment for the 2026-08-25 20x->10x
                # lowering and the WHLR/FUBO evidence behind it). Only for domestic filers - a
                # foreign private issuer's company_info_sec figure carries the same
                # home-market-units risk as everywhere else in this method.
                if shares_out and not is_foreign_private_issuer:
                    cur.execute(
                        """
                        SELECT shares_outstanding FROM company_info_sec
                        WHERE symbol = %s AND shares_outstanding > %s AND shares_outstanding < %s
                        ORDER BY filing_date DESC LIMIT 1
                        """,
                        (symbol, self.MIN_PLAUSIBLE_SHARES_OUTSTANDING, self.MAX_PLAUSIBLE_SHARES_OUTSTANDING),
                    )
                    cross_check_row = cur.fetchone()
                    if cross_check_row and cross_check_row[0]:
                        cross_check_shares = float(cross_check_row[0])
                        larger = max(shares_out, cross_check_shares)
                        smaller = min(shares_out, cross_check_shares)
                        if smaller > 0 and larger / smaller > self.SHARES_OUTSTANDING_SCALE_MISMATCH_RATIO:
                            logger.warning(
                                f"[{symbol}] shares_outstanding scale mismatch: resolved={shares_out:,.0f} "
                                f"vs company_info_sec={cross_check_shares:,.0f} (ratio {larger / smaller:.0f}x) "
                                f"- preferring company_info_sec as the independently-extracted value"
                            )
                            shares_out = cross_check_shares

                # DELIBERATE, NARROW EXCEPTION to this file's "SEC data only, yfinance never a
                # value source" rule (see module docstring) - added 2026-08-22 after live-
                # verifying against real SEC EDGAR data that the exception is structurally
                # unavoidable: data.sec.gov's companyfacts convenience API flattens each
                # concept to ONE value per CIK+period and does not expose XBRL dimensional/
                # segment axes at all, so for a true dual-class filer it CANNOT distinguish one
                # share class's count from another - not a bug in our extraction, a real gap in
                # the only SEC data source this loader has access to (see
                # dual_class_primary_ticker_shares_outstanding_structural_gap_found_20260822 in
                # memory for the live BRK.A/BRK.B verification that established this: SEC has
                # carried NO per-class share data for Berkshire since 2011). Every tier above
                # this point is deliberately disabled for has_dual_class_sibling=True (see each
                # tier's own 2026-08-21 comment) specifically to avoid attributing one class's
                # SEC-reported count to its sibling - that gate stays exactly as strict. This
                # tier only fires when every one of those SEC-sourced paths has already been
                # exhausted and failed, for this narrow case alone. yfinance queries per-LISTING
                # (ticker), not per-company, so it naturally resolves the correct class-specific
                # value instead of SEC's collapsed one - live-verified 2026-08-22: BRK-A/BRK-B,
                # AGM/AGM-A, and BIO/BIO-B each independently resolve to a market_cap
                # (shares x price) matching its sibling's within a few percent, the strongest
                # available sanity check that these are genuinely distinct correct values, not
                # a copy of the parent/sibling figure. Marked via a distinct data_source value
                # below so this narrow exception stays visible/auditable, never silently blended
                # into the "sec_audited" label the rest of this file's output uses.
                shares_out_from_dual_class_yfinance = False
                if not shares_out and has_dual_class_sibling:
                    dual_class_shares = self._fetch_live_dual_class_shares_outstanding(symbol)
                    if (
                        dual_class_shares
                        and self.MIN_PLAUSIBLE_SHARES_OUTSTANDING
                        < dual_class_shares
                        < self.MAX_PLAUSIBLE_SHARES_OUTSTANDING
                    ):
                        shares_out = dual_class_shares
                        shares_out_from_dual_class_yfinance = True
                        logger.debug(
                            f"[{symbol}] Using yfinance per-class shares_outstanding (dual-class "
                            f"sibling, SEC companyfacts has no per-class data): {shares_out:,.0f}"
                        )

                # THIRD narrow, deliberate exception to this file's "SEC data only" rule - ADDED
                # 2026-08-27 (goal: recover the market_cap data gap found live - 945 universe
                # symbols with market_cap=NULL, 81% (768) tagged
                # foreign_private_issuer_shares_unavailable, 99% of those still actively
                # tradable with a live price in the last 5 trading days - not delisted, a
                # permanent structural gap this fallback closes for most of them). Every
                # SEC-sourced tier above is deliberately gated off for FPIs (home-market-vs-ADS
                # unit-mismatch risk - see the tier comments above); this is the exact same
                # "SEC's own API structurally cannot carry the data we need" situation as
                # dual-class shares just above, not a new category of risk. yfinance queries
                # per-LISTING (the ADS ticker itself), so its sharesOutstanding is already on
                # the correct ADS/USD basis - same reasoning that already justifies using
                # yfinance for the dual-class case and for this file's existing FPI live
                # market_cap/PE sanity-check (_fetch_live_fpi_yfinance_check_values). Marked via
                # a distinct data_source value below, same transparency convention as the
                # dual-class exception - never silently blended into "sec_audited".
                shares_out_from_fpi_yfinance = False
                if not shares_out and is_foreign_private_issuer:
                    fpi_shares = self._fetch_live_fpi_shares_outstanding_yfinance(symbol)
                    if (
                        fpi_shares
                        and self.MIN_PLAUSIBLE_SHARES_OUTSTANDING < fpi_shares < self.MAX_PLAUSIBLE_SHARES_OUTSTANDING
                    ):
                        shares_out = fpi_shares
                        shares_out_from_fpi_yfinance = True
                        logger.debug(
                            f"[{symbol}] Using yfinance shares_outstanding (foreign private "
                            f"issuer, no usable SEC-tagged share count): {shares_out:,.0f}"
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
                # INSURANCE_CAPEX_EXEMPT_SYMBOLS allowlist above (symbol-based, not SIC-based
                # - insurance isn't a uniformly capex-less sector the way banking is).
                is_capex_exempt = (
                    sic_code in self.DEPOSITORY_INSTITUTION_SIC_CODES or symbol in self.INSURANCE_CAPEX_EXEMPT_SYMBOLS
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
                live_mcap, live_pe = self._fetch_live_fpi_yfinance_check_values(symbol)
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
                    live_mcap, _live_pe = self._fetch_live_fpi_yfinance_check_values(symbol)
                    if live_mcap is not None:
                        yf_market_cap = live_mcap
                        yf_market_cap_is_live = True

            self._sanity_check_market_cap(symbol, valuation_row, yf_market_cap, yf_market_cap_is_live)
            self._sanity_check_pe_ratio(symbol, valuation_row, yf_pe_ratio, yf_market_cap_is_live)
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

    # DCF constants (migration 1208, Value factor goal 2026-08-17)
    #
    # FIXED 2026-08-20 (goal: finance-accuracy audit): DCF_DISCOUNT_RATE used to be a single
    # flat 10%/yr applied to every company in the universe regardless of risk - a mega-cap
    # utility and a small-cap biotech got the exact same cost of capital. That's not
    # industry-standard DCF practice: the discount rate for an equity-cash-flow DCF should be
    # a risk-adjusted cost of equity (CAPM: risk-free rate + beta x equity risk premium), not
    # one guessed constant for the whole universe. Replaced with a live, per-symbol CAPM rate -
    # see _compute_discount_rate() below. DCF_DISCOUNT_RATE itself is gone; DCF_EQUITY_RISK_
    # PREMIUM/DCF_DEFAULT_RISK_FREE_RATE/DCF_BLUME_ADJUSTMENT_WEIGHT/DCF_DEFAULT_BETA replace it.
    DCF_TERMINAL_GROWTH_RATE = 0.025
    DCF_GROWTH_FLOOR = -0.10
    DCF_GROWTH_CEILING = 0.15
    DCF_FORECAST_YEARS = 5
    MAX_INTRINSIC_VALUE_PER_SHARE = 1_000_000.0  # $1M/share - no real per-share DCF exceeds this

    # Long-run US equity risk premium (Damodaran/Ibbotson-style estimate - the ~4-6% range is
    # the standard academic/practitioner convention for the market's average excess return
    # over Treasuries; 5.0% sits at the middle of that range). Used as the fallback/test
    # default when _get_equity_risk_premium() below can't produce a live reading - see that
    # method's docstring for why this is no longer the value live runs actually use.
    DCF_EQUITY_RISK_PREMIUM = 0.05
    # FIXED 2026-08-25 (goal: DCF audit follow-up - dynamic ERP, previously deferred as "a
    # much bigger data undertaking" in dcf_growth_rate_fade_landed_20260825/
    # dual_class_dcf_entity_fcf_shares_mismatch_fixed_20260825): a proper Damodaran-style
    # *implied* ERP (solving for the discount rate that equates the S&P 500's current level to
    # its expected cash flows) needs index-level dividend/buyback yield and a forward earnings
    # growth estimate - live-checked economic_data's full series inventory and neither exists
    # anywhere in this pipeline (only raw SP500 index level and DGS-series Treasury yields are
    # fetched), so that route is still genuinely out of reach without a new data source.
    # VIXCLS (CBOE VIX close), however, IS already in economic_data (26 years, 2000-present)
    # and is itself a forward-looking, options-implied measure of the market's expected risk
    # (Whaley's "investor fear gauge") - unlike a trailing-realized-return premium (rejected:
    # backward-looking, would make the DCF noisier without being more accurate), VIX already
    # prices in forward risk the same way implied ERP is supposed to, just via a different
    # market (options, not equities). Scaling the static 5.0% anchor by current VIX / its own
    # long-run average gives a genuinely dynamic, live, forward-looking ERP without requiring
    # data this pipeline doesn't have - same spirit as _get_risk_free_rate's live DGS10 feed,
    # applied to the other CAPM input that was still a hardcoded constant.
    #
    # Bounds keep the result within Damodaran's own published yearly implied-ERP history
    # (his S&P 500 implied ERP series has run roughly 2%-8% since 1960, only approaching the
    # top of that band in acute crises like 2008) - an unclamped VIX ratio could otherwise push
    # the multiplier far outside that real historical range during a 2020-COVID-style vol
    # spike (VIXCLS peaked at 82.69 in this DB's own history) or an unusually complacent
    # stretch (VIXCLS low of 9.14), neither of which real implied ERP ever actually reached.
    DCF_MIN_EQUITY_RISK_PREMIUM = 0.03
    DCF_MAX_EQUITY_RISK_PREMIUM = 0.08
    # Long-run VIX average lookback - the full ~26-year history on file (not just a recent
    # window) so a multi-year low- or high-vol REGIME doesn't get compared only against
    # itself (e.g. averaging only the last 3 calm years would understate how elevated "normal"
    # VIX really is over a full cycle, permanently inflating the dynamic ERP relative to that
    # regime). economic_data's VIXCLS starts 2000-01-03, so this comfortably covers the whole
    # series without hardcoding a start date.
    DCF_VIX_LOOKBACK_YEARS = 25

    # Sanity bound on _get_net_borrowing_for_dcf's result relative to the DCF's own fcf_base
    # (OCF - CapEx - SBC) - live-caught (500-symbol universe spot-check, same day, before
    # committing) BWXT: a real, small ($50-500M/yr OCF) industrial company whose
    # operating_lease_liability data jumps to an implausible $44B in one fiscal year (almost
    # certainly a pre-existing XBRL extraction bug elsewhere in this pipeline - annual_balance_
    # sheet already carries this bad figure into total_debt/enterprise_value/ev_ebitda today,
    # independent of this fix - not something this net-borrowing feature caused, but something
    # it would otherwise blindly amplify into an even more absurd DCF result). A company's real
    # net borrowing in a single year, however large, is essentially never dozens-to-hundreds of
    # times its own operating cash flow scale (BWXT's $24B swing was ~50x its most recent real
    # annual OCF) - genuine large financing events (AMZN's real $72B swing, live-confirmed
    # plausible against Amazon's own ~$100-160B OCF scale) stay within a much smaller multiple.
    # 10x is generous enough to avoid rejecting a real large one-time raise for a company with a
    # temporarily weak FCF year, while still catching an order-of-magnitude data-quality outlier
    # like BWXT's.
    DCF_NET_BORROWING_MAX_FCF_MULTIPLE = 10.0
    # Fallback risk-free rate (approx. long-run average 10Y Treasury yield) - used only as a
    # test/caller default and on the rare day economic_data has no recent DGS10 reading. Live
    # runs use the actual current 10Y yield via _get_risk_free_rate() below, not this constant.
    DCF_DEFAULT_RISK_FREE_RATE = 0.045
    # Blume adjustment (Bloomberg/Merrill Lynch convention): shrinks a raw regression beta
    # 2/3 of the way toward the market average of 1.0. Individual-stock raw betas are noisy
    # (small sample, name-specific events) - shrinking toward 1.0 is the standard industry
    # correction rather than trusting a raw estimate (or a whole-universe flat rate) outright.
    DCF_BLUME_ADJUSTMENT_WEIGHT = 2.0 / 3.0
    # Assumed market-average risk when a symbol has no computed beta (stability_metrics.beta
    # NULL - e.g. insufficient price history). Beta=1.0 is the standard "unknown risk, assume
    # average" convention, not a guess biased toward either overvaluing or undervaluing.
    DCF_DEFAULT_BETA = 1.0
    # Cost of equity must exceed the risk-free rate by at least this much - equities are
    # inherently riskier than Treasuries, so CAPM should never produce a discount rate at or
    # below the risk-free rate even for a very low/negative-beta name.
    DCF_MIN_EQUITY_RISK_PREMIUM_APPLIED = 0.01
    # Sanity ceiling on the resulting discount rate - prevents degenerate terminal-value math
    # (or a silently absurd near-zero intrinsic value) on an extreme/noisy beta outlier.
    DCF_MAX_DISCOUNT_RATE = 0.25
    # Minimum spread the discount rate must keep above DCF_TERMINAL_GROWTH_RATE (2.5%). Gordon
    # Growth's terminal_value = fcf * (1+g) / (discount_rate - g) is a genuine singularity as
    # discount_rate approaches g: it blows up to an absurd multiple just below the singularity,
    # goes negative at/below it, and produces a negative intrinsic_per_share that the plausibility
    # guard then silently swallows as None. This isn't theoretical - this system's own DGS10
    # history includes a 0.52% reading (2020 COVID-era), and rfr+MIN_EQUITY_RISK_PREMIUM_APPLIED
    # alone doesn't keep the rate away from g in that regime (a low-beta name could land at ~2.2%,
    # under the 2.5% terminal growth rate). A 3pp floor above g keeps the terminal multiple
    # bounded to a sane range in any real-world rate environment while still leaving genuine
    # risk-based discount-rate differences visible above the floor.
    DCF_MIN_DISCOUNT_TERMINAL_SPREAD = 0.03

    def _compute_discount_rate(
        self,
        beta: float | None,
        risk_free_rate: float | None,
        equity_risk_premium: float | None = None,
    ) -> float:
        """CAPM cost of equity: risk_free_rate + Blume-adjusted-beta x equity_risk_premium.

        Replaces the old flat 10%/yr DCF_DISCOUNT_RATE (see its removal comment above) with a
        risk-adjusted rate so a high-beta, high-risk name gets a real risk-adjusted cost of
        capital instead of borrowing a safe/average company's discount rate (which would
        systematically overstate its intrinsic value), and vice versa for a genuinely
        low-risk name.

        equity_risk_premium: ADDED 2026-08-25 (goal: DCF audit follow-up - dynamic ERP, see
        DCF_MIN_EQUITY_RISK_PREMIUM's docstring above for the full rationale/derivation).
        Defaults to None -> DCF_EQUITY_RISK_PREMIUM (the static 5% anchor), so every existing
        caller/test that only passes beta/risk_free_rate keeps computing the exact same rate
        as before. Live calls from _compute_valuations pass the VIX-scaled dynamic value from
        _get_equity_risk_premium().
        """
        rfr = self.DCF_DEFAULT_RISK_FREE_RATE if risk_free_rate is None else risk_free_rate
        erp = self.DCF_EQUITY_RISK_PREMIUM if equity_risk_premium is None else equity_risk_premium
        raw_beta = self.DCF_DEFAULT_BETA if beta is None else beta
        adjusted_beta = self.DCF_BLUME_ADJUSTMENT_WEIGHT * raw_beta + (1 - self.DCF_BLUME_ADJUSTMENT_WEIGHT) * 1.0
        rate = rfr + adjusted_beta * erp
        floor = max(
            rfr + self.DCF_MIN_EQUITY_RISK_PREMIUM_APPLIED,
            self.DCF_TERMINAL_GROWTH_RATE + self.DCF_MIN_DISCOUNT_TERMINAL_SPREAD,
        )
        return max(floor, min(self.DCF_MAX_DISCOUNT_RATE, rate))

    def _get_risk_free_rate(self, cur: Any) -> float:
        """Live 10-year Treasury yield (economic_data.DGS10) as the CAPM risk-free rate.

        Cached on the instance for the lifetime of this loader run - this doesn't change
        intra-day and querying it once per symbol (5,000+ times a run) would be pure waste.
        Falls back to the most recent reading within 10 days (FRED doesn't publish on
        weekends/holidays) rather than requiring an exact today's-date row, and to
        DCF_DEFAULT_RISK_FREE_RATE on the rare day even that's unavailable.
        """
        if self._risk_free_rate_cache is not None:
            return self._risk_free_rate_cache
        cur.execute(
            """
            SELECT value FROM economic_data
            WHERE series_id = 'DGS10' AND date >= CURRENT_DATE - INTERVAL '10 days' AND value IS NOT NULL
            ORDER BY date DESC LIMIT 1
            """
        )
        row = cur.fetchone()
        # DGS10 is published as a percentage (e.g. 4.71 meaning 4.71%) - convert to decimal.
        self._risk_free_rate_cache = (
            float(row[0]) / 100.0 if row and row[0] is not None else self.DCF_DEFAULT_RISK_FREE_RATE
        )
        return self._risk_free_rate_cache

    def _get_equity_risk_premium(self, cur: Any) -> float:
        """VIX-scaled dynamic equity risk premium: DCF_EQUITY_RISK_PREMIUM x (current VIX /
        long-run average VIX), clamped to [DCF_MIN_EQUITY_RISK_PREMIUM, DCF_MAX_EQUITY_RISK_
        PREMIUM] - see that constant's docstring above for the full derivation (why VIX, why
        those bounds, why not a trailing-realized-return premium instead).

        Cached on the instance for the lifetime of this loader run, same rationale as
        _get_risk_free_rate immediately above. Falls back to the most recent VIXCLS reading
        within 90 days (live-checked: this DB's VIXCLS feed runs ~60 days behind CURRENT_DATE,
        well past DGS10's ~4-day lag - a tight window here would silently fall back to the
        static default on every single run, defeating the point) rather than requiring an
        exact today's-date row. Falls back to DCF_EQUITY_RISK_PREMIUM outright when either the
        current reading or the long-run average is unavailable (new/empty economic_data table,
        e.g. in a fresh test DB).
        """
        if self._equity_risk_premium_cache is not None:
            return self._equity_risk_premium_cache
        cur.execute(
            """
            SELECT value FROM economic_data
            WHERE series_id = 'VIXCLS' AND date >= CURRENT_DATE - INTERVAL '90 days' AND value IS NOT NULL
            ORDER BY date DESC LIMIT 1
            """
        )
        current_row = cur.fetchone()
        cur.execute(
            """
            SELECT AVG(value) FROM economic_data
            WHERE series_id = 'VIXCLS' AND date >= CURRENT_DATE - INTERVAL '%s years' AND value IS NOT NULL
            """,
            (self.DCF_VIX_LOOKBACK_YEARS,),
        )
        avg_row = cur.fetchone()
        current_vix = float(current_row[0]) if current_row and current_row[0] is not None else None
        avg_vix = float(avg_row[0]) if avg_row and avg_row[0] is not None else None
        if current_vix is None or avg_vix is None or avg_vix <= 0:
            self._equity_risk_premium_cache = self.DCF_EQUITY_RISK_PREMIUM
            return self._equity_risk_premium_cache
        scaled = self.DCF_EQUITY_RISK_PREMIUM * (current_vix / avg_vix)
        self._equity_risk_premium_cache = max(
            self.DCF_MIN_EQUITY_RISK_PREMIUM, min(self.DCF_MAX_EQUITY_RISK_PREMIUM, scaled)
        )
        return self._equity_risk_premium_cache

    def _get_net_borrowing_for_dcf(self, cur: Any, symbol: str) -> float | None:
        """Change in total balance-sheet debt (long_term_debt + short_term_debt +
        operating_lease_liability + finance_lease_liability, same components as total_debt
        above) between the two most recent fiscal years, when they're genuinely ADJACENT
        (fiscal_year apart by exactly 1) - an additive correction toward a true FCFE
        (OCF - CapEx - SBC + Net Borrowing) instead of the zero-net-borrowing-assumed proxy
        this DCF has used until now.

        FIXED 2026-08-25 (goal: DCF audit follow-up - true FCFE via net borrowing, previously
        deferred in dcf_growth_fade_live_verified_and_remaining_items_reassessed_20260825 as
        needing debt issuance/repayment cash-flow data this pipeline doesn't fetch - confirmed
        via a schema check of annual_cash_flow that no such concept is collected, only a
        blended financing_cash_flow that also mixes in equity/dividends). Uses the
        balance-sheet debt-LEVEL change instead - a standard practitioner proxy for net
        borrowing (issued minus repaid) when the cash-flow statement's own financing detail
        isn't available, mathematically exact absent other balance-sheet effects (FX
        remeasurement, fair-value adjustments on convertible debt, etc.) that this proxy can't
        see and doesn't attempt to correct for.

        The adjacency requirement is the safety guard: this file's own comments elsewhere
        document real filers switching which XBRL debt concept they tag between fiscal years
        (CAT/XOM/DKNG - see total_debt's docstring above) - comparing two non-adjacent years
        (a multi-year gap where a tag switch is more likely to have happened) risked reading a
        tag-switch artifact as a "borrowing" event. Requiring the two years be exactly 1 fiscal
        year apart doesn't eliminate that risk (an adjacent-year tag switch is possible too,
        just less common) but meaningfully bounds it versus comparing whatever two years happen
        to have data.

        FIXED same day (live-caught via a 500-symbol universe spot-check before committing):
        the newest-year query originally accepted a row with ANY ONE component non-NULL (same
        "at least one real value" leniency total_debt's own query above uses, reasonable for
        picking a single best year). Live-confirmed via AAPL this is WRONG for a two-year
        delta: AAPL's current in-progress fiscal year has real long_term_debt/short_term_debt
        but NULL operating_lease_liability/finance_lease_liability (not yet tagged - the same
        "current interim year isn't fully filed yet" gap this file fixes elsewhere for capex/
        fcf_yield), while the prior complete year has all four populated. Treating NULL-this-
        year-real-last-year as "$0 of lease debt now" manufactured a spurious -$28B "paydown"
        that was actually just missing data, not a real deleveraging event. Fixed: a
        component's null-ness must MATCH between the two years (both present or both absent)
        for every one of the four components, or the whole comparison is skipped - a component
        that's null in both years is a real "no debt of that kind" data point, safe to treat
        as 0 either way, but a mismatch is a completeness gap, not a borrowing signal, and no
        real net-borrowing figure can be extracted from it.

        Returns None (falls back to the existing OCF-CapEx-SBC proxy unchanged) when fewer
        than 2 usable, adjacent, component-comparable years exist - the common case for a
        newer filer, one with sparse balance-sheet history, or (per the fix above) a current
        fiscal year that isn't fully tagged yet.
        """
        cur.execute(
            """
            SELECT fiscal_year, long_term_debt, short_term_debt, operating_lease_liability, finance_lease_liability
            FROM annual_balance_sheet
            WHERE symbol = %s AND fiscal_year IS NOT NULL AND data_unavailable IS NOT TRUE
              AND (long_term_debt IS NOT NULL OR short_term_debt IS NOT NULL
                   OR operating_lease_liability IS NOT NULL OR finance_lease_liability IS NOT NULL)
            ORDER BY fiscal_year DESC LIMIT 1
            """,
            (symbol,),
        )
        newest_row = cur.fetchone()
        if not newest_row:
            return None
        newest_year = newest_row[0]
        newest_components = newest_row[1:]
        cur.execute(
            """
            SELECT long_term_debt, short_term_debt, operating_lease_liability, finance_lease_liability
            FROM annual_balance_sheet
            WHERE symbol = %s AND fiscal_year = %s AND data_unavailable IS NOT TRUE
              AND (long_term_debt IS NOT NULL OR short_term_debt IS NOT NULL
                   OR operating_lease_liability IS NOT NULL OR finance_lease_liability IS NOT NULL)
            """,
            (symbol, newest_year - 1),
        )
        prior_row = cur.fetchone()
        if not prior_row:
            return None
        if any(
            (newest_c is None) != (prior_c is None)
            for newest_c, prior_c in zip(newest_components, prior_row, strict=True)
        ):
            return None
        newest_debt = sum(float(c) if c is not None else 0.0 for c in newest_components)
        prior_debt = sum(float(c) if c is not None else 0.0 for c in prior_row)
        return newest_debt - prior_debt

    @staticmethod
    def _compute_avg_fcf_fallback(
        cash_rows: list[tuple[Any, Any, Any, Any, Any]], is_capex_exempt: bool
    ) -> float | None:
        """Average FCF (OCF - CapEx - Stock-Based Comp) across up to 3 fetched fiscal years,
        skipping any year with unusable ocf/capex - used when the latest year alone can't
        produce a usable FCF (negative, or capex not yet tagged - see fetch_incremental's
        `cash_rows` query, most recent 3 fiscal years DESC).

        cash_rows: (operating_cash_flow, capex, dividends_paid, stock_based_compensation,
        common_stock_repurchased) tuples, most recent year first (dividends_paid/
        common_stock_repurchased unused here, kept for call-site tuple-unpacking convenience -
        common_stock_repurchased added 2026-08-26 for net_payout_yield, see
        _compute_valuations - this widened every mock fixture across the sec_valuations test
        family that constructs cash_rows directly; see that migration's own commit for the
        full list of touched test files).
        is_capex_exempt: depository institutions / the insurance capex-exempt allowlist
        never report capex - treat it as 0 rather than unknowable for every year, not just
        the latest (see DEPOSITORY_INSTITUTION_SIC_CODES/INSURANCE_CAPEX_EXEMPT_SYMBOLS).

        FIXED 2026-08-25 (goal: "finance best practices" methodology audit): OCF already adds
        stock-based compensation back as a non-cash expense, but SBC is a real economic cost to
        existing shareholders via future dilution - the "Owner Earnings" convention (and most
        practitioner FCF/DCF models for SBC-heavy issuers, esp. tech) deducts it rather than
        treating OCF-CapEx as clean free cash flow. `stock_based_compensation` was already
        collected in annual_cash_flow but never used anywhere in this file before now. Treated
        as 0 when NULL (not skipped like a NULL capex is) - unlike capex, which this file's own
        comments document as commonly un-tagged for a still-open interim fiscal year, a NULL
        SBC overwhelmingly means "this filer has none to report" (true for most non-tech/non-
        growth sectors) rather than a timing gap - treating it as unknowable would incorrectly
        null out the FCF fallback for the common case of a company that simply doesn't grant
        stock comp.

        FIXED 2026-08-24 (goal: "missing_cash_flow_data" coverage audit): this used to
        require >=2 usable years to compute an "average" - reasonable when the gap is just
        the current, still-open fiscal year (the common case this fallback was built for),
        but real filers can lag capex tagging TWO years deep at once, not just one.
        Live-confirmed via VLO (Valero): capex is real and correctly extracted for FY2024
        ($2.057B, matches Valero's public figure) via the "PaymentsToAcquireProductiveAssets"
        concept fallback, but NULL for FY2025/FY2026 (both not yet re-tagged in the
        3-fiscal-year fetch window) - leaving only 1 usable year, below the old >=2 floor,
        so avg_fcf_fallback stayed None and both fcf_yield and margin_of_safety were
        permanently NULL despite a real, recent, correctly-extracted FCF figure sitting
        right there. Same root cause as COIN and likely a meaningful slice of the 543
        universe symbols carrying margin_of_safety_unavailable_reason='missing_cash_flow_data'
        (live DB scan, 2026-08-24). A single real recent year is still far better than a
        permanent NULL - "average" of 1 value is just that value, so `sum/len` is correct
        unchanged; only the floor moved from >=2 to >=1.
        """
        yearly_fcfs = []
        for row_ocf, row_capex, _row_dividends, row_sbc, _row_buyback in cash_rows:
            if row_ocf is None:
                continue
            if row_capex is None:
                if not is_capex_exempt:
                    continue
                row_capex = 0
            row_sbc = 0 if row_sbc is None else row_sbc
            yearly_fcfs.append(float(row_ocf) - float(row_capex) - float(row_sbc))
        return sum(yearly_fcfs) / len(yearly_fcfs) if len(yearly_fcfs) >= 1 else None

    @staticmethod
    def _compute_multi_year_eps_cagr(income_rows: list[tuple[Any, ...]]) -> float | None:
        """Multi-year EPS CAGR used as the DCF's growth driver instead of the bare single-year
        TTM-vs-prior-year delta (see the LIMIT-6 comment on the income_rows query in
        fetch_incremental) - smooths past a one-off blip in either the newest or oldest usable
        year, same rationale _compute_avg_fcf_fallback already applies to FCF.

        income_rows: the (fiscal_year, revenue, net_income, earnings_per_share, ...) tuples
        fetch_incremental fetches, ORDER BY tier then fiscal_year DESC, up to 6 rows. Rows with
        a NULL or non-positive earnings_per_share are dropped first (CAGR isn't meaningful
        across a sign change or through a missing year - same requirement PEG's own growth_rate
        already imposes on prior_year_eps/ttm_eps); a tier-1 row (no revenue/EPS/net_income at
        all - see the query's ORDER BY CASE) always has a NULL earnings_per_share and is
        dropped here too, so the remaining rows stay in fiscal_year DESC order without needing
        a separate sort. Requires the newest and oldest surviving rows to be >=3 fiscal years
        apart - below that, a 2-year-apart CAGR is arithmetically identical to the existing
        single-year delta, so let that stand unchanged rather than silently duplicating it
        under a different name. Only the two endpoints matter; a gap year missing from the
        fetched window (e.g. row 4 has a NULL EPS) doesn't block the calculation.

        Returns None (falls back to the existing single-year delta) when fewer than 2 usable
        years exist, or they're not >=3 fiscal years apart.
        """
        eps_by_year = [(int(row[0]), float(row[3])) for row in income_rows if row[3] is not None and float(row[3]) > 0]
        if len(eps_by_year) < 2:
            return None
        newest_year, newest_eps = eps_by_year[0]
        oldest_year, oldest_eps = eps_by_year[-1]
        n_years = newest_year - oldest_year
        if n_years < 3:
            return None
        return float(((newest_eps / oldest_eps) ** (1 / n_years) - 1) * 100)

    def _compute_dcf_intrinsic_value(
        self,
        symbol: str,
        fcf: float | None,
        eps_growth_pct: float | None,
        shares_out: float | None,
        current_price: float | None,
        beta: float | None = None,
        risk_free_rate: float | None = None,
        equity_risk_premium: float | None = None,
    ) -> tuple[float | None, float | None]:
        """Two-stage FCFE DCF: 5-year explicit forecast of `fcf`, discounted at a CAPM cost of
        equity (see _compute_discount_rate), plus a Gordon Growth terminal value at
        DCF_TERMINAL_GROWTH_RATE, divided by shares_out.

        equity_risk_premium: ADDED 2026-08-25 (goal: DCF audit follow-up - dynamic ERP). See
        DCF_MIN_EQUITY_RISK_PREMIUM's docstring for the full rationale. Defaults to None ->
        _compute_discount_rate's own default (the static DCF_EQUITY_RISK_PREMIUM), so every
        existing caller/test is unaffected; live calls from _compute_valuations pass the
        VIX-scaled value from _get_equity_risk_premium().

        FIXED 2026-08-25 (goal: DCF audit follow-up - growth-rate fade, previously deferred as
        real-blast-radius in dcf_sbc_and_multi_year_eps_cagr_fixed_20260825): the explicit
        forecast used to hold `eps_growth_pct` flat for all 5 years, then drop straight to
        DCF_TERMINAL_GROWTH_RATE (2.5%) in the terminal-value formula - an abrupt one-year
        cliff from (say) 15%/yr to 2.5%/yr, not how a real high-growth company's growth
        actually decays. Replaced with a Damodaran-style linear fade: year 1 uses
        `eps_growth_pct` in full, year DCF_FORECAST_YEARS uses DCF_TERMINAL_GROWTH_RATE
        exactly (so the explicit forecast's last year already matches the terminal value's own
        growth assumption - no discontinuity at the handoff), with each year in between
        interpolated linearly. A company already growing at/below the terminal rate now fades
        *up* to it just as mechanically as a high-growth company fades down - both are the
        same linear interpolation, not a special case.

        Returns (intrinsic_value_per_share, margin_of_safety_pct) - both None when fcf/
        shares_out/current_price aren't usable or the result is implausible. A missing/
        unusable eps_growth_pct defaults to flat 0%/yr rather than skipping the DCF entirely:
        FCF, shares, and price are the primary drivers and are independently available even
        when EPS history isn't (unlike peg_ratio, which requires a positive prior_year_eps to
        be meaningful at all). beta/risk_free_rate default to DCF_DEFAULT_BETA/
        DCF_DEFAULT_RISK_FREE_RATE when not supplied (test/caller convenience) - live calls
        from _compute_valuations always pass the symbol's real beta and the live Treasury rate.
        """
        if (
            fcf is None
            or fcf <= 0
            or shares_out is None
            or shares_out <= 0
            or current_price is None
            or current_price <= 0
        ):
            return None, None

        growth_rate = 0.0 if eps_growth_pct is None else eps_growth_pct / 100.0
        growth_rate = max(self.DCF_GROWTH_FLOOR, min(self.DCF_GROWTH_CEILING, growth_rate))
        discount_rate = self._compute_discount_rate(beta, risk_free_rate, equity_risk_premium)

        pv_explicit = 0.0
        fcf_year = fcf
        for year in range(1, self.DCF_FORECAST_YEARS + 1):
            fade_frac = (year - 1) / (self.DCF_FORECAST_YEARS - 1) if self.DCF_FORECAST_YEARS > 1 else 1.0
            year_growth_rate = growth_rate - (growth_rate - self.DCF_TERMINAL_GROWTH_RATE) * fade_frac
            fcf_year = fcf_year * (1 + year_growth_rate)
            pv_explicit += fcf_year / ((1 + discount_rate) ** year)

        terminal_value = (fcf_year * (1 + self.DCF_TERMINAL_GROWTH_RATE)) / (
            discount_rate - self.DCF_TERMINAL_GROWTH_RATE
        )
        pv_terminal = terminal_value / ((1 + discount_rate) ** self.DCF_FORECAST_YEARS)
        intrinsic_per_share = (pv_explicit + pv_terminal) / shares_out

        if not (0 < intrinsic_per_share < self.MAX_INTRINSIC_VALUE_PER_SHARE):
            logger.debug(f"[{symbol}] DCF intrinsic value implausible ({intrinsic_per_share:.2f}), marking as NULL")
            return None, None

        margin_of_safety_pct = (intrinsic_per_share - current_price) / intrinsic_per_share * 100
        if not (-1000 <= margin_of_safety_pct <= 1000):
            logger.debug(f"[{symbol}] Margin of safety out of bounds ({margin_of_safety_pct:.0f}%), marking as NULL")
            return round(intrinsic_per_share, 2), None

        return round(intrinsic_per_share, 2), round(margin_of_safety_pct, 2)

    def _compute_valuations(  # noqa: C901
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

        # PE Ratio = Price ÷ TTM EPS (bound to MIN_PLAUSIBLE_PE_RATIO..10000 - see
        # MIN_PLAUSIBLE_PB_RATIO's docstring for the VCIG-driven lower-bound addition)
        if ttm_eps and ttm_eps > 0:
            pe = current_price / ttm_eps
            if pe <= 10000 and pe >= self.MIN_PLAUSIBLE_PE_RATIO:  # Reasonable PE bounds
                result["pe_ratio"] = round(pe, 2)
            elif pe > 10000:
                logger.warning(f"[{symbol}] PE ratio out of bounds ({pe:.0f}), marking as NULL")
            else:
                logger.warning(
                    f"[{symbol}] PE ratio implausibly low ({pe:.4f} < {self.MIN_PLAUSIBLE_PE_RATIO}), "
                    "excluding from Value scoring rather than letting a single extreme value rank #1."
                )
        elif ttm_eps == 0:
            # Company is unprofitable this TTM
            result["pe_ratio"] = None
        else:
            logger.warning(f"[{symbol}] TTM EPS missing or invalid, PE ratio unavailable")

        # PB Ratio = Price ÷ Book Value Per Share (bound to MIN_PLAUSIBLE_PB_RATIO..1000 -
        # see that constant's docstring for the VCIG-driven lower-bound addition)
        if book_value and book_value > 0:
            bvps = book_value / shares_out
            if bvps > 0:
                pb = current_price / bvps
                if pb <= 1000 and pb >= self.MIN_PLAUSIBLE_PB_RATIO:  # Reasonable PB bounds
                    result["pb_ratio"] = round(pb, 2)
                elif pb > 1000:
                    logger.warning(f"[{symbol}] PB ratio out of bounds ({pb:.0f}), marking as NULL")
                else:
                    logger.warning(
                        f"[{symbol}] PB ratio implausibly low ({pb:.4f} < {self.MIN_PLAUSIBLE_PB_RATIO}), "
                        "excluding from Value scoring rather than letting a single extreme value rank #1."
                    )
        else:
            logger.warning(f"[{symbol}] Book value missing, PB ratio unavailable")

        # PS Ratio = Price ÷ Revenue Per Share (bound to MIN_PLAUSIBLE_PS_RATIO..10000 -
        # see MIN_PLAUSIBLE_PB_RATIO's docstring for the VCIG-driven lower-bound addition)
        if ttm_revenue and ttm_revenue > 0:
            rps = ttm_revenue / shares_out
            if rps > 0:
                ps = current_price / rps
                if ps <= 10000 and ps >= self.MIN_PLAUSIBLE_PS_RATIO:  # Reasonable PS bounds
                    result["ps_ratio"] = round(ps, 2)
                elif ps > 10000:
                    logger.warning(f"[{symbol}] PS ratio out of bounds ({ps:.0f}), marking as NULL")
                else:
                    logger.warning(
                        f"[{symbol}] PS ratio implausibly low ({ps:.4f} < {self.MIN_PLAUSIBLE_PS_RATIO}), "
                        "excluding from Value scoring rather than letting a single extreme value rank #1."
                    )
        else:
            logger.warning(f"[{symbol}] TTM revenue missing, PS ratio unavailable")

        # PEG Ratio = PE ÷ Earnings Growth Rate % (bound to 0..10000)
        # Growth rate: (TTM EPS - EPS from prior fiscal year) / EPS from prior fiscal year
        # NOTE: Annual (fiscal-year over fiscal-year), not quarterly - full quarterly
        # lookback would require quarterly history this loader doesn't fetch.
        if (
            result["pe_ratio"]
            and prior_year_eps is not None
            and prior_year_eps > 0
            and ttm_eps is not None
            and ttm_eps > 0
        ):
            growth_rate = ((ttm_eps - prior_year_eps) / abs(prior_year_eps)) * 100 if prior_year_eps != 0 else None
            if growth_rate and growth_rate > 0 and result["pe_ratio"] > 0:
                peg = result["pe_ratio"] / growth_rate
                if peg <= 10000:  # Reasonable PEG bounds
                    result["peg_ratio"] = round(peg, 2)
                else:
                    logger.debug(f"[{symbol}] PEG ratio out of bounds ({peg:.0f}), marking as NULL")

        # FCF Yield = Free Cash Flow ÷ Market Cap
        # FCF = Operating Cash Flow - Capital Expenditures - Stock-Based Compensation
        #
        # FIXED 2026-08-25 (goal: "finance best practices" methodology audit): OCF already
        # adds SBC back as a non-cash expense, but SBC is a real economic cost via future
        # dilution ("Owner Earnings" convention - see _compute_avg_fcf_fallback's docstring
        # for the full rationale). Treated as 0 when None (most non-SBC filers simply don't
        # tag the concept - unlike capex, whose None/timing-lag handling is the FIXED comment
        # immediately below).
        #
        # FIXED 2026-08-22 (goal session - coverage-bucket root-cause audit): `ocf`/`capex`
        # here are always the SINGLE latest fiscal_year row (fetch_incremental's `cash_rows[0]`)
        # - for the current, still-open fiscal year (e.g. 2026 while that year is in progress),
        # a full-year capex figure genuinely hasn't been filed yet, so capex is None and this
        # unconditionally left fcf_yield NULL even when the immediately preceding COMPLETE
        # fiscal year had perfectly good ocf/capex on file. Live-confirmed: BAX, VTR, STM, CWT,
        # FAF, UMH, ESE, MWA (and ~1574 symbols universe-wide, ~30% of the tracked universe) -
        # all real, established companies with a real, complete prior-year FCF figure already in
        # annual_cash_flow - permanently NULL here purely because the current interim year's
        # capex isn't tagged yet. Same "current partial year masks real prior-year data" bug
        # class already fixed for margin_of_safety/intrinsic_value_per_share via
        # `avg_fcf_fallback` (see fcf_base a few lines below) - that fallback was computed and
        # passed into this function all along, just never wired up for fcf_yield itself.
        sbc = 0.0 if stock_based_compensation is None else stock_based_compensation
        fcf = ocf - capex - sbc if ocf is not None and capex is not None else None
        if fcf is None and avg_fcf_fallback is not None:
            fcf = avg_fcf_fallback
        # FIXED 2026-08-25 (dual-class entity-wide-FCF fix, see entity_shares_out_for_fcf's
        # definition above): fcf is entity-wide, so it must be paired with an entity-wide
        # market cap (current_price x entity_shares_out_for_fcf), not result["market_cap"]
        # (current_price x this ticker's own class-specific shares_out) - otherwise a minority
        # share class's fcf_yield is inflated by the same ratio its share count understates the
        # full entity (live-confirmed: TAP.A was 936%, should read close to TAP's own ~14%).
        entity_market_cap = current_price * entity_shares_out if entity_shares_out else None
        if fcf is not None and entity_market_cap and entity_market_cap > 0:
            fcf_yield_pct = (fcf / entity_market_cap) * 100
            # Only store if within reasonable bounds (-1000% to +1000%)
            # Extreme values indicate data errors or tiny market caps
            if -1000 <= fcf_yield_pct <= 1000:
                result["fcf_yield"] = round(fcf_yield_pct, 2)
            else:
                logger.debug(f"[{symbol}] FCF yield out of bounds ({fcf_yield_pct:.1f}%), marking as NULL")

        # Dividend Yield = Dividends Paid ÷ Market Cap (stored as a decimal fraction, e.g.
        # 0.03 = 3% - matches load_stock_scores.py._score_value's existing "decimal ->
        # percent" conversion for this field; NOT the same convention as fcf_yield above,
        # which is stored as a percentage already).
        # FIXED 2026-08-25 (same dual-class entity-wide fix as fcf_yield above):
        # dividends_paid is the entity-wide total dollar amount from the cash flow statement
        # (no per-class breakdown exists in SEC data, same as ocf/capex) - paired with
        # entity_market_cap for the same reason fcf_yield was, otherwise a minority class's
        # dividend_yield is inflated the same way fcf_yield was.
        if dividends_paid and dividends_paid > 0 and entity_market_cap and entity_market_cap > 0:
            div_yield = dividends_paid / entity_market_cap
            if 0 < div_yield <= self.MAX_PLAUSIBLE_DIVIDEND_YIELD_RATIO:
                result["dividend_yield"] = round(div_yield, 4)
            else:
                logger.debug(f"[{symbol}] Dividend yield out of bounds ({div_yield:.2%}), marking as NULL")

        # Net Payout (Shareholder) Yield = (Dividends Paid + Buybacks) ÷ Market Cap - ADDED
        # 2026-08-26 (goal: full Value pillar re-audit). Same decimal-fraction convention as
        # dividend_yield above (0.03 = 3%), same entity-wide-market-cap dual-class pairing.
        # "Total payout yield" (Boudoukh/Michaely/Richardson/Roberts 2007) / O'Shaughnessy's
        # "Shareholder Yield" - captures buybacks alongside dividends, which dividend_yield
        # alone misses (most large-cap US firms have shifted a meaningful share of shareholder
        # returns to buybacks since the 1980s). Own Fama-MacBeth validation
        # (algo/research/fama_macbeth_value_factors.py, 2026-08-26): univariate t=3.27,
        # multivariate t=3.05 (jointly with the live Value inputs) - stronger than
        # dividend_yield's own t=1.55-2.28, and dividend_yield's own multivariate coefficient
        # flips negative once net_payout_yield is present (its positive univariate signal was
        # actually payout information net_payout_yield now captures better). common_stock_
        # repurchased defaults to None for backward-compat callers/tests - net_payout_yield
        # then reduces to dividends-only (same number dividend_yield computes), never worse
        # than not having this field at all.
        buyback = 0.0 if common_stock_repurchased is None else abs(common_stock_repurchased)
        dividends = 0.0 if dividends_paid is None or dividends_paid <= 0 else dividends_paid
        total_payout = dividends + buyback
        if total_payout > 0 and entity_market_cap and entity_market_cap > 0:
            payout_yield = total_payout / entity_market_cap
            # BOUND TIGHTENED 150%->50% same day, later pass: live-confirmed DDT still passed
            # this gate at a real, non-broken market cap ($412M, real ~15.6M shares) with a
            # 143.82% payout yield - not the shares-outstanding-scale bug the equivalent
            # load_value_quality_growth_metrics.py fallback bound was tightened for, more
            # likely a raw common_stock_repurchased extraction issue (e.g. a multi-year figure
            # picked up as one year's), but the same "no real company legitimately buys back +
            # dividends more than half its market cap in a year" bound catches it regardless of
            # root cause - kept consistent with that fallback's now-50% bound rather than
            # leaving this (more-trusted) path more permissive for no principled reason.
            if 0 < payout_yield <= 0.5:
                result["net_payout_yield"] = round(payout_yield, 4)
            else:
                logger.debug(f"[{symbol}] Net payout yield out of bounds ({payout_yield:.2%}), marking as NULL")

        # Enterprise Value = Market Cap + Total Debt - Cash & Equivalents
        # FIXED 2026-08-25 (same dual-class entity-wide fix as fcf_yield above): total_debt/
        # total_cash are entity-wide (balance sheet has no per-class breakdown), so pairing
        # them with a class-specific market_cap understated EV for a minority class the same
        # way it inflated fcf_yield/the DCF - EV/EBITDA and EV/Revenue (both entity-wide
        # ebitda/revenue) inherited the distortion. entity_market_cap (current_price x
        # entity-wide shares) is also just the more standard definition of "enterprise value
        # of the company" to begin with - EV is conceptually a whole-company figure, not a
        # single share class's. Falls back to result["market_cap"] only in the pathological
        # case entity_market_cap is unset (current_price/shares_out themselves missing,
        # which already guards result["market_cap"] being None above).
        if result["market_cap"] is not None:
            equity_val = entity_market_cap if entity_market_cap else result["market_cap"]
            debt_val = total_debt if total_debt else 0
            cash_val = total_cash if total_cash else 0
            ev = equity_val + debt_val - cash_val
            if ev > 0 and abs(ev) < MAX_ABSOLUTE_DOLLAR_VALUE:
                result["enterprise_value"] = round(ev, 2)
            else:
                logger.debug(f"[{symbol}] Enterprise value non-positive or implausible ({ev:.0f}), marking as NULL")

        # EV / EBITDA Ratio
        if result["enterprise_value"] and ebitda and ebitda > 0:
            ev_ebitda = result["enterprise_value"] / ebitda
            if 0 < ev_ebitda <= 10000:  # Reasonable bounds
                result["ev_ebitda"] = round(ev_ebitda, 2)
            else:
                logger.debug(f"[{symbol}] EV/EBITDA out of bounds ({ev_ebitda:.0f}), marking as NULL")

        # EV / Revenue Ratio
        if result["enterprise_value"] and ttm_revenue and ttm_revenue > 0:
            ev_revenue = result["enterprise_value"] / ttm_revenue
            if 0 < ev_revenue <= 10000:  # Reasonable bounds
                result["ev_revenue"] = round(ev_revenue, 2)
            else:
                logger.debug(f"[{symbol}] EV/Revenue out of bounds ({ev_revenue:.0f}), marking as NULL")

        # Intrinsic Value / Margin of Safety: 2-stage FCFE DCF (migration 1208, Value factor
        # goal 2026-08-17). Reuses the same FCF base (OCF - CapEx - SBC, see the 2026-08-25
        # "finance best practices" fix on fcf_yield above) as FCF yield above so this
        # stays consistent with the other value metrics instead of introducing a second FCF
        # definition. Growth basis: the same YoY EPS delta peg_ratio uses, UNLESS a multi-year
        # EPS CAGR is available (dcf_eps_cagr_pct - see _compute_multi_year_eps_cagr), which is
        # preferred for the DCF specifically since it smooths past a one-off blip in either
        # endpoint year the way avg_fcf_fallback already does for FCF - peg_ratio's own
        # growth_rate above is untouched, it deliberately stays single-year (see that
        # calculation's own comment). See _compute_dcf_intrinsic_value for why a missing/
        # unusable growth rate defaults to flat 0%/yr here instead of blocking the DCF the way
        # peg_ratio is blocked.
        # FIXED 2026-08-18 (coverage): a single negative-FCF year (capex-heavy or cash-flow-
        # lumpy, common for real capital-intensive/cyclical businesses) used to zero out the
        # DCF outright even when the company is normally FCF-positive. Standard DCF practice
        # normalizes FCF over multiple years for exactly this reason - fall back to the
        # 3-year average FCF (fetch_incremental's avg_fcf_fallback) only when the latest
        # year alone is unusable and the multi-year average is positive; fcf_yield above is
        # deliberately left on the latest year only (it's meant to reflect current cash
        # generation, not a smoothed figure).
        fcf_base = ocf - capex - sbc if ocf is not None and capex is not None else None
        if (fcf_base is None or fcf_base <= 0) and avg_fcf_fallback is not None and avg_fcf_fallback > 0:
            fcf_base = avg_fcf_fallback
        # net_borrowing (see this parameter's own docstring above): DCF-only additive
        # correction toward a true FCFE, never applied to fcf_yield above. Bounded to
        # DCF_NET_BORROWING_MAX_FCF_MULTIPLE x |fcf_base| - see that constant's docstring
        # (BWXT live-caught data-quality outlier) - an implausibly large net_borrowing relative
        # to the entity's own cash-flow scale is silently skipped (falls back to fcf_base
        # unadjusted) rather than corrupting the DCF with what's almost certainly bad
        # upstream balance-sheet data, not a genuine financing event.
        dcf_fcf_base = fcf_base
        if (
            fcf_base is not None
            and net_borrowing is not None
            and fcf_base != 0
            and abs(net_borrowing) <= self.DCF_NET_BORROWING_MAX_FCF_MULTIPLE * abs(fcf_base)
        ):
            dcf_fcf_base = fcf_base + net_borrowing
        eps_growth_pct = None
        if prior_year_eps is not None and prior_year_eps != 0 and ttm_eps is not None:
            eps_growth_pct = ((ttm_eps - prior_year_eps) / abs(prior_year_eps)) * 100
        dcf_growth_pct = dcf_eps_cagr_pct if dcf_eps_cagr_pct is not None else eps_growth_pct
        # entity_shares_out (not shares_out): fcf_base is entity-wide, same reasoning as
        # fcf_yield's entity_market_cap fix just above.
        result["intrinsic_value_per_share"], result["margin_of_safety_pct"] = self._compute_dcf_intrinsic_value(
            symbol,
            dcf_fcf_base,
            dcf_growth_pct,
            entity_shares_out,
            current_price,
            beta,
            risk_free_rate,
            equity_risk_premium,
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

        return result

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
    def _fetch_live_fpi_yfinance_check_values(self, symbol: str) -> tuple[float | None, float | None]:
        """Live market_cap/trailingPE for a foreign private issuer, for sanity-check use only.

        Never a value source for pe_ratio/market_cap themselves (those stay 100% SEC-derived
        per this file's module docstring) - only used to validate/reject an already-computed
        SEC-derived value. Fails open (returns None, None) on any fetch error: a sanity check
        that can't run is not itself a reason to block valuation output. Uses the same shared
        cross-ECS-task IP circuit breaker as utils/external/yfinance_financials.py/
        yfinance_analyst_ratings.py (this loader can run for thousands of symbols across a
        full pipeline run, same coordination requirement as those callers).
        """
        try:
            from utils.external.yfinance_analyst_ratings import _get_module_worker
            from utils.external.yfinance_circuit_breaker import (
                YFinanceStillBannedError,
                get_circuit_breaker,
            )
            from utils.external.yfinance_symbol import to_yfinance_symbol

            circuit_breaker = get_circuit_breaker()
            try:
                circuit_breaker.wait_or_raise()
            except YFinanceStillBannedError as e:
                logger.debug(f"[{symbol}] yfinance shared IP ban active, skipping FPI sanity-check fetch: {e}")
                return None, None

            # FIXED 2026-08-29: fetches via the shared _YfinanceAttrProcessWorker (see
            # utils/external/yfinance_analyst_ratings.py) rather than an in-process
            # yf.Ticker(...).info call wrapped in socket.setdefaulttimeout() - that timeout
            # has no effect on a curl_cffi hang (yfinance 0.2.40+ requires curl_cffi, not
            # built on Python's socket module) - same root cause fixed at 4 other call
            # sites this session. A TimeoutError from the worker is caught by the generic
            # except below like any other fetch failure - this function already fails
            # open on any error, so no special-casing needed.
            info = _get_module_worker().fetch(to_yfinance_symbol(symbol), "info", timeout_seconds=10.0)
        except Exception as e:
            error_str = str(e).lower()
            if any(kw in error_str for kw in ("429", "rate", "too many", "invalid crumb", "unauthorized")):
                try:
                    get_circuit_breaker().report_rate_limit_error()
                except Exception:
                    pass
            logger.debug(f"[{symbol}] Live FPI yfinance sanity-check fetch failed (non-fatal): {e}")
            return None, None

        try:
            get_circuit_breaker().report_success()
        except Exception:
            pass
        if not isinstance(info, dict):
            return None, None
        mcap = info.get("marketCap")
        pe = info.get("trailingPE")
        yf_market_cap = float(mcap) if isinstance(mcap, (int, float)) and mcap > 0 else None
        yf_pe_ratio = float(pe) if isinstance(pe, (int, float)) and pe > 0 else None
        return yf_market_cap, yf_pe_ratio

    # ADDED 2026-08-22 (goal session - real-money-readiness audit): the one narrow, deliberate
    # exception to this file's "SEC data only, yfinance never a value source" rule - see the
    # call site's comment (in _resolve_shares_outstanding-equivalent block above) and
    # dual_class_primary_ticker_shares_outstanding_structural_gap_found_20260822 in memory for
    # the full justification (SEC's companyfacts API structurally cannot carry per-share-class
    # data for a true dual-class filer - live-verified against BRK.A/BRK.B).
    def _fetch_live_dual_class_shares_outstanding(self, symbol: str) -> float | None:
        """Live per-ticker shares_outstanding for a dual-class sibling, from yfinance.

        ONLY called when has_dual_class_sibling=True and every SEC-derived tier above has
        already failed - never a substitute for a real SEC value when one exists. yfinance
        queries per-LISTING (ticker), not per-company like SEC's companyfacts API, so it
        naturally resolves the correct class-specific count. Fails open (returns None) on any
        fetch error, same as _fetch_live_fpi_yfinance_check_values above - a fetch failure here
        just means this symbol stays data_unavailable, not a reason to block the whole run.
        """
        try:
            from utils.external.yfinance_analyst_ratings import _get_module_worker
            from utils.external.yfinance_circuit_breaker import (
                YFinanceStillBannedError,
                get_circuit_breaker,
            )
            from utils.external.yfinance_symbol import to_yfinance_symbol

            circuit_breaker = get_circuit_breaker()
            try:
                circuit_breaker.wait_or_raise()
            except YFinanceStillBannedError as e:
                logger.debug(f"[{symbol}] yfinance shared IP ban active, skipping dual-class shares fetch: {e}")
                return None

            # FIXED 2026-08-29: see _fetch_live_fpi_yfinance_check_values's identical fix
            # above for why the process-isolated worker replaces socket.setdefaulttimeout().
            info = _get_module_worker().fetch(to_yfinance_symbol(symbol), "info", timeout_seconds=10.0)
        except Exception as e:
            error_str = str(e).lower()
            if any(kw in error_str for kw in ("429", "rate", "too many", "invalid crumb", "unauthorized")):
                try:
                    get_circuit_breaker().report_rate_limit_error()
                except Exception:
                    pass
            logger.debug(f"[{symbol}] Live dual-class yfinance shares fetch failed (non-fatal): {e}")
            return None

        try:
            get_circuit_breaker().report_success()
        except Exception:
            pass
        if not isinstance(info, dict):
            return None
        shares = info.get("sharesOutstanding")
        return float(shares) if isinstance(shares, (int, float)) and shares > 0 else None

    # ADDED 2026-08-27 (goal: recover the market_cap data gap - 768 foreign private issuer
    # symbols with market_cap=NULL, 99% still actively tradable). Third narrow exception to
    # this file's "SEC data only" rule - see the call site's comment above for the full
    # justification (SEC's 20-F/companyfacts data structurally lacks a usable US-GAAP shares
    # tag for most FPIs, the same class of gap as dual-class shares just above).
    def _fetch_live_fpi_shares_outstanding_yfinance(self, symbol: str) -> float | None:
        """Live per-ticker shares_outstanding for a foreign private issuer, from yfinance.

        ONLY called when is_foreign_private_issuer=True and every SEC-derived tier above has
        already failed - never a substitute for a real SEC value when one exists. yfinance
        queries per-LISTING (the ADS ticker), so its sharesOutstanding is already on the
        correct ADS/USD basis, avoiding the home-market-units mismatch every SEC-sourced tier
        above is gated off to avoid. Fails open (returns None) on any fetch error, same as
        _fetch_live_dual_class_shares_outstanding/_fetch_live_fpi_yfinance_check_values above -
        a fetch failure here just means this symbol stays data_unavailable, not a reason to
        block the whole run.
        """
        try:
            from utils.external.yfinance_analyst_ratings import _get_module_worker
            from utils.external.yfinance_circuit_breaker import (
                YFinanceStillBannedError,
                get_circuit_breaker,
            )
            from utils.external.yfinance_symbol import to_yfinance_symbol

            circuit_breaker = get_circuit_breaker()
            try:
                circuit_breaker.wait_or_raise()
            except YFinanceStillBannedError as e:
                logger.debug(f"[{symbol}] yfinance shared IP ban active, skipping FPI shares fetch: {e}")
                return None

            # FIXED 2026-08-29: see _fetch_live_fpi_yfinance_check_values's identical fix
            # above for why the process-isolated worker replaces socket.setdefaulttimeout().
            info = _get_module_worker().fetch(to_yfinance_symbol(symbol), "info", timeout_seconds=10.0)
        except Exception as e:
            error_str = str(e).lower()
            if any(kw in error_str for kw in ("429", "rate", "too many", "invalid crumb", "unauthorized")):
                try:
                    get_circuit_breaker().report_rate_limit_error()
                except Exception:
                    pass
            logger.debug(f"[{symbol}] Live FPI yfinance shares fetch failed (non-fatal): {e}")
            return None

        try:
            get_circuit_breaker().report_success()
        except Exception:
            pass
        if not isinstance(info, dict):
            return None
        shares = info.get("sharesOutstanding")
        return float(shares) if isinstance(shares, (int, float)) and shares > 0 else None

    # FIXED 2026-08-20 (goal: finance-accuracy audit): shares_outstanding can be wrong by a
    # factor neither the plausibility ceiling nor the company_info_sec cross-check (both
    # earlier in this file) catches - both can independently derive from the SAME
    # underlying mis-scaled SEC concept and agree with each other while both being wrong.
    # Live-confirmed: ONC (BeOne Medicines) computed market_cap=$534.3B here, while
    # company_info_sec's shares_outstanding (1.478B) agreed with the SEC-derived value
    # (1.418B) within the existing 20x cross-check tolerance - both sourced from the same
    # mis-scaled concept. yfinance_snapshot.market_cap (a genuinely independent,
    # differently-sourced figure) shows ONC's real market cap is ~$31.0B - a 17x gap. A
    # DB-wide scan found 92 symbols with a >10x mismatch against yfinance_snapshot.market_cap
    # (up to 792x for MTLS). This file's own module docstring is explicit that yfinance must
    # never be a VALUE source here ("No fallback to yfinance (SEC data only)"), so this only
    # uses it as a validity check: a >10x disagreement nulls every field that depends on
    # shares_outstanding (market_cap, pb_ratio, ps_ratio, fcf_yield, dividend_yield,
    # net_payout_yield (ADDED 2026-08-26 - same entity_market_cap denominator as
    # dividend_yield, same exposure to this bug), enterprise_value, ev_ebitda, ev_revenue,
    # intrinsic_value_per_share, margin_of_safety_pct) rather than presenting a number now
    # positively known to likely be
    # wrong - pe_ratio/peg_ratio are untouched since they don't depend on shares_outstanding
    # at all. 10x (not the shares-cross-check's 20x) because this is comparing two fully
    # independent extraction pipelines, not two paths that can share a root cause - a real,
    # non-buggy 10x+ gap between SEC-audited and yfinance market cap would itself be a strong
    # sign of stale/wrong data on one side, worth losing the metric over.
    def _sanity_check_market_cap(
        self, symbol: str, result: dict[str, Any], yf_market_cap: float | None, yf_market_cap_is_live: bool = False
    ) -> None:
        market_cap = result.get("market_cap")
        if market_cap is None or market_cap <= 0:
            return
        if yf_market_cap is None:
            return
        ratio = max(market_cap, yf_market_cap) / min(market_cap, yf_market_cap)
        if ratio <= 10:
            return
        # FIXED 2026-08-31 (goal: data-coverage sweep): yf_market_cap here almost always comes
        # from the yfinance_snapshot table read at the top of fetch_incremental, which has had
        # NO active writer since Session 275 (see that read's own comment) - live-confirmed
        # 100% of its 4,683 rows are frozen at 2026-07-04/07-12, 7-8 weeks stale as of this fix.
        # A >10x disagreement against an 8-week-old number is exactly what normal price
        # movement produces for any volatile small/mid-cap - NOT evidence of a mis-scaled
        # shares_outstanding. Live-confirmed via AMRN: SEC-derived market_cap=$5.86B (price
        # $13.97 x 419.5M shares, both independently correct) was rejected against the frozen
        # table's $312M (implying $0.74/share, nowhere near the real price) - AMRN's real
        # market cap is ~$6.00B per live external quotes, i.e. the SEC-derived value was right
        # and the frozen table was wrong. This hit 66 active symbols (FUBO, GENI and other
        # real, liquid names among them, not just illiquid micro-caps). Before finalizing a
        # rejection on a *stale* comparison value, get one live number and re-check against
        # that instead - bounded to only the ~rejection-path symbols (not the whole universe)
        # so this doesn't multiply live-fetch volume on a full run. yf_market_cap_is_live=True
        # (FPI / >$50B-ceiling tiers) means this IS already a live number - no help there,
        # already the best signal available; keep it as-is and reject as before.
        if not yf_market_cap_is_live:
            live_mcap, _live_pe = self._fetch_live_fpi_yfinance_check_values(symbol)
            if live_mcap is not None:
                yf_market_cap = live_mcap
                ratio = max(market_cap, yf_market_cap) / min(market_cap, yf_market_cap)
                if ratio <= 10:
                    return
        logger.warning(
            f"[{symbol}] market_cap sanity check failed: SEC-derived=${market_cap:,.0f} vs "
            f"yfinance=${yf_market_cap:,.0f} (ratio {ratio:.0f}x) - shares_outstanding is "
            f"likely mis-scaled; nulling shares_outstanding-dependent fields"
        )
        for field in (
            "market_cap",
            "pb_ratio",
            "ps_ratio",
            "fcf_yield",
            "dividend_yield",
            "net_payout_yield",
            "enterprise_value",
            "ev_ebitda",
            "ev_revenue",
            "intrinsic_value_per_share",
            "margin_of_safety_pct",
        ):
            result[field] = None
        if result.get("reason") is None:
            result["reason"] = "shares_outstanding_scale_mismatch"
        # Mirror _compute_valuations' own "all key metrics null" consistency check (it already
        # ran once before this nulling and may have passed on a metric this method just
        # cleared) - re-evaluate so a row that's now genuinely all-NULL is correctly flagged
        # data_unavailable instead of silently claiming success with nothing but a symbol/price.
        key_metrics = [result.get("pe_ratio"), result.get("pb_ratio"), result.get("ps_ratio"), result.get("fcf_yield")]
        if all(m is None for m in key_metrics):
            result["data_unavailable"] = True

    # FIXED 2026-08-20 (goal: finance-accuracy audit, ONC follow-up): pe_ratio doesn't depend
    # on shares_outstanding (current_price / ttm_eps only), so _sanity_check_market_cap above
    # correctly leaves it untouched - but that also means a separately-mis-scaled ttm_eps
    # (a different SEC concept, same underlying class of per-filing XBRL scale bug) survives
    # completely unguarded. Live-confirmed: ONC (BeOne Medicines) still shows pe_ratio=1884.30
    # after the market_cap fix, vs yfinance's pe_ratio=67.58 for the same company - a ~28x
    # gap. A DB-wide scan found 38 symbols with a >10x pe_ratio mismatch against
    # yfinance_snapshot.pe_ratio. Same validity-check-only discipline as market_cap (never a
    # yfinance value substitution - see that method's docstring): nulls pe_ratio and its
    # sole dependent, peg_ratio, on a >10x disagreement.
    def _sanity_check_pe_ratio(
        self, symbol: str, result: dict[str, Any], yf_pe_ratio: float | None, yf_value_is_live: bool = False
    ) -> None:
        pe_ratio = result.get("pe_ratio")
        if pe_ratio is None or pe_ratio <= 0:
            return
        if yf_pe_ratio is None:
            return
        ratio = max(pe_ratio, yf_pe_ratio) / min(pe_ratio, yf_pe_ratio)
        if ratio <= 10:
            return
        # FIXED 2026-08-31 (goal: data-coverage sweep) - same frozen-yfinance_snapshot false-
        # positive fixed in _sanity_check_market_cap above (see that method's comment for the
        # full 66-symbol/AMRN evidence): pe_ratio moves with price just like market_cap does,
        # so an 7-8-week-stale comparison value is just as unreliable here. One bounded live
        # re-check before committing to a rejection.
        if not yf_value_is_live:
            _live_mcap, live_pe = self._fetch_live_fpi_yfinance_check_values(symbol)
            if live_pe is not None:
                yf_pe_ratio = live_pe
                ratio = max(pe_ratio, yf_pe_ratio) / min(pe_ratio, yf_pe_ratio)
                if ratio <= 10:
                    return
        logger.warning(
            f"[{symbol}] pe_ratio sanity check failed: SEC-derived={pe_ratio:.2f} vs "
            f"yfinance={yf_pe_ratio:.2f} (ratio {ratio:.0f}x) - ttm_eps is likely mis-scaled; "
            f"nulling pe_ratio/peg_ratio"
        )
        result["pe_ratio"] = None
        result["peg_ratio"] = None
        if result.get("reason") is None:
            result["reason"] = "eps_scale_mismatch"
        key_metrics = [result.get("pe_ratio"), result.get("pb_ratio"), result.get("ps_ratio"), result.get("fcf_yield")]
        if all(m is None for m in key_metrics):
            result["data_unavailable"] = True

    def _unavailable_marker(
        self,
        symbol: str,
        reason: str,
        total_debt: float | None = None,
        total_cash: float | None = None,
        ebitda: float | None = None,
    ) -> dict[str, Any]:
        """Return data_unavailable marker for symbol.

        total_debt/total_cash/ebitda are optional overrides (2026-08-19, goal session
        continuation): these three are pure balance-sheet/income-statement dollar figures
        that don't need shares_outstanding or current_price to compute, unlike every other
        field this marker nulls out - see fetch_incremental's "MOVED 2026-08-19" comment for
        why they're now computed before the gates that produce this marker. Callers that
        genuinely have nothing yet (e.g. "no_income_statement", before any balance-sheet
        query has even run) simply omit them and get the same all-NULL behavior as before.
        """
        return {
            "symbol": symbol,
            "computed_at": date.today().isoformat(),
            "data_unavailable": True,
            "reason": reason,
            "data_source": "none",
            # All metrics NULL except the three overridable ones above
            "current_price": None,
            "shares_outstanding": None,
            "market_cap": None,
            "total_debt": total_debt,
            "total_cash": total_cash,
            "enterprise_value": None,
            "ebitda": ebitda,
            "pe_ratio": None,
            "pb_ratio": None,
            "ps_ratio": None,
            "peg_ratio": None,
            "fcf_yield": None,
            "dividend_yield": None,
            "net_payout_yield": None,
            "ev_ebitda": None,
            "ev_revenue": None,
            "intrinsic_value_per_share": None,
            "margin_of_safety_pct": None,
        }


if __name__ == "__main__":
    sys.exit(run_loader(SecValuationsLoader, description="Compute valuations from SEC audited data"))
