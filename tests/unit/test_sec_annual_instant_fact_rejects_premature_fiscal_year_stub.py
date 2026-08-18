"""Regression test for a fiscal-year balance-sheet mis-selection bug in
_aggregate_concepts() (utils/external/sec_statements.py) - "no SEC data"/loader-audit
goal, 2026-08-18 continuation.

Live-verified via GM and DIS (both file normal 10-Ks every year): annual_balance_sheet had
a fiscal_year=2026 row (the current, not-yet-concluded fiscal year - today is 2026-08-18,
GM's FY2026 10-K won't file until ~Feb 2027) with total_assets/stockholders_equity
populated from a real 10-Q's mid-year instant snapshot (GM: Assets end=2026-06-30,
form=10-Q, val=$282.742B - the actual number on GM's Q2 2026 balance sheet), while
long_term_debt stayed NULL because no 10-Q that quarter re-tagged that concept. Real,
complete FY2025 data (long_term_debt=$131.574B, confirmed via GM's real SEC companyfacts
JSON) already existed one fiscal year back, but every "ORDER BY fiscal_year DESC LIMIT 1"
downstream consumer (loaders/load_value_quality_growth_metrics.py) picked the incomplete
FY2026 stub instead - a single root cause behind a large share of "missing_sec_data" across
quality_metrics/value_metrics (debt_to_equity, interest_coverage, total_debt, roic_pct).

Instant (point-in-time) facts have no "start" date, so they're exempt from the
duration-based span_days filter (correctly - a 10-Q's "as of" balance is a real, valid
snapshot). The existing instant-fact "prefer latest end date" tie-break
(test_sec_statements_instant_fact_prefers_latest_end_date.py) already established that only
a true fiscal-year-end snapshot should win WITHIN a single (fiscal_year, "FY") bucket - this
closes the related gap where a 10-Q's mid-year snapshot seeds an entirely NEW, premature
bucket for a fiscal year whose 10-K hasn't been filed yet, since period_year is derived
independently per-entry from the fact's own end date.

Fix: an instant fact sourced from a 10-Q/6-K is rejected during annual extraction whenever
this concept has ANY real 10-K/20-F/40-F history at all. Quarterly-only reporters (no
annual-report form ever, e.g. EE) are unaffected - their 10-Q instant facts remain the only
available annual data, same fallback-of-last-resort precedent as _PRIMARY_STATEMENT_FORMS.
"""

from utils.external.sec_statements import get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0001467858"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


class TestPrematureFiscalYearStubRejected:
    def test_midyear_10q_snapshot_does_not_create_new_annual_bucket(self):
        # GM-shaped data: a real, complete FY2025 10-K exists. A later Q2 2026 10-Q reports
        # a real mid-year Assets snapshot, but with no matching long_term_debt for that
        # date - the premature "2026" bucket must not appear at all, since the 10-K for
        # fiscal_year 2026 doesn't exist yet.
        facts = {
            "us-gaap": {
                "Assets": _concept(
                    [
                        {
                            "end": "2025-12-31",
                            "val": 281_284_000_000,
                            "filed": "2026-02-04",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-K",
                        },
                        {
                            "end": "2026-06-30",
                            "val": 282_742_000_000,
                            "filed": "2026-07-21",
                            "fp": "Q2",
                            "fy": 2026,
                            "form": "10-Q",
                        },
                    ]
                ),
                "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities": _concept(
                    [
                        {
                            "end": "2025-12-31",
                            "val": 131_574_000_000,
                            "filed": "2026-02-04",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-K",
                        },
                        # No 2026 entry for this concept - not re-tagged in the Q2 10-Q.
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "GM", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert 2026 not in by_year, (
            "a 10-Q's mid-year instant snapshot must not seed a premature annual bucket "
            "when a real 10-K history exists for this concept"
        )
        assert by_year[2025]["assets"] == 281_284_000_000
        assert (
            by_year[2025]["long_term_debt_and_capital_lease_obligations_including_current_maturities"]
            == 131_574_000_000
        )

    def test_quarterly_only_reporter_still_gets_10q_instant_fact(self):
        # A filer with NO 10-K/20-F/40-F history at all for this concept (e.g. EE-style
        # quarterly-only reporter) must still get its 10-Q instant fact - this is the only
        # annual data available for them.
        facts = {
            "us-gaap": {
                "Assets": _concept(
                    [
                        {
                            "end": "2026-06-30",
                            "val": 50_000_000,
                            "filed": "2026-07-21",
                            "fp": "Q2",
                            "fy": 2026,
                            "form": "10-Q",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "EE", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2026]["assets"] == 50_000_000

    def test_10k_present_for_same_concept_and_year_still_wins(self):
        # Sanity check: when a real 10-K entry DOES exist for the current fiscal year, it
        # must still be accepted normally (this fix only rejects 10-Q entries, never 10-K).
        facts = {
            "us-gaap": {
                "Assets": _concept(
                    [
                        {
                            "end": "2025-12-31",
                            "val": 281_284_000_000,
                            "filed": "2026-02-04",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-K",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "GM", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["assets"] == 281_284_000_000
