"""Regression test for a real, latent (never-yet-triggered) data-integrity bug found
2026-07-27 while sweeping scripts/ for the same class of issue as the fetch_13f_with_openfigi.py
rogue-script bug (see tests/unit/test_institutional_holdings_13f_no_synthetic_fallback.py):

scripts/backfill_shares_outstanding.py fetched shares_outstanding from yfinance and wrote it
directly into company_info_sec.shares_outstanding - a table load_company_info_sec.py sources
exclusively from SEC EDGAR (data_source='sec_edgar_submissions'/'none', confirmed live in the
DB: only those two values ever appear). The yfinance backfill never set data_source at all, so
a yfinance-sourced value would have been completely indistinguishable from a real SEC figure -
worse than the 13F bug, which at least tagged its fabricated rows with a distinct data_source.

Confirmed via direct DB query this script had never actually been run (no non-SEC data_source
values present) - a landmine, not yet a live corruption. Its own docstring explicitly targeted
"the FINRA short interest coverage gap (currently 79.9%)" - but steering/DATA_LOADERS.md
documents that gap as the CORRECT, intended fail-fast behavior ("symbols without an SEC
shares-outstanding figure are marked data_unavailable even when FINRA has data"), not a bug to
route around with a non-SEC source. Deleted outright, same as the 13F script.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestCompanyInfoSecStaysSecOnly:
    def test_yfinance_shares_outstanding_backfill_script_is_gone(self):
        assert not (REPO_ROOT / "scripts" / "backfill_shares_outstanding.py").exists(), (
            "this script wrote yfinance-sourced shares_outstanding into company_info_sec "
            "with no data_source tag at all, indistinguishable from a real SEC EDGAR figure - "
            "it must stay deleted, not be resurrected to 'fix' the FINRA short-interest "
            "coverage gap, which is documented, correct fail-fast behavior, not a bug"
        )

    def test_no_script_writes_yfinance_data_into_company_info_sec(self):
        """Static guard: no file in scripts/ should combine an actual yfinance fetch call with
        an actual write statement targeting company_info_sec - that combination is exactly what
        caused the deleted script's bug, regardless of what the file is eventually named. Keyed
        on real fetch/write call patterns (not just both words appearing anywhere) to avoid
        false positives on files that merely mention both names in comments/registries, e.g.
        scripts/verify_loaders_health.py's loader table-name listing."""
        hits = []
        for path in (REPO_ROOT / "scripts").rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            has_yfinance_fetch = "yf.Ticker(" in text or "yfinance.Ticker(" in text
            has_company_info_sec_write = "UPDATE company_info_sec" in text or "INSERT INTO company_info_sec" in text
            if has_yfinance_fetch and has_company_info_sec_write:
                hits.append(str(path.relative_to(REPO_ROOT)))
        assert not hits, f"found yfinance-fetch + company_info_sec-write combination in: {hits}"
