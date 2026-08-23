"""Regression test for a real EPS fallback gap in get_income_statement()
(utils/external/sec_statements.py) - "insufficient_history" eps_growth audit,
pre-real-money data-integrity review, 2026-08-23.

Live-confirmed via TV (Grupo Televisa)'s real SEC companyfacts JSON: tags ONLY
DilutedEarningsLossPerShareFromContinuingOperations and
...FromDiscontinuedOperations (IAS 33.68's required split for filers with discontinued
operations) - never a combined BasicEarningsLossPerShare/DilutedEarningsLossPerShare
concept, and no Basic-shaped EPS concept in any form. annual_income_statement.earnings_per_share
was NULL for every fiscal year despite 10+ years of real revenue/net_income already on
file, wrongly presenting downstream as growth_metrics eps_growth_5y/3y/1y
"insufficient_history" for a well-covered filer (real values live-confirmed: FY2022
continuing=-0.03, discontinued=0.17 MXN/shares).

Fix: the four *FromContinuingOperations/*FromDiscontinuedOperations concepts (Basic and
Diluted) are fetched as fallback-only inputs and summed by
_fill_earnings_per_share_from_continuing_discontinued_split() - same "fallback-only, sum
two real parts, never overwrite a real combined value" pattern as
_fill_long_term_debt_from_noncurrent_current_split. Diluted also falls back into the
basic-only "earnings_per_share_basic" key (downstream field_mapping's sole source for the
earnings_per_share column growth_metrics reads) when a filer tags no Basic-shaped EPS
concept at all.
"""

from typing import Any

from utils.external.sec_statements import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000912892"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(year: int, val: float, filed: str, form: str = "20-F") -> dict[str, Any]:
    return {"end": f"{year}-12-31", "val": val, "filed": filed, "fp": "FY", "fy": year, "form": form}


class TestEarningsPerShareContinuingDiscontinuedSplitFallback:
    def test_tv_shaped_diluted_only_split_summed_and_falls_back_to_basic(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "DilutedEarningsLossPerShareFromContinuingOperations": {
                    "units": {"USD/shares": [_entry(2022, -0.03, "2023-04-28")]}
                },
                "DilutedEarningsLossPerShareFromDiscontinuedOperations": {
                    "units": {"USD/shares": [_entry(2022, 0.17, "2023-04-28")]}
                },
            },
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "TV", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2022]["earnings_per_share_diluted"] == 0.14
        # No Basic-shaped concept tagged at all - diluted fills in for basic rather than
        # leaving the column (which growth_metrics actually reads) permanently NULL.
        assert by_year[2022]["earnings_per_share_basic"] == 0.14
        assert "earnings_per_share_diluted_continuing" not in by_year[2022]
        assert "earnings_per_share_diluted_discontinued" not in by_year[2022]

    def test_continuing_only_no_discontinued_tag_still_fills(self) -> None:
        # Most filers most years have no discontinued operations at all - must still use
        # the continuing figure alone rather than staying NULL for lack of a 0 tag.
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "BasicEarningsLossPerShareFromContinuingOperations": {
                    "units": {"USD/shares": [_entry(2025, 1.25, "2026-03-01")]}
                },
            },
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "TEST", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["earnings_per_share_basic"] == 1.25

    def test_real_combined_concept_not_overwritten_by_split_fallback(self) -> None:
        # A filer reporting the standard combined BasicEarningsLossPerShare must keep that
        # value even if a stray Continuing/Discontinued split also exists for the same year.
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "BasicEarningsLossPerShare": {"units": {"USD/shares": [_entry(2025, 5.00, "2026-03-01")]}},
                "BasicEarningsLossPerShareFromContinuingOperations": {
                    "units": {"USD/shares": [_entry(2025, 999.0, "2026-03-01")]}
                },
            },
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "TEST2", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["earnings_per_share_basic"] == 5.00
