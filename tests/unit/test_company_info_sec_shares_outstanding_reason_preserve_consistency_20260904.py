"""Regression test: shares_outstanding_unavailable_reason must not overwrite a real,
already-on-file shares_outstanding value's correct (None) reason with a fresh "unavailable"
label just because THIS run's own fetch came back empty.

Found 2026-09-04 (goal: "Missing SEC/XBRL data" reduction to zero). `shares_outstanding` is one
of CompanyInfoSECLoader.__init__'s `preserve_on_missing_fields` columns: when a run's own fetch
for a symbol comes back None, the bulk-insert COALESCEs against the existing DB value instead of
overwriting it with NULL, so a symbol with a real value on file keeps it. But
`shares_outstanding_unavailable_reason` is ALSO in that preserve set, and unlike
`shares_outstanding` it is never None going into the insert - some reason string gets computed
unconditionally whenever `shares_outstanding is None` on this run - so it is NOT
COALESCE-preserved, it unconditionally overwrites whatever the row's reason correctly was
(None, for a symbol with a real preserved value). Live-confirmed 66 active-universe rows (DDS,
MKC, WLY, WSO, AGM among others) end up with a real, non-NULL `shares_outstanding` sitting next
to a contradictory "shares_outstanding_not_in_xbrl_or_filing_text" reason - each counted as a
live "Missing SEC/XBRL data" gap despite having real data.
"""

from unittest.mock import MagicMock, patch

from loaders.load_company_info_sec import CompanyInfoSECLoader


def _loader() -> CompanyInfoSECLoader:
    loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
    loader.sec_client = MagicMock()
    return loader


def _submissions(forms: list[str]) -> dict:
    return {
        "name": "Test Co",
        "sic": "3674",
        "sicDescription": "SEMICONDUCTORS & RELATED DEVICES",
        "entityType": "operating",
        "filings": {"recent": {"form": forms}},
    }


class _ExistingValueCursor:
    def __init__(self, existing_shares_outstanding):
        self._existing = existing_shares_outstanding
        self.last_query = None

    def execute(self, query, params=None):
        self.last_query = query

    def fetchone(self):
        if self.last_query and "SELECT shares_outstanding" in self.last_query:
            return (self._existing,) if self._existing is not None else None
        return None

    def fetchall(self):
        return []


class TestSharesOutstandingReasonPreserveConsistency:
    def test_existing_real_value_on_file_keeps_reason_none(self):
        """DDS-shaped case: this run's own fetch finds nothing new, but the symbol already
        has a real shares_outstanding value on file (which the bulk insert will preserve) -
        the reason must stay None, not get overwritten with a fresh "unavailable" label."""
        loader = _loader()
        loader.sec_client.symbol_to_cik.return_value = "0000028917"
        loader.sec_client.get_submissions.return_value = _submissions(["10-K"])
        loader.sec_client.get_company_facts.return_value = {"facts": {"dei": {}, "us-gaap": {}}}
        loader.sec_client.get_filing_plaintext.return_value = ""

        with patch("loaders.load_company_info_sec.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _ExistingValueCursor(11_630_838)
            result = loader.fetch_incremental("DDS", None)[0]

        assert result["shares_outstanding"] is None
        assert result["shares_outstanding_unavailable_reason"] is None

    def test_no_existing_value_still_gets_specific_reason(self):
        """Companion case: no real value on file either (a genuine, never-resolved gap) -
        the specific fallback reason must still fire as before."""
        loader = _loader()
        loader.sec_client.symbol_to_cik.return_value = "0000800457"
        loader.sec_client.get_submissions.return_value = _submissions(["10-K"])
        loader.sec_client.get_company_facts.return_value = {"facts": {"dei": {}, "us-gaap": {}}}
        loader.sec_client.get_filing_plaintext.return_value = ""

        with patch("loaders.load_company_info_sec.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _ExistingValueCursor(None)
            result = loader.fetch_incremental("DGICA", None)[0]

        assert result["shares_outstanding"] is None
        assert result["shares_outstanding_unavailable_reason"] == "shares_outstanding_not_in_xbrl_or_filing_text"
