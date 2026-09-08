#!/usr/bin/env python3
"""Regression test: company_profile.sector prefers yfinance_snapshot's real GICS-based
classification over the SIC-derived approximation whenever it's available.

Live-verified 2026-09-07 (goal session: "top scores by sector" audit): SIC's 4-digit
granularity is too coarse to reconstruct GICS at scale - a live scan of every active
symbol with both a SIC-derived sector and a real yfinance sector found 579 disagreements
after normalizing yfinance's "Basic Materials" naming to this codebase's "Materials".
GOOG/GOOGL/META (SIC 7370, a catch-all shared with generic enterprise software) were
sitting in "Technology" under the SIC-only path, when GICS's own 2018 sector realignment
moved them into "Communication Services" - a distinction no SIC code can express. CSCO
(SIC 3576) was similarly misfiled into "Industrials" by a narrow division-35 fallback
vote. yfinance_snapshot.sector carries Yahoo's own classification (built on the same GICS
taxonomy S&P uses for the SPDR sector ETFs) for ~2,466 of 5,143 active symbols and is used
as an override whenever present; SIC derivation remains the only source for the rest.
"""

from unittest.mock import MagicMock, patch

from loaders.load_company_profile import CompanyProfileLoader


class TestYfinanceSectorOverride:
    def _mock_row(self, symbol, sic_code, sic_description="Services-Computer Programming, Data Processing, Etc."):
        return (
            symbol,
            f"{symbol} Inc.",
            sic_code,
            sic_description,
            None,  # shares_outstanding
            None,  # created_at
            "2026-09-07",  # updated_at
            False,  # data_unavailable
            None,  # reason
            "operating",  # entity_type
        )

    def test_yfinance_sector_overrides_sic_derived_technology_for_goog(self):
        """GOOG's SIC code (7370) resolves to "Technology" via the division-73 fallback,
        but yfinance_snapshot correctly carries "Communication Services" - the real
        classification must win."""
        loader = CompanyProfileLoader.__new__(CompanyProfileLoader)
        mock_cur = MagicMock()
        mock_cur.fetchone.side_effect = [
            self._mock_row("GOOG", 7370),
            ("Communication Services",),  # yfinance_snapshot.sector
        ]

        with patch("loaders.load_company_profile.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = mock_cur
            mock_db_ctx.return_value.__exit__.return_value = False
            result = loader.fetch_incremental("GOOG", None)

        assert result is not None
        assert result[0]["sector"] == "Communication Services"
        assert result[0]["data_unavailable"] is False

    def test_no_yfinance_row_falls_back_to_sic_derived_sector(self):
        """When yfinance_snapshot has no row (or data_unavailable/sector NULL - excluded
        by the query's own WHERE clause), the SIC-derived sector is used unchanged."""
        loader = CompanyProfileLoader.__new__(CompanyProfileLoader)
        mock_cur = MagicMock()
        mock_cur.fetchone.side_effect = [
            self._mock_row("OBSCURESYM", 7370),
            None,  # no yfinance_snapshot row
        ]

        with patch("loaders.load_company_profile.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = mock_cur
            mock_db_ctx.return_value.__exit__.return_value = False
            result = loader.fetch_incremental("OBSCURESYM", None)

        assert result is not None
        assert result[0]["sector"] == "Technology"  # division-73 fallback, unchanged

    def test_yfinance_basic_materials_normalized_to_materials(self):
        """Yahoo's own vocabulary calls this sector "Basic Materials" where this codebase
        (SIC_TO_GICS, hardcoded DEFENSIVE/CYCLICAL sector lists, dashboard filters) says
        "Materials" - the override must normalize it, not introduce a second spelling."""
        loader = CompanyProfileLoader.__new__(CompanyProfileLoader)
        mock_cur = MagicMock()
        mock_cur.fetchone.side_effect = [
            self._mock_row("AA", 3334, "Primary Production of Aluminum"),
            ("Basic Materials",),  # yfinance_snapshot.sector - raw Yahoo spelling
        ]

        with patch("loaders.load_company_profile.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = mock_cur
            mock_db_ctx.return_value.__exit__.return_value = False
            result = loader.fetch_incremental("AA", None)

        assert result is not None
        assert result[0]["sector"] == "Materials"  # normalized, not "Basic Materials"

    def test_yfinance_sector_rescues_symbol_with_no_sic_code(self):
        """A symbol with no sic_code at all (and not a BDC/bank-holding-co) would
        otherwise be marked data_unavailable - if yfinance has a real sector, use it
        instead of losing the symbol from sector-relative scoring entirely."""
        loader = CompanyProfileLoader.__new__(CompanyProfileLoader)
        mock_cur = MagicMock()
        mock_cur.fetchone.side_effect = [
            (
                "NOSIC2",
                "No SIC Corp 2",
                None,  # sic_code
                None,  # sic_description
                None,
                None,
                "2026-09-07",
                False,
                None,
                "other",  # not "operating" - would otherwise fail closed
            ),
            ("Technology",),  # yfinance_snapshot.sector
        ]

        with patch("loaders.load_company_profile.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = mock_cur
            mock_db_ctx.return_value.__exit__.return_value = False
            result = loader.fetch_incremental("NOSIC2", None)

        assert result is not None
        assert result[0]["data_unavailable"] is False
        assert result[0]["sector"] == "Technology"
