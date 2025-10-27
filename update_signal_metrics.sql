-- Update signal metrics for recent records (past 7 days)
-- This SQL script updates calculated fields directly in the database

-- 1. Calculate and update risk_pct (percentage risk from entry to stop)
UPDATE buy_sell_daily
SET risk_pct = ROUND(
  CASE
    WHEN buylevel > 0 THEN ((buylevel - stoplevel) / buylevel) * 100
    ELSE 0.0
  END, 2)
WHERE date >= CURRENT_DATE - INTERVAL '7 days'
  AND risk_pct IS NULL;

-- 2. Update entry_quality_score (0-100 based on volume, price range, RS rating)
UPDATE buy_sell_daily
SET entry_quality_score = ROUND(
  CASE WHEN (high - low) > 0 AND volume > 0 THEN
    50 +
    CASE
      WHEN volume_surge_pct > 50 THEN 20
      WHEN volume_surge_pct > 25 THEN 15
      WHEN volume_surge_pct > 0 THEN 10
      ELSE 0
    END +
    CASE
      WHEN ((high - low) / low) * 100 > 3.0 THEN 15
      WHEN ((high - low) / low) * 100 > 1.5 THEN 10
      ELSE 0
    END +
    CASE
      WHEN rs_rating >= 70 THEN 20
      WHEN rs_rating >= 50 THEN 10
      ELSE 0
    END
  ELSE 50
  END, 1)
WHERE date >= CURRENT_DATE - INTERVAL '7 days'
  AND entry_quality_score IS NULL;

-- 3. Update position_size_recommendation (2% risk rule with RR adjustment)
UPDATE buy_sell_daily
SET position_size_recommendation = ROUND(
  CASE
    WHEN risk_pct > 0 AND risk_reward_ratio > 0 THEN
      LEAST(5.0,
        (2.0 / GREATEST(risk_pct, 0.1)) *
        CASE
          WHEN risk_reward_ratio > 3 THEN 1.5
          WHEN risk_reward_ratio > 2 THEN 1.25
          ELSE 1.0
        END
      )
    ELSE 0.0
  END, 2)
WHERE date >= CURRENT_DATE - INTERVAL '7 days'
  AND position_size_recommendation IS NULL;

-- 4. Update market_stage and related fields
UPDATE buy_sell_daily
SET
  market_stage = CASE
    WHEN rs_rating >= 70 AND volume_surge_pct > 25 THEN 'Stage 2 - Advancing'
    WHEN rs_rating >= 50 AND rs_rating < 70 AND volume_surge_pct >= 0 THEN 'Stage 1 - Basing'
    WHEN rs_rating >= 80 AND volume_surge_pct < 15 THEN 'Stage 3 - Topping'
    ELSE 'Stage 4 - Declining'
  END,
  stage_number = CASE
    WHEN rs_rating >= 70 AND volume_surge_pct > 25 THEN 2
    WHEN rs_rating >= 50 AND rs_rating < 70 AND volume_surge_pct >= 0 THEN 1
    WHEN rs_rating >= 80 AND volume_surge_pct < 15 THEN 3
    ELSE 4
  END,
  stage_confidence = CASE
    WHEN rs_rating >= 70 AND volume_surge_pct > 25 THEN 85.0
    WHEN rs_rating >= 50 AND rs_rating < 70 AND volume_surge_pct >= 0 THEN 75.0
    WHEN rs_rating >= 80 AND volume_surge_pct < 15 THEN 65.0
    ELSE 60.0
  END
WHERE date >= CURRENT_DATE - INTERVAL '7 days'
  AND (market_stage IS NULL OR stage_number IS NULL);

-- 5. Update substage
UPDATE buy_sell_daily
SET substage = CASE
  WHEN market_stage = 'Stage 2 - Advancing' THEN
    CASE WHEN volume_surge_pct > 50 THEN 'Breakout' ELSE 'Continuation' END
  WHEN market_stage = 'Stage 1 - Basing' THEN 'Consolidation'
  WHEN market_stage = 'Stage 3 - Topping' THEN 'Distribution'
  ELSE '—'
END
WHERE date >= CURRENT_DATE - INTERVAL '7 days'
  AND substage IS NULL;

-- 6. Update profit targets and sell level
UPDATE buy_sell_daily
SET
  profit_target_8pct = ROUND(buylevel * 1.08, 2),
  profit_target_20pct = ROUND(buylevel * 1.20, 2),
  profit_target_25pct = ROUND(buylevel * 1.25, 2),
  sell_level = ROUND(
    CASE
      WHEN risk_reward_ratio > 2 THEN buylevel * 1.30
      WHEN risk_reward_ratio > 1.5 THEN buylevel * 1.25
      ELSE buylevel * 1.20
    END, 2)
WHERE date >= CURRENT_DATE - INTERVAL '7 days'
  AND (profit_target_8pct IS NULL OR sell_level IS NULL);

-- Verify updates
SELECT COUNT(*) as records_updated,
       COUNT(DISTINCT symbol) as symbols_updated,
       MAX(date) as latest_date,
       COUNT(CASE WHEN risk_pct IS NOT NULL THEN 1 END) as with_risk_pct,
       COUNT(CASE WHEN entry_quality_score IS NOT NULL THEN 1 END) as with_quality_score,
       COUNT(CASE WHEN market_stage IS NOT NULL THEN 1 END) as with_market_stage
FROM buy_sell_daily
WHERE date >= CURRENT_DATE - INTERVAL '7 days';
