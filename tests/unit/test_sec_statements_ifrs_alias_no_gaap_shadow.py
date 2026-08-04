"""Regression test for a silent-shadowing bug in _aggregate_concepts()
(utils/external/sec_statements.py):

Before this fix, an IFRS alias spec (e.g. ("Assets", "assets")) was looked up exactly the
same way as its plain us-gaap spec: us-gaap first, ifrs-full only if us-gaap had NOTHING
under that concept name at all. Since "Assets"/"Liabilities"/"Goodwill" etc. are valid tags
in BOTH taxonomies, any filer with even a stale, long-dead us-gaap entry under that name
(e.g. two pre-IFRS-transition fiscal years) permanently shadowed the real, current ifrs-full
data for every later fiscal year - live-confirmed against ASR (Grupo Aeroportuario del
Sureste): us-gaap:Assets had exactly 2 entries (FY2016-2017), so total_assets came back NULL
for FY2018-2024 despite ifrs-full:Assets having real data for those years. The fix makes IFRS
alias specs read ifrs-full directly, never falling back through us-gaap first.
"""

from utils.external.sec_statements import get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000000000"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


def _entry(year: int, val: float, filed: str, form: str = "10-K") -> dict:
    return {"end": f"{year}-12-31", "val": val, "filed": filed, "fp": "FY", "fy": year, "form": form}


class TestIfrsAliasDoesNotShadowThroughStaleUsGaap:
    def test_ifrs_alias_reads_ifrs_data_even_when_stale_us_gaap_entry_exists(self):
        facts = {
            "us-gaap": {
                # Stale, pre-IFRS-transition entries - real, but from years before the
                # filer switched to ifrs-full-only reporting.
                "Assets": _concept([_entry(2016, 1_000.0, "2017-03-01"), _entry(2017, 1_100.0, "2018-03-01")]),
            },
            "ifrs-full": {
                # Real, current data for later years - must NOT be shadowed by the stale
                # us-gaap entries above just because both taxonomies use the tag "Assets".
                "Assets": _concept([_entry(2023, 5_000.0, "2024-03-01"), _entry(2024, 5_500.0, "2025-03-01")]),
            },
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "ASR", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2016]["assets"] == 1_000.0
        assert by_year[2017]["assets"] == 1_100.0
        # This is the bug: previously NULL/missing because the ifrs alias spec re-read the
        # same stale us-gaap "Assets" entries instead of ifrs-full's real 2023/2024 data.
        assert by_year[2023]["assets"] == 5_000.0
        assert by_year[2024]["assets"] == 5_500.0

    def test_longterm_borrowings_ifrs_alias_maps_to_long_term_debt(self):
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "LongtermBorrowings": _concept([_entry(2023, 2_500.0, "2024-03-01")]),
            },
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "ASR", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2023]["long_term_debt"] == 2_500.0
