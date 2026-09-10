"""Regression test for the 2026-09-10 fix (goal: "SEC/XBRL missing data" under-500 push,
no_annual_report_filing/eps_never_tagged_in_filings investigation): load_company_info_sec.py's
`has_annual_report_filing` check only recognized 10-K/10-K-A/20-F/20-F-A - never 40-F/40-F-A,
the MJDS annual-report form Canadian foreign private issuers file in lieu of 20-F - even
though this same function's own `is_foreign_private_issuer` classification a few lines below
(and the income/balance-sheet extraction pipeline's own `_ANNUAL_REPORT_FORMS`/
`_PRIMARY_STATEMENT_FORMS`) already treat 40-F as a real annual-report form.

Live-confirmed via real SEC EDGAR submissions JSON: 137 active-universe symbols with
is_foreign_private_issuer=TRUE were wrongly stuck at has_annual_report_filing=FALSE purely
from this omission, including large 40-F-only Canadian megacaps with real, current annual
filings on file (BMO, BNS, CM, CNQ, BCE, CAE, CNI, CVE, ...). `has_annual_report_filing=FALSE`
is consumed directly by lambda/api/routes/scores_handlers/stock_scores.py's active-universe
leaderboard filter to exclude a symbol outright - so this bug was silently dropping real,
well-covered megacaps from the scored leaderboard, not just mislabeling a coverage reason.
"""

from unittest.mock import MagicMock

from loaders.load_company_info_sec import CompanyInfoSECLoader


def _loader() -> CompanyInfoSECLoader:
    loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
    loader.sec_client = MagicMock()
    return loader


def _submissions(forms: list[str]) -> dict:
    return {
        "name": "Bank of Nova Scotia",
        "sic": "6029",
        "sicDescription": "NATIONAL COMMERCIAL BANKS",
        "entityType": "operating",
        "filings": {"recent": {"form": forms}},
    }


class TestHasAnnualReportFilingRecognizes40F:
    def test_40f_only_filer_has_annual_report_filing_true(self) -> None:
        """A Canadian MJDS filer (40-F, never 10-K/20-F) must be recognized as having a real
        annual report on file - live-confirmed shape for BMO/BNS/CM/CNQ/BCE/CAE/CNI/CVE and
        132 more active-universe symbols."""
        loader = _loader()
        loader.sec_client.symbol_to_cik.return_value = "9631"
        loader.sec_client.get_submissions.return_value = _submissions(["40-F", "6-K", "6-K", "10-Q"])
        loader.sec_client.get_company_facts.return_value = {"facts": {"dei": {}, "us-gaap": {}}}
        loader.sec_client.get_filing_plaintext.return_value = ""

        result = loader.fetch_incremental("BNS", None)[0]

        assert result["has_annual_report_filing"] is True
        # Also correctly classified as a foreign private issuer via the pre-existing
        # 40-F-aware annual_report_forms_recent_first logic just below this check.
        assert result["is_foreign_private_issuer"] is True

    def test_10k_only_filer_still_has_annual_report_filing_true(self) -> None:
        """Unaffected: a plain domestic 10-K filer is unchanged by this fix."""
        loader = _loader()
        loader.sec_client.symbol_to_cik.return_value = "320193"
        loader.sec_client.get_submissions.return_value = {
            "name": "Test Domestic Co",
            "sic": "3674",
            "sicDescription": "SEMICONDUCTORS & RELATED DEVICES",
            "entityType": "operating",
            "filings": {"recent": {"form": ["10-K", "10-Q"]}},
        }
        loader.sec_client.get_company_facts.return_value = {"facts": {"dei": {}, "us-gaap": {}}}
        loader.sec_client.get_filing_plaintext.return_value = ""

        result = loader.fetch_incremental("TESTCO", None)[0]

        assert result["has_annual_report_filing"] is True
        assert result["is_foreign_private_issuer"] is False

    def test_no_annual_report_at_all_still_false(self) -> None:
        """Unaffected: a filer with genuinely no 10-K/20-F/40-F still gets False."""
        loader = _loader()
        loader.sec_client.symbol_to_cik.return_value = "1"
        loader.sec_client.get_submissions.return_value = {
            "name": "Blank Check Co",
            "sic": "6770",
            "sicDescription": "BLANK CHECKS",
            "entityType": "operating",
            "filings": {"recent": {"form": ["10-Q", "8-K"]}},
        }
        loader.sec_client.get_company_facts.return_value = {"facts": {"dei": {}, "us-gaap": {}}}
        loader.sec_client.get_filing_plaintext.return_value = ""

        result = loader.fetch_incremental("SPAC1", None)[0]

        assert result["has_annual_report_filing"] is False
        assert result["shares_outstanding_unavailable_reason"] == "no_annual_report_filing"
