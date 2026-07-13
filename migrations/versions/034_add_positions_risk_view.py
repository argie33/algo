#!/usr/bin/env python3
"""Migration 034: Move position-level risk calculations from API to database.

Creates a materialized view that pre-computes all risk metrics.
Allows API layer to be a pure display layer (not calculation engine).
"""

from utils.db.context import DatabaseContext

DESCRIPTION = "Add positions with risk materialized view"


def up():
    with DatabaseContext("write") as cur:
        # Drop existing view if it exists (for re-runs/updates)
        cur.execute("""
            DROP MATERIALIZED VIEW IF EXISTS algo_positions_with_risk CASCADE
        """)

        # Create materialized view with all risk calculations computed in SQL
        cur.execute("""
            CREATE MATERIALIZED VIEW algo_positions_with_risk AS
            WITH latest_trade AS (
              SELECT DISTINCT ON (symbol)
                symbol,
                stop_loss_price,
                target_1_price,
                target_2_price,
                target_3_price,
                target_1_r_multiple,
                target_2_r_multiple,
                target_3_r_multiple,
                signal_date
              FROM algo_trades
              WHERE status = 'open'
              ORDER BY symbol, trade_date DESC
            ),
            latest_trend AS (
              SELECT DISTINCT ON (symbol)
                symbol,
                weinstein_stage,
                minervini_trend_score,
                percent_from_52w_low,
                percent_from_52w_high
              FROM trend_template_data
              ORDER BY symbol, date DESC
            )
            SELECT
              p.position_id,
              p.id,
              p.symbol,
              p.quantity,
              p.avg_entry_price,
              p.current_price,
              p.position_value,
              p.unrealized_pnl,
              p.unrealized_pnl_pct,
              p.status,
              p.stage_in_exit_plan,
              p.days_since_entry,
              lt.stop_loss_price,
              lt.target_1_price,
              lt.target_2_price,
              lt.target_3_price,
              lt.target_1_r_multiple,
              lt.target_2_r_multiple,
              lt.target_3_r_multiple,
              cp.sector,
              cp.industry,
              ltt.weinstein_stage,
              ltt.minervini_trend_score,
              ltt.percent_from_52w_low,
              ltt.percent_from_52w_high,
              CASE
                WHEN p.avg_entry_price IS NOT NULL AND lt.stop_loss_price IS NOT NULL
                  AND p.avg_entry_price > lt.stop_loss_price
                THEN p.avg_entry_price - lt.stop_loss_price
                ELSE NULL
              END AS initial_risk_per_share,
              CASE
                WHEN p.avg_entry_price IS NOT NULL
                  AND lt.stop_loss_price IS NOT NULL
                  AND p.current_price IS NOT NULL
                  AND p.avg_entry_price > lt.stop_loss_price
                  AND (p.avg_entry_price - lt.stop_loss_price) > 0
                THEN ROUND((p.current_price - p.avg_entry_price)::NUMERIC /
                          (p.avg_entry_price - lt.stop_loss_price), 2)
                ELSE NULL
              END AS r_multiple,
              CASE
                WHEN p.current_price IS NOT NULL
                  AND lt.stop_loss_price IS NOT NULL
                  AND p.quantity IS NOT NULL
                THEN ROUND(
                  GREATEST(0, p.current_price - lt.stop_loss_price)::NUMERIC *
                  p.quantity, 2)
                ELSE NULL
              END AS open_risk_dollars,
              CASE
                WHEN p.current_price IS NOT NULL
                  AND lt.stop_loss_price IS NOT NULL
                  AND p.current_price > 0
                THEN ROUND(
                  ((p.current_price - lt.stop_loss_price)::NUMERIC / p.current_price) * 100, 2)
                ELSE NULL
              END AS distance_to_stop_pct,
              CASE
                WHEN p.current_price IS NOT NULL
                  AND lt.target_1_price IS NOT NULL
                  AND p.current_price > 0
                THEN ROUND(
                  ((lt.target_1_price - p.current_price)::NUMERIC / p.current_price) * 100, 2)
                ELSE NULL
              END AS distance_to_t1_pct,
              CASE
                WHEN p.current_price IS NOT NULL
                  AND lt.target_2_price IS NOT NULL
                  AND p.current_price > 0
                THEN ROUND(
                  ((lt.target_2_price - p.current_price)::NUMERIC / p.current_price) * 100, 2)
                ELSE NULL
              END AS distance_to_t2_pct,
              CASE
                WHEN p.current_price IS NOT NULL
                  AND lt.target_3_price IS NOT NULL
                  AND p.current_price > 0
                THEN ROUND(
                  ((lt.target_3_price - p.current_price)::NUMERIC / p.current_price) * 100, 2)
                ELSE NULL
              END AS distance_to_t3_pct
            FROM algo_positions p
            LEFT JOIN latest_trade lt ON lt.symbol = p.symbol
            LEFT JOIN company_profile cp ON cp.ticker = p.symbol
            LEFT JOIN latest_trend ltt ON ltt.symbol = p.symbol
            WHERE p.status = 'open'
            ORDER BY p.position_value DESC
        """)

        # Create indexes for materialized view - these are on the view data itself
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_algo_positions_with_risk_symbol
              ON algo_positions_with_risk(symbol)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_algo_positions_with_risk_position_id
              ON algo_positions_with_risk(position_id)
        """)


def down():
    """Drop the materialized view."""
    with DatabaseContext("write") as cur:
        cur.execute("""
            DROP MATERIALIZED VIEW IF EXISTS algo_positions_with_risk CASCADE
        """)
