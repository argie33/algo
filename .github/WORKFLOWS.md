# GitHub Workflows — Decision Guide

This guide explains when to use each workflow. Choose the right one to avoid redundant runs and confusion.

---

## CI/CD Pipeline Flow

```
Pull Request:
┌────────────────────────────────────────────────────────────────┐
│ STEP 1: Code Review                                            │
│ ├─ ci-fast-gates.yml (runs ~12 minutes)                        │
│ │  ├─ Security: scan secrets, deps, SAST, IaC                 │
│ │  ├─ Code Quality: mypy, black, isort, flake8                │
│ │  ├─ Tests: unit, edge case, integration                     │
│ │  ├─ Coverage: test coverage report + Codecov upload          │
│ │  └─ RESULT: ✓ MUST PASS to merge                            │
│ │                                                              │
│ └─ terraform-plan.yml (runs on PR, shows plan in comment)     │
│    ├─ Terraform plan (AWS infrastructure changes)             │
│    ├─ Validates Terraform format                              │
│    └─ Posts diff to PR for human review                       │
│    RESULT: ✓ Informs review — no apply yet                    │
│                                                               │
└────────────────────────────────────────────────────────────────┘

After Merge to main:
┌────────────────────────────────────────────────────────────────┐
│ STEP 2: Manual Deploy (workflow_dispatch only)                 │
│ └─ deploy-all-infrastructure.yml (MANUAL TRIGGER)              │
│    ├─ Terraform apply (AWS infrastructure)                     │
│    ├─ Build & push ECR image (loaders)                         │
│    ├─ Deploy Lambda functions (algo + API)                     │
│    ├─ Deploy frontend (S3 + CloudFront)                        │
│    └─ Run database migrations                                  │
│    RESULT: ✓ Manual approval required before apply             │
│                                                               │
└────────────────────────────────────────────────────────────────┘
```

---

## Deployment Workflows

### Terraform Plan + Apply (Safe Approval Gate)

1. **Terraform Plan (on PR)** — `terraform-plan.yml`
   - Trigger: Pull request to main
   - Action: Runs `terraform plan`, posts diff to PR comment
   - Human review: Inspector sees infrastructure changes before merge
   - Result: Plan is read-only (no apply yet)

2. **Terraform Apply (Manual Deploy)** — `deploy-all-infrastructure.yml`
   - Trigger: **Manual only** (`workflow_dispatch`), after PR is merged to main
   - Action: Runs Terraform apply + builds Lambda + deploys frontend
   - Requires: Human explicitly clicks "Run workflow" in GitHub Actions
   - Result: Infrastructure changes applied only after human review + merge

### When to Use Which Deploy Workflow

| Scenario | Workflow | Trigger | Notes |
|----------|----------|---------|-------|
| **Review infra changes before merge** | `terraform-plan.yml` | Auto (PR to main) | Shows plan in PR comment — no apply yet |
| **Deploy after merge (normal flow)** | `deploy-all-infrastructure.yml` | Manual (`workflow_dispatch`) | Requires human to click "Run" in Actions tab |
| **Code-only deploy (skip Terraform)** | `deploy-all-infrastructure.yml` + `skip_terraform=true` | Manual (`workflow_dispatch`) | Use the `skip_terraform` input option |
| **Infrastructure-only (skip code deploy)** | `deploy-all-infrastructure.yml` + `skip_code=true` | Manual (`workflow_dispatch`) | Use the `skip_code` input option |

### Decision Tree: How to Deploy

```
Have Terraform changes?
│
├─ YES
│  ├─ Push PR: terraform-plan.yml auto-runs, shows diff in PR comment
│  ├─ Review plan and code in PR
│  ├─ Merge when approved
│  └─ Manually run deploy-all-infrastructure (click "Run workflow")
│
└─ NO (code-only changes)
   ├─ Merge PR normally (CI gates pass)
   └─ Manually run deploy-all-infrastructure with skip_terraform=true
```

---

## Credential Management Workflows

### Consolidated Workflow Purpose Matrix

| Workflow | Purpose | Trigger | When to Use |
|----------|---------|---------|------------|
| `rotate-credentials.yml` | Primary quarterly IAM key rotation with optional grace period (7 days) | Scheduled (first Monday of each quarter, 2 AM ET) or Manual | Standard quarterly rotation (includes cleanup) |
| `rotate-credentials-simple.yml` | Create new IAM key via AWS CLI (direct, no grace period) | Manual | Emergency fallback when primary rotation is stuck |
| `update-credentials.yml` | Sync GitHub Secrets → Secrets Manager for Alpaca/FRED API keys | Manual | After updating API credentials in GitHub Secrets |
| `check-credential-status.yml` | Report credential rotation status and expiration dates | Reusable workflow (called by CI/CD) | Audit: verify credentials valid before deployment |

### Decision Tree: Which Credential Workflow?

```
Credential task?
│
├─ Quarterly rotation (with grace period)
│  └─ Automatic: runs first Monday of each quarter at 2 AM ET
│     (or manually trigger: gh workflow run rotate-credentials.yml)
│     Includes: create new key → dual-credentials period (7 days) → auto-cleanup
│
├─ Emergency: need immediate rotation (rotation stuck)
│  └─ run: rotate-credentials-simple
│     (direct AWS CLI, bypasses grace period and Terraform)
│
├─ Update API credentials (Alpaca, FRED)
│  └─ 1. Update GitHub Secret (gh secret set ALPACA_API_KEY ...)
│     2. run: update-credentials with trading_mode input
│
├─ Check credential rotation status
│  └─ run: check-credential-status (called by CI/CD)
│     Use: --fail-on-grace-period to enforce credential updates
│
└─ Local dev: refresh your AWS credentials
   └─ Don't use workflow. Instead:
      ! scripts/refresh-aws-credentials.ps1
      (reads from Secrets Manager directly, no workflow overhead)
```

---

## Operational Workflows (Manual Triggers)

These trigger data loaders, monitors, and reports. **Currently all manual — should some be scheduled?**

| Workflow | Purpose | Current Trigger | Should Be Scheduled? |
|----------|---------|-----------------|----------------------|
| `manual-trigger-eod-pipeline.yml` | Run all EOD data loaders (stocks, technical, trends, signals) | Manual | ✓ YES — daily at 4:00 AM ET (after market close) |
| `manual-invoke-orchestrator.yml` | Invoke trading orchestrator (run all 7 phases) | Manual | ✓ YES — daily at 9:30 AM ET (market open) |
| `trigger-loader.yml` | Run a single loader by name | Manual | ✗ NO — ad-hoc tool for testing |
| `run-fred-loader.yml` | Fetch economic data (FRED) | Manual | ✓ MAYBE — daily or weekly? |
| `monitor-loader-health.yml` | Check loader task status | Manual | ✓ YES — hourly during market hours |
| `kill-hung-loader.yml` | Force-kill a stuck loader task | Manual | ✗ NO — ad-hoc emergency tool |
| `check-morning-prep-status.yml` | Report daily prep tasks done (prices, technicals loaded) | Manual | ✓ YES — daily 8:30 AM ET (before market open) |
| `run-dashboard.yml` | Regenerate performance dashboard | Manual | ✓ YES — daily at 5:00 PM ET (after EOD) |

### Recommended: Convert These to Scheduled (Cron)

```
Daily Schedule (Proposed):
├─ 4:00 AM ET  → manual-trigger-eod-pipeline (load yesterday's data)
├─ 8:30 AM ET  → check-morning-prep-status (verify data loaded)
├─ 9:30 AM ET  → manual-invoke-orchestrator (run trading)
├─ Hourly 9:30-16:00 ET → monitor-loader-health (watch health)
└─ 5:00 PM ET  → run-dashboard (update performance report)
```

**Action Item:** Convert these to `CronCreate` scheduled workflows instead of manual `workflow_dispatch`.

---

## Issues Found

### 🔴 Critical

1. **Duplicate CI Workflows**
   - `ci-fast-gates.yml` and `quality-gates.yml` both run type checking, linting, and tests
   - They fire in parallel on every commit (wasting ~5-10 min)
   - **Fix:** Consolidate into one, or make one non-blocking with distinct purpose
   - **Tracking:** See GitHub issue (to be created)

2. **Confusing Deploy Workflow Split**
   - `deploy-code.yml` exists but has `if: false` Lambda jobs with comment about deploy-all-infrastructure
   - Unclear why it would ever be used (deploy-all-infrastructure does everything)
   - **Fix:** Either delete or document exact use case (code-only emergency deploy?)
   - **Tracking:** See GitHub issue (to be created)

3. **Auto-Deploy on Every Push** ✅ FIXED
   - ~~`deploy-all-infrastructure` runs `terraform apply` automatically on every push to main~~
   - ✅ **FIXED:** Split into two workflows:
     - `terraform-plan.yml`: Shows diff on PR (read-only)
     - `deploy-all-infrastructure.yml`: Manual-only, requires clicking "Run workflow"
   - Infrastructure changes now require human review + merge + manual approval
   - **Completed:** Terraform apply is now manual-only

### 🟡 Medium

4. **Operational Workflows Need Scheduling** ✅ CREDENTIALS FIXED
   - ✅ **DONE:** 8 credential workflows consolidated to 4 (clear naming, automatic scheduling)
   - ⏳ **TODO:** 8 operational workflows (loaders, monitoring) still all manual
   - **Fix:** Convert to cron-based scheduled workflows (see Operational Workflows section)

5. **No Scheduled Workflows**
   - Daily tasks (EOD pipeline, morning status, orchestrator) are all manual
   - Human must remember to run them; prone to missed runs
   - **Fix:** Use `CronCreate` for daily tasks (see Operational Workflows section)

---

## Quick Reference: "I Want to Deploy X"

**I changed code and want to see infrastructure changes:**
→ Push PR. terraform-plan.yml auto-runs and posts the plan to your PR comment.

**I merged to main and want to deploy:**
→ Go to GitHub Actions → select `Deploy All Infrastructure` → click `Run workflow` → choose options → deploy.
→ Never automatic — always requires human approval via manual trigger.

**I need to deploy code-only without changing infrastructure:**
→ Manually trigger: `deploy-all-infrastructure.yml` with `skip_terraform=true`

**I need to rotate AWS credentials:**
→ Automatic: `rotate-credentials.yml` runs first Monday of each quarter at 2 AM ET (includes cleanup).
→ Manual or emergency: `gh workflow run rotate-credentials.yml` (standard) or `gh workflow run rotate-credentials-simple.yml` (fallback).
→ Follow the credential decision tree above.

**I need to run the EOD data pipeline manually:**
→ Manually trigger: `manual-trigger-eod-pipeline.yml`
→ (Or wait for scheduled run if we enable cron)

**I need to check if overnight data loaded:**
→ Manually trigger: `check-morning-prep-status.yml`
→ (Or wait for scheduled run at 8:30 AM)

**I need to test a single data loader:**
→ Manually trigger: `trigger-loader.yml` with loader name

**A loader is hung and won't finish:**
→ Manually trigger: `kill-hung-loader.yml` to force-kill it

---

## Next Steps

**To Clean Up Workflows:**

1. [ ] Consolidate `ci-fast-gates.yml` + `quality-gates.yml` (duplicate work)
2. [ ] Clarify or delete `deploy-code.yml` (confusing purpose)
3. [x] Add approval gate to `deploy-all-infrastructure` (prevent unvetted deploys) — ✅ DONE: now manual-only via `workflow_dispatch`
4. [x] Consolidate credential workflows (rename/document for clarity) — ✅ DONE: 8 workflows → 4 (rotate-credentials.yml primary, rotate-credentials-simple.yml fallback, update-credentials.yml, check-credential-status.yml)
5. [ ] Convert manual operational workflows to scheduled (cron-based)

See CLAUDE.md for instructions on updating workflows in future commits.
