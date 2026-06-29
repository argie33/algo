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

## For Detailed Reference

See:
- `steering/GOVERNANCE.md` — Architecture, safety rules, system map, fail-fast principles
- `steering/LINT_POLICY.md` — Code quality, pre-commit enforcement
