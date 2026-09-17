#!/usr/bin/env python3
"""Quarterly counterpart to scripts/xbrl_yfinance_crosscheck.py: our SEC-XBRL-derived
QUARTERLY financial statement values vs yfinance's own quarterly parse, across every
mappable line item on quarterly_income_statement/quarterly_balance_sheet/quarterly_cash_flow.

ADDED 2026-09-17: the annual crosscheck (migration 1300, 2026-09-10/16) never covered
quarterly data at all - a real, previously undiscovered blind spot found while working the
2026-09-16 divergence-repair incident (scripts/DIVERGENCE_REPAIR_POSTMORTEM.md). Reuses the
SAME persistence table (xbrl_yfinance_line_item_report, extended by migration 1303 with
fiscal_quarter/period_type) and the SAME review workflow (scripts/xbrl_line_item_report.py,
scripts/xbrl_line_item_review.py both already updated to handle fiscal_quarter) rather than
duplicating tooling - see migration 1303's comment for why fiscal_quarter is NOT NULL DEFAULT 0
(0 = annual) instead of nullable.

KNOWN PRECISION LIMIT (accepted, not a bug): yfinance's quarterly period matching is by
CALENDAR quarter of the period-end month (utils/external/yfinance_financials.py's
_build_period_row docstring: "Best-effort calendar-quarter label ... not a real fiscal-period
tag like SEC's fp field"), not the filer's own fiscal-quarter numbering. For a filer whose
fiscal year doesn't align with the calendar (e.g. one ending in June), our fiscal_quarter=1
might land in a different calendar quarter than yfinance's Q1 label for the same real period.
This script matches on (fiscal_year, calendar-quarter-of-period_end) - the same class of
approximation the annual script already accepts for calendar-year matching (annual also just
compares by calendar year of yfinance's period_end, not filer-fiscal-year-precise), not a new
or worse precision bar. A genuine false-divergence source for non-calendar-fiscal-year filers;
review candidates rather than blind-trusting either side, same posture as the annual script.

Safety posture identical to the annual script: NOT part of every DataPatrol run (live yfinance
network calls through the shared rate-limited circuit breaker - utils/external/
yfinance_circuit_breaker.py), sampling + --sweep mode with its OWN persistent cursor
(xbrl_yfinance_crosscheck_progress id=2, separate from the annual sweep's id=1 since the
quarterly universe/row-count is ~4x larger), same ban-detection/backoff, same
"every comparison gets upserted, not just flagged ones" behavior.

Usage:
    python scripts/xbrl_yfinance_quarterly_crosscheck.py                  # sample 25 symbols
    python scripts/xbrl_yfinance_quarterly_crosscheck.py --limit 50
    python scripts/xbrl_yfinance_quarterly_crosscheck.py --sweep          # next 25 in the sweep
    python scripts/xbrl_yfinance_quarterly_crosscheck.py --symbols AAPL,MSFT,KO
    python scripts/xbrl_yfinance_quarterly_crosscheck.py --dry-run        # print, don't write
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
import uuid
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# (our_table, our_field, yfinance statement_type, yfinance target_key) - target_key values come
# straight from utils/external/yfinance_financials.py's own field maps (_INCOME_FIELD_MAP /
# _BALANCE_FIELD_MAP / _CASHFLOW_FIELD_MAP - SHARED between annual and quarterly, only the
# fetch's `period` argument differs), same discipline as the annual script's _FIELDS. our_field
# is this codebase's live DB column name on the corresponding quarterly_* table (confirmed live
# via information_schema.columns 2026-09-17) - narrower than the annual field list because the
# quarterly tables don't carry every column the annual ones do (e.g. no quarterly goodwill or
# accounts_receivable columns exist yet).
_FIELDS: list[tuple[str, str, str, str]] = [
    # quarterly_income_statement
    ("quarterly_income_statement", "revenue", "income", "revenues"),
    ("quarterly_income_statement", "cost_of_revenue", "income", "cost_of_revenue"),
    ("quarterly_income_statement", "gross_profit", "income", "gross_profit"),
    ("quarterly_income_statement", "operating_income", "income", "operating_income_loss"),
    ("quarterly_income_statement", "net_income", "income", "net_income_loss"),
    ("quarterly_income_statement", "earnings_per_share", "income", "earnings_per_share_basic"),
    ("quarterly_income_statement", "diluted_eps", "income", "earnings_per_share_diluted"),
    (
        "quarterly_income_statement",
        "shares_outstanding_basic",
        "income",
        "weighted_average_number_of_shares_outstanding_basic",
    ),
    (
        "quarterly_income_statement",
        "shares_outstanding_diluted",
        "income",
        "weighted_average_number_of_diluted_shares_outstanding",
    ),
    ("quarterly_income_statement", "interest_expense", "income", "interest_expense"),
    ("quarterly_income_statement", "depreciation_expense", "income", "depreciation"),
    ("quarterly_income_statement", "income_tax_expense", "income", "income_tax_expense_benefit"),
    (
        "quarterly_income_statement",
        "pretax_income",
        "income",
        "income_loss_from_continuing_operations_before_income_taxes_extraordinary_items_noncontrolling_interest",
    ),
    # quarterly_balance_sheet
    ("quarterly_balance_sheet", "total_assets", "balance", "assets"),
    ("quarterly_balance_sheet", "current_assets", "balance", "assets_current"),
    ("quarterly_balance_sheet", "total_liabilities", "balance", "liabilities"),
    ("quarterly_balance_sheet", "stockholders_equity", "balance", "stockholders_equity"),
    ("quarterly_balance_sheet", "current_liabilities", "balance", "liabilities_current"),
    ("quarterly_balance_sheet", "inventory", "balance", "inventory_net"),
    ("quarterly_balance_sheet", "cash_and_equivalents", "balance", "cash_and_cash_equivalents_at_carrying_value"),
    ("quarterly_balance_sheet", "accounts_receivable", "balance", "accounts_receivable_net_current"),
    ("quarterly_balance_sheet", "ppe_net", "balance", "property_plant_and_equipment_net"),
    ("quarterly_balance_sheet", "goodwill", "balance", "goodwill"),
    ("quarterly_balance_sheet", "long_term_debt", "balance", "long_term_debt"),
    # quarterly_cash_flow
    ("quarterly_cash_flow", "operating_cash_flow", "cashflow", "net_cash_provided_by_used_in_operating_activities"),
    ("quarterly_cash_flow", "investing_cash_flow", "cashflow", "net_cash_provided_by_used_in_investing_activities"),
    ("quarterly_cash_flow", "financing_cash_flow", "cashflow", "net_cash_provided_by_used_in_financing_activities"),
    ("quarterly_cash_flow", "capex", "cashflow", "payments_to_acquire_property_plant_and_equipment"),
    ("quarterly_cash_flow", "dividends_paid", "cashflow", "payments_of_dividends"),
]

_PER_SHARE_FIELDS = frozenset({"earnings_per_share", "diluted_eps"})
_SHARE_COUNT_FIELDS = frozenset({"shares_outstanding_basic", "shares_outstanding_diluted"})

_DIVERGENCE_RATIO = 2.0
_DIVERGENCE_FLOOR_DOLLARS = 1_000_000.0
_DIVERGENCE_FLOOR_PER_SHARE = 0.01
_DIVERGENCE_FLOOR_SHARE_COUNT = 100_000.0
_MAX_EXAMPLES_PER_FIELD = 15
_MAX_CONSECUTIVE_BAN_ERRORS = 3
_DEFAULT_INTER_SYMBOL_DELAY_SECS = 2.0

# Same composite-sum fix as the annual script (live-confirmed 2026-09-16 there): yfinance's
# "Reconciled Depreciation" is depreciation + amortization combined on the cash-flow statement,
# not pure depreciation. Applies identically to the quarterly column pair.
_COMPOSITE_SUM_FIELDS: dict[tuple[str, str], str] = {
    ("quarterly_income_statement", "depreciation_expense"): "amortization_expense",
}

# Sweep cursor row id for this script, distinct from the annual sweep's id=1 (migration 1304).
_SWEEP_CURSOR_ID = 2


def _floor_for_field(our_field: str) -> float:
    if our_field in _PER_SHARE_FIELDS:
        return _DIVERGENCE_FLOOR_PER_SHARE
    if our_field in _SHARE_COUNT_FIELDS:
        return _DIVERGENCE_FLOOR_SHARE_COUNT
    return _DIVERGENCE_FLOOR_DOLLARS


def _select_symbols_random(cur: Any, limit: int) -> list[str]:
    """Daily-rotating pseudo-random sample of active symbols with real SEC-audited quarterly
    income-statement data (data_source='sec_audited' - never compares yfinance against itself)."""
    cur.execute(
        """
        SELECT symbol FROM (
            SELECT DISTINCT qis.symbol
            FROM quarterly_income_statement qis
            JOIN stock_symbols s ON s.symbol = qis.symbol AND s.active = true
            WHERE qis.data_source = 'sec_audited' AND qis.data_unavailable = FALSE
        ) candidates
        ORDER BY md5(symbol || CURRENT_DATE::text)
        LIMIT %s
        """,
        (limit,),
    )
    return [row[0] for row in cur.fetchall()]


def _eligible_universe(cur: Any) -> list[str]:
    cur.execute(
        """
        SELECT DISTINCT qis.symbol
        FROM quarterly_income_statement qis
        JOIN stock_symbols s ON s.symbol = qis.symbol AND s.active = true
        WHERE qis.data_source = 'sec_audited' AND qis.data_unavailable = FALSE
        ORDER BY 1
        """
    )
    return [row[0] for row in cur.fetchall()]


def _select_symbols_sweep(cur: Any, limit: int) -> list[str]:
    universe = _eligible_universe(cur)
    if not universe:
        return []

    cur.execute("SELECT last_symbol FROM xbrl_yfinance_crosscheck_progress WHERE id = %s", (_SWEEP_CURSOR_ID,))
    row = cur.fetchone()
    last_symbol = row[0] if row else None

    start_idx = 0
    if last_symbol is not None:
        for i, sym in enumerate(universe):
            if sym > last_symbol:
                start_idx = i
                break
        else:
            start_idx = 0  # last_symbol was >= everything - wrap to the start

    if start_idx + limit <= len(universe):
        batch = universe[start_idx : start_idx + limit]
    else:
        batch = universe[start_idx:] + universe[: (start_idx + limit) - len(universe)]
    return batch


def _advance_sweep_cursor(cur: Any, last_symbol_checked: str) -> None:
    cur.execute(
        """
        INSERT INTO xbrl_yfinance_crosscheck_progress (id, last_symbol, updated_at)
        VALUES (%s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (id) DO UPDATE SET last_symbol = EXCLUDED.last_symbol, updated_at = EXCLUDED.updated_at
        """,
        (_SWEEP_CURSOR_ID, last_symbol_checked),
    )


def _our_all_values(cur: Any, table: str, field: str, symbol: str) -> list[tuple[int, int, float]]:
    """Every (fiscal_year, fiscal_quarter) on file for this (table, field, symbol)."""
    extra = _COMPOSITE_SUM_FIELDS.get((table, field))
    select_expr = f"({field} + COALESCE({extra}, 0))" if extra else field
    cur.execute(
        f"""
        SELECT fiscal_year, fiscal_quarter, {select_expr}
        FROM {table}
        WHERE symbol = %s AND data_source = 'sec_audited' AND data_unavailable = FALSE AND {field} IS NOT NULL
        ORDER BY fiscal_year DESC, fiscal_quarter DESC
        """,
        (symbol,),
    )
    return [(int(fy), int(fq), float(val)) for fy, fq, val in cur.fetchall()]


def _is_foreign_private_issuer(cur: Any, symbol: str) -> bool:
    cur.execute("SELECT is_foreign_private_issuer FROM company_info_sec WHERE symbol = %s", (symbol,))
    row = cur.fetchone()
    return bool(row and row[0])


def _calendar_quarter(period_end: Any) -> int:
    return int(((period_end.month - 1) // 3) + 1)


def _record_line_item(
    cur: Any,
    symbol: str,
    table: str,
    field: str,
    fiscal_year: int,
    fiscal_quarter: int,
    our_value: float,
    yfinance_value: float,
    ratio: float,
    divergent: bool,
) -> None:
    """Mirrors the annual script's _record_line_item exactly, keyed additionally by
    fiscal_quarter (migration 1303) and always writing period_type='quarterly'."""
    cur.execute(
        """
        INSERT INTO xbrl_yfinance_line_item_report
            (symbol, our_table, our_field, fiscal_year, fiscal_quarter, period_type,
             our_value, yfinance_value, ratio, divergent, checked_at)
        VALUES (%s, %s, %s, %s, %s, 'quarterly', %s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (symbol, our_table, our_field, fiscal_year, fiscal_quarter) DO UPDATE SET
            our_value = EXCLUDED.our_value,
            yfinance_value = EXCLUDED.yfinance_value,
            ratio = EXCLUDED.ratio,
            divergent = EXCLUDED.divergent,
            checked_at = EXCLUDED.checked_at,
            review_status = CASE
                WHEN xbrl_yfinance_line_item_report.our_value IS DISTINCT FROM EXCLUDED.our_value
                  OR xbrl_yfinance_line_item_report.yfinance_value IS DISTINCT FROM EXCLUDED.yfinance_value
                THEN 'unreviewed'
                ELSE xbrl_yfinance_line_item_report.review_status
            END,
            review_note = CASE
                WHEN xbrl_yfinance_line_item_report.our_value IS DISTINCT FROM EXCLUDED.our_value
                  OR xbrl_yfinance_line_item_report.yfinance_value IS DISTINCT FROM EXCLUDED.yfinance_value
                THEN NULL
                ELSE xbrl_yfinance_line_item_report.review_note
            END,
            reviewed_at = CASE
                WHEN xbrl_yfinance_line_item_report.our_value IS DISTINCT FROM EXCLUDED.our_value
                  OR xbrl_yfinance_line_item_report.yfinance_value IS DISTINCT FROM EXCLUDED.yfinance_value
                THEN NULL
                ELSE xbrl_yfinance_line_item_report.reviewed_at
            END,
            reviewed_by = CASE
                WHEN xbrl_yfinance_line_item_report.our_value IS DISTINCT FROM EXCLUDED.our_value
                  OR xbrl_yfinance_line_item_report.yfinance_value IS DISTINCT FROM EXCLUDED.yfinance_value
                THEN NULL
                ELSE xbrl_yfinance_line_item_report.reviewed_by
            END
        """,
        (symbol, table, field, fiscal_year, fiscal_quarter, our_value, yfinance_value, ratio, divergent),
    )


def run(  # noqa: C901
    limit: int,
    symbols_override: list[str] | None,
    dry_run: bool,
    sweep: bool = False,
    delay_seconds: float = _DEFAULT_INTER_SYMBOL_DELAY_SECS,
) -> dict[str, Any]:
    from psycopg2.extras import DictCursor

    from algo.monitoring.data_patrol.base import CheckResult
    from algo.monitoring.data_patrol.logger import PatrolLogger
    from utils.db.connection import get_db_connection
    from utils.external.yfinance_financials import fetch_financial_statement

    conn = get_db_connection(max_retries=2, timeout=30)
    cur = conn.cursor(cursor_factory=DictCursor)

    if symbols_override:
        symbols = symbols_override
    elif sweep:
        symbols = _select_symbols_sweep(cur, limit)
    else:
        symbols = _select_symbols_random(cur, limit)
    logger.info(
        f"[YFINANCE_QUARTERLY_CROSSCHECK] {'Sweeping' if sweep else 'Sampling'} {len(symbols)} symbol(s): {symbols}"
    )

    flagged: dict[str, list[dict[str, Any]]] = {f"{t}:{f}": [] for t, f, _, _ in _FIELDS}
    sampled_count: dict[str, int] = {f"{t}:{f}": 0 for t, f, _, _ in _FIELDS}
    consecutive_ban_errors = 0
    last_symbol_checked: str | None = None

    for i, symbol in enumerate(symbols):
        if consecutive_ban_errors >= _MAX_CONSECUTIVE_BAN_ERRORS:
            logger.warning(
                f"[YFINANCE_QUARTERLY_CROSSCHECK] {_MAX_CONSECUTIVE_BAN_ERRORS} consecutive shared-IP-ban "
                "errors - aborting the rest of this batch rather than spinning through it uselessly."
            )
            break

        is_fpi = _is_foreign_private_issuer(cur, symbol)
        statement_cache: dict[str, list[dict[str, Any]] | None] = {}

        for table, field, statement_type, target_key in _FIELDS:
            our_rows = _our_all_values(cur, table, field, symbol)
            if not our_rows:
                continue

            if statement_type not in statement_cache:
                try:
                    statement_cache[statement_type] = fetch_financial_statement(
                        symbol, statement_type, "quarterly", is_known_foreign_issuer=is_fpi
                    )
                    consecutive_ban_errors = 0
                except RuntimeError as e:
                    statement_cache[statement_type] = None
                    if "shared IP ban" in str(e):
                        consecutive_ban_errors += 1
                    logger.debug(
                        f"[YFINANCE_QUARTERLY_CROSSCHECK] {symbol} {statement_type} fetch failed (non-fatal): {e}"
                    )

            yf_rows = statement_cache.get(statement_type)
            if not yf_rows:
                continue
            # Match by (calendar year, calendar quarter) of yfinance's period-end - see this
            # module's docstring for why this is an accepted approximation, not fiscal-quarter-exact.
            yf_rows_by_period: dict[tuple[int, int], dict[str, Any]] = {}
            for r in yf_rows:
                fp = r.get("fiscal_period")  # e.g. "Q3"
                fy = r.get("fiscal_year")
                if fp is None or fy is None or not fp.startswith("Q"):
                    continue
                try:
                    cal_q = int(fp[1:])
                except ValueError:
                    continue
                yf_rows_by_period[(int(fy), cal_q)] = r

            for fiscal_year, fiscal_quarter, our_value in our_rows:
                yf_row = yf_rows_by_period.get((fiscal_year, fiscal_quarter))
                if yf_row is None or target_key not in yf_row:
                    continue
                yf_value = float(yf_row[target_key])

                field_key = f"{table}:{field}"
                sampled_count[field_key] += 1
                floor = _floor_for_field(field)
                if max(abs(our_value), abs(yf_value)) < floor or yf_value == 0:
                    continue
                ratio = abs(our_value) / abs(yf_value)
                divergent = not (_DIVERGENCE_RATIO > ratio > (1.0 / _DIVERGENCE_RATIO))

                if not dry_run:
                    _record_line_item(
                        cur, symbol, table, field, fiscal_year, fiscal_quarter, our_value, yf_value, ratio, divergent
                    )

                if divergent:
                    flagged[field_key].append(
                        {
                            "symbol": symbol,
                            "fiscal_year": fiscal_year,
                            "fiscal_quarter": fiscal_quarter,
                            "our_value": our_value,
                            "yfinance_value": yf_value,
                            "ratio": round(ratio, 4),
                        }
                    )

        last_symbol_checked = symbol

        is_last = i == len(symbols) - 1
        if delay_seconds > 0 and not is_last and consecutive_ban_errors < _MAX_CONSECUTIVE_BAN_ERRORS:
            time.sleep(delay_seconds)

    results: list[CheckResult] = []
    for table, field, _, _ in _FIELDS:
        field_key = f"{table}:{field}"
        check_name = f"yfinance_independent_quarterly_crosscheck_{field}"
        examples = flagged[field_key]
        n_sampled = sampled_count[field_key]
        if examples:
            results.append(
                CheckResult(
                    check_name,
                    "warn",
                    table,
                    f"{len(examples)}/{n_sampled} symbol-quarter(s) with a yfinance-comparable {field} value "
                    f"diverge >{_DIVERGENCE_RATIO:.0f}x from our SEC-derived value - review queue, not a "
                    "confirmed bug.",
                    {"sampled": n_sampled, "flagged": len(examples), "examples": examples[:_MAX_EXAMPLES_PER_FIELD]},
                )
            )
        else:
            results.append(
                CheckResult(
                    check_name,
                    "info",
                    table,
                    f"no >{_DIVERGENCE_RATIO:.0f}x yfinance divergence in {field} ({n_sampled} symbol-quarter(s) "
                    "had a comparable yfinance value this run)",
                )
            )

    if dry_run:
        for result in results:
            logger.info(f"[DRY-RUN] [{result.severity.upper()}] {result.check_name}: {result.message}")
    else:
        run_id = uuid.uuid4().hex
        patrol_logger = PatrolLogger(run_id)
        patrol_logger.log_results(cur, results)
        if sweep and last_symbol_checked is not None:
            _advance_sweep_cursor(cur, last_symbol_checked)
        conn.commit()
        logger.info(f"[YFINANCE_QUARTERLY_CROSSCHECK] Logged {len(results)} result(s) (run_id={run_id})")

    cur.close()
    conn.close()
    return {"sampled_symbols": len(symbols), "results": [r.to_dict() for r in results]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=25, help="How many symbols to sample this run (default 25)")
    parser.add_argument("--symbols", help="Comma-separated explicit symbol list, overrides --limit sampling")
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="Walk the active universe alphabetically via a persistent cursor instead of random daily sampling",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print findings, don't write to DB")
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=_DEFAULT_INTER_SYMBOL_DELAY_SECS,
        help=f"Pause between symbols to avoid tripping the shared-IP rate limit (default {_DEFAULT_INTER_SYMBOL_DELAY_SECS}s)",
    )
    args = parser.parse_args()

    symbols_override = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else None

    started = time.monotonic()
    summary = run(
        limit=args.limit,
        symbols_override=symbols_override,
        dry_run=args.dry_run,
        sweep=args.sweep,
        delay_seconds=args.delay_seconds,
    )
    elapsed = time.monotonic() - started
    logger.info(
        f"[YFINANCE_QUARTERLY_CROSSCHECK] Done in {elapsed:.1f}s - {summary['sampled_symbols']} symbol(s) sampled"
    )


if __name__ == "__main__":
    main()
