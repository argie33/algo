# Wave 2 Optimizations - Queued for Implementation

**Status:** Ready to deploy (after Wave 1 verification)  
**Priority:** MEDIUM  
**Expected Impact:** 15-30% additional performance improvement

---

## What Wave 2 Addresses

### 1. Request Deduplication (MEDIUM Priority)
**Problem:** Some loaders make redundant API calls for the same symbol  
**Solution:** Add simple request cache (symbol → last_fetch_time)  
**Expected Gain:** 20-30% fewer API calls  
**Files to modify:**
- loadpricedaily.py (symbol cache)
- loadetfpricedaily.py (symbol cache)
- loaddailycompanydata.py (dedup requests)

**Implementation:**
```python
# At start of load_table
request_cache = {}
last_fetch = {}

# Before fetch_symbol_data
if symbol in last_fetch and (time.time() - last_fetch[symbol]) < 3600:
    continue  # Skip if fetched in last hour
```

---

### 2. Connection Pooling (HIGH Priority)
**Problem:** Each loader creates new DB connection; reopens for every batch  
**Solution:** Reuse connection across all operations within single run  
**Expected Gain:** 10-15% faster inserts (fewer connection setup overhead)  
**Current Issue:** DatabaseHelper creates fresh connection per insert() call

**Implementation:**
```python
# In DatabaseHelper.__init__, add:
self.connection_pool = None

# New method:
def get_pooled_connection(self):
    if not self.conn:
        self.connect()
    return self.conn
```

---

### 3. Memory Optimization (MEDIUM Priority)
**Problem:** Loaders hold entire datasets in memory; no garbage collection  
**Solution:** 
- Stream process data (fetch 500, insert 500, release)
- Add gc.collect() after each batch commit
- Reduce list copies in DatabaseHelper

**Expected Gain:** 5-10% lower memory usage (prevent OOM on large runs)  
**Current:** Some loaders consuming 500MB+ for price data

---

### 4. Parallel Batch Commit (LOW Priority - Wave 3)
**Problem:** Batches committed sequentially; could parallelize  
**Solution:** ThreadPoolExecutor for batch commits (max 3 threads)  
**Expected Gain:** 5-10% faster for large datasets  
**Risk:** Must avoid connection pool contention

---

## Implementation Order

### Stage 1 (This Week)
1. ✓ Wave 1 deployed & verified (current)
2. → Request deduplication (1-2 hour implementation)
3. → Connection pooling (2-3 hour implementation)
4. → Memory optimization (1-2 hour implementation)

### Stage 2 (Next Week)
5. → Parallel batch commit
6. → S3 bulk staging for high-volume loaders (1M+ rows)
7. → Spot instance enablement (-70% cost)

---

## Success Metrics

| Metric | Wave 1 Target | Wave 2 Target | Current → Target |
|--------|---------------|---------------|------------------|
| Speed | 10 min | 8.5 min | 10min → 8.5min (15% faster) |
| Cost | $133/mo | $110/mo | $133 → $110 (17% cheaper) |
| Memory | Stable | 20% lower | 500MB → 400MB per loader |
| Error Rate | <1% | <0.5% | <1% → <0.5% (half) |

---

## Deployment Plan

### When to Deploy
- After Wave 1 completion confirmed in logs (expect by 2026-05-02 06:00 UTC)
- After monitor shows timeout protection working

### How to Deploy
1. Implement all 3 changes in parallel
2. Test locally with 10 symbols (fast)
3. Push to GitHub → Auto-triggers rebuild
4. Monitor ECS for new images
5. Log verify improvements

### Rollback
If any Wave 2 optimization causes issues:
```bash
git revert <wave-2-commit>
git push origin main
# Auto-redeploys previous version
```

---

## Code Checklist

- [ ] Request deduplication (3 loaders)
- [ ] Connection pooling (DatabaseHelper)
- [ ] Memory gc.collect() (4 main loaders)
- [ ] Local test (10 symbols, verify speed + mem)
- [ ] Push to GitHub
- [ ] Monitor ECS deployment
- [ ] Verify logs show improvements
- [ ] Document results in BEFORE_AFTER_METRICS.md

---

## Next: Wave 3 Preview

After Wave 2 verified:
- S3 bulk COPY (10x faster for big datasets)
- Lambda parallelization (100x faster for API calls)
- Spot instances (-70% cost)
- RDS Proxy (connection pooling at infrastructure level)

---

## Never Settle

Wave 2 isn't the end. After verified:
- Monitor finds next bottleneck
- Check for anomalies
- Profile for hotspots
- Always find next improvement
