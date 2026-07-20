# Data Loader Orchestration

Live data pipeline: 40+ loaders organized into 4 Step Functions pipelines (morning 2:00 AM, reference 9:15 AM, EOD 4:05 PM, computed-metrics 7:00 PM ET; MON-FRI).

---

## Loading Architecture (updated 2026-07-19, Session 275)

Design principles (the "panel data" model — bulk everything, fetch once, write incrementally):

1. **One query per table per run, not one per symbol.** Loaders prefetch shared data
   (metric tables, watermarks, freshness maps) in `_prepare_batch_context()` and read
   from in-memory dicts in the per-symbol path. Per-symbol `WHERE symbol = %s` round
   trips are treated as bugs (N+1).
2. **Fetch each external payload at most once per run.** SEC companyfacts are fetched
   once per symbol and reused across all 6 statement/period combos (symbol-major
   iteration + per-CIK LRU in `SecEdgarClient`). Crash-retries resume from the unfetched 
   tail instead of restarting.
3. **Derive, don't re-fetch.** Weekly/monthly bars are derived in SQL from
   `price_daily` after every daily load (`derive_aggregate_prices` in
   `loaders/load_prices.py`) — labeled consistently (weekly = Monday, monthly = 1st). 
   No 1wk/1mo interval is fetched from external APIs.
4. **Write incrementally with watermarks.** `technical_data_daily` computes over its
   full 400-day lookback but writes only rows past each symbol's watermark (7-day
   healing overlap; `TECH_FULL_REFRESH=true` forces a full rewrite). The price loader
   trims each symbol's fetched rows to its OWN watermark before writing.
5. **Batch the write path.** Price batches stage all symbols' rows through one chunked
   `bulk_insert` (staging COPY + upsert) instead of one staging-table cycle per symbol;
   watermarks are read in one query and advanced in one transaction per batch, only
   after the insert commits. `LOADER_CHUNK_SIZE` is the DB insert chunk (5000), not an
   API batch.
6. **Coordinate rate limits via shared config.** `LoaderConfigManager` provides per-loader
   parallelism (DynamoDB `algo-loader-config` → env → constraint max), with CloudWatch-based
   adaptive reduction when RDS proxy connections approach saturation. SEC-facing loaders
   are clamped to parallelism 1-2 to protect rate limits.
7. **Don't discard good data on transient blips.** Failed price batches get one
   sequential retry pass; validation failures mark explicit `data_unavailable` rows
   rather than zeroing out completed work. Locks (DynamoDB, TTL tied to
   `LOADER_SLA_TIMEOUT_SECONDS`) outlive the longest legitimate run and release in
   `finally`.

Scaling note: this architecture (bulk panel queries, incremental writes, derived
aggregates) is what lets the same Postgres + ECS stack absorb higher-frequency
loading later — an intraday cadence is "run the same incremental loaders more often,"
not a redesign.

**Alpaca Market Data is the PRIMARY daily-bar source (Session 275+):** the FREE Alpaca
plan serves full SIP consolidated-tape historical bars for anything older than 15
minutes (200 calls/min; ~200 symbols per request → the whole universe in ~43 calls /
~20s). `PRICE_DATA_SOURCE` (terraform `price_data_source`, prod default `alpaca`)
routes daily-bar batches through `utils/external/alpaca_market_data.py`. Symbols Alpaca
doesn't serve (index symbols, delisted stragglers) are marked explicitly `data_unavailable`
rather than falling back to deprecated yfinance API. Compare historical sources anytime 
with `python scripts/compare_price_sources.py` (prior result: 99.4% coverage, close diff
median 0.0000%, volume ratio median 1.000 = true SIP). **Session 275+:** yfinance_snapshot
fully deprecated from all loaders (removed from terraform pipeline and trigger-loaders).
The $99/mo plan is only needed for intraday/real-time (recent-SIP + websocket + 10k/min).

---

## Loader Execution Model

**Unified Runner:** `loaders/runner.py` is the shared entry point for most loaders. Each loader defines:
- `table_name`, `primary_key`, `watermark_field` (per-symbol high-water-mark tracking in `loader_watermarks`)
- `_prepare_batch_context()` — bulk prefetch hook, called once before the symbol loop
- `fetch_incremental(symbol, since)` — returns rows or explicit `data_unavailable` markers

**Config Management:** `utils/loaders/config.py` LoaderConfigManager provides per-loader
parallelism (DynamoDB `algo-loader-config` → env → constraint max), with CloudWatch-based
adaptive reduction when RDS proxy connections approach saturation. SEC-facing loaders are 
clamped to parallelism 1-2 to protect rate limits.

**Data sources (actual, per code, Session 275+):**
- **Prices (OHLCV):** Alpaca Market Data multi-symbol daily bars (SIP, free plan) via
  `DataSourceRouter.fetch_ohlcv_batch`. Symbols Alpaca doesn't serve are marked 
  `data_unavailable`. Weekly/monthly bars are DERIVED in SQL from dailies (never fetched).
- **Fundamentals/filings:** SEC EDGAR (`SecEdgarClient`, 2 req/s per task, companyfacts
  cached per CIK per run).
- **Economic series:** FRED (4 series: T10Y2Y, FEDFUNDS, BAMLH0A0HYM2, ICSA) + DXY (currency index).
- **Snapshot metrics (PE/holdings/analyst/etc.):** SEC EDGAR for fundamentals, FINRA for short interest.
  (Session 275: yfinance_snapshot fully deprecated; was quoteSummary fetches per symbol per day)
- **Short interest:** FINRA Query API "Consolidated Short Interest" dataset (Session 298;
  `POST https://api.finra.org/data/group/otcMarket/name/ConsolidatedShortInterest`, no API
  key). The old CSV endpoint (`finra.org/sites/default/files/shortinterest/...`) was 404
  for years - `utils/finra_short_interest.py` now paginates this API for the latest
  bi-weekly settlement cycle (15th/EOM, ~2-3 week publish lag) covering NYSE/Nasdaq/OTC
  (~22k symbols/cycle). FINRA reports raw share counts, not a percent; `short_pct` is
  computed against `company_info_sec.shares_outstanding` (SEC DEI), so symbols without an
  SEC shares-outstanding figure are marked `data_unavailable` even when FINRA has data.
  Lifted `positioning_metrics` availability from 58.9% -> ~93% and `stock_scores`
  tradeable coverage (>=70% completeness) from 53.4% -> ~64%.
- **Institutional holdings (13F):** still unavailable (`institutional_holdings_13f`).
  Form 13F is filed by the institutional manager under their OWN CIK with CUSIP-level
  holdings, not cross-indexed under the issuer's CIK - there's no per-issuer 13F lookup.
  A real implementation needs the SEC's bulk quarterly structured datasets
  (sec.gov/files/structureddata/data/form-13f-data-sets/*.zip, INFOTABLE.tsv) aggregated
  by CUSIP, which requires a CUSIP->ticker crosswalk SEC does not publish for free (CUSIP
  is licensed by CUSIP Global Services). `utils/sec_form13f_aggregator.py` currently only
  checks whether the ISSUER'S OWN CIK filed a `13F-HR` (which it never will for an
  operating company) - that check is a dead end and needs to be replaced with the bulk
  INFOTABLE approach, which is blocked on the crosswalk.
- **Insider holdings (Form 4/5):** implemented (Session 304) via SEC's official bulk
  "Insider Transactions Data Sets" (sec.gov/data-research/sec-markets-data/
  insider-transactions-data-sets - quarterly ZIPs of SUBMISSION/REPORTINGOWNER/
  NONDERIV_HOLDING/NONDERIV_TRANS TSVs, pre-joined by issuer ticker). This sidesteps the
  per-filing XML crawl the ~8-16h estimate above was based on: a dozen quarterly ZIP
  downloads instead of one HTTP request per Form 4. See
  `utils/external/sec_form345_bulk.py` for the aggregation methodology (latest
  SHRS_OWND_FOLWNG_TRANS per issuer/reporting-owner pair, ~3yr lookback) and
  `loaders/load_insider_holdings_sec.py`. Foreign private issuers commonly exempt from
  Section 16 correctly report `data_unavailable` (no Form 3/4/5 filings exist for them).
- **Cash flow health metrics (`sec_cash_flow_metrics`):** fixed 2026-07-20. The loader
  (`load_sec_cash_flow_metrics.py`, table registered "critical" in terraform since Session
  274) had NO destination table anywhere in migrations/schema.sql - every run failed
  outright on INSERT. Added migration 1131 + `sql_safety.py` whitelist entry + registered
  in `scripts/local_loader_scheduler.py`'s metrics pipeline (was also missing there).
  Verified live end-to-end (AAPL/MSFT/GOOGL rows written).
- **Business segment metrics (`sec_segment_metrics`):** genuinely unimplemented, same class
  as the 13F gap above - do not re-enable without a real fix. `load_sec_segment_metrics.py`
  reads from `sec_segment_info`, a table that does not exist and has zero writers anywhere
  in the codebase (no 10-K/10-Q segment-disclosure extraction was ever built), and writes to
  `sec_segment_metrics`, which also does not exist. Registered "critical" in terraform since
  Session 274 but not wired into any actual Step Functions pipeline step (dead task-def
  entry, confirmed via `grep` - not invoked automatically). A real implementation needs an
  XBRL segment-reporting (ASC 280) extractor feeding `sec_segment_info` before this loader
  can do anything.
- **Capex/net-change-in-cash silently NULL since Session 274 (fixed 2026-07-20):**
  `load_financial_statements.py`'s `_CASHFLOW_FIELD_MAPPING` mapped SEC's
  `PaymentsToAcquirePropertyPlantAndEquipment` concept to a DB column named
  `capital_expenditures`, which has never existed on `annual_cash_flow`/
  `quarterly_cash_flow` (real column: `capex`) - every write silently vanished at the
  schema-validation step in `loaders/helpers/sec_base.py::transform()` (which validates
  against the loader's own hardcoded `schema_cols`, not the live DB schema, so the mismatch
  never raised). Confirmed live: 0 of ~140K existing rows across both tables had `capex`
  populated. Fixed the mapping + `schema_cols` naming (also `net_change_in_cash` ->
  `net_change_cash`, though no SEC concept is actually fetched for that column yet - it
  remains legitimately unpopulated, not a bug). New/incremental fetches now populate `capex`
  correctly (verified live against AAPL). Existing rows needed a backfill since the
  watermark gate skips already-seen fiscal years regardless of column completeness - ran a
  one-time full re-fetch (`loader_watermarks` reset to 2000-01-01 for
  `financial_statements_cashflow_{annual,quarterly}`, then a full un-scoped loader run) to
  backfill all symbols. Same silent-drop mechanism also affected
  `quarterly_income_statement.cost_of_revenue` (schema_cols listed it, column never existed
  on that table) - fixed via migration 1130 (added the column; annual already had it, no
  downstream reader yet so no backfill urgency).
  **Process note for future loader work:** `SecEdgarStatementLoader.transform()`'s
  `schema_cols` frozensets in `get_*_config()` are hand-maintained and can silently drift
  from the real DB schema with no error - when adding/renaming a mapped field, verify the
  target column actually exists (`information_schema.columns`), don't just trust the
  frozenset.

---

## KNOWN GAP: 5 "critical" loaders are registered but never actually scheduled in AWS (found 2026-07-20)

`terraform/modules/loaders/main.tf`'s `critical_loaders` set (task-def catalog, controls
FARGATE launch type + IAM) lists 24 loaders. Cross-checked every one against actual
`var.loader_task_definition_arns[...]` usages inside Step Functions Task states in
`terraform/modules/pipeline/main.tf` (the only thing that actually triggers a loader run in
AWS) - **5 have zero matches, meaning they never run automatically in production**:

- `company_info_sec` (`load_company_info_sec.py`) - company master data (sector/industry,
  shares outstanding used by the FINRA short-interest % calc below)
- `earnings_calendar_sec` (`load_earnings_calendar_sec.py`) - earnings dates
- `short_interest_finra` (`load_short_interest_finra.py`) - the loader this doc credits with
  lifting `positioning_metrics` coverage 58.9% -> ~93% and `stock_scores` tradeable coverage
  53.4% -> ~64%; that lift may only be reflected in whichever DB last ran it manually/locally,
  not on an ongoing basis in AWS
- `sec_cash_flow_metrics` / `sec_segment_metrics` (see below - the former is now fixed and
  functional, just still unscheduled in AWS; the latter is a genuine dead end)

**Root cause, `company_info_sec`/`earnings_calendar_sec`:** a `reference_data_pipeline` state
machine used to trigger these at 9:15 AM ET. Session 276 deleted it, believing its
functionality had been "merged into computed_metrics_pipeline" after the yfinance Phase 3
consolidation (see the Session 276 comment right above `eod_pipeline_trigger` in
`terraform/modules/pipeline/main.tf`). That belief was incorrect for these two loaders -
grepped the full pipeline file for both script names and `loader_task_definition_arns["company_info_sec"|"earnings_calendar_sec"]`
and found zero references anywhere. This looks like an unintentional regression from Session
276, not a deliberate deprecation (contrast with the *actually*-deprecated yfinance loaders in
`loaders/DEPRECATED_LOADERS.md`, which were removed from terraform on purpose and documented
as such).

**Root cause, `short_interest_finra`/`sec_cash_flow_metrics`/`sec_segment_metrics`:** appear to
have been added to the `critical_loaders` task-def catalog (Session 274/298) without a
corresponding Step Functions wiring step ever being added - infrastructure was scaffolded but
the actual pipeline integration was never finished.

**Local dev is NOT affected** (as of 2026-07-20): `scripts/local_loader_scheduler.py` already
runs `load_company_info_sec.py` + `load_earnings_calendar_sec.py` in its "reference" pipeline
and `load_short_interest_finra.py` in its "morning" pipeline; `load_sec_cash_flow_metrics.py`
was just added to "metrics" (see below). Only AWS production has this gap.

**Not fixed in this pass:** this needs new Step Functions Task states added to
`computed_metrics_pipeline` (or a revived reference-data step) in
`terraform/modules/pipeline/main.tf`, which is a production infrastructure change this
environment cannot validate (no working AWS credentials here - confirmed via live
`UnrecognizedClientException`/`InvalidClientTokenId` errors when the loaders themselves tried
to reach DynamoDB/CloudWatch/Secrets Manager during testing). Flagging for the user to review
and apply via the normal `terraform plan`/`apply` + CI flow rather than hand-editing blind.

---

## Pipelines (Step Functions, EventBridge Scheduler, America/New_York)

**Morning (2:00 AM):** prices (1d, FAIL-CLOSED) → market health ∥ trend template →
market exposure → technical data → sector ranking.

**Reference (9:15 AM):** Market data refreshes, sector/industry consolidation (Session 275: yfinance_derived_metrics deprecated).

**EOD (4:05 PM):** stock symbols → bulk prices (FAIL-CLOSED) → trend template →
technical data (FAIL-CLOSED) → market health → buy/sell signals → algo metrics →
sector/industry/performance → FRED → market exposure → sentiment → data patrol →
orchestrator dry-run validation.

**Computed metrics (7:00 PM):** SEC financials (symbol-major) → growth → quality → value → 
stability → stock scores (Session 275: yfinance snapshot removed; uses SEC + institutional holdings).

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
| price_daily | 1 day | Alpaca SIP multi-symbol batch |
| price_weekly / price_monthly (+etf_) | 7 days | **derived in SQL** after each daily load |
| technical_data_daily | 1 day | incremental write past per-symbol watermark |
| sec_valuations | 7 days | SEC EDGAR companyfacts batch |
| institutional_holdings_13f | 30 days | SEC Form 13-F filings (quarterly) |
| insider_holdings_sec | 7 days | SEC Form 4/5 filings |
| quality/growth/value/stability metrics | 7 days | computed from SEC + holdings tables |
| stock_scores | 4 hours | batch-context panel computation |

Alerts: data patrol + freshness monitor publish to CloudWatch/SNS; dashboard shows
green/yellow/red per table.

---

## For Detailed Reference

- `steering/GOVERNANCE.md` — data quality principles, fail-fast rules
- `steering/OPERATIONS.md` — troubleshooting, deploy chain (CI success auto-deploys; a
  failed CI run silently skips deployment — always verify after pushing)
- `loaders/runner.py`, `utils/optimal_loader.py`, `utils/bulk_insert_manager.py`
- `utils/external/alpaca_market_data.py` (SIP price data)
- `utils/external/sec_edgar_client.py` (companyfacts LRU, form 4/5/13F)
