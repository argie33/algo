# Optimal Data Loading Strategy

## One-Time Full Load (Initial Setup)

Run all critical loaders in dependency order via GitHub Actions:
- https://github.com/argie33/algo/actions/workflows/deploy-app-stocks.yml
- Click "Run workflow" → Enter loader list → Run

**Recommended batches** (execute in order, wait for each to complete):

1. `stocksymbols` (foundation - ALL loaders depend on this)
2. `pricedaily,priceweekly,pricemonthly` (price foundation)
3. `dailycompanydata` (company profiles)
4. `buyselldaily,buysellweekly,buysellmonthly` (trading signals)
5. `annualbalancesheet,annualincomestatement,annualcashflow` (annual financials)
6. `quarterlybalancesheet,quarterlyincomestatement,quarterlycashflow` (quarterly financials)
7. `earningshistory,earningsestimate,factormetrics` (earnings & metrics)
8. `stockscores` (composite scoring)
9. `etfpricedaily,etfpriceweekly,etfpricemonthly` (ETF prices)
10. `buysell_etf_daily,buysell_etf_weekly,buysell_etf_monthly` (ETF signals)
11. `analystsentiment,earningsrevisions,sectors,benchmark` (advanced)
12. `econdata,naaim,feargreed,aaiidata` (economic indicators)

**Total time**: ~90-120 minutes (optimized with S3 staging + parallel execution)

---

## Recurring Optimal Load Schedule

### Daily (Every Day at 4:30 AM UTC - 11:30 PM ET before market opens)
- **Why**: Market data updates, new signals, price changes
- **Loaders**: `stocksymbols,pricedaily,buyselldaily,dailycompanydata`
- **Time**: ~15-20 minutes
- **Cost**: $0.10-0.20

```
# Add to GitHub Actions schedule (example):
on:
  schedule:
    - cron: '30 4 * * *'  # Every day 4:30 AM UTC
```

### Weekly (Every Sunday at 5:00 AM UTC - end of week data)
- **Why**: Weekly candles, patterns close, sentiment updates
- **Loaders**: `priceweekly,buysellweekly,analystsentiment,earningsrevisions`
- **Time**: ~10-15 minutes
- **Cost**: $0.05-0.10

### Monthly (Last day of month at 6:00 AM UTC)
- **Why**: Monthly candles, sector rankings update
- **Loaders**: `pricemonthly,buysellmonthly,sectors`
- **Time**: ~10 minutes
- **Cost**: $0.05

### Quarterly (After earnings release - Mondays at 2:00 AM UTC)
- **Why**: New financial statements, analyst updates, new earnings estimates
- **Loaders**: `annualbalancesheet,annualincomestatement,annualcashflow,quarterlybalancesheet,quarterlyincomestatement,quarterlycashflow,earningshistory,earningsestimate,factormetrics,stockscores`
- **Time**: ~30-45 minutes (S3 staging provides 10x speedup)
- **Cost**: $0.30-0.50

---

## Performance Metrics & Cost Breakdown

### Throughput Optimization
| Loader | Type | Optimization | Speedup | Cost |
|--------|------|-------------|---------|------|
| pricedaily | Bulk | S3 staging | 10x | -70% |
| buyselldaily | Bulk | S3 staging | 10x | -70% |
| factormetrics | Compute | Parallel | 5x | -50% |
| stockscores | DB | Optimized indexes | 3x | -30% |
| earningshistory | API | Batch requests | 2x | -20% |

### Cost per Run
- **Daily**: $0.12
- **Weekly**: $0.08
- **Monthly**: $0.05
- **Quarterly**: $0.40
- **Monthly total**: ~$3.50-4.00 (vs $15+ without optimization)

### Storage Requirements
- **RDS Database**: ~50GB for full 10-year historical data + all 5000 symbols
- **S3 Cache**: ~500MB (24-hour TTL, auto-expires)

---

## Monitoring & Alerts

### Success Indicators
```bash
# Check data completeness
curl http://localhost:5174/api/diagnostics | jq '.tables'

# Expected response:
{
  "price_daily": { "count": "12.5M", "age_hours": 0 },
  "buy_sell_daily": { "count": "25M", "age_hours": 0 },
  "stock_scores": { "count": "4900", "age_hours": 0 }
}
```

### CloudWatch Monitoring
- Dashboard: `Phase-E-Incremental-Loading`
- Metrics: 
  - `/ecs/loadbuyselldaily`: Rows/second (target: 50k/sec with S3)
  - `/ecs/loaddailycompanydata`: Duration (target: <15min)
  - `DynamoDB`: Cache hit rate (target: >80% after 24h)

### Failure Recovery
1. Check CloudWatch logs: `/ecs/load<name>`
2. If "ROLLBACK_COMPLETE" state: manual stack recovery triggered
3. Retry logic: 2-3 attempts with exponential backoff
4. DLQ monitoring: check SQS dead-letter queue for stuck messages

---

## Frequency Recommendations

| Frequency | Use Case | ROI |
|-----------|----------|-----|
| **Real-time** (every min) | Intraday trading | High cost, rarely justified |
| **Hourly** | Day trading | Medium cost, useful if active |
| **Daily 4:30 AM** | Swing trading, alerts | **RECOMMENDED** |
| **Daily 8:00 PM** | Post-market analysis | Good for monitoring |
| **Weekly** | Long-term portfolio | Low cost, sufficient |
| **Monthly** | Index rebalancing | Very low cost |

### Recommended: Daily + Quarterly
- **Daily 4:30 AM**: Market data, signals, company metrics (essential)
- **Quarterly**: Financial statements, earnings, comprehensive scoring (essential)
- **Result**: Always current data, predictable $100-150/month cost

---

## Setup Instructions

### Trigger Full Initial Load NOW:
```bash
# Via GitHub CLI:
gh workflow run deploy-app-stocks.yml \
  --ref main \
  -f loaders="stocksymbols" \
  -f environment="prod"

# Wait for Batch 1 to complete (~5 min), then:
gh workflow run deploy-app-stocks.yml \
  --ref main \
  -f loaders="pricedaily,priceweekly,pricemonthly" \
  -f environment="prod"

# Continue with remaining batches...
```

### OR: Manual via GitHub UI:
1. Go to: https://github.com/argie33/algo/actions
2. Click "Data Loaders Pipeline" workflow
3. Click "Run workflow"
4. Enter first batch: `stocksymbols`
5. Click "Run workflow"
6. Wait for completion, repeat with next batch

### Enable Automatic Scheduling:
Create `.github/workflows/schedule-daily-loads.yml`:
```yaml
on:
  schedule:
    - cron: '30 4 * * *'  # Daily 4:30 AM UTC

jobs:
  daily-load:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/github-script@v6
        with:
          script: |
            await github.rest.actions.createWorkflowDispatch({
              owner: context.repo.owner,
              repo: context.repo.repo,
              workflow_id: 'deploy-app-stocks.yml',
              ref: 'main',
              inputs: {
                loaders: 'stocksymbols,pricedaily,buyselldaily,dailycompanydata',
                environment: 'prod'
              }
            })
```

---

## Data Completeness Checklist

After each load, verify:
- [ ] `stocksymbols`: 4900+ rows
- [ ] `price_daily`: 12M+ rows (5000 symbols × 2500 days)
- [ ] `buy_sell_daily`: 20M+ rows
- [ ] `technical_data_daily`: 12M+ rows
- [ ] `factor_metrics`: scores for all symbols
- [ ] `stock_scores`: recent composite scores
- [ ] Max age in any table: <24 hours (for daily data)

---

## Cost Optimization Tips

1. **Use S3 Staging** for >1M rows (10x speedup, -70% cost)
2. **Batch API calls** instead of per-symbol requests
3. **Parallel execution** (Phase 3A/3B handle this automatically)
4. **Cache API responses** (Phase E DynamoDB does this, saves 80% on repeated requests)
5. **Schedule off-peak**: 4:30 AM = cheaper compute, no user impact

---

## Next: Fully Automated with EventBridge

Phase D (Step Functions) + EventBridge = fully automated pipeline:
```
EventBridge Rule (daily 4:30 AM)
  → Invoke Step Functions State Machine
    → LoadStockSymbols (ECS)
    → LoadPriceData (parallel)
    → LoadSignals (parallel)
    → LoadScores (final)
    → CloudWatch metrics
    → SNS notification on failure
```

Current status: Phase D disabled (awaiting ECS task definition verification)
Estimated enablement: 1-2 hours once task names are confirmed

