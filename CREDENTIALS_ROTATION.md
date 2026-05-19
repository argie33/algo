# Credentials Rotation - URGENT

## Issue
Alpaca and FRED API keys were exposed in git history (commit b5596425f, deleted in 45af219f3).

**Keys Compromised:**
- Alpaca Paper Trading API Key ID: `PKAZZLZK2HX7JB6P7GBVDORY76`
- Alpaca Paper Trading Secret Key: `HEzu13fSdQwwDStWWwjEFyh25XjE17cfM9uJ7267mK73`
- FRED API Key: `450ae65f7efbaedbd1f1a8bb02582fcb`

## Immediate Actions Required

### 1. Rotate Alpaca Keys (Paper Trading Account)
1. Log in to [Alpaca Dashboard](https://app.alpaca.markets/login)
2. Go to **Account → Settings → API Keys**
3. **Revoke** existing paper trading keys
4. Generate **new API Key ID** and **Secret Key**
5. Update locally:
   ```powershell
   # In PowerShell profile or terminal
   $env:APCA_API_KEY_ID = "NEW_KEY_ID"
   $env:APCA_API_SECRET_KEY = "NEW_SECRET_KEY"
   ```
6. Update in **AWS Secrets Manager** (if Lambda uses it):
   ```bash
   aws secretsmanager update-secret --secret-id algo-secrets \
     --secret-string '{"APCA_API_KEY_ID":"NEW_KEY_ID","APCA_API_SECRET_KEY":"NEW_SECRET_KEY"}'
   ```

### 2. Rotate FRED API Key
1. Log in to [FRED](https://fred.stlouisfed.org/)
2. Go to **API → My API Keys**
3. **Delete** the compromised key: `450ae65f7efbaedbd1f1a8bb02582fcb`
4. Generate **new API key**
5. Update locally:
   ```powershell
   $env:FRED_API_KEY = "NEW_FRED_KEY"
   ```
6. Update in **AWS Secrets Manager**:
   ```bash
   aws secretsmanager update-secret --secret-id algo-secrets \
     --secret-string '{"FRED_API_KEY":"NEW_FRED_KEY"}'
   ```

### 3. Verify in Git History (Optional)
The keys are still technically visible in git history (before the rewrite), but they are no longer committed to main branch. If this was a public repository, consider:
- Using `git-filter-branch` or `bfg-repo-cleaner` to rewrite history
- Pushing a force-update to main

**Current status:** Main branch is clean, keys deleted in commit 45af219f3.

## Prevention

Enforce via pre-commit hook (already in CLAUDE.md):
- ✓ No .env files committed (Rule 7)
- ✓ No hardcoded secrets (Rule 7)
- ✓ Use AWS Secrets Manager for production
- ✓ Use local environment variables for dev (via PowerShell profile, not .env files)

## Timeline
- **Immediate:** Generate new keys (5 min)
- **Same session:** Update AWS Secrets Manager (2 min)
- **Verify:** Test orchestrator with new keys (5 min)
