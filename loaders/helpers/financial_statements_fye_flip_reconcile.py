"""Fye_month-flip duplicate-row reconcile methods for ConsolidatedFinancialStatementsLoader,
extracted from load_financial_statements.py (2026-09-16, file-size ratchet - see the
financial_statements_q4_sweeps.py sibling module's docstring for the same precedent/reasoning).
Mixed into ConsolidatedFinancialStatementsLoader, which defines `table_name`/`_field_mapping`.

Root cause (see call site in load_financial_statements.py's fetch_incremental): a non-December-
FYE symbol's fye_month can be re-derived differently between two loader runs, so the same
underlying SEC fact can land under a different fiscal_year on a later run. Since the primary
key is (symbol, fiscal_year, fiscal_quarter), ON CONFLICT never fires and bulk_insert() adds a
second row instead of correcting the first. Live-confirmed DB-wide sweep found 1,000+
quarterly_income_statement groups with this signature, plus 1,442/417 in
quarterly_balance_sheet/quarterly_cash_flow (which lack a period_end column, hence the second,
value-fingerprint variant below).

`DatabaseContext` is accessed via the load_financial_statements module object at call time, not
imported by name here, for the same test-patchability/circular-import reasons documented in
financial_statements_q4_sweeps.py's `_database_context()`.
"""

import logging
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

# All fields must be present+equal to recognize "same filed fact" with no period_end to key off.
VALUE_FINGERPRINT_FIELDS = {
    "quarterly_balance_sheet": ("total_assets", "total_liabilities", "stockholders_equity"),
    "quarterly_cash_flow": ("operating_cash_flow", "investing_cash_flow", "financing_cash_flow"),
}

QUARTERLY_TABLES_WITH_FISCAL_QUARTER_PK = {
    "quarterly_income_statement",
    "quarterly_balance_sheet",
    "quarterly_cash_flow",
}


def _database_context() -> type:
    import loaders.load_financial_statements as _lfs

    return _lfs.DatabaseContext


class FyeFlipReconcileMixin:
    """Reconcile methods that delete a stale duplicate row left over from a fye_month-flip
    (or, for balance/cashflow, a value-fingerprint-matched) fiscal_year relabeling.
    """

    table_name: str

    def _reconcile_stale_fiscal_year_duplicate_period_end(self, symbol: str, rows: list[dict[str, Any]]) -> None:
        """Delete any existing DB row for `symbol` sharing a `period_end` with one of `rows`
        but disagreeing on (fiscal_year, fiscal_quarter) - see module docstring for root cause.
        BUGFIX 2026-09-16: pre-transform() rows carry raw "fiscal_period"/str period_end,
        not int fiscal_quarter/date - parse both like transform() does, else always empty.

        quarterly_balance_sheet/quarterly_cash_flow have no period_end DB column to key off,
        so they're routed to _reconcile_stale_fiscal_year_duplicate_value_fingerprint instead.
        """
        if self.table_name in VALUE_FINGERPRINT_FIELDS:
            self._reconcile_stale_fiscal_year_duplicate_value_fingerprint(symbol, rows)
            return
        quarter_map = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}
        candidates = []
        for row in rows:
            raw_end, raw_period = row.get("period_end"), row.get("fiscal_period")
            period_end = date.fromisoformat(raw_end) if isinstance(raw_end, str) else raw_end
            fiscal_quarter = quarter_map.get(raw_period) if isinstance(raw_period, str) else None
            if period_end is None or row.get("fiscal_year") is None or fiscal_quarter is None:
                continue
            candidates.append(
                {"period_end": period_end, "fiscal_year": row["fiscal_year"], "fiscal_quarter": fiscal_quarter}
            )
        if not candidates:
            return
        period_ends = {row["period_end"] for row in candidates}
        with _database_context()("read") as cur:
            cur.execute(
                f"""
                SELECT fiscal_year, fiscal_quarter, period_end
                FROM {self.table_name}
                WHERE symbol = %s AND period_end = ANY(%s)
                """,
                (symbol, list(period_ends)),
            )
            existing = cur.fetchall()
        current_keys_by_period_end: dict[Any, set[tuple[Any, Any]]] = {}
        for row in candidates:
            current_keys_by_period_end.setdefault(row["period_end"], set()).add(
                (row["fiscal_year"], row["fiscal_quarter"])
            )
        stale_keys = [
            (existing_fy, existing_fq)
            for existing_fy, existing_fq, existing_period_end in existing
            if (existing_fy, existing_fq) not in current_keys_by_period_end.get(existing_period_end, set())
        ]
        if not stale_keys:
            return
        with _database_context()("write") as cur:
            deleted = 0
            for stale_fy, stale_fq in stale_keys:
                cur.execute(
                    f"DELETE FROM {self.table_name} WHERE symbol = %s AND fiscal_year = %s AND fiscal_quarter = %s",
                    (symbol, stale_fy, stale_fq),
                )
                deleted += cur.rowcount
        if deleted:
            logger.warning(
                f"[{self.table_name}] {symbol}: deleted {deleted} stale duplicate row(s) whose "
                "period_end matched this run's fresh data under a different (fiscal_year, "
                "fiscal_quarter) - see _reconcile_stale_fiscal_year_duplicate_period_end docstring."
            )

    def _reconcile_stale_fiscal_year_duplicate_value_fingerprint(self, symbol: str, rows: list[dict[str, Any]]) -> None:
        """Value-fingerprint variant for tables with no period_end column - matches on core
        reported values (VALUE_FINGERPRINT_FIELDS) being identical under a fiscal_year exactly
        1 away for the same fiscal_quarter instead.
        BUGFIX 2026-09-16 (0 matches across a 665-symbol run): `rows` is PRE-transform, so
        canonical names like "total_assets" never appear directly - resolve via
        self._field_mapping's raw concept keys instead, same as required_raw_keys elsewhere.
        """
        quarter_map = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}
        fields = VALUE_FINGERPRINT_FIELDS[self.table_name]
        field_mapping = getattr(self, "_field_mapping", None) or {}
        raw_keys_by_field: dict[str, list[str]] = {f: [] for f in fields}
        for raw, mapped in field_mapping.items():
            if mapped in raw_keys_by_field:
                raw_keys_by_field[mapped].append(raw)

        def _resolve(row: dict[str, Any], field: str) -> Any:
            for raw_key in raw_keys_by_field[field]:
                val = row.get(raw_key)
                if val is not None:
                    return val
            return None

        candidates = []
        for row in rows:
            raw_period = row.get("fiscal_period")
            fiscal_quarter = quarter_map.get(raw_period) if isinstance(raw_period, str) else None
            fiscal_year = row.get("fiscal_year")
            if fiscal_quarter is None or fiscal_year is None:
                continue
            values = tuple(_resolve(row, f) for f in fields)
            if any(v is None for v in values):
                continue
            candidates.append({"fiscal_year": fiscal_year, "fiscal_quarter": fiscal_quarter, "values": values})
        if not candidates:
            return
        fiscal_years = {row["fiscal_year"] for row in candidates}
        adjacent_years = {y + delta for y in fiscal_years for delta in (-1, 1)}
        with _database_context()("read") as cur:
            cur.execute(
                f"""
                SELECT fiscal_year, fiscal_quarter, {", ".join(fields)}
                FROM {self.table_name}
                WHERE symbol = %s AND fiscal_year = ANY(%s)
                """,
                (symbol, list(adjacent_years)),
            )
            existing = cur.fetchall()
        stale_keys = []
        for existing_fy, existing_fq, *existing_values in existing:
            existing_values_t = tuple(existing_values)
            for candidate in candidates:
                if (
                    candidate["fiscal_quarter"] == existing_fq
                    and abs(candidate["fiscal_year"] - existing_fy) == 1
                    and candidate["values"] == existing_values_t
                    and (candidate["fiscal_year"], candidate["fiscal_quarter"]) != (existing_fy, existing_fq)
                ):
                    stale_keys.append((existing_fy, existing_fq))
                    break
        if not stale_keys:
            return
        with _database_context()("write") as cur:
            deleted = 0
            for stale_fy, stale_fq in stale_keys:
                cur.execute(
                    f"DELETE FROM {self.table_name} WHERE symbol = %s AND fiscal_year = %s AND fiscal_quarter = %s",
                    (symbol, stale_fy, stale_fq),
                )
                deleted += cur.rowcount
        if deleted:
            logger.warning(
                f"[{self.table_name}] {symbol}: deleted {deleted} stale duplicate row(s) whose "
                "value fingerprint matched this run's fresh data under a different fiscal_year - "
                "see _reconcile_stale_fiscal_year_duplicate_value_fingerprint docstring."
            )
