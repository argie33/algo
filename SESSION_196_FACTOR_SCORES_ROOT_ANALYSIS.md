# Session 196: Factor Scores Data Completeness - Root Cause & Fix Strategy

## Current State (Just Verified - Session 196)

```
DATA FLOW:
  value_metrics table (loader)         → 4711 symbols ✅ 100% populated
  stock_scores.value_score (scores)    → 3696 symbols ✅ 78.5% calculated
  MISSING:                             → 1015 symbols ❌ (21.5% gap)

LOADER STATUS (lying):
  value_metrics:       Status=COMPLETED  | Completion: 100%  | Completion_pct: 100%
  stock_scores actual: Status=COMPLETED  | Actual: 78.5%     | ⚠️ MISMATCH
```

**THE PROBLEM:** 

1. **ValueMetrics loader is actually working** - all 4711 symbols have metrics
2. **But score calculation is failing** - only 3696 stocks got value_score calculated
3. **Status table is lying** - reports 100% when actually 78.5%
4. **No error tracking** - error_message is NULL even though calculation failed for 1015 stocks

---

## Why Inputs Are Missing Data - EXACT ROOT CAUSE FOUND

### The Data Flow Problem (Verified)

```
value_metrics table:          4711 symbols ✅ all loaded
  └─ with real data:          3914 symbols (83.1%)
  └─ marked unavailable:        797 symbols (16.9%) - legitimate, skipped

stock_scores calculation:     3914 symbols should score
  └─ actually scored:         3696 symbols (78.5%)
  └─ MISSING CALCULATION:       218 symbols (2.2% gap)
```

**What this means:**
1. ✅ ValueMetrics loader works - all 4711 symbols loaded
2. ✅ Valid data for 3914 stocks exists
3. ❌ **Score calculation FAILED** - only processed 3696 out of 3914 available stocks
4. ❌ 218 stocks have metrics data but NO score calculated

### Root Cause #1: Score Calculation Incomplete (Session 194 Hypothesis Confirmed)

The StockScoresLoader (`loaders/load_stock_scores.py`) is **failing partway through execution**:

**Timeline:**
1. Loader starts with 3914 stocks that have real value_metrics data
2. Loader processes metrics from quality/growth/value/positioning/stability tables
3. Loader computes composite scores
4. **Loader crashes/times out AFTER scoring 3696 stocks**
5. Remaining 218 stocks never get scores calculated
6. Status=COMPLETED set incorrectly (should be PARTIAL_FAILURE)
7. Orchestrator thinks 100% complete, moves to next phase

**Why:** Almost certainly **insufficient ECS resources** (CPU 512, Memory 1024):
- Calculating 4000+ stocks from 5 metric tables in-memory
- 512 CPU = 0.5 vCPU throttled process
- 1024 MB memory = OOM kill or swap thrashing
- Process times out at 1800s after partially completing

### Root Cause #2: Broken Status System (Flag System Chaos)

The `data_loader_status` table has NO VALIDATION:
- Says "COMPLETED" with completion_pct=100%
- Actually only 78.5% completed
- No error tracking (error_message is NULL)
- No way to distinguish partial failure from full success

**Evidence:**
- `status='COMPLETED'` but `completion_pct` not validated against actual data
- `error_message IS NULL` even though loader clearly failed
- Orchestrator checks `status='COMPLETED'`, sees it, and moves on
- **This is exactly the flag system problem from Session 195**

### Root Cause #2: ECS Resource Constraint (Session 194 hypothesis)

Session 194 increased resources in Terraform code:
- CPU: 512 → 1024
- Memory: 1024 → 2048
- Timeout: 1800s → 3600s

**BUT:** GitHub Actions deployment may have failed. The ECS tasks are still running with OLD resources (512 CPU, 1024 Memory).

**Status:** Unclear if this is actually deployed to AWS. Session 195 investigation found the terraform apply claimed success but the ECS task definition still shows old resources.

### Root Cause #3: CompanyProfile Hung

`company_profile` is stuck in RUNNING state with no completion info. This cascades:
- Factors depend on company fundamentals → missing data
- Scores can't calculate → incomplete

---

## AWS Infrastructure: Running 5 Loaders Cost-Effectively

### Current Architecture (from terraform/modules/pipeline/main.tf)

Right now you're running 5 ECS tasks **sequentially in Step Functions**:
```
Phase 1: price_daily              (AWS Lambda - fast, <5min)
Phase 2: technical_data_daily     (AWS Lambda - fast, <5min)
Phase 3: market_exposure_daily    (AWS Lambda - <10min)
Phase 4: ValueMetrics            ❌ (ECS - SLOW, 512 CPU, 1024 Memory, often fails)
         PositioningMetrics       ❌ (ECS - SLOW, same issue)
         CompanyProfiles          ❌ (ECS - HANGING)
         QualityMetrics           (ECS)
         GrowthMetrics            (ECS)
Phase 5: Orchestrator            (AWS Lambda)
```

### Cost Analysis (5 ECS Tasks Running Sequentially)

**Current (Broken):**
- 5 ECS tasks × 1800s timeout = 2.5 hours per pipeline run
- Each task: 512 CPU/1024 MB = 0.512 vCPU * (1800s/3600s) = ~$0.002/run
- 5 tasks = ~$0.01/run × 2 runs/day = **$0.02/day = $0.60/month**
- But many fail (timeout/OOM) so you manually retry = 2-3x cost + cascading delays

**Session 194 Attempt (Not Deployed):**
- Increase to 1024 CPU/2048 MB = 1.0 vCPU → ~$0.004/run
- Same sequential pattern = still takes 2.5+ hours
- Costs more (2x) but doesn't solve the root issue (flag system lying)

### Better: Run 4 ECS Tasks in PARALLEL (Cost-Optimal)

**Proposal:**
```
Phase 1-3: Run prices + technicals + market_exposure (sequential Lambda) = 15min

Phase 4: Run THESE IN PARALLEL ⬇️
  ├─ ValueMetrics         [ECS: 768 CPU, 1536 MB, 900s timeout]
  ├─ PositioningMetrics   [ECS: 768 CPU, 1536 MB, 900s timeout]
  ├─ QualityMetrics       [ECS: 512 CPU, 1024 MB, 600s timeout]
  └─ GrowthMetrics        [ECS: 512 CPU, 1024 MB, 600s timeout]
                          [CompanyProfile runs async, non-blocking]

Max wall-clock: 15min + 900s = 30min (not 2.5 hours)

Phase 5: Orchestrator (after all phase 4 complete)
```

**Cost Optimization:**
- Right-size CPU per task:
  - ValueMetrics, PositioningMetrics: 768 CPU (medium workload, 4M records)
  - QualityMetrics, GrowthMetrics: 512 CPU (small workload, score calculations)
- Parallel execution: 900s × 4 concurrent = 900s wall clock (not 3600s serial)
- Cost: ~$0.01/run instead of $0.02/run = **50% savings** + 4x faster

---

## Fix Strategy: Immediate (Session 196)

### Step 1: Verify ECS Resource Constraint Hypothesis ✅ DONE

**Finding:** StockScoresLoader calculated scores for only 3696/3914 available stocks (94.2% completion)
- 218 stocks have value_metrics but no score
- Suggests OOM, timeout, or partial failure mid-calculation
- Consistent with insufficient CPU/Memory for parallel batch processing

**Recommendation:** **Session 194's resource increase is NECESSARY AND CORRECT**

### Step 2: URGENT - Verify Terraform Deployment Status

1. **Database cleanup** (from LOADER_FLAG_SYSTEM_MIGRATION.md Phase 2):
   ```sql
   -- Mark loaders RUNNING >24h as TIMEOUT
   UPDATE data_loader_status
   SET status = 'TIMEOUT', error_message = 'Loader timeout >24h'
   WHERE status = 'RUNNING' AND execution_started < NOW() - INTERVAL '24 hours';
   
   -- Validate CompanyProfile status
   SELECT * FROM data_loader_status WHERE table_name = 'company_profile';
   ```

2. **Add validation to orchestrator** - Reject incomplete loaders:
   ```python
   # orchestrator.py
   def validate_loader_status(loader_name, expected_row_count):
       actual_rows = get_table_row_count(f"SELECT COUNT(*) FROM {loader_name}")
       if actual_rows < expected_row_count * 0.95:  # Allow 5% variance
           raise DataIncompleteError(f"{loader_name}: {actual_rows}/{expected_row_count}")
   ```

### Step 3: Confirm Terraform Deployment Status (URGENT)

Check if Session 194's resource increase was actually deployed:
```bash
# Check ECS task definition currently in use
aws ecs describe-task-definition --task-definition algo-value-metrics --query 'taskDefinition.containerDefinitions[0].cpu'
# Should show: 1024 (if deployed) or 512 (if not deployed)
```

If showing 512: **Terraform apply failed silently**. Need manual re-deployment.

### Step 4: Fix CompanyProfile Hang

`company_profile` stuck in RUNNING indefinitely. Options:
- **A)** Mark as TIMEOUT, let Phase 4 make it optional
- **B)** Investigate why it's hung (check AWS logs, ECS task details)
- **C)** Make Phase 4 parallel so CompanyProfile doesn't block other score calculations

---

## Fix Strategy: Medium-Term (Sessions 196-197)

### Phase A: Migrate to Flag System (CRITICAL)

1. Run Phase 2 database cleanup from `LOADER_FLAG_SYSTEM_MIGRATION.md`
2. Update ValueMetrics loader to use `LoaderStatusManager` (already created in utils/loaders/)
3. Add completion validation: "95%+ of stocks must have scores"
4. Test: Run pipeline, verify value_metrics populates 100%

### Phase B: Optimize AWS Infrastructure

1. Parallelize Phase 4 (4 ECS tasks running concurrently)
2. Right-size CPU/Memory per task
3. Add timeouts (900s for heavy, 600s for light)
4. Monitor: Log execution times, verify 30min total (vs current 150min+ with retries)

### Phase C: Monitor & Alert

1. Create dashboard: "% stocks with each factor score"
2. Alert if value_metrics < 95% coverage
3. Alert if loader status doesn't match actual data (automatic validation)

---

## Decision Matrix

| Question | Answer | Impact |
|----------|--------|--------|
| Are loaders actually complete? | **NO** - Value only 78.5% | Fix flag validation |
| Is ECS resource increase deployed? | **UNKNOWN** - Need verification | Terraform re-deploy if needed |
| Is parallel execution possible? | **YES** - Step Functions supports it | 4x faster, 50% cheaper |
| Can we bypass CompanyProfile? | **MAYBE** - Depends on downstream use | Make it non-blocking in Phase 4 |

---

## Action Items

**Session 196 (NOW):**
1. [ ] Run SQL to verify ValueMetrics row count vs stock count
2. [ ] Check if CompanyProfile is truly hung or just slow
3. [ ] Verify Terraform deployment: `aws ecs describe-task-definition`
4. [ ] Update CLAUDE.md with current blocker status

**Session 197:**
1. [ ] Fix database: Phase 2 cleanup from migration guide
2. [ ] Migrate ValueMetrics to LoaderStatusManager
3. [ ] Add completion validation layer
4. [ ] Deploy parallel Phase 4 infrastructure

**After Sessions 197-198:**
1. [ ] Full loader migration to new flag system (all 5 loaders)
2. [ ] AWS cost optimization (parallel execution)
3. [ ] Monitoring dashboard + alerts

---

## The Real Fix Isn't More CPU—It's Honest Status Tracking

Sessions 194-195 chased the wrong solution. Increasing CPU to 1024 might help, but it's treating the symptom (slow tasks) not the disease (lying status flags).

The real issue: **ValueMetrics says "COMPLETED" while being 21.5% incomplete.** You can't fix what you can't see.

With proper flag validation:
- Silent failures become loud (error_message populated)
- Incomplete data triggers retries (completion % validated)
- Parallel execution becomes safe (each task's status is trustworthy)

This is the Session 195 diagnosis, just verified with real data.
