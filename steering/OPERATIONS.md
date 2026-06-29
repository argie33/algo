# Operations: CI/CD & Quick Reference

## CI/CD Pipeline (ci-fast-gates.yml)

Runs on every commit to `main` and every PR. 27 min average, all gates blocking.

**What gets checked:**
- Security: Secrets scan (TruffleHog), dependencies (pip-audit), static analysis (Bandit), IaC (tfsec), containers (Trivy), JS/TS (Semgrep)
- Quality: Imports validation, linting (ruff), formatting, type checking (mypy), unit/integration tests, coverage (75% minimum)
- Compliance: License scan (warning only), SBOM generation, supply chain scan

**How to run locally:**
```bash
make lint           # Ruff linter
make format         # Auto-format code
make type-check     # MyPy type checking
make test           # Unit + integration tests
make coverage       # Tests with coverage report
make ci-local       # All checks (simulates full CI)
```

**Common failures & fixes:**

| Failure | Fix |
|---------|-----|
| Secrets detected | Remove credential, use AWS Secrets Manager or PowerShell profile |
| Import/type errors | Run `make format && make type-check` |
| Linting violations | Run `make format` |
| Test failures | Run `make test -v` locally to debug |
| Terraform invalid | `cd terraform && terraform fmt -recursive && terraform validate` |
| Coverage dropped | Run `make coverage`, write tests for uncovered lines |

**Skip (local only, not recommended):** `git commit --no-verify`

---

## Dashboard Diagnostics

Run: `python -m dashboard.diagnose_dashboard`

Shows:
- ✓ SUCCESS: Data loaded (field count)
- ⚠ STALE: Data too old (loader hasn't run recently)
- ✗ ERRORS: API failed or validation failed
- ⚡ MISSING FIELDS: Data partial (some fields None)

**Key data freshness thresholds:**
| Data | Max Age | Why |
|------|---------|-----|
| Portfolio | 5 days | Algo runs trading days only |
| Performance | 1 hour | Needs recent PnL |
| Market | 24 hours | Used for position sizing |

**Critical fields (must never be None):** `run.run_id`, `run.success`, `mkt.spy_close`, `mkt.vix_level`, `port.total_portfolio_value`, `port.total_cash`, `perf.total_trades`

---

## Branch Protection Rules (main)

Required:
- `ci-fast-gates` passes (all gates)
- CodeQL analysis passes
- ≥1 approval (if PR)
- No direct pushes (PR only)
- Stale reviews dismissed on new commits

---

## Portfolio Data Freshness (Critical for Trading)

**Problem:** Dashboard shows "Data is stale (Xs old, max 360s)"

**Root Cause:** Phase 9 (Daily Reconciliation) hasn't run. Creates `algo_portfolio_snapshots` rows. If latest row is > 6 minutes old (trading hours), portfolio is stale.

**Quick Fix (2 min):**
1. AWS Lambda Console → Find `algo-orchestrator` function
2. Click **Test** tab → Create test event → Click **Test** button
3. Wait 60-120 seconds for execution
4. ✅ Status = "success" → Portfolio data is now fresh

**Prevent Recurrence:**
1. AWS EventBridge Console → **Rules** → Search `algo-orchestrator-schedule`
2. If **State = DISABLED** → Click rule → Click **Enable**
3. If rule missing → Create rule with:
   - Schedule: `cron(*/5 13-20 ? * MON-FRI *)` (every 5 min, trading hours)
   - Target: `algo-orchestrator` Lambda function

**Diagnosis (if manual refresh doesn't help):**
- CloudWatch Logs: `/aws/lambda/algo-orchestrator` — Check for Phase 9 errors
- RDS Connectivity: Can Lambda reach database? Check VPC, security groups
- EventBridge Metrics: Is rule firing (Invocations > 0 in last hour)?
- Lambda Concurrency: Check if provisioned concurrency is 0 (would throttle)

**Architecture:** EventBridge (cron) → Lambda → 9 phases → Phase 9 creates portfolio snapshot → Dashboard reads snapshot age

---

## Factor Scores Data Quality (AWS Metric Loaders)

**Problem:** Factor scores showing 0's, NULL, or incomplete (data_completeness < 50%)

**Root Cause:** Metric loaders timing out in AWS
- Default 300s timeout insufficient for yfinance + SEC filing fetches
- Rate limiting from parallel loading of 3000+ symbols
- Batch size 1000 causes rate limit cascade, backoff increases execution time
- VPC network latency and database connection pooling contention

**Solution (Deployed):**
- Metric loader timeout: 300s → 600s (10 minutes)
- Batch size in AWS: 1000 → 100 (avoids rate limiting)
- ECS task memory: 512MB → 1024MB (sufficient for batches)
- Loader classification: CRITICAL (FARGATE resource guarantee, not SPOT)

**Verify Fix Working:**
```bash
# Check metric loader completion (should be > 75% in last hour)
SELECT table_name, completion_pct, last_updated 
FROM data_loader_status 
WHERE table_name IN ('quality_metrics', 'growth_metrics', 'value_metrics', 'positioning_metrics', 'stability_metrics')
ORDER BY last_updated DESC;

# Check factor scores calculated (should be 2000+ with avg 45-65)
SELECT COUNT(*) as total, 
       ROUND(AVG(composite_score), 2) as avg_score,
       MIN(composite_score) as min_score,
       MAX(composite_score) as max_score
FROM stock_scores 
WHERE composite_score > 0;
```

**Expected Results (Fixed):**
- total: 2000+
- avg_score: 45-65
- min_score: > 0
- max_score: 90-100

**If Still Broken (< 500 scores):**
1. Check CloudWatch: `/ecs/algo-cluster` — metric loader errors?
2. Check data_loader_status: completion_pct for each metric table
3. If < 70% completion: increase ECS memory to 2048MB, reduce parallelism to 2
4. Monitor next loader run (EventBridge triggers every 5 min trading hours)
5. Each loader needs ~10 min to complete; allow 60+ min for all 5 metrics + stock_scores

**Auto-Recovery:** EventBridge trigger → Loader execution → Data loaded → Scores calculated

---

## For Detailed Reference

See:
- `steering/GOVERNANCE.md` — Architecture, safety rules, system map, fail-fast principles
- `steering/LINT_POLICY.md` — Code quality, pre-commit enforcement
