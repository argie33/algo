# Operations: CI/CD & Quick Reference

## AWS Account Setup (Prerequisites)

**Required IAM:** ECS task management + S3 Terraform access + CloudWatch Logs access for `algo-developer` user.

**Core Permissions Needed:**
- `ecs:*` — ECS task management (describe, run, list tasks)
- `s3:*` — S3 Terraform access (get/put bucket policy)
- `ec2:*` — VPC networking (describe subnets, security groups)
- `logs:GetLogEvents` — Read CloudWatch logs (for local CLI diagnostics)
- `logs:DescribeLogStreams` — List log streams (to find latest logs)
- `logs:DescribeLogGroups` — List log groups (for log discovery)

**CLI Access for Logs:**
```bash
# Check if you have CloudWatch Logs access
aws logs describe-log-groups --query 'logGroups[0].logGroupName' --region us-east-1

# If you get AccessDenied, contact AWS admin to grant logs:GetLogEvents and logs:DescribeLogStreams
```

**Permission Error:** If you see `AccessDeniedException` (e.g., `ecs:DescribeTaskDefinition` or `logs:GetLogEvents`), contact AWS admin to grant the missing permissions. Check IAM policy for `algo-developer` user — required permissions listed in section above.

---

## CI/CD Pipeline (.github/workflows/ci.yml)

**Correction (2026-07-21):** this section previously described a file named
`ci-fast-gates.yml`, which does not exist anywhere in this repo - the actual (and only)
CI workflow is `.github/workflows/ci.yml` ("CI"), 3 jobs: `validate` (Python lint/type/
test), `lint-js` (webapp/lambda ESLint/Prettier/npm audit - see the dead-code note above,
this job still runs even though webapp/lambda isn't deployed), `coverage`.

**What actually runs (verified against the workflow file, not the checklist below):**
- Quality: ruff lint + format check, mypy, a narrow pylint rule pair
  (`comparison-with-callable`/`unsupported-binary-operation`), 4 pre-commit validation
  scripts, unit/edge/integration/StrictValidationError test suites, coverage report
  (no enforced minimum/threshold - just reported).
- Security: Bandit (`--severity-level medium --confidence-level high`) and TruffleHog
  (`--only-verified`) do run, but **both commands end in `2>/dev/null || true` /
  `|| true`, so neither can ever fail the job regardless of what they find** - directly
  contradicting the "all gates blocking" claim this section used to make. Currently
  moot in practice (Bandit reports 0 issues at that severity/confidence threshold as of
  2026-07-21), but a real secret or high-severity issue introduced later would not block
  a merge. `webapp/lambda`'s `npm audit --audit-level=high` (in `lint-js`) is NOT
  similarly neutered and does block.
- **Does NOT exist in this pipeline at all** (previously claimed here): pip-audit
  (dependency scanning), tfsec (IaC scanning), Trivy (container scanning), Semgrep,
  license scanning, SBOM generation, supply-chain scanning. If any of these are wanted,
  they need to be added, not just documented.

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

## AWS Deployment via GitHub Actions

**Standard Deployment Flow:** All AWS infrastructure updates go through GitHub Actions workflows (automated on push to main).

**Available Workflows:**

| Workflow | File | Trigger | Purpose |
|----------|------|---------|---------|
| Deploy API Lambda | `.github/workflows/deploy-api-lambda.yml` | Auto (CI success on main) + manual | Update `algo-api-dev` function code |
| Deploy Orchestrator Lambda | `.github/workflows/deploy-orchestrator-lambda.yml` | Auto (CI success on main) + manual | Update `algo-orchestrator` function code |
| Deploy ECS Image | `.github/workflows/deploy-ecs-image.yml` | Auto (CI success on main) + manual | Build and push the shared Docker image used by ALL ECS loaders and the orchestrator |
| Deploy All Infrastructure | `.github/workflows/deploy-all-infrastructure.yml` | Auto (CI success on main) + manual | Terraform apply + **DB migrations** + Lambda updates |

**A fix is NOT live until its deploy workflow succeeds.** Pushing to main runs CI; only if CI succeeds do the deploy workflows fire (`workflow_run` trigger). A green push with a failed/skipped deploy silently leaves prod running old code — this has caused multi-day staleness before. Always confirm with `gh run list --limit 10` that the relevant deploy workflow completed after your push.

**`webapp/lambda/` (Node.js) is NOT the deployed API — confirmed dead/legacy (Session 314).** `deploy-all-infrastructure.yml`'s "Build API Lambda ZIP" step packages `lambda_api.zip` from `lambda/api/` + `utils/` + `algo/` (Python, handler `lambda_function.lambda_handler`) — that's what `algo-api-dev` actually runs, and it's the same code `lambda/api/dev_server.py` uses for local dev. `webapp/lambda/` (a full second Node.js implementation, ~171 files, own Dockerfile) is not referenced anywhere in `deploy-all-infrastructure.yml` or terraform. It IS still exercised by `.github/workflows/ci.yml`, which is why it keeps getting bug-fixed as if it were live — it isn't. Before spending time fixing a bug there, check whether the equivalent Python route in `lambda/api/routes/` has (or needs) the same fix instead. Not removed yet (171 files, still wired into CI, and no exhaustive check was done for a differently-named terraform/API-Gateway resource that might still route to it) — verify no live traffic depends on it before deleting.

**Database migrations (`migrations/versions/*.sql`):**
- Applied ONLY by the `algo-db-migration-dev` Lambda, which `deploy-all-infrastructure.yml` (run-migrations job) re-packages with the current `migrations/versions/` and invokes. Committing a migration does nothing until that workflow runs.
- Manual apply: `aws lambda invoke --function-name algo-db-migration-dev --payload '{}' out.json` — any payload runs all pending migrations. Note: the Lambda package must already contain your migration (i.e., deploy-all-infrastructure must have packaged it).
- **NEVER edit an already-applied migration file** — the runner tracks applied state by version number only, never content, so edits are a silent no-op in every environment that already ran it. Ship a new version number instead.
- Loader mutual exclusion uses the `loader_execution_locks` table (migration 1111), NOT `pg_try_advisory_lock` — advisory locks are unreliable through RDS Proxy connection pinning (two tasks can both "acquire" the same lock).

**Production trigger chain (who runs what):**
- EventBridge Scheduler → Step Functions pipelines (`algo-morning-prep-pipeline-dev`, `algo-eod-pipeline-dev`, `algo-computed-metrics-pipeline-dev`, `algo-reference-data-pipeline-dev`) → ECS loader tasks → orchestrator ECS task (logs: `/ecs/algo-algo-orchestrator`).
- The EOD pipeline intentionally halts at `PriceLoadFailureHalt` if `stock_prices_daily` fails after retries — no trading on stale prices. When that happens the orchestrator never runs and everything downstream (scores, signals, positions view, risk metrics) goes stale together. Diagnose with `aws stepfunctions list-executions --state-machine-arn <eod-arn>`.
- Pipelines have a concurrency gate (`CheckConcurrency` → `SkipAlreadyRunning`): an execution that "SUCCEEDED" in under a second is a normal skip because another execution of the same pipeline was still running, not a bug.
- Orchestrator phase-level results live in `orchestrator_execution_log` (written by `OrchestratorExecutionTracker`, per-phase status `"ok"`), NOT in `algo_orchestrator_runs.phase_results` (which is never populated).

**How to Trigger Deployment (Example: API Lambda):**

```bash
# Method 1: Using GitHub CLI (from terminal)
gh workflow run deploy-api-lambda.yml -R owner/algo

# Method 2: Via GitHub Web UI
# 1. Go to Actions tab
# 2. Select workflow (e.g., "Deploy API Lambda")
# 3. Click "Run workflow" button
```

**Monitor Deployment:**
```bash
# Watch workflow status
gh run list -R owner/algo --workflow deploy-api-lambda.yml

# View specific run (replace RUN_ID)
gh run view RUN_ID -R owner/algo

# Stream logs (real-time)
gh run view RUN_ID --log -R owner/algo
```

**Verify in AWS (After Successful Deployment):**
```bash
# Check API Lambda was updated
aws lambda get-function --function-name algo-api-dev --query 'Configuration.LastModified'

# Check CloudWatch logs for new activity
aws logs describe-log-streams \
  --log-group-name /aws/lambda/algo-api-dev \
  --order-by LastEventTime \
  --descending \
  --region us-east-1
```

---

## Dashboard Diagnostics

**Correction 2026-07-20:** `dashboard.diagnose_dashboard` does not exist as a module -
this section described aspirational tooling, not something you can actually run. Use one
of the real diagnostic scripts instead:

```bash
python check_system_health.py           # DB connectivity + freshness, orchestrator status, dev_server, dashboard import
python scripts/dashboard_health_monitor.py
python scripts/diagnose_system.py
```

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

## Lambda VPC Configuration (Critical - Blocks Database Access)

**Problem:** Lambda endpoints (circuit-breakers, sentiment) return HTTP 503 from AWS.

**Root Cause:** API Lambda (`algo-api-dev`) has no VPC configuration, cannot reach RDS database in VPC. This breaks all endpoints that query the database.

**CRITICAL FIX (Required for AWS deployment):**

Run this script (requires AWS credentials with Lambda + EC2 + RDS permissions):
```bash
python3 scripts/fix-lambda-vpc-config.py
```

This script:
1. Queries RDS to find VPC/subnet/security group configuration
2. Creates Lambda security group (if not exists)
3. Authorizes Lambda SG to access RDS port 5432
4. Updates Lambda VPC configuration with correct subnets and security group

**Manual Fix (if script unavailable):**
```bash
# 1. Get RDS VPC details
aws rds describe-db-instances --db-instance-identifier algo-db \
  --query 'DBInstances[0].[DBSubnetGroup.VpcId,DBSubnetGroup.Subnets[].SubnetIdentifier,VpcSecurityGroups[].VpcSecurityGroupId]'

# 2. Create Lambda security group
aws ec2 create-security-group --group-name algo-lambda-sg \
  --description "Lambda RDS access" --vpc-id <VPC_ID>

# 3. Authorize RDS inbound
aws ec2 authorize-security-group-ingress --group-id <RDS_SG> \
  --protocol tcp --port 5432 --source-group <LAMBDA_SG>

# 4. Update Lambda VPC
aws lambda update-function-configuration --function-name algo-api-dev \
  --vpc-config SubnetIds=<SUBNET1>,<SUBNET2> SecurityGroupIds=<LAMBDA_SG>
```

**Verification:**
After fix + Lambda redeploy, test:
```bash
curl https://<api-gateway-url>/api/algo/circuit-breakers \
  -H "Authorization: Bearer <token>"
# Should return HTTP 200, not 503
```

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

## Factor Scores & Metric Loaders

**Troubleshooting factor score issues** (NULL scores, incomplete metrics, timing):

Key points:
- Metric loaders need ≥70% coverage to trigger stock_scores computation
- Max parallelism: 3-4 tasks (avoid yfinance rate limiting)
- Orchestrator timeout: 25 min (sufficient for all loaders + stock_scores)
- Check `data_loader_status` table to monitor completion

For full loader details, see `steering/DATA_LOADERS.md`.

---

## Configuration Hotload (Runtime Parameter Changes)

**Problem:** Need to adjust trading thresholds without restarting Lambda.

**Solution:** Read `algo_config` table at each orchestrator run (5-min cache, refreshed on-demand).

**Hot-Reloadable Parameters:**

**Corrected 2026-07-20 (superseded same day):** the previous version of this table verified
every key existed as a row in `algo_config` and stopped there - it never checked whether any
code actually *reads* the key to gate behavior. Four of the eight listed keys
(`signal_score_threshold`, `swing_score_threshold`, `data_completeness_threshold`,
`orchestrator_halt_enabled`) turned out to be exactly that: seeded rows with no reader
anywhere in the codebase (confirmed via full-repo grep) - editing them via the `UPDATE`
examples below was a real SQL statement that succeeded, changed a real row, and had **zero
effect on trading behavior**, which is worse than a no-op UPDATE because nothing signals the
mistake. Removed from `algo/infrastructure/config_schema.py` the same day (they were also
misleading anyone auditing the schema directly, not just this table). The real, actually-
enforced keys are listed below in their place; swing-score has no live equivalent - that
gating mechanism was formally retired in migration 103 (composite_score-only trading logic).

| Parameter | Type | Live value | Effect |
|-----------|------|---------|--------|
| `min_signal_quality_score` | int | 60 | Min score to enter trade (was documented as `signal_score_threshold` - that key is dead, never read) |
| `min_completeness_score` | int | 70 | Min % data available (was documented as `data_completeness_threshold` - dead, never read) |
| `earnings_blackout_days_before` / `_after` | int | 7 / 3 | Block entries N days before / after earnings (replaces the nonexistent `enable_earnings_blackout` bool - this gate can't be disabled with a single flag, only widened/narrowed) |
| `min_daily_volume_shares` | int | 500000 | Min daily volume (replaces nonexistent `entry_volume_threshold`) |
| `min_avg_daily_dollar_volume` | int | 500000 | Min $ volume (replaces nonexistent `entry_dollar_volume`) |
| `halt_drawdown_pct` | float | -20.0 | Max drawdown before halt (replaces nonexistent `cb_drawdown_threshold` - note the value is negative) |

**There is no live "disable circuit breakers" flag.** `orchestrator_halt_enabled` was
documented as one (see "Manual CB Override" below, also corrected) but no code anywhere
reads it - `CircuitBreaker.check_all()` runs all 8 checks unconditionally, every run. This
matches `steering/GOVERNANCE.md`'s "no bypasses" principle; it is not a gap to fill.

`price_loader_batch_size` and `metric_loader_parallelism` have no equivalent live config
key - loader concurrency is governed by `LoaderConfigManager` (DynamoDB
`algo-loader-config` → env → constraint max), see `steering/DATA_LOADERS.md`.

**Update Config (live change, no restart):**
```sql
UPDATE algo_config
SET value = '75'
WHERE key = 'min_signal_quality_score';

-- Verify
SELECT * FROM algo_config WHERE key = 'min_signal_quality_score';
-- Result: min_signal_quality_score | 75 | (timestamp)
```

**When does change take effect?**
- Orchestrator next run (9:30 AM, 1 PM, 3 PM, 5:30 PM ET) loads fresh config
- Example: Change at 2:00 PM → Takes effect at 3 PM orchestrator run

**Validation (prevents bad configs):**
- Type must match (int for `min_signal_quality_score`, not string)
- Bounds enforced per `algo/infrastructure/config_schema.py` (e.g. `min_completeness_score`: 1-100)
- Invalid config rejected, old value persists
- Error logged: `Config validation failed: min_signal_quality_score=200 exceeds max 100`

**Example: Emergency Threshold Tightening**

Market spike, want to reduce risk:
```sql
UPDATE algo_config SET value = '75' WHERE key = 'min_signal_quality_score';
UPDATE algo_config SET value = '85' WHERE key = 'min_completeness_score';

-- Next 3 PM orchestrator run uses new thresholds
-- Result: Fewer entries (higher signal score required), higher data quality requirement
```

---

## Circuit Breaker Monitoring & Alerts

**Circuit Breakers** (`algo/risk/circuit_breaker.py` - corrected path, 2026-07-20): 8 automatic halts to prevent catastrophic loss.

**Active Circuit Breakers:**

| Name | Condition | Threshold | Action |
|------|-----------|-----------|--------|
| Drawdown | Max drawdown since start | ≥20% | **HALT all new entries** |
| Daily Loss | Loss today | ≥2% | Halt new entries (allow exits) |
| Loss Streak | Consecutive losing days | ≥3 | Halt new entries |
| Open Risk | Total open risk | ≥4% of portfolio | Halt new entries |
| VIX Level | Market volatility index | ≥35 | Halt new entries (warn) |
| Market Stage | 12mo yield + momentum | Stage 4 (terminal) | Halt new entries |
| Weekly Loss | Loss this week | ≥5% | Halt new entries |
| Win Rate | Ratio of winning trades | <40% | Halt new entries (warn) |

**Monitoring Halts (Live Dashboard):**

**Correction 2026-07-20:** `dashboard.circuit_breaker_monitor` does not exist as a module.
The dashboard's circuit-breaker panel (`dashboard/panels/`) shows this live when running
`python -m dashboard --local`; for a one-shot check query `circuit_breaker_status`
directly: `SELECT * FROM circuit_breaker_status ORDER BY updated_at DESC LIMIT 10;`

If any circuit breaker triggers:
```
Circuit Breaker Monitoring
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Drawdown:         21.5% (threshold: 20%)  ⛔ HALT
Daily Loss:       0.1% (threshold: 2%)    ✓ OK
...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Overall:          🔴 HALTED (1 circuit breaker active)

Reason: Maximum drawdown (21.5%) exceeded threshold (20%)
Halted: All new position entries blocked
Allowed: Exits, rebalancing, portfolio reconciliation
Re-engagement: See "Re-Engagement Logic" below (drawdown recovery is a 3-part gate, not a
single recovery percentage)
```

**Alert Configuration:**

Slack webhook to `#trading-alerts` when CB triggers:
```
🚨 CIRCUIT BREAKER TRIGGERED
Breaker: Drawdown (21.5% > 20% threshold)
Time: 2026-06-29 14:45 ET
Action: All new entries halted
Manual Recovery: See "Re-Engagement Logic" below - there is no config flag that bypasses
this (see "Manual CB Override" note)
```

**Re-Engagement Logic:**

**Corrected 2026-07-20:** the drawdown re-engagement gate (`algo/risk/circuit_breaker.py::
_check_drawdown_re_engagement`) is a 3-part AND, not a single recovery percentage - all three
must pass before new entries resume:
1. Recovered to within `re_engage_recovery_pct` of peak (live default **8.0%**, not 15%/20%*0.75
   as a previous version of this doc claimed)
2. At least `re_engage_min_days` (live default **5**) days elapsed since the halt fired
3. If `require_ftd_to_re_engage` is set, market must be in Stage 2 uptrend (Follow-Through Day)

Other breakers are stateless and simply re-evaluate current conditions each run - if the
underlying metric (VIX, daily loss, weekly loss, open risk, market stage) is no longer past
threshold on the next run, they clear on their own; there is no separate "re-engagement"
gate for them like drawdown has.

**Manual CB Override (Emergency Only):**

**Corrected 2026-07-20:** the SQL below (setting `orchestrator_halt_enabled=false`) was
never functional - no code reads that key (confirmed via full-repo grep; also removed from
`config_schema.py` the same day). There is currently **no config flag that bypasses circuit
breakers**, and per `steering/GOVERNANCE.md`'s "no bypasses" principle, adding one back is
not the intended fix if a breaker fires on genuinely bad/stale data.

If a circuit breaker fires on data later proven wrong (a since-fixed calculation bug, a bad
upstream data point), the correct, auditable path - already used and documented in prior
sessions - is to annotate the specific triggering row in `algo_audit_log`
(`action_type='circuit_breaker_halt'`) with `details->>'corrected'=true` plus a
`correction_reason` and evidence, via a direct, reviewed `UPDATE`. This never deletes or
alters the original recorded check (the halt stays fully visible in history) and only
affects the drawdown re-engagement gate's `WHERE ... NOT corrected` clause - it does not
touch the other 7 breakers, which self-clear as described above once their underlying data
is fixed and the next run re-evaluates.

**Testing Circuit Breakers (Paper Trading):**

```sql
-- Set drawdown threshold to 5% temporarily (real key is halt_drawdown_pct, and it's
-- negative - 'cb_drawdown_threshold' from a previous version of this doc does not exist)
UPDATE algo_config SET value = '-5' WHERE key = 'halt_drawdown_pct';

-- Make a losing trade → Drawdown > 5% → CB triggers
-- Observe in dashboard: CB status = HALTED, reason = Drawdown

-- Restore to 20%
UPDATE algo_config SET value = '-20' WHERE key = 'halt_drawdown_pct';
```

---

## For Detailed Reference

See:
- `steering/GOVERNANCE.md` — Architecture, safety rules, system map, fail-fast principles
- `steering/LINT_POLICY.md` — Code quality, pre-commit enforcement
- `steering/DATA_LOADERS.md` — Loader orchestration, batch sizing, freshness thresholds
- `steering/DATABASE_AND_ENVIRONMENTS.md` does not exist (dead link, found 2026-07-20). For database setup see `QUICKSTART_LOCAL.md`; for AWS credentials see `steering/GOVERNANCE.md`'s "Credentials & Deployment" section
