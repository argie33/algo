"""Regression test for the 2026-09-09 fix in utils/external/sec_statements_entry_resolution.py's
`_aggregate_concepts_resolve_entry_period` (goal session: dedicated follow-up to the
net_income_not_reported bucket audit).

Live-confirmed via BACC (CIK 0002059654, real SEC companyfacts JSON): a genuine SPAC/de-SPAC
entity's first fiscal year after its business combination can be a real, audited stub under
330 days - BACC was incorporated 2025-02-10, and its real FY2025 10-K covers 2025-02-10 to
2025-12-31 (324 days), tagged form=10-K, fp=FY, fy=2025, frame=CY2025, val=2531400. The blanket
span<330 "Real single-quarter/partial-year data - not annual" rejection
(_aggregate_concepts_resolve_entry_period, added 2026-08-09 for the ORLY bug) had no way to tell
this apart from a real filer-side quarterly-fact-tagged-as-annual mistake, and discarded this
filer's only NetIncomeLoss fact entirely - the root cause of BACC/BACCR/BRR being stuck in the
"net_income_not_reported" bucket despite having a valid, on-file annual figure.

Fix: a span<330 entry is still accepted when form is a genuine primary annual-report form
(10-K/20-F/40-F), fp=="FY", and SEC's own "frame" field exactly confirms this entry as the
calendar year's aggregate ("CY<fy>") - a signal only ever assigned by SEC's frames API to a real
annual aggregate, never observed on a filer-side mistagged-quarterly fact in this codebase's
history. Deliberately narrow: does not touch the ORLY (form=10-Q, no frame)/AAT (form=10-Q,
fp="FY" but no frame)/BTCS (form=10-Q) mistagged-quarterly cases already covered by dedicated
tests, since none of those carry a frame-confirmed 10-K/20-F/40-F entry.
"""

from utils.external.sec_statements import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0002059654"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


class TestStubFiscalYearFrameConfirmedAccepted:
    def test_bacc_style_324_day_10k_fy_frame_confirmed_stub_accepted(self) -> None:
        facts = {
            "us-gaap": {
                "NetIncomeLoss": _concept(
                    [
                        # Real BACC-shaped entry: incorporated 2025-02-10, FY2025 10-K
                        # covers the 324-day stub first fiscal year, frame-confirmed by
                        # SEC as the CY2025 aggregate.
                        {
                            "start": "2025-02-10",
                            "end": "2025-12-31",
                            "val": 2531400,
                            "filed": "2026-03-15",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-K",
                            "frame": "CY2025",
                            "accn": "0002059654-26-000001",
                        },
                    ]
                ),
            },
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "BACC", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["net_income_loss"] == 2531400

    def test_short_span_10k_without_frame_still_rejected(self) -> None:
        # Guard against over-fixing: without SEC's frame confirmation, a short-span 10-K
        # entry is not distinguishable from a filer-side tagging mistake and must still
        # be rejected.
        facts = {
            "us-gaap": {
                "NetIncomeLoss": _concept(
                    [
                        {
                            "start": "2025-02-10",
                            "end": "2025-12-31",
                            "val": 2531400,
                            "filed": "2026-03-15",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-K",
                            "frame": None,
                            "accn": "0002059654-26-000001",
                        },
                    ]
                ),
            },
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "BACC", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert "net_income_loss" not in by_year.get(2025, {})

    def test_short_span_10q_with_frame_still_rejected(self) -> None:
        # Guard against over-fixing: a frame-confirmed short-span entry from a 10-Q (not
        # a genuine primary annual-report form) must still be rejected - the frame signal
        # is only trusted paired with a real 10-K/20-F/40-F.
        facts = {
            "us-gaap": {
                "NetIncomeLoss": _concept(
                    [
                        {
                            "start": "2025-02-10",
                            "end": "2025-12-31",
                            "val": 2531400,
                            "filed": "2026-03-15",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-Q",
                            "frame": "CY2025",
                            "accn": "0002059654-26-000001",
                        },
                    ]
                ),
            },
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "BACC", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert "net_income_loss" not in by_year.get(2025, {})
