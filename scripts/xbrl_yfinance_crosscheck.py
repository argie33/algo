#!/usr/bin/env python3
"""Periodic independent cross-check: our SEC-XBRL-derived financial statement values vs
yfinance's own, independently-parsed financials, for a rotating sample of the active universe.

Added 2026-09-10 (goal session: institution-grade XBRL data-quality architecture). Real
vendors validate XBRL preparation with three layers, none of which require paying for
another data vendor: (1) a filing's own calculation-linkbase arithmetic ties within that
same document (not implemented here - that needs parsing the instance's calc linkbase, a
separate piece of work), (2) same-filer time-series continuity and cross-sectional peer
statistics (already covered by algo/monitoring/data_patrol/checks/statistical_anomaly.py
and tie_out.py), and (3) an independently-*parsed* second read of the same underlying
filing to catch extraction/mapping bugs that are internally self-consistent (so tie_out.py's
identity checks pass) and don't stand out against peers/history either (so
statistical_anomaly.py doesn't fire). This script is #3.

yfinance is not a truly independent SOURCE - it likely also derives from XBRL, probably
through a data vendor between the SEC feed and Yahoo's site. But it goes through completely
different extraction/tagging/mapping code than ours, so it catches a different bug class:
wrong-concept-picked, scale/unit errors, fiscal-period misalignment, sign errors. It's the
same "second opinion, not ground truth" role sec_valuations already gives it for market_cap/
shares_outstanding (see loaders/helpers/sec_valuations_checks.py) and the same fallback-only
fetch (utils/external/yfinance_financials.py) - REUSED here, not reimplemented.

Deliberately NOT part of every DataPatrol run (unlike statistical_anomaly.py, which is pure
SQL and cheap): this makes live yfinance network calls per symbol through the same
rate-limited/circuit-broken worker every other yfinance call in this codebase shares
(utils/external/yfinance_circuit_breaker.py) - see MEMORY.md's
yfinance_validation_calls_self_triggered_ban_during_reload_20260903 for why a naive
"check everything, every run" version of this would risk self-triggering the shared-IP ban
that live loader runs also depend on. Run this by hand or from a low-frequency schedule
(e.g. weekly), on a small rotating sample (--limit, default 25) - NOT the full universe -
and let findings accumulate into the existing data_patrol_review triage workflow over many
runs rather than trying to cover everyone in one pass.

Findings are WARN severity (review queue, not a confirmed bug - same posture as
statistical_anomaly.py: a real divergence can be a genuine restatement, non-GAAP
reclassification, or fiscal-period misalignment, not necessarily an extraction bug) and flow
into the same data_patrol_log / data_patrol_review triage + symbol_quarantine machinery as
every other DataPatrol check - no new review path, no new schema for "did anyone look at
this".

Usage:
    python scripts/xbrl_yfinance_crosscheck.py                  # sample 25 symbols, write findings
    python scripts/xbrl_yfinance_crosscheck.py --limit 50
    python scripts/xbrl_yfinance_crosscheck.py --symbols AAPL,MSFT,KO
    python scripts/xbrl_yfinance_crosscheck.py --dry-run         # print, don't write to data_patrol_log
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

# (our_table, our_field, yfinance statement_type, yfinance target_key) - target_key values
# come straight from utils/external/yfinance_financials.py's own field maps, not reinvented.
_FIELDS: list[tuple[str, str, str, str]] = [
    ("annual_income_statement", "revenue", "income", "revenues"),
    ("annual_income_statement", "net_income", "income", "net_income_loss"),
    ("annual_balance_sheet", "total_assets", "balance", "assets"),
    ("annual_balance_sheet", "stockholders_equity", "balance", "stockholders_equity"),
    ("annual_cash_flow", "operating_cash_flow", "cashflow", "net_cash_provided_by_used_in_operating_activities"),
]

# Wide by design: two independently-parsed sources legitimately disagree by 20-40% on plenty
# of real filers (non-GAAP reclassifications, discontinued-ops treatment, fiscal-period-end
# drift). This threshold is a starting point, not tuned against a live feasibility pass the
# way statistical_anomaly.py's 20x was - tighten it once real runs show what the normal
# divergence distribution actually looks like.
_DIVERGENCE_RATIO = 2.0
_DIVERGENCE_FLOOR = 1_000_000.0
_MAX_EXAMPLES_PER_FIELD = 15
_MAX_CONSECUTIVE_BAN_ERRORS = 3


def _select_symbols(cur: Any, limit: int) -> list[str]:
    """Daily-rotating pseudo-random sample of active symbols with real SEC-audited annual
    income-statement data (data_source='sec_audited' - excludes our own yfinance-fallback
    rows and unknown-source rows, so we're never comparing yfinance against itself)."""
    cur.execute(
        """
        SELECT symbol FROM (
            SELECT DISTINCT ais.symbol
            FROM annual_income_statement ais
            JOIN stock_symbols s ON s.symbol = ais.symbol AND s.active = true
            WHERE ais.data_source = 'sec_audited' AND ais.data_unavailable = FALSE
        ) candidates
        ORDER BY md5(symbol || CURRENT_DATE::text)
        LIMIT %s
        """,
        (limit,),
    )
    return [row[0] for row in cur.fetchall()]


def _our_latest_value(cur: Any, table: str, field: str, symbol: str) -> tuple[int, float] | None:
    cur.execute(
        f"""
        SELECT fiscal_year, {field}
        FROM {table}
        WHERE symbol = %s AND data_source = 'sec_audited' AND data_unavailable = FALSE AND {field} IS NOT NULL
        ORDER BY fiscal_year DESC
        LIMIT 1
        """,
        (symbol,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return int(row[0]), float(row[1])


def _is_foreign_private_issuer(cur: Any, symbol: str) -> bool:
    cur.execute("SELECT is_foreign_private_issuer FROM company_info_sec WHERE symbol = %s", (symbol,))
    row = cur.fetchone()
    return bool(row and row[0])


def run(limit: int, symbols_override: list[str] | None, dry_run: bool) -> dict[str, Any]:
    from psycopg2.extras import DictCursor

    from algo.monitoring.data_patrol.base import CheckResult
    from algo.monitoring.data_patrol.logger import PatrolLogger
    from utils.db.connection import get_db_connection
    from utils.external.yfinance_financials import fetch_financial_statement

    conn = get_db_connection(max_retries=2, timeout=30)
    cur = conn.cursor(cursor_factory=DictCursor)

    symbols = symbols_override or _select_symbols(cur, limit)
    logger.info(f"[YFINANCE_CROSSCHECK] Sampling {len(symbols)} symbol(s): {symbols}")

    # field_key ("table:field") -> list of flagged example dicts
    flagged: dict[str, list[dict[str, Any]]] = {f"{t}:{f}": [] for t, f, _, _ in _FIELDS}
    sampled_count: dict[str, int] = {f"{t}:{f}": 0 for t, f, _, _ in _FIELDS}
    consecutive_ban_errors = 0

    for symbol in symbols:
        if consecutive_ban_errors >= _MAX_CONSECUTIVE_BAN_ERRORS:
            logger.warning(
                f"[YFINANCE_CROSSCHECK] {_MAX_CONSECUTIVE_BAN_ERRORS} consecutive shared-IP-ban "
                "errors - aborting the rest of this batch rather than spinning through it uselessly."
            )
            break

        is_fpi = _is_foreign_private_issuer(cur, symbol)
        statement_cache: dict[str, list[dict[str, Any]] | None] = {}

        for table, field, statement_type, target_key in _FIELDS:
            ours = _our_latest_value(cur, table, field, symbol)
            if ours is None:
                continue
            fiscal_year, our_value = ours

            if statement_type not in statement_cache:
                try:
                    statement_cache[statement_type] = fetch_financial_statement(
                        symbol, statement_type, "annual", is_known_foreign_issuer=is_fpi
                    )
                    consecutive_ban_errors = 0
                except RuntimeError as e:
                    statement_cache[statement_type] = None
                    if "shared IP ban" in str(e):
                        consecutive_ban_errors += 1
                    logger.debug(f"[YFINANCE_CROSSCHECK] {symbol} {statement_type} fetch failed (non-fatal): {e}")

            yf_rows = statement_cache.get(statement_type)
            if not yf_rows:
                continue
            yf_row = next((r for r in yf_rows if r.get("fiscal_year") == fiscal_year), None)
            if yf_row is None or target_key not in yf_row:
                continue
            yf_value = float(yf_row[target_key])

            field_key = f"{table}:{field}"
            sampled_count[field_key] += 1
            if max(abs(our_value), abs(yf_value)) < _DIVERGENCE_FLOOR or yf_value == 0:
                continue
            ratio = abs(our_value) / abs(yf_value)
            if _DIVERGENCE_RATIO > ratio > (1.0 / _DIVERGENCE_RATIO):
                continue
            flagged[field_key].append(
                {
                    "symbol": symbol,
                    "fiscal_year": fiscal_year,
                    "our_value": our_value,
                    "yfinance_value": yf_value,
                    "ratio": round(ratio, 4),
                }
            )

    results: list[CheckResult] = []
    for table, field, _, _ in _FIELDS:
        field_key = f"{table}:{field}"
        check_name = f"yfinance_independent_crosscheck_{field}"
        examples = flagged[field_key]
        n_sampled = sampled_count[field_key]
        if examples:
            results.append(
                CheckResult(
                    check_name,
                    "warn",
                    table,
                    f"{len(examples)}/{n_sampled} symbol(s) with a yfinance-comparable {field} value "
                    f"diverge >{_DIVERGENCE_RATIO:.0f}x from our SEC-derived value (floor "
                    f"${_DIVERGENCE_FLOOR:,.0f}) - review queue, not a confirmed bug: restatements, "
                    "non-GAAP reclassification, and fiscal-period misalignment can all produce this.",
                    {"sampled": n_sampled, "flagged": len(examples), "examples": examples[:_MAX_EXAMPLES_PER_FIELD]},
                )
            )
        else:
            results.append(
                CheckResult(
                    check_name,
                    "info",
                    table,
                    f"no >{_DIVERGENCE_RATIO:.0f}x yfinance divergence in {field} ({n_sampled} symbol(s) "
                    "had a comparable yfinance value this run)",
                )
            )

    if dry_run:
        for r in results:
            logger.info(f"[DRY-RUN] [{r.severity.upper()}] {r.check_name}: {r.message}")
    else:
        run_id = uuid.uuid4().hex
        patrol_logger = PatrolLogger(run_id)
        patrol_logger.log_results(cur, results)
        conn.commit()
        logger.info(f"[YFINANCE_CROSSCHECK] Logged {len(results)} result(s) to data_patrol_log (run_id={run_id})")

    cur.close()
    conn.close()
    return {"sampled_symbols": len(symbols), "results": [r.to_dict() for r in results]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=25, help="How many symbols to sample this run (default 25)")
    parser.add_argument("--symbols", help="Comma-separated explicit symbol list, overrides --limit sampling")
    parser.add_argument("--dry-run", action="store_true", help="Print findings, don't write to data_patrol_log")
    args = parser.parse_args()

    symbols_override = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else None

    started = time.monotonic()
    summary = run(limit=args.limit, symbols_override=symbols_override, dry_run=args.dry_run)
    elapsed = time.monotonic() - started
    logger.info(f"[YFINANCE_CROSSCHECK] Done in {elapsed:.1f}s - {summary['sampled_symbols']} symbol(s) sampled")


if __name__ == "__main__":
    main()
