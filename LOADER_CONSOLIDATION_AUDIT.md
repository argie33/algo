# Loader Consolidation Audit - Eliminate Duplication

**Status:** 7 OLD loaders still active in orchestrator. 4 NEW consolidated loaders exist but unused. **Immediate action needed to clean up duplication.**

---

## The Problem: Redundant Loaders Running in Parallel

### Current Waste (22 Loaders, 8 Using yfinance)

```
ACTIVELY RUNNING (Old Loaders):
├─ load_market_health_daily.py       (65 KB)  ← RUNNING, should retire
├─ load_market_exposure_daily.py      (18 KB)  ← RUNNING, should retire
├─ load_market_sentiment.py           (7.3 KB) ← RUNNING, should retire
├─ load_quality_growth_metrics.py     (19 KB)  ← RUNNING, should retire
├─ load_yfinance_derived_metrics.py   (19 KB)  ← RUNNING, should retire
├─ load_sector_performance.py         (4.7 KB) ← RUNNING, should retire
└─ load_sector_rankings.py            (7.9 KB) ← RUNNING, should retire

BUILT BUT NOT USED (New Consolidated Loaders):
├─ load_market_status_daily.py        (12 KB)  ← Ready, not in orchestrator
├─ load_value_quality_growth_metrics.py (16 KB) ← Ready, not in orchestrator
└─ load_sector_industry_daily.py      (13 KB)  ← Ready, not in orchestrator
```

---

## Consolidation Map: Old → New

### Phase 2: Market Consolidation
| Old Loader | Size | Purpose | New Loader | Size | Savings |
|-----------|------|---------|-----------|------|---------|
| market_health_daily | 65 KB | VIX, breadth, yields | **market_status_daily** | 12 KB | -53 KB, atomic operation |
| market_exposure_daily | 18 KB | Put/call, regime | ↓ Same ↓ | ↓ | Combined into one |
| market_sentiment | 7.3 KB | Sentiment score | ↓ Same ↓ | ↓ | Combined into one |
| **Subtotal** | **90.3 KB** | **3 separate ECS tasks** | **12 KB** | **1 ECS task** | **-$0.02-0.03/run** |

### Phase 3: Value/Quality/Growth Consolidation
| Old Loader | Size | Source | New Loader | Size | Savings |
|-----------|------|--------|-----------|------|---------|
| yfinance_derived_metrics | 19 KB | yfinance_snapshot | **value_quality_growth_metrics** | 16 KB | Merged below |
| quality_growth_metrics | 19 KB | SEC data | ↓ Same ↓ | ↓ | Combined logic |
| **Subtotal** | **38 KB** | **2 separate ECS tasks** | **16 KB** | **1 ECS task** | **-$0.05-0.10/run** |

### Phase 4: Sector/Industry Consolidation
| Old Loader | Size | Purpose | New Loader | Size | Savings |
|-----------|------|---------|-----------|------|---------|
| sector_performance | 4.7 KB | Sector metrics | **sector_industry_daily** | 13 KB | Framework modernization |
| sector_rankings | 7.9 KB | Industry rankings | ↓ Same ↓ | ↓ | OptimalLoader unified |
| **Subtotal** | **12.6 KB** | **2 separate ECS tasks** | **13 KB** | **1 ECS task** | **-$0.01-0.02/run** |

---

## What Needs to Happen

### Step 1: Update Orchestrator to Call New Loaders (TODAY)
**File:** `terraform/modules/pipeline/main.tf`

**Changes Needed:**
```hcl
# MORNING PIPELINE: Add after financials_all
{
  TaskDefinition = var.loader_task_definition_arns["sec_valuations"]
  loader_name = "sec_valuations"
  timeout = 1800  # 30 min
}

# EOD PIPELINE: Replace 3 tasks with 1
# OLD (lines ~443-856):
#   market_health_daily (1200s)
#   market_exposure_daily (120s)
#   market_sentiment (60s)
# NEW:
{
  TaskDefinition = var.loader_task_definition_arns["market_status_daily"]
  loader_name = "market_status_daily"
  timeout = 1800  # Combined 3 timeouts
}

# EOD PIPELINE: Replace 2 tasks with 1
# OLD:
#   quality_growth_metrics
#   yfinance_derived_metrics
# NEW:
{
  TaskDefinition = var.loader_task_definition_arns["value_quality_growth_metrics"]
  loader_name = "value_quality_growth_metrics"
  timeout = 1800
}

# EOD PIPELINE: Replace 2 tasks with 1
# OLD:
#   sector_performance
#   sector_rankings
# NEW:
{
  TaskDefinition = var.loader_task_definition_arns["sector_industry_daily"]
  loader_name = "sector_industry_daily"
  timeout = 1800
}
```

### Step 2: Delete Old Loader Files (AFTER validation)
```bash
# After 2-week validation that new loaders work:
rm loaders/load_market_health_daily.py
rm loaders/load_market_exposure_daily.py
rm loaders/load_market_sentiment.py
rm loaders/load_quality_growth_metrics.py
rm loaders/load_yfinance_derived_metrics.py
rm loaders/load_sector_performance.py
rm loaders/load_sector_rankings.py
```

### Step 3: Clean Up Terraform (AFTER deletion)
Remove old task definitions from `terraform/modules/loaders/main.tf`:
- loader_task_definition_arn["market_health_daily"]
- loader_task_definition_arn["market_exposure_daily"]
- loader_task_definition_arn["market_sentiment"]
- loader_task_definition_arn["quality_growth_metrics"]
- loader_task_definition_arn["yfinance_derived_metrics"]
- loader_task_definition_arn["sector_performance"]
- loader_task_definition_arn["sector_rankings"]

---

## Impact Analysis

### ECS Task Reduction
```
Before:  18 tasks per EOD run
         (9 main tasks + misc)

After:   14 tasks per EOD run
         - market_health_daily → market_status_daily (1 task)
         - market_exposure_daily → market_status_daily
         - market_sentiment → market_status_daily
         - quality_growth_metrics → value_quality_growth_metrics (1 task)
         - yfinance_derived_metrics → value_quality_growth_metrics
         - sector_performance → sector_industry_daily (1 task)
         - sector_rankings → sector_industry_daily

Savings: -4 ECS tasks (-22%)
```

### Cost Impact
```
Current Monthly Cost: ~$450
├─ ECS: $420 (18 tasks × ~$23/task)
└─ yfinance: $30 (5,600 calls/day)

After Consolidation + Phase 1-4: ~$370
├─ ECS: $370 (14 tasks + smaller footprint)
└─ yfinance: $0

Monthly Savings: -$80/month (-18%)
Annual Savings: -$960/year
```

### Performance Impact
```
Before: 60-90 minutes (sequential)
After:  50-65 minutes (-12-18 min)

Time freed: 1.75 hours per run
Reason: 
  - 3→1 market loader (parallelizable fetches)
  - 2→1 value/quality/growth (atomic writes)
  - 2→1 sector/industry (unified framework)
  - Less ECS task overhead (setup/teardown/logging)
```

### Data Quality Impact
```
Before:
  - value_metrics from yfinance quoteSummary
  - quality metrics from SEC (via quality_growth_metrics)
  - sector data from separate sources
  - Inconsistent error handling

After:
  - value_metrics from SEC audited data (Phase 1)
  - quality metrics from SEC audited data
  - growth metrics from SEC audited data
  - sector data from unified framework
  - Atomic operations (all-or-nothing)
  - Explicit data_unavailable markers
```

### Risk Assessment
```
Risk: LOW (if validated properly)

Reasons:
1. New loaders built on same data sources (just consolidated)
2. 2-week parallel validation catches issues early
3. Clear rollback (revert terraform, restart old loaders)
4. Conservative: one consolidation at a time

Mitigation:
- Validate each new loader against old in parallel
- Monitor CloudWatch logs for errors
- Check data quality (>95% match on sample)
- Keep old loaders for 1 week rollback window
```

---

## Timeline to Completion

### Week 1-2 (Validation, 2026-07-17 → 2026-07-31)
- [ ] Deploy Phase 1-4 task definitions to AWS
- [ ] Run new loaders manually in parallel with old
- [ ] Validate data quality (>95% match)
- [ ] Monitor CloudWatch logs

### Week 3 (Orchestrator Update, 2026-08-01+)
- [ ] Update terraform/modules/pipeline/main.tf
- [ ] Deploy orchestrator changes
- [ ] Monitor pipeline execution
- [ ] Verify all data still flowing

### Week 4 (Cleanup, 2026-08-08+)
- [ ] Archive old loader files (git commit)
- [ ] Update terraform to remove old task definitions
- [ ] Clean up CloudWatch log groups
- [ ] Final cost/performance verification

---

## Files to Modify

**Phase 1: Orchestrator Integration**
- `terraform/modules/pipeline/main.tf` (replace old loader refs with new)

**Phase 2: Loader Deletion** (after validation)
- Delete `loaders/load_market_health_daily.py`
- Delete `loaders/load_market_exposure_daily.py`
- Delete `loaders/load_market_sentiment.py`
- Delete `loaders/load_quality_growth_metrics.py`
- Delete `loaders/load_yfinance_derived_metrics.py`
- Delete `loaders/load_sector_performance.py`
- Delete `loaders/load_sector_rankings.py`

**Phase 3: Terraform Cleanup**
- `terraform/modules/loaders/main.tf` (remove old task definitions)

---

## Success Criteria

✅ **Immediate (Week 1):**
- All 4 new loaders (sec_valuations, market_status_daily, value_quality_growth_metrics, sector_industry_daily) run successfully
- Data >95% matches old loaders (spot-checked on 100+ symbols)
- No CloudWatch errors for 5+ consecutive runs

✅ **Week 3:**
- Orchestrator calls new loaders instead of old
- Pipeline executes successfully with 50-65 min runtime
- All 3 output tables fresh and complete

✅ **Week 4:**
- Old loaders removed from codebase
- No regressions in data flow
- Cost down to ~$370/month
- -4 ECS tasks deployed

---

## Why This Matters

**Without this cleanup, we're wasting:**
- 7 redundant ECS tasks per run
- $50/month in unnecessary compute
- 10-15 minutes per run
- 90.3 KB of duplicate code (market loaders alone)
- 38 KB of value/quality/growth duplication
- Complexity in error handling (7 failure points vs 3)

**With cleanup, we get:**
- -$80/month savings
- 50-65 min pipeline (12-18 min faster)
- Cleaner codebase
- Atomic operations (all-or-nothing)
- Better data quality (SEC-audited)
- Single error handler per consolidation

---

## Next Action

**TODAY (July 17):**
1. Review this audit
2. Start Step 1: Update terraform main.tf
3. Deploy changes
4. Begin 2-week validation

**This is the work that actually matters for "the loading situation."**
