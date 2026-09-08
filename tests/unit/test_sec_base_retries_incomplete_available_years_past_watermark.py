"""Regression test for the 2026-08-18 fix: fetch_incremental()'s retry-set only covered
fiscal years marked `data_unavailable = TRUE` (test_sec_base_retries_unavailable_years_
past_watermark.py) - it did nothing for the DIFFERENT, more common shape of the same bug:
a row written successfully (data_unavailable = FALSE) but missing this statement's one
load-bearing field because of an extraction gap that a later fix might now close.

Live-confirmed on AVAV: annual_balance_sheet FY2024-2026 rows have real total_assets on
file, data_unavailable=FALSE, yet stockholders_equity NULL every year. The 2026-08-18
mid-year-10-Q-stub fix (d36598a2d) landed and a fresh full pipeline pass ran afterward,
but AVAV's watermark had already advanced past FY2026 from an earlier run, so
`fiscal_year > since_year` silently discarded these rows before the fix could ever reach
them - same root mechanism, just never marked data_unavailable=TRUE in the first place
because total_assets DID extract fine that year.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import (
    ConsolidatedFinancialStatementsLoader,
    get_balance_sheet_config,
    get_cash_flow_config,
)


def _make_cashflow_loader() -> ConsolidatedFinancialStatementsLoader:
    loader = ConsolidatedFinancialStatementsLoader.__new__(ConsolidatedFinancialStatementsLoader)
    config = get_cash_flow_config("annual")
    loader.table_name = config["table_name"]
    loader.period = "annual"
    loader.statement_type = "cashflow"
    loader.is_symbol_based = True
    loader._schema_cols = config["schema_cols"]
    loader._field_mapping = config["field_mapping"]
    loader._sec_client = MagicMock()
    loader._sec_client.symbol_to_cik.return_value = "0001234567"
    return loader


def _make_balance_loader() -> ConsolidatedFinancialStatementsLoader:
    loader = ConsolidatedFinancialStatementsLoader.__new__(ConsolidatedFinancialStatementsLoader)
    config = get_balance_sheet_config("annual")
    loader.table_name = config["table_name"]
    loader.period = "annual"
    loader.statement_type = "balance"
    loader.is_symbol_based = True
    loader._schema_cols = config["schema_cols"]
    loader._field_mapping = config["field_mapping"]
    loader._sec_client = MagicMock()
    loader._sec_client.symbol_to_cik.return_value = "0001234567"
    return loader


def _fake_db_context(has_rows_for_symbol: bool, unavailable_years: list, incomplete_years: list):
    """Dispatches by query text: the desync-guard's `SELECT 1 ... LIMIT 1`, the
    data_unavailable=TRUE retry query, the data_unavailable=FALSE + core-field-NULL retry
    query, and the unrelated (2026-09-02) dual-class-EPS `stock_symbols` security_name bulk
    lookup (income statement_type only) each return a different fixed result."""

    def factory(mode, **kwargs):
        ctx = MagicMock()
        cur = MagicMock()
        state = {"query": None}

        def execute(query, params=None):
            state["query"] = query

        def fetchone():
            return (1,) if has_rows_for_symbol else None

        def fetchall():
            if "stock_symbols" in state["query"]:
                return []  # no dual-class security_name matches in these fixtures
            if "data_unavailable = TRUE" in state["query"]:
                return [(y,) for y in unavailable_years]
            if "data_unavailable = FALSE" in state["query"]:
                return [(y,) for y in incomplete_years]
            raise AssertionError(f"Unexpected query: {state['query']}")

        cur.execute.side_effect = execute
        cur.fetchone.side_effect = fetchone
        cur.fetchall.side_effect = fetchall
        ctx.__enter__.return_value = cur
        ctx.__exit__.return_value = False
        return ctx

    return factory


class TestRetriesIncompleteAvailableYearsPastWatermark:
    def test_retries_fiscal_year_available_but_missing_core_field(self):
        loader = _make_balance_loader()
        # Full refetched history from SEC - both the current year (already past the
        # watermark) and an older year that IS on file (data_unavailable=FALSE) but
        # missing stockholders_equity specifically, same as AVAV's real state.
        loader._sec_client.get_balance_sheet.return_value = [
            {"symbol": "AVAV", "fiscal_year": 2026, "total_assets": 5_716_742_000, "stockholders_equity": 900_000_000},
            {"symbol": "AVAV", "fiscal_year": 2024, "total_assets": 1_015_860_000, "stockholders_equity": 700_000_000},
        ]

        with patch(
            "utils.db.context.DatabaseContext",
            side_effect=_fake_db_context(has_rows_for_symbol=True, unavailable_years=[], incomplete_years=[2024]),
        ):
            rows = loader.fetch_incremental("AVAV", since=date(2025, 12, 31))

        # Without the fix, since_year=2025 would silently drop the FY2024 row forever,
        # even though stockholders_equity is now extractable and right there in the
        # freshly refetched data.
        fiscal_years = {r["fiscal_year"] for r in rows}
        assert fiscal_years == {2026, 2024}

    def test_does_not_retry_years_with_core_field_already_populated(self):
        loader = _make_balance_loader()
        loader._sec_client.get_balance_sheet.return_value = [
            {
                "symbol": "AAPL",
                "fiscal_year": 2025,
                "total_assets": 400_000_000_000,
                "stockholders_equity": 60_000_000_000,
            },
            {
                "symbol": "AAPL",
                "fiscal_year": 2020,
                "total_assets": 275_000_000_000,
                "stockholders_equity": 65_000_000_000,
            },
        ]

        with patch(
            "utils.db.context.DatabaseContext",
            side_effect=_fake_db_context(has_rows_for_symbol=True, unavailable_years=[], incomplete_years=[]),
        ):
            rows = loader.fetch_incremental("AAPL", since=date(2024, 12, 31))

        # Normal incremental behavior preserved: no incomplete years on file, so only
        # the fiscal year newer than the watermark comes through.
        assert {r["fiscal_year"] for r in rows} == {2025}

    def test_income_statement_uses_net_income_as_core_field(self):
        """Different statement_type -> different core field(s) (_CORE_FIELD_BY_STATEMENT_TYPE)."""
        from loaders.load_financial_statements import get_income_statement_config

        loader = ConsolidatedFinancialStatementsLoader.__new__(ConsolidatedFinancialStatementsLoader)
        config = get_income_statement_config("annual")
        loader.table_name = config["table_name"]
        loader.period = "annual"
        loader.statement_type = "income"
        loader.is_symbol_based = True
        loader._schema_cols = config["schema_cols"]
        loader._field_mapping = config["field_mapping"]
        loader._sec_client = MagicMock()
        loader._sec_client.symbol_to_cik.return_value = "0001234567"
        loader._sec_client.get_income_statement.return_value = [
            {"symbol": "XYZ", "fiscal_year": 2025, "revenues": 100},
            {"symbol": "XYZ", "fiscal_year": 2023, "revenues": 90},
        ]

        captured_queries = []

        def factory(mode, **kwargs):
            ctx = MagicMock()
            cur = MagicMock()

            def execute(query, params=None):
                captured_queries.append(query)

            cur.execute.side_effect = execute
            cur.fetchone.side_effect = lambda: (1,)
            cur.fetchall.side_effect = list
            ctx.__enter__.return_value = cur
            ctx.__exit__.return_value = False
            return ctx

        with patch("utils.db.context.DatabaseContext", side_effect=factory):
            loader.fetch_incremental("XYZ", since=date(2024, 12, 31))

        assert any("net_income IS NULL" in q for q in captured_queries)
        # ADDED 2026-09-02: revenue is now ALSO a retry-trigger field for income - see
        # test_retries_amzn_style_stub_row_with_net_income_but_null_revenue below.
        assert any("revenue IS NULL" in q for q in captured_queries)

    def test_retries_amzn_style_stub_row_with_net_income_but_null_revenue(self):
        """2026-09-02 fix: income's core-field retry now ALSO fires on `revenue` alone, not
        just `net_income` - see _CORE_FIELD_BY_STATEMENT_TYPE's comment (same bug shape as
        the 2026-08-29 cashflow/capex fix above). Live-confirmed for AMZN: a TTM 10-Q
        duration fact (commit 42d24bbdb) could clobber a fiscal year's real
        revenue/operating_income/pretax_income while `net_income` stayed non-NULL (a
        DIFFERENT fact happened to land there) - AMZN's FY2026 stub row
        (net_income=$135,281,000,000, revenue/operating_income/pretax_income all NULL,
        data_unavailable=FALSE) was permanently unreachable by the old net_income-only
        retry check, so the already-fixed 42d24bbdb correction could never actually reach
        the row despite the code fix being live."""
        from loaders.load_financial_statements import get_income_statement_config

        loader = ConsolidatedFinancialStatementsLoader.__new__(ConsolidatedFinancialStatementsLoader)
        config = get_income_statement_config("annual")
        loader.table_name = config["table_name"]
        loader.period = "annual"
        loader.statement_type = "income"
        loader.is_symbol_based = True
        loader._schema_cols = config["schema_cols"]
        loader._field_mapping = config["field_mapping"]
        loader._sec_client = MagicMock()
        loader._sec_client.symbol_to_cik.return_value = "0001234567"
        loader._sec_client.get_income_statement.return_value = [
            # The real AMZN shape: net_income populated (from the TTM fact that clobbered
            # this bucket), revenue left None (the field the clobber actually broke).
            {"symbol": "AMZN", "fiscal_year": 2026, "net_income": 135_281_000_000, "revenue": None},
            {"symbol": "AMZN", "fiscal_year": 2025, "net_income": 70_623_000_000, "revenue": 716_924_000_000},
        ]

        with patch(
            "utils.db.context.DatabaseContext",
            # since_year=2026 excludes FY2026 from the normal "fiscal_year > since_year"
            # path entirely (the real AMZN watermark is stuck exactly this way) - only the
            # revenue-IS-NULL retry query (incomplete_years=[2026]) can rescue it.
            side_effect=_fake_db_context(has_rows_for_symbol=True, unavailable_years=[], incomplete_years=[2026]),
        ):
            rows = loader.fetch_incremental("AMZN", since=date(2026, 12, 31))

        # Without the fix, FY2026's stub row (net_income present, revenue NULL) would never
        # qualify for retry (only net_income IS NULL was checked) and, with since_year=2026
        # excluding it from the normal path too, would be permanently unreachable - exactly
        # AMZN's real state even after 42d24bbdb's parser-level fix landed on main.
        assert {r["fiscal_year"] for r in rows} == {2026}

    def test_retries_fiscal_year_with_net_income_and_revenue_but_income_tax_expense_null(self):
        """2026-09-05 fix: income's core-field retry now ALSO fires on `operating_income`/
        `income_tax_expense`/`interest_expense`/`pretax_income` alone, not just
        `net_income`/`revenue` - see _CORE_FIELD_BY_STATEMENT_TYPE's comment. Live-confirmed
        for CNS (Cohen & Steers): FY2025 has real net_income=$153.2M/revenue=$556.1M on file
        (watermark already at 2025-12-31), but income_tax_expense NULL - the same-session
        `0e7051e9a` wiring fix could never reach this row without this addition."""
        from loaders.load_financial_statements import get_income_statement_config

        loader = ConsolidatedFinancialStatementsLoader.__new__(ConsolidatedFinancialStatementsLoader)
        config = get_income_statement_config("annual")
        loader.table_name = config["table_name"]
        loader.period = "annual"
        loader.statement_type = "income"
        loader.is_symbol_based = True
        loader._schema_cols = config["schema_cols"]
        loader._field_mapping = config["field_mapping"]
        loader._sec_client = MagicMock()
        loader._sec_client.symbol_to_cik.return_value = "0001234567"
        loader._sec_client.get_income_statement.return_value = [
            {
                "symbol": "CNS",
                "fiscal_year": 2025,
                "net_income": 153_217_000,
                "revenue": 556_116_000,
                "income_tax_expense": 46_749_000,
            },
        ]

        with patch(
            "utils.db.context.DatabaseContext",
            side_effect=_fake_db_context(has_rows_for_symbol=True, unavailable_years=[], incomplete_years=[2025]),
        ):
            rows = loader.fetch_incremental("CNS", since=date(2025, 12, 31))

        assert {r["fiscal_year"] for r in rows} == {2025}

    def test_income_statement_uses_all_six_core_fields(self):
        """Confirms all 6 income retry-trigger fields are wired into the query set."""
        from loaders.load_financial_statements import get_income_statement_config

        loader = ConsolidatedFinancialStatementsLoader.__new__(ConsolidatedFinancialStatementsLoader)
        config = get_income_statement_config("annual")
        loader.table_name = config["table_name"]
        loader.period = "annual"
        loader.statement_type = "income"
        loader.is_symbol_based = True
        loader._schema_cols = config["schema_cols"]
        loader._field_mapping = config["field_mapping"]
        loader._sec_client = MagicMock()
        loader._sec_client.symbol_to_cik.return_value = "0001234567"
        loader._sec_client.get_income_statement.return_value = [
            {"symbol": "XYZ", "fiscal_year": 2025, "revenue": 100},
        ]

        captured_queries = []

        def factory(mode, **kwargs):
            ctx = MagicMock()
            cur = MagicMock()

            def execute(query, params=None):
                captured_queries.append(query)

            cur.execute.side_effect = execute
            cur.fetchone.side_effect = lambda: (1,)
            cur.fetchall.side_effect = list
            ctx.__enter__.return_value = cur
            ctx.__exit__.return_value = False
            return ctx

        with patch("utils.db.context.DatabaseContext", side_effect=factory):
            loader.fetch_incremental("XYZ", since=date(2024, 12, 31))

        for field in (
            "net_income",
            "revenue",
            "operating_income",
            "income_tax_expense",
            "interest_expense",
            "pretax_income",
        ):
            assert any(f"{field} IS NULL" in q for q in captured_queries), f"missing retry query for {field}"

    def test_retries_fiscal_year_with_operating_cash_flow_populated_but_capex_null(self):
        """2026-08-29 fix: cashflow's core-field retry now also fires on `capex` alone,
        not just `operating_cash_flow` - see _CORE_FIELD_BY_STATEMENT_TYPE's comment.
        Live-confirmed for SIC-1311 oil & gas E&P symbols (APA etc.): FY2025 had real
        operating_cash_flow on file (so it never qualified as a core-field retry
        candidate) but NULL capex, which a later concept-mapping fix could now resolve -
        without this, that fiscal year could never be retried again once the watermark
        advanced past it."""
        loader = _make_cashflow_loader()
        loader._sec_client.get_cash_flow.return_value = [
            {"symbol": "APA", "fiscal_year": 2026, "operating_cash_flow": 1_000_000_000, "capex": None},
            {"symbol": "APA", "fiscal_year": 2025, "operating_cash_flow": 4_545_000_000, "capex": 2_740_000_000},
        ]

        with patch(
            "utils.db.context.DatabaseContext",
            side_effect=_fake_db_context(has_rows_for_symbol=True, unavailable_years=[], incomplete_years=[2025]),
        ):
            rows = loader.fetch_incremental("APA", since=date(2025, 12, 31))

        # Without the fix, since_year=2025 would silently drop the FY2025 row forever,
        # even though capex is now extractable and right there in the freshly refetched
        # data - operating_cash_flow being non-NULL meant it never triggered a retry.
        assert {r["fiscal_year"] for r in rows} == {2026, 2025}

    def test_does_not_retry_cashflow_years_with_both_fields_already_populated(self):
        loader = _make_cashflow_loader()
        loader._sec_client.get_cash_flow.return_value = [
            {"symbol": "XOM", "fiscal_year": 2025, "operating_cash_flow": 55_000_000_000, "capex": 24_000_000_000},
            {"symbol": "XOM", "fiscal_year": 2020, "operating_cash_flow": 20_000_000_000, "capex": 20_000_000_000},
        ]

        with patch(
            "utils.db.context.DatabaseContext",
            side_effect=_fake_db_context(has_rows_for_symbol=True, unavailable_years=[], incomplete_years=[]),
        ):
            rows = loader.fetch_incremental("XOM", since=date(2024, 12, 31))

        assert {r["fiscal_year"] for r in rows} == {2025}

    def test_retries_fiscal_year_with_equity_populated_but_long_term_debt_null(self):
        """2026-09-05 fix: balance's core-field retry now ALSO fires on `long_term_debt`/
        `short_term_debt` alone, not just `stockholders_equity` - see
        _CORE_FIELD_BY_STATEMENT_TYPE's comment (same bug shape as cashflow's capex/income's
        revenue additions above, previously the one documented gap: "balance left as a
        single-field tuple ... no equivalent secondary-field gap found for it yet").
        Live-confirmed this session for mortgage REITs (ORC/EARN/etc.) and dozens of other
        symbols: a real, non-NULL `stockholders_equity` meant these fiscal years never
        qualified as retry candidates, so this week's debt-concept fallbacks (repo
        agreements, LineOfCredit, DebtCurrent, ...) could never actually reach an
        already-processed year even after landing in sec_statements.py."""
        loader = _make_balance_loader()
        loader._sec_client.get_balance_sheet.return_value = [
            {"symbol": "ORC", "fiscal_year": 2026, "stockholders_equity": 1_371_948_000, "long_term_debt": None},
            {"symbol": "ORC", "fiscal_year": 2025, "stockholders_equity": 668_500_000, "long_term_debt": None},
        ]

        with patch(
            "utils.db.context.DatabaseContext",
            side_effect=_fake_db_context(has_rows_for_symbol=True, unavailable_years=[], incomplete_years=[2025]),
        ):
            rows = loader.fetch_incremental("ORC", since=date(2025, 12, 31))

        # Without the fix, since_year=2025 would silently drop the FY2025 row forever,
        # even though a debt concept fix now landed and is right there in the freshly
        # refetched data - stockholders_equity being non-NULL meant it never triggered a
        # retry under the old single-field check.
        assert {r["fiscal_year"] for r in rows} == {2026, 2025}

    def test_retries_fiscal_year_with_debt_populated_but_retained_earnings_null(self):
        """2026-09-07 fix: balance's core-field retry now ALSO fires on `retained_earnings`
        alone - see _CORE_FIELD_BY_STATEMENT_TYPE's comment. Live-confirmed: quarterly_
        balance_sheet's retained_earnings column (migration 1266) sat at 0/212,531 populated
        even on rows this session's own reload freshly wrote, because every other balance
        core field was already non-NULL for those symbols - exactly the same
        already-processed-year gap as the long_term_debt/short_term_debt fix above."""
        loader = _make_balance_loader()
        loader._sec_client.get_balance_sheet.return_value = [
            {
                "symbol": "CSX",
                "fiscal_year": 2026,
                "stockholders_equity": 12_000_000_000,
                "long_term_debt": 18_000_000_000,
                "short_term_debt": 500_000_000,
                "retained_earnings": None,
            },
            {
                "symbol": "CSX",
                "fiscal_year": 2025,
                "stockholders_equity": 11_500_000_000,
                "long_term_debt": 17_500_000_000,
                "short_term_debt": 450_000_000,
                "retained_earnings": None,
            },
        ]

        with patch(
            "utils.db.context.DatabaseContext",
            side_effect=_fake_db_context(has_rows_for_symbol=True, unavailable_years=[], incomplete_years=[2025]),
        ):
            rows = loader.fetch_incremental("CSX", since=date(2025, 12, 31))

        # Without the fix, since_year=2025 would silently drop the FY2025 row forever, even
        # though retained_earnings is now extractable and right there in the freshly
        # refetched data - stockholders_equity/long_term_debt/short_term_debt all being
        # non-NULL meant it never triggered a retry under the old 3-field check.
        assert {r["fiscal_year"] for r in rows} == {2026, 2025}

    def test_balance_statement_uses_debt_fields_as_core_fields(self):
        """Different statement_type -> different core field(s) (_CORE_FIELD_BY_STATEMENT_TYPE)."""
        loader = _make_balance_loader()
        loader._sec_client.get_balance_sheet.return_value = [
            {"symbol": "AIG", "fiscal_year": 2025, "stockholders_equity": 41_139_000_000},
            {"symbol": "AIG", "fiscal_year": 2023, "stockholders_equity": 45_351_000_000},
        ]

        captured_queries = []

        def factory(mode, **kwargs):
            ctx = MagicMock()
            cur = MagicMock()

            def execute(query, params=None):
                captured_queries.append(query)

            cur.execute.side_effect = execute
            cur.fetchone.side_effect = lambda: (1,)
            cur.fetchall.side_effect = list
            ctx.__enter__.return_value = cur
            ctx.__exit__.return_value = False
            return ctx

        with patch("utils.db.context.DatabaseContext", side_effect=factory):
            loader.fetch_incremental("AIG", since=date(2024, 12, 31))

        assert any("stockholders_equity IS NULL" in q for q in captured_queries)
        assert any("long_term_debt IS NULL" in q for q in captured_queries)
        assert any("short_term_debt IS NULL" in q for q in captured_queries)
