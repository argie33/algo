"""Regression test for a duration-fact magnitude bug in
_aggregate_concepts_should_replace_entry() (utils/external/sec_statements_entry_resolution.py):

Live-verified 2026-09-10 via Universe Pharmaceuticals (UPC, CIK 0001809616) real SEC
companyfacts JSON: Revenues for start=2022-10-01/end=2023-09-30 has two independent, agreeing
prior 20-Fs (accn 0001213900-24-007745 filed 2024-01-30, accn 0001213900-25-036798 filed
2025-04-29, both val=$32,308,735, no frame) - then UPC's FY2025 20-F (accn
0001213900-26-009000, filed 2026-01-29) re-cites the SAME period as $32,308,735,000, a
filer-side 1000x decimals-tag error, now tagged frame="CY2023". The TKR-pattern duration-fact
frame-preference branch (the "else" branch of _aggregate_concepts_should_replace_entry, added
2026-08-31) had `should_replace = entry_has_frame` with NO magnitude-sanity check - unlike the
sibling instant-fact frame-preference branch, which got exactly this guard for the analogous
IPAR bug (see test_sec_statements_frame_magnitude_scale_guard_ipar_20260906.py). This let the
1000x outlier confidently win, corrupting downstream ps_ratio/ev_revenue for the whole
universe of symbols exhibiting this filer-side re-tagging-error shape, not just UPC.

Fixed by porting the same magnitude-sanity guard to the duration-fact frame-preference branch:
a frame-tagged replacement whose value differs from an ALREADY-STORED value by a ratio within
1% of a clean power of 10 is rejected.
"""

from utils.external.sec_income_statement import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0001809616"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


_UPC_REVENUE_ENTRIES = [
    {
        "start": "2022-10-01",
        "end": "2023-09-30",
        "val": 32_308_735,
        "accn": "0001213900-24-007745",
        "fy": 2023,
        "fp": "FY",
        "form": "20-F",
        "filed": "2024-01-30",
    },
    {
        "start": "2022-10-01",
        "end": "2023-09-30",
        "val": 32_308_735,
        "accn": "0001213900-25-036798",
        "fy": 2024,
        "fp": "FY",
        "form": "20-F",
        "filed": "2025-04-29",
    },
    {
        "start": "2022-10-01",
        "end": "2023-09-30",
        "val": 32_308_735_000,
        "accn": "0001213900-26-009000",
        "fy": 2025,
        "fp": "FY",
        "form": "20-F",
        "filed": "2026-01-29",
        "frame": "CY2023",
    },
]


class TestFrameMagnitudeScaleGuardDuration:
    def test_upc_rejects_1000x_frame_tagged_duration_outlier(self):
        facts = {"us-gaap": {"Revenues": _concept(_UPC_REVENUE_ENTRIES)}, "ifrs-full": {}}
        client = _FakeClient(facts)

        rows = get_income_statement(client, "UPC", period="annual")

        matching = [r for r in rows if r.get("revenues") in (32_308_735, 32_308_735_000)]
        assert matching, f"expected a row for the 2022-10-01..2023-09-30 period, got {rows!r}"
        assert all(r["revenues"] == 32_308_735 for r in matching), (
            f"Expected UPC's real revenue $32,308,735 for the FY2023 period, got "
            f"{[r['revenues'] for r in matching]!r} - a value of $32,308,735,000 means the "
            f"duration-fact frame-magnitude-scale-guard regression is back"
        )

    def test_genuine_frame_correction_without_round_power_of_ten_ratio_still_wins(self):
        """A REAL restatement (non-power-of-10 divergence) must still win via the pre-existing
        frame-preference rule - the new guard must not become a blanket "reject any frame'd
        duration-fact change"."""
        facts = {
            "us-gaap": {
                "Revenues": _concept(
                    [
                        {
                            "start": "2022-10-01",
                            "end": "2023-09-30",
                            "val": 32_308_735,
                            "accn": "0001213900-24-007745",
                            "fy": 2023,
                            "fp": "FY",
                            "form": "20-F",
                            "filed": "2024-01-30",
                        },
                        {
                            "start": "2022-10-01",
                            "end": "2023-09-30",
                            "val": 33_924_172,  # real ~5% restatement, not a power-of-10 error
                            "accn": "0001213900-25-036798",
                            "fy": 2024,
                            "fp": "FY",
                            "form": "20-F",
                            "filed": "2025-04-29",
                            "frame": "CY2023",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "UPC", period="annual")
        matching = [r for r in rows if r.get("revenues") is not None]
        assert any(r["revenues"] == 33_924_172 for r in matching)
