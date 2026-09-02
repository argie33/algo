"""Regression test for a phantom-fiscal-year bug in the Jan-1-10-crossing correction in
_aggregate_concepts() (utils/external/sec_statements.py).

test_sec_statements_fiscal_year_end_crosses_january.py already covers the base case: a
52/53-week fiscal year whose end date lands in the first 10 days of January gets relabeled
to the earlier calendar year using the entry's own SEC-tagged `fy` field. This test covers
two ways a same-concept ECHO of that same real fact - not the fact's own home filing - can
defeat that correction and create a phantom bucket for the year AFTER the real one:

1. A DEF 14A proxy statement restating prior years' NetIncomeLoss for its compensation-
   discussion table carries fy=None/fp=None (no SEC period label at all). Since fy isn't an
   int, the correction previously no-op'd entirely, leaving the entry's naive (one-year-too-
   late) end-date-derived bucket - a phantom fiscal year seeded with only whatever the proxy
   restates (usually just net income), while the real, complete row sits one bucket back.
   Live-confirmed via FLO (Flowers Foods) and EXPO (Exponent Inc)'s real DEF 14A filings.

2. A LATER 10-K's own prior-year comparative column for the same fact carries fy=<that LATER
   filing's own year>, not the fact's true period - the general "SEC tags ALL periods in a
   10-K with fy=FILING_YEAR" behavior already documented elsewhere in this file for the non-
   crossing case applies inside the Jan-crossing window too. This is worse than case 1: since
   fy already looks like a valid int, it doesn't even reach the "fy is missing" branch - it
   just fails the `fy == period_year - 1` check and silently collides INTO the real next
   fiscal year's own bucket (same period_year, same form, often the same filed date), able to
   overwrite the real value depending on iteration order alone. Live-confirmed via EXPO's
   FY2025 10-K, which echoes FY2024's real net income ($109,002,000) under fy=2025.

Fix: resolve fy for an entry landing in the Jan-crossing window from whichever entry for this
same concept+(start, end, val) was filed EARLIEST, not from the entry's own bare fy field. A
fact's earliest-filed appearance is always its own home filing (correctly fy-tagged for its
own period); every later echo inherits its own filing's fy/no-fy instead, which is not
trustworthy for this purpose - applied unconditionally, not just when the entry's own fy is
missing, so case 2's misleading-but-present fy is overridden too.
"""

from utils.external.sec_statements import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0001128928"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


class TestJanCrossingComparativeEchoPhantomYear:
    def test_def14a_fy_none_echo_does_not_create_phantom_year(self):
        # Real FLO-shaped data: FY2025 10-K (end 2026-01-03, fy=2025, correctly relabeled to
        # 2025 by the base correction) plus a DEF 14A proxy echo of the identical fact with
        # fy=None/fp=None, filed later. Before the fix, the proxy echo's naive period_year
        # (2026) survived uncorrected, creating a phantom fiscal_year=2026 bucket containing
        # only net_income_loss.
        facts = {
            "us-gaap": {
                "NetIncomeLoss": _concept(
                    [
                        {
                            "start": "2024-12-29",
                            "end": "2026-01-03",
                            "val": 83_825_000.0,
                            "filed": "2026-02-25",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-K",
                        },
                        {
                            "start": "2024-12-29",
                            "end": "2026-01-03",
                            "val": 83_825_000.0,
                            "filed": "2026-04-14",
                            "fp": None,
                            "fy": None,
                            "form": "DEF 14A",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "FLO", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert 2026 not in by_year, "DEF 14A echo must not seed a phantom fiscal_year=2026 bucket"
        assert by_year[2025]["net_income_loss"] == 83_825_000.0

    def test_later_10k_comparative_echo_with_misleading_fy_does_not_clobber_real_year(self):
        # Real EXPO-shaped data: FY2024's real 10-K (end 2025-01-03, fy=2024) plus FY2025's
        # own 10-K, which tags BOTH its own current-year fact (end 2026-01-02, fy=2025 -
        # correctly relabels to 2025) AND a prior-year comparative echo of FY2024's identical
        # value (end 2025-01-03, val matches FY2024's own figure) - but that comparative
        # echo carries fy=2025 (its OWN filing's year, not 2024, the fact's true period).
        # Before the fix this echo's fy (2025) failed the `fy == period_year - 1` check
        # (2025 != 2024) and kept its naive period_year=2025, colliding with and - depending
        # on iteration order - overwriting FY2025's own real value.
        facts = {
            "us-gaap": {
                "NetIncomeLoss": _concept(
                    [
                        {
                            "start": "2023-12-30",
                            "end": "2025-01-03",
                            "val": 109_002_000.0,
                            "filed": "2025-02-28",
                            "fp": "FY",
                            "fy": 2024,
                            "form": "10-K",
                        },
                        {
                            "start": "2025-01-04",
                            "end": "2026-01-02",
                            "val": 106_009_000.0,
                            "filed": "2026-02-27",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-K",
                        },
                        # Prior-year comparative echo of the FY2024 fact, embedded in the
                        # FY2025 10-K - same (start, end, val) as the real FY2024 entry above,
                        # but mistagged fy=2025 (the FY2025 filing's own year).
                        {
                            "start": "2023-12-30",
                            "end": "2025-01-03",
                            "val": 109_002_000.0,
                            "filed": "2026-02-27",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-K",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "EXPO", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2024]["net_income_loss"] == 109_002_000.0
        assert by_year[2025]["net_income_loss"] == 106_009_000.0, (
            "FY2025's own real value must not be clobbered by FY2024's comparative echo"
        )
