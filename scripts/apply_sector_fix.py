#!/usr/bin/env python3
"""Apply sector enrichment fix to database."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

from utils.db.context import DatabaseContext

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

migration_sql = """
-- Migration 083: Fix sector enrichment in algo_positions_with_risk view

DROP MATERIALIZED VIEW IF EXISTS algo_positions_with_risk CASCADE;

CREATE MATERIALIZED VIEW algo_positions_with_risk AS
WITH latest_prices AS (
  SELECT DISTINCT ON (symbol)
    symbol,
    close AS current_price,
    date AS price_date
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
),
latest_swing AS (
  SELECT DISTINCT ON (symbol)
    symbol,
    score AS swing_score
  FROM swing_trader_scores
  ORDER BY symbol, date DESC
)
SELECT
  ap.id,
  ap.position_id,
  ap.symbol,
  ap.quantity,
  ap.avg_entry_price,
  lp.current_price,
  ap.position_value,
  ap.unrealized_pnl,
  ap.unrealized_pnl_pct,
  ap.status,
  ap.stage_in_exit_plan,
  ap.days_since_entry,

  COALESCE(ap.stop_loss_price, ap.current_stop_price) AS stop_loss_price,

  lt.target_1_price,
  lt.target_2_price,
  lt.target_3_price,
  lt.target_1_r_multiple,
  lt.target_2_r_multiple,
  lt.target_3_r_multiple,

  COALESCE(lt.sector, cp.sector, 'Unknown'::VARCHAR) AS sector,
  COALESCE(lt.industry, cp.industry, 'Unknown'::VARCHAR) AS industry,

  lt_tech.minervini_trend_score,
  lt_tech.weinstein_stage,
  lt_tech.percent_from_52w_low,
  lt_tech.percent_from_52w_high,

  ls.swing_score,

  CASE
    WHEN lp.current_price IS NULL OR ap.stop_loss_price IS NULL AND ap.current_stop_price IS NULL OR ap.avg_entry_price = 0
    THEN NULL
    WHEN ap.avg_entry_price - COALESCE(ap.stop_loss_price, ap.current_stop_price) <= 0
    THEN NULL
    ELSE (lp.current_price - ap.avg_entry_price) /
         NULLIF(ap.avg_entry_price - COALESCE(ap.stop_loss_price, ap.current_stop_price), 0)
  END::DECIMAL(8, 4) AS r_multiple,

  CASE
    WHEN ap.stop_loss_price IS NULL AND ap.current_stop_price IS NULL
    THEN NULL
    ELSE (ap.avg_entry_price - COALESCE(ap.stop_loss_price, ap.current_stop_price, ap.avg_entry_price))::DECIMAL(12, 4)
  END AS initial_risk_per_share,

  CASE
    WHEN ap.stop_loss_price IS NULL AND ap.current_stop_price IS NULL
    THEN NULL
    ELSE ((ap.avg_entry_price - COALESCE(ap.stop_loss_price, ap.current_stop_price, ap.avg_entry_price)) * ap.quantity)::DECIMAL(14, 2)
  END AS open_risk_dollars,

  CASE
    WHEN lp.current_price IS NULL OR lp.current_price = 0 OR COALESCE(ap.stop_loss_price, ap.current_stop_price) IS NULL
    THEN NULL
    ELSE (lp.current_price - COALESCE(ap.stop_loss_price, ap.current_stop_price)) / NULLIF(lp.current_price, 0) * 100
  END::DECIMAL(8, 4) AS distance_to_stop_pct,

  CASE
    WHEN lp.current_price IS NULL OR lp.current_price = 0 OR lt.target_1_price IS NULL
    THEN NULL
    ELSE (lt.target_1_price - lp.current_price) / NULLIF(lp.current_price, 0) * 100
  END::DECIMAL(8, 4) AS distance_to_t1_pct,

  CASE
    WHEN lp.current_price IS NULL OR lp.current_price = 0 OR lt.target_2_price IS NULL
    THEN NULL
    ELSE (lt.target_2_price - lp.current_price) / NULLIF(lp.current_price, 0) * 100
  END::DECIMAL(8, 4) AS distance_to_t2_pct,

  CASE
    WHEN lp.current_price IS NULL OR lp.current_price = 0 OR lt.target_3_price IS NULL
    THEN NULL
    ELSE (lt.target_3_price - lp.current_price) / NULLIF(lp.current_price, 0) * 100
  END::DECIMAL(8, 4) AS distance_to_t3_pct

FROM algo_positions ap
INNER JOIN latest_prices lp ON ap.symbol = lp.symbol
LEFT JOIN latest_trades lt ON ap.symbol = lt.symbol
LEFT JOIN latest_technical lt_tech ON ap.symbol = lt_tech.symbol
LEFT JOIN company_profile cp ON ap.symbol = cp.ticker
LEFT JOIN latest_swing ls ON ap.symbol = ls.symbol
WHERE ap.quantity > 0 AND ap.status NOT IN ('archived', 'deleted');

-- Create unique index first (required for REFRESH CONCURRENT)
CREATE UNIQUE INDEX IF NOT EXISTS idx_algo_positions_with_risk_symbol
ON algo_positions_with_risk(symbol);

CREATE INDEX IF NOT EXISTS idx_algo_positions_with_risk_status
ON algo_positions_with_risk(status);

-- Refresh the materialized view (simple refresh since it's new)
REFRESH MATERIALIZED VIEW algo_positions_with_risk;
"""

try:
    with DatabaseContext() as db:
        cur = db.connection.cursor()
        logger.info("Applying sector enrichment fix...")
        cur.execute(migration_sql)
        db.connection.commit()
        logger.info("SUCCESS: View recreated with sector enrichment")

        # Verify the fix
        cur.execute("""
            SELECT symbol, sector FROM algo_positions_with_risk
            WHERE status = 'open'
            LIMIT 5
        """)
        print("\nVerification - Sample positions after fix:")
        for row in cur.fetchall():
            print(f"  {row[0]:6} -> sector: {row[1]}")

except Exception as e:
    logger.error(f"FAILED: {e}")
    sys.exit(1)
