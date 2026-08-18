#!/usr/bin/env python3
"""Regression tests for loaders/load_company_profile.py's SIC-major-group fallback.

Live-verified 2026-07-27: running CompanyProfileLoader against the full local universe
(5471 symbols in company_info_sec) failed closed on sic_code_unmapped for 58.7%
(3213/5471) of them. SIC_TO_GICS's own comments claim several entries are "broad"
(e.g. "3500: Industrials # Machinery except electrical (broad)"), but the dict only
ever matched the exact 4-digit code - a code one digit off in the same division (e.g.
3560, sitting right next to the mapped 3500/3510/3523/3531/3532/3537/3550) failed
closed even though every other code in that division already resolves to the same
sector. SIC_MAJOR_GROUP_FALLBACK fixes this by deriving a same-division (code // 100)
fallback via majority vote over SIC_TO_GICS's own existing entries - live re-run after
the fix: unmapped rate fell to 30.2% (1650/5471), covering real symbols like
ZBRA (3560), ZM/ZS (7370/7371), ZTO (4210) without inventing any new sector judgment
call divisions have zero precedent for stay correctly unmapped.
"""

from unittest.mock import MagicMock, patch

from loaders.load_company_profile import SIC_MAJOR_GROUP_FALLBACK, SIC_TO_GICS, CompanyProfileLoader


class TestMajorGroupFallbackDerivation:
    def test_derives_industrials_for_division_35_from_existing_precedent(self):
        # SIC_TO_GICS has 7 exact entries in the 3500-3599 division (3500/3510/3523/3531/
        # 3532/3537/3550), all Industrials - 3560 (Zebra Technologies' real SIC code) is
        # not one of them but sits in the same division.
        assert SIC_MAJOR_GROUP_FALLBACK.get(35) == "Industrials"
        assert 3560 not in SIC_TO_GICS

    def test_derives_technology_for_division_73_from_existing_precedent(self):
        # 7372-7379 are all mapped Technology; 7370/7371 (Zoom, Zscaler's real SIC codes)
        # are not individually listed but share the division.
        assert SIC_MAJOR_GROUP_FALLBACK.get(73) == "Technology"
        assert 7370 not in SIC_TO_GICS
        assert 7371 not in SIC_TO_GICS

    def test_never_invents_a_sector_for_a_division_with_zero_precedent(self):
        # Division 87 (engineering/management services, e.g. SIC 8742) has no exact
        # entries anywhere in SIC_TO_GICS - must stay unmapped, not silently guessed.
        assert all(code // 100 != 87 for code in SIC_TO_GICS)
        assert SIC_MAJOR_GROUP_FALLBACK.get(87) is None

    def test_every_fallback_value_is_a_real_sector_already_present_in_sic_to_gics(self):
        real_sectors = set(SIC_TO_GICS.values())
        for sector in SIC_MAJOR_GROUP_FALLBACK.values():
            assert sector in real_sectors


class TestFetchIncrementalUsesFallback:
    def _mock_row(self, sic_code):
        return (
            "ZBRA",  # symbol
            "Zebra Technologies Corp",  # entity_name
            sic_code,  # sic_code
            "Special Industry Machinery",  # sic_description
            None,  # shares_outstanding
            None,  # created_at
            "2026-07-27",  # updated_at
            False,  # data_unavailable
            None,  # reason
        )

    def test_unmapped_code_in_precedented_division_resolves_via_fallback(self):
        loader = CompanyProfileLoader.__new__(CompanyProfileLoader)
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = self._mock_row(3560)

        with patch("loaders.load_company_profile.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = mock_cur
            mock_db_ctx.return_value.__exit__.return_value = False
            result = loader.fetch_incremental("ZBRA", None)

        assert result is not None
        assert result[0]["data_unavailable"] is False
        assert result[0]["sector"] == "Industrials"

    def test_unmapped_code_in_unprecedented_division_still_fails_closed(self):
        loader = CompanyProfileLoader.__new__(CompanyProfileLoader)
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = self._mock_row(8742)  # management consulting

        with patch("loaders.load_company_profile.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = mock_cur
            mock_db_ctx.return_value.__exit__.return_value = False
            result = loader.fetch_incremental("ZTG", None)

        assert result is not None
        assert result[0]["data_unavailable"] is True
        assert result[0]["reason"] == "sic_code_unmapped:8742"
        # WATERMARK FIX regression (2026-08-17): this dict must carry the loader's own
        # watermark_field ("updated_at") - utils/optimal_loader.py's watermark_from_rows()
        # raises ValueError on any row missing it, which live-reproduced as 1296 symbols/run
        # failing outright (never even landing their intended data_unavailable marker)
        # instead of being cleanly marked unavailable. See the two sibling tests below for
        # the other two "unavailable" record paths in this same method.
        assert "updated_at" in result[0]


class TestUnavailableRecordsCarryWatermarkField:
    """Every data_unavailable early-return in fetch_incremental must include this loader's
    watermark_field ("updated_at") - see WATERMARK FIX regression comment above."""

    def test_no_row_in_company_info_sec_carries_updated_at(self):
        loader = CompanyProfileLoader.__new__(CompanyProfileLoader)
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = None

        with patch("loaders.load_company_profile.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = mock_cur
            mock_db_ctx.return_value.__exit__.return_value = False
            result = loader.fetch_incremental("NOPROFILE", None)

        assert result is not None
        assert result[0]["data_unavailable"] is True
        assert "updated_at" in result[0]
        assert result[0]["updated_at"] is not None

    def test_missing_sic_code_carries_updated_at(self):
        loader = CompanyProfileLoader.__new__(CompanyProfileLoader)
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (
            "NOSIC",  # symbol
            "No SIC Corp",  # entity_name
            None,  # sic_code
            None,  # sic_description
            None,  # shares_outstanding
            None,  # created_at
            "2026-07-27",  # updated_at
            False,  # data_unavailable
            None,  # reason
        )

        with patch("loaders.load_company_profile.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = mock_cur
            mock_db_ctx.return_value.__exit__.return_value = False
            result = loader.fetch_incremental("NOSIC", None)

        assert result is not None
        assert result[0]["data_unavailable"] is True
        assert result[0]["reason"] == "no_sic_code_available"
        assert "updated_at" in result[0]
