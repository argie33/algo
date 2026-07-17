# CRITICAL FIX: Alpaca Credentials Missing in AWS (Session 193)

## Problem

Orchestrator Phase 8 (trading execution) is halted with:
```
[PHASE 8 CRITICAL] Alpaca credentials not available
```

The `algo/alpaca` secret does NOT exist in AWS Secrets Manager, preventing any trade execution.

## Root Cause

GitHub Actions workflow expects these secrets to be set:
- `ALPACA_API_KEY_ID` 
- `ALPACA_API_SECRET_KEY`

Terraform reads these and creates the AWS Secrets Manager secret. If not deployed, credentials are missing.

## Solution

### Step 1: Set GitHub Secrets

1. Go to: https://github.com/argie33/algo/settings/secrets/actions
2. Click "New repository secret"
3. Add **ALPACA_API_KEY_ID**:
   - Name: `ALPACA_API_KEY_ID`
   - Value: Your Alpaca API key (e.g., `PK_PAPER_xxxxxxxx`)
   - Click "Add secret"
4. Add **ALPACA_API_SECRET_KEY**:
   - Name: `ALPACA_API_SECRET_KEY`
   - Value: Your Alpaca secret key
   - Click "Add secret"

### Step 2: Trigger Terraform Deployment

**Option A: Via GitHub UI (Recommended)**
1. Go to Actions tab: https://github.com/argie33/algo/actions
2. Find "Deploy All Infrastructure (Terraform)" workflow
3. Click "Run workflow" → Select "main" branch → "Run workflow"
4. Wait ~15 minutes for deployment to complete

**Option B: Via Git Push**
```bash
git push origin main
```
This will trigger automatic deployment.

### Step 3: Verify

After deployment completes, check AWS:
```bash
aws secretsmanager get-secret-value --secret-id algo/alpaca --region us-east-1
```

Should return:
```json
{
  "APCA_API_KEY_ID": "PK_PAPER_...",
  "APCA_API_SECRET_KEY": "...",
  "APCA_API_BASE_URL": "https://paper-api.alpaca.markets"
}
```

Then run orchestrator:
```bash
python scripts/trigger_morning_pipeline.py
```

Should execute successfully with Phase 8 completing trades.

## What Gets Fixed

- ✅ Phase 8 (execution) can now run
- ✅ Trades will be generated and sent to Alpaca API
- ✅ Portfolio positions will be tracked
- ✅ Dashboard will show live trade activity

## Related Files

- `.github/workflows/deploy-all-infrastructure.yml` - Sets `TF_VAR_alpaca_api_key_id` and `TF_VAR_alpaca_api_secret_key` from GitHub Secrets
- `terraform/modules/database/main.tf` (line 412) - Creates `algo/alpaca` secret in Secrets Manager
- `config/credential_manager.py` - Loads credentials from AWS in production
- `lambda/algo_orchestrator/lambda_function.py` - Loads credentials on Lambda startup
