# Data Loader Scheduling Checklist

**Problem:** Data loader for May 9 didn't run. System shows 0 symbols loaded today.

**Root Cause:** ECS/Lambda scheduler not triggering the load job daily.

**Critical Path:** 
- EventBridge Scheduler must trigger ECS task or Lambda daily
- Current: Manual or no schedule
- Required: Daily at 4:00am ET (before market opens at 9:30am)

## Verification Checklist

### Check EventBridge/Scheduler Config
```bash
# Verify EventBridge rule exists and is enabled
aws events list-rules --name-prefix "*loader*" --region us-east-1

# Check schedule details
aws events describe-rule --name algo-price-loader --region us-east-1

# Check associated targets
aws events list-targets-by-rule --rule algo-price-loader --region us-east-1
```

### Check ECS Task
```bash
# Verify ECS task definition for loaders
aws ecs describe-task-definition \
  --task-definition stocks-loaders:1 \
  --region us-east-1

# Check if task is registered
aws ecs list-task-definitions \
  --family-prefix stocks-loaders \
  --region us-east-1
```

### Required Configuration

**EventBridge Rule:**
- Name: `algo-price-loader` (or similar)
- Schedule: `cron(0 4 * * MON-FRI *)` — 4:00am UTC Mon-Fri (= 11pm ET previous day, 4am ET day-of)
- Target: ECS task `stocks-data-cluster` + `stocks-loaders:1`
- Retry: 2x with 5min backoff

**ECS Task Definition:**
- Container: `stocks-loaders`
- Command override: `["python3", "loadpricedaily.py", "--parallelism", "4"]`
- Memory: 2048 MB min
- Timeout: 1800 seconds (30 min)
- Environment: `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`

**Alternative (Lambda):**
- Function: `price-data-loader`
- Handler: `lambda_loader_wrapper.handler`
- Event: EventBridge rule (same schedule)
- Timeout: 300 seconds
- Memory: 1024 MB

## After Scheduling is Fixed

1. **Verify it runs:**
   ```bash
   # Monitor logs for next scheduled run
   aws logs tail /ecs/stocks-data-cluster --follow --since 4am
   ```

2. **Verify data loaded:**
   ```bash
   psql -h $DB_HOST -U stocks -d stocks -c \
     "SELECT MAX(date) FROM price_daily WHERE date = CURRENT_DATE;"
   ```

3. **Alert if missing:**
   - Phase 1 of orchestrator will detect "0 symbols loaded" and halt trading
   - Alert sent via AlertManager
   - Manual trigger: `python3 loadpricedaily.py`

## Current Status (May 9, 2026)

- ❌ May 9: 0 symbols (scheduler didn't run)
- ✓ May 8: 4,925 symbols (partial load, likely from local test)
- ✓ May 7: 5,469 symbols (full load)
- ✓ May 6: 5,469 symbols

**Next Action:** Deploy EventBridge rule to auto-trigger daily loads.
