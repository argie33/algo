# API Authentication Blocker Resolution Guide

**Current Status:** Code Ready, Awaiting Terraform Deployment

---

## Issue

All data endpoints (`/api/algo/status`, `/api/stocks`, `/api/scores/*`, etc.) return **HTTP 401 Unauthorized**, preventing dashboards from loading real data.

## Root Cause

API Gateway route still enforces JWT authentication in AWS, even though:
- ✅ `terraform.tfvars` has `cognito_enabled = false`
- ✅ Terraform code correctly configures auth as "NONE" when cognito_enabled is false
- ❌ BUT: Terraform changes haven't been applied to AWS yet

## Solution: Run Terraform Deployment

### Option 1: Automatic (if workflow runs on next push)
Just merged commits trigger `deploy-all-infrastructure.yml` automatically when pushed to main.

### Option 2: Manual Trigger (if workflow hasn't started)
1. Go to: https://github.com/argie33/algo/actions
2. Click: **Deploy All Infrastructure** workflow
3. Click: **Run workflow** button
4. Select: `main` branch
5. Leave defaults, click: **Run workflow**
6. Monitor logs for 15-20 minutes

## What Terraform Will Do

```
Step 1: Terraform Plan
  - Reads: terraform.tfvars (cognito_enabled = false)
  - Compares: Current AWS state vs desired state
  - Shows: api_default route will change from JWT → NONE

Step 2: Terraform Apply
  - Updates: AWS API Gateway route authorization_type from JWT to NONE
  - Waits: API Gateway auto-deploy (~30 seconds)
  
Step 3: Auto-Deploy
  - Redeploys: API Gateway stage with new auth config
  - Result: Data endpoints now return 200 instead of 401
```

## Verification

Once Terraform completes, verify the fix:

```bash
# Check API status endpoint
curl -w "Status: %{http_code}\n" \
  https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/algo/status

# Expected output (not 401):
# Status: 200
# {"status": "running", "version": "1.0.0", ...}

# Check stocks endpoint
curl "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/stocks?limit=5"

# Expected output (not 401):
# [{"symbol": "AAPL", "price": 150.25, ...}, ...]
```

## Timeline

- Terraform workflow: **15-20 minutes**
- API Gateway auto-deploy: **~30 seconds** (after apply completes)
- Dashboard pages loading real data: **immediately after**

## Monitoring

**Real-time check:**
```bash
# Watch endpoint status change from 401 to 200
while true; do
  curl -s -o /dev/null -w "Status: %{http_code}\n" \
    https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/algo/status
  sleep 10
done
```

**GitHub Actions:**
- Workflow page: https://github.com/argie33/algo/actions
- Logs will show terraform plan output and apply results

## Troubleshooting

**If workflow fails:**
1. Check GitHub Actions logs for specific error
2. Common issues:
   - AWS credentials expired: Re-run workflow (automatic on next push)
   - Terraform state locked: Wait 10 minutes, try again
   - Missing secrets: Check GitHub Actions settings

**If API still returns 401 after deployment:**
1. Verify terraform apply succeeded (check logs)
2. Wait 2-3 minutes for API Gateway cache to clear
3. Manually redeploy API in AWS Console:
   - API Gateway → Select API → Deployments → Deploy

## System Status After Fix

Once Terraform deployment completes and API returns 200:

- ✅ MetricsDashboard - Shows 5000+ stock metrics
- ✅ ScoresDashboard - Shows weighted scores with prices
- ✅ VaR Dashboard - Shows portfolio risk metrics
- ✅ All data-driven pages - Display real data
- ✅ System is production-ready

---

## Summary

**Do This:**
1. Run `python3 check_deployment_status.py` (verify config)
2. Go to GitHub Actions
3. Trigger `deploy-all-infrastructure` workflow
4. Wait 15-20 minutes
5. Test API endpoints (should return 200)
6. Dashboards now load real data ✅

**Time to Resolution:** ~20 minutes from workflow start
