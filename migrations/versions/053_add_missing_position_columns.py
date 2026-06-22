#!/usr/bin/env python3
"""
Migration 053: Add missing target and risk columns to algo_positions.

ISSUE #3: Missing Position Target & Risk Columns

PROBLEM:
- algo_positions table is missing columns for stop/target levels and risk metrics
- The view algo_positions_with_risk joins with algo_trades to get these values
- Orphaned positions (no corresponding trade) have NULL for all risk metrics
- Frontend risk dashboard cannot display position ladders or target prices

SOLUTION:
- Add target_1_price, target_2_price, target_3_price columns to algo_positions
- Add target_1_r_multiple, target_2_r_multiple, target_3_r_multiple columns
- Add r_multiple and initial_risk_per_share computed columns
- Add stop_loss_price column and populate from existing trades
- Positions become self-contained (no external joins for risk data)
"""

from utils.db.context import DatabaseContext

DESCRIPTION = "Add missing target and risk columns to algo_positions table"


def up():
    """Add columns and populate from algo_trades data."""
    with DatabaseContext("write") as cur:
        # Step 1: Add target and stop loss columns to algo_positions
        cur.execute("""
            ALTER TABLE algo_positions
            ADD COLUMN IF NOT EXISTS stop_loss_price DECIMAL(12, 4),
            ADD COLUMN IF NOT EXISTS target_1_price DECIMAL(12, 4),
            ADD COLUMN IF NOT EXISTS target_2_price DECIMAL(12, 4),
            ADD COLUMN IF NOT EXISTS target_3_price DECIMAL(12, 4),
            ADD COLUMN IF NOT EXISTS target_1_r_multiple DECIMAL(8, 4),
            ADD COLUMN IF NOT EXISTS target_2_r_multiple DECIMAL(8, 4),
            ADD COLUMN IF NOT EXISTS target_3_r_multiple DECIMAL(8, 4),
            ADD COLUMN IF NOT EXISTS r_multiple DECIMAL(8, 4),
            ADD COLUMN IF NOT EXISTS initial_risk_per_share DECIMAL(12, 4)
        """)

        # Step 2: Create indexes on frequently accessed columns
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_algo_positions_stop_loss_price
            ON algo_positions(stop_loss_price)
            WHERE stop_loss_price IS NOT NULL
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_algo_positions_targets
            ON algo_positions(target_1_price, target_2_price, target_3_price)
            WHERE target_1_price IS NOT NULL OR target_2_price IS NOT NULL OR target_3_price IS NOT NULL
        """)

        # Step 3: Populate stop/target columns from algo_trades for positions that have matching trades
        cur.execute("""
            UPDATE algo_positions ap
            SET
              stop_loss_price = lt.stop_loss_price,
              target_1_price = lt.target_1_price,
              target_2_price = lt.target_2_price,
              target_3_price = lt.target_3_price,
              target_1_r_multiple = lt.target_1_r_multiple,
              target_2_r_multiple = lt.target_2_r_multiple,
              target_3_r_multiple = lt.target_3_r_multiple
            FROM (
              SELECT DISTINCT ON (symbol)
                symbol,
                stop_loss_price,
                target_1_price,
                target_2_price,
                target_3_price,
                target_1_r_multiple,
                target_2_r_multiple,
                target_3_r_multiple
              FROM algo_trades
              WHERE status IN ('open', 'filled', 'partially_filled', 'closed')
              ORDER BY symbol, trade_date DESC
            ) lt
            WHERE ap.symbol = lt.symbol
            AND (ap.stop_loss_price IS NULL OR ap.target_1_price IS NULL)
        """)

        # Step 4: Compute r_multiple and initial_risk_per_share for all positions
        cur.execute("""
            UPDATE algo_positions
            SET
              initial_risk_per_share = CASE
                WHEN stop_loss_price > 0 AND avg_entry_price > stop_loss_price
                THEN avg_entry_price - stop_loss_price
                ELSE NULL
              END,
              r_multiple = CASE
                WHEN stop_loss_price > 0
                  AND avg_entry_price > stop_loss_price
                  AND current_price IS NOT NULL
                  AND (avg_entry_price - stop_loss_price) > 0
                THEN ROUND((current_price - avg_entry_price)::NUMERIC / (avg_entry_price - stop_loss_price), 4)
                ELSE NULL
              END
            WHERE status IN ('open', 'filled', 'partially_filled')
        """)

        # Step 5: Drop and recreate the materialized view to use denormalized columns
        cur.execute("DROP MATERIALIZED VIEW IF EXISTS algo_positions_with_risk CASCADE")

        cur.execute("""
            CREATE MATERIALIZED VIEW algo_positions_with_risk AS
            WITH latest_prices AS (
              SELECT DISTINCT ON (symbol)
                symbol,
                close as current_price,
                date as price_date
              FROM price_daily
              ORDER BY symbol, date DESC
            ),
            latest_technical AS (
              SELECT DISTINCT ON (symbol)
                symbol,
                minervini_trend_score,
                weinstein_stage,
                percent_from_52w_low,
                percent_from_52w_high
              FROM trend_template_data
              ORDER BY symbol, date DESC
            ),
            latest_trades AS (
              SELECT DISTINCT ON (symbol)
                symbol,
                sector,
                industry,
                stage_phase
              FROM algo_trades
              ORDER BY symbol, trade_date DESC
            )
            SELECT
              ap.id,
              ap.position_id,
              ap.symbol,
              ap.quantity,
              ap.avg_entry_price,
              COALESCE(lp.current_price, ap.current_price) as current_price,
              ap.position_value,
              ap.unrealized_pnl,
              ap.unrealized_pnl_pct,
              ap.status,
              ap.stage_in_exit_plan,
              ap.days_since_entry,

              COALESCE(ap.stop_loss_price, 0)::DECIMAL(12, 4) as stop_loss_price,
              ap.target_1_price,
              ap.target_2_price,
              ap.target_3_price,
              ap.target_1_r_multiple,
              ap.target_2_r_multiple,
              ap.target_3_r_multiple,

              COALESCE(lt.sector, 'Unknown') as sector,
              COALESCE(lt.industry, 'Unknown') as industry,

              lt_tech.minervini_trend_score,
              lt_tech.weinstein_stage,
              lt_tech.percent_from_52w_low,
              lt_tech.percent_from_52w_high,

              ap.r_multiple,
              ap.initial_risk_per_share,

              CASE
                WHEN COALESCE(ap.stop_loss_price, 0) = 0
                THEN 0
                ELSE ((ap.avg_entry_price - COALESCE(ap.stop_loss_price, ap.avg_entry_price)) * ap.quantity)::DECIMAL(14, 2)
              END as open_risk_dollars,

              CASE
                WHEN COALESCE(lp.current_price, ap.current_price) = 0 OR COALESCE(ap.stop_loss_price, 0) = 0
                THEN NULL
                ELSE (COALESCE(lp.current_price, ap.current_price) - COALESCE(ap.stop_loss_price, ap.current_price)) / NULLIF(COALESCE(lp.current_price, ap.current_price), 0) * 100
              END::DECIMAL(8, 4) as distance_to_stop_pct,

              CASE
                WHEN COALESCE(lp.current_price, ap.current_price) = 0 OR ap.target_1_price IS NULL
                THEN NULL
                ELSE (ap.target_1_price - COALESCE(lp.current_price, ap.current_price)) / NULLIF(COALESCE(lp.current_price, ap.current_price), 0) * 100
              END::DECIMAL(8, 4) as distance_to_t1_pct,

              CASE
                WHEN COALESCE(lp.current_price, ap.current_price) = 0 OR ap.target_2_price IS NULL
                THEN NULL
                ELSE (ap.target_2_price - COALESCE(lp.current_price, ap.current_price)) / NULLIF(COALESCE(lp.current_price, ap.current_price), 0) * 100
              END::DECIMAL(8, 4) as distance_to_t2_pct,

              CASE
                WHEN COALESCE(lp.current_price, ap.current_price) = 0 OR ap.target_3_price IS NULL
                THEN NULL
                ELSE (ap.target_3_price - COALESCE(lp.current_price, ap.current_price)) / NULLIF(COALESCE(lp.current_price, ap.current_price), 0) * 100
              END::DECIMAL(8, 4) as distance_to_t3_pct

            FROM algo_positions ap
            LEFT JOIN latest_prices lp ON ap.symbol = lp.symbol
            LEFT JOIN latest_technical lt_tech ON ap.symbol = lt_tech.symbol
            LEFT JOIN latest_trades lt ON ap.symbol = lt.symbol
            WHERE ap.quantity > 0 AND ap.status NOT IN ('archived', 'deleted')
        """)

        # Step 6: Create index for materialized view
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_algo_positions_with_risk_symbol
            ON algo_positions_with_risk(symbol)
        """)


def down():
    """Remove columns and restore view."""
    with DatabaseContext("write") as cur:
        # Drop the modified view
        cur.execute("DROP MATERIALIZED VIEW IF EXISTS algo_positions_with_risk CASCADE")

        # Drop indexes
        cur.execute("DROP INDEX IF EXISTS idx_algo_positions_stop_loss_price")
        cur.execute("DROP INDEX IF EXISTS idx_algo_positions_targets")

        # Drop columns
        cur.execute("""
            ALTER TABLE algo_positions
            DROP COLUMN IF EXISTS stop_loss_price,
            DROP COLUMN IF EXISTS target_1_price,
            DROP COLUMN IF EXISTS target_2_price,
            DROP COLUMN IF EXISTS target_3_price,
            DROP COLUMN IF EXISTS target_1_r_multiple,
            DROP COLUMN IF EXISTS target_2_r_multiple,
            DROP COLUMN IF EXISTS target_3_r_multiple,
            DROP COLUMN IF EXISTS r_multiple,
            DROP COLUMN IF EXISTS initial_risk_per_share
        """)

        # Recreate the original view (reading from algo_trades)
        cur.execute("""
            CREATE MATERIALIZED VIEW algo_positions_with_risk AS
            WITH latest_prices AS (
              SELECT DISTINCT ON (symbol)
                symbol,
                close as current_price,
                date as price_date
              FROM price_daily
              ORDER BY symbol, date DESC
            ),
            latest_trades AS (
              SELECT DISTINCT ON (symbol)
                symbol,
                stop_loss_price,
                target_1_price,
                target_1_r_multiple,
                target_2_price,
                target_2_r_multiple,
                target_3_price,
                target_3_r_multiple,
                sector,
                industry,
                stage_phase,
                trade_date
              FROM algo_trades
              ORDER BY symbol, trade_date DESC
            ),
            latest_technical AS (
              SELECT DISTINCT ON (symbol)
                symbol,
                minervini_trend_score,
                weinstein_stage,
                percent_from_52w_low,
                percent_from_52w_high
              FROM trend_template_data
              ORDER BY symbol, date DESC
            )
            SELECT
              ap.id,
              ap.position_id,
              ap.symbol,
              ap.quantity,
              ap.avg_entry_price,
              COALESCE(lp.current_price, ap.current_price) as current_price,
              ap.position_value,
              ap.unrealized_pnl,
              ap.unrealized_pnl_pct,
              ap.status,
              ap.stage_in_exit_plan,
              ap.days_since_entry,

              COALESCE(lt.stop_loss_price, 0)::DECIMAL(12, 4) as stop_loss_price,
              lt.target_1_price,
              lt.target_2_price,
              lt.target_3_price,
              lt.target_1_r_multiple,
              lt.target_2_r_multiple,
              lt.target_3_r_multiple,

              COALESCE(lt.sector, 'Unknown') as sector,
              COALESCE(lt.industry, 'Unknown') as industry,

              lt_tech.minervini_trend_score,
              lt_tech.weinstein_stage,
              lt_tech.percent_from_52w_low,
              lt_tech.percent_from_52w_high,

              CASE
                WHEN COALESCE(lt.stop_loss_price, 0) = 0 OR ap.avg_entry_price = 0
                THEN NULL
                ELSE (ap.avg_entry_price - COALESCE(lt.stop_loss_price, ap.avg_entry_price)) / NULLIF(ap.avg_entry_price, 0)
              END::DECIMAL(8, 4) as r_multiple,

              CASE
                WHEN COALESCE(lt.stop_loss_price, 0) = 0
                THEN NULL
                ELSE (ap.avg_entry_price - COALESCE(lt.stop_loss_price, ap.avg_entry_price))::DECIMAL(12, 4)
              END as initial_risk_per_share,

              CASE
                WHEN COALESCE(lt.stop_loss_price, 0) = 0
                THEN 0
                ELSE ((ap.avg_entry_price - COALESCE(lt.stop_loss_price, ap.avg_entry_price)) * ap.quantity)::DECIMAL(14, 2)
              END as open_risk_dollars,

              CASE
                WHEN COALESCE(lp.current_price, ap.current_price) = 0 OR COALESCE(lt.stop_loss_price, 0) = 0
                THEN NULL
                ELSE (COALESCE(lp.current_price, ap.current_price) - COALESCE(lt.stop_loss_price, ap.current_price)) / NULLIF(COALESCE(lp.current_price, ap.current_price), 0) * 100
              END::DECIMAL(8, 4) as distance_to_stop_pct,

              CASE
                WHEN COALESCE(lp.current_price, ap.current_price) = 0 OR lt.target_1_price IS NULL
                THEN NULL
                ELSE (lt.target_1_price - COALESCE(lp.current_price, ap.current_price)) / NULLIF(COALESCE(lp.current_price, ap.current_price), 0) * 100
              END::DECIMAL(8, 4) as distance_to_t1_pct,

              CASE
                WHEN COALESCE(lp.current_price, ap.current_price) = 0 OR lt.target_2_price IS NULL
                THEN NULL
                ELSE (lt.target_2_price - COALESCE(lp.current_price, ap.current_price)) / NULLIF(COALESCE(lp.current_price, ap.current_price), 0) * 100
              END::DECIMAL(8, 4) as distance_to_t2_pct,

              CASE
                WHEN COALESCE(lp.current_price, ap.current_price) = 0 OR lt.target_3_price IS NULL
                THEN NULL
                ELSE (lt.target_3_price - COALESCE(lp.current_price, ap.current_price)) / NULLIF(COALESCE(lp.current_price, ap.current_price), 0) * 100
              END::DECIMAL(8, 4) as distance_to_t3_pct

            FROM algo_positions ap
            LEFT JOIN latest_prices lp ON ap.symbol = lp.symbol
            LEFT JOIN latest_trades lt ON ap.symbol = lt.symbol
            LEFT JOIN latest_technical lt_tech ON ap.symbol = lt_tech.symbol
            WHERE ap.quantity > 0 AND ap.status NOT IN ('archived', 'deleted')
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_algo_positions_with_risk_symbol
            ON algo_positions(symbol)
        """)
