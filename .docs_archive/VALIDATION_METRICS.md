# VALIDATION & METRICS TRACKING

**Purpose:** Verify Phase 2 Corrected meets expected performance, cost, and functionality

---

## PHASE 2 CORRECTED - EXPECTED VS ACTUAL

### Performance Metrics

| Metric | Expected | Actual | Status |
|--------|----------|--------|--------|
| Execution time | 17 min | TBD | Monitoring |
| Rows loaded (total) | 240k | TBD | Monitoring |
| Rows/second | 235 | TBD | Monitoring |
| ECS tasks running | 3 parallel | TBD | Monitoring |
| Task failures | 0 | TBD | Monitoring |

**Phase 2 Loaders:**
- loadecondata: 85,000 rows (FRED economic data)
- loadstockscores: 5,000 rows (stock scores)
- loadfactormetrics: 150,000 rows (6 factor metric tables)

---

### Cost Metrics

| Item | Expected | Actual | Status |
|------|----------|--------|--------|
| Total cost | $0.50 | TBD | Monitoring |
| ECS compute | $0.25 | TBD | Monitoring |
| RDS operations | $0.15 | TBD | Monitoring |
| Data transfer | $0.10 | TBD | Monitoring |
| Cost per row | $0.0000021 | TBD | Monitoring |

**Cost cap:** $1.35 (auto-abort if exceeded)

---

### Functionality Checks

#### Data Integrity
- [ ] All rows inserted (no partial loads)
- [ ] No duplicate rows
- [ ] No NULL values in required fields
- [ ] Date ranges valid
- [ ] Numeric values in expected ranges

#### Database State
- [ ] sector_technical_data: empty or has data
- [ ] economic_data: ~85k rows
- [ ] stock_scores: ~5k rows
- [ ] quality_metrics: ~25k rows
- [ ] growth_metrics: ~25k rows
- [ ] momentum_metrics: ~25k rows
- [ ] stability_metrics: ~25k rows
- [ ] value_metrics: ~25k rows
- [ ] positioning_metrics: ~25k rows

#### Safeguards
- [ ] No timeout errors
- [ ] No hanging processes
- [ ] All exceptions caught and logged
- [ ] CloudWatch logs available
- [ ] Cost tracking accurate

---

## PHASE 3 READINESS

### S3 Bulk COPY (10x speedup)
**Target Loaders:** 12 high-volume loaders
- loadbuyselldaily (250k rows, 5 min → 1 min)
- loadbuysellweekly (250k rows, 5 min → 1 min)
- loadbuysellmonthly (250k rows, 5 min → 1 min)
- loadetfpricedaily (250k rows, 5 min → 1 min)
- loadetfpriceweekly (100k rows, 2 min → 20 sec)
- loadstockpricedaily (1.2M rows, 25 min → 2.5 min)
- loadstockpriceweekly (250k rows, 5 min → 1 min)
- loadstockpricemonthly (250k rows, 5 min → 1 min)
- loaddailycompanydata (250k rows, 5 min → 1 min)
- loadtechnical_data_daily (250k rows, 5 min → 1 min)
- loadearningshistory (50k rows, 1 min → 10 sec)
- loadfactormetrics (already parallelized)

**Expected Impact:**
- Total time: 100+ min → 30 min (3.3x speedup)
- Cost: $6+ → $1 (6x cheaper)

### Lambda Parallelization (100x speedup)
**Target Loaders:** 8 API-intensive loaders
- loadecondata: 30 sec (was 5 min)
- loadearningshistory: 5 min (was 50 min)
- loadanalystsentiment: 2 min (was 30 min)
- loadanalystupgradedowngrade: 2 min (was 20 min)
- loadstocksentials: 3 min (was 30 min)
- loadsectormomentum: 30 sec (was 5 min)
- loadmarketsentiment: 2 min (was 20 min)
- loadfundamentals: 5 min (was 50 min)

**Expected Impact:**
- Total time: 200+ min → 20 min (10x speedup)
- Cost: $15+ → $0.01 (1500x cheaper)

---

## VALIDATION CHECKLIST (POST-PHASE2)

### Immediate (5 min after Phase 2 complete)
- [ ] Workflow status: SUCCESS
- [ ] All 3 loaders completed
- [ ] No failed jobs
- [ ] No timeout errors
- [ ] CloudWatch logs available

### RDS Validation (5 min)
```bash
psql -h rds-stocks.c2gujitq3h1b.us-east-1.rds.amazonaws.com \
     -U stocks -d stocks << 'SQL'
SELECT 
  'economic_data' as t, COUNT(*) FROM economic_data
UNION ALL SELECT 'stock_scores', COUNT(*) FROM stock_scores
UNION ALL SELECT 'quality_metrics', COUNT(*) FROM quality_metrics
UNION ALL SELECT 'growth_metrics', COUNT(*) FROM growth_metrics
UNION ALL SELECT 'momentum_metrics', COUNT(*) FROM momentum_metrics
UNION ALL SELECT 'stability_metrics', COUNT(*) FROM stability_metrics
UNION ALL SELECT 'value_metrics', COUNT(*) FROM value_metrics
UNION ALL SELECT 'positioning_metrics', COUNT(*) FROM positioning_metrics;
SQL
```

Expected output:
```
economic_data        | 85000
stock_scores         | 5000
quality_metrics      | 25000
growth_metrics       | 25000
momentum_metrics     | 25000
stability_metrics    | 25000
value_metrics        | 25000
positioning_metrics  | 25000
```

### Data Quality (5 min)
- [ ] Run validate_all_data.py
- [ ] Check for nulls (should be minimal)
- [ ] Verify date ranges
- [ ] Check symbol coverage
- [ ] Spot-check values

### Cost Validation (5 min)
- [ ] Check AWS billing dashboard
- [ ] Verify actual cost ~$0.50 (target)
- [ ] Compare to estimate
- [ ] Document cost savings vs original ($0.30)

### Performance Validation (5 min)
- [ ] Check execution time ~17 min
- [ ] Calculate rows/second (should be 235+)
- [ ] Compare to Phase 2 original (30 min)
- [ ] Document speedup: 1.76x

---

## DECISION GATES

### Gate 1: Phase 2 Validation Complete
- **Condition:** Phase 2 complete, 240k rows loaded, $0.50 cost, no errors
- **Action:** Proceed to Phase 3
- **Fallback:** Debug issues, re-run Phase 2

### Gate 2: Phase 3A Readiness
- **Condition:** S3 bulk copy tested on 1 loader, 10x speedup confirmed
- **Action:** Roll out to 12 loaders
- **Fallback:** Use batch inserts until S3 issue resolved

### Gate 3: Phase 3B Readiness
- **Condition:** Lambda function tested, parallelization works, 100x speedup confirmed
- **Action:** Deploy to 8 API loaders
- **Fallback:** Use ThreadPoolExecutor until Lambda issue resolved

---

## SUCCESS CRITERIA

### Phase 2 Success
✓ All 3 official loaders executed  
✓ 240k rows loaded  
✓ $0.50 cost (±10%)  
✓ No failures or timeouts  
✓ ~17 min execution time  
✓ Cost savings vs Phase 2 original: 37.5% ($0.30 saved)

### Phase 3A Success
✓ 10x speedup on bulk loaders  
✓ 3.3x overall speedup (100+ min → 30 min)  
✓ 6x cost savings ($6 → $1)  
✓ No data loss or corruption  
✓ Automated S3 cleanup

### Phase 3B Success
✓ 100x speedup on API loaders  
✓ 10x overall speedup (200+ min → 20 min)  
✓ 1500x cost savings ($15 → $0.01)  
✓ Lambda scaling to 1000+ concurrent  
✓ No API rate limiting issues

---

## MONITORING DASHBOARD

Real-time metrics:
- **GitHub Actions:** https://github.com/argie33/algo/actions
- **CloudWatch:** AWS Console → CloudWatch → Logs
- **RDS:** AWS Console → RDS → Databases → rds-stocks
- **Billing:** AWS Console → Billing Dashboard

---

**Status: PHASE 2 EXECUTING - VALIDATION READY**
