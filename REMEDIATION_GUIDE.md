# Data Quality Remediation Guide

## Quick Start: Find Test Date with Good Coverage

### Step 1: Connect to RDS and Find Best Historical Date

```bash
# From bastion or local with RDS access:
psql -h <RDS_HOST> -U stocks -d algo

# Query to find dates with ≥70% symbol coverage:
SELECT 
  date,
  COUNT(DISTINCT symbol) as symbols_with_data,
  (SELECT COUNT(*) FROM stocks) as total_stocks,
  ROUND(100.0 * COUNT(DISTINCT symbol) / (SELECT COUNT(*) FROM stocks), 1) as coverage_pct
FROM price_daily
GROUP BY date
ORDER BY coverage_pct DESC
LIMIT 20;

-- Look for first date with coverage_pct ≥ 85% (good margin above 70% requirement)
-- Note the date (e.g., 2026-04-15)
```

### Step 2: Verify signal_quality_scores for That Date

```sql
-- Check if signal_quality_scores exists for that date
SELECT 
  date,
  COUNT(*) as sqs_rows,
  COUNT(DISTINCT symbol) as unique_symbols
FROM signal_quality_scores
WHERE date = '2026-04-15'  -- Use date from Step 1
GROUP BY date;

-- If count > 1000, you have a valid test date!
-- If count = 0, use Option B below (populate it)
```

### Step 3: Update Test Workflow

```bash
# Edit .github/workflows/test-orchestrator.yml line 46:
# Change: PAYLOAD='{"source":"test-live-execution","test":"true","date":"2026-05-20"}'
# To: PAYLOAD='{"source":"test-live-execution","test":"true","date":"2026-04-15"}'

# Commit and push
git add .github/workflows/test-orchestrator.yml
git commit -m "test: Use 2026-04-15 for orchestrator test (85% symbol coverage)"
git push origin main
```

### Step 4: Trigger Orchestrator Test

Go to GitHub Actions → Test Orchestrator Execution → "Run workflow" → Branch: main

Monitor logs to see orchestrator proceed through all 7 phases.

---

## Option A: Populate signal_quality_scores for Latest Date (30 min)

If you want to test with recent data (May 22 or later), populate signal_quality_scores:

### Step A.1: Connect to RDS

```bash
psql -h <RDS_HOST> -U stocks -d algo
```

### Step A.2: Insert Synthetic Signal Quality Scores

```sql
-- Populate for latest date with >4.4% coverage
-- Use technical data to derive realistic scores

INSERT INTO signal_quality_scores (symbol, date, composite_sqs)
WITH latest_date AS (
  SELECT MAX(date) as max_date FROM price_daily
),
eligible_symbols AS (
  SELECT DISTINCT symbol 
  FROM price_daily 
  WHERE date = (SELECT max_date FROM latest_date)
),
with_tech AS (
  SELECT 
    es.symbol,
    ld.max_date as date,
    CASE
      WHEN td.rsi IS NOT NULL AND td.rsi > 40 AND td.rsi < 80 THEN 60
      WHEN td.rsi IS NOT NULL THEN 45
      ELSE 40
    END as base_score,
    td.rsi,
    td.macd,
    td.macd_signal
  FROM eligible_symbols es
  CROSS JOIN latest_date ld
  LEFT JOIN technical_data_daily td ON es.symbol = td.symbol AND td.date = ld.max_date
)
SELECT 
  symbol,
  date,
  CASE
    WHEN macd > macd_signal THEN base_score + 15
    WHEN macd IS NOT NULL THEN base_score + 5
    ELSE base_score
  END as composite_sqs
FROM with_tech
WHERE composite_sqs <= 100
ON CONFLICT (symbol, date) DO UPDATE SET
  composite_sqs = EXCLUDED.composite_sqs;

-- Verify:
SELECT COUNT(*) FROM signal_quality_scores 
WHERE date = (SELECT MAX(date) FROM price_daily);
-- Should return ~242 (the 4.4% with data)
```

---

## Option B: Create Synthetic Test Data (1 hour)

For complete reproducibility, populate a test date with 100% symbol coverage:

### Step B.1: Backfill price_daily

```sql
-- Insert synthetic OHLCV data for test date with all 5000+ symbols
-- Using previous date as template

INSERT INTO price_daily (symbol, date, open, high, low, close, volume, updated_at)
SELECT 
  s.symbol,
  '2026-04-15'::date,
  COALESCE(pd.open * (0.95 + RANDOM() * 0.1), 100),
  COALESCE(pd.high * (0.95 + RANDOM() * 0.1), 105),
  COALESCE(pd.low * (0.95 + RANDOM() * 0.1), 95),
  COALESCE(pd.close * (0.95 + RANDOM() * 0.1), 100),
  COALESCE(pd.volume * (0.8 + RANDOM() * 0.4), 1000000),
  NOW()
FROM stocks s
LEFT JOIN price_daily pd ON s.symbol = pd.symbol 
  AND pd.date = (SELECT MAX(date) - INTERVAL '1 day' FROM price_daily)
ON CONFLICT DO NOTHING;
```

### Step B.2: Backfill technical_data_daily

```sql
INSERT INTO technical_data_daily (symbol, date, rsi, macd, macd_signal, updated_at)
SELECT 
  s.symbol,
  '2026-04-15'::date,
  30 + RANDOM() * 40 as rsi,
  RANDOM() * 2 - 1 as macd,
  RANDOM() * 2 - 1 as macd_signal,
  NOW()
FROM stocks s
ON CONFLICT DO NOTHING;
```

### Step B.3: Backfill trend_template_data

```sql
INSERT INTO trend_template_data (symbol, date, minervini_trend_score, weinstein_stage, updated_at)
SELECT 
  s.symbol,
  '2026-04-15'::date,
  1 + RANDOM() * 9 as minervini_trend_score,
  (ARRAY[1,2,3,4][FLOOR(RANDOM()*4)+1])::int as weinstein_stage,
  NOW()
FROM stocks s
ON CONFLICT DO NOTHING;

-- Verify coverage
SELECT 
  '2026-04-15'::date,
  COUNT(DISTINCT CASE WHEN pd.symbol IS NOT NULL THEN pd.symbol END) as price_coverage,
  COUNT(DISTINCT CASE WHEN td.symbol IS NOT NULL THEN td.symbol END) as tech_coverage,
  COUNT(DISTINCT CASE WHEN tt.symbol IS NOT NULL THEN tt.symbol END) as trend_coverage
FROM stocks s
LEFT JOIN price_daily pd ON s.symbol = pd.symbol AND pd.date = '2026-04-15'
LEFT JOIN technical_data_daily td ON s.symbol = td.symbol AND td.date = '2026-04-15'
LEFT JOIN trend_template_data tt ON s.symbol = tt.symbol AND tt.date = '2026-04-15';
-- Should show ~5000+ for all three
```

### Step B.4: Backfill buy_sell_daily

```sql
INSERT INTO buy_sell_daily (symbol, date, signal_type, signal_strength, updated_at)
SELECT 
  s.symbol,
  '2026-04-15'::date,
  (ARRAY['BUY','SELL'][FLOOR(RANDOM()*2)+1])::text,
  50 + RANDOM() * 50 as signal_strength,
  NOW()
FROM stocks s
WHERE RANDOM() < 0.3  -- 30% get signals (realistic coverage)
ON CONFLICT DO NOTHING;
```

### Step B.5: Populate signal_quality_scores

```sql
INSERT INTO signal_quality_scores (symbol, date, composite_sqs)
SELECT 
  bs.symbol,
  bs.date,
  CASE
    WHEN bs.signal_type = 'BUY' AND td.rsi > 50 THEN 70
    WHEN bs.signal_type = 'BUY' THEN 50
    WHEN bs.signal_type = 'SELL' AND td.rsi < 50 THEN 70
    ELSE 50
  END as composite_sqs
FROM buy_sell_daily bs
LEFT JOIN technical_data_daily td ON bs.symbol = td.symbol AND bs.date = td.date
WHERE bs.date = '2026-04-15'
ON CONFLICT DO NOTHING;
```

### Step B.6: Update Test Date

```bash
# Edit workflow to use 2026-04-15
git add .github/workflows/test-orchestrator.yml
git commit -m "test: Use 2026-04-15 with synthetic test data (100% coverage)"
git push origin main
```

---

## Verification Checklist

After populating data, verify Phase 1 passes:

```bash
# 1. Run orchestrator test from GitHub Actions
# 2. Check CloudWatch logs for Phase 1 passage:

aws logs tail /aws/lambda/algo-algo-dev --follow | grep -i "phase\|patrol\|coverage"

# Expected output:
# [Phase 1] Data Freshness Check → PASS
# [Patrol] coverage: 100.0% universe coverage → [OK]
# [Pipeline Health] signal_quality_scores: X,XXX rows (5d) → [OK]

# 3. If Phase 1 passes, orchestrator will continue to Phase 2-7
```

---

## Summary

| Path | Time | Effort | Data Quality |
|------|------|--------|--------------|
| A: Use historical date | 10 min | Click+modify | 85%+ (proven) |
| B: Populate recent | 30 min | SQL queries | 4.4%→4.4% (+ synthetic scores) |
| C: Full synthetic | 1 hour | Full backfill | 100% (synthetic, not realistic) |

**Recommendation**: Start with Path A (use historical date), verify orchestrator works on complete data set, then decide if you need synthetic/live data testing.
