# Deployment Checklist - Enhanced Stage Analysis System

## Overview
World-class enhanced stage analysis system with 27 swing trading metrics including:
- Volatility-adaptive stage classification (80-85% accuracy target)
- Multi-factor confidence scoring (0-100)
- Substage detection (Early/Mid/Late)
- Complete swing trading decision framework

## Pre-Deployment Checklist

### 1. Database Migration (AWS RDS)
- [ ] Connect to AWS RDS PostgreSQL database
- [ ] Run migration: `psql -h [host] -U [user] -d [database] -f migrate_enhanced_stage_analysis.sql`
- [ ] Verify functions created:
  ```sql
  SELECT COUNT(*) FROM pg_proc WHERE proname IN (
    'get_volatility_profile',
    'get_dynamic_adx_threshold',
    'get_dynamic_slope_threshold',
    'calculate_enhanced_stage'
  );
  -- Should return 4
  ```
- [ ] Verify columns added:
  ```sql
  SELECT column_name FROM information_schema.columns
  WHERE table_name IN ('buy_sell_daily', 'buy_sell_weekly', 'buy_sell_monthly')
  AND column_name IN ('stage_confidence', 'substage', 'volatility_profile');
  -- Should return 9 rows (3 columns × 3 tables)
  ```

### 2. Backend Deployment (ECS Task)
- [ ] Code already committed to main branch (commit 5c2394bb4)
- [ ] loadbuyselldaily.py calls calculate_enhanced_stage() function
- [ ] Rebuild Docker image: `docker build -t loadbuyselldaily:latest -f Dockerfile.buyselldaily .`
- [ ] Push to ECR: `docker push [ecr-url]/loadbuyselldaily:latest`
- [ ] Update ECS task definition
- [ ] Force new deployment: `aws ecs update-service --cluster [cluster] --service buyselldaily --force-new-deployment`
- [ ] Run loader once: Verify stage_confidence and substage populate correctly

### 3. Lambda API Deployment
- [ ] Code already committed to main branch
- [ ] Routes/signals.js returns stage_confidence and substage fields
- [ ] Deploy Lambda: `cd webapp/lambda && npm install && npm run build && [deploy-command]`
- [ ] Test API: `curl https://[api-url]/api/signals | jq '.data[0] | {market_stage, stage_confidence, substage}'`

### 4. Frontend Deployment
- [ ] Code already committed to main branch
- [ ] TradingSignals.jsx displays confidence scores and substages
- [ ] All "Minervini" references removed (replaced with "Trend ✓")
- [ ] Tooltips enhanced with complete trading guidance
- [ ] Build: `cd webapp/frontend && npm install && npm run build`
- [ ] Deploy to S3/CloudFront: `[deploy-command]`
- [ ] Clear CloudFront cache if needed

## Post-Deployment Verification

### 1. API Test
```bash
curl https://[api-url]/api/signals | jq '.data[0] | {
  symbol,
  market_stage,
  stage_confidence,
  substage,
  entry_quality_score,
  volume_analysis,
  risk_reward_ratio
}'
```

Expected output:
```json
{
  "symbol": "AAPL",
  "market_stage": "Stage 2 - Advancing",
  "stage_confidence": 85,
  "substage": "Stage 2 - Mid",
  "entry_quality_score": 82,
  "volume_analysis": "Pocket Pivot",
  "risk_reward_ratio": 3.5
}
```

### 2. UI Verification
- [ ] Navigate to Trading Signals page
- [ ] Verify "Stage" column shows stage abbreviation + confidence number (e.g., "S2 85")
- [ ] Hover over stage badge to see tooltip with full stage, confidence, and substage
- [ ] Verify confidence color coding:
  - 75+ = green (#059669)
  - 60-74 = blue (#3B82F6)
  - 40-59 = yellow (#F59E0B)
  - 0-39 = red (#DC2626)
- [ ] Verify "Trend ✓" column (no "Minervini" references)
- [ ] Hover over all column headers to verify enhanced tooltips

### 3. Database Verification
```sql
-- Check confidence score distribution
SELECT
  CASE
    WHEN stage_confidence >= 80 THEN '80-100 (Very High)'
    WHEN stage_confidence >= 60 THEN '60-79 (High)'
    WHEN stage_confidence >= 40 THEN '40-59 (Moderate)'
    ELSE '0-39 (Low)'
  END as confidence_range,
  COUNT(*) as signal_count
FROM buy_sell_daily
WHERE stage_confidence IS NOT NULL
GROUP BY confidence_range
ORDER BY MIN(stage_confidence) DESC;

-- Check substage distribution
SELECT substage, COUNT(*) as count
FROM buy_sell_daily
WHERE substage IS NOT NULL
GROUP BY substage
ORDER BY count DESC;

-- Check average confidence by stage
SELECT
  market_stage,
  COUNT(*) as count,
  ROUND(AVG(stage_confidence), 1) as avg_confidence
FROM buy_sell_daily
WHERE stage_confidence IS NOT NULL
GROUP BY market_stage
ORDER BY avg_confidence DESC;
```

## All 27 Swing Trading Metrics

### Risk Management (5 metrics)
1. `buylevel` - Entry price
2. `stoplevel` - Stop loss (7-8% max risk)
3. `risk_pct` - Percentage risk (≤8% acceptable)
4. `risk_reward_ratio` - R/R ratio (≥2:1 required, ≥3:1 excellent)
5. `position_size_recommendation` - Shares to buy (1% portfolio risk)

### Profit Targets (4 metrics)
6. `target_price` - 25% profit target
7. `profit_target_8pct` - First target (sell 20-25%)
8. `profit_target_20pct` - Second target (sell 25-30%)
9. `current_gain_loss_pct` - Current profit/loss %

### Stage Analysis (3 metrics)
10. `market_stage` - Weinstein stage (1=Basing, 2=Advancing, 3=Topping, 4=Declining)
11. `stage_confidence` - **NEW** Confidence score 0-100
12. `substage` - **NEW** Early/Mid/Late within stage

### Entry Quality (9 metrics)
13. `entry_quality_score` - Overall quality 0-100 (80+=excellent)
14. `pct_from_ema_21` - Distance from 21 EMA (-1% to +2% = best)
15. `pct_from_sma_50` - Distance from 50 SMA
16. `pct_from_sma_200` - Distance from 200 SMA
17. `volume_ratio` - Current/avg volume ratio
18. `volume_analysis` - Pocket Pivot/Volume Surge/Normal/Dry-up
19. `rsi` - RSI indicator (40-55 = best buy zone)
20. `adx` - Trend strength (>30 = very strong)
21. `passes_minervini_template` - 7-point trend template

### Volatility & Risk (3 metrics)
22. `atr` - Average True Range
23. `daily_range_pct` - Daily volatility %
24. `current_price` - Current market price

### Position Management (3 metrics)
25. `inposition` - Currently holding position
26. `selllevel` - Sell target price
27. `timeframe` - Daily/Weekly/Monthly

## Rollback Procedure

If issues occur:

### 1. Quick Rollback (Keep Schema)
```bash
# Revert code only
git revert 5c2394bb4
git push

# Redeploy Lambda and Frontend
cd webapp/lambda && [deploy-command]
cd webapp/frontend && [deploy-command]
```

The database schema is backward compatible - old `calculate_weinstein_stage()` still works.

### 2. Full Rollback (Remove Schema)
```sql
-- Only if you want to remove new columns
ALTER TABLE buy_sell_daily
  DROP COLUMN IF EXISTS stage_confidence,
  DROP COLUMN IF EXISTS substage,
  DROP COLUMN IF EXISTS volatility_profile;

ALTER TABLE buy_sell_weekly
  DROP COLUMN IF EXISTS stage_confidence,
  DROP COLUMN IF EXISTS substage,
  DROP COLUMN IF EXISTS volatility_profile;

ALTER TABLE buy_sell_monthly
  DROP COLUMN IF EXISTS stage_confidence,
  DROP COLUMN IF EXISTS substage,
  DROP COLUMN IF EXISTS volatility_profile;

DROP FUNCTION IF EXISTS calculate_enhanced_stage;
DROP FUNCTION IF EXISTS get_dynamic_slope_threshold;
DROP FUNCTION IF EXISTS get_dynamic_adx_threshold;
DROP FUNCTION IF EXISTS get_volatility_profile;
```

## Performance Expectations

- **Database migration**: <30 seconds
- **Per-symbol calculation**: 50-100ms (vs 20-30ms basic)
- **API response time**: No change (data pre-calculated)
- **Frontend rendering**: No change
- **Accuracy improvement**: From 65-75% to 80-85%

## Support & Monitoring

Monitor confidence score distribution weekly:
- Target: 50%+ signals with confidence ≥60
- Alert if average confidence <50 for Stage 2 signals
- Review substage distribution for data quality

## Reference Documents

- **SWING_TRADING_DECISION_GUIDE.md** - Complete decision framework for users
- **SWING_TRADING_METRICS.md** - Technical metric explanations
- **ENHANCED_STAGE_DEPLOYMENT.md** - Detailed deployment guide
- **migrate_enhanced_stage_analysis.sql** - Database migration file

## Completion Sign-Off

- [ ] Database migration completed successfully
- [ ] Backend deployed and loader running
- [ ] Lambda API deployed and tested
- [ ] Frontend deployed and UI verified
- [ ] All 27 metrics populating correctly
- [ ] Confidence scores in expected range
- [ ] No "Minervini" references in UI
- [ ] Documentation updated
- [ ] Monitoring alerts configured

**Deployed by**: _______________
**Date**: _______________
**Version**: 2.0 (Enhanced Rule-Based)
