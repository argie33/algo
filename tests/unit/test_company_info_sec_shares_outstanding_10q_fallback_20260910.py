"""Regression test for a 2026-09-10 fix (goal: "under 300" SEC/XBRL missing-data push,
no_annual_report_filing investigation): load_company_info_sec.py's
_fetch_shares_outstanding_from_filing_text only ever looked at the most recent 10-K/10-K-A
for the cover-page dei:EntityCommonStockSharesOutstanding inline-XBRL fallback tag, so a
domestic filer too new to have filed a 10-K yet (a recent IPO) got shares_outstanding=None
and the generic "no_annual_report_filing" ("Missing SEC/XBRL data") reason forever, even
though its 10-Qs carry the identical cover-page tag with a real, current value.

Live-confirmed via XPRO (a real symbol in this exact bucket): its 2026-07-28 10-Q (accession
0001437749-26-024670) tags "112,349,149" via the same
<ix:nonFraction ... name="dei:EntityCommonStockSharesOutstanding"> pattern the 10-K path
already parses.

Fixed: fall back to the most recent 10-Q/10-Q/A only when no 10-K/10-K-A exists at all -
never overrides a real annual filing (10-K stays higher priority), and stays domestic-only
(10-Q, unlike 6-K, is never filed by foreign private issuers) so this can't reintroduce the
BP/TV 20-F unit-mismatch trap the annual-only restriction already guards against.
"""

from unittest.mock import MagicMock

from loaders.load_company_info_sec import CompanyInfoSECLoader


def _loader() -> CompanyInfoSECLoader:
    loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
    loader.sec_client = MagicMock()
    return loader


_INLINE_TAG = (
    '<ix:nonFraction name="dei:EntityCommonStockSharesOutstanding" scale="0" '
    'unitRef="Share" decimals="INF" format="ixt:num-dot-decimal" '
    'contextRef="i_2026-07-21" id="ixv-1">{value}</ix:nonFraction>'
)


class TestSharesOutstandingFilingTextFallsBackToQuarterlyReport:
    def test_recent_ipo_with_no_10k_recovers_from_10q_cover_page(self) -> None:
        loader = _loader()
        loader.sec_client.get_filing_plaintext.return_value = _INLINE_TAG.format(value="112,349,149")

        submissions = {
            "filings": {
                "recent": {
                    "form": ["10-Q", "8-K", "S-1"],
                    "accessionNumber": ["0001437749-26-024670", "acc-8k", "acc-s1"],
                    "filingDate": ["2026-07-28", "2026-06-01", "2026-01-15"],
                }
            }
        }

        result = loader._fetch_shares_outstanding_from_filing_text("XPRO", "0002126198", submissions)

        assert result == 112349149
        loader.sec_client.get_filing_plaintext.assert_called_once_with("0002126198", "0001437749-26-024670")

    def test_filer_with_real_10k_never_falls_back_to_10q(self) -> None:
        """A filer that already has a real 10-K must keep using it - the 10-Q fallback is
        strictly lowest priority, never a substitute for an existing annual filing."""
        loader = _loader()
        loader.sec_client.get_filing_plaintext.return_value = _INLINE_TAG.format(value="500,000")

        submissions = {
            "filings": {
                "recent": {
                    "form": ["10-Q", "10-K", "8-K"],
                    "accessionNumber": ["acc-10q", "acc-10k", "acc-8k"],
                    "filingDate": ["2026-08-01", "2026-03-01", "2026-06-01"],
                }
            }
        }

        loader._fetch_shares_outstanding_from_filing_text("SYM", "cik", submissions)

        loader.sec_client.get_filing_plaintext.assert_called_once_with("cik", "acc-10k")

    def test_no_10k_and_no_10q_stays_none(self) -> None:
        """Genuinely no annual report and no quarterly report either (e.g. only S-1/8-K on
        file) must still return None, not error."""
        loader = _loader()

        submissions = {
            "filings": {
                "recent": {
                    "form": ["S-1", "8-K"],
                    "accessionNumber": ["acc-s1", "acc-8k"],
                    "filingDate": ["2026-01-15", "2026-06-01"],
                }
            }
        }

        result = loader._fetch_shares_outstanding_from_filing_text("NEW", "cik", submissions)

        assert result is None
        loader.sec_client.get_filing_plaintext.assert_not_called()
