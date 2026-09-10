"""Regression test for the "Missing SEC/XBRL data" under-500 push, ANDG live-confirmed
2026-09-10.

_aggregate_concepts' has_annual_report_form/_max_annual_report_end guard (see
sec_statements_unit_context.py's own GM/DIS/WEC comments) withholds a 10-Q's premature
mid-year instant snapshot from the annual bucket once a concept has confirmed 10-K/20-F/40-F
history - but it tracked that history per raw XBRL concept name only. ANDG's real FY2025 10-K
tags bare "StockholdersEquity", while its FY2026 Q2 10-Q instead tags
"StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest" - a DIFFERENT concept
name that maps to the SAME "stockholders_equity" DB column. That concept has no 10-K history of
its own, so the guard never fired for it: its premature 10-Q snapshot sailed into the FY2026
bucket while Assets/LongTermDebt (same concept name in both filings) were correctly withheld -
an inconsistent partial row (one premature field present, siblings correctly absent) instead of
a clean "not yet confirmed" state.

Fix: `_aggregate_concepts` takes an optional `alias_groups` map (target_key -> canonical group
key) so sec_balance_sheet.py can tell it which concepts are known equity-family aliases for the
same downstream column; the guard's annual-report-form history is then computed per GROUP, not
per raw concept name. Purely additive - a target_key absent from the map (or with no group
history at all) behaves exactly as before.
"""

from utils.external.sec_balance_sheet import get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0002000000"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


class TestEquityAliasGroupWithholdsPrematureStubRow:
    def test_andg_shaped_equity_alias_switch_withheld_until_confirmed(self) -> None:
        facts = {
            "us-gaap": {
                # Real FY2025 10-K: Assets/LongTermDebt/StockholdersEquity all confirmed.
                "Assets": _concept(
                    [
                        {
                            "end": "2025-12-31",
                            "val": 565_140_000,
                            "filed": "2026-03-27",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-K",
                            "accn": "A",
                        },
                    ]
                ),
                "LongTermDebt": _concept(
                    [
                        {
                            "end": "2025-12-31",
                            "val": 350_085_000,
                            "filed": "2026-03-27",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-K",
                            "accn": "A",
                        },
                    ]
                ),
                "StockholdersEquity": _concept(
                    [
                        {
                            "end": "2025-12-31",
                            "val": -134_731_000,
                            "filed": "2026-03-27",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-K",
                            "accn": "A",
                        },
                    ]
                ),
                # FY2026 Q2 10-Q: Assets/LongTermDebt re-tagged (same concept names, so the
                # existing per-concept guard correctly withholds these premature snapshots).
                # But the equity fact switches to the "...IncludingNCI" concept instead of
                # bare "StockholdersEquity" - without the alias-group fix, this premature
                # value would leak into the FY2026 bucket unguarded.
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": _concept(
                    [
                        {
                            "end": "2026-06-30",
                            "val": 31_454_000,
                            "filed": "2026-08-12",
                            "fp": "Q2",
                            "fy": 2026,
                            "form": "10-Q",
                            "accn": "B",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "ANDG", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        # FY2025 (real 10-K year) is fully populated and unaffected.
        assert by_year[2025]["assets"] == 565_140_000
        assert by_year[2025]["long_term_debt"] == 350_085_000
        assert by_year[2025]["stockholders_equity"] == -134_731_000

        # FY2026's premature equity snapshot must be withheld, same as its Assets/LongTermDebt
        # siblings - not silently accepted just because it happened to switch concept names.
        # (get_balance_sheet() returns the raw, pre-field-mapping concept key at this layer.)
        fy2026 = by_year.get(2026, {})
        assert fy2026.get("stockholders_equity_including_portion_attributable_to_noncontrolling_interest") is None
        assert fy2026.get("assets") is None
        assert fy2026.get("long_term_debt") is None

    def test_unrelated_symbol_with_no_confirmed_history_is_unaffected(self) -> None:
        """A quarterly-only reporter with NO 10-K history at all for any equity alias must
        still get its 10-Q instant fact as the best-available annual data (same fallback-of-
        last-resort precedent the guard already carves out) - the alias-group widening must
        never newly reject a fact when no group member has annual-report history either."""
        facts = {
            "us-gaap": {
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": _concept(
                    [
                        {
                            "end": "2026-06-30",
                            "val": 900_000_000,
                            "filed": "2026-08-12",
                            "fp": "Q2",
                            "fy": 2026,
                            "form": "10-Q",
                            "accn": "C",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "NOHISTORY", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        # get_balance_sheet() returns the raw (pre-field-mapping) concept key here - the
        # "...IncludingNCI" -> "stockholders_equity" DB-column mapping happens one layer up,
        # in load_financial_statements.py's transform(), not tested at this layer.
        assert (
            by_year[2026]["stockholders_equity_including_portion_attributable_to_noncontrolling_interest"]
            == 900_000_000
        )
