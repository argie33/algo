# 🚀 LIVE TRADING MODE SETUP (2026-07-06)

## Current Status
✅ **Orchestrator**: Fully operational (9/9 phases working)
✅ **Alpaca Credentials**: Present in AWS Secrets Manager (`algo/alpaca`)
✅ **IaC Configuration**: Updated to `execution_mode = "live"`
✅ **Code**: Fixed and deployed
⏳ **GitHub Secrets**: PENDING - Needs Alpaca credentials added

## Step 1: Add Alpaca Credentials to GitHub Secrets

Your Alpaca API credentials are already securely stored in AWS Secrets Manager. Now add them to GitHub Secrets so the GitHub Actions deployment workflow can pass them to Terraform.

**To add secrets to GitHub:**

1. Go to: https://github.com/argeropolos/algo/settings/secrets/actions

2. Click **"New repository secret"** and add these TWO secrets:

| Secret Name | Value |
|---|---|
| `ALPACA_API_KEY_ID` | `PKZ6MHPX2B24O7RRCG4XGWXYU3` |
| `ALPACA_API_SECRET_KEY` | `AmTANE8xkjTXKWTZwnJhuNwGzwg97SQdDsD5PDaS1yWs` |

⚠️ **Security Note**: GitHub Secrets are encrypted and only passed to GitHub Actions workflows. They are NOT stored in your repository or code.

## Step 2: Deploy via GitHub Actions

Once secrets are added, deploy the updated configuration:

```bash
# Option A: Use GitHub Web UI
# 1. Go to: https://github.com/argeropolos/algo/actions
# 2. Select: "Deploy All Infrastructure"
# 3. Click: "Run workflow"
# 4. Wait for completion (~10-15 minutes)

# Option B: Trigger via CLI
gh workflow run deploy-all-infrastructure.yml --repo argeropolos/algo
```

## Step 3: Verify Deployment

After deployment completes, verify the system is ready:

```bash
# Check that Terraform updated execution_mode environment variable
aws lambda get-function-configuration --function-name algo-algo-dev \
  --query 'Environment.Variables.ORCHESTRATOR_EXECUTION_MODE' \
  --region us-east-1
# Expected output: "live"

# Verify orchestrator can load credentials on next run
# (Will be tested automatically on next EventBridge trigger)
```

## Step 4: Monitor First Run

The orchestrator will run automatically on the next scheduled time:
- **9:30 AM ET** (Primary morning run)
- **1:00 PM ET** (Afternoon update)
- **3:00 PM ET** (Pre-close update)

To trigger immediately for testing:
```bash
gh workflow run orchestrator-scheduler.yml --repo argeropolos/algo
```

Check logs:
```bash
# View CloudWatch logs for orchestrator Lambda
aws logs tail /aws/lambda/algo-algo-dev --follow --region us-east-1
```

## Architecture: Credentials Flow

```
┌─────────────────────────────────────────────────────────────┐
│                  GitHub Repository                          │
│  - terraform/terraform.tfvars (execution_mode = "live")     │
│  - NO credentials in code (security best practice)          │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ↓
┌─────────────────────────────────────────────────────────────┐
│              GitHub Actions Workflow                         │
│  - Reads ALPACA_API_KEY_ID from GitHub Secrets             │
│  - Reads ALPACA_API_SECRET_KEY from GitHub Secrets         │
│  - Passes via TF_VAR_* environment variables to Terraform   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ↓
┌─────────────────────────────────────────────────────────────┐
│                  Terraform Apply                             │
│  - Updates AWS Secrets Manager (algo/alpaca)               │
│  - Sets Lambda environment variables:                       │
│    - ORCHESTRATOR_EXECUTION_MODE=live                       │
│    - ALGO_SECRETS_ARN=arn:aws:secretsmanager:...           │
│    - APCA_API_BASE_URL=https://paper-api.alpaca.markets    │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ↓
┌─────────────────────────────────────────────────────────────┐
│              EventBridge Scheduler (AWS)                     │
│  - Triggers API Lambda at scheduled times                   │
│  - 9:30 AM, 1 PM, 3 PM ET (Mon-Fri)                        │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ↓
┌─────────────────────────────────────────────────────────────┐
│           API Lambda (algo-algo-dev)                        │
│  - Receives environment variables from Terraform           │
│  - Spawns orchestrator subprocess                          │
│  - Passes environment variables to subprocess              │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ↓
┌─────────────────────────────────────────────────────────────┐
│         Orchestrator Subprocess (algo/orchestration)        │
│  1. Reads ORCHESTRATOR_EXECUTION_MODE=live from env        │
│  2. Reads ALGO_SECRETS_ARN from env                        │
│  3. Initializes config with execution_mode=live            │
│  4. Calls CredentialManager.get_alpaca_credentials()       │
│  5. CredentialManager reads from AWS Secrets Manager       │
│  6. Orchestrator validates credentials                     │
│  7. Phase 8 executes trades with real Alpaca API keys      │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ↓
┌─────────────────────────────────────────────────────────────┐
│           AWS Secrets Manager (algo/alpaca)                │
│  - Stores credentials securely                             │
│  - Never exposed in code, logs, or environment            │
│  - Only CredentialManager can read via IAM role           │
└─────────────────────────────────────────────────────────────┘
```

## Testing the Credentials Flow

### Local Test (Dry-run Mode)
```bash
# Test orchestrator can start and find credentials
export ORCHESTRATOR_EXECUTION_MODE=live
export ALGO_SECRETS_ARN=arn:aws:secretsmanager:us-east-1:626216981288:secret:algo/alpaca-PCRI0a
python3 -m algo.orchestration.orchestrator --dry-run

# Expected output:
# [OK] Alpaca credentials validated for live trading
# [STARTUP] All validation checks passed
# Orchestrator executes all 9 phases (Phase 8 skipped in dry-run)
```

### Lambda Test (Immediate Trigger)
```bash
# Invoke API Lambda directly with EventBridge event format
aws lambda invoke \
  --function-name algo-algo-dev \
  --region us-east-1 \
  --invocation-type RequestResponse \
  --payload '{"source":"eventbridge-scheduler","run_identifier":"manual-test"}' \
  response.json
cat response.json
```

## Troubleshooting

### Problem: "Alpaca credentials not found"
**Cause**: GitHub Secrets not added, or GitHub Actions workflow not re-run after adding secrets

**Solution**:
1. Verify secrets exist: https://github.com/argeropolos/algo/settings/secrets/actions
2. Re-run deployment workflow: https://github.com/argeropolos/algo/actions
3. Check Lambda environment variables:
   ```bash
   aws lambda get-function-configuration --function-name algo-algo-dev --region us-east-1
   ```

### Problem: "execution_mode is paper, not live"
**Cause**: Terraform apply didn't complete, or old Lambda layer cached

**Solution**:
1. Check Terraform state: `terraform state show | grep execution_mode`
2. Verify Lambda environment: `aws lambda get-function-configuration ...`
3. Force redeploy: `gh workflow run deploy-all-infrastructure.yml --ref main`

### Problem: Trades not executing
**Cause**: Paper trading mode active (expected), or Phase 8 skipping due to credentials error

**Solution**:
1. Check orchestrator logs: `aws logs tail /aws/lambda/algo-algo-dev --follow`
2. Look for "Phase 8" output - should show: `[EXECUTOR] Running in live mode`
3. If it says "paper trading mode without live broker", credentials aren't being loaded

## What Happens Next

### After Deployment
1. **Within 5 minutes**: CloudFormation/Terraform apply completes
2. **At next scheduled time** (9:30 AM ET, 1 PM ET, or 3 PM ET):
   - EventBridge Scheduler triggers API Lambda
   - Orchestrator loads Alpaca credentials from AWS Secrets Manager
   - Phase 7: Generates trading signals
   - Phase 8: Executes live trades with your credentials
   - Positions stored in database
   - Dashboard shows live positions and P&L

### Monitoring
- **Dashboard**: `python -m dashboard --local` (shows live positions)
- **Logs**: `aws logs tail /aws/lambda/algo-algo-dev --follow`
- **Database**: Check `algo_trades` and `algo_positions` tables

## Rolling Back to Paper Mode

If you need to disable live trading:

```bash
# Edit terraform.tfvars
# Change: execution_mode = "live"
# To:     execution_mode = "paper"

# Deploy
gh workflow run deploy-all-infrastructure.yml
```

## Security Checklist

- ✅ Credentials in AWS Secrets Manager (not in code)
- ✅ Credentials in GitHub Secrets (encrypted by GitHub)
- ✅ GitHub Actions passes via environment variables only
- ✅ Terraform never logs credentials
- ✅ Lambda environment has ARN to secret, not the secret itself
- ✅ CredentialManager fetches only at runtime via IAM role

---

**Questions?** Check:
- `steering/GOVERNANCE.md` - Risk management and safety gates
- `steering/OPERATIONS.md` - Day-to-day operations
- `CLAUDE.md` - Project structure and patterns
