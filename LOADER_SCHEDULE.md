# Loader Run Schedule

This is the operational discipline document for running data loaders. The
algo's accuracy depends entirely on having fresh, valid data — this is how we
guarantee that.

## Pipeline Flow

```
                                    ┌──────────────┐
                                    │ DATA PATROL  │
                                    │  (watchdog)  │
                                    └──────┬───────┘
                                           │ approves
                                           ▼
   ┌────────────────────────────────────────────────────────┐
   │            LOADER RUNNERS BY FREQUENCY                 │
   │                                                        │
   │  INTRADAY (4-6× per trading day)                       │
   │    loader_pricing_loader.py  (price_daily, real-time)  │
   │                                                        │
   │  EOD (5pm ET, every trading day)                       │
   │    loader_pricing_loader.py        (final close prices)│
   │    loader_technicals_loader.py     (RSI/MACD/SMA/ATR)  │
   │    loader_buysell_loader.py        (Pine signals)      │
   │    load_algo_metrics_daily.py      (trend, market, SQS)│
   │    loader_sector_ranking_loader.py                     │
   │    loader_industry_ranking_loader.py                   │
   │                                                        │
   │  WEEKLY (Saturday 8am ET)                              │
   │    loader_pricing_loader.py --weekly                   │
   │    loader_buysell_loader.py --weekly                   │
   │    loader_stock_scores_loader.py    (IBD composite)    │
   │    loader_value_trap_scores_loader.py                  │
   │    loader_aaii_sentiment_loader.py                     │
   │    loader_insider_loader.py                            │
   │    loader_analyst_upgrade_loader.py                    │
   │                                                        │
   │  MONTHLY (1st Saturday)                                │
   │    loader_pricing_loader.py --monthly                  │
   │    loader_buysell_loader.py --monthly                  │
   │    loader_growth_metrics_loader.py                     │
   │    loader_key_metrics_loader.py                        │
   │                                                        │
   │  QUARTERLY (5 days after quarter end)                  │
   │    loader_earnings_history_loader.py                   │
   │    loader_earnings_metrics_loader.py                   │
   │                                                        │
   │  STATIC (run once, refresh as needed)                  │
   │    loader_company_profile_loader.py                    │
   │    loader_stock_symbols_loader.py                      │
   └────────────────────────┬───────────────────────────────┘
                            │
                            ▼
   ┌────────────────────────────────────────────────────────┐
   │            DATA PATROL (post-load validation)          │
   │  - staleness, NULL, zero-rows, sequence, sanity         │
   │  - cross-validate vs Alpaca (top symbols)               │
   └────────────────────────┬───────────────────────────────┘
                            │ approves
                            ▼
   ┌────────────────────────────────────────────────────────┐
   │            ORCHESTRATOR (algo_orchestrator.py)         │
   │  Phase 1: data_freshness — fail-closed if patrol failed│
   │  Phases 2-7: circuit breakers → monitor → exits → ...  │
   └────────────────────────────────────────────────────────┘
```

## Cron Expressions (operational)

```cron
# === INTRADAY (every 90 min, 9:30am-4pm ET, Mon-Fri) ===
30,0 9-15 * * 1-5  cd /c/Users/arger/code/algo && python3 -m loaders.loader_pricing_loader --intraday >> /var/log/algo/intraday.log 2>&1

# === EOD (5:30pm ET, Mon-Fri) — full daily refresh ===
30 17 * * 1-5  cd /c/Users/arger/code/algo && bash run_eod_loaders.sh >> /var/log/algo/eod.log 2>&1

# === EOD ALGO RUN (6pm ET, Mon-Fri) — after data refreshed ===
0 18 * * 1-5  cd /c/Users/arger/code/algo && python3 algo_orchestrator.py >> /var/log/algo/orchestrator.log 2>&1

# === WEEKLY (Saturday 8am ET) ===
0 8 * * 6  cd /c/Users/arger/code/algo && bash run_weekly_loaders.sh >> /var/log/algo/weekly.log 2>&1

# === MONTHLY (1st Saturday 9am ET) ===
0 9 1-7 * 6  cd /c/Users/arger/code/algo && bash run_monthly_loaders.sh >> /var/log/algo/monthly.log 2>&1

# === DATA PATROL (every 4 hours during trading) ===
0 */4 * * 1-5  cd /c/Users/arger/code/algo && python3 algo_data_patrol.py --quick >> /var/log/algo/patrol.log 2>&1

# === DATA PATROL (full nightly, 11pm ET) ===
0 23 * * *  cd /c/Users/arger/code/algo && python3 algo_data_patrol.py --validate-alpaca >> /var/log/algo/patrol.log 2>&1
```

## AWS Production — IaC via GitHub Actions

The same loaders that run locally must work identically in AWS. Architecture:

```
GitHub Actions (CI/CD)
      │ pushes IaC + container images
      ▼
AWS CodeBuild → ECR (loader Docker images, 1 per loader phase)
      │
      ▼
EventBridge (cron schedules, mirrors local cron)
      │ triggers
      ▼
ECS Fargate Tasks (run loader containers)
      │ writes to
      ▼
RDS PostgreSQL (same schema as local)
      │ algo reads from
      ▼
Lambda (webapp/lambda/index.js — Express via serverless-http)
      │ serves
      ▼
CloudFront → S3 static frontend
```

### EventBridge Schedule Rules

```
INTRADAY:    rate(90 minutes)         + filter Mon-Fri 9:30-16:00 ET
EOD:         cron(30 17 ? * MON-FRI *)
WEEKLY:      cron(0 8 ? * SAT *)
MONTHLY:     cron(0 9 1-7 ? * SAT *)
PATROL_4H:   cron(0 0/4 ? * MON-FRI *)
PATROL_FULL: cron(0 23 ? * * *)
```

### GitHub Actions Workflow

A single workflow file (`.github/workflows/deploy.yml`) triggers on push to
`main`. It:

1. Runs `python3 FULL_BUILD_VERIFICATION.py` and `python3 algo_data_patrol.py --quick`
   — fail the build if either reports critical issues
2. Builds one Docker image per loader phase (`Dockerfile.eod`, `Dockerfile.intraday`)
3. Pushes images to ECR (one per phase, tagged with commit SHA)
4. Deploys CloudFormation/SAM updates to update EventBridge rules + ECS task defs
5. Deploys Lambda updates for the webapp API
6. Deploys static frontend to S3 + invalidates CloudFront

Reference templates already exist in repo:
- `template-webapp-lambda.yml` (SAM)
- `template-step-functions-phase-d.yml`
- `template-tier1-api-lambda.yml`
- `template-tier1-cost-optimization.yml`

### Local-vs-AWS Parity Rules

To guarantee that local-tested code runs identically in production:

1. **Same Python version** (3.11 in local, 3.11 in ECS task definition)
2. **Same environment variables** loaded from `.env.local` locally and AWS
   Secrets Manager / Parameter Store in production
3. **Same DB schema** — migrations applied via single canonical SQL files in
   `migrations/` (run by both local setup script and AWS CodeBuild step)
4. **No local-only paths** — every loader uses `Path(__file__).parent` to
   resolve relative paths
5. **All output to stdout/stderr** — never write logs to local-only files;
   ECS captures stdout/stderr to CloudWatch
6. **Database connection from env only** — both local and AWS read DB_HOST etc.
   from environment, never hardcoded
7. **Idempotent loaders** — every loader uses `ON CONFLICT DO UPDATE` so
   re-runs don't duplicate
8. **Patrol-gated** — every wrapper script (local + ECS task) calls
   `algo_data_patrol.py --quick` before AND after loaders; fails closed

## The Wrapper Script Pattern

Each grouping has a wrapper script that:
1. Runs `algo_data_patrol.py --quick` BEFORE loaders to verify DB sanity
2. Runs the loaders for that frequency tier (parallelizing where safe)
3. Runs `algo_data_patrol.py` AFTER loaders to verify the writes
4. Aborts and alerts if patrol detects critical issues

Example `run_eod_loaders.sh`:

```bash
#!/bin/bash
set -e
cd "$(dirname "$0")"

# Pre-load patrol (sanity check)
python3 algo_data_patrol.py --quick || {
    echo "Pre-load patrol FAILED — aborting EOD load"
    exit 1
}

# Load in dependency order
python3 -m loaders.loader_pricing_loader --eod
python3 -m loaders.loader_technicals_loader
python3 -m loaders.loader_buysell_loader
python3 load_algo_metrics_daily.py
python3 -m loaders.loader_sector_ranking_loader
python3 -m loaders.loader_industry_ranking_loader

# Post-load patrol (validation)
python3 algo_data_patrol.py
```

## Decision Tree for Mid-Day Runs

When the orchestrator runs intraday:
1. **Pine Script signals** are computed at bar close — today's BUY/SELL
   signals don't exist until 4:00pm ET. We use the most recent COMPLETED
   day's signals, never trade on an in-progress bar.
2. **Position monitoring** uses live prices (intraday loader).
3. **Stop-raising decisions** use today's intraday low to identify if a stop
   has been touched.
4. **New entries** are computed against yesterday's signals + today's
   live price, but rate-limited to once per day per symbol via idempotency.

## When to Re-Run

| Condition | Action |
|---|---|
| `data_patrol_log` shows CRITICAL after a load | Re-run that loader, then re-patrol |
| Orchestrator Phase 1 fails-closed | Identify which table is stale, run that loader |
| Alpaca cross-validation > 5% mismatch | Investigate the source feed, may need to roll back |
| New symbol added to universe | Run `loader_stock_symbols_loader.py` + backfill price_daily |
| API limit hit (40+ identical OHLC) | Wait 1 hour, retry. If persistent, check broker key. |

## Monitoring

- `data_patrol_log` table → all severity findings persisted with run_id
- `algo_audit_log` table → every algo decision and phase result
- `data_loader_status` table → freshness state per source
- `/api/algo/data-status` endpoint → live UI dashboard
- `/api/algo/patrol-log` endpoint → recent patrol findings

The frontend's "DATA HEALTH" tab surfaces all of this in real-time.

## Cost Discipline

We use ONLY existing API keys:
- **Alpaca** (free with our paper account) — used for cross-validation
  and live price polling
- **Pine Script** (no API; runs in TradingView on your account)
- **Yahoo / yfinance** (free) — used by existing loaders
- **FRED** (free with `FRED_API_KEY`)

We do NOT integrate paid data feeds (Bloomberg, Refinitiv, etc.).
The patrol's cross-validation uses Alpaca's free data tier.

## The Three Promises

1. **Real data only.** No mock, no synthetic, no defaults — fail closed.
2. **Best research.** Every threshold cited in `ALGO_ARCHITECTURE.md`.
3. **No silos.** Pine signals + scores + market + portfolio all consulted.
