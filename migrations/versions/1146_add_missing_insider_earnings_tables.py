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
"""

import logging

logger = logging.getLogger(__name__)


def upgrade() -> None:
    """Create missing insider_transactions and earnings_metrics tables."""
    from utils.db.context import DatabaseContext

    with DatabaseContext("postgres") as cur:
        # Create insider_transactions table
        # Needed by: AdvancedFilters._insider_score()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS insider_transactions (
                id BIGSERIAL PRIMARY KEY,
                symbol VARCHAR(10) NOT NULL,
                insider_name VARCHAR(255),
                transaction_date DATE NOT NULL,
                transaction_type VARCHAR(50),  -- 'buy', 'sale', etc.
                shares BIGINT,
                price NUMERIC(16, 2),
                value NUMERIC(20, 2),  -- shares * price
                filing_date DATE,
                sec_filing_url TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(symbol, insider_name, transaction_date, transaction_type, value)
            )
        """)
        logger.info("Created insider_transactions table")

        # Create index for fast lookups by date range
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_insider_transactions_symbol_date
            ON insider_transactions(symbol, transaction_date DESC)
        """)

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


def downgrade() -> None:
    """Drop the newly created tables."""
    from utils.db.context import DatabaseContext

    with DatabaseContext("postgres") as cur:
        cur.execute("DROP TABLE IF EXISTS earnings_metrics CASCADE")
        cur.execute("DROP TABLE IF EXISTS insider_transactions CASCADE")
        logger.info("Migration 1146 downgrade complete: tables dropped")


if __name__ == "__main__":
    import sys
    action = sys.argv[1] if len(sys.argv) > 1 else "upgrade"
    if action == "upgrade":
        upgrade()
    elif action == "downgrade":
        downgrade()
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)
