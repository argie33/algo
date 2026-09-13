"""Regression test for a revenue-extraction bug fixed via a new post-processing fallback,
_null_abandoned_revenues_concept_when_asc606_supersedes (utils/external/
sec_income_statement_fallbacks.py):

Live-confirmed via IONQ (IonQ, de-SPAC 2021): "Revenues" was tagged with a real-looking but
actually wildly wrong figure (~$1.235B, presumably a frozen/leftover value from the SPAC
shell's own pre-merger accounts) for FY2022, then never tagged again in any filing after
IonQ's FY2022 10-K - meanwhile RevenueFromContractWithCustomerExcludingAssessedTax continues
with real, small, growing figures through IonQ's most recent 10-K, a gap of almost 3 years.
Because the frozen figure is LARGER than the real ASC-606 figure,
asc606_existing_value_outranks_candidate's "a real consolidated total is never smaller than a
genuine sub-line of itself" guard (correct for CHTR/HTLD/ANDE, where "Revenues" is still
actively filed) incorrectly protected the frozen, abandoned value from ever being superseded -
a ~111x overstatement.

Fix: null a "Revenues" value when its own concept has gone durably silent (no filing in the
`_ABANDONED_REVENUES_CONCEPT_MIN_GAP_DAYS`+ window before a real ASC-606 successor concept's
own most recent filing) - deliberately NOT a magnitude/ratio rule (which produced 413 false
positives universe-wide when tried, mostly legitimate bank/conglomerate structural dualities
like CHTR's own ~55x revenue-vs-ASC-606-sub-line gap). CHTR-shaped cases (both concepts
still actively filed) must be completely unaffected.
"""

from utils.external.sec_income_statement import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict, cik: str = "0001824920"):
        self._facts = facts
        self._cik = cik

    def symbol_to_cik(self, symbol: str) -> str:
        return self._cik

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


class TestAbandonedRevenuesConceptIonq:
    def test_ionq_frozen_spac_era_revenues_nulled_in_favor_of_asc606(self):
        facts = {
            "us-gaap": {
                "Revenues": _concept(
                    [
                        {
                            "start": "2022-01-01",
                            "end": "2022-12-31",
                            "val": 1_235_000_000.0,
                            "filed": "2023-03-30",
                            "fp": "FY",
                            "fy": 2022,
                            "form": "10-K",
                        },
                    ]
                ),
                "RevenueFromContractWithCustomerExcludingAssessedTax": _concept(
                    [
                        {
                            "start": "2022-01-01",
                            "end": "2022-12-31",
                            "val": 11_131_000.0,
                            "filed": "2023-03-30",
                            "fp": "FY",
                            "fy": 2022,
                            "form": "10-K",
                        },
                        # Continues to be actively filed for years after "Revenues" went
                        # silent - the durable-abandonment signal this fix relies on.
                        {
                            "start": "2024-01-01",
                            "end": "2024-12-31",
                            "val": 43_073_000.0,
                            "filed": "2025-02-26",
                            "fp": "FY",
                            "fy": 2024,
                            "form": "10-K",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "IONQ", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2022].get("revenues") is None
        assert by_year[2022]["revenue_from_contract_with_customer_excluding_assessed_tax"] == 11_131_000.0

    def test_chtr_shaped_still_actively_filed_revenues_not_nulled(self):
        """A "Revenues" concept still tagged right alongside a smaller, real ASC-606
        sub-line in the filer's own most recent filing (CHTR/HTLD/ANDE shape) must be
        completely unaffected - the gap-based abandonment signal never fires for it."""
        facts = {
            "us-gaap": {
                "Revenues": _concept(
                    [
                        {
                            "start": "2025-01-01",
                            "end": "2025-12-31",
                            "val": 54_774_000_000.0,
                            "filed": "2026-01-30",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-K",
                        },
                    ]
                ),
                "RevenueFromContractWithCustomerExcludingAssessedTax": _concept(
                    [
                        {
                            "start": "2025-01-01",
                            "end": "2025-12-31",
                            "val": 993_000_000.0,
                            "filed": "2026-01-30",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-K",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts, cik="0001091667")

        rows = get_income_statement(client, "CHTR", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["revenues"] == 54_774_000_000.0
