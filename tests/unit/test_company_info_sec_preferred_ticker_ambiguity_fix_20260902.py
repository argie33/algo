"""Regression test for the 2026-09-02 fix (goal session: SEC/XBRL missing-data sweep):
_fetch_shares_outstanding_from_filing_text's multi_ticker_cik ambiguity guard was counting
every registered ticker on a CIK, including preferred-stock series (BASE-P<letter>, e.g.
F-PB/F-PC/F-PD, AMH-PG/PH) - these never carry their own dei:EntityCommonStockSharesOutstanding
fact competing with the common ticker's, so their presence falsely triggered "cannot determine
which class" for real, unambiguous common-stock filers.

Live-verified against Ford's (CIK 37996) and American Homes 4 Rent's (CIK 1562401) actual,
current 10-K inline XBRL and submissions.json ticker lists: both have exactly one publicly
traded common class in the filing text (a much smaller non-traded sibling class correctly
loses to the existing "take the max" logic once the false ambiguity signal is removed).
"""

from unittest.mock import MagicMock

from loaders.load_company_info_sec import CompanyInfoSECLoader

# Real (structure-preserving) shape of Ford's 10-K inline XBRL: common stock (traded, ticker F)
# vs the non-traded Class B (Ford family, no ticker of its own).
_FORD_FILING_TEXT = (
    '<ix:nonFraction unitRef="shares" contextRef="c-7" decimals="0" '
    'name="dei:EntityCommonStockSharesOutstanding" id="f-39">3,918,623,149</ix:nonFraction>'
    '<ix:nonFraction unitRef="shares" contextRef="c-8" decimals="0" '
    'name="dei:EntityCommonStockSharesOutstanding" id="f-40">70,852,076</ix:nonFraction>'
)

_AMH_FILING_TEXT = (
    '<ix:nonFraction unitRef="shares" contextRef="c-7" decimals="INF" '
    'name="dei:EntityCommonStockSharesOutstanding" id="f-52">363,141,211</ix:nonFraction>'
    '<ix:nonFraction unitRef="shares" contextRef="c-8" decimals="INF" '
    'name="dei:EntityCommonStockSharesOutstanding" id="f-53">635,075</ix:nonFraction>'
)


def _loader() -> CompanyInfoSECLoader:
    loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
    loader.sec_client = MagicMock()
    return loader


def _submissions_with_10k(accession: str, tickers: list) -> dict:
    return {
        "tickers": tickers,
        "filings": {"recent": {"form": ["10-K"], "accessionNumber": [accession], "filingDate": ["2026-02-11"]}},
    }


class TestPreferredTickerAmbiguityFix:
    def test_ford_resolves_despite_three_preferred_series_tickers(self):
        loader = _loader()
        loader.sec_client.get_filing_plaintext.return_value = _FORD_FILING_TEXT

        result = loader._fetch_shares_outstanding_from_filing_text(
            "F", "37996", _submissions_with_10k("0000037996-26-000015", ["F", "F-PB", "F-PC", "F-PD"])
        )

        assert result == 3_918_623_149

    def test_amh_resolves_despite_two_preferred_series_tickers(self):
        loader = _loader()
        loader.sec_client.get_filing_plaintext.return_value = _AMH_FILING_TEXT

        result = loader._fetch_shares_outstanding_from_filing_text(
            "AMH", "1562401", _submissions_with_10k("0001562401-26-000010", ["AMH", "AMH-PG", "AMH-PH"])
        )

        assert result == 363_141_211

    def test_genuine_dual_common_class_ambiguity_still_rejected(self):
        """A non-preferred sibling ticker (WSO-B shaped, real second common class) must still
        block the guess - only the preferred-suffix pattern is excluded from the count."""
        loader = _loader()
        loader.sec_client.get_filing_plaintext.return_value = _FORD_FILING_TEXT

        result = loader._fetch_shares_outstanding_from_filing_text(
            "F", "37996", _submissions_with_10k("0000037996-26-000015", ["F", "F-B"])
        )

        assert result is None

    def test_preferred_suffix_regex_does_not_match_lettered_common_class_tickers(self):
        """Defensive: BRK-B/HEI-A/GTN-A must not be mistaken for preferred-stock tickers -
        only the BASE-P<letter> convention is excluded."""
        assert not CompanyInfoSECLoader._PREFERRED_TICKER_SUFFIX_RE.search("BRK-B")
        assert not CompanyInfoSECLoader._PREFERRED_TICKER_SUFFIX_RE.search("HEI-A")
        assert not CompanyInfoSECLoader._PREFERRED_TICKER_SUFFIX_RE.search("GTN-A")
        assert CompanyInfoSECLoader._PREFERRED_TICKER_SUFFIX_RE.search("F-PB")
        assert CompanyInfoSECLoader._PREFERRED_TICKER_SUFFIX_RE.search("AGM-PD")
