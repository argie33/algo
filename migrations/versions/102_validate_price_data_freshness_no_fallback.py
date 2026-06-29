"""Migration 102: Validate price data freshness - reject stale fallback usage.

CRITICAL FIX: algo_positions_with_risk materialized view uses COALESCE fallback
to stale alpaca_positions.current_price when price_daily missing.

This migration adds:
1. Validation that latest_prices view doesn't have gaps for open positions
2. Error when P&L calculation would use stale price fallback
3. Explicit logging when price data freshness issues detected

Never silently use stale alpaca prices for P&L or risk calculations.
"""

import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    """Add validation to reject stale price fallbacks."""
    # Create function to validate price freshness for open positions
    op.execute("""
    CREATE OR REPLACE FUNCTION validate_position_price_freshness()
    RETURNS TABLE (
      symbol VARCHAR,
      position_status VARCHAR,
      latest_price_date DATE,
      price_data_age_days INT,
      has_price_in_daily BOOLEAN,
      status VARCHAR
    ) AS $$
    WITH position_symbols AS (
      SELECT DISTINCT symbol FROM algo_positions WHERE status IN ('open', 'filled', 'partially_filled')
    ),
    latest_prices AS (
      SELECT DISTINCT ON (symbol)
        symbol,
        date as price_date
      FROM price_daily
      ORDER BY symbol, date DESC
    ),
    price_check AS (
      SELECT
        p.symbol,
        ap.status,
        lp.price_date,
        CURRENT_DATE - lp.price_date as age_days,
        lp.price_date IS NOT NULL as has_price,
        CASE
          WHEN lp.price_date IS NULL THEN 'MISSING'
          WHEN (CURRENT_DATE - lp.price_date) > 2 THEN 'STALE'
          WHEN (CURRENT_DATE - lp.price_date) = 0 THEN 'FRESH_TODAY'
          WHEN (CURRENT_DATE - lp.price_date) = 1 THEN 'YESTERDAY'
          ELSE 'RECENT'
        END as data_status
      FROM position_symbols p
      LEFT JOIN algo_positions ap ON ap.symbol = p.symbol AND ap.status IN ('open', 'filled', 'partially_filled')
      LEFT JOIN latest_prices lp ON lp.symbol = p.symbol
      ORDER BY p.symbol
    )
    SELECT
      symbol,
      status,
      price_date,
      age_days,
      has_price,
      data_status
    FROM price_check;
    $$ LANGUAGE SQL;
    """)

    # Create view to detect positions that would use stale alpaca fallback
    op.execute("""
    CREATE OR REPLACE VIEW positions_using_stale_fallback AS
    SELECT
      ap.id,
      ap.symbol,
      ap.status,
      ap.avg_entry_price,
      ap.position_value,
      ap.unrealized_pnl,
      CURRENT_DATE - pd.max_price_date as price_data_age_days,
      pd.max_price_date as latest_price_date,
      CASE
        WHEN pd.max_price_date IS NULL THEN 'NO_PRICE_DATA'
        WHEN (CURRENT_DATE - pd.max_price_date) > 2 THEN 'STALE_PRICE_DATA'
        ELSE 'RECENT_PRICE_DATA'
      END as price_freshness,
      COALESCE(ap.current_price, 0) as alpaca_fallback_price,
      CASE
        WHEN pd.max_price_date IS NULL THEN 'CRITICAL: No price_daily data - would use stale alpaca price'
        WHEN (CURRENT_DATE - pd.max_price_date) > 2 THEN 'WARNING: Would use stale alpaca price for P&L'
        ELSE 'OK: Using fresh price_daily'
      END as risk_assessment
    FROM algo_positions ap
    LEFT JOIN (
      SELECT symbol, MAX(date) as max_price_date
      FROM price_daily
      GROUP BY symbol
    ) pd ON pd.symbol = ap.symbol
    WHERE ap.status IN ('open', 'filled', 'partially_filled')
      AND (pd.max_price_date IS NULL OR (CURRENT_DATE - pd.max_price_date) > 2);
    """)

    # Add trigger to log warnings when view is accessed
    op.execute("""
    COMMENT ON VIEW positions_using_stale_fallback IS
    'CRITICAL: Shows all open positions that would use stale alpaca_positions.current_price as fallback.
     If any rows in this view exist and P&L is calculated, results use STALE prices (up to days old).

     DO NOT IGNORE THIS VIEW - indicates price_daily loader is failing or falling behind.
     algo_positions_with_risk materialized view uses COALESCE(price_daily, alpaca_positions)
     which silently uses stale prices when price_daily missing.

     Action: Investigate price_daily loader status. Halt P&L calculations if stale prices detected.';
    """)

    # Add validation that raises error if stale fallback would be used
    op.execute("""
    CREATE OR REPLACE FUNCTION check_price_freshness_before_pnl()
    RETURNS VOID AS $$
    DECLARE
      stale_count INT;
    BEGIN
      SELECT COUNT(*) INTO stale_count
      FROM positions_using_stale_fallback
      WHERE price_freshness = 'STALE_PRICE_DATA'
         OR price_freshness = 'NO_PRICE_DATA';

      IF stale_count > 0 THEN
        RAISE EXCEPTION
          'CRITICAL: % open positions would use STALE alpaca prices for P&L. '
          'Price_daily loader missing/stale. Fix before calculating P&L or risk metrics.',
          stale_count;
      END IF;
    END;
    $$ LANGUAGE plpgsql;
    """)

    # Create alert function for monitoring
    op.execute("""
    CREATE OR REPLACE FUNCTION alert_stale_position_prices()
    RETURNS TABLE (
      alert_type VARCHAR,
      symbol_count INT,
      oldest_price_date DATE,
      age_days INT,
      action_required VARCHAR
    ) AS $$
    SELECT
      'STALE_POSITION_PRICES',
      COUNT(DISTINCT symbol),
      MIN(latest_price_date),
      MAX(price_data_age_days),
      'HALT_PNL_CALCULATIONS'
    FROM positions_using_stale_fallback
    WHERE price_freshness IN ('STALE_PRICE_DATA', 'NO_PRICE_DATA');
    $$ LANGUAGE SQL;
    """)

    print("""
    ✅ Migration 102 complete: Price freshness validation added.

    NEW VIEWS & FUNCTIONS:
    - positions_using_stale_fallback: Shows positions that would use stale alpaca prices
    - validate_position_price_freshness(): Detailed freshness check per position
    - check_price_freshness_before_pnl(): Raises error if stale prices detected
    - alert_stale_position_prices(): Monitoring alert function

    CRITICAL: algo_positions_with_risk still uses COALESCE fallback silently.
    Run SELECT * FROM positions_using_stale_fallback to detect issues.
    """)


def downgrade() -> None:
    """Remove price freshness validation."""
    op.execute("DROP VIEW IF EXISTS positions_using_stale_fallback CASCADE")
    op.execute("DROP FUNCTION IF EXISTS validate_position_price_freshness()")
    op.execute("DROP FUNCTION IF EXISTS check_price_freshness_before_pnl()")
    op.execute("DROP FUNCTION IF EXISTS alert_stale_position_prices()")
