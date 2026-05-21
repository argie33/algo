# Fallback Fixes — Ready to Deploy

**Status**: Staged (not yet committed)
**Condition**: If pipeline 26257674391 fails with price_daily coverage < 75%
**Action**: Execute fallback procedure immediately (2-3 min total)

## Root Cause

Stock prices loader has insufficient timeout for symbol count:
- Current: timeout=900s (15 min), parallelism=16
- Need: 5000 symbols ÷ 16 workers = 312 symbols/worker = 624-936s → EXCEEDS 900s
- Plus: 16 parallel workers hitting yfinance = rate-limiting

## Solution

Match pattern of other yfinance-heavy loaders (financial statements, key_metrics):
- Increase timeout: 900s → 1800s (30 min)
- Reduce parallelism: 16 → 8 (yfinance respects this)
- Apply to: stock_prices_daily, stock_prices_weekly, stock_prices_monthly
- Apply to: etf_prices_daily, etf_prices_weekly, etf_prices_monthly

## Files Modified

**terraform/modules/loaders/main.tf**
- Lines 371-378: Updated stock/ETF price loader configs
- Changes staged in Git (ready to commit)

## Execution Procedure (If Needed)

```bash
# Step 1: Verify pipeline failed
gh run view 26257674391 --repo argie33/algo --json conclusion

# Step 2: Commit staged fixes
git commit -m "fix: increase loader timeout + reduce parallelism for yfinance rate limits

Stock prices loaders timing out due to insufficient window for 5000+ symbols
at parallelism=16. Matches pattern of other yfinance-heavy loaders by:
- Increasing timeout 900→1800s (30 min)
- Reducing parallelism 16→8

Also apply to ETF loaders for consistency:
- Timeout 600→1200s
- Parallelism 8→4

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"

# Step 3: Deploy infrastructure
git push origin main
# Wait for deploy-code.yml to run (auto on push)
# Then trigger deploy-all-infrastructure.yml to apply Terraform changes

# Step 4: Re-trigger pipeline
gh workflow run loaders-and-orchestrator.yml --repo argie33/algo

# Step 5: Monitor new run
gh run view <new-run-id> --repo argie33/algo --log | tail -50
```

## Success Criteria After Fallback

✅ signal_quality_scores populated (algo_metrics_daily completed)
✅ price_daily coverage > 75% (stock_prices_daily completed with new timeout)
✅ Orchestrator phases 1-7 execute
✅ Trades placed in Alpaca LIVE account

## Estimated Time Impact

- If current pipeline succeeds: **+0 min** (already done)
- If fallback needed:
  - Deploy infrastructure: ~5-10 min
  - Loaders + orchestrator: ~40 min
  - **Total from now: ~45-50 min to completion**

---

**Status**: Ready to execute immediately if needed. Currently awaiting pipeline 26257674391 completion (~30 min remaining).
