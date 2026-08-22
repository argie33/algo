"""Regression test for the 2026-08-22 fix (goal session - "BRK.B and those types" follow-up):
the 2026-08-21 ambiguity guard (test_company_info_sec_dual_class_shares_ambiguity_guard.py)
correctly stopped guessing a dual-class filer's shares_outstanding via max(), but left every
dot-suffixed ticker (BRK.A, BRK.B, LEN.B, ...) permanently NULL even when the filing text
unambiguously identifies each class's real share count.

Live-verified against real SEC inline XBRL (Berkshire Hathaway CIK 1067983's and Lennar's
CIK 920760's actual, current 10-Q filings): each <ix:nonFraction> shares-outstanding fact has
a contextRef pointing at an <xbrli:context> whose <xbrldi:explicitMember
dimension="us-gaap:StatementClassOfStockAxis"> names the exact class
(us-gaap:CommonClassAMember / us-gaap:CommonClassBMember) - this is the standard US-GAAP
taxonomy convention, not a per-filer guess. _fetch_shares_outstanding_from_filing_text() now
tries this dimensional resolution first; only falls through to the original ambiguous-reject
guard when it can't determine an unambiguous single match.
"""

from unittest.mock import MagicMock, patch

from loaders.load_company_info_sec import CompanyInfoSECLoader

# Real (structure-preserving, values are the live-verified real ones) shape of Berkshire's
# 10-Q inline XBRL for the two EntityCommonStockSharesOutstanding facts plus their contexts.
_BRK_FILING_TEXT = (
    '<ix:nonFraction id="f-1" contextRef="c-classA" name="dei:EntityCommonStockSharesOutstanding" '
    'unitRef="shares" decimals="INF">488,450</ix:nonFraction>'
    '<ix:nonFraction id="f-2" contextRef="c-classB" name="dei:EntityCommonStockSharesOutstanding" '
    'unitRef="shares" decimals="INF">1,408,035,161</ix:nonFraction>'
    '<xbrli:context id="c-classA"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">'
    "0001067983</xbrli:identifier><xbrli:segment><xbrldi:explicitMember "
    'dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassAMember</xbrldi:explicitMember>'
    "</xbrli:segment></xbrli:entity><xbrli:period><xbrli:instant>2026-07-29</xbrli:instant>"
    "</xbrli:period></xbrli:context>"
    '<xbrli:context id="c-classB"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">'
    "0001067983</xbrli:identifier><xbrli:segment><xbrldi:explicitMember "
    'dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassBMember</xbrldi:explicitMember>'
    "</xbrli:segment></xbrli:entity><xbrli:period><xbrli:instant>2026-07-29</xbrli:instant>"
    "</xbrli:period></xbrli:context>"
)


def _loader() -> CompanyInfoSECLoader:
    loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
    loader.sec_client = MagicMock()
    return loader


def _submissions_with_10k(accession: str = "0001067983-26-000018", tickers: list | None = None) -> dict:
    d: dict = {"filings": {"recent": {"form": ["10-K"], "accessionNumber": [accession]}}}
    if tickers is not None:
        d["tickers"] = tickers
    return d


class TestDimensionalClassResolution:
    def test_brk_a_resolves_to_its_own_class_a_value(self):
        loader = _loader()
        loader.sec_client.get_filing_plaintext.return_value = _BRK_FILING_TEXT

        result = loader._fetch_shares_outstanding_from_filing_text("BRK.A", "1067983", _submissions_with_10k())

        assert result == 488_450

    def test_brk_b_resolves_to_its_own_class_b_value_not_its_siblings(self):
        """The exact bug this whole fix chain started from: BRK.B must get its OWN real
        ~1.4B share count, not BRK.A's ~488K (the $1.03 QUADRILLION market_cap incident)."""
        loader = _loader()
        loader.sec_client.get_filing_plaintext.return_value = _BRK_FILING_TEXT

        result = loader._fetch_shares_outstanding_from_filing_text("BRK.B", "1067983", _submissions_with_10k())

        assert result == 1_408_035_161

    def test_context_without_class_dimension_falls_through_to_ambiguous_reject(self):
        """A context that exists but carries no ClassOfStockAxis member (e.g. reused from an
        unrelated fact) must not be treated as a match - falls through to the original,
        still-correct reject-on-ambiguity behavior."""
        loader = _loader()
        loader.sec_client.get_filing_plaintext.return_value = (
            '<ix:nonFraction contextRef="c-1" name="dei:EntityCommonStockSharesOutstanding">'
            "601,935</ix:nonFraction>"
            '<ix:nonFraction contextRef="c-2" name="dei:EntityCommonStockSharesOutstanding">'
            "1,389,605,139</ix:nonFraction>"
            '<xbrli:context id="c-1"><xbrli:entity><xbrli:identifier>0001067983</xbrli:identifier>'
            "</xbrli:entity></xbrli:context>"
            '<xbrli:context id="c-2"><xbrli:entity><xbrli:identifier>0001067983</xbrli:identifier>'
            "</xbrli:entity></xbrli:context>"
        )

        result = loader._fetch_shares_outstanding_from_filing_text("BRK.A", "1067983", _submissions_with_10k())

        assert result is None

    def test_bare_ticker_resolves_via_explicit_class_text_in_security_name(self):
        """Lennar-shaped fixture: LEN is bare (no dot) but stock_symbols.security_name
        literally says "...Class A Common Stock" - a real, live-confirmed exception to the
        usual bare-ticker-has-no-signal case, trusted only because the text is explicit."""
        loader = _loader()
        loader.sec_client.get_filing_plaintext.return_value = (
            '<ix:nonFraction contextRef="c-a" name="dei:EntityCommonStockSharesOutstanding">'
            "210,506,003</ix:nonFraction>"
            '<ix:nonFraction contextRef="c-b" name="dei:EntityCommonStockSharesOutstanding">'
            "30,389,139</ix:nonFraction>"
            '<xbrli:context id="c-a"><xbrli:segment><xbrldi:explicitMember '
            'dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassAMember'
            "</xbrldi:explicitMember></xbrli:segment></xbrli:context>"
            '<xbrli:context id="c-b"><xbrli:segment><xbrldi:explicitMember '
            'dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassBMember'
            "</xbrldi:explicitMember></xbrli:segment></xbrli:context>"
        )

        with patch("loaders.load_company_info_sec.DatabaseContext") as mock_db_ctx:
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = ("Lennar Corporation Class A Common Stock",)
            mock_db_ctx.return_value.__enter__.return_value = mock_cur

            result = loader._fetch_shares_outstanding_from_filing_text("LEN", "920760", _submissions_with_10k())

        assert result == 210_506_003

    def test_bare_ticker_with_no_class_text_in_security_name_stays_unresolved(self):
        """Real, live-confirmed case (WSO/AGM/GTN/HVT-shaped): security_name is plain
        "...Common Stock" with no class wording - must NOT guess, stays None same as before
        this fix existed."""
        loader = _loader()
        loader.sec_client.get_filing_plaintext.return_value = (
            '<ix:nonFraction contextRef="c-a" name="dei:EntityCommonStockSharesOutstanding">'
            "601,935</ix:nonFraction>"
            '<ix:nonFraction contextRef="c-b" name="dei:EntityCommonStockSharesOutstanding">'
            "1,389,605,139</ix:nonFraction>"
            '<xbrli:context id="c-a"><xbrli:segment><xbrldi:explicitMember '
            'dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassAMember'
            "</xbrldi:explicitMember></xbrli:segment></xbrli:context>"
            '<xbrli:context id="c-b"><xbrli:segment><xbrldi:explicitMember '
            'dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassBMember'
            "</xbrldi:explicitMember></xbrli:segment></xbrli:context>"
        )

        with patch("loaders.load_company_info_sec.DatabaseContext") as mock_db_ctx:
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = ("Watsco, Inc. Common Stock",)
            mock_db_ctx.return_value.__enter__.return_value = mock_cur

            result = loader._fetch_shares_outstanding_from_filing_text(
                "WSO", "469759", _submissions_with_10k(tickers=["WSO", "WSO-B"])
            )

        assert result is None


class TestTargetClassLetter:
    def test_dot_suffix_resolves_directly_without_db_lookup(self):
        with patch("loaders.load_company_info_sec.DatabaseContext") as mock_db_ctx:
            assert CompanyInfoSECLoader._target_class_letter("BRK.B") == "B"
            mock_db_ctx.assert_not_called()

    def test_multi_letter_suffix_is_not_a_class_letter(self):
        """Defensive: something like a ".R" (rights) suffix isn't a single-letter class -
        must not be misread as a class letter."""
        assert CompanyInfoSECLoader._target_class_letter("XYZ.WS") is None
