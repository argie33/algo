# Infrastructure Audit — What We Have, What Works, What's Broken

**Last Updated:** 2026-05-04  
**Data Freshness:** STALE (latest rows are 2026-05-01, today is 2026-05-04)

---

## Quick Assessment

✅ **GOOD:** Infrastructure templates exist (CloudFormation, ECS, Lambda)  
✅ **GOOD:** OptimalLoader framework is solid (watermark, dedup, routing)  
❌ **BAD:** Data is stale — loaders aren't running in AWS  
❌ **BAD:** deploy-app-stocks.yml exists but unclear if it's actually executing loaders  
❌ **BAD:** Too many workflows (13), unclear hierarchy  
⚠️ **UNCLEAR:** Phase C/D/E templates (experimental? abandoned? deployed?)

---

## WORKFLOWS (13 after cleanup)

### Primary Deployment Workflows

| Workflow | Purpose | Triggers | Status |
|----------|---------|----------|--------|
| **deploy-app-stocks.yml** | Data loaders pipeline | `load*.py`, `Dockerfile.*` changes | ❓ Active but data is STALE |
| **deploy-webapp.yml** | Lambda API + React frontend | `webapp/**` changes | ✅ Working |
| **deploy-infrastructure.yml** | RDS CloudFormation | `template-app-stocks.yml` changes | ✅ Working |
| **deploy-core.yml** | Core infrastructure | Manual trigger | ✅ Working |
| **deploy-tier1-optimizations.yml** | Cost/perf optimizations | Manual trigger | ✅ Working |

### Secondary/Experimental Workflows

| Workflow | Purpose | Status |
|----------|---------|--------|
| bootstrap-oidc.yml | GitHub OIDC setup | ✅ One-time setup |
| deploy-billing.yml | Billing alerts | ⚠️ Minimal, not clear if needed |
| manual-reload-data.yml | Manual data reload | ⚠️ Minimal, not clear how it works |
| optimize-data-loading.yml | Data loading optimization | ⚠️ Manual, unclear purpose |
| test-automation.yml | Automated testing | ✅ Running |
| algo-verify.yml | Algo verification | ⚠️ Push trigger, unclear scope |
| pr-testing.yml | PR testing | ✅ Running |
| gemini-code-review.yml | Code review | ⚠️ Minimal, unclear if needed |

---

## CLOUDFORMATION TEMPLATES (12)

### Used & Active

| Template | Purpose | Deployed By | Status |
|----------|---------|------------|--------|
| template-app-stocks.yml | RDS + base infra | deploy-infrastructure.yml | ✅ Active |
| template-core.yml | Core AWS setup | deploy-core.yml | ✅ Active |
| template-webapp-lambda.yml | Lambda + frontend | deploy-webapp.yml | ✅ Active |
| template-bootstrap.yml | GitHub OIDC | bootstrap-oidc.yml | ✅ One-time |
| template-tier1-cost-optimization.yml | VPC endpoints, S3, CloudWatch | deploy-tier1-optimizations.yml | ✅ Active |
| template-tier1-api-lambda.yml | HTTP API migration | deploy-tier1-optimizations.yml | ✅ Active |
| template-app-ecs-tasks.yml | ECS task definitions | deploy-app-stocks.yml | ❓ Unclear |

### Experimental/Unused

| Template | Purpose | Status |
|----------|---------|--------|
| **template-lambda-phase-c.yml** | Lambda fan-out for data loading | ⚠️ In deploy-app-stocks but unclear if deployed |
| **template-step-functions-phase-d.yml** | Step Functions DAG orchestration | ⚠️ In deploy-app-stocks but unclear if deployed |
| **template-phase-e-dynamodb.yml** | DynamoDB execution metadata | ⚠️ In deploy-app-stocks but unclear if deployed |
| **template-eventbridge-scheduling.yml** | EventBridge loader scheduling | ❌ NOT USED BY ANY WORKFLOW |
| **template-optimize-database.yml** | Database optimizations | ❌ NOT USED BY ANY WORKFLOW |

---

## The Real Problem

### Data is Stale
```
Database state as of 2026-05-04 08:50:
  price_daily:        21,743,023 rows (latest: 2026-05-01) ← 3 days old
  buy_sell_daily:     823,231 rows (latest: 2026-05-01) ← 3 days old
  technical_data_daily: 19,104,570 rows (latest: 2026-05-01) ← 3 days old
```

### Why?
1. **deploy-app-stocks.yml** triggers on `load*.py` changes, but loaders haven't been modified since being deployed
2. **No scheduled execution** — loaders only run if code changes OR manual trigger
3. **EventBridge not deployed** — template-eventbridge-scheduling.yml exists but isn't used
4. **Unclear what Phase C/D/E do** — are they actually running loaders, or just test infrastructure?

---

## What Should Happen (Per LOADER_SCHEDULE.md)

```
Intraday (every 90min):    loadlatestpricedaily
EOD (5:30pm ET):           All Phase 2-5 daily loaders + load_algo_metrics_daily  
Weekly (Sat 8am):          Phase 2-5 weekly loaders + scoring
Monthly (1st Sat):         Phase 2-5 monthly + factor metrics
Quarterly:                 Fundamentals + earnings
```

None of this is happening automatically. We have no scheduler deployed.

---

## Next Steps (What We Need to Decide)

1. **Deploy EventBridge scheduling** (template-eventbridge-scheduling.yml)
   - Or delete it if we don't want scheduled execution

2. **Fix/verify deploy-app-stocks.yml**
   - Is it actually deploying loaders?
   - Can it be manually triggered to test?
   - What are Phase C/D/E doing?

3. **Consolidate workflows**
   - 13 workflows is too many
   - Some seem redundant or one-off

4. **Document which Phase templates are needed**
   - Keep Phase C/D/E if they're part of the plan
   - Delete if they're experiments that didn't pan out

---

## Clean Up Tasks

- ✅ `deploy-app-stocks-original.yml` — deleted (dead code)
- 🔲 `template-eventbridge-scheduling.yml` — deploy it OR delete it?
- 🔲 `template-optimize-database.yml` — deploy it OR delete it?
- 🔲 Reduce 13 workflows to 5-6 core ones
- 🔲 Document Phase C/D/E purpose (keep or remove?)
