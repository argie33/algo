"""Regression test (2026-09-06, goal: "SEC/XBRL missing data to zero" sweep): a foreign
private issuer that tags its required statement concepts only under an unsupported
(non-major, non-USD) currency - e.g. GGAL/BBAR/BSAC/SUPV/TEO/TKC/TGS/TV, real Argentine/
regional banks/telecoms/utilities filing ifrs-full "Assets" only under unit="ARS" - was
falling to the generic "incomplete_sec_filing_{type}" reason instead of the specific
"unsupported_currency_no_fx_rate" reason (both are "Missing SEC/XBRL data" in
coverage_category_rules.py, same as this reason's post_run()-path sibling
fpi_currency_data_rejected - a diagnostic-specificity fix, not a recategorization).
_aggregate_concepts already correctly skips a non-major-currency fact (no reliable FX rate
to safely convert a hyperinflationary filer), but the currency a raw fact was tagged under
isn't persisted anywhere once _aggregate_concepts discards it, so
ConsolidatedFinancialStatementsLoader.transform() couldn't previously distinguish this from
a genuinely incomplete/broken filing.

Companion to test_financial_statements_transient_refetch_gap_not_downgraded_20260820.py,
whose test_new_row_with_no_prior_data_still_marked_unavailable case (a non-FPI symbol)
must keep the generic reason unchanged - covered here too as a control.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


def _make_loader(statement_type: str = "balance") -> ConsolidatedFinancialStatementsLoader:
    return ConsolidatedFinancialStatementsLoader(statement_type=statement_type, period="annual")


def _mock_db_context(fpi_symbols: list[tuple[str]]) -> MagicMock:
    """Single mock DatabaseContext reused for both the already_available guard query (empty
    existing rows - these tests are all "no prior DB row" cases) and the new FPI-symbol
    lookup query - transform() issues both against the same patched DatabaseContext, and
    fetchall() is called fresh (LIFO order doesn't matter here since it's re-queried, not
    consumed via a stateful iterator) for each `with DatabaseContext(...) as cur:` block, so
    a single static return value serves the already_available block's real needs (empty) and
    the FPI-lookup block's real needs (the fpi_symbols this test wants) simultaneously - the
    already_available block CAN tolerate fpi_symbols-shaped rows since none of these tests'
    rows have real required-metric values to match against, and the FPI-lookup block CAN
    tolerate an always-empty list from a non-FPI test since `fpi_symbols` then stays empty,
    exactly what's wanted.
    """
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = fpi_symbols
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False
    return mock_ctx


class TestFpiUnsupportedCurrencyReason:
    def test_fpi_with_only_rejected_currency_fact_gets_specific_reason(self) -> None:
        loader = _make_loader("balance")
        rows: list[dict[str, Any]] = [
            {
                "symbol": "GGAL",
                "fiscal_year": 2025,
                "total_assets": None,
                "stockholders_equity": None,
                "data_unavailable": False,
                "reason": None,
            }
        ]
        fake_facts = {
            "facts": {
                "ifrs-full": {
                    "Assets": {"units": {"ARS": [{"val": 32517979372000, "fy": 2025}]}},
                },
            }
        }
        fake_client = MagicMock()
        fake_client.symbol_to_cik.return_value = "0001114700"
        fake_client.get_company_facts.return_value = fake_facts

        with (
            patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "transform", side_effect=lambda r: r),
            patch(
                "loaders.load_financial_statements.DatabaseContext",
                return_value=_mock_db_context([("GGAL",)]),
            ),
        ):
            loader._sec_client = fake_client
            result = loader.transform(rows)

        assert result[0]["data_unavailable"] is True
        assert result[0]["reason"] == "unsupported_currency_no_fx_rate"

    def test_fpi_with_real_usd_fact_elsewhere_keeps_generic_reason(self) -> None:
        """A required field is still None this run (e.g. a transient extraction gap), but the
        filer's company facts DO carry a real USD value for the concept somewhere - not a
        currency-support gap, so the generic reason must stay."""
        loader = _make_loader("balance")
        rows: list[dict[str, Any]] = [
            {
                "symbol": "SOMEFPI",
                "fiscal_year": 2025,
                "total_assets": None,
                "stockholders_equity": None,
                "data_unavailable": False,
                "reason": None,
            }
        ]
        fake_facts = {
            "facts": {
                "us-gaap": {
                    "Assets": {"units": {"USD": [{"val": 500_000_000, "fy": 2024}]}},
                },
            }
        }
        fake_client = MagicMock()
        fake_client.symbol_to_cik.return_value = "0001111111"
        fake_client.get_company_facts.return_value = fake_facts

        with (
            patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "transform", side_effect=lambda r: r),
            patch(
                "loaders.load_financial_statements.DatabaseContext",
                return_value=_mock_db_context([("SOMEFPI",)]),
            ),
        ):
            loader._sec_client = fake_client
            result = loader.transform(rows)

        assert result[0]["data_unavailable"] is True
        assert result[0]["reason"] == "incomplete_sec_filing_balance"

    def test_non_fpi_symbol_never_triggers_currency_check(self) -> None:
        """Domestic filer (not in the FPI lookup result) - the currency check must not even
        run (no get_company_facts call), keeping the generic reason exactly as before this
        fix for the vastly more common case."""
        loader = _make_loader("balance")
        rows: list[dict[str, Any]] = [
            {
                "symbol": "NEWCO",
                "fiscal_year": 2026,
                "total_assets": None,
                "stockholders_equity": None,
                "data_unavailable": False,
                "reason": None,
            }
        ]
        fake_client = MagicMock()

        with (
            patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "transform", side_effect=lambda r: r),
            patch(
                "loaders.load_financial_statements.DatabaseContext",
                return_value=_mock_db_context([]),
            ),
        ):
            loader._sec_client = fake_client
            result = loader.transform(rows)

        fake_client.get_company_facts.assert_not_called()
        assert result[0]["data_unavailable"] is True
        assert result[0]["reason"] == "incomplete_sec_filing_balance"
