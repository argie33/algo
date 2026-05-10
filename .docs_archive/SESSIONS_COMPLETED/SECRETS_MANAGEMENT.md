# Secrets Management System

This project uses a local vault system to manage all secrets securely while preventing accidental commits of sensitive data.

## Architecture

```
Local Development          GitHub Actions
┌─────────────────┐       ┌──────────────────────┐
│  .env.vault     │──────▶│ Repository Secrets   │
│ (local file)    │       │ (Settings→Secrets)   │
└─────────────────┘       └──────────────────────┘
       │                           │
       ├─ NEVER committed          └─ Used by workflows
       ├─ In .gitignore
       └─ Synced via sync-secrets.sh
```

## Setup Instructions

### Step 1: Create Local Vault

```bash
cp .env.vault.template .env.vault
```

### Step 2: Add Your Secrets

Edit `.env.vault` and fill in actual values for:

- `AWS_ACCESS_KEY_ID` — AWS IAM user access key
- `AWS_SECRET_ACCESS_KEY` — AWS IAM user secret key  
- `AWS_ACCOUNT_ID` — Your AWS account ID (12 digits)
- `RDS_PASSWORD` — PostgreSQL master password
- `ALPACA_API_KEY_ID` — From app.alpaca.markets/paper/api-keys
- `ALPACA_API_SECRET_KEY` — From app.alpaca.markets/paper/api-keys
- `ALERT_EMAIL_ADDRESS` — Email for CloudWatch alerts
- `API_GATEWAY_URL` — (leave empty initially, fill after first deployment)

### Step 3: Sync to GitHub

```bash
chmod +x scripts/sync-secrets.sh
./scripts/sync-secrets.sh
```

This pushes all secrets from `.env.vault` to GitHub Actions repository secrets.

### Step 4: Verify

Check GitHub: https://github.com/argie33/algo/settings/secrets/actions

All 8 secrets should be listed there.

## Usage

### For Local Development

Source the vault file in your shell:

```bash
set -a
source .env.vault
set +a
```

Then run commands that need secrets:

```bash
# Example: Manual RDS access
psql -h $RDS_ENDPOINT -U postgres -p 5432
# (enter RDS_PASSWORD when prompted)
```

### For GitHub Actions

Secrets are automatically available in workflows via `${{ secrets.SECRET_NAME }}`.

No additional setup needed - workflows just use them directly.

## Security Best Practices

### DO ✅
- Keep `.env.vault` in `.gitignore`
- Only commit `.env.vault.template` (no actual values)
- Store `.env.vault` securely locally (encrypted disk, secure folder)
- Rotate secrets regularly (especially AWS keys, RDS passwords)
- Use minimal IAM permissions for GitHub Actions user
- Keep `.env.vault` updated when secrets change

### DON'T ❌
- Never commit `.env.vault` to Git
- Never paste secrets in Slack, email, or logs
- Never hardcode secrets in code
- Never share `.env.vault` via email or chat
- Never use same secrets across environments (dev/staging/prod)
- Never log secret values in GitHub Actions output

## Troubleshooting

### Sync fails with "secret not found"

```bash
# Install gh CLI if needed
brew install gh  # macOS
# or visit https://github.com/cli/cli

# Authenticate
gh auth login
```

### Sync says "already exists" for all secrets

This is normal - secrets already set in GitHub won't be overwritten without explicit deletion.

To update a secret:

```bash
# Update single secret
gh secret set AWS_ACCOUNT_ID --body "123456789012" --repo argie33/algo

# List all secrets
gh secret list --repo argie33/algo
```

### `.env.vault` file is large / slow to load

The vault file should only contain secrets. Keep it small and simple. Don't add comments or extra lines.

## Workflow

Normal development workflow:

1. **New secret needed** → Add to `.env.vault.template` and `.env.vault`
2. **Secret changes** → Update `.env.vault`
3. **Ready for production** → Run `./scripts/sync-secrets.sh`
4. **Commit only template** → Never commit `.env.vault`

Example:

```bash
# Edit .env.vault
nano .env.vault

# Sync to GitHub
./scripts/sync-secrets.sh

# Commit only template changes (if any)
git add .env.vault.template
git commit -m "docs: Update secrets documentation"
```

## Related Files

- `.env.vault` — Local secrets (NOT in Git, NOT shared)
- `.env.vault.template` — Template showing required secrets (IN Git, safe to share)
- `.gitignore` — Prevents .env.vault from being committed
- `scripts/sync-secrets.sh` — Syncs local vault to GitHub
- `GITHUB_SECRETS_SETUP.md` — Setup guide for GitHub secrets
- `.github/workflows/deploy-all-infrastructure.yml` — Uses these secrets

## Questions?

All secrets usage must follow this pattern to maintain security.
