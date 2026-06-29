# Complete Pipeline Orchestration Strategy

**Date:** 2026-06-28  
**Status:** Phase 1-2 Complete, Phase 3-4 Ready  
**Version:** 4.0

---

## Pipeline Architecture Overview

### Current State (Phase 1-2: Financial & Metrics)

```
TIMELINE (ET, Mon-Fri)

2:00 AM ┌─ morning_prep_pipeline ─────────────────┐
        │ • market_constituents                     │
        │ • stock_prices_daily (1d only)            │
        │ • market_health_daily                     │
        │ • trend_template_data                     │
        │ • swing_trader_scores (lookback mode)     │ 1.5-2 hours
        │ • technical_data_daily                    │
        │ • sector_ranking                          │
        │ • market_exposure_daily                   │
        └─ COMPLETE by 9:30 AM ────────────────────┘

4:05 PM ┌─ financial_data_pipeline ┐  ┌─ eod_pipeline ──────────────────┐
        │ • annual_income          │  │ • market_constituents           │
        │ • annual_balance         │  │ • stock_prices_daily (1d+1w+1mo)│
        │ • annual_cashflow        │  │ • market_health_daily           │ 3-4 hours
        │ • quarterly_income       │  │ • trend_template_data           │
        │ • quarterly_balance      │  │ • algo_metrics_daily            │
        │ • quarterly_cashflow     │  │ • swing_trader_scores           │
        │ • ttm_income             │  │ • technical_data_daily          │
        │ • ttm_cashflow           │  │ • buy_sell_daily                │
        │  ~60 minutes             │  │ • sector_ranking                │
        └──────────────────────────┘  │ • market_exposure_daily         │
                                      │ • data_patrol                   │
        5:00 PM ┌─ computed_metrics_pipeline ─┐  │ • orchestrator (dry-run) │
                │ • growth_metrics            │  └─────────────────────────┘
                │ • quality_metrics           │
                │ • value_metrics             │ ~45 minutes
                │ • stability_metrics         │
                │ • stock_scores              │
                └─────────────────────────────┘

12:50 PM ┌─ afternoon_update_pipeline ───────────┐
         │ • swing_trader_scores (intraday mode) │ 20-25 min
         └───────────────────────────────────────┘

2:50 PM ┌─ preclose_update_pipeline ────────────┐
        │ • swing_trader_scores (intraday mode) │ 15-20 min
        └───────────────────────────────────────┘
```

### Phase Breakdown

**Phase 1 (COMPLETE): Morning Data Prep**
- Status: ✅ Implemented via morning_prep_pipeline
- Loaders: 8 (symbols, prices, health, trends, technicals, sector)
- Duration: ~2 hours (2 AM - 4 AM ET)
- Dependencies: None (core data)

**Phase 2 (COMPLETE): Evening Data Load & Orchestration**
- Status: ✅ Implemented via eod_pipeline
- Loaders: 11 (prices full, metrics, scores, signals, ranking)
- Duration: ~3-4 hours (4 PM - 8 PM ET)
- Dependencies: morning_prep_pipeline (for comparison)

**Phase 3 (COMPLETE): Financial Data Integration**
- Status: ✅ Implemented via financial_data_pipeline
- Loaders: 8 (annual, quarterly, TTM statements)
- Duration: ~60 minutes (4 PM - 5 PM ET)
- Dependencies: None (SEC EDGAR)
- Triggers: computed_metrics_pipeline

**Phase 4 (COMPLETE): Computed Metrics**
- Status: ✅ Implemented via computed_metrics_pipeline
- Loaders: 5 (growth, quality, value, stability, scores)
- Duration: ~45 minutes (5 PM - 5:45 PM ET)
- Dependencies: financial_data_pipeline
- Impact: 5,832 stocks now compute quality/growth scores

---

## Next Phases (Ready to Implement)

### Phase 5: Reference Data (Earnings & Company Info)

**Timeline: 4:15 AM ET (after prices loaded)**

```
Pipeline: reference_data_pipeline
Duration: ~45 minutes
Loaders (5):
  • earnings_calendar        [1200s timeout]  — Next 180 days earnings
  • earnings_history         [7200s timeout]  — Historical earnings (yfinance)
  • company_profile          [1800s timeout]  — Sector, industry, name
  • positioning_metrics      [3600s timeout]  — Short interest, institutional
  • analyst_sentiment        [1800s timeout]  — Buy/hold/sell recommendations
  • analyst_upgrades_downgrades [1800s timeout] — Recent rating changes
Dependencies: market_constituents (symbol list)
Triggers: None (runs standalone, used by API/dashboard)
```

**Why it matters:**
- Earnings calendar blocks blackout periods (Phase 2 gates)
- Company profile used by dashboard search
- Analyst data improves signal quality filters

**Implementation: 2 option for timing**
- Option A: 4:15 AM (after market_constituents completes)
- Option B: Parallel with financial_data_pipeline at 4:05 PM (independent)

### Phase 6: Intraday Updates (1 PM & 3 PM)

**Timeline: 12:50 PM & 2:50 PM ET**

```
Pipelines: afternoon_update_pipeline, preclose_update_pipeline
Status: ✅ ALREADY IMPLEMENTED
Loaders (1 each): swing_trader_scores (INTRADAY_MODE flag)
Duration: 15-25 minutes each
Purpose: Fresh scores for afternoon/preclose orchestrator runs
```

### Phase 7: Market Sentiment & Economic Data (Optional Daily)

**Timeline: 4:30 PM ET (after financial pipeline)**

```
Pipeline: market_sentiment_pipeline (PROPOSED)
Duration: ~20 minutes
Loaders (6):
  • fred_economic_data       [300s timeout]   — Macro indicators (weekly)
  • economic_metrics_daily   [600s timeout]   — CPI, yields, SPY change
  • fear_greed_index         [600s timeout]   — CNN Fear & Greed
  • aaii_sentiment           [600s timeout]   — Investor sentiment (weekly Fri)
  • naaim_data               [600s timeout]   — Exposure index (weekly Fri)
  • options_chains           [3600s timeout]  — Put/call volumes
Dependencies: None (independent APIs)
Purpose: Market regime, breadth, positioning for Phase 1/3 gates
```

**Note:** FRED runs weekly only (Mondays). Consider consolidating or scheduling separately.

### Phase 8: Signal Processing (Currently Removed)

**Status: ❌ REMOVED intentionally**

Loaders removed from pipeline:
- signal_quality_scores → Removed (on-the-fly computation in Phase 5)
- signal_themes → Still on EventBridge (runs 5 AM)

Reason: Signal quality computed in Phase 5 orchestrator, not pre-computed. Reduces stale data risk.

---

## Implementation Priority

### ✅ DONE (Deployed to AWS)
1. Financial data pipeline (financial_data_pipeline)
2. Computed metrics pipeline (computed_metrics_pipeline)
3. Intraday updates (afternoon_update_pipeline, preclose_update_pipeline)

### 🔲 NEXT (Ready for implementation)
4. **Reference data pipeline** — Unlocks earnings blackout + analyst signals
   - Effort: Medium (new state machine)
   - Impact: High (enables all entry gates)
   - Timeline: Next week

5. **Market sentiment pipeline** — Improves regime detection
   - Effort: Low (new state machine)
   - Impact: Medium (optional, improves accuracy)
   - Timeline: Following week

### 📋 FUTURE (Design phase)
6. Advanced enrichment (sector/industry rankings, positioning analysis)
7. Real-time webhooks for market events (earnings, upgrades)
8. ML-based scoring integration

---

## Critical Success Factors

### Data Freshness SLAs

| Data | Max Age | Pipeline | Loader | SLA |
|------|---------|----------|--------|-----|
| Stock prices | 1 day | morning + EOD | stock_prices_daily | ✅ Met |
| Technical indicators | 1 day | EOD | technical_data_daily | ✅ Met |
| Financial statements | 1 day | financial | financials_* | ✅ Met |
| Quality scores | 1 day | computed | quality_metrics | ✅ Met |
| Growth scores | 1 day | computed | growth_metrics | ✅ Met |
| Market regime | 1 day | EOD | market_exposure_daily | ✅ Met |
| Earnings calendar | 180 days | reference | earnings_calendar | ⚠️ Pending |
| Analyst sentiment | 1 day | reference | analyst_sentiment | ⚠️ Pending |

### Dependency Chain Validation

```
stock_prices_daily
  ├─ technical_data_daily → buy_sell_daily ✅
  ├─ swing_trader_scores ✅
  ├─ algo_metrics_daily ✅
  └─ market_health_daily → market_exposure_daily ✅

financials_*
  ├─ growth_metrics ✅
  ├─ quality_metrics ✅
  └─ value_metrics ✅

growth_metrics
  └─ stock_scores ✅

market_constituents
  ├─ stock_prices_daily ✅
  └─ earnings_calendar ⚠️
```

### RDS Connection Pool Management

**Peak connection usage:**
- Morning pipeline: ~8 concurrent loaders × 1 parallelism = 8 connections
- Financial pipeline: 8 sequential × 1 parallelism = 1 connection
- EOD pipeline: ~11 concurrent × 1 parallelism = 11 connections
- Metrics pipeline: 5 sequential × 2 parallelism = 10 connections peak
- **Total peak: ~20 connections** (safe: RDS configured for 100 max)

---

## Troubleshooting Playbook

### Financial Pipeline Timeout (5 PM deadline)

**Symptom:** Financial pipeline not complete by 5 PM ET  
**Impact:** Computed metrics run with stale financial data

**Solutions:**
1. Check RDS CPU (CloudWatch → RDS → CPU %)
2. Increase financial loader parallelism (currently 1)
3. Split into two parallel chains (annual vs quarterly)
4. Add RDS Proxy connection multiplexing

### Metrics Pipeline Missing Data

**Symptom:** quality_metrics runs but stock_scores show "--"  
**Impact:** No composite scores despite financial data available

**Solutions:**
1. Check financial pipeline logs for failures
2. Verify quality/growth/value/stability all completed
3. Check stock_scores input data (requires ≥3 metrics)
4. Monitor data_unavailable flags in tables

### EOD Pipeline Slow (>4 hours)

**Symptom:** buy_sell_daily or orchestrator delayed  
**Impact:** Trading signals not ready for next market open

**Solutions:**
1. Check stock_prices_daily completion time (yfinance rate limits)
2. Verify market close data lag (sometimes prices delayed 30+ min)
3. Check RDS statement timeouts (CloudWatch logs)
4. Increase EOD pipeline timeout or split into phases

---

## Monitoring & Alerting

### Required CloudWatch Metrics

**Per pipeline:**
- ExecutionsFailed (count)
- ExecutionTime (max)
- ExecutionsTimedOut (count)

**Per loader (from loader_execution_status table):**
- Completion time
- Data row counts
- Error rate (% symbols failed)
- Data freshness (minutes since last update)

### Recommended Alarms

```
- Morning pipeline not complete by 9:00 AM → ALERT
- Financial pipeline not complete by 5:00 PM → ALERT
- Metrics pipeline not complete by 6:00 PM → ALERT
- EOD pipeline > 4.5 hours → ALERT
- Any loader > 80% failure rate → ALERT
- Data gap > 24 hours → CRITICAL
```

### Dashboard Widgets

- Pipeline execution timeline (Gantt chart)
- Loader status per pipeline (completion time, failures)
- Data freshness heatmap (age by table)
- RDS connection pool utilization
- Stock score distribution (% with quality, growth, etc.)

---

## Cost Optimization

### Current Infrastructure Cost

**Step Functions:**
- ~8 executions per day (morning + 3×EOD + 3×financial + 3×metrics + 2×intraday)
- ~$0.25 per 1K state transitions
- Estimate: ~$1-2/month

**ECS Fargate:**
- Morning: 2 hours × 8 tasks × $0.032/hour = $0.51/day
- EOD: 4 hours × 11 tasks × $0.032/hour = $1.41/day
- Financial: 1 hour × 8 tasks × $0.032/hour = $0.26/day
- Metrics: 1 hour × 5 tasks × $0.032/hour = $0.16/day
- Intraday: 40 min × 2 × 1 task × $0.032/hour = $0.04/day
- **Total: ~$2.38/day = $70/month (dev environment)**

**RDS (db.t4g.small):**
- ~$30/month

**Total Monthly: ~$100**

### Optimization Opportunities

1. **Batch loaders in single task** (save container startup overhead)
2. **Use ECS Spot instances** for non-critical loaders (50% savings)
3. **Consolidate small loaders** (earnings_calendar + company_profile in one task)
4. **On-demand only for critical paths** (prices, technicals, signals)

---

## Success Metrics

### Phase 1-4 Complete (TODAY)

- [x] Financial data loads daily (was Monday-only)
- [x] Quality/growth scores compute for 50%+ stocks (was 17%)
- [x] BREZ and 5,831 other stocks now have quality/growth scores
- [x] All metric loaders run with fresh data daily
- [x] No manual re-runs needed for data gaps
- [x] Complete data dependency chain documented

### Phase 5-6 Ready (Next 2 weeks)

- [ ] Reference data pipeline implemented (earnings + analyst)
- [ ] Earnings blackout gates enabled
- [ ] Analyst sentiment integrated into signal scoring
- [ ] Dashboard shows earnings calendar

### Phase 7+ Future

- [ ] Market sentiment pipeline for regime detection
- [ ] Real-time earnings alerts
- [ ] ML-enhanced scoring
- [ ] Automated infrastructure scaling

---

## Rollback & Recovery

### If Pipeline Fails Completely

```bash
# Disable all Step Functions triggers
aws scheduler update-schedule --name algo-financial-data-pipeline-dev --state DISABLED
aws scheduler update-schedule --name algo-computed-metrics-pipeline-dev --state DISABLED

# Fall back to EventBridge (will have stale data but functional)
# Financial loaders run Monday only (in EventBridge)
# Quality/growth metrics run staggered (EventBridge)

# Manual re-run for same-day recovery
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:us-east-1:626216981288:stateMachine:algo-financial-data-pipeline-dev \
  --name manual-recovery-$(date +%s)
```

### Data Consistency Check

```sql
-- Verify financial data freshness
SELECT COUNT(*) FROM annual_income_statement 
WHERE updated_at >= NOW() - INTERVAL '24 hours';

-- Verify metrics computed
SELECT COUNT(*) FROM quality_metrics 
WHERE data_unavailable = FALSE;

-- Verify scores populated
SELECT COUNT(*) FROM stock_scores 
WHERE quality_factor_score IS NOT NULL;
```

---

## References

- `PHASE_4_FINANCIAL_PIPELINE.md` — Financial data pipeline (Phase 3)
- `terraform/modules/pipeline/main.tf` — All state machines + triggers
- `terraform/modules/loaders/main.tf` — Task definitions + EventBridge rules
- `steering/GOVERNANCE.md` — Architecture & safety rules
- `steering/OPERATIONS.md` — CI/CD & deployment procedures

