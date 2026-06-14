# AWS Infrastructure Audit & Cleanup Report
**Date:** 2026-06-14  
**Status:** ACTIVE ISSUES FOUND

## Executive Summary
The infrastructure is **MOSTLY CLEAN but has ONE CRITICAL BUG**:
- All AWS resources are properly deployed and operational
- S3 buckets are current and sized appropriately  
- No stale/orphaned resources in AWS
- **CRITICAL:** Old database tables are referenced in code but never populated

## Issues Found

### 🔴 CRITICAL: Dead Code - Stale Database Tables
**Severity:** HIGH - Daily reports will return empty data  
**Location:** `algo/reporting/daily_report.py`  
**Problem:**
- Tables `algo_performance_daily` and `algo_risk_daily` exist in database schema
- Code in `daily_report.py` queries these tables (lines 102, 128)
- **NO loaders populate these tables** - they're empty
- Loaders `load_algo_performance_daily.py` and `load_algo_risk_daily.py` exist in code but aren't scheduled

**Root Cause:** Refactoring replaced old performance tracking with new pre-computed metrics:
- Old: `load_algo_performance_daily.py` → `algo_performance_daily` table
- New: `compute_performance_metrics.py` → `algo_performance_metrics` table
- Daily report code wasn't updated to use new tables

**Options to Fix:**
1. (RECOMMENDED) Delete old table references; update code to use `algo_performance_metrics`
2. Schedule the old loaders (not recommended - using old schema)
3. Delete unused loader files and clear daily_report.py references

---

### ⚠️  YELLOW: Unused/Unscheduled Loaders
**Severity:** LOW - Code is kept for reference, can be cleaned up  
**Unscheduled loaders in code (not in Terraform EventBridge/Step Functions):**
- load_algo_performance_daily.py (part of CRITICAL issue above)
- load_algo_risk_daily.py (part of CRITICAL issue above)
- load_economic_calendar.py (deprecated, use economic_metrics_daily instead)
- load_equity_curve_daily.py (legacy, not used by orchestrator)
- load_portfolio_exposure_daily.py (legacy, replaced by sector allocation tracking)
- load_seasonality.py (computed but not exposed in API)
- load_stock_correlations.py (computed but not actively used)
- load_sector_performance.py (was removed: no real data source, wrote zeros)

**Action:** These can be deleted after CRITICAL issue is fixed. They serve no purpose.

---

## AWS Deployment Status ✓

### S3 Buckets (All Current)
- `algo-frontend-626216981288` - 91MB, current (2026-06-14 09:35)
- `algo-lambda-artifacts-626216981288` - empty (normal)
- `algo-config-bucket-626216981288` - AWS Config snapshots (disabled feature)
- `algo-code-626216981288` - code repository cache
- `algo-cloudtrail-logs-us-east-1-626216981288` - CloudTrail logs
- `algo-log-archive-626216981288` - archived logs
- `algo-terraform-state-dev` - Terraform remote state (healthy)

### Database
- RDS: `algo-db` (db.t4g.small) - operational, healthy connections
- DynamoDB tables (11 total) - all operational:
  - `algo-orchestrator-locks-dev`
  - `algo-loader-status-dev`
  - `algo-loader-locks-dev`
  - `algo-loader-config-dev`
  - `algo-orchestrator-state-dev`
  - `algo-phase1-cache-dev`
  - `algo-token-blocklist-dev`
  - `algo-contact-rate-limit-dev`
  - Plus 3 more supporting tables

### Lambda & Compute
- Lambda functions: properly configured
  - api-dev: 256MB, 25s timeout, 1 provisioned concurrency ✓
  - algo-dev: 512MB, 600s timeout, 0 provisioned concurrency ✓
- ECS Cluster: operational (Fargate)
- ECR Repository: clean, current images

### Configuration
- Terraform: validated & clean
- AWS Config: properly disabled (was causing S3 state corruption)
- Cost Optimization: good
  - S3 versioning: disabled ✓
  - CloudWatch retention: 7 days (good balance)
  - RDS: single-AZ, no multi-AZ standby ✓
  - No unused reserved instances

---

## Cleanup Actions Required

### MUST DO (Blocks Daily Report)
1. **Fix Performance Metrics References**
   - Update `algo/reporting/daily_report.py` to query `algo_performance_metrics` instead of `algo_performance_daily`
   - Remove references to `algo_risk_daily` or create equivalent risk metrics loader
   - Test that daily reports no longer return empty data

2. **Timeline:** Do this immediately - daily reports are currently broken

### SHOULD DO (Clean Code)
Delete unscheduled/unused loaders after CRITICAL issue is fixed:
- `loaders/load_algo_performance_daily.py` (replaced by compute_performance_metrics.py)
- `loaders/load_algo_risk_daily.py` (no equivalent replacement)
- `loaders/load_economic_calendar.py` (deprecated, use economic_metrics_daily)
- `loaders/load_equity_curve_daily.py` (legacy)
- `loaders/load_portfolio_exposure_daily.py` (legacy)
- `loaders/load_seasonality.py` (computed but unused)
- `loaders/load_stock_correlations.py` (computed but unused)
- `loaders/load_sector_performance.py` (intentionally removed)

### NICE TO DO (Optimize)
- Mark `algo_performance_daily` and `algo_risk_daily` tables as deprecated in schema
- Add deprecation comments to schema.sql explaining replacement tables
- Document why old loaders were replaced in git commit message

---

## Cost Summary
✓ Monthly infrastructure cost: ~$60-80 (well-optimized)  
✓ No wasted resources  
✓ No unused VPCs, security groups, or NAT gateways  
✓ Storage costs are minimal (frontend ~91MB, logs auto-expire in 7 days)  
✓ No lingering resources from past experiments  

---

## Next Steps
1. Review this audit and approve cleanup plan
2. Fix daily_report.py to use correct tables
3. Delete unused loaders and update Terraform documentation
4. Mark old tables as deprecated in schema
5. Deploy cleanup changes to main branch
