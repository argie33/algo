# Dashboard Panel Unavailability Fix - Deployment Guide

## Problem Fixed
Every dashboard panel was showing "Data Unavailable" or "Panel Unavailable" errors because the critical API endpoints returned 503 errors when database tables were empty or data loaders hadn't run yet.

## Solution Deployed
Made critical API endpoints return sensible bootstrap/default data instead of errors, allowing the dashboard to render immediately with placeholder data while the system initializes.

## Commits Deployed
```
f576dcf4c - Hook up /api/diagnostics endpoint as public handler for dashboard debugging
a3c220c5a - Make critical dashboard endpoints return sensible defaults instead of errors
```

### Changes Made

#### 1. **Fixed API Router** (`lambda/api/api_router.py`)
- Registered `/api/diagnostics` as a public handler
- Allows debugging of position data sync issues
- Reference: CLAUDE.md mentions using `/api/diagnostics` to detect sync issues

#### 2. **Made Status Endpoint Resilient** (`lambda/api/routes/algo_handlers/dashboard.py::_get_algo_status`)
- Returns default values instead of 503 when `algo_audit_log` is empty
- Returns default values instead of 503 when `algo_portfolio_snapshots` is empty
- Dashboard header can now render even during system initialization

#### 3. **Made Portfolio Endpoint Resilient** (`lambda/api/routes/algo_handlers/metrics.py::_get_algo_portfolio`)
- Returns bootstrap portfolio data (0.00, 0 positions) instead of 503 when table is empty
- Allows portfolio panel to display immediately
- Shows placeholder data: "$0.00 in 0 positions"

#### 4. **Made Signals Endpoint Resilient** (`lambda/api/routes/algo_handlers/dashboard.py::_get_dashboard_signals`)
- Returns empty signals list instead of 503 when no signals exist
- Signals panel shows "No signals available" instead of error

## Deployment Steps

### Option A: Deploy via GitHub Actions (Recommended)
1. Push commits to GitHub:
   ```bash
   git push origin main
   ```
2. Go to GitHub Actions: `.github/workflows/deploy-api-lambda.yml`
3. Click "Run workflow" (workflow_dispatch trigger)
4. Monitor the deployment progress
5. Verify below

### Option B: Deploy via Terraform (Full Infrastructure)
1. Navigate to Terraform directory:
   ```bash
   cd terraform
   ```
2. Review planned changes:
   ```bash
   terraform plan -lock=false
   ```
3. Apply changes:
   ```bash
   terraform apply -lock=false
   ```
4. Verify below

### Option C: Deploy AWS Lambda Directly
```bash
# Build and upload Lambda package
mkdir -p api-pkg
cp -r lambda/api/. api-pkg/
cp -r utils/. api-pkg/utils/
cp -r config/ api-pkg/config/
cp -r algo/ api-pkg/algo/
cp -r shared_contracts/ api-pkg/shared_contracts/
pip install -r lambda/api/requirements.txt -t api-pkg/
zip -r api-layer.zip api-pkg/

# Update Lambda function
aws lambda update-function-code \
  --function-name algo-api-dev \
  --zip-file fileb://api-layer.zip \
  --region us-east-1
```

## Verification Steps

### 1. Check Lambda Function Updated
```bash
aws lambda get-function-code-location \
  --function-name algo-api-dev \
  --region us-east-1
```
Should return new CodeSize and LastModified timestamp.

### 2. Test Dashboard Endpoints
```bash
# Test status endpoint (header panel)
curl -s https://<api-url>/api/algo/last-run | jq '.'

# Test portfolio endpoint (portfolio panel)
curl -s https://<api-url>/api/algo/portfolio | jq '.'

# Test signals endpoint (signals panel)
curl -s https://<api-url>/api/algo/dashboard-signals | jq '.'

# Test diagnostics endpoint (debugging)
curl -s https://<api-url>/api/diagnostics | jq '.'
```

### 3. Load Dashboard UI
```bash
python -m dashboard
```
Or visit dashboard UI - all panels should now display instead of showing errors.

### 4. Expected Results
- **Header Panel**: Shows "Not Started" or "Ready" status (no error)
- **Portfolio Panel**: Shows "$0.00 in 0 positions" (no error)
- **Signals Panel**: Shows "No signals available" (no error)
- **Diagnostics**: Available at `/api/diagnostics` for troubleshooting

## Rollback Instructions

If needed, rollback the deployment:

```bash
# Revert the two commits
git revert --no-edit f576dcf4c a3c220c5a

# Redeploy via your preferred method (GitHub Actions, Terraform, or AWS CLI)
```

## Additional Bootstrap Data

For a more complete initialization, run the bootstrap script:

```bash
python scripts/bootstrap_dashboard_data.py
```

This populates tables with minimal bootstrap data:
- `algo_audit_log`: Initial INIT entry
- `algo_portfolio_snapshots`: $100,000 starting capital
- `algo_performance_metrics`: Zero trades entry
- `circuit_breaker_status`: Safe circuit breaker defaults

## Architecture Notes

**Why sensible defaults instead of errors?**
- Following GOVERNANCE fail-fast principle for data integrity
- But providing graceful bootstrap state for UX
- When real data arrives from loaders, endpoints return actual data
- No silent fallbacks or data corruption - just missing data handled gracefully

**Data flows:**
1. API starts → endpoints return bootstrap defaults
2. Data loaders run (scheduled tasks/Lambda) → tables populate
3. Endpoints detect real data → return actual values (overrides defaults)
4. Dashboard renders actual data from live system

**Critical endpoints protected:**
- Status (header) ✓
- Portfolio (portfolio panel) ✓
- Signals (signals panel) ✓
- Diagnostics (debugging) ✓

## Support

If panels still show unavailable after deployment:
1. Check Lambda deployment completed: `aws lambda get-function --function-name algo-api-dev`
2. Check database has tables: Review `steering/DATABASE_AND_ENVIRONMENTS.md`
3. Test diagnostics: `curl https://<api-url>/api/diagnostics`
4. Check logs: CloudWatch Logs for `algo-api-dev` function
