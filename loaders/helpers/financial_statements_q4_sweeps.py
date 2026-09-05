"""Q4-derivation sweep methods for ConsolidatedFinancialStatementsLoader, extracted from
load_financial_statements.py (2026-09-05, file-size ratchet: it's the last remaining Tier-1
bloater flagged for decomposition). Methods are verbatim, no logic changed - mixed into
ConsolidatedFinancialStatementsLoader, which still defines the `table_name` instance
attribute these methods read via `self`.

`DatabaseContext` is accessed via the load_financial_statements module object at call time
(not imported by name here) because several existing tests patch
`loaders.load_financial_statements.DatabaseContext` expecting that to affect these sweeps -
a plain module-level import here would silently stop seeing those patches, AND
`loaders.load_financial_statements` itself imports this module at load time, so a
module-level `import loaders.load_financial_statements` here would deadlock as a circular
import (confirmed live 2026-09-05: this exact ImportError broke financial_statements'
entire loader run). `_database_context()` below defers the import to call time instead.
"""

import logging

logger = logging.getLogger(__name__)


def _database_context() -> type:
    import loaders.load_financial_statements as _lfs

    return _lfs.DatabaseContext


class Q4DerivationSweepMixin:
    """Post-run Q4-derivation sweep methods for ConsolidatedFinancialStatementsLoader.
    Not usable standalone - relies on the `table_name` instance attribute defined there.
    """

    table_name: str

    def _sweep_derive_missing_q4_cash_flow(self) -> None:
        """Derive operating_cash_flow for a missing/incomplete Q4 quarterly_cash_flow row as
        FY_annual - (Q1+Q2+Q3), independent of what this run happened to fetch.

        FOUND 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep, same root
        cause and derivation as _sweep_derive_missing_q4() for the income statement):
        operating_cash_flow is a flow quantity, additive across a fiscal year's four
        quarters, so FY - (Q1+Q2+Q3) is the same accounting identity a real Q4 cash-flow
        statement would satisfy if one were ever filed - and none ever is, for the same
        "Q4 is only ever disclosed inside the annual 10-K" reason as the income statement.
        Live-confirmed 929 rows recoverable this way. Scoped to operating_cash_flow only -
        free_cash_flow/capex are deliberately NOT derived here: capex is frequently NULL for
        one or more of Q1-Q3 even when OCF is present (see this file's own capex-fallback
        history), so a Q4 capex subtraction would silently produce a wrong result far more
        often than the OCF-only case does; a future pass could add it with its own explicit
        null-guard on all three quarters' capex.
        """
        with _database_context()("write") as cur:
            cur.execute(
                """
                UPDATE quarterly_cash_flow q4
                   SET operating_cash_flow = derived.operating_cash_flow,
                       data_unavailable = FALSE,
                       reason = NULL,
                       data_source = 'derived_fy_minus_9m'
                  FROM (
                        SELECT q4x.id,
                               a.operating_cash_flow - (q1.operating_cash_flow + q2.operating_cash_flow + q3.operating_cash_flow) AS operating_cash_flow
                          FROM quarterly_cash_flow q4x
                          JOIN annual_cash_flow a
                            ON a.symbol = q4x.symbol AND a.fiscal_year = q4x.fiscal_year
                          JOIN quarterly_cash_flow q1
                            ON q1.symbol = q4x.symbol AND q1.fiscal_year = q4x.fiscal_year AND q1.fiscal_quarter = 1
                          JOIN quarterly_cash_flow q2
                            ON q2.symbol = q4x.symbol AND q2.fiscal_year = q4x.fiscal_year AND q2.fiscal_quarter = 2
                          JOIN quarterly_cash_flow q3
                            ON q3.symbol = q4x.symbol AND q3.fiscal_year = q4x.fiscal_year AND q3.fiscal_quarter = 3
                         WHERE q4x.fiscal_quarter = 4
                           AND (q4x.operating_cash_flow IS NULL OR q4x.data_unavailable = TRUE)
                           AND a.operating_cash_flow IS NOT NULL
                           AND q1.operating_cash_flow IS NOT NULL
                           AND q2.operating_cash_flow IS NOT NULL
                           AND q3.operating_cash_flow IS NOT NULL
                       ) AS derived
                 WHERE q4.id = derived.id
                """
            )
            if cur.rowcount:
                logger.warning(
                    f"[quarterly_cash_flow] post_run(): derived {cur.rowcount} Q4 "
                    "operating_cash_flow row(s) as FY_annual - 9mo_YTD (Q4 is never "
                    "separately filed by any US GAAP domestic filer)."
                )
        self._sweep_derive_missing_q4_cash_flow_remaining_fields()

    def _sweep_derive_missing_q4_cash_flow_remaining_fields(self) -> None:
        """Derive financing_cash_flow/investing_cash_flow/dividends_paid/
        stock_based_compensation/common_stock_repurchased for a missing Q4
        quarterly_cash_flow row as FY_annual - (Q1+Q2+Q3), same identity and independent-
        per-field gating as _sweep_derive_missing_q4_interest_expense() (income statement).

        Live-confirmed recoverable: 818 financing_cash_flow / 796 investing_cash_flow / 90
        dividends_paid / 623 stock_based_compensation / 411 common_stock_repurchased rows -
        smaller than operating_cash_flow's own 929 (fewer symbols have all 4 quarters'
        components tagged for these less-universally-reported lines), but the identical safe
        accounting identity. No non-negative floor on any of them: financing_cash_flow and
        investing_cash_flow are net flows that legitimately go either sign every quarter for
        ordinary companies, and this file has no independently-verified sign convention for
        the other three to safely floor against - same "don't guess a bound you can't verify"
        discipline as pretax_income/income_tax_expense above.

        ADDED 2026-09-04 (goal: "missing SEC/XBRL data under 6k" sweep continuation): capex
        is now included in this same per-field FY-minus-9mo identity, closing the gap
        `_sweep_derive_missing_q4_cash_flow`'s docstring flagged as deliberately deferred
        ("a future pass could add it with its own explicit null-guard on all three quarters'
        capex") - this loop already requires all three quarters non-null per field before
        deriving, same guard that comment asked for. free_cash_flow is then derived
        separately below from the (now-populated) Q4 operating_cash_flow/capex, same
        `ocf - capex` formula _sweep_missing_free_cash_flow() already uses for annual_cash_flow.
        """
        fields = (
            "financing_cash_flow",
            "investing_cash_flow",
            "dividends_paid",
            "stock_based_compensation",
            "common_stock_repurchased",
            "capex",
        )
        with _database_context()("write") as cur:
            for field in fields:
                cur.execute(
                    f"""
                    UPDATE quarterly_cash_flow q4
                       SET {field} = derived.{field},
                           data_source = 'derived_fy_minus_9m'
                      FROM (
                            SELECT q4x.id,
                                   a.{field} - (q1.{field} + q2.{field} + q3.{field}) AS {field}
                              FROM quarterly_cash_flow q4x
                              JOIN annual_cash_flow a
                                ON a.symbol = q4x.symbol AND a.fiscal_year = q4x.fiscal_year
                              JOIN quarterly_cash_flow q1
                                ON q1.symbol = q4x.symbol AND q1.fiscal_year = q4x.fiscal_year AND q1.fiscal_quarter = 1
                              JOIN quarterly_cash_flow q2
                                ON q2.symbol = q4x.symbol AND q2.fiscal_year = q4x.fiscal_year AND q2.fiscal_quarter = 2
                              JOIN quarterly_cash_flow q3
                                ON q3.symbol = q4x.symbol AND q3.fiscal_year = q4x.fiscal_year AND q3.fiscal_quarter = 3
                             WHERE q4x.fiscal_quarter = 4
                               AND q4x.{field} IS NULL
                               AND a.{field} IS NOT NULL
                               AND q1.{field} IS NOT NULL
                               AND q2.{field} IS NOT NULL
                               AND q3.{field} IS NOT NULL
                           ) AS derived
                     WHERE q4.id = derived.id
                    """
                )
                if cur.rowcount:
                    logger.warning(
                        f"[quarterly_cash_flow] post_run(): derived {cur.rowcount} Q4 "
                        f"{field} row(s) as FY_annual - 9mo_YTD."
                    )
            cur.execute(
                """
                UPDATE quarterly_cash_flow
                   SET free_cash_flow = operating_cash_flow - capex,
                       data_source = 'derived_fy_minus_9m'
                 WHERE fiscal_quarter = 4
                   AND free_cash_flow IS NULL
                   AND operating_cash_flow IS NOT NULL
                   AND capex IS NOT NULL
                """
            )
            if cur.rowcount:
                logger.warning(
                    f"[quarterly_cash_flow] post_run(): derived {cur.rowcount} Q4 "
                    "free_cash_flow row(s) as operating_cash_flow - capex."
                )

    def _sweep_copy_missing_q4_balance_sheet(self) -> None:
        """Fill a missing/incomplete Q4 quarterly_balance_sheet row by copying the matching
        annual_balance_sheet row for the same fiscal year, independent of what this run
        happened to fetch.

        FOUND 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep, same root
        cause as _sweep_derive_missing_q4() above): US GAAP filers never file a discrete Q4
        10-Q, so quarterly_balance_sheet's Q4 row has no directly-tagged XBRL fact to extract.
        Unlike the income statement, the balance sheet is a point-in-time snapshot, not a flow
        quantity - a fiscal year's Q4 balance sheet IS, by definition, the exact same
        year-end snapshot the annual 10-K itself reports (verified live: AAL's real Q4 2025
        total_assets already on file, $61.774B, is byte-identical to its annual FY2025
        total_assets) - so recovering it is a direct copy, not an arithmetic derivation, with
        no scale-mismatch or corroboration risk at all. Live-confirmed 597 rows recoverable
        this way (574 symbols / 815 total gap rows before this fix).
        """
        with _database_context()("write") as cur:
            cur.execute(
                """
                UPDATE quarterly_balance_sheet q4
                   SET total_assets = a.total_assets,
                       total_liabilities = a.total_liabilities,
                       stockholders_equity = a.stockholders_equity,
                       current_assets = a.current_assets,
                       current_liabilities = a.current_liabilities,
                       inventory = a.inventory,
                       cash_and_equivalents = a.cash_and_equivalents,
                       accounts_receivable = a.accounts_receivable,
                       ppe_net = a.ppe_net,
                       goodwill = a.goodwill,
                       long_term_debt = a.long_term_debt,
                       short_term_debt = a.short_term_debt,
                       operating_lease_liability = a.operating_lease_liability,
                       finance_lease_liability = a.finance_lease_liability,
                       data_unavailable = FALSE,
                       reason = NULL,
                       data_source = 'derived_annual_q4'
                  FROM annual_balance_sheet a
                 WHERE a.symbol = q4.symbol AND a.fiscal_year = q4.fiscal_year
                   AND q4.fiscal_quarter = 4
                   AND (q4.total_assets IS NULL OR q4.data_unavailable = TRUE)
                   AND a.total_assets IS NOT NULL
                """
            )
            if cur.rowcount:
                logger.warning(
                    f"[quarterly_balance_sheet] post_run(): copied {cur.rowcount} Q4 row(s) "
                    "from the matching annual_balance_sheet fiscal year (Q4 is never "
                    "separately filed - the year-end snapshot IS the annual balance sheet)."
                )

    def _sweep_derive_missing_q4(self) -> None:
        """Derive revenue/net_income for a missing/incomplete Q4 quarterly row as
        FY_annual - (Q1+Q2+Q3), independent of what this run happened to fetch.

        FOUND 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): US GAAP
        filers never file a discrete "three months ended" Q4 10-Q - Q4 results are only ever
        disclosed as part of the full-year 10-K, so quarterly_income_statement's Q4 row has no
        directly-tagged XBRL fact to extract, ever, for any domestic filer, regardless of how
        many times a fetch re-runs. Live-confirmed: 3,816 symbols / 36,812 rows currently sit
        at data_unavailable/'incomplete_sec_filing_income' purely because of this - by far the
        largest single class found this session, dwarfing every other individual bug fixed
        today combined.

        Revenue and net_income are simple accounting flow quantities - by definition additive
        across a fiscal year's four quarters - so FY - (Q1+Q2+Q3) is not a heuristic, it's the
        same identity a real Q4 income statement would satisfy if one were ever filed. EPS is
        deliberately NOT derived this way: live-confirmed via AZTR (a nano-cap with an
        extreme, volatile per-quarter EPS and a share count that nearly doubled between its
        last 10-Q and its next 10-K's cover-page date) that subtracting quarterly EPS values
        the same way produces a wildly implausible result (23.67, vs a real ~-0.20 when
        computed instead as this derived net_income / Q4's OWN reported share count) - EPS
        isn't a flow quantity, and isn't safely additive across quarters with a changing share
        count. Scope limited to revenue/net_income only; a future pass could add EPS via
        net_income / shares_outstanding (same quarter, not subtraction) with its own guard.

        Guards: only fires when Q1+Q2+Q3+annual all have real, non-null revenue AND
        net_income for the same fiscal year, and only writes revenue when the derived value is
        >= 0 (a real filer's revenue can restate but never actually go negative for a quarter -
        a negative derived value is a signal of an inter-filing restatement/reclassification
        between the annual and quarterly figures, not a real Q4 revenue result, and is skipped
        entirely rather than written). No corresponding bound on net_income - a real Q4 often
        legitimately absorbs large one-time items (annual bonus true-ups, impairments, tax
        adjustments) that don't afflict revenue the same way, so an aggressive magnitude guard
        there would reject far more real results than bad ones.
        """
        with _database_context()("write") as cur:
            cur.execute(
                """
                UPDATE quarterly_income_statement q4
                   SET revenue = derived.revenue,
                       net_income = derived.net_income,
                       data_unavailable = FALSE,
                       reason = NULL,
                       data_source = 'derived_fy_minus_9m'
                  FROM (
                        SELECT q4x.id,
                               a.revenue - (q1.revenue + q2.revenue + q3.revenue) AS revenue,
                               a.net_income - (q1.net_income + q2.net_income + q3.net_income) AS net_income
                          FROM quarterly_income_statement q4x
                          JOIN annual_income_statement a
                            ON a.symbol = q4x.symbol AND a.fiscal_year = q4x.fiscal_year
                          JOIN quarterly_income_statement q1
                            ON q1.symbol = q4x.symbol AND q1.fiscal_year = q4x.fiscal_year AND q1.fiscal_quarter = 1
                          JOIN quarterly_income_statement q2
                            ON q2.symbol = q4x.symbol AND q2.fiscal_year = q4x.fiscal_year AND q2.fiscal_quarter = 2
                          JOIN quarterly_income_statement q3
                            ON q3.symbol = q4x.symbol AND q3.fiscal_year = q4x.fiscal_year AND q3.fiscal_quarter = 3
                         WHERE q4x.fiscal_quarter = 4
                           AND (q4x.revenue IS NULL OR q4x.data_unavailable = TRUE)
                           AND a.revenue IS NOT NULL AND a.net_income IS NOT NULL
                           AND q1.revenue IS NOT NULL AND q2.revenue IS NOT NULL AND q3.revenue IS NOT NULL
                           AND q1.net_income IS NOT NULL AND q2.net_income IS NOT NULL AND q3.net_income IS NOT NULL
                           AND (a.revenue - (q1.revenue + q2.revenue + q3.revenue)) >= 0
                       ) AS derived
                 WHERE q4.id = derived.id
                """
            )
            if cur.rowcount:
                logger.warning(
                    f"[quarterly_income_statement] post_run(): derived {cur.rowcount} Q4 "
                    "revenue/net_income row(s) as FY_annual - 9mo_YTD (Q4 is never separately "
                    "filed by any US GAAP domestic filer)."
                )
        self._sweep_derive_missing_q4_interest_expense()
        self._sweep_derive_missing_q4_eps()
        self._sweep_derive_missing_q4_income_remaining_fields()

    def _sweep_derive_missing_q4_income_remaining_fields(self) -> None:
        """Derive operating_income/gross_profit/cost_of_revenue/depreciation_expense/
        amortization_expense/research_development_expense for a missing Q4
        quarterly_income_statement row as FY_annual - (Q1+Q2+Q3), same identity and
        independent-per-field gating as _sweep_derive_missing_q4_cash_flow_remaining_fields()
        (cash flow statement's sibling sweep).

        ADDED 2026-09-04 (goal: "missing SEC/XBRL data under 6k" sweep continuation):
        _sweep_derive_missing_q4() above only ever covered revenue/net_income - every other
        additive flow field on this table was left untouched, even though nothing about them
        is any less safe to derive this way than revenue/net_income already are. Live-
        confirmed recoverable: 25,792 operating_income / 12,873 gross_profit / 15,731
        cost_of_revenue / 11,224 depreciation_expense / 13,036 amortization_expense / 12,054
        research_development_expense rows - by far the largest remaining Q4-derivation gap in
        this file.

        Floor: cost_of_revenue/depreciation_expense/amortization_expense/
        research_development_expense are reported as non-negative cost/expense figures in this
        schema (same "a real filer's [cost] can restate but never actually go negative for a
        quarter" reasoning _sweep_derive_missing_q4() already applies to revenue) - a negative
        derived value there signals an inter-filing reclassification, not a real Q4 result, and
        is skipped. gross_profit and operating_income get NO floor: both can legitimately go
        negative for a real quarter (a company selling below cost, or absorbing a one-time
        operating charge), same reasoning _sweep_derive_missing_q4() already applies to
        net_income.
        """
        floored_fields = (
            "cost_of_revenue",
            "depreciation_expense",
            "amortization_expense",
            "research_development_expense",
        )
        unfloored_fields = ("operating_income", "gross_profit")
        with _database_context()("write") as cur:
            for field in floored_fields + unfloored_fields:
                floor_clause = (
                    f"AND (a.{field} - (q1.{field} + q2.{field} + q3.{field})) >= 0" if field in floored_fields else ""
                )
                cur.execute(
                    f"""
                    UPDATE quarterly_income_statement q4
                       SET {field} = derived.{field},
                           data_source = 'derived_fy_minus_9m'
                      FROM (
                            SELECT q4x.id,
                                   a.{field} - (q1.{field} + q2.{field} + q3.{field}) AS {field}
                              FROM quarterly_income_statement q4x
                              JOIN annual_income_statement a
                                ON a.symbol = q4x.symbol AND a.fiscal_year = q4x.fiscal_year
                              JOIN quarterly_income_statement q1
                                ON q1.symbol = q4x.symbol AND q1.fiscal_year = q4x.fiscal_year AND q1.fiscal_quarter = 1
                              JOIN quarterly_income_statement q2
                                ON q2.symbol = q4x.symbol AND q2.fiscal_year = q4x.fiscal_year AND q2.fiscal_quarter = 2
                              JOIN quarterly_income_statement q3
                                ON q3.symbol = q4x.symbol AND q3.fiscal_year = q4x.fiscal_year AND q3.fiscal_quarter = 3
                             WHERE q4x.fiscal_quarter = 4
                               AND q4x.{field} IS NULL
                               AND a.{field} IS NOT NULL
                               AND q1.{field} IS NOT NULL
                               AND q2.{field} IS NOT NULL
                               AND q3.{field} IS NOT NULL
                               {floor_clause}
                           ) AS derived
                     WHERE q4.id = derived.id
                    """
                )
                if cur.rowcount:
                    logger.warning(
                        f"[quarterly_income_statement] post_run(): derived {cur.rowcount} Q4 "
                        f"{field} row(s) as FY_annual - 9mo_YTD."
                    )

    def _sweep_derive_missing_q4_eps(self) -> None:
        """Derive earnings_per_share for a missing quarterly_income_statement row (any
        quarter) as net_income / shares_outstanding (that row's OWN reported share count),
        independent of what this run happened to fetch.

        FOUND 2026-09-04 (goal session: "missing SEC/XBRL data under 6k" sweep): unlike
        _sweep_derive_missing_q4()'s deliberate exclusion of EPS via subtraction (FY -
        (Q1+Q2+Q3) - see that method's own AZTR evidence for why subtracting per-share values
        across a changing share count produces wildly implausible results), this derives EPS
        the same safe way load_financial_statements.py's _fill_derived_eps() already does for
        annual rows: net_income / THIS row's own share count - never a subtraction, so a
        changing share count between quarters cannot corrupt the result. Guarded by the exact
        same corroboration discipline as _fill_derived_eps(): only derives when the resolved
        share count agrees with company_info_sec's independently-extracted value within 20x
        (same threshold, same rationale - an uncorroborated or scale-mismatched share count is
        skipped entirely rather than trusted). Originally scoped to fiscal_quarter=4 only
        (the "never separately filed" gap - 26,668 of 27,203 Q4 candidates passed); WIDENED
        2026-09-04 (same pass) to all four quarters once the underlying method was proven
        safe in production - the identical extraction gap (net_income/shares present, EPS
        itself not tagged) also occurs on Q1-Q3 rows for unrelated reasons (a transient
        concept-fetch gap, not the Q4-specific filing-never-exists cause), and the same safe
        derivation applies unchanged: 1,144 additional Q1-Q3 rows recoverable. Directly feeds
        growth_metrics' quarterly-derived fields (earnings_growth_4q_avg, eps_growth_stability,
        consecutive_positive_quarters).

        FIXED 2026-09-04 (same pass, live-caught before it could linger): the share-count
        corroboration guard above cannot catch a corrupted net_income - live-confirmed INVE
        FY2021/2022 quarterly net_income tagged as $1.6 TRILLION / -$392 BILLION (a pre-
        existing scale/tagging error in already-stored data, several orders of magnitude
        beyond anything a ~22M-share company could produce), dividing through to a
        "confirmed-real" 22.2M share count and landing a $72,874/share derived EPS - the
        exact same "confidently wrong, not just missing" failure _reject_implausible_eps()
        exists to catch for directly-reported EPS, applied here to a value THIS sweep itself
        would otherwise manufacture.

        FIXED 2026-09-04 (same pass, second catch on the SAME bug): the first ceiling
        (abs(eps) <= 100,000) was too loose to actually exclude INVE's $72,874 - it slipped
        back through when this sweep was widened to all four quarters and re-ran. Live-
        checked the real distribution of every value this sweep has ever derived: the
        highest genuine one is BRK.A's own $1,604.92/share (2011, a real, well-known
        high-price-per-share stock), with SEB/BH/BH.A the next tier down around $150-340 -
        a wide, clean gap below INVE's garbage value. Tightened to abs(eps) <= 10,000 (still
        ~6x BRK.A's own real historical maximum, comfortable margin without being loose
        enough to let a similarly-corrupted net_income back through). INVE's two rows were
        caught and reverted by hand a second time before this tighter guard existed.
        """
        with _database_context()("write") as cur:
            cur.execute(
                """
                UPDATE quarterly_income_statement q4
                   SET earnings_per_share = derived.eps,
                       data_source = 'derived_ni_shares'
                  FROM (
                        SELECT q4x.id,
                               q4x.net_income / COALESCE(
                                   q4x.shares_outstanding_diluted, q4x.shares_outstanding_basic, q4x.shares_outstanding_dei
                               ) AS eps
                          FROM quarterly_income_statement q4x
                          JOIN company_info_sec cis
                            ON cis.symbol = q4x.symbol AND cis.shares_outstanding > 0
                         WHERE q4x.earnings_per_share IS NULL
                           AND q4x.net_income IS NOT NULL
                           AND COALESCE(
                                   q4x.shares_outstanding_diluted, q4x.shares_outstanding_basic, q4x.shares_outstanding_dei
                               ) IS NOT NULL
                           AND COALESCE(
                                   q4x.shares_outstanding_diluted, q4x.shares_outstanding_basic, q4x.shares_outstanding_dei
                               ) > 0
                           AND GREATEST(
                                   cis.shares_outstanding,
                                   COALESCE(q4x.shares_outstanding_diluted, q4x.shares_outstanding_basic, q4x.shares_outstanding_dei)
                               )
                               / LEAST(
                                   cis.shares_outstanding,
                                   COALESCE(q4x.shares_outstanding_diluted, q4x.shares_outstanding_basic, q4x.shares_outstanding_dei)
                               ) <= 20
                           AND ABS(
                                   q4x.net_income / COALESCE(
                                       q4x.shares_outstanding_diluted, q4x.shares_outstanding_basic, q4x.shares_outstanding_dei
                                   )
                               ) <= 10000
                       ) AS derived
                 WHERE q4.id = derived.id
                """
            )
            if cur.rowcount:
                logger.warning(
                    f"[quarterly_income_statement] post_run(): derived {cur.rowcount} "
                    "earnings_per_share row(s) as net_income / shares_outstanding "
                    "(company_info_sec-corroborated)."
                )

    def _sweep_derive_missing_q4_interest_expense(self) -> None:
        """Derive interest_expense for a missing Q4 quarterly_income_statement row as
        FY_annual - (Q1+Q2+Q3), same identity and same discipline as
        _sweep_derive_missing_q4()'s revenue/net_income above, but as its own independent
        UPDATE: interest_expense can be (and very often is) the only field still missing on a
        Q4 row whose revenue/net_income were already recovered by the sweep above (or were
        never missing to begin with) - gating this on revenue's own null-check would miss all
        of those rows. Live-confirmed 27,037 rows recoverable this way - directly feeds
        interest_coverage, currently one of the largest remaining quality_metrics gaps.
        Same non-negative guard as revenue: a real filer's interest_expense doesn't go
        negative for a quarter; a negative derived value signals an inter-filing
        restatement/reclassification, not a real Q4 result, and is skipped.
        """
        with _database_context()("write") as cur:
            cur.execute(
                """
                UPDATE quarterly_income_statement q4
                   SET interest_expense = derived.interest_expense,
                       data_source = 'derived_fy_minus_9m'
                  FROM (
                        SELECT q4x.id,
                               a.interest_expense - (q1.interest_expense + q2.interest_expense + q3.interest_expense) AS interest_expense
                          FROM quarterly_income_statement q4x
                          JOIN annual_income_statement a
                            ON a.symbol = q4x.symbol AND a.fiscal_year = q4x.fiscal_year
                          JOIN quarterly_income_statement q1
                            ON q1.symbol = q4x.symbol AND q1.fiscal_year = q4x.fiscal_year AND q1.fiscal_quarter = 1
                          JOIN quarterly_income_statement q2
                            ON q2.symbol = q4x.symbol AND q2.fiscal_year = q4x.fiscal_year AND q2.fiscal_quarter = 2
                          JOIN quarterly_income_statement q3
                            ON q3.symbol = q4x.symbol AND q3.fiscal_year = q4x.fiscal_year AND q3.fiscal_quarter = 3
                         WHERE q4x.fiscal_quarter = 4
                           AND q4x.interest_expense IS NULL
                           AND a.interest_expense IS NOT NULL
                           AND q1.interest_expense IS NOT NULL
                           AND q2.interest_expense IS NOT NULL
                           AND q3.interest_expense IS NOT NULL
                           AND (a.interest_expense - (q1.interest_expense + q2.interest_expense + q3.interest_expense)) >= 0
                       ) AS derived
                 WHERE q4.id = derived.id
                """
            )
            if cur.rowcount:
                logger.warning(
                    f"[quarterly_income_statement] post_run(): derived {cur.rowcount} Q4 "
                    "interest_expense row(s) as FY_annual - 9mo_YTD."
                )
        self._sweep_derive_missing_q4_pretax_and_tax()

    def _sweep_derive_missing_q4_pretax_and_tax(self) -> None:
        """Derive pretax_income/income_tax_expense for a missing Q4 quarterly_income_statement
        row as FY_annual - (Q1+Q2+Q3), same identity as interest_expense above, as two more
        independent UPDATEs (each field gated on its own null-check only). Live-confirmed
        27,992 pretax_income / 27,836 income_tax_expense rows recoverable - comparable in
        scale to interest_expense, both feed operating_margin/roic_pct/effective-tax-rate
        inputs elsewhere.

        Unlike revenue/interest_expense, NEITHER field gets a non-negative floor: a real Q4
        can legitimately post a pretax LOSS (a floor would reject genuine bad quarters) and a
        real income_tax_expense can legitimately be negative (a tax BENEFIT in a loss
        quarter) - same "no floor" treatment already given to net_income in
        _sweep_derive_missing_q4() above, for the identical reason.
        """
        with _database_context()("write") as cur:
            cur.execute(
                """
                UPDATE quarterly_income_statement q4
                   SET pretax_income = derived.pretax_income,
                       data_source = 'derived_fy_minus_9m'
                  FROM (
                        SELECT q4x.id,
                               a.pretax_income - (q1.pretax_income + q2.pretax_income + q3.pretax_income) AS pretax_income
                          FROM quarterly_income_statement q4x
                          JOIN annual_income_statement a
                            ON a.symbol = q4x.symbol AND a.fiscal_year = q4x.fiscal_year
                          JOIN quarterly_income_statement q1
                            ON q1.symbol = q4x.symbol AND q1.fiscal_year = q4x.fiscal_year AND q1.fiscal_quarter = 1
                          JOIN quarterly_income_statement q2
                            ON q2.symbol = q4x.symbol AND q2.fiscal_year = q4x.fiscal_year AND q2.fiscal_quarter = 2
                          JOIN quarterly_income_statement q3
                            ON q3.symbol = q4x.symbol AND q3.fiscal_year = q4x.fiscal_year AND q3.fiscal_quarter = 3
                         WHERE q4x.fiscal_quarter = 4
                           AND q4x.pretax_income IS NULL
                           AND a.pretax_income IS NOT NULL
                           AND q1.pretax_income IS NOT NULL
                           AND q2.pretax_income IS NOT NULL
                           AND q3.pretax_income IS NOT NULL
                       ) AS derived
                 WHERE q4.id = derived.id
                """
            )
            if cur.rowcount:
                logger.warning(
                    f"[quarterly_income_statement] post_run(): derived {cur.rowcount} Q4 "
                    "pretax_income row(s) as FY_annual - 9mo_YTD."
                )
            cur.execute(
                """
                UPDATE quarterly_income_statement q4
                   SET income_tax_expense = derived.income_tax_expense,
                       data_source = 'derived_fy_minus_9m'
                  FROM (
                        SELECT q4x.id,
                               a.income_tax_expense - (q1.income_tax_expense + q2.income_tax_expense + q3.income_tax_expense) AS income_tax_expense
                          FROM quarterly_income_statement q4x
                          JOIN annual_income_statement a
                            ON a.symbol = q4x.symbol AND a.fiscal_year = q4x.fiscal_year
                          JOIN quarterly_income_statement q1
                            ON q1.symbol = q4x.symbol AND q1.fiscal_year = q4x.fiscal_year AND q1.fiscal_quarter = 1
                          JOIN quarterly_income_statement q2
                            ON q2.symbol = q4x.symbol AND q2.fiscal_year = q4x.fiscal_year AND q2.fiscal_quarter = 2
                          JOIN quarterly_income_statement q3
                            ON q3.symbol = q4x.symbol AND q3.fiscal_year = q4x.fiscal_year AND q3.fiscal_quarter = 3
                         WHERE q4x.fiscal_quarter = 4
                           AND q4x.income_tax_expense IS NULL
                           AND a.income_tax_expense IS NOT NULL
                           AND q1.income_tax_expense IS NOT NULL
                           AND q2.income_tax_expense IS NOT NULL
                           AND q3.income_tax_expense IS NOT NULL
                       ) AS derived
                 WHERE q4.id = derived.id
                """
            )
            if cur.rowcount:
                logger.warning(
                    f"[quarterly_income_statement] post_run(): derived {cur.rowcount} Q4 "
                    "income_tax_expense row(s) as FY_annual - 9mo_YTD."
                )

    def _sweep_missing_free_cash_flow(self) -> None:
        """Table-wide free_cash_flow = operating_cash_flow - capex recompute, independent of
        what this run happened to fetch.

        FOUND 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep):
        free_cash_flow has no direct XBRL concept - sec_base.py's transform() derives it
        in-row from THIS run's own freshly-fetched operating_cash_flow/capex only (see that
        block's own comment). But free_cash_flow itself is not in preserve_on_missing_fields
        (it's synthesized, not a field_mapping value), so bulk_insert()'s ON CONFLICT always
        overwrites it with whatever this run's row computed - including NULL, whenever this
        run's fetch came back without a fresh value for either input. operating_cash_flow and
        capex ARE preserved (real field_mapping values), so a transient gap in either one
        (rate limiting, a concept SEC didn't re-serve this run, an interim filing that simply
        doesn't re-disclose the full cash-flow statement) leaves the DB with real, COALESCE-
        preserved operating_cash_flow/capex but a wiped, never-recomputed free_cash_flow -
        permanently, until some future run happens to fetch both fresh in the very same pass.
        Live-confirmed 57 rows / 39 symbols (CNQ, DB, VET, BTE and others) with exactly this
        shape: both real inputs on file, right now, but free_cash_flow NULL. Since the
        recompute only ever needs the two values already committed in the table - not a fresh
        SEC response - this sweep applies the identical `ocf - capex` formula directly
        against the full table on every cash-flow-statement run, same "recompute from
        already-stored real values" discipline as _sweep_stale_implausible_eps() above.
        """
        with _database_context()("write") as cur:
            cur.execute(
                """
                UPDATE annual_cash_flow
                   SET free_cash_flow = operating_cash_flow - capex
                 WHERE free_cash_flow IS NULL
                   AND operating_cash_flow IS NOT NULL
                   AND capex IS NOT NULL
                """
            )
            if cur.rowcount:
                logger.warning(
                    f"[annual_cash_flow] post_run(): recomputed {cur.rowcount} free_cash_flow "
                    "row(s) that had both real operating_cash_flow and capex on file but a "
                    "NULL free_cash_flow left behind by a prior run's incomplete refetch."
                )

    def _sweep_stale_implausible_eps(self) -> None:
        """Table-wide implausible-EPS sweep, independent of what this run happened to fetch.

        FOUND 2026-08-24 (goal session: real-money-readiness sweep): the per-run rejection
        path above (_explicit_null_rejections) can only force-null a cell if THIS run's SEC
        fetch actually returned a value for that (symbol, fiscal_year, field) - live-confirmed
        via a scoped --symbols remediation re-fetch of 38 known-bad symbols (SWK, LNG, ICE,
        FITB, NU, CRVO, and 32 others) that only cleared 5 of 85 known-bad rows. The other 80
        are older fiscal years (mostly pre-2015) that SEC's live companyfacts API no longer
        serves fresh data for on a routine re-fetch, so _reject_implausible_eps() never even
        sees them and post_run()'s force-null above has nothing to act on - re-fetching can
        NEVER reach these rows no matter how many times it runs. Since the implausibility
        criterion (abs(net_income/eps) < 10,000 implied shares) only needs the value already
        stored in the DB, not a fresh SEC response, this sweep applies the identical,
        already-tested rule directly against the full table on every income-statement run -
        not new unverified data, just removing values already known to be confidently wrong
        by the same rule the fresh-fetch path uses. Same 10,000 floor as
        _reject_implausible_eps() (BRK.A/BSAC/EC all clear it comfortably).
        """
        with _database_context()("write") as cur:
            cur.execute(
                f"""
                UPDATE {self.table_name}
                SET earnings_per_share = CASE
                        WHEN earnings_per_share IS NOT NULL AND earnings_per_share != 0
                             AND net_income IS NOT NULL AND net_income != 0
                             AND abs(net_income / earnings_per_share) < 10000
                        THEN NULL ELSE earnings_per_share END,
                    diluted_eps = CASE
                        WHEN diluted_eps IS NOT NULL AND diluted_eps != 0
                             AND net_income IS NOT NULL AND net_income != 0
                             AND abs(net_income / diluted_eps) < 10000
                        THEN NULL ELSE diluted_eps END
                WHERE net_income IS NOT NULL AND net_income != 0
                  AND (
                        (earnings_per_share IS NOT NULL AND earnings_per_share != 0
                         AND abs(net_income / earnings_per_share) < 10000)
                        OR
                        (diluted_eps IS NOT NULL AND diluted_eps != 0
                         AND abs(net_income / diluted_eps) < 10000)
                      )
                """
            )
            swept = cur.rowcount
        if swept:
            logger.warning(
                f"[{self.table_name}] _sweep_stale_implausible_eps(): force-nulled implausible "
                f"earnings_per_share/diluted_eps on {swept} row(s) that this run's fetch never "
                "touched (stale historical data the live SEC API no longer re-serves)."
            )
