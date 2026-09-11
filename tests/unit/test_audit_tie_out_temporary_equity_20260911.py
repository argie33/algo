"""Regression test for the 2026-09-11 fix: scripts/audit_statement_tie_outs.py's
audit_balance_sheet_identity() had fallen out of sync with the production check
(algo/monitoring/data_patrol/checks/tie_out_identity_annual.py's
check_balance_sheet_identity) after migration 1274 (2026-09-09) added a
`temporary_equity` term to the balance-sheet identity for mezzanine-equity filers
(PROK/ATTO/FAC/LTGO/SCTX-style: modest assets/liabilities, deeply negative
stockholders_equity, real SEC-tagged TemporaryEquityCarryingAmountAttributableToParent).
The standalone diagnostic never got that update, so it kept flagging OBAI/LTGO/SCTX as
90-450% balance-sheet-identity "violations" - looking like unresolved extraction bugs -
when the production check (and the real underlying data) already tie out once
temporary_equity is included.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

import audit_statement_tie_outs as audit_module


class _FakeCursor:
    def __init__(self, rows: list[tuple[Any, ...]], columns: set[str]) -> None:
        self._rows = rows
        self._columns = columns
        self._last_query_had_temp_equity = False

    def execute(self, sql: str, params: object = None) -> None:
        if "information_schema.columns" in sql:
            self._info_schema_query = True
        else:
            self._info_schema_query = False
            self._last_query_had_temp_equity = "temporary_equity" in sql

    def fetchall(self) -> list[tuple[Any, ...]]:
        if self._info_schema_query:
            return [(c,) for c in self._columns]
        return self._rows


def test_flags_obai_style_row_without_temporary_equity_column() -> None:
    # A schema from before migration 1274 (no temporary_equity column at all) should
    # still work via the same COALESCE(..., 0)/degrade-when-missing discipline as
    # noncontrolling_interest - and, lacking the column, correctly flags the residual.
    columns = {"symbol", "fiscal_year", "total_assets", "total_liabilities", "stockholders_equity"}
    # The query always selects 7 positions (nci/temp_equity fall back to a literal NULL
    # in the SQL text when the columns are absent), so the fake row still has 7 fields.
    rows = [("OBAI", 2025, 2_501_000.0, 13_775_000.0, -22_663_000.0, None, None)]
    cur = _FakeCursor(rows, columns)

    flagged = audit_module.audit_balance_sheet_identity(cur, min_relative_error=0.01, limit=50)

    assert len(flagged) == 1
    assert flagged[0][0] == "OBAI"


def test_temporary_equity_closes_the_obai_gap_when_column_present() -> None:
    # With temporary_equity present and populated to the real, live-confirmed value,
    # the identity ties out exactly and OBAI must NOT be flagged.
    columns = {
        "symbol",
        "fiscal_year",
        "total_assets",
        "total_liabilities",
        "stockholders_equity",
        "noncontrolling_interest",
        "temporary_equity",
    }
    rows = [("OBAI", 2025, 2_501_000.0, 13_775_000.0, -22_663_000.0, None, 11_389_000.0)]
    cur = _FakeCursor(rows, columns)

    flagged = audit_module.audit_balance_sheet_identity(cur, min_relative_error=0.01, limit=50)

    assert flagged == []
