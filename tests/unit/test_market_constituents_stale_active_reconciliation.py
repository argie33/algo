"""Regression: already-`active=true` stock_symbols rows must be re-evaluated against
CURRENT should_exclude() patterns, not just newly-fetched rows.

Bug (confirmed live 2026-08-04): excluded symbols are simply omitted from the list
fetch_global() returns to the bulk-insert write path, so a symbol that was `active=true`
under an OLDER, looser pattern set stays `active=true` forever even after a later pattern
change tightens to newly cover it. Live-confirmed 59 already-active SPAC-rights symbols
(AACPR, AESPR, ...) still `active=true` a full day after the 2026-08-03 `\\brights?\\b`
pattern addition - inflating price_daily's "active universe" denominator and pinning its
completion % below the 98% mark_completed() safety threshold every single day, so the
dashboard's Data Freshness table showed price_daily as chronically FAILED for a reason
that had nothing to do with the price loader itself.

Also covers the companion pattern-gap fix: CORP_SPONSOR_PATTERN (formerly
INVESTMENT_CORP_PATTERN) widened from `\\binvestment corp\\b` to
`\\b(investment|acquisition) corp(oration)?\\b`, since "... Acquisition Corp[oration]"
turned out to be the more common SPAC-sponsor naming convention and its base
"Class A Ordinary Share(s)" equity line was never excluded by any pattern.
"""

from unittest.mock import MagicMock, patch

from loaders.load_market_constituents import MarketConstituentsLoader, should_exclude


def _make_loader():
    return MarketConstituentsLoader.__new__(MarketConstituentsLoader)


class TestAcquisitionCorpSponsorPattern:
    def test_acquisition_corp_ordinary_shares_excluded(self):
        assert should_exclude("Abony Acquisition Corp. I - Class A Ordinary Share")

    def test_acquisition_corporation_ordinary_shares_excluded(self):
        assert should_exclude("Alpex Acquisition Corporation - Class A Ordinary Shares")

    def test_acquisition_corp_units_still_excluded_by_existing_pattern(self):
        assert should_exclude("Iron Dome Acquisition I Corp. - Units")

    def test_real_operating_company_with_acquisition_in_name_not_excluded(self):
        """A real operating company's Common Stock line must stay included even if its
        legal name happens to contain 'Acquisition Corp' - the SPAC_SHARE_CLASS_PATTERN
        gate (Ordinary Shares/Rights) is what keeps this safe, same guard as the existing
        investment-corp case (AGNC/Saratoga)."""
        assert not should_exclude("Example Acquisition Corp. - Common Stock")


class TestDeactivateStaleExcludedSymbols:
    def test_active_row_matching_current_pattern_gets_deactivated(self):
        loader = _make_loader()
        with patch("loaders.load_market_constituents.DatabaseContext") as mock_db_ctx:
            mock_read_cur = MagicMock()
            mock_read_cur.fetchall.return_value = [
                ("AACPR", "Apogee Acquisition Corp - Rights"),
                ("AAPL", "Apple Inc. - Common Stock"),
            ]
            mock_write_cur = MagicMock()
            mock_db_ctx.return_value.__enter__.side_effect = [mock_read_cur, mock_write_cur]

            loader._deactivate_stale_excluded_symbols()

            mock_write_cur.execute.assert_called_once()
            sql, params = mock_write_cur.execute.call_args[0]
            assert "UPDATE stock_symbols" in sql
            assert "active = false" in sql
            assert params == (["AACPR"],)

    def test_no_stale_matches_skips_write(self):
        loader = _make_loader()
        with patch("loaders.load_market_constituents.DatabaseContext") as mock_db_ctx:
            mock_read_cur = MagicMock()
            mock_read_cur.fetchall.return_value = [("AAPL", "Apple Inc. - Common Stock")]
            mock_db_ctx.return_value.__enter__.return_value = mock_read_cur

            loader._deactivate_stale_excluded_symbols()

            # Only the read call happened - DatabaseContext("write") never entered.
            assert mock_db_ctx.call_args_list == [(("read",), {})]
