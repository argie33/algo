# Data Loader Orchestration

Live data pipeline: 40+ loaders organized into 4 Step Functions pipelines (morning 2:00 AM, reference 9:15 AM, EOD 4:05 PM, computed-metrics 7:00 PM ET; MON-FRI).

---

## Loading Architecture (updated 2026-07-14)

Design principles (the "panel data" model — bulk everything, fetch once, write incrementally):

1. **One query per table per run, not one per symbol.** Loaders prefetch shared data
   (metric tables, watermarks, freshness maps) in `_prepare_batch_context()` and read
   from in-memory dicts in the per-symbol path. Per-symbol `WHERE symbol = %s` round
   trips are treated as bugs (N+1).
2. **Fetch each external payload at most once per run.** SEC companyfacts is fetched
   once per symbol and reused across all 6 statement/period combos (symbol-major
   iteration + per-CIK LRU in `SecEdgarClient`). yfinance quoteSummary snapshots skip
   symbols whose `yfinance_snapshot` row is fresher than `YFINANCE_SNAPSHOT_MAX_AGE_HOURS`
   (default 20h) — crash-retries resume from the unfetched tail instead of restarting.
3. **Derive, don't re-fetch.** Weekly/monthly bars are derived in SQL from
   `price_daily` after every daily load (`derive_aggregate_prices` in
   `loaders/load_prices.py`) — labeled identically to the historical yfinance rows
   (weekly = Monday, monthly = 1st). No 1wk/1mo interval is fetched from yfinance.
4. **Write incrementally with watermarks.** `technical_data_daily` computes over its
   full 400-day lookback but writes only rows past each symbol's watermark (7-day
   healing overlap; `TECH_FULL_REFRESH=true` forces a full rewrite). The price loader
   trims each symbol's fetched rows to its OWN watermark before writing.
5. **Batch the write path.** Price batches stage all symbols' rows through one chunked
   `bulk_insert` (staging COPY + upsert) instead of one staging-table cycle per symbol;
   watermarks are read in one query and advanced in one transaction per batch, only
   after the insert commits. `LOADER_CHUNK_SIZE` is the DB insert chunk (5000), not an
   API batch.
6. **All yfinance traffic goes through one funnel.** `YFinanceWrapper` (serialized,
   0.3s min interval per process) + the PostgreSQL-backed shared IP circuit breaker
   (`yfinance_ip_ban` table) coordinate all ECS tasks behind the shared NAT IP. Raw
   `yf.download`/`yf.Ticker` call sites outside the funnel are treated as bugs.
7. **Don't discard good data on transient blips.** Failed price batches get one
   sequential retry pass; validation failures mark explicit `data_unavailable` rows
   rather than zeroing out completed work. Locks (DynamoDB, TTL tied to
   `LOADER_SLA_TIMEOUT_SECONDS`) outlive the longest legitimate run and release in
   `finally`.

Scaling note: this architecture (bulk panel queries, incremental writes, derived
aggregates) is what lets the same Postgres + ECS stack absorb higher-frequency
loading later — an intraday cadence is "run the same incremental loaders more often,"
not a redesign.

**Alpaca Market Data parallel track (2026-07-14, live-verified):** the FREE Alpaca
plan serves full SIP consolidated-tape historical bars for anything older than 15
minutes (200 calls/min; ~200 symbols per request → the whole universe in ~43 calls /
~20s). `PRICE_DATA_SOURCE=alpaca` routes daily-bar batches through
`utils/external/alpaca_market_data.py` with automatic yfinance fallback; default
remains yfinance. Evaluate with `python scripts/compare_price_sources.py` (live
result: 99.4% coverage, close diff median 0.0000%, volume ratio median 1.000 = true
SIP). Switch when coverage ~100% / close p95 <0.5% / volume median ~1.0 hold across
several trading days. Index symbols (^VIX, ^GSPC...) always stay on yfinance. The
$99/mo plan is only needed for intraday/real-time (recent-SIP + websocket + 10k/min).

---

## Loader Execution Model

**Unified Runner:** `loaders/runner.py` is the shared entry point for most loaders. Each loader defines:
- `table_name`, `primary_key`, `watermark_field` (per-symbol high-water-mark tracking in `loader_watermarks`)
- `_prepare_batch_context()` — bulk prefetch hook, called once before the symbol loop
- `fetch_incremental(symbol, since)` — returns rows or explicit `data_unavailable` markers

**Config Management:** `utils/loaders/config.py` LoaderConfigManager provides per-loader
parallelism (DynamoDB `algo-loader-config` → env → constraint max), with CloudWatch-based
adaptive reduction when RDS proxy connections approach saturation. yfinance- and
SEC-facing loaders are clamped to parallelism 1-2 to protect the shared NAT IP.

**Data sources (actual, per code):**
- **Prices (OHLCV):** yfinance `yf.download` batches — the sole OHLCV source. Alpaca is
  broker/trading API only (orders, positions); it is NOT used for bulk price data.
- **Fundamentals/filings:** SEC EDGAR (`SecEdgarClient`, 2 req/s per task, companyfacts
  cached per CIK per run).
- **Economic series:** FRED (4 series) + DXY via yfinance (`DX-Y.NYB`).
- **Snapshot metrics (PE/holdings/analyst/etc.):** yfinance quoteSummary once per symbol
  per day into `yfinance_snapshot`; downstream metric loaders read the table, not the API.

---

## Pipelines (Step Functions, EventBridge Scheduler, America/New_York)

**Morning (2:00 AM):** prices (1d, FAIL-CLOSED) → market health ∥ trend template →
market exposure → technical data → sector ranking.

**Reference (9:15 AM):** yfinance_derived_metrics (reads `yfinance_snapshot`, writes 7 tables).

**EOD (4:05 PM):** stock symbols → bulk prices (FAIL-CLOSED) → trend template →
technical data (FAIL-CLOSED) → market health → buy/sell signals → algo metrics →
sector/industry/performance → FRED → market exposure → sentiment → data patrol →
orchestrator dry-run validation.

**Computed metrics (7:00 PM):** yfinance snapshot → financials_all (SEC, symbol-major) →
growth → quality → value → stability → stock scores.

**Failure handling:**
- Price or technical-data failure halts the dependent chain (`PriceLoadFailureHalt`,
  `TechDataFailureHalt`); everything else is fail-open with explicit `data_unavailable`.
- Failed price batches get one sequential retry pass before the run is declared failed.
- `loader-timeout-guardian` Lambda (5 min) stops ECS tasks past their `LOADER_TIMEOUT`;
  `data-freshness-monitor` Lambda publishes `AlgoDataFreshness` metrics hourly 2AM-10AM.

---

## Completeness Validation & Recovery

- Upstream gates: `_check_upstream_completeness` requires `data_loader_status`
  completion ≥ 95% for hard dependencies (technical←price, buy_sell←technical).
- Coverage denominators use price_daily symbol counts, not the raw active-symbol list.

**Manual Loader Re-Trigger:**

```bash
# GitHub Actions (recommended; logs in the UI)
gh workflow run run-loader.yml -f loader_name=<name> -R owner/algo

# AWS CLI (direct)
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:us-east-1:xxx:stateMachine:algo-eod-pipeline \
  --name "manual-trigger-$(date +%s)"
```

**Recovery from a stalled/failed loader:** see `steering/LOADER_RECOVERY_GUIDE.md` and
`python scripts/monitor_data_staleness.py`.

---

## Data Freshness & Staleness Detection

| Table | Max Age | Writer |
|-------|---------|--------|
| price_daily | 1 day | yfinance 1d fetch |
| price_weekly / price_monthly (+etf_) | 7 days | **derived in SQL** after each daily load |
| technical_data_daily | 1 day | incremental write past per-symbol watermark |
| yfinance_snapshot | ~1 day | freshness-skip fetch (20h horizon) |
| quality/growth/value/stability metrics | 7 days | computed from SEC + snapshot tables |
| stock_scores | 4 hours | batch-context panel computation |

Alerts: data patrol + freshness monitor publish to CloudWatch/SNS; dashboard shows
green/yellow/red per table.

---

## For Detailed Reference

- `steering/GOVERNANCE.md` — data quality principles, fail-fast rules
- `steering/OPERATIONS.md` — troubleshooting, deploy chain (CI success auto-deploys; a
  failed CI run silently skips deployment — always verify after pushing)
- `loaders/runner.py`, `utils/optimal_loader.py`, `utils/bulk_insert_manager.py`
- `utils/external/yfinance.py` + `utils/external/yfinance_circuit_breaker.py`
- `utils/external/sec_edgar_client.py` (companyfacts LRU)
