#!/usr/bin/env python3
"""Regression test: load_company_profile.py's data_unavailable fallback paths omitted the
"symbol" key from their returned dict, unlike the success path (which sets both "ticker" and
"symbol").

Live-confirmed 2026-08-23 (goal session: sector_ranking "Unknown" bucket audit): company_profile
has both a "ticker" and a "symbol" column, but every other table in this codebase (stock_scores,
value_metrics, quality_metrics, ...) joins against company_profile.symbol - the standard pattern
used almost everywhere, including algo/signals/sector_rotation.py's sector-ranking source query
(`LEFT JOIN company_profile cp ON ss.symbol = cp.symbol`). Since this loader's UPSERT never
updates "symbol" on ON CONFLICT (only sets it from the dict on the very first INSERT), any ticker
whose first-ever company_profile write happened to hit one of these three fallback branches
(no company_info_sec row at all, no SIC code, or an unmapped SIC code) got symbol=NULL
permanently - no later run could ever fix it, even after transitioning to the success path.
Live-confirmed 4 real active symbols (QVC, RCBC, BNC, SAR) stuck with ticker set but symbol NULL,
silently excluded from every symbol-keyed join against this table - including landing in
sector_ranking's "Unknown" sector bucket instead of being properly excluded-with-reason or
correctly classified.
"""

from unittest.mock import MagicMock, patch

from loaders.load_company_profile import CompanyProfileLoader


class TestDataUnavailablePathsSetSymbolKey:
    def test_no_company_info_sec_row_sets_symbol_key(self):
        loader = CompanyProfileLoader.__new__(CompanyProfileLoader)
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = None  # row is None -> "No data in company_info_sec"

        with patch("loaders.load_company_profile.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = mock_cur
            mock_db_ctx.return_value.__exit__.return_value = False
            result = loader.fetch_incremental("QVC", None)

        assert result is not None
        assert result[0]["data_unavailable"] is True
        assert result[0]["ticker"] == "QVC"
        assert result[0]["symbol"] == "QVC"

    def test_no_sic_code_available_sets_symbol_key(self):
        loader = CompanyProfileLoader.__new__(CompanyProfileLoader)
        mock_cur = MagicMock()
        # ADDED 2026-09-07: fetch_incremental now issues a second query (yfinance_snapshot
        # override lookup) before unpacking the company_info_sec row - side_effect gives each
        # cur.execute()/fetchone() pair its own return value in call order, matching the real
        # two-query flow. None for the yfinance lookup means "no override available", which is
        # what this fixture intends to test (SIC-only fail-closed path).
        mock_cur.fetchone.side_effect = [
            (
                "RCBC",  # symbol
                None,  # entity_name
                None,  # sic_code - missing, triggers this branch
                None,  # sic_description
                None,  # shares_outstanding
                None,  # created_at
                "2026-08-23",  # updated_at
                False,  # data_unavailable
                None,  # reason
                "other",  # entity_type - NOT "operating", so this must still fail closed
            ),
            None,  # yfinance_snapshot lookup: no override available
        ]

        with patch("loaders.load_company_profile.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = mock_cur
            mock_db_ctx.return_value.__exit__.return_value = False
            result = loader.fetch_incremental("RCBC", None)

        assert result is not None
        assert result[0]["data_unavailable"] is True
        assert result[0]["reason"] == "no_sic_code_available"
        assert result[0]["ticker"] == "RCBC"
        assert result[0]["symbol"] == "RCBC"

    def test_sic_code_unmapped_sets_symbol_key(self):
        # UPDATED 2026-08-29: this test originally used BNC's real SIC code 700
        # ("Agricultural Services") as its unmapped-code fixture - see the goal session's
        # own [[company_info_sec_cik_not_found_small_banks_checked_20260829]]-adjacent
        # fix, `loaders/load_company_profile.py`'s SIC_TO_GICS now maps 700 -> "Consumer
        # Defensive", so BNC is no longer a real example of this path. Swapped to 9995
        # ("Non-classifiable establishments" - SIC's own generic catch-all for shell/
        # blank-check entities, with zero real-industry meaning to map), the same
        # permanently-unmapped code test_company_profile_sic_fallback.py's own
        # test_never_invents_a_sector_for_a_division_with_zero_precedent already asserts
        # stays unmapped - this test only cares about the symbol-key bug, not the
        # specific code, so any genuinely-unmapped code preserves its intent.
        loader = CompanyProfileLoader.__new__(CompanyProfileLoader)
        mock_cur = MagicMock()
        # See test_no_sic_code_available_sets_symbol_key's comment above on why this is now
        # side_effect: fetch_incremental's second query (yfinance override lookup) must
        # return None here too, so this stays a genuine no-override unmapped-code case.
        mock_cur.fetchone.side_effect = [
            (
                "BNC",  # symbol
                "CEA Industries Inc.",  # entity_name
                9995,  # sic_code - non-classifiable establishment, permanently unmapped
                "Non-classifiable Establishments",  # sic_description
                None,  # shares_outstanding
                None,  # created_at
                "2026-08-23",  # updated_at
                False,  # data_unavailable
                None,  # reason
                "operating",  # entity_type - irrelevant to this branch (sic_code is present)
            ),
            None,  # yfinance_snapshot lookup: no override available
        ]

        with patch("loaders.load_company_profile.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = mock_cur
            mock_db_ctx.return_value.__exit__.return_value = False
            result = loader.fetch_incremental("BNC", None)

        assert result is not None
        assert result[0]["data_unavailable"] is True
        assert result[0]["reason"] == "sic_code_unmapped:9995"
        assert result[0]["ticker"] == "BNC"
        assert result[0]["symbol"] == "BNC"
