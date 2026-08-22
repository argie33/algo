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

    def test_frame_tagged_fact_wins_over_later_filed_schedule_reentry(self):
        """FIXED 2026-08-22 (live-verified PMT): a debt-maturity-schedule footnote entry can
        share the exact same (concept, end_date) as the real balance-sheet snapshot, AND get
        re-disclosed with an identical value in each subsequent year's 10-K/10-Q - so it can
        have a LATER filed date than the one real snapshot fact for that period, defeating the
        plain "latest filed wins" tiebreak even when end dates are identical. Live-confirmed
        via PMT's real companyfacts JSON: LongTermDebt end=2026-03-31 has 3 schedule re-entries
        (fy=2021/2022/2023, all val=$695M, no "frame" key) and 1 real snapshot fact (fy=2024,
        val=$1.497B, frame="CY2026Q1I") - the schedule entries' filed dates are chronologically
        earlier here, but even a later-filed schedule re-entry must not beat a frame-tagged
        fact. SEC's own "frame" key is only ever assigned to the single canonical,
        non-dimensional fact for a standardized period - never to a dimensional/footnote
        schedule entry - so it's the reliable signal, not filed-date."""
        facts = {
            "us-gaap": {
                "LongTermDebt": _concept(
                    [
                        {
                            "end": "2026-03-31",
                            "val": 695_000_000,  # stale schedule re-entry, filed LATER
                            "filed": "2026-08-01",
                            "fp": "Q1",
                            "fy": 2023,
                            "form": "10-Q",
                        },
                        {
                            "end": "2026-03-31",
                            "val": 1_497_385_000,  # real snapshot, filed earlier but frame-tagged
                            "filed": "2024-05-02",
                            "fp": "Q1",
                            "fy": 2024,
                            "form": "10-Q",
                            "frame": "CY2026Q1I",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "PMT", period="quarterly")

        assert len(rows) == 1
        assert rows[0]["long_term_debt"] == 1_497_385_000

    def test_comparative_fy_end_snapshot_does_not_clobber_real_quarter_snapshot(self):
        """FIXED 2026-08-22 (live-verified PMT): a 10-Q's comparative prior-fiscal-year-end
        balance (shown alongside the current quarter's own balance, for context) is tagged
        with THAT FILING's fp, not its own period - e.g. the real FY2022 year-end
        (end=2022-12-31) balance gets re-cited as the comparative figure in the FY2023 Q1
        10-Q, tagged fp='Q1'. Because period_year is derived from end date (2022) same as the
        real Q1-2022 fact, both land in the same (fiscal_year=2022, fp='Q1') bucket, and the
        instant "prefer latest end date" tiebreak then always preferred the comparative (Dec
        31 > Mar 31) - silently overwriting every real quarterly snapshot with that year's
        FY-end figure. Live-confirmed via PMT's real companyfacts JSON: quarterly_balance_sheet
        held an IDENTICAL total_assets value across Q1/Q2/Q3 of nearly every fiscal year
        2011-2024, impossible for an actively-financed mortgage REIT with fluctuating repo
        balances. Fix: within one filing (accn), only the latest-end-date fact for a concept
        is that filing's own current-period value - every other same-accn fact is a
        comparative echo, dropped regardless of what fp/fy it's mislabeled with."""
        facts = {
            "us-gaap": {
                "Assets": _concept(
                    [
                        # The real FY2022 year-end fact (from PMT's own FY2022 10-K, accn A).
                        {
                            "end": "2022-12-31",
                            "val": 13_921_564_000,
                            "filed": "2023-02-24",
                            "fp": "FY",
                            "fy": 2022,
                            "form": "10-K",
                            "accn": "0001564590-23-002430",
                        },
                        # The genuine Q1-2022 snapshot (from PMT's own Q1-2022 10-Q, accn B).
                        {
                            "end": "2022-03-31",
                            "val": 12_387_515_000,
                            "filed": "2022-05-06",
                            "fp": "Q1",
                            "fy": 2022,
                            "form": "10-Q",
                            "accn": "0001564590-22-018584",
                        },
                        # PMT's real Q1-2023 10-Q (accn C): its own current-period value...
                        {
                            "end": "2023-03-31",
                            "val": 15_357_229_000,
                            "filed": "2023-05-04",
                            "fp": "Q1",
                            "fy": 2023,
                            "form": "10-Q",
                            "accn": "0000950170-23-017766",
                        },
                        # ...plus the SAME accn C re-citing the FY2022 year-end as its
                        # comparative prior-year-end figure - tagged with accn C's own
                        # fp='Q1', not its true period, but NOT the max end date within
                        # accn C (2023-03-31 is), so the fix drops it.
                        {
                            "end": "2022-12-31",
                            "val": 13_921_564_000,
                            "filed": "2023-05-04",
                            "fp": "Q1",
                            "fy": 2023,
                            "form": "10-Q",
                            "accn": "0000950170-23-017766",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "PMT", period="quarterly")
        by_year_quarter = {(r["fiscal_year"], r["fiscal_period"]): r for r in rows}

        assert by_year_quarter[(2023, "Q1")]["assets"] == 15_357_229_000

        assert by_year_quarter[(2022, "Q1")]["assets"] == 12_387_515_000
