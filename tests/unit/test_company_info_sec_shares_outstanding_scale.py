"""Regression test for load_company_info_sec.py's inline-XBRL shares-outstanding fallback.

FIXED 2026-08-18 (goal: "no SEC data" loader audit): the fallback regex extracted the raw
numeric text of a dei:EntityCommonStockSharesOutstanding inline-XBRL fact but ignored the
scale= attribute, which means "value is expressed in 10^scale units". Live-confirmed on
Alphabet's real 10-K: this cover-page fact is tagged scale="6" (millions) with raw text
"5,822" (i.e. 5,822,000,000 real shares), "837", and "5,438" for its three share classes -
all three failed the >100,000 plausibility filter unscaled and were silently discarded,
leaving shares_outstanding NULL for a real mega-cap with the data sitting right there in the
filing. Same root cause almost certainly affects every other large-cap filer that reports
this fact in millions rather than raw share counts.
"""

from unittest.mock import MagicMock

from loaders.load_company_info_sec import CompanyInfoSECLoader


def _loader() -> CompanyInfoSECLoader:
    loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
    loader.sec_client = MagicMock()
    return loader


def _submissions_with_10k(accession: str = "0001652044-26-000018") -> dict:
    return {
        "filings": {
            "recent": {
                "form": ["10-K"],
                "accessionNumber": [accession],
            }
        }
    }


class TestSharesOutstandingScaleAttribute:
    def test_scale_6_million_value_is_multiplied_correctly(self):
        """Live-shaped Alphabet fixture: three share classes, all tagged scale="6"."""
        loader = _loader()
        loader.sec_client.get_filing_plaintext.return_value = (
            '<ix:nonFraction unitRef="shares" contextRef="c-16" decimals="INF" '
            'name="dei:EntityCommonStockSharesOutstanding" format="ixt:num-dot-decimal" '
            'scale="6" id="f-66">5,822</ix:nonFraction> million shares of Class A stock, '
            '<ix:nonFraction unitRef="shares" contextRef="c-17" decimals="INF" '
            'name="dei:EntityCommonStockSharesOutstanding" scale="6" id="f-67">837'
            "</ix:nonFraction> million shares of Class B stock, "
            '<ix:nonFraction unitRef="shares" contextRef="c-18" decimals="INF" '
            'name="dei:EntityCommonStockSharesOutstanding" scale="6" id="f-68">5,438'
            "</ix:nonFraction> million shares of Class C stock"
        )

        result = loader._fetch_shares_outstanding_from_filing_text("GOOGL", "1652044", _submissions_with_10k())

        assert result == 5_822_000_000

    def test_no_scale_attribute_defaults_to_raw_units(self):
        """PLNT-style filer: raw share counts, no scale= attribute at all - must stay
        exactly as-is, not accidentally scaled."""
        loader = _loader()
        loader.sec_client.get_filing_plaintext.return_value = (
            '<ix:nonFraction unitRef="shares" contextRef="c-1" '
            'name="dei:EntityCommonStockSharesOutstanding" decimals="INF">79,697,889'
            "</ix:nonFraction> shares of Class A common stock, "
            '<ix:nonFraction unitRef="shares" contextRef="c-2" '
            'name="dei:EntityCommonStockSharesOutstanding" decimals="INF">316,128'
            "</ix:nonFraction> shares of Class B common stock"
        )

        result = loader._fetch_shares_outstanding_from_filing_text("PLNT", "0000000000", _submissions_with_10k())

        assert result == 79_697_889

    def test_scale_0_is_a_no_op(self):
        loader = _loader()
        loader.sec_client.get_filing_plaintext.return_value = (
            '<ix:nonFraction name="dei:EntityCommonStockSharesOutstanding" scale="0">12,345,678</ix:nonFraction>'
        )

        result = loader._fetch_shares_outstanding_from_filing_text("ZZZZ", "0000000000", _submissions_with_10k())

        assert result == 12_345_678

    def test_scaled_value_still_respects_plausibility_floor(self):
        """A tiny scaled value (e.g. scale="3" on a 12-share fact) must still be dropped -
        the floor applies to the SCALED value, not the raw text."""
        loader = _loader()
        loader.sec_client.get_filing_plaintext.return_value = (
            '<ix:nonFraction name="dei:EntityCommonStockSharesOutstanding" scale="0">12</ix:nonFraction>'
        )

        result = loader._fetch_shares_outstanding_from_filing_text("ZZZZ", "0000000000", _submissions_with_10k())

        assert result is None
