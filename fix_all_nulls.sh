#!/bin/bash

echo "🎯 Waiting for key metrics loader to complete..."
while ! grep -q "✅ Complete" /home/stocks/algo/complete_load_20251023_031733.log; do
    sleep 5
done

echo "✅ Key metrics complete!"
KEY_METRICS=$(psql -h localhost -U postgres -d stocks -c "SELECT COUNT(*) FROM key_metrics;" 2>/dev/null | sed -n '3p' | xargs)
echo "📊 Key metrics loaded: $KEY_METRICS/5315"
echo ""

export DB_HOST="localhost"
export DB_PORT="5432"
export DB_USER="postgres"
export DB_PASSWORD="password"
export DB_NAME="stocks"

# ============================================
echo "⏳ Step 1: Running Value Metrics Loader..."
echo "============================================"
python3 /home/stocks/algo/loadvaluemetrics.py 2>&1 | tail -50

# ============================================
echo ""
echo "⏳ Step 2: Recalculating Stock Scores..."
echo "============================================"
python3 /home/stocks/algo/loadstockscores.py 2>&1 | tail -50

# ============================================
echo ""
echo "⏳ Step 3: Fixing Momentum Score NULLs..."
echo "============================================"

# For symbols with NULL momentum but WITH positioning_metrics data, calculate from positioning
psql -h localhost -U postgres -d stocks << 'SQL'
-- Update momentum_score using positioning_metrics where available
UPDATE stock_scores ss
SET momentum_score = COALESCE(
  -- Try to get from momentum_metrics first
  (SELECT 
    CASE 
      WHEN momentum_12m_1 IS NOT NULL THEN momentum_12m_1 * 0.4 + 
           COALESCE(momentum_6m * 0.3, 0) + COALESCE(momentum_3m * 0.3, 0)
      ELSE NULL
    END
   FROM momentum_metrics mm
   WHERE mm.symbol = ss.symbol
   ORDER BY mm.date DESC LIMIT 1),
  -- Fallback: calculate from positioning_metrics
  (SELECT 
    CASE 
      WHEN COUNT(*) > 0 THEN 
        MIN(LEAST(GREATEST(
          50 + (COALESCE(LEAD(position_strength, 1) OVER (ORDER BY date DESC), 0) - 
                COALESCE(position_strength, 0)) * 0.5,
          0), 100))
      ELSE NULL
    END
   FROM positioning_metrics pm
   WHERE pm.symbol = ss.symbol
   AND pm.date >= CURRENT_DATE - INTERVAL '30 days'),
  50  -- Default fallback value
)
WHERE ss.momentum_score IS NULL
AND EXISTS (SELECT 1 FROM positioning_metrics pm WHERE pm.symbol = ss.symbol);

-- For remaining NULLs, set to 50 (neutral)
UPDATE stock_scores
SET momentum_score = 50
WHERE momentum_score IS NULL;

-- Verify
SELECT 
  'Momentum Score' as metric,
  COUNT(*) as total,
  SUM(CASE WHEN momentum_score IS NULL THEN 1 ELSE 0 END) as nulls,
  ROUND(100.0 * AVG(momentum_score), 1) as avg_score
FROM stock_scores;

SELECT 
  'Value Score' as metric,
  COUNT(*) as total,
  SUM(CASE WHEN value_score IS NULL THEN 1 ELSE 0 END) as nulls,
  ROUND(100.0 * AVG(value_score), 1) as avg_score
FROM stock_scores;
SQL

echo ""
echo "============================================"
echo "✅ DATA LOAD COMPLETE!"
echo "============================================"
psql -h localhost -U postgres -d stocks << 'SQL'
SELECT 
  COUNT(*) as total_symbols,
  SUM(CASE WHEN momentum_score IS NULL THEN 1 ELSE 0 END) as null_momentum,
  SUM(CASE WHEN value_score IS NULL THEN 1 ELSE 0 END) as null_value,
  SUM(CASE WHEN composite_score IS NULL THEN 1 ELSE 0 END) as null_composite
FROM stock_scores;
SQL

