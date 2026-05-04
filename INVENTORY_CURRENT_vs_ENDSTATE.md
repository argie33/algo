# Complete Inventory: Current State vs End State

---

## SECTION 1: WORKFLOWS (GitHub Actions)

### CURRENT STATE (13 workflows)

| # | Workflow | Purpose | Status | Lines | Issue |
|---|----------|---------|--------|-------|-------|
| 1 | bootstrap-oidc.yml | GitHub OIDC setup (one-time) | ✅ Working | 53 | One-time, can keep as reference |
| 2 | deploy-infrastructure.yml | Deploy RDS + CloudFormation | ✅ Working | 165 | Core, necessary |
| 3 | deploy-core.yml | Deploy core AWS resources | ✅ Working | 80 | Core, necessary |
| 4 | deploy-webapp.yml | Deploy Lambda API + frontend | ✅ Working | 688 | Core, necessary |
| 5 | deploy-tier1-optimizations.yml | Cost/perf optimizations | ✅ Working | 215 | Core, necessary |
| 6 | **deploy-app-stocks.yml** | Data loaders pipeline | ❓ BROKEN | **1,787** | **Too complex, uses Phase C/D/E** |
| 7 | **manual-reload-data.yml** | Manual loader trigger | ⚠️ FRAGILE | 123 | **Hardcoded IDs, only 2 loaders** |
| 8 | **optimize-data-loading.yml** | Data optimization features | ⚠️ INCOMPLETE | 134 | **Doesn't execute loaders** |
| 9 | **test-automation.yml** | Test suite | ❌ DEAD | 566 | **Triggers on non-existent branches** |
| 10 | **pr-testing.yml** | PR testing | ⚠️ PLACEHOLDER | 437 | **Mostly empty, not critical** |
| 11 | **gemini-code-review.yml** | AI code review | ⚠️ MINIMAL | 45 | **Nice to have, not critical** |
| 12 | **deploy-billing.yml** | Billing alerts | ⚠️ UNCLEAR | 37 | **Unclear purpose** |
| 13 | **algo-verify.yml** | Algo verification | ⚠️ RUNS EVERY PUSH | 128 | **Likely fails due to stale data** |

**Total: 13 workflows, 4,462 lines**

### END STATE (5-6 workflows)

```
✅ bootstrap-oidc.yml              — GitHub OIDC (one-time setup)
✅ deploy-infrastructure.yml       — RDS + CloudFormation base
✅ deploy-core.yml                 — Core AWS resources
✅ deploy-webapp.yml               — Lambda API + frontend
✅ deploy-tier1-optimizations.yml  — Cost/perf optimizations
✅ deploy-loaders.yml              — Build Docker + register ECS tasks (NEW)
✅ deploy-loader-scheduler.yml     — Deploy EventBridge scheduler (NEW)
```

**Target: 6-7 workflows, ~2,000 lines**

**What to do with the rest:**
- ❌ DELETE: deploy-app-stocks.yml, manual-reload-data.yml, optimize-data-loading.yml, test-automation.yml, pr-testing.yml, gemini-code-review.yml, deploy-billing.yml, algo-verify.yml
- Consolidate all loader logic into **one clean workflow: deploy-loaders.yml**

---

## SECTION 2: CLOUDFORMATION TEMPLATES

### CURRENT STATE (12 templates)

| # | Template | Purpose | Status | Lines | Used By |
|---|----------|---------|--------|-------|---------|
| 1 | template-bootstrap.yml | GitHub OIDC | ✅ One-time | 46 | bootstrap-oidc.yml |
| 2 | template-app-stocks.yml | RDS database | ✅ Core | 244 | deploy-infrastructure.yml |
| 3 | template-core.yml | Core AWS (S3, CloudWatch, IAM) | ✅ Core | 416 | deploy-core.yml |
| 4 | template-webapp-lambda.yml | Lambda API + frontend | ✅ Core | 454 | deploy-webapp.yml |
| 5 | template-tier1-api-lambda.yml | HTTP API + SnapStart | ✅ Core | 243 | deploy-tier1-optimizations.yml |
| 6 | template-tier1-cost-optimization.yml | VPC endpoints, S3, CloudWatch | ✅ Core | 249 | deploy-tier1-optimizations.yml |
| 7 | **template-app-ecs-tasks.yml** | ECS task definitions | ⚠️ HUGE | **5,511** | **Dead workflow (deploy-app-stocks)** |
| 8 | **template-lambda-phase-c.yml** | Lambda fan-out (Phase C) | ❌ EXPERIMENTAL | 221 | **Only used by dead workflow** |
| 9 | **template-step-functions-phase-d.yml** | Step Functions DAG (Phase D) | ❌ EXPERIMENTAL | 332 | **Only used by dead workflow** |
| 10 | **template-phase-e-dynamodb.yml** | DynamoDB metadata (Phase E) | ❌ EXPERIMENTAL | 169 | **Only used by dead workflow** |
| 11 | **template-eventbridge-scheduling.yml** | EventBridge scheduler | ⚠️ NOT DEPLOYED | 243 | **None (will use for loaders)** |
| 12 | **template-optimize-database.yml** | DB optimizations | ❌ NEVER USED | 357 | **None** |

**Total: 12 templates, 8,885 lines**

### END STATE (6-7 templates)

```
✅ template-bootstrap.yml              — GitHub OIDC (reference)
✅ template-app-stocks.yml             — RDS database
✅ template-core.yml                   — Core AWS
✅ template-webapp-lambda.yml          — Lambda API + frontend
✅ template-tier1-api-lambda.yml       — HTTP API + SnapStart
✅ template-tier1-cost-optimization.yml — VPC endpoints, S3, etc
✅ template-ecs-loader-tasks.yml       — ECS task definitions for 61 loaders (NEW, REPLACE 5,511-line monster)
✅ template-loader-scheduler.yml       — EventBridge rules + Lambda orchestrator (NEW)
```

**Target: 7-8 templates, ~3,000 lines** (5,800+ lines saved by simplifying ECS tasks)

**What to do:**
- ❌ DELETE: template-lambda-phase-c.yml, template-step-functions-phase-d.yml, template-phase-e-dynamodb.yml, template-optimize-database.yml
- ❌ REPLACE: template-app-ecs-tasks.yml (5,511 → 400 lines, use loop to define all 61 loaders)
- ✅ REPURPOSE: template-eventbridge-scheduling.yml → template-loader-scheduler.yml

---

## SECTION 3: DOCKERFILES

### CURRENT STATE (78 files)

```
Dockerfile                           — Main API (needed)
Dockerfile.loader                    — Generic loader (needed)
Dockerfile.aaiidata                  — Individual loader (legacy)
Dockerfile.alpacaportfolio           — Individual loader (legacy)
... 74 more individual Dockerfiles ... (all legacy)
```

**Total: 78 files**

### END STATE (2 files)

```
✅ Dockerfile                    — Main API
✅ Dockerfile.loader            — Generic loader (uses ARG LOADER_SCRIPT=load*.py)
```

**Target: 2 files**

**What to do:**
- ✅ KEEP: Dockerfile, Dockerfile.loader
- ❌ DELETE: All 76 individual Dockerfiles (Dockerfile.load*.py)
- ⚠️ VERIFY: That Dockerfile.loader works for all loader types

---

## SECTION 4: LOADERS (Python files)

### CURRENT STATE (64 files)

Per documentation: should be 61 (41 official + 20 supplementary)
Actual: 64 files

**3 unaccounted loaders:**
- `loadearningsestimates.py` — Is this a duplicate of `loadearningsrevisions.py`?
- `load_algo_metrics_daily.py` — Documented as supplementary (with underscore prefix)
- `load_eod_bulk.py` — Undocumented
- `load_market_health_daily.py` — Documented
- `load_trend_template_data.py` — Documented

**Helper files mixed with loaders (should separate):**
- `optimal_loader.py` — Base class (needed)
- `watermark_loader.py` — Framework (needed)
- `bloom_dedup.py` — Helper (needed)
- `data_source_router.py` — Router (needed)
- `sec_edgar_client.py` — Client (needed)
- `loader_base_optimized.py` — Base (needed)
- `loader_metrics.py` — Metrics (needed)
- `loader_polars_base.py` — Base (needed)
- `loader_safety.py` — Safety (needed)

### END STATE (61 loaders + helpers organized)

**Official loaders (41):**
```
Phase 1: loadstocksymbols, loaddailycompanydata, loadmarketindices
Phase 2: loadpricedaily, loadpriceweekly, loadpricemonthly, loadlatestpricedaily, loadlatestpriceweekly, loadlatestpricemonthly
Phase 3: loadetfpricedaily, loadetfpriceweekly, loadetfpricemonthly, loadetfsignals
Phase 4: loadbuyselldaily, loadbuysellweekly, loadbuysellmonthly, loadbuysell_etf_daily, loadbuysell_etf_weekly, loadbuysell_etf_monthly
Phase 5: loadtechnicalsdaily
Phase 6: loadannualbalancesheet, loadquarterlybalancesheet, loadannualincomestatement, loadquarterlyincomestatement, loadannualcashflow, loadquarterlycashflow, loadttmincomestatement, loadttmcashflow
Phase 7: loadearningshistory, loadearningsrevisions, loadearningssurprise
Phase 8: loadstockscores, loadfactormetrics, loadrelativeperformance
Phase 9: loadmarket, loadecondata, loadcommodities, loadseasonality, loadsectorranking, loadindustryranking
Phase 10: loadanalystupgradedowngrade
```

**Supplementary (20):**
```
load_algo_metrics_daily, load_market_health_daily, load_trend_template_data
loadalpacaportfolio, algo_data_patrol, algo_data_freshness, backfill_historical_scores
loadaaiidata, loadnaaim, loadfeargreed, loadnews, loadanalystsentiment
loadetfsignals, loadmeanreversionsignals, loadrangesignals, loadcoveredcallopportunities, loadoptionschains, loadforwardeps, loadearningsestimates
loadcalendar, loadbenchmark, loadsectors, loadsentiment, loadsecfilings, loadmultisource_ohlcv
```

**Helpers (separate directory or clearly marked):**
```
optimal_loader.py
watermark_loader.py
bloom_dedup.py
data_source_router.py
sec_edgar_client.py
loader_base_optimized.py
loader_metrics.py
loader_polars_base.py
loader_safety.py
```

**Cleanup:**
- ❌ RESOLVE: The 3 extra/unclear loaders (investigate if duplicates)
- ✅ UPDATE: DATA_LOADING.md to match reality
- ✅ ORGANIZE: Helpers in clear separate section

---

## SECTION 5: RUNNING THE SYSTEM

### CURRENT STATE: How Loaders Actually Run

**Attempt 1: deploy-app-stocks.yml**
```
Trigger: On load*.py change
Flow: Detect → Build Docker → Deploy Phase C/D/E → ???
Status: ❌ BROKEN (no evidence it works)
```

**Attempt 2: manual-reload-data.yml**
```
Trigger: Manual dispatch
Flow: Run hardcoded ECS tasks (only 2 loaders)
Status: ⚠️ FRAGILE (hardcoded subnet/security group IDs)
```

**Attempt 3: optimize-data-loading.yml**
```
Trigger: Manual dispatch
Flow: Enable optimizations (TimescaleDB, multi-source)
Status: ⚠️ INCOMPLETE (doesn't execute loaders)
```

**Actual result:** Data is stale (2026-05-01 → today). **No loaders are running.**

### END STATE: How Loaders SHOULD Run

**Step 1: Build Docker Image**
```
Trigger: On load*.py change OR manual dispatch
Workflow: deploy-loaders.yml
Action: 
  1. Detect changed loaders
  2. Build Docker image (using Dockerfile.loader)
  3. Push to ECR
  4. Register ECS task definition
Result: Loader is ready to run in AWS
```

**Step 2: Run on Schedule**
```
Trigger: EventBridge rules (via CloudFormation)
Scheduler: template-loader-scheduler.yml
Schedule:
  - Intraday (every 90min):    loadlatestpricedaily
  - EOD (5:30pm ET):           All Phase 2-5 daily loaders
  - Weekly (Sat 8am):          Phase 2-5 weekly + scoring
  - Monthly (1st Sat):         Phase 2-5 monthly + factor metrics
  - Quarterly:                 Fundamentals + earnings
Result: Data loads automatically, stays fresh
```

**Step 3: Manual Override (if needed)**
```
Trigger: Manual dispatch to deploy-loaders.yml
Action: Run specific loader immediately
Result: One-off backfill or test
```

---

## SECTION 6: THE GAP (What's Missing)

### Broken/Missing Components

| Component | Current | End State | Status |
|-----------|---------|-----------|--------|
| Loader deployment | 3 overlapping broken approaches | 1 clean workflow | ❌ MISSING |
| Scheduler | EventBridge template (not deployed) | Deployed EventBridge rules | ❌ MISSING |
| ECS tasks for loaders | 5,511-line monster template | ~400-line simple template | ❌ NEEDS REPLACEMENT |
| Docker image strategy | 78 individual Dockerfiles | 1 generic + 1 API | ❌ NEEDS CLEANUP |
| Data freshness | Stale (3 days old) | Current (loaded daily) | ❌ BROKEN |
| Loader inventory | 64 files (3 unaccounted) | 61 files (documented) | ⚠️ OUT OF SYNC |

### Clean-up Required

| Item | Count | Action |
|------|-------|--------|
| Workflows to delete | 8 | Remove dead/broken workflows |
| Templates to delete | 4 | Remove experimental Phase C/D/E, database optimization |
| Dockerfiles to delete | 76 | Remove individual loader images |
| Workflows to create | 2 | deploy-loaders.yml, deploy-loader-scheduler.yml |
| Templates to create | 2 | template-ecs-loader-tasks.yml (simplified), template-loader-scheduler.yml |
| Templates to replace | 1 | template-app-ecs-tasks.yml (5,511 → 400 lines) |

---

## SUMMARY

### Current Reality
- **13 workflows**, 4 of which are broken or dead
- **12 templates**, 4 of which are experimental or unused
- **78 Dockerfiles**, 76 of which are legacy
- **64 loaders**, 3 unaccounted for
- **Data is stale** — nothing runs on schedule

### End State Vision
- **6 workflows**, all focused and working
- **7 templates**, organized by concern
- **2 Dockerfiles**, clear source of truth
- **61 loaders**, fully documented
- **Data flows daily** — EventBridge scheduler runs loaders on schedule

### Path Forward
1. ✅ Understand current state (DONE — this document)
2. ⏳ Verify AWS state (check what's actually deployed)
3. ⏳ Simplify templates (replace 5,511-line ECS tasks)
4. ⏳ Create new workflows (deploy-loaders.yml, deploy-loader-scheduler.yml)
5. ⏳ Delete dead code (8 workflows, 4 templates, 76 Dockerfiles)
6. ⏳ Deploy scheduler (make it run on schedule)
7. ⏳ Verify data loads (check database for fresh data)

