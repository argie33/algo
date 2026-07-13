# Ruthless Cost Audit: Keep Essential, Cut Bloat

**Goal**: Keep algo, dashboard, data, site working. Cut everything else.

---

## TIER 1: ABSOLUTELY REQUIRED (~$17-25/day)

### Database & Storage
- **RDS PostgreSQL (db.t4g.small)**: ~$6-7/day
  - Stores: Prices, signals, positions, portfolio snapshots
  - Used by: Algo, Dashboard, Data loaders
  - ✓ KEEP - Cannot remove, core data layer

- **S3**: ~$0.50-1/day
  - Stores: Code artifacts, Lambda ZIPs
  - ✓ KEEP - Required for deployments

### Trading System (Core)
- **Lambda: algo-orchestrator**: ~$0.10-0.20/day
  - Runs: 9 trading phases (analysis, signals, position management)
  - Triggered: 2x daily (9:30 AM + 5:30 PM ET)
  - ✓ KEEP - Core trading logic

- **Step Functions: algo-morning-prep-pipeline**: ~$0.05-0.10/day
  - Orchestrates: Data loaders sequentially
  - ✓ KEEP - Fresh data delivery

### Data Loading (Core)
- **ECS Tasks**: stock_prices_daily + buy_sell_daily + market_health_daily
  - Cost: ~$10-15/day (2x daily runs, 30-60 min each)
  - ✓ KEEP - Source of market data

### Orchestration
- **EventBridge Scheduler**: 2 schedules (morning 9:30 AM, evening 5:30 PM)
  - Cost: ~$0.01/day (free tier covers this)
  - ✓ KEEP - Automated triggering

**SUBTOTAL TIER 1: ~$17-25/day**

---

## TIER 2: DASHBOARD (Frontend) (~$0.50-1.00/day)

- **Lambda: dashboard-api**: ~$0.20-0.50/day
  - Fetches: Portfolio, positions, signals from RDS
  - Endpoints: /api/portfolio, /api/positions, /api/scores, etc.
  - ✓ KEEP - Dashboard needs data

- **API Gateway**: ~$0.10-0.20/day
  - Routes: Requests to Lambda
  - ✓ KEEP - HTTP endpoint

- **Cognito**: ~$0/day (free tier)
  - Protects: Algo endpoints
  - ✓ KEEP - Security

- **S3 + CloudFront**: ~$0.20-0.30/day (CloudFront already disabled ✓)
  - ✓ KEEP - Dashboard UI

**SUBTOTAL TIER 2: ~$0.50-1.00/day**

---

## TIER 3: WEBSITE (If Needed) — TBD

**Question**: Do you need a public website? Or just internal dashboard?
- If **internal only**: Skip this, save $5-20/day
- If **public needed**: Similar cost to dashboard

---

## TIER 4: MONITORING & ALERTING (MOSTLY BLOAT)

### Currently Configured (~$1.20-2.00/day)

- **CloudWatch Alarms**: 43 alarms (~$0.50-1.00/day)
  - Loader monitoring (9), Pipeline monitoring (4), Database (9), Freshness (1), Other (20)
  - ✗ **CUT TO 5 CRITICAL ONLY**: Save $0.40-0.80/day
    - Keep: Orchestrator execution, pipeline timeout, data stale
    - Delete: Loader task failures, granular load monitoring, non-critical stuff

- **CloudWatch Dashboards**: 2 dashboards (~$0.50/month = $0.02/day)
  - ✗ **DELETE**: Nice to have, not essential
  - Save: $0.02/day (negligible)

- **EventBridge Task Failure Rules**: Capture ECS state changes (~$0.10-0.20/day)
  - ✗ **DELETE**: Nice to have, not essential for trading
  - Save: $0.10-0.20/day

- **SNS Topic + Email Alerts**: (~$0.05-0.10/day)
  - ✗ **DELETE**: Nice to have, not essential
  - Save: $0.05-0.10/day

- **SQS Dead-Letter Queue**: Scheduler failures (~$0.05/day)
  - ✗ **DELETE**: Useful for debugging, but not essential
  - Save: $0.05/day

**SUBTOTAL CUT FROM TIER 4: ~$0.60-1.15/day**

---

## TIER 5: OPTIMIZATION & META (DEFINITELY BLOAT)

### DELETE These (Not Essential for Trading)

| Item | Cost | Action | Savings |
|------|------|--------|---------|
| Pre-warm Lambda schedules (4 schedules) | $0.50-1.00/day | DELETE | $0.50-1.00 |
| Cost circuit breaker Lambda | $0.20/day | DELETE | $0.20 |
| Weight optimization scheduler (6:00 PM) | $0.20/day | DELETE | $0.20 |
| RDS scheduler | $0.10/day | DELETE | $0.10 |
| Credential rotation service | $0.05/day | DELETE | $0.05 |
| **SUBTOTAL** | **$1.05-1.55/day** | **DELETE** | **$1.05-1.55** |

---

## TIER 6: OTHER OPTIONAL ITEMS

| Item | Current | Recommendation |
|------|---------|-----------------|
| Log retention | 1 day | KEEP (debugging needs justify cost) |
| ECR image scans | Disabled | KEEP DISABLED |
| RDS Multi-AZ | Single-AZ | KEEP SINGLE-AZ (saves $15/month) |
| RDS Proxy | Disabled | KEEP DISABLED (saves $150/month) |

---

## BLOAT CHECK: Loaders

**Question**: Are you using ALL 36+ loaders?

Current loaders listed in loader-monitoring.tf:
- aaii_sentiment, algo_metrics_daily, analyst_sentiment_analysis, analyst_upgrade_downgrade, balance_sheet, buy_sell_daily, cash_flow, company_profile, earnings_calendar, earnings_history, economic_calendar, fear_greed_index, fred_economic_data, growth_metrics, income_statement, industry_ranking, market_health_daily, naaim, positioning_metrics, prices, quality_metrics, russell2000_constituents, seasonality, sector_performance, sector_ranking, sentiment, sentiment_aggregate, signal_quality_scores, signal_themes, sp500_constituents, stability_metrics, stock_scores, stock_symbols, swing_trader_scores, technical_data_daily, trend_criteria_data, value_metrics

**Action**: Audit which ones you actually use in your algo:
- ✓ KEEP: stock_prices, buy_sell_daily, market_health_daily (confirmed essential)
- ✗ AUDIT: Do you use sentiment, technical_data_daily, stock_scores, sector_performance?
- ✗ DELETE: Any loader not referenced in algo signals/phases

Each unnecessary loader ECS task wastes ~$5-10/day if running.

---

## SUMMARY: COST REDUCTION PLAN

### Current State (Bloated)
- Estimated: ~$31-42/day (per my earlier analysis)

### After Cuts (Lean & Mean)
- **Essential Only**: ~$17-25/day
  - RDS: $6-7/day
  - ECS loaders (2x daily): $10-15/day
  - Everything else: $1-3/day

- **+ Minimal Monitoring** (5 critical alarms only): +$0.10-0.20/day
- **TOTAL REALISTIC**: ~$17-26/day

### Savings Achievable
- Delete bloat (Tier 5): **-$1.05-1.55/day**
- Reduce alarms (Tier 4): **-$0.60-1.15/day**
- Delete optional monitoring: **-$0.20-0.40/day**
- **TOTAL MONTHLY SAVINGS: ~$52-90/month**

### If You Reduce Loader Frequency (Morning + Evening → Evening Only)
- Save: **$5-7/day** (one less daily load)
- Tradeoff: Miss morning trading opportunities
- **TOTAL**: ~$10-18/day

---

## QUESTIONS FOR YOU

1. **Do you need a public website?**
   - Yes → Keep website tier (~$0.50-1.00/day)
   - No → Delete, save $0.50-1.00/day

2. **Do you use all 36+ loaders?**
   - List the ones actually referenced in your algo
   - Audit: Delete unused loaders from ECS pipeline

3. **Can you live with cold-start delays (15-40s)?**
   - Yes → Delete pre-warm schedules, save $0.50-1.00/day
   - No → Keep pre-warm (optimization cost)

4. **Do you need email alerts for everything?**
   - Just critical (orchestrator failures) → Delete most SNS/alarms
   - Detailed monitoring → Keep current setup

5. **One loading run per day, or two?**
   - One (evening only) → Save $5-7/day, miss morning trades
   - Two (current) → Keep, costs more but better trading coverage

---

## Recommended Minimal Configuration

**For maximum cost reduction while keeping algo working:**

```
✓ KEEP:
  - RDS ($6-7/day)
  - ECS loaders: prices, buy_sell, market_health ($10-15/day)
  - Lambda: orchestrator, dashboard-api ($0.30-0.70/day)
  - Step Functions, EventBridge, API Gateway ($0.20-0.30/day)
  - Cognito, S3 ($0.20-0.30/day)

✗ DELETE:
  - Pre-warm schedules
  - Cost circuit breaker
  - Weight optimization
  - Most alarms (keep 5 critical)
  - SNS alerts (except critical failures)
  - CloudWatch dashboards
  - EventBridge task failure rules
  - SQS DLQ

RESULT: ~$17-23/day ($510-690/month)
```

---

## Next Steps

1. **Confirm your priorities** (answer the 5 questions above)
2. **Audit loaders** (which ones do you actually use?)
3. **Identify critical alarms** (which monitoring is essential?)
4. **Delete bloat from Terraform** (mechanical cleanup)
5. **Deploy and verify** (measure actual costs)

**I can do all the Terraform deletion once you confirm what to keep.**
