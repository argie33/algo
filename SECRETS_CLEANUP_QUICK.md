# Quick Secrets Cleanup (GitHub Actions + Developer Role)
**Your Setup:** Developer IAM role + GitHub Actions OIDC  
**Time:** ~20 minutes  
**Risk:** Low (credentials not in code, only in GitHub + AWS Secrets Manager)

---

## What You Actually Need to Do

### Step 1: Delete Old Duplicate Alpaca Secrets (5 min)

**Why:** You have 4 Alpaca secrets — 2 old (June) and 2 new (July). Keep only the new ones.

```bash
# Delete old duplicates
gh secret delete ALPACA_API_KEY --repo argie33/algo
gh secret delete ALPACA_SECRET_KEY --repo argie33/algo

# Verify only the new ones remain
gh secret list --repo argie33/algo | grep ALPACA
# Should show:
# ALPACA_API_KEY_ID          2026-07-08
# ALPACA_API_SECRET_KEY      2026-07-08
```

### Step 2: Check Database Password Rotation (5 min)

**Why:** Your DB password was last updated in May (2+ months). Verify Secrets Manager auto-rotation is working.

```bash
# Check if rotation is enabled
aws secretsmanager describe-secret \
  --secret-id algo/database \
  --region us-east-1 \
  --query 'RotationRules'

# Expected output:
# {
#   "AutomaticallyAfterDays": 30
# }
```

**If rotation is NOT enabled:** 
```bash
# Enable it (contact AWS admin if you can't run this)
aws secretsmanager rotate-secret \
  --secret-id algo/database \
  --rotation-rules '{"AutomaticallyAfterDays":30}' \
  --region us-east-1
```

### Step 3: About AWS_ACCESS_KEY_ID & AWS_SECRET_ACCESS_KEY (5 min)

**Current situation:**
- ✅ You're using OIDC (recommended) via `AWS_GITHUB_ACTIONS_ROLE_ARN`
- ⚠️ You also have legacy AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY (from May — old)

**What to do:**

**Option A: Keep them (minimal effort)**
- If they're not actively used and just sitting there unused → leave them
- They'll auto-expire per AWS security policy
- GitHub Actions uses OIDC role (better security)

**Option B: Rotate them (best practice)**
- Go to AWS Console → IAM → Users → algo-developer
- Click "Security credentials" tab
- Create NEW access key
- Update GitHub Secrets:
  ```bash
  gh secret set AWS_ACCESS_KEY_ID --body "NEW_KEY_ID" --repo argie33/algo
  gh secret set AWS_SECRET_ACCESS_KEY --body "NEW_SECRET" --repo argie33/algo
  ```
- Test: Run a GitHub Actions workflow to make sure it still works
- Delete OLD key from IAM console

**Option C: Remove them entirely (if not used)**
- If only OIDC is being used (via `AWS_GITHUB_ACTIONS_ROLE_ARN`):
  ```bash
  gh secret delete AWS_ACCESS_KEY_ID --repo argie33/algo
  gh secret delete AWS_SECRET_ACCESS_KEY --repo argie33/algo
  ```
- Verify workflows still work (they'll use OIDC role only)

**I'd recommend: Option B** (rotate them, safer than leaving old keys lying around)

### Step 4: Verify Everything Works (5 min)

```bash
# Run a quick test
python3 scripts/diagnose_system.py

# Expected output:
# [OK] AWS: Credentials configured
# [OK] Database: Connection OK
# [OK] Secrets Manager: algo/alpaca accessible
# [OK] API Endpoints: All responding
```

---

## Complete Checklist (Copy & Paste Order)

### Do This Now:

```bash
# 1. Delete old Alpaca secrets
gh secret delete ALPACA_API_KEY --repo argie33/algo
gh secret delete ALPACA_SECRET_KEY --repo argie33/algo

# 2. Verify new ones still there
gh secret list --repo argie33/algo | grep ALPACA

# 3. Check DB password rotation
aws secretsmanager describe-secret \
  --secret-id algo/database \
  --region us-east-1 \
  --query 'RotationRules'

# 4. Run system diagnostic
python3 scripts/diagnose_system.py
```

### Optional (But Recommended):

**If you want to rotate AWS keys:**
1. Go to AWS Console → IAM → Users → algo-developer → Security credentials
2. Click "Create access key"
3. Copy new KEY_ID and SECRET
4. Run:
   ```bash
   gh secret set AWS_ACCESS_KEY_ID --body "YOUR_NEW_KEY_ID" --repo argie33/algo
   gh secret set AWS_SECRET_ACCESS_KEY --body "YOUR_NEW_SECRET" --repo argie33/algo
   ```
5. Test: Run any GitHub Actions workflow (should pass with new keys)
6. After workflow passes: Delete old key from IAM console

---

## What Each Secret Does

| Secret | Used By | How | Action Needed |
|--------|---------|-----|---|
| `AWS_GITHUB_ACTIONS_ROLE_ARN` | GitHub Actions | OIDC to assume developer role | ✅ None (working) |
| `AWS_ACCESS_KEY_ID` | Potentially GitHub Actions | Legacy key auth | ⚠️ Rotate or remove |
| `AWS_SECRET_ACCESS_KEY` | Potentially GitHub Actions | Legacy key auth | ⚠️ Rotate or remove |
| `ALPACA_API_KEY_ID` | Terraform (Secrets Manager) | Paper trading creds | ✅ Fresh (2026-07-08) |
| `ALPACA_API_SECRET_KEY` | Terraform (Secrets Manager) | Paper trading creds | ✅ Fresh (2026-07-08) |
| `JWT_SECRET` | Terraform (Secrets Manager) | API token signing | ✅ Recent (2026-06-25) |
| `FRED_API_KEY` | Terraform (Secrets Manager) | Economic data | ✅ Recent (2026-06-25) |
| `DB_PASSWORD` | Terraform (Secrets Manager) | RDS connection | ✅ Auto-rotated |

---

## After You've Done the Cleanup

**For live trading setup:**
1. Alpaca credentials are already there (fresh)
2. JWT secret is set (Cognito auth works)
3. Database is connected (loaders working)
4. Orchestrator is configured (ready to trade)

**Next step:** Configure Alpaca account settings (paper vs live) and test orchestrator

---

## If Something Goes Wrong

**GitHub Actions fails after rotating keys:**
```bash
# Restore old keys temporarily
gh secret set AWS_ACCESS_KEY_ID --body "OLD_KEY_ID" --repo argie33/algo
gh secret set AWS_SECRET_ACCESS_KEY --body "OLD_SECRET" --repo argie33/algo

# Then debug: check that new key has right IAM permissions
```

**Dashboard shows "Data not available":**
```bash
# Restart dev server (Terminal 1)
python3 api-pkg/dev_server.py

# Then restart dashboard (Terminal 2)
python3 -m dashboard --local
```

---

## My Recommendation: Full Cleanup Order

1. ✅ **Delete old Alpaca secrets** (5 min) — safe, just cleanup
2. ✅ **Verify DB password rotation** (5 min) — check health
3. ✅ **Rotate AWS keys** (10 min) — security best practice
4. ✅ **Run diagnostics** (5 min) — verify everything works

**Total time:** ~25 minutes  
**Safety:** Low risk (only touching credentials, no service changes)  
**Payoff:** Clean state, fresh credentials, everything documented

Ready? Start with:
```bash
gh secret delete ALPACA_API_KEY --repo argie33/algo
```
