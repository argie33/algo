"""QualityInputsMixin._derive_quality_row_inputs, extracted from vqg_quality.py (2026-09-09,
file-size ratchet: that file is past the hard ceiling - see .file-size-baseline.json /
.pre-commit-scripts/check_file_size_ratchet.py). Pure extraction, no behavior change: this was
the first ~250 lines of _compute_quality_metrics's try block - deriving every input value out
of the joined `quality_row` (plus a couple of same-fiscal-year DB rescues) before any ratio is
computed. Returns a plain dict rather than a dataclass so the caller's unpacking stays a
literal `x = result["x"]` per field - the safest mechanical transcription for a first pass.
"""

from typing import TYPE_CHECKING, Any

from utils.type_conversion import safe_float


def _owner() -> Any:
    from loaders import load_value_quality_growth_metrics as _owner_mod

    return _owner_mod


class QualityInputsMixin:
    """See module docstring. Mixed into ValueQualityGrowthMetricsLoader alongside
    QualityMetricsMixin - every `self.` call here resolves normally through the instance.
    """

    if TYPE_CHECKING:

        def _nan_to_none(self, value: float | None) -> float | None: ...

        def _fetch_annual_fallback_row(
            self, table: str, columns: str, extra_where: str, symbol: str
        ) -> tuple[Any, ...] | None: ...

        def _fetch_balance_sheet_anchor_fallback(self, symbol: str, column: str) -> float | None: ...

        def _fetch_ttm_net_income_from_quarterly(self, symbol: str) -> float | None: ...

        def _get_last_known_zero_dividends_symbols(self) -> frozenset[str]: ...

    def _derive_quality_row_inputs(self, symbol: str, quality_row: Any) -> dict[str, Any]:
        """Derive every base input value from the joined `quality_row` (plus same-fiscal-year
        DB rescues for dividends_paid) - verbatim extraction of _compute_quality_metrics's own
        former try-block opening.
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
        # Recent IPOs (and pre-IPO S-1 stub annual rows) can have a real annual_balance_sheet
        # anchor row but no usable annual_income_statement.net_income - no 10-K filed yet,
        # only 10-Qs. Recover a TTM figure from 4 real consecutive quarters rather than
        # falling through to "net_income_not_reported" for a symbol that genuinely has
        # current SEC-reported earnings data, just not in annual form yet.
        net_income_from_ttm_quarterly = False
        net_income_from_annual_fallback = False
        if net_income is None:
            net_income = self._fetch_ttm_net_income_from_quarterly(symbol)
            if net_income is not None:
                net_income_from_ttm_quarterly = True
        # ADDED 2026-09-09 (goal session: SEC/XBRL missing-data count under 500, missing_sec_data
        # investigation): symbols with a real, recent-but-not-current-year annual_income_statement
        # net_income AND fewer than 4 real quarterly rows (so the TTM fallback above also fails)
        # were falling all the way through to "missing_sec_data" - live-confirmed MDV: FY2025
        # net_income=$1,068,000 real and populated, FY2026 anchor row is a data_unavailable
        # placeholder, and quarterly_income_statement only has one real quarter (Q1 2025), too few
        # for the TTM sum. Same "prior real annual row" fallback pattern
        # _fetch_balance_sheet_anchor_fallback already uses for stockholders_equity/
        # total_liabilities/total_assets above - reuses the same underlying
        # _fetch_annual_fallback_row helper, just against annual_income_statement.net_income
        # instead of annual_balance_sheet.
        if net_income is None:
            fallback_row = self._fetch_annual_fallback_row(
                "annual_income_statement", "net_income", "AND net_income IS NOT NULL", symbol
            )
            if fallback_row:
                net_income = self._nan_to_none(
                    safe_float(fallback_row[0], f"{symbol}.net_income_fallback_year", allow_none=True)
                )
                if net_income is not None:
                    net_income_from_annual_fallback = True
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
        return {
            "stockholders_equity": stockholders_equity,
            "total_liabilities": total_liabilities,
            "total_assets": total_assets,
            "net_income": net_income,
            "net_income_from_ttm_quarterly": net_income_from_ttm_quarterly,
            "net_income_from_annual_fallback": net_income_from_annual_fallback,
            "revenue": revenue,
            "operating_income": operating_income,
            "current_assets": current_assets,
            "current_liabilities": current_liabilities,
            "inventory": inventory,
            "interest_expense": interest_expense,
            "pretax_income": pretax_income,
            "interest_coverage_operating_income": interest_coverage_operating_income,
            "interest_coverage_pretax_income": interest_coverage_pretax_income,
            "shares_outstanding": shares_outstanding,
            "cost_of_revenue": cost_of_revenue,
            "operating_cash_flow": operating_cash_flow,
            "free_cash_flow": free_cash_flow,
            "dividends_paid": dividends_paid,
            "earnings_per_share": earnings_per_share,
            "prior_year_eps": prior_year_eps,
            "prior_year_revenue": prior_year_revenue,
            "gross_profit_direct": gross_profit_direct,
            "long_term_debt_bs": long_term_debt_bs,
            "cash_and_equivalents_bs": cash_and_equivalents_bs,
            "income_tax_expense": income_tax_expense,
            "prior_year_net_income": prior_year_net_income,
            "prior_year_operating_income": prior_year_operating_income,
            "prior_year_operating_cash_flow": prior_year_operating_cash_flow,
            "prior_year_free_cash_flow": prior_year_free_cash_flow,
            "prior_year_cost_of_revenue": prior_year_cost_of_revenue,
            "prior_year_total_assets": prior_year_total_assets,
            "prior_year_stockholders_equity": prior_year_stockholders_equity,
            "prior_year_pretax_income": prior_year_pretax_income,
            "prior_year_interest_expense": prior_year_interest_expense,
            "prior_year_gross_profit": prior_year_gross_profit,
            "prior_year_dividends_paid": prior_year_dividends_paid,
            "dividends_paid_with_prior_year_fallback": dividends_paid_with_prior_year_fallback,
            "prior_year_operating_income_for_trend": prior_year_operating_income_for_trend,
        }
