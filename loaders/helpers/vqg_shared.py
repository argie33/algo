"""Constants and small pure functions shared between load_value_quality_growth_metrics.py
and its extracted compute mixins (vqg_value.py/vqg_quality.py/vqg_growth.py).

Lives in its own module with NO import of load_value_quality_growth_metrics (or anything
that imports it) specifically so any vqg_*.py mixin can import these at module level
without risking a circular import with the owner loader - see
vqg_and_stock_scores_dead_split_files_deleted_20260905 in memory for the exact
circular-import crash this separation avoids (a prior extraction imported shared names
from the owner module itself, which broke the moment the owner was run as a script rather
than imported as a package).

load_value_quality_growth_metrics.py re-imports every name here under the same name, so
`loaders.load_value_quality_growth_metrics.X` still resolves for existing callers/tests.
"""

import logging
from datetime import datetime, timezone
from typing import Any

import psycopg2

from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

# Full timestamp, not just date - a date-only value casts to midnight and makes the
# freshness monitor see stale data for hours after the actual load time.
_LOADER_RUN_TIMESTAMP: str | None = None


def get_loader_timestamp() -> str:
    """Get the current run timestamp (ISO format with time component).

    Initialized on first call to capture when the loader run() started.
    All rows written in this run will have the same timestamp for consistency.
    """
    global _LOADER_RUN_TIMESTAMP
    if _LOADER_RUN_TIMESTAMP is None:
        _LOADER_RUN_TIMESTAMP = datetime.now(timezone.utc).isoformat()
    return _LOADER_RUN_TIMESTAMP


def peg_ratio_reason_from_eps_history(
    eps_rows: list[tuple[Any, Any]], other_positive_eps: list[float] | None = None
) -> str:
    """Given the two most recent (fiscal_year, earnings_per_share) rows (newest first, both
    non-NULL EPS), decide why peg_ratio is unavailable when pe_ratio IS present.

    load_sec_valuations.py only computes peg_ratio when YoY EPS growth is positive (declining
    or newly-profitable earnings make PEG not meaningful, same "not applicable" class as
    unprofitable_stock/non_dividend_paying_stock elsewhere in this file) - distinguish that
    from a genuine <2-fiscal-years-on-file gap ("insufficient_history"), since scores.py's
    `_categorize_reason()` buckets them into different UI categories.

    Args:
        eps_rows: 0-2 (fiscal_year, earnings_per_share) tuples, already filtered to non-NULL
            EPS and ordered fiscal_year DESC (i.e. exactly what the caller's DB query returns).
        other_positive_eps: every OTHER real, positive fiscal-year EPS on file for this symbol
            (excluding prior_eps_for_growth itself) - only needed to replicate
            _compute_peg_ratio()'s own low-base-year rejection (see ADDED 2026-09-06 below).
    """
    if len(eps_rows) < 2:
        return "insufficient_history"
    ttm_eps_for_growth, prior_eps_for_growth = eps_rows[0][1], eps_rows[1][1]
    if prior_eps_for_growth is None or prior_eps_for_growth <= 0:
        return "negative_earnings_growth"
    if ttm_eps_for_growth is not None and ttm_eps_for_growth <= prior_eps_for_growth:
        return "negative_earnings_growth"
    # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, gap found while
    # cross-checking sec_valuations_ratios.py's _compute_peg_ratio against this function): a
    # prior session (see peg_ratio_low_base_effect in memory) fixed the VALUE side of the
    # GILD/AA-shaped bug (a real but anomalously low prior_year_eps - a one-off
    # litigation/impairment trough year - deflates peg_ratio toward zero via an artificially
    # huge growth_rate) by having _compute_peg_ratio return None instead of the wrong 0.01, but
    # never gave this reason function the matching label - every affected symbol still fell
    # through this function's own growth checks (which see the same "positive growth" data)
    # straight to the generic "missing_sec_data" (Missing SEC/XBRL data) instead of the correct
    # "peg_ratio_low_base_effect" (Legitimate / not applicable - the DATA is real, the ratio is
    # just not meaningful off that anchor year). Mirrors _compute_peg_ratio's exact math
    # (growth_rate > 300 pre-filter, median of >=2 other real positive EPS years, prior_year_eps
    # < 25% of that median) so this can only fire on the identical population the real
    # computation rejects.
    if other_positive_eps and ttm_eps_for_growth is not None:
        growth_rate = ((ttm_eps_for_growth - prior_eps_for_growth) / abs(prior_eps_for_growth)) * 100
        if growth_rate > 300 and len(other_positive_eps) >= 2:
            sorted_eps = sorted(other_positive_eps)
            mid = len(sorted_eps) // 2
            median_eps = sorted_eps[mid] if len(sorted_eps) % 2 else (sorted_eps[mid - 1] + sorted_eps[mid]) / 2
            if median_eps > 0 and prior_eps_for_growth < 0.25 * median_eps:
                return "peg_ratio_low_base_effect"
    return "missing_sec_data"


def intrinsic_value_reason_from_fcf_yield(fcf_yield: float | None, fcf_yield_reason: str | None = None) -> str:
    """Decide why intrinsic_value_per_share (the DCF result) is unavailable when it's NULL.

    fcf_yield being present does NOT imply FCF was positive (it only requires being within
    +/-1000% of market cap) - _compute_dcf_intrinsic_value's first gate is `fcf <= 0` (the
    2-stage FCFE model can't discount a cash-burning company), so fcf_yield <= 0 must map to
    "negative_free_cash_flow", not a generic "implausible_dcf_result".

    Args:
        fcf_yield: sec_valuations.fcf_yield for this symbol (same sign as the FCF that fed
            the DCF, since both derive from the same ocf - capex over the same positive
            market_cap).
        fcf_yield_reason: the already-computed fcf_yield_unavailable_reason for this symbol
            (e.g. "capex_never_tagged_in_recent_filings", "no_recent_free_cash_flow_reported")
            when fcf_yield is None - propagate this specific reason instead of collapsing to
            the generic "missing_cash_flow_data" label; that label is only a fallback when no
            specific reason is available (e.g. direct callers/tests).
    """
    if fcf_yield is None:
        return fcf_yield_reason or "missing_cash_flow_data"
    if fcf_yield <= 0:
        return "negative_free_cash_flow"
    return "implausible_dcf_result"


# Sanity bound for the 4 percentage-point-delta trend fields (gross/operating/net margin
# trend, ROE trend), stored in NUMERIC(10,4) columns. A near-zero prior-year denominator
# (equity/revenue crossing from negative to barely-positive) makes the delta mathematically
# enormous despite being a real computation - treat as unavailable rather than let it
# overflow the column and roll back the entire 3-table write for that symbol.
MAX_TREND_PERCENTAGE_POINTS = 100_000.0

# Plausibility bound for growth-RATE fields (distinct from the margin/ROE trend fields
# above, which are percentage-POINT deltas bounded by the 0-100% margin range and stay on
# MAX_TREND_PERCENTAGE_POINTS). A near-zero prior-period denominator can produce
# mathematically enormous but meaningless growth rates; genuine hypergrowth small-caps can
# hit a few hundred percent but essentially never four or five digits.
MAX_PLAUSIBLE_GROWTH_PCT = 2_000.0

# Sanity bound for absolute-dollar fields (free_cash_flow, operating_cash_flow, total_debt,
# total_cash, ebitda), stored in NUMERIC(15,2) columns (max abs value < 10^13). Foreign
# filers reporting in local currency (e.g. VND/KRW) can overflow this column if a value
# isn't converted to USD before reaching this file, which would abort the entire 3-table
# write transaction for that symbol - mark implausible values unavailable instead of
# crashing on them, as a safety net independent of any particular currency-conversion bug.
MAX_ABSOLUTE_DOLLAR_VALUE = 1_000_000_000_000.0  # $1 trillion - no real company in this universe exceeds this for any single one of these fields

# Computed once in _compute_quality_metrics (needs balance-sheet data _compute_growth_metrics
# doesn't have), then mirrored into growth_dict in fetch_incremental - see that call site for
# why quality_metrics and growth_metrics each carry their own copy of the same values.
# These are computed from quarterly data in _compute_quarterly_metrics() (which is called
# from _compute_quality_metrics), and must be propagated to growth_metrics via this list
# to avoid dropping quarterly-derived metrics that growth_metrics doesn't compute on its own.
_SHARED_TREND_FIELDS = (
    "net_income_growth_yoy",
    "operating_income_growth_yoy",
    "gross_margin_trend",
    "operating_margin_trend",
    "net_margin_trend",
    "roe_trend",
    "sustainable_growth_rate",
    "quarterly_growth_momentum",
    "fcf_growth_yoy",
    "ocf_growth_yoy",
    "asset_growth_yoy",
    "consecutive_positive_quarters",
    "earnings_growth_4q_avg",
    "eps_growth_stability",
    "earnings_surprise_avg",
    "earnings_beat_rate",
)

# Subset of _SHARED_TREND_FIELDS sourced from _compute_quarterly_metrics() (quarterly
# income-statement history), not the annual balance-sheet ratios the rest of quality_metrics
# computes - see compute_quality_row_level_reason()'s docstring below.
_QUARTERLY_DERIVED_TREND_FIELDS = (
    "quarterly_growth_momentum",
    "consecutive_positive_quarters",
    "earnings_growth_4q_avg",
    "eps_growth_stability",
    "earnings_surprise_avg",
    "earnings_beat_rate",
)


def compute_quality_row_level_reason(
    symbol: str,
    stockholders_equity: float | None,
    total_assets: float | None,
    etf_trust_symbols: frozenset[str],
    unsupported_currency_symbols: frozenset[str],
    no_recent_equity_symbols: frozenset[str],
    never_tagged_equity_symbols: frozenset[str],
    no_recent_total_assets_symbols: frozenset[str],
    never_tagged_total_assets_symbols: frozenset[str],
    reit_or_special_entity_no_balance_data_symbols: frozenset[str] = frozenset(),
) -> str | None:
    """Row-level reason for _compute_quality_metrics's "all core ratios None" early return.
    Extracted out of vqg_quality.py (2026-09-09, file-size ratchet: that file is past the
    hard ceiling and cannot grow) - pure function, gate symbol sets passed in rather than
    fetched via self so this has no DB/mixin dependency.

    "etf_trust_no_gaap_financials" (ADDED 2026-09-05): GLD/SLV/... file a "Statement of
    Assets and Liabilities" with no GAAP stockholders_equity concept at all.

    "unsupported_currency_no_fx_rate" (ADDED 2026-09-06): an FPI tagging Assets/Equity only
    under an unsupported currency (e.g. ARS) has a real, non-fabricatable None, not a gap.

    "no_recent_balance_sheet_data_reported": genuine "never tagged, real extraction gap".

    "reit_special_entity" (FIXED 2026-09-10, goal: "under 500" missing-XBRL push): checked
    BEFORE the generic no_recent_balance_sheet_data_reported fallback whenever the balance-
    sheet loader itself already recorded zero SEC filings for this symbol as a REIT/special-
    entity structural fact (see _get_reit_or_special_entity_no_balance_data_symbols's
    docstring in vqg_quality_recategorize.py) - live-confirmed BIOT/IMC/PSQL/RPGL.

    "zero_total_assets_reported_shell_entity" (FIXED 2026-09-05): a real reported $0.00
    total_assets/stockholders_equity (blank-check/shell pre-merger, e.g. OBX) trips the same
    `all(... is None)` check via division-by-zero-shaped ratios, not a data gap - a known
    business fact, same "Legitimate / not applicable" class as reit_special_entity.

    Callers must NOT apply this reason to _QUARTERLY_DERIVED_TREND_FIELDS - those fields'
    unavailability (if any) comes from a completely different input (quarterly income
    statement history, via _compute_quarterly_metrics), already diagnosed with its own
    specific reason (e.g. "foreign_private_issuer_no_quarterly_filings") before this
    function ever runs; overwriting it here would be the same class of bug this function's
    own 2026-09-09 extraction fixed (see caller's own comment for the live-confirmed symbols).
    """
    if stockholders_equity is None and symbol in etf_trust_symbols:
        return "etf_trust_no_gaap_financials"
    if stockholders_equity is None and symbol in unsupported_currency_symbols:
        return "unsupported_currency_no_fx_rate"
    if stockholders_equity is None and symbol in reit_or_special_entity_no_balance_data_symbols:
        return "reit_special_entity"
    if stockholders_equity is None and (symbol in no_recent_equity_symbols or symbol in never_tagged_equity_symbols):
        return "no_recent_balance_sheet_data_reported"
    if (
        total_assets is not None
        and total_assets <= 0
        and (symbol in no_recent_total_assets_symbols or symbol in never_tagged_total_assets_symbols)
    ):
        return "zero_total_assets_reported_shell_entity"
    return None


_BS_CURRENCY_TOTAL_ASSETS_FIELDS = ("roa", "asset_turnover", "debt_to_assets", "gross_profitability")
_BS_CURRENCY_TOTAL_ASSETS_SOURCE_REASONS = frozenset({"no_recent_total_assets_reported", "missing_sec_data"})
# ADDED 2026-09-11 (goal: "under 300" push, same re-audit that found total_debt/roce_pct
# above): operating_profitability's own reason chain (vqg_quality_reasons_profitability.py)
# sets "stockholders_equity_not_reported" whenever stockholders_equity is None for a symbol
# in _get_no_recent_stockholders_equity_symbols()/_get_never_tagged_stockholders_equity_
# symbols() - the exact same source reason roe/debt_to_equity already get recategorized from,
# just never added to this tuple. Live-confirmed CEPU/IRS/LOMA (Argentine 40-F filers): roe/
# debt_to_equity on the same row already correctly show "unsupported_currency_no_fx_rate"
# while operating_profitability stayed on the generic reason.
_BS_CURRENCY_EQUITY_FIELDS = ("roe", "debt_to_equity", "sustainable_growth_rate", "operating_profitability")
_BS_CURRENCY_EQUITY_SOURCE_REASONS = frozenset({"stockholders_equity_not_reported", "missing_sec_data"})
# ADDED 2026-09-11 (goal: "under 300" push, total_debt_not_itemized re-investigation): debt_to_
# equity above was already covered (it needs stockholders_equity), but the standalone total_debt
# field itself - and roce_pct, which fails the same way whenever its own total_debt lookup is
# what's missing - were never added, so a confirmed unsupported-currency-balance-sheet symbol
# (live-confirmed CEPU/CRESY/IRS/LOMA/BMA, all ARS 20-F/40-F filers already recognized by
# _get_unsupported_currency_balance_sheet_symbols()) still got the generic "total_debt_not_
# itemized" for these two fields specifically instead of the real "unsupported_currency_no_fx_
# rate" cause every sibling equity/total-assets-derived field on the same row already carries.
# Same "Missing SEC/XBRL data" category either way (doesn't move the coverage headline) - this
# is a reason-accuracy fix, not a category recategorization like the royalty-trust/royalty-
# streaming checks.
_BS_CURRENCY_DEBT_FIELDS = ("total_debt", "roce_pct")
_BS_CURRENCY_DEBT_SOURCE_REASONS = frozenset({"total_debt_not_itemized", "missing_sec_data"})


def recategorize_balance_sheet_currency_fields(metrics: dict[str, Any]) -> None:
    """Mutates `metrics` in place: for a symbol already confirmed as
    _get_unsupported_currency_balance_sheet_symbols()-shaped (an FPI whose Assets/equity is
    only tagged under a hyperinflationary/unsupported currency, e.g. CRESY's Assets tagged
    only under ARS - live-confirmed via real SEC companyfacts JSON), overrides each
    total_assets/stockholders_equity-derived field's generic unavailable_reason with the
    real, specific "unsupported_currency_no_fx_rate" cause.

    ADDED 2026-09-09 (goal: "SEC/XBRL missing data under 500" sweep). Extracted into this
    module rather than inlined in vqg_quality.py (file-size ratchet: that file is past the
    hard ceiling and cannot grow) - same discipline as compute_quality_row_level_reason
    above. That row-level function already covers this cause for the "all core ratios None"
    early return, but a symbol with SOME other ratio available (CRESY has operating_margin/
    net_margin from its income statement, needing neither total_assets nor
    stockholders_equity) skips that early return entirely, so its individual per-field
    reasons never got the same treatment - same reason-string-doesn't-match-real-cause bug
    class as the sibling OCF recategorize loop in vqg_quality.py this mirrors. Only overrides
    a generic fallback reason on a field whose value is still None - never a real computed
    value or a more specific already-set reason.
    """
    for field in _BS_CURRENCY_TOTAL_ASSETS_FIELDS:
        reason_key = f"{field}_unavailable_reason"
        if metrics.get(field) is None and metrics.get(reason_key) in _BS_CURRENCY_TOTAL_ASSETS_SOURCE_REASONS:
            metrics[reason_key] = "unsupported_currency_no_fx_rate"

    for field in _BS_CURRENCY_EQUITY_FIELDS:
        reason_key = f"{field}_unavailable_reason"
        if metrics.get(field) is None and metrics.get(reason_key) in _BS_CURRENCY_EQUITY_SOURCE_REASONS:
            metrics[reason_key] = "unsupported_currency_no_fx_rate"

    for field in _BS_CURRENCY_DEBT_FIELDS:
        reason_key = f"{field}_unavailable_reason"
        if metrics.get(field) is None and metrics.get(reason_key) in _BS_CURRENCY_DEBT_SOURCE_REASONS:
            metrics[reason_key] = "unsupported_currency_no_fx_rate"


def acquire_pooled_connection(table_name: str) -> Any:
    """Acquire one pooled DB connection for a whole loader run and register it for reuse.

    PERF FIX (goal session 20260908, "optimize all loading activity"): pulled out of
    load_value_quality_growth_metrics.py's run() to keep that file's line count under the
    file-size ratchet's hard ceiling - see its call site for the full rationale (that loader
    fully overrides OptimalLoader.run() and never got the base class's pooled-connection
    setup, so every `with DatabaseContext(...)` inside fetch_incremental() was opening a
    brand new physical psycopg2 connection - confirmed up to ~13x per symbol across ~5,100
    symbols). Mirrors OptimalLoader.run()'s own PooledConnectionManager/set_pooled_connection
    pair exactly; DatabaseContext.__enter__ transparently reuses whatever this sets via
    get_pooled_connection(). Pair with release_pooled_connection() in a finally block.
    """
    from utils.db.pooled_connection_manager import PooledConnectionManager
    from utils.db.pooled_context_var import set_pooled_connection

    conn_manager = PooledConnectionManager(table_name)
    set_pooled_connection(conn_manager.acquire())
    return conn_manager


def release_pooled_connection(conn_manager: Any) -> None:
    """Release a connection acquired via acquire_pooled_connection(). Safe to call with None."""
    from utils.db.pooled_context_var import set_pooled_connection

    set_pooled_connection(None)
    if conn_manager is not None:
        conn_manager.release()


# MOVED HERE (goal session 20260908, "optimize/shrink monoliths"): these 3 frozensets plus
# SectorIndustryCacheMixin below used to live directly in load_value_quality_growth_metrics.py,
# which is already past the file-size ratchet's 2000-line hard ceiling (no further growth
# accepted there, only extraction - see check_file_size_ratchet.py). Pure move, no behavior
# change: load_value_quality_growth_metrics.py re-imports all 3 names under the same name (like
# every other constant in this module), and _owner().DEPOSITORY_BANK_INDUSTRIES etc. in
# vqg_quality.py/vqg_quality_batch.py keep resolving through that re-export unchanged.

# SIC-derived company_profile.industry values covering depository institutions (commercial
# banks, savings institutions/thrifts) - a strict subset of the "Financial Services" sector.
# FIXED 2026-09-06 (stock_scores symbol spot-check, see
# stock_scores_symbol_spotcheck_20260906/bank_deposit_debt_to_equity_gap_fixed_20260906 in
# memory): debt_for_roic (interest-bearing debt: long_term_debt/total_debt_ev) structurally
# excludes customer deposits, because SEC filers tag deposits under concepts this pipeline
# doesn't map to "long_term_debt". For an operating company that's the right call (Total
# Liabilities/Equity is a bad debt proxy - see this file's own "NOT Total Liabilities / Equity"
# comment - because it's contaminated by AP/accrued expenses/deferred revenue). For a
# depository institution, deposits ARE the core interest-bearing liability funding its loan
# book, so excluding them isn't a narrower, more precise "debt" figure - it's missing most of
# the bank's real leverage, and disproportionately so for small banks with little wholesale
# borrowing (live-verified: TCBX/PEBK's debt_to_equity computed near 0.11-0.12, inflating both
# debt_to_equity_score and ROCE's capital_employed-based return for exactly this cohort -
# Financial Services quality_score averaged 53.5 vs the universe's ~38-44, and small commercial
# banks took 14/20 of the day's top BUY signals by composite_score). AP/accrued/deferred-revenue
# contamination that makes total_liabilities a bad proxy for an operating company is a rounding
# error against a bank's deposit base, so total_liabilities is the better proxy here - narrowly
# scoped to this industry list (not the whole Financial Services sector, which also includes
# payment networks/asset managers/insurance brokers whose liabilities aren't deposit-shaped -
# see INSURANCE_UNDERWRITER_INDUSTRIES just below for the separate, analogous fix for
# risk-bearing insurers, whose core liability is loss reserves, not deposits) via
# _get_symbol_industry(), a sibling of _get_symbol_sector() with the same fail-open contract.
DEPOSITORY_BANK_INDUSTRIES = frozenset(
    {
        "State Commercial Banks",
        "National Commercial Banks",
        "Commercial Banks, NEC",
        "Savings Institution, Federally Chartered",
        "Savings Institutions, Not Federally Chartered",
        "Functions Related To Depository Banking, NEC",
    }
)

# SIC-derived company_profile.industry values covering risk-bearing insurance underwriters -
# same bug class as DEPOSITORY_BANK_INDUSTRIES above, found the same session while checking why
# Financial Services still dominated the top of composite_score after the bank fix landed.
# An underwriter's core liability is policy/loss reserves and unearned premium - functionally
# its "debt" (the capital it owes against future claims), same role deposits play for a bank -
# but SEC filers tag reserves under concepts this pipeline doesn't map to "long_term_debt"
# either, so debt_for_roic understates underwriters' real leverage the same way. Live-verified
# against annual_balance_sheet.total_liabilities/stockholders_equity: RGA (Reinsurance Group of
# America) computed debt_to_equity=0.42 vs a real ~11.5x; ACGL (Arch Capital)=0.01 vs ~2.5x;
# HIG (Hartford)=0.24 vs ~3.5x - all in the "Fire, Marine & Casualty Insurance"/"Life Insurance"
# SIC buckets. Confirmed narrowly scoped, not the whole insurance-adjacent space: "Insurance
# Agents, Brokers & Service" (non-risk-bearing intermediaries who don't hold reserves - MRSH/AON
# both show real 1.4-1.7x debt_to_equity already, genuine corporate bonds, not understated)
# deliberately excluded.
INSURANCE_UNDERWRITER_INDUSTRIES = frozenset(
    {
        "Fire, Marine & Casualty Insurance",
        "Life Insurance",
        "Accident & Health Insurance",
        "Surety Insurance",
        "Title Insurance",
        "Insurance Carriers, NEC",
    }
)

# SIC-derived company_profile.industry values covering regulated rate-base utilities - same bug
# class as DEPOSITORY_BANK_INDUSTRIES/INSURANCE_UNDERWRITER_INDUSTRIES above, found the same
# session while sanity-checking Quality scores across a broader known-symbol set (goal: stock_scores
# factor/composite sanity audit). A regulated utility's enormous rate-base asset structure
# structurally compresses ROA/ROCE and requires more leverage than a typical industrial by design
# (regulators set allowed ROE against a rate base financed partly by debt) - live-verified across
# 10 electric utilities (NEE/DUK/SO/D/AEP/EXC/XEL/WEC/ED/PEG): ROA clustered 2.37-3.67% (industrial
# curve's (3.0,40)/(8.0,80)/(15.0,100) floors nearly all of them near the bottom), debt_to_equity
# clustered 1.11-1.91x (industrial curve's 2.0-floors-to-0 crushes every one of them toward zero),
# ROCE clustered 3.96-7.23%. Water/gas distribution utilities (CWT/OGS/WTRG/YORW/ARTNA/NGG)
# independently confirmed the same 2.26-3.17% ROA/0.71-1.42x D/E range - same regulated-rate-base
# economics, included here; midstream/pipeline gas transmission names (WMB/AROC) were spot-checked
# and show materially different (healthier, unregulated-economics) ROA/quality already, deliberately
# excluded pending their own evidence. fcf_margin_score is also excluded for this group (same
# "raw value kept, not scored" treatment as DEPOSITORY_BANK_INDUSTRIES) - heavy, continuous grid/
# generation capex routinely drives utility FCF margin deeply negative (NEE -42%, XEL -46%, D -44%
# live-confirmed) even for fundamentally healthy, dividend-growing utilities, the same "raw ratio
# reflects an unrelated structural cash-flow pattern, not real operating profitability" problem
# fcf_margin has for depository banks.
UTILITY_INDUSTRIES = frozenset(
    {
        "Electric Services",
        "Electric & Other Services Combined",
        "Water Supply",
        "Natural Gas Distribution",
    }
)


class SectorIndustryCacheMixin:
    """Lazy, once-per-run symbol->sector/industry caches shared by the value/quality/growth mixins.

    Extracted from load_value_quality_growth_metrics.py (see MOVED HERE comment above) - added
    to ValueQualityGrowthMetricsLoader's base classes so self._get_symbol_sector/_get_symbol_industry
    keep resolving exactly as before for every mixin that calls them.
    """

    def _get_symbol_sector(self, symbol: str) -> str | None:
        """Lazily fetches and caches symbol -> company_profile.sector (GICS) once per loader
        run, reused across every _compute_quality_metrics call (no per-symbol query).

        Financial Services and Real Estate get a 7-input variant of quality_score (see
        quality_components below) that drops asset_turnover_score - Revenue/Total Assets isn't a
        coherent "operating efficiency" measure for a bank's loan book or a REIT's portfolio the
        way it is for an operating company (confirmed via isolated testing, matches Fama-French's
        practice of excluding financials from similar factor constructions).

        Returns None (falls through to the universal formula) if the sector map can't be
        fetched or the symbol isn't in company_profile - fails open to the well-tested
        universal formula rather than silently miscategorizing a symbol."""
        if not hasattr(self, "_sector_cache"):
            self._sector_cache: dict[str, str] = {}
            try:
                with DatabaseContext("read") as cur:
                    cur.execute("SELECT symbol, sector FROM company_profile WHERE sector IS NOT NULL")
                    self._sector_cache = dict(cur.fetchall())
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.warning(
                    f"[QUALITY_METRICS] Failed to fetch company_profile sector map for the "
                    f"sector-conditional Quality formula - falling back to the universal "
                    f"8-input formula for every symbol this run: {e}"
                )
        return self._sector_cache.get(symbol)

    def _get_symbol_industry(self, symbol: str) -> str | None:
        """Lazily fetches and caches symbol -> company_profile.industry (SIC-derived) once per
        loader run, sibling to _get_symbol_sector above with the same caching/fail-open
        contract (see DEPOSITORY_BANK_INDUSTRIES for why this is a separate, narrower lookup
        than sector: depository institutions need a debt_for_roic override that the rest of
        the broader Financial Services sector - payment networks, asset managers, insurers -
        must not get).

        Returns None (falls through to the universal debt_for_roic) if the industry map can't
        be fetched or the symbol isn't in company_profile."""
        if not hasattr(self, "_industry_cache"):
            self._industry_cache: dict[str, str] = {}
            try:
                with DatabaseContext("read") as cur:
                    cur.execute("SELECT symbol, industry FROM company_profile WHERE industry IS NOT NULL")
                    self._industry_cache = dict(cur.fetchall())
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.warning(
                    f"[QUALITY_METRICS] Failed to fetch company_profile industry map for the "
                    f"depository-bank debt_for_roic override - falling back to the universal "
                    f"debt figure for every symbol this run: {e}"
                )
        return self._industry_cache.get(symbol)
