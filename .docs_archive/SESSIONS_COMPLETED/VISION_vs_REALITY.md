# Vision vs Reality — Understanding What Should Be

---

## PART 1: THE VISION (Per Documentation)

### From CLAUDE.md — The Intended Architecture

```
ONE API server: webapp/lambda/index.js (Express, runs on port 3001 locally, Lambda in prod)
ONE frontend: webapp/frontend (Vite, port 5174)
ONE database: PostgreSQL RDS (VPC, private subnet)
ONE data loading system: 41 official + 20 supplementary loaders
```

**The Stack:**
```
Frontend (React)
    ↓
API (Lambda/Express)
    ↓
Database (RDS PostgreSQL)
    ↑
Loaders (ECS Fargate tasks on schedule)
```

### From DATA_LOADING.md — The Loading Strategy

```
OFFICIAL LOADERS (41):
  Phase 1: Universe & Symbols (3)
  Phase 2: Price Data (6)
  Phase 3: ETF Data (4)
  Phase 4: Pine Signals (6)
  Phase 5: Technical Indicators (1)
  Phase 6: Fundamentals (8)
  Phase 7: Earnings (3)
  Phase 8: Scoring & Metrics (3)
  Phase 9: Market Data & Sector (6)
  Phase 10: Analyst Sentiment (1)

SUPPLEMENTARY (20):
  Algo computed metrics (3)
  Algo operational (4)
  Sentiment & behavioral (5)
  Specialized signals (5)
  Calendar & reference (3)

TOTAL: 61 loaders, run in dependency order
```

**The Schedule (Per LOADER_SCHEDULE.md):**
```
Intraday (every 90min):     loadlatestpricedaily
EOD (5:30pm ET):            All Phase 2-5 daily loaders + metrics
Weekly (Sat 8am):           Phase 2-5 weekly + scoring
Monthly (1st Sat):          Phase 2-5 monthly + factor metrics
Quarterly:                  Fundamentals + earnings
```

### From ALGO_ARCHITECTURE.md — The Algo System

```
Buy/Sell signals from Pine Script (loaded via loadbuyselldaily, etc)
    ↓
Algo evaluates signals (6 tiers of filtering)
    ↓
Scores candidates (swing_trader_scores)
    ↓
Executes trades (Alpaca paper trading)
    ↓
Manages exits (11-rule hierarchy)
```

---

## PART 2: THE REALITY (What We Actually Have)

### Local State

```
Loader files:           64 (should be 61)
Dockerfiles:            78 (should be 2)
CloudFormation:         12 templates (should be 6)
GitHub Actions:         13 workflows (should be 5)
Helper/base classes:    6+ (optimal_loader, watermark_loader, etc)
```

### Deployment State

```
Database:               ✅ RDS running (healthy, 21M+ rows in price_daily)
API:                    ✅ Lambda deployed (webapp/lambda/index.js)
Frontend:               ✅ S3 + CloudFront deployed
Loaders in AWS:         ❓ UNCLEAR (probably not running)
Scheduler:              ❌ NOT DEPLOYED (EventBridge template exists but not used)
Data freshness:         ❌ STALE (latest: 2026-05-01, today: 2026-05-04)
```

### What We Know Works

```
✅ Database connectivity
✅ API endpoint responses
✅ Frontend loads
✅ OptimalLoader framework (locally)
✅ Dockerfile.loader (generic, tested)
❓ Loader deployment to AWS (unclear)
❌ Scheduled loader execution (not running)
```

### What's Broken/Unclear

```
❌ Data is 3 days stale
❌ No evidence loaders run in AWS
❌ Three conflicting deployment approaches (deploy-app-stocks, manual-reload, optimize)
❌ Phase C/D/E templates (experimental, unclear if deployed)
❌ Test automation (triggers on non-existent branches)
❌ 78 individual Dockerfiles (confusing, redundant)
❌ No scheduler deployed
```

---

## PART 3: THE GAPS

### What We Said We'd Do (Vision) vs What Actually Happens (Reality)

| What Should Happen | What Actually Happens | Status |
|-------------------|----------------------|--------|
| Loaders run on schedule (EOD daily, weekly, monthly) | Data hasn't loaded since 2026-05-01 | ❌ BROKEN |
| One clear "run a loader" mechanism | Three conflicting workflows (deploy-app-stocks, manual-reload, optimize) | ❌ CONFUSING |
| Generic Dockerfile.loader for all loaders | 78 individual Dockerfiles + generic | ⚠️ REDUNDANT |
| Simple ECS task definitions | Huge template-app-ecs-tasks.yml (5,511 lines) | ⚠️ OVERCOMPLEX |
| EventBridge scheduler deployed | Template exists but not deployed | ❌ MISSING |
| 61 official loaders + 20 supplementary | 64 loaders on disk (3 unaccounted) | ⚠️ OUT OF SYNC |
| Clear infrastructure definition | 12 templates with unclear relationships | ⚠️ UNCLEAR |
| Test automation running | test-automation.yml triggers on non-existent branches | ❌ BROKEN |

---

## PART 4: QUESTIONS WE NEED TO ANSWER BEFORE DELETING

### About Phase C/D/E Templates

1. **Are they deployed in AWS?**
   - If YES: What stacks exist? (CloudFormation list-stacks)
   - If NO: Safe to delete
   - **Current assumption:** NOT deployed (no evidence they work)

2. **Are they referenced anywhere?**
   - template-lambda-phase-c.yml: Used by deploy-app-stocks.yml (which is probably broken)
   - template-step-functions-phase-d.yml: Used by deploy-app-stocks.yml
   - template-phase-e-dynamodb.yml: Used by deploy-app-stocks.yml
   - **Conclusion:** Only used by dead workflow, safe to delete

### About Individual Dockerfiles

1. **Are any of them actually used?**
   - deploy-app-stocks.yml references them
   - No other workflow references them
   - **Conclusion:** Probably not used, safe to delete after testing Dockerfile.loader

2. **Can Dockerfile.loader handle all 61 loaders?**
   - Yes — it's generic, uses ARG LOADER_SCRIPT
   - **Conclusion:** Safe to delete individual ones

### About The Three Loader Workflows

1. **deploy-app-stocks.yml (1787 lines)**
   - Tries to: Detect changes → Build Docker → Deploy CloudFormation → Run loaders
   - Problem: Too complex, uses Phase C/D/E, no evidence it works
   - Alternative: Create simpler deploy-loaders.yml

2. **manual-reload-data.yml (123 lines)**
   - Tries to: Manually run specific ECS tasks
   - Problem: Hardcoded subnet/security group IDs, only 2 loaders
   - Question: Is this how loaders are actually being run?

3. **optimize-data-loading.yml (134 lines)**
   - Tries to: Enable optimizations (TimescaleDB, multi-source)
   - Problem: Incomplete, doesn't execute loaders
   - Question: Is this ever used?

---

## PART 5: THE ARCHITECTURE WE SHOULD HAVE

### Tier 1: Core Infrastructure (Never Changes)

```
template-app-stocks.yml        → RDS database + networking
template-core.yml              → S3, CloudWatch, IAM basics
template-bootstrap.yml         → One-time GitHub OIDC setup
```

**Deployed by:**
```
deploy-infrastructure.yml       → RDS, database setup
deploy-core.yml                → Core AWS resources
```

---

### Tier 2: Application (Changes when webapp code changes)

```
template-webapp-lambda.yml     → Lambda API + API Gateway + S3 frontend
template-tier1-api-lambda.yml  → HTTP API migration + SnapStart
template-tier1-cost-optimization.yml → VPC endpoints, S3 lifecycle, CloudWatch retention
```

**Deployed by:**
```
deploy-webapp.yml              → Lambda + frontend
deploy-tier1-optimizations.yml → Cost/perf improvements
```

---

### Tier 3: Data Loading (Our Problem Area)

**What we need:**
```
template-ecs-loader-tasks.yml       → ECS task definitions for 61 loaders
                                       (REPLACE the 5,511-line monster with simple version)

template-loader-scheduler.yml       → EventBridge rules + Lambda orchestrator
                                       (Deploy loaders on schedule)

Dockerfile.loader                   → Generic loader image
                                       (Delete 76 individual ones)
```

**Deployed by:**
```
deploy-loaders.yml                 → Build Docker, register ECS tasks
deploy-loader-scheduler.yml        → Deploy EventBridge scheduler
```

---

## PART 6: THE SAFETY MATRIX

### Safe to Delete NOW

```
✅ deploy-app-stocks.yml                 — Broken, complex, experimental
✅ manual-reload-data.yml                — Hardcoded, fragile
✅ optimize-data-loading.yml             — Incomplete
✅ test-automation.yml                   — Dead code (non-existent branches)
✅ pr-testing.yml                        — Placeholders
✅ gemini-code-review.yml                — Not critical
✅ deploy-billing.yml                    — Unclear purpose
✅ algo-verify.yml                       — Can move to cron later

✅ template-lambda-phase-c.yml           — Experimental, only used by dead workflow
✅ template-step-functions-phase-d.yml   — Experimental, only used by dead workflow
✅ template-phase-e-dynamodb.yml         — Experimental, only used by dead workflow
✅ template-optimize-database.yml        — Never deployed, dead code

✅ Dockerfile.aaiidata through           — All 76 individual Dockerfiles
   Dockerfile.ttmincomestatement         (keep only Dockerfile.loader)
```

### Safe to Replace

```
⚠️  template-app-ecs-tasks.yml           — Replace with simpler version
                                          (5,511 lines → ~400 lines)
                                          Make sure we understand current config first
```

### Need to Create

```
🆕 template-ecs-loader-tasks.yml         → Simple ECS task defs for 61 loaders
🆕 template-loader-scheduler.yml         → EventBridge + Lambda scheduler
🆕 deploy-loaders.yml                    → Build Docker + register tasks
🆕 deploy-loader-scheduler.yml           → Deploy scheduler
```

### Must Keep

```
✅ deploy-infrastructure.yml              — RDS setup
✅ deploy-webapp.yml                      → Lambda API + frontend
✅ deploy-core.yml                        → Core AWS
✅ deploy-tier1-optimizations.yml         → Cost/perf
✅ bootstrap-oidc.yml                     → One-time setup (for reference)

✅ template-app-stocks.yml                → RDS database
✅ template-core.yml                      → Core AWS
✅ template-webapp-lambda.yml             → Lambda API + frontend
✅ template-tier1-api-lambda.yml          → HTTP API
✅ template-tier1-cost-optimization.yml   → Optimizations

✅ Dockerfile                             → Main API
✅ Dockerfile.loader                      → Generic loader image
```

---

## PART 7: VERIFICATION CHECKLIST

Before we delete, let's verify:

### Check AWS State

- [ ] What CloudFormation stacks actually exist?
- [ ] Is Phase C/D/E deployed? (Look for stack names with "phase-c", "phase-d", "phase-e")
- [ ] What ECS cluster exists?
- [ ] What ECS task definitions are registered?
- [ ] Have loaders ever run in ECS? (Check CloudWatch logs)

### Check Local Consistency

- [ ] Are all 61 loaders documented in DATA_LOADING.md? (We have 64, 3 extra)
- [ ] What are the 3 extra loaders?
- [ ] Does Dockerfile.loader work for all loader types?
- [ ] Are there any hardcoded assumptions in deploy-app-stocks.yml we'd lose?

### Understand the Failure

- [ ] Why is data stale? (loaders never ran, or they failed?)
- [ ] If deploy-app-stocks.yml tried to run, what error would occur?
- [ ] Is there any evidence in git history of successful loader runs?

---

## NEXT STEPS

Before we delete anything:

1. **Run AWS audit** — check what's actually deployed
2. **Check git history** — when did loaders last run successfully?
3. **Review template-app-ecs-tasks.yml** — what custom config exists?
4. **Test Dockerfile.loader** — does it work for different loader types?
5. **Then make deletion decisions** — with confidence

**Want to do this investigation now?**
