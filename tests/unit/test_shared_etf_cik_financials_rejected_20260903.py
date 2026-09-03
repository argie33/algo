"""Regression test for the 2026-09-03 fix: symbols in `SHARED_ISSUER_OR_TRUST_CIK_SYMBOLS`
(every `etf_symbols` ticker whose SEC CIK is shared with another `etf_symbols` ticker - an
ETN issued under its issuing bank's own CIK, or a series within a multi-fund umbrella trust
CIK) must never be fetched/stored as if the resulting companyfacts data were that symbol's
own financials - see
[[etn_etf_trust_shared_cik_implausible_financials_found_not_fixed_20260903]] for the live
evidence (AMJB/VYLD both resolving to JPMorgan's CIK with $4.4T "total_assets", ProShares
Trust II's 16 leveraged/inverse funds sharing one CIK) and
SHARED_ISSUER_OR_TRUST_CIK_SYMBOLS' module comment for the full cross-reference.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import SHARED_ISSUER_OR_TRUST_CIK_SYMBOLS, ConsolidatedFinancialStatementsLoader


def _make_loader(statement_type: str = "balance", period: str = "annual") -> ConsolidatedFinancialStatementsLoader:
    return ConsolidatedFinancialStatementsLoader(statement_type=statement_type, period=period)


class _FakeCursor:
    def __init__(self, fetchall_results: list[list[Any]]) -> None:
        self._fetchall_results = list(fetchall_results)
        self.execute_calls: list[tuple[str, Any]] = []
        self.rowcount = 1

    def execute(self, query: str, params: Any = None) -> None:
        self.execute_calls.append((query, params))

    def fetchall(self) -> list[Any]:
        return self._fetchall_results.pop(0) if self._fetchall_results else []


def _mock_context(fetchall_results: list[list[Any]]) -> tuple[MagicMock, _FakeCursor]:
    fake_cur = _FakeCursor(fetchall_results)
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = fake_cur
    mock_ctx.__exit__.return_value = False
    return mock_ctx, fake_cur


class TestSharedIssuerOrTrustCikRegistry:
    def test_known_affected_symbols_are_registered(self) -> None:
        # A representative sample from each documented group, not the full ~70-symbol list.
        for sym in ("AMJB", "VYLD", "UVXY", "SVXY", "GLDI", "CPER", "USCI", "CANE", "WEAT"):
            assert sym in SHARED_ISSUER_OR_TRUST_CIK_SYMBOLS

    def test_genuinely_scored_commodity_etfs_are_not_registered(self) -> None:
        for sym in ("GLD", "SLV", "IAU", "GLDM", "AAAU", "SGOL", "PPLT", "PALL", "SIVR", "GLTR", "BNO", "OUNZ"):
            assert sym not in SHARED_ISSUER_OR_TRUST_CIK_SYMBOLS

    def test_equity_dual_class_pairs_are_not_registered(self) -> None:
        for sym in ("GOOG", "GOOGL", "BRK.A", "BRK.B"):
            assert sym not in SHARED_ISSUER_OR_TRUST_CIK_SYMBOLS


class TestFetchIncrementalRejectsSharedCikSymbols:
    def test_shared_symbol_short_circuits_without_fetching(self) -> None:
        loader = _make_loader(statement_type="balance")
        with patch.object(loader, "_reject_shared_etf_cik_data") as mock_reject:
            with patch("loaders.helpers.sec_base.SecEdgarStatementLoader.fetch_incremental") as mock_super_fetch:
                rows = loader.fetch_incremental("AMJB", None)
        mock_reject.assert_called_once_with("AMJB")
        mock_super_fetch.assert_not_called()
        assert len(rows) == 1
        assert rows[0]["data_unavailable"] is True
        assert rows[0]["reason"] == "shared_issuer_or_trust_cik_not_attributable"

    def test_non_shared_symbol_falls_through_to_normal_fetch(self) -> None:
        loader = _make_loader(statement_type="balance")
        with patch.object(loader, "_reject_shared_etf_cik_data") as mock_reject:
            with patch(
                "loaders.helpers.sec_base.SecEdgarStatementLoader.fetch_incremental",
                return_value=[{"symbol": "AAPL", "fiscal_year": 2024}],
            ) as mock_super_fetch:
                rows = loader.fetch_incremental("AAPL", None)
        mock_reject.assert_not_called()
        mock_super_fetch.assert_called_once()
        assert rows == [{"symbol": "AAPL", "fiscal_year": 2024}]


class TestRejectSharedEtfCikData:
    def test_queues_force_null_for_every_existing_row_and_field(self) -> None:
        loader = _make_loader(statement_type="balance")
        loader._bulk_insert_mgr.preserve_on_missing_fields = frozenset({"total_assets", "stockholders_equity"})
        mock_ctx, _ = _mock_context([[("AMJB", 2024), ("AMJB", 2023)]])
        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader._reject_shared_etf_cik_data("AMJB")
        rejected_fields = {field for _, field in loader._explicit_null_rejections}
        assert rejected_fields == {"total_assets", "stockholders_equity"}
        assert len(loader._explicit_null_rejections) == 4
        assert all(
            reason == "shared_issuer_or_trust_cik_not_attributable" for reason in loader._rejection_reasons.values()
        )

    def test_no_existing_rows_is_a_no_op(self) -> None:
        loader = _make_loader(statement_type="balance")
        mock_ctx, _ = _mock_context([[]])
        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader._reject_shared_etf_cik_data("NEWSYM")
        assert loader._explicit_null_rejections == []
