"""Regression test for a quarterly balance-sheet key-collision bug in
_aggregate_concepts() (utils/external/sec_statements.py), found 2026-08-24 while
following up on the [[quarterly_balance_sheet_16_symbols_sparse_extraction_residual_found_20260822]]
memory's leftover residual.

Live-verified via CCLD's real companyfacts JSON: its Q1/Q2/Q3 2021 10-Qs each have exactly
ONE Assets fact - end=2020-12-31 (the FY2020 year-end comparative figure), tagged with THAT
FILING's own fp ('Q1'/'Q2'/'Q3' 2021), not the fact's true period. Because the accn-latest-
end-date filter (the 66249a0f9 fix) only drops a comparative echo when its OWN accn has a
LATER, genuine current-period fact to lose to, a filing whose XBRL tagging never re-tags its
own current-period value for a concept at all leaves that lone comparative fact untouched by
the filter - it then computes key=(2020, 'Q1'/'Q2'/'Q3') (period_year from its own end date,
fp from the filing's own quarter), colliding with the REAL Q1/Q2/Q3 2020 facts' identical
keys. The existing "prefer latest end date" instant-fact tiebreak then always preferred the
later end date (2020-12-31) over the genuinely correct one, silently overwriting the real
quarter. DB-confirmed: CCLD's quarterly_balance_sheet showed total_assets=$137,999,000
(the FY2020 figure) for ALL FOUR quarters of 2020, though the real Q1/Q2/Q3 values
($89.8M/$125.9M/$137.4M) were readily available from those quarters' own 10-Qs. A
universe-wide scan for this exact single-quarter-aliasing signature (one quarter's value
exactly equal to that year's Q4 value, others distinct) found 53 affected symbols, including
actively-traded large/mid-caps (BX, BN, AES), not just micro-caps.

Fix: always derive fp from the fact's own end date for December-fiscal-year-end instant
facts (already trusted elsewhere in this file as more reliable than any SEC period label),
not only as a fallback when the filer's own fp tag doesn't parse as Q1-Q4 at all. When the
filer's own fp already agrees with the derived quarter, this is a no-op; when it doesn't
(this bug class), the derived quarter is the fact's real period, so it correctly collides
with (rather than silently overwrites) the genuine same-period fact.
"""

from utils.external.sec_statements import get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0001582982"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


class TestComparativeOnlyAccnDoesNotAliasQuarter:
    def test_lone_comparative_fact_does_not_overwrite_real_quarter(self):
        facts = {
            "us-gaap": {
                "Assets": _concept(
                    [
                        # Real Q1 2020 10-Q (accn A): its own current-period value.
                        {
                            "end": "2020-03-31",
                            "val": 89_832_645,
                            "filed": "2020-05-14",
                            "fp": "Q1",
                            "fy": 2020,
                            "form": "10-Q",
                            "accn": "0001493152-20-008771",
                        },
                        # Real Q2 2020 10-Q (accn B): its own current-period value.
                        {
                            "end": "2020-06-30",
                            "val": 125_914_722,
                            "filed": "2020-08-13",
                            "fp": "Q2",
                            "fy": 2020,
                            "form": "10-Q",
                            "accn": "0001493152-20-015546",
                        },
                        # Real Q3 2020 10-Q (accn C): its own current-period value.
                        {
                            "end": "2020-09-30",
                            "val": 137_354_448,
                            "filed": "2020-11-09",
                            "fp": "Q3",
                            "fy": 2020,
                            "form": "10-Q",
                            "accn": "0001493152-20-020828",
                        },
                        # Real FY2020 10-K (accn D): establishes has_december_fiscal_year_end
                        # and is the genuine Q4/FY-end value.
                        {
                            "end": "2020-12-31",
                            "val": 137_999_000,
                            "filed": "2021-02-25",
                            "fp": "FY",
                            "fy": 2020,
                            "form": "10-K",
                            "accn": "0001493152-21-004837",
                        },
                        # BUG TRIGGER: Q1 2021 10-Q (accn E) never re-tags its own
                        # 2021-03-31 Assets value under this concept - the ONLY Assets fact
                        # in this accn is the FY2020 year-end comparative, tagged with this
                        # filing's own fp='Q1' (2021's Q1, not the fact's true period). It
                        # passes the accn-latest-end-date filter (nothing later in accn E to
                        # lose to).
                        {
                            "end": "2020-12-31",
                            "val": 137_999_000,
                            "filed": "2021-05-06",
                            "fp": "Q1",
                            "fy": 2021,
                            "form": "10-Q",
                            "accn": "0001493152-21-010632",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "CCLD", period="quarterly")
        by_year_quarter = {(r["fiscal_year"], r["fiscal_period"]): r for r in rows}

        # The real, distinct Q1-Q3 2020 values must survive, not be clobbered by the
        # comparative echo riding along in the Q1-2021 filing.
        assert by_year_quarter[(2020, "Q1")]["assets"] == 89_832_645
        assert by_year_quarter[(2020, "Q2")]["assets"] == 125_914_722
        assert by_year_quarter[(2020, "Q3")]["assets"] == 137_354_448
        assert by_year_quarter[(2020, "Q4")]["assets"] == 137_999_000

    def test_end_date_derived_fp_is_a_noop_when_filer_tag_already_agrees(self) -> None:
        """A normal, correctly-tagged filer (fp already agrees with the end-date-derived
        quarter) must be completely unaffected by this fix."""
        facts = {
            "us-gaap": {
                "Assets": _concept(
                    [
                        {
                            "end": "2024-03-31",
                            "val": 500_000_000,
                            "filed": "2024-05-01",
                            "fp": "Q1",
                            "fy": 2024,
                            "form": "10-Q",
                            "accn": "0000000000-24-000001",
                        },
                        {
                            "end": "2024-12-31",
                            "val": 600_000_000,
                            "filed": "2025-03-01",
                            "fp": "FY",
                            "fy": 2024,
                            "form": "10-K",
                            "accn": "0000000000-25-000001",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "TEST", period="quarterly")
        by_year_quarter = {(r["fiscal_year"], r["fiscal_period"]): r for r in rows}

        assert by_year_quarter[(2024, "Q1")]["assets"] == 500_000_000
        assert by_year_quarter[(2024, "Q4")]["assets"] == 600_000_000
