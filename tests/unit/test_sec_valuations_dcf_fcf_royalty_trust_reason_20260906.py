"""Regression test (2026-09-06, goal: "SEC/XBRL missing data to zero" sweep, comprehensive
RIC-gap scan follow-up): sec_valuations.dcf_fcf_unavailable_reason never distinguished an oil
royalty trust (SIC 6792 - NRT/MTR/CRT/PBT/SBR/SJT, files a "Statement of Distributable Income"
with no conventional cash-flow-statement concepts to tag at all) from a generic missing-cash-
flow-data gap - same root fact already fixed for the RIC case in
test_sec_valuations_dcf_fcf_ric_reason_20260905.py, and already established for quality_metrics.
fcf_margin/value_metrics.fcf_yield's own royalty-trust blocks in vqg_quality.py/vqg_value.py.

Unlike the RIC/unsupported-currency checks, this one is a pure symbol-membership check (no DB
query - only 6 royalty trusts exist, hardcoded), so it doesn't consume a fetchone() slot.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _FakeCursor:
    def __init__(self, income_rows: list[tuple[Any, ...]], fetchone_results: list[tuple[Any, ...] | None]) -> None:
        self._fetchone_results = list(fetchone_results)
        self._fetchone_idx = 0
        self._fetchall_results = [income_rows, [(80_000_000.0, 10_000_000.0, None, None, None)]]
        self._fetchall_idx = 0

    def execute(self, query: str, *args: object, **kwargs: object) -> None:
        pass

    def fetchall(self) -> list[tuple[Any, ...]]:
        result = self._fetchall_results[self._fetchall_idx]
        self._fetchall_idx += 1
        return result

    def fetchone(self) -> tuple[Any, ...] | None:
        result = self._fetchone_results[self._fetchone_idx]
        self._fetchone_idx += 1
        return result


# Same downstream fetchone() sequence as test_sec_valuations_dcf_fcf_ric_reason_20260905.py,
# plus the RIC-check slot (None - doesn't match) and the currency-check slot (None - doesn't
# match) before falling through to the royalty-trust check, which needs no query slot.
_BASE_DOWNSTREAM_FETCHONE = [
    (30_000_000.0,),
    (20_000_000.0, 5_000_000.0, None, None),
    None,
    (None, None),
    (None,),
    (35.26,),
    (500_000_000.0,),
    (1.0,),
    (4.5,),
    (20.0,),
    (20.0,),
    None,
    (None, None),
]

_INCOME_ROWS = [
    (
        2025,
        100_000_000.0,
        10_000_000.0,
        1.0,
        8_000_000.0,
        9_000_000.0,
        None,
        None,
        50_000_000.0,
        None,
        False,
        6726,
        None,
    ),
]


def _run(
    symbol: str,
    capex_query_result: tuple[Any, ...] | None = None,
    blank_check_query_result: tuple[Any, ...] | None = None,
) -> dict[str, Any]:
    loader = _make_loader()
    # RIC-check query (None: doesn't match), unsupported-currency-check query (None: doesn't
    # match) - the royalty-trust check after them is pure symbol membership, no query. The
    # capex-never-tagged check after THAT (2026-09-06 sibling fix), and the blank-check
    # recategorization after THAT (2026-09-06 sibling fix), each only consume their own
    # fetchone() slot when the royalty-trust check didn't already override the reason (e.g. for
    # NRT, which short-circuits before reaching either).
    extra_fetchone = [] if symbol == "NRT" else [capex_query_result, blank_check_query_result]
    fake_cursor = _FakeCursor(_INCOME_ROWS, [*_BASE_DOWNSTREAM_FETCHONE, None, None, *extra_fetchone])
    fake_ctx = MagicMock()
    fake_ctx.__enter__ = MagicMock(return_value=fake_cursor)
    fake_ctx.__exit__ = MagicMock(return_value=False)

    forced_yield_dcf_result = {
        "fcf_yield": None,
        "fcf_yield_unavailable_reason": "missing_cash_flow_data",
        "dividend_yield": None,
        "net_payout_yield": None,
        "enterprise_value": 500_000_000.0,
        "ev_ebitda": None,
        "ev_revenue": None,
        "intrinsic_value_per_share": None,
        "margin_of_safety_pct": None,
        "dcf_fcf_unavailable_reason": "missing_cash_flow_data",
    }

    with (
        patch("loaders.load_sec_valuations.DatabaseContext", return_value=fake_ctx),
        patch.object(SecValuationsLoader, "_compute_yield_and_dcf_fields", return_value=forced_yield_dcf_result),
    ):
        return loader.fetch_incremental(symbol, None)


class TestSecValuationsDcfFcfRoyaltyTrustReason:
    def test_royalty_trust_symbol_reports_reit_special_entity_reason(self) -> None:
        result = _run("NRT")

        row = result[0]
        assert row["dcf_fcf_unavailable_reason"] == "reit_special_entity"

    def test_non_royalty_trust_symbol_keeps_generic_reason(self) -> None:
        result = _run("NORMALCO")

        row = result[0]
        assert row["dcf_fcf_unavailable_reason"] == "missing_cash_flow_data"
