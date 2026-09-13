#!/usr/bin/env python3
"""One-off correction for the 2026-09-13 noncontrolling-interest double-count finding (see
spac_temporary_equity_fy2025_extraction_gap_lead_20260913 in memory).

Two extraction bugs in utils/external/sec_balance_sheet.py were fixed this session
(10b444644, 7e2454582) so a FUTURE reload of these filings won't reproduce the double-count -
but the wrong values are still sitting in annual_balance_sheet right now, reachable by any
consumer of total_liabilities/stockholders_equity (book value, ROE, leverage ratios).

Systematically verified via scripts/balance_sheet_identity_residual_classifier.py's
nci_double_count signature (residual == -noncontrolling_interest) that ALL 172 currently
affected symbols hit this through the SAME mechanism: total_liabilities was derived as
LiabilitiesAndStockholdersEquity - stockholders_equity (no plain "Liabilities" concept tagged),
without subtracting noncontrolling_interest - confirmed by checking
total_liabilities == total_assets - stockholders_equity (exactly, to 0.01% of assets) for
every one of them. So the single correction needed is: total_liabilities -= noncontrolling_interest.

Deliberately does NOT touch stockholders_equity (the OTHER fix, for the IFRS Equity-total case)
- live-verified none of the 172 currently-flagged symbols need that correction; if this
assumption ever breaks (a future run finds a symbol where total_liabilities is NOT the derived
value), this script skips it rather than guessing, same "don't guess-correct" discipline as
fix_shares_outstanding_scale_errors.py.

Usage:
    python scripts/fix_balance_sheet_nci_double_count.py --dry-run   # print only
    python scripts/fix_balance_sheet_nci_double_count.py             # writes corrections
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
            continue  # already balances, not affected
        if abs(residual + nci) > max(1.0, abs(nci) * 0.001):
            continue  # not the nci_double_count signature specifically
        derived_liab = assets - eq
        if abs(liab - derived_liab) > max(1.0, abs(assets) * DERIVED_LIABILITIES_TOLERANCE_PCT):
            continue  # not the derived-liabilities mechanism - don't guess-correct
        corrected_liabilities = liab - nci
        # SAFETY GUARD (live-confirmed 2026-09-13, TK/Teekay Corp): numeric coincidence can make
        # a REAL, directly-tagged "Liabilities" fact equal assets-equity even when it was NOT
        # derived that way - TK's real 20-F Liabilities=$396,292,000 (FY2023) happened to match
        # this heuristic exactly, but the actual bug for TK is on the EQUITY side (stockholders_
        # equity itself includes NCI, confirmed via TK's real companyfacts JSON), not liabilities.
        # Blindly subtracting nci from TK's already-correct Liabilities produced a NEGATIVE
        # total_liabilities (-$671,776,000) - a hard sanity floor catches this class of false
        # positive without needing a live SEC fetch per row.
        if corrected_liabilities <= 0:
            logger.warning(
                f"{row['symbol']} FY{row['fiscal_year']}: skipping - corrected total_liabilities "
                f"would be {corrected_liabilities:,.0f} (<= 0), meaning this symbol's "
                "total_liabilities is likely a real directly-tagged value that only "
                "coincidentally matches the derived-liabilities heuristic, not an actual "
                "derivation - the real bug here (if any) is elsewhere (e.g. stockholders_equity "
                "itself including NCI) and needs live SEC verification before touching."
            )
            continue
        affected.append({**row, "corrected_liabilities": corrected_liabilities})
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
            old_liab, new_liab = float(row["total_liabilities"]), row["corrected_liabilities"]
            logger.info(
                f"{symbol} FY{fiscal_year}: total_liabilities {old_liab:,.0f} -> {new_liab:,.0f} "
                f"(subtracting noncontrolling_interest={float(row['noncontrolling_interest']):,.0f})"
                f"{' [DRY-RUN]' if dry_run else ''}"
            )
            if not dry_run:
                cur.execute(
                    "UPDATE annual_balance_sheet SET total_liabilities = %s WHERE symbol = %s AND fiscal_year = %s",
                    (new_liab, symbol, fiscal_year),
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
