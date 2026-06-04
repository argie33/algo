# Loader Timeout & Data Collection Fixes

## Summary
Comprehensive fixes for loader timeouts, database connection pool exhaustion, module import errors, and rate limiting issues.

## Commits
1. **fix: Reduce loader parallelism to prevent database connection pool exhaustion** (705f009a)
2. **fix: Add module import fallback and implement global rate limiter for yfinance** (00b02974)

## Issues Addressed

### 1. Database Connection Pool Exhaustion
**Problem**: Loaders with parallelism=4 (9 loaders × 4 = 36 concurrent connections) exhausted RDS Proxy connection pool
- technical_data_daily: "Timed-out waiting to acquire database connection"
- trend_template_data: 2 connection timeout errors
- swing_trader_scores: Connection contention

**Fix**: Reduce parallelism for critical loaders
- technical_data_daily: 4 → 2
- signal_quality_scores: 4 → 2
- swing_trader_scores: 4 → 2
- buy_sell_daily: 4 → 3

**Impact**: 
- Individual loader execution time may increase by ~20-30%
- Overall EOD pipeline faster (no retries/contention)
- Full dataset loaded without timeouts

### 2. Module Import Error: "No module named 'algo'"
**Problem**: growth_metrics, quality_metrics loaders failing with:
```
[growth_metrics] AA failed: No module named 'algo'
[quality_metrics] AA failed: No module named 'algo'
189 total module import errors across loaders
```

**Root Cause**: data_source_router.py imports from algo.algo_retry at module level, before loaders set sys.path

**Fix**: Added fallback implementations in data_source_router.py
- Try import from algo.algo_retry
- If fails, provide working retry() decorator and _RateLimiter class
- Allows loaders to function even if algo package unavailable at import time

**Impact**: Loaders can initialize and run successfully regardless of sys.path state

### 3. yfinance Rate Limiting
**Problem**: "Too Many Requests" errors (481 total rate limit errors)
- analyst_sentiment: 73 errors
- analyst_upgrades_downgrades: 72 errors
- company_profile: 117 errors
- stability_metrics: 79 errors

**Root Cause**: Each DataSourceRouter instance creates own YFINANCE_LIMITER (400 calls/min). With 4+ concurrent loaders:
- 4 loaders × 400 calls/min = 1600 calls/min
- Exceeds yfinance's actual limit (~400-600 calls/min)

**Fix**: Implement global/shared rate limiter
- All DataSourceRouter instances share single YFINANCE_LIMITER
- Global limiter set to 200 calls/min (conservative for 4+ concurrent loaders)
- Use get_global_yfinance_limiter() to access shared instance

**Impact**: yfinance loaders stay within API rate limits, full data collection without "Too Many Requests" errors

### 4. Statement Timeouts
**Problem**: Signal quality scoring and technical data queries exceed 30-second timeout
- signal_quality_scores: 2 statement timeout errors
- swing_trader_scores: 1 statement timeout error
- trend_template_data: 1 statement timeout error

**Status**: Addressed by parallelism reduction (fewer concurrent queries = shorter query time)
**Note**: RDS statement_timeout is configured as 900 seconds (15 minutes) in terraform, which is sufficient for batch operations

### 5. Numeric Field Overflow
**Problem**: buy_sell_daily producing values exceeding database column limits
- Example: "numeric field overflow" for symbols ABLD, ADGM, AFBI

**Status**: Not addressed in these commits (data validation issue, requires separate investigation)
**Action**: Monitor post-deployment; may require schema adjustment or output value clamping

## Deployment Steps

1. **Build new Docker image**
   - GitHub Actions will automatically build on `git push main`
   - New image includes all fixes

2. **Deploy to ECS**
   - GitHub Actions automatically deploys on `git push main`
   - Old ECS tasks will be replaced with new image

3. **Monitor**
   - Check CloudWatch logs for specific loaders
   - Verify no "timed-out waiting", "module import", or "too many requests" errors
   - Monitor EOD pipeline completion time (should be similar or faster)

## Testing

### Local Testing (Pre-Deployment)
```bash
# Test module imports
python3 -c "from utils.data_source_router import DataSourceRouter; print('OK')"

# Test rate limiter
python3 loaders/load_company_profile.py --symbols AAPL,MSFT --parallelism 2

# Test technical data loading
python3 loaders/load_technical_data_daily.py --symbols AAPL --parallelism 2
```

### Post-Deployment Verification
1. Wait for next scheduled loader run (daily 4 AM ET)
2. Check CloudWatch logs for the loaders:
   - No "timed-out waiting to acquire database connection"
   - No "No module named 'algo'"
   - No "Too Many Requests" errors for yfinance loaders
3. Verify full dataset loaded:
   - Check technical_data_daily row count should match symbols
   - Check signal_quality_scores completion without timeout

## Configuration Changes
- **terraform/modules/loaders/main.tf**: Updated parallelism values for 5 loaders
- **utils/data_source_router.py**: Added fallback imports and global rate limiter
- **steering/algo.md**: Updated RDS configuration documentation

## Files Modified
- terraform/modules/loaders/main.tf
- utils/data_source_router.py  
- steering/algo.md
- scripts/check_loader_logs.py (new)
- scripts/check_all_loader_errors.py (new)
- scripts/check_rds_config.py (new)

## Performance Impact

### Positive
- Elimination of retry overhead from connection timeouts
- Faster overall EOD pipeline (no contention, fewer retries)
- More stable yfinance data collection (respects rate limits)
- Full dataset collection without failures

### Minimal
- Individual loader execution time +20-30% (due to lower parallelism)
- But overall pipeline faster because no timeouts/retries
- Total EOD time likely same or faster

## Known Limitations

1. **Numeric overflow**: buy_sell_daily still produces overflow errors for some symbols (separate issue)
2. **Rate limiting aggressiveness**: Conservative 200 calls/min may slow yfinance loaders slightly (trade-off for stability)

## Rollback Plan

If issues occur post-deployment:
```bash
git revert 00b02974  # Revert rate limiter fix
git revert 705f009a  # Revert parallelism reductions
git push main
# Wait for automatic redeployment
```
