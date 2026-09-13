"""Regression test for the FY-stub cross-concept period-mismatch bug in
_aggregate_concepts() (utils/external/sec_statements_aggregate.py).

Live-verified 2026-09-13 via PROK (ProKidney Corp): a not-yet-10-K-filed "current fiscal
year" annual_balance_sheet row was synthesized from whichever 10-Q instant snapshot was
latest available PER CONCEPT independently - stockholders_equity came from PROK's Q1-2026
10-Q (end=2026-03-31), while total_assets/total_liabilities in the SAME nominal
fiscal_year=2026 "FY" row came from its Q2-2026 10-Q (end=2026-06-30). Each per-concept
"latest available" tiebreak is correct in isolation, but nothing previously checked that a
synthesized (non-10-K-anchored) FY row's instant facts actually agree on WHEN they were
measured, silently mixing two different balance-sheet dates into one row and breaking the
assets = liabilities + equity identity for reasons having nothing to do with real
mezzanine-equity/NCI gaps.

Fix: for an FY row not anchored to a real annual-report form, keep only the instant-fact
columns sharing the MAJORITY end date; null the minority (period-mismatched) ones rather
than silently combining them.
"""

from utils.external.sec_statements import get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0001786500"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


class TestFyStubPeriodMismatch:
    def test_mismatched_quarter_snapshots_do_not_combine_into_one_fy_row(self):
        facts = {
            "us-gaap": {
                "Assets": _concept(
                    [
                        {
                            "end": "2026-06-30",
                            "val": 249_016_000,
                            "filed": "2026-08-10",
                            "fp": "Q2",
                            "fy": 2026,
                            "form": "10-Q",
                            "accn": "0001786500-26-000002",
                        },
                    ]
                ),
                "Liabilities": _concept(
                    [
                        {
                            "end": "2026-06-30",
                            "val": 26_178_000,
                            "filed": "2026-08-10",
                            "fp": "Q2",
                            "fy": 2026,
                            "form": "10-Q",
                            "accn": "0001786500-26-000002",
                        },
                    ]
                ),
                "StockholdersEquity": _concept(
                    [
                        {
                            "end": "2026-03-31",
                            "val": -1_023_783_000,
                            "filed": "2026-05-10",
                            "fp": "Q1",
                            "fy": 2026,
                            "form": "10-Q",
                            "accn": "0001786500-26-000001",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "PROK", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        row = by_year[2026]
        # The majority (2 of 3) instant facts agree on end=2026-06-30 (Assets/Liabilities);
        # the outlier (StockholdersEquity, end=2026-03-31) must be dropped, not silently
        # combined with them into a mismatched-period row.
        assert row["assets"] == 249_016_000
        assert row["liabilities"] == 26_178_000
        assert row.get("stockholders_equity") is None

    def test_real_10k_row_is_never_touched_by_the_majority_vote(self):
        """A row anchored to a real annual-report form is one filing's own balance sheet -
        the majority-vote guard must never fire for it even if (hypothetically) its own
        comparative-echo cleanup left differing end dates on unrelated columns."""
        facts = {
            "us-gaap": {
                "Assets": _concept(
                    [
                        {
                            "end": "2025-12-31",
                            "val": 500_000_000,
                            "filed": "2026-02-15",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-K",
                            "accn": "0001786500-26-000010",
                        },
                    ]
                ),
                "Liabilities": _concept(
                    [
                        {
                            "end": "2025-12-31",
                            "val": 200_000_000,
                            "filed": "2026-02-15",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-K",
                            "accn": "0001786500-26-000010",
                        },
                    ]
                ),
                "StockholdersEquity": _concept(
                    [
                        {
                            "end": "2025-12-31",
                            "val": 300_000_000,
                            "filed": "2026-02-15",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-K",
                            "accn": "0001786500-26-000010",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "TEST10K", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        row = by_year[2025]
        assert row["assets"] == 500_000_000
        assert row["liabilities"] == 200_000_000
        assert row["stockholders_equity"] == 300_000_000
