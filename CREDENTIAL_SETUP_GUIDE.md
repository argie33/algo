# Credential Setup Guide

**CRITICAL ISSUE FIXED:** Alpaca credentials were not being persisted to the system. This guide explains where credentials go and how to set them up so they actually work end-to-end.

## Quick Start

Choose your setup path:

### Local Development (No AWS Required)

```bash
# 1. Set credentials for this session
source scripts/setup_local_alpaca_credentials.sh
# Follow prompts to enter your Alpaca API key and secret

# 2. Run orchestrator with credentials active
python3 scripts/run_local_orchestrator.py

# 3. Or run dev server
python3 api-pkg/dev_server.py
```

### Production (AWS Lambda + GitHub Actions)

1. **Set GitHub Secrets** (one-time setup):
   ```
   https://github.com/argie33/algo/settings/secrets/actions
   ```

2. **Add these secrets:**
   - `ALPACA_API_KEY_ID`: Your Alpaca paper API key (e.g., `PK_PAPER_xxxxx`)
   - `ALPACA_API_SECRET_KEY`: Your Alpaca secret key
   - `JWT_SECRET`: Generate with `openssl rand -base64 32`
   - `FRED_API_KEY`: Your FRED API key (for economic data loader)

3. **Deploy:**
   ```bash
   git push origin main
   # GitHub Actions will automatically:
   # - Validate secrets are set (scripts/verify_github_secrets.py)
   # - Pass them to Terraform as TF_VAR_* environment variables
   # - Create AWS Secrets Manager secrets
   # - Deploy Lambda functions with access to secrets
   ```

---

## How Credentials Flow Through the System

### Local Development Path
```
Your Terminal
    ↓
Environment Variables: APCA_API_KEY_ID, APCA_API_SECRET_KEY
    ↓
config/credential_manager.py → getenv("APCA_API_KEY_ID")
    ↓
Phase 8 (Entry Execution) → Reads credentials, executes trades
```

**Files involved:**
- `scripts/setup_local_alpaca_credentials.sh` - Prompts & exports env vars
- `config/credential_manager.py` - Reads from environment
- `algo/orchestrator/phase8_entry_execution.py` - Uses credentials to execute trades

### AWS Production Path
```
GitHub Secrets: ALPACA_API_KEY_ID, ALPACA_API_SECRET_KEY
    ↓
GitHub Actions Workflow (deploy-all-infrastructure.yml)
    ↓
TF_VAR_alpaca_api_key_id, TF_VAR_alpaca_api_secret_key
    ↓
Terraform (terraform/modules/secrets/main.tf)
    ↓
AWS Secrets Manager: Secret "algo/alpaca"
    ↓
Lambda gets secret via credential_manager.py
    ↓
Phase 8 executes trades
```

**Files involved:**
- `.github/workflows/deploy-all-infrastructure.yml` - Reads GitHub Secrets, passes to Terraform
- `terraform/modules/secrets/main.tf` - Creates AWS Secrets Manager secret
- `terraform/modules/secrets/variables.tf` - Defines `var.alpaca_api_key`, `var.alpaca_api_secret`
- `config/credential_manager.py` - Reads from Secrets Manager in Lambda
- `algo/orchestrator/phase8_entry_execution.py` - Uses credentials

---

## Setup Instructions by Scenario

### Scenario 1: Local Development (Easiest)

**Goal:** Test trades locally without AWS or GitHub setup

```bash
# Step 1: Source the setup script
source scripts/setup_local_alpaca_credentials.sh

# It will prompt you for:
# - Alpaca API Key ID (looks like: PK_PAPER_XXXXXXXXXXXXX)
# - Alpaca Secret Key

# Step 2: Verify credentials are in environment
echo $APCA_API_KEY_ID
echo $APCA_API_SECRET_KEY

# Step 3: Run the system
python3 scripts/run_local_orchestrator.py --morning

# Step 4: Check if trades executed
# Look for Phase 8 output:
# [PHASE 8] Alpaca credentials loaded successfully
# [PHASE 8] symbol: BUY entry=... stop=... ENTERED trade_id=...
```

**Note:** Credentials only exist in this shell session. To persist them:
```bash
# Add to ~/.bashrc or ~/.zshrc
export APCA_API_KEY_ID="your-key-here"
export APCA_API_SECRET_KEY="your-secret-here"

# Then reload
source ~/.bashrc
```

### Scenario 2: AWS Production Deployment

**Goal:** Deploy to AWS Lambda for scheduled trading

#### Step 1: Generate/Get Credentials

Get from Alpaca:
1. Go to https://alpaca.markets → Dashboard
2. Settings → API Keys
3. Copy "API Key ID" (starts with `PK_PAPER_` or `PK_`)
4. Copy "Secret Key"

Generate JWT Secret:
```bash
openssl rand -base64 32
```

Get FRED API Key:
1. Go to https://fred.stlouisfed.org/user/register
2. Create account
3. Copy API key from profile

#### Step 2: Set GitHub Secrets

Go to: https://github.com/argie33/algo/settings/secrets/actions

Click "New repository secret" for each:

| Secret Name | Value |
|---|---|
| `ALPACA_API_KEY_ID` | Your Alpaca API Key ID (e.g., `PK_PAPER_XXXXX...`) |
| `ALPACA_API_SECRET_KEY` | Your Alpaca Secret Key |
| `JWT_SECRET` | Output from `openssl rand -base64 32` |
| `FRED_API_KEY` | Your FRED API key |
| `AWS_ACCOUNT_ID` | `626216981288` |
| `GITHUB_ACTIONS_ROLE_NAME` | `algo-svc-github-actions-dev` |

#### Step 3: Deploy

```bash
# Push to main (triggers GitHub Actions)
git push origin main

# Or manually trigger deployment:
gh workflow run deploy-all-infrastructure.yml -R argie33/algo

# Monitor deployment:
gh run list -R argie33/algo --workflow deploy-all-infrastructure.yml
gh run view <RUN_ID> -R argie33/algo --log
```

GitHub Actions will:
1. ✅ Verify all secrets exist (scripts/verify_github_secrets.py)
2. ✅ Pass them to Terraform as TF_VAR_* variables
3. ✅ Create AWS Secrets Manager secret `algo/alpaca`
4. ✅ Deploy Lambda functions
5. ✅ Lambda will read credentials from Secrets Manager when needed

#### Step 4: Verify Deployment

```bash
# Check Lambda received the secret
aws secretsmanager get-secret-value --secret-id algo/alpaca --region us-east-1 | jq .SecretString

# Check orchestrator ran and trades executed
aws logs tail /aws/lambda/orchestrator --follow

# Look for Phase 8 logs:
# [PHASE 8] Alpaca credentials loaded successfully
# [PHASE 8] symbol: BUY entry=... ENTERED trade_id=...
```

---

## Verification Scripts

### Check if Credentials Exist

**Local dev:**
```bash
echo "API Key: $APCA_API_KEY_ID"
echo "Secret: $APCA_API_SECRET_KEY"
```

**AWS (requires `aws` CLI):**
```bash
aws secretsmanager get-secret-value --secret-id algo/alpaca --region us-east-1 | jq .SecretString
```

**GitHub (requires `gh` CLI):**
```bash
gh secret list -R argie33/algo
python scripts/verify_github_secrets.py
```

### Test Credentials Work

```bash
# Verify credential manager can load them
python3 << 'EOF'
from config.credential_manager import get_credential_manager
try:
    creds = get_credential_manager().get_alpaca_credentials()
    if creds:
        print(f"[OK] Credentials loaded")
        print(f"  Key: {creds['key'][:15]}...")
        print(f"  Secret: (loaded, {len(creds['secret'])} chars)")
    else:
        print("[ERROR] Credentials not found")
except Exception as e:
    print(f"[ERROR] {e}")
EOF
```

---

## Troubleshooting

### "Phase 8: Alpaca credentials not available"

**Local dev:**
```bash
# Did you run the setup script?
source scripts/setup_local_alpaca_credentials.sh

# Verify they're in environment:
env | grep APCA_
```

**AWS:**
```bash
# 1. Check GitHub Secrets are set:
python scripts/verify_github_secrets.py

# 2. Check AWS Secrets Manager has the secret:
aws secretsmanager list-secrets --region us-east-1 | grep algo/alpaca

# 3. Check Lambda has permission to read it:
aws iam get-role-policy --role-name algo-orchestrator-dev \
  --policy-name orchestrator-secrets-access
```

### "Invalid credentials" from Alpaca API

**Check format:**
- API Key should start with `PK_PAPER_` (paper trading) or `PK_` (live)
- Secret key should be 40+ characters
- No extra whitespace or quotes

**Verify with Alpaca:**
```bash
# Test API connection
curl -H "Authorization: Bearer $APCA_API_KEY_ID:$APCA_API_SECRET_KEY" \
  https://paper-api.alpaca.markets/v2/account
# Should return account info, not 401 Unauthorized
```

### "Credentials rotated, Lambda not getting new values"

AWS Secrets Manager caches values. To force refresh:
1. Update GitHub Secret
2. Trigger Terraform deployment:
   ```bash
   gh workflow run deploy-all-infrastructure.yml -R argie33/algo
   ```
3. Terraform updates the Secrets Manager secret
4. Lambda reads fresh values on next execution

---

## Security Notes

- **Never commit credentials to git** - Use environment variables or GitHub Secrets only
- **Rotate credentials regularly** - Update GitHub Secrets and re-deploy
- **Alpaca paper trading is safe** - Uses paper account, no real money
- **AWS Secrets Manager is encrypted** - Credentials encrypted at rest in AWS
- **GitHub Secrets are masked in logs** - Never displayed in GitHub Actions output

---

## Migration from Old Setup

If you previously set credentials in `.env` or hardcoded:

1. **Delete old credentials:**
   ```bash
   rm .env
   git checkout -- any-file-with-hardcoded-creds.py
   ```

2. **Use new setup:**
   - Local: `source scripts/setup_local_alpaca_credentials.sh`
   - AWS: Set GitHub Secrets

3. **Commit the cleanup:**
   ```bash
   git add -A
   git commit -m "fix: Remove hardcoded credentials, use credential manager"
   ```

---

## Reference Files

- `scripts/setup_local_alpaca_credentials.sh` - Interactive credential setup for local dev
- `scripts/verify_github_secrets.py` - Check GitHub Secrets are configured
- `config/credential_manager.py` - Reads credentials from environment or AWS Secrets Manager
- `terraform/terraform.tfvars.example` - Template for Terraform variables (for local Terraform runs)
- `terraform/modules/secrets/main.tf` - Creates AWS Secrets Manager secrets
- `.github/workflows/deploy-all-infrastructure.yml` - GitHub Actions workflow that passes GitHub Secrets to Terraform
- `algo/orchestrator/phase8_entry_execution.py` - Uses credentials to execute trades (now fails loud if missing)
