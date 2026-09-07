"""Regression test for a balance-sheet magnitude bug in
_aggregate_concepts_should_replace_entry() (utils/external/sec_statements_entry_resolution.py):

Live-verified 2026-09-06 via Inter Parfums (IPAR, CIK 0000822663) real SEC companyfacts JSON:
CashAndCashEquivalentsAtCarryingValue for end=2021-12-31 has multiple candidate entries -
the ORIGINAL FY2021 10-K (filed 2022-03-01, val=$168,387,000) and three later 10-Qs plus one
10-K comparative period (filed 2022-2023, val=$159,613,000 each, no frame tag on any of them) -
then IPAR's FY2023 10-K (filed 2024-02-27) re-cites the SAME 2021-12-31 period as
$159,613,000,000, a filer-side 1000x decimals-tag error on IPAR's own part. SEC's frames API
happened to assign "CY2021Q4I" to THAT corrupted entry, not to any of the earlier, unanimous,
correct ones - so the existing frame-preference tiebreak (built for the PMT debt-maturity-
schedule case, see test_sec_statements_instant_fact_prefers_latest_end_date.py) confidently
replaced the correct ~$159.6M figure with a bogus $159.6B one, since it always trusts a
frame-tagged entry over a non-framed one unconditionally.

Fixed by adding a narrow magnitude-sanity check: a frame-tagged replacement whose value
differs from an ALREADY-STORED value by a ratio within 1% of a clean power of 10
(100x/1000x/10000x) is rejected - a real restatement essentially never moves a balance by an
exact round factor of 10, so this is a much stronger signal of a filer decimals-tag error than
of a genuine correction. Every other frame-vs-no-frame case (the overwhelming majority) is
unaffected - this guard only fires when BOTH a stored value already exists AND the ratio is a
near-exact power of 10.
"""

from utils.external.sec_balance_sheet import get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000822663"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


_IPAR_CASH_ENTRIES = [
    {
        "end": "2021-12-31",
        "val": 168_387_000,
        "accn": "0001753926-22-000273",
        "fy": 2021,
        "fp": "FY",
        "form": "10-K",
        "filed": "2022-03-01",
    },
    {
        "end": "2021-12-31",
        "val": 159_613_000,
        "accn": "0001753926-23-000213",
        "fy": 2022,
        "fp": "FY",
        "form": "10-K",
        "filed": "2023-02-28",
    },
    {
        "end": "2021-12-31",
        "val": 159_613_000_000,
        "accn": "0001753926-24-000405",
        "fy": 2023,
        "fp": "FY",
        "form": "10-K",
        "filed": "2024-02-27",
        "frame": "CY2021Q4I",
    },
]


class TestFrameMagnitudeScaleGuard:
    def test_ipar_rejects_1000x_frame_tagged_outlier(self):
        facts = {"us-gaap": {"CashAndCashEquivalentsAtCarryingValue": _concept(_IPAR_CASH_ENTRIES)}, "ifrs-full": {}}
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "IPAR", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2021]["cash_and_cash_equivalents_at_carrying_value"] == 159_613_000, (
            f"Expected IPAR's real FY2021 cash $159,613,000, got "
            f"{by_year[2021].get('cash_and_cash_equivalents_at_carrying_value')!r} - a value of $159,613,000,000 means "
            f"the frame-magnitude-scale-guard regression is back"
        )

    def test_genuine_frame_correction_without_round_power_of_ten_ratio_still_wins(self):
        """Sanity check: a REAL restatement (a frame-tagged value that diverges by a non-
        power-of-10 ratio, e.g. a 5% adjustment) must still win via the pre-existing frame-
        preference rule - the new guard must not become a blanket "reject any frame'd change"."""
        facts = {
            "us-gaap": {
                "CashAndCashEquivalentsAtCarryingValue": _concept(
                    [
                        {
                            "end": "2021-12-31",
                            "val": 168_387_000,
                            "accn": "0001753926-22-000273",
                            "fy": 2021,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2022-03-01",
                        },
                        {
                            "end": "2021-12-31",
                            "val": 159_613_000,  # real ~5% restatement, not a power-of-10 error
                            "accn": "0001753926-23-000213",
                            "fy": 2022,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2023-02-28",
                            "frame": "CY2021Q4I",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "IPAR", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2021]["cash_and_cash_equivalents_at_carrying_value"] == 159_613_000

    def test_no_stored_value_yet_still_accepts_frame_tagged_entry(self):
        """When there's no prior value to compare against (col not in row yet), the guard has
        nothing to check against and must not block the frame-tagged entry from being the
        first value stored."""
        facts = {
            "us-gaap": {
                "CashAndCashEquivalentsAtCarryingValue": _concept(
                    [
                        {
                            "end": "2021-12-31",
                            "val": 159_613_000_000,
                            "accn": "0001753926-24-000405",
                            "fy": 2023,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2024-02-27",
                            "frame": "CY2021Q4I",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "IPAR", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2021]["cash_and_cash_equivalents_at_carrying_value"] == 159_613_000_000
