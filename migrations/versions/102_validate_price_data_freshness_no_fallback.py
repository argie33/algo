#!/usr/bin/env python3
"""Migration 102: Validate price data freshness - reject stale fallback usage.

CRITICAL FIX: algo_positions_with_risk materialized view uses COALESCE fallback
to stale alpaca_positions.current_price when price_daily missing.

This migration adds:
1. Validation that latest_prices view doesn't have gaps for open positions
2. Error when P&L calculation would use stale price fallback
3. Explicit logging when price data freshness issues detected

Never silently use stale alpaca prices for P&L or risk calculations.
"""

import os
import psycopg2


def up():
    """Add validation to reject stale price fallbacks."""
    ssl_map = {
        "true": "require",
        "false": "disable",
        "disable": "disable",
        "prefer": "prefer",
        "require": "require",
    }
    db_ssl = ssl_map.get(os.getenv("DB_SSL", "require").lower(), "require")

    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
        dbname=os.getenv("DB_NAME", "postgres"),
        sslmode=db_ssl,
    )
    cur = conn.cursor()

    try:
        # Create function to validate price freshness for open positions
        cur.execute("""
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
        cur.execute("""
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

        # Add function to check price freshness before PnL
        cur.execute("""
        CREATE OR REPLACE FUNCTION check_price_freshness_before_pnl()
        RETURNS VOID AS $$
        DECLARE
          stale_count INT;
          error_msg VARCHAR;
        BEGIN
          SELECT COUNT(*) INTO stale_count
          FROM positions_using_stale_fallback
          WHERE price_freshness = 'STALE_PRICE_DATA'
             OR price_freshness = 'NO_PRICE_DATA';

          IF stale_count > 0 THEN
            error_msg := 'CRITICAL: ' || stale_count || ' open positions would use STALE alpaca prices for P&L. '
              || 'Price_daily loader missing/stale. Fix before calculating P&L or risk metrics.';
            RAISE EXCEPTION '%', error_msg;
          END IF;
        END;
        $$ LANGUAGE plpgsql;
        """)

        # Create alert function for monitoring
        cur.execute("""
        CREATE OR REPLACE FUNCTION alert_stale_position_prices()
        RETURNS TABLE (
          alert_type VARCHAR,
          symbol_count INT,
          oldest_price_date DATE,
          age_days INT,
          action_required VARCHAR
        ) AS $$
        SELECT
          'STALE_POSITION_PRICES'::VARCHAR,
          COUNT(DISTINCT symbol)::INT,
          MIN(latest_price_date),
          MAX(price_data_age_days),
          'HALT_PNL_CALCULATIONS'::VARCHAR
        FROM positions_using_stale_fallback
        WHERE price_freshness IN ('STALE_PRICE_DATA', 'NO_PRICE_DATA');
        $$ LANGUAGE SQL;
        """)

        conn.commit()
        print("[OK] Migration 102: Price freshness validation added")

    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"Migration 102 failed: {e}") from e

    finally:
        cur.close()
        conn.close()


def down():
    """Remove price freshness validation."""
    ssl_map = {
        "true": "require",
        "false": "disable",
        "disable": "disable",
        "prefer": "prefer",
        "require": "require",
    }
    db_ssl = ssl_map.get(os.getenv("DB_SSL", "require").lower(), "require")

    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
        dbname=os.getenv("DB_NAME", "postgres"),
        sslmode=db_ssl,
    )
    cur = conn.cursor()

    try:
        cur.execute("DROP VIEW IF EXISTS positions_using_stale_fallback CASCADE")
        cur.execute("DROP FUNCTION IF EXISTS validate_position_price_freshness()")
        cur.execute("DROP FUNCTION IF EXISTS check_price_freshness_before_pnl()")
        cur.execute("DROP FUNCTION IF EXISTS alert_stale_position_prices()")
        conn.commit()
        print("[OK] Migration 102 reversed")

    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"Downgrade for migration 102 failed: {e}") from e

    finally:
        cur.close()
        conn.close()
