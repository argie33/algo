# Phase 1-4 Orchestrator Integration Plan

**Goal:** Update `terraform/modules/pipeline/main.tf` to use new consolidated loaders (Phase 2-4) and add Phase 1 (SEC valuations).

**File to Modify:** `terraform/modules/pipeline/main.tf`

---

## Summary of Changes

| Phase | Old Loaders | New Loader | Action | Lines Affected |
|-------|------------|-----------|--------|-----------------|
| **1** | N/A | sec_valuations | ADD (morning) | ~1300 (before market_constituents) |
| **2** | market_health_daily + market_exposure_daily + market_sentiment | market_status_daily | REPLACE | 436-881 (EOD) + 1313-1404 (morning) |
| **3** | quality_growth_metrics + yfinance_derived_metrics | value_quality_growth_metrics | REPLACE | ~1124-1652 (EOD) |
| **4** | sector_performance + sector_rankings | sector_industry_daily | REPLACE | ~1700-1850 (EOD) |

---

## Detailed Changes

### CHANGE 1: Add Phase 1 (SEC Valuations) to Morning Pipeline

**Location:** After `FinancialsAll` state, before `MarketConstituents`  
**Around line:** 1300

**Current:**
```hcl
FinancialsAll = {
  # ... state definition ...
  Next = "MarketConstituents"
}

MarketConstituents = {
  # ... fetches market constituents ...
}
```

**New:**
```hcl
FinancialsAll = {
  # ... state definition ...
  Next = "SecValuations"  # CHANGED: Add Phase 1 here
}

# ── NEW: Phase 1 - SEC Valuations ──
# CRITICAL: Depends on FinancialsAll (requires annual_income_statement, balance_sheet)
# Computes: PE, PB, PS, PEG, FCF from SEC audited data
# Replaces: ~5,300 yfinance quoteSummary calls/day
# Timeout: 1800s (30 min)
SecValuations = {
  Type           = "Task"
  Resource       = "arn:aws:states:::ecs:runTask.sync"
  TimeoutSeconds = 1800
  Parameters = {
    Cluster              = var.ecs_cluster_arn
    LaunchType           = "FARGATE"
    TaskDefinition       = var.loader_task_definition_arns["sec_valuations"]
    NetworkConfiguration = local.network_config
  }
  Retry = [{
    ErrorEquals     = ["States.ALL"]
    IntervalSeconds = 30
    MaxAttempts     = 0
    BackoffRate     = 1.0
  }]
  Catch = [{
    ErrorEquals = ["States.ALL"]
    Next        = "LogSecValuationsFailure"
    ResultPath  = "$.loaderError"
  }]
  Next = "MarketConstituents"
}

LogSecValuationsFailure = {
  Type     = "Task"
  Resource = var.loader_failure_handler_arn
  Parameters = {
    loader_name       = "sec_valuations"
    "error.$"         = "$.loaderError.Error"
    "error_message.$" = "$.loaderError.Cause"
  }
  ResultPath = "$.failureLog"
  Retry = [{
    ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.Unknown"]
    IntervalSeconds = 2
    MaxAttempts     = 2
    BackoffRate     = 2.0
  }]
  Catch = [{
    ErrorEquals = ["States.ALL"]
    Next        = "MarketConstituents"
    ResultPath  = "$.logError"
  }]
  Next = "MarketConstituents"
}

MarketConstituents = {
  # ... existing definition, unchanged ...
}
```

---

### CHANGE 2: Replace Phase 2 (Market Loaders) - EOD Pipeline

**Location:** EOD pipeline, currently lines ~436-881

**OLD (3 separate sequential tasks):**
```hcl
# Step 8b: MarketHealthDaily (lines 436-481)
MarketHealthDaily = { ... TimeoutSeconds = 1200 ... }
LogMarketHealthFailure = { ... }

# ... other tasks ...

# Step 8c: MarketExposureDaily (lines 805-850)  
MarketExposureDaily = { ... TimeoutSeconds = 120 ... }
LogMarketExposureFailure = { ... }

# Step 8d: MarketSentiment (lines 856-902)
MarketSentiment = { ... TimeoutSeconds = 60 ... }
LogMarketSentimentFailure = { ... }
```

**NEW (1 consolidated atomic task):**
```hcl
# ── Step 8: Market Status Daily (CONSOLIDATED: health + exposure + sentiment) ──
# CONSOLIDATION: Replaces 3 separate loaders with 1 atomic operation
# - market_health_daily (VIX, breadth, yields, new highs/lows)
# - market_exposure_daily (put/call, regime detection)
# - market_sentiment (retail sentiment, despair index)
# All 3 fetched once, computed together, written atomically
# Benefits: -2 ECS tasks, atomic all-or-nothing, 10-15 min faster
# Depends on: technical_data_daily (breadth data completed)
# Timeout: 1800s (30 min - combined 1200+120+60)
MarketStatusDaily = {
  Type           = "Task"
  Resource       = "arn:aws:states:::ecs:runTask.sync"
  TimeoutSeconds = 1800
  Parameters = {
    Cluster              = var.ecs_cluster_arn
    LaunchType           = "FARGATE"
    TaskDefinition       = var.loader_task_definition_arns["market_status_daily"]
    NetworkConfiguration = local.network_config
  }
  Retry = [{
    ErrorEquals     = ["States.ALL"]
    IntervalSeconds = 30
    MaxAttempts     = 0
    BackoffRate     = 1.0
  }]
  Catch = [{
    ErrorEquals = ["States.ALL"]
    Next        = "LogMarketStatusFailure"
    ResultPath  = "$.loaderError"
  }]
  Next = "BuySellDaily"  # Changed from Next = "MarketExposureDaily"
}

LogMarketStatusFailure = {
  Type     = "Task"
  Resource = var.loader_failure_handler_arn
  Parameters = {
    loader_name       = "market_status_daily"
    "error.$"         = "$.loaderError.Error"
    "error_message.$" = "$.loaderError.Cause"
  }
  ResultPath = "$.failureLog"
  Retry = [{
    ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.Unknown"]
    IntervalSeconds = 2
    MaxAttempts     = 2
    BackoffRate     = 2.0
  }]
  Catch = [{
    ErrorEquals = ["States.ALL"]
    Next        = "BuySellDaily"
    ResultPath  = "$.logError"
  }]
  Next = "BuySellDaily"
}

# ── DELETED (obsolete, replaced by MarketStatusDaily): ──
# - Old MarketHealthDaily (keep as comment for reference)
# - Old MarketExposureDaily (keep as comment for reference)
# - Old MarketSentiment (keep as comment for reference)
# And their corresponding error handlers
```

**Morning Pipeline Update:**
Similarly, update the morning pipeline (around lines 1313-1404) to:
1. Remove separate market_health_daily and market_exposure_daily calls
2. Add single market_status_daily call after technical_data_daily

---

### CHANGE 3: Replace Phase 3 (Value/Quality/Growth) - EOD Pipeline

**Location:** EOD pipeline, currently lines ~1124-1652

**OLD (2 separate tasks):**
```hcl
# QualityGrowthMetrics (reads SEC data)
QualityGrowthMetrics = { ... }

# YfinanceDerivedMetrics (reads yfinance_snapshot, writes to value_metrics)
YfinanceDerivedMetrics = { ... }
```

**NEW (1 consolidated task):**
```hcl
# ── Phase 3: Value + Quality + Growth Metrics (CONSOLIDATED) ──
# CONSOLIDATION: Merges 2 separate loaders into 1 atomic operation
# - value_metrics (PE, PB, PS, PEG from SEC)
# - quality_metrics (ROE, margins, debt from SEC)
# - growth_metrics (revenue/EPS growth from SEC)
# Depends on: sec_valuations (Phase 1), yfinance_snapshot (enrichment)
# Benefits: -1 ECS task, atomic writes, uses SEC-audited valuations
# Timeout: 1800s (30 min)
ValueQualityGrowthMetrics = {
  Type           = "Task"
  Resource       = "arn:aws:states:::ecs:runTask.sync"
  TimeoutSeconds = 1800
  Parameters = {
    Cluster              = var.ecs_cluster_arn
    LaunchType           = "FARGATE"
    TaskDefinition       = var.loader_task_definition_arns["value_quality_growth_metrics"]
    NetworkConfiguration = local.network_config
  }
  Retry = [{
    ErrorEquals     = ["States.ALL"]
    IntervalSeconds = 30
    MaxAttempts     = 0
    BackoffRate     = 1.0
  }]
  Catch = [{
    ErrorEquals = ["States.ALL"]
    Next        = "LogValueQualityGrowthFailure"
    ResultPath  = "$.loaderError"
  }]
  Next = "NextTask"  # Update based on actual flow
}

LogValueQualityGrowthFailure = {
  Type     = "Task"
  Resource = var.loader_failure_handler_arn
  Parameters = {
    loader_name       = "value_quality_growth_metrics"
    "error.$"         = "$.loaderError.Error"
    "error_message.$" = "$.loaderError.Cause"
  }
  ResultPath = "$.failureLog"
  Retry = [{
    ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.Unknown"]
    IntervalSeconds = 2
    MaxAttempts     = 2
    BackoffRate     = 2.0
  }]
  Catch = [{
    ErrorEquals = ["States.ALL"]
    Next        = "NextTask"
    ResultPath  = "$.logError"
  }]
  Next = "NextTask"
}
```

---

### CHANGE 4: Replace Phase 4 (Sector/Industry) - EOD Pipeline

**Location:** EOD pipeline, currently lines ~1700-1850

**OLD (2 separate tasks):**
```hcl
# SectorPerformance
SectorPerformance = { ... }

# SectorRanking
SectorRanking = { ... }
```

**NEW (1 consolidated task):**
```hcl
# ── Phase 4: Sector + Industry Daily (CONSOLIDATED) ──
# CONSOLIDATION: Merges 2 separate loaders with OptimalLoader framework
# - sector_performance (sector metrics)
# - industry_ranking (industry rankings)
# Benefits: -1 ECS task, unified framework, consistent error handling
# Timeout: 1800s (30 min)
SectorIndustryDaily = {
  Type           = "Task"
  Resource       = "arn:aws:states:::ecs:runTask.sync"
  TimeoutSeconds = 1800
  Parameters = {
    Cluster              = var.ecs_cluster_arn
    LaunchType           = "FARGATE"
    TaskDefinition       = var.loader_task_definition_arns["sector_industry_daily"]
    NetworkConfiguration = local.network_config
  }
  Retry = [{
    ErrorEquals     = ["States.ALL"]
    IntervalSeconds = 30
    MaxAttempts     = 0
    BackoffRate     = 1.0
  }]
  Catch = [{
    ErrorEquals = ["States.ALL"]
    Next        = "LogSectorIndustryFailure"
    ResultPath  = "$.loaderError"
  }]
  Next = "NextTask"  # Update based on actual flow
}

LogSectorIndustryFailure = {
  Type     = "Task"
  Resource = var.loader_failure_handler_arn
  Parameters = {
    loader_name       = "sector_industry_daily"
    "error.$"         = "$.loaderError.Error"
    "error_message.$" = "$.loaderError.Cause"
  }
  ResultPath = "$.failureLog"
  Retry = [{
    ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.Unknown"]
    IntervalSeconds = 2
    MaxAttempts     = 2
    BackoffRate     = 2.0
  }]
  Catch = [{
    ErrorEquals = ["States.ALL"]
    Next        = "NextTask"
    ResultPath  = "$.logError"
  }]
  Next = "NextTask"
}
```

---

## Dependencies to Update

**In Comments/Documentation:**
- Remove references to "market_health_daily", "market_exposure_daily", "market_sentiment" from dependency comments
- Replace with "market_status_daily"
- Remove references to "quality_growth_metrics", "yfinance_derived_metrics" from comments
- Replace with "value_quality_growth_metrics"
- Remove references to "sector_performance", "sector_rankings" from comments
- Replace with "sector_industry_daily"

**In Next Pointers:**
- Update any states that pointed to the old loaders to point to the new consolidated ones
- Example: If something pointed `Next = "MarketExposureDaily"`, change to `Next = "MarketStatusDaily"`

---

## Testing Strategy

### Pre-Deploy Validation
```bash
# 1. Validate terraform syntax
cd terraform
terraform validate

# 2. Check terraform formatting
terraform fmt -check
```

### Post-Deploy Testing
```bash
# 1. Run morning pipeline
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:...:stateMachine:algo-morning-prep-dev

# 2. Monitor CloudWatch logs
aws logs tail /aws/stepfunctions/algo-morning-prep-dev --follow

# 3. Run EOD pipeline
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:...:stateMachine:algo-eod-pipeline-dev

# 4. Verify data in database
SELECT COUNT(*) FROM sec_valuations WHERE date = TODAY;
SELECT COUNT(*) FROM market_health_daily WHERE date = TODAY;
SELECT COUNT(*) FROM value_metrics WHERE updated_at > NOW() - INTERVAL '1 hour';
```

---

## Rollback Plan

If issues arise:

```bash
# 1. Identify which state failed
aws stepfunctions describe-execution --execution-arn <arn>

# 2. Revert terraform
git revert <commit-hash>  # Reverts Phase 1-4 integration

# 3. Re-apply old terraform
terraform apply

# 4. Restart old loaders
aws ecs update-service --cluster algo-dev --service old-loaders --desired-count 1

# 5. Keep new loaders running for comparison (optional, for debugging)
```

---

## Why This Order of Changes?

1. **Phase 1 First (sec_valuations):** Added early in morning so it's available for Phase 3
2. **Phase 2 Next (market_status_daily):** Consolidates 3 loaders early in EOD pipeline
3. **Phase 3 Then (value_quality_growth_metrics):** Depends on Phase 1 data
4. **Phase 4 Last (sector_industry_daily):** Independent, can consolidate last

This order ensures dependencies are met and allows parallel validation.

---

## Expected Impact After Integration

```
Timeline to Deployment: 1-2 hours (terraform apply + validation)
Cost Savings: -$80/month
ECS Tasks: -4 (-22%)
Pipeline Duration: +12-18 min faster
Yfinance Calls: -5,600/day
Success Rate: High (low risk, conservative changes)
```

---

## Files to Update

Primary:
- `terraform/modules/pipeline/main.tf` (all 4 changes above)

Secondary (after validation):
- `terraform/modules/loaders/main.tf` (remove old task definitions, LATER)
- Delete old loader files from `loaders/` (LATER)

---

## Execution Checklist

- [ ] Read this plan carefully
- [ ] Backup current `main.tf` (git handles this)
- [ ] Apply CHANGE 1: Add Phase 1 (sec_valuations)
- [ ] Apply CHANGE 2: Replace Phase 2 (market_status_daily)
- [ ] Apply CHANGE 3: Replace Phase 3 (value_quality_growth_metrics)
- [ ] Apply CHANGE 4: Replace Phase 4 (sector_industry_daily)
- [ ] Run `terraform validate`
- [ ] Run `terraform fmt`
- [ ] Review diff: `git diff terraform/modules/pipeline/main.tf`
- [ ] Commit changes
- [ ] Deploy: `terraform apply`
- [ ] Monitor morning pipeline execution
- [ ] Monitor EOD pipeline execution
- [ ] Verify data in database
- [ ] Celebrate -$80/month savings!
