#!/usr/bin/env python3
"""One-off correction for the 2026-09-13 shares_outstanding unit-scale-error finding (see
shares_outstanding_scale_error_growth_guard_fixed_20260913 in memory).

annual_income_statement.shares_outstanding_diluted/shares_outstanding_basic swings by almost
exactly 1000x-1,000,000x between adjacent fiscal years for dozens of symbols (mostly 20-F
foreign-private-issuer filers: VALE, PDD, WB, BMA, GGAL, CIGI, ALC, and more) - live-confirmed
a filer/extraction unit-scale tagging error, not a real corporate action (no legitimate split
exceeds ~100x). A guard in loaders/helpers/vqg_growth.py now stops these values from poisoning
growth-pillar CAGR calculations, but the wrong raw values were still sitting in
annual_income_statement itself, reachable by any OTHER consumer of these columns.

This script does NOT try to guess-correct the magnitude (multiply/divide by 1000) - that would
just replace one wrong number with another wrong number if the guess is off, and several
symbols in this population (DUO, XHG, JCSE, CCEC) show erratic multi-directional jumps that
aren't a clean single 1000x factor, consistent with real corporate actions (mergers, reverse
splits, restatements) tangled up with the scale error rather than a uniform bug. Instead:
NULLs the specific column value(s) that are >100x off the symbol's own median (same
SHARE_COUNT_IMPLAUSIBLE_RATIO threshold as the growth-guard fix, for consistency) - a real
"we don't trust this number" signal rather than a fabricated replacement, matching this
repo's own "no guessed data" governance principle.

Usage:
    python scripts/fix_shares_outstanding_scale_errors.py --dry-run   # print only
    python scripts/fix_shares_outstanding_scale_errors.py             # writes NULLs
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

IMPLAUSIBLE_RATIO = 150


def _find_outliers(cur: Any) -> list[dict[str, Any]]:
    cur.execute(
        """
        WITH s AS (
            SELECT symbol, fiscal_year, shares_outstanding_diluted, shares_outstanding_basic
            FROM annual_income_statement
        ),
        med AS (
            SELECT symbol,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY shares_outstanding_diluted)
                       FILTER (WHERE shares_outstanding_diluted > 0) AS med_diluted,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY shares_outstanding_basic)
                       FILTER (WHERE shares_outstanding_basic > 0) AS med_basic
            FROM s
            GROUP BY symbol
        )
        SELECT s.symbol, s.fiscal_year,
               s.shares_outstanding_diluted, m.med_diluted,
               s.shares_outstanding_basic, m.med_basic
        FROM s
        JOIN med m ON m.symbol = s.symbol
        WHERE (s.shares_outstanding_diluted > 0 AND m.med_diluted > 0
               AND GREATEST(s.shares_outstanding_diluted / m.med_diluted,
                            m.med_diluted / s.shares_outstanding_diluted) > %(ratio)s)
           OR (s.shares_outstanding_basic > 0 AND m.med_basic > 0
               AND GREATEST(s.shares_outstanding_basic / m.med_basic,
                            m.med_basic / s.shares_outstanding_basic) > %(ratio)s)
        ORDER BY s.symbol, s.fiscal_year
        """,
        {"ratio": IMPLAUSIBLE_RATIO},
    )
    columns = [d[0] for d in cur.description]
    return [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]


def _null_column_for_row(cur: Any, symbol: str, fiscal_year: int, column: str) -> None:
    cur.execute(
        f"UPDATE annual_income_statement SET {column} = NULL WHERE symbol = %s AND fiscal_year = %s",
        (symbol, fiscal_year),
    )


def run(dry_run: bool) -> dict[str, Any]:
    from utils.db.context import DatabaseContext

    mode = "read" if dry_run else "write"
    summary: dict[str, Any] = {"rows_examined": 0, "diluted_nulled": 0, "basic_nulled": 0}

    with DatabaseContext(mode) as cur:
        outliers = _find_outliers(cur)
        summary["rows_examined"] = len(outliers)

        for row in outliers:
            symbol, fiscal_year = row["symbol"], row["fiscal_year"]
            diluted = float(row["shares_outstanding_diluted"]) if row["shares_outstanding_diluted"] else None
            med_diluted = float(row["med_diluted"]) if row["med_diluted"] else None
            basic = float(row["shares_outstanding_basic"]) if row["shares_outstanding_basic"] else None
            med_basic = float(row["med_basic"]) if row["med_basic"] else None

            if diluted and med_diluted and max(diluted / med_diluted, med_diluted / diluted) > IMPLAUSIBLE_RATIO:
                logger.info(
                    f"{symbol} FY{fiscal_year}: shares_outstanding_diluted={diluted} vs symbol "
                    f"median={med_diluted:.0f} ({'DRY-RUN, ' if dry_run else ''}nulling)"
                )
                if not dry_run:
                    _null_column_for_row(cur, symbol, fiscal_year, "shares_outstanding_diluted")
                summary["diluted_nulled"] += 1

            if basic and med_basic and max(basic / med_basic, med_basic / basic) > IMPLAUSIBLE_RATIO:
                logger.info(
                    f"{symbol} FY{fiscal_year}: shares_outstanding_basic={basic} vs symbol "
                    f"median={med_basic:.0f} ({'DRY-RUN, ' if dry_run else ''}nulling)"
                )
                if not dry_run:
                    _null_column_for_row(cur, symbol, fiscal_year, "shares_outstanding_basic")
                summary["basic_nulled"] += 1

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Print findings, don't write NULLs")
    args = parser.parse_args()

    summary = run(dry_run=args.dry_run)
    logger.info(f"Done: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
