"""Regression test for the 2026-08-21 fix: CompanyInfoSECLoader never opted into
preserve_on_missing_fields, unlike load_financial_statements.py which already has this exact
guard for the identical failure mode (see utils/bulk_insert_manager.py's docstring).

primary_key=("symbol",) means every run does an ON CONFLICT DO UPDATE against the same row
per symbol. Without this guard, a single transient/point-in-time CIK-lookup miss (the SEC
ticker cache's live-documented completeness gaps, or its browse-edgar fallback endpoint being
inconsistent about a given ticker) writes an all-NULL _unavailable_record() that unconditionally
overwrites real entity_name/sic_code/shares_outstanding a symbol already had on file.

Live-confirmed: AXIA, BNZI, BRNX, FRBA, GRAF, GV, HIFS, IA all have 5-12 real
annual_income_statement rows (proving a CIK was resolved before) but got their entity_name/
sic_code wiped to NULL mid-run by exactly this path.
"""

from loaders.load_company_info_sec import CompanyInfoSECLoader


class TestPreserveOnMissingFields:
    def test_real_data_columns_are_preserved(self) -> None:
        loader = CompanyInfoSECLoader()
        preserved = loader._bulk_insert_mgr.preserve_on_missing_fields
        for field in (
            "entity_name",
            "sic_code",
            "sic_description",
            "entity_type",
            "shares_outstanding",
            "shares_outstanding_unavailable_reason",
            "has_annual_report_filing",
        ):
            assert field in preserved, (
                f"'{field}' must be preserved on a NULL re-fetch - otherwise a transient "
                "CIK-lookup miss silently wipes real, previously-loaded company data."
            )

    def test_governance_marker_columns_are_not_preserved(self) -> None:
        """data_unavailable/reason must always reflect the CURRENT run's real assessment,
        never a stale one - same carve-out as load_financial_statements.py."""
        loader = CompanyInfoSECLoader()
        preserved = loader._bulk_insert_mgr.preserve_on_missing_fields
        assert "data_unavailable" not in preserved
        assert "reason" not in preserved

    def test_unavailable_record_shape_matches_preserved_field_set(self) -> None:
        """Every field _unavailable_record() nulls out must be covered by
        preserve_on_missing_fields, or a future field added to one and not the other would
        silently reopen this exact bug."""
        loader = CompanyInfoSECLoader()
        from datetime import datetime

        from utils.infrastructure.timezone import EASTERN_TZ

        record = loader._unavailable_record("ZZZZ", datetime.now(EASTERN_TZ), "cik_not_found")[0]
        nulled_data_fields = {k for k, v in record.items() if v is None and k not in ("symbol",)}
        preserved = loader._bulk_insert_mgr.preserve_on_missing_fields
        assert nulled_data_fields <= preserved, (
            f"_unavailable_record() nulls {nulled_data_fields - preserved} but "
            "preserve_on_missing_fields doesn't cover it - real data for those columns "
            "would be silently wiped on the next unavailable run."
        )
