# Deployment Procedures

Deployment flow: Infrastructure code review → Terraform plan approval → Docker build → Lambda/ECS update → Verification.

---

## Code Deployment (Application Changes)

**For changes to:** Lambda functions, Python loaders, API routes, dashboard logic, configs.

**Process:**
1. Make code changes locally
2. Pre-commit hooks validate: `mypy strict`, linting, no `.env` files (see `LINT_POLICY.md`)
3. Push to branch, create PR
4. CI gates run (27 min average): secrets scan, type checking, tests, coverage ≥75%
5. ≥1 approval required, all gates pass
6. Merge to `main`
7. **Auto-deployment trigger:** GitHub Actions `ci-fast-gates.yml` detects `main` commit
   - Builds Lambda functions (zips Python code)
   - Pushes Docker image to ECR (for ECS loaders)
   - Updates Lambda code on `algo-orchestrator`, `algo-api`, etc.
   - **No downtime:** Lambda provisioned concurrency pre-warmed; ECS loaders stateless

**Verification after deployment:**
```bash
# Check Lambda function version (should show new timestamp)
aws lambda get-function --function-name algo-orchestrator | jq '.Configuration.LastModified'

# Check CloudWatch Logs (should show fresh events)
aws logs tail /aws/lambda/algo-orchestrator --follow

# Check ECS task CPU/memory (no runaway tasks)
aws ecs describe-services --cluster algo-cluster --services algo-eod-pipeline \
  | jq '.services[0].deployments'
```

---

## Infrastructure Deployment (AWS Resources, Terraform)

**For changes to:** VPC, security groups, RDS, Lambda configuration, IAM, EventBridge, ECS task definitions.

**Process:**
1. Modify `.tf` files in `terraform/` directory
2. Pre-commit hook validates: `terraform fmt -recursive`, `terraform validate`
3. Push to branch, create PR
4. CI runs `terraform plan` in dry-run mode:
   ```
   Terraform will perform the following actions:
   + aws_lambda_function.algo_orchestrator (Lambda timeout change)
   ...
   Plan: 1 to add, 0 to change, 2 to destroy.
   ```
5. Plan output posted to PR comments (review for correctness)
6. ≥1 approval required
7. Merge to `main`
8. **Manual deployment trigger:** GitHub Actions workflow `deploy-all-infrastructure.yml` (manual `workflow_dispatch`)
   - **Bootstrap backend** (first-time only): Creates S3 bucket + DynamoDB for Terraform state
   - **Terraform plan:** Generates execution plan (posted to Slack for review)
   - **Wait for manual approval** (60-minute window)
   - **Terraform apply:** Executes plan, applies changes to AWS
   - **Smoke test:** Queries RDS, checks Lambda invocation, verifies S3 access
   - Posts result to Slack (#eng channel)

**Manual Deployment Trigger:**
```
1. Go to GitHub repo → Actions tab
2. Select workflow: "Deploy All Infrastructure"
3. Click "Run workflow"
4. Wait for plan (5 min)
5. Review in Slack (#eng) for any "destroy" warnings
6. If OK, click "Approve and Deploy" in workflow UI
7. Apply runs (10-15 min), posts success/failure to Slack
```

**Safety Checks Built-In:**
- Prevents destruction of RDS database (added `prevent_destroy = true`)
- Blocks changes to `algo_config` table schema (manual only)
- Limits Lambda timeout changes to trading hours only

**Rollback if Terraform Fails:**
```bash
# Revert last git commit (Terraform will see old state)
git revert HEAD

# Manual deployment trigger again (applies old state)
# Result: AWS resources roll back to previous config
```

---

## Database Migrations

**For changes to:** Table schema, new columns, index additions, data type changes.

**Process:**

1. **Create migration file:**
   ```bash
   alembic revision --autogenerate -m "add column to stock_scores"
   # Creates: migrations/versions/092_add_column_to_stock_scores.py
   ```

2. **Edit migration manually** (autogenerate not always correct):
   ```python
   def upgrade():
       op.add_column('stock_scores', sa.Column('new_field', sa.Float))
       op.execute("UPDATE stock_scores SET new_field = 0")
   
   def downgrade():
       op.drop_column('stock_scores', 'new_field')
   ```

3. **Test locally:**
   ```bash
   # Reset local DB to HEAD state, apply new migration
   python -m alembic upgrade head
   # Verify schema: \dt stock_scores in psql
   ```

4. **Commit & merge to main** (like normal code changes)

5. **Production application:**
   - **During low-load window** (after 8 PM ET trading closes)
   - **Single window, no back-offs:** Lambda orchestrator runs schema migration on first execution
   - Alembic tracks applied migrations in `alembic_version` table (never re-applies)
   - If migration fails → Lambda logs error, continues (operator must fix manually)

**Backfill Data Without Downtime:**

If adding new column that traders need immediately (e.g., new risk metric):

```python
# Migration: add column with default
op.add_column('stock_scores', sa.Column('new_metric', sa.Float, default=0.0))

# Backfill in-background (doesn't block trading):
op.execute("""
    UPDATE stock_scores SET new_metric = (
        SELECT computed_value FROM temp_metrics WHERE stock_id = stock_scores.stock_id
    ) WHERE new_metric IS NULL
""")
```

**Rollback Production Migration:**

```bash
# If migration broken (e.g., corrupt data):
alembic downgrade -1  # Revert last migration
# Redeploy Lambda (auto-applies previous state)
```

**Check Migration Status:**
```sql
-- List applied migrations
SELECT * FROM alembic_version;

-- Verify table schema
\d stock_scores
```

---

## Configuration Hotload

**For changes to:** Trading parameters, safety thresholds, loader timeouts (no code restart needed).

**Process:**

1. **Update `algo_config` table directly** (during trading hours):
   ```sql
   UPDATE algo_config 
   SET value = '75' 
   WHERE key = 'signal_score_threshold';
   ```

2. **Validation:** LoaderConfigManager re-reads on next operation (5-min cache):
   - Checks type (int vs string)
   - Checks bounds (e.g., signal_score_threshold: 40-100)
   - Raises error if invalid (config rejected, old value persists)

3. **Orchestrator reloads config** at next scheduled run (9:30 AM, 1 PM, 3 PM, 5:30 PM)

4. **Immediate effect examples:**
   - Change `enable_earnings_blackout` to `false` → Next orchestrator run uses new setting
   - Change `entry_volume_threshold` → New positions use new threshold instantly
   - Change `loader_parallelism` → Next 4:05 PM EOD loader run uses new parallelism

**Config Parameter Registry:**
| Parameter | Type | Default | Bounds | Hot-Reload? |
|-----------|------|---------|--------|-------------|
| signal_score_threshold | int | 60 | 40-100 | ✅ yes |
| swing_score_threshold | int | 55 | 0-100 | ✅ yes |
| data_completeness_threshold | float | 0.70 | 0.50-1.00 | ✅ yes |
| enable_earnings_blackout | bool | true | — | ✅ yes |
| entry_volume_threshold | int | 300000 | 50000-10M | ✅ yes |
| entry_dollar_volume | int | 500000 | 100k-50M | ✅ yes |
| orchestrator_halt_enabled | bool | true | — | ✅ yes |
| price_loader_batch_size | int | 1000 | 100-5000 | ✅ (EOD only) |
| metric_loader_parallelism | int | 5 | 1-20 | ✅ (EOD only) |

**Example: Emergency Safety Adjustment**

During market volatility, want to tighten entry signal threshold:
```sql
-- Current setting
SELECT * FROM algo_config WHERE key = 'signal_score_threshold';
-- signal_score_threshold | 60 |

-- Tighten to 75 (higher = fewer entries)
UPDATE algo_config SET value = '75' WHERE key = 'signal_score_threshold';

-- Verify next orchestrator run (5:30 PM) uses new threshold
-- Dashboard shows: "Config reloaded: signal_score_threshold=75"
```

---

## Deployment Verification Checklist

**After any deployment (code or infrastructure):**

```
☐ CloudWatch Logs: No ERROR or CRITICAL in last 10 min
☐ Lambda Invocations: Count > 0 in last hour (orchestrator running)
☐ RDS Performance: CPU < 80%, connection count < 80 (not maxed at 100)
☐ Dashboard Data: Portfolio snapshot age < 6 min (reconciliation running)
☐ ECS Tasks: No failed tasks in last hour (loaders completing)
☐ Secrets Manager: All secrets readable (credential validation passed)
☐ S3/CloudFront: Frontend loads without errors (if frontend deployed)
☐ Test Trade: Paper trade entry/exit in test mode (if orchestrator changed)
```

**Rollback if Critical Issue Found:**
```bash
git revert HEAD  # Revert code changes
git push main    # Auto-redeploys old version
# Or manual Terraform rollback if infrastructure broke
```

---

## For Detailed Reference

See:
- `steering/GOVERNANCE.md` — Architecture, system map, pre-commit rules
- `steering/OPERATIONS.md` — Troubleshooting, CI/CD gates, branch protection
- `.github/workflows/ci-fast-gates.yml` — Full CI pipeline definition
- `.github/workflows/deploy-all-infrastructure.yml` — Infrastructure deployment workflow
- `terraform/` — All AWS resource definitions
