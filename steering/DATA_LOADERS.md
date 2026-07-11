# Data Loader Orchestration

Live data pipeline: 40+ loaders organized into 5 Step Functions pipelines, scheduled 2:15 AM and 4:05 PM ET.

---

## Loader Execution Model

**Unified Runner:** `loaders/runner.py` is single entry point for all loaders. Each loader defines:
- `LOADER_TYPE` — 'critical' (Fargate, guaranteed resources) or 'auxiliary' (Fargate, batched)
- `REQUIRED_SYMBOLS` — which symbols this loader covers (or None for all)
- `SCHEMA` — output table schema with field validation
- `COMPLETENESS_THRESHOLD` — failure threshold (e.g., 95% coverage required)

**Config Management:** `utils/loaders/config.py` LoaderConfigManager provides:
- Per-loader parallelism tuning (min/max constraints from database)
- Adaptive batching (reduces parallelism when RDS connection pool approaches saturation)
- In-memory cache of loader config (5-minute TTL, refreshed on-demand)
- Fail-fast if config invalid or missing

**Example:** Price loader runs 3000+ symbols in batches of 100 → LoaderConfigManager queries `algo_config` table for `price_loader_parallelism` (default 10) → Parallel ECS tasks fetch symbols → Results validated for completeness → Loaded to `price_daily` table.

---

## Loader Pipeline: 2:15 AM (Morning)

**Purpose:** Freshest data for 9:30 AM signal generation.

**Sequence (all parallel except Terminal steps):**
1. `load_prices` — Fetches OHLCV from Alpaca (3000+ symbols)
2. `load_technical_data_daily` — Computes 50/200-day SMA, momentum, ATR, ADX from price_daily (vectorized in-database). Also computes VCP (Volatility Contraction Pattern) data for signal quality scoring.
3. `load_swing_trader_scores` — Swing score calculation (auxiliary, non-blocking if timeout)

**Timing:**
- Starts 2:15 AM (pre-market, 7:15 hours before 9:30 AM open)
- Must complete by 9:30 AM (signal generation depends on it)
- Typical duration: 45-60 minutes for all 3 loaders

**Failure Handling:**
- Price loader timeout → entire pipeline fails (no market data = no trading)
- Technical data timeout → use prior day's SMA (market_exposure already has fallback calculation)
- Swing scores timeout → skip (auxiliary, trading continues without swing filters)

---

## Loader Pipeline: 4:05 PM (EOD)

**Purpose:** End-of-day reconciliation and next-day preparation.

**Sequence (staged):**

**Stage 1 (Parallel, ~5 min):**
- `load_prices` — Close and volume
- `load_market_exposure_daily` — Computes 12 market factors (12-month yield, VIX, SPY price, etc.)
- `load_fred_economic_data` — Fetches FRED economic series + DXY_ICE from Yahoo Finance

**Stage 2 (Parallel, ~15 min, after Stage 1):**
- `load_quality_metrics` — yfinance + SEC filings (quality score, debt/equity, ROA, etc.)
- `load_growth_metrics` — Revenue growth, earnings growth (SEC + yfinance)
- `load_value_metrics` — P/E, P/B, P/S (daily prices)
- `load_positioning_metrics` — Short interest, institutional ownership
- `load_stability_metrics` — Dividend yield, payout ratio

**Stage 3 (Parallel, ~30 min, after Stage 2):**
- `load_stock_scores` — Composite score calculation (depends on all metric loaders)

**Timing:**
- Starts 4:05 PM (35 minutes after 3:30 PM market close)
- Must complete by 4:35 PM for 5:30 PM orchestrator run (uses scores for position sizing)

**Failure Handling:**
- Market exposure timeout → use defaults (12-month yield=3.5%, VIX=18, market_stage=2)
- Any metric loader (quality/growth/value/positioning/stability) timeout → score calculates from available metrics (min 3 metrics required)
- Stock scores timeout → use prior day's scores (no new entries, no re-weighting)

---

## AWS Batch Sizing & Parallelism Tuning

**Problem:** yfinance + SEC filing fetches hit rate limits when parallelizing across 3000+ symbols.

**Solution:** Adaptive batch sizing per environment.

**Metric loaders (quality, growth, value, positioning, stability):**
- **Local:** batch=1000, parallelism=unlimited (no rate limit from yfinance)
- **AWS:** batch=100, parallelism=5 (reduces parallel requests, avoids rate limit cascade)
- **Timeout:** 600 seconds (10 minutes per task, sufficient for 100-symbol batches)
- **Memory:** 1024 MB (sufficient for parallel DataFrame operations + RDS connection pool)
- **Resource:** FARGATE (guaranteed, not SPOT — data quality is safety-critical)

**Price loader:**
- **Batch:** 1000 symbols per parallel task (Alpaca has different rate limit than yfinance)
- **Parallelism:** 10 (Alpaca's websocket rate limit: ~100 symbols/sec, so 10 parallel × 1000 = 10k sym/sec)
- **Timeout:** 300 seconds (5 minutes, price fetch is fast)
- **Memory:** 512 MB
- **Resource:** FARGATE

**Query:** Check actual parallelism in use:
```sql
SELECT loader_name, parallelism_override, batch_size_override
FROM algo_config
WHERE loader_name IN ('load_quality_metrics', 'load_growth_metrics', 'load_prices');
```

---

## Completeness Validation & Recovery

**Completeness Validator** (`utils/loaders/completeness_validator.py`):
- Counts successfully-loaded symbols
- Compares to `REQUIRED_SYMBOLS` or active portfolio
- Fails if coverage < threshold (typically 95%)
- Returns explicit reason: "insufficient_price_history", "rate_limit_exceeded", "sec_filing_unavailable"

**At-Risk Loaders** (lower coverage, higher timeout risk):
- `load_quality_metrics` — 87% coverage (some micro-caps lack SEC filings)
- `load_positioning_metrics` — 92% coverage (small-cap short interest delayed)
- `load_analyst_sentiment` — 85% coverage (no coverage for micro-caps, OTC stocks)

**Recovery Procedure (if EOD loader times out):**
1. Check CloudWatch: `/ecs/algo-cluster` for loader task logs
2. Query data_loader_status:
   ```sql
   SELECT table_name, completion_pct, last_updated, reason
   FROM data_loader_status
   WHERE table_name = 'quality_metrics'
   ORDER BY last_updated DESC LIMIT 1;
   ```
3. If completion_pct < 70%: Increase ECS memory to 2048 MB, reduce batch to 50
4. If completion_pct > 70%, completeness_pct > 85%: Data is acceptable, proceed to stock_scores
5. If still failing: Check rate limit logs (yfinance errors), wait 5 minutes, re-trigger manually

**Manual Loader Re-Trigger:**

**Option 1: GitHub Actions (Recommended)**
```bash
# Run any loader via GitHub Actions workflow
gh workflow run run-loader.yml \
  -f loader_name=load_dxy_index \
  -R owner/algo

# Or use the web UI:
# GitHub → Actions → "Run Loader" → Run workflow → Enter loader name
```

**Option 2: AWS CLI (Direct)**
```bash
# Trigger morning pipeline (2:15 AM re-run)
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:us-east-1:xxx:stateMachine:algo-morning-pipeline \
  --name "manual-trigger-$(date +%s)"

# Trigger EOD pipeline (4:05 PM re-run)
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:us-east-1:xxx:stateMachine:algo-eod-pipeline \
  --name "manual-trigger-$(date +%s)"
```

**Why GitHub Actions?** Logs visible in GitHub UI, no AWS CLI needed, easier audit trail.

---

## Data Freshness & Staleness Detection

**Data Patrol:** `scripts/data_patrol.py` runs every 5 minutes, checks table freshness.

**Freshness Thresholds (max age before ALERT):**
| Table | Max Age | Why |
|-------|---------|-----|
| price_daily | 30 min (trading hours) | Used for intra-day scoring |
| technical_data_daily | 1 day | Computed from price_daily |
| market_exposure_daily | 4 hours | Used for position sizing |
| quality_metrics | 7 days | Slow-changing (only loads EOD) |
| stock_scores | 4 hours | Needs fresh for entries |

**Alert Threshold Exceeded:**
- If any loader missing for > threshold → Email ops, log ERROR
- Data patrol continues; traders aware via dashboard

**Dashboard Display:**
- Green: All loaders fresh (within threshold)
- Yellow: One loader stale (>threshold but <2× threshold)
- Red: Loader critical (>2× threshold)

---

## For Detailed Reference

See:
- `steering/GOVERNANCE.md` — Data quality principles, fail-fast rules
- `steering/OPERATIONS.md` — Troubleshooting loader failures, dashboard diagnostics
- `loaders/runner.py` — Unified loader entry point
- `utils/loaders/config.py` — LoaderConfigManager API
