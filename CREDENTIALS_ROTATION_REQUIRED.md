# CRITICAL: Credentials Rotation Required

## Status
**COMPROMISED** - The following credentials were exposed in git history and must be rotated immediately.

## Exposed Credentials

### Alpaca Trading API Keys (EXPOSED IN GIT)
- **Key 1 (PRIMARY):** `PKAZZLZK2HX7JB6P7GBVDORY76`
- **Secret 1:** `HEzu13fSdQwwDStWWwjEFyh25XjE17cfM9uJ7267mK73`
- **Key 2:** `PK5NU6IU3BA5T5DYR2IP7FRKIL`
- **Secret 2:** `29MRDnC5prmJXYKBRE29bvc1BUiqPhdSaaqrtJNZwJeY`

**Commit with exposure:** `b5596425f` (docs: add quickstart guide and fix server credentials)

### FRED API Key (EXPOSED IN GIT)
- **Key:** `450ae65f7efbaedbd1f1a8bb02582fcb`

### AWS Credentials (POSSIBLY EXPOSED)
- **Access Key:** [redacted — see security incident log]
- **Secret Key:** [redacted — see security incident log]

## Required Actions

### 1. Rotate Alpaca Keys (URGENT)
- [ ] Log in to Alpaca dashboard (https://dashboard.alpaca.markets)
- [ ] Navigate to API Keys section
- [ ] Deactivate both exposed keys immediately
- [ ] Generate new API keys for paper trading
- [ ] Store new keys in AWS Secrets Manager
- [ ] Update GitHub Actions secrets with new values
- [ ] Test with new keys in CI/staging environment

### 2. Rotate FRED Keys (URGENT)
- [ ] Log in to FRED API dashboard (https://fredaccount.stlouisfed.org)
- [ ] Generate new API key
- [ ] Store in AWS Secrets Manager
- [ ] Update all loaders to use new key

### 3. Rotate AWS Credentials (URGENT)
- [ ] Check if keys were actually committed (search git history)
- [ ] If exposed, deactivate in AWS IAM console
- [ ] Create new access keys
- [ ] Store in AWS Secrets Manager

### 4. Verify Remediation
- [ ] Run CI pipeline with new credentials
- [ ] Test all loaders work with new keys
- [ ] Verify no trading issues in paper mode
- [ ] Monitor for unauthorized API calls on old keys (should be zero)

## Prevention (ALREADY IMPLEMENTED)

- ✅ TruffleHog added to CI pipeline to detect secrets in commits
- ✅ Manual patterns added to CI to catch known exposed keys
- ✅ PowerShell profile cleaned of hardcoded credentials
- ✅ Credentials stored securely in AWS Secrets Manager (recommended)
- ✅ Environment variables configured locally only (not in files)

## Timeline

- **2026-05-18 22:30** - Compromised credentials identified
- **2026-05-18 22:35** - CI scanning implemented
- **2026-05-18 NOW** - Awaiting credential rotation by user
