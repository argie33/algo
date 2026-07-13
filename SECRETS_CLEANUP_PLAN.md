# Secrets Cleanup & Fix Plan
**Status:** Ready to Execute  
**Complexity:** Medium (3 phases, ~30 min total)  
**Impact:** Security + cleanup only (no service changes)

---

## Overview

| Phase | Task | Time | User Action |
|-------|------|------|---|
| **1** | Audit current state | 5 min | Run diagnostics |
| **2** | Rotate AWS keys | 10 min | AWS Console + GitHub CLI |
| **3** | Clean duplicates | 5 min | GitHub CLI commands |
| **4** | Verify Secrets Manager | 5 min | Run validation |
| **5** | Test end-to-end | 5 min | Run system diagnostic |

---

## Phase 1: Audit Current State

### Step 1.1 - Check GitHub Secrets
**What:** Verify all 27 secrets are there  
**Command:**
```bash
gh secret list --repo argie33/algo | wc -l
# Should show: 27
```

**What:** Check which ones are critical
```bash
gh secret list --repo argie33/algo | grep -E "ALPACA|JWT|FRED|AWS_ACCOUNT|DB_"
```

**Expected output:**
```
ALPACA_API_KEY_ID          2026-07-08
ALPACA_API_SECRET_KEY      2026-07-08
ALPACA_API_KEY             2026-06-08  ← OLD (delete)
ALPACA_SECRET_KEY          2026-06-08  ← OLD (delete)
JWT_SECRET                 2026-06-25
FRED_API_KEY               2026-06-25
AWS_ACCESS_KEY_ID          2026-05-17  ← ROTATE (>60 days)
AWS_SECRET_ACCESS_KEY      2026-05-17  ← ROTATE (>60 days)
AWS_ACCOUNT_ID             2026-05-29
DB_PASSWORD                2026-05-10
DB_USER                    2026-05-01
DB_NAME                    2026-05-01
```

---

## Phase 2: Rotate AWS Keys ⚠️ CRITICAL SECURITY

### Step 2.1 - Generate New AWS Access Keys
**Where:** AWS IAM Console  
**URL:** https://console.aws.amazon.com/iam/home#/security_credentials

**Steps:**
1. Go to AWS Console → IAM → Users → algo-developer
2. Click "Security credentials" tab
3. Scroll to "Access keys"
4. Click "Create access key"
5. Choose "Other" → Next
6. **Copy the values:**
   - ✂️ Copy: **Access key ID** (NEW_KEY_ID)
   - ✂️ Copy: **Secret access key** (NEW_SECRET)
   - ⚠️ **SAVE THESE** — you won't see the secret again

### Step 2.2 - Update GitHub Secrets (Local Terminal)
**Command:**
```bash
# Set new AWS keys
gh secret set AWS_ACCESS_KEY_ID \
  --body "YOUR_NEW_KEY_ID" \
  --repo argie33/algo

gh secret set AWS_SECRET_ACCESS_KEY \
  --body "YOUR_NEW_SECRET" \
  --repo argie33/algo

# Verify they were set
gh secret list --repo argie33/algo | grep AWS_
```

**Expected output:**
```
AWS_ACCESS_KEY_ID          2026-07-12  ← TODAY
AWS_SECRET_ACCESS_KEY      2026-07-12  ← TODAY
AWS_ACCOUNT_ID             2026-05-29
AWS_GITHUB_ACTIONS_ROLE_ARN 2026-05-29
AWS_REGION                 2026-05-01
```

### Step 2.3 - Test New Keys Work
**Where:** GitHub Actions  
**What to do:**
1. Go to GitHub → Actions
2. Click any deploy workflow (e.g., "Deploy Orchestrator Lambda")
3. Click "Run workflow" → "Run workflow"
4. Wait 2-3 min
5. Check if it passes ✅

**If it fails:** The new keys don't have the right permissions. Restore old keys and investigate.

### Step 2.4 - Delete Old AWS Keys
**ONLY after GitHub Actions test passed!**  
**Where:** AWS IAM Console  
**Steps:**
1. Go to AWS Console → IAM → Users → algo-developer → Security credentials
2. Scroll to "Access keys"
3. Find the OLD key (created in May 2026)
4. Click "Delete" → Confirm

**Verify deletion:**
```bash
# Should only show the NEW key (from Step 2.1)
aws iam list-access-keys --user-name algo-developer
# (You may get access denied; that's OK if the old key is gone)
```

---

## Phase 3: Clean Up Duplicate Secrets

### Step 3.1 - Delete Old Alpaca Secrets
**Why:** You have 2 old secrets from June that are superseded by the fresh ones from July  
**Commands:**
```bash
# Delete old duplicate secrets
gh secret delete ALPACA_API_KEY --repo argie33/algo
gh secret delete ALPACA_SECRET_KEY --repo argie33/algo

# Verify they're gone
gh secret list --repo argie33/algo | grep ALPACA
```

**Expected output (only these 2):**
```
ALPACA_API_KEY_ID          2026-07-08
ALPACA_API_SECRET_KEY      2026-07-08
```

### Step 3.2 - Check Workflows Use Correct Secret Names
**Why:** Some workflows might reference the old names  
**Check:**
```bash
grep -r "ALPACA_API_KEY\|ALPACA_SECRET_KEY" .github/workflows/ | grep -v "ALPACA_API_KEY_ID"
```

**If it finds matches:** Edit those workflows to use `ALPACA_API_KEY_ID` instead

---

## Phase 4: Verify AWS Secrets Manager

### Step 4.1 - List Secrets
**Command:**
```bash
aws secretsmanager list-secrets \
  --region us-east-1 \
  --query 'SecretList[?starts_with(Name, `algo/`)].{Name:Name,Updated:LastChangedDate,Accessed:LastAccessedDate}' \
  --output table
```

**Expected output:**
```
┌─────────────────────┬──────────────────┬──────────────────┐
│ Name                │ Updated          │ Accessed         │
├─────────────────────┼──────────────────┼──────────────────┤
│ algo/alpaca         │ 2026-07-XX       │ 2026-07-XX       │
│ algo/database       │ 2026-XX-XX       │ 2026-07-12       │
│ algo/fred           │ 2026-XX-XX       │ 2026-07-XX       │
│ algo/jwt            │ 2026-XX-XX       │ 2026-07-XX       │
│ algo/orchestrator   │ 2026-XX-XX       │ 2026-07-XX       │
└─────────────────────┴──────────────────┴──────────────────┘
```

### Step 4.2 - Verify Database Secret Rotation
**Command:**
```bash
aws secretsmanager describe-secret \
  --secret-id algo/database \
  --region us-east-1 \
  --query '{Name:Name, RotationRules:RotationRules, LastRotatedDate:LastRotatedDate}' \
  --output table
```

**Expected output:**
```
┌───────────────────────┬────────────────────┐
│ Name                  │ algo/database       │
│ RotationRules         │ {AutomaticallyAfter │
│                       │  Days: 30}          │
│ LastRotatedDate       │ 2026-07-XX          │
└───────────────────────┴────────────────────┘
```

**If `RotationRules` is empty:** Database password rotation is NOT enabled. Contact AWS team to enable it.

### Step 4.3 - Check Alpaca Secret Format
**Command:**
```bash
aws secretsmanager get-secret-value \
  --secret-id algo/alpaca \
  --region us-east-1 \
  --query 'SecretString' \
  --output text | python3 -m json.tool
```

**Expected output:**
```json
{
  "APCA_API_KEY_ID": "PK...",
  "APCA_API_SECRET_KEY": "..."
}
```

---

## Phase 5: Test End-to-End

### Step 5.1 - Run System Diagnostics
**Command:**
```bash
python3 scripts/diagnose_system.py
```

**Expected output:**
```
[OK] AWS: Credentials configured
[OK] GitHub: Secrets present (27)
[OK] Database: Connection OK (8.6M records)
[OK] Secrets Manager: algo/alpaca accessible
[OK] Secrets Manager: algo/database accessible
[OK] API Endpoints: All 7 responding
[OK] Orchestrator: Dry-run successful
```

### Step 5.2 - Test Credential Loading
**Command:**
```bash
python3 -c "
from config.credential_manager import get_credential_manager
mgr = get_credential_manager()

# Try to load each secret
try:
    alpaca = mgr.get_alpaca_credentials()
    print('[OK] Alpaca credentials loaded')
except Exception as e:
    print(f'[ERROR] Alpaca: {e}')

try:
    db = mgr.get_db_credentials()
    print('[OK] Database credentials loaded')
except Exception as e:
    print(f'[ERROR] Database: {e}')

try:
    jwt = mgr.get_secret('algo/jwt')
    print('[OK] JWT secret loaded')
except Exception as e:
    print(f'[ERROR] JWT: {e}')

try:
    fred = mgr.get_secret('algo/fred')
    print('[OK] FRED API key loaded')
except Exception as e:
    print(f'[ERROR] FRED: {e}')
"
```

**Expected output:**
```
[OK] Alpaca credentials loaded
[OK] Database credentials loaded
[OK] JWT secret loaded
[OK] FRED API key loaded
```

### Step 5.3 - Run Dashboard & API
**Terminal 1 (API):**
```bash
python3 api-pkg/dev_server.py
# Should show: [INFO] Starting API dev server on http://localhost:3001
```

**Terminal 2 (Dashboard):**
```bash
python3 -m dashboard --local
# Should show: All 26 fetchers working, no "Data not available" errors
```

**Check:** Open http://localhost:3000 in browser → All panels have data ✅

---

## Phase 6: Document Final State

### Step 6.1 - Update Memory
**Command:**
```bash
# (This will be done by Claude)
```

**What gets updated:**
- ✅ AWS keys rotated (2026-07-12)
- ✅ Duplicate secrets cleaned up
- ✅ Secrets Manager verified working
- ✅ All end-to-end tests passing

### Step 6.2 - Commit Cleanup Notes
**Command:**
```bash
# Create a commit documenting the cleanup
git add .
git commit -m "chore: Secrets audit and cleanup - rotated AWS keys, removed duplicates, verified Secrets Manager"
```

---

## Rollback Plan (If Something Breaks)

### If GitHub Actions Fails After Key Rotation
**Action:**
1. Check the error in GitHub Actions logs
2. If it's a permissions error: AWS keys don't have right permissions
3. Restore old keys:
   ```bash
   gh secret set AWS_ACCESS_KEY_ID --body "OLD_KEY_ID" --repo argie33/algo
   gh secret set AWS_SECRET_ACCESS_KEY --body "OLD_SECRET" --repo argie33/algo
   ```
4. Investigate IAM permissions on the old key
5. Try rotating again after fixing permissions

### If Dashboard Shows "Data not available"
**Action:**
```bash
# Restart dev_server (Terminal 1 issue)
python3 api-pkg/dev_server.py

# Then restart dashboard
python3 -m dashboard --local
```

### If Secrets Manager Secrets Disappear
**Action:**
1. Check CloudTrail logs for deletion
2. Restore from backup (7-day recovery window)
3. Investigate who/what deleted them

---

## Checklist - Execute in Order

### Pre-Execution
- [ ] Read entire plan
- [ ] Have AWS Console open
- [ ] Have terminal open
- [ ] Have GitHub CLI logged in

### Phase 1: Audit
- [ ] Run `gh secret list` — confirm 27 secrets
- [ ] Run `gh secret list | grep ALPACA` — confirm old duplicates exist
- [ ] Run `gh secret list | grep AWS_ACCESS_KEY` — confirm old keys exist

### Phase 2: Rotate AWS Keys
- [ ] Go to AWS IAM console
- [ ] Create new access key for algo-developer
- [ ] Save new KEY_ID and SECRET
- [ ] Update GitHub Secrets (AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY)
- [ ] Run GitHub Actions workflow to test
- [ ] Wait for workflow to pass ✅
- [ ] Delete old AWS keys in IAM console
- [ ] Verify old keys deleted

### Phase 3: Clean Duplicates
- [ ] Delete ALPACA_API_KEY
- [ ] Delete ALPACA_SECRET_KEY
- [ ] Verify with `gh secret list | grep ALPACA` (only 2 left)

### Phase 4: Verify Secrets Manager
- [ ] Run `aws secretsmanager list-secrets` — see 5 algo/* secrets
- [ ] Run `aws secretsmanager describe-secret` for algo/database — check rotation
- [ ] Run `aws secretsmanager get-secret-value` for algo/alpaca — verify format

### Phase 5: Test End-to-End
- [ ] Run `python3 scripts/diagnose_system.py` — all [OK]
- [ ] Run credential manager test — all 4 secrets load
- [ ] Start dev_server — shows running on localhost:3001
- [ ] Start dashboard — no "Data not available" errors
- [ ] Open http://localhost:3000 in browser — all panels have data

### Post-Execution
- [ ] Document completion
- [ ] Update project memory
- [ ] Create completion commit

---

## Questions?

**Q: Do I need to run all phases?**  
A: Yes. Phases 1-4 are security/cleanup. Phase 5 is verification.

**Q: What if I can't access AWS Console?**  
A: You need IAM permissions to rotate keys. Contact your AWS admin.

**Q: What if GitHub Actions fails after key rotation?**  
A: See "Rollback Plan" section above. Likely missing IAM permissions on new key.

**Q: How long does this take?**  
A: ~30 minutes total (most is waiting for GitHub Actions to run).

**Q: Can I do this while system is running?**  
A: Yes! This only touches credentials, not the live system.

---

## Next Steps After Completion

Once this is done:
1. ✅ All secrets are fresh and organized
2. ✅ No duplicates or stale credentials
3. ✅ Secrets Manager integration verified
4. ✅ End-to-end testing passed
5. → Ready for next phase: Live trading setup or production deployment

---

**Status:** Ready to execute  
**Last Updated:** 2026-07-12  
**Owner:** argeropolos@gmail.com
