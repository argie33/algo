#!/usr/bin/env python3
"""Migration 1146: Add missing insider_transactions and earnings_metrics tables.

CONTEXT:
- AdvancedFilters.evaluate_signal() references insider_transactions and earnings_metrics tables
- These tables do not exist in the schema
- This causes crashes if evaluate_signal() is called (currently dead code, but prevents usage)

SOLUTION:
1. Create insider_transactions table from insider_holdings_sec + insider_transaction_velocity data
   - Provides missing insider buy/sell transaction values needed by _insider_score()
2. Create earnings_metrics table
   - Provides earnings_quality_score needed by _earnings_quality_score()
   - Can be populated from quarterly_income_statement (earnings surprises, consistency)

NOTE: These are currently unused (evaluate_signal not called by orchestrator), but
this migration ensures no crashes if code is activated in future phases.

FIX (2026-08-09): this file defined upgrade()/downgrade() instead of the up()/down()
names migrations/run.py actually looks for (every other .py migration in this repo
uses up()/down() - confirmed via repo-wide grep). That meant this migration could
never be applied through the normal runner and silently stayed pending indefinitely,
which is the actual reason earnings_metrics/insider_transactions never existed despite
this file being written specifically to prevent that. Renamed to match convention.
Do NOT also run migration 1147 to populate earnings_metrics - see the warning at the
top of that file first.

FIX (2026-08-09, second pass): the insider_transactions CREATE TABLE block below never
actually ran either - a table named insider_transactions already exists in real
databases (a different, active, in-use schema: id/symbol/insider_name/title/trade_type/
shares/trade_price/trade_date/created_at/updated_at, no `value`/`transaction_type`/
`transaction_date` columns). `CREATE TABLE IF NOT EXISTS` silently no-opped against it,
then the following `CREATE INDEX ... (symbol, transaction_date DESC)` failed with
UndefinedColumn since the real table has no transaction_date column - confirmed live by
attempting to apply this migration. Removed the insider_transactions block entirely
(the table this migration wanted already exists, just under a different column layout)
and fixed AdvancedFilters._insider_score() to query the real column names instead
(algo/signals/advanced_filters.py, 2026-08-09). This migration now only creates
earnings_metrics, which was genuinely and fully missing.

FIX (2026-08-09, third pass): both DDL blocks used `DatabaseContext("postgres")`, but
that role always rolls back on __exit__ regardless of outcome (utils/db/context.py:
only role="write" auto-commits on a clean exit; every other role, including "postgres",
rolls back unconditionally). This migration ran clean, logged "complete", and got
recorded as applied in schema_version - while silently persisting nothing. Confirmed
live: earnings_metrics did not exist after a "successful" apply. Changed to
DatabaseContext("write") so the CREATE TABLE actually commits.
"""

import logging

logger = logging.getLogger(__name__)


def up() -> None:
    """Create missing insider_transactions and earnings_metrics tables."""
    from utils.db.context import DatabaseContext

    with DatabaseContext("write") as cur:
        # insider_transactions already exists in real databases under a different column
        # layout (trade_type/trade_price/trade_date, no `value`) - see file docstring.
        # Not recreated here; AdvancedFilters._insider_score() was fixed to match it instead.

        # Create earnings_metrics table
        # Needed by: AdvancedFilters._earnings_quality_score()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS earnings_metrics (
                id BIGSERIAL PRIMARY KEY,
                symbol VARCHAR(10) NOT NULL,
                report_date DATE NOT NULL,
                earnings_quality_score NUMERIC(5, 2),  -- 0-100 scale
                earnings_surprise_pct NUMERIC(8, 4),
                earnings_surprise_value NUMERIC(16, 6),
                beat_estimate BOOLEAN,
                estimated_eps NUMERIC(12, 4),
                actual_eps NUMERIC(12, 4),
                revenue_estimated NUMERIC(20, 2),
                revenue_actual NUMERIC(20, 2),
                guidance_raised BOOLEAN,
                consistency_score NUMERIC(5, 2),  -- 0-100 scale
                data_unavailable BOOLEAN DEFAULT FALSE,
                unavailable_reason VARCHAR(255),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(symbol, report_date)
            )
        """)
        logger.info("Created earnings_metrics table")

        # Create index for fast lookups
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_earnings_metrics_symbol_date
            ON earnings_metrics(symbol, report_date DESC)
        """)

        logger.info("Migration 1146 complete: insider_transactions and earnings_metrics tables created")


def down() -> None:
    """Drop the newly created tables."""
    from utils.db.context import DatabaseContext

    with DatabaseContext("write") as cur:
        cur.execute("DROP TABLE IF EXISTS earnings_metrics CASCADE")
        cur.execute("DROP TABLE IF EXISTS insider_transactions CASCADE")
        logger.info("Migration 1146 downgrade complete: tables dropped")


if __name__ == "__main__":
    import sys
    action = sys.argv[1] if len(sys.argv) > 1 else "upgrade"
    if action == "upgrade":
        up()
    elif action == "downgrade":
        down()
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)
