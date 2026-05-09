# Stock Analytics Platform — System Audit & Roadmap (2026-05-09)

## Executive Summary

You've built a **solid foundation** — 165 modules, 7-phase orchestrator, 6 CloudFormation stacks, 25+ API endpoints, professional frontend, and deployed AWS infrastructure. **But it's not cohesive yet.** There are real wiring gaps, incomplete data pipelines, monitoring blind spots, and architectural loose ends.

**Key finding:** You have ~70% of a production-grade algo platform, but the missing 30% is causing friction in daily operations. This roadmap fixes that.

---

## PART 1: CURRENT STATE (What You Have)

### ✅ What's Working Well

#### Infrastructure (Solid Foundation)
- **AWS Deployment:** 145 CloudFormation resources deployed, auto-scaling EventBridge, Lambda+ECS orchestration
- **IaC & Versioning:** All infrastructure code-controlled, reproducible deployments
- **Database:** PostgreSQL 14 with 21M+ price rows, 19M+ indicators, structured schema
- **Compute:** Lambda (algo + API), ECS (loaders), serverless design, $77/month cost target achieved
- **Frontend:** 25 pages, all API endpoints wired, professional React/Vite UI

#### Core Algo (Safe & Feature-Complete)
- **7-Phase Orchestrator:** Data → Signals → Exits → Entries → Trades → Reconciliation → Audit (well-designed flow)
- **Risk Management:** Circuit breakers (drawdown, daily loss, VIX, market stage), position sizing (Kelly), exposure limits
- **Safety:** 11 production blockers fixed, fail-closed on zero data, audit trail on every decision
- **Signals:** Multi-factor scoring, technical patterns, quality filters, 5-tier pipeline
- **Trading:** Alpaca paper trading, order execution with fail-safes, P&L tracking

#### Observability (Good Start)
- **Loader Monitoring:** Built system that detects silent failures, fails algo closed on zero data
- **Audit Log:** Complete decision trail (Phase 1-7 actions)
- **CloudWatch Logs:** All Lambda functions logged to 7-day retention
- **Alerts:** Email/Slack on critical events

#### Data Loaders (Partially Working)
- **18 Official Loaders:** Symbol universe, daily/weekly/monthly prices, scores, signals, earnings, Alpaca portfolio
- **Constraint Discipline:** No experimental loaders, strictly official sources only
- **Scheduling:** EventBridge cron at 4am ET (partially configured)

---

### ⚠️ Gaps & Holes (Why It Doesn't Feel Cohesive)

#### **1. Data Pipeline Issues**

| Gap | Impact | Current State | Issue |
|-----|--------|---------------|-------|
| **Loader Triggering** | Algo can't run if no data loaded | Manual ECS triggers only | EventBridge daily trigger not wired to ECS loaders |
| **Watermarking** | Reloading same data repeatedly | Full daily reload (wasteful) | No incremental load tracking — every run is a full re-fetch |
| **Multi-Source Fallbacks** | Data loss if primary source fails | yfinance only | No fallback to Alpaca or Polygon if yfinance down |
| **Stage 2 Data Gap** | Missing current prices for BRK.B, LEN.B, WSO.B | Data exists but stale | Loader doesn't handle these symbols correctly |
| **ETF vs Stock Handling** | Separate loaders, code duplication | 18 loaders (stock × 3 + ETF × 3 variants) | No unified loader template — maintenance nightmare |
| **Post-Market Data** | Prices loaded at 4am but algo runs at 5:30pm | 1.5-hour lag | Could load afternoon updates but doesn't |

**Root Cause:** Loaders built individually, no orchestration layer to: trigger → validate → retry → alert

#### **2. Architecture Fragmentation**

| Component | Current | Best Practice | Gap |
|-----------|---------|----------------|-----|
| **Data Quality** | Manual checks in Phase 1 | Continuous monitoring | No proactive data patrol (checks happen at trade time, not load time) |
| **Algo Parameters** | Hardcoded in algo_config.py | Feature flags + parameter store | Can't disable signals without code deploy |
| **Signal Tuning** | Backtest then deploy | A/B testing framework | No way to compare signal A vs B in production |
| **Execution** | Single Alpaca account | Multi-account/broker routing | Can't diversify execution or hedge across accounts |
| **Backtesting** | Historical validation only | Walk-forward, Monte Carlo, stress tests | Limited to past data, no robustness analysis |

#### **3. Observability Gaps**

| What's Missing | Why It Matters | Current State |
|---|---|---|
| **Query Performance Dashboard** | Know which queries are slow | No monitoring — RDS hidden |
| **Data Freshness Dashboard** | Real-time view of what's stale | Email alerts only |
| **Signal Performance Tracker** | Which signals work vs don't | Manual review of audit log |
| **Loader Health Timeline** | When did loaders last succeed? | No execution history stored |
| **Trade Slippage Analysis** | Entry vs actual fill price | Not tracked in audit log |
| **Cost Attribution** | Which loaders/signals cost most? | No tagged metrics |

#### **4. Operational Friction**

| Pain Point | Impact | Current State |
|---|---|---|
| **Manual Loader Trigger** | Data loads late or not at all | `aws ecs run-task` every morning |
| **No Loader Retry Logic** | One failure blocks all | ECS task fails → manual restart needed |
| **Terraform Partial** | IaC incomplete | CloudFormation is primary, Terraform has issues (seen in uncommitted changes) |
| **Local Dev vs AWS Parity** | Changes that work locally fail in AWS | Docker Compose ≠ AWS environment (creds, ENV vars, secrets) |
| **No Secrets Rotation** | Credentials could be leaked for months | Manual rotation only |
| **Limited Rollback Story** | Can't quickly revert bad code | Only git revert + redeploy (slow) |

#### **5. Known Limitations (Intentional But Limiting)**

- Paper trading only — no real money flow, no execution verification against real market
- RDS publicly accessible (0.0.0.0/0) — fine for dev, but not "production-ready" even for staging
- Lambda not in VPC — can reach internet directly, which is good for data loading but bad for security boundaries
- No staging environment — can only test in dev
- No disaster recovery runbook — if RDS dies, no backup+restore procedure documented

---

## PART 2: BEST PRACTICES COMPARISON

### Citadel-Grade Algorithmic Trading Platform

**What industry leaders do:**

#### 1. **Data Pipeline Architecture**
- ✅ **You have:** 18 loaders, PostgreSQL
- ❌ **You're missing:**
  - Streaming data (Kafka/Kinesis) for intraday updates
  - Watermarking (track what's loaded, avoid re-fetching)
  - Unified data model (loaders → stream → warehouse → cache)
  - Dead-letter queue for failed ingests
  - Schema validation at entry point

#### 2. **Observability & Monitoring**
- ✅ **You have:** CloudWatch logs, audit trail
- ❌ **You're missing:**
  - Real-time dashboards (Grafana/Datadog)
  - SLA tracking (loaders must finish by 4:30am)
  - Anomaly detection (sudden data gaps, unusual trades)
  - Cost breakdown per feature (per loader, per signal)
  - Performance profiling (query times, algo execution time)

#### 3. **Risk Management**
- ✅ **You have:** Circuit breakers, position limits, Kelly criterion
- ❌ **You're missing:**
  - Real-time position monitoring during market hours (only at 5:30pm)
  - Intraday P&L tracking
  - Correlation/concentration alerts
  - Slippage analysis (entry intention vs execution)
  - Stress test scenarios (what if VIX +50%?)

#### 4. **Trading Execution**
- ✅ **You have:** Order execution, Alpaca integration
- ❌ **You're missing:**
  - Smart order routing (multiple brokers)
  - VWAP/TWAP execution strategies
  - Partial fill handling
  - Execution cost tracking
  - Broker-side risk checks (duplicate prevention)

#### 5. **Experimentation & Tuning**
- ✅ **You have:** Backtest framework
- ❌ **You're missing:**
  - Feature flags (A/B test signals in production)
  - Parameter optimization (gradient descent, grid search)
  - Walk-forward testing (rolling window backtests)
  - Sensitivity analysis (which params matter?)
  - Online learning (adapt based on recent performance)

#### 6. **Infrastructure**
- ✅ **You have:** IaC (CloudFormation), auto-scaling, serverless compute
- ❌ **You're missing:**
  - Multi-region failover
  - Staging/prod separation
  - Blue/green deployments
  - Canary releases (test new signals on % of portfolio)
  - Rollback automation

---

## PART 3: PRIORITY ROADMAP (Next 6 Weeks)

### **CRITICAL PATH (Unblock Operational Dailies)**

These must work reliably for the algo to run consistently.

#### Week 1: Data Pipeline Wiring
**Goal:** Loaders run autonomously, data guaranteed fresh daily

- [ ] **Wire EventBridge → ECS Loaders**
  - Create EventBridge rule: daily 4:00am ET trigger
  - Target: ECS task (run all loaders in parallel)
  - Add retry logic (auto-retry on failure 3x)
  - Add SNS alert on failure
  - Verify 5+ consecutive days of unattended runs
  - **Time:** 2-3 hours
  - **Files:** `terraform/modules/loaders/main.tf`, EventBridge rule in CloudFormation

- [ ] **Add Watermarking to Loaders**
  - Track `last_loaded_date` per data source in database
  - Modify `loadpricedaily.py`, `loadpriceweekly.py` to check watermark
  - Only fetch data since last load + 1 day (overlap for safety)
  - Reduces API calls by 80-90%
  - **Time:** 3-4 hours
  - **Files:** `init_db.sql` (add watermarks table), modify all `load*.py`

- [ ] **Add Multi-Source Fallback**
  - yfinance primary → Alpaca secondary → Polygon tertiary
  - Implement in `data_source_router.py`
  - Track which source was used per symbol per day
  - Alert if primary source fails but secondary succeeds
  - **Time:** 2-3 hours
  - **Files:** `data_source_router.py`, `algo_config.py`

#### Week 2: Observability Wiring
**Goal:** See what's happening in real-time, no more surprises

- [ ] **Build Data Freshness Dashboard**
  - Real-time page showing: last load timestamp, symbols loaded today, any gaps
  - Query: `SELECT symbol, MAX(date) FROM price_daily GROUP BY symbol`
  - Show red/yellow/green (stale/warning/fresh)
  - Add to existing webapp frontend
  - **Time:** 2-3 hours
  - **Files:** `webapp/frontend/src/pages/DataFreshnessDashboard.jsx`, add API endpoint

- [ ] **Add Loader Execution History**
  - Create `loader_execution` table: (timestamp, loader_name, status, rows_loaded, elapsed_ms, error)
  - Log every ECS task execution
  - Query historical: "Did loaders run yesterday? When did they fail?"
  - **Time:** 1-2 hours
  - **Files:** `init_db.sql`, modify all loaders to emit status

- [ ] **Add Signal Performance Tracking**
  - Track: `(signal_name, date, hit_rate, avg_return, win_rate)`
  - Auto-generate from audit log + actual trade results
  - Dashboard showing which signals work/don't
  - **Time:** 2 hours
  - **Files:** `webapp/frontend/src/pages/SignalPerformance.jsx`, backend API

#### Week 3: Algo Stability & Config
**Goal:** Change algo behavior without redeploying

- [ ] **Add Feature Flags**
  - Store in database: `(feature_name, enabled, created_at, updated_at)`
  - Modify each signal filter: `if flags.get('signal_momentum'): ...`
  - Modify each risk check: `if flags.get('circuit_breaker_vix'): ...`
  - Add UI toggle in admin panel
  - Allows disabling broken signals at 5:29pm (before algo run at 5:30pm)
  - **Time:** 2-3 hours
  - **Files:** Create `algo_feature_flags.py`, modify `algo_filter_pipeline.py`, `algo_circuit_breaker.py`, etc.

- [ ] **Parameter Store Integration**
  - Move hardcoded thresholds to AWS Secrets Manager / Parameter Store
  - Examples: `kelly_fraction=0.25`, `max_position_size=2000`, `vix_kill_threshold=40`
  - Allow editing without code changes
  - Cache locally to avoid 100ms latency per check
  - **Time:** 1-2 hours
  - **Files:** `algo_config.py`, add parameter fetch on Lambda startup

- [ ] **Add Slack Real-Time Alerts**
  - Bind Phase 1-7 alerts to Slack webhook
  - Show: phase, status, positions opened/closed, P&L
  - Allows real-time monitoring without checking logs
  - **Time:** 1 hour
  - **Files:** `algo_alerts.py`

#### Week 4: Testing & Validation
**Goal:** Confidence that changes don't break things

- [ ] **Add E2E Test Suite**
  - Test: `load price → verify freshness → run signals → execute trades → reconcile`
  - Run against test database (separate from production)
  - Verify both successful and failure paths (e.g., "zero data loads" → algo halts)
  - Run on every commit
  - **Time:** 3-4 hours
  - **Files:** Create `tests/e2e_pipeline_test.py`

- [ ] **Add Backtest Regression Suite**
  - Current: Single backtest snapshot
  - Better: Run backtest on every code change, compare results
  - Alert if new code *breaks* historical returns
  - Prevent accidental signal degradation
  - **Time:** 2 hours
  - **Files:** Modify CI workflow, store baseline equity curve

- [ ] **Add Load Testing**
  - Simulate: API gets 100 concurrent requests, loaders run in parallel
  - Verify: RDS doesn't timeout, Lambda doesn't exceed memory
  - Identify bottlenecks before production
  - **Time:** 2 hours
  - **Files:** Create `tests/load_test.py` using `locust` or similar

#### Week 5: Cleanup & Refactor
**Goal:** Code is maintainable and follows patterns

- [ ] **Unify Loader Architecture**
  - Current: `loadpricedaily.py`, `loadpriceweekly.py`, ... all different
  - Better: Single `TemplateLoader` class, subclass for each data source
  - Reduces 18 loaders → 6-8 with shared logic
  - Easier to add new loaders or fix bugs across all
  - **Time:** 4-5 hours
  - **Files:** Create `loader_template.py`, refactor all `load*.py`

- [ ] **Consolidate IaC (CloudFormation → Terraform)**
  - You have both CF and TF partially
  - Pick one as source of truth, auto-generate the other OR fully switch to Terraform
  - Current uncommitted changes suggest you're moving to Terraform — complete this
  - **Time:** 4-6 hours
  - **Files:** `terraform/` directory, finalize modules

- [ ] **Add Type Hints & Linting**
  - Add mypy type checking (find bugs before they run)
  - Add pydantic for data validation
  - Enforce linting on all code (black, flake8)
  - **Time:** 2-3 hours
  - **Files:** `pyproject.toml`, update all `.py` files with type hints

#### Week 6: Documentation & Handoff
**Goal:** System is understandable and maintainable

- [ ] **Update Decision Matrix for New Features**
  - Current: Good start but incomplete
  - Add: "How to add a new signal?" "How to disable a signal?" "How to add a data source?"
  - **Time:** 1 hour

- [ ] **Create Runbooks**
  - "Data is stale — what to do?"
  - "Algo not trading — debug steps"
  - "Loader failed — recovery procedure"
  - "How to deploy a signal change safely"
  - **Time:** 2-3 hours

- [ ] **Create Admin Onboarding Guide**
  - New person can understand: data sources, signals, risk limits, alerts
  - How to monitor health
  - How to make safe changes
  - **Time:** 2 hours

---

### **NICE-TO-HAVE (After Core Works)**

These improve the algo but aren't blocking:

#### Performance & Cost
- **TimescaleDB:** 10-100x query speedup on time-series (hypertables, compression)
- **Query Caching:** Cache signal results for 5min (fewer DB hits)
- **Lambda Optimization:** ARM64 + SnapStart already done, consider memory tuning
- **RDS Optimization:** Add read replicas, enable caching mode for read-heavy workloads

#### Experimentation
- **A/B Testing Framework:** Compare signal A vs B on % of portfolio
- **Walk-Forward Backtesting:** Rolling window validation
- **Parameter Optimization:** Grid search / genetic algorithm for tuning
- **Online Learning:** Adapt weights based on recent 5-day performance

#### Advanced Monitoring
- **Real-Time Positions:** Intraday P&L dashboard (currently only at 5:30pm)
- **Slippage Analysis:** Entry intention vs actual fill price
- **Cost Attribution:** Which loaders/signals drive returns vs costs?
- **Correlation Heatmap:** See exposure overlaps

---

## PART 4: QUICK WINS (Do These First)

Do these in next 2-3 days to remove immediate pain:

1. **Wire EventBridge → ECS (2 hours)**
   - Just connect the scheduler to the loader task
   - Verify 1-2 manual runs first, then automate
   
2. **Add Data Freshness Query (1 hour)**
   - One-liner: `SELECT symbol, MAX(date) FROM price_daily GROUP BY symbol`
   - Add to admin dashboard or simple report
   - Answers "Is data fresh?" without hunting logs

3. **Add Loader Execution Logging (1 hour)**
   - Every loader: before exit, `INSERT INTO loader_execution (...) VALUES (...)`
   - Answers "Did loaders run last night?" in seconds

4. **Add Slack Alert on Loader Failure (30 min)**
   - Just hook SNS → Slack webhook
   - Get notified immediately instead of discovering stale data hours later

5. **Feature Flag for Signal Enable/Disable (1 hour)**
   - Add database table: `(name, enabled, updated_at)`
   - In each filter: `if DB.get_flag('momentum_enabled'): ...`
   - Allows disabling broken signals without code deploy

---

## PART 5: METRICS (How to Know It's Working)

Use these to track progress:

| Metric | Current | Target (Week 6) | How to Measure |
|--------|---------|-----------------|-----------------|
| **Data Freshness** | Manual checks | 100% automated | All prices loaded by 4:30am daily |
| **Loader Success Rate** | ~80% (failures require manual restart) | 99%+ | Consecutive successful auto-runs |
| **Algo Run Reliability** | 100% when data arrives | 100% (but data always arrives) | No crashes, complete audit trail |
| **Observability Score** | 3/10 (logs only) | 8/10 (dashboards, alerts, history) | Can answer "What happened?" in <30 sec |
| **Code Quality** | 60% (some type hints) | 90% (full typing, linting) | mypy clean, flake8 clean |
| **Deployment Confidence** | 50% (worried about surprises) | 90% (tests catch regressions) | New code tested before production |
| **Operational Friction** | High (manual triggers) | Low (autonomous) | No manual intervention needed 5x/week |

---

## PART 6: RISK AREAS (Watch These)

These could bite you if not addressed:

1. **Data Pipeline Fragility** → Loaders fail silently, algo runs on stale data
   - *Mitigation:* EventBridge wiring + watermarking + alerts (Week 1)

2. **Config Coupling** → Can't change signal thresholds without code deploy
   - *Mitigation:* Feature flags + parameter store (Week 3)

3. **No Staging** → Changes tested only in dev, fail in production
   - *Mitigation:* Add staging environment (after core works)

4. **Execution Verification Missing** → Orders execute but aren't tracked properly
   - *Mitigation:* Add Alpaca sync check, verify fills match orders (Week 2)

5. **Credentials in Code** → API keys, DB passwords could be exposed
   - *Mitigation:* Already using Secrets Manager — verify not overridden locally

---

## PART 7: FILES TO MODIFY (Roadmap Mapping)

### Week 1 (Data Pipeline)
- `terraform/modules/loaders/main.tf` — EventBridge rule
- `init_db.sql` — watermarks table
- `loader_base_optimized.py` (you're already working on this!)
- `loadpricedaily.py`, others — add watermark checks
- `data_source_router.py` — multi-source fallback

### Week 2 (Observability)
- `webapp/frontend/src/pages/DataFreshness.jsx` — new page
- `webapp/lambda/routes/stocks.js` — new `/api/data-freshness` endpoint
- `init_db.sql` — `loader_execution` table
- All `load*.py` — emit execution status

### Week 3 (Config)
- Create `algo_feature_flags.py`
- `algo_filter_pipeline.py` — add flag checks
- `algo_circuit_breaker.py` — add flag checks
- `algo_config.py` — parameter store integration

### Week 4 (Testing)
- `.github/workflows/ci-*.yml` — add E2E test
- Create `tests/e2e_pipeline_test.py`
- Modify backtest CI

### Week 5 (Cleanup)
- Create `loader_template.py`
- Refactor `load*.py` to inherit from template
- `terraform/` — complete migration from CloudFormation (or vice versa)

---

## PART 8: DECISION: What's Your North Star?

Before executing, pick one:

**Option A: Minimum Viable Production (8 weeks)**
- Focus: Data reliability + observability + safe deployment
- Target: System runs autonomously, you can trust what's happening
- Nice features come later

**Option B: Feature-Rich but Less Stable (16+ weeks)**
- Focus: Advanced signals, A/B testing, multi-broker execution
- Risk: Complexity added before fundamentals stabilized

**Recommendation:** **Option A.** Get the boring stuff right first (data, monitoring, deployments), then add features on a stable foundation. Every week spent on untested features now will cost you 3 weeks debugging later.

---

## Summary

You have **a good engine with poor visibility.** Fix visibility + wiring first (Weeks 1-4), then optimize (Weeks 5-6).

**Starting point:** Event your EventBridge → ECS trigger this week. That unblocks autonomous operation. Everything else flows from there.

