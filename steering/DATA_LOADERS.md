# Data Loader Orchestration

Live data pipeline: 40+ loaders organized into 4 Step Functions pipelines (morning 2:00 AM, reference 9:15 AM, metrics 3:30 PM, signals 4:05 PM ET; MON-FRI). Metrics runs BEFORE signals to ensure stock_scores has fresh fundamentals.

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
routes daily-bar batches through `utils/external/alpaca_market_data.py`.

**Correction (2026-07-20, migration 1135):** this doc previously claimed symbols Alpaca
doesn't serve are marked `data_unavailable` "rather than falling back to deprecated
yfinance API" - that was never true of the actual code. `utils/data/source_router.py`'s
`fetch_ohlcv_batch` still falls back to yfinance in two cases: (1) per-symbol, for any
symbol Alpaca's response didn't include (`_fill_alpaca_residual_from_yfinance` -
index/caret symbols, OTC/delisted stragglers, ~0.6% of the universe per the 99.4%
coverage figure below), and (2) wholesale, for the entire batch if the Alpaca call itself
raises. This is a deliberate resilience tradeoff (never silently produce zero price data
for a symbol just because Alpaca doesn't cover it), not a bug to remove - but it WAS a
governance violation as originally built: which rows actually came from yfinance was
computed in memory (`row["_source_name"]`) and then discarded before the DB write, so the
fallback was invisible at the only layer anyone actually queries. Migration 1135 added a
`data_source` column to `price_daily`/`etf_price_daily` and `loaders/load_prices.py` now
persists the real per-row source instead of dropping it - `SELECT data_source, COUNT(*)
FROM price_daily WHERE date = CURRENT_DATE GROUP BY data_source` shows the true source mix
for any day going forward (NULL = written before this migration, source unknown).
Fundamentals fallback to yfinance already had the right instinct: `require_sec=True`
(used for Phase 7 signal generation) refuses the yfinance fallback entirely and returns
`data_unavailable` instead - the price path had no equivalent strict mode before this,
though this doc doesn't add one, since dropping price data outright for 0.6% of the
universe would trade "we can't tell the source" for "we don't have the data at all",
without an ask for that tradeoff. Compare historical sources anytime with
`python scripts/compare_price_sources.py` (prior result: 99.4% coverage, close diff
median 0.0000%, volume ratio median 1.000 = true SIP). **Session 275+:** yfinance_snapshot
(the metrics/fundamentals table, unrelated to the OHLCV fallback above) fully deprecated
from all loaders (removed from terraform pipeline and trigger-loaders). The $99/mo plan
is only needed for intraday/real-time (recent-SIP + websocket + 10k/min).

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
- **Institutional holdings (13F):** partial coverage (2026-07-27, was fully blocked).
  Form 13F is filed by the institutional manager under their OWN CIK with CUSIP-level
  holdings, not cross-indexed under the issuer's CIK - there's no per-issuer 13F lookup.
  `loaders/load_institutional_holdings_13f.py` downloads SEC's real bulk quarterly
  INFOTABLE.tsv dataset directly. CUSIP itself is licensed (no free crosswalk), but
  OpenFIGI (`api.openfigi.com`, free, public, no signup) resolves a CUSIP directly to
  its real ticker. The loader queries OpenFIGI CUSIP->ticker directly
  (`utils/external/openfigi_crosswalk.py::fetch_cusip_tickers`) and caches every result
  (including negative/unresolved ones) in `sec_13f_cusip_crosswalk` (migration 1161), so
  only each quarter's small delta of never-seen CUSIPs costs a live OpenFIGI call.
  Live-verified against real mega-cap 13F data: AAPL 86.9%, AMZN 86.6%, MSFT 112.8%, JPM
  106.1%, TSLA 68.7%, NVDA 87.9% institutional ownership (>100% is a known, already-handled
  custodial/prime-broker double-counting artifact of 13F data, not a bug). Coverage is real
  but partial: only symbols where (a) OpenFIGI can resolve that CUSIP to a ticker, (b) that
  ticker is in our own tracked universe, and (c) the resolved entity name plausibly matches
  our own SEC entity_name (`names_plausibly_match()`) get a real ownership % - see that
  module's docstring for a live-verified wrong-entity gotcha (OpenFIGI resolves "XOM" to a
  different corporate entity than the real 10-K filer) that (c) guards against. Everything
  else stays honestly `data_unavailable`, per GOVERNANCE fail-fast.
  **Note:** an earlier version of this approach tried joining on SEC's own optional FIGI
  column instead of querying OpenFIGI directly (to avoid the CUSIP-direction rate-limit
  cost) - live-verified to be catastrophically incomplete (~7.4% of AAPL's real
  institutional shares carry any FIGI tag), self-caught and replaced before shipping. This
  doc previously still described that rejected approach as current; corrected 2026-07-27.
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
- **Business segment metrics (`sec_segment_info`/`sec_segment_metrics`):** IMPLEMENTED and
  live-verified (2026-07-26/27) - this entry was stale for a long time and should not be
  trusted as current without re-checking. `sec_segment_info` (migration 1157) and
  `sec_segment_metrics` (migration 1150) both exist and are both written by real loaders:
  `load_sec_segment_info.py` tries the SEC companyfacts API first (fast, but structurally
  can only ever report segment *count*, never per-segment revenue - a real API limitation,
  not a bug), and on `data_available=False` falls back to fetching the filer's actual 10-K
  instance XML and parsing real per-segment revenue, operating income, and (where the filer
  discloses it) assets directly from the XBRL dimensional model
  (`utils/external/sec_xbrl_segments.py`). `load_sec_segment_metrics.py` reads
  `sec_segment_info` and computes Herfindahl concentration / diversification. Both are wired
  into the real Step Functions pipeline (`terraform/modules/pipeline/main.tf`, `SecSegmentInfo`
  -> `SecSegmentMetrics` steps, not a dead task-def entry) and into
  `scripts/local_loader_scheduler.py`. Live-verified end-to-end for AAPL/MSFT/AMZN: real
  segment revenue, operating income, and (AMZN only - MSFT/AAPL don't disclose it)
  segment assets all landed correctly in the local DB. See memory
  `sec_xbrl_companyfacts_limitation.md` for the full verification history and remaining
  (non-blocking) known gaps.
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

## FIXED 2026-07-27: sec_segment_metrics (real XBRL diversification data) had zero consumers

Continuation of the loader-review goal ("scores should factor in inputs all loaded and used
... and displayed ... on the site too"). `sec_segment_metrics` (revenue concentration HHI,
segment count - computed from real XBRL segment disclosures, see "Business segment metrics"
above) was fully implemented and live-verified, but grep confirmed **zero consumers anywhere**:
not `load_stock_scores.py`, not any `lambda/api` route, not the dashboard. Its own docstring
says "Provides business segment analysis for diversification scoring" - it was built for this
purpose and never wired up.

**Fixed:** folded `revenue_concentration_hhi` into `load_stock_scores.py::_score_stability` as
a minor (0.10) sub-weight, same pattern already used for `debt_to_assets` (a small slot inside
an existing factor's local renormalization, not a new top-level factor - GOVERNANCE's "no
weight redistribution" rule applies to the 6-way top-level split, not sub-components within
one factor). Scored gently (HHI<=1500 -> 100, floors at 50 for a single-segment company at
HHI=10000) since most healthy companies legitimately report one segment - concentration is a
secondary risk signal, not a verdict. Also added to `lambda/api/routes/scores.py`'s
`stability_inputs` display object (new `revenue_concentration_hhi` field + `_unavailable_reason`
companion, same convention as every other displayed input). Live-verified against the real
local DB: AAPL (HHI 2901) and MSFT (HHI 3638) now flow through `_get_stability_metrics` ->
`_score_stability` and the API JOIN correctly; TSLA (not yet backfilled) correctly reports
`revenue_concentration_hhi_unavailable_reason: "no_segment_disclosure"` rather than a fabricated
value. New tests: `tests/unit/test_stock_scores_segment_diversification.py`.
**Caveat:** `sec_segment_metrics` currently has only 5 real rows locally (AAPL/MSFT/AMZN/KO/JNJ
- the mega-caps used during the XBRL parser fix sessions), not full-universe coverage yet; the
loader is correctly wired into the Step Functions pipeline and will backfill more symbols as it
runs on schedule.

**Correction (2026-07-27) - found the actual root cause of the 5-row caveat above:**
`terraform/modules/pipeline/main.tf`'s `computed_metrics_pipeline` had the exact same
structurally-unreachable-state bug already documented elsewhere in this file (the
`InstitutionalHoldings13F` class), just inverted - `SecCashFlowMetrics`'s SUCCESS `Next`
pointed straight to `ValueQualityGrowthMetrics`, skipping `SecSegmentInfo`/`SecSegmentMetrics`
entirely; only `SecCashFlowMetrics`'s own FAILURE handler pointed at `SecSegmentInfo`. One state
deeper, `SecSegmentInfo`'s SUCCESS `Next` had the identical bug pointed at
`ValueQualityGrowthMetrics` instead of `SecSegmentMetrics` (again, only its failure handler
chained forward correctly). Net effect: on the normal/success path - the overwhelming majority
of runs - both segment states were skipped completely; they only ran on the (uncommon) case
where `SecCashFlowMetrics` or `SecSegmentInfo` itself failed. This fully explains why
`sec_segment_metrics` never grew past its initial 5 manually-backfilled rows despite being
"wired into the pipeline" in the structural/deploy-time-valid sense - it was practically
unreachable in production. Fixed both `Next` values to chain forward on success
(`SecValuations` -> `SecCashFlowMetrics` -> `SecSegmentInfo` -> `SecSegmentMetrics` ->
`ValueQualityGrowthMetrics`, matching `scripts/local_loader_scheduler.py`'s order); `terraform
validate` clean. Same caveat as the original Class 2/3 fixes in this file: no AWS credentials in
this environment to verify via a real `terraform apply` - only structurally/locally validated.

## FIXED 2026-07-27: sec_cash_flow_metrics removed from scheduling (duplicated quality_metrics, added no real signal)

Same audit found a second table in the same situation - `sec_cash_flow_metrics`
(`working_capital`, `free_cash_flow`, `operating_cash_flow`, `cash_conversion_rate`) also has
zero consumers. Unlike segment metrics, this one should **not** be wired in: tracing its fields
shows it's a near-total duplicate of data that already exists, is already scored, and is already
displayed elsewhere -
- `free_cash_flow` / `operating_cash_flow`: identical formula (`operating_cf - capex`), already
  computed by `load_value_quality_growth_metrics.py` into `quality_metrics.free_cash_flow` /
  `.operating_cash_flow`, already factored into `_score_quality`/`_enhance_quality_score` (via
  `fcf_to_net_income`), and already displayed (`lambda/api/routes/stocks.py`'s `fcf_data` CTE,
  `scores.py`'s `quality_inputs.free_cashflow`).
- `cash_conversion_rate` (`operating_cf / net_income`): identical formula to
  `quality_metrics.ocf_to_net_income`, same already-scored, already-displayed status.
- `working_capital` (`current_assets - current_liabilities`): the one field with no direct
  duplicate, but it's a strictly weaker, non-size-normalized version of a signal already
  covered - `quality_metrics.current_ratio`/`quick_ratio` are the same liquidity concept
  normalized by current liabilities, already scored (`_score_current_ratio` inside
  `_score_financial_stability`) and displayed. Wiring the raw dollar figure in as a new score
  input would be a real modeling mistake (not comparable across mega-cap vs. small-cap
  companies without normalization) - the "right" fix here is not to force it in.

Net effect: this loader ran, wrote real rows, cost real SEC EDGAR API calls, and produced zero
incremental information over what already exists.

**Fixed (2026-07-27, deliberate removal pass, confirmed with the user first):** removed from
scheduling everywhere - `terraform/modules/pipeline/main.tf` (deleted the `SecCashFlowMetrics`/
`LogSecCashFlowMetricsFailure` states, `SecValuations` now transitions directly to
`SecSegmentInfo`), `terraform/modules/loaders/main.tf` (task-def catalog, resource sizing,
`critical_loaders`), `loaders/loader_registry.py`, `scripts/local_loader_scheduler.py`,
`lambda/trigger-loaders/lambda_function.py`'s trigger allowlist, and
`scripts/verify_loaders_health.py` (would otherwise false-alarm the now-frozen table as
perpetually stale). `terraform validate` clean. Deliberately NOT touched: the
`sec_cash_flow_metrics` table itself, its migration (1131), and its `utils/db/sql_safety.py`
query-allowlist entry - existing rows are harmless and still queryable, only the ongoing
scheduling/API cost was the problem. No AWS credentials in this environment to verify via a real
`terraform apply` (same constraint noted elsewhere in this doc).

---

## FIXED 2026-07-21: 10,904 stale snapshot rows for out-of-scope symbols (ETF leak + delisted stragglers)

Continuation of the loader-review goal ("if we have dupes or slops or other messes, address
them"). Audited every single-row-per-symbol "snapshot" table whose loader sets
`exclude_etfs_from_symbols = True` (stocks-only) for rows belonging to symbols that can never
legitimately be there. Found two distinct leftover categories, both confirmed via
`updated_at`/`computed_at` recency to be residue from bugs **already fixed in code** - not
live/active bugs:
- **ETF leak** in `momentum_metrics`/`stability_metrics` (2,272/2,273 rows) and
  `sec_valuations` (5,426 rows, of which only 3 held non-`data_unavailable` data - the rest
  correctly failed with `no_financial_data`/`no_income_statement`, since ETFs don't file
  10-Ks). All frozen at `updated_at`/`computed_at` = 2026-07-18/07-19; the most recent run
  (07-20) touched zero ETF symbols in any of the three - confirms the fix that scoped these
  loaders to `get_active_symbols(exclude_etfs=True)` already landed and is working, this was
  just never backfilled away.
- **Delisted stragglers**: a consistent set of 147 symbols (verified identical membership
  across `growth_metrics`/`quality_metrics`/`stock_scores`/`institutional_holdings_13f`/
  `company_info_sec`) plus smaller counts elsewhere (20-26), for symbols that were once in
  `stock_symbols` but have since been hard-deleted from it (this codebase removes delisted
  rows outright rather than soft-deleting with `active=false` - confirmed `stock_symbols` has
  zero `active=false` rows). Single-row snapshot tables have no pruning mechanism, so these
  rows just accumulate forever once their symbol falls out of the active universe.
- **Deliberately NOT touched**: `earnings_calendar_sec` (5,351 rows for delisted symbols) -
  that table is a per-event historical log (one row per symbol per earnings date), not a
  snapshot; keeping history for delisted symbols there is correct, not slop. Also not
  touched: `price_daily`/`etf_price_daily` cross-contamination (5,185 ETF-tagged symbols with
  multi-year history in `price_daily`; 4,798 stock-tagged symbols with history through
  2026-05-28 in `etf_price_daily`) - verified this is real OHLCV price history (not a null
  snapshot marker), frozen since well before this session (`etf_price_daily`'s contamination
  stopped 2026-05-28, ~7 weeks ago; today's writes to both tables are exactly the 5
  hardcoded essential symbols `SPY`/`QQQ`/`IWM`/`GLD`/`TLT`, confirmed via
  `MarketSymbolsConfig.DEFAULT_ESSENTIAL_STOCKS`/`DEFAULT_ESSENTIAL_ETF_SYMBOLS`), and no
  consumer reads either table by broad enumeration (`lambda/api/routes/prices.py` checks
  `price_daily` first and only falls back to `etf_price_daily`, so a stock found correctly in
  `price_daily` never surfaces the `etf_price_daily` copy; `signals.py`'s ETF-signals endpoint
  filters to a curated symbol list, not `SELECT DISTINCT symbol FROM etf_price_daily`).
  Deleting years of real price history for a table-placement mismatch that no code depends on
  would be destructive for no benefit - left alone.

**Fix:** deleted the 10,904 confirmed-stale rows (one-time cleanup, live-verified before/after
counts). Added `scripts/prune_stale_snapshot_symbols.py` (dry-run by default, `--execute` to
delete) as a reusable maintenance tool, since nothing currently prunes these tables
automatically and the same accumulation will recur every time a stock gets delisted. Not
wired into the pipeline/terraform (that's a scheduling decision, not made here) - run
manually or add to a periodic maintenance job.

**Also fixed in passing:** `scripts/monitor_data_staleness.py` (the script this doc's own
"Data is stale?" pointer at the top of `CLAUDE.md` sends users to first) did
`from utils.logging import logger` - `utils/logging/__init__.py` doesn't export a `logger`
name, so that import silently bound the `utils.logging.logger` *submodule* instead of a
configured `Logger` instance (Python exposes imported submodules as package attributes even
without an explicit re-export). The one call site (`logger.error(...)` in the per-table
exception handler) would have raised `AttributeError` and masked the real error the moment
this script's own error-handling path was ever exercised - exactly when a real operator is
depending on it most. Fixed to `from utils.logging.logger import get_logger` /
`logger = get_logger(__name__)`; verified live (clean run, 14/14 tables fresh, no crash).

---

## FIXED 2026-07-21: growth_metrics all-or-nothing bug discarding real partial data (score-input quality)

`load_value_quality_growth_metrics.py::_compute_growth_metrics` computes 6 independent
growth periods (revenue/EPS x 1y/3y/5y CAGR) from `annual_income_statement` history. Any
single period failing (most commonly `eps_growth_5y`/`revenue_growth_5y`, which need 6
distinct fiscal years - many symbols simply don't have that much SEC history yet) set
`data_unavailable = True` on the ENTIRE row, even when 1-5 of the 6 periods computed real
values. `load_stock_scores.py::_get_growth_metrics` checks that flag and discards the whole
row via `marker_not_applicable` when set - so the real partial values it wrote never reached
`_score_growth`, which already renormalizes over whatever periods are non-NULL (documented
"RETURN TYPES: metrics available with ≥1 growth field -> returns float"). The scorer was
never the problem; the loader's flag was silently throwing away good data before the scorer
ever saw it. This is the SAME bug class already found and fixed in momentum (see
`load_risk_metrics_daily.py::_compute_momentum_row`'s 2026-07-20 fix comment) - momentum,
quality_metrics, and value_metrics were all already correctly partial-tolerant (checked
directly, not just by analogy); growth was the one loader that still had it. Fixed by only
setting `data_unavailable=True` when ALL 6 periods fail (`reason` still records what's
missing, for diagnostics). Backfilled live via a full loader re-run (no external API calls -
growth is computed purely from already-loaded `annual_income_statement`):
- `growth_metrics` real coverage: 34.3% -> 87.7% (1739 -> 4446 of 5069 rows)
- `stock_scores` real coverage: 76.5% -> 83.3% (4294 -> 4674 of 5613 rows)

## FIXED 2026-07-21: dead yfinance quoteSummary (`.info`) code path removed

`utils/external/yfinance.py` (`YFinanceWrapper`/`get_ticker`) wrapped yfinance's
`.info`/quoteSummary endpoint - the API surface `load_yfinance_snapshot.py` used before it
was deleted in Session 295. After that deletion, this wrapper had exactly one remaining
caller: `RateLimitValidator.check_api_health()` (`utils/validation/rate_limit.py`), which
used it purely to answer "is yfinance up" for an ops health check - firing a live, more
fragile ("Invalid Crumb" 401-prone) request against an endpoint nothing else in the
pipeline uses anymore, and risking tripping the SHARED cross-ECS-task circuit breaker that
the real OHLCV fallback path (`yf.download` in `utils/data/source_router.py`) depends on.
Deleted `utils/external/yfinance.py` and the now-fully-dead `loaders/helpers/
yfinance_batcher.py` (batch helpers for the same deleted `.info` path, zero callers).
Replaced the health check with `DataSourceRouter.check_yfinance_reachable()`, a new small
method that exercises the actual `yf.download` fallback path under the existing shared
circuit breaker/throttle instead. Also corrected `VIXFetcher`'s docstring/class comment
(`loaders/market_health_fetchers.py`) - it reads VIX from `price_daily` (Alpaca-sourced),
not from yfinance; the `"yfinance_vix"` circuit-breaker name is legacy/dashboard-compat
only and was never a real yfinance call site. And rewrote `tests/
test_put_call_ratio_yfinance.py`, which still asserted a live yfinance options-chain fetch
(`0.2 <= result <= 3.0` float) that has been unreachable dead code since Session 291 -
`PutCallRatioFetcher.fetch()` now unconditionally returns a `data_unavailable` marker (no
official free put/call source exists); the test now asserts that actual contract instead of
a path it could never exercise. No production behavior change from the test fix; the health
check and dead-code removal reduce yfinance surface area per the "break away from yfinance
as much as we can" ongoing goal - full data flow now: Alpaca (primary, ~99.4%) ->
`yf.download` OHLCV fallback (~0.6% residual + whole-batch-failure fallback) -> nothing else
touches yfinance.

**Correction (2026-07-27):** the paragraph above is wrong about `PutCallRatioFetcher` - it does
NOT "unconditionally return a `data_unavailable` marker" and the yfinance options-chain path is
NOT dead code. Live-checked: `PutCallRatioFetcher._fetch_from_yfinance()`
(`loaders/market_health_fetchers.py`) still does a real `yf.Ticker("SPY").option_chain(...)`
call behind its own circuit breaker, `fetch()` returns real `put_call_ratio` values when it
succeeds, and those real values are actively consumed as an 8%-weighted "HIGH-priority
enrichment" factor in market exposure scoring (`algo/risk/factors/put_call_ratio_factor.py`,
`algo/risk/market_factor_calculator.py`) - not inert. `tests/test_put_call_ratio_yfinance.py`
itself already flagged this contradiction in its own docstring ("Despite Session 291 comment
saying yfinance was removed, it still works") rather than being corrected to match. Since no
free official CBOE put/call feed exists, keeping this working yfinance-sourced signal is the
right call (same "unofficial but real, transparently documented" tradeoff as the OHLCV
residual fallback above) - the actual bug was only that this doc and the test's module
docstring both asserted a removal that never happened, which could have misled a future session
into "finishing" a phantom removal and silently deleting a real, working, weighted signal.
Fixed both docstrings to state the real, current contract. Also correcting the yfinance
surface-area count from the paragraph above: `market_health_fetchers.py` is a fourth live
yfinance call site alongside the three OHLCV-fallback-related files, not zero.

---

## FIXED 2026-07-20: 4 broken/dangling Step Functions transitions + 5 unscheduled "critical" loaders

Two distinct classes of bug found in `terraform/modules/pipeline/main.tf`, both from the same
pattern: a state got renamed/removed/added during a consolidation commit, but not every
transition that pointed at it was updated to match.

**Class 1 - dangling `Next` references (AWS rejects these at deploy time):**
- `computed_metrics_pipeline`: `SecValuations` (+ its failure handler) had `Next =
  "QualityMetrics"`, a state renamed to `ValueQualityGrowthMetrics` by commit `0eb93ea27`
  (Phase 3 consolidation) - 3 occurrences, never updated.
- `eod_pipeline`: `TechnicalDataDaily.Next = "MarketHealthDaily"`, a state removed by commit
  `60bccc14b` (Phase 2 consolidation into `MarketStatusDaily`). Corrected to `"BuySellDaily"`,
  the real next step.
- `eod_pipeline`: `AlgoMetricsAfterSignals` (+ its failure handler) had `Next =
  "SectorRanking"`, a state removed by commit `5bc60bb97` (Phase 4 consolidation into
  `SectorIndustryDaily`) - 3 occurrences, never updated.

Since AWS Step Functions validates every `Next` target exists at `CreateStateMachine`/
`UpdateStateMachine` time, any `terraform apply` touching these state machines after those
consolidation commits would have been rejected outright - meaning production was very likely
still running whatever version last applied successfully *before* the rename, silently
skipping the intended consolidated loaders.

**Class 2 - structurally unreachable (orphaned) states, no deploy-time error, but the state
never runs:** `computed_metrics_pipeline`'s `ValueQualityGrowthMetrics.Next` was hardcoded to
`"PositioningMetrics"`, skipping straight past `InstitutionalHoldings13F` and
`InsiderHoldingsSec` - both defined, both with correct internal wiring to each other and to
`PositioningMetrics`, but nothing ever transitioned *into* `InstitutionalHoldings13F`. Commit
`5327a555b` (Session 294, "restore positioning metrics pipeline") added these two states but
never repointed the predecessor's `Next`. This is the direct explanation for the live-DB
finding that `institutional_ownership_pct` is ~0% populated (2 of 4,826 stocks) despite
`load_institutional_holdings_13f.py` existing and being registered - it has likely never
actually run via this pipeline since Session 294.

All fixed by correcting the `Next` targets in place (verified with a scripted reachability
scan of every state machine + `terraform validate` with dummy AWS creds - both clean for
`pipeline/main.tf`, no dangling or orphaned states remain).

**Update (2026-07-21):** the "2 of 4,826" figure below is now stale - re-checked live
against the current local DB and it's 0 of 5245 checked symbols with real data (all 5245
`institutional_holdings_13f` rows are explicit `data_unavailable=true` markers, reasons
`no_13f_filings`/`companyfacts_error`/`cik_not_found`). The underlying diagnosis is
unchanged and still accurate (this is the architectural per-issuer-CIK dead end described
below, correctly surfacing as `data_unavailable` per governance rather than silently
faking a number) - just noting the count moved from "almost entirely unpopulated" to
"entirely unpopulated" since this doc was last updated, not that anything regressed.

**Class 3 - registered but never wired in at all** (separate root cause, same symptom -
missing data): `terraform/modules/loaders/main.tf`'s `critical_loaders` set lists 24 loaders;
5 had zero `var.loader_task_definition_arns[...]` usages anywhere in the pipeline file, so
they never ran automatically in production, ever:
- `company_info_sec` / `earnings_calendar_sec` - a `reference_data_pipeline` state machine
  used to trigger these at 9:15 AM ET; Session 276 deleted it believing its functionality had
  been "merged into computed_metrics_pipeline" after the yfinance Phase 3 consolidation - true
  for value/quality/growth metrics, false for these two (never actually added anywhere).
- `short_interest_finra` / `sec_cash_flow_metrics` - added to the task-def catalog (Session
  274/298) without a corresponding Step Functions wiring step ever being added.
- `sec_segment_metrics` - **stale as of 2026-07-26/27**: this was a genuine dead end when
  written, but `sec_segment_info`/`sec_segment_metrics` are now both implemented, wired into
  `computed_metrics_pipeline` in `terraform/modules/pipeline/main.tf` (`SecSegmentInfo` ->
  `SecSegmentMetrics` steps), and live-verified end-to-end - see the corrected entry above
  ("Business segment metrics") and memory `sec_xbrl_companyfacts_limitation.md`. Left this
  bullet in place rather than deleted, per this doc's own convention of appending corrections
  instead of rewriting history.

**Fix:** added `CompanyInfoSec` -> `EarningsCalendarSec` -> `ShortInterestFinra` ->
(existing `InstitutionalHoldings13F` chain) and `SecCashFlowMetrics` (after `SecValuations`,
before `ValueQualityGrowthMetrics`) as new Task states in `computed_metrics_pipeline`,
matching the dependency order `scripts/local_loader_scheduler.py` already used locally.
`short_interest_finra` kept at `LOADER_PARALLELISM=1` per the SEC/FINRA rate-limit clamp
documented above.

**Still needs a human:** this environment has no working AWS credentials (confirmed via live
`InvalidClientTokenId` from a bare-creds `terraform validate`/STS check), so none of this could
be applied or exercised against real infrastructure - only validated locally (state-machine
JSON structure, `terraform fmt`, `terraform validate` schema checks). Review the diff and run
the normal `terraform plan`/`apply` + CI flow before trusting it in production.

---

## FIXED 2026-07-27: analyst_upgrade_downgrade AND analyst_sentiment_analysis had no live writer

Continuation of the loader-review goal (factor-input completeness audit). `analyst_upgrade_downgrade`
(consumed by `algo/signals/advanced_filters.py::_analyst_score()` as the "catalyst" subscore's analyst
input) had **zero writers anywhere in the codebase** - its only historical writer,
`load_yfinance_snapshot.py`, was deleted in Session 275 alongside the rest of the yfinance-snapshot
deprecation (see the "Session 275+" note near the top of this doc) and never replaced. Confirmed live
against the local DB: frozen at 50 rows, all dated 2026-05-22 (the loader's last run before deletion).

**This does NOT crash** (worth stating precisely, since it initially looked like it might):
`_analyst_score()`'s query is a bare `COUNT(*) FILTER (...)` aggregate with no `GROUP BY`, which always
returns exactly one row with integer counts (0, not NULL, when nothing matches) - so its two
`row is None` / `row[0] is None` guard clauses are unreachable dead code, not a live crash path. The
real effect was quieter and arguably worse per this codebase's own governance principle ("explicit
`data_unavailable` flags, no silent fallbacks"): for the ~99.99% of symbols with zero rows in the
table, this silently computed `net=0` ("no upgrades or downgrades") indistinguishably from a symbol
that genuinely has zero recent analyst activity.

**An earlier version of this note concluded "fixing it for real needs a live analyst-ratings data
source... not a code fix" and left it as a documented, unfixable gap** (SEC/EDGAR doesn't publish
analyst ratings - real-time coverage is proprietary, typically a paid feed). **That conclusion was
wrong** - the user pointed out directly that yfinance's `Ticker.upgrades_downgrades` provides real
analyst rating-action data (Firm/ToGrade/FromGrade/Action/price targets), live-verified working
2026-07-27. Same "unofficial but real, transparently documented" tradeoff already accepted for
`put_call_ratio` (see the correction above) - used here because no free official feed exists, not as
a substitute for one that does. This is exactly the "not trying hard enough to get the data we need"
failure mode the loader-review goal called out: a usable free source existed and a prior audit pass
didn't look hard enough before declaring the gap unfixable.

**Fixed:** new `loaders/load_analyst_upgrade_downgrade.py` +
`utils/external/yfinance_analyst_ratings.py` (shared cross-ECS-task yfinance IP circuit breaker,
same as the OHLCV fallback - a full-universe run hits this once per symbol, thousands of calls/run,
unlike the single-SPY-call put_call_ratio case). Also found and fixed along the way: the live table
schema didn't match `lambda/db-init/schema.sql`'s documented shape at all (real columns: `id` SERIAL
PK, `firm` not `analyst_firm`, no `action_detail`/`price_target`, no compound PK) - someone edited
the CREATE TABLE statement in the past without a migration to carry existing databases forward, so
`CREATE TABLE IF NOT EXISTS` silently never applied anywhere it mattered. Migration 1167 adds a real
`UNIQUE (symbol, action_date, firm)` constraint (needed since multiple firms commonly rate the same
symbol on the same calendar date - the loader upserts on this). `schema.sql` corrected to match
reality for fresh installs. Wired into `eod_pipeline`'s `AaiiSentiment` -> `AnalystUpgradeDowngrade`
-> `MarketStatusDaily` chain (`terraform/modules/pipeline/main.tf`) and
`scripts/local_loader_scheduler.py`. Live-verified end-to-end against real symbols (AAPL/MSFT/TSLA/
GOOGL): real rows landed with correct schema mapping, and the incremental watermark path correctly
fetched only new activity on a second run. Removed from `pipeline_health.py`'s no-writer staleness
exclusion list now that a real writer exists.

**`analyst_sentiment_analysis` (separate table, consumed by `lambda/api/routes/sentiment.py`'s
`/api/sentiment/analyst/*` endpoints) - also fixed, same pass.** yfinance's `recommendations_summary`
(strongBuy/buy/hold/sell/strongSell counts) + `analyst_price_targets` (current/mean target price)
is the same real shape this table was designed for. New `loaders/load_analyst_sentiment_analysis.py`
+ `fetch_analyst_sentiment()` (added to `utils/external/yfinance_analyst_ratings.py` alongside
`fetch_analyst_actions()`, sharing a `_fetch_with_circuit_breaker()` helper). Wired into the same
`eod_pipeline` chain right after `AnalystUpgradeDowngrade` (`AaiiSentiment` ->
`AnalystUpgradeDowngrade` -> `AnalystSentimentAnalysis` -> `MarketStatusDaily`), same fail-open
pattern, `terraform validate` clean. Live-verified (re-confirmed 2026-07-27, this pass): real
counts/target prices landed for AAPL (47 analysts, target $318.81 vs $336.91 current) and MSFT
(58 analysts, target $556.75 vs $389.10 current), and the sentiment API's own `days_stale > 7`
fail-fast check now passes (0 days stale) instead of the ~60+ it had been serving as a hard
failure for ~2 months. `schema.sql`'s `analyst_sentiment_analysis` CREATE TABLE had the same
drift-from-live-schema bug as `analyst_upgrade_downgrade` above (stale `hold_count`/
`recommendation_key`/`data_unavailable`/`reason` columns instead of the real `id` SERIAL PK,
`neutral_count`/`target_price`/`current_price`/`upside_downside_percent`, `UNIQUE(symbol, date)`
shape) - corrected this pass, same "only bites fresh installs" caveat since the live table
already had the right shape.

Also found both `load_analyst_upgrade_downgrade.py` and `load_analyst_sentiment_analysis.py`
missing entirely from `loaders/loader_registry.py`'s `LOADER_TABLES` (the canonical
loader-script -> output-table mapping several health/audit scripts read) - same "restored
loader, forgot to register it" gap class as `load_company_profile.py` a few entries above.
Added both this pass.

---

## GAP (documented, not fixed) 2026-07-21: economic_metrics_daily has a table but no loader

`economic_metrics_daily` (CPI YoY, SPY price change, 10Y-2Y yield curve slope - migration 079,
`report_date` PK) is a genuinely different table from `economic_data` (the FRED series table
T10Y2Y/FEDFUNDS/BAMLH0A0HYM2/ICSA + DXY that `loaders/load_economic_data.py` actually writes) -
don't confuse the two, they were both real at some point. Migration 079's own comment says "The
economic_metrics_daily loader fails... until this runs," confirming a loader for this table
existed at some point, but **no such loader file exists anywhere in the current codebase**, it
is not wired into either `terraform/modules/loaders/main.tf` or `terraform/modules/pipeline/
main.tf`, and no dashboard/API code actually queries it for data (only config/allowlist
references remain: `utils/data_tiers.py`, `utils/loader_priority.py`, `utils/db/sql_safety.py`'s
SQL-safety allowlist, a CloudWatch log-group placeholder in `terraform/modules/lifecycle/
main.tf`, and `lambda/api/routes/algo_handlers/market.py`'s dashboard health-panel *exclusion*
list - which correctly already treats it as "not used in trading logic," so this isn't causing
a false-stale health-panel alarm today). Net effect: inert, not actively harmful, but genuine
slop - a migration and several scattered config references pointing at a feature that was
apparently built once and then had its loader removed without cleaning those up. Left in place
rather than touched in this pass (removing the migration/table would need confirming nothing in
git history still depends on it; removing just the scattered config references is low-value
churn for a table nothing reads) - flagging here so it isn't mistaken for an active gap needing
a new loader built from scratch.

**UPDATE 2026-07-27:** a later session read this gap note as an invitation and built exactly the
"new loader from scratch" this section warns against - a full `load_economic_metrics_daily.py`
plus a migration recreating the table, wired into `scripts/local_loader_scheduler.py` and
`utils/db/sql_safety.py`. Reverted before commit: two of its three computed fields (CPI YoY,
10Y-2Y yield slope) are already live elsewhere (`lambda/api/routes/economic.py` computes CPI YoY
on the fly from `economic_data`; `market_health_daily.yield_curve_slope` is populated by
`loaders/load_market_status_daily.py` from the same FRED series) and the third (SPY daily %
change) had zero consumers. Same root problem as before: no dashboard/API code queries this
table. Do not rebuild this loader again without first shipping the consumer that would read it.

---

## Pipelines (Step Functions, EventBridge Scheduler, America/New_York)

**Morning (2:00 AM):** prices (1d, FAIL-CLOSED) → market health ∥ trend template →
market exposure → technical data → sector ranking.

**Reference (9:15 AM):** Market data refreshes, sector/industry consolidation (Session 275: yfinance_derived_metrics deprecated).

**EOD (4:05 PM):** stock symbols → bulk prices (FAIL-CLOSED) → trend template →
technical data (FAIL-CLOSED) → market health → buy/sell signals → algo metrics →
sector/industry/performance → FRED → market exposure → sentiment → data patrol →
orchestrator dry-run validation.

**Metrics (3:30 PM):** SEC financials (symbol-major) → growth → quality → value → 
stability → stock scores (Session 275: yfinance snapshot removed; uses SEC + institutional holdings).
CRITICAL: Runs BEFORE signals pipeline (4:05 PM) to ensure stock_scores computes with fresh fundamentals.

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
