"""Regression test for a directionality bug in the frame_magnitude_scale_guard
(utils/external/sec_statements_entry_resolution.py's _aggregate_concepts_should_replace_entry):
the guard added for UPC (see test_sec_statements_frame_magnitude_scale_guard_duration_upc_20260910.py)
unconditionally blocked ANY frame-tagged replacement that was a clean power-of-10 away from the
existing row value, implicitly assuming the EXISTING (arrived-first) value is always correct
and a LATER power-of-10-scaled entry is always the corruption.

That assumption is backwards for a filer whose FIRST ("home") filing is itself the one with
the typo, later silently self-corrected in a subsequent filing's own frame-tagged comparative
column - live-verified via PagSeguro (PAGS, CIK 0001712807) real SEC companyfacts JSON:
PAGS's FY2023 20-F (accn 0001628280-24-018744, filed 2024-04-29) mistags
WeightedAverageShares for 2023-01-01..2023-12-31 as 321,806,480,000 (3 extra zeros, no frame).
PagSeguro's OWN NEXT 20-F (accn 0001628280-25-020406, filed 2025-04-29) re-cites the SAME
period as its own prior-year comparative with the CORRECT value, 321,806,480, now WITH
frame="CY2023" - the unconditional block silently kept the wrong (larger) value forever
instead of accepting the filer's own later correction.

Fixed by making the guard direction-aware: when the power-of-ten pattern is detected, prefer
whichever value is SMALLER in magnitude, regardless of which one arrived first or which one
already occupies the row - every documented instance of this bug class in this codebase
(IPAR/UPC/MKZR/CCU/PAGS) has the smaller value be correct, since a filer/filing-agent
decimals-tag error manifests as spurious zeros being ADDED, never removed.
"""

from utils.external.sec_income_statement import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0001712807"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"shares": entries}}


_PAGS_WEIGHTED_AVERAGE_SHARES_ENTRIES = [
    {
        "start": "2023-01-01",
        "end": "2023-12-31",
        "val": 321_806_480_000,
        "accn": "0001628280-24-018744",
        "fy": 2022,
        "fp": "FY",
        "form": "20-F",
        "filed": "2024-04-29",
    },
    {
        "start": "2023-01-01",
        "end": "2023-12-31",
        "val": 321_806_480,
        "accn": "0001628280-25-020406",
        "fy": 2024,
        "fp": "FY",
        "form": "20-F",
        "filed": "2025-04-29",
        "frame": "CY2023",
    },
]


class TestFrameMagnitudeScaleGuardDirectionAware:
    def test_pags_accepts_filers_own_later_correction_over_earlier_buggy_home_filing(self):
        facts = {
            "ifrs-full": {"WeightedAverageShares": _concept(_PAGS_WEIGHTED_AVERAGE_SHARES_ENTRIES)},
            "us-gaap": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "PAGS", period="annual")

        matching = [
            r
            for r in rows
            if r.get("weighted_average_number_of_shares_outstanding_basic") in (321_806_480, 321_806_480_000)
        ]
        assert matching, f"expected a row for the 2023-01-01..2023-12-31 period, got {rows!r}"
        assert all(r["weighted_average_number_of_shares_outstanding_basic"] == 321_806_480 for r in matching), (
            "Expected PagSeguro's own later-corrected share count (321,806,480), got "
            f"{[r['weighted_average_number_of_shares_outstanding_basic'] for r in matching]!r} - "
            "the directionality fix regressed"
        )

    def test_ipar_shaped_case_still_rejects_the_later_corruption(self):
        """The ORIGINAL IPAR/UPC direction (correct value arrives first, a LATER filing
        introduces a power-of-10 corruption) must still be rejected - this fix must not flip
        into blindly always preferring whichever value arrives later."""
        facts = {
            "us-gaap": {
                "Revenues": _concept(
                    [
                        {
                            "start": "2022-01-01",
                            "end": "2022-12-31",
                            "val": 32_308_735,
                            "accn": "0001213900-23-007745",
                            "fy": 2022,
                            "fp": "FY",
                            "form": "20-F",
                            "filed": "2023-01-30",
                        },
                        {
                            "start": "2022-01-01",
                            "end": "2022-12-31",
                            "val": 32_308_735_000,
                            "accn": "0001213900-26-009000",
                            "fy": 2025,
                            "fp": "FY",
                            "form": "20-F",
                            "filed": "2026-01-29",
                            "frame": "CY2022",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "PAGS", period="annual")
        matching = [r for r in rows if r.get("revenues") in (32_308_735, 32_308_735_000)]
        assert matching
        assert all(r["revenues"] == 32_308_735 for r in matching), (
            f"Expected the smaller (correct) value to win regardless of arrival order, got "
            f"{[r['revenues'] for r in matching]!r}"
        )
