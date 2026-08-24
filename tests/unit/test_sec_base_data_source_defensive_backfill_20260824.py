"""Regression test for the 2026-08-24 real-money-readiness audit finding: live DB scan found
6,340+ real (non-data_unavailable) annual_balance_sheet/quarterly_balance_sheet rows written
with data_source=NULL as recently as 2026-08-22 - well after migration 1202's tagging fix was
believed to have closed this gap universally (see loaders/load_financial_statements.py's
_MARKER_FIELDS comment). Root cause: fetch_incremental()/_try_yfinance_fallback() tag the RAW
row dict before transform() runs, but if "data_source" doesn't survive as a literal key on a
given row through every skip/continue branch in transform()'s per-field copy loop, the key is
simply absent from the DB-bound row - and bulk_insert_manager.py's CSV writer (csv.DictWriter,
default restval='') turns a missing key into an empty string, which COPY's FORCE_NULL then
turns into a real DB NULL. transform() now defensively re-applies the same
setdefault("data_source", "sec_audited") guarantee fetch_incremental() already makes on the raw
rows, so no non-marker row can leave transform() without a source tag regardless of which
upstream branch dropped it.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


def _make_loader() -> SecEdgarStatementLoader:
    loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
    loader.table_name = "annual_balance_sheet"
    loader.period = "annual"
    loader.statement_type = "balance"
    loader._schema_cols = frozenset(
        {"symbol", "fiscal_year", "total_assets", "current_assets", "data_unavailable", "reason", "data_source"}
    )
    loader._field_mapping = {
        "total_assets": "total_assets",
        "assets_current": "current_assets",
        "data_unavailable": "data_unavailable",
        "reason": "reason",
        "data_source": "data_source",
    }
    loader._fallback_only_fields = frozenset()
    loader._reit_only_fallback_fields = frozenset()
    loader._reit_exclusive_fields = frozenset()
    loader._reit_symbols = frozenset()
    return loader


class TestDataSourceDefensiveBackfill:
    def test_row_missing_data_source_key_entirely_gets_sec_audited_default(self) -> None:
        # Simulates the live-confirmed bug shape: a real SEC-EDGAR row (SLN/UCB/SKT-style)
        # whose "data_source" key never survived into the row dict transform() builds.
        loader = _make_loader()
        row = {"symbol": "SLN", "fiscal_year": 2021, "assets_current": 116_272_022.13}

        transformed = loader.transform([row])

        assert transformed[0]["data_source"] == "sec_audited"

    def test_row_with_explicit_data_source_key_is_preserved(self) -> None:
        # The normal path (setdefault already ran upstream) must not be disturbed.
        loader = _make_loader()
        row = {
            "symbol": "AAPL",
            "fiscal_year": 2025,
            "total_assets": 350_000_000_000.0,
            "data_source": "sec_audited",
        }

        transformed = loader.transform([row])

        assert transformed[0]["data_source"] == "sec_audited"

    def test_yfinance_tagged_row_is_not_overwritten(self) -> None:
        # A yfinance-fallback row must keep its real tag, never silently relabeled sec_audited.
        loader = _make_loader()
        row = {
            "symbol": "TEST",
            "fiscal_year": 2024,
            "total_assets": 1_000_000.0,
            "data_source": "yfinance",
        }

        transformed = loader.transform([row])

        assert transformed[0]["data_source"] == "yfinance"

    def test_marker_row_gets_no_data_source_tag(self) -> None:
        # data_unavailable=True marker rows have no data to source-tag - must stay untagged.
        loader = _make_loader()
        row = {"symbol": "SHELLCO", "fiscal_year": 0, "data_unavailable": True, "reason": "cik_not_found"}

        transformed = loader.transform([row])

        assert "data_source" not in transformed[0] or transformed[0]["data_source"] is None
