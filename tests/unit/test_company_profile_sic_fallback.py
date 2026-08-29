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
        # Division 99 (SIC 9995 "Non-classifiable establishments" - a common real-world
        # code for shell/blank-check entities) has no exact entries anywhere in
        # SIC_TO_GICS - must stay unmapped, not silently guessed.
        assert all(code // 100 != 99 for code in SIC_TO_GICS)
        assert SIC_MAJOR_GROUP_FALLBACK.get(99) is None

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
            "operating",  # entity_type
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
        mock_cur.fetchone.return_value = self._mock_row(9995)  # non-classifiable establishment

        with patch("loaders.load_company_profile.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = mock_cur
            mock_db_ctx.return_value.__exit__.return_value = False
            result = loader.fetch_incremental("ZTG", None)

        assert result is not None
        assert result[0]["data_unavailable"] is True
        assert result[0]["reason"] == "sic_code_unmapped:9995"
        # WATERMARK FIX regression (2026-08-17): this dict must carry the loader's own
        # watermark_field ("updated_at") - utils/optimal_loader.py's watermark_from_rows()
        # raises ValueError on any row missing it, which live-reproduced as 1296 symbols/run
        # failing outright (never even landing their intended data_unavailable marker)
        # instead of being cleanly marked unavailable. See the two sibling tests below for
        # the other two "unavailable" record paths in this same method.
        assert "updated_at" in result[0]


class TestOperatingEntityWithBlankSicFallsBackToFinancialServices:
    """Regression test (2026-08-29, goal session: data-completeness pass over the
    analyst-coverage audit's top-market-cap outliers). Blank sic_code is ambiguous
    between real closed-end funds (never file a 10-K/20-F, entity_type='other') and
    real operating/lending companies SEC's submissions.json simply never populated a
    SIC for - live-verified universe-wide: every symbol with entity_type='operating'
    AND sic_code NULL is a Business Development Company or bank holding company
    (BBDC, MAIN, HTGC, FSK, CBC, 25 more - live SEC submissions.json fetch even shows
    Bank OZK itself returns sic="" from SEC's own API). Before this fix all 30 were
    dropped to sector="Other"/data_unavailable=True despite having complete SEC
    filings and, in several cases, an already-live stock_scores composite score.
    """

    def _mock_row(self, entity_type):
        return (
            "MAIN",  # symbol
            "Main Street Capital Corporation",  # entity_name
            None,  # sic_code - SEC's own submissions.json returns "" for this bucket
            None,  # sic_description
            None,  # shares_outstanding
            None,  # created_at
            "2026-08-29",  # updated_at
            False,  # data_unavailable
            None,  # reason
            entity_type,
        )

    def test_operating_entity_with_blank_sic_gets_financial_services(self):
        loader = CompanyProfileLoader.__new__(CompanyProfileLoader)
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = self._mock_row("operating")

        with patch("loaders.load_company_profile.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = mock_cur
            mock_db_ctx.return_value.__exit__.return_value = False
            result = loader.fetch_incremental("MAIN", None)

        assert result is not None
        assert result[0]["data_unavailable"] is False
        assert result[0]["reason"] is None
        assert result[0]["sector"] == "Financial Services"
        assert result[0]["symbol"] == "MAIN"

    def test_non_operating_entity_with_blank_sic_still_fails_closed(self):
        """A real CEF (entity_type='other') must NOT get the Financial Services
        fallback - it genuinely has no determinable sector."""
        loader = CompanyProfileLoader.__new__(CompanyProfileLoader)
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = self._mock_row("other")

        with patch("loaders.load_company_profile.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = mock_cur
            mock_db_ctx.return_value.__exit__.return_value = False
            result = loader.fetch_incremental("MAIN", None)

        assert result is not None
        assert result[0]["data_unavailable"] is True
        assert result[0]["reason"] == "no_sic_code_available"


class TestNewlyMappedDivisions:
    """Regression test (2026-08-19, "no SEC data" audit "find the holes" pass): live DB
    audit found 119 distinct sic_code_unmapped:XXXX values covering 1,176 active-universe
    symbols, across entire SIC divisions with zero SIC_TO_GICS precedent (Real Estate 65xx,
    non-depository credit/insurance agents 61xx/64xx, metal/coal mining 10xx/12xx,
    construction 15xx-17xx, apparel/furniture/toys 22xx-25xx/39xx, publishing 27xx,
    wholesale trade 50xx/51xx, hotels/recreation 70xx/79xx, professional/research services
    81xx/87xx, agriculture 0xxx). Spot-checks a representative code from each newly-added
    division resolves to a real GICS sector, not just presence in the dict.
    """

    def test_reit_maps_to_real_estate(self):
        assert SIC_TO_GICS[6798] == "Real Estate"

    def test_finance_services_maps_to_financial_services(self):
        assert SIC_TO_GICS[6199] == "Financial Services"

    def test_gold_mining_maps_to_materials(self):
        assert SIC_TO_GICS[1040] == "Materials"

    def test_coal_mining_maps_to_energy(self):
        assert SIC_TO_GICS[1220] == "Energy"

    def test_apparel_maps_to_consumer_cyclical(self):
        assert SIC_TO_GICS[2300] == "Consumer Cyclical"

    def test_publishing_maps_to_communication_services(self):
        assert SIC_TO_GICS[2711] == "Communication Services"

    def test_wholesale_trade_maps_to_industrials(self):
        assert SIC_TO_GICS[5045] == "Industrials"

    def test_commercial_biological_research_maps_to_healthcare(self):
        assert SIC_TO_GICS[8731] == "Healthcare"

    def test_agricultural_production_maps_to_consumer_defensive(self):
        assert SIC_TO_GICS[100] == "Consumer Defensive"

    def test_previously_unprecedented_division_87_now_resolves_via_new_precedent(self):
        # 8742 (management consulting) is now directly mapped; a still-unlisted code in the
        # same division (e.g. 8748, generic management services) must resolve via the
        # major-group fallback instead of failing closed, now that division 87 has real
        # precedent.
        assert 8748 not in SIC_TO_GICS
        assert SIC_MAJOR_GROUP_FALLBACK.get(87) is not None


class TestSecondRoundNewlyMappedCodes:
    """Regression test (2026-08-29, "full data" audit continuation): live DB audit found
    sic_code_unmapped:700/:7200 covering 16 active-universe symbols (AVO/BNC/BV/RYM/PFAI on
    700; HRB/SCI/CSV/RGS/WW/EVI/MRM/DLPN/UNF/XWEL/YELP on 7200) - the earlier 2026-08-19 batch's
    sample didn't happen to surface these two codes even though the fix class is identical.
    """

    def test_agricultural_services_maps_to_consumer_defensive(self):
        assert SIC_TO_GICS[700] == "Consumer Defensive"

    def test_personal_services_maps_to_consumer_cyclical(self):
        assert SIC_TO_GICS[7200] == "Consumer Cyclical"


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
            "other",  # entity_type - NOT "operating", so this must still fail closed
        )

        with patch("loaders.load_company_profile.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = mock_cur
            mock_db_ctx.return_value.__exit__.return_value = False
            result = loader.fetch_incremental("NOSIC", None)

        assert result is not None
        assert result[0]["data_unavailable"] is True
        assert result[0]["reason"] == "no_sic_code_available"
        assert "updated_at" in result[0]
