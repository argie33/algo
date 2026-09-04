"""Regression test for the 2026-09-04 fix (goal session: SEC/XBRL missing-data sweep):
same false-ambiguity bug class as _NON_COMMON_SECURITY_TICKERS
(test_company_info_sec_non_common_security_ticker_fix_20260903.py), but for SPAC unit/warrant/
rights tickers sharing a CIK with the underlying common stock (e.g. TWLV/TWLVU/TWLVR,
JACS/JACS-UN/JACS-RI). Unlike the fixed-set approach used for SFB/DDT, these are matched
relative to another ticker already on the same CIK so a real standalone ticker ending in
U/W/R can't be misclassified.
"""

from unittest.mock import MagicMock

from loaders.load_company_info_sec import CompanyInfoSECLoader

_TWLV_FILING_TEXT = (
    '<ix:nonFraction unitRef="shares" contextRef="c-7" decimals="0" '
    'name="dei:EntityCommonStockSharesOutstanding" id="f-39">28,750,000</ix:nonFraction>'
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


class TestSpacUnitWarrantRightTickerFix:
    def test_bare_suffix_forms_detected(self):
        tickers = ["TWLV", "TWLVR", "TWLVU"]
        assert CompanyInfoSECLoader._is_spac_unit_warrant_right_ticker("TWLVU", tickers)
        assert CompanyInfoSECLoader._is_spac_unit_warrant_right_ticker("TWLVR", tickers)
        assert not CompanyInfoSECLoader._is_spac_unit_warrant_right_ticker("TWLV", tickers)

    def test_dash_suffix_forms_detected(self):
        tickers = ["JACS", "JACS-RI", "JACS-UN"]
        assert CompanyInfoSECLoader._is_spac_unit_warrant_right_ticker("JACS-RI", tickers)
        assert CompanyInfoSECLoader._is_spac_unit_warrant_right_ticker("JACS-UN", tickers)
        assert not CompanyInfoSECLoader._is_spac_unit_warrant_right_ticker("JACS", tickers)

    def test_real_dual_common_classes_not_misclassified(self):
        assert not CompanyInfoSECLoader._is_spac_unit_warrant_right_ticker("BRK-A", ["BRK-B", "BRK-A"])
        assert not CompanyInfoSECLoader._is_spac_unit_warrant_right_ticker("HEI-A", ["HEI", "HEI-A"])
        assert not CompanyInfoSECLoader._is_spac_unit_warrant_right_ticker("HVT-A", ["HVT", "HVT-A"])

    def test_twlv_resolves_despite_unit_and_rights_tickers(self):
        loader = _loader()
        loader.sec_client.get_filing_plaintext.return_value = _TWLV_FILING_TEXT

        result = loader._fetch_shares_outstanding_from_filing_text(
            "TWLV", "2052243", _submissions_with_10k("0001193125-26-067130", ["TWLV", "TWLVR", "TWLVU"])
        )

        assert result == 28_750_000
