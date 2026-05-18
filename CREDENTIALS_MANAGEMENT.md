# Credentials Management - Complete Setup

## Overview

Credentials are managed via **Infrastructure as Code (Terraform)** and synced securely to local development via **GitHub Secrets**.

- **Local Dev:** PowerShell profile (persistent, not in git)
- **Production:** AWS Secrets Manager (encrypted, team-shareable)
- **CI/CD:** GitHub Actions with OIDC (no hardcoded keys)

---

## Architecture

```
┌─────────────────┐
│  Terraform IaC  │  (terraform/modules/iam/main.tf)
│  ├─ Developer   │  ├─ aws_iam_user.developer
│  │   IAM User   │  ├─ aws_access_key.developer
│  │               │  └─ ReadOnly + Secrets access
│  └─ Access Keys │
└────────┬────────┘
         │
         ├─→ [GitHub Actions Workflow] ──(OIDC)──→ AWS
         │    sync-credentials.yml
         │
         ├─→ GitHub Secrets (encrypted)
         │    ├─ AWS_DEVELOPER_ACCESS_KEY_ID
         │    └─ AWS_DEVELOPER_SECRET_ACCESS_KEY
         │
         └─→ Local PowerShell Profile
              (sync-credentials-local.ps1)
              └─ $env:AWS_ACCESS_KEY_ID (cached locally)
```

---

## Current Setup

### ✅ Local Credentials (Already Set)

Your PowerShell profile (`$PROFILE`) now contains:

```powershell
# Database
$env:DB_HOST = "localhost"
$env:DB_PORT = "5432"
$env:DB_USER = "stocks"
$env:DB_NAME = "stocks"
$env:DB_PASSWORD = "bed0elAn"

# Alpaca Trading
$env:ALPACA_API_KEY = "PK5NU6IU3BA5T5DYR2IP7FRKIL"
$env:ALPACA_API_SECRET = "29MRDnC5prmJXYKBRE29bvc1BUiqPhdSaaqrtJNZwJeY"
$env:APCA_API_BASE_URL = "https://paper-api.alpaca.markets"

# AWS (commented - see below)
# $env:AWS_ACCESS_KEY_ID = ???
# $env:AWS_SECRET_ACCESS_KEY = ???
```

### ⏳ AWS Credentials (Need Setup)

1. **Get from Terraform Outputs:**
   ```bash
   cd terraform
   terraform output developer_access_key_id      # Access Key ID
   terraform output developer_secret_access_key  # Secret Access Key
   ```

2. **OR Get from AWS Console:**
   - Go to AWS Console → IAM → Users → `algo-developer`
   - View access keys (or create new ones)
   - Copy Access Key ID and Secret Access Key

3. **Add to GitHub Secrets:**
   - GitHub Repo → Settings → Secrets and variables → Actions
   - Create:
     - `AWS_DEVELOPER_ACCESS_KEY_ID` = `<value>`
     - `AWS_DEVELOPER_SECRET_ACCESS_KEY` = `<value>`

4. **Uncomment in PowerShell Profile:**
   ```powershell
   $env:AWS_ACCESS_KEY_ID = "AKIA..."
   $env:AWS_SECRET_ACCESS_KEY = "..."
   $env:AWS_REGION = "us-east-1"
   ```

5. **Restart PowerShell** and verify:
   ```powershell
   $env:AWS_ACCESS_KEY_ID
   ```

---

## Workflows

### Workflow 1: Local Development

**Setup (One-time):**
1. Restart PowerShell (loads profile with DB + Alpaca creds)
2. Add AWS credentials (see above)

**Daily Use:**
```bash
python3 algo/algo_orchestrator.py --dry-run
python3 run-all-loaders.py
```

Credentials are loaded from PowerShell profile automatically.

### Workflow 2: Sync Credentials from IaC (Optional)

If you want GitHub Actions to automatically keep credentials in sync:

1. **Trigger the workflow manually:**
   - GitHub Repo → Actions → "Sync Credentials from IaC to Secrets"
   - Click "Run workflow"

2. **What it does:**
   - Uses OIDC to assume deployer role (no hardcoded keys!)
   - Fetches credentials from Terraform state
   - Displays them (you manually add to GitHub Secrets)

3. **To automate further:**
   - Workflow could use GitHub API to update secrets
   - Requires GitHub token with admin permissions
   - (Optional enhancement)

### Workflow 3: Production Deployment

GitHub Actions uses OIDC:
- No hardcoded AWS keys in repo
- Each deployment assumes role with temporary credentials
- Deploys to AWS with least-privilege permissions

---

## File Reference

| File | Purpose | Managed By |
|------|---------|-----------|
| `terraform/modules/iam/main.tf` | Defines developer IAM user + access keys | IaC (Terraform) |
| `.github/workflows/sync-credentials.yml` | Fetches creds from Terraform, syncs to Secrets | Git |
| `sync-credentials-local.ps1` | Fetches from GitHub Secrets, updates PowerShell profile | Manual/Local |
| `$PROFILE` | Your local credentials (persistent, not in git) | Manual/Local |

---

## Security Notes

✅ **What's Protected:**
- Credentials in PowerShell profile: local-only, never in git
- Credentials in GitHub Secrets: encrypted at rest
- IAM access keys: least-privilege reader role
- AWS credentials: only for dev, never for production
- Production: AWS Secrets Manager + Lambda/ECS roles (no keys needed)

❌ **Never Commit:**
- `.env*` files (forbidden by git hooks)
- AWS access keys (GitHub Secrets instead)
- Database passwords (PowerShell profile, not git)
- Alpaca secrets (PowerShell profile, not git)

✅ **Always Use:**
- PowerShell profile for local dev (persistent, safe)
- AWS Secrets Manager for production
- OIDC for GitHub Actions (no hardcoded keys)

---

## Troubleshooting

**"DB_PASSWORD not set"**
- PowerShell profile not loaded
- Restart PowerShell
- Verify: `$env:DB_PASSWORD`

**"AWS credentials not available"**
- Uncomment AWS lines in PowerShell profile
- Add values from GitHub Secrets or Terraform output
- Restart PowerShell

**"Cannot access Terraform state"**
- Need AWS credentials to read remote state
- Use deployer role (OIDC in GitHub Actions)
- Or AWS console to fetch developer credentials

**"GitHub CLI not found"**
- Install from: https://github.com/cli/cli
- Run: `gh auth login`

---

## Next Steps

1. ✅ Local credentials set (DB, Alpaca)
2. ⏳ Get AWS developer credentials (Terraform or AWS Console)
3. ⏳ Add to GitHub Secrets (optional, for automation)
4. ⏳ Uncomment AWS lines in PowerShell profile
5. ⏳ Restart PowerShell
6. ✅ Run: `python3 algo/algo_orchestrator.py --dry-run`

---

## Questions?

- **Local setup:** See PowerShell profile or run `sync-credentials-local.ps1`
- **Terraform:** Check `terraform/modules/iam/main.tf`
- **GitHub Secrets:** Repo Settings → Secrets and variables
- **AWS Console:** IAM → Users → algo-developer
