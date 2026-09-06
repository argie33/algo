"""Regression test for the 2026-08-23 fix (goal session: "Ownership data unresolved"
bucket investigation): load_company_info_sec.py left shares_outstanding_unavailable_reason
unset (column didn't even exist) whenever shares_outstanding ended up None on an otherwise-
available row (data_unavailable=False) - unlike every other partial-field gap in this
codebase, which always carries an explicit *_unavailable_reason sibling.

Live audit found 1,237 active-universe rows with shares_outstanding NULL and
data_unavailable=false, requiring ad-hoc SQL to manually decompose into 3 buckets before
confirming none were a new bug: 1,035 foreign private issuers (restrict_to_domestic_forms
correctly excludes their facts), 152 closed-end funds/trusts with has_annual_report_filing=
false (structurally never file 10-K/20-F), and 50 real 10-K/20-F filers - live-confirmed via
symbol inspection to be overwhelmingly dual/multi-class tickers (DGICA/DGICB, FWONA/FWONK,
UHAL/UHAL.B, ...) and royalty trusts reporting "units" not "shares" - the same already-known
structural EDGAR limitation as the dual-class primary-ticker gap, not a new bug. See
migration 1201's own comment for the full evidence.
"""

from unittest.mock import MagicMock

from loaders.load_company_info_sec import CompanyInfoSECLoader


def _loader() -> CompanyInfoSECLoader:
    loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
    loader.sec_client = MagicMock()
    return loader


def _submissions(forms: list[str], sic: str | None = "3674", entity_type: str = "operating") -> dict:
    return {
        "name": "Test Co",
        "sic": sic,
        "sicDescription": "SEMICONDUCTORS & RELATED DEVICES" if sic == "3674" else None,
        "entityType": entity_type,
        "filings": {"recent": {"form": forms}},
    }


class TestSharesOutstandingUnavailableReason:
    def test_foreign_private_issuer_gets_fpi_reason(self):
        """TSM-shaped case: a real 20-F dei fact exists but is correctly rejected as
        foreign-form, and the text-fallback also finds nothing - must be attributed to the
        FPI exclusion, not left as an unexplained None."""
        loader = _loader()
        loader.sec_client.symbol_to_cik.return_value = "1046179"
        loader.sec_client.get_submissions.return_value = _submissions(["20-F"])
        loader.sec_client.get_company_facts.return_value = {
            "facts": {
                "dei": {
                    "EntityCommonStockSharesOutstanding": {
                        "units": {"shares": [{"end": "2025-12-31", "val": 25_932_524_521, "form": "20-F"}]}
                    }
                },
                "us-gaap": {},
            }
        }
        loader.sec_client.get_filing_plaintext.return_value = ""

        result = loader.fetch_incremental("TSM", None)[0]

        assert result["shares_outstanding"] is None
        assert result["shares_outstanding_unavailable_reason"] == "fpi_shares_excluded_domestic_only"

    def test_no_annual_report_filing_gets_registered_investment_company_reason(self):
        """A real closed-end-fund/investment-trust shape (entity_type='other', no SIC code -
        the same discriminator _get_registered_investment_company_symbols() uses elsewhere,
        e.g. vqg_symbol_gates.py): never files 10-K/20-F at all (only fund-specific forms), so
        no dei/us-gaap shares fact can exist. FIXED 2026-09-06 (goal: "SEC/XBRL missing data to
        zero" sweep): this used to fall to the generic "no_annual_report_filing" ("Missing
        SEC/XBRL data") - live-confirmed 30+ real Gabelli/Invesco/Franklin-class trusts hitting
        this exact shape, a permanent structural fact that belongs in "Legitimate / not
        applicable" alongside this same population's registered_investment_company_no_xbrl
        (dividend/cash-flow gaps)."""
        loader = _loader()
        loader.sec_client.symbol_to_cik.return_value = "0000914208"
        loader.sec_client.get_submissions.return_value = _submissions(
            ["N-CSR", "NPORT-P"], sic=None, entity_type="other"
        )
        loader.sec_client.get_company_facts.return_value = {"facts": {"dei": {}, "us-gaap": {}}}
        loader.sec_client.get_filing_plaintext.return_value = ""

        result = loader.fetch_incremental("BGT", None)[0]

        assert result["shares_outstanding"] is None
        assert result["shares_outstanding_unavailable_reason"] == "registered_investment_company_no_annual_report"

    def test_no_annual_report_filing_keeps_generic_reason_for_real_operating_company(self):
        """A genuinely new/recently-registered real operating company (has a real SIC code,
        entity_type='operating') that simply hasn't filed a 10-K yet must keep the generic
        "no_annual_report_filing" reason - the registered_investment_company_no_annual_report
        reclassification above must not sweep in a real gap just because has_annual_report_
        filing is also False for this population."""
        loader = _loader()
        loader.sec_client.symbol_to_cik.return_value = "0001900000"
        loader.sec_client.get_submissions.return_value = _submissions(["S-1"])
        loader.sec_client.get_company_facts.return_value = {"facts": {"dei": {}, "us-gaap": {}}}
        loader.sec_client.get_filing_plaintext.return_value = ""

        result = loader.fetch_incremental("NEWCO", None)[0]

        assert result["shares_outstanding"] is None
        assert result["shares_outstanding_unavailable_reason"] == "no_annual_report_filing"

    def test_domestic_filer_with_no_resolvable_shares_gets_fallback_reason(self):
        """A real domestic 10-K filer (e.g. a dual-class ticker like DGICA) where all 3
        pathways - dei, us-gaap, filing-text - come back empty. Must be distinguished from
        both the FPI and CEF buckets above."""
        loader = _loader()
        loader.sec_client.symbol_to_cik.return_value = "0000800457"
        loader.sec_client.get_submissions.return_value = _submissions(["10-K"])
        loader.sec_client.get_company_facts.return_value = {"facts": {"dei": {}, "us-gaap": {}}}
        loader.sec_client.get_filing_plaintext.return_value = ""

        result = loader.fetch_incremental("DGICA", None)[0]

        assert result["shares_outstanding"] is None
        assert result["shares_outstanding_unavailable_reason"] == "shares_outstanding_not_in_xbrl_or_filing_text"

    def test_cik_not_found_also_sets_shares_outstanding_reason(self):
        """FIXED 2026-09-02 (SEC/XBRL missing-data sweep): a whole-row failure via
        _unavailable_record() (cik_not_found/submissions_not_found_404/submissions_empty/
        entity_name_not_found) must ALSO populate shares_outstanding_unavailable_reason,
        not just the bare top-level `reason` - live-caught via FRBA/GV/HIFS/HOS/NBN/NUTR/
        PAAI/QMMM/RCBC/SSBI/TOWN/YFOR all sitting with shares_outstanding NULL and
        shares_outstanding_unavailable_reason ALSO NULL (invisible to the coverage
        dashboard's per-field breakdown) despite data_unavailable=True making the gap
        obvious at the row level."""
        loader = _loader()
        loader.sec_client.symbol_to_cik.side_effect = ValueError("not in ticker cache")

        result = loader.fetch_incremental("FRBA", None)[0]

        assert result["data_unavailable"] is True
        assert result["reason"] == "cik_not_found"
        assert result["shares_outstanding"] is None
        assert result["shares_outstanding_unavailable_reason"] == "cik_not_found"

    def test_reason_is_none_when_shares_outstanding_resolved(self):
        """Companion case: a real domestic 10-K filer whose dei fact resolves normally must
        not have any unavailable_reason attached - this only fires on a genuine gap."""
        loader = _loader()
        loader.sec_client.symbol_to_cik.return_value = "0000320193"
        loader.sec_client.get_submissions.return_value = _submissions(["10-K"])
        loader.sec_client.get_company_facts.return_value = {
            "facts": {
                "dei": {
                    "EntityCommonStockSharesOutstanding": {
                        "units": {"shares": [{"end": "2026-06-30", "val": 14_594_180_000, "form": "10-K"}]}
                    }
                },
                "us-gaap": {},
            }
        }

        result = loader.fetch_incremental("AAPL", None)[0]

        assert result["shares_outstanding"] == 14_594_180_000
        assert result["shares_outstanding_unavailable_reason"] is None
