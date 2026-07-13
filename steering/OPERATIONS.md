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

## AWS Deployment via GitHub Actions

**Standard Deployment Flow:** All AWS infrastructure updates go through GitHub Actions workflows (automated on push to main).

**Available Workflows:**

| Workflow | File | Trigger | Purpose |
|----------|------|---------|---------|
| Deploy API Lambda | `.github/workflows/deploy-api-lambda.yml` | Manual (workflow_dispatch) | Update `algo-api-dev` function code |
| Deploy Orchestrator Lambda | `.github/workflows/deploy-orchestrator-lambda.yml` | Manual (workflow_dispatch) | Update `algo-orchestrator` function code |
| Deploy ECS Image | `.github/workflows/deploy-ecs-image.yml` | Manual (workflow_dispatch) | Build and push ECS task images |
| Deploy All Infrastructure | `.github/workflows/deploy-all-infrastructure.yml` | Manual (workflow_dispatch) | Full Terraform apply + Lambda updates |

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

## Lambda VPC Configuration (Critical - Blocks Database Access)

**Problem:** Lambda endpoints (circuit-breakers, sentiment) return HTTP 503 from AWS.

**Root Cause:** API Lambda (`algo-api-dev`) has no VPC configuration, cannot reach RDS database in VPC. This breaks all endpoints that query the database.

**CRITICAL FIX (Required for AWS deployment):**

Run this script (requires AWS credentials with Lambda + EC2 + RDS permissions):
```bash
bash scripts/fix-lambda-vpc.sh
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

| Parameter | Type | Default | Effect | Example |
|-----------|------|---------|--------|---------|
| `signal_score_threshold` | int | 60 | Min score to enter trade | Change to 75 during volatility |
| `swing_score_threshold` | int | 55 | Min swing score filter | Change to 45 if too restrictive |
| `data_completeness_threshold` | float | 0.70 | Min % data available | Change to 0.60 if missing data |
| `enable_earnings_blackout` | bool | true | Block near-earnings trades | Change to false to trade through earnings |
| `entry_volume_threshold` | int | 300000 | Min daily volume | Change to 500k for large-cap only |
| `entry_dollar_volume` | int | 500000 | Min $ volume | Change to 1M for liquidity |
| `orchestrator_halt_enabled` | bool | true | Circuit breaker active | Change to false only for testing |
| `price_loader_batch_size` | int | 1000 | Symbols per parallel task | Change to 500 if rate limit hit |
| `metric_loader_parallelism` | int | 5 | Parallel AWS tasks | Change to 10 for faster loads |

**Update Config (live change, no restart):**
```sql
UPDATE algo_config
SET value = '75'
WHERE key = 'signal_score_threshold';

-- Verify
SELECT * FROM algo_config WHERE key = 'signal_score_threshold';
-- Result: signal_score_threshold | 75 | (timestamp)
```

**When does change take effect?**
- Orchestrator next run (9:30 AM, 1 PM, 3 PM, 5:30 PM ET) loads fresh config
- Example: Change at 2:00 PM → Takes effect at 3 PM orchestrator run

**Validation (prevents bad configs):**
- Type must match (int for `signal_score_threshold`, not string)
- Bounds enforced (signal_score: 40-100, data_completeness: 0.50-1.00)
- Invalid config rejected, old value persists
- Error logged: `Config validation failed: signal_score_threshold=200 exceeds max 100`

**Example: Emergency Threshold Tightening**

Market spike, want to reduce risk:
```sql
UPDATE algo_config SET value = '75' WHERE key = 'signal_score_threshold';
UPDATE algo_config SET value = '65' WHERE key = 'swing_score_threshold';
UPDATE algo_config SET value = '0.85' WHERE key = 'data_completeness_threshold';

-- Next 3 PM orchestrator run uses new thresholds
-- Result: Fewer entries (higher signal score required), higher data quality requirement
```

---

## Circuit Breaker Monitoring & Alerts

**Circuit Breakers** (`algo/circuit_breaker.py`): 8 automatic halts to prevent catastrophic loss.

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

Run: `python -m dashboard.circuit_breaker_monitor`

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
Re-engagement: Will resume when drawdown recovers to 15% (80% of threshold)
```

**Alert Configuration:**

Slack webhook to `#trading-alerts` when CB triggers:
```
🚨 CIRCUIT BREAKER TRIGGERED
Breaker: Drawdown (21.5% > 20% threshold)
Time: 2026-06-29 14:45 ET
Action: All new entries halted
Manual Recovery: Update `orchestrator_halt_enabled` to false in algo_config table OR wait for drawdown to recover to 15%
```

**Re-Engagement Logic:**

Circuit breakers auto-recover when condition improves:
- Drawdown breach (20%) → Auto-resumes when drawdown recovers to 15% (75% recovery)
- Daily loss (2%) → Auto-resumes at next day (midnight ET)
- Loss streak (3 days) → Auto-resumes at next winning day
- Other metrics → Auto-resumes when metric improves below threshold

**Manual CB Override (Emergency Only):**

If CB falsely triggered (bad data, calculation error):
```sql
-- Disable halt (allows new entries despite active CB)
UPDATE algo_config
SET value = 'false'
WHERE key = 'orchestrator_halt_enabled';

-- Verify next orchestrator run ignores CB (dangerous, use cautiously)
SELECT value FROM algo_config WHERE key = 'orchestrator_halt_enabled';

-- Re-enable when safe
UPDATE algo_config
SET value = 'true'
WHERE key = 'orchestrator_halt_enabled';
```

**Testing Circuit Breakers (Paper Trading):**

```sql
-- Set drawdown threshold to 5% temporarily
UPDATE algo_config SET value = '5' WHERE key = 'cb_drawdown_threshold';

-- Make a losing trade → Drawdown > 5% → CB triggers
-- Observe in dashboard: CB status = HALTED, reason = Drawdown

-- Restore to 20%
UPDATE algo_config SET value = '20' WHERE key = 'cb_drawdown_threshold';
```

---

## For Detailed Reference

See:
- `steering/GOVERNANCE.md` — Architecture, safety rules, system map, fail-fast principles
- `steering/LINT_POLICY.md` — Code quality, pre-commit enforcement
- `steering/DATA_LOADERS.md` — Loader orchestration, batch sizing, freshness thresholds
- `steering/DATABASE_AND_ENVIRONMENTS.md` — Database setup, AWS credentials, production infrastructure
