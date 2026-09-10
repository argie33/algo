"""Regression test: dividend_data must distinguish registered investment companies
(closed-end funds) from a generic SEC extraction failure.

Found live 2026-08-19 ("no SEC data" audit, industry-specific nuance pass): closed-end funds
like the BlackRock BBN/BCAT/BGT/BIT/BKT-class trusts file under SEC's "cef"/"ffd" XBRL
taxonomies instead of the standard 10-K "us-gaap"/"ifrs-full" taxonomies this loader checks -
live-confirmed via SEC's own companyfacts API for BBN: `facts` contains only "cef" (20
concepts) and "ffd" (5 concepts), zero "us-gaap"/"ifrs-full". Every one of the "cef" taxonomy's
20 concepts was inspected live: all are N-2 prospectus fee-table data (ManagementFeesPercent,
ExpenseExampleYears1to10, ...), none is a dividend/distribution amount. This is a genuine,
permanent structural absence (SEC has no machine-readable distribution data for these filers at
all), same class as reit_special_entity elsewhere in this codebase - not a loader gap that
trying harder XBRL concepts could ever close, so it must not keep reading as "no_us_gaap_facts"
(which sounds like our own extraction failed).
"""

from unittest.mock import MagicMock, patch

from loaders.load_dividend_data import DividendDataLoader


def _loader() -> DividendDataLoader:
    loader = DividendDataLoader.__new__(DividendDataLoader)
    loader.sec_client = None
    return loader


class TestDividendRegisteredInvestmentCompanyReason:
    def test_cef_taxonomy_only_gets_specific_reason(self, monkeypatch):
        def fake_fetch(self, symbol, timeout_sec=20.0):
            return {
                "cik": "1",
                "facts_response": {
                    "facts": {
                        "cef": {"ManagementFeesPercent": {"units": {"pure": [{"val": 0.01, "end": "2025-12-31"}]}}},
                    }
                },
            }

        monkeypatch.setattr(DividendDataLoader, "_fetch_sec_data_with_timeout", fake_fetch)

        results = _loader().fetch_incremental("BBN", None)

        assert len(results) == 1
        assert results[0]["data_unavailable"] is True
        assert results[0]["data_unavailable_reason"] == "registered_investment_company_no_xbrl"

    def test_ffd_taxonomy_only_also_gets_specific_reason(self, monkeypatch):
        def fake_fetch(self, symbol, timeout_sec=20.0):
            return {
                "cik": "1",
                "facts_response": {"facts": {"ffd": {"SomeFundConcept": {"units": {"pure": [{"val": 1}]}}}}},
            }

        monkeypatch.setattr(DividendDataLoader, "_fetch_sec_data_with_timeout", fake_fetch)

        results = _loader().fetch_incremental("SOMEFUND", None)

        assert results[0]["data_unavailable_reason"] == "registered_investment_company_no_xbrl"

    def test_ordinary_filer_with_no_facts_at_all_keeps_generic_reason(self, monkeypatch):
        # Control: a genuinely thin filer with neither us-gaap/ifrs-full NOR cef/ffd, and NOT
        # matching the entity_type='other'/sic_code IS NULL RIC fingerprint either, must keep
        # the original generic reason - this must not become a catch-all for every empty facts
        # dict, only the specific registered-investment-company case (cef/ffd OR the
        # company_info_sec fingerprint added 2026-09-10).
        def fake_fetch(self, symbol, timeout_sec=20.0):
            return {"cik": "1", "facts_response": {"facts": {}}}

        monkeypatch.setattr(DividendDataLoader, "_fetch_sec_data_with_timeout", fake_fetch)

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ("operating", "3674")  # ordinary operating company

        with patch("utils.db.DatabaseContext") as mock_db:
            mock_db.return_value.__enter__.return_value = mock_cursor
            results = _loader().fetch_incremental("THINFILER", None)

        assert results[0]["data_unavailable_reason"] == "no_us_gaap_facts"

    def test_empty_facts_with_ric_company_info_fingerprint_gets_specific_reason(self, monkeypatch):
        # FIX 2026-09-10: some closed-end funds (BKT/BME/ETO/EVN/VMO-class) don't even carry a
        # cef/ffd taxonomy - companyfacts returns a totally empty `facts: {}`. Live-confirmed via
        # SEC's own submissions API that these are genuine Investment Company Act filers (forms
        # 40-17G/486BPOS/497, zero 10-K ever) - company_info_sec's entity_type='other'/
        # sic_code IS NULL fingerprint (already used by vqg_symbol_gates.py for this same fund
        # class) catches them without an extra live SEC call.
        def fake_fetch(self, symbol, timeout_sec=20.0):
            return {"cik": "1", "facts_response": {"facts": {}}}

        monkeypatch.setattr(DividendDataLoader, "_fetch_sec_data_with_timeout", fake_fetch)

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ("other", None)  # RIC fingerprint

        with patch("utils.db.DatabaseContext") as mock_db:
            mock_db.return_value.__enter__.return_value = mock_cursor
            results = _loader().fetch_incremental("BKT", None)

        assert results[0]["data_unavailable_reason"] == "registered_investment_company_no_xbrl"

    def test_empty_facts_with_no_company_info_sec_row_keeps_generic_reason(self, monkeypatch):
        # Control: a symbol with no company_info_sec row at all (e.g. not yet loaded) must not
        # be misclassified - fail safe to the honest generic reason, not a guess.
        def fake_fetch(self, symbol, timeout_sec=20.0):
            return {"cik": "1", "facts_response": {"facts": {}}}

        monkeypatch.setattr(DividendDataLoader, "_fetch_sec_data_with_timeout", fake_fetch)

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None

        with patch("utils.db.DatabaseContext") as mock_db:
            mock_db.return_value.__enter__.return_value = mock_cursor
            results = _loader().fetch_incremental("NEWCO", None)

        assert results[0]["data_unavailable_reason"] == "no_us_gaap_facts"

    def test_real_us_gaap_facts_unaffected(self, monkeypatch):
        # Control: a normal operating company with real us-gaap facts must never take this
        # branch at all, regardless of whether it happens to also carry unrelated keys.
        def fake_fetch(self, symbol, timeout_sec=20.0):
            return {
                "cik": "1",
                "facts_response": {
                    "facts": {
                        "us-gaap": {
                            "CommonStockDividendsPerShareDeclared": {
                                "units": {"USD/shares": [{"end": "2025-03-31", "val": 0.5, "filed": "2025-04-22"}]}
                            }
                        }
                    }
                },
            }

        monkeypatch.setattr(DividendDataLoader, "_fetch_sec_data_with_timeout", fake_fetch)

        results = _loader().fetch_incremental("NORMALCO", None)

        assert results[0]["data_unavailable"] is False
        assert results[0]["dividend_per_share"] == 0.5
