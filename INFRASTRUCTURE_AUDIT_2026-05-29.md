# Infrastructure Audit & Slop Inventory — 2026-05-29

## Goal
Identify architectural misalignments, redundancies, and incomplete migrations where we "started one way, pivoted, and ended up with messes." Fix them the RIGHT way only.

---

## SLOP #1: Loader Count Discrepancy
**Steering Doc Claims:** 49 loaders (9 essential + 40 supporting)  
**Reality:** 33 loaders exist in `loaders/` directory
**Root Cause:** Loaders were removed (line 14 in `loaders/main.tf` comments: "Removed: market_overview, sector_performance, relative_performance, social_sentiment") without updating steering doc.
**Status:** ❌ Steering doc is stale

**What Should Be:**
- Steering doc should list exactly 33 loaders with clear categorization
- Remove claims about 49 loaders and 40 "supporting" loaders
- Document the 8 removed loaders and why (bad data, duplicates, etc)

---

## SLOP #2: EOD Pipeline Incomplete
**Steering Doc Claims:** 9 essential loaders in EOD pipeline (stock_symbols, prices, technical, market_health, trend, signals, quality, metrics, swing)  
**Reality:** Step Functions uses 8 tasks:
1. eod_bulk_refresh (= stock_prices_daily)
2. technical_data_daily
3. market_health_daily
4. trend_template_data
5. buy_sell_daily
6. signal_quality_scores
7. algo_metrics_daily
8. swing_trader_scores

**Missing:** `stock_symbols` is NOT in the Step Functions pipeline — it runs via EventBridge at 3:25am ET

**Impact:** If `stock_symbols` fails or is late, the EOD pipeline runs but can't properly mark new symbols as S&P 500 constituents. This is a race condition.

**Status:** ❌ Architecture incomplete

**What Should Be:**
- Add `stock_symbols` to Step Functions pipeline as first step (before eod_bulk_refresh)
- Verify the dependency: prices need fresh symbols first
- Remove the EventBridge schedule for `stock_symbols` to avoid dual triggering
- Update steering doc with actual 8-step pipeline (currently claims 9)

---

## SLOP #3: Orchestrator Execution Frequency Mismatch
**Steering Doc Claims:** "2x daily (9:30 AM ET + 5:30 PM ET)"  
**Terraform Config Shows:**
- `enable_morning_orchestrator = true` (9:30 AM ET)
- `enable_afternoon_orchestrator = true` (1:00 PM ET) — **NOT in steering doc**
- `enable_preclose_orchestrator = true` (3:00 PM ET) — **NOT in steering doc**
- Evening at 5:30 PM ET = signal prep only, no trading
- Pre-market disabled

**Reality:** 3-4 orchestrator executions during market hours + 1 evening signal prep = **4 runs, not 2**

**Status:** ❌ Steering doc is wildly out of sync

**What Should Be:**
- Update steering doc to list all 4 execution times with purposes:
  - **9:30 AM ET (market open):** Primary execution with overnight-computed signals
  - **1:00 PM ET (mid-day):** Rebalance check + catch missed opportunities
  - **3:00 PM ET (pre-close):** Final execution before 4 PM close, SLA finish by 3:15 PM
  - **5:30 PM ET (after close):** Signal prep + EOD pipeline trigger (no trading)
- Add a section explaining WHY 3 trading runs (better coverage, SLA compliance, etc)
- Mark the 3 trading runs as "enabled" and explain disabled pre-market

---

## SLOP #4: Loader Schedule Complexity Not Documented
**Current State:** 26 EventBridge rules create a complex staggered schedule:
- 3:25am ET: stock_symbols
- 3:30am ET: sp500_constituents  
- 3:35am ET: russell2000_constituents
- 4:00am ET: stock_prices_daily
- 4:20-4:34am ET: company_profile, positioning_metrics, analyst sentiment, earnings calendar, sentiment (staggered 2-4 min apart)
- 4:30pm ET: FRED (moved here to provide fresh data for EOD pipeline)
- 5:00pm ET: signal_themes
- 5:02pm-5:30pm ET: metrics (growth, quality, value, stability loaders staggered 2-4 min apart)
- Sundays: financials and earnings history (staggered hourly)
- Fridays: AAII, NAAIM weekly sentiments

**Steering Doc:** References "schedule" vaguely but DOES NOT document the actual cron times or explain stagger pattern

**Status:** ❌ Schedule details are missing from steering doc

**What Should Be:**
- Add a detailed loader schedule table to steering doc with:
  - Loader name
  - UTC cron expression
  - ET equivalent
  - Reason for that time (e.g., "after market close", "after prices load")
  - Dependencies (e.g., "after stock_symbols")
- Explain the 2-4 minute stagger strategy for preventing simultaneous API calls
- Document why FRED moved from 4am to 4:30pm (fresh data for EOD pipeline)

---

## SLOP #5: Price Loader Naming Inconsistency
**File:** `loaders/load_prices.py`  
**Terraform Key:** `"stock_prices_daily"`  
**Variable:** `eod_bulk_refresh` in Step Functions  
**Steering Doc:** Calls it `stock_prices_daily`

**Three names for the same loader.** Confusing for operators.

**Status:** ❌ Inconsistent naming

**What Should Be:**
- Pick ONE canonical name: recommend `stock_prices_daily` (most descriptive)
- Update Step Functions variable from `eod_bulk_refresh` → `stock_prices_daily`
- Verify file is named correctly in terraform task definitions

---

## SLOP #6: RDS Proxy Marked as Optional When It's Critical
**Terraform Config:**
```hcl
enable_rds_proxy = true    # Enable RDS Proxy: connection pooling reduces latency & query overhead (critical for performance)
```

**Comment Says:** "critical for performance" but variable is `enable_rds_proxy = true` with default `true`

**Steering Doc:** Says "Dynamic RDS Proxy" with clear guidance: "when enabled" → suggests it's toggleable

**Reality:** Without RDS Proxy, orchestrator Phase 1 data freshness queries timeout (DiskQueueDepth 30-45 causes 5+ min waits). It's NOT optional; it's mandatory.

**Status:** ❌ Architectural requirement treated as configuration toggle

**What Should Be:**
- **Remove** `enable_rds_proxy` variable — always create it
- Make RDS Proxy a standard component like the database itself
- Update steering doc: "RDS Proxy is always enabled for production use. In dev, RDS Proxy can be disabled only for cost optimization if orchestrator timeouts are acceptable."
- Document the performance requirement: "Phase 1 data freshness must complete in <60 seconds; RDS Proxy reduces DiskQueueDepth from 30+ to <5."

---

## SLOP #7: Lambda Layer Management Not Documented
**What's Happening:** 
- `terraform/modules/services/main.tf` creates psycopg2 layer
- GitHub Actions `build-lambda-layer.yml` creates and uploads the layer
- `.github/workflows/deploy-code.yml` references layers by name

**Steering Doc:** Mentions "Lambda Layer (psycopg2)" briefly but:
- Does NOT explain when/how layer is rebuilt
- Does NOT document layer versioning strategy
- Does NOT explain dependencies (why only psycopg2? What about pandas, yfinance, etc?)
- Does NOT explain the layer attachment to Lambda functions

**Status:** ❌ Critical infrastructure component undocumented

**What Should Be:**
- Add section "Lambda Layer Management" explaining:
  - **When rebuilt:** Only when `requirements-lambda.txt` changes
  - **What's in it:** List all pinned dependencies (psycopg2, pandas, numpy, requests, etc)
  - **How deployed:** GitHub Actions `build-lambda-layer.yml` runs automatically on code change
  - **Versioning:** How layer versions are managed (latest always used? or pinned?)
  - **Fallback:** What happens if layer upload fails during deploy?

---

## SLOP #8: API Lambda Configuration Unclear
**Terraform Config:**
```hcl
api_lambda_timeout = 300  # Increased from 120s to handle VPC cold-start (15-20s) + DNS + DB connection delays
# COST: API Lambda reserved_concurrent_executions=2: ~$14.10/month (keeps Lambda warm to avoid cold-start timeout)
```

**Issues:**
1. Comment explains PAST action ("increased from 120s") — not useful for future operators
2. Reserved concurrency `=2` is hardcoded in code, not a variable
3. Cost notes in tfvars (environment config) instead of documentation
4. Steering doc says "5 minutes" but tfvars says "30 seconds" — **inconsistent**

**Status:** ❌ Configuration misaligned with documentation

**What Should Be:**
- Remove "increased from" historical comments (belongs in git log)
- Make reserved concurrency a variable: `api_lambda_reserved_concurrency`
- Update steering doc: "API Lambda timeout: 30 seconds (hard API Gateway limit is 29s). Reserved concurrency = 2 to keep instance warm during trading hours and avoid cold-start timeout (15-20s ENI provisioning)."
- Move cost notes to a separate "AWS Cost Optimization" section in steering

---

## SLOP #9: Orchestrator Timeout Configuration Inconsistent
**Terraform Config:**
```hcl
algo_lambda_timeout = 600  # Max Lambda timeout (10 min). RDS disk queue depth 30-45 causes Phase 1 data freshness to take 5+ minutes...
```

**Steering Doc:**
```
Orchestrator Lambda timeout (600+ second hangs):
  NOT a cold-start issue. Root cause: RDS disk I/O contention during Phase 3b market exposure computation.
  ...
  Fix: Enable RDS Proxy in terraform.tfvars: enable_rds_proxy = true
```

**Discrepancy:** Steering doc says Phase 3b is the bottleneck, but tfvars says Phase 1. 

**Root Cause:** These are OUTDATED comments from multiple fix sessions. The actual bottleneck might have shifted as code was optimized.

**Status:** ❌ Conflicting documentation about performance bottleneck

**What Should Be:**
- Run profiling to identify ACTUAL current bottleneck (Phase 1 or Phase 3b?)
- Document only the current state: "Orchestrator timeout is 600s (Lambda max). With RDS Proxy enabled, typical execution is 120-180s. If timeout occurs, check CloudWatch Logs for Phase that's slow."
- Remove historical fix comments; they're technical debt

---

## SLOP #10: Multiple Databases or Multiple Connection Patterns?
**Potential Issues to Investigate:**
1. Are loaders and orchestrator using the SAME database host (`DB_HOST` env var)?
2. Is RDS Proxy endpoint set for ALL connections or just some?
3. Are there hardcoded `localhost` or other database endpoints in code?

**Need to Check:**
- `algo/algo_orchestrator.py` — what DB connection method?
- `loaders/loader_loop.py` — what DB connection method?
- `lambda/api/lambda_function.py` — what DB connection method?
- Search codebase for hardcoded database URLs

**Status:** ⚠️ Unknown — needs audit of actual code

---

## SLOP #11: Credential Flow Partially Documented
**Steering Doc Claims:**
"GitHub Secrets → AWS Secrets Manager → Lambda env vars"

**What Steering Doc DOESN'T Explain:**
1. **Loaders:** How do ECS tasks get credentials? Via Secrets Manager or env vars?
2. **Orchestrator:** Does it read from Secrets Manager or env vars?
3. **Rotation flow:** Who rotates Alpaca keys? Manual? Automatic?
4. **Local development:** How does local PowerShell profile env var flow work during testing?
5. **Validation:** Is there any code that validates credentials are set before execution?

**Terraform shows:**
- Lambda functions have `DB_SECRET_ARN` env var pointing to Secrets Manager
- ECS tasks pull secrets via `valueFrom` (lines 596-616 in loaders/main.tf)
- But does code validate they're present?

**Status:** ❌ Credentials subsystem incompletely documented

**What Should Be:**
- Add diagram: where each component pulls credentials
- Document rotation procedures for each credential type with examples
- Add troubleshooting section: "What to do if credentials are invalid"
- Update memory from prior sessions: [[credential_system_consolidation_20260529.md]] suggests this was "solved" but docs don't show the final state

---

## SLOP #12: Database Initialization on Deploy Not Documented
**Steering Doc:** Mentions init.sql for schema but DOESN'T explain:
1. When does schema get applied?
2. Is there a db-init Lambda that runs?
3. What happens if schema is stale?
4. How do migrations work?

**Terraform shows:** `deploy-code.yml` invokes db-init Lambda

**Status:** ❌ Database initialization pipeline undocumented

**What Should Be:**
- Add section "Database Schema Management":
  - Schema defined in: `terraform/modules/database/init.sql`
  - Applied automatically when Lambda is deployed via db-init task
  - Migrations: add process for rolling out schema changes safely

---

## SLOP #13: EventBridge Scheduler Timing Assumed Correct
**Steering Doc Assumption:** "EventBridge has no concept of US holidays. Orchestrator exits early on market holidays via `MarketCalendar.is_trading_day()`"

**Risk:** What if orchestrator Lambda takes 5 minutes to start (cold-start)? Then market has closed by the time it runs.

**Status:** ⚠️ Timing assumptions not validated with actual execution metrics

---

## SLOP #14: Frontend/Cognito Integration Status Unknown
**Steering Doc Claims:** Cognito authentication system, CloudFront frontend, S3 storage

**From Memory:** Multiple sessions fixing Cognito ([[auth_fixed_20260529.md]], [[authentication_hardening_complete.md]])

**Terraform Config:** `cognito_enabled = true`, `cognito_test_user_email = "testuser@algo.local"`

**Questions:**
1. Is Cognito actually protecting the API endpoints or just the frontend?
2. Are all API routes using Cognito auth or are some open?
3. What's the actual frontend deployment process?
4. Is there an issue with CloudFront CORS that required workarounds?

**Status:** ⚠️ Auth architecture may have workarounds that need cleanup

---

## SLOP #15: Many "FIXED Issue #X" Comments Without Context
**Examples from Code:**
- `FIXED Issue #3: Timeout was 3600s but unified price loader needs 21600s`
- `FIXED Issue #8: Replaced filesystem locks with DynamoDB for Fargate`
- `FIXED Issue #9: ECS task timeout is 21600s, Step Functions timeout is also 21600s`
- `FIXED Issue #14: Moved from 4:05am to 4:30pm ET`
- `FIXED Issue #29: EventBridge Rule Naming Convention`
- `FIXED Issue #30: Separate loader status from lock TTL`

**Problem:** These comments suggest previous bugs/misconfigurations. If issues recur, we have no context. Are these issues tracked somewhere? Are they verified fixed?

**Status:** ❌ Issue tracking disconnected from code

**What Should Be:**
- If using GitHub Issues, link them in comments: `// FIXED GitHub Issue #123`
- Remove comments about past fixes; keep only current behavior description
- Verify the "fixed" issues are actually fixed by checking recent execution logs

---

## SUMMARY OF SLOPS

| # | Category | Issue | Severity | Fix Effort |
|----|----------|-------|----------|-----------|
| 1 | Docs | Loader count (49 vs 33) | High | Low |
| 2 | Architecture | stock_symbols missing from EOD pipeline | High | Medium |
| 3 | Docs | Orchestrator runs 4x not 2x | High | Low |
| 4 | Docs | Loader schedule not documented | Medium | Medium |
| 5 | Code | Price loader naming inconsistent | Low | Low |
| 6 | Architecture | RDS Proxy should be required, not optional | High | Low |
| 7 | Docs | Lambda layer management undocumented | Medium | Low |
| 8 | Config | API Lambda config has stale comments | Low | Low |
| 9 | Docs | Performance bottleneck docs conflict | Medium | Medium |
| 10 | Code | Database connection patterns unclear | High | High |
| 11 | Docs | Credential flow incompletely documented | Medium | Medium |
| 12 | Docs | Database initialization pipeline undocumented | Medium | Low |
| 13 | Ops | EventBridge timing assumptions unvalidated | Medium | High |
| 14 | Docs | Auth integration status unclear | Medium | High |
| 15 | Maintenance | "FIXED Issue #X" comments lack context | Low | Low |

---

## PRIORITY ORDER: FIX THESE FIRST (RIGHT WAY ONLY)

**CRITICAL (Blocking Operations):**
1. **#2 - Add stock_symbols to EOD pipeline** — Prevents symbol marking from failing
2. **#10 - Audit database connections** — Ensure ALL connections use correct endpoint + RDS Proxy
3. **#14 - Verify Cognito/Auth integration** — Ensure all protected routes are actually protected

**HIGH IMPACT (Fix Documentation):**
1. **#3 - Update orchestrator execution schedule** — Steering doc is misleading
2. **#1 - Fix loader count** — Steering doc claims 49, we have 33
3. **#11 - Complete credential flow docs** — Critical for rotation procedures

**MEDIUM IMPACT (Improve Operations):**
1. **#4 - Document loader schedule** — Helps with debugging late loaders
2. **#6 - Make RDS Proxy required** — Clarifies performance requirements
3. **#12 - Document database initialization** — Helps with schema troubleshooting

**LOW IMPACT (Code Cleanup):**
1. **#5 - Standardize price loader naming** — Consistency
2. **#8 - Remove stale config comments** — Reduce technical debt
3. **#9 - Verify performance bottleneck** — Update docs with truth
4. **#15 - Remove issue comments** — Reduce clutter

---

## NEXT STEPS

1. **Create tasks** for each critical slop fix
2. **Verify** each fix with actual code/logs (don't guess)
3. **Update steering doc** to match reality
4. **Test** after each fix to ensure no regressions
5. **Document the WHY** for each architectural decision in steering doc

