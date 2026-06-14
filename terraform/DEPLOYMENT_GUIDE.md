# Deployment Guide: IaC Outputs to Dashboard Wiring

This document explains how the infrastructure-as-code (Terraform outputs) automatically wire to the dashboard configuration.

## System Architecture

```
GitHub Actions (deploy-all-infrastructure.yml)
  ↓
Terraform Apply → Creates Infrastructure
  ├─ API Gateway (outputs: api_url)
  ├─ Cognito Pool (outputs: cognito_user_pool_id, cognito_user_pool_client_id)
  └─ RDS, ECS, Lambda, etc.
  ↓
Terraform Outputs → Stored in 2 Places
  ├─ S3 Remote Backend (stocks-terraform-state bucket)
  └─ AWS Secrets Manager (algo/dashboard-config secret)
  ↓
Dashboard Startup (python tools/dashboard/dashboard.py)
  ↓
Automatic Credential Fetch (tries in order)
  ├─ Environment Variables
  ├─ Terraform Outputs
  └─ Secrets Manager
  ↓
Dashboard Displays Live Data from AWS Endpoints
```

## Complete Deployment Flow

### Step 1: Infrastructure Deployment

**Via GitHub Actions (Recommended for Production):**
```bash
git push main  # Triggers deploy-all-infrastructure.yml
```

Workflow does:
1. AWS OIDC authentication (no static keys)
2. Terraform init + apply (creates infrastructure)
3. Terraform outputs extracted and stored
4. Secrets Manager secret created
5. Database migrations applied
6. Deployment summary generated

### Step 2: Dashboard Configuration

After infrastructure deploys, dashboard automatically gets config through fallback chain:

**Option A: Fetch from Terraform Outputs (Default)**
```bash
cd tools/dashboard
python dashboard.py
# Tries: terraform output -json
# Gets: api_url, cognito_user_pool_id, cognito_user_pool_client_id
# Dashboard connects to AWS endpoints
```

**Option B: Fetch from Secrets Manager (If Terraform unavailable)**
Dashboard automatically falls back to:
```bash
aws secretsmanager get-secret-value --secret-id algo/dashboard-config
# Gets: api_url, cognito_user_pool_id, cognito_user_pool_client_id
# Dashboard connects to AWS endpoints
```

**Option C: Manual Environment Variables (For Testing)**
```powershell
$env:DASHBOARD_API_URL = "<terraform output api_url>"
$env:COGNITO_USER_POOL_ID = "<terraform output cognito_user_pool_id>"
$env:COGNITO_CLIENT_ID = "<terraform output cognito_user_pool_client_id>"

python tools/dashboard/dashboard.py
```

### Step 3: Verify Deployment

```bash
# Check Terraform state
cd terraform
terraform output -json | jq .

# Check Secrets Manager
aws secretsmanager get-secret-value --secret-id algo/dashboard-config --query SecretString

# Run dashboard (auto-fetches config)
python tools/dashboard/dashboard.py
```

## Local Development (Without AWS Deployment)

For testing without deploying infrastructure:

```bash
# Option 1: Local API server (no AWS)
python tools/dashboard/dashboard.py --local  # Uses localhost:3001

# Option 2: Manual environment variables (for staging/pre-release)
$env:DASHBOARD_API_URL = "https://staging-api.example.com"
$env:COGNITO_USER_POOL_ID = "us-east-1_xyz"
$env:COGNITO_CLIENT_ID = "abc123"
python tools/dashboard/dashboard.py
```

## Credential Refresh (Quarterly or After Rotation)

When credentials expire or are rotated:

```powershell
# Refresh local AWS credentials and Terraform state
.\scripts\refresh-aws-credentials.ps1

# Dashboard will automatically fetch new credentials on next startup
python tools/dashboard/dashboard.py
```

## System Readiness Checklist

### Tests
- [x] 141 tests passing
- [x] 2 tests skipped (expected)
- [x] Credential-fetching code implemented
- [x] Fallback chain: environment vars → Terraform → Secrets Manager

### IaC Configuration
- [x] Terraform configured with S3 remote backend
- [x] Terraform outputs defined (api_url, cognito_*, etc.)
- [x] Secrets Manager integration in Terraform
- [x] Backend bucket configuration in workflow

### GitHub Actions
- [x] deploy-all-infrastructure.yml created
- [x] AWS OIDC role configured
- [x] Terraform init + apply steps
- [x] Secrets Manager creation step
- [x] Database migrations step

### Dashboard
- [x] Credential fetching (_fetch_terraform_credentials, _fetch_secrets_manager_credentials)
- [x] Fallback chain implemented
- [x] Error messages guide users to solutions
- [x] Supports --local for development

### Documentation
- [x] steering/algo.md updated with credential flow
- [x] Dashboard code comments documenting architecture
- [x] Deployment guide (this file)
- [x] Error messages in dashboard guide users

## Production Deployment Steps

1. **Configure AWS OIDC Role**
   ```bash
   # GitHub Actions needs: AWS_OIDC_ROLE_ARN secret in GitHub
   # This role has permissions to: run Terraform, create infrastructure, access Secrets Manager
   ```

2. **Push to Main**
   ```bash
   git push main
   # Automatically triggers deploy-all-infrastructure.yml
   ```

3. **Monitor Deployment**
   - Check GitHub Actions logs: infrastructure creation, migrations, outputs
   - Expected time: 15-30 minutes

4. **Verify Dashboard Works**
   ```bash
   # On local machine (with AWS credentials configured)
   python tools/dashboard/dashboard.py
   # Dashboard fetches config from Terraform outputs
   # Displays live data from API Gateway
   ```

## Troubleshooting

### Dashboard Shows: "Could not fetch AWS credentials"

This means dashboard tried all three sources and failed:

1. **Check environment variables**
   ```powershell
   echo $env:DASHBOARD_API_URL
   ```

2. **Check Terraform outputs** (requires AWS credentials)
   ```bash
   cd terraform
   terraform output -json  # Should show api_url, cognito_user_pool_id, cognito_user_pool_client_id
   ```

3. **Check Secrets Manager** (requires AWS credentials)
   ```bash
   aws secretsmanager get-secret-value --secret-id algo/dashboard-config
   ```

4. **If all fail:**
   - Infrastructure may not be deployed yet (run GitHub Actions workflow)
   - OR AWS credentials not configured locally (run `aws configure`)
   - OR use `--local` flag for development

### Terraform Output Fails: "No valid credential sources found"

Means Terraform can't access S3 backend:

```bash
# Refresh AWS credentials
.\scripts\refresh-aws-credentials.ps1

# Re-initialize Terraform
cd terraform && terraform init
```

## Next Steps

1. **Deploy Infrastructure:** `git push main` (runs deploy-all-infrastructure.yml)
2. **Monitor Deployment:** Check GitHub Actions workflow logs
3. **Run Dashboard:** `python tools/dashboard/dashboard.py` (auto-fetches config)
4. **Verify System:** Check dashboard displays live data from AWS endpoints

The credential wiring is complete and automatic—no manual config passing needed.

