# GitHub Workflows — Decision Guide

This guide explains when to use each workflow. Choose the right one to avoid redundant runs and confusion.

---

## CI/CD Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ Push to main OR Pull Request                                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ STEP 1: FAST GATES (Required to merge)                          │
│ ├─ ci-fast-gates.yml (runs ~90 seconds)                         │
│ │  ├─ Security: scan secrets, deps, SAST, IaC                  │
│ │  ├─ Code Quality: mypy, black, isort, flake8                 │
│ │  ├─ Unit Tests: test_position_sizer, test_circuit_breaker   │
│ │  └─ Integration Tests: core integration tests                │
│ │  RESULT: ✓ MUST PASS to merge                                │
│ │                                                               │
│ └─ quality-gates.yml (runs ~5-10 min, PARALLEL with fast-gates)│
│    ├─ Type Check: mypy strict mode (stricter than fast-gates) │
│    ├─ Coverage: full test coverage + codecov upload             │
│    ├─ Code Quality: black, isort, flake8 (duplicate!)          │
│    └─ Test Suite: full pytest with DB                          │
│    RESULT: ⚠ CURRENTLY DUPLICATES fast-gates — see issue #TBD  │
│                                                                 │
│ STEP 2: AUTO-DEPLOY (if on main branch)                        │
│ ├─ deploy-all-infrastructure.yml (runs on push to main)        │
│ │  ├─ Terraform apply (AWS infrastructure)                     │
│ │  ├─ Build & push ECR image (loaders)                         │
│ │  ├─ Deploy Lambda functions (algo + API)                     │
│ │  ├─ Deploy frontend (S3 + CloudFront)                        │
│ │  └─ Run database migrations                                  │
│ │  RESULT: ⚠ AUTO-DEPLOYS ON EVERY PUSH — requires approval?  │
│ │                                                               │
│ └─ build-push-ecr.yml (runs on push to main, path-filtered)    │
│    └─ Build loader Docker image (if loaders/ changed)          │
│    RESULT: ✓ Called by deploy-all-infrastructure               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Deployment Workflows

### When to Use Which Deploy Workflow

| Scenario | Workflow | Trigger | Notes |
|----------|----------|---------|-------|
| **Normal code push to main** | `deploy-all-infrastructure.yml` | Auto (push to main) | Terraform + Lambda + Frontend all deploy together |
| **Emergency: code-only deploy without Terraform** | `deploy-code.yml` | Manual (`workflow_dispatch`) | ⚠ **CONFUSING**: has `if: false` Lambda jobs — when would you actually use this? |
| **Manual infrastructure-only (no code)** | `deploy-all-infrastructure.yml` + `skip_code=true` | Manual (`workflow_dispatch`) | Use the `skip_code` input option |
| **Manual Terraform-only (dry-run first)** | `deploy-all-infrastructure.yml` + `skip_terraform=false` | Manual (`workflow_dispatch`) | Full Terraform plan+apply |

### Decision Tree: Which Deploy to Trigger?

```
Need to deploy?
│
├─ YES, on main (normal flow)
│  └─ Just push. deploy-all-infrastructure runs automatically.
│
├─ YES, but Terraform is broken (need code-only deploy)
│  └─ Manually run deploy-all-infrastructure with skip_terraform=true
│     (deploy-code.yml exists but is confusing — prefer deploy-all-infrastructure)
│
└─ YES, but as dry-run (plan without apply)
   └─ Manually run deploy-all-infrastructure
      (no built-in plan-only mode yet)
```

---

## Credential Management Workflows

### Workflow Purpose Matrix

| Workflow | Purpose | Trigger | When to Use |
|----------|---------|---------|------------|
| `rotate-credentials-simple.yml` | Create new IAM key via AWS CLI (fallback) | Manual | When `rotate-credentials-with-grace-period` is stuck |
| `rotate-credentials-with-grace-period.yml` | IAM rotation with old key validity window | Manual | Quarterly credential rotation (preferred method) |
| `rotate-developer-credentials.yml` | Rotate developer-specific keys | Manual | Developer onboarding / offboarding |
| `update-credentials.yml` | Update existing secret in Secrets Manager | Manual | Post-rotation: update app-facing secrets |
| `reset-passwords.yml` | Reset database passwords | Manual | Emergency password reset (rare) |
| `refresh-dev-credentials.yml` | Local dev: refresh .aws/credentials file | Manual | Dev local setup (use `scripts/refresh-aws-credentials.ps1` instead) |
| `cleanup-old-credentials.yml` | Deregister old IAM keys | Manual | Post-rotation cleanup (run after rotation completes) |
| `check-credential-status.yml` | Report credential age and key rotation dates | Manual | Audit: check which keys are expiring soon |

### Decision Tree: Which Credential Workflow?

```
Credential task?
│
├─ Quarterly rotation
│  └─ run: rotate-credentials-with-grace-period
│     then: update-credentials
│     then: cleanup-old-credentials
│
├─ Emergency: rotation stuck
│  └─ run: rotate-credentials-simple
│     (direct AWS CLI, bypasses Terraform)
│
├─ Developer onboarding/offboarding
│  └─ run: rotate-developer-credentials
│
├─ Check what's expiring soon
│  └─ run: check-credential-status
│
└─ Local dev: refresh your AWS creds
   └─ Don't use workflow. Instead:
      ! scripts/refresh-aws-credentials.ps1
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

3. **Auto-Deploy on Every Push**
   - `deploy-all-infrastructure` runs `terraform apply` automatically on every push to main
   - No approval gate — infrastructure changes go live instantly
   - **Fix:** Require manual approval or add approval gate
   - **Tracking:** See GitHub issue (to be created)

### 🟡 Medium

4. **16 Manual Workflows for Operational Tasks**
   - 8 credential workflows with overlapping purpose
   - 8 operational workflows (loaders, monitoring) all manual
   - Unclear naming and sequencing
   - **Fix:** See decision trees above; consolidate and schedule as needed

5. **No Scheduled Workflows**
   - Daily tasks (EOD pipeline, morning status, orchestrator) are all manual
   - Human must remember to run them; prone to missed runs
   - **Fix:** Use `CronCreate` for daily tasks (see Operational Workflows section)

---

## Quick Reference: "I Want to Deploy X"

**I changed code and merged to main:**
→ Wait. deploy-all-infrastructure.yml runs automatically. Monitor GitHub Actions.

**I need to deploy code-only without changing infrastructure:**
→ Manually trigger: `deploy-all-infrastructure.yml` with `skip_terraform=true`

**I need to rotate AWS credentials:**
→ Follow the credential decision tree above. Usually: `rotate-credentials-with-grace-period` → `update-credentials` → `cleanup-old-credentials`

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
3. [ ] Add approval gate to `deploy-all-infrastructure` (prevent unvetted deploys)
4. [ ] Consolidate credential workflows (rename/document for clarity)
5. [ ] Convert manual operational workflows to scheduled (cron-based)

See CLAUDE.md for instructions on updating workflows in future commits.
