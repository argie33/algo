"""QualityMetricsMixin._compute_quality_metrics, extracted from
load_value_quality_growth_metrics.py (2026-09-05, file-size-ratchet compliance split): this
single method was ~2,600 of the file's ~6,070 lines - by far the largest single
concentration. Moved verbatim - no behavior change - except `DatabaseContext(...)` call
sites now go through `_owner()` (see that helper's own docstring for why).

Mixed into ValueQualityGrowthMetricsLoader via multiple inheritance alongside
ValueMetricsMixin/GrowthMetricsMixin - every `self.` call here (the 39 SymbolGateMixin
gates, _fetch_annual_fallback_row, _fetch_balance_sheet_anchor_fallback,
_ratio_with_implausible_fallback, _find_plausible_cross_year_ratio, etc.) resolves normally
through the instance regardless of which mixin file defines it.
"""

import logging
from typing import TYPE_CHECKING, Any

from loaders.helpers.vqg_shared import (
    MAX_ABSOLUTE_DOLLAR_VALUE,
    MAX_PLAUSIBLE_GROWTH_PCT,
    MAX_TREND_PERCENTAGE_POINTS,
    get_loader_timestamp,
)
from loaders.helpers.vqg_symbol_gates import SymbolGateMixin
from utils.type_conversion import safe_float


def _owner() -> Any:
    """Lazy reference to the owner module, resolved at call time (not import time).

    Two reasons this indirection exists, both load-bearing:
    (1) DatabaseContext: dozens of existing unit tests monkeypatch
    ``loaders.load_value_quality_growth_metrics.DatabaseContext`` directly. A module-level
    ``from utils.db.context import DatabaseContext`` here would bind this module's own
    separate copy of the name, which those patches can never reach - going through
    ``_owner().DatabaseContext`` always reads whatever the owner module's current attribute
    is, mocked or real.
    (2) Avoids importing anything from the owner module at THIS module's top level, which
    is what caused a real circular-import crash on 2026-09-05 (see
    vqg_and_stock_scores_dead_split_files_deleted_20260905 in memory): when the owner is run
    as a script (``python loaders/load_value_quality_growth_metrics.py``) rather than
    imported as a package, it registers under ``sys.modules["__main__"]``, not its dotted
    path - a top-level `from loaders.load_value_quality_growth_metrics import X` here then
    re-imports the owner from scratch while it's still mid-import, before this class exists
    yet, raising ImportError. Importing lazily inside a function body sidesteps this
    entirely since it only runs after both modules have finished importing.
    """
    from loaders import load_value_quality_growth_metrics as _owner_mod

    return _owner_mod


logger = logging.getLogger("loaders.load_value_quality_growth_metrics")


class QualityMetricsMixin(SymbolGateMixin):
    """See module docstring.

    Inherits SymbolGateMixin (also a base of ValueQualityGrowthMetricsLoader itself - a
    diamond, harmless since it's the same class both times) purely so mypy can see the 39
    `_get_*_symbols` gate methods called via `self.` below; the handful of other
    cross-mixin members (defined on ValueQualityGrowthMetricsLoader or a sibling mixin,
    which don't exist as types this file can import without a real circular import) are
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

        def _find_plausible_cross_year_ratio(
            self, symbol: str, numerator_field: str, denominator_field: str, *, as_percentage: bool = True
        ) -> float | None: ...

        def _find_plausible_cross_year_roic_ratio(self, symbol: str, metric: str) -> float | None: ...

        def _find_plausible_cross_year_ebitda_margin_ratio(self, symbol: str) -> float | None: ...

    def _compute_quality_metrics(  # noqa: C901
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
            operating_income = self._nan_to_none(
                safe_float(quality_row[5], f"{symbol}.operating_income", allow_none=True)
            )
            current_assets = self._nan_to_none(safe_float(quality_row[6], f"{symbol}.current_assets", allow_none=True))
            if current_assets is None:
                current_assets = self._fetch_balance_sheet_anchor_fallback(symbol, "current_assets")
            current_liabilities = self._nan_to_none(
                safe_float(quality_row[7], f"{symbol}.current_liabilities", allow_none=True)
            )
            if current_liabilities is None:
                current_liabilities = self._fetch_balance_sheet_anchor_fallback(symbol, "current_liabilities")
            inventory = self._nan_to_none(safe_float(quality_row[9], f"{symbol}.inventory", allow_none=True))
            interest_expense = self._nan_to_none(
                safe_float(quality_row[10], f"{symbol}.interest_expense", allow_none=True)
            )
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
            _income_inputs_missing = (
                interest_coverage_operating_income is None and interest_coverage_pretax_income is None
            )
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
            cost_of_revenue = self._nan_to_none(
                safe_float(quality_row[12], f"{symbol}.cost_of_revenue", allow_none=True)
            )
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
            gross_profit_direct = self._nan_to_none(
                safe_float(quality_row[19], f"{symbol}.gross_profit", allow_none=True)
            )
            long_term_debt_bs = self._nan_to_none(
                safe_float(quality_row[20], f"{symbol}.long_term_debt", allow_none=True)
            )
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
            if (
                dividends_paid_with_prior_year_fallback is None
                and symbol in self._get_last_known_zero_dividends_symbols()
            ):
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
            # Metrics whose value came from _find_plausible_cross_year_ratio /
            # _find_plausible_cross_year_roic_ratio (up to 6 fiscal years back, tightened
            # 2026-09-05 real-money audit from an original 30-year lookback that let this
            # rescue reach implausibly far into the past) rather than the current anchor
            # year. That value is written into the SAME row as this symbol's current-period
            # metrics with no other provenance marker, so without this tracking a multi-year-
            # old ratio is indistinguishable from fresh data to any downstream scoring/
            # backtest consumer. See data_source override near this function's return.
            stale_fallback_metrics: list[str] = []
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

            # ROE = Net Income / Shareholders' Equity. Same near-zero-denominator garbage-value
            # bound as the other ratios in this function; falls back to the most recent OTHER
            # fiscal year with a plausible pair before giving up as implausible_ratio.
            metrics["roe"], _roe_implausible = self._ratio_with_implausible_fallback(
                symbol, net_income, stockholders_equity, "net_income", "stockholders_equity"
            )
            if metrics["roe"] is None:
                failed_metrics.append("roe")
                if _roe_implausible:
                    implausible_ratio_metrics.append("roe")

            # ROA = Net Income / Total Assets. Same bound and cross-year fallback as roe above.
            metrics["roa"], _roa_implausible = self._ratio_with_implausible_fallback(
                symbol, net_income, total_assets, "net_income", "total_assets"
            )
            if metrics["roa"] is None:
                failed_metrics.append("roa")
                if _roa_implausible:
                    implausible_ratio_metrics.append("roa")

            # Operating Margin = Operating Income / Revenue
            # Fallback for banks (NULL revenue): use Operating Income / Total Assets instead
            # EBIT-approximation fallback (pretax_income + interest_expense), same as
            # interest_coverage_operating_income/roic_operating_income above - uses the anchor
            # row's own pretax_income/interest_expense (not the cross-year-searched value) so
            # numerator and denominator (revenue) stay from the same fiscal year.
            operating_income_for_margin = operating_income
            if operating_income_for_margin is None and pretax_income is not None:
                operating_income_for_margin = pretax_income + (interest_expense or 0)
            # Some REIT/tonnage-tax filers (AGNC/ARE/AMH-class) never tag OperatingIncomeLoss OR
            # pretax_income/income_tax_expense at all - a permanent different-accounting-model
            # gap, not an XBRL extraction failure, so recategorize as "reit_special_entity"
            # rather than "missing_sec_data" once confirmed unrecoverable (reuses the same
            # _get_no_tax_concept_symbols() 3-consecutive-year check as roic_pct's
            # effective_tax_rate=0.0 branch). Deliberately does not attempt a numeric
            # reconstruction here (net_income-based reconstruction was tried and rejected
            # elsewhere in this file - too much deviation). sustainable_growth_rate is
            # unaffected since its ROE input only needs net_income+equity.
            no_operating_income_concept = (
                operating_income_for_margin is None and symbol in self._get_no_tax_concept_symbols()
            )
            if operating_income_for_margin is not None and operating_income_for_margin != 0:
                operating_margin_denominator_field = None
                if revenue is not None and revenue > 0:
                    computed_operating_margin = (operating_income_for_margin / revenue) * 100
                    operating_margin_denominator_field = "revenue"
                elif total_assets is not None and total_assets != 0:
                    # Fallback: ROA of operating income (useful for banks with NULL revenue)
                    computed_operating_margin = (operating_income_for_margin / total_assets) * 100
                    operating_margin_denominator_field = "total_assets"
                else:
                    computed_operating_margin = None
                if computed_operating_margin is None:
                    failed_metrics.append("operating_margin")
                else:
                    # Same near-zero-denominator garbage-value bound as gross_margin/
                    # ebitda_margin/roic_pct above.
                    if abs(computed_operating_margin) > 1000:
                        # Same cross-year fallback as ROE/ROA/roic_pct - search for an older
                        # fiscal year with a plausible same-year (operating_income, denominator)
                        # pair, using the SAME denominator field the anchor year used (revenue
                        # vs total_assets), before giving up as implausible.
                        operating_margin_fallback = (
                            self._find_plausible_cross_year_ratio(
                                symbol, "operating_income", operating_margin_denominator_field
                            )
                            if operating_margin_denominator_field is not None
                            else None
                        )
                        if operating_margin_fallback is not None:
                            metrics["operating_margin"] = operating_margin_fallback
                            stale_fallback_metrics.append("operating_margin")
                        else:
                            failed_metrics.append("operating_margin")
                            implausible_ratio_metrics.append("operating_margin")
                    else:
                        metrics["operating_margin"] = float(computed_operating_margin)
            else:
                failed_metrics.append("operating_margin")

            # Net Margin = Net Income / Revenue
            # Fallback for banks (NULL revenue): use Net Income / Total Assets instead
            if net_income is not None and net_income != 0:
                net_margin_denominator_field = None
                if revenue is not None and revenue > 0:
                    computed_net_margin = (net_income / revenue) * 100
                    net_margin_denominator_field = "revenue"
                elif total_assets is not None and total_assets != 0:
                    # Fallback: ROA of net income (useful for banks with NULL revenue)
                    computed_net_margin = (net_income / total_assets) * 100
                    net_margin_denominator_field = "total_assets"
                else:
                    computed_net_margin = None
                if computed_net_margin is None:
                    failed_metrics.append("net_margin")
                else:
                    # Same near-zero-denominator garbage-value bound as the margins above.
                    if abs(computed_net_margin) > 1000:
                        # Same cross-year fallback as operating_margin above.
                        net_margin_fallback = (
                            self._find_plausible_cross_year_ratio(symbol, "net_income", net_margin_denominator_field)
                            if net_margin_denominator_field is not None
                            else None
                        )
                        if net_margin_fallback is not None:
                            metrics["net_margin"] = net_margin_fallback
                            stale_fallback_metrics.append("net_margin")
                        else:
                            failed_metrics.append("net_margin")
                            implausible_ratio_metrics.append("net_margin")
                    else:
                        metrics["net_margin"] = float(computed_net_margin)
            else:
                failed_metrics.append("net_margin")

            # Debt to Equity is computed after roic_pct below, alongside ROCE, from
            # debt_for_roic (interest-bearing debt) / equity - NOT Total Liabilities / Equity,
            # which is a different, broader ratio (includes AP/deferred revenue/accrued
            # expenses) than what "Debt-to-Equity" means in standard finance usage or what was
            # Fama-MacBeth validated for this factor.

            # Debt to Assets = Total Liabilities / Total Assets
            # Same >1000 near-zero-denominator bound as the other ratios in this function.
            if total_liabilities is not None and total_assets is not None and total_assets != 0:
                computed_debt_to_assets = total_liabilities / total_assets
                if abs(computed_debt_to_assets) > 1000:
                    failed_metrics.append("debt_to_assets")
                    implausible_ratio_metrics.append("debt_to_assets")
                else:
                    metrics["debt_to_assets"] = float(computed_debt_to_assets)
            else:
                failed_metrics.append("debt_to_assets")

            # Current Ratio = Current Assets / Current Liabilities
            # Same >1000 bound as the other ratios above.
            if current_assets is not None and current_liabilities is not None and current_liabilities != 0:
                computed_current_ratio = current_assets / current_liabilities
                if abs(computed_current_ratio) > 1000:
                    failed_metrics.append("current_ratio")
                    implausible_ratio_metrics.append("current_ratio")
                else:
                    metrics["current_ratio"] = float(computed_current_ratio)
            else:
                failed_metrics.append("current_ratio")

            # Quick Ratio = (Current Assets - Inventory) / Current Liabilities
            # `inventory` NULL means genuinely none carried (service/software) or simply not
            # broken out - treat as 0 rather than failing the metric, same as IBD/most screeners.
            # Same >1000 bound as current_ratio above (shares the same denominator).
            if current_assets is not None and current_liabilities is not None and current_liabilities != 0:
                computed_quick_ratio = (current_assets - (inventory or 0)) / current_liabilities
                if abs(computed_quick_ratio) > 1000:
                    failed_metrics.append("quick_ratio")
                    implausible_ratio_metrics.append("quick_ratio")
                else:
                    metrics["quick_ratio"] = float(computed_quick_ratio)
            else:
                failed_metrics.append("quick_ratio")

            # REITs/banks file unclassified balance sheets and never report
            # AssetsCurrent/LiabilitiesCurrent - a permanent structural gap, distinct from an
            # ordinary filer's one-year extraction/timing gap, so check full symbol history.
            unclassified_balance_sheet = (
                current_assets is None
                and current_liabilities is None
                and symbol in self._get_unclassified_balance_sheet_symbols()
            )

            # Companies that stop itemizing interest_expense (debt-free, or netted into other
            # income/expense) never report it again - full-history check, not just this row.
            no_recent_interest_expense = interest_expense is None and (
                symbol in self._get_no_recent_interest_expense_symbols()
                or symbol in self._get_never_tagged_interest_expense_symbols()
            )
            # REITs with real interest_expense (mortgage debt) but no operating_income/
            # pretax_income concept ever tagged fail interest_coverage on the operating-income
            # side, not interest_expense - distinct from no_recent_interest_expense above.
            no_operating_income_concept_ic = (
                interest_coverage_operating_income is None and symbol in self._get_no_tax_concept_symbols()
            )

            # Interest Coverage = Operating Income / Interest Expense. Higher is better
            # (ability to service debt from operating earnings). Column existed on
            # quality_metrics (migration predates this loader) and is already displayed by
            # the frontend/API, but no loader ever computed it - annual_income_statement had
            # no interest_expense column until migration 1145. Only computed when
            # interest_expense > 0 (zero debt service is a real "not applicable" case, not
            # an infinite/undefined ratio to fake a max score for).
            if interest_expense is not None and interest_expense > 0 and interest_coverage_operating_income is not None:
                computed_interest_coverage = interest_coverage_operating_income / interest_expense
                # A negligibly small interest_expense denominator blows this ratio up into
                # noise (real but meaningless), not a real coverage signal.
                if abs(computed_interest_coverage) > 1000:
                    # Same cross-year fallback as operating_margin/net_margin/roic_pct above -
                    # search for an older fiscal year with a plausible same-year
                    # (operating_income, interest_expense) pair.
                    interest_coverage_fallback = self._find_plausible_cross_year_ratio(
                        symbol, "operating_income", "interest_expense", as_percentage=False
                    )
                    if interest_coverage_fallback is not None:
                        metrics["interest_coverage"] = interest_coverage_fallback
                        stale_fallback_metrics.append("interest_coverage")
                    else:
                        failed_metrics.append("interest_coverage")
                        implausible_ratio_metrics.append("interest_coverage")
                else:
                    metrics["interest_coverage"] = float(computed_interest_coverage)
            else:
                failed_metrics.append("interest_coverage")

            # Extract EV metrics from sec_valuations if available
            total_debt_ev = None
            total_cash_ev = None
            ebitda_ev = None
            # sec_valuations' own `reason` column carries a specific cause (e.g.
            # "income_statement_revenue_and_eps_null") - prefer it over a generic bucket.
            # `len(ev_metrics) > 3` guards callers/tests still passing the older 3-tuple shape.
            sec_valuations_reason = ev_metrics[3] if ev_metrics and len(ev_metrics) > 3 else None
            if ev_metrics:
                total_debt_ev = self._nan_to_none(safe_float(ev_metrics[0], f"{symbol}.total_debt", allow_none=True))
                total_cash_ev = self._nan_to_none(safe_float(ev_metrics[1], f"{symbol}.total_cash", allow_none=True))
                ebitda_ev = self._nan_to_none(safe_float(ev_metrics[2], f"{symbol}.ebitda", allow_none=True))

            # Gross Margin = Gross Profit / Revenue. Prefers gross_profit directly from SEC
            # data over computing it from cost_of_revenue, with a prior-year fallback (like
            # ROIC/interest_coverage) when the anchor year has neither. Fetched as a triple
            # (gross_profit, cost_of_revenue, revenue) to avoid year mismatches.
            gross_profit_used = None
            gross_profit_revenue = revenue  # Track which revenue used (for margin calc)

            if gross_profit_direct is not None:
                gross_profit_used = gross_profit_direct
            elif cost_of_revenue is not None and revenue is not None:
                gross_profit_used = revenue - cost_of_revenue

            # Fallback to prior year if current year lacks both sources
            if gross_profit_used is None and (gross_profit_direct is None and cost_of_revenue is None):
                # `data_unavailable IS NOT TRUE` (applied inside the helper) excludes
                # incomplete/unfiled stub rows, which under-report vs the real complete fiscal
                # year.
                fallback_gm_row = self._fetch_annual_fallback_row(
                    "annual_income_statement",
                    "gross_profit, cost_of_revenue, revenue",
                    "AND (gross_profit IS NOT NULL OR cost_of_revenue IS NOT NULL) AND revenue IS NOT NULL",
                    symbol,
                )
                if fallback_gm_row:
                    fallback_gross_profit = self._nan_to_none(
                        safe_float(fallback_gm_row[0], f"{symbol}.gross_profit_fallback_year", allow_none=True)
                    )
                    fallback_cost_of_revenue = self._nan_to_none(
                        safe_float(fallback_gm_row[1], f"{symbol}.cost_of_revenue_fallback_year", allow_none=True)
                    )
                    fallback_revenue = self._nan_to_none(
                        safe_float(fallback_gm_row[2], f"{symbol}.revenue_fallback_year", allow_none=True)
                    )
                    if fallback_gross_profit is not None:
                        gross_profit_used = fallback_gross_profit
                        gross_profit_revenue = fallback_revenue
                    elif fallback_cost_of_revenue is not None and fallback_revenue is not None:
                        gross_profit_used = fallback_revenue - fallback_cost_of_revenue
                        gross_profit_revenue = fallback_revenue

            # Still None here means this symbol has never once reported gross_profit or
            # cost_of_revenue - banks, insurers, and service/REIT filers legitimately don't
            # break out a COGS line at all (structural gap, not a data gap).
            no_gross_profit_concept = gross_profit_used is None

            if gross_profit_used is not None and gross_profit_revenue is not None and gross_profit_revenue != 0:
                # Bound the ratio - a real but implausibly tiny revenue relative to gross_profit
                # (e.g. a mis-scaled/mis-tagged SEC fact) explodes this into nonsense.
                computed_gross_margin = (gross_profit_used / gross_profit_revenue) * 100
                if abs(computed_gross_margin) > 1000:
                    # Same cross-year fallback as operating_margin/net_margin/interest_coverage
                    # above - search for an older fiscal year with a plausible same-year
                    # (gross_profit, revenue) pair.
                    gross_margin_fallback = self._find_plausible_cross_year_ratio(symbol, "gross_profit", "revenue")
                    if gross_margin_fallback is not None:
                        metrics["gross_margin"] = gross_margin_fallback
                        stale_fallback_metrics.append("gross_margin")
                    else:
                        failed_metrics.append("gross_margin")
                        implausible_ratio_metrics.append("gross_margin")
                else:
                    metrics["gross_margin"] = float(computed_gross_margin)
            else:
                failed_metrics.append("gross_margin")

            # EBITDA Margin = EBITDA / Revenue
            if ebitda_ev is not None and revenue is not None and revenue != 0:
                # Same near-zero-denominator bound as gross_margin above.
                computed_ebitda_margin = (ebitda_ev / revenue) * 100
                if abs(computed_ebitda_margin) > 1000:
                    ebitda_margin_fallback = self._find_plausible_cross_year_ebitda_margin_ratio(symbol)
                    if ebitda_margin_fallback is not None:
                        metrics["ebitda_margin"] = ebitda_margin_fallback
                        stale_fallback_metrics.append("ebitda_margin")
                    else:
                        failed_metrics.append("ebitda_margin")
                        implausible_ratio_metrics.append("ebitda_margin")
                else:
                    metrics["ebitda_margin"] = float(computed_ebitda_margin)
            else:
                failed_metrics.append("ebitda_margin")

            # ROIC = NOPAT / Invested Capital, NOPAT = EBIT * (1 - effective_tax_rate). No
            # hardcoded tax-rate assumption - only real SEC-reported tax/pretax concepts are
            # used (a fabricated 0.21/0.25 fallback was rejected/reverted). Pulled as one row
            # (not independent lookups) so NOPAT never mixes mismatched fiscal years.
            anchor_interest_expense_for_roic = self._nan_to_none(
                safe_float(quality_row[10], f"{symbol}.interest_expense_roic_anchor", allow_none=True)
            )
            roic_tax_expense, roic_pretax_income, roic_operating_income, roic_interest_expense, roic_net_income = (
                income_tax_expense,
                pretax_income,
                operating_income,
                anchor_interest_expense_for_roic,
                net_income,
            )
            # Banks especially often have tax+pretax in the anchor year but neither
            # operating_income nor interest_expense that same year (both untagged) - trigger
            # the rescue search below even when tax/pretax themselves are present.
            if (
                income_tax_expense is None
                or pretax_income is None
                or (operating_income is None and anchor_interest_expense_for_roic is None)
            ):
                with _owner().DatabaseContext("read") as cur:
                    # First try: tax+pretax together in recent history (3 years). Prefer a
                    # row that also has operating_income or interest_expense (either lets
                    # NOPAT compute - operating_income directly, interest_expense via EBIT
                    # approximation), but don't require it - a tax/pretax-only row still
                    # unblocks effective_tax_rate even if NOPAT itself later fails.
                    # `data_unavailable IS NOT TRUE` excludes incomplete/unfiled stub rows.
                    cur.execute(
                        """
                        SELECT income_tax_expense, pretax_income, operating_income, interest_expense, net_income
                        FROM annual_income_statement
                        WHERE symbol = %s AND income_tax_expense IS NOT NULL
                          AND pretax_income IS NOT NULL AND data_unavailable IS NOT TRUE
                          AND fiscal_year >= EXTRACT(YEAR FROM CURRENT_DATE)::int - 3
                        ORDER BY (CASE WHEN operating_income IS NOT NULL OR interest_expense IS NOT NULL
                                       THEN 0 ELSE 1 END), fiscal_year DESC
                        LIMIT 1
                        """,
                        (symbol,),
                    )
                    fallback_tax_row = cur.fetchone()

                    # Widen to full history if the 3-year window found nothing, OR found a
                    # tax/pretax row that still can't recover operating_income/interest_expense
                    # (both None) - a 3-year match on tax/pretax alone must not short-circuit
                    # the widen, since it recovers nothing this fallback needs. Keep the 3-year
                    # row (still unblocks effective_tax_rate) if the wider search also empties.
                    if not fallback_tax_row or (fallback_tax_row[2] is None and fallback_tax_row[3] is None):
                        cur.execute(
                            """
                            SELECT income_tax_expense, pretax_income, operating_income, interest_expense, net_income
                            FROM annual_income_statement
                            WHERE symbol = %s AND income_tax_expense IS NOT NULL
                              AND pretax_income IS NOT NULL AND data_unavailable IS NOT TRUE
                            ORDER BY (CASE WHEN operating_income IS NOT NULL OR interest_expense IS NOT NULL
                                           THEN 0 ELSE 1 END), fiscal_year DESC
                            LIMIT 1
                            """,
                            (symbol,),
                        )
                        wider_fallback_tax_row = cur.fetchone()
                        if wider_fallback_tax_row:
                            fallback_tax_row = wider_fallback_tax_row

                if fallback_tax_row:
                    # The search above ranks candidate years by "has operating_income or
                    # interest_expense" ABOVE recency, so it can pick an older, worse year's
                    # tax/pretax over the anchor's own good ones (e.g. a stale loss year beating
                    # a current profitable one for insurers, who often lack both concepts even
                    # when otherwise current). Only take the fallback row's tax/pretax when the
                    # anchor didn't already have real values - this fallback exists solely to
                    # recover operating_income/interest_expense for NOPAT, never to override an
                    # anchor year's own good profitability figures.
                    if roic_tax_expense is None:
                        roic_tax_expense = self._nan_to_none(
                            safe_float(
                                fallback_tax_row[0], f"{symbol}.income_tax_expense_fallback_year", allow_none=True
                            )
                        )
                    if roic_pretax_income is None:
                        roic_pretax_income = self._nan_to_none(
                            safe_float(fallback_tax_row[1], f"{symbol}.pretax_income_fallback_year", allow_none=True)
                        )
                    # Same "don't clobber a real anchor-year value" guard for
                    # operating_income/interest_expense - otherwise the anchor year's real
                    # operating_income could get mixed with a different fallback year's
                    # interest_expense (or vice versa).
                    if roic_operating_income is None:
                        roic_operating_income = self._nan_to_none(
                            safe_float(fallback_tax_row[2], f"{symbol}.operating_income_fallback_year", allow_none=True)
                        )
                    if roic_interest_expense is None:
                        roic_interest_expense = self._nan_to_none(
                            safe_float(fallback_tax_row[3], f"{symbol}.interest_expense_fallback_year", allow_none=True)
                        )
                    if roic_net_income is None:
                        roic_net_income = self._nan_to_none(
                            safe_float(fallback_tax_row[4], f"{symbol}.net_income_fallback_year", allow_none=True)
                        )

            if roic_operating_income is None and roic_pretax_income is not None and roic_interest_expense is not None:
                # EBIT approximation fallback - see comment above. roic_interest_expense is
                # always from the same row as roic_pretax_income (anchor or fallback_tax_row),
                # so this never mixes fiscal years.
                roic_operating_income = roic_pretax_income + roic_interest_expense

            # No hardcoded tax-rate assumption - only real SEC-reported IncomeTaxExpenseBenefit/
            # pretax_income concepts are used (a fabricated 0.21/0.25 fallback was rejected).
            # Bounded to [-60%, 60%]: an implausible rate (near-zero pretax income swamped by an
            # unrelated tax swing) would distort NOPAT worse than marking unavailable, but a
            # real net tax benefit in a profitable year (R&D credits, valuation-allowance
            # releases) is normal and should compute, hence the symmetric range rather than
            # [0, 60%] alone.
            roic_pct_unprofitable = roic_pretax_income is not None and roic_pretax_income <= 0
            effective_tax_rate = None
            if roic_tax_expense is not None and roic_pretax_income is not None and roic_pretax_income > 0:
                candidate_rate = roic_tax_expense / roic_pretax_income
                if -0.60 <= candidate_rate <= 0.60:
                    effective_tax_rate = candidate_rate
                else:
                    implausible_ratio_metrics.append("roic_pct")
            elif (
                roic_tax_expense is None and roic_pretax_income is None and symbol in self._get_no_tax_concept_symbols()
            ):
                # See _get_no_tax_concept_symbols - a filer that has never once tagged a tax
                # concept is structurally tax-exempt (Marine Shipping tonnage-tax filers,
                # REITs), not missing data. NOPAT = operating_income * (1 - 0%).
                effective_tax_rate = 0.0
            elif roic_tax_expense == 0 and roic_pretax_income is None:
                # Some filers (simple loss-making biotechs/small-caps) tag
                # IncomeTaxExpenseBenefit=$0 every year but never tag any pretax_income concept
                # (nothing to reconcile with $0 tax). This needs no net_income+tax_expense
                # approximation (rejected elsewhere as too imprecise, ~25% deviation from
                # NCI/discontinued-ops noise) - effective_tax_rate = tax/pretax is exact algebra
                # when tax is EXACTLY 0: 0/x = 0 for any nonzero x.
                effective_tax_rate = 0.0
            elif (
                roic_pretax_income is None
                and roic_tax_expense is not None
                and roic_tax_expense != 0
                and roic_net_income is not None
                and (roic_net_income + roic_tax_expense) > 0
                and symbol in self._get_never_tagged_pretax_income_symbols()
            ):
                # See _get_never_tagged_pretax_income_symbols - REITs/mortgage trusts never tag
                # a distinct pretax_income concept but do report a real, usually small,
                # income_tax_expense. The general net_income+tax_expense approximation for
                # pretax_income is rejected elsewhere (NCI/discontinued-ops noise), but scoped
                # narrowly here (confirmed-absent concept, same-fiscal-year net_income, same
                # [-0.60, 0.60] bound as every other branch) it's safe: when tax is this small
                # relative to net_income, even a materially wrong pretax base yields only a
                # small implied rate.
                candidate_rate = roic_tax_expense / (roic_net_income + roic_tax_expense)
                if -0.60 <= candidate_rate <= 0.60:
                    effective_tax_rate = candidate_rate
                else:
                    implausible_ratio_metrics.append("roic_pct")

            # Invested Capital = Stockholders' Equity + Total Debt - Cash & Equivalents
            # Use total_debt_ev (from sec_valuations, 81% available) as primary source
            # Fall back to long_term_debt_bs (from balance_sheet, only 22% available) if needed
            # ROIC requires complete balance sheet data, not partial guesses. A prior session
            # added a (total_liabilities - current_liabilities) debt estimate - reverted: that
            # includes non-debt liabilities (AP, accrued expenses, deferred revenue, pensions),
            # so it is not a real "total debt" figure.
            #
            # stockholders_equity/cash_and_equivalents get the same same-year-substitute
            # treatment as the tax triple above, for the same reason (76% cash coverage in the
            # FCF-prioritized row vs a different year that has it).
            roic_stockholders_equity, roic_cash_and_equivalents = stockholders_equity, cash_and_equivalents_bs
            if stockholders_equity is None or cash_and_equivalents_bs is None:
                # `data_unavailable IS NOT TRUE` (applied inside the helper) excludes an
                # incomplete/unfiled or stale-orphan (see sec_base.py's
                # stale_fiscal_year_not_confirmed_by_full_sec_refetch) fiscal year's stub.
                fallback_bs_row = self._fetch_annual_fallback_row(
                    "annual_balance_sheet",
                    "stockholders_equity, cash_and_equivalents",
                    "AND stockholders_equity IS NOT NULL AND cash_and_equivalents IS NOT NULL",
                    symbol,
                )

                if fallback_bs_row:
                    roic_stockholders_equity = self._nan_to_none(
                        safe_float(fallback_bs_row[0], f"{symbol}.stockholders_equity_fallback_year", allow_none=True)
                    )
                    roic_cash_and_equivalents = self._nan_to_none(
                        safe_float(fallback_bs_row[1], f"{symbol}.cash_and_equivalents_fallback_year", allow_none=True)
                    )

            # Banks often tag deposits/FHLB advances/subordinated debentures under concepts
            # this pipeline doesn't map to "long_term_debt" for the current fiscal year, even
            # though an older 10-K (within the 3-year lookback) has a real figure.
            # total_debt_ev has no fiscal-year dimension (sec_valuations is a single
            # latest-snapshot row), so only long_term_debt_bs can be rescued this way - only
            # search when total_debt_ev is also absent (it remains the primary source below).
            roic_long_term_debt = long_term_debt_bs
            if total_debt_ev is None and long_term_debt_bs is None:
                # `data_unavailable IS NOT TRUE` (applied inside the helper) excludes an
                # incomplete/stale-orphan stub.
                fallback_debt = self._fetch_balance_sheet_anchor_fallback(symbol, "long_term_debt")
                if fallback_debt is not None:
                    roic_long_term_debt = fallback_debt

            invested_capital = None
            debt_for_roic = total_debt_ev if total_debt_ev is not None else roic_long_term_debt

            # A symbol that has never tagged ANY debt component across its full balance-sheet
            # history AND never reports nonzero interest_expense is double-confirmed
            # structurally debt-free (SPACs, pre-revenue biotech, small tech/services - see
            # _get_never_tagged_debt_components_symbols()'s docstring), not an extraction gap.
            # Mirrors load_sec_valuations.py's own EV treatment of missing total_debt as 0, but
            # requires the interest_expense corroboration since debt_to_equity/roce_pct/
            # roic_pct feed real trading scores and a false "0 debt" would overstate safety.
            if (
                debt_for_roic is None
                and symbol in self._get_never_tagged_debt_components_symbols()
                and symbol in self._get_never_tagged_interest_expense_symbols()
            ):
                debt_for_roic = 0.0

            if (
                roic_stockholders_equity is not None
                and debt_for_roic is not None
                and roic_cash_and_equivalents is not None
            ):
                invested_capital = roic_stockholders_equity + debt_for_roic - roic_cash_and_equivalents
            # A large cash pile (common for well-capitalized biotechs, e.g. equity-raise-funded)
            # can push equity + debt - cash negative even with real, complete SEC data - a real
            # business-state fact, not an absent concept (same distinction as
            # roic_pct_unprofitable below for pretax losses).
            roic_pct_negative_invested_capital = invested_capital is not None and invested_capital <= 0
            # roic_operating_income (NOPAT's other input) can independently be None for
            # no-tax-concept REITs even when effective_tax_rate's own branch already handles
            # them - same structural-not-missing gate.
            no_operating_income_concept_roic = (
                roic_operating_income is None and symbol in self._get_no_tax_concept_symbols()
            )

            if (
                effective_tax_rate is not None
                and roic_operating_income is not None
                and invested_capital is not None
                and invested_capital > 0
            ):
                nopat = roic_operating_income * (1 - effective_tax_rate)
                # Same near-zero-denominator bound as gross_margin/ebitda_margin/
                # interest_coverage above - invested_capital > 0 only rules out literal zero,
                # not an implausibly tiny-but-positive value that explodes the ratio.
                computed_roic_pct = (nopat / invested_capital) * 100
                if abs(computed_roic_pct) > 1000:
                    roic_fallback = self._find_plausible_cross_year_roic_ratio(symbol, "roic_pct")
                    if roic_fallback is not None:
                        metrics["roic_pct"] = roic_fallback
                        stale_fallback_metrics.append("roic_pct")
                    else:
                        failed_metrics.append("roic_pct")
                        implausible_ratio_metrics.append("roic_pct")
                else:
                    metrics["roic_pct"] = float(computed_roic_pct)
            else:
                failed_metrics.append("roic_pct")

            # ROCE = EBIT / (Equity + Debt), deliberately NO cash subtraction - unlike roic_pct
            # above, whose cash-netted invested_capital goes negative for well-capitalized,
            # profitable companies. roic_operating_income is used as the EBIT proxy (pretax,
            # classic ROCE convention - not NOPAT). Replaces roic_score in the composite (see
            # weighted_score) - more stable and higher coverage per FM validation.
            capital_employed = (
                roic_stockholders_equity + debt_for_roic
                if roic_stockholders_equity is not None and debt_for_roic is not None
                else None
            )
            roce_pct_negative_capital_employed = capital_employed is not None and capital_employed <= 0
            if roic_operating_income is not None and capital_employed is not None and capital_employed > 0:
                computed_roce_pct = (roic_operating_income / capital_employed) * 100
                if abs(computed_roce_pct) > 1000:
                    roce_fallback = self._find_plausible_cross_year_roic_ratio(symbol, "roce_pct")
                    if roce_fallback is not None:
                        metrics["roce_pct"] = roce_fallback
                        stale_fallback_metrics.append("roce_pct")
                    else:
                        failed_metrics.append("roce_pct")
                        implausible_ratio_metrics.append("roce_pct")
                else:
                    metrics["roce_pct"] = float(computed_roce_pct)
            else:
                failed_metrics.append("roce_pct")

            # Debt to Equity: interest-bearing Debt / Equity (replaced the old Total
            # Liabilities / Equity formula). Reuses debt_for_roic/roic_stockholders_equity, same
            # inputs as ROIC/ROCE above. Correlates strongly with debt_to_assets (corr=0.67), so
            # replaces it in the composite rather than being scored alongside it.
            if roic_stockholders_equity is not None and debt_for_roic is not None and roic_stockholders_equity != 0:
                computed_debt_to_equity = debt_for_roic / roic_stockholders_equity
                if abs(computed_debt_to_equity) > 1000:
                    failed_metrics.append("debt_to_equity")
                    implausible_ratio_metrics.append("debt_to_equity")
                else:
                    metrics["debt_to_equity"] = float(computed_debt_to_equity)
            else:
                failed_metrics.append("debt_to_equity")

            # FCF to Net Income = Free Cash Flow / Net Income
            if free_cash_flow is not None and net_income is not None and net_income != 0:
                metrics["fcf_to_net_income"] = float(free_cash_flow / net_income)
            else:
                failed_metrics.append("fcf_to_net_income")

            # OCF to Net Income = Operating Cash Flow / Net Income
            if operating_cash_flow is not None and net_income is not None and net_income != 0:
                metrics["ocf_to_net_income"] = float(operating_cash_flow / net_income)
            else:
                failed_metrics.append("ocf_to_net_income")

            # Payout Ratio = Dividends / Net Income (% of earnings paid out). A loss year
            # (net_income <= 0) makes the ratio not meaningful - "not applicable", not a data
            # gap; distinguish from genuine non-payers (no dividend history at all) and true
            # extraction gaps (dividend history exists elsewhere, concept missing this year).
            # Magnitude-guarded like the other ratio fields: quality_metrics.payout_ratio is
            # NUMERIC(10,2) (max ~1e8) and a near-zero net_income denominator can otherwise
            # explode the ratio and crash the INSERT with NumericValueOutOfRange.
            MAX_PAYOUT_RATIO_ABS_PCT = 1000.0  # noqa: N806
            payout_ratio_reason = None
            if dividends_paid_with_prior_year_fallback is not None and net_income is not None and net_income > 0:
                payout_ratio_pct = (dividends_paid_with_prior_year_fallback / net_income) * 100
                if abs(payout_ratio_pct) <= MAX_PAYOUT_RATIO_ABS_PCT:
                    metrics["payout_ratio"] = float(payout_ratio_pct)
                else:
                    failed_metrics.append("payout_ratio")
                    payout_ratio_reason = "implausible_ratio"
            else:
                failed_metrics.append("payout_ratio")
                if dividends_paid_with_prior_year_fallback is not None and net_income is not None and net_income <= 0:
                    payout_ratio_reason = "unprofitable_stock"
                # Same net_income_not_reported gate net_margin/roa/roe already use - genuinely
                # never-tagged net_income, not just <=0.
                elif net_income is None and (
                    symbol in self._get_no_recent_net_income_symbols()
                    or symbol in self._get_never_tagged_net_income_symbols()
                ):
                    payout_ratio_reason = "net_income_not_reported"
                else:
                    # Same "ever, not recently" distinction as dividend_yield_reason above - a
                    # symbol that discontinued its dividend years ago has real history on file
                    # but isn't a current data gap. Same 2-year recency window used there.
                    with _owner().DatabaseContext("read") as cur:
                        cur.execute(
                            """
                            SELECT 1 FROM dividend_data
                            WHERE symbol = %s AND data_unavailable = FALSE
                              AND ex_dividend_date > CURRENT_DATE - INTERVAL '2 years'
                            LIMIT 1
                            """,
                            (symbol,),
                        )
                        has_real_dividend_history = cur.fetchone() is not None
                    payout_ratio_reason = (
                        "missing_sec_data" if has_real_dividend_history else "non_dividend_paying_stock"
                    )

            # Absolute cash flow values
            #
            # FIXED 2026-09-05 (goal session: "implausible values"/missing-XBRL sweep):
            # unlike fcf_margin/fcf_to_net_income, this field isn't a ratio requiring same-year
            # pairing with anything else - it's a standalone dollar figure, so an older real
            # value is a straightforward, safe substitution (same reasoning as the roic_pct/
            # roce_pct cross-year fallback) rather than the local-variable-only, label-only
            # treatment fcf_margin/fcf_to_net_income need to preserve their anchor-year
            # alignment (see the fcf_margin fallback's own comment above for why those stay
            # separate). Deliberately a fresh query, not a reuse of
            # `_get_free_cash_flow_available_elsewhere_symbols()` (that gate only proves
            # membership for labeling, not the actual value).
            standalone_free_cash_flow = free_cash_flow
            if standalone_free_cash_flow is None:
                # Same two-tier recency window as the fcf_margin fallback above (recent 3 fiscal
                # years preferred, only reaching further back if nothing qualifies there) - keeps
                # this from resurrecting a decade-stale figure for a symbol that's simply been
                # `_get_no_recent_free_cash_flow_symbols()`-flagged for years.
                with _owner().DatabaseContext("read") as cur:
                    cur.execute(
                        """
                        SELECT free_cash_flow FROM annual_cash_flow
                        WHERE symbol = %s AND free_cash_flow IS NOT NULL AND data_unavailable = FALSE
                          AND fiscal_year >= EXTRACT(YEAR FROM CURRENT_DATE)::int - 3
                        ORDER BY fiscal_year DESC LIMIT 1
                        """,
                        (symbol,),
                    )
                    fallback_row = cur.fetchone()
                    if not fallback_row:
                        cur.execute(
                            """
                            SELECT free_cash_flow FROM annual_cash_flow
                            WHERE symbol = %s AND free_cash_flow IS NOT NULL AND data_unavailable = FALSE
                            ORDER BY fiscal_year DESC LIMIT 1
                            """,
                            (symbol,),
                        )
                        fallback_row = cur.fetchone()
                if fallback_row:
                    standalone_free_cash_flow = self._nan_to_none(
                        safe_float(fallback_row[0], f"{symbol}.free_cash_flow_fallback_year", allow_none=True)
                    )
            if standalone_free_cash_flow is not None and abs(standalone_free_cash_flow) < MAX_ABSOLUTE_DOLLAR_VALUE:
                metrics["free_cash_flow"] = float(standalone_free_cash_flow)
            else:
                failed_metrics.append("free_cash_flow")

            # FIXED 2026-09-05 (same fix as standalone_free_cash_flow above): operating_cash_flow
            # is also a standalone dollar figure with no same-year pairing requirement of its
            # own - ocf_to_net_income/accruals_ratio/the YoY growth check above DO need the
            # anchor-year-aligned global `operating_cash_flow`, so this fallback is scoped to a
            # separate local variable exactly like standalone_free_cash_flow.
            standalone_operating_cash_flow = operating_cash_flow
            if standalone_operating_cash_flow is None:
                with _owner().DatabaseContext("read") as cur:
                    cur.execute(
                        """
                        SELECT operating_cash_flow FROM annual_cash_flow
                        WHERE symbol = %s AND operating_cash_flow IS NOT NULL AND data_unavailable = FALSE
                          AND fiscal_year >= EXTRACT(YEAR FROM CURRENT_DATE)::int - 3
                        ORDER BY fiscal_year DESC LIMIT 1
                        """,
                        (symbol,),
                    )
                    fallback_row = cur.fetchone()
                    if not fallback_row:
                        cur.execute(
                            """
                            SELECT operating_cash_flow FROM annual_cash_flow
                            WHERE symbol = %s AND operating_cash_flow IS NOT NULL AND data_unavailable = FALSE
                            ORDER BY fiscal_year DESC LIMIT 1
                            """,
                            (symbol,),
                        )
                        fallback_row = cur.fetchone()
                if fallback_row:
                    standalone_operating_cash_flow = self._nan_to_none(
                        safe_float(fallback_row[0], f"{symbol}.operating_cash_flow_fallback_year", allow_none=True)
                    )
            if (
                standalone_operating_cash_flow is not None
                and abs(standalone_operating_cash_flow) < MAX_ABSOLUTE_DOLLAR_VALUE
            ):
                metrics["operating_cash_flow"] = float(standalone_operating_cash_flow)
            else:
                failed_metrics.append("operating_cash_flow")

            # Absolute balance sheet values from sec_valuations
            if total_debt_ev is not None and abs(total_debt_ev) < MAX_ABSOLUTE_DOLLAR_VALUE:
                metrics["total_debt"] = float(total_debt_ev)
            else:
                failed_metrics.append("total_debt")

            if total_cash_ev is not None and abs(total_cash_ev) < MAX_ABSOLUTE_DOLLAR_VALUE:
                metrics["total_cash"] = float(total_cash_ev)
            else:
                failed_metrics.append("total_cash")

            if ebitda_ev is not None and abs(ebitda_ev) < MAX_ABSOLUTE_DOLLAR_VALUE:
                metrics["ebitda"] = float(ebitda_ev)
            else:
                failed_metrics.append("ebitda")

            # Cash per Share = Total Cash / Shares Outstanding
            cash_per_share_shares_missing = False
            if total_cash_ev is not None and shares_outstanding is not None and shares_outstanding > 0:
                metrics["cash_per_share"] = float(total_cash_ev / shares_outstanding)
            else:
                failed_metrics.append("cash_per_share")
                # shares_outstanding here is sv.shares_outstanding (quality_row[11]) - same
                # column that already gets its own "shares_outstanding_unavailable" reason
                # elsewhere in this codebase, not a generic SEC extraction gap.
                cash_per_share_shares_missing = shares_outstanding is None or shares_outstanding <= 0

            # Earnings Growth YoY = (Current EPS - Prior Year EPS) / Prior Year EPS * 100.
            # Bounded like the sibling *_growth_yoy fields below: a near-zero prior-year base
            # can overflow NUMERIC(10,2) and crash the whole row's INSERT. Appends to
            # implausible_ratio_metrics (in addition to failed_metrics) so a real-but-rejected
            # ratio is distinguished from a genuinely absent prior-year base.
            if earnings_per_share is not None and prior_year_eps is not None and prior_year_eps != 0:
                try:
                    yoy_growth = ((earnings_per_share - prior_year_eps) / abs(prior_year_eps)) * 100
                    if abs(yoy_growth) < MAX_TREND_PERCENTAGE_POINTS:
                        metrics["earnings_growth_yoy"] = float(round(yoy_growth, 2))
                    else:
                        failed_metrics.append("earnings_growth_yoy")
                        implausible_ratio_metrics.append("earnings_growth_yoy")
                except (ValueError, TypeError):
                    failed_metrics.append("earnings_growth_yoy")
            else:
                failed_metrics.append("earnings_growth_yoy")

            # Revenue Growth YoY = (Current Revenue - Prior Year Revenue) / Prior Year Revenue * 100
            if revenue is not None and prior_year_revenue is not None and prior_year_revenue != 0:
                try:
                    yoy_growth = ((revenue - prior_year_revenue) / abs(prior_year_revenue)) * 100
                    if abs(yoy_growth) < MAX_TREND_PERCENTAGE_POINTS:
                        metrics["revenue_growth_yoy"] = float(round(yoy_growth, 2))
                    else:
                        failed_metrics.append("revenue_growth_yoy")
                        implausible_ratio_metrics.append("revenue_growth_yoy")
                except (ValueError, TypeError):
                    failed_metrics.append("revenue_growth_yoy")
            else:
                failed_metrics.append("revenue_growth_yoy")

            # TREND FIELDS (new fields for enhanced scoring)
            # Net Income Growth YoY - only if actual prior net income available.
            # Bounded by MAX_TREND_PERCENTAGE_POINTS (same guard as roe_trend below): a real but
            # near-zero prior-year base can overflow this column's NUMERIC(10,4) and crash the
            # whole row's INSERT.
            if net_income is not None and prior_year_net_income is not None and prior_year_net_income != 0:
                if (net_income > 0 and prior_year_net_income < 0) or (net_income < 0 and prior_year_net_income > 0):
                    # Profit<->loss sign flip - growth % is mathematically undefined here,
                    # same treatment _cagr()/_compute_period_growth already give this exact
                    # condition (root cause of CRWD's -966% net_income_growth_yoy despite
                    # genuinely strong ~22% revenue growth).
                    sign_change_yoy_metrics.append("net_income_growth_yoy")
                elif (
                    prior_year_revenue is not None
                    and prior_year_revenue > 0
                    and abs(prior_year_net_income) < 0.01 * prior_year_revenue
                ):
                    immaterial_base_yoy_metrics.append("net_income_growth_yoy")
                else:
                    try:
                        ni_growth = ((net_income - prior_year_net_income) / abs(prior_year_net_income)) * 100
                        if abs(ni_growth) < MAX_PLAUSIBLE_GROWTH_PCT:
                            metrics["net_income_growth_yoy"] = float(round(ni_growth, 2))
                        else:
                            implausible_ratio_metrics.append("net_income_growth_yoy")
                    except (ValueError, TypeError, ZeroDivisionError) as e:
                        logger.warning(
                            f"[{symbol}] Failed to calculate net_income_growth_yoy: {type(e).__name__}. "
                            f"Metric marked data_unavailable."
                        )

            # Operating Income Growth YoY - uses the same EBIT-approximation fallback as
            # operating_income_for_margin (current year) and prior_year_operating_income_for_trend
            # (prior year) so filers that never tag OperatingIncomeLoss aren't blocked here too.
            if (
                operating_income_for_margin is not None
                and prior_year_operating_income_for_trend is not None
                and prior_year_operating_income_for_trend != 0
            ):
                if (operating_income_for_margin > 0 and prior_year_operating_income_for_trend < 0) or (
                    operating_income_for_margin < 0 and prior_year_operating_income_for_trend > 0
                ):
                    sign_change_yoy_metrics.append("operating_income_growth_yoy")
                elif (
                    prior_year_revenue is not None
                    and prior_year_revenue > 0
                    and abs(prior_year_operating_income_for_trend) < 0.01 * prior_year_revenue
                ):
                    immaterial_base_yoy_metrics.append("operating_income_growth_yoy")
                else:
                    try:
                        oi_growth = (
                            (operating_income_for_margin - prior_year_operating_income_for_trend)
                            / abs(prior_year_operating_income_for_trend)
                        ) * 100
                        if abs(oi_growth) < MAX_TREND_PERCENTAGE_POINTS:
                            metrics["operating_income_growth_yoy"] = float(round(oi_growth, 2))
                        else:
                            implausible_ratio_metrics.append("operating_income_growth_yoy")
                    except (ValueError, TypeError, ZeroDivisionError):
                        pass

            # Margin Trends (current - prior year) - only compute when actual prior data available.
            # The trend-level MAX_TREND_PERCENTAGE_POINTS check only bounds the DELTA, not the
            # two margins that produce it - a near-zero-revenue year can put curr/prior
            # individually in the tens of thousands of percent while their difference still
            # lands under threshold. Bound each side of the subtraction first (same |ratio| <=
            # 1000 bound as the base margin fields) - a trend from two implausible margins is
            # itself meaningless.
            MAX_MARGIN_ABS_PCT = 1000.0  # noqa: N806
            if revenue is not None and prior_year_revenue is not None and revenue > 0 and prior_year_revenue > 0:
                # Gross Margin Trend - prefers each year's directly-reported gross_profit (same
                # source the base gross_margin metric above falls back to), only deriving from
                # revenue - cost_of_revenue when a filer doesn't tag GrossProfit at all (some
                # filers report GrossProfit but never a separate CostOfRevenue concept).
                curr_gross_profit = (
                    gross_profit_direct
                    if gross_profit_direct is not None
                    else (revenue - cost_of_revenue if cost_of_revenue is not None else None)
                )
                prior_gross_profit = (
                    prior_year_gross_profit
                    if prior_year_gross_profit is not None
                    else (
                        prior_year_revenue - prior_year_cost_of_revenue
                        if prior_year_cost_of_revenue is not None
                        else None
                    )
                )
                if curr_gross_profit is not None and prior_gross_profit is not None:
                    # Prefer the base gross_margin metric's own value when already computed
                    # above - it may already reflect that field's cross-year implausible-ratio
                    # fallback (a genuine extraction artifact this fiscal year, e.g. near-zero
                    # revenue, rescued from a different coherent year), so reusing it here
                    # avoids re-deriving the SAME raw (and possibly implausible) ratio inline.
                    curr_gm = metrics.get("gross_margin")
                    if curr_gm is None:
                        curr_gm = (curr_gross_profit / revenue) * 100 if revenue > 0 else None
                    prior_gm = (prior_gross_profit / prior_year_revenue) * 100 if prior_year_revenue > 0 else None
                    if (
                        curr_gm is not None
                        and prior_gm is not None
                        and abs(curr_gm) <= MAX_MARGIN_ABS_PCT
                        and abs(prior_gm) <= MAX_MARGIN_ABS_PCT
                    ):
                        try:
                            gm_trend = round(curr_gm - prior_gm, 2)
                            if abs(gm_trend) < MAX_TREND_PERCENTAGE_POINTS:
                                metrics["gross_margin_trend"] = float(gm_trend)
                            else:
                                implausible_ratio_metrics.append("gross_margin_trend")
                        except (ValueError, TypeError, ZeroDivisionError):
                            pass
                    elif curr_gm is not None and prior_gm is not None:
                        # Inputs existed but one/both margins blew past MAX_MARGIN_ABS_PCT
                        # (e.g. cost_of_revenue exceeding revenue) - a real, if garbage,
                        # ratio that was deliberately excluded, not a missing-data gap.
                        implausible_ratio_metrics.append("gross_margin_trend")

                # Operating Margin Trend - uses the same EBIT-approximation fallback as
                # operating_income_growth_yoy above (see prior_year_operating_income_for_trend).
                if (
                    operating_income_for_margin is not None
                    and prior_year_operating_income_for_trend is not None
                    and prior_year_revenue > 0
                ):
                    # Prefer the base operating_margin metric's own value when already
                    # computed above - see gross_margin_trend's comment on why.
                    curr_om = metrics.get("operating_margin")
                    if curr_om is None:
                        curr_om = (operating_income_for_margin / revenue) * 100
                    prior_om = (prior_year_operating_income_for_trend / prior_year_revenue) * 100
                    if abs(curr_om) <= MAX_MARGIN_ABS_PCT and abs(prior_om) <= MAX_MARGIN_ABS_PCT:
                        try:
                            om_trend = round(curr_om - prior_om, 2)
                            if abs(om_trend) < MAX_TREND_PERCENTAGE_POINTS:
                                metrics["operating_margin_trend"] = float(om_trend)
                            else:
                                implausible_ratio_metrics.append("operating_margin_trend")
                        except (ValueError, TypeError, ZeroDivisionError):
                            pass
                    else:
                        implausible_ratio_metrics.append("operating_margin_trend")

                # Net Margin Trend - only if actual prior net income available
                if net_income is not None and prior_year_net_income is not None and prior_year_revenue > 0:
                    # Prefer the base net_margin metric's own value when already computed
                    # above - see gross_margin_trend's comment on why.
                    curr_nm = metrics.get("net_margin")
                    if curr_nm is None:
                        curr_nm = (net_income / revenue) * 100
                    prior_nm = (prior_year_net_income / prior_year_revenue) * 100
                    if abs(curr_nm) <= MAX_MARGIN_ABS_PCT and abs(prior_nm) <= MAX_MARGIN_ABS_PCT:
                        try:
                            nm_trend = round(curr_nm - prior_nm, 2)
                            if abs(nm_trend) < MAX_TREND_PERCENTAGE_POINTS:
                                metrics["net_margin_trend"] = float(nm_trend)
                            else:
                                implausible_ratio_metrics.append("net_margin_trend")
                        except (ValueError, TypeError, ZeroDivisionError):
                            pass
                    else:
                        implausible_ratio_metrics.append("net_margin_trend")

            # Sustainable Growth Rate = ROE * Retention Ratio - only with real data
            # dividends_paid is None (not 0) for genuine non-dividend-payers, since SEC XBRL
            # simply omits the PaymentsOfDividends concept when nothing was paid - same
            # "confirmed non-payer vs missing data" ambiguity as dividend_yield/payout_ratio
            # above. Confirmed non-payers still compute (retention_ratio = 1.0).
            sgr_reason = None
            # Same prior-year fallback as payout_ratio above, so a confirmed-recent payer's
            # current-year extraction gap doesn't get stuck on "missing_sec_data".
            sgr_dividends_paid = dividends_paid_with_prior_year_fallback
            if (
                sgr_dividends_paid is None
                and stockholders_equity is not None
                and net_income is not None
                and stockholders_equity > 0
            ):
                # Same "ever, not recently" distinction as dividend_yield_reason/
                # payout_ratio_reason above; same 2-year recency window.
                with _owner().DatabaseContext("read") as cur:
                    cur.execute(
                        """
                        SELECT 1 FROM dividend_data
                        WHERE symbol = %s AND data_unavailable = FALSE
                          AND ex_dividend_date > CURRENT_DATE - INTERVAL '2 years'
                        LIMIT 1
                        """,
                        (symbol,),
                    )
                    has_real_dividend_history = cur.fetchone() is not None
                if has_real_dividend_history:
                    # FIXED 2026-09-05 (goal session: "SEC/XBRL missing data to zero" audit):
                    # annual_cash_flow.dividends_paid is unpopulated for many real payers
                    # (live-confirmed SPG/RS/CNK - see value_metrics.dividend_yield's own TIER 4
                    # fallback docstring, same root cause) - this used to give up entirely and
                    # blame "missing_sec_data" the instant has_real_dividend_history confirmed a
                    # real payer, never trying the same dividend_data.dividend_per_share TTM
                    # recovery TIER 4 already uses. Mirrors that fallback exactly: trailing
                    # ~370-day per-share sum x shares_outstanding = a real, if approximate,
                    # dollar dividends_paid figure - same recency window, same "a confirmed real
                    # payer deserves a real attempt before falling back to the generic label"
                    # reasoning.
                    _sgr_ttm_attempted = False
                    if shares_outstanding is not None and shares_outstanding > 0:
                        _sgr_ttm_attempted = True
                        with _owner().DatabaseContext("read") as cur:
                            cur.execute(
                                """
                                SELECT SUM(dividend_per_share) FROM dividend_data
                                WHERE symbol = %s AND data_unavailable = FALSE
                                  AND dividend_per_share IS NOT NULL
                                  AND ex_dividend_date > CURRENT_DATE - INTERVAL '370 days'
                                """,
                                (symbol,),
                            )
                            ttm_row = cur.fetchone()
                            ttm_dividend_per_share = ttm_row[0] if ttm_row else None
                        if ttm_dividend_per_share is not None and ttm_dividend_per_share > 0:
                            sgr_dividends_paid = float(ttm_dividend_per_share) * shares_outstanding
                    if sgr_dividends_paid is None and _sgr_ttm_attempted:
                        # FIXED 2026-09-05 (goal session: "SEC/XBRL missing data to zero"
                        # follow-up, same fix as value_metrics.dividend_yield's identical gap):
                        # a real payment inside the 2-year has_real_dividend_history window but
                        # outside the 370-day TTM window just used is genuine recent data, too
                        # stale to compute a confident current dividends_paid figure from - a
                        # real fact, not a missing SEC concept, same "Legitimate / not
                        # applicable" class as a confirmed non-payer. Only applies when the TTM
                        # attempt actually ran (shares_outstanding was available) - no
                        # shares_outstanding at all stays the genuine "missing_sec_data" gap.
                        sgr_reason = "dividend_lapsed_beyond_ttm_window"
                    elif sgr_dividends_paid is None:
                        sgr_reason = "missing_sec_data"
                else:
                    sgr_dividends_paid = 0.0

            if stockholders_equity is not None and net_income is not None and stockholders_equity > 0:
                if sgr_dividends_paid is not None and net_income != 0:
                    # Actual retention ratio = (earnings - dividends) / earnings
                    roe_pct = net_income / stockholders_equity
                    retention_ratio = 1.0 - (sgr_dividends_paid / abs(net_income)) if net_income != 0 else 0.0
                    try:
                        sgr = round(roe_pct * retention_ratio * 100, 2)
                        # Bounded by MAX_PLAUSIBLE_GROWTH_PCT - a near-zero stockholders_equity
                        # base blows up roe_pct the same way a near-zero prior-year base blows
                        # up other ratios.
                        if abs(sgr) < MAX_PLAUSIBLE_GROWTH_PCT:
                            metrics["sustainable_growth_rate"] = float(sgr)
                        elif sgr_reason is None:
                            # Real value, deliberately rejected as implausible - not a missing
                            # SEC concept.
                            sgr_reason = "implausible_ratio"
                            implausible_ratio_metrics.append("sustainable_growth_rate")
                    except (ValueError, TypeError, ZeroDivisionError):
                        if sgr_reason is None:
                            sgr_reason = "missing_sec_data"
                elif sgr_reason is None:
                    sgr_reason = "missing_sec_data"
            elif sgr_reason is None:
                # stockholders_equity <= 0 (debt-funded buybacks/distributions, e.g.
                # YUM/IRM/COKE) is real data, not missing - SGR's "growth financeable from
                # retained earnings relative to the equity base" doesn't translate to a negative
                # base, so this deliberately still doesn't compute a value, but the label must
                # say why. Reuses "negative_book_value" (same as pb_ratio above) rather than
                # inventing a new string.
                if stockholders_equity is not None and stockholders_equity <= 0:
                    sgr_reason = "negative_book_value"
                # Remaining case: stockholders_equity is None, or (rarely) present but
                # net_income is None - reuse the same gates roe/roa/debt_to_equity use above.
                elif stockholders_equity is None and (
                    symbol in self._get_no_recent_stockholders_equity_symbols()
                    or symbol in self._get_never_tagged_stockholders_equity_symbols()
                ):
                    sgr_reason = "stockholders_equity_not_reported"
                elif net_income is None and (
                    symbol in self._get_no_recent_net_income_symbols()
                    or symbol in self._get_never_tagged_net_income_symbols()
                ):
                    sgr_reason = "net_income_not_reported"
                # quality_row_db's current-year income-statement columns require an EXACT
                # fiscal_year match to the balance-sheet anchor row (~line 716) - a
                # still-in-progress income statement for that year can leave net_income None
                # here even when real data exists 1-2 years back. Deliberately does NOT
                # recompute from the mismatched-year net_income (same discipline as
                # revenue_absent_from_anchor_year/implausible_dcf_result elsewhere) - label-only,
                # to distinguish "SEC data isn't there" from "SEC data is there, wrong year".
                elif net_income is None and symbol in self._get_net_income_available_elsewhere_symbols():
                    sgr_reason = "net_income_absent_from_anchor_year"
                else:
                    sgr_reason = "missing_sec_data"

            # ROE Trend = Current ROE - Prior ROE. Same per-side MAX_MARGIN_ABS_PCT bound as
            # the margin trends above - a near-zero prior-year equity base must be caught before
            # the subtraction, not just via the looser trend-level check on the delta. Uses
            # `!= 0` (not `> 0`) to match the base roe field - negative equity (debt-funded
            # buybacks/distributions, e.g. YUM/IRM/COKE) is real data, and MAX_MARGIN_ABS_PCT
            # already rejects genuine near-zero-equity garbage.
            if (
                stockholders_equity is not None
                and net_income is not None
                and stockholders_equity != 0
                and prior_year_stockholders_equity is not None
                and prior_year_net_income is not None
                and prior_year_stockholders_equity != 0
            ):
                # Prefer the base roe metric's own value when already computed above - it may
                # already reflect roe's own cross-year implausible-ratio fallback (see
                # gross_margin_trend's comment on why reusing it here is safe).
                curr_roe = metrics.get("roe")
                if curr_roe is None:
                    curr_roe = (net_income / stockholders_equity) * 100
                prior_roe = (prior_year_net_income / prior_year_stockholders_equity) * 100
                if abs(curr_roe) <= MAX_MARGIN_ABS_PCT and abs(prior_roe) <= MAX_MARGIN_ABS_PCT:
                    try:
                        roe_trend = round(curr_roe - prior_roe, 2)
                        if abs(roe_trend) < MAX_TREND_PERCENTAGE_POINTS:
                            metrics["roe_trend"] = float(roe_trend)
                        else:
                            implausible_ratio_metrics.append("roe_trend")
                    except (ValueError, TypeError, ZeroDivisionError):
                        pass
                else:
                    implausible_ratio_metrics.append("roe_trend")

            # FCF Growth YoY - only if actual prior FCF available
            # Same MAX_TREND_PERCENTAGE_POINTS overflow guard as net_income_growth_yoy above -
            # these three share the identical NUMERIC(10,4) column and tiny-prior-year-base risk.
            if free_cash_flow is not None and prior_year_free_cash_flow is not None and prior_year_free_cash_flow != 0:
                if (free_cash_flow > 0 and prior_year_free_cash_flow < 0) or (
                    free_cash_flow < 0 and prior_year_free_cash_flow > 0
                ):
                    sign_change_yoy_metrics.append("fcf_growth_yoy")
                elif (
                    prior_year_revenue is not None
                    and prior_year_revenue > 0
                    and abs(prior_year_free_cash_flow) < 0.01 * prior_year_revenue
                ):
                    immaterial_base_yoy_metrics.append("fcf_growth_yoy")
                else:
                    try:
                        fcf_growth = (
                            (free_cash_flow - prior_year_free_cash_flow) / abs(prior_year_free_cash_flow)
                        ) * 100
                        if abs(fcf_growth) < MAX_PLAUSIBLE_GROWTH_PCT:
                            metrics["fcf_growth_yoy"] = float(round(fcf_growth, 2))
                        else:
                            implausible_ratio_metrics.append("fcf_growth_yoy")
                    except (ValueError, TypeError, ZeroDivisionError):
                        pass

            # OCF Growth YoY - only if actual prior OCF available
            if (
                operating_cash_flow is not None
                and prior_year_operating_cash_flow is not None
                and prior_year_operating_cash_flow != 0
            ):
                if (operating_cash_flow > 0 and prior_year_operating_cash_flow < 0) or (
                    operating_cash_flow < 0 and prior_year_operating_cash_flow > 0
                ):
                    sign_change_yoy_metrics.append("ocf_growth_yoy")
                elif (
                    prior_year_revenue is not None
                    and prior_year_revenue > 0
                    and abs(prior_year_operating_cash_flow) < 0.01 * prior_year_revenue
                ):
                    immaterial_base_yoy_metrics.append("ocf_growth_yoy")
                else:
                    try:
                        ocf_growth = (
                            (operating_cash_flow - prior_year_operating_cash_flow) / abs(prior_year_operating_cash_flow)
                        ) * 100
                        if abs(ocf_growth) < MAX_TREND_PERCENTAGE_POINTS:
                            metrics["ocf_growth_yoy"] = float(round(ocf_growth, 2))
                        else:
                            implausible_ratio_metrics.append("ocf_growth_yoy")
                    except (ValueError, TypeError, ZeroDivisionError):
                        pass

            # Asset Growth YoY - now can compute with prior-year total assets
            if total_assets is not None and prior_year_total_assets is not None and prior_year_total_assets != 0:
                try:
                    asset_growth = ((total_assets - prior_year_total_assets) / abs(prior_year_total_assets)) * 100
                    if abs(asset_growth) < MAX_TREND_PERCENTAGE_POINTS:
                        metrics["asset_growth_yoy"] = float(round(asset_growth, 2))
                    else:
                        implausible_ratio_metrics.append("asset_growth_yoy")
                except (ValueError, TypeError, ZeroDivisionError):
                    pass

            # Record WHY each of these 9 trend/growth fields stayed None (mirrored into
            # growth_metrics via the _SHARED_TREND_FIELDS copy below). Order matters: check the
            # structural gross_profit gap and implausible-ratio rejection before falling through
            # to the generic "insufficient_prior_year_data" - both are legitimate-gap or
            # garbage-data cases, not evidence of a loader fetch failure.
            for _trend_field in (
                "net_income_growth_yoy",
                "operating_income_growth_yoy",
                "gross_margin_trend",
                "operating_margin_trend",
                "net_margin_trend",
                "roe_trend",
                "fcf_growth_yoy",
                "ocf_growth_yoy",
                "asset_growth_yoy",
            ):
                if metrics.get(_trend_field) is None:
                    if _trend_field == "gross_margin_trend" and no_gross_profit_concept:
                        metrics[f"{_trend_field}_unavailable_reason"] = "reit_special_entity"
                    elif _trend_field in sign_change_yoy_metrics:
                        metrics[f"{_trend_field}_unavailable_reason"] = "growth_undefined_sign_change"
                    elif _trend_field in immaterial_base_yoy_metrics:
                        metrics[f"{_trend_field}_unavailable_reason"] = "immaterial_prior_year_base"
                    elif _trend_field in implausible_ratio_metrics:
                        metrics[f"{_trend_field}_unavailable_reason"] = "implausible_ratio"
                    else:
                        metrics[f"{_trend_field}_unavailable_reason"] = "insufficient_prior_year_data"

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

            # sustainable_growth_rate uses NO prior-year data (see its own computation above),
            # so it gets its own explicit sgr_reason rather than the blanket trend-field loop.
            if metrics.get("sustainable_growth_rate") is None:
                metrics["sustainable_growth_rate_unavailable_reason"] = sgr_reason or "missing_sec_data"

            # Quarterly-derived fields (consecutive_positive_quarters, quarterly_growth_momentum,
            # earnings_growth_4q_avg, eps_growth_stability, earnings_surprise_avg,
            # earnings_beat_rate) are merged in from _compute_quarterly_metrics() above, which
            # sets its own specific reason when the value is None. The generic
            # "insufficient_quarterly_data"/"no_analyst_estimates" fallback for these fields
            # lives further below and only fires if that specific reason wasn't already set.

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
                    "etf_trust_no_gaap_financials"
                    if stockholders_equity is None and symbol in self._get_etf_trust_no_stockholders_equity_symbols()
                    else "no_recent_balance_sheet_data_reported"
                    if stockholders_equity is None
                    and (
                        symbol in self._get_no_recent_stockholders_equity_symbols()
                        or symbol in self._get_never_tagged_stockholders_equity_symbols()
                    )
                    # FIXED 2026-09-05 (goal session: "implausible values" sweep follow-up): a
                    # real, reported $0.00 total_assets/stockholders_equity (a blank-check/
                    # shell company pre-merger, e.g. OBX) makes every ratio in the `all( ...
                    # is None)` check above genuinely undefined (division by zero), tripping
                    # this same blanket early return - but neither branch above catches it
                    # since both only check `is None`, not "real zero". Distinct reason string
                    # from "no_recent_balance_sheet_data_reported" just above (a genuine "never
                    # tagged, real extraction gap" fact for most of its population) - a real
                    # reported zero is a known business fact (pre-merger shell, no assets yet),
                    # same "Legitimate / not applicable" class as reit_special_entity/
                    # non_dividend_paying_stock, not a data gap. Live-confirmed OBX: real
                    # total_assets=$0.00/stockholders_equity=$0.00 (2026 anchor row, not
                    # data_unavailable) - every quality_metrics ratio correctly came back None,
                    # but the row-level reason defaulted to generic "missing_sec_data" instead
                    # of this real, knowable cause.
                    else "zero_total_assets_reported_shell_entity"
                    if total_assets is not None
                    and total_assets <= 0
                    and (
                        symbol in self._get_no_recent_total_assets_symbols()
                        or symbol in self._get_never_tagged_total_assets_symbols()
                    )
                    else None
                )
                return self._unavailable_marker("quality_metrics", symbol, reason=row_level_reason)

            # Compute composite quality_score from available metrics
            # Score is average of available metrics (0-100 scale)
            # debt_to_assets is "lower is better" so it's converted to a comparable
            # higher-is-better score before joining the same clamp-and-average as the
            # raw percentage metrics below (100 - debt_to_assets%, e.g. 30% debt -> 70).
            #
            # NOTE: debt_to_assets is positively signed vs forward return in FM testing
            # (higher leverage -> higher forward return), the opposite of this "low debt is
            # good" inversion - a genuine, unresolved literature tension (Modigliani-Miller
            # leverage-beta effect vs. the distress-risk anomaly), not miscalibration. Left
            # unchanged pending a real distress-risk proxy (e.g. Altman Z-score) to resolve it.
            # debt_to_assets_score is no longer scored (replaced by debt_to_equity_score, see
            # that field's comment near roic_pct/roce_pct below) - metrics["debt_to_assets"]
            # itself is still persisted/displayed. Same for interest_coverage_score (dead after
            # interest_coverage was dropped from quality_components) - metrics
            # ["interest_coverage"] is still persisted independently.

            # roe/roa/operating_margin/net_margin are rescaled onto domain-informed curves
            # (not fed in as raw percentage points) - a flat 0-100=percentage mapping requires
            # a 100% margin to hit 100, a threshold no real business reaches, which
            # structurally compressed quality_score toward ~20-50 regardless of actual quality
            # and defeated min_composite_score's intended selectivity. This is a scale fix only
            # - the underlying roe/roa/operating_margin/net_margin values feeding
            # fama_macbeth_quality_factors.py are untouched. Thresholds are hand-set, not
            # FM-backtested (calibration, not a new empirical claim).
            roe_score = (
                self._margin_curve(metrics["roe"], [(10.0, 50.0), (20.0, 85.0), (40.0, 100.0)])
                if metrics["roe"] is not None
                else None
            )
            if stockholders_equity is not None and stockholders_equity <= 0:
                # Negative/zero book equity: net_income/equity can land positive when both are
                # negative (distressed co. with a loss on a negative equity base), which the
                # >1000 implausibility bound in _ratio_with_implausible_fallback doesn't catch
                # since it isn't a scale artifact - it's a real ratio that's directionally
                # meaningless. Floors to worst score rather than inverting into a spuriously
                # high one, same treatment as debt_to_equity_score below for the same reason.
                roe_score = 0.0
            roa_score = (
                self._margin_curve(metrics["roa"], [(3.0, 40.0), (8.0, 80.0), (15.0, 100.0)])
                if metrics["roa"] is not None
                else None
            )
            if total_assets is not None and total_assets <= 0:
                roa_score = 0.0
            # operating_margin_score/net_margin_score are not scored - operating_margin and
            # net_margin are still fetched/stored/displayed for reference, but neither carries
            # independent signal once ROA is controlled for (see
            # quality_operating_net_margin_no_independent_signal_over_roa_20260826 in MEMORY.md).

            # Quality pillar composition follows a literature-informed denominator-sharing
            # check (Novy-Marx 2013, Fama-French 2015 RMW, Sloan 1996, QMJ 2013): ROE
            # (NI/BookEquity) overlaps with FF's Operating Profitability ((Rev-COGS-SGA-
            # Interest)/BookEquity, same denominator), and ROA (NI/Assets) overlaps with
            # Novy-Marx's Gross Profitability ((Rev-COGS)/Assets, same denominator).
            # Cash-flow ROA (OCF/Assets) is not independent once ROA and Accruals Ratio
            # ((NI-OCF)/Assets, Sloan 1996) are both present - it's their exact linear
            # difference. operating_margin/net_margin (r=0.91, both profit/revenue ratios) are
            # the other genuinely redundant pair; roe/debt_to_assets (r=0.82) is a DIFFERENT,
            # DuPont-mechanical overlap the literature treats as fine to keep.
            #
            # No separate SG&A field exists in this pipeline - operating_income (GAAP, already
            # nets out COGS+SG&A) minus interest_expense is the available proxy for FF's
            # (Rev-COGS-SGA-Interest) construction.
            # operating_profitability_score/roic_score/accruals_score are not scored (failed
            # this repo's |t|>2 bar, or replaced by a more robust alternative - roic_score ->
            # roce_score, see below). The raw values are still computed and persisted for
            # display - only the scoring curves and composite weight are removed. See
            # weighted_score below for the full final composite.
            #
            # operating_income_for_margin falls back to the EBIT approximation (pretax_income +
            # interest_expense) for 40-F-style filers that never tag OperatingIncomeLoss - same
            # fallback operating_margin/operating_margin_trend already use.
            #
            # Guarded at |ratio|>1000 like every sibling ratio in this file - a near-zero
            # stockholders_equity base can otherwise blow this up multiple orders of magnitude.
            #
            # A negative or zero stockholders_equity denominator (real, common for mature
            # buyback-heavy filers) makes this ratio mathematically undefined - same "real
            # business-state fact, not an absent SEC concept" case pb_ratio/roic_pct/roce_pct
            # carve out via negative_book_value/negative_invested_capital/
            # negative_capital_employed. Reuses "negative_book_value" rather than a new string.
            operating_profitability_negative_equity = stockholders_equity is not None and stockholders_equity <= 0
            operating_profitability = None
            if operating_income_for_margin is not None and stockholders_equity is not None and stockholders_equity > 0:
                computed_operating_profitability = (
                    (operating_income_for_margin - (interest_expense or 0.0)) / stockholders_equity * 100.0
                )
                if abs(computed_operating_profitability) > 1000:
                    failed_metrics.append("operating_profitability")
                    implausible_ratio_metrics.append("operating_profitability")
                else:
                    operating_profitability = float(computed_operating_profitability)
            # Novy-Marx (2013, JFE) "gross profitability" - a firm that converts revenue to
            # gross profit efficiently relative to its asset base is a genuine quality signal
            # independent of the margin-based ratios already scored here. Guarded at
            # |ratio|>1000 like the sibling ratios in this file (near-zero total_assets can
            # otherwise blow this up multiple orders of magnitude).
            # Reuses gross_profit_used (same numerator gross_margin already recovers via
            # fallback) instead of a separate lookup. Banks/REITs and some real filers (e.g.
            # REGN, JAZZ) structurally never tag a gross-profit-style income statement at all -
            # distinguished from a genuine loader gap via no_gross_profit_concept below.
            gross_profit_for_profitability = gross_profit_used
            gross_profitability = None
            if gross_profit_for_profitability is not None and total_assets is not None and total_assets > 0:
                computed_gross_profitability = gross_profit_for_profitability / total_assets * 100.0
                if abs(computed_gross_profitability) > 1000:
                    failed_metrics.append("gross_profitability")
                    implausible_ratio_metrics.append("gross_profitability")
                else:
                    gross_profitability = float(computed_gross_profitability)
            # Breakpoints are a domain-judgment fit to the live distribution, not FM-fit to
            # inflection points.
            gross_profitability_score = (
                self._margin_curve(gross_profitability, [(10.0, 40.0), (25.0, 75.0), (50.0, 100.0)])
                if gross_profitability is not None
                else None
            )
            # Near-zero total_assets can blow this ratio up arbitrarily; same |ratio|>1000 guard
            # as gross_profitability/operating_profitability/fcf_margin.
            accruals_ratio = None
            if (
                net_income is not None
                and operating_cash_flow is not None
                and total_assets is not None
                and total_assets > 0
            ):
                computed_accruals_ratio = (net_income - operating_cash_flow) / total_assets * 100.0
                if abs(computed_accruals_ratio) > 1000:
                    failed_metrics.append("accruals_ratio")
                    implausible_ratio_metrics.append("accruals_ratio")
                else:
                    accruals_ratio = float(computed_accruals_ratio)
            # ROCE score: same curve shape as the old roic_score (both are "return on capital
            # deployed" measures, similar scale) - see the roce_pct computation's own comment
            # (near roic_pct above) for why ROCE replaces ROIC in the composite.
            roce_pct_val = metrics.get("roce_pct")
            roce_score = (
                self._margin_curve(roce_pct_val, [(8.0, 40.0), (15.0, 75.0), (25.0, 100.0)])
                if roce_pct_val is not None
                else None
            )
            # FCF Margin (free_cash_flow / revenue): cash-conversion efficiency net of capex,
            # independent of Accruals Ratio (never nets out capex). Replaces accruals_score in
            # the composite.
            #
            # The anchor fiscal year is chosen for balance-sheet freshness first, so it can have
            # free_cash_flow present but revenue not yet extracted (or vice versa) even though a
            # jointly-valid pair exists in an earlier year - the fallback below checks both
            # sides' None-ness, not just the numerator's, and is scoped to LOCAL variables
            # (fcf_margin_free_cash_flow/fcf_margin_revenue) rather than overwriting the global
            # free_cash_flow/revenue, which also feed fcf_to_net_income and fcf_growth_yoy and
            # must stay aligned to the anchor year for those.
            #
            # Each fallback tier scans every candidate year and picks the most recent one that's
            # actually plausible (|margin|<=1000), not just the single nearest year - an older
            # plausible year can sit behind a nearer implausible one (e.g. a near-zero-revenue
            # year).
            fcf_margin_free_cash_flow = free_cash_flow
            fcf_margin_revenue = revenue
            anchor_fcf_margin_implausible = (
                fcf_margin_free_cash_flow is not None
                and fcf_margin_revenue is not None
                and fcf_margin_revenue > 0
                and abs(fcf_margin_free_cash_flow / fcf_margin_revenue * 100.0) > 1000
            )
            if (
                fcf_margin_free_cash_flow is None
                or fcf_margin_revenue is None
                or fcf_margin_revenue <= 0
                or anchor_fcf_margin_implausible
            ):
                # anchor_fcf_margin_implausible also routes here (not just None/<=0) - a
                # near-zero-revenue anchor year is an extraction artifact, not a real business
                # characteristic, and an older fiscal year can have a plausible pair even when
                # the anchor doesn't (same gap class as operating_margin/net_margin's
                # _find_plausible_cross_year_ratio, fixed 2026-09-05 - this metric has its own
                # inline cross-table (cash_flow+income_statement) query instead of reusing that
                # helper because it needs a join those single-table lookups don't).
                #
                # FIXED 2026-09-05 (goal: "SEC/XBRL missing data to zero" sweep): neither side of
                # this JOIN filtered `data_unavailable`, so a disclaimed row's leftover stray
                # non-NULL free_cash_flow/revenue value could feed fcf_margin directly. Live-
                # confirmed 147 affected rows, e.g. BRK.A/BRK.B 2026 (free_cash_flow=$5.452B,
                # revenue=$63.137B, both flagged data_unavailable=TRUE) and CEG 2026.
                with _owner().DatabaseContext("read") as cur:
                    cur.execute(
                        """
                        SELECT free_cash_flow, revenue
                        FROM annual_cash_flow acf
                        JOIN annual_income_statement ais
                          ON ais.symbol = acf.symbol AND ais.fiscal_year = acf.fiscal_year
                        WHERE acf.symbol = %s AND acf.free_cash_flow IS NOT NULL AND ais.revenue IS NOT NULL
                          AND acf.data_unavailable IS NOT TRUE AND ais.data_unavailable IS NOT TRUE
                          AND acf.fiscal_year >= EXTRACT(YEAR FROM CURRENT_DATE)::int - 3
                        ORDER BY acf.fiscal_year DESC
                        """,
                        (symbol,),
                    )
                    fallback_fcf_rows = cur.fetchall()
                    if not fallback_fcf_rows:
                        cur.execute(
                            """
                            SELECT free_cash_flow, revenue
                            FROM annual_cash_flow acf
                            JOIN annual_income_statement ais
                              ON ais.symbol = acf.symbol AND ais.fiscal_year = acf.fiscal_year
                            WHERE acf.symbol = %s AND acf.free_cash_flow IS NOT NULL AND ais.revenue IS NOT NULL
                              AND acf.data_unavailable IS NOT TRUE AND ais.data_unavailable IS NOT TRUE
                            ORDER BY acf.fiscal_year DESC
                            """,
                            (symbol,),
                        )
                        fallback_fcf_rows = cur.fetchall()
                # row[0]/row[1] are raw Decimal; must cast to float before arithmetic here -
                # `Decimal * float` raises TypeError, which propagates through this function's
                # outer try/except and wipes out EVERY quality_metrics field for the symbol, not
                # just fcf_margin.
                fallback_fcf_row = next(
                    (
                        row
                        for row in fallback_fcf_rows
                        if row[1] is not None
                        and float(row[1]) > 0
                        and abs(float(row[0]) / float(row[1]) * 100.0) <= 1000
                    ),
                    fallback_fcf_rows[0] if fallback_fcf_rows else None,
                )
                if fallback_fcf_row:
                    fcf_margin_free_cash_flow = self._nan_to_none(
                        safe_float(fallback_fcf_row[0], f"{symbol}.free_cash_flow_fallback_year", allow_none=True)
                    )
                    fcf_margin_revenue = self._nan_to_none(
                        safe_float(fallback_fcf_row[1], f"{symbol}.revenue_fcf_margin_fallback_year", allow_none=True)
                    )
            fcf_margin = None
            if fcf_margin_free_cash_flow is not None and fcf_margin_revenue is not None and fcf_margin_revenue > 0:
                computed_fcf_margin = fcf_margin_free_cash_flow / fcf_margin_revenue * 100.0
                if abs(computed_fcf_margin) > 1000:
                    failed_metrics.append("fcf_margin")
                    implausible_ratio_metrics.append("fcf_margin")
                else:
                    fcf_margin = float(computed_fcf_margin)
            fcf_margin_score = (
                self._margin_curve(fcf_margin, [(5.0, 40.0), (15.0, 75.0), (30.0, 100.0)])
                if fcf_margin is not None
                else None
            )
            # Asset Turnover (Revenue / Total Assets, x100 - same "ratio-as-percentage" storage
            # convention as gross_profitability). Breakpoints: 0.3x (capital-intensive/utilities)
            # maps to 40, 0.8x (typical industrial) to 75, 1.5x+ (retail/services) to 100 -
            # domain-judgment, not FM-fit to inflection points.
            # Uses the same cross-year implausible-ratio fallback as roe/roa - see
            # _find_plausible_cross_year_ratio's docstring.
            asset_turnover, _asset_turnover_implausible = self._ratio_with_implausible_fallback(
                symbol, revenue, total_assets, "revenue", "total_assets", denominator_must_be_positive=True
            )
            if asset_turnover is None and _asset_turnover_implausible:
                failed_metrics.append("asset_turnover")
                implausible_ratio_metrics.append("asset_turnover")
            asset_turnover_score = (
                self._margin_curve(asset_turnover, [(30.0, 40.0), (80.0, 75.0), (150.0, 100.0)])
                if asset_turnover is not None
                else None
            )
            # Debt-to-Equity score: inverted (lower leverage = higher score), 0.5 maps to 75,
            # 1.0 to 50, 2.0+ to 0. Negative D/E (negative book equity, real financial distress)
            # floors to 0 rather than inverting into a spuriously high score.
            debt_to_equity_val = metrics.get("debt_to_equity")
            if debt_to_equity_val is None:
                debt_to_equity_score = None
            elif debt_to_equity_val < 0:
                debt_to_equity_score = 0.0
            else:
                debt_to_equity_score = max(0.0, min(100.0, 100.0 - (debt_to_equity_val / 2.0) * 100.0))
            # Margin volatility (QMJ 2013 Safety leg proxy): precomputed by the caller from
            # multi-year income_rows this function doesn't have (see _compute_margin_volatility).
            # Inverted curve: LOWER volatility (more stable margins) scores higher.
            # Must read the `margin_volatility` parameter directly, NOT `metrics.get(
            # "margin_volatility")` - that dict key is only written later in this function (see
            # the PERSISTED block below), so reading it here always returns None.
            margin_volatility_val = margin_volatility
            margin_volatility_score = (
                100.0 - self._margin_curve(margin_volatility_val, [(5.0, 20.0), (15.0, 60.0), (30.0, 100.0)])
                if margin_volatility_val is not None
                else None
            )

            # operating_margin_trend/net_margin_trend/roe_trend/payout_ratio/interest_coverage
            # score curves, equity_cluster/asset_cluster, debt_to_assets_score, roic_score, and
            # a flat accruals_score are all deliberately NOT scored (confirmed insignificant or
            # superseded per FM re-testing) even though raw values are still persisted:
            # debt_to_assets -> debt_to_equity_score, roic -> roce_score, accruals ->
            # fcf_margin_score. See _score_quality's docstring in load_stock_scores.py.
            #
            # Altman Z''-Score is not scored: it's a DISCRETE distress-triage classifier in the
            # literature, not meant to be continuously averaged into a magnitude-weighted
            # composite alongside ROA/ROE/margin ratios. A discrete distress-flag use may
            # belong on GOVERNANCE's trading-eligibility checks instead, separate from the
            # continuous quality_score - deliberately left open.
            #
            # Weights are set from both full-sample t-stat magnitude and a half-split
            # time-stability check - a component whose t-stat holds up identically across both
            # eras is weighted higher relative to its raw t-stat than one whose apparent
            # strength was concentrated in a short/recent window. debt_to_equity/roa/roce/
            # fcf_margin/roe (the "core five", 80% of the composite) have either the strongest
            # full-sample evidence or the best demonstrated time-stability. current_ratio was
            # tested and deliberately excluded (sign-flips across the half-split).
            # min_quality_weight_pct below is calibrated to ~40% of the composite's nominal
            # weight sum - above any thin-sample case found so far.
            #
            # Financial Services and Real Estate use a 7-input, two-cluster (profitability +
            # safety) structure instead of the flat 8-input tiered average - asset_turnover_score
            # is the one input confirmed (via isolated testing) to actively hurt Quality's
            # signal for these two sectors. Matches AQR QMJ's own profitability/safety cluster
            # construction. Both clusters and the top-level blend are internally renormalized
            # (same _weighted_avg helper) - a symbol missing part of one cluster still scores
            # off whatever it has.
            #
            # update_quality_roe_roce_percentiles() (further below) assumes every symbol was
            # scored via the flat 8-input structure - it does NOT reconcile through this
            # two-cluster structure, so it explicitly SKIPS Financial Services/Real Estate
            # symbols (see its own SQL filter); those symbols keep the Pass-1 curve-based
            # ROE/ROCE scores rather than the cross-sectional-percentile correction.
            sector = self._get_symbol_sector(symbol)
            if sector in ("Financial Services", "Real Estate"):
                profitability_cluster_score = self._weighted_avg(
                    [
                        (roe_score, 1.0),
                        (roa_score, 1.0),
                        (roce_score, 1.0),
                        (fcf_margin_score, 1.0),
                        (gross_profitability_score, 1.0),
                    ],
                    min_weight_pct=2.0,  # >=2 of 5 available - proportional to the 40%-of-101 floor below
                )
                safety_cluster_score = self._weighted_avg(
                    [(debt_to_equity_score, 1.0), (margin_volatility_score, 1.0)],
                    min_weight_pct=1.0,  # >=1 of 2 available
                )
                # Cluster weights (69/25, summing to 94 = universal branch's 101 minus
                # asset_turnover's 7) reflect each cluster's ACTUAL share of the universal
                # branch's nominal weight - a flat 1.0/1.0 split previously let a single
                # cluster, down to one raw field once its own internal floor was barely
                # cleared, produce a full undiscounted quality_score (e.g. an Oil Royalty
                # Trust scoring 97 off margin_volatility alone with every other input NULL).
                quality_components = [(profitability_cluster_score, 69.0), (safety_cluster_score, 25.0)]
                # Proportional to the universal branch's 40/101 (~39.6%) floor: 40 * (94/101) =
                # 37.2. Safety alone is only 25 points (below this floor), so a safety-only
                # symbol correctly returns None instead of a single-field score.
                min_quality_weight_pct = 37.2
            else:
                quality_components = [
                    (roe_score, 11.0),
                    (roa_score, 18.0),
                    (roce_score, 18.0),
                    (fcf_margin_score, 15.0),
                    (debt_to_equity_score, 18.0),
                    (margin_volatility_score, 7.0),
                    (asset_turnover_score, 7.0),
                    (gross_profitability_score, 7.0),
                ]
            # COMPLETENESS FLOOR: without it, renormalizing over 1-3 available components lets
            # a single extreme raw ratio (e.g. an oil/gas royalty trust's ROA of 700%+) drive
            # quality_score to 100.00 even though data_completeness/GOVERNANCE's eligibility
            # floor should treat this as thin data. Only applies to the universal (non-FS/RE)
            # branch - the sector-conditional branch sets its own proportional floor inline.
            if sector not in ("Financial Services", "Real Estate"):
                min_quality_weight_pct = 40.0
            available_quality_weight = sum(w for v, w in quality_components if v is not None)
            weighted_score = self._weighted_avg(quality_components, min_weight_pct=min_quality_weight_pct)

            metrics["gross_profitability"] = gross_profitability
            metrics["gross_profitability_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "gross_profitability" in implausible_ratio_metrics
                    else "reit_special_entity"
                    if no_gross_profit_concept
                    else "no_revenue_reported"
                    if symbol in self._get_blank_check_symbols()
                    or symbol in self._get_no_recent_revenue_symbols()
                    or symbol in self._get_never_tagged_revenue_symbols()
                    else "no_recent_total_assets_reported"
                    if (total_assets is None or total_assets <= 0)
                    and (
                        symbol in self._get_no_recent_total_assets_symbols()
                        or symbol in self._get_never_tagged_total_assets_symbols()
                    )
                    else "missing_sec_data"
                )
                if gross_profitability is None
                else None
            )
            metrics["operating_profitability"] = operating_profitability
            metrics["operating_profitability_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "operating_profitability" in implausible_ratio_metrics
                    else "negative_book_value"
                    if operating_profitability_negative_equity
                    else "reit_special_entity"
                    if no_operating_income_concept
                    # Label-only: the anchor year's income statement can lack operating_income
                    # (and its EBIT fallback) even when the symbol reports it in other years.
                    else "operating_income_absent_from_anchor_year"
                    if operating_income_for_margin is None
                    and symbol in self._get_operating_income_available_elsewhere_symbols()
                    # operating_profitability_negative_equity only fires when stockholders_equity
                    # is a real value <=0 - stays False (not caught) when equity is None.
                    else "stockholders_equity_not_reported"
                    if stockholders_equity is None
                    and (
                        symbol in self._get_no_recent_stockholders_equity_symbols()
                        or symbol in self._get_never_tagged_stockholders_equity_symbols()
                    )
                    else "operating_income_not_itemized"
                    if symbol in self._get_no_recent_operating_income_symbols()
                    or symbol in self._get_never_tagged_operating_income_symbols()
                    else "missing_sec_data"
                )
                if operating_profitability is None
                else None
            )
            metrics["accruals_ratio"] = accruals_ratio
            metrics["accruals_ratio_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "accruals_ratio" in implausible_ratio_metrics
                    # FIXED 2026-09-05 (goal: "SEC/XBRL missing data to zero" follow-up): a
                    # registered investment company files a "Statement of Changes in Net
                    # Assets" instead of a conventional cash-flow statement, leaving it with
                    # ZERO fiscal_year>0 annual_cash_flow rows - too sparse to match
                    # _get_no_recent_operating_cash_flow_symbols()'s own pattern. Live-confirmed
                    # GGN (GAMCO Global Gold, Natural Resources & Income Trust). Checked first,
                    # same priority as fcf_margin/fcf_yield's identical RIC check elsewhere.
                    else "registered_investment_company_no_xbrl"
                    if accruals_ratio is None and symbol in self._get_registered_investment_company_symbols()
                    else "no_recent_operating_cash_flow_reported"
                    if operating_cash_flow is None and symbol in self._get_no_recent_operating_cash_flow_symbols()
                    # Label-only: operating_cash_flow is None because the anchor year's own
                    # cash-flow row is unavailable, not because the symbol lacks real OCF.
                    else "operating_cash_flow_absent_from_anchor_year"
                    if operating_cash_flow is None
                    and symbol in self._get_operating_cash_flow_available_elsewhere_symbols()
                    else "no_recent_total_assets_reported"
                    if (total_assets is None or total_assets <= 0)
                    and (
                        symbol in self._get_no_recent_total_assets_symbols()
                        or symbol in self._get_never_tagged_total_assets_symbols()
                    )
                    else "missing_sec_data"
                )
                if accruals_ratio is None
                else None
            )
            metrics["margin_volatility"] = margin_volatility
            metrics["margin_volatility_unavailable_reason"] = (
                "insufficient_history" if margin_volatility is None else None
            )
            # Gate on `X is None` directly (not `"X" in failed_metrics`) - the compute blocks
            # above don't append fcf_margin/asset_turnover to failed_metrics when inputs are
            # merely missing (only when the |ratio|>1000 bound fires), so gating on
            # failed_metrics left many rows with a NULL value and no reason recorded.
            metrics["fcf_margin"] = fcf_margin
            metrics["fcf_margin_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "fcf_margin" in implausible_ratio_metrics
                    # Closed-end funds/investment trusts file no cash-flow statement at all
                    # (see _get_registered_investment_company_symbols' docstring) - checked
                    # before the generic never-tagged-FCF gate below so this more specific,
                    # correctly-categorized ("Legitimate / not applicable") reason wins.
                    else "registered_investment_company_no_xbrl"
                    if symbol in self._get_registered_investment_company_symbols()
                    # ADDED 2026-09-05: fcf_yield's own reason chain already checks this gate;
                    # fcf_margin's sibling chain here never did (AIG-verified: real OCF every
                    # year, capex-shaped concept stops after FY2023, not PPE-delta-recoverable
                    # since AIG never tags depreciation either).
                    else "capex_never_tagged_in_recent_filings"
                    if symbol in self._get_no_recent_capex_symbols()
                    # fcf_margin's own cross-year fallback (fcf_margin_free_cash_flow/
                    # fcf_margin_revenue above) already looks past the anchor row, so a
                    # remaining None here means both inputs are genuinely absent across recent
                    # fiscal years, not just off the anchor.
                    else "no_recent_free_cash_flow_reported"
                    if symbol in self._get_no_recent_free_cash_flow_symbols()
                    or symbol in self._get_never_tagged_free_cash_flow_symbols()
                    else "no_revenue_reported"
                    if symbol in self._get_no_recent_revenue_symbols()
                    or symbol in self._get_never_tagged_revenue_symbols()
                    # A real free_cash_flow value exists somewhere in the symbol's history but
                    # not in the same fiscal year as a real revenue value (the cross-year
                    # fallback above requires both in the SAME year) - live-confirmed FTW/OBX/
                    # AADX/AVEX/ALLO. Same reason free_cash_flow_unavailable_reason already
                    # uses for this exact gate above - label-only, no value recomputed.
                    else "free_cash_flow_absent_from_anchor_year"
                    if symbol in self._get_free_cash_flow_available_elsewhere_symbols()
                    else "missing_sec_data"
                )
                if fcf_margin is None
                else None
            )
            metrics["asset_turnover"] = asset_turnover
            metrics["asset_turnover_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "asset_turnover" in implausible_ratio_metrics
                    else "no_revenue_reported"
                    if symbol in self._get_no_recent_revenue_symbols()
                    or symbol in self._get_never_tagged_revenue_symbols()
                    else "no_recent_total_assets_reported"
                    if (total_assets is None or total_assets <= 0)
                    and (
                        symbol in self._get_no_recent_total_assets_symbols()
                        or symbol in self._get_never_tagged_total_assets_symbols()
                    )
                    # Label-only: revenue is None because the balance-sheet anchor year's own
                    # income-statement row is unavailable, not because the symbol lacks real
                    # revenue - the windowed gate above already ruled that out.
                    else "revenue_absent_from_anchor_year"
                    if revenue is None and symbol in self._get_revenue_available_elsewhere_symbols()
                    else "missing_sec_data"
                )
                if asset_turnover is None
                else None
            )

            # An unprofitable company still has a real, computed quality score (0,
            # after clamping) - that's honest data, not missing data. Do not mark
            # data_unavailable just because every component came out <= 0.
            if weighted_score is not None:
                metrics["quality_score"] = float(min(100.0, max(0.0, weighted_score)))

            # Only mark data_unavailable if ALL metrics are missing - partial quality data
            # (2-3 metrics) is legitimate and scored with completeness tracking, not discarded.
            metrics["roe_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "roe" in implausible_ratio_metrics
                    else "stockholders_equity_not_reported"
                    if stockholders_equity is None
                    and (
                        symbol in self._get_no_recent_stockholders_equity_symbols()
                        or symbol in self._get_never_tagged_stockholders_equity_symbols()
                    )
                    else "net_income_not_reported"
                    if net_income is None
                    and (
                        symbol in self._get_no_recent_net_income_symbols()
                        or symbol in self._get_never_tagged_net_income_symbols()
                    )
                    # Label-only: net_income is None because the anchor year's own
                    # income-statement row is unavailable, not because it lacks real net_income.
                    else "net_income_absent_from_anchor_year"
                    if net_income is None and symbol in self._get_net_income_available_elsewhere_symbols()
                    else "missing_sec_data"
                )
                if "roe" in failed_metrics
                else None
            )
            metrics["roa_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "roa" in implausible_ratio_metrics
                    else "no_recent_total_assets_reported"
                    if (total_assets is None or total_assets <= 0)
                    and (
                        symbol in self._get_no_recent_total_assets_symbols()
                        or symbol in self._get_never_tagged_total_assets_symbols()
                    )
                    else "net_income_not_reported"
                    if net_income is None
                    and (
                        symbol in self._get_no_recent_net_income_symbols()
                        or symbol in self._get_never_tagged_net_income_symbols()
                    )
                    else "net_income_absent_from_anchor_year"
                    if net_income is None and symbol in self._get_net_income_available_elsewhere_symbols()
                    else "missing_sec_data"
                )
                if "roa" in failed_metrics
                else None
            )
            metrics["operating_margin_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "operating_margin" in implausible_ratio_metrics
                    # Tonnage-tax shipping cos + REITs structurally never tag
                    # pretax_income/income_tax_expense (_get_no_tax_concept_symbols) -
                    # recategorized as reit_special_entity, not generic missing_sec_data.
                    else "reit_special_entity"
                    if no_operating_income_concept
                    # Label-only: anchor year's income statement lacks operating_income even
                    # though the symbol reports it elsewhere.
                    else "operating_income_absent_from_anchor_year"
                    if operating_income_for_margin is None
                    and symbol in self._get_operating_income_available_elsewhere_symbols()
                    else "no_revenue_reported"
                    if operating_income_for_margin is None
                    and (
                        symbol in self._get_blank_check_symbols()
                        or symbol in self._get_no_recent_revenue_symbols()
                        or symbol in self._get_never_tagged_revenue_symbols()
                    )
                    # Real, revenue-generating filer whose income statement never itemizes a
                    # distinct operating income subtotal.
                    else "operating_income_not_itemized"
                    if operating_income_for_margin is None
                    and (
                        symbol in self._get_no_recent_operating_income_symbols()
                        or symbol in self._get_never_tagged_operating_income_symbols()
                    )
                    else "missing_sec_data"
                )
                if "operating_margin" in failed_metrics
                else None
            )
            metrics["net_margin_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "net_margin" in implausible_ratio_metrics
                    else "net_income_not_reported"
                    if net_income is None
                    and (
                        symbol in self._get_no_recent_net_income_symbols()
                        or symbol in self._get_never_tagged_net_income_symbols()
                    )
                    # Label-only: net_income is None because the balance-sheet anchor year's
                    # own income-statement row is unavailable, not because the symbol lacks
                    # real net_income - both gates above already ruled that out.
                    else "net_income_absent_from_anchor_year"
                    if net_income is None and symbol in self._get_net_income_available_elsewhere_symbols()
                    else "missing_sec_data"
                )
                if "net_margin" in failed_metrics
                else None
            )
            metrics["debt_to_equity_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "debt_to_equity" in implausible_ratio_metrics
                    else "stockholders_equity_not_reported"
                    if stockholders_equity is None
                    and (
                        symbol in self._get_no_recent_stockholders_equity_symbols()
                        or symbol in self._get_never_tagged_stockholders_equity_symbols()
                    )
                    # debt_to_equity fails when EITHER roic_stockholders_equity or debt_for_roic
                    # is None - check the debt side too, not just equity.
                    else "total_debt_not_itemized"
                    if debt_for_roic is None
                    and (
                        symbol in self._get_no_recent_debt_components_symbols()
                        or symbol in self._get_never_tagged_debt_components_symbols()
                    )
                    else "missing_sec_data"
                )
                if "debt_to_equity" in failed_metrics
                else None
            )
            metrics["current_ratio_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "current_ratio" in implausible_ratio_metrics
                    else "reit_special_entity"
                    if unclassified_balance_sheet
                    else "no_recent_current_assets_reported"
                    if current_assets is None
                    and (
                        symbol in self._get_no_recent_current_assets_symbols()
                        or symbol in self._get_never_tagged_current_assets_symbols()
                    )
                    else "no_recent_current_liabilities_reported"
                    if current_liabilities is None
                    and (
                        symbol in self._get_no_recent_current_liabilities_symbols()
                        or symbol in self._get_never_tagged_current_liabilities_symbols()
                    )
                    else "missing_sec_data"
                )
                if "current_ratio" in failed_metrics
                else None
            )
            metrics["quick_ratio_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "quick_ratio" in implausible_ratio_metrics
                    else "reit_special_entity"
                    if unclassified_balance_sheet
                    # quick_ratio shares current_ratio's structural inputs; inventory's absence
                    # is a normal "not a goods business" fact, not a data gap, deliberately not
                    # gated.
                    else "no_recent_current_assets_reported"
                    if current_assets is None
                    and (
                        symbol in self._get_no_recent_current_assets_symbols()
                        or symbol in self._get_never_tagged_current_assets_symbols()
                    )
                    else "no_recent_current_liabilities_reported"
                    if current_liabilities is None
                    and (
                        symbol in self._get_no_recent_current_liabilities_symbols()
                        or symbol in self._get_never_tagged_current_liabilities_symbols()
                    )
                    else "missing_sec_data"
                )
                if "quick_ratio" in failed_metrics
                else None
            )
            metrics["interest_coverage_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "interest_coverage" in implausible_ratio_metrics
                    else "interest_expense_not_itemized"
                    if no_recent_interest_expense
                    else "reit_special_entity"
                    if no_operating_income_concept_ic
                    else "operating_income_not_itemized"
                    if symbol in self._get_no_recent_operating_income_symbols()
                    or symbol in self._get_never_tagged_operating_income_symbols()
                    else "missing_sec_data"
                )
                if "interest_coverage" in failed_metrics
                else None
            )
            metrics["debt_to_assets_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "debt_to_assets" in implausible_ratio_metrics
                    else "no_recent_total_assets_reported"
                    if (total_assets is None or total_assets <= 0)
                    and (
                        symbol in self._get_no_recent_total_assets_symbols()
                        or symbol in self._get_never_tagged_total_assets_symbols()
                    )
                    else "total_liabilities_not_reported"
                    if total_liabilities is None
                    and (
                        symbol in self._get_no_recent_total_liabilities_symbols()
                        or symbol in self._get_never_tagged_total_liabilities_symbols()
                    )
                    else "missing_sec_data"
                )
                if "debt_to_assets" in failed_metrics
                else None
            )
            # Phase 3 Expansion (Session 357+): New metrics - initialize their _unavailable_reason fields
            metrics["gross_margin_unavailable_reason"] = (
                (
                    "reit_special_entity"
                    if no_gross_profit_concept
                    else "implausible_ratio"
                    if "gross_margin" in implausible_ratio_metrics
                    else "no_revenue_reported"
                    if symbol in self._get_blank_check_symbols()
                    or symbol in self._get_no_recent_revenue_symbols()
                    or symbol in self._get_never_tagged_revenue_symbols()
                    # Label-only: gross_profit_revenue (this field's own denominator, read from
                    # the same balance-sheet-anchor-joined row as `revenue`) is None because
                    # that anchor fiscal year's own income-statement row lacks it, not because
                    # the symbol lacks real revenue anywhere.
                    else "revenue_absent_from_anchor_year"
                    if revenue is None and symbol in self._get_revenue_available_elsewhere_symbols()
                    else "missing_sec_data"
                )
                if "gross_margin" in failed_metrics
                else None
            )
            metrics["ebitda_margin_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "ebitda_margin" in implausible_ratio_metrics
                    # load_sec_valuations.py's own EBITDA computation (EBITDA = OperatingIncome
                    # + D&A) requires operating_income and stays None when it's absent - same
                    # REIT/tonnage-tax-exempt population no_operating_income_concept identifies,
                    # cascading into ebitda_ev is None here.
                    else "reit_special_entity"
                    if no_operating_income_concept
                    else "no_revenue_reported"
                    if symbol in self._get_no_recent_revenue_symbols()
                    or symbol in self._get_never_tagged_revenue_symbols()
                    or symbol in self._get_blank_check_symbols()
                    # Label-only, no value recomputed.
                    else "revenue_absent_from_anchor_year"
                    if revenue is None and symbol in self._get_revenue_available_elsewhere_symbols()
                    # ebitda_margin also depends on operating_income via EBITDA = OperatingIncome
                    # + D&A - same operating_income_not_itemized case as operating_margin/
                    # interest_coverage above.
                    else "operating_income_not_itemized"
                    if symbol in self._get_no_recent_operating_income_symbols()
                    or symbol in self._get_never_tagged_operating_income_symbols()
                    else "missing_sec_data"
                )
                if "ebitda_margin" in failed_metrics
                else None
            )
            metrics["roic_pct_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "roic_pct" in implausible_ratio_metrics
                    else "unprofitable_stock"
                    if roic_pct_unprofitable
                    else "negative_invested_capital"
                    if roic_pct_negative_invested_capital
                    # Commodity/crypto trusts (GLD, GLDM, GLTR, IAUM, AAAU, BTCO) structurally
                    # report no revenue by their trust/ETF nature - same "no operating business"
                    # fact blank-check SPACs represent, just not SIC-classified as one.
                    else "no_revenue_reported"
                    if symbol in self._get_blank_check_symbols()
                    or symbol in self._get_no_recent_revenue_symbols()
                    or symbol in self._get_never_tagged_revenue_symbols()
                    else "reit_special_entity"
                    if no_operating_income_concept_roic
                    # invested_capital (this field's own denominator) comes back None whenever
                    # debt_for_roic OR roic_stockholders_equity is None - the
                    # negative_invested_capital branch above only catches a computed non-None
                    # value <= 0, not a missing input.
                    else "total_debt_not_itemized"
                    if debt_for_roic is None
                    and (
                        symbol in self._get_no_recent_debt_components_symbols()
                        or symbol in self._get_never_tagged_debt_components_symbols()
                    )
                    else "stockholders_equity_not_reported"
                    if stockholders_equity is None
                    and (
                        symbol in self._get_no_recent_stockholders_equity_symbols()
                        or symbol in self._get_never_tagged_stockholders_equity_symbols()
                    )
                    else "operating_income_not_itemized"
                    if symbol in self._get_no_recent_operating_income_symbols()
                    or symbol in self._get_never_tagged_operating_income_symbols()
                    else "missing_sec_data"
                )
                if "roic_pct" in failed_metrics
                else None
            )
            metrics["roce_pct_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "roce_pct" in implausible_ratio_metrics
                    else "negative_capital_employed"
                    if roce_pct_negative_capital_employed
                    else "no_revenue_reported"
                    if symbol in self._get_blank_check_symbols()
                    or symbol in self._get_no_recent_revenue_symbols()
                    or symbol in self._get_never_tagged_revenue_symbols()
                    # roce_pct shares roic_operating_income (EBIT numerator) with roic_pct -
                    # same REIT structural gap.
                    else "reit_special_entity"
                    if no_operating_income_concept_roic
                    # capital_employed (this field's own denominator) comes back None whenever
                    # debt_for_roic OR roic_stockholders_equity is None, which
                    # negative_capital_employed's <=0 check doesn't catch.
                    else "total_debt_not_itemized"
                    if debt_for_roic is None
                    and (
                        symbol in self._get_no_recent_debt_components_symbols()
                        or symbol in self._get_never_tagged_debt_components_symbols()
                    )
                    else "stockholders_equity_not_reported"
                    if stockholders_equity is None
                    and (
                        symbol in self._get_no_recent_stockholders_equity_symbols()
                        or symbol in self._get_never_tagged_stockholders_equity_symbols()
                    )
                    else "operating_income_not_itemized"
                    if symbol in self._get_no_recent_operating_income_symbols()
                    or symbol in self._get_never_tagged_operating_income_symbols()
                    else "missing_sec_data"
                )
                if "roce_pct" in failed_metrics
                else None
            )
            metrics["fcf_to_net_income_unavailable_reason"] = (
                (
                    # See fcf_margin_unavailable_reason above for why this check comes first.
                    "registered_investment_company_no_xbrl"
                    if free_cash_flow is None and symbol in self._get_registered_investment_company_symbols()
                    # ADDED 2026-09-05: same sibling-wiring gap as fcf_margin above.
                    else "capex_never_tagged_in_recent_filings"
                    if free_cash_flow is None and symbol in self._get_no_recent_capex_symbols()
                    else "no_recent_free_cash_flow_reported"
                    if free_cash_flow is None
                    and (
                        symbol in self._get_no_recent_free_cash_flow_symbols()
                        or symbol in self._get_never_tagged_free_cash_flow_symbols()
                    )
                    # Label-only, no value recomputed.
                    else "free_cash_flow_absent_from_anchor_year"
                    if free_cash_flow is None and symbol in self._get_free_cash_flow_available_elsewhere_symbols()
                    # fcf_to_net_income = free_cash_flow / net_income - check the net_income
                    # denominator too, not just the FCF numerator.
                    else "net_income_not_reported"
                    if net_income is None
                    and (
                        symbol in self._get_no_recent_net_income_symbols()
                        or symbol in self._get_never_tagged_net_income_symbols()
                    )
                    else "net_income_absent_from_anchor_year"
                    if net_income is None and symbol in self._get_net_income_available_elsewhere_symbols()
                    else "missing_sec_data"
                )
                if "fcf_to_net_income" in failed_metrics
                else None
            )
            metrics["ocf_to_net_income_unavailable_reason"] = (
                (
                    # Same RIC gap as accruals_ratio_unavailable_reason above. Live-confirmed
                    # 14 universe symbols (IGI/TY/ASA/GAM/GGN/GGT/GLU/PIM/PMM/GNT/HQH/PPT/NXP/
                    # SOR).
                    "registered_investment_company_no_xbrl"
                    if operating_cash_flow is None and symbol in self._get_registered_investment_company_symbols()
                    else "no_recent_operating_cash_flow_reported"
                    if operating_cash_flow is None and symbol in self._get_no_recent_operating_cash_flow_symbols()
                    # Label-only, no value recomputed.
                    else "operating_cash_flow_absent_from_anchor_year"
                    if operating_cash_flow is None
                    and symbol in self._get_operating_cash_flow_available_elsewhere_symbols()
                    # ocf_to_net_income = operating_cash_flow / net_income - check the net_income
                    # denominator too, not just the OCF numerator.
                    else "net_income_not_reported"
                    if net_income is None
                    and (
                        symbol in self._get_no_recent_net_income_symbols()
                        or symbol in self._get_never_tagged_net_income_symbols()
                    )
                    else "net_income_absent_from_anchor_year"
                    if net_income is None and symbol in self._get_net_income_available_elsewhere_symbols()
                    else "missing_sec_data"
                )
                if "ocf_to_net_income" in failed_metrics
                else None
            )
            metrics["payout_ratio_unavailable_reason"] = payout_ratio_reason
            metrics["free_cash_flow_unavailable_reason"] = (
                (
                    # See fcf_margin_unavailable_reason above for why this check comes first.
                    "registered_investment_company_no_xbrl"
                    if symbol in self._get_registered_investment_company_symbols()
                    # ADDED 2026-09-05: same sibling-wiring gap as fcf_margin above.
                    else "capex_never_tagged_in_recent_filings"
                    if symbol in self._get_no_recent_capex_symbols()
                    # Only covers the unambiguous "genuinely no FCF in the 3 most recent fiscal
                    # years" case - the rest have FCF in an off-anchor year (see
                    # _get_free_cash_flow_available_elsewhere_symbols() below).
                    else "no_recent_free_cash_flow_reported"
                    if symbol in self._get_no_recent_free_cash_flow_symbols()
                    or symbol in self._get_never_tagged_free_cash_flow_symbols()
                    # Label-only, no value recomputed.
                    else "free_cash_flow_absent_from_anchor_year"
                    if symbol in self._get_free_cash_flow_available_elsewhere_symbols()
                    else "missing_sec_data"
                )
                if "free_cash_flow" in failed_metrics
                else None
            )
            metrics["operating_cash_flow_unavailable_reason"] = (
                (
                    # Only covers the unambiguous "genuinely no OCF in the 3 most recent fiscal
                    # years" case - the rest have OCF in an off-anchor year (see
                    # _get_operating_cash_flow_available_elsewhere_symbols() below).
                    "no_recent_operating_cash_flow_reported"
                    if symbol in self._get_no_recent_operating_cash_flow_symbols()
                    # Label-only, no value recomputed.
                    else "operating_cash_flow_absent_from_anchor_year"
                    if symbol in self._get_operating_cash_flow_available_elsewhere_symbols()
                    else "missing_sec_data"
                )
                if "operating_cash_flow" in failed_metrics
                else None
            )
            metrics["total_debt_unavailable_reason"] = (
                (
                    "total_debt_not_itemized"
                    if symbol in self._get_no_recent_debt_components_symbols()
                    or symbol in self._get_never_tagged_debt_components_symbols()
                    # total_debt_ev comes from the same ev_metrics tuple as total_cash_ev/
                    # ebitda_ev below - reuse sec_valuations' own reason. Checked after the
                    # debt-components gate above (largest, best-tested population).
                    else "no_sec_valuations_row"
                    if ev_metrics is None
                    else sec_valuations_reason
                    if sec_valuations_reason
                    # ADDED 2026-09-05 (goal: "SEC/XBRL missing data to zero" follow-up):
                    # etf_symbols tickers with ZERO annual_balance_sheet rows ever (SPY/IGV/
                    # BKDV live-confirmed) fall through every check above - they have no
                    # sec_valuations row's own reason to inherit AND no real balance-sheet
                    # history to even attempt the debt-components gate against. Unlike
                    # _get_etf_trust_no_stockholders_equity_symbols() (which requires real
                    # balance-sheet history to distinguish "weird trust filing shape" from
                    # "too new to have filed yet"), an ETF's total_debt/total_cash absence
                    # doesn't depend on listing age at all - a UIT/index-tracking ETF never
                    # files an operating-company-style GAAP balance sheet regardless of how
                    # long it's been trading (SPY: listed 1993, zero balance-sheet rows,
                    # obviously not "too new"). etf_symbols membership alone is sufficient.
                    else "etf_trust_no_gaap_financials"
                    if symbol in self._get_etf_symbols()
                    else "missing_sec_data"
                )
                if "total_debt" in failed_metrics
                else None
            )
            # total_cash_ev is None whenever sec_valuations has no row at all for this symbol,
            # or has a row but load_sec_valuations.py already recorded why total_cash came back
            # NULL there - reuse that reason. A genuinely never-tagged cash concept doesn't fail
            # the rest of the valuation row, so sec_valuations_reason can stay empty even then -
            # check cash_and_equivalents against its own no-data gate too.
            no_recent_cash_concept = (
                symbol in self._get_no_recent_cash_symbols() or symbol in self._get_never_tagged_cash_symbols()
            )
            metrics["total_cash_unavailable_reason"] = (
                (
                    "no_sec_valuations_row"
                    if ev_metrics is None
                    else sec_valuations_reason
                    if sec_valuations_reason
                    else "no_recent_cash_reported"
                    if no_recent_cash_concept
                    # Same etf_symbols fallback as total_debt_unavailable_reason above - same
                    # root fact (no GAAP balance sheet at all), same 3 live-confirmed symbols
                    # (SPY/IGV/BKDV).
                    else "etf_trust_no_gaap_financials"
                    if symbol in self._get_etf_symbols()
                    else "missing_sec_data"
                )
                if "total_cash" in failed_metrics
                else None
            )
            metrics["cash_per_share_unavailable_reason"] = (
                (
                    "shares_outstanding_unavailable"
                    if cash_per_share_shares_missing
                    else "no_sec_valuations_row"
                    if ev_metrics is None
                    else sec_valuations_reason
                    if sec_valuations_reason
                    else "no_recent_cash_reported"
                    if no_recent_cash_concept
                    else "missing_sec_data"
                )
                if "cash_per_share" in failed_metrics
                else None
            )
            metrics["ebitda_unavailable_reason"] = (
                (
                    # ebitda is the same load_sec_valuations.py-derived absolute-dollar value
                    # ebitda_margin's numerator uses - fails structurally for the same
                    # REIT/tonnage-tax-exempt population.
                    "reit_special_entity"
                    if no_operating_income_concept
                    # ebitda = OperatingIncome + D&A, so a real filer that never itemizes a
                    # distinct operating income subtotal fails here too.
                    else "operating_income_not_itemized"
                    if symbol in self._get_no_recent_operating_income_symbols()
                    or symbol in self._get_never_tagged_operating_income_symbols()
                    # ebitda_ev comes from the same ev_metrics tuple as total_cash_ev - reuse the
                    # sec_valuations `reason` column instead of a generic label.
                    else "no_sec_valuations_row"
                    if ev_metrics is None
                    else sec_valuations_reason
                    if sec_valuations_reason
                    else "missing_sec_data"
                )
                if "ebitda" in failed_metrics
                else None
            )
            metrics["earnings_growth_yoy_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "earnings_growth_yoy" in implausible_ratio_metrics
                    else "insufficient_prior_year_data"
                )
                if "earnings_growth_yoy" in failed_metrics
                else None
            )
            metrics["revenue_growth_yoy_unavailable_reason"] = (
                (
                    "implausible_ratio"
                    if "revenue_growth_yoy" in implausible_ratio_metrics
                    else "insufficient_prior_year_data"
                )
                if "revenue_growth_yoy" in failed_metrics
                else None
            )

            # Quarterly metrics unavailable reasons (Session 78+). Only fill the generic
            # fallback when _compute_quarterly_metrics() (merged into `metrics` above) didn't
            # already set a more specific reason (e.g. "insufficient_eps_data",
            # "insufficient_revenue_data", "insufficient_eps_growth_datapoints",
            # "insufficient_quarterly_history") - this block previously overwrote every one of
            # those with the generic "insufficient_quarterly_data" unconditionally, silently
            # discarding the more specific diagnosis the moment it was computed.
            if metrics.get("consecutive_positive_quarters") is None and not metrics.get(
                "consecutive_positive_quarters_unavailable_reason"
            ):
                metrics["consecutive_positive_quarters_unavailable_reason"] = "insufficient_quarterly_data"
            if metrics.get("earnings_growth_4q_avg") is None and not metrics.get(
                "earnings_growth_4q_avg_unavailable_reason"
            ):
                metrics["earnings_growth_4q_avg_unavailable_reason"] = "insufficient_quarterly_data"
            if metrics.get("eps_growth_stability") is None and not metrics.get(
                "eps_growth_stability_unavailable_reason"
            ):
                metrics["eps_growth_stability_unavailable_reason"] = "insufficient_quarterly_data"
            if metrics.get("quarterly_growth_momentum") is None and not metrics.get(
                "quarterly_growth_momentum_unavailable_reason"
            ):
                metrics["quarterly_growth_momentum_unavailable_reason"] = "insufficient_quarterly_data"

            # Analyst metrics - not yet implemented. Guard all fields to avoid clobbering prior reasons.
            # _compute_quarterly_metrics() sets "insufficient_quarterly_history" for quarterly fields;
            # we must not override with "no_analyst_estimates" if that was already set.
            if metrics.get("earnings_surprise_avg") is None and not metrics.get(
                "earnings_surprise_avg_unavailable_reason"
            ):
                metrics["earnings_surprise_avg_unavailable_reason"] = "no_analyst_estimates"
            if metrics.get("earnings_beat_rate") is None and not metrics.get("earnings_beat_rate_unavailable_reason"):
                metrics["earnings_beat_rate_unavailable_reason"] = "no_analyst_estimates"
            if metrics.get("estimate_revision_direction") is None and not metrics.get(
                "estimate_revision_direction_unavailable_reason"
            ):
                metrics["estimate_revision_direction_unavailable_reason"] = "no_analyst_estimates"
            if metrics.get("revision_activity_30d") is None and not metrics.get(
                "revision_activity_30d_unavailable_reason"
            ):
                metrics["revision_activity_30d_unavailable_reason"] = "no_analyst_estimates"
            if metrics.get("estimate_momentum_60d") is None and not metrics.get(
                "estimate_momentum_60d_unavailable_reason"
            ):
                metrics["estimate_momentum_60d_unavailable_reason"] = "no_analyst_estimates"
            if metrics.get("estimate_momentum_90d") is None and not metrics.get(
                "estimate_momentum_90d_unavailable_reason"
            ):
                metrics["estimate_momentum_90d_unavailable_reason"] = "no_analyst_estimates"
            if metrics.get("revision_trend_score") is None and not metrics.get(
                "revision_trend_score_unavailable_reason"
            ):
                metrics["revision_trend_score_unavailable_reason"] = "no_analyst_estimates"

            # Score can be partial; only mark unavailable if ALL metrics failed OR the
            # available weight didn't clear the completeness floor above (thin-sample
            # extrapolation, not honest partial data - see quality_components' own comment).
            if weighted_score is None and available_quality_weight < min_quality_weight_pct:
                metrics["quality_score_unavailable_reason"] = "insufficient_completeness"
            else:
                metrics["quality_score_unavailable_reason"] = None

            if failed_metrics:
                # Log which metrics are incomplete (for debugging), but don't mark data_unavailable
                logger.debug(
                    f"[VALUE_QUALITY_GROWTH] {symbol}: Quality metrics computed from available data. "
                    f"Unavailable: {', '.join(sorted(set(failed_metrics)))} (insufficient SEC data)"
                )

            # Recategorize debt/cash/interest/FCF-derived fields these grantor trusts
            # structurally never report to "reit_special_entity" (same label as their
            # current_ratio/quick_ratio/gross_margin siblings) - only when the field is None and
            # already carries one of the reasons this structural gap produces, so real data or
            # an unrelated reason is left untouched.
            if symbol in self._ROYALTY_TRUST_NO_BALANCE_SHEET_SYMBOLS:
                _trust_recategorize_fields = (
                    "total_debt",
                    "debt_to_equity",
                    "debt_to_assets",
                    "roic_pct",
                    "roce_pct",
                    "interest_coverage",
                    "total_cash",
                    "cash_per_share",
                    "free_cash_flow",
                    "operating_cash_flow",
                    "fcf_to_net_income",
                    "ocf_to_net_income",
                    "accruals_ratio",
                    "fcf_margin",
                    "ebitda",
                    "ebitda_margin",
                    "operating_margin",
                )
                _trust_source_reasons = {
                    "missing_sec_data",
                    "total_debt_not_itemized",
                    "no_recent_cash_reported",
                    "interest_expense_not_itemized",
                    "stockholders_equity_not_reported",
                    "operating_income_not_itemized",
                    "total_liabilities_not_reported",
                }
                for _field in _trust_recategorize_fields:
                    _reason_key = f"{_field}_unavailable_reason"
                    if metrics.get(_field) is None and metrics.get(_reason_key) in _trust_source_reasons:
                        metrics[_reason_key] = "reit_special_entity"

            # Same recategorization pattern as the royalty-trust block above, for physical
            # commodity/currency/crypto trusts (see _get_etf_trust_no_stockholders_equity_
            # symbols' own docstring - GLDM/USO/UNG/FXA/GBTC-class tickers). ADDED 2026-09-05
            # (goal: "SEC/XBRL missing data to zero" sweep, follow-up to the same day's
            # etf_trust_no_gaap_financials fix): that fix only wired the ETF-trust gate into
            # this function's single "ALL metrics null" early return - live-confirmed via a
            # scoped rerun of the 43 real etf_symbols matching this gate that most (38/43)
            # never hit that early return at all (some other field, e.g. current_ratio,
            # legitimately computes for a Statement-of-Assets-and-Liabilities filer even
            # without stockholders_equity) and fell through to this function's normal per-field
            # `stockholders_equity_not_reported` ternary branches instead (roe/roa/debt_to_
            # equity/roic_pct/roce_pct/sustainable_growth_rate all check that reason before ever
            # reaching the ETF-specific gate) - the exact same "fix wired into only one of
            # several call sites" bug class as the royalty-trust block's own reason set.
            # roa is excluded: it never reaches stockholders_equity_not_reported (gated on
            # total_assets instead, which these trusts DO report).
            if symbol in self._get_etf_trust_no_stockholders_equity_symbols():
                _etf_trust_recategorize_fields = (
                    "operating_profitability",
                    "roe",
                    "debt_to_equity",
                    "roic_pct",
                    "roce_pct",
                    "sustainable_growth_rate",
                )
                for _field in _etf_trust_recategorize_fields:
                    _reason_key = f"{_field}_unavailable_reason"
                    if metrics.get(_field) is None and metrics.get(_reason_key) == "stockholders_equity_not_reported":
                        metrics[_reason_key] = "etf_trust_no_gaap_financials"

            # Same recategorization pattern as the ETF-trust block above, for registered
            # investment companies (closed-end funds/investment trusts - same root fact
            # already established for fcf_margin/fcf_yield/accruals_ratio/ocf_to_net_income
            # elsewhere in this file: a "Statement of Changes in Net Assets" has no
            # stockholders_equity/total_debt concepts to tag at all). ADDED 2026-09-05 (goal:
            # "SEC/XBRL missing data to zero" follow-up): roic_pct/debt_to_equity's own ternary
            # chains never reach a specific reason for a RIC either - live-confirmed GGN (GAMCO
            # Global Gold, Natural Resources & Income Trust): roe computes a real value (its
            # denominator, stockholders_equity, IS available), but roic_pct/debt_to_equity
            # (which also need debt_for_roic, structurally absent) fell all the way through to
            # generic "missing_sec_data" - broader than the ETF-trust block's single
            # "stockholders_equity_not_reported" check, reusing the royalty-trust block's wider
            # source-reason set (which already includes "missing_sec_data", mirroring the
            # royalty-trust block's own _trust_source_reasons above - NOT reused directly since
            # that name is only defined inside the royalty-trust `if`, a scope this RIC check
            # doesn't share) since a RIC can hit any of several different missing-denominator
            # reasons depending on which concept it happens to lack first.
            if symbol in self._get_registered_investment_company_symbols():
                # Not reusing _etf_trust_recategorize_fields above - that name is only defined
                # inside the ETF-trust `if`, a scope this RIC check doesn't share (a RIC that
                # isn't ALSO an etf_symbols-registered ticker, GGN's case, would otherwise hit
                # an UnboundLocalError here).
                _ric_recategorize_fields = (
                    "operating_profitability",
                    "roe",
                    "debt_to_equity",
                    "roic_pct",
                    "roce_pct",
                    "sustainable_growth_rate",
                )
                _ric_source_reasons = {
                    "missing_sec_data",
                    "total_debt_not_itemized",
                    "no_recent_cash_reported",
                    "interest_expense_not_itemized",
                    "stockholders_equity_not_reported",
                    "operating_income_not_itemized",
                    "total_liabilities_not_reported",
                }
                for _field in _ric_recategorize_fields:
                    _reason_key = f"{_field}_unavailable_reason"
                    if metrics.get(_field) is None and metrics.get(_reason_key) in _ric_source_reasons:
                        metrics[_reason_key] = "registered_investment_company_no_xbrl"

            if stale_fallback_metrics:
                # One or more fields above came from a prior fiscal year (up to 6 years
                # back) via the cross-year "implausible anchor" rescue, not this symbol's
                # current reporting period. Flag it on data_source (VARCHAR(50) - keep this
                # short) so a downstream scoring/backtest consumer can at least tell this row
                # isn't purely fresh current-period data, since there's no per-field
                # provenance column to name which ones.
                metrics["data_source"] = "sec_audited_stale_fallback"
                logger.info(
                    f"[VALUE_QUALITY_GROWTH] {symbol}: data_source marked stale_fallback - "
                    f"fields from a prior fiscal year: {stale_fallback_metrics}"
                )

            return metrics

        except Exception as e:
            logger.warning(f"[VALUE_QUALITY_GROWTH] {symbol}: Quality metrics compute failed: {e}")
            # Propagate the real exception (not the generic "missing_sec_data" default) so a
            # genuine loader bug lands in scores.py's _categorize_reason() "Other (errors /
            # excluded)" bucket instead of silently inflating "Missing SEC/XBRL data" - same
            # fix already applied to this file's outer fetch_incremental() except block.
            exc_reason = f"fetch_exception: {type(e).__name__}: {str(e)[:150]}"
            return self._unavailable_marker("quality_metrics", symbol, reason=exc_reason)
