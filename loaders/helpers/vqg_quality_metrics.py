"""_compute_quality_metrics, extracted from load_value_quality_growth_metrics.py (2026-09-04,
"still too bloated after the mega-bloater cleanup" pass): this single method was ~2,500 of the
file's ~5,700 lines - by far the largest remaining concentration, dwarfing the 39 gates already
pulled out into vqg_symbol_gates.py. Moved verbatim (only the 3 module-level lookups below were
touched) - every fix-history comment/live-verified sample count/bound is preserved byte-for-byte.

2026-09-04 follow-up pass: the moved-but-not-decomposed 2,490-line function body was itself a
known anti-pattern (relocating code isn't the same as simplifying it) - split, via a pure
extract-method refactor with NO behavior change, into this orchestrator plus four sibling
files, one per natural seam: vqg_quality_ratios.py (QualityRatiosMixin - margins/liquidity/
interest-coverage, ROIC/ROCE/debt-to-equity), vqg_quality_growth.py (QualityGrowthMixin -
cash-flow ratios, YoY growth/trend fields, SGR), vqg_quality_score.py (QualityScoreMixin - the
composite quality_score + its phase-3 ratio fields), vqg_quality_reasons.py
(QualityReasonsMixin - `*_unavailable_reason` assembly + royalty-trust recategorization). Each
helper mutates the shared `metrics`/`failed_metrics`/`implausible_ratio_metrics` (etc.) the
caller continues to use, returning only the extra flags a later block needs - every value
purely local to a block in the original code stays local to its new method. This
orchestrator's own control flow is unchanged from the original.

Mixed into ValueQualityGrowthMetricsLoader via multiple inheritance - every `self.` call here
(the 39 SymbolGateMixin gates, _fetch_annual_fallback_row/_fetch_balance_sheet_anchor_fallback/
_has_recent_dividend_history, _ratio_with_implausible_fallback, _get_symbol_sector, etc.)
resolves normally through the instance regardless of which file defines it.

DatabaseContext is deliberately NOT imported at module level here, for the exact reason
documented in vqg_symbol_gates.py: dozens of existing unit tests monkeypatch
`loaders.load_value_quality_growth_metrics.DatabaseContext` directly, and a module-level import
here would bind its own copy those patches can't reach. MAX_ABSOLUTE_DOLLAR_VALUE/
MAX_PLAUSIBLE_GROWTH_PCT/MAX_TREND_PERCENTAGE_POINTS/get_loader_timestamp are NOT
test-monkeypatched anywhere, so those are imported directly - safe as long as this module is
only imported by the owner module AFTER those names are defined in it (see the import site in
load_value_quality_growth_metrics.py). The four sibling helper files deliberately do NOT import
these constants themselves (to avoid spreading this import-ordering constraint further) - this
module passes them through as plain function arguments instead.
"""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from loaders.helpers.vqg_quality_growth import QualityGrowthMixin
from loaders.helpers.vqg_quality_ratios import QualityRatiosMixin
from loaders.helpers.vqg_quality_reasons import QualityReasonsMixin
from loaders.helpers.vqg_quality_score import QualityScoreMixin
from loaders.helpers.vqg_symbol_gates import SymbolGateMixin
from loaders.load_value_quality_growth_metrics import (
    MAX_ABSOLUTE_DOLLAR_VALUE,
    MAX_PLAUSIBLE_GROWTH_PCT,
    MAX_TREND_PERCENTAGE_POINTS,
    get_loader_timestamp,
)
from utils.type_conversion import safe_float

logger = logging.getLogger("loaders.load_value_quality_growth_metrics")


def _owner() -> Any:
    from loaders import load_value_quality_growth_metrics as _owner_mod

    return _owner_mod


@dataclass
class ExtractedQualityFields:
    """Raw fields parsed out of `quality_row` (+ its NaN/None guards and balance-sheet-anchor
    fallbacks), returned by `_extract_quality_row_fields`. One field per named local variable
    the original inline code built from `quality_row` - see that method's own comments for the
    fallback reasoning behind each.
    """

    stockholders_equity: float | None
    total_liabilities: float | None
    total_assets: float | None
    net_income: float | None
    revenue: float | None
    operating_income: float | None
    current_assets: float | None
    current_liabilities: float | None
    inventory: float | None
    interest_expense: float | None
    pretax_income: float | None
    interest_coverage_operating_income: float | None
    interest_coverage_pretax_income: float | None
    shares_outstanding: float | None
    cost_of_revenue: float | None
    operating_cash_flow: float | None
    free_cash_flow: float | None
    dividends_paid: float | None
    earnings_per_share: float | None
    prior_year_eps: float | None
    prior_year_revenue: float | None
    gross_profit_direct: float | None
    long_term_debt_bs: float | None
    cash_and_equivalents_bs: float | None
    income_tax_expense: float | None
    prior_year_net_income: float | None
    prior_year_operating_income: float | None
    prior_year_operating_cash_flow: float | None
    prior_year_free_cash_flow: float | None
    prior_year_cost_of_revenue: float | None
    prior_year_total_assets: float | None
    prior_year_stockholders_equity: float | None
    prior_year_pretax_income: float | None
    prior_year_interest_expense: float | None
    prior_year_gross_profit: float | None
    prior_year_dividends_paid: float | None
    dividends_paid_with_prior_year_fallback: float | None
    prior_year_operating_income_for_trend: float | None


class QualityMetricsMixin(
    QualityRatiosMixin,
    QualityGrowthMixin,
    QualityScoreMixin,
    QualityReasonsMixin,
    SymbolGateMixin,
):
    """`_compute_quality_metrics`, decomposed into named helper methods across this file and
    its four siblings (see module docstring). Inherits SymbolGateMixin (also a base of
    ValueQualityGrowthMetricsLoader itself - a diamond, harmless since it's the same class both
    times) purely so mypy can see the 39 `_get_*_symbols` gate methods called via `self.`; the
    handful of other cross-mixin members (defined directly on ValueQualityGrowthMetricsLoader,
    which doesn't exist as a type this file can import without a real circular import) are
    declared type-checking-only below.
    """

    if TYPE_CHECKING:
        _ROYALTY_TRUST_NO_BALANCE_SHEET_SYMBOLS: frozenset[str]

        def _nan_to_none(self, value: float | None) -> float | None: ...

        def _unavailable_marker(self, table: str, symbol: str, reason: str | None = None) -> dict[str, Any]: ...

        def _fetch_annual_fallback_row(
            self, table: str, columns: str, extra_where: str, symbol: str
        ) -> tuple[Any, ...] | None: ...

        def _fetch_balance_sheet_anchor_fallback(self, symbol: str, column: str) -> float | None: ...

        def _has_recent_dividend_history(self, symbol: str) -> bool: ...

        def _ratio_with_implausible_fallback(
            self,
            symbol: str,
            numerator: float | None,
            denominator: float | None,
            numerator_field: str,
            denominator_field: str,
            *,
            denominator_must_be_positive: bool = False,
        ) -> tuple[float | None, bool]: ...

        def _get_symbol_sector(self, symbol: str) -> str | None: ...

        def _compute_quarterly_metrics(self, symbol: str) -> dict[str, Any]: ...

        def _margin_curve(self, value: float, breakpoints: list[tuple[float, float]]) -> float: ...

        def _weighted_avg(
            self, components: list[tuple[float | None, float]], min_weight_pct: float = 0.0
        ) -> float | None: ...

    def _extract_quality_row_fields(self, symbol: str, quality_row: Any) -> ExtractedQualityFields:
        """Parse `quality_row` into named, NaN/None-guarded fields, applying the
        balance-sheet-anchor and same-fiscal-year fallbacks that don't depend on any other
        metric's computation. Identical to the original inline code.
        """
        stockholders_equity = self._nan_to_none(
            safe_float(quality_row[0], f"{symbol}.stockholders_equity", allow_none=True)
        )
        # The anchor balance-sheet row (quality_row[0]) can have stockholders_equity NULL
        # even though a nearby fiscal year has a real value - ROE/sustainable_growth_rate
        # need the same 3-year-window-then-full-history fallback search already used
        # elsewhere in this file (roic_pct/roce_pct/debt_to_equity get it via
        # roic_stockholders_equity below).
        # The anchor balance-sheet row (quality_row[0]) can have stockholders_equity NULL
        # even though a nearby fiscal year has a real value - ROE/sustainable_growth_rate
        # need the same 3-year-window-then-full-history fallback search already used
        # elsewhere in this file (roic_pct/roce_pct/debt_to_equity get it via
        # roic_stockholders_equity below). Same fallback pattern applies to
        # total_liabilities/total_assets/current_assets/current_liabilities below.
        if stockholders_equity is None:
            stockholders_equity = self._fetch_balance_sheet_anchor_fallback(symbol, "stockholders_equity")
        total_liabilities = self._nan_to_none(
            safe_float(quality_row[1], f"{symbol}.total_liabilities", allow_none=True)
        )
        if total_liabilities is None:
            total_liabilities = self._fetch_balance_sheet_anchor_fallback(symbol, "total_liabilities")
        total_assets = self._nan_to_none(safe_float(quality_row[2], f"{symbol}.total_assets", allow_none=True))
        if total_assets is None:
            total_assets = self._fetch_balance_sheet_anchor_fallback(symbol, "total_assets")
        net_income = self._nan_to_none(safe_float(quality_row[3], f"{symbol}.net_income", allow_none=True))
        revenue = self._nan_to_none(safe_float(quality_row[4], f"{symbol}.revenue", allow_none=True))
        operating_income = self._nan_to_none(safe_float(quality_row[5], f"{symbol}.operating_income", allow_none=True))
        current_assets = self._nan_to_none(safe_float(quality_row[6], f"{symbol}.current_assets", allow_none=True))
        if current_assets is None:
            current_assets = self._fetch_balance_sheet_anchor_fallback(symbol, "current_assets")
        current_liabilities = self._nan_to_none(
            safe_float(quality_row[7], f"{symbol}.current_liabilities", allow_none=True)
        )
        if current_liabilities is None:
            current_liabilities = self._fetch_balance_sheet_anchor_fallback(symbol, "current_liabilities")
        inventory = self._nan_to_none(safe_float(quality_row[9], f"{symbol}.inventory", allow_none=True))
        interest_expense = self._nan_to_none(safe_float(quality_row[10], f"{symbol}.interest_expense", allow_none=True))
        pretax_income = self._nan_to_none(safe_float(quality_row[23], f"{symbol}.pretax_income", allow_none=True))
        # quality_row is ONE joined row for a single fiscal_year (chosen to prioritize FCF
        # availability - see the ORDER BY above), so interest_expense/operating_income/
        # pretax_income can be NULL together even when an older year has all three - search
        # across years below rather than mixing an anchor value with a fallback from a
        # different year. EBIT = Pretax Income + Interest Expense is used as a fallback
        # numerator when a filer never tags OperatingIncomeLoss at all (some real filers
        # never do, not a missing-year issue).
        interest_coverage_operating_income = operating_income
        interest_coverage_pretax_income = pretax_income
        _interest_expense_invalid = interest_expense is None or interest_expense <= 0
        # A filer can have a valid current-year interest_expense while only operating_income/
        # pretax_income are missing for that specific anchor year - trigger the fallback
        # search on either condition, not just interest_expense itself.
        _income_inputs_missing = interest_coverage_operating_income is None and interest_coverage_pretax_income is None
        if _interest_expense_invalid or _income_inputs_missing:
            # `data_unavailable IS NOT TRUE` (applied inside the helper) prevents an
            # incomplete/unfiled fiscal year's stub value from being picked up as the real
            # figure.
            fallback_ie_row = self._fetch_annual_fallback_row(
                "annual_income_statement",
                "interest_expense, operating_income, pretax_income",
                "AND interest_expense IS NOT NULL AND interest_expense > 0 "
                "AND (operating_income IS NOT NULL OR pretax_income IS NOT NULL)",
                symbol,
            )

            if fallback_ie_row:
                # Only overwrite interest_expense itself when IT was the reason this
                # fallback fired - WELL-style callers already have a real, current-year
                # interest_expense and must keep it, not silently swap in a prior year's
                # (which would mix a current-year denominator with a stale numerator).
                if _interest_expense_invalid:
                    interest_expense = self._nan_to_none(
                        safe_float(fallback_ie_row[0], f"{symbol}.interest_expense_fallback_year", allow_none=True)
                    )
                interest_coverage_operating_income = self._nan_to_none(
                    safe_float(fallback_ie_row[1], f"{symbol}.operating_income_fallback_year", allow_none=True)
                )
                interest_coverage_pretax_income = self._nan_to_none(
                    safe_float(fallback_ie_row[2], f"{symbol}.pretax_income_fallback_year", allow_none=True)
                )

        if interest_coverage_operating_income is None and interest_coverage_pretax_income is not None:
            # EBIT approximation fallback - see comment above.
            interest_coverage_operating_income = interest_coverage_pretax_income + (interest_expense or 0)
        shares_outstanding = self._nan_to_none(
            safe_float(quality_row[11], f"{symbol}.shares_outstanding", allow_none=True)
        )
        cost_of_revenue = self._nan_to_none(safe_float(quality_row[12], f"{symbol}.cost_of_revenue", allow_none=True))
        operating_cash_flow = self._nan_to_none(
            safe_float(quality_row[13], f"{symbol}.operating_cash_flow", allow_none=True)
        )
        free_cash_flow = self._nan_to_none(safe_float(quality_row[14], f"{symbol}.free_cash_flow", allow_none=True))
        dividends_paid = self._nan_to_none(safe_float(quality_row[15], f"{symbol}.dividends_paid", allow_none=True))
        # The shared query's `acf.data_unavailable = FALSE` JOIN condition discards
        # dividends_paid whenever the row is flagged incomplete_sec_filing_cashflow (missing
        # operating_cash_flow flags the WHOLE row), even when dividends_paid itself was
        # extracted fine. Recover it directly for the SAME fiscal year as the anchor row -
        # never mixes years, and operating_cash_flow/free_cash_flow correctly stay None.
        if dividends_paid is None:
            with _owner().DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT dividends_paid FROM annual_cash_flow
                    WHERE symbol = %s AND fiscal_year = %s AND dividends_paid IS NOT NULL
                    """,
                    (symbol, quality_row[8]),
                )
                same_year_dividends_row = cur.fetchone()
            if same_year_dividends_row:
                dividends_paid = self._nan_to_none(
                    safe_float(
                        same_year_dividends_row[0],
                        f"{symbol}.dividends_paid_incomplete_row_fallback",
                        allow_none=True,
                    )
                )
        earnings_per_share = self._nan_to_none(
            safe_float(quality_row[16], f"{symbol}.earnings_per_share", allow_none=True)
        )
        prior_year_eps = self._nan_to_none(safe_float(quality_row[17], f"{symbol}.prior_year_eps", allow_none=True))
        prior_year_revenue = self._nan_to_none(
            safe_float(quality_row[18], f"{symbol}.prior_year_revenue", allow_none=True)
        )
        gross_profit_direct = self._nan_to_none(safe_float(quality_row[19], f"{symbol}.gross_profit", allow_none=True))
        long_term_debt_bs = self._nan_to_none(safe_float(quality_row[20], f"{symbol}.long_term_debt", allow_none=True))
        cash_and_equivalents_bs = self._nan_to_none(
            safe_float(quality_row[21], f"{symbol}.cash_and_equivalents", allow_none=True)
        )
        income_tax_expense = self._nan_to_none(
            safe_float(quality_row[22], f"{symbol}.income_tax_expense", allow_none=True)
        )
        prior_year_net_income = self._nan_to_none(
            safe_float(quality_row[24], f"{symbol}.prior_year_net_income", allow_none=True)
        )
        prior_year_operating_income = self._nan_to_none(
            safe_float(quality_row[25], f"{symbol}.prior_year_operating_income", allow_none=True)
        )
        prior_year_operating_cash_flow = self._nan_to_none(
            safe_float(quality_row[26], f"{symbol}.prior_year_operating_cash_flow", allow_none=True)
        )
        prior_year_free_cash_flow = self._nan_to_none(
            safe_float(quality_row[27], f"{symbol}.prior_year_free_cash_flow", allow_none=True)
        )
        prior_year_cost_of_revenue = self._nan_to_none(
            safe_float(quality_row[28], f"{symbol}.prior_year_cost_of_revenue", allow_none=True)
        )
        prior_year_total_assets = self._nan_to_none(
            safe_float(quality_row[29], f"{symbol}.prior_year_total_assets", allow_none=True)
        )
        prior_year_stockholders_equity = self._nan_to_none(
            safe_float(quality_row[30], f"{symbol}.prior_year_stockholders_equity", allow_none=True)
        )
        prior_year_pretax_income = self._nan_to_none(
            safe_float(quality_row[31], f"{symbol}.prior_year_pretax_income", allow_none=True)
        )
        prior_year_interest_expense = self._nan_to_none(
            safe_float(quality_row[32], f"{symbol}.prior_year_interest_expense", allow_none=True)
        )
        prior_year_gross_profit = self._nan_to_none(
            safe_float(quality_row[33], f"{symbol}.prior_year_gross_profit", allow_none=True)
        )
        # Recovers dividends_paid when the anchor fiscal year genuinely never extracted it
        # (vs. the same-year "unavailable row" rescue above, which only handles the
        # masked-but-present case). Appended as the LAST column (index 34), bounds-checked
        # rather than accessed bare so an old 34-column test fixture reads None instead of
        # raising IndexError - see the Net Debt Issuance comment below for why adding a
        # column here elsewhere had to be deferred.
        prior_year_dividends_paid = self._nan_to_none(
            safe_float(
                quality_row[34] if len(quality_row) > 34 else None,
                f"{symbol}.prior_year_dividends_paid",
                allow_none=True,
            )
        )
        # A genuine non-payer has no dividends_paid in EITHER year, so this only ever
        # substitutes a real, one-year-old figure for a confirmed-recent payer's current-
        # year extraction gap - never fabricates a dividend for a symbol with no history.
        # Pure in-memory fallback (no new DB call - this function's tests mock the cursor
        # with a fixed, position-matched sequence of canned results).
        dividends_paid_with_prior_year_fallback = dividends_paid
        if dividends_paid_with_prior_year_fallback is None and prior_year_dividends_paid is not None:
            dividends_paid_with_prior_year_fallback = prior_year_dividends_paid
        # prior_year_dividends_paid only reaches back one fiscal year, so a gap spanning 3+
        # consecutive years still falls through to None - see
        # _get_last_known_zero_dividends_symbols()'s docstring for why only the "last known
        # value was exactly $0" subset is safe to carry forward indefinitely.
        if dividends_paid_with_prior_year_fallback is None and symbol in self._get_last_known_zero_dividends_symbols():
            dividends_paid_with_prior_year_fallback = 0.0
        # Net Debt Issuance (Bradshaw/Richardson/Sloan 2006) DEFERRED: needs prior-year
        # long_term_debt, which isn't in quality_row (appending a column there breaks
        # fixed-length mock rows in existing tests) and can't be fetched via a new
        # mid-function query either (tests mock the DB cursor with a fixed,
        # position-matched sequence of canned results - any new cur.execute() call shifts
        # that sequence for every test exercising this path). Its 5% weight allocation
        # moved to margin_volatility_score below instead.
        # EBIT-approximation fallback for prior-year operating income, mirroring the
        # current-year fallback below - needed so operating_income_growth_yoy/
        # operating_margin_trend (which compare CURRENT vs PRIOR year) aren't blocked for
        # filers that tag pretax_income/interest_expense but never OperatingIncomeLoss.
        prior_year_operating_income_for_trend = prior_year_operating_income
        if prior_year_operating_income_for_trend is None and prior_year_pretax_income is not None:
            prior_year_operating_income_for_trend = prior_year_pretax_income + (prior_year_interest_expense or 0)

        return ExtractedQualityFields(
            stockholders_equity=stockholders_equity,
            total_liabilities=total_liabilities,
            total_assets=total_assets,
            net_income=net_income,
            revenue=revenue,
            operating_income=operating_income,
            current_assets=current_assets,
            current_liabilities=current_liabilities,
            inventory=inventory,
            interest_expense=interest_expense,
            pretax_income=pretax_income,
            interest_coverage_operating_income=interest_coverage_operating_income,
            interest_coverage_pretax_income=interest_coverage_pretax_income,
            shares_outstanding=shares_outstanding,
            cost_of_revenue=cost_of_revenue,
            operating_cash_flow=operating_cash_flow,
            free_cash_flow=free_cash_flow,
            dividends_paid=dividends_paid,
            earnings_per_share=earnings_per_share,
            prior_year_eps=prior_year_eps,
            prior_year_revenue=prior_year_revenue,
            gross_profit_direct=gross_profit_direct,
            long_term_debt_bs=long_term_debt_bs,
            cash_and_equivalents_bs=cash_and_equivalents_bs,
            income_tax_expense=income_tax_expense,
            prior_year_net_income=prior_year_net_income,
            prior_year_operating_income=prior_year_operating_income,
            prior_year_operating_cash_flow=prior_year_operating_cash_flow,
            prior_year_free_cash_flow=prior_year_free_cash_flow,
            prior_year_cost_of_revenue=prior_year_cost_of_revenue,
            prior_year_total_assets=prior_year_total_assets,
            prior_year_stockholders_equity=prior_year_stockholders_equity,
            prior_year_pretax_income=prior_year_pretax_income,
            prior_year_interest_expense=prior_year_interest_expense,
            prior_year_gross_profit=prior_year_gross_profit,
            prior_year_dividends_paid=prior_year_dividends_paid,
            dividends_paid_with_prior_year_fallback=dividends_paid_with_prior_year_fallback,
            prior_year_operating_income_for_trend=prior_year_operating_income_for_trend,
        )

    def _compute_quality_metrics(
        self,
        symbol: str,
        quality_row: Any,
        ev_metrics: Any = None,
        margin_volatility: float | None = None,
    ) -> dict[str, Any]:
        """Compute quality_metrics from SEC financials (balance sheet + income statement + cash flow + EV data).

        ev_metrics: tuple of (total_debt, total_cash, ebitda[, reason]) from sec_valuations -
        the 4th element (sec_valuations.reason) is optional for backward compatibility with
        callers/tests still passing a 3-tuple.
        margin_volatility: trailing-3yr net_margin stdev, precomputed by the caller (see
        _compute_margin_volatility) from multi-year income_rows this function doesn't have.
        """
        if not quality_row:
            return self._unavailable_marker("quality_metrics", symbol)

        if not isinstance(quality_row, (tuple, list)):
            logger.error(
                f"[VALUE_QUALITY_GROWTH] {symbol}: quality_row is {type(quality_row)}, not tuple/list. This is a CRITICAL BUG. "
                f"Upstream transformation (cur.fetchone() from annual_balance_sheet JOIN) failed to return tuple. "
                f"Data structure: {repr(quality_row)[:200]}. "
                f"Check: (1) DatabaseContext cursor type, (2) Connection pool configuration, (3) Database driver version. "
                f"Recovery: Mark symbol unavailable and skip quality metrics for this run."
            )
            return self._unavailable_marker("quality_metrics", symbol)

        if len(quality_row) < 28:
            logger.error(f"[VALUE_QUALITY_GROWTH] {symbol}: quality_row has {len(quality_row)} columns, expected 28")
            return self._unavailable_marker("quality_metrics", symbol)

        try:
            qf = self._extract_quality_row_fields(symbol, quality_row)
            stockholders_equity = qf.stockholders_equity
            total_liabilities = qf.total_liabilities
            total_assets = qf.total_assets
            net_income = qf.net_income
            revenue = qf.revenue
            operating_income = qf.operating_income
            current_assets = qf.current_assets
            current_liabilities = qf.current_liabilities
            inventory = qf.inventory
            interest_expense = qf.interest_expense
            pretax_income = qf.pretax_income
            interest_coverage_operating_income = qf.interest_coverage_operating_income
            # interest_coverage_pretax_income/dividends_paid/prior_year_operating_income/
            # prior_year_pretax_income/prior_year_interest_expense/prior_year_dividends_paid are
            # only consumed inside _extract_quality_row_fields itself, not unpacked here.
            shares_outstanding = qf.shares_outstanding
            cost_of_revenue = qf.cost_of_revenue
            operating_cash_flow = qf.operating_cash_flow
            free_cash_flow = qf.free_cash_flow
            earnings_per_share = qf.earnings_per_share
            prior_year_eps = qf.prior_year_eps
            prior_year_revenue = qf.prior_year_revenue
            gross_profit_direct = qf.gross_profit_direct
            long_term_debt_bs = qf.long_term_debt_bs
            cash_and_equivalents_bs = qf.cash_and_equivalents_bs
            income_tax_expense = qf.income_tax_expense
            prior_year_net_income = qf.prior_year_net_income
            prior_year_operating_cash_flow = qf.prior_year_operating_cash_flow
            prior_year_free_cash_flow = qf.prior_year_free_cash_flow
            prior_year_cost_of_revenue = qf.prior_year_cost_of_revenue
            prior_year_total_assets = qf.prior_year_total_assets
            prior_year_stockholders_equity = qf.prior_year_stockholders_equity
            prior_year_gross_profit = qf.prior_year_gross_profit
            dividends_paid_with_prior_year_fallback = qf.dividends_paid_with_prior_year_fallback
            prior_year_operating_income_for_trend = qf.prior_year_operating_income_for_trend

            metrics: dict[str, Any] = {
                "symbol": symbol,
                "roe": None,
                "roa": None,
                "operating_margin": None,
                "net_margin": None,
                "debt_to_equity": None,
                "debt_to_assets": None,
                "current_ratio": None,
                "quick_ratio": None,
                "interest_coverage": None,
                # New fields - Phase 3 expansion
                "gross_margin": None,
                "ebitda_margin": None,
                "roic_pct": None,
                "roce_pct": None,
                "fcf_to_net_income": None,
                "ocf_to_net_income": None,
                "payout_ratio": None,
                "free_cash_flow": None,
                "operating_cash_flow": None,
                "total_debt": None,
                "total_cash": None,
                "cash_per_share": None,
                "ebitda": None,
                "earnings_growth_yoy": None,
                "revenue_growth_yoy": None,
                "quality_score": None,
                "data_unavailable": False,
                "data_source": "sec_audited",
                "updated_at": get_loader_timestamp(),
            }

            failed_metrics: list[str] = []
            # Metrics suppressed by the |ratio| > 1000 garbage-value bound below - tracked
            # separately from failed_metrics because "we computed a real ratio and threw it
            # away as implausible" (near-zero-denominator extraction artifact, or a
            # legitimately near-zero-revenue filer like a pre-revenue biotech/SPAC) is a
            # materially different situation from "SEC never reported the inputs at all", and
            # both were previously labeled with the same generic "missing_sec_data" reason.
            implausible_ratio_metrics: list[str] = []
            # Tracks the reason for the sign-change guards below (a YoY comparison that flips
            # sign, e.g. -$15M to +$2M, produces a meaningless growth percentage).
            sign_change_yoy_metrics: list[str] = []
            # A prior-year base under 1% of that year's revenue is too small to produce a
            # meaningful growth percentage even without a sign flip - mark unavailable rather
            # than compute a technically-real but misleading number.
            immaterial_base_yoy_metrics: list[str] = []

            core_ratios = self._compute_core_financial_ratios(
                symbol,
                net_income,
                stockholders_equity,
                total_assets,
                revenue,
                operating_income,
                interest_expense,
                pretax_income,
                current_assets,
                current_liabilities,
                inventory,
                total_liabilities,
                gross_profit_direct,
                cost_of_revenue,
                ev_metrics,
                interest_coverage_operating_income,
                metrics,
                failed_metrics,
                implausible_ratio_metrics,
            )
            operating_income_for_margin = core_ratios.operating_income_for_margin
            no_operating_income_concept = core_ratios.no_operating_income_concept
            unclassified_balance_sheet = core_ratios.unclassified_balance_sheet
            no_recent_interest_expense = core_ratios.no_recent_interest_expense
            no_operating_income_concept_ic = core_ratios.no_operating_income_concept_ic
            total_debt_ev = core_ratios.total_debt_ev
            total_cash_ev = core_ratios.total_cash_ev
            ebitda_ev = core_ratios.ebitda_ev
            sec_valuations_reason = core_ratios.sec_valuations_reason
            gross_profit_used = core_ratios.gross_profit_used
            no_gross_profit_concept = core_ratios.no_gross_profit_concept

            roic_roce = self._compute_roic_roce_and_leverage(
                symbol,
                quality_row,
                income_tax_expense,
                pretax_income,
                operating_income,
                net_income,
                stockholders_equity,
                cash_and_equivalents_bs,
                long_term_debt_bs,
                total_debt_ev,
                metrics,
                failed_metrics,
                implausible_ratio_metrics,
            )
            debt_for_roic = roic_roce.debt_for_roic
            roic_pct_unprofitable = roic_roce.roic_pct_unprofitable
            roic_pct_negative_invested_capital = roic_roce.roic_pct_negative_invested_capital
            roce_pct_negative_capital_employed = roic_roce.roce_pct_negative_capital_employed
            no_operating_income_concept_roic = roic_roce.no_operating_income_concept_roic

            payout_ratio_reason, cash_per_share_shares_missing = self._compute_cash_flow_ratios(
                symbol,
                free_cash_flow,
                net_income,
                operating_cash_flow,
                dividends_paid_with_prior_year_fallback,
                total_debt_ev,
                total_cash_ev,
                ebitda_ev,
                shares_outstanding,
                metrics,
                failed_metrics,
                MAX_ABSOLUTE_DOLLAR_VALUE,
            )

            self._compute_yoy_growth_metrics(
                symbol,
                earnings_per_share,
                prior_year_eps,
                revenue,
                prior_year_revenue,
                net_income,
                prior_year_net_income,
                operating_income_for_margin,
                prior_year_operating_income_for_trend,
                gross_profit_direct,
                cost_of_revenue,
                prior_year_gross_profit,
                prior_year_cost_of_revenue,
                metrics,
                failed_metrics,
                implausible_ratio_metrics,
                sign_change_yoy_metrics,
                immaterial_base_yoy_metrics,
                MAX_PLAUSIBLE_GROWTH_PCT,
                MAX_TREND_PERCENTAGE_POINTS,
            )

            self._compute_sgr_and_remaining_trends(
                symbol,
                stockholders_equity,
                net_income,
                dividends_paid_with_prior_year_fallback,
                prior_year_stockholders_equity,
                prior_year_net_income,
                free_cash_flow,
                prior_year_free_cash_flow,
                operating_cash_flow,
                prior_year_operating_cash_flow,
                total_assets,
                prior_year_total_assets,
                prior_year_revenue,
                no_gross_profit_concept,
                metrics,
                implausible_ratio_metrics,
                sign_change_yoy_metrics,
                immaterial_base_yoy_metrics,
                MAX_PLAUSIBLE_GROWTH_PCT,
                MAX_TREND_PERCENTAGE_POINTS,
            )

            # Quarterly Metrics (Session 74+)
            quarterly_metrics = self._compute_quarterly_metrics(symbol)
            metrics.update(quarterly_metrics)

            # Initialize missing trend fields as None
            for field in [
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
                "earnings_surprise_avg",
                "eps_growth_stability",
                "earnings_beat_rate",
                "consecutive_positive_quarters",
                "estimate_revision_direction",
                "revision_activity_30d",
                "estimate_momentum_60d",
                "estimate_momentum_90d",
                "revision_trend_score",
                "earnings_growth_4q_avg",
            ]:
                if field not in metrics:
                    metrics[field] = None

            # Quarterly-derived fields are merged in from _compute_quarterly_metrics() above,
            # which sets its own specific reason when a value is None; the generic
            # "insufficient_quarterly_data"/"no_analyst_estimates" fallback (only fired when
            # no specific reason was already set) is assigned further below.

            # Mark unavailable if all metrics are None
            if (
                all(
                    metrics[k] is None
                    for k in [
                        "roe",
                        "roa",
                        "operating_margin",
                        "net_margin",
                        "debt_to_equity",
                        "debt_to_assets",
                        "current_ratio",
                    ]
                )
                and metrics.get("consecutive_positive_quarters") is None
            ):
                # consecutive_positive_quarters is always a real int (never None) whenever >=4
                # real quarters exist, so checking it here is a direct signal that real
                # quarterly data exists - guards against this early return's blanket
                # None+"missing_sec_data" stamp wiping already-computed quarterly-derived
                # fields. This return also fires before any of the per-field reason blocks
                # below run, so propagate a real row-level reason when one is knowable instead
                # of leaving _unavailable_marker's generic default on every column.
                row_level_reason = (
                    "no_recent_balance_sheet_data_reported"
                    if stockholders_equity is None
                    and (
                        symbol in self._get_no_recent_stockholders_equity_symbols()
                        or symbol in self._get_never_tagged_stockholders_equity_symbols()
                    )
                    else None
                )
                return self._unavailable_marker("quality_metrics", symbol, reason=row_level_reason)

            self._compute_quality_composite_score(
                symbol,
                metrics,
                failed_metrics,
                implausible_ratio_metrics,
                margin_volatility,
                stockholders_equity,
                interest_expense,
                total_assets,
                net_income,
                operating_cash_flow,
                revenue,
                free_cash_flow,
                operating_income_for_margin,
                no_operating_income_concept,
                no_gross_profit_concept,
                gross_profit_used,
            )

            self._assign_core_ratio_unavailable_reasons(
                symbol,
                metrics,
                failed_metrics,
                implausible_ratio_metrics,
                stockholders_equity,
                net_income,
                total_assets,
                no_operating_income_concept,
                operating_income_for_margin,
                no_recent_interest_expense,
                no_operating_income_concept_ic,
                unclassified_balance_sheet,
                current_assets,
                current_liabilities,
                total_liabilities,
                debt_for_roic,
            )

            self._assign_extended_metric_unavailable_reasons(
                symbol,
                metrics,
                failed_metrics,
                implausible_ratio_metrics,
                no_gross_profit_concept,
                revenue,
                no_operating_income_concept,
                roic_pct_unprofitable,
                roic_pct_negative_invested_capital,
                no_operating_income_concept_roic,
                debt_for_roic,
                stockholders_equity,
                roce_pct_negative_capital_employed,
                free_cash_flow,
                net_income,
                operating_cash_flow,
                cash_per_share_shares_missing,
                ev_metrics,
                sec_valuations_reason,
                payout_ratio_reason,
            )

            self._assign_quarterly_and_analyst_fallback_reasons(metrics)

            if failed_metrics:
                # Log which metrics are incomplete (for debugging), but don't mark data_unavailable
                logger.debug(
                    f"[VALUE_QUALITY_GROWTH] {symbol}: Quality metrics computed from available data. "
                    f"Unavailable: {', '.join(sorted(set(failed_metrics)))} (insufficient SEC data)"
                )

            self._recategorize_royalty_trust_reasons(symbol, metrics)

            return metrics

        except Exception as e:
            logger.warning(f"[VALUE_QUALITY_GROWTH] {symbol}: Quality metrics compute failed: {e}")
            # Propagate the real exception (not the generic "missing_sec_data" default) so a
            # genuine loader bug lands in scores.py's _categorize_reason() "Other (errors /
            # excluded)" bucket instead of silently inflating "Missing SEC/XBRL data" - same
            # fix already applied to this file's outer fetch_incremental() except block.
            exc_reason = f"fetch_exception: {type(e).__name__}: {str(e)[:150]}"
            return self._unavailable_marker("quality_metrics", symbol, reason=exc_reason)
