# Operations: CI/CD & Quick Reference

## AWS Account Setup (Prerequisites)

**Required IAM Permissions for `algo-developer` User:**

The following permissions are required to deploy and manage infrastructure:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ECSTaskManagement",
      "Effect": "Allow",
      "Action": [
        "ecs:DescribeTaskDefinition",
        "ecs:RegisterTaskDefinition",
        "ecs:ListTaskDefinitions",
        "ecs:DescribeClusters",
        "ecs:RunTask",
        "ecs:ListTasks",
        "ecs:DescribeTasks"
      ],
      "Resource": "*"
    },
    {
      "Sid": "TerraformBasic",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:GetObjectVersion",
        "s3:ListBucket",
        "s3:GetBucketVersioning"
      ],
      "Resource": "*"
    }
  ]
}
```

**If you see `AccessDeniedException` for `ecs:DescribeTaskDefinition` or `s3:GetBucketPolicy`:**

Contact your AWS account admin and request these additional actions added to `algo-developer` user:
- `ecs:DescribeTaskDefinition`
- `ecs:RegisterTaskDefinition`
- `s3:GetBucketPolicy`
- `ec2:DescribeVpcAttribute`

**Status:** Code fixes deployed to main. ECS task definitions require manual update via AWS Console or elevated IAM permissions.

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

**Solution (Deployed - Lambda Routing Fix):**
- Metric loader timeout: 300s → 600s (10 minutes) — ✅ Environment override in Lambda
- Batch size in AWS: 1000 → 100 (avoids rate limiting) — ✅ Environment override in Lambda
- ECS task memory: 512MB → 1024MB (sufficient for batches) — ✅ Environment override in Lambda
- Loader classification: CRITICAL (FARGATE resource guarantee, not SPOT) — ✅ Lambda trigger routing

**How It Works (No ECS Task Definition Changes Needed):**
GitHub Actions now routes all loader triggers through the `algo-trigger-loaders` Lambda function, which applies the correct environment overrides before launching ECS tasks:
- `.github/workflows/trigger-loader.yml` modified to invoke Lambda instead of calling ECS directly
- Lambda applies containerOverrides with LOADER_CHUNK_SIZE=100, LOADER_TIMEOUT_SEC=600
- ECS task definitions do NOT need to be updated in AWS

**Deployment Status:** ✅ Complete and running
- Code changes committed to main
- GitHub Actions workflow updated and deployed
- Metric loaders running with Lambda routing (batch size 100, timeout 600s)

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

Shows:
```
Circuit Breaker Status (as of 2026-06-29 14:30 ET)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Drawdown:         0.5% (threshold: 20%)  ✓ OK
Daily Loss:       0.1% (threshold: 2%)   ✓ OK
Loss Streak:      0 days (threshold: 3)  ✓ OK
Open Risk:        2.1% (threshold: 4%)   ✓ OK
VIX Level:        18.5 (threshold: 35)   ✓ OK
Market Stage:     2 (threshold: 4)       ✓ OK
Weekly Loss:      1.2% (threshold: 5%)   ✓ OK
Win Rate:         62% (threshold: 40%)   ✓ OK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Overall:          🟢 TRADING (all green)
```

If any circuit breaker triggers:
```
Circuit Breaker Status (as of 2026-06-29 14:45 ET)
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
- `steering/DEPLOYMENT.md` — Infrastructure deployment, database migrations
- `steering/API_ARCHITECTURE.md` — API error handling, validation patterns
