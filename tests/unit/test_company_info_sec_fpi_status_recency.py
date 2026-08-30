"""Regression test for a 2026-08-30 fix (goal: full-data audit, AKTX shares_outstanding
follow-up): load_company_info_sec.py's `is_foreign_private_issuer` was computed as
`any(f in ("20-F", ..., "6-K") for f in recent_forms)` - true if a foreign form EVER appeared
anywhere in SEC's "recent" filings array, with no recency bound at all.

Live-confirmed via AKTX (Akari Therapeutics): its last 6-K was filed 2023-12-01. Every annual
and quarterly report since - 10-K filed 2024-03-29, 2025-04-15, 2026-03-30; 10-Qs throughout;
plus DEF 14A and Form 4 filings, both of which real FPIs are exempt from and so don't file -
is domestic-form. AKTX stopped being a foreign private issuer over two years ago, but the old
`any()` check kept it permanently misclassified as True, which gates behavior across multiple
downstream loaders (load_sec_valuations.py's domestic-only cross-check, load_short_interest_
finra.py/load_institutional_holdings_13f.py's "foreign_private_issuer_shares_unavailable"
labeling).

Fixed: FPI status is now determined by the MOST RECENT annual report on file (10-K/10-K-A vs
20-F/20-F-A/40-F/40-F-A) - recent_forms is newest-first, same ordering assumption
_fetch_shares_outstanding_from_filing_text already relies on. Falls back to the original
any-6-K behavior only when no annual report of either kind exists yet (a genuinely new/
recently-registered filer).
"""

from unittest.mock import MagicMock

from loaders.load_company_info_sec import CompanyInfoSECLoader


def _loader() -> CompanyInfoSECLoader:
    loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
    loader.sec_client = MagicMock()
    return loader


def _run(forms: list[str]) -> dict:
    loader = _loader()
    loader.sec_client.symbol_to_cik.return_value = "1541157"
    loader.sec_client.get_submissions.return_value = {
        "name": "Akari Therapeutics Plc",
        "sic": "2836",
        "sicDescription": "BIOLOGICAL PRODUCTS",
        "entityType": "operating",
        "filings": {"recent": {"form": forms}},
    }
    loader.sec_client.get_company_facts.return_value = {"facts": {"dei": {}, "us-gaap": {}}}
    loader.sec_client.get_filing_plaintext.return_value = ""

    result = loader.fetch_incremental("AKTX", None)
    return result[0]


class TestForeignPrivateIssuerStatusUsesMostRecentAnnualReport:
    def test_converted_to_domestic_filer_no_longer_flagged_fpi(self) -> None:
        """AKTX-shaped: newest-first forms with 10-K/10-Q/DEF 14A/Form 4 all appearing AFTER
        the last 6-K - a completed FPI-to-domestic conversion must not be flagged FPI."""
        forms = ["10-Q", "8-K", "10-Q", "DEF 14A", "4", "10-K", "6-K", "6-K", "20-F"]

        result = _run(forms)

        assert result["is_foreign_private_issuer"] is False

    def test_still_currently_fpi_stays_flagged(self) -> None:
        """A filer whose most recent annual report is still a 20-F must stay flagged FPI -
        this fix must not weaken the original, still-valid protection."""
        forms = ["6-K", "6-K", "20-F", "6-K", "20-F"]

        result = _run(forms)

        assert result["is_foreign_private_issuer"] is True

    def test_never_filed_annual_report_falls_back_to_any_foreign_form(self) -> None:
        """No 10-K or 20-F/40-F anywhere yet (genuinely new/recently-registered filer) -
        falls back to the original any-6-K behavior rather than defaulting to False."""
        forms = ["6-K", "8-A12B"]

        result = _run(forms)

        assert result["is_foreign_private_issuer"] is True

    def test_always_domestic_filer_unaffected(self) -> None:
        """A filer that has never touched a foreign form at all must stay unflagged, same
        as before this fix."""
        forms = ["10-Q", "8-K", "10-K", "DEF 14A"]

        result = _run(forms)

        assert result["is_foreign_private_issuer"] is False
