# Local Secrets Management - Best Practices

This guide explains how to manage credentials locally without committing them to git.

## Overview

- **Local Development**: Use one of the methods below
- **CI/CD (GitHub)**: Secrets stored in GitHub Actions Secrets
- **Production (AWS)**: Secrets stored in AWS Secrets Manager

## Option 1: Docker Compose (Recommended for Local Dev)

Use dummy credentials in Docker Compose - no real credentials needed locally.

```bash
# Start with docker-compose
docker-compose up -d

# Database: postgres://stocks:yourpassword@localhost:5432/stocks
# No AWS credentials needed - use Docker network
```

**Pros:**
- No credentials stored on disk
- Matches production environment
- Easy to reset
- Perfect for local development

**Cons:**
- Requires Docker

## Option 2: AWS Secrets Manager (Cloud-like Experience Locally)

If you want to test production-like secrets management locally.

```bash
# 1. Configure AWS CLI
aws configure
# Enter your AWS Access Key ID and Secret Access Key

# 2. Create a secret in AWS Secrets Manager
aws secretsmanager create-secret \
  --name local/dev/db-credentials \
  --secret-string '{"username":"stocks","password":"your-password"}'

# 3. Your code automatically fetches from AWS Secrets Manager
# No .env.local needed
```

**Pros:**
- Matches production setup exactly
- Credentials never touch local disk
- Easy to rotate credentials
- Audit trail in AWS

**Cons:**
- Requires AWS account and CLI configuration
- Network call on each app startup

## Option 3: 1Password, Bitwarden, or LastPass CLI

Use a password manager CLI to inject secrets at runtime.

```bash
# 1. Install 1Password CLI
brew install 1password-cli

# 2. Sign in
op signin my.1password.com user@example.com

# 3. Load secret and start app
op run --env-file <(op item get "Dev DB Password" --format json | jq -r '.fields[] | "\(.label)=\(.value)"') -- npm start
```

**Pros:**
- Credentials encrypted in password manager
- No local files
- Credentials rotate automatically

**Cons:**
- Requires password manager account
- CLI syntax can be complex

## Option 4: Local .env.local File (Simple but Manual)

If you use `.env.local` locally:

```bash
# 1. Copy template
cp .env.local.example .env.local

# 2. Edit with your local credentials
# .env.local is already in .gitignore - safe to commit
nano .env.local

# 3. Never commit this file
git status  # Should show .env.local as untracked
```

**Pros:**
- Simplest setup
- No external dependencies

**Cons:**
- Credentials on disk (even if gitignored)
- Risk of accidental commit
- Must manage rotation manually

## Recommended Setup for Your Project

### For Local Development:
**Use Docker Compose + dummy credentials**

```bash
docker-compose up -d
# Everything works with mock data - no real credentials needed
```

### For CI/CD (GitHub Actions):
**Use GitHub Secrets** (already configured)

```yaml
env:
  DB_PASSWORD: ${{ secrets.DB_PASSWORD }}
  ALPACA_API_KEY_ID: ${{ secrets.ALPACA_API_KEY_ID }}
```

These automatically sync to AWS Secrets Manager during deployment.

### For Production (AWS):
**Use AWS Secrets Manager** (built-in via Terraform)

```javascript
// Code automatically reads from AWS Secrets Manager
// No credentials in environment variables
```

## Setting Up Git Security

### Remove .env.local from Git History

```bash
# Install BFG Repo-Cleaner
brew install bfg

# Remove .env.local from all history
bfg --delete-files .env.local

# Force push (CAUTION - rewrites history)
git reflog expire --expire=now --all && git gc --prune=now --aggressive
git push origin --force
```

### Verify Cleanup

```bash
git log --all --full-history -- .env.local
# Should show nothing if cleanup was successful

git ls-files | grep .env
# Should only show .env.example files, not .env.local
```

## Credential Rotation Policy

### For Local Development:
- Change whenever you remember
- Reset to dummy values when switching between projects

### For Production:
- Rotate every 90 days
- Rotate immediately if exposed
- Use AWS Secrets Manager rotation feature

## Checking for Accidentally Committed Secrets

```bash
# Install secret scanning
brew install detect-secrets

# Scan for secrets
detect-secrets scan --baseline .secrets.baseline

# Pre-commit hook (auto-run before commit)
detect-secrets install --force --hook-type commit
```

## Files That Should NEVER Contain Real Credentials

- `.env.local` ✅ (gitignored but never commit)
- `.env` ✅ (gitignored but never commit)
- `.env.example` ✅ (template only, safe to commit)
- `config.json` ✗ (commits will leak it)
- `secrets.js` ✗ (commits will leak it)
- Any file not in `.gitignore` ✗ (high risk)

## Summary

| Method | Local | CI/CD | Production | Risk | Setup |
|--------|-------|-------|------------|------|-------|
| Docker Compose | ✅ | ❌ | ❌ | Low | Easy |
| AWS Secrets Manager | ✅ | ✅ | ✅ | Very Low | Medium |
| Password Manager CLI | ✅ | ❌ | ❌ | Low | Hard |
| .env.local (gitignored) | ✅ | ❌ | ❌ | Medium | Easy |
| .env.local (committed) | ✅ | ✅ | ✅ | **CRITICAL** | Easy but DANGEROUS |

**Recommendation**: Use **Docker Compose locally** + **GitHub Secrets for CI/CD** + **AWS Secrets Manager for production**.

This approach:
- ✅ Never commits credentials to git
- ✅ Works for local, staging, and production
- ✅ Follows industry best practices
- ✅ Easy to rotate credentials
- ✅ Audit trail for security
