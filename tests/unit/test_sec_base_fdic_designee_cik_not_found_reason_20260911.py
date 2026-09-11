"""Regression test: SecEdgarStatementLoader.fetch_incremental's CIK-not-found path must
use cik_not_found_reason(), not the bare "cik_not_found" literal.

Found live 2026-09-11 (goal: "SEC/XBRL missing data under 300" push, continuation of the
same-session fdic_designee_no_sec_cik fix already landed for load_company_info_sec.py/
load_current_reports_8k.py/load_dividend_data.py). This is the single shared CIK-lookup
call site for EVERY statement loader (income/balance/cashflow, annual/quarterly) via
loaders/helpers/sec_base.py's fetch_incremental() - it still wrote the generic
"cik_not_found" for a confirmed FDIC/OCC/Fed-supervised bank (no SEC CIK ever, see
KNOWN_NON_SEC_FILER_BANK_TICKERS's docstring in sec_ticker_cache.py) even though the
identical situation was already fixed for the 3 loaders above. Live-confirmed impact:
RCBC's annual_income_statement/quality_metrics/sec_valuations rows were all still stale
on "cik_not_found"/"total_debt_not_itemized" ("Missing SEC/XBRL data" - actionable) after
the FDIC fix landed, since financial_statements never routed through cik_not_found_reason().
"""

from unittest.mock import MagicMock, patch

from loaders.helpers.sec_base import SecEdgarStatementLoader


def _make_loader() -> SecEdgarStatementLoader:
    loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
    loader.table_name = "annual_income_statement"
    loader.statement_type = "income"
    loader.period = "annual"
    loader._sec_client = MagicMock()
    return loader


class TestFdicDesigneeCikNotFoundReason:
    def test_confirmed_fdic_designee_bank_gets_distinct_reason(self) -> None:
        loader = _make_loader()
        loader._sec_client.symbol_to_cik.side_effect = ValueError("not found")

        with patch("utils.external.yfinance_financials.fetch_financial_statement", return_value=None):
            result = loader.fetch_incremental("HIFS", since=None)

        assert len(result) == 1
        assert result[0]["reason"] == "fdic_designee_no_sec_cik"

    def test_generic_unresolved_symbol_still_gets_cik_not_found(self) -> None:
        loader = _make_loader()
        loader._sec_client.symbol_to_cik.side_effect = ValueError("not found")

        with patch("utils.external.yfinance_financials.fetch_financial_statement", return_value=None):
            result = loader.fetch_incremental("ZZZZQ", since=None)

        assert len(result) == 1
        assert result[0]["reason"] == "cik_not_found"
