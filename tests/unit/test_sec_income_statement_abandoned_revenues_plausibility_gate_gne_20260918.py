"""Regression test for a 2026-09-18 fix (goal session: quarantine-backlog continuation) to
_null_abandoned_revenues_concept_when_asc606_supersedes (utils/external/
sec_income_statement_fallbacks.py) - the sibling of test_sec_income_statement_abandoned_
revenues_concept_ionq_20260913.py's fix, addressing a gap that fix left open.

Live-confirmed via GNE (Genie Energy, CIK 0001528356): "Revenues" is genuinely abandoned
(durably superseded by RevenueFromContractWithCustomerIncludingAssessedTax) starting FY2018,
same IonQ-shaped signal the 2026-09-13 fix correctly detects. But for FY2018 specifically, the
ONLY IncludingAssessedTax fact available is a $170,000 anomaly that exists ONLY in the FY2019
10-K's comparative column (never in GNE's own FY2018 10-K) - not a real restated total, a
stray/inconsistent comparative-column fact - while GNE's real FY2018 revenue (confirmed via
its own FY2018 10-K's "Revenues" tag, and via the sum of GNE's own real quarterly filings) is
$280,309,000. Unconditionally popping "revenues" for every row let this ~1,649x-too-small
value become GNE's stored annual revenue, then quarantined the symbol once
quarterly_revenue_sum_vs_annual_extreme caught the resulting >10x mismatch.

Fix: only pop a row's "revenues" when the successor concept's OWN value for that specific row
is not implausibly tiny (>=5%) relative to the median of this same symbol's OTHER "revenues"
values - a robust per-filer scale reference computed before any row is popped. A genuine
ASC-606 transition (IONQ's own real ~$1.235B -> ~$11M drop, a real business-model change) can
still shrink revenue by orders of magnitude when it happens consistently across the whole
history (IONQ has no "other revenues" year to compare against, so the guard doesn't apply);
only a one-off anomaly surrounded by normal-scale years on both sides is rejected.
"""

from utils.external.sec_income_statement import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict, cik: str = "0001528356"):
        self._facts = facts
        self._cik = cik

    def symbol_to_cik(self, symbol: str) -> str:
        return self._cik

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


def _fy_entry(fy: int, val: float, filed: str, frame: str | None = None) -> dict:
    entry = {
        "start": f"{fy}-01-01",
        "end": f"{fy}-12-31",
        "val": val,
        "filed": filed,
        "fp": "FY",
        "fy": fy,
        "form": "10-K",
    }
    if frame:
        entry["frame"] = frame
    return entry


class TestAbandonedRevenuesPlausibilityGate:
    def test_gne_shaped_anomalous_successor_year_keeps_real_revenues_value(self) -> None:
        facts = {
            "us-gaap": {
                "Revenues": _concept(
                    [
                        _fy_entry(2016, 212_112_000.0, "2017-03-10"),
                        _fy_entry(2017, 264_202_000.0, "2018-03-15"),
                        _fy_entry(2018, 280_309_000.0, "2019-03-19"),
                    ]
                ),
                "RevenueFromContractWithCustomerIncludingAssessedTax": _concept(
                    [
                        # The ONLY FY2018 fact for this concept: a stray comparative-column
                        # anomaly from the FY2019 10-K, ~1,649x too small.
                        _fy_entry(2018, 170_000.0, "2020-03-16", frame="CY2018"),
                        _fy_entry(2019, 315_291_000.0, "2021-03-16"),
                        _fy_entry(2020, 356_930_000.0, "2022-03-01"),
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "GNE", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        # The real, correct FY2018 total must survive - not the 170,000 anomaly.
        assert by_year[2018]["revenues"] == 280_309_000.0
        # FY2019/2020 (no reference distortion - the successor value there is the real,
        # trend-consistent total) still correctly fall through to the successor concept.
        assert by_year[2019]["revenue_from_contract_with_customer_including_assessed_tax"] == 315_291_000.0

    def test_ionq_shaped_single_year_still_unconditionally_nulled(self) -> None:
        """No sanity-check regression: a symbol with only ONE fiscal year of "revenues" data
        (no other-year reference to compare against) falls through to the original
        unconditional-pop behavior - same assertion as the 2026-09-13 IonQ regression test."""
        facts = {
            "us-gaap": {
                "Revenues": _concept([_fy_entry(2022, 1_235_000_000.0, "2023-03-30")]),
                "RevenueFromContractWithCustomerExcludingAssessedTax": _concept(
                    [
                        _fy_entry(2022, 11_131_000.0, "2023-03-30"),
                        _fy_entry(2024, 43_073_000.0, "2025-02-26"),
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts, cik="0001824920")

        rows = get_income_statement(client, "IONQ", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2022].get("revenues") is None
        assert by_year[2022]["revenue_from_contract_with_customer_excluding_assessed_tax"] == 11_131_000.0
