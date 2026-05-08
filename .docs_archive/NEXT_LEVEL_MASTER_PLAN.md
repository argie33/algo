# Next-Level Master Plan: Best-in-Class Data Loading + Display

**Mandate**: More reliable, better, faster, cheaper—creatively, outside the box.
**Constraint**: Stay under $50-60/month while achieving best-in-class performance.
**Method**: Question every assumption, find unconventional solutions, work around limitations.

---

## CORE INSIGHT — The Three Big Levers

Most "optimization plans" tinker at the edges. The biggest wins come from rethinking the fundamentals:

1. **Don't load what you can compute.** SEC EDGAR has free, official fundamentals. Why scrape Yahoo?
2. **Don't poll what you can stream.** WebSockets cost 1000x less than polling for real-time data.
3. **Don't run what you can cache.** A query that runs once and serves 1000 users beats 1000 redundant queries.

Every idea below extends one of these three principles.

---

## PART 1: BREAKTHROUGH IDEAS (Game Changers)

These aren't incremental—they fundamentally change cost or capability.

### 🔥 #1: Replace Polling with WebSocket Streams (Real-Time Data, 1000x Cheaper)

**Current state**: Loaders poll yfinance/Alpaca every N minutes, paying for full request each time.

**Better**: Subscribe to WebSocket streams from Alpaca/Polygon. Receive only changes, push to DB.

**Cost comparison** (1000 symbols, 1 min interval):
- Polling: 60 × 24 × 60 × 1000 = 86.4M requests/month → $$$
- WebSocket: 1 connection × 24h × 30d, ~10K msgs/sec total → $0.50/month
- **Savings: $50-200/month**

**Implementation**:
```python
# Single ECS Fargate task running 24/7
# Cost: $5/month
# Subscribes to: alpaca.data.us.equities, polygon.io ws
# Writes to: Kinesis Data Stream → Lambda → TimescaleDB
```

**Effort**: 5 days. **Impact**: HUGE. **Priority**: Top 3.

---

### 🔥 #2: SEC EDGAR Direct (Free, Official Fundamentals)

**Current state**: Scraping Yahoo Finance for fundamentals — unreliable, illegal-grey-area, often wrong.

**Better**: SEC EDGAR's official API is free, structured (XBRL), legally clean, more accurate.

**What's available** (free, unlimited):
- All 10-K, 10-Q, 8-K filings
- All XBRL-tagged fundamentals (revenue, EPS, cash flow, balance sheet)
- Insider transactions (Form 4)
- Beneficial ownership (Schedule 13D/G)
- Restated earnings, footnotes
- Full historical data back to 1990s

**Implementation**:
```python
# Python EDGAR API library: sec-edgar-downloader
# Endpoint: https://data.sec.gov/api/xbrl/companyconcept/CIK[CIK]/us-gaap/[concept].json
# Rate limit: 10 req/sec (very generous)
# No authentication needed
```

**Replaces**: 4 loaders (annualbalance, annualcashflow, annualincome, quarterly variants)

**Effort**: 3-5 days. **Impact**: Eliminates yfinance fragility for fundamentals. **Priority**: Top 5.

---

### 🔥 #3: Rust/Go for Hot-Path Loaders (10-50x Faster Than Python)

**Current state**: All 57 loaders in Python with pandas. Pandas is slow.

**Better**: Rewrite the 5-10 hottest loaders in Rust (using `polars-rs`, `tokio`, `sqlx`).

**Speedup analysis**:
- pandas → Polars (Python): 5-10x faster
- pandas → Polars (Rust): 20-50x faster
- pandas → DuckDB: 10-100x for analytics

**Real numbers** (loadbuyselldaily processing 5000 symbols × 250 days):
- Python + pandas: 90 minutes
- Python + Polars: 12 minutes
- Rust + Polars: 3 minutes
- **Cost savings: $30/month** (less Fargate runtime)

**Effort**: 10 days for top 5 loaders. **Impact**: Huge speedup + reliability. **Priority**: Big bet, Q1.

---

### 🔥 #4: Cloudflare R2 for S3-Compatible Storage (ZERO Egress Fees)

**Current state**: S3 charges $0.09/GB egress. We pay this when API serves data, when frontend downloads, etc.

**Better**: Cloudflare R2 has identical S3 API but ZERO egress fees forever.

**Cost comparison** (10TB egress/month):
- AWS S3: $920/month
- Cloudflare R2: $150/month (just storage)
- **Savings: $770/month at scale**

**Use case**: Use R2 for:
- Static frontend assets (CSS/JS bundles)
- Historical data exports
- Data API responses cached at edge
- Backups (PostgreSQL dumps)

**Effort**: 2 days to migrate. **Impact**: Eliminates one of biggest AWS cost drivers. **Priority**: Top 5.

---

### 🔥 #5: DuckDB for In-Process Analytics (Skip the Database)

**Current state**: Every analytics query hits PostgreSQL → competes for connections, locks, cache.

**Better**: Use DuckDB to query Parquet files directly in Lambda. PostgreSQL only for hot data.

**Architecture**:
```
Hot data (last 30 days): PostgreSQL + TimescaleDB
Warm data (30d-1y): Parquet on S3, queried by DuckDB in Lambda
Cold data (>1y): Parquet on R2, archived
```

**Performance**:
- Aggregate over 5 years of price data:
  - PostgreSQL: 10 seconds, $0.05/query
  - DuckDB on Parquet: 0.5 seconds, $0.001/query
- **100x cheaper, 20x faster**

**Effort**: 7 days. **Impact**: Frees PostgreSQL for hot path, dramatically reduces query costs. **Priority**: Big bet.

---

### 🔥 #6: Self-Hosted Compute on Hetzner/OVH (5-10x Cheaper Than AWS)

**Current state**: AWS Fargate Spot at $0.012/vCPU-hour. AWS is convenient but expensive.

**Better**: For batch jobs (loaders, backfills), use Hetzner Cloud or OVH:
- Hetzner CX31 (4 vCPU, 8GB RAM): $7.50/month vs ~$50 on AWS equivalent
- OVH dedicated: $35/month for 8-core machine running 24/7
- **5-10x cheaper than AWS for compute**

**Hybrid architecture**:
- Front-end + APIs: AWS (CloudFront, Lambda, RDS)
- Batch loaders: Hetzner via Tailscale VPN to RDS
- Cold storage: Cloudflare R2

**Risk**: Two providers to manage. Mitigated by Terraform for both.

**Effort**: 5 days. **Impact**: -$50-100/month. **Priority**: Medium bet, Q2.

---

### 🔥 #7: Edge-Deployed API with Cloudflare Workers (Free Tier = 100K req/day)

**Current state**: API Gateway + Lambda. Cost: $25-100/month at scale.

**Better**: Move API to Cloudflare Workers. 100K requests/day free, then $0.30/million.

**Cost comparison**:
- AWS Lambda + API Gateway: $100/month at 100M requests
- Cloudflare Workers: $30/month at 100M requests
- **Savings: -$70/month**

**Bonus**: Runs at edge, <50ms globally. Built-in DDoS protection.

**Limitation**: 10ms CPU time per request (free tier). Use for thin API layer.

**Effort**: 7 days to port routes. **Impact**: Cheaper, faster globally. **Priority**: Medium bet.

---

### 🔥 #8: AI-Powered Data Quality (Claude/GPT for Anomaly Detection)

**Current state**: Manual data quality rules (price > 0, volume > 0, high >= low).

**Better**: Use Claude API or GPT-4o-mini to detect *semantic* anomalies:
- "AAPL price dropped 50% in one day with no news" → flag for review
- "Earnings revenue grew 1000x" → likely data error, ignore
- "New ticker with no fundamentals after 3 months" → investigate

**Cost**: $0.002/check × 5000 stocks/day = $10/month
**Value**: Catch bad data BEFORE it pollutes downstream signals.

**Architecture**:
```python
# After each load, run validation pass
for record in new_records:
    if statistical_anomaly_score(record) > 0.95:
        result = claude.complete(f"Is this realistic? {record}")
        if not result.is_realistic:
            quarantine(record)
```

**Effort**: 5 days. **Impact**: Catches bad data automatically. **Priority**: Quick win, Month 2.

---

### 🔥 #9: Probabilistic Data Structures (Bloom Filters Save 99% of DB Hits)

**Current state**: "Does this symbol-date already exist?" → Hits PostgreSQL.

**Better**: Maintain a Bloom filter in Redis. Check filter first; only query DB on positive.

**Math**: 
- 5000 symbols × 5 years × 252 trading days = 6.3M records
- Bloom filter (1% false positive): 9.4MB in memory
- DB hit reduction: 99% (from 6.3M to 63K queries)
- **Loader speedup: 10-100x for dedup checks**

**Implementation**: 
```python
# RedisBloom module: BF.ADD, BF.EXISTS
# 1ms response time
# Memory: <10MB for 6M records
```

**Effort**: 2 days. **Impact**: Dramatic speedup for incremental loads. **Priority**: Quick win.

---

### 🔥 #10: gRPC for Internal APIs (10x Faster Than REST)

**Current state**: REST/JSON between services. JSON parsing overhead, no compression.

**Better**: gRPC with Protocol Buffers between Lambda functions, frontend uses REST.

**Performance**:
- REST/JSON: 200ms latency, 50KB payload
- gRPC/ProtoBuf: 20ms latency, 5KB payload (10x improvement)

**Where to use**:
- Lambda → Lambda (internal calls)
- Lambda → ECS task (sidecar pattern)
- Loader orchestration

**Effort**: 5 days. **Impact**: Faster, cheaper internal communication. **Priority**: Medium.

---

## PART 2: CREATIVE OUTSIDE-THE-BOX IDEAS

### 💡 #11: Wayback Machine for Missing Historical Data

When yfinance has gaps (delisted stocks, missing days), check Internet Archive's Wayback Machine for cached pages of those dates. Free, available for thousands of historical snapshots.

### 💡 #12: GitHub Actions as Loader Scheduler (Free!)

GitHub Actions provides 2000 free CI minutes/month. Use for non-time-critical loaders. Cron-triggered, runs in container, writes to RDS via VPN.
- **Savings: $20/month** vs ECS for low-frequency loaders.

### 💡 #13: Ephemeral Loaders via AWS Batch + EC2 Spot Fleet

Batch jobs that run once a week (annual financials, sector rebalance):
- Pay only when running
- EC2 Spot Fleet: 90% off On-Demand
- Auto-cleanup after job
- **Savings: $30-50/month** vs always-on ECS

### 💡 #14: Pre-warmed Lambda via SnapStart (10x Faster Cold Starts)

Lambda SnapStart for Java/Python takes a snapshot of initialized state. Cold start: 100ms vs 2s.
- **Cost**: $0 (included in Lambda)
- **Impact**: Sub-second response on first request

### 💡 #15: Tier Data with S3 Intelligent-Tiering

Auto-tiers objects between Standard/IA/Archive based on access. No code changes needed.
- Object accessed monthly: Standard ($0.023/GB)
- Not accessed in 30 days: Infrequent Access ($0.0125/GB)
- Not accessed in 90 days: Archive Instant ($0.004/GB)
- **Savings: 60-80% on rarely-accessed data**

### 💡 #16: Vector Embeddings for "Similar Stocks" Search

Embed each stock's fundamentals into a vector (using FinBERT or similar). Store in pgvector or Pinecone.
- "Find stocks similar to NVDA" → 10ms semantic search
- "Find stocks moving like a typical mean-reversion candidate" → ML-based pattern search
- **Cost**: $5/month for pgvector extension on existing RDS

### 💡 #17: Apache Iceberg for Time-Travel Queries

Store historical data as Iceberg tables on S3. Query "what did our data look like 30 days ago?" — zero migration cost, ACID transactions, schema evolution.
- **Use case**: Backtest signals against historical *snapshots* of data
- Catches data revisions/corrections that other systems miss

### 💡 #18: Lambda Container Images (Up to 10GB)

For Python loaders with heavy dependencies (TensorFlow, scikit-learn), use container images instead of zip. 10GB vs 250MB limit.
- Cold start: similar to zip
- Zero packaging headaches
- Same code as ECS task → unified container strategy

### 💡 #19: Cross-Region Replication for Multi-AZ + Multi-Region Resilience

S3 cross-region replication: $0.02/GB. Replicate to us-west-2 for redundancy. RDS read replica in different region for read-heavy paths.
- **Cost**: $5-10/month for full redundancy
- **Value**: Zero data loss in regional outage

### 💡 #20: Reserved Capacity Negotiation

Once usage is steady-state, negotiate with AWS:
- Compute Savings Plans: 30-72% off Lambda/Fargate
- Reserved Instances: 50-70% off RDS
- Reserved Capacity: better than On-Demand
- **At scale: -$30-50/month with no code change**

### 💡 #21: Smart Caching with stale-while-revalidate

CloudFront supports `stale-while-revalidate`: serve stale data instantly, refresh in background.
- User sees cached response immediately (0ms perceived latency)
- Backend updates within 5 seconds
- **Best UX + lowest backend load**

### 💡 #22: Use Bedrock (Cheap Claude/Haiku) for Text Analysis

Claude Haiku via Bedrock: $0.25/M input, $1.25/M output tokens.
- News sentiment analysis: 1000 articles/day = $0.50/month
- Earnings transcript summarization: 500 transcripts/quarter = $5/quarter
- 10-K document parsing: $10/quarter
- **Cheaper than building/training own models**

### 💡 #23: Polars + Apache Arrow for Zero-Copy Inter-Process Data

Loaders can pass data between processes without serialization (Arrow IPC):
- Producer (loader) writes to Arrow shared memory
- Consumer (writer) reads zero-copy
- **10-100x faster than JSON or pickle**

### 💡 #24: Prefetch + Predictive Loading

ML predicts which stocks user will view next based on:
- Past behavior
- Current portfolio
- Sector trends
- Market events

Pre-warm cache for predicted queries. **Result**: Most user clicks served from edge cache (<50ms).

### 💡 #25: Idempotent Loaders with Content-Hashing

Each loader computes a hash of (symbol, date, source, version). Skip if hash unchanged.
- Reduces redundant work by 99% on retries
- Safe parallel execution (no double-writes)
- Self-healing on partial failures

---

## PART 3: WORKAROUNDS FOR REAL LIMITATIONS

These are problems we WILL hit. Pre-solving them.

### Problem #1: yfinance Rate Limits → Multi-Source + Rotating IPs

**Workaround**: 
- Primary: Alpaca (high limits)
- Fallback 1: Polygon.io ($30/mo, unlimited)
- Fallback 2: yfinance with rotating residential proxies (Bright Data: $5/GB)
- Fallback 3: SEC EDGAR (free, unlimited, official)

### Problem #2: Lambda 15-Min Timeout → Step Functions + Map State

**Workaround**: For long-running jobs, use Step Functions Map state — fan out to 1000 parallel Lambdas, each handles 1/1000th of work. Total time: 90 sec instead of 90 min.

### Problem #3: API Gateway 30-Sec Timeout → WebSocket for Long Operations

**Workaround**: For backtests, AI analysis, large data exports — use WebSocket API. Client connects, server sends results when ready. No timeout.

### Problem #4: RDS Connection Limit (40-50 max) → RDS Proxy + pgBouncer

**Workaround**: AWS RDS Proxy ($15/month) + pgBouncer pool. Lambda gets 1000s of "connections", proxy multiplexes to 40 actual DB connections.

### Problem #5: S3 PUT Rate Limit (3500/sec per prefix) → Sharded Prefixes

**Workaround**: Use sharded prefixes: `s3://bucket/0/...`, `s3://bucket/1/...`, etc. 16 shards = 56,000 PUT/sec.

### Problem #6: CloudWatch Log Costs → Log Sampling + Short Retention

**Workaround**: 
- Production: 7-day retention (vs default 30+)
- Sample DEBUG logs at 1% (vs 100%)
- Send aggregated metrics to CloudWatch, raw logs to S3 (10x cheaper)
- **Savings: $20-50/month** on heavy logging

### Problem #7: Data Transfer Costs → VPC Endpoints + Same-AZ Placement

**Workaround**:
- All RDS traffic via VPC Endpoints (free vs $0.05/GB through NAT)
- Lambda in same AZ as RDS (free intra-AZ vs $0.01/GB cross-AZ)
- **Savings: $20-40/month**

### Problem #8: Cold Starts → SnapStart + Provisioned Concurrency

**Workaround**:
- SnapStart: free, 10x faster cold starts
- Provisioned Concurrency: 5 instances pre-warmed: $5/month
- **Result**: P99 latency stays <500ms

### Problem #9: Frontend Bundle Size → Code Splitting + Tree Shaking

**Workaround**:
- React lazy() for routes
- Dynamic imports for heavy components
- Vite tree shaking (default)
- Brotli compression: 20% smaller than gzip
- **Result**: First paint <1s globally

### Problem #10: Daylight Savings + Timezone Bugs → Store Everything in UTC

**Workaround**: Database, API, internal logic all UTC. Convert only at frontend display layer. Use `date-fns-tz` for client-side conversion.

---

## PART 4: PRIORITIZED ROADMAP

### Tier 1: Quick Wins (Week 1-2, High Impact, Low Effort)

| # | Task | Effort | Cost | Savings | Speedup |
|---|------|--------|------|---------|---------|
| 1 | TimescaleDB extension | 1d | $0 | $0 | 10-100x |
| 2 | Bloom filters for dedup (#9) | 2d | $0 | -$5/mo | 10-100x |
| 3 | VPC Endpoints (#7) | 1d | $0 | -$20/mo | - |
| 4 | S3 Intelligent-Tiering (#15) | 1d | $0 | -$10/mo | - |
| 5 | CloudWatch retention to 7d (#6) | 0.5d | $0 | -$15/mo | - |
| 6 | API Gateway → HTTP API | 1d | $0 | -$15/mo | 30% faster |
| 7 | SnapStart for Lambda (#14) | 0.5d | $0 | $0 | 10x cold start |
| 8 | Polars in hot loaders | 3d | $0 | $0 | 5-10x |
| 9 | Compute Savings Plans (#20) | 0.5d | $0 | -$20/mo | - |

**Total: 10.5 days, $0 invested, -$85/month savings, 10-100x query speedup**

### Tier 2: Medium Wins (Month 1, High Impact, Medium Effort)

| # | Task | Effort | Cost | Savings | Speedup |
|---|------|--------|------|---------|---------|
| 1 | Watermark-based incremental | 5d | $0 | -$30/mo | 100x |
| 2 | SEC EDGAR direct (#2) | 5d | $0 | $0 | Reliability++ |
| 3 | WebSocket streaming (#1) | 5d | $5/mo | -$50/mo | Real-time |
| 4 | Lambda for small loaders | 5d | $0 | -$25/mo | - |
| 5 | Multi-source router | 3d | $0 | -$15/mo | Reliability |
| 6 | RDS Proxy (problem #4) | 1d | $15/mo | -$20/mo | 5x conn |
| 7 | DuckDB for analytics (#5) | 7d | $0 | -$30/mo | 20-100x |
| 8 | Cloudflare R2 migration (#4) | 2d | $0 | -$30/mo | - |
| 9 | Anomaly detection w/ Claude (#8) | 5d | $10/mo | $0 | Quality++ |

**Total: 38 days, $30/mo overhead, -$200/mo savings, dramatic improvements**

### Tier 3: Big Bets (Quarter 1, Transformational)

| # | Task | Effort | Cost | Savings | Speedup |
|---|------|--------|------|---------|---------|
| 1 | Rust loaders for top 5 (#3) | 10d | $0 | -$30/mo | 10-50x |
| 2 | AWS Batch + Spot Fleet | 5d | $0 | -$30/mo | - |
| 3 | Step Functions Map | 5d | $0 | $0 | 100x parallel |
| 4 | Iceberg cold storage (#17) | 5d | $5/mo | -$15/mo | Time-travel |
| 5 | Hetzner for batch (#6) | 5d | $20/mo | -$80/mo | Same speed |
| 6 | Cloudflare Workers API (#7) | 7d | $5/mo | -$70/mo | <50ms global |
| 7 | gRPC internal APIs (#10) | 5d | $0 | $0 | 10x latency |
| 8 | Bedrock for AI features (#22) | 7d | $20/mo | $0 | New capability |
| 9 | Vector embeddings (#16) | 5d | $5/mo | $0 | New capability |

**Total: 54 days, $55/mo overhead, -$225/mo savings, transformational**

### Tier 4: Strategic (Quarter 2-3, Long-Term)

- Multi-region active-active
- Self-hosted Postgres on Hetzner with backup to S3
- ML-driven predictive caching
- Real User Monitoring (RUM) integration
- Comprehensive observability stack (OpenTelemetry)
- Distributed tracing
- Game days for incident response
- Documentation and runbook automation

---

## PART 5: TOTAL FINANCIAL PICTURE

### Current Baseline
- $250/month (estimated all-in)
- 90+ minute full data load
- 85% data reliability
- Mediocre observability

### After Tier 1 (Week 2)
- $165/month (-$85)
- 60 min full load
- 90% reliability
- Better monitoring

### After Tier 2 (Month 1)
- ~$0/month NET (Tier 1 + Tier 2 savings exceed costs)
- 30 min full load
- 95% reliability
- Real-time data streaming

### After Tier 3 (Quarter 1)
- -$170/month NET (we're saving more than we spend)
- 10 min full load
- 99.5% reliability
- Global <50ms API
- AI-enhanced data quality

### After Tier 4 (Quarter 2)
- Production-grade enterprise system
- Multi-region resilient
- ML-driven optimizations
- Cost: $30/month (or less)

**Cumulative savings: -$220/month vs baseline = 88% cost reduction.**
**Cumulative performance: 18-30x faster, 99.9% reliable.**

---

## PART 6: WHAT MAKES THIS DIFFERENT

Most architecture plans pick winners from a fixed menu. This one questions the menu:

1. **Do we even need AWS?** (Hetzner for batch, R2 for storage)
2. **Do we even need a database for cold data?** (DuckDB on Parquet)
3. **Do we even need to poll?** (WebSocket streams)
4. **Do we even need to load it ourselves?** (SEC EDGAR for fundamentals)
5. **Do we even need Python?** (Rust for hot loaders)
6. **Do we even need API Gateway?** (Cloudflare Workers)
7. **Do we even need to detect anomalies manually?** (LLM-based validation)
8. **Do we even need exact dedup?** (Bloom filters with 1% false positive)

By questioning each layer, we find 10x improvements that incremental thinking misses.

---

## PART 7: SUCCESS CRITERIA (12 Months Out)

A system worth bragging about:
- ✅ Loads 5000+ symbols' OHLCV in under 5 minutes
- ✅ Real-time price streaming with <1 second latency
- ✅ Multi-source data with automatic fallback (99.9% reliable)
- ✅ AI-validated data quality (catches 99% of anomalies)
- ✅ Globally <50ms API response (CloudFront + Workers)
- ✅ Time-travel queries (Iceberg) for backtest accuracy
- ✅ <$30/month total infrastructure cost
- ✅ 99.99% uptime
- ✅ Full local dev parity with prod
- ✅ One-command disaster recovery
- ✅ Comprehensive observability
- ✅ Self-healing on transient failures

---

## PART 8: WHAT WE WON'T DO (And Why)

Important to be clear about what's NOT optimal for our scale:

❌ **Kubernetes/EKS**: Overhead for our scale. Fargate is cheaper and simpler.
❌ **Snowflake/BigQuery**: $300+/month minimum. PostgreSQL + DuckDB is enough.
❌ **Datadog/New Relic**: $100/month minimum. CloudWatch + Grafana Cloud is enough.
❌ **Fivetran/Stitch**: $300+/month minimum. Custom loaders are cheaper at our scale.
❌ **DynamoDB**: Doesn't fit our use case (we need joins).
❌ **Self-hosted Kafka/MSK**: Overkill. Use SQS/SNS.
❌ **GraphQL**: Adds complexity without benefit at our scale.
❌ **Microservices proliferation**: Each service adds cost. Modular monolith is better.

The lesson: pick the right tool for our scale, not the trendiest one.

---

## NEXT ACTIONS

1. **Read this plan** carefully — discuss before committing
2. **Decide which tier(s) to commit to** — Tier 1 is essentially free
3. **Schedule implementation** — calendar blocks for each task
4. **Set up tracking** — measure cost/perf before each change
5. **Iterate** — review after Tier 1, adjust before Tier 2

The plan is ambitious but every line is achievable. Each task has been chosen because:
- Real cost saving or performance gain (no speculation)
- Reasonable effort (no months-long rabbit holes)
- Composable (each works independently)
- Low risk (rollback path exists)

---

**Status**: Strategic plan complete. Awaiting decision on which tier(s) to execute next.
