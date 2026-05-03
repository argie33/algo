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

## AWS Production (EventBridge rules)

For AWS deployment, translate the above cron to EventBridge schedule
expressions targeting Lambda or ECS tasks:

```
INTRADAY:    rate(90 minutes)        + filter for market hours
EOD:         cron(30 17 ? * MON-FRI *)
WEEKLY:      cron(0 8 ? * SAT *)
MONTHLY:     cron(0 9 1-7 ? * SAT *)
PATROL_4H:   cron(0 0/4 ? * MON-FRI *)
PATROL_FULL: cron(0 23 ? * * *)
```

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
