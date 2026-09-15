"""Regression test for the asymmetric-ordering gap in the frame-magnitude-scale-guard
(_aggregate_concepts_should_replace_entry(), utils/external/sec_statements_entry_resolution.py).

Live-verified 2026-09-15 via United-Guardian (UG, CIK 0000101778) real SEC companyfacts JSON:
RevenueFromContractWithCustomerIncludingAssessedTax for start=2019-01-01/end=2019-12-31 has two
facts - UG's original FY2019 10-K (accn 0001171843-20-002021, filed 2020-03-26, no frame,
val=$13,599,084 - the correct value, exactly matching the quarterly sum) and UG's own NEXT 10-K
(accn 0001171843-21-001963, filed 2021-03-22, frame="CY2019") re-citing the SAME period as
$13,599.084 - exactly 1000x SMALLER, a filer decimals-tag error on the re-citation.

Every other documented instance of this bug class (IPAR/UPC/MKZR/CCU/PAGS/DYAI/FENC, see the
sibling tests in this directory) has the frame-tagged replacement be the LARGER value, and the
existing guard already handled that direction correctly by checking magnitude whenever the
*incoming* entry carried the frame. But the guard's `if` condition required `entry_has_frame`
(or `entry.get("frame")` in the quarterly branch) to even run the magnitude check - if SEC's
companyfacts JSON array happens to deliver the frame-tagged (corrupted) entry FIRST, so it
becomes the row's already-stored value, and the correct non-framed entry arrives SECOND as
`entry`, then `entry_has_frame` is False and the whole magnitude check was skipped entirely -
the corrupted value then never gets corrected, regardless of how confidently a plain
power-of-10 ratio would flag it. This is the mirror image of every other test in this file:
same bug class, reversed processing order.

Fixed by dropping the `entry_has_frame`/`entry.get("frame")` requirement from the guard's outer
`if` in all three branches (instant-fact, quarterly, annual) - the magnitude check itself
(_is_power_of_ten_scale_outlier / _prefer_smaller_power_of_ten_value) was already symmetric and
order-independent; only the gate guarding entry into it was one-sided.
"""

from utils.external.sec_income_statement import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000101778"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


class TestFrameMagnitudeScaleGuardReversedOrder:
    def test_ug_corrects_1000x_frame_tagged_duration_outlier_processed_first(self):
        """The corrupted frame-tagged entry appears FIRST in the source array (so it becomes
        the row's initial value) and the correct non-framed entry arrives SECOND - the reverse
        of the UPC/IPAR test fixtures, where the corrupted entry always arrives last."""
        facts = {
            "us-gaap": {
                "RevenueFromContractWithCustomerIncludingAssessedTax": _concept(
                    [
                        {
                            "start": "2019-01-01",
                            "end": "2019-12-31",
                            "val": 13_599.084,
                            "accn": "0001171843-21-001963",
                            "fy": 2020,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2021-03-22",
                            "frame": "CY2019",
                        },
                        {
                            "start": "2019-01-01",
                            "end": "2019-12-31",
                            "val": 13_599_084,
                            "accn": "0001171843-20-002021",
                            "fy": 2019,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2020-03-26",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "UG", period="annual")

        field = "revenue_from_contract_with_customer_including_assessed_tax"
        matching = [r for r in rows if r.get(field) in (13_599_084, 13_599.084)]
        assert matching, f"expected a row for the 2019-01-01..2019-12-31 period, got {rows!r}"
        assert all(r[field] == 13_599_084 for r in matching), (
            f"Expected UG's real revenue $13,599,084 for the FY2019 period, got "
            f"{[r[field] for r in matching]!r} - a value of $13,599.084 means the "
            f"asymmetric-ordering frame-magnitude-scale-guard regression is back"
        )
