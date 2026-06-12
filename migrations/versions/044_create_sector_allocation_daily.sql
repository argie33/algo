-- ════════════════════════════════════════════════════════════════════════════
-- MIGRATION: 044_create_sector_allocation_daily
-- ════════════════════════════════════════════════════════════════════════════
--
-- PURPOSE: Create pre-computed daily sector allocation table to eliminate O(n)
-- position iteration in panel_sector_compact() and enable historical sector tracking.
--
-- SCHEMA:
-- - date: Trading date (not null)
-- - sector_name: Sector name from finviz mapping (not null)
-- - symbol_count: Number of positions in sector
-- - total_position_value: Total $ value of positions in sector
-- - pct_portfolio: Percentage of total portfolio
-- - avg_unrealized_pnl_pct: Average win % in sector
-- - sector_day_return_pct: Sector contribution to daily return
--
-- PRIMARY KEY: (date, sector_name)
--
-- CONSUMED BY: Dashboard panel_sector_compact(), fetch_portfolio()
--
-- CREATED: 2026-06-12

CREATE TABLE IF NOT EXISTS sector_allocation_daily (
  date DATE NOT NULL,
  sector_name VARCHAR(50) NOT NULL,
  symbol_count INTEGER,
  total_position_value DECIMAL(15, 2),
  pct_portfolio DECIMAL(8, 4),
  avg_unrealized_pnl_pct DECIMAL(8, 4),
  sector_day_return_pct DECIMAL(8, 4),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (date, sector_name)
);

COMMENT ON TABLE sector_allocation_daily IS
'Pre-computed daily sector allocations. Eliminates O(n) position iteration in dashboard render. Updated by loaders after position refresh.';

COMMENT ON COLUMN sector_allocation_daily.date IS
'Trading date. Composite key with sector_name ensures one allocation per sector per day.';

COMMENT ON COLUMN sector_allocation_daily.sector_name IS
'Sector name (e.g., "Technology", "Financials"). From company_sector_mapping table.';

COMMENT ON COLUMN sector_allocation_daily.symbol_count IS
'Number of positions held in this sector on date.';

COMMENT ON COLUMN sector_allocation_daily.total_position_value IS
'Sum of all position values in this sector. Used for concentration analysis.';

COMMENT ON COLUMN sector_allocation_daily.pct_portfolio IS
'Sector value as % of total portfolio. Enables allocation breakdown.';

COMMENT ON COLUMN sector_allocation_daily.avg_unrealized_pnl_pct IS
'Average unrealized gain/loss % for positions in this sector. Win % indicator.';

COMMENT ON COLUMN sector_allocation_daily.sector_day_return_pct IS
'Sector contribution to daily portfolio return. Identifies best/worst performing sectors.';

CREATE INDEX IF NOT EXISTS idx_sector_allocation_date
  ON sector_allocation_daily(date DESC);

CREATE INDEX IF NOT EXISTS idx_sector_allocation_sector
  ON sector_allocation_daily(date DESC, sector_name);

-- Backfill from existing positions (optional)
-- WITH sector_summary AS (
--   SELECT
--     CURRENT_DATE as date,
--     csm.sector_name,
--     COUNT(DISTINCT ap.symbol) as symbol_count,
--     SUM(ap.position_value) as total_position_value,
--     SUM(ap.position_value) / (SELECT SUM(position_value) FROM algo_positions) * 100 as pct_portfolio,
--     AVG(ap.unrealized_pnl_pct) as avg_unrealized_pnl_pct
--   FROM algo_positions ap
--   LEFT JOIN company_sector_mapping csm ON ap.symbol = csm.symbol
--   WHERE ap.status = 'open'
--   GROUP BY csm.sector_name
-- )
-- INSERT INTO sector_allocation_daily (date, sector_name, symbol_count, total_position_value, pct_portfolio, avg_unrealized_pnl_pct)
-- SELECT date, sector_name, symbol_count, total_position_value, pct_portfolio, avg_unrealized_pnl_pct FROM sector_summary
-- ON CONFLICT (date, sector_name) DO UPDATE SET
--   symbol_count = EXCLUDED.symbol_count,
--   total_position_value = EXCLUDED.total_position_value,
--   pct_portfolio = EXCLUDED.pct_portfolio,
--   avg_unrealized_pnl_pct = EXCLUDED.avg_unrealized_pnl_pct;
