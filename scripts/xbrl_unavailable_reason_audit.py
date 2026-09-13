#!/usr/bin/env python3
"""8th XBRL data-quality layer: audits the "Missing SEC/XBRL data" unavailability VERDICTS
themselves, not the values that made it through.

Added 2026-09-13 (goal session: "question our own assumptions" audit). The other 7 layers
(concept-coverage, calculation-linkbase, DQC/Arelle, segment-sum, yfinance crosscheck,
tie-out, statistical-anomaly) all check whether a computed VALUE is correct. None of them
check whether a "we can't compute this" verdict is still true, or whether a fallback that
already exists is being wrongly skipped by a gate that's broader than the risk it was built
for. That gap is how two real bugs sat unnoticed in this exact bucket:

  1. ATTT (goal: this same audit): DB's latest annual_balance_sheet fiscal year was one year
     behind the filer's real latest 20-F (filed 2026-07-31, already in the SEC EDGAR
     companyfacts cache), because the loader watermark had already advanced past it. See
     Check A below.
  2. eps_never_tagged_in_filings' EPS-from-net-income fallback blanket-excluded every
     foreign private issuer to avoid an ADR/ADS share-count mismatch (the real TSM bug) -
     live re-verified all 19 real cases (BP/AZUL/FMX/etc.) never had that mismatch at all
     (fixed directly in sec_valuations_income_context.py, not detectable by a generic scan
     the way Check A/B below are - that one required reading the actual gating code).

This script covers the two audit shapes that ARE generically automatable across the whole
"Missing SEC/XBRL data" headline population (see coverage_classification.py's
_categorize_reason), one per Check function below. It does NOT try to re-derive every
possible fallback - that's exactly the kind of per-reason, per-symbol forensic work found in
this session's own history, not a mechanical scan.

Check A - DB-behind-filing staleness: for each headline symbol, compares the latest fiscal
year our own annual_income_statement/annual_balance_sheet/annual_cash_flow tables have
(data_unavailable IS NOT TRUE) against the latest annual (10-K/20-F/40-F, fp='FY') fiscal
year the SEC EDGAR companyfacts cache actually has a real revenue/net_income/assets/profit
fact for. A mismatch means the filer has filed something more recent than what we loaded -
worth a real look, though it doesn't guarantee the newer filing has the missing concept
either.

Check B - unresolved yfinance-comparable share count for FPI EPS/PE gaps: flags any
eps_never_tagged_in_filings/pe_ratio "Missing SEC/XBRL data" FPI symbol where yfinance DOES
have a live, plausible sharesOutstanding for that ticker but our own value_metrics/
sec_valuations still shows the gap - a candidate for the exact fallback class fixed in #2
above, surfaced generically instead of requiring another by-hand investigation.

Same posture as the other periodic layers: WARN severity (review queue, not a confirmed
bug), NOT part of every DataPatrol run (Check A reads the local companyfacts cache only -
cheap - but Check B makes live yfinance calls, so it shares that rate-limit discipline),
small rotating sample by default, writes into the same data_patrol_log / data_patrol_review
triage machinery as every other check - no new review path.

Usage:
    python scripts/xbrl_unavailable_reason_audit.py                # sample 40, write findings
    python scripts/xbrl_unavailable_reason_audit.py --limit 80
    python scripts/xbrl_unavailable_reason_audit.py --symbols BP,ATTT,AZUL
    python scripts/xbrl_unavailable_reason_audit.py --dry-run      # print, don't write to data_patrol_log
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "lambda" / "api"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

_CACHE_DIR = os.path.expandvars(r"%TEMP%/algo-sec-edgar-cache/companyfacts")
_ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}
_ANNUAL_TABLES = ("annual_income_statement", "annual_balance_sheet", "annual_cash_flow")
_ANCHOR_CONCEPTS = ("Revenues", "RevenueFromContractsWithCustomers", "Revenue", "NetIncomeLoss", "ProfitLoss", "Assets")
_MAX_EXAMPLES = 15


def _headline_symbols(cur: Any) -> dict[str, list[tuple[str, str, str]]]:
    """Every active-universe symbol currently carrying a real "Missing SEC/XBRL data"
    *_unavailable_reason (or bare `reason`) on its LATEST row per table/column - same
    DISTINCT ON/active-universe/_categorize_reason logic scripts/xbrl_scored_headline_count.py
    uses, reused here rather than reimplemented so this audit always tracks the real live
    headline, not a stale snapshot of it.

    BUG FIX 2026-09-13 (found live while running the full xbrl_second_opinion_daily suite
    during this goal session): this function was missing xbrl_scored_headline_count.py's
    own _UNSCORED_TABLES/_UNSCORED_FACTORS skip - factors deliberately descoped from the
    live composite/display headline but still carrying stale *_unavailable_reason values
    from before they were descoped. Without that skip this counted 1045 symbols against
    the tracked headline's own 126 for the exact same live data - the "reused logic"
    docstring claim above was false until this fix; the two scripts now agree."""
    from routes.scores_handlers.coverage_classification import (
        _UNSCORED_FACTORS,
        _UNSCORED_TABLES,
        _categorize_reason,
    )

    from scripts.xbrl_scored_headline_count import _find_reason_columns
    from utils.loaders.helpers import get_active_symbols

    active = set(get_active_symbols(exclude_etfs=True))
    out: dict[str, list[tuple[str, str, str]]] = {}
    for table, column in _find_reason_columns(cur):
        factor_name = column.replace("_unavailable_reason", "") if column != "reason" else table
        if table in _UNSCORED_TABLES or (table, factor_name) in _UNSCORED_FACTORS:
            continue
        cur.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s "
            "AND column_name IN ('symbol','fiscal_year','date','computed_at','updated_at','created_at')",
            (table,),
        )
        cols = {r[0] for r in cur.fetchall()}
        if "symbol" not in cols:
            continue
        order_col = next(
            (c for c in ("fiscal_year", "date", "computed_at", "updated_at", "created_at") if c in cols), None
        )
        if order_col is None:
            continue
        cur.execute(
            f'SELECT DISTINCT ON (symbol) symbol, "{column}" FROM "{table}" ORDER BY symbol, "{order_col}" DESC'
        )
        for symbol, reason in cur.fetchall():
            if symbol not in active or reason is None:
                continue
            if _categorize_reason(reason) == "Missing SEC/XBRL data":
                out.setdefault(symbol, []).append((table, column, reason))
    return out


def _select_symbols(headline: dict[str, list[tuple[str, str, str]]], limit: int) -> list[str]:
    import hashlib
    from datetime import date

    today = date.today().isoformat()
    ranked = sorted(headline, key=lambda s: hashlib.md5(f"{s}{today}".encode()).hexdigest())
    return ranked[:limit]


def _latest_cached_annual_fy(cik: str | None) -> tuple[int | None, str | None]:
    if cik is None:
        return None, None
    path = os.path.join(_CACHE_DIR, f"{int(cik):010d}.json")
    if not os.path.exists(path):
        return None, None
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, None
    facts = raw.get("data", raw).get("facts", {})
    best_end: str | None = None
    best_fy: int | None = None
    for ns in ("us-gaap", "ifrs-full"):
        for concept_name in _ANCHOR_CONCEPTS:
            concept = facts.get(ns, {}).get(concept_name)
            if not concept:
                continue
            for unit_vals in concept.get("units", {}).values():
                for v in unit_vals:
                    if v.get("form") not in _ANNUAL_FORMS or v.get("fp") != "FY":
                        continue
                    end = v.get("end")
                    if end and (best_end is None or end > best_end):
                        best_end, best_fy = end, v.get("fy")
    return best_fy, best_end


def _latest_db_annual_fy(cur: Any, symbol: str) -> int | None:
    values = []
    for table in _ANNUAL_TABLES:
        cur.execute(
            f"SELECT MAX(fiscal_year) FROM {table} WHERE symbol = %s AND data_unavailable IS NOT TRUE", (symbol,)
        )
        row = cur.fetchone()
        if row and row[0] is not None:
            values.append(row[0])
    return max(values) if values else None


def _check_a_staleness(cur: Any, symbols: list[str], headline: dict[str, list[tuple[str, str, str]]]) -> dict[str, Any]:
    from utils.external.sec_edgar_client import SecEdgarClient

    client = SecEdgarClient()
    examples: list[dict[str, Any]] = []
    sampled = 0
    for symbol in symbols:
        try:
            cik = client.symbol_to_cik(symbol)
        except ValueError:
            continue
        sampled += 1
        cache_fy, cache_end = _latest_cached_annual_fy(cik)
        if cache_fy is None:
            continue
        db_fy = _latest_db_annual_fy(cur, symbol)
        if db_fy is not None and cache_fy <= db_fy:
            continue
        examples.append(
            {
                "symbol": symbol,
                "cache_latest_fiscal_year": cache_fy,
                "cache_latest_period_end": cache_end,
                "db_latest_fiscal_year": db_fy,
                "reasons": [f"{t}.{c}={r}" for t, c, r in headline[symbol]],
            }
        )
    return {"sampled": sampled, "examples": examples}


def _check_b_fpi_yfinance_shares(
    cur: Any, symbols: list[str], headline: dict[str, list[tuple[str, str, str]]]
) -> dict[str, Any]:
    from loaders.helpers.sec_valuations_checks import ValuationSanityCheckMixin

    class _Fetcher(ValuationSanityCheckMixin):
        pass

    fetcher = _Fetcher()
    examples: list[dict[str, Any]] = []
    sampled = 0
    consecutive_failures = 0
    for symbol in symbols:
        reasons = headline[symbol]
        relevant = [
            r for t, c, r in reasons if r in ("eps_never_tagged_in_filings", "missing_sec_data") and "pe_ratio" in c
        ]
        if not relevant:
            relevant = [r for t, c, r in reasons if c == "reason" and r == "eps_never_tagged_in_filings"]
        if not relevant:
            continue
        cur.execute("SELECT is_foreign_private_issuer FROM company_info_sec WHERE symbol = %s", (symbol,))
        row = cur.fetchone()
        if not (row and row[0]):
            continue
        if consecutive_failures >= 3:
            logger.warning("[XBRL_REASON_AUDIT] 3 consecutive yfinance failures - stopping Check B early this run.")
            break
        sampled += 1
        yfinance_shares = fetcher._fetch_live_fpi_shares_outstanding_yfinance(symbol)
        if yfinance_shares is None:
            consecutive_failures += 1
            continue
        consecutive_failures = 0
        examples.append(
            {
                "symbol": symbol,
                "yfinance_shares_outstanding": yfinance_shares,
                "reasons": [f"{t}.{c}={r}" for t, c, r in reasons],
            }
        )
    return {"sampled": sampled, "examples": examples}


def run(limit: int, symbols_override: list[str] | None, dry_run: bool) -> dict[str, Any]:
    from psycopg2.extras import DictCursor

    from algo.monitoring.data_patrol.base import CheckResult
    from algo.monitoring.data_patrol.logger import PatrolLogger
    from utils.db.connection import get_db_connection

    conn = get_db_connection(max_retries=2, timeout=30)
    cur = conn.cursor(cursor_factory=DictCursor)

    headline = _headline_symbols(cur)
    logger.info(f"[XBRL_REASON_AUDIT] {len(headline)} symbol(s) currently in the Missing SEC/XBRL data headline")

    symbols = [s.upper() for s in symbols_override] if symbols_override else _select_symbols(headline, limit)
    symbols = [s for s in symbols if s in headline]
    logger.info(f"[XBRL_REASON_AUDIT] Sampling {len(symbols)} symbol(s) this run")

    check_a = _check_a_staleness(cur, symbols, headline)
    check_b = _check_b_fpi_yfinance_shares(cur, symbols, headline)

    results: list[CheckResult] = []
    if check_a["examples"]:
        results.append(
            CheckResult(
                "xbrl_reason_db_behind_filing",
                "warn",
                "annual_income_statement",
                f"{len(check_a['examples'])}/{check_a['sampled']} symbol(s) carrying a 'Missing "
                "SEC/XBRL data' reason have a newer annual filing in the SEC EDGAR cache than our "
                "own DB's latest loaded fiscal year - review queue: the newer filing may or may "
                "not carry the specific missing concept, but the DB is provably behind it.",
                {
                    "sampled": check_a["sampled"],
                    "flagged": len(check_a["examples"]),
                    "examples": check_a["examples"][:_MAX_EXAMPLES],
                },
            )
        )
    else:
        results.append(
            CheckResult(
                "xbrl_reason_db_behind_filing",
                "info",
                "annual_income_statement",
                f"no DB-behind-filing staleness found ({check_a['sampled']} symbol(s) checked this run)",
            )
        )

    if check_b["examples"]:
        results.append(
            CheckResult(
                "xbrl_reason_fpi_yfinance_shares_available",
                "warn",
                "value_metrics",
                f"{len(check_b['examples'])}/{check_b['sampled']} FPI symbol(s) stuck on "
                "eps_never_tagged_in_filings have a live, fetchable yfinance sharesOutstanding - "
                "review queue: candidate for the FPI EPS-derivation fallback "
                "(sec_valuations_income_context.py._fpi_confirmed_eps_shares_basis) if not "
                "already covered by it.",
                {
                    "sampled": check_b["sampled"],
                    "flagged": len(check_b["examples"]),
                    "examples": check_b["examples"][:_MAX_EXAMPLES],
                },
            )
        )
    else:
        results.append(
            CheckResult(
                "xbrl_reason_fpi_yfinance_shares_available",
                "info",
                "value_metrics",
                f"no unresolved FPI yfinance-shares candidates found ({check_b['sampled']} symbol(s) checked this run)",
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
        logger.info(f"[XBRL_REASON_AUDIT] Logged {len(results)} result(s) to data_patrol_log (run_id={run_id})")

    cur.close()
    conn.close()
    return {"sampled_symbols": len(symbols), "results": [r.to_dict() for r in results]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--limit", type=int, default=40, help="How many headline symbols to sample this run (default 40)"
    )
    parser.add_argument("--symbols", help="Comma-separated explicit symbol list, overrides --limit sampling")
    parser.add_argument("--dry-run", action="store_true", help="Print findings, don't write to data_patrol_log")
    args = parser.parse_args()

    symbols_override = [s.strip() for s in args.symbols.split(",")] if args.symbols else None

    started = time.monotonic()
    summary = run(limit=args.limit, symbols_override=symbols_override, dry_run=args.dry_run)
    elapsed = time.monotonic() - started
    logger.info(f"[XBRL_REASON_AUDIT] Done in {elapsed:.1f}s - {summary['sampled_symbols']} symbol(s) sampled")


if __name__ == "__main__":
    main()
