"""Regression test for the 2026-09-03 fix (goal session: SEC/XBRL missing-data sweep):
_NON_COMMON_SECURITY_TICKERS - same "false ambiguity" bug class as the preferred-suffix regex
fix (test_company_info_sec_preferred_ticker_ambiguity_fix_20260902.py), but for exchange-traded
DEBT securities (baby bonds/subordinated notes) registered on the same CIK as a common stock.
These don't follow the preferred-stock "-P<letter>" naming convention (no dash, no "P"), so the
existing regex doesn't catch them and they falsely trigger the "cannot determine which class"
ambiguity guard.

Live-verified against Stifel Financial's (CIK 720672) actual submissions.json ticker list
(['SF', 'SF-PB', 'SFB', 'SF-PC', 'SF-PD']) - SFB is Stifel's 6.25% Subordinated Notes due 2054,
not a second common share class; SF itself has exactly one common class.

Also covers DDT (Dillard's 7.5% Cumulative Preferred Stock, same CIK as DDS) - the same false-
ambiguity shape but for PREFERRED stock spelled without the "-P<letter>" convention the existing
regex expects.
"""

from unittest.mock import MagicMock

from loaders.load_company_info_sec import CompanyInfoSECLoader

_SF_FILING_TEXT = (
    '<ix:nonFraction unitRef="shares" contextRef="c-7" decimals="0" '
    'name="dei:EntityCommonStockSharesOutstanding" id="f-39">225,000,000</ix:nonFraction>'
)

# Two-context shape (Ford-style) for the genuine-ambiguity test below - a real second common
# class must still block resolution even when a verified non-common note ticker is also present.
_SF_TWO_CLASS_FILING_TEXT = (
    '<ix:nonFraction unitRef="shares" contextRef="c-7" decimals="0" '
    'name="dei:EntityCommonStockSharesOutstanding" id="f-39">225,000,000</ix:nonFraction>'
    '<ix:nonFraction unitRef="shares" contextRef="c-8" decimals="0" '
    'name="dei:EntityCommonStockSharesOutstanding" id="f-40">1,000,000</ix:nonFraction>'
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


class TestNonCommonSecurityTickerFix:
    def test_sf_resolves_despite_subordinated_note_ticker(self):
        loader = _loader()
        loader.sec_client.get_filing_plaintext.return_value = _SF_FILING_TEXT

        result = loader._fetch_shares_outstanding_from_filing_text(
            "SF", "720672", _submissions_with_10k("0001193125-26-067130", ["SF", "SF-PB", "SFB", "SF-PC", "SF-PD"])
        )

        assert result == 225_000_000

    def test_genuine_dual_common_class_still_rejected_alongside_note_ticker(self):
        """A real second common class must still block the guess even when a non-common note
        ticker is also present on the same CIK - only the verified note ticker is excluded."""
        loader = _loader()
        loader.sec_client.get_filing_plaintext.return_value = _SF_TWO_CLASS_FILING_TEXT

        result = loader._fetch_shares_outstanding_from_filing_text(
            "SF",
            "720672",
            _submissions_with_10k("0001193125-26-067130", ["SF", "SF-B", "SFB"]),
        )

        assert result is None

    def test_dds_resolves_despite_non_dash_preferred_ticker(self):
        loader = _loader()
        loader.sec_client.get_filing_plaintext.return_value = (
            '<ix:nonFraction unitRef="shares" contextRef="c-7" decimals="0" '
            'name="dei:EntityCommonStockSharesOutstanding" id="f-39">11,630,838</ix:nonFraction>'
        )

        result = loader._fetch_shares_outstanding_from_filing_text(
            "DDS", "28917", _submissions_with_10k("0000028917-26-000009", ["DDS", "DDT"])
        )

        assert result == 11_630_838

    def test_non_common_security_set_is_narrowly_scoped(self):
        """Defensive: an unrelated bare-letter-suffix ticker (a genuine second common class
        shape, e.g. GTN-A/ATROB) must not be swept into this set by accident."""
        assert "SFB" in CompanyInfoSECLoader._NON_COMMON_SECURITY_TICKERS
        assert "DDT" in CompanyInfoSECLoader._NON_COMMON_SECURITY_TICKERS
        assert "GTN-A" not in CompanyInfoSECLoader._NON_COMMON_SECURITY_TICKERS
        assert "ATROB" not in CompanyInfoSECLoader._NON_COMMON_SECURITY_TICKERS
        assert "HVT-A" not in CompanyInfoSECLoader._NON_COMMON_SECURITY_TICKERS
        assert "CENTA" not in CompanyInfoSECLoader._NON_COMMON_SECURITY_TICKERS
