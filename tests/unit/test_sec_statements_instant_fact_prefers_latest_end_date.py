"""Regression test for a fiscal-year balance-sheet mis-selection bug in
_aggregate_concepts() (utils/external/sec_statements.py):

Live-verified 2026-08-18 via RIGL's dashboard (Institutional/Quality panel): stored ROE
showed +1976.8%, and roe_trend/fcf_growth_yoy were both stuck on
"insufficient_prior_year_data". Root cause traced to annual_balance_sheet.stockholders_equity
for fiscal_year=2025: DB held $18,567,000, but SEC's real FY2025 10-K reports
StockholdersEquity of $391,480,000 as of the true year-end (2025-12-31). $18,567,000 is
actually RIGL's Q1 2025 comparative figure (end=2025-03-31), re-cited verbatim in later 10-Qs'
XBRL context (including the same 10-Q that also carries the real 2025-12-31 figure).

Instant/point-in-time balance-sheet facts have no "start" date, so they were exempted from
the duration-based span_days filter (correctly - an "as of" balance is valid regardless of
duration). But when two instant facts for DIFFERENT actual dates both bucket into the same
(fiscal_year, "FY") key and happen to share the same "filed" date (routine - both facts often
come from the same filing's XBRL context), "keep latest filed" degenerates to "keep whichever
was iterated last" - order-dependent, not correctness-driven. The Q1 snapshot won, silently
replacing the real year-end value. Downstream: net_income($367.0M) / equity($18.567M) =
1976.75% (matches the live-observed dashboard value) instead of the real ~94%.

Fix: for instant facts specifically, prefer the entry whose end date is latest (closest to
the true fiscal year end) before falling back to filed-date as a tiebreak. Duration facts
(has "start") are unaffected.
"""

from utils.external.sec_statements import get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0001034842"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


class TestInstantFactPrefersLatestEndDate:
    def test_q1_comparative_snapshot_does_not_beat_real_fiscal_year_end_value(self):
        # Real RIGL-shaped data: both facts filed on the same date (both cited in the same
        # 10-Q's XBRL context), the Q1 comparative snapshot appearing AFTER the real FY-end
        # fact in list order - exactly the ordering that triggered the live bug.
        facts = {
            "us-gaap": {
                "StockholdersEquity": _concept(
                    [
                        {
                            "end": "2025-12-31",
                            "val": 391_480_000,
                            "filed": "2026-08-04",
                            "fp": "Q2",
                            "fy": 2026,
                            "form": "10-Q",
                        },
                        {
                            "end": "2025-03-31",
                            "val": 18_567_000,
                            "filed": "2026-08-04",
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

        rows = get_balance_sheet(client, "RIGL", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["stockholders_equity"] == 391_480_000

    def test_later_filed_correction_still_wins_when_end_dates_match(self):
        """Two instant facts for the SAME end date (a genuine restatement) must still use
        filed-date as the tiebreak - the end-date preference must not break normal
        restatement handling."""
        facts = {
            "us-gaap": {
                "StockholdersEquity": _concept(
                    [
                        {
                            "end": "2024-12-31",
                            "val": 100_000_000,
                            "filed": "2025-03-01",
                            "fp": "FY",
                            "fy": 2024,
                            "form": "10-K",
                        },
                        {
                            "end": "2024-12-31",
                            "val": 105_000_000,  # restated, filed later
                            "filed": "2025-06-01",
                            "fp": "FY",
                            "fy": 2024,
                            "form": "10-K/A",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "TEST", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2024]["stockholders_equity"] == 105_000_000
