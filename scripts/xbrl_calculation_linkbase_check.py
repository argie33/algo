#!/usr/bin/env python3
"""Layer 5/5 of the institutional XBRL data-quality build: calculation-linkbase
self-consistency - validating a filing's OWN declared XBRL arithmetic relationships
(e.g. Assets = AssetsCurrent + AssetsNoncurrent) directly against the reported fact
values for that same filing.

This is the piece explicitly flagged as "not implemented yet, needs a new data source/
pipeline" in scripts/xbrl_yfinance_crosscheck.py's docstring (layer 4) and in
MEMORY.md's 20260910 goal session. The five layers, for context:
    1. Self-consistency (arithmetic identities across OUR derived fields) -
       algo/monitoring/data_patrol/checks/tie_out*.py
    2. Statistical/peer-history outlier detection - statistical_anomaly.py
    3. Negative-value/definitional guards (DQC-style) - tie_out_nonnegative_magnitudes.py
    4. Independent second-opinion cross-check (yfinance) - xbrl_yfinance_crosscheck.py
    5. Calculation-linkbase self-consistency (THIS SCRIPT)

Layers 1-3 only ever look at values WE already extracted into our own tables - they
can't catch a bug where our extraction picked the wrong XBRL concept/context but did so
*consistently* (so our own identities still tie, and the wrong number doesn't look
statistically weird either). Layer 5 is different in kind from all four: it doesn't
touch our tables at all. It parses the filer's own calculation linkbase (a structural
XBRL document declaring which line items are declared subtotals of which others) and
checks reported us-gaap fact values against the filer's own arithmetic - entirely
independent of anything our loaders do. A mismatch here means the FILING itself is
internally inconsistent (rare but real - filer tagging errors happen) or, more likely
in practice, reveals a concept relationship worth knowing about even when it ties.

Deliberately NOT part of every DataPatrol run, same reasoning as
xbrl_yfinance_crosscheck.py: each symbol costs 2-3 extra live SEC EDGAR requests
(submissions, filing index, calculation linkbase XML - companyfacts is normally
already warm from other loaders via the shared disk cache in
utils/external/sec_edgar_client.py) through the same rate-limited session every loader
shares. Run by hand or from a low-frequency schedule on a small rotating sample.

Usage:
    python scripts/xbrl_calculation_linkbase_check.py                # sample 15, write findings
    python scripts/xbrl_calculation_linkbase_check.py --limit 30
    python scripts/xbrl_calculation_linkbase_check.py --symbols AAPL,MSFT,KO
    python scripts/xbrl_calculation_linkbase_check.py --dry-run       # print only
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

# A parent concept must have at least this many children (all resolvable to us-gaap
# facts on the SAME filing) before we bother checking it - a single-child "sum" is
# usually just a relabeling/nil-weight housekeeping arc, not a real subtotal assertion.
_MIN_CHILDREN = 2

# Real filings legitimately don't tie to the last dollar (rounding to the nearest
# thousand/million during tagging, immaterial reclass between subtotal and detail rows
# in the same period). This tolerance is a starting point, not tuned against a live
# feasibility pass - tighten once real runs show the normal near-miss distribution.
_RELATIVE_TOLERANCE = 0.02
_ABSOLUTE_FLOOR = 50_000.0

_MAX_PARENTS_CHECKED_PER_FILING = 40
_MAX_EXAMPLES = 20


def _select_symbols(cur: Any, limit: int) -> list[str]:
    """Daily-rotating pseudo-random sample of active symbols with real SEC-audited
    annual balance-sheet data - mirrors xbrl_yfinance_crosscheck.py's _select_symbols."""
    cur.execute(
        """
        SELECT symbol FROM (
            SELECT DISTINCT abs.symbol
            FROM annual_balance_sheet abs
            JOIN stock_symbols s ON s.symbol = abs.symbol AND s.active = true
            WHERE abs.data_source = 'sec_audited' AND abs.data_unavailable = FALSE
        ) candidates
        ORDER BY md5(symbol || CURRENT_DATE::text)
        LIMIT %s
        """,
        (limit,),
    )
    return [row[0] for row in cur.fetchall()]


def _latest_10k_accession(submissions: dict[str, Any]) -> tuple[str, str] | None:
    """Most recently filed original 10-K (not 10-K/A) accession + filed date, or None."""
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    filed = recent.get("filingDate", [])
    best: tuple[str, str] | None = None
    for form, accn, date in zip(forms, accessions, filed, strict=False):
        if form != "10-K":
            continue
        if best is None or date > best[1]:
            best = (accn, date)
    return best


def _facts_by_concept_for_accession(
    company_facts: dict[str, Any], taxonomy: str, concept: str, accession_number: str
) -> float | None:
    """Reported value for one us-gaap concept on this exact filing (matched by accn -
    ties the value to the SAME document the calculation linkbase came from, not just
    "the latest value we happen to have" which could be a later restatement).

    Prefers USD; if multiple facts share (accn, concept) - e.g. both an instant and a
    duration context somehow tag the same concept, or FY vs cumulative quarters - takes
    the one with the longest/most-recent period end, which is the one a balance-sheet
    or full-year income-statement calc relationship actually means.
    """
    node = company_facts.get("facts", {}).get(taxonomy, {}).get(concept)
    if not node:
        return None
    units: dict[str, list[dict[str, Any]]] = node.get("units", {})
    entries: list[dict[str, Any]] = units.get("USD") or next(iter(units.values()), [])
    matches = [e for e in entries if e.get("accn") == accession_number and e.get("val") is not None]
    if not matches:
        return None
    matches.sort(key=lambda e: e.get("end") or "")
    return float(matches[-1]["val"])


def _resolve_tree_children(
    child_arcs: list[Any], company_facts: dict[str, Any], accession_number: str
) -> list[tuple[str, float, float]] | None:
    """Resolve one calculation tree's child arcs to (concept, weight, value) triples,
    or None if any child isn't a us-gaap concept resolvable to a fact on this filing."""
    if len({a.child_concept for a in child_arcs}) < _MIN_CHILDREN:
        return None
    child_values: list[tuple[str, float, float]] = []
    for arc in child_arcs:
        child_taxonomy, _, child_concept_name = arc.child_concept.partition(":")
        if child_taxonomy != "us-gaap" or not child_concept_name:
            return None
        child_value = _facts_by_concept_for_accession(company_facts, "us-gaap", child_concept_name, accession_number)
        if child_value is None:
            return None
        child_values.append((child_concept_name, arc.weight, child_value))
    return child_values


def _best_tying_tree(
    trees: list[list[Any]], parent_value: float, company_facts: dict[str, Any], accession_number: str
) -> tuple[float, float, list[tuple[str, float, float]]] | None:
    """Evaluate every independent calculation tree for one parent concept (see
    group_by_parent's docstring for why there can be more than one) and return the
    closest-tying one as (diff, expected, child_values), or None if no tree had every
    child concept resolvable to a us-gaap fact on this filing."""
    best: tuple[float, float, list[tuple[str, float, float]]] | None = None
    for child_arcs in trees:
        child_values = _resolve_tree_children(child_arcs, company_facts, accession_number)
        if child_values is None:
            continue
        expected = sum(weight * value for _, weight, value in child_values)
        diff = abs(expected - parent_value)
        if best is None or diff < best[0]:
            best = (diff, expected, child_values)
    return best


def _check_symbol(client: Any, cur: Any, symbol: str) -> dict[str, Any] | None:
    from utils.external.sec_calculation_linkbase import (
        group_by_parent,
        is_primary_statement_role,
        parse_calculation_arcs,
    )

    try:
        cik = client.symbol_to_cik(symbol)
    except ValueError:
        return None

    try:
        submissions = client.get_submissions(cik)
    except (FileNotFoundError, RuntimeError) as e:
        logger.debug(f"[CALC_LINKBASE] {symbol}: submissions fetch failed: {e}")
        return None

    latest = _latest_10k_accession(submissions)
    if latest is None:
        return None
    accession_number, filed_date = latest

    try:
        cal_xml = client.get_calculation_linkbase_xml(cik, accession_number)
    except FileNotFoundError:
        return None  # No calc linkbase on this filing (pre-Inline-XBRL era) - nothing to check
    except RuntimeError as e:
        logger.debug(f"[CALC_LINKBASE] {symbol}: calc linkbase fetch failed: {e}")
        return None

    try:
        company_facts = client.get_company_facts(cik)
    except (FileNotFoundError, RuntimeError) as e:
        logger.debug(f"[CALC_LINKBASE] {symbol}: company facts fetch failed: {e}")
        return None

    arcs = [a for a in parse_calculation_arcs(cal_xml) if is_primary_statement_role(a.role)]
    grouped = group_by_parent(arcs)

    checked = 0
    mismatches: list[dict[str, Any]] = []
    for parent_concept, trees in grouped.items():
        if checked >= _MAX_PARENTS_CHECKED_PER_FILING:
            break
        taxonomy, _, concept = parent_concept.partition(":")
        if taxonomy != "us-gaap" or not concept:
            continue  # Only the standard taxonomy is guaranteed comparable across filers

        parent_value = _facts_by_concept_for_accession(company_facts, "us-gaap", concept, accession_number)
        if parent_value is None:
            continue

        # A parent can have more than one independently-valid calculation tree (see
        # group_by_parent's docstring) - evaluate each separately and only flag a
        # mismatch if NONE of them tie; report the closest-tying tree either way.
        best = _best_tying_tree(trees, parent_value, company_facts, accession_number)
        if best is None:
            continue

        checked += 1
        diff, expected, child_values = best
        tolerance = max(_ABSOLUTE_FLOOR, _RELATIVE_TOLERANCE * max(abs(parent_value), abs(expected)))
        if diff <= tolerance:
            continue
        mismatches.append(
            {
                "parent_concept": concept,
                "parent_value": parent_value,
                "expected_from_children": expected,
                "diff": diff,
                "children": [{"concept": c, "weight": w, "value": v} for c, w, v in child_values],
            }
        )

    if checked == 0:
        return None
    return {
        "symbol": symbol,
        "accession_number": accession_number,
        "filed_date": filed_date,
        "parents_checked": checked,
        "mismatches": mismatches,
    }


def run(limit: int, symbols_override: list[str] | None, dry_run: bool) -> dict[str, Any]:
    from psycopg2.extras import DictCursor

    from algo.monitoring.data_patrol.base import CheckResult
    from algo.monitoring.data_patrol.logger import PatrolLogger
    from utils.db.connection import get_db_connection
    from utils.external.sec_edgar_client import SecEdgarClient

    conn = get_db_connection(max_retries=2, timeout=30)
    cur = conn.cursor(cursor_factory=DictCursor)
    client = SecEdgarClient()

    symbols = symbols_override or _select_symbols(cur, limit)
    logger.info(f"[CALC_LINKBASE] Sampling {len(symbols)} symbol(s): {symbols}")

    per_symbol: list[dict[str, Any]] = []
    for symbol in symbols:
        outcome = _check_symbol(client, cur, symbol)
        if outcome is not None:
            per_symbol.append(outcome)

    total_parents_checked = sum(r["parents_checked"] for r in per_symbol)
    all_mismatches = [
        {"symbol": r["symbol"], "accession_number": r["accession_number"], "filed_date": r["filed_date"], **m}
        for r in per_symbol
        for m in r["mismatches"]
    ]

    results: list[CheckResult] = []
    check_name = "xbrl_calculation_linkbase_self_consistency"
    if all_mismatches:
        results.append(
            CheckResult(
                check_name,
                "warn",
                "financial_statements",
                f"{len(all_mismatches)} calculation-linkbase mismatch(es) across "
                f"{len({m['symbol'] for m in all_mismatches})} symbol(s) ({total_parents_checked} "
                f"parent/children subtotal relationship(s) checked total) - a filing's own declared "
                f"summation-item arithmetic didn't tie within {_RELATIVE_TOLERANCE:.0%} tolerance "
                f"(floor ${_ABSOLUTE_FLOOR:,.0f}). Review queue, not automatically a bug: legitimate "
                "causes include immaterial reclass between a subtotal and its detail rows, or "
                "dimensional (segment/member) facts colliding with the consolidated total under the "
                "same concept name.",
                {"symbols_with_filings_checked": len(per_symbol), "examples": all_mismatches[:_MAX_EXAMPLES]},
            )
        )
    else:
        results.append(
            CheckResult(
                check_name,
                "info",
                "financial_statements",
                f"no calculation-linkbase mismatches ({len(per_symbol)} symbol(s) had a checkable "
                f"filing, {total_parents_checked} parent/children relationship(s) verified)",
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
        logger.info(f"[CALC_LINKBASE] Logged {len(results)} result(s) to data_patrol_log (run_id={run_id})")

    cur.close()
    conn.close()
    return {"sampled_symbols": len(symbols), "results": [r.to_dict() for r in results]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=15, help="How many symbols to sample this run (default 15)")
    parser.add_argument("--symbols", help="Comma-separated explicit symbol list, overrides --limit sampling")
    parser.add_argument("--dry-run", action="store_true", help="Print findings, don't write to data_patrol_log")
    args = parser.parse_args()

    symbols_override = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else None

    started = time.monotonic()
    summary = run(limit=args.limit, symbols_override=symbols_override, dry_run=args.dry_run)
    elapsed = time.monotonic() - started
    logger.info(f"[CALC_LINKBASE] Done in {elapsed:.1f}s - {summary['sampled_symbols']} symbol(s) sampled")


if __name__ == "__main__":
    main()
