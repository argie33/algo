# ECS Task Right-Sizing Strategy (Phase 6)

## Current State
All 28 loaders have been cost-optimized in Phase 4:
- **256 CPU / 512 MB:** 5 loaders (market data, lightweight)
- **512 CPU / 1024 MB:** 13 loaders (metrics, financials)
- **1024 CPU / 2048 MB:** 10 loaders (heavy compute: signal generation, analyst data, stock scores)

**Total current allocation:** ~15,500 MB + 11,520 CPU across all loaders
**Estimated Fargate cost:** $30-50/month

## Phase 6 Opportunity: Further Memory Reduction
**Goal:** Identify underutilized loaders and reduce by 10-20% conservatively
**Estimated additional savings:** $5-10/month
**Risk Level:** MEDIUM (OOM errors if reduced too aggressively)

## Safe Right-Sizing Approach

### Step 1: Measure Actual Usage (Weeks 1-2)
Monitor CloudWatch metrics during orchestrator runs:

```
For each loader, track:
1. Max memory usage per run (CloudWatch: ContainerMemoryUtilization)
2. CPU usage per run (CloudWatch: ContainerCpuUtilization)
3. Success/failure rate
4. Execution time
5. Any OOM/timeout errors
```

**Commands to monitor:**
```bash
# Real-time loader performance
python3 scripts/monitor_loader_optimization.py

# CloudWatch logs for OOM/memory errors
aws logs tail /ecs/algo-<loader> --follow --log-stream-name-pattern '*'
```

### Step 2: Identify Reduction Candidates (Week 2)
Loaders that are good candidates for reduction:

| Loader | Current | Safe Target | Rationale |
|--------|---------|------------|-----------|
| `market_exposure_daily` | 256/512 | KEEP | Already minimal |
| `dxy_index` | 256/512 | KEEP | Already minimal |
| `market_constituents` | 256/512 | KEEP | Already minimal |
| `market_health_daily` | 256/512 | KEEP | Already minimal |
| `market_sentiment` | 256/512 | KEEP | Already minimal |
| `financials_*` (8 loaders) | 512/1024 | **512/768** | SEC filing parse + DB insert; lightweight |
| `earnings_history` | 512/1024 | **512/768** | History queries only; no real-time fetch |
| `earnings_calendar` | 512/1024 | **512/768** | Calendar data lightweight |
| `growth_metrics` | 512/1024 | **512/768** | yfinance API fetch only, no CPU-heavy calc |
| `quality_metrics` | 512/1024 | **512/768** | SEC data parse only |
| `value_metrics` | 512/1024 | KEEP | Already optimized |
| `positioning_metrics` | 512/1024 | KEEP | Moderate compute |
| `stability_metrics` | 512/1024 | KEEP | Dividend calculations, safe |
| `momentum_metrics` | 512/1024 | KEEP | Return calculations, safe |
| `sector_ranking` | 512/1024 | KEEP | Already optimized |
| `industry_ranking` | 512/1024 | KEEP | Already optimized |
| `stock_prices_daily` | 512/1024 | KEEP | Price fetching, already optimized |
| `technical_data_daily` | 1024/2048 | **1024/1536** | Vectorized SQL on ~10k rows; can reduce memory |
| `trend_template_data` | 1024/2048 | **1024/1536** | Template analysis; moderate memory |
| `yfinance_snapshot` | 1024/2048 | **1024/1536** | Snapshot caching; try reducing |
| `algo_metrics_daily` | 1024/2048 | KEEP | Phase 9 reconciliation; heavy |
| `buy_sell_daily` | 1024/2048 | KEEP | Signal generation; complex |
| `company_profile` | 1024/2048 | **1024/1536** | Profile fetch + parse |
| `analyst_sentiment` | 1024/2048 | **1024/1536** | Sentiment aggregation |
| `analyst_upgrades_downgrades` | 1024/2048 | **1024/1536** | Upgrade/downgrade parse |
| `stock_scores` | 1024/2048 | KEEP | Final scoring computation; heavy |
| `compute_performance_metrics` | 512/1024 | KEEP | Already optimized |

### Step 3: Conservative Reduction Schedule

**Week 1:** Continue monitoring current allocations. Collect baseline metrics.

**Week 2:** After 7 days of data:
1. Reduce Group A (lightest candidates first):
   - `financials_*` (8 loaders): 512/1024 → 512/768
   - `earnings_*` (2 loaders): 512/1024 → 512/768
   - `growth_metrics` + `quality_metrics`: 512/1024 → 512/768
   - **Cost savings: ~$2-3/month**

2. Reduce Group B (medium candidates):
   - `technical_data_daily`, `trend_template_data`: 1024/2048 → 1024/1536
   - `yfinance_snapshot`: 1024/2048 → 1024/1536
   - `company_profile`, `analyst_*`: 1024/2048 → 1024/1536
   - **Cost savings: ~$3-5/month**

3. **Stop here.** Remaining loaders (algo_metrics_daily, buy_sell_daily, stock_scores) are compute-heavy and risky to reduce.

### Step 4: Monitor After Changes (Week 3+)

After each reduction wave, monitor for:
- ✓ Success rate stays ≥88%
- ✓ No OOM errors in CloudWatch logs
- ✓ Execution time doesn't increase >10%
- ✓ No 502/timeout errors in orchestrator

**If failures occur:** Immediately revert that group (update terraform.tfvars and re-apply)

## Expected Outcomes

| Scenario | Savings | Risk |
|----------|---------|------|
| Group A reduction only | $2-3/month | LOW |
| Group A + B reduction | $5-8/month | MEDIUM |
| Aggressive reduction (all) | $10-15/month | HIGH (not recommended) |

## Measurement Commands

### Current memory usage by loader:
```sql
SELECT table_name, status, error_message
FROM data_loader_status
WHERE last_updated > NOW() - INTERVAL '1 hour'
ORDER BY table_name;
```

### Check for recent OOM errors:
```bash
aws logs filter-log-events \
  --log-group-name /ecs/algo-loaders \
  --filter-pattern "OOM|OutOfMemory|MemoryError" \
  --start-time $(date -d '7 days ago' +%s)000
```

### Monitor loader execution times:
```bash
python3 scripts/monitor_loader_optimization.py
```

## Risk Mitigation

- **Rollback plan:** If a loader fails after reduction, revert in terraform.tfvars within 5 minutes
- **Testing:** Run orchestrator manually (via `trigger_orchestrator.py`) before sleep to catch issues
- **Monitoring:** Set CloudWatch alarm for loader error rate > 5% during test week
- **Conservative step:** Start with Group A only (lowest risk). Only proceed to Group B if Group A succeeds.

## Timeline

- **Week 1:** Measure (no changes)
- **Week 2:** Apply Group A reductions, monitor
- **Week 3:** Apply Group B reductions if Group A stable, monitor
- **Week 4+:** Verify stability. Decision: keep changes or revert.

**Estimated total effort:** 2-3 weeks of monitoring
**Estimated payoff:** $5-8/month recurring savings
**ROI:** Break-even in ~2 weeks if changes hold
