"""Regression test for a resource-contention bug in
_fill_long_term_debt_from_segment_dimensional_facts() (utils/external/sec_statements.py).

Live-caught 2026-09-01 (goal session: "understand our data gaps before resuming Fama-MacBeth")
via a `py-spy dump --pid <pid>` (safe, read-only) on a genuinely stalled
load_financial_statements.py process: the loop had no cap on how many fiscal years it would
attempt per symbol. A genuinely debt-free filer (real, not a data gap) has long_term_debt=None
for EVERY fiscal year, so every year in a symbol's annual history - some run 15-18 years deep
(FLO: 18, live-confirmed) - triggered its own submissions-fetch-then-XML-fetch-then-parse round
trip, unconditionally, on every run. The per-symbol 30s timeout in _run_symbol_pass bounds the
*reported* time, but the worker thread is daemon=True and gets abandoned (not killed) on
timeout, so a symbol stuck mid-way through a dozen-plus sequential SEC fetches kept running in
the background indefinitely, competing for the shared RateLimiter(2) every other in-flight and
future thread needs - degrading throughput for the whole remaining run.

Fix: cap to the most recent 3 missing fiscal years per symbol. This test locks in that cap
(only 3 get_filing_xml calls for a 10-missing-year symbol) and confirms the 3 attempted years
are the most recent ones, not an arbitrary subset.
"""

from utils.external.sec_statements import _fill_long_term_debt_from_segment_dimensional_facts


class _FakeClient:
    def __init__(self) -> None:
        self.get_filing_xml_calls: list[tuple[str, str, str]] = []

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000000001"

    def get_submissions(self, cik: str) -> dict:
        # One 10-K per fiscal year 2010-2025 (16 years), all locatable.
        years = list(range(2010, 2026))
        return {
            "filings": {
                "recent": {
                    "form": ["10-K"] * len(years),
                    "reportDate": [f"{y}-12-31" for y in years],
                    "accessionNumber": [f"acc-{y}" for y in years],
                    "filingDate": [f"{y + 1}-02-15" for y in years],
                }
            }
        }

    def get_filing_xml(self, cik: str, accession_number: str, form_type: str) -> str:
        self.get_filing_xml_calls.append((cik, accession_number, form_type))
        # No usable dimensional debt decomposition - sum_segment_dimensional_debt will
        # return None, leaving long_term_debt untouched (the outcome doesn't matter here,
        # only the CALL COUNT does).
        return "<xbrl></xbrl>"


class TestSegmentDebtFiscalYearCap:
    def test_caps_to_three_most_recent_missing_years(self) -> None:
        # A genuinely debt-free symbol: 10 consecutive years, long_term_debt=None in every
        # one - the exact shape that made the old, uncapped loop issue 10 sequential HTTP
        # fetches for a single symbol.
        rows = [{"fiscal_year": year, "long_term_debt": None} for year in range(2015, 2025)]
        client = _FakeClient()

        _fill_long_term_debt_from_segment_dimensional_facts(rows, client, "TEST")

        assert len(client.get_filing_xml_calls) == 3, (
            "must not attempt more than the 3 most recent missing fiscal years per symbol"
        )
        attempted_accessions = {accn for _, accn, _ in client.get_filing_xml_calls}
        assert attempted_accessions == {"acc-2024", "acc-2023", "acc-2022"}, (
            "must attempt the MOST RECENT missing years, not an arbitrary subset"
        )

    def test_does_not_attempt_years_that_already_have_debt(self) -> None:
        rows = [
            {"fiscal_year": 2024, "long_term_debt": None},
            {"fiscal_year": 2023, "long_term_debt": 5_000_000.0},  # already resolved
            {"fiscal_year": 2022, "long_term_debt": None},
        ]
        client = _FakeClient()

        _fill_long_term_debt_from_segment_dimensional_facts(rows, client, "TEST")

        attempted_accessions = {accn for _, accn, _ in client.get_filing_xml_calls}
        assert attempted_accessions == {"acc-2024", "acc-2022"}
