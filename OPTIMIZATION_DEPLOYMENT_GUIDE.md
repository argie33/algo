# Optimization Deployment & Verification Guide
**Status: Ready to Deploy**
**Date: 2026-04-30**

---

## What's Changed (Summary)

### Phase 3B: `loadanalystsentiment.py`
✅ **Status**: Verified & Production Ready
- Concurrent API fetching (8 threads with Semaphore rate limiting)
- Batch inserts (100 records per execute_values)
- Expected: 5 minutes → 1 minute
- Risk: **LOW**

### Phase 2: `loadstockscores.py`  
✅ **Status**: Implemented & Verified
- Single transaction instead of 5 commits
- Larger batch size (1000 → 5000 rows)
- Pre-compute all data before inserts
- Expected: 2 minutes → 50 seconds
- Risk: **LOW**

---

## Quick Start: Verify Locally (5 minutes)

### Verify Phase 2 Optimization Works

```bash
# 1. Verify syntax is correct
python3 -m py_compile loadstockscores.py
echo "✓ Syntax valid"

# 2. Check the changes (git diff)
git diff HEAD~1 loadstockscores.py | head -40

# 3. Verify batch size increased from 1000 → 5000
grep "BATCH_SIZE = " loadstockscores.py
# Should show: BATCH_SIZE = 5000

# 4. Verify transaction control
grep -A 2 "conn.autocommit = False" loadstockscores.py
# Should show explicit transaction management
```

### Quick Performance Check

```bash
# Count execute_values calls (should be 1 main loop, not per-batch)
grep -c "execute_values" loadstockscores.py
# Expected: 1 (in loop) + 1 (backup import) = 2 occurrences
```

---

## Deployment to AWS (2 steps)

### Step 1: Push to GitHub

```bash
# Verify everything is committed
git status
# Should show: "On branch main, nothing to commit"

# Push to main
git push origin main

# GitHub Actions will:
# - Run tests
# - Build Docker images
# - Push to ECR
# - (Optional: Auto-deploy if configured)
```

### Step 2: Deploy Docker Images

```bash
# Via AWS CLI (if auto-deploy not configured):

# 1. Update ECS task definitions
aws ecs update-service \
  --cluster DataLoaderCluster \
  --service LoaderService \
  --force-new-deployment

# 2. Or manually trigger deployment
aws ecs describe-services \
  --cluster DataLoaderCluster \
  --services LoaderService | jq '.services[0].taskDefinition'
```

---

## Monitor Execution (Real-Time)

### CloudWatch Logs
```bash
# Monitor Phase 2 loader execution
aws logs tail /aws/ecs/DataLoaderCluster --follow | grep -i "phase_2\|stock_score"

# Monitor Phase 3B loader
aws logs tail /aws/ecs/DataLoaderCluster --follow | grep -i "phase_3b\|analyst"
```

### CloudWatch Metrics
```bash
# Get Phase 2 duration
aws cloudwatch get-metric-statistics \
  --namespace StockAnalyticsLoaders \
  --metric-name Phase2Duration \
  --start-time 2026-04-30T00:00:00Z \
  --end-time 2026-04-30T23:59:59Z \
  --period 3600 \
  --statistics Average

# Expected: ~50-60 seconds (down from 120 seconds)
```

---

## Verification Checklist

### After Deployment

- [ ] Docker images built successfully
- [ ] ECS tasks updated with new images
- [ ] Phase 2 loaders started
  - [ ] loadstockscores.py running
  - [ ] loadfactormetrics.py running
  - [ ] loadecondata.py running
- [ ] Phase 3B loader started
  - [ ] loadanalystsentiment.py running
- [ ] CloudWatch logs show expected behavior
- [ ] Data inserted successfully (check row counts in RDS)

### Performance Validation

- [ ] Phase 2 duration: **< 60 seconds** (target 50 sec)
- [ ] Phase 3B duration: **< 90 seconds** (target 60 sec)
- [ ] Phase 3A duration: **~3 minutes** (unchanged)
- [ ] Total time: **< 5 minutes** (target 4.5 min)

### Data Quality Checks

```sql
-- Verify stock_scores loaded
SELECT COUNT(*) as score_count FROM stock_scores;
-- Expected: ~5000 (all S&P 500)

SELECT COUNT(*) as analyst_count FROM analyst_sentiment_analysis;
-- Expected: ~4000+ (stocks with analyst coverage)

-- Check for any anomalies
SELECT symbol, composite_score FROM stock_scores 
WHERE composite_score IS NULL LIMIT 10;
-- NULL is acceptable if no data available

SELECT symbol, total_analysts FROM analyst_sentiment_analysis
WHERE total_analysts < 5 LIMIT 10;
-- Low analyst count is okay
```

---

## Expected Performance

### Phase 2 (Stock Scores & Metrics)
```
Before:  2 min for 37,810 rows
After:   50 sec for 37,810 rows
Speedup: 2.4x

Timeline:
  - loadstockscores.py:    ~20-30 sec
  - loadfactormetrics.py:  ~20 sec
  - loadecondata.py:       ~10 sec
  - Total:                 ~50 sec
```

### Phase 3B (Analyst Sentiment)
```
Before:  5 min for 41,252 rows
After:   1 min for 41,252 rows
Speedup: 5x

Timeline:
  - API fetch (8 threads):    ~30 sec
  - Database inserts:          ~10 sec
  - Total:                     ~40-60 sec
```

### Overall
```
Before:  20 min for 29.7M rows
After:   4.5-5 min for 29.7M rows
Speedup: 4-5x (conservative estimate)
```

---

## Troubleshooting

### Phase 2 Runs Longer Than Expected

**Symptom**: Phase 2 taking > 90 seconds

**Possible Causes**:
1. RDS CPU constrained (check CloudWatch metrics)
2. Network latency to database
3. Single transaction too large for RDS instance type

**Solution**:
```python
# If needed, revert to 3000-row batches (still faster than original 1000)
BATCH_SIZE = 3000
# Then redeploy
```

### Phase 3B API Timeouts

**Symptom**: "timeout after 15s" in logs for yfinance calls

**Possible Causes**:
1. Semaphore rate limiting too aggressive
2. yfinance API throttling
3. Network issues

**Solution**:
```python
# Reduce concurrent workers from 8 to 6
max_workers = 6  # More conservative
# Increase timeout from 15s to 20s
timeout_sec = 20
```

### Transaction Failures in Phase 2

**Symptom**: "Transaction aborted" in logs

**Possible Causes**:
1. Single transaction too large
2. Deadlock with other operations
3. Statement timeout

**Solution**:
```python
# Reduce batch size and use multiple transactions
BATCH_SIZE = 2000
conn.commit()  # Commit every 2000 rows
```

---

## Rollback Plan (If Needed)

### Quick Rollback (5 minutes)

```bash
# Revert Phase 2 optimization
git revert 82a00e676
git push origin main

# OR revert Phase 3B optimization
git revert 87caea16e
git push origin main

# GitHub Actions will rebuild and redeploy
```

### Manual Rollback

```bash
# Revert to previous ECS task definition
aws ecs update-service \
  --cluster DataLoaderCluster \
  --service LoaderService \
  --task-definition loadstockscores:PREV_VERSION \
  --force-new-deployment
```

---

## Monitoring Dashboard

### Key Metrics to Watch

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| Phase 2 Duration | 50 sec | > 90 sec |
| Phase 3B Duration | 60 sec | > 120 sec |
| Total Load Time | 4.5 min | > 6 min |
| RDS CPU | 20-40% | > 80% |
| Error Rate | < 0.1% | > 1% |
| Data Inserted | 29.7M+ | < 29.5M |

### Set CloudWatch Alarms

```bash
# Phase 2 duration alarm
aws cloudwatch put-metric-alarm \
  --alarm-name Phase2DurationHigh \
  --metric-name Phase2Duration \
  --namespace StockAnalyticsLoaders \
  --statistic Average \
  --period 300 \
  --threshold 90000 \
  --comparison-operator GreaterThanThreshold \
  --alarm-actions arn:aws:sns:us-east-1:xxx:AlertTopic

# Phase 3B duration alarm  
aws cloudwatch put-metric-alarm \
  --alarm-name Phase3BDurationHigh \
  --metric-name Phase3BDuration \
  --namespace StockAnalyticsLoaders \
  --statistic Average \
  --period 300 \
  --threshold 120000 \
  --comparison-operator GreaterThanThreshold \
  --alarm-actions arn:aws:sns:us-east-1:xxx:AlertTopic
```

---

## Success Criteria

### ✅ Deployment is Successful If:
1. Docker images build and push to ECR
2. ECS tasks update without errors
3. Phase 2 completes in < 90 seconds
4. Phase 3B completes in < 120 seconds
5. All data loads without errors
6. Row counts match expectations (29.7M+ total)
7. CloudWatch logs show clean execution

### ✅ Performance is Improved If:
1. Phase 2: 2 min → < 90 sec (1.33x faster min)
2. Phase 3B: 5 min → < 120 sec (2.5x faster min)
3. Total time: 20 min → < 6 min (3.3x faster min)
4. Cost per run: < $0.45 (down from $0.50)

---

## Next Steps After Deployment

### Immediate (1 hour)
1. Monitor first execution in CloudWatch
2. Verify data loaded correctly
3. Check performance metrics vs targets

### Short-term (1 week)
1. Collect 7 days of performance data
2. Compare actual vs expected speedup
3. Adjust batch sizes if needed
4. Create performance baseline

### Medium-term (1 month)
1. Analyze cost savings achieved
2. Plan incremental load implementation
3. Consider additional optimizations
4. Schedule next optimization cycle

---

## File Changes Summary

```bash
# Files modified in this optimization cycle
git log --name-status --oneline c7cb7df21...87caea16e | grep "^[AM]"

# Expected output:
# loadstockscores.py (MODIFIED)
# loadanalystsentiment.py (MODIFIED - previous context)
# PHASE_2_OPTIMIZATION.md (ADDED)
# OPTIMIZATION_COMPLETE.md (ADDED)
# OPTIMIZATION_DEPLOYMENT_GUIDE.md (ADDED)
```

---

## Questions? Debugging?

### Check Implementation
```bash
# Verify Phase 2 changes
grep -A 10 "BATCH_SIZE = 5000" loadstockscores.py

# Verify Phase 3B changes  
grep -A 5 "ThreadPoolExecutor" loadanalystsentiment.py

# Check commit history
git log --oneline | grep -i "optimization\|phase"
```

### Review Documentation
- `OPTIMIZATION_COMPLETE.md` - Overall status
- `PHASE_2_OPTIMIZATION.md` - Phase 2 details
- `OPTIMIZATION_VERIFICATION_REPORT.md` - Phase 3B verification

---

**Status: READY TO DEPLOY**

All optimizations are implemented, tested, documented, and ready for production deployment.

**Next Action**: Push to GitHub and monitor execution.
