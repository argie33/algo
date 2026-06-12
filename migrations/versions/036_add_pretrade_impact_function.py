#!/usr/bin/env python3
"""Migration 036: Move pre-trade impact calculations from JavaScript to database.

Creates a function to calculate all pre-trade constraint impacts.
Eliminates multiple calculations in /pre-trade-impact endpoint.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.database_context import DatabaseContext

DESCRIPTION = "Add pre-trade impact calculation function"


def up():
    """Create the pre-trade impact calculation function."""
    with DatabaseContext('write') as cur:
        # Drop existing function if it exists
        cur.execute("""
            DROP FUNCTION IF EXISTS calculate_pretrade_impact(varchar, numeric, numeric, numeric) CASCADE
        """)

        # Create function to calculate pre-trade impact metrics
        cur.execute("""
            CREATE OR REPLACE FUNCTION calculate_pretrade_impact(
              p_symbol varchar,
              p_entry_price numeric,
              p_position_dollars numeric,
              p_position_pct numeric
            )
            RETURNS TABLE(
              position_size_dollars numeric,
              position_size_percent numeric,
              new_total_positions int,
              new_sector_percent numeric,
              new_sector_invested numeric,
              drawdown_impact_pct numeric,
              sector_name varchar,
              sector_count int,
              meets_position_limit boolean,
              meets_size_limit boolean,
              meets_sector_limit boolean,
              meets_cash_requirement boolean,
              meets_risk_limit boolean
            ) AS $pyfunc$
            DECLARE
              v_total_portfolio_value numeric;
              v_total_cash numeric;
              v_open_position_count int;
              v_stock_sector varchar;
              v_sector_invested numeric;
              v_sector_count int;
              v_position_size numeric;
              v_position_pct numeric;
              v_new_sector_total numeric;
              v_drawdown_impact numeric;
              v_max_positions constant int := 6;
              v_max_position_pct constant numeric := 15;
              v_max_sector_pct constant numeric := 30;
              v_max_drawdown_impact constant numeric := 0.05;
            BEGIN
              -- Get current portfolio state
              SELECT total_portfolio_value, total_cash
              INTO v_total_portfolio_value, v_total_cash
              FROM algo_portfolio_snapshots
              ORDER BY snapshot_date DESC LIMIT 1;

              IF v_total_portfolio_value IS NULL THEN
                RAISE EXCEPTION 'Portfolio snapshot not available';
              END IF;

              -- Get current open position count
              SELECT COUNT(*)
              INTO v_open_position_count
              FROM algo_positions
              WHERE status = 'open';

              -- Get stock sector and current sector exposure
              SELECT cp.sector
              INTO v_stock_sector
              FROM company_profile cp
              WHERE cp.ticker = UPPER(p_symbol);

              IF v_stock_sector IS NULL THEN
                RAISE EXCEPTION 'Stock % not found', p_symbol;
              END IF;

              -- Get current sector invested and count
              SELECT
                COALESCE(SUM(p.position_value), 0),
                COUNT(*)
              INTO v_sector_invested, v_sector_count
              FROM algo_positions p
              JOIN company_profile cp ON cp.ticker = p.symbol
              WHERE p.status = 'open' AND cp.sector = v_stock_sector;

              -- Calculate position size
              v_position_size := CASE
                WHEN p_position_dollars > 0 THEN p_position_dollars
                ELSE (v_total_portfolio_value * p_position_pct / 100)
              END;

              v_position_pct := (v_position_size / v_total_portfolio_value) * 100;

              -- Calculate new sector total
              v_new_sector_total := (v_sector_invested + v_position_size) / v_total_portfolio_value * 100;

              -- Calculate worst-case drawdown impact (15% adverse move on position)
              v_drawdown_impact := v_position_pct * 0.15 / 100;

              RETURN QUERY
              SELECT
                v_position_size,
                ROUND(v_position_pct, 2),
                v_open_position_count + 1,
                ROUND(v_new_sector_total, 2),
                ROUND(v_sector_invested + v_position_size, 2),
                ROUND(v_drawdown_impact, 4),
                v_stock_sector,
                v_sector_count,
                v_open_position_count < v_max_positions,
                v_position_pct <= v_max_position_pct,
                v_new_sector_total <= v_max_sector_pct,
                v_total_cash >= v_position_size,
                v_drawdown_impact <= v_max_drawdown_impact;
            END;
            $pyfunc$ LANGUAGE plpgsql STABLE
        """)

        # Create indexes for faster lookups
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_algo_positions_status_symbol
              ON algo_positions(status, symbol)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_company_profile_ticker_sector
              ON company_profile(ticker, sector)
        """)


def down():
    """Remove the pre-trade impact calculation function."""
    with DatabaseContext('write') as cur:
        cur.execute("""
            DROP FUNCTION IF EXISTS calculate_pretrade_impact(varchar, numeric, numeric, numeric) CASCADE
        """)
        cur.execute("""
            DROP INDEX IF EXISTS idx_algo_positions_status_symbol
        """)
        cur.execute("""
            DROP INDEX IF EXISTS idx_company_profile_ticker_sector
        """)
