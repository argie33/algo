"""Regression test: a quarterly data_unavailable marker must survive transform(), not
silently vanish and crash the loader with "CRITICAL: No valid rows after transformation".

Found live 2026-07-28: SecLoaderBase.fetch_incremental() (loaders/helpers/sec_base.py)
returns an explicit data_unavailable marker (fiscal_year=0) for symbols with no SEC
facts at all - correct behavior for annual statements, where transform()'s dedup key is
just (symbol, fiscal_year). But for QUARTERLY statements, transform() also requires a
non-None fiscal_quarter to build its dedup key; the marker never set one, so it
silently failed the "if fiscal_quarter is None: skip" check and vanished entirely. If a
symbol's only row that run was this marker (true for foreign private issuers that file
Form 20-F/6-K instead of 10-Q, e.g. ZIM, ZTO, ZH, ZKH), transform() ended up with zero
rows and raised a hard RuntimeError - a real failure - instead of writing the clean
marker this code path exists to produce. Live-confirmed: quarterly_income_statement's
full-universe backfill hit exactly this, 767/5465 symbols "failed" this way.

Fixed via SecLoaderBase._unavailable_marker(), which adds a "fiscal_period": 0 sentinel
(the SEC-side field name field_mapping maps to the "fiscal_quarter" DB column - NOT the
literal "fiscal_quarter" key, which itself isn't in field_mapping and would vanish the
same way) whenever self.period != "annual".
"""

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader, get_income_statement_config


def _make_loader(period: str) -> ConsolidatedFinancialStatementsLoader:
    loader = ConsolidatedFinancialStatementsLoader.__new__(ConsolidatedFinancialStatementsLoader)
    config = get_income_statement_config(period)
    loader.table_name = config["table_name"]
    loader.period = period
    loader.statement_type = "income"
    loader._schema_cols = config["schema_cols"]
    loader._field_mapping = config["field_mapping"]
    return loader


class TestQuarterlyUnavailableMarkerSurvivesTransform:
    def test_quarterly_marker_from_fetch_incremental_survives_transform(self) -> None:
        loader = _make_loader("quarterly")
        marker = loader._unavailable_marker("ZIM", "no_quarterly_income_data_in_sec_edgar_reit_or_special_entity")

        transformed = loader.transform([marker])

        assert len(transformed) == 1, "the marker row must survive transform(), not vanish"
        assert transformed[0]["symbol"] == "ZIM"
        assert transformed[0]["data_unavailable"] is True
        assert transformed[0]["fiscal_quarter"] == 0

    def test_annual_marker_unaffected_no_fiscal_quarter_key(self) -> None:
        """Annual markers never needed a fiscal_quarter sentinel - confirms the fix didn't
        change annual's already-correct behavior."""
        loader = _make_loader("annual")
        marker = loader._unavailable_marker("ZIM", "cik_not_found")

        assert "fiscal_period" not in marker
        transformed = loader.transform([marker])

        assert len(transformed) == 1
        assert transformed[0]["symbol"] == "ZIM"
        assert transformed[0]["data_unavailable"] is True

    def test_quarterly_marker_missing_fiscal_period_would_vanish(self) -> None:
        """Guards the failure mode itself: a marker WITHOUT the fiscal_period sentinel
        (the pre-fix shape) must reproduce the original bug - the row silently vanishes,
        leaving transform() with zero rows, which raises the same hard RuntimeError this
        fix eliminates. Proves this test would have caught the original bug."""
        import pytest

        loader = _make_loader("quarterly")
        pre_fix_marker = {
            "symbol": "ZIM",
            "fiscal_year": 0,
            "data_unavailable": True,
            "reason": "cik_not_found",
        }

        with pytest.raises(RuntimeError, match="No valid rows after transformation"):
            loader.transform([pre_fix_marker])
