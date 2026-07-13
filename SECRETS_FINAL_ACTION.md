# Secrets Fix - Final Action Items
**Status:** Cleanup in progress  
**Date:** 2026-07-12  
**Completed:** ✅ Duplicate cleanup done  
**Remaining:** ⏳ AWS key rotation + DB password rotation

---

## What's Done ✅

- [x] Deleted old `ALPACA_API_KEY` (2026-06-08)
- [x] Deleted old `ALPACA_SECRET_KEY` (2026-06-08)
- [x] Verified new Alpaca credentials present (2026-07-08)
- [x] Ran system diagnostic (database + API endpoints working)
- [x] GitHub Secrets reduced from 27 → 25 (cleanup completed)

**Result:** You now have clean, organized secrets with no duplicates.

---

## What's Remaining ⏳

### URGENT: Database Password Rotation NOT Enabled ⚠️

**Current state:**
```
RotationEnabled: None
RotationRules: None
LastRotatedDate: None
```

**What this means:**
- Your database password in AWS Secrets Manager is NOT auto-rotating
- If compromised, it stays compromised until manually rotated
- Production databases should always have rotation enabled

**Fix (Choose One):**

#### Option A: Enable via AWS CLI (1 min)
```bash
aws secretsmanager rotate-secret \
  --secret-id algo/database \
  --rotation-rules '{"AutomaticallyAfterDays":30}' \
  --region us-east-1 \
  --query 'ARN'

# Expected output: arn:aws:secretsmanager:us-east-1:626216981288:secret:algo/database-XXXXX
```

**Then verify:**
```bash
aws secretsmanager describe-secret \
  --secret-id algo/database \
  --region us-east-1 \
  --query 'RotationRules'

# Should show: {"AutomaticallyAfterDays": 30}
```

#### Option B: Do It in AWS Console (5 min)
1. Go to https://console.aws.amazon.com/secretsmanager
2. Find `algo/database`
3. Click "Rotation configuration"
4. Click "Enable rotation"
5. Set to: "Rotate immediately" + "30 days"
6. Save

---

### RECOMMENDED: Rotate AWS Access Keys ⚠️

**Current state:**
```
AWS_ACCESS_KEY_ID         2026-05-17  ← 2 months old
AWS_SECRET_ACCESS_KEY     2026-05-17  ← 2 months old
```

**Why rotate:**
- AWS best practice: rotate every 90 days
- These are old and should be fresh
- You're using OIDC (better) but these legacy keys might still have permissions

**Steps (10 min):**

1. **Generate new key in AWS Console:**
   - Go to https://console.aws.amazon.com/iam/home#/security_credentials
   - Click Users → algo-developer
   - Click "Security credentials" tab
   - Click "Create access key"
   - Choose "Other" → Next
   - **SAVE:** Access key ID and Secret access key (won't see secret again)

2. **Update GitHub Secrets:**
   ```bash
   gh secret set AWS_ACCESS_KEY_ID \
     --body "YOUR_NEW_KEY_ID" \
     --repo argie33/algo

   gh secret set AWS_SECRET_ACCESS_KEY \
     --body "YOUR_NEW_SECRET" \
     --repo argie33/algo

   # Verify
   gh secret list --repo argie33/algo | grep AWS_ACCESS_KEY
   # Should show today's date
   ```

3. **Test in GitHub Actions:**
   - Go to GitHub → Actions
   - Click any workflow (e.g., "Deploy Orchestrator Lambda")
   - Click "Run workflow"
   - Wait 2-3 min for it to complete
   - If it passes ✅: keys are good
   - If it fails ❌: new key missing permissions → restore old keys and investigate

4. **Delete old key (AFTER test passes):**
   - Go back to AWS Console → IAM → algo-developer → Security credentials
   - Find OLD key (created 2026-05-17)
   - Click "Delete" → Confirm
   - Done!

---

## Final Checklist

### Do This (Order Matters):

#### STEP 1: Enable Database Password Rotation (1 min)
```bash
aws secretsmanager rotate-secret \
  --secret-id algo/database \
  --rotation-rules '{"AutomaticallyAfterDays":30}' \
  --region us-east-1
```

OR do it in AWS Console (see above).

#### STEP 2: Rotate AWS Access Keys (10 min)
1. AWS Console → Create new access key
2. GitHub Secrets → Update both AWS_* secrets
3. GitHub Actions → Run any workflow to test
4. AWS Console → Delete old key (after test passes)

#### STEP 3: Verify Everything Works (5 min)
```bash
# Test credential loading
python3 -c "
from config.credential_manager import get_credential_manager
mgr = get_credential_manager()

try:
    alpaca = mgr.get_alpaca_credentials()
    print('✓ Alpaca credentials loaded')
except Exception as e:
    print(f'✗ Alpaca error: {e}')

try:
    db = mgr.get_db_credentials()
    print('✓ Database credentials loaded')
except Exception as e:
    print(f'✗ Database error: {e}')
"

# Run system diagnostic
python3 scripts/diagnose_system.py
```

#### STEP 4: Document Completion
```bash
git add SECRETS_CLEANUP_QUICK.md SECRETS_FINAL_ACTION.md
git commit -m "chore: Secrets cleanup complete - removed duplicates, enabled DB rotation, rotated AWS keys"
```

---

## Current Secret Status Dashboard

| Secret Category | Status | Last Updated | Action |
|---|---|---|---|
| **Alpaca Credentials** | ✅ OK | 2026-07-08 | None needed |
| **JWT Secret** | ✅ OK | 2026-06-25 | None needed |
| **FRED API Key** | ✅ OK | 2026-06-25 | None needed |
| **AWS Account ID** | ✅ OK | 2026-05-29 | None needed |
| **AWS Role ARN** | ✅ OK | 2026-05-29 | None needed |
| **AWS Access Keys** | ⚠️ OLD | 2026-05-17 | **ROTATE** |
| **DB Password** | ✅ OK* | 2026-05-10 | **Enable rotation** |
| **Duplicates** | ✅ CLEANED | 2026-07-12 | Done ✓ |

\* Password is OK but rotation is not enabled — fix this first

---

## Why This Matters

### Security
- Old AWS keys = higher risk if compromised
- No DB password rotation = no automatic recovery if breached
- Clean secrets = less to audit, easier to manage

### Compliance
- Secrets rotation every 90 days = AWS security best practice
- Database credential rotation every 30 days = production standard
- Clean inventory = easy to audit for compliance

### Operational
- Fresh credentials = no unexpected auth failures
- Clear documentation = easier for next person to maintain
- Rotation enabled = automatic recovery without manual intervention

---

## Success Criteria

After completing all steps, you'll have:

- ✅ No duplicate secrets
- ✅ AWS keys fresh (< 30 days old)
- ✅ Database password auto-rotation enabled
- ✅ All diagnostics passing
- ✅ GitHub Actions deploying successfully
- ✅ Clean, documented state

---

## Quick Reference

**Do this first:**
```bash
# Enable DB password rotation
aws secretsmanager rotate-secret \
  --secret-id algo/database \
  --rotation-rules '{"AutomaticallyAfterDays":30}' \
  --region us-east-1

# Then go to AWS Console to rotate access keys
# (2026-05-17 keys need refresh)
```

**Questions?** Check SECRETS_CLEANUP_QUICK.md for detailed steps

---

**Status:** Ready for your action  
**Time to complete:** ~20 minutes  
**Next update:** After you complete the steps above
