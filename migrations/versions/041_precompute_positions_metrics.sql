-- ════════════════════════════════════════════════════════════════════════════
-- MIGRATION 041: Pre-compute position metrics to optimize /api/algo/positions
-- ════════════════════════════════════════════════════════════════════════════
--
-- ISSUES ADDRESSED:
-- #6: Sector Allocation Grouping — Pre-compute sector concentration
-- #7: Risk Allocation Ranking — Pre-compute risk_pct and risk_rank
-- #8: R-Ladder Percentage Scaling — Pre-compute ladder percentages
--
-- STRATEGY:
-- 1. Add computed columns to algo_positions table for risk metrics and ladder percentages
-- 2. Create sector_allocation_summary table for daily sector grouping
-- 3. Update view to expose pre-computed fields
-- 4. API returns pre-computed values instead of computing on every request

-- Step 1: Add pre-computed columns to algo_positions table
ALTER TABLE algo_positions
ADD COLUMN IF NOT EXISTS risk_pct DECIMAL(8, 4),
ADD COLUMN IF NOT EXISTS risk_rank INTEGER,
ADD COLUMN IF NOT EXISTS ladder_pct_stop DECIMAL(8, 4),
ADD COLUMN IF NOT EXISTS ladder_pct_entry DECIMAL(8, 4),
ADD COLUMN IF NOT EXISTS ladder_pct_current DECIMAL(8, 4),
ADD COLUMN IF NOT EXISTS ladder_pct_t1 DECIMAL(8, 4),
ADD COLUMN IF NOT EXISTS ladder_pct_t2 DECIMAL(8, 4),
ADD COLUMN IF NOT EXISTS ladder_pct_t3 DECIMAL(8, 4),
ADD COLUMN IF NOT EXISTS ladder_scale_min DECIMAL(12, 4),
ADD COLUMN IF NOT EXISTS ladder_scale_max DECIMAL(12, 4),
ADD COLUMN IF NOT EXISTS metrics_updated_at TIMESTAMP;

-- Step 2: Create sector_allocation_summary table for daily pre-computed sector grouping
CREATE TABLE IF NOT EXISTS sector_allocation_summary (
  id SERIAL PRIMARY KEY,
  snapshot_date DATE NOT NULL,
  sector VARCHAR(100) NOT NULL,
  position_count INTEGER NOT NULL DEFAULT 0,
  total_value_dollars DECIMAL(14, 2) NOT NULL DEFAULT 0,
  allocation_pct DECIMAL(8, 4) NOT NULL DEFAULT 0,
  is_overweight BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(snapshot_date, sector)
);

CREATE INDEX IF NOT EXISTS idx_sector_allocation_summary_date
ON sector_allocation_summary(snapshot_date DESC);

-- Step 3: Create indexes for performance on new columns
CREATE INDEX IF NOT EXISTS idx_algo_positions_risk_rank
ON algo_positions(risk_rank);

CREATE INDEX IF NOT EXISTS idx_algo_positions_metrics_updated
ON algo_positions(metrics_updated_at DESC);

-- Step 4: Create function to compute and update position metrics
-- This function is called after positions change to keep metrics up-to-date
CREATE OR REPLACE FUNCTION compute_position_metrics()
RETURNS void AS $$
DECLARE
  v_total_risk DECIMAL;
  v_position_count INTEGER;
  v_item RECORD;
  v_rank INTEGER;
  v_entry DECIMAL;
  v_cur DECIMAL;
  v_stop DECIMAL;
  v_t1 DECIMAL;
  v_t2 DECIMAL;
  v_t3 DECIMAL;
  v_lo DECIMAL;
  v_hi DECIMAL;
  v_span DECIMAL;
BEGIN
  -- Get total open risk across all open positions
  SELECT COALESCE(SUM(open_risk_dollars), 0)
  INTO v_total_risk
  FROM algo_positions
  WHERE status = 'open';

  -- Get count of open positions
  SELECT COUNT(*)
  INTO v_position_count
  FROM algo_positions
  WHERE status = 'open';

  -- Compute and update risk_pct and risk_rank for each open position
  v_rank := 1;
  FOR v_item IN
    SELECT id, position_id, open_risk_dollars, avg_entry_price, current_price,
           stop_loss_price, target_1_price, target_2_price, target_3_price
    FROM algo_positions
    WHERE status = 'open'
    ORDER BY open_risk_dollars DESC NULLS LAST
  LOOP
    -- Update risk metrics
    UPDATE algo_positions
    SET
      risk_pct = CASE
        WHEN v_total_risk > 0 THEN (v_item.open_risk_dollars / v_total_risk) * 100
        ELSE 0
      END,
      risk_rank = v_rank,
      metrics_updated_at = CURRENT_TIMESTAMP
    WHERE id = v_item.id;

    v_rank := v_rank + 1;
  END LOOP;

  -- Compute ladder percentages for visualization
  FOR v_item IN
    SELECT id, avg_entry_price, current_price, stop_loss_price,
           target_1_price, target_2_price, target_3_price
    FROM algo_positions
    WHERE status = 'open'
  LOOP
    v_entry := v_item.avg_entry_price;
    v_cur := v_item.current_price;
    v_stop := v_item.stop_loss_price;
    v_t1 := v_item.target_1_price;
    v_t2 := v_item.target_2_price;
    v_t3 := v_item.target_3_price;

    IF v_entry > 0 AND v_cur > 0 AND v_stop > 0 THEN
      v_lo := LEAST(v_stop, v_entry, v_cur);
      v_hi := GREATEST(COALESCE(v_t3, COALESCE(v_t2, COALESCE(v_t1, v_entry))), v_cur);
      v_span := GREATEST(0.0001, v_hi - v_lo);

      UPDATE algo_positions
      SET
        ladder_scale_min = v_lo,
        ladder_scale_max = v_hi,
        ladder_pct_stop = ((v_stop - v_lo) / v_span) * 100,
        ladder_pct_entry = ((v_entry - v_lo) / v_span) * 100,
        ladder_pct_current = ((v_cur - v_lo) / v_span) * 100,
        ladder_pct_t1 = CASE WHEN v_t1 > 0 THEN ((v_t1 - v_lo) / v_span) * 100 ELSE NULL END,
        ladder_pct_t2 = CASE WHEN v_t2 > 0 THEN ((v_t2 - v_lo) / v_span) * 100 ELSE NULL END,
        ladder_pct_t3 = CASE WHEN v_t3 > 0 THEN ((v_t3 - v_lo) / v_span) * 100 ELSE NULL END,
        metrics_updated_at = CURRENT_TIMESTAMP
      WHERE id = v_item.id;
    END IF;
  END LOOP;
END;
$$ LANGUAGE plpgsql;

-- Step 5: Create function to compute and update sector allocation summary
CREATE OR REPLACE FUNCTION compute_sector_allocation(p_snapshot_date DATE)
RETURNS void AS $$
DECLARE
  v_sector_record RECORD;
  v_total_value DECIMAL;
BEGIN
  -- Delete existing records for this date
  DELETE FROM sector_allocation_summary
  WHERE snapshot_date = p_snapshot_date;

  -- Get total position value
  SELECT COALESCE(SUM(position_value), 0)
  INTO v_total_value
  FROM algo_positions
  WHERE status = 'open';

  -- Insert sector groupings
  INSERT INTO sector_allocation_summary
    (snapshot_date, sector, position_count, total_value_dollars, allocation_pct, is_overweight, created_at, updated_at)
  SELECT
    p_snapshot_date,
    COALESCE(sector, 'Unknown') as sector,
    COUNT(*) as position_count,
    COALESCE(SUM(position_value), 0) as total_value_dollars,
    CASE
      WHEN v_total_value > 0 THEN (COALESCE(SUM(position_value), 0) / v_total_value) * 100
      ELSE 0
    END as allocation_pct,
    CASE
      WHEN v_total_value > 0 AND (COALESCE(SUM(position_value), 0) / v_total_value) > 0.3 THEN TRUE
      ELSE FALSE
    END as is_overweight,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
  FROM algo_positions
  WHERE status = 'open'
  GROUP BY sector;
END;
$$ LANGUAGE plpgsql;

-- COMMENT: These functions are called by the API layer when positions change,
-- ensuring metrics are always fresh without recomputing them on every request.
