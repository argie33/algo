"""Regression test for the SKM currency-unit false positive in xbrl_us_crosscheck.py.

FIXED 2026-09-16 (/goal data-patrol sweep, SKM live-confirmed): XBRL US's fact-search endpoint
returns the raw filed value with no USD conversion. SK Telecom (SKM) reports in KRW, so its
`Assets` fact came back as ~30.5 trillion KRW while our own total_assets is USD-converted
(~$20.69B) - an apparent ~1370x divergence that is a currency-units mismatch, not a data bug.
`scripts/xbrl_us_crosscheck.py` now skips any XBRL US fact whose `unit.unit-of-measure` isn't
USD (or missing, for endpoints/fixtures that omit the field) before comparing magnitudes.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import scripts.xbrl_us_crosscheck as xbrl_us_crosscheck


class _FakeCursor:
    """Serves one row for the symbol-select query, then one row per _FIELDS lookup."""

    def __init__(self, our_value: float) -> None:
        self._our_value = our_value
        self._next_result: list[tuple[Any, ...]] = []

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> None:
        query_lower = query.lower()
        if "stock_symbols" in query_lower:
            self._next_result = [("SKM",)]
        elif "from annual_balance_sheet" in query_lower and "total_assets" in query_lower:
            self._next_result = [(2024, self._our_value)]
        else:
            self._next_result = []

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._next_result

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._next_result[0] if self._next_result else None

    def close(self) -> None:
        pass


def _run_total_assets_check(krw_fact_value: float, unit: str | None) -> dict[str, Any]:
    fake_cursor = _FakeCursor(our_value=20_691_394_648.69)
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor

    def fake_fact_search(symbol: str, concept: str, fiscal_year: int, fiscal_period: str = "Y") -> list[dict[str, Any]]:
        if concept != "Assets":
            return []
        fact: dict[str, Any] = {"fact.value": krw_fact_value}
        if unit is not None:
            fact["unit.unit-of-measure"] = unit
        return [fact]

    with (
        patch("utils.db.connection.get_db_connection", return_value=fake_conn),
        patch("utils.external.xbrl_us_client.fact_search", side_effect=fake_fact_search),
    ):
        return xbrl_us_crosscheck.run(limit=1, symbols_override=["SKM"], dry_run=True)


def test_non_usd_fact_is_not_flagged_as_a_divergence() -> None:
    # Real SKM Assets fact: 30,515,255,000,000 KRW - a real ~1370x apparent divergence
    # against our USD-converted value if compared directly, without the currency guard.
    summary = _run_total_assets_check(krw_fact_value=30_515_255_000_000.0, unit="KRW")
    total_assets_result = next(
        r for r in summary["results"] if r["check"] == "xbrl_us_independent_crosscheck_total_assets"
    )
    assert total_assets_result["severity"] == "info"
    assert total_assets_result["details"].get("flagged", 0) == 0


def test_usd_fact_is_still_compared_normally() -> None:
    # A genuine USD-denominated divergence must still be caught - the guard only excludes
    # non-USD units, it doesn't disable the check.
    summary = _run_total_assets_check(krw_fact_value=99_000_000_000.0, unit="USD")
    total_assets_result = next(
        r for r in summary["results"] if r["check"] == "xbrl_us_independent_crosscheck_total_assets"
    )
    assert total_assets_result["severity"] == "warn"
    assert total_assets_result["details"]["flagged"] == 1
    assert total_assets_result["details"]["examples"][0]["symbol"] == "SKM"


def test_missing_unit_field_is_still_compared() -> None:
    # Some responses/fixtures may omit unit.unit-of-measure entirely - don't silently drop
    # every comparison in that case, only reject an EXPLICITLY non-USD unit.
    summary = _run_total_assets_check(krw_fact_value=99_000_000_000.0, unit=None)
    total_assets_result = next(
        r for r in summary["results"] if r["check"] == "xbrl_us_independent_crosscheck_total_assets"
    )
    assert total_assets_result["severity"] == "warn"
