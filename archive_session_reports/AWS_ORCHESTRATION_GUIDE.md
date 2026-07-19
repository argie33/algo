# AWS Orchestration & Data Pipeline Guide

## Status: Manual Triggers Required (EventBridge Scheduler Deployment Pending)

The system is fully operational in AWS, but automated pipeline scheduling is blocked by IAM permissions. **Workaround: Use manual trigger scripts** to keep data fresh while EventBridge Scheduler is being deployed.

## Quick Start

### Option 1: Manual Pipeline Triggers (Recommended for Testing)

Run all pipelines in sequence:
```bash
python scripts/trigger_data_pipelines_all.py
```

Or trigger individual pipelines:
```bash
# Morning: Load prices + technicals (runs 2:00 AM ET)
python scripts/trigger_morning_pipeline.py

# EOD: Load signals + financial data (runs 4:05 PM ET)
python scripts/trigger_eod_pipeline.py

# Computed Metrics: Load value/quality/growth/stability + scores (runs 7:00 PM ET)
python scripts/trigger_computed_metrics_pipeline.py
```

### Option 2: Local Dev Mode (Dashboard Development)

Use the unified startup script - handles everything:
```bash
python start_dashboard_dev.py       # Auto-starts dev_server + dashboard
python start_dashboard_dev.py -w 30 # With auto-refresh every 30s
```

For AWS mode with manual triggers:
```bash
python scripts/trigger_data_pipelines_all.py
python dashboard.py  # Now shows fresh data
```

## Data Pipeline Execution Order

The system requires pipelines to run in dependency order. Manual triggers enforce this:

1. **Morning Pipeline (2:00 AM ET)**
   - Loads: stock prices + technical indicators
   - Dependency: None (first pipeline)
   - Timeout: 6 hours (prices take 60-120 min with yfinance rate limiting)

2. **EOD Pipeline (4:05 PM ET)**
   - Loads: financial data, signals, sector rankings
   - Dependency: Prices must be fresh (from morning pipeline)
   - Timeout: 8 hours
   - Critical for: Phase 5 signal generation, Phase 9 risk metrics

3. **Computed Metrics Pipeline (7:00 PM ET)**
   - Loads: value/quality/growth/stability metrics + stock scores
   - Dependency: Financial data must complete (from EOD pipeline)
   - Timeout: 4 hours
   - Critical for: Dashboard factor scores, stock ranking

4. **Orchestrator (9:30 AM ET)**
   - Generates trading signals and recommendations
   - Dependency: All metric pipelines must be fresh
   - Runs automatically via Lambda EventBridge rule (deployed)

## Why Factor Scores Show "--"

### Expected Behavior (Not a Bug)
Some stocks may have incomplete data (< 70% completeness). The dashboard API intentionally filters these out to avoid showing misleading scores.

Stock scores require minimum 3/6 metrics (50%) to be computed, but the API only returns scores with 70%+ completeness to prevent low-confidence trading signals.

Distribution of stock score completeness (as of 2026-07-16):
- 70%+ completeness: 3099 stocks (visible in dashboard)
- 50-69% completeness: 1214 stocks (filtered by API)
- < 50% completeness: 398 stocks (incomplete)

### Common Causes of Missing Scores
1. **Insufficient factor data**
   - Stock is too young (IPO < 1 year) - no historical metrics
   - Missing SEC filings - no growth/quality metrics
   - Penny stock - no institutional data (positioning metrics)

2. **Pipeline didn't run** (Symptom: old data across entire dashboard)
   - Morning pipeline failed to load prices
   - EOD pipeline timed out
   - Computed metrics pipeline timed out
   - **Fix:** Run `python scripts/trigger_data_pipelines_all.py`

3. **Loaders encountered data issues**
   - yfinance rate limited on shared AWS IP - **Workaround:** `PRICE_DATA_SOURCE=alpaca`
   - Financial data incomplete - some firms don't publish all filings
   - Metrics loader timed out - rerun individual pipeline

## EventBridge Scheduler Deployment Status

### Current Blocker: IAM Permissions
The `algo-developer` user lacks permissions to deploy EventBridge Scheduler resources:
- Missing: `scheduler:ListSchedules`, `scheduler:PutSchedule`, `events:PutRule`
- These allow Terraform to create/manage scheduler rules

### Deployment Options

#### Option A: GitHub Actions Deployment (Recommended)
GitHub Actions has `algo-svc-github-actions-dev` role with higher permissions:

```bash
# Commit these changes
git add scripts/
git commit -m "Add manual pipeline trigger scripts"
git push origin main

# Trigger GitHub Actions deployment
gh workflow run deploy-all-infrastructure.yml
```

This runs `terraform apply` in AWS with elevated permissions and deploys:
- EventBridge Scheduler rules (morning/EOD/computed-metrics at scheduled times)
- Step Functions state machines
- Lambda functions
- All infrastructure-as-code

#### Option B: Admin Deployment (Manual)
Ask AWS admin to run:
```bash
cd terraform
terraform apply -target="module.pipeline.aws_scheduler_schedule.morning_pipeline_trigger" \
                 -target="module.pipeline.aws_scheduler_schedule.eod_pipeline_trigger" \
                 -target="module.pipeline.aws_scheduler_schedule.computed_metrics_pipeline_trigger" \
                 -target="module.pipeline.aws_scheduler_schedule.reference_data_pipeline_trigger"
```

#### Option C: Grant IAM Permissions (Permanent Fix)
Add these permissions to `algo-developer` IAM user policy:
```json
{
  "Effect": "Allow",
  "Action": [
    "scheduler:ListSchedules",
    "scheduler:PutSchedule",
    "scheduler:GetSchedule",
    "scheduler:DeleteSchedule",
    "scheduler:UpdateSchedule",
    "events:PutRule",
    "events:DescribeRule",
    "events:DeleteRule",
    "events:PutTargets",
    "events:RemoveTargets"
  ],
  "Resource": "arn:aws:scheduler:us-east-1:*:schedule/*"
}
```

## Monitoring Pipeline Health

### Check Latest Pipeline Executions
```bash
# AWS CLI
aws stepfunctions list-executions --state-machine-arn "arn:aws:states:us-east-1:626216981288:stateMachine:algo-eod-pipeline-dev" --max-items 5

# Or via Python
python scripts/verify_eventbridge_scheduler.py
```

### Monitor Data Staleness
```bash
python scripts/monitor_data_staleness.py
python scripts/monitor_data_staleness.py --watch 60  # Poll every 60s
```

### Check Data Quality
```sql
-- Latest prices
SELECT symbol, MAX(date) as latest_price_date FROM price_daily GROUP BY symbol ORDER BY latest_price_date DESC LIMIT 5;

-- Latest stock scores
SELECT COUNT(*), MAX(updated_at) FROM stock_scores WHERE composite_score IS NOT NULL;

-- Latest metrics
SELECT table_name, status, last_updated FROM data_loader_status WHERE status = 'COMPLETED' ORDER BY last_updated DESC;
```

## Troubleshooting

### "Data not available" on Dashboard
1. Run system health check:
   ```bash
   python check_system_health.py
   ```

2. Check if dev_server is running:
   ```bash
   curl http://localhost:3001/api/health
   ```

3. Refresh data with manual triggers:
   ```bash
   python scripts/trigger_data_pipelines_all.py
   ```

### Factor Scores Showing "--"
1. Verify computed metrics pipeline ran recently:
   ```bash
   python scripts/monitor_data_staleness.py
   ```
   Look for: `value_metrics`, `quality_metrics`, `growth_metrics`, `stability_metrics`, `stock_scores`

2. If older than 24 hours, run:
   ```bash
   python scripts/trigger_computed_metrics_pipeline.py
   ```

3. Check for failures:
   ```bash
   # CloudWatch logs (requires AWS CLI)
   aws logs tail /aws/states/algo-computed-metrics-pipeline-dev --follow
   ```

### Prices Stale or "Rate Limited"
1. Check price freshness:
   ```bash
   python scripts/monitor_data_staleness.py | grep price_daily
   ```

2. If stale, trigger morning pipeline:
   ```bash
   python scripts/trigger_morning_pipeline.py
   ```

3. If yfinance rate limited (Session 184 workaround):
   ```bash
   export PRICE_DATA_SOURCE=alpaca
   python scripts/trigger_morning_pipeline.py
   ```

## Architecture Reference

### Data Dependency Graph
```
Morning Pipeline (2:00 AM ET)
  ├─→ stock_prices_daily
  ├─→ technical_data_daily
  ├─→ market_health_daily
  ├─→ market_exposure_daily (fresh regime)
  └─→ sector_ranking

EOD Pipeline (4:05 PM ET)
  ├─→ financial_data_loaders (annual financials)
  ├─→ quality_metrics (depends on financial_data)
  ├─→ buy_sell_daily (depends on prices + technical_data)
  └─→ market_exposure_daily (final regime)

Computed Metrics Pipeline (7:00 PM ET)
  ├─→ yfinance_snapshot (fetch all stock data once)
  ├─→ value_metrics (depends on yfinance_snapshot)
  ├─→ quality_metrics (depends on financial_data from EOD)
  ├─→ growth_metrics (depends on financial_data from EOD)
  ├─→ positioning_metrics (depends on yfinance_snapshot)
  ├─→ stability_metrics (depends on prices + prices history)
  └─→ stock_scores (depends on all above metrics)

Orchestrator Lambda (9:30 AM ET)
  └─→ Generates signals using:
      - stock_scores
      - buy_sell_daily
      - market_exposure_daily
      - portfolio_config
```

### Phase Execution Dependencies
- **Phase 1 (Freshness Check):** Requires stock_prices_daily, market_health_daily, market_exposure_daily
- **Phase 5 (Signal Generation):** Requires technical_data_daily, buy_sell_daily, stock_scores
- **Phase 9 (Portfolio Snapshot):** Requires all above + risk_metrics

## References
- `steering/DATA_LOADERS.md` — Loader configuration and troubleshooting
- `steering/OPERATIONS.md` — AWS infrastructure operations
- `steering/GOVERNANCE.md` — Data integrity and risk management rules
- `DASHBOARD_TROUBLESHOOTING.md` — Dashboard-specific issues
