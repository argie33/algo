#!/usr/bin/env python3
"""Periodic independent cross-check: our SEC-XBRL-derived financial statement values vs
XBRL US's own, independently-parsed/tagged Public Filings Database, for a rotating sample of
the active universe.

Added 2026-09-15 (/goal "get our XBRL data handling all right" session, after the user
obtained a real XBRL US API account). Same "independent second read of the same underlying
filing" role as scripts/xbrl_yfinance_crosscheck.py (see that script's own docstring for the
full 3-layer data-quality architecture this slots into as an ADDITIONAL 4th cross-check, not a
replacement) - but XBRL US is a genuinely independent XBRL PARSER of the exact same SEC filings
(maintained by the org that publishes the DQC rule set scripts/xbrl_dqc_arelle_check.py already
runs), not a secondary vendor that may itself derive from XBRL data through unknown means the
way yfinance's ultimate source is unclear. A divergence here more directly implicates either
our own extraction code or a genuine XBRL-tagging ambiguity in the filing itself, since both
sides parsed the identical instance document.

Deliberately NOT part of every DataPatrol run (same reasoning as the yfinance/DQC/segment-sum
layers already documented in CLAUDE.md): each symbol here is a live authenticated API call
against XBRL US's own rate limits, and the OAuth2 token/refresh_token dance has its own cost.
Run this by hand or from a low-frequency schedule, small rotating sample only (--limit,
default 25).

Findings are WARN severity (review queue, not a confirmed bug - same posture as the yfinance
crosscheck) and flow into the same data_patrol_log / data_patrol_review triage workflow as
every other DataPatrol check.

Usage:
    python scripts/xbrl_us_crosscheck.py                  # sample 25 symbols, write findings
    python scripts/xbrl_us_crosscheck.py --limit 50
    python scripts/xbrl_us_crosscheck.py --symbols AAPL,MSFT,KO
    python scripts/xbrl_us_crosscheck.py --dry-run         # print, don't write to data_patrol_log
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

from utils.dotenv_loader import load_env_local  # noqa: E402

load_env_local()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# (our_table, our_field, [XBRL US us-gaap concept local-names, tried in order]) - a short
# fallback chain per field, not the full ~10-concept chain utils/external/sec_income_statement.py
# walks for OUR OWN extraction (that many concepts is overkill for a review-queue sanity check,
# and a filer using a concept this chain doesn't cover just yields "no comparable value this
# run" rather than a false divergence). Order matters: newer ASC-606-era filers (AAPL 2019+)
# report RevenueFromContractWithCustomerExcludingAssessedTax and never tag "Revenues" at all -
# live-confirmed 2026-09-15 testing this client against AAPL FY2023 (plain "Revenues" returned
# zero facts, the ASC-606 tag returned the real $383.285B figure).
_FIELDS: list[tuple[str, str, list[str]]] = [
    (
        "annual_income_statement",
        "revenue",
        ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"],
    ),
    ("annual_income_statement", "net_income", ["NetIncomeLoss"]),
    ("annual_balance_sheet", "total_assets", ["Assets"]),
    ("annual_balance_sheet", "stockholders_equity", ["StockholdersEquity"]),
    ("annual_cash_flow", "operating_cash_flow", ["NetCashProvidedByUsedInOperatingActivities"]),
]

# Same "wide by design" reasoning as xbrl_yfinance_crosscheck.py's own threshold comment - a
# starting point, not yet tuned against a live feasibility pass.
_DIVERGENCE_RATIO = 2.0
_DIVERGENCE_FLOOR = 1_000_000.0
_MAX_EXAMPLES_PER_FIELD = 15
_MAX_CONSECUTIVE_AUTH_ERRORS = 3


def _select_symbols(cur: Any, limit: int) -> list[str]:
    """Daily-rotating pseudo-random sample of active symbols with real SEC-audited annual
    income-statement data - same query shape as xbrl_yfinance_crosscheck.py's own sampler."""
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


def run(limit: int, symbols_override: list[str] | None, dry_run: bool) -> dict[str, Any]:
    from psycopg2.extras import DictCursor

    from algo.monitoring.data_patrol.base import CheckResult
    from algo.monitoring.data_patrol.logger import PatrolLogger
    from utils.db.connection import get_db_connection
    from utils.external.xbrl_us_client import XbrlUsAuthError, fact_search

    conn = get_db_connection(max_retries=2, timeout=30)
    cur = conn.cursor(cursor_factory=DictCursor)

    symbols = symbols_override or _select_symbols(cur, limit)
    logger.info(f"[XBRL_US_CROSSCHECK] Sampling {len(symbols)} symbol(s): {symbols}")

    flagged: dict[str, list[dict[str, Any]]] = {f"{t}:{f}": [] for t, f, _ in _FIELDS}
    sampled_count: dict[str, int] = {f"{t}:{f}": 0 for t, f, _ in _FIELDS}
    consecutive_auth_errors = 0
    concept_fetch_errors = 0
    concept_fetch_attempts = 0

    for symbol in symbols:
        if consecutive_auth_errors >= _MAX_CONSECUTIVE_AUTH_ERRORS:
            logger.error(
                f"[XBRL_US_CROSSCHECK] {_MAX_CONSECUTIVE_AUTH_ERRORS} consecutive auth errors - "
                "aborting the rest of this batch (credentials likely invalid/expired, not a "
                "per-symbol data problem)."
            )
            break

        for table, field, concepts in _FIELDS:
            ours = _our_latest_value(cur, table, field, symbol)
            if ours is None:
                continue
            fiscal_year, our_value = ours

            # Try every concept in the chain (not just the first hit) and keep the
            # largest-magnitude fact. FIXED 2026-09-16 (live-caught on REXR): a REIT's
            # "RevenueFromContractWithCustomerExcludingAssessedTax" is real and correctly
            # tagged but ASC 606 explicitly excludes lease income (ASC 842), so for a
            # lease-revenue-heavy filer it's a small non-lease sliver ($589K), not the
            # total - the true top-line total is still tagged under "Revenues" ($1.003B,
            # exactly matching our own value). Stopping at the first concept with ANY fact
            # produced a false >1000x divergence WARN. Picking the max magnitude across all
            # concepts in the chain generalizes correctly for both directions this file's own
            # docstring already documents: it still prefers the ASC-606 concept for AAPL
            # (where "Revenues" is untagged and returns zero facts, so it can't win a max()),
            # while preferring "Revenues" for REITs/lease-heavy filers where it dominates.
            best_value: float | None = None
            for concept in concepts:
                concept_fetch_attempts += 1
                try:
                    concept_facts = fact_search(symbol, concept, fiscal_year, fiscal_period="Y")
                    consecutive_auth_errors = 0
                except XbrlUsAuthError as e:
                    consecutive_auth_errors += 1
                    concept_fetch_errors += 1
                    logger.warning(f"[XBRL_US_CROSSCHECK] auth error fetching {symbol}/{concept}: {e}")
                    break
                except RuntimeError as e:
                    concept_fetch_errors += 1
                    logger.debug(f"[XBRL_US_CROSSCHECK] {symbol}/{concept} fetch failed (non-fatal): {e}")
                    continue
                if not concept_facts:
                    continue
                candidate = float(concept_facts[0]["fact.value"])
                if best_value is None or abs(candidate) > abs(best_value):
                    best_value = candidate

            if best_value is None:
                continue
            xbrl_us_value = best_value

            field_key = f"{table}:{field}"
            sampled_count[field_key] += 1
            if max(abs(our_value), abs(xbrl_us_value)) < _DIVERGENCE_FLOOR or xbrl_us_value == 0:
                continue
            ratio = abs(our_value) / abs(xbrl_us_value)
            if _DIVERGENCE_RATIO > ratio > (1.0 / _DIVERGENCE_RATIO):
                continue
            flagged[field_key].append(
                {
                    "symbol": symbol,
                    "fiscal_year": fiscal_year,
                    "our_value": our_value,
                    "xbrl_us_value": xbrl_us_value,
                    "ratio": round(ratio, 4),
                }
            )

    results: list[CheckResult] = []

    # Every concept fetch attempted this run errored (credentials/auth/API-shape problem) and
    # zero symbols produced a comparable value - without this, that looks identical to a
    # genuinely clean "no divergence found" run in data_patrol_log (both emit 'info' results
    # with 0 flagged), which is exactly how this check silently ran broken for a full day
    # (2026-09-16 root cause: missing .env.local load meant XBRL_US_* credentials were never
    # in the environment, so every fetch failed instantly and was swallowed at DEBUG level).
    total_sampled = sum(sampled_count.values())
    if concept_fetch_attempts > 0 and concept_fetch_errors == concept_fetch_attempts and total_sampled == 0:
        logger.error(
            f"[XBRL_US_CROSSCHECK] All {concept_fetch_attempts} concept fetch(es) failed and 0 symbols "
            "produced a comparable value - this run found nothing to compare, not nothing to flag. "
            "Check credentials/API connectivity, not the data."
        )
        results.append(
            CheckResult(
                "xbrl_us_independent_crosscheck_fetch_health",
                "warn",
                "annual_income_statement",
                f"All {concept_fetch_attempts} XBRL US concept fetch(es) failed this run (0/{len(symbols)} "
                "symbols sampled produced a comparable value) - likely a credentials/auth/API problem, "
                "not a clean run. Review queue.",
                {"attempts": concept_fetch_attempts, "errors": concept_fetch_errors, "symbols_sampled": len(symbols)},
            )
        )

    for table, field, _ in _FIELDS:
        field_key = f"{table}:{field}"
        check_name = f"xbrl_us_independent_crosscheck_{field}"
        examples = flagged[field_key]
        n_sampled = sampled_count[field_key]
        if examples:
            results.append(
                CheckResult(
                    check_name,
                    "warn",
                    table,
                    f"{len(examples)}/{n_sampled} symbol(s) with an XBRL-US-comparable {field} value "
                    f"diverge >{_DIVERGENCE_RATIO:.0f}x from our SEC-derived value (floor "
                    f"${_DIVERGENCE_FLOOR:,.0f}) - review queue, not a confirmed bug.",
                    {"sampled": n_sampled, "flagged": len(examples), "examples": examples[:_MAX_EXAMPLES_PER_FIELD]},
                )
            )
        else:
            results.append(
                CheckResult(
                    check_name,
                    "info",
                    table,
                    f"no >{_DIVERGENCE_RATIO:.0f}x XBRL US divergence in {field} ({n_sampled} symbol(s) "
                    "had a comparable XBRL US value this run)",
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
        logger.info(f"[XBRL_US_CROSSCHECK] Logged {len(results)} result(s) to data_patrol_log (run_id={run_id})")

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
    logger.info(f"[XBRL_US_CROSSCHECK] Done in {elapsed:.1f}s - {summary['sampled_symbols']} symbol(s) sampled")


if __name__ == "__main__":
    main()
