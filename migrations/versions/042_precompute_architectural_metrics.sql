-- ════════════════════════════════════════════════════════════════════════════
-- MIGRATION: 041_precompute_architectural_metrics
-- ════════════════════════════════════════════════════════════════════════════
--
-- PURPOSE: Add pre-computed columns and tables to move calculation burden
-- from API layer to database layer, addressing architectural issues #1-5.
--
-- FIXES:
-- - Issue #1: Pre-compute drawdown_pct in algo_portfolio_snapshots
-- - Issue #2: Create daily_return_histogram table for pre-computed histogram
-- - Issue #3: Create trade_distribution_histogram table for pre-computed bins
-- - Issue #4: Create holding_period_histogram table for pre-computed distribution
-- - Issue #5: Add stage_label column to algo_positions for deduplication
--
-- CREATED: 2026-06-11

-- ════════════════════════════════════════════════════════════════════════════
-- ISSUE #1: Add drawdown pre-computation to algo_portfolio_snapshots
-- ════════════════════════════════════════════════════════════════════════════

ALTER TABLE algo_portfolio_snapshots
ADD COLUMN IF NOT EXISTS drawdown_pct DECIMAL(8, 4),
ADD COLUMN IF NOT EXISTS running_peak DECIMAL(14, 2);

COMMENT ON COLUMN algo_portfolio_snapshots.drawdown_pct IS
'Pre-computed drawdown percentage: ((running_peak - current_value) / running_peak) * 100. Eliminates O(n) calculation in API.';

COMMENT ON COLUMN algo_portfolio_snapshots.running_peak IS
'Running peak portfolio value to date. Used to compute drawdown_pct.';

-- Compute initial drawdown values for historical data
WITH chronological AS (
  SELECT
    id,
    snapshot_date,
    total_portfolio_value,
    ROW_NUMBER() OVER (ORDER BY snapshot_date) as rn
  FROM algo_portfolio_snapshots
  WHERE total_portfolio_value > 0
    AND drawdown_pct IS NULL
  ORDER BY snapshot_date
),
with_peak AS (
  SELECT
    id,
    snapshot_date,
    total_portfolio_value,
    MAX(total_portfolio_value) OVER (
      ORDER BY snapshot_date
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) as peak,
    rn
  FROM chronological
)
UPDATE algo_portfolio_snapshots
SET
  running_peak = wp.peak,
  drawdown_pct = CASE
    WHEN wp.peak > 0 THEN -((wp.peak - wp.total_portfolio_value) / wp.peak * 100)::DECIMAL(8, 4)
    ELSE 0
  END
FROM with_peak wp
WHERE algo_portfolio_snapshots.id = wp.id;

-- ════════════════════════════════════════════════════════════════════════════
-- ISSUE #2: Create daily_return_histogram table
-- ════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS algo_daily_return_histogram (
  id SERIAL PRIMARY KEY,
  snapshot_date DATE NOT NULL UNIQUE,
  num_buckets INTEGER NOT NULL DEFAULT 12,
  lo DECIMAL(8, 4),           -- Min return in sample
  hi DECIMAL(8, 4),           -- Max return in sample
  span DECIMAL(8, 4),         -- hi - lo
  buckets JSONB NOT NULL,     -- [{bucket: 0, mid: -2.5, min: -3, max: -2, count: 5}, ...]
  stats JSONB NOT NULL,       -- {n: 180, mean: 0.42, std: 1.23, min: -5.2, max: 4.8}
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_daily_return_histogram_date
ON algo_daily_return_histogram(snapshot_date DESC);

COMMENT ON TABLE algo_daily_return_histogram IS
'Pre-computed daily return histogram. Calculated from last 90 daily returns in algo_portfolio_snapshots. Eliminates O(n) binning and statistics calculation in API.';

-- ════════════════════════════════════════════════════════════════════════════
-- ISSUE #3: Create trade_distribution_histogram table
-- ════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS algo_trade_r_distribution (
  id SERIAL PRIMARY KEY,
  snapshot_date DATE NOT NULL UNIQUE,
  buckets JSONB NOT NULL,     -- [{range: '< -2R', min: -Infinity, max: -2, count: 3}, ...]
  total_trades INTEGER NOT NULL,
  win_count INTEGER NOT NULL,
  loss_count INTEGER NOT NULL,
  avg_winner_r DECIMAL(8, 4),
  avg_loser_r DECIMAL(8, 4),
  expectancy_r DECIMAL(8, 4),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_trade_r_distribution_date
ON algo_trade_r_distribution(snapshot_date DESC);

COMMENT ON TABLE algo_trade_r_distribution IS
'Pre-computed trade R-multiple distribution. Calculated from last 500 closed trades. Fixed bin structure: <-2R, -2 to -1R, -1 to 0R, 0 to 1R, 1 to 2R, 2 to 3R, >3R. Eliminates O(n) binning in API.';

-- ════════════════════════════════════════════════════════════════════════════
-- ISSUE #4: Create holding_period_histogram table
-- ════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS algo_holding_period_histogram (
  id SERIAL PRIMARY KEY,
  snapshot_date DATE NOT NULL UNIQUE,
  buckets JSONB NOT NULL,     -- [{range: '0-3d', min: 0, max: 4, count: 12}, ...]
  total_trades INTEGER NOT NULL,
  median_days DECIMAL(5, 2),
  avg_days DECIMAL(5, 2),
  min_days INTEGER,
  max_days INTEGER,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_holding_period_histogram_date
ON algo_holding_period_histogram(snapshot_date DESC);

COMMENT ON TABLE algo_holding_period_histogram IS
'Pre-computed holding period distribution. Calculated from last 500 closed trades. Fixed bin structure: 0-3d, 4-7d, 8-14d, 15-30d, 31-60d, 60d+. Eliminates O(n) binning in API.';

-- ════════════════════════════════════════════════════════════════════════════
-- ISSUE #5: Add stage_label column to algo_positions
-- ════════════════════════════════════════════════════════════════════════════

ALTER TABLE algo_positions
ADD COLUMN IF NOT EXISTS stage_label VARCHAR(50);

COMMENT ON COLUMN algo_positions.stage_label IS
'Pre-computed stage label based on Weinstein stage + Minervini trend score and config thresholds. Eliminates duplicated logic in API. Values: Stage 1 (base), Early Stage-2, Mid Stage-2, Late Stage-2, Stage 3 (top), Stage 4 (down), Unknown.';

-- ════════════════════════════════════════════════════════════════════════════
-- ORCHESTRATOR INTEGRATION NOTES
-- ════════════════════════════════════════════════════════════════════════════
--
-- The orchestrator must call these stored procedures at the end of Phase 1
-- (Evaluation phase) after all position and trade data is updated:
--
--   SELECT compute_daily_return_histogram(CURRENT_DATE);
--   SELECT compute_trade_r_distribution(CURRENT_DATE);
--   SELECT compute_holding_period_histogram(CURRENT_DATE);
--
-- This ensures histograms reflect the current state before dashboard queries read them.
--
-- ════════════════════════════════════════════════════════════════════════════
-- Create stored procedure to compute all histograms
-- ════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION compute_daily_return_histogram(target_date DATE DEFAULT CURRENT_DATE)
RETURNS VOID AS $$
DECLARE
  v_lo DECIMAL(8, 4);
  v_hi DECIMAL(8, 4);
  v_span DECIMAL(8, 4);
  v_step DECIMAL(8, 4);
  v_buckets JSONB;
  v_stats JSONB;
  v_count INTEGER;
  v_mean DECIMAL(8, 4);
  v_variance DECIMAL(8, 4);
  v_std DECIMAL(8, 4);
BEGIN
  -- Get last 90 daily returns
  WITH returns_data AS (
    SELECT daily_return_pct
    FROM algo_portfolio_snapshots
    WHERE daily_return_pct IS NOT NULL
    ORDER BY snapshot_date DESC
    LIMIT 90
  ),
  returns_stats AS (
    SELECT
      MIN(daily_return_pct) as lo,
      MAX(daily_return_pct) as hi,
      COUNT(*) as cnt
    FROM returns_data
  ),
  binned AS (
    SELECT
      rs.lo, rs.hi,
      GREATEST(0.5, rs.hi - rs.lo) as span,
      rs.cnt,
      rd.daily_return_pct,
      CASE
        WHEN rs.span > 0 THEN FLOOR(((rd.daily_return_pct - rs.lo) / GREATEST(0.5, rs.hi - rs.lo)) * 12)
        ELSE 0
      END as bucket_idx
    FROM returns_data rd, returns_stats rs
  ),
  buckets_agg AS (
    SELECT
      json_agg(
        json_build_object(
          'bucket', i,
          'mid', ROUND((lo + span * (i + 0.5) / 12)::NUMERIC, 2),
          'min', ROUND((lo + span * i / 12)::NUMERIC, 2),
          'max', ROUND((lo + span * (i + 1) / 12)::NUMERIC, 2),
          'count', bucket_counts.count
        )
        ORDER BY i
      ) as buckets,
      lo, hi, span, cnt
    FROM (SELECT 0 AS i UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4
          UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9
          UNION SELECT 10 UNION SELECT 11) as bucket_nums
    CROSS JOIN (
      SELECT DISTINCT lo, hi, span, cnt FROM binned LIMIT 1
    ) bs
    LEFT JOIN (
      SELECT bucket_idx, COUNT(*) as count FROM binned GROUP BY bucket_idx
    ) bucket_counts ON bucket_nums.i = bucket_counts.bucket_idx
    GROUP BY bs.lo, bs.hi, bs.span, bs.cnt
  )
  INSERT INTO algo_daily_return_histogram (snapshot_date, buckets, stats)
  SELECT
    target_date,
    ba.buckets,
    json_build_object(
      'n', ba.cnt,
      'mean', ROUND(AVG(rd.daily_return_pct)::NUMERIC, 2),
      'std', ROUND(STDDEV_SAMP(rd.daily_return_pct)::NUMERIC, 2)
    )
  FROM buckets_agg ba
  CROSS JOIN (
    SELECT daily_return_pct FROM algo_portfolio_snapshots
    WHERE daily_return_pct IS NOT NULL
    ORDER BY snapshot_date DESC LIMIT 90
  ) rd
  GROUP BY ba.buckets, ba.cnt
  ON CONFLICT (snapshot_date) DO UPDATE
  SET
    buckets = EXCLUDED.buckets,
    stats = EXCLUDED.stats,
    updated_at = CURRENT_TIMESTAMP;
END;
$$ LANGUAGE plpgsql;

-- ════════════════════════════════════════════════════════════════════════════
-- Create stored procedure to compute trade R distribution
-- ════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION compute_trade_r_distribution(target_date DATE DEFAULT CURRENT_DATE)
RETURNS VOID AS $$
DECLARE
  v_buckets JSONB;
  v_total INTEGER;
  v_wins INTEGER;
  v_losses INTEGER;
BEGIN
  WITH recent_trades AS (
    SELECT exit_r_multiple
    FROM algo_closed_trades
    WHERE exit_r_multiple IS NOT NULL
    ORDER BY close_date DESC
    LIMIT 500
  ),
  binned AS (
    SELECT
      CASE
        WHEN exit_r_multiple < -2 THEN 0
        WHEN exit_r_multiple < -1 THEN 1
        WHEN exit_r_multiple < 0 THEN 2
        WHEN exit_r_multiple < 1 THEN 3
        WHEN exit_r_multiple < 2 THEN 4
        WHEN exit_r_multiple < 3 THEN 5
        ELSE 6
      END as bin_idx,
      exit_r_multiple,
      CASE WHEN exit_r_multiple > 0 THEN 1 ELSE 0 END as is_win,
      CASE WHEN exit_r_multiple < 0 THEN 1 ELSE 0 END as is_loss
    FROM recent_trades
  ),
  stats AS (
    SELECT
      COUNT(*) as total,
      SUM(is_win) as wins,
      SUM(is_loss) as losses,
      AVG(CASE WHEN is_win = 1 THEN exit_r_multiple END) as avg_winner,
      AVG(CASE WHEN is_loss = 1 THEN exit_r_multiple END) as avg_loser,
      (SUM(CASE WHEN is_win = 1 THEN exit_r_multiple ELSE 0 END) +
       SUM(CASE WHEN is_loss = 1 THEN exit_r_multiple ELSE 0 END)) / NULLIF(COUNT(*), 0) as expectancy
    FROM binned
  )
  INSERT INTO algo_trade_r_distribution (
    snapshot_date, buckets, total_trades, win_count, loss_count,
    avg_winner_r, avg_loser_r, expectancy_r
  )
  SELECT
    target_date,
    json_agg(
      json_build_object(
        'range', range_label,
        'min', min_val,
        'max', max_val,
        'count', COALESCE(bin_counts.count, 0)
      )
      ORDER BY bin_idx
    ),
    s.total,
    COALESCE(s.wins, 0),
    COALESCE(s.losses, 0),
    ROUND(s.avg_winner::NUMERIC, 4),
    ROUND(s.avg_loser::NUMERIC, 4),
    ROUND(s.expectancy::NUMERIC, 4)
  FROM (
    VALUES
      (0, '< -2R', -9999::DECIMAL, -2),
      (1, '-2 to -1R', -2, -1),
      (2, '-1 to 0R', -1, 0),
      (3, '0 to 1R', 0, 1),
      (4, '1 to 2R', 1, 2),
      (5, '2 to 3R', 2, 3),
      (6, '> 3R', 3, 9999)
  ) AS bins(bin_idx, range_label, min_val, max_val)
  LEFT JOIN (
    SELECT bin_idx, COUNT(*) as count FROM binned GROUP BY bin_idx
  ) bin_counts ON bins.bin_idx = bin_counts.bin_idx
  CROSS JOIN stats s
  GROUP BY s.total, s.wins, s.losses, s.avg_winner, s.avg_loser, s.expectancy
  ON CONFLICT (snapshot_date) DO UPDATE
  SET
    buckets = EXCLUDED.buckets,
    total_trades = EXCLUDED.total_trades,
    win_count = EXCLUDED.win_count,
    loss_count = EXCLUDED.loss_count,
    avg_winner_r = EXCLUDED.avg_winner_r,
    avg_loser_r = EXCLUDED.avg_loser_r,
    expectancy_r = EXCLUDED.expectancy_r,
    updated_at = CURRENT_TIMESTAMP;
END;
$$ LANGUAGE plpgsql;

-- ════════════════════════════════════════════════════════════════════════════
-- Create stored procedure to compute holding period distribution
-- ════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION compute_holding_period_histogram(target_date DATE DEFAULT CURRENT_DATE)
RETURNS VOID AS $$
BEGIN
  WITH recent_trades AS (
    SELECT trade_duration_days
    FROM algo_closed_trades
    WHERE trade_duration_days IS NOT NULL
    ORDER BY close_date DESC
    LIMIT 500
  ),
  binned AS (
    SELECT
      CASE
        WHEN trade_duration_days < 4 THEN 0
        WHEN trade_duration_days < 8 THEN 1
        WHEN trade_duration_days < 15 THEN 2
        WHEN trade_duration_days < 31 THEN 3
        WHEN trade_duration_days < 61 THEN 4
        ELSE 5
      END as bin_idx,
      trade_duration_days
    FROM recent_trades
  ),
  stats AS (
    SELECT
      COUNT(*) as total,
      PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY trade_duration_days) as median,
      AVG(trade_duration_days) as average,
      MIN(trade_duration_days) as min_val,
      MAX(trade_duration_days) as max_val
    FROM recent_trades
  )
  INSERT INTO algo_holding_period_histogram (
    snapshot_date, buckets, total_trades, median_days, avg_days, min_days, max_days
  )
  SELECT
    target_date,
    json_agg(
      json_build_object(
        'range', range_label,
        'min', min_val,
        'max', max_val,
        'count', COALESCE(bin_counts.count, 0)
      )
      ORDER BY bin_idx
    ),
    s.total,
    ROUND(s.median::NUMERIC, 2),
    ROUND(s.average::NUMERIC, 2),
    s.min_val,
    s.max_val
  FROM (
    VALUES
      (0, '0-3d', 0, 4),
      (1, '4-7d', 4, 8),
      (2, '8-14d', 8, 15),
      (3, '15-30d', 15, 31),
      (4, '31-60d', 31, 61),
      (5, '60d+', 61, 9999)
  ) AS bins(bin_idx, range_label, min_val, max_val)
  LEFT JOIN (
    SELECT bin_idx, COUNT(*) as count FROM binned GROUP BY bin_idx
  ) bin_counts ON bins.bin_idx = bin_counts.bin_idx
  CROSS JOIN stats s
  GROUP BY s.total, s.median, s.average, s.min_val, s.max_val
  ON CONFLICT (snapshot_date) DO UPDATE
  SET
    buckets = EXCLUDED.buckets,
    total_trades = EXCLUDED.total_trades,
    median_days = EXCLUDED.median_days,
    avg_days = EXCLUDED.avg_days,
    min_days = EXCLUDED.min_days,
    max_days = EXCLUDED.max_days,
    updated_at = CURRENT_TIMESTAMP;
END;
$$ LANGUAGE plpgsql;
