# Data Loader Specifications - Complete Implementation Guide

**Total Loaders:** 40 actual loaders defined in `run-all-loaders.py`
**Terraform Status:** 7 stubs, 33 missing
**Target:** All 40 fully configured with resource requirements, schedules, and IAM

---

## Loader Categories & Resource Requirements

### 1. PRICE DATA LOADERS (High CPU/Memory - API intensive)
**CPU: 512, Memory: 1024**
- Requires: Alpaca API, market data sources
- Timeout: 600 seconds (10 min)
- Schedule: Daily 4:00am ET (9am UTC Mon-Fri)

| Loader Name | File | Purpose | Type |
|-------------|------|---------|------|
| stock_prices_daily | loadpricedaily.py | Daily OHLCV for all stocks | Daily schedule |
| stock_prices_weekly | loadpriceweekly.py | Weekly OHLCV aggregation | Weekly schedule |
| stock_prices_monthly | loadpricemonthly.py | Monthly OHLCV aggregation | Monthly schedule |
| etf_prices_daily | loadetfpricedaily.py | Daily OHLCV for ETFs | Daily schedule |
| etf_prices_weekly | loadetfpriceweekly.py | Weekly OHLCV for ETFs | Weekly schedule |
| etf_prices_monthly | loadetfpricemonthly.py | Monthly OHLCV for ETFs | Monthly schedule |

**Total: 6 loaders**

---

### 2. FINANCIAL STATEMENTS (Medium CPU/Memory - API rate limited)
**CPU: 256, Memory: 512**
- Requires: SEC/Financial data API
- Timeout: 1200 seconds (20 min)
- Schedule: Daily 10am ET (3pm UTC Mon-Fri)

| Loader Name | File | Purpose |
|-------------|------|---------|
| financials_annual_income | loadannualincomestatement.py | Annual P&L statements |
| financials_annual_balance | loadannualbalancesheet.py | Annual balance sheets |
| financials_annual_cashflow | loadannualcashflow.py | Annual cash flow |
| financials_quarterly_income | loadquarterlyincomestatement.py | Quarterly P&L |
| financials_quarterly_balance | loadquarterlybalancesheet.py | Quarterly balance |
| financials_quarterly_cashflow | loadquarterlycashflow.py | Quarterly cash flow |
| financials_ttm_income | loadttmincomestatement.py | TTM P&L (trailing 12m) |
| financials_ttm_cashflow | loadttmcashflow.py | TTM cash flow |

**Total: 8 loaders**

---

### 3. TRADING SIGNALS (Medium CPU/Memory - Algorithm driven)
**CPU: 256, Memory: 512**
- Requires: Historical price data (must run AFTER price loaders)
- Timeout: 900 seconds (15 min)
- Schedule: Daily 5pm ET (10pm UTC Mon-Fri) — after price load completes

| Loader Name | File | Purpose |
|-------------|------|---------|
| signals_daily | loadbuyselldaily.py | Daily buy/sell signals |
| signals_weekly | loadbuysellweekly.py | Weekly signals |
| signals_monthly | loadbuysellmonthly.py | Monthly signals |
| signals_etf_daily | loadbuysell_etf_daily.py | ETF daily signals |
| etf_signals | loadetfsignals.py | ETF technical signals |

**Total: 5 loaders**

---

### 4. EARNINGS DATA (Low-Medium CPU/Memory - External feeds)
**CPU: 256, Memory: 512**
- Requires: Earnings calendar API
- Timeout: 600 seconds (10 min)
- Schedule: Daily 11am ET (4pm UTC Mon-Fri) — quarterly data

| Loader Name | File | Purpose |
|-------------|------|---------|
| earnings_history | loadearningshistory.py | Historical earnings dates |
| earnings_revisions | loadearningsrevisions.py | Analyst estimate changes |
| earnings_surprise | loadearningssurprise.py | Beat/miss percentages |
| earnings_sp500 | load_sp500_earnings.py | S&P 500 earnings calendar |

**Total: 4 loaders**

---

### 5. MARKET & ECONOMIC DATA (Low CPU/Memory - Single source, light processing)
**CPU: 256, Memory: 256**
- Requires: Economic data APIs, market indices providers
- Timeout: 300 seconds (5 min)
- Schedule: Daily 6pm ET (11pm UTC Mon-Fri) — after market close

| Loader Name | File | Purpose |
|-------------|------|---------|
| market_overview | loadmarket.py | Daily market breadth, advances/declines |
| market_indices | loadmarketindices.py | Major index OHLCV |
| sector_performance | loadsectors.py | Sector OHLCV |
| relative_performance | loadrelativeperformance.py | Relative strength vs benchmark |
| seasonality | loadseasonality.py | Seasonal patterns |
| econ_data | loadecondata.py | Economic indicators (CPI, jobs, etc) |
| aaiidata | loadaaiidata.py | AAII sentiment survey |
| naaim_data | loadnaaim.py | NAAIM asset allocation |
| feargreed | loadfeargreed.py | Fear & Greed Index |
| calendar | loadcalendar.py | Economic calendar |

**Total: 10 loaders**

---

### 6. SENTIMENT & ANALYSIS (Low CPU/Memory - Aggregated data)
**CPU: 256, Memory: 256**
- Requires: Sentiment APIs, research feeds
- Timeout: 600 seconds (10 min)
- Schedule: Daily 12pm ET (5pm UTC Mon-Fri) — midday update

| Loader Name | File | Purpose |
|-------------|------|---------|
| analyst_sentiment | loadanalystsentiment.py | Analyst rating aggregates |
| analyst_upgrades | loadanalystupgradedowngrade.py | Rating changes |
| social_sentiment | loadsentiment.py | Social media sentiment |
| factor_metrics | loadfactormetrics.py | Factor performance |
| stock_scores | loadstockscores.py | Composite quality scores |

**Total: 5 loaders**

---

### 7. STOCK SYMBOLS (Very Low CPU/Memory - Reference data)
**CPU: 128, Memory: 256**
- Requires: SEC exchange listing data
- Timeout: 300 seconds (5 min)
- Schedule: Daily 3:30am ET (8:30am UTC Mon-Fri) — before price loader

| Loader Name | File | Purpose |
|-------------|------|---------|
| stock_symbols | loadstocksymbols.py | NYSE, NASDAQ, AMEX listings |

**Total: 1 loader**

---

### 8. ALGO METRICS (Low CPU/Memory - Computed from other loaders)
**CPU: 256, Memory: 256**
- Requires: All price and signal data loaded first
- Timeout: 600 seconds (10 min)
- Schedule: Daily 5:15pm ET (10:15pm UTC Mon-Fri) — after signals load

| Loader Name | File | Purpose |
|-------------|------|---------|
| algo_metrics_daily | load_algo_metrics_daily.py | Market health, trend templates, completeness scores |

**Total: 1 loader**

---

## Schedule Timeline (ET - Eastern Time)

```
3:30am — loadstocksymbols (symbols refresh)
4:00am — loadpricedaily + loadpriceweekly + loadpricemonthly + loadetfpricedaily/weekly/monthly (6 parallel)
10:00am — loadannualincomestatement + loadquarterlyincomestatement + ... (8 parallel financials)
11:00am — loadearningshistory + loadearningsrevisions + ... (4 parallel earnings)
12:00pm — loadanalystsentiment + loadsectors + ... (10 parallel market/econ)
1:00pm — loadanalystsentiment + loadsentiment + ... (5 parallel sentiment)
5:00pm — loadbuyselldaily + loadbuysellweekly + ... (5 parallel signals)
5:15pm — load_algo_metrics_daily (after signals complete)
```

**Note:** Times are staggered to: (1) distribute API load, (2) respect data dependencies, (3) avoid resource contention

---

## Missing Loaders in Current Terraform

Currently implemented (7 stubs):
- stock_symbols ✓
- stock_prices ✓
- company_fundamentals ✓
- market_indices ✓
- econdata ✓
- feargreed ✓
- sector_ranking ✓

Missing (33):
- All price loaders (weekly, monthly, ETF)
- All financial statement loaders (annual, quarterly, TTM - 8 total)
- All trading signal loaders (5 total)
- All earnings loaders (4 total)
- Market/economic loaders (except indices/feargreed/econ)
- Sentiment/analysis loaders (5 total)
- Algo metrics loader
- Calendar loader

---

## Terraform Implementation Map

Each loader becomes:
1. **`aws_ecs_task_definition`** — Container configuration with resource requirements
2. **`aws_cloudwatch_log_group`** — Log stream for debugging
3. **`aws_cloudwatch_event_rule`** — Schedule (cron expression)
4. **`aws_cloudwatch_event_target`** — ECS task to execute on schedule

### Resource Sizing Logic

| Category | CPU | Memory | Timeout | Reason |
|----------|-----|--------|---------|--------|
| Price Data | 512 | 1024 | 600s | Requires bulk API calls, market data aggregation |
| Financial Statements | 256 | 512 | 1200s | Rate-limited APIs, large dataset processing |
| Trading Signals | 256 | 512 | 900s | Algorithm computation on historical data |
| Earnings | 256 | 512 | 600s | External calendar + analyst data |
| Market/Economic | 256 | 256 | 300s | Single API endpoint calls, light processing |
| Sentiment/Analysis | 256 | 256 | 600s | Aggregated data, sentiment scoring |
| Stock Symbols | 128 | 256 | 300s | Reference data, minimal processing |
| Algo Metrics | 256 | 256 | 600s | Computation from loaded data, not external APIs |

---

## What Gets Generated

### File: `terraform/modules/loaders/loaders_full.tf`
Complete Terraform code with:
- `locals.all_loaders` map (40 entries, replacing `default_loaders`)
- `aws_ecs_task_definition.loader` resources (40 instances)
- `aws_cloudwatch_log_group.loader` resources (40 instances)
- `aws_cloudwatch_event_rule.*` for each scheduled loader (25+ rules)
- `aws_cloudwatch_event_target.*` for each scheduled loader (25+ targets)

### File: `terraform/modules/loaders/outputs_full.tf`
Updated outputs:
- All 40 loader task definition ARNs
- All scheduled EventBridge rules
- All EventBridge targets

### File: `.github/workflows/deploy-loaders.yml`
Updated workflow:
- Remove CloudFormation template reference
- Use Terraform deployment instead
- Trigger on changes to `terraform/modules/loaders/`
- Same pre-flight checks, same rollback on failure

---

## Next Steps

1. **Generate Terraform code** for all 40 loaders with proper resource sizing
2. **Create EventBridge rules** for all scheduled loaders with correct cron expressions
3. **Update GitHub workflow** to deploy via Terraform
4. **Test locally** with Docker Compose + mock data
5. **Deploy to AWS** via GitHub Actions
6. **Monitor first run** to verify all loaders execute on schedule

---

## Verification Checklist

After deployment:
```bash
# Verify all 40 loaders registered
aws ecs describe-task-definition --task-definition stocks-* --region us-east-1 | grep family | wc -l

# Verify all EventBridge rules exist
aws events list-rules --name-prefix stocks-loader --region us-east-1 | jq '.Rules | length'

# Verify all targets configured
aws events list-targets-by-rule --rule stocks-stock-prices-daily-schedule --region us-east-1

# Test one loader manually
aws ecs run-task --cluster stocks-dev-cluster --task-definition stocks-stock-prices-daily-loader --launch-type FARGATE --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx]}"

# Check logs
aws logs tail /ecs/stocks-stock-prices-daily-loader --follow
```
