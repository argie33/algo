#!/usr/bin/env python3
"""One-off correction for 2 individually-verified real bugs found while investigating the
"temp_equity_double_count" classifier signature (see
spac_temporary_equity_fy2025_extraction_gap_lead_20260913 in memory) - NOT a bulk/generalized
fix, since that investigation confirmed the ~136-symbol population is heterogeneous (at least
3 different bug shapes plus likely-correct real mezzanine-equity balances) and unsafe to
correct in bulk without per-symbol live SEC verification.

CRWD (CrowdStrike): annual_balance_sheet's fiscal_year=2019 row held a Q3 FY2020 10-Q
snapshot (period end 2019-10-31, form=10-Q, fp=Q3, fy=2020) instead of the real fiscal_year=
2019 (period end 2019-01-31) values - live-confirmed via CrowdStrike's own first 10-K (fy=
2020, form=10-K, fp=FY), which reports the 2019-01-31 comparative column identically across
4 separate filings (3 10-Qs + the 10-K itself): Assets=$433,219,000, Liabilities=$363,100,000,
StockholdersEquity=-$487,793,000 (real, correct - pre-IPO accumulated deficit),
TemporaryEquityCarryingAmountAttributableToParent=$557,912,000. These four values satisfy the
balance-sheet identity exactly (363,100,000 - 487,793,000 + 557,912,000 = 433,219,000).

HYPR (Hyperfine): annual_balance_sheet's fiscal_year=2021 temporary_equity ($158,747,000) came
from a real XBRL fact, but that fact's own end date (2021-07-06) is Hyperfine's SPAC-merger
closing date - a one-time note disclosure, not the FY2021 (2021-12-31) year-end balance.
Live-confirmed the real FY-end balance has zero temporary equity (fully converted to permanent
stock by year-end): Liabilities($16,246,000) + StockholdersEquity($186,227,000, both already
correctly stored) already equal Assets($202,473,000) exactly with temporary_equity=0.

Usage:
    python scripts/fix_crwd_hypr_balance_sheet_period_mismatch.py --dry-run
    python scripts/fix_crwd_hypr_balance_sheet_period_mismatch.py
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def run(dry_run: bool) -> None:
    from utils.db.context import DatabaseContext

    mode = "read" if dry_run else "write"
    with DatabaseContext(mode) as cur:
        logger.info(
            "CRWD FY2019: total_assets/total_liabilities/stockholders_equity/temporary_equity "
            "-> 433219000.00/363100000.00/-487793000.00/557912000.00 (real 2019-01-31 values, "
            "was holding a mislabeled 2019-10-31 Q3 FY2020 snapshot)"
            f"{' [DRY-RUN]' if dry_run else ''}"
        )
        if not dry_run:
            cur.execute(
                """
                UPDATE annual_balance_sheet
                SET total_assets = %s, total_liabilities = %s, stockholders_equity = %s, temporary_equity = %s
                WHERE symbol = 'CRWD' AND fiscal_year = 2019
                """,
                (433219000.00, 363100000.00, -487793000.00, 557912000.00),
            )
            logger.info(f"CRWD rows updated: {cur.rowcount}")

        logger.info(
            "HYPR FY2021: temporary_equity -> NULL (was 158747000.00, a spurious off-period "
            f"note-disclosure fact){' [DRY-RUN]' if dry_run else ''}"
        )
        if not dry_run:
            cur.execute(
                "UPDATE annual_balance_sheet SET temporary_equity = NULL WHERE symbol = 'HYPR' AND fiscal_year = 2021"
            )
            logger.info(f"HYPR rows updated: {cur.rowcount}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Print findings, don't write corrections")
    args = parser.parse_args()

    run(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
