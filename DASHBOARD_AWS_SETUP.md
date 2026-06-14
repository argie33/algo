# Dashboard AWS Setup - Complete Architecture Guide

This document explains the complete architecture for running the dashboard with AWS-only endpoints, with no fallbacks and all credentials dynamically fetched.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     DASHBOARD STARTUP                          │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 1. LOCAL AWS CREDENTIALS NEEDED                                │
│    ~/.aws/credentials (algo-developer profile)                 │
│    Set by: scripts/refresh-aws-credentials.ps1                │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. FETCH DASHBOARD CONFIG FROM SECRETS MANAGER                 │
│    Secret: algo/dashboard-config                              │
│    Keys: api_url, cognito_user_pool_id, cognito_user_pool_client_id
│    Set by: GitHub Actions deploy-all-infrastructure.yml       │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. SET ENVIRONMENT VARIABLES                                   │
│    DASHBOARD_API_URL                                          │
│    COGNITO_USER_POOL_ID                                       │
│    COGNITO_CLIENT_ID                                          │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. COGNITO AUTHENTICATION                                      │
│    Try (in order):                                            │
│    - Env vars: COGNITO_USERNAME + COGNITO_PASSWORD           │
│    - Cached token: ~/.algo/cognito_token.json                │
│    - Interactive: Prompt user for email/password             │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. START DASHBOARD                                            │
│    - Connect to API Gateway with Cognito tokens              │
│    - Fetch real-time market data                             │
│    - Render TUI with positions, signals, health, etc.        │
└─────────────────────────────────────────────────────────────────┘
```

## Prerequisites

1. **AWS Account with Algo infrastructure deployed**
   - Lambda API Gateway
   - RDS database
   - Cognito user pool
   - Deployed via: `.github/workflows/deploy-all-infrastructure.yml`

2. **Local AWS credentials**
   - Profile: `algo-developer`
   - Location: `~/.aws/credentials`
   - Set by: `scripts/refresh-aws-credentials.ps1`

3. **Python environment**
   - `python3.10+` with `pip`
   - Dependencies: `pip install -r tools/dashboard/requirements.txt`

## Step-by-Step Setup

### Step 1: Verify Infrastructure is Deployed

The GitHub Actions deploy must have completed successfully:
- Check: `.github/workflows/deploy-all-infrastructure.yml` (should show ✅ SUCCESS)
- This creates:
  - API Gateway endpoint
  - Cognito user pool with client
  - Terraform outputs saved to Secrets Manager (`algo/dashboard-config`)

### Step 2: Refresh Local AWS Credentials

Run the credential refresh script:

```powershell
./scripts/refresh-aws-credentials.ps1
```

This:
- Triggers GitHub Actions to fetch fresh AWS developer credentials
- Downloads credentials to local `~/.aws/credentials`
- Verifies credentials work with `aws sts get-caller-identity`
- Checks if dashboard config exists in Secrets Manager

**Output should show:**
```
[OK] Credentials verified successfully
  Profile: algo-developer
  IAM ARN: arn:aws:iam::...
  Account: ...
[OK] Dashboard config found in Secrets Manager:
  API URL: https://...
  Cognito Pool: us-east-1_...
  Cognito Client: ...
```

### Step 3: Run Dashboard Setup Verification

Run the setup verification script:

```powershell
./scripts/setup-dashboard.ps1
```

This:
- Verifies local AWS credentials (`algo-developer` profile)
- Fetches dashboard config from Secrets Manager
- Tests API Gateway connectivity
- Provides clear errors if anything is missing

**Output should show:**
```
[1/4] Checking local AWS credentials... [OK]
[2/4] Verifying AWS credentials... [OK]
[3/4] Fetching dashboard configuration... [OK]
[4/4] Testing API Gateway connectivity... [OK]

╔════════════════════════════════════════╗
║  DASHBOARD READY TO RUN                ║
╚════════════════════════════════════════╝
```

### Step 4: Start the Dashboard

```bash
cd tools/dashboard
python dashboard.py -w 30  # Auto-refresh every 30 seconds
```

On first run, you'll be prompted for Cognito credentials:
```
============================================================
Cognito Authentication Required
============================================================
Email [user@example.com]: your-email@example.com
Password: ••••••••
[Cognito] Authenticated as your-email@example.com
```

## Credential Flow (Detailed)

### Local AWS Credentials

**File**: `~/.aws/credentials`

```ini
[algo-developer]
aws_access_key_id = AKIAIOSFODNN7EXAMPLE
aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
region = us-east-1
```

**Set by**: `scripts/refresh-aws-credentials.ps1` → GitHub Actions workflow → IAM credentials

**Used for**: Accessing AWS Secrets Manager to fetch dashboard config

### Secrets Manager: algo/dashboard-config

**Secret ID**: `algo/dashboard-config`

**Secret Format** (JSON):
```json
{
  "api_url": "https://abc123def456.execute-api.us-east-1.amazonaws.com",
  "cognito_user_pool_id": "us-east-1_aBcDeF1Gh",
  "cognito_user_pool_client_id": "1a2b3c4d5e6f7g8h9i0j"
}
```

**Set by**: GitHub Actions `.github/workflows/deploy-all-infrastructure.yml` → Terraform outputs → Secrets Manager

**Used for**: Dashboard startup → Determine API endpoint and Cognito configuration

### Cognito User Pool Configuration

**Default Test User** (created by deploy): `default_test_user@example.com`

**Credentials** (in Secrets Manager):
- Secret: `algo/cognito-test-user`
- Contains: username, password

**Used for**: Dashboard authentication → User logs in with Cognito → Gets access token → Includes token in API calls

## Complete Example: From Deployment to Dashboard

### 1. Deploy Infrastructure

Push to main:
```bash
git push origin main
```

GitHub Actions runs `.github/workflows/deploy-all-infrastructure.yml`:
- Creates Terraform infrastructure
- Saves outputs to Secrets Manager (`algo/dashboard-config`)
- Workflow completes with ✅ SUCCESS

### 2. Refresh Local Credentials

```powershell
./scripts/refresh-aws-credentials.ps1
# Output shows Secrets Manager config is present
```

### 3. Verify Setup

```powershell
./scripts/setup-dashboard.ps1
# Output shows all 4 checks pass
```

### 4. Run Dashboard

```bash
cd tools/dashboard
python dashboard.py -w 30
# First run: Interactive Cognito login
# Subsequent runs: Uses cached token or cached Cognito session
```

## Troubleshooting

### "Dashboard credentials not found in AWS Secrets Manager"

**Cause**: Deploy hasn't run, or deploy failed

**Fix**:
1. Check GitHub Actions: `.github/workflows/deploy-all-infrastructure.yml`
2. If not run: Push code to main to trigger deploy
3. If failed: Check workflow logs for errors
4. After deploy succeeds: Run `scripts/refresh-aws-credentials.ps1` again

### "AWS credentials not working"

**Cause**: Credentials expired or not set up locally

**Fix**:
```powershell
./scripts/refresh-aws-credentials.ps1
# This fetches fresh credentials and updates ~/.aws/credentials
```

### "Could not reach API Gateway"

**Cause**: API not responding, or network issue

**Fix**:
1. Verify API Gateway deployed: Check AWS Console → API Gateway
2. Check API Gateway logs: CloudWatch → Logs
3. Verify network: Can you ping the API URL?
4. Wait: API may be initializing (takes 1-2 minutes after deploy)

### "Authentication failed"

**Cause**: Invalid Cognito credentials, or Cognito user doesn't exist

**Fix**:
1. Verify user in Cognito: AWS Console → Cognito → User Pools → Users
2. Reset password: `aws cognito-idp admin-set-user-password`
3. Check test user credentials: `aws secretsmanager get-secret-value --secret-id algo/cognito-test-user`

## Environment Variables (For Reference)

The dashboard sets these automatically from Secrets Manager:

```bash
DASHBOARD_API_URL              # e.g., https://abc123.execute-api.us-east-1.amazonaws.com
COGNITO_USER_POOL_ID          # e.g., us-east-1_aBcDeF1Gh
COGNITO_CLIENT_ID             # e.g., 1a2b3c4d5e6f7g8h
AWS_PROFILE                    # algo-developer
AWS_DEFAULT_REGION             # us-east-1
```

Optional (for testing):
```bash
COGNITO_USERNAME               # Email of test user
COGNITO_PASSWORD               # Password (for non-interactive testing)
```

## Key Files

| File | Purpose |
|------|---------|
| `tools/dashboard/dashboard.py` | Main dashboard entry point |
| `tools/dashboard/fetchers.py` | API endpoint fetchers (positions, trades, signals, etc.) |
| `tools/dashboard/utilities.py` | API call helpers, Cognito integration |
| `tools/dashboard/cognito_auth.py` | Cognito authentication logic |
| `scripts/refresh-aws-credentials.ps1` | Set up local AWS credentials |
| `scripts/setup-dashboard.ps1` | Verify dashboard is ready to run |
| `.github/workflows/deploy-all-infrastructure.yml` | Deploy all AWS infrastructure |
| `steering/algo.md` | System architecture documentation |

## What The Dashboard Does (AWS Mode)

1. **Fetches live market data** from API Gateway
   - SPY price, VIX, market breadth, economic indicators
   
2. **Displays trading positions** from the algo
   - Open positions, entry price, T1/T2 targets, P&L
   
3. **Shows trading signals** from the signal engine
   - Buy signals, grades, near-term plays, top performers
   
4. **Displays algo health** from data loaders
   - Which data sources are fresh, which are stale
   
5. **Auto-refreshes every 30 seconds** (configurable)
   - Keep market view up-to-date throughout trading day

6. **Handles real-time updates** with no fallbacks
   - Missing data → shows error (not zero)
   - Stale data (>5min) → shows warning with timestamp

## AWS-Only Architecture Benefits

✅ **No hardcoded values** - Everything fetched at runtime from Secrets Manager

✅ **No environment variable setup needed** - Dashboard fetches everything automatically

✅ **No fallbacks to stale data** - Real-time API or clear error

✅ **Single source of truth** - Terraform outputs → Secrets Manager → Dashboard

✅ **Fully dynamic** - Redeploy infrastructure, refresh credentials, dashboard picks it up

✅ **Secure** - Credentials in Secrets Manager, not in code or env files

## See Also

- `steering/algo.md` - System architecture and credentials strategy
- `.github/workflows/deploy-all-infrastructure.yml` - Deployment process
- `terraform/` - Infrastructure as Code
