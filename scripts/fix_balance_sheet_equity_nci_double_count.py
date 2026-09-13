#!/usr/bin/env python3
"""One-off correction for the 2026-09-13 noncontrolling-interest double-count finding, equity
side (see spac_temporary_equity_fy2025_extraction_gap_lead_20260913 in memory).

Sibling of scripts/fix_balance_sheet_nci_double_count.py, which corrected the
liabilities-derivation mechanism (1,527 cells). This corrects the OTHER mechanism fixed by the
same session's b1115ae/10b444644: a filer that only ever tags an "...IncludingPortionAttributable
ToNoncontrollingInterest"/ifrs-full:Equity TOTAL equity concept (never a parent-only one) has
stockholders_equity itself holding the NCI-inclusive figure. Correction: subtract
noncontrolling_interest from stockholders_equity.

Only touches rows where residual == -noncontrolling_interest AND total_liabilities is NOT the
derived-assets-minus-equity value (already handled by the liabilities-side script) - i.e. the
remaining population after that correction. Live-confirmed the shape via TK/Teekay Corp's
real companyfacts JSON.

Usage:
    python scripts/fix_balance_sheet_equity_nci_double_count.py --dry-run
    python scripts/fix_balance_sheet_equity_nci_double_count.py
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

IDENTITY_TOLERANCE_PCT = 0.01
DERIVED_LIABILITIES_TOLERANCE_PCT = 0.0001


def _find_double_counted_rows(cur: Any) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT symbol, fiscal_year, total_assets, total_liabilities, stockholders_equity,
               noncontrolling_interest, COALESCE(temporary_equity, 0) AS te
        FROM annual_balance_sheet
        WHERE data_unavailable = FALSE
          AND total_assets IS NOT NULL AND total_liabilities IS NOT NULL
          AND stockholders_equity IS NOT NULL AND total_assets != 0
          AND noncontrolling_interest IS NOT NULL AND noncontrolling_interest != 0
        """
    )
    columns = [d[0] for d in cur.description]
    rows = [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]

    affected = []
    for row in rows:
        assets, liab, eq, nci, te = (
            float(row["total_assets"]),
            float(row["total_liabilities"]),
            float(row["stockholders_equity"]),
            float(row["noncontrolling_interest"]),
            float(row["te"]),
        )
        implied = liab + eq + nci + te
        residual = assets - implied
        identity_tol = max(1.0, abs(assets) * IDENTITY_TOLERANCE_PCT)
        if abs(residual) <= identity_tol:
            continue
        if abs(residual + nci) > max(1.0, abs(nci) * 0.001):
            continue  # not the nci_double_count signature
        derived_liab = assets - eq
        if abs(liab - derived_liab) <= max(1.0, abs(assets) * DERIVED_LIABILITIES_TOLERANCE_PCT):
            continue  # already handled by fix_balance_sheet_nci_double_count.py (liabilities side)
        corrected_equity = eq - nci
        # SAFETY GUARD: a corrected equity that flips sign relative to the uncorrected value in
        # an extreme way, or where equity currently EQUALS nci exactly (both mapped from the
        # same source fact by some other bug, live-confirmed on IRD/RR - corrected equity would
        # be exactly 0, indistinguishable from "no real equity data" vs "double count") needs a
        # human look, not an automatic correction.
        if eq == nci:
            logger.warning(
                f"{row['symbol']} FY{row['fiscal_year']}: skipping - stockholders_equity "
                f"({eq:,.0f}) exactly equals noncontrolling_interest, corrected value would be "
                "exactly 0 - ambiguous between a real double-count and a different extraction "
                "bug (e.g. both fields sourced from the same fact by mistake). Needs live SEC "
                "verification before touching."
            )
            continue
        affected.append({**row, "corrected_equity": corrected_equity})
    return affected


def run(dry_run: bool) -> dict[str, Any]:
    from utils.db.context import DatabaseContext

    mode = "read" if dry_run else "write"
    summary: dict[str, Any] = {"rows_examined": 0, "corrected": 0}

    with DatabaseContext(mode) as cur:
        affected = _find_double_counted_rows(cur)
        summary["rows_examined"] = len(affected)

        for row in affected:
            symbol, fiscal_year = row["symbol"], row["fiscal_year"]
            old_eq, new_eq = float(row["stockholders_equity"]), row["corrected_equity"]
            logger.info(
                f"{symbol} FY{fiscal_year}: stockholders_equity {old_eq:,.0f} -> {new_eq:,.0f} "
                f"(subtracting noncontrolling_interest={float(row['noncontrolling_interest']):,.0f})"
                f"{' [DRY-RUN]' if dry_run else ''}"
            )
            if not dry_run:
                cur.execute(
                    "UPDATE annual_balance_sheet SET stockholders_equity = %s WHERE symbol = %s AND fiscal_year = %s",
                    (new_eq, symbol, fiscal_year),
                )
                summary["corrected"] += 1

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Print findings, don't write corrections")
    args = parser.parse_args()

    summary = run(dry_run=args.dry_run)
    logger.info(f"Done: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
