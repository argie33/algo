"""Regression test for the 2026-09-13 fix: _reject_implausible_shares_outstanding()'s relative
cross-check only used company_info_sec.shares_outstanding as a reference, which is NULL for
every 20-F foreign-private-issuer this session found with the ~1000x-1,000,000x
shares_outstanding scale-error pattern (VALE, PDD, WB, BMA, GGAL, CIGI, ALC, BBD and more - see
shares_outstanding_scale_error_growth_guard_fixed_20260913 in memory) - the guard was a
structural no-op for exactly the population it needed to catch. Added a second-chance
reference: the symbol's own median shares_outstanding_basic/diluted across every OTHER
fiscal year already stored in the same table, used only when company_info_sec has nothing.
"""

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


def _make_loader(statement_type: str = "income", period: str = "annual") -> ConsolidatedFinancialStatementsLoader:
    return ConsolidatedFinancialStatementsLoader(statement_type=statement_type, period=period)


def _transform(loader: ConsolidatedFinancialStatementsLoader, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    with patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "transform", side_effect=lambda r: r):
        return loader.transform(rows)


def _make_context(rows: list[tuple[Any, ...]]) -> Any:
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = rows
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False
    return mock_ctx


def _two_stage_db_context(company_info_rows: list[tuple[Any, ...]], own_history_rows: list[tuple[Any, ...]]) -> Any:
    """company_info_sec's query runs first, this table's own-history query second, and any
    later DatabaseContext() call (e.g. _fill_derived_eps's own lookup) after that - all go
    through the same patched call site, so a side_effect function keyed on call count lets
    the first two get their own canned result and everything after returns empty."""
    contexts = [_make_context(company_info_rows), _make_context(own_history_rows)]

    def _side_effect(*_args: Any, **_kwargs: Any) -> Any:
        return contexts.pop(0) if contexts else _make_context([])

    return _side_effect


class TestSharesOutstandingOwnHistoryFallback:
    def test_no_company_info_reference_falls_back_to_own_table_history(self) -> None:
        """WB-shaped: company_info_sec has nothing (real for this population), but the table
        already has 5 other plausible fiscal years for the same symbol clustered around ~220M -
        the current row's 236,407 (real value ~236,407,000, a ~1000x scale error) should be
        rejected against that median even with no company_info_sec row at all."""
        loader = _make_loader()
        rows = [
            {
                "symbol": "WBFAKE",
                "fiscal_year": 2022,
                "revenue": Decimal("2000000000"),
                "net_income": Decimal("100000000"),
                "shares_outstanding_basic": Decimal("235164"),
                "shares_outstanding_diluted": Decimal("236407"),
                "shares_outstanding_dei": None,
                "data_unavailable": False,
                "reason": None,
            }
        ]

        contexts = _two_stage_db_context(
            company_info_rows=[],
            own_history_rows=[
                ("WBFAKE", 210000000.0, 220000000.0),
                ("WBFAKE", 215000000.0, 225000000.0),
                ("WBFAKE", 225000000.0, 230000000.0),
            ],
        )

        with patch(
            "loaders.helpers.financial_statements_share_count_validation.DatabaseContext",
            side_effect=contexts,
        ):
            transformed = _transform(loader, rows)

        assert (
            {"symbol": "WBFAKE", "fiscal_year": 2022},
            "shares_outstanding_basic",
        ) in loader._explicit_null_rejections
        assert (
            {"symbol": "WBFAKE", "fiscal_year": 2022},
            "shares_outstanding_diluted",
        ) in loader._explicit_null_rejections
        assert transformed[0]["shares_outstanding_basic"] is None
        assert transformed[0]["shares_outstanding_diluted"] is None

    def test_plausible_value_with_own_history_reference_not_rejected(self) -> None:
        loader = _make_loader()
        rows = [
            {
                "symbol": "STABLEFAKE",
                "fiscal_year": 2024,
                "revenue": Decimal("500000000"),
                "net_income": Decimal("40000000"),
                "shares_outstanding_basic": 100500000.0,
                "shares_outstanding_diluted": 101000000.0,
                "shares_outstanding_dei": None,
                "data_unavailable": False,
                "reason": None,
            }
        ]

        contexts = _two_stage_db_context(
            company_info_rows=[],
            own_history_rows=[
                ("STABLEFAKE", 99000000.0, 99500000.0),
                ("STABLEFAKE", 100000000.0, 100200000.0),
            ],
        )

        with patch(
            "loaders.helpers.financial_statements_share_count_validation.DatabaseContext",
            side_effect=contexts,
        ):
            transformed = _transform(loader, rows)

        assert loader._explicit_null_rejections == []
        assert transformed[0]["shares_outstanding_basic"] == 100500000.0
        assert transformed[0]["shares_outstanding_diluted"] == 101000000.0
