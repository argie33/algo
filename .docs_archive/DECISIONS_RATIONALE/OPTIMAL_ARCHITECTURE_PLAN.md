# Optimal Data Loading Architecture - Complete Plan

**Goal**: More reliable, faster, cheaper data loading - in AWS and locally - across all dimensions.

This is the MASTER PLAN. Each section identifies what's optimal, the gap from current state, and a prioritized roadmap.

---

## 🎯 GUIDING PRINCIPLES

1. **Use the right tool for the job** - Lambda for fast/small, ECS for long/heavy, Batch for compute-intensive
2. **Pay only for what you use** - Spot, Serverless, auto-scaling everywhere
3. **Don't reload what hasn't changed** - Incremental + CDC + watermarks
4. **Multiple data sources with fallback** - No single point of failure
5. **Data quality is non-negotiable** - Validate at every stage
6. **Observability over hope** - You can't fix what you can't see
7. **Local dev should mirror prod** - LocalStack + Docker Compose

---

## 📊 PART 1: DATA SOURCES - The Foundation

### Current State
- **yfinance only** - rate-limited, unreliable, scraped from Yahoo
- **FRED** for economic data (good)
- **Alpaca** credentials exist but unused

### The Problem
- yfinance breaks weekly (Yahoo changes HTML)
- 5000 symbols × yfinance API = hours of API calls
- No fallback when yfinance fails
- No data validation between sources

### 🚀 OPTIMAL SOLUTION: Multi-Source with Voting

```
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│ Alpaca   │  │ Polygon  │  │ EODHD    │  │ yfinance │
│ (real-   │  │ ($30/mo  │  │ ($20/mo  │  │ (free    │
│ time)    │  │ unlimited)│  │ EOD)     │  │ fallback)│
└────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘
     │             │              │              │
     └─────────────┴──────────────┴──────────────┘
                          │
              ┌───────────▼───────────┐
              │  Data Source Router   │
              │  (with voting/quorum) │
              └───────────┬───────────┘
                          │
              ┌───────────▼───────────┐
              │  Validated Data       │
              │  (quality-checked)    │
              └───────────────────────┘
```

### Recommended Sources by Data Type

| Data Type | Primary | Secondary | Fallback | Cost |
|-----------|---------|-----------|----------|------|
| **Real-time prices** | Alpaca WebSocket | Polygon WebSocket | yfinance | $0 / $30 |
| **Historical OHLCV** | Polygon | EODHD | yfinance | $30-50/mo |
| **Fundamentals** | SEC EDGAR (free!) | Polygon | yfinance | $0 |
| **Earnings** | Alpaca | Polygon | yfinance | included |
| **Economic** | FRED (already) | BLS direct | - | $0 |
| **Sentiment** | NewsAPI | Reddit API | scraping | $0-50/mo |
| **Insider trades** | SEC EDGAR | OpenInsider | - | $0 |
| **Options** | Polygon | CBOE | yfinance | included |

### Outside-the-Box Ideas
- **SEC EDGAR direct** - Official fundamentals, free, more accurate than scraping
- **Internet Archive** - Historical price data from Wayback Machine for missing days
- **Alpha Vantage** - 25 free calls/day per key, multiple keys = unlimited
- **Quandl/Nasdaq Data Link** - Some datasets free, some premium
- **WebSocket streaming** - 1000x cheaper than polling for real-time
- **GraphQL APIs** where available - request only fields you need

### Implementation Priority
1. **Add Alpaca historical** (high impact, credentials exist) - 1 day
2. **Add SEC EDGAR fundamentals** (free, official) - 2 days
3. **Build source router with fallback** - 3 days
4. **Add Polygon ($30/mo)** when scaling - 1 day
5. **WebSocket streaming for real-time** - 5 days

---

## 💪 PART 2: COMPUTE - Right Tool for the Job

### Current State
- **Everything on ECS Fargate** - one-size-fits-all
- Fargate Spot = 70% cost savings (good)
- No Lambda/Batch differentiation

### The Problem
- Small loaders (econdata, sentiment) waste ECS cold-start time
- Large loaders (buyselldaily) run sequentially per task
- No way to handle bursts efficiently

### 🚀 OPTIMAL SOLUTION: Tiered Compute

```
┌─────────────────────────────────────────────────────┐
│  Loader Classification by Workload Profile          │
├─────────────────────────────────────────────────────┤
│                                                     │
│  TIER 1: Small/Fast (<5 min, <512MB)              │
│  → Lambda Functions (zero idle cost)               │
│  Examples: econdata, naaim, feargreed, calendar    │
│                                                     │
│  TIER 2: Medium (<15 min, 1-4GB)                  │
│  → ECS Fargate Spot (current)                      │
│  Examples: most loaders                            │
│                                                     │
│  TIER 3: Large/Compute-heavy (>15 min, >4GB)      │
│  → AWS Batch with EC2 Spot Fleet                   │
│  Examples: buyselldaily, factormetrics             │
│  Savings: 60% over Fargate                         │
│                                                     │
│  TIER 4: Massive parallel (10000+ symbols)        │
│  → Step Functions Map state + Lambda workers       │
│  Examples: full universe scoring                   │
│  Concurrency: 1000+ simultaneous                   │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### Cost Comparison (per full load)

| Architecture | Time | Cost | Reliability |
|-------------|------|------|-------------|
| Current (Fargate Spot) | 90-120 min | $0.60-1.20 | ⭐⭐⭐⭐ |
| **Tiered (Lambda+ECS+Batch)** | **45-60 min** | **$0.25-0.50** | **⭐⭐⭐⭐⭐** |
| Step Functions Map (extreme) | 15-20 min | $0.40-0.80 | ⭐⭐⭐⭐ |

### Outside-the-Box Compute Ideas
- **Lambda SnapStart** - 90% faster cold starts (free for Java/Python)
- **Lambda + Polars** - 10x faster than pandas, fits in 256MB
- **EC2 Spot with capacity rebalancing** - graceful interruption
- **Graviton (ARM)** - 40% cheaper, 20% faster
- **Function URL** for loaders - direct HTTPS invoke, no API Gateway
- **EFS for shared state** between loaders
- **Lambda layers** for shared deps (yfinance, pandas, etc.)
- **Container reuse** - keep DB connections warm

### Implementation Priority
1. **Move 10 small loaders to Lambda** - 70% cost reduction on those - 3 days
2. **Move buyselldaily to AWS Batch** - 50% time reduction - 5 days
3. **Step Functions Map for parallel** - massive scaling - 7 days
4. **Graviton ARM migration** - 40% cost reduction - 2 days

---

## 🗄️ PART 3: STORAGE - Right Engine for the Pattern

### Current State
- **All data in RDS PostgreSQL** - one database, all queries
- Vanilla PostgreSQL on RDS

### The Problem
- Time-series queries on price_daily are slow (12M rows)
- Full table scans on aggregations
- Storage costs growing
- No cold/hot tiering

### 🚀 OPTIMAL SOLUTION: Storage Tiering

```
┌──────────────────────────────────────────────────────────┐
│                    DATA LIFECYCLE                        │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  HOT (last 30 days, real-time)                          │
│  → Redis ElastiCache (sub-ms reads)                     │
│  → DynamoDB (latest prices, JSON cache)                 │
│                                                          │
│  WARM (30 days - 2 years, frequent queries)             │
│  → RDS PostgreSQL + TimescaleDB extension               │
│  → Indexed, partitioned, compressed                     │
│  → 10-100x faster on time-series                        │
│                                                          │
│  COLD (>2 years, rare queries)                          │
│  → S3 Parquet + Athena (90% cheaper)                    │
│  → Iceberg table format for ACID                        │
│  → Time-travel queries supported                        │
│                                                          │
│  ANALYTICS (heavy aggregations)                         │
│  → ClickHouse on EC2 (1000x faster)                     │
│  OR Redshift Serverless (managed)                       │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### TimescaleDB - The Game Changer

PostgreSQL extension, FREE on AWS RDS, transforms time-series performance:

```sql
-- Convert price_daily to hypertable (10-100x faster queries)
SELECT create_hypertable('price_daily', 'date', chunk_time_interval => INTERVAL '1 month');

-- Continuous aggregates (auto-refreshed materialized views)
CREATE MATERIALIZED VIEW price_weekly_agg
WITH (timescaledb.continuous) AS
SELECT symbol, time_bucket('1 week', date) AS week,
       first(open, date), max(high), min(low), last(close, date), sum(volume)
FROM price_daily GROUP BY symbol, week;

-- Compression (10x smaller, queries still fast)
ALTER TABLE price_daily SET (timescaledb.compress, timescaledb.compress_segmentby = 'symbol');
SELECT add_compression_policy('price_daily', INTERVAL '90 days');

-- Data retention (auto-drop old data)
SELECT add_retention_policy('price_daily', INTERVAL '10 years');
```

**Result**: 50GB → 5GB compressed, 100x faster aggregation queries, automatic retention.

### Outside-the-Box Storage Ideas
- **DuckDB embedded** - in-process analytics, replaces Athena for small queries
- **Iceberg on S3** - ACID, schema evolution, time travel, FREE storage layer
- **DynamoDB Streams + Kinesis** - real-time CDC to ClickHouse
- **Aurora Serverless v2** - scales to 0, only pay for what runs
- **PostgreSQL Foreign Data Wrapper** - query S3 from RDS directly
- **Zstandard compression** - 5x better than gzip
- **Parquet column pruning** - only read columns you need
- **Bloom filters** - skip files entirely if symbol not present

### Implementation Priority
1. **Enable TimescaleDB on RDS** - massive perf win, free - 1 day
2. **Add ElastiCache Redis** for hot prices - sub-ms reads - 3 days
3. **S3 Parquet for historical >2 years** - 90% storage savings - 5 days
4. **Athena for ad-hoc analytics** - serverless queries - 2 days
5. **Iceberg tables for cold tier** - future-proof - 7 days

---

## 🔄 PART 4: LOADING PATTERNS - Don't Repeat Work

### Current State
- **Full reload daily** - download all 5000 symbols × 10 years every time
- No change detection
- No incremental updates

### The Problem
- 99% of historical data hasn't changed
- Wastes API calls, compute, bandwidth
- Slow because we're reloading static data

### 🚀 OPTIMAL SOLUTION: Incremental Everything

```
┌─────────────────────────────────────────────────┐
│  Daily Run Pattern (Optimal)                    │
├─────────────────────────────────────────────────┤
│                                                 │
│  1. Read watermark (last_loaded_date per sym)  │
│     → DynamoDB: O(1) lookup                    │
│                                                 │
│  2. Fetch ONLY new data since watermark        │
│     → 1 day instead of 2500 days = 2500x less  │
│                                                 │
│  3. Validate with bloom filter                 │
│     → Skip if no changes                       │
│                                                 │
│  4. UPSERT (INSERT ... ON CONFLICT)            │
│     → Idempotent, safe to retry                │
│                                                 │
│  5. Update watermark                           │
│                                                 │
│  6. Trigger downstream via EventBridge         │
│                                                 │
└─────────────────────────────────────────────────┘
```

### Loading Strategies by Data Type

| Pattern | Use For | Implementation |
|---------|---------|----------------|
| **Watermark-based** | Time-series (prices) | Track last_date per symbol |
| **CDC streaming** | Real-time updates | DynamoDB Streams → Lambda |
| **Snapshot + Delta** | Slowly changing dims | Daily snapshot, hourly deltas |
| **Event-driven** | Earnings, splits, news | EventBridge schedule + ad-hoc |
| **Bloom filter skip** | Unchanged data | Pre-check before fetch |
| **Conditional GET** | API endpoints with ETag | If-Modified-Since headers |

### Outside-the-Box Loading Ideas
- **Reverse-chronological loading** - Load newest first (immediate value)
- **Symbol prioritization** - SPY/QQQ first, then high-volume, then long tail
- **Adaptive batching** - bigger batches when DB is fast, smaller when slow
- **Speculative fetching** - predict what user will want, preload it
- **Backfill jobs** for missing historical data (separate from daily)
- **Data lineage tracking** - know where every value came from
- **Append-only logs** - never delete, only insert (event sourcing)
- **Materialized aggregates refreshed on insert** - downstream stays fresh

### Implementation Priority
1. **Add watermark column** to all time-series tables - 2 days
2. **Convert all loaders to incremental** - 5 days
3. **Bloom filter for change detection** - 3 days
4. **EventBridge scheduling** - 2 days
5. **Backfill job for historical** - 3 days

---

## ⚡ PART 5: PERFORMANCE - 10x Speed Gains

### Current State
- **Pandas everywhere** - slow, memory-hungry
- Synchronous I/O - waits for each API call
- Row-by-row inserts - terrible throughput

### The Problem
- Pandas is the bottleneck for large datasets
- Sequential API calls waste 90% of available bandwidth
- INSERT one-row-at-a-time is 100x slower than COPY

### 🚀 OPTIMAL SOLUTION: Modern Data Stack

```python
# CURRENT (slow)
import pandas as pd
df = pd.read_csv("data.csv")           # Slow, memory-hungry
df = df.groupby("symbol").agg(...)     # Single-threaded
for row in df.iterrows():
    cursor.execute("INSERT...", row)   # Catastrophic

# OPTIMAL (10-100x faster)
import polars as pl                     # 10x faster than pandas
import asyncio                          # Concurrent I/O
import duckdb                           # In-process analytics

# Read with Polars (10x faster, lower memory)
df = pl.read_csv("data.csv")

# Concurrent fetch from multiple sources
results = await asyncio.gather(*[fetch(sym) for sym in symbols])

# DuckDB for complex aggregations (1000x faster)
con = duckdb.connect()
result = con.execute("""
    SELECT symbol, AVG(close), STDDEV(returns) 
    FROM df GROUP BY symbol
""").pl()

# Bulk COPY to PostgreSQL (100x faster than INSERT)
copy_sql = "COPY price_daily FROM STDIN WITH CSV"
cursor.copy_expert(copy_sql, csv_buffer)
```

### Performance Benchmarks (5000 symbols × 1 day)

| Stack | Read | Process | Write | Total |
|-------|------|---------|-------|-------|
| Current (pandas + INSERT) | 5s | 30s | 60s | **95s** |
| Polars + asyncio + COPY | 0.5s | 3s | 2s | **5.5s** |
| **Speedup** | 10x | 10x | 30x | **17x** |

### Outside-the-Box Performance Ideas
- **uvloop** - 2-4x faster asyncio (drop-in replacement)
- **httpx** with HTTP/2 - multiplexed connections
- **pyarrow** for data interchange - zero-copy across libraries
- **Numba JIT** for hot loops - C-speed Python
- **Cython** for critical paths
- **GPU acceleration** with cuDF for huge datasets
- **Process pools** for CPU-bound work
- **Connection pooling** - reuse DB connections
- **Prepared statements** - parse SQL once
- **Pipeline mode** in psycopg3 - send multiple commands

### Implementation Priority
1. **Replace pandas with Polars** in hot loaders - 5 days
2. **Add asyncio for API calls** - 3 days
3. **Use COPY instead of INSERT** everywhere - 2 days (already partial)
4. **Connection pooling** with pgbouncer - 2 days
5. **DuckDB for aggregations** - 3 days

---

## 🛡️ PART 6: RELIABILITY - Build for Failure

### Current State
- Try/except with basic retries
- No circuit breakers
- No data quality framework
- Limited monitoring

### The Problem
- One bad API response can poison the whole load
- No way to detect data drift
- Failures are invisible until users complain
- No SLOs or error budgets

### 🚀 OPTIMAL SOLUTION: Defense in Depth

```
┌─────────────────────────────────────────────────────┐
│  Reliability Stack                                  │
├─────────────────────────────────────────────────────┤
│                                                     │
│  LAYER 1: Source Resilience                        │
│  • Circuit breakers (stop hammering broken APIs)   │
│  • Multi-source fallback (Alpaca → Polygon → yf)   │
│  • Timeout + retry with exponential backoff        │
│  • Rate limiting (respect API limits)              │
│                                                     │
│  LAYER 2: Data Validation                          │
│  • Schema validation (pydantic)                    │
│  • Range checks (price > 0, volume >= 0)           │
│  • Anomaly detection (3-sigma deviation)           │
│  • Cross-source comparison (vote on values)        │
│  • Great Expectations data tests                   │
│                                                     │
│  LAYER 3: Processing Safety                        │
│  • Idempotent operations (UPSERT not INSERT)       │
│  • Transactions per symbol (isolation)             │
│  • Dead letter queue for poison messages           │
│  • Checkpoint progress (resume from failure)       │
│                                                     │
│  LAYER 4: Output Verification                      │
│  • Row count assertions                            │
│  • Freshness checks (max age < 24h)                │
│  • Completeness (all symbols loaded?)              │
│  • Cross-table consistency                         │
│                                                     │
│  LAYER 5: Observability                            │
│  • Structured logging (JSON)                       │
│  • Distributed tracing (OpenTelemetry)             │
│  • Custom metrics (rows/sec, errors, latency)      │
│  • Dashboards (Grafana/CloudWatch)                 │
│  • Alerts (PagerDuty)                              │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### Outside-the-Box Reliability Ideas
- **Chaos engineering** - kill loaders randomly, ensure graceful recovery
- **Synthetic monitoring** - 24/7 fake user that exercises the system
- **Data contracts** - producers commit to schema, consumers validate
- **SLO/error budgets** - quantify acceptable failure rate
- **Game days** - practice incident response
- **Runbooks** for every alert type
- **Auto-remediation** - automatic recovery for known issues
- **Blue/green deployments** for loaders - test before swapping

### Data Quality Framework (Great Expectations example)

```python
# Define expectations once
expectations = {
    "price_daily.close": {"min": 0.01, "max": 100000},
    "price_daily.volume": {"min": 0},
    "price_daily.date": {"freshness_max_hours": 24},
    "price_daily.symbol": {"matches_regex": r"^[A-Z]{1,5}$"}
}

# Run validation after every load
results = validate(df, expectations)
if not results.success:
    alert("Data quality check failed", results.failures)
    rollback()
```

### Implementation Priority
1. **Add Great Expectations** for data quality - 5 days
2. **Circuit breakers** on all external APIs - 3 days
3. **Structured logging** everywhere - 2 days
4. **OpenTelemetry tracing** - 5 days
5. **Grafana dashboards** + PagerDuty alerts - 5 days

---

## 💰 PART 7: COST OPTIMIZATION - 90% Savings Available

### Current State
- Fargate Spot (good, 70% off)
- No reserved capacity
- No data lifecycle policies
- Estimated $100-150/month

### The Problem
- Even Fargate Spot is more expensive than EC2 Spot
- NAT Gateway charges add up ($45/mo + data)
- Cross-AZ traffic charges
- No S3 lifecycle policies

### 🚀 OPTIMAL SOLUTION: Aggressive Cost Engineering

| Optimization | Savings | Effort |
|-------------|---------|--------|
| **Graviton (ARM)** | -40% on compute | Low |
| **EC2 Spot Fleet** vs Fargate Spot | -40% additional | Medium |
| **VPC Endpoints** (eliminate NAT) | $45/mo + data | Low |
| **S3 Intelligent-Tiering** | -50% storage | Low |
| **TimescaleDB compression** | -90% storage | Medium |
| **Compute Savings Plans** (1yr) | -30% | Low |
| **Lambda for small loaders** | -100% idle cost | Medium |
| **Right-size containers** | -20-50% | Low |
| **Reserved Instances for RDS** | -30-60% | Low |

### Real Cost Targets

| Workload | Current | Optimal | Savings |
|----------|---------|---------|---------|
| Daily load | $0.12 | $0.04 | -67% |
| Weekly load | $0.08 | $0.03 | -63% |
| Monthly load | $0.05 | $0.02 | -60% |
| Quarterly load | $0.40 | $0.15 | -63% |
| **Monthly total** | **$10-15** | **$3-5** | **-67%** |

### Outside-the-Box Cost Ideas
- **AWS Free Tier maximization** - 750 hours Lambda free
- **CloudWatch Logs retention** - 7 days vs forever (huge savings)
- **CloudWatch Logs Insights** instead of always-on log aggregation
- **S3 Glacier Instant Retrieval** for old data
- **Spot capacity rebalancing** - smooth interruptions
- **Use Lambda@Edge** for simple transforms (no cold start)
- **Eliminate dev/test environments idle** - tear down nightly
- **AWS Trusted Advisor** - automated cost recommendations
- **Cost allocation tags** - know exactly what costs what
- **Budget alarms** - get notified before surprises

### Implementation Priority
1. **Graviton migration** - 1 day, 40% off compute
2. **VPC Endpoints** - 1 day, eliminate NAT charges
3. **S3 lifecycle policies** - 1 day, automatic tiering
4. **CloudWatch Logs retention** - 30 min, large savings
5. **EC2 Spot Fleet for Batch** - 5 days, 90% off compute

---

## 🏠 PART 8: LOCAL DEVELOPMENT - Production Parity

### Current State
- Manual psql + Python scripts
- Different setup than production
- Hard to test loaders end-to-end

### The Problem
- Bugs only surface in AWS
- Slow feedback loop
- Hard to onboard new developers
- Can't easily test failure scenarios

### 🚀 OPTIMAL SOLUTION: Docker Compose + LocalStack

```yaml
# docker-compose.yml - Full stack with one command
version: '3.9'
services:
  postgres:
    image: timescale/timescaledb:latest-pg16
    environment:
      POSTGRES_DB: stocks
      POSTGRES_USER: stocks
      POSTGRES_PASSWORD: stocks
    ports: ["5432:5432"]
    volumes: ["./db-init:/docker-entrypoint-initdb.d"]
  
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
  
  localstack:
    image: localstack/localstack:latest
    ports: ["4566:4566"]
    environment:
      SERVICES: s3,dynamodb,sqs,lambda,stepfunctions,secretsmanager,kinesis
    volumes: ["./localstack:/var/lib/localstack"]
  
  prometheus:
    image: prom/prometheus
    ports: ["9090:9090"]
  
  grafana:
    image: grafana/grafana
    ports: ["3000:3000"]

# Start everything: docker compose up
```

### Outside-the-Box Local Dev Ideas
- **Devcontainers** - VSCode opens project in pre-configured container
- **Mutagen** - fast file sync between host and container
- **Telepresence** - run local code against real AWS resources
- **mitmproxy** - intercept and replay API traffic
- **Faker** for realistic test data
- **pytest-postgresql** - per-test database fixtures
- **moto** - mock AWS services without LocalStack
- **VCR.py** - record/replay HTTP interactions
- **make commands** for common operations
- **pre-commit hooks** - format/lint before commit
- **Tilt/Skaffold** - watch+rebuild for k8s if used
- **Direnv** - per-project env vars

### Recommended Make Commands

```makefile
# Makefile
.PHONY: setup start stop test load-sample

setup:           ## First-time setup
	docker compose up -d
	./scripts/init-db.sh
	./scripts/seed-test-data.sh

start:           ## Start all services
	docker compose up -d

stop:            ## Stop all services
	docker compose down

test:            ## Run all tests
	pytest --cov=. tests/

load-sample:     ## Load 100 symbols for development
	python loadstocksymbols.py --limit 100
	python loadpricedaily.py --symbols AAPL,MSFT,GOOGL

load-full:       ## Load full dataset (production-like)
	./trigger-optimal-load.sh

deploy-dev:      ## Deploy to dev environment
	cdk deploy --profile dev

clean:           ## Reset everything
	docker compose down -v
	rm -rf .cache/
```

### Implementation Priority
1. **Docker Compose stack** with TimescaleDB - 2 days
2. **LocalStack for AWS services** - 3 days
3. **Devcontainers config** - 1 day
4. **Makefile with common commands** - 1 day
5. **Test data factory** - 3 days

---

## 📅 PART 9: SMART SCHEDULING - Event-Driven > Time-Driven

### Current State
- Fixed cron schedule (4:30 AM daily)
- Same schedule regardless of market events
- All loaders run together

### The Problem
- Wastes resources loading data that hasn't changed
- Misses important events (earnings releases, splits, etc.)
- Doesn't adapt to system load

### 🚀 OPTIMAL SOLUTION: Event-Driven Architecture

```
┌──────────────────────────────────────────────────────┐
│  Event Sources                Triggers Loaders       │
├──────────────────────────────────────────────────────┤
│                                                      │
│  Market Open (9:30 AM ET)  → loadlatestpricedaily   │
│  Market Close (4:00 PM ET) → loadpricedaily         │
│  After-hours (8:00 PM ET)  → loadbuyselldaily       │
│  Sunday 2 AM               → loadpriceweekly        │
│  Last day of month 6 AM    → loadpricemonthly       │
│                                                      │
│  Earnings Calendar Event:                           │
│    AAPL reports tonight    → priority load AAPL     │
│                                                      │
│  News Event:                                        │
│    Fed announcement         → load economic data     │
│                                                      │
│  System Event:                                      │
│    DB migration complete    → trigger backfill       │
│                                                      │
│  Custom Event:                                      │
│    User requests historical → backfill on demand    │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### EventBridge Pattern Examples

```yaml
# Earnings-aware loading
EarningsEventRule:
  Type: AWS::Events::Rule
  Properties:
    EventPattern:
      source: ["custom.earnings"]
      detail-type: ["EarningsRelease"]
    Targets:
      - Arn: !GetAtt LoadEarningsLambda.Arn
        Input: !Sub |
          {"symbol": "$.detail.symbol", "priority": "high"}

# Smart prioritization
HighVolumeSymbolsRule:
  ScheduleExpression: "cron(35 13 * * MON-FRI *)"  # 9:35 AM ET
  Targets:
    - Arn: !GetAtt LoadPricesLambda.Arn
      Input: '{"symbols": ["SPY","QQQ","AAPL","MSFT"], "priority": "critical"}'
```

### Outside-the-Box Scheduling Ideas
- **Earnings calendar integration** - load company before/after earnings
- **Split/dividend events** - trigger price recalculation
- **Index rebalancing dates** - update sector ETFs
- **Market holidays** - skip non-trading days automatically
- **Volatility-based scheduling** - more frequent during high VIX
- **User-driven priority** - load symbols users actually look at
- **Predictive loading** - ML predicts what to load when
- **Backpressure** - slow down if DB is loaded
- **Adaptive batch sizes** - bigger when fast, smaller when slow

### Implementation Priority
1. **EventBridge for cron** - 2 days
2. **Earnings calendar integration** - 5 days
3. **User-priority loading** - 7 days
4. **Adaptive batching** - 5 days

---

## 🔬 PART 10: ML/AI INTEGRATION

### Why ML Matters for Data Loading
- **Anomaly detection**: Is this price real or bad data?
- **Predictive caching**: What will users query next?
- **Load forecasting**: Scale ahead of demand
- **Smart retry**: When is the API likely to work?
- **Cost prediction**: Estimate spend before run

### Implementations
1. **Prophet for time-series** - detect anomalies in incoming data
2. **SageMaker for scoring** - GPU-accelerated factor models
3. **Bedrock for natural language** - ask "load me AAPL data" via chat
4. **Personalize for ranking** - which symbols to load first?
5. **Forecast for capacity** - predict next month's compute needs

---

## 📊 PART 11: OBSERVABILITY - Know Everything

### Current State
- CloudWatch Logs (basic)
- No tracing
- No metrics dashboards
- No SLOs

### 🚀 OPTIMAL SOLUTION: Three Pillars + Cost

```
┌──────────────────────────────────────────────────┐
│  LOGS         METRICS      TRACES      COSTS    │
│   ↓            ↓            ↓           ↓       │
│  CloudWatch   Prometheus   Jaeger      Cost     │
│  + Loki       + Grafana    + Tempo     Explorer │
│   ↓            ↓            ↓           ↓       │
│         OpenTelemetry Collector                 │
│   ↓            ↓            ↓           ↓       │
│         Unified Dashboard (Grafana)              │
│                  ↓                              │
│           Alerts (PagerDuty)                    │
└──────────────────────────────────────────────────┘
```

### Critical Metrics to Track

```python
# Per-loader metrics
loader_duration_seconds = Histogram(...)
loader_rows_inserted = Counter(...)
loader_errors_total = Counter(...)
loader_data_freshness_seconds = Gauge(...)

# Pipeline-level metrics
pipeline_completion_rate = Gauge(...)  # SLO: >99%
pipeline_duration_seconds = Histogram(...)  # SLO: <2hr
data_quality_score = Gauge(...)  # SLO: >0.95

# Cost metrics
cost_per_load_usd = Gauge(...)
cost_per_symbol_loaded = Gauge(...)
cost_per_row_inserted = Gauge(...)
```

### Implementation Priority
1. **Structured logging** (JSON) - 2 days
2. **Custom CloudWatch metrics** - 3 days
3. **OpenTelemetry tracing** - 5 days
4. **Grafana dashboards** - 3 days
5. **PagerDuty alerts** - 2 days

---

## 🎯 PART 12: CONSOLIDATED ROADMAP

### Quick Wins (Week 1-2) - High Impact, Low Effort

| # | Task | Impact | Effort | Owner |
|---|------|--------|--------|-------|
| 1 | Enable TimescaleDB on RDS | 10-100x query speed | 1 day | DB |
| 2 | Add Alpaca historical loader | More reliable than yfinance | 1 day | Data |
| 3 | Graviton ARM migration | -40% compute cost | 1 day | Infra |
| 4 | VPC Endpoints (kill NAT) | -$45/mo + data charges | 1 day | Infra |
| 5 | CloudWatch Logs 7-day retention | Big savings | 30 min | Infra |
| 6 | S3 lifecycle policies | -50% storage | 1 day | Infra |
| 7 | Connection pooling (pgbouncer) | 5x throughput | 2 days | DB |
| 8 | Replace pandas with Polars (top 10 loaders) | 10x speed | 3 days | Code |

### Medium Wins (Month 1) - Significant Impact

| # | Task | Impact | Effort |
|---|------|--------|--------|
| 9 | Watermark-based incremental loading | 100x less data | 5 days |
| 10 | Move 10 small loaders to Lambda | -70% cost | 5 days |
| 11 | Multi-source data router | High reliability | 5 days |
| 12 | Great Expectations data quality | Catch bad data | 5 days |
| 13 | OpenTelemetry tracing | Full visibility | 5 days |
| 14 | ElastiCache Redis caching | Sub-ms reads | 3 days |
| 15 | Docker Compose local dev | Better DX | 3 days |
| 16 | LocalStack AWS emulation | True local dev | 3 days |

### Big Bets (Quarter 1) - Transformative

| # | Task | Impact | Effort |
|---|------|--------|--------|
| 17 | AWS Batch with EC2 Spot Fleet | -90% compute on heavy loads | 7 days |
| 18 | Step Functions Map for parallelism | 1000+ concurrent | 7 days |
| 19 | Iceberg tables on S3 | ACID + cheap storage | 10 days |
| 20 | EventBridge event-driven loading | Smart scheduling | 7 days |
| 21 | DynamoDB Streams + Kinesis CDC | Real-time updates | 10 days |
| 22 | ClickHouse for analytics | 1000x faster queries | 10 days |
| 23 | Polygon.io integration | Best-in-class data | 5 days |
| 24 | WebSocket streaming prices | Real-time | 7 days |

### Strategic (Quarter 2+) - Future-Proof

| # | Task | Impact | Effort |
|---|------|--------|--------|
| 25 | dbt for transformations (ELT pattern) | Maintainable | 14 days |
| 26 | SageMaker for ML scoring | GPU-accelerated | 14 days |
| 27 | Multi-region failover | High availability | 21 days |
| 28 | Data contracts framework | Producer/consumer alignment | 14 days |
| 29 | Synthetic monitoring | 24/7 health | 7 days |
| 30 | Chaos engineering | Resilience | 14 days |

---

## 💡 PART 13: SPECIFIC NEXT ACTIONS

### Decisions Needed
1. **Data sources budget?** Polygon.io = $30/mo, dramatically more reliable
2. **Storage tiering acceptable?** Hot/warm/cold with TimescaleDB + S3
3. **Streaming or batch?** Real-time requires architectural shift
4. **Local dev priority?** Docker Compose + LocalStack vs AWS dev account
5. **Observability stack?** Self-hosted Grafana vs Datadog ($$$)

### Top 5 Recommendations (Do First)

1. **Enable TimescaleDB on RDS** (1 day) → 10-100x query speedup, free
2. **Add Alpaca + SEC EDGAR loaders** (3 days) → Data reliability
3. **Watermark-based incremental loading** (5 days) → 100x less work
4. **Move buyselldaily to AWS Batch with Spot** (5 days) → -50% cost, faster
5. **Docker Compose + LocalStack local dev** (3 days) → 10x dev speed

### Decision Matrix

| Approach | Cost | Speed | Reliability | Effort | Recommended? |
|----------|------|-------|-------------|--------|--------------|
| Status Quo | Medium | Low | Medium | None | ❌ |
| Quick Wins Only | Low | Medium | Medium | 1 week | ⭐⭐⭐ |
| Full Tiered Compute | Very Low | High | High | 1 month | ⭐⭐⭐⭐⭐ |
| Full Streaming Architecture | Low | Very High | Very High | 3 months | ⭐⭐⭐⭐ (overkill?) |
| Lakehouse + ML | Medium | Highest | Highest | 6 months | ⭐⭐ (premature) |

**Recommendation**: Execute Quick Wins (1-2 weeks) first, then evaluate which Medium Wins have most pull, then revisit.

---

## 🏆 SUCCESS METRICS

When complete, the system should achieve:

- **Speed**: Full daily load in <5 minutes (vs current 90+ min)
- **Cost**: <$50/month for full pipeline (vs current ~$150)
- **Reliability**: 99.9% load success rate (vs current ~95%)
- **Freshness**: <1 hour data lag (vs current up to 24h)
- **Coverage**: 100% of S&P 500 + Russell 3000 (vs current limited)
- **Quality**: 99.95% data accuracy (cross-source verified)
- **Recovery**: <5 min MTTR (mean time to recovery)
- **Observability**: 100% of operations traced
- **Local Dev**: Full stack running in <30 seconds locally

---

## 🎯 BOTTOM LINE

We have a working system. To make it **best-in-class**, we need to:

1. **Use the right tool for each job** (Lambda+ECS+Batch tiering)
2. **Stop reloading unchanged data** (watermarks + incremental)
3. **Use modern data tools** (Polars, DuckDB, asyncio)
4. **Multiple data sources** (Alpaca + SEC + Polygon + yfinance fallback)
5. **TimescaleDB extension** (massive perf gain, free)
6. **Aggressive cost engineering** (Graviton, VPC endpoints, lifecycle)
7. **Observability everywhere** (logs + metrics + traces + costs)
8. **Local dev parity** (Docker Compose + LocalStack)

**Estimated outcome**: 10-20x faster, 70% cheaper, 99.9% reliable, joyful to develop on.

This is the plan. Pick what to execute first.
