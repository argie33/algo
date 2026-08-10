#!/usr/bin/env python3
"""Prune stale rows for out-of-scope symbols from single-row-per-symbol snapshot tables.

Context (found 2026-07-21): several loaders set `exclude_etfs_from_symbols = True`
(stocks-only) and write one row per symbol, keyed on symbol alone (no history). When a
symbol is later delisted (removed from `stock_symbols` entirely - this codebase hard-
deletes rather than soft-deletes) or was written before an ETF-exclusion fix landed, its
row is never touched again by any loader - it just sits there forever. A one-time cleanup
on 2026-07-21 removed 10,904 such rows (2,272 ETF-leak rows in momentum_metrics, 2,273 in
stability_metrics, and 5,426 in sec_valuations from a since-fixed ETF leak; ~20-150 leftover
rows per table from ordinary delisting in the rest). This script is the reusable version of
that cleanup - run it periodically (there's no automatic trigger; nothing currently calls
this from the pipeline) to prevent the same accumulation from silently recurring.

Deliberately excludes `earnings_calendar_sec` (and any other per-event/historical table):
that table stores one row per symbol per earnings date, so rows for delisted symbols are a
legitimate historical record, not slop. Only touch tables that are true single-row
snapshots - check `primary_key = ("symbol",)` on the loader class before adding one here.

Usage:
  python scripts/prune_stale_snapshot_symbols.py            # dry run (default) - prints counts only
  python scripts/prune_stale_snapshot_symbols.py --execute  # actually deletes + commits
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db.context import DatabaseContext
from utils.logging.logger import get_logger

logger = get_logger(__name__)

# Single-row-per-symbol snapshot tables whose loaders set exclude_etfs_from_symbols=True
# (stocks-only universe). Cross-reference loaders/loader_registry.py's LOADER_TABLES if a
# new stocks-only snapshot loader is added - it belongs here too.
STOCKS_ONLY_SNAPSHOT_TABLES = [
    "growth_metrics",
    "quality_metrics",
    "value_metrics",
    "stability_metrics",
    "momentum_metrics",
    "positioning_metrics",
    "stock_scores",
    "institutional_holdings_13f",
    "insider_holdings_sec",
    "short_interest_finra",
    "company_info_sec",
    "sec_valuations",
    "sec_cash_flow_metrics",
    # Added 2026-07-28: primary_key = ("symbol",), exclude_etfs_from_symbols = True -
    # same single-row-per-symbol shape as the tables above, confirmed via
    # load_sec_segment_metrics.py. 58 orphaned rows found live the day this was added.
    "sec_segment_metrics",
]

# Single-row-per-symbol snapshot tables that intentionally cover BOTH stocks and ETFs (no
# exclude_etfs_from_symbols), so staleness must be checked against the union of
# stock_symbols and etf_symbols, not stock_symbols alone - checking against stock_symbols
# only would misclassify every legitimately-covered ETF row as orphaned.
UNIVERSAL_SNAPSHOT_TABLES = [
    # load_company_profile.py: primary_key = ("ticker",) (DB column is `symbol`), no
    # exclude_etfs_from_symbols - restored 2026-07-27, covers both universes. 242 orphaned
    # rows found live the day this was added (delisted from both stock_symbols and
    # etf_symbols entirely, not an ETF-scoping miss).
    "company_profile",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Actually delete rows (default: dry run)")
    args = parser.parse_args()

    role = "write" if args.execute else "read"
    total = 0
    with DatabaseContext(role) as cur:
        for table, scope_clause in [
            *(
                (t, "SELECT 1 FROM stock_symbols s WHERE s.symbol = tt.symbol AND s.active = true")
                for t in STOCKS_ONLY_SNAPSHOT_TABLES
            ),
            *(
                (
                    t,
                    "SELECT 1 FROM stock_symbols s WHERE s.symbol = tt.symbol AND s.active = true "
                    "UNION SELECT 1 FROM etf_symbols e WHERE e.symbol = tt.symbol",  # etf_symbols has no active column - all rows are in-scope
                )
                for t in UNIVERSAL_SNAPSHOT_TABLES
            ),
        ]:
            cur.execute(f"SELECT COUNT(*) FROM {table} tt WHERE NOT EXISTS ({scope_clause})")
            stale_count = cur.fetchone()[0]
            total += stale_count
            if args.execute and stale_count > 0:
                cur.execute(f"DELETE FROM {table} tt WHERE NOT EXISTS ({scope_clause})")
            logger.info(f"{table:28s} {'deleted' if args.execute else 'stale (dry run)':20s} {stale_count}")

    logger.info(f"TOTAL: {total} stale rows {'deleted' if args.execute else 'found (rerun with --execute to delete)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
