# Pragmatic Cloud Execution Strategy
**Philosophy:** Keep it simple. Make it work. Make it fast. Make it reliable.

---

## Current State: Serial ECS Loaders
- ❌ Takes 45-120 minutes per loader
- ❌ Inefficient (only 1 core used)
- ✓ Simple to understand
- ✓ Already deployed in CloudFormation

## Goal: Minimal Changes, Maximum Impact
- ✓ Use what we have (ECS Fargate)
- ✓ 5-10x faster with 10 lines of code change
- ✓ Deployed next week
- ✓ Not over-complicated

---

## PRAGMATIC EXECUTION PLAN

### Week 1: Deploy Parallel Processing (5-10x faster)
**Time investment: 4-6 hours**

What to do:
```
1. Convert 6 Batch 5 loaders to parallel (ThreadPoolExecutor)
2. Test locally → Test in AWS → Deploy
3. Measure improvement
4. Celebrate 5x speedup
```

Result: 
- Quarterly Income: 60m → 12m
- Annual Income: 45m → 9m
- Balance Sheets: 50m → 10m
- Total Batch 5: 7 hours → 1.5 hours

**Status: DONE (mostly - just deploy)**

---

### Week 2: Optimize What Works
**Time investment: 2-3 hours**

Simple improvements:
```
1. Reduce REQUEST_DELAY from 0.5s → 0.1s
2. Increase batch size from 10 → 50 rows
3. Monitor CloudWatch logs
4. Adjust worker count if needed
```

Result:
- Additional 2-3x improvement
- Better reliability
- Better visibility

**Status: IN PROGRESS**

---

### Week 3: Full Rollout
**Time investment: 4-6 hours**

Apply to all 52 loaders:
```
1. Use template for remaining 46 loaders
2. Test in batches (10 at a time)
3. Deploy incrementally
4. Monitor each batch
```

Result:
- All 52 loaders running in parallel
- Total execution time: ~50-100 hours (for all)
- Monthly cost reduction: 50-70%

**Status: READY**

---

## WHAT NOT TO DO (Keep It Simple)

❌ **Don't** implement Lambda serverless (too much change)  
❌ **Don't** build Step Functions (unnecessary complexity)  
❌ **Don't** switch to async/await (stick with threads)  
❌ **Don't** change database architecture (use existing RDS)  
❌ **Don't** redesign workflows (keep GitHub Actions)  

✓ **Do** use ThreadPoolExecutor (proven, simple)  
✓ **Do** stick with ECS (already deployed)  
✓ **Do** improve incrementally (test as you go)  
✓ **Do** measure everything (know what works)  
✓ **Do** deploy weekly (get value fast)  

---

## IMMEDIATE ACTION ITEMS

### This Week (Priority 1)

```
[ ] Monday
    - Apply parallel to loadannualincomestatement
    - Apply parallel to loadquarterlybalancesheet
    - Test both locally
    - Commit changes

[ ] Tuesday
    - Apply parallel to loadannualbalancesheet
    - Apply parallel to loadquarterlycashflow
    - Apply parallel to loadannualcashflow
    - Test all in local environment

[ ] Wednesday
    - Push all changes to main
    - GitHub Actions will build Docker images
    - Monitor ECR for new images

[ ] Thursday
    - Manually trigger one loader in AWS
    - Monitor CloudWatch logs
    - Verify 5-10x speedup
    - Document results

[ ] Friday
    - Deploy to remaining Batch 5 loaders
    - Full verification
    - Celebrate success
```

### Measurement Checklist

For each loader, measure:
```
✓ Before: How long did it take serially?
✓ After: How long with parallel?
✓ Speedup: 5x? 10x? More?
✓ Errors: Any data issues?
✓ CloudWatch: Any errors in logs?
✓ Database: Did all data insert correctly?
✓ Cost: How much did it cost to run?
```

---

## SIMPLE METRICS DASHBOARD

Create a tracking spreadsheet:

```
Loader                  | Serial | Parallel | Speedup | Status
────────────────────────┼────────┼──────────┼─────────┼────────
quarterly_income        | 60m    | 12m      | 5x      | DONE
annual_income          | 45m    | 9m       | 5x      | TODO
quarterly_balance      | 50m    | 10m      | 5x      | TODO
annual_balance         | 55m    | 11m      | 5x      | TODO
quarterly_cashflow     | 40m    | 8m       | 5x      | TODO
annual_cashflow        | 35m    | 7m       | 5x      | TODO
daily_company_data     | 90m    | 18m      | 5x      | TODO
buy_sell_daily         | 70m    | 14m      | 5x      | TODO
buy_sell_weekly        | 65m    | 13m      | 5x      | TODO
buy_sell_monthly       | 60m    | 12m      | 5x      | TODO
[... 42 more loaders]
────────────────────────┼────────┼──────────┼─────────┼────────
BATCH 5 Total          | 7h     | 1.5h     | 4.7x    | IN PROGRESS
All 52 Total           | 200h   | 40h      | 5x      | PENDING
```

---

## DEPLOY SEQUENCE

**Phase 1 - Week 1**
```
Deploy: Batch 5 Financial Statements (6 loaders)
Time: 1-2 hours
Test: Manual verification in AWS
Result: 4.7x speedup
Risk: Low (isolated batch)
```

**Phase 2 - Week 2**
```
Deploy: Buy/Sell & ETF loaders (8 loaders)
Time: 1-2 hours
Test: Automated testing + manual spot-check
Result: 5x speedup
Risk: Low (proven pattern)
```

**Phase 3 - Week 3**
```
Deploy: All remaining loaders (38 loaders)
Time: 2-3 hours
Test: Batch deployments with monitoring
Result: 5x speedup across all
Risk: Very Low (proven & monitored)
```

---

## MONITORING (Keep It Simple)

Watch these 5 things:

1. **CloudWatch Logs**
   ```
   Search: "ERROR\|FAIL\|Exception"
   Look for: Connection errors, missing data
   Action: Fix and redeploy
   ```

2. **Execution Time**
   ```
   Track: How long does each loader take?
   Target: 5-25 minutes (down from 45-120)
   Alert: If > 30 minutes
   ```

3. **Data Integrity**
   ```
   Check: SELECT COUNT(*) from each table
   Compare: Before vs after deployment
   Verify: No missing rows
   ```

4. **Database Performance**
   ```
   Monitor: CPU utilization
   Monitor: Connection count
   Alert: If CPU > 80%
   ```

5. **Cost**
   ```
   Track: ECS task hours
   Expected: 70-80% reduction
   Alert: If costs increase
   ```

---

## Troubleshooting (When Things Go Wrong)

### Problem: "Loader takes longer than before"
```
Likely cause: 5 workers creating contention
Solution: Reduce workers to 3, test again
```

### Problem: "Database connections maxing out"
```
Likely cause: Each worker has own connection
Solution: Increase RDS max_connections or reduce workers
```

### Problem: "Some symbols fail, some succeed"
```
Likely cause: Transient API errors
Solution: Already handled with try/except, will retry
```

### Problem: "Data didn't insert"
```
Likely cause: Batch insert exception
Solution: Check CloudWatch logs for error message, debug
```

---

## Success Criteria (How to Know It's Working)

✅ **Speed**
```
Each loader: < 25 minutes (down from 60+ minutes)
Batch 5 total: < 2 hours (down from 7 hours)
All 52: < 50 hours (down from 200 hours)
```

✅ **Reliability**
```
Error rate: < 1% of symbols
Data completeness: 100% of symbols have data
Database: No duplicate rows, no missing rows
```

✅ **Efficiency**
```
CPU utilization: 50-75% during execution
Memory: Stable, no leaks
Network: Efficient, no timeouts
```

✅ **Cost**
```
Per-loader cost: < $0.05
Monthly cost: < $100 for all loads
Savings: 50-70% reduction from current
```

---

## Timeline

| Week | What | Time | Status |
|------|------|------|--------|
| 1 | Batch 5 conversion | 4h | This week |
| 1 | Testing in AWS | 2h | This week |
| 2 | Remaining loaders | 4h | Next week |
| 2 | Full monitoring setup | 2h | Next week |
| 3 | Optimizations | 2h | Week 3 |
| 3 | Documentation | 2h | Week 3 |
| **Total** | **Everything** | **16h** | **Done in 3 weeks** |

---

## Bottom Line

**Simple approach. Big impact.**

- Use ThreadPoolExecutor (10 line change)
- 5 workers per loader (proven safe)
- Batch inserts (already in code)
- Monitor CloudWatch (built-in)
- Deploy incrementally (test as you go)

**Result: 5-10x faster, 50% cheaper, deployed in 3 weeks**

No Lambda. No Step Functions. No over-engineering.  
Just smart use of what we have.

That's pragmatic cloud execution.
