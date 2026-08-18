"""Regression test for a silent-corruption bug in _aggregate_concepts()
(utils/external/sec_statements.py):

SEC's mandatory Pay vs Performance table (Item 402(v), required in every proxy since 2023)
re-tags NetIncomeLoss in XBRL using the table's display units (thousands), but many filers/
filing agents omit the corresponding XBRL scale factor - so the tagged fact is the raw table
number, 1000x too small, instead of true dollars. DEF 14A proxies are filed after the 10-K
for the same fiscal year, so the old date-only "latest filing wins" tie-break let this broken
value silently overwrite the correct 10-K figure. Live-confirmed via real companyfacts JSON:
FDX FY2026 10-K NetIncomeLoss=$4,433,000,000 vs its same-period DEF 14A entry=$4,433.

The fix ranks primary financial-statement forms (10-K/10-Q and foreign-filer equivalents)
above all other forms regardless of filing date, while still preferring a later primary form
(e.g. a genuine 10-K/A restatement) over an earlier one, and still falling back to a
non-primary form as a last resort when no primary-form entry exists for that period at all
(proxy-only reporters like EE have no 10-K net income).
"""

from utils.external.sec_statements import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000000000"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


def _entry(year: int, val: float, filed: str, form: str = "10-K") -> dict:
    return {"end": f"{year}-12-31", "val": val, "filed": filed, "fp": "FY", "fy": year, "form": form}


class TestPrimaryFormOutranksLaterNonPrimaryForm:
    def test_def14a_filed_after_10k_does_not_clobber_10k_net_income(self):
        facts = {
            "us-gaap": {
                "NetIncomeLoss": _concept(
                    [
                        _entry(2026, 4_433_000_000.0, "2026-07-20", form="10-K"),
                        # Same fiscal year, filed later, but from the proxy's Pay vs
                        # Performance table - 1000x too small due to a missing scale factor.
                        _entry(2026, 4_433.0, "2026-08-17", form="DEF 14A"),
                    ]
                ),
            },
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "FDX", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2026]["net_income_loss"] == 4_433_000_000.0

    def test_later_10ka_restatement_still_outranks_earlier_10k(self):
        facts = {
            "us-gaap": {
                "NetIncomeLoss": _concept(
                    [
                        _entry(2026, 4_433_000_000.0, "2026-07-20", form="10-K"),
                        _entry(2026, 4_500_000_000.0, "2026-09-01", form="10-K/A"),
                    ]
                ),
            },
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "FDX", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2026]["net_income_loss"] == 4_500_000_000.0

    def test_non_primary_form_still_used_as_last_resort_fallback(self):
        # Proxy-only reporter (e.g. EE) with no 10-K net income entry at all - the DEF 14A
        # value must still be accepted rather than leaving net_income NULL.
        facts = {
            "us-gaap": {
                "NetIncomeLoss": _concept([_entry(2026, 12_345.0, "2026-08-17", form="DEF 14A")]),
            },
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "EE", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2026]["net_income_loss"] == 12_345.0
