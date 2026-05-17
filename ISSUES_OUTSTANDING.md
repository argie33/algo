# Outstanding Issues - Stock Analytics Platform

**Date:** 2026-05-17  
**Scope:** Full platform audit - local dev + AWS deployment  
**Status:** Comprehensive list of blocking and non-blocking issues

---

## PRIORITY 1: CRITICAL BLOCKING ISSUES

### Issue #1: Config Validator Import Error (FIXED)
- **Status:** FIXED in this commit
- **File:** `utils/config_validator.py:14`
- **Error:** `NameError: name 'DEFAULT_DB_HOST' is not defined`
- **Root Cause:** Missing imports from `utils.defaults`
- **Fix Applied:** Added imports for `DEFAULT_DB_HOST`, `DEFAULT_DB_PORT`, `DEFAULT_DB_USER`, `DEFAULT_DB_NAME`
- **Impact:** Config validator can now be imported without errors
- **Verification:** `python3 -c "from utils.config_validator import ConfigValidator"` now works

### Issue #2: Database Credentials Not Available (Needs Setup)
- **File:** `config/credential_helper.py`
- **Error:** `ValueError: Database password not available...`
- **Cause:** No AWS Secrets Manager setup for local dev OR missing environment variables
- **Impact:** BLOCKING - Can't run any loaders locally
- **Fix Required:** User must run `LOCAL_CRED_SETUP.md` (5-minute setup)
  ```bash
  aws secretsmanager create-secret --name db/password --secret-string "your_postgres_password"
  # ... create other secrets per LOCAL_CRED_SETUP.md
  ```
- **Status:** Expected. User hasn't completed credential setup yet.

### Issue #3: Loader Direct Invocation Path Issue
- **File:** `loaders/loadstocksymbols.py` and similar
- **Error:** `ModuleNotFoundError: No module named 'utils'`
- **When:** Running loaders directly (e.g., `python3 loaders/loadstocksymbols.py`)
- **Cause:** PYTHONPATH not set - loaders need root directory in path
- **Workaround:** Use `python3 run-all-loaders.py` instead (sets PYTHONPATH correctly)
- **Impact:** MINOR - Users should use the orchestrator anyway
- **Note:** Direct invocation is not recommended per CLAUDE.md rule (use run-all-loaders.py)

---

## PRIORITY 2: AWS DEPLOYMENT ISSUES

### Issue #4: Missing GitHub Secrets (AWS Deployment Blocker)
- **File:** `.github/workflows/deploy-all-infrastructure.yml`
- **Missing Secrets:**
  - `AWS_ACCOUNT_ID` - AWS account number
  - `RDS_PASSWORD` - PostgreSQL admin password
  - `ALPACA_API_KEY_ID` - Alpaca API key
  - `ALPACA_API_SECRET_KEY` - Alpaca secret
  - `ALERT_EMAIL_ADDRESS` - Alert recipient email
  - `JWT_SECRET` - JWT signing key
  - `FRED_API_KEY` - FRED economic data API key
- **Impact:** BLOCKING - Deploy workflow will fail without these
- **Fix:** Add secrets to GitHub repo settings
- **Status:** Deployment infrastructure ready, just needs secrets configured

### Issue #5: Frontend S3 Bucket Resolution (Terraform Output Issue)
- **From STATUS.md:** "ERROR: could not resolve frontend S3 bucket"
- **Cause:** `frontend_bucket_name` Terraform output is empty or null
- **Impact:** Frontend deployment job fails
- **Check:** 
  ```bash
  cd terraform
  terraform state show module.frontend.aws_s3_bucket.frontend_bucket
  terraform output frontend_bucket_name
  ```
- **Fix:** Verify S3 bucket creation succeeded in Terraform apply
- **Status:** Needs investigation in AWS/Terraform state

### Issue #6: Lambda Functions Not Yet Deployed
- **Status:** Infrastructure created but code not deployed
- **Functions Pending:**
  - `algo_orchestrator` Lambda (main trading logic)
  - `api` Lambda (HTTP API backend)
  - `data-freshness-monitor` Lambda (data quality monitoring)
- **What's Done:** Docker image build scripts ready, ZIP files building successfully
- **What's Needed:** 
  - Push Docker image to ECR
  - Create ECS task definitions for loaders
  - Deploy Lambda ZIPs via Terraform
- **Impact:** Can't run trading algorithm in AWS yet
- **Timeline:** Terraform apply should deploy these (check if jobs were skipped)

### Issue #7: ECS Loader Tasks Not Yet Scheduled
- **Status:** Infrastructure ready but not active
- **What's Needed:**
  - Push loader Docker image to ECR (via GitHub Actions)
  - Verify EventBridge rules created by Terraform
  - Test ECS task invocation
- **Checklist:**
  ```bash
  aws ecs list-task-definitions
  aws ecs describe-tasks --cluster algo-dev --task-definition algo-load-stock-symbols-dev
  aws logs tail /ecs/algo-load-stock-symbols-dev --follow
  ```
- **Impact:** Loaders can't run on schedule in AWS yet

### Issue #8: Database Initialization in AWS
- **Status:** Schema needs to be created in AWS RDS
- **Action:** Run `init_database.py` in Lambda or ECS task
- **Check:**
  ```bash
  psql -h <rds-endpoint> -U postgres -d stocks -c "SELECT COUNT(*) FROM information_schema.tables;"
  ```
- **Impact:** BLOCKING for loader execution in AWS

---

## PRIORITY 3: DATA LOADER ISSUES

### Issue #9: Tier 2 Reference Data Loaders Status
- **Status:** Multiple loaders need credential setup to test
- **Affected Loaders (Tier 2):**
  - `load_income_statement.py`
  - `load_balance_sheet.py`
  - `load_cash_flow.py`
  - `load_key_metrics.py`
  - `loadearningshistory.py`
  - `loadearningsrevisions.py`
  - `loadearningsestimates.py`
  - `loadmarketindices.py`
  - `loadseasonality.py`
  - etc. (22 loaders in Tier 2)
- **Current Test:** All fail with credentials error (expected)
- **Next Step:** Once credentials are set up, run:
  ```bash
  python3 run-all-loaders.py
  ```
- **Expected Runtime:** ~20 minutes for full pipeline

### Issue #10: Technical Indicator Loader Status
- **File:** `loaders/load_technical_indicators.py`
- **Status:** PASSING locally (confirmed 2026-05-17 12:52:05)
- **Note:** This loader is CPU-bound, no API calls needed
- **Implication:** Price data pipeline is working when symbols exist

### Issue #11: Price Data Loaders Need Alpaca Credentials
- **Files:** `loadpricedaily.py`, `loadetfpricedaily.py`
- **Status:** Need Alpaca API credentials
- **Setup Required:** 
  ```bash
  aws secretsmanager create-secret --name alpaca/api-key --secret-string "..."
  aws secretsmanager create-secret --name alpaca/secret-key --secret-string "..."
  ```
- **Impact:** Can't fetch price data until Alpaca creds configured

---

## PRIORITY 4: INFRASTRUCTURE VERIFICATION NEEDED

### Issue #12: VPC and Networking
- **Status:** Infrastructure code is ready
- **Need to Verify:**
  - VPC endpoints working
  - Private subnet routing to NAT Gateway
  - RDS security group allows Lambda/ECS ingress
  - API Gateway can reach Lambda
- **Test:**
  ```bash
  aws ec2 describe-vpcs --filters "Name=tag:Project,Values=algo"
  aws ec2 describe-security-groups --filters "Name=group-name,Values=algo-*"
  aws rds describe-db-instances --db-instance-identifier algo-stocks-dev
  ```

### Issue #13: CloudFront Distribution
- **Status:** Infrastructure code ready
- **Need to Verify:**
  - S3 origin configured
  - Cache behavior settings correct
  - HTTPS certificate valid
  - Content is actually being served
- **Test:**
  ```bash
  aws cloudfront list-distributions
  curl -I https://<cloudfront-distribution-url>
  ```

### Issue #14: API Gateway Integration
- **Status:** Infrastructure code ready
- **Need to Verify:**
  - Route definitions correct
  - Lambda integrations working
  - CORS enabled if needed
  - Rate limiting configured
- **Test:**
  ```bash
  curl https://<api-gateway-endpoint>/health
  ```

---

## PRIORITY 5: CODE QUALITY ISSUES

### Issue #15: Import Path Consistency
- **Status:** Fixed by run-all-loaders.py but not isolated-run safe
- **Suggestion:** Add `__main__.py` to loaders/ directory or document that direct invocation isn't supported
- **Impact:** MINOR - not part of production workflow

### Issue #16: Orchestrator Phase Dependencies
- **Status:** Orchestrator has 7 phases, need to verify phase ordering
- **File:** `algo/algo_orchestrator.py`
- **Check:** Each phase properly gates on previous phase completion
- **Impact:** MEDIUM - data consistency issues if phases run out of order

---

## SUMMARY

### What Works Locally
- ✓ Database schema (init_database.py)
- ✓ Technical indicators loader (no API calls)
- ✓ Config validator (after fix)
- ✓ run-all-loaders.py orchestration script
- ✓ Orchestrator workflow (7 phases defined)

### What Needs Credentials Setup
- All data loaders (waiting on DB password + API keys)
- Price data loaders (Alpaca API credentials)
- SEC/fundamental data loaders (API keys)

### What Needs AWS Setup
- GitHub Secrets configuration
- RDS database initialization
- Lambda deployment
- ECS task scheduling
- Frontend S3/CloudFront verification

### What Needs Testing
- Full loader pipeline end-to-end
- Orchestrator execution (all 7 phases)
- API endpoints
- Frontend functionality
- CloudWatch monitoring/logging

---

## NEXT STEPS (IN PRIORITY ORDER)

1. **IMMEDIATE (TODAY)**
   - [ ] Fix config_validator import (DONE in this commit)
   - [ ] Set up LOCAL_CRED_SETUP.md secrets in AWS Secrets Manager
   - [ ] Test loader orchestration locally: `python3 run-all-loaders.py`

2. **DEPLOYMENT (NEXT)**
   - [ ] Add GitHub Secrets (7 secrets needed)
   - [ ] Trigger `deploy-all-infrastructure.yml` workflow
   - [ ] Verify RDS initialization
   - [ ] Verify Lambda deployment success
   - [ ] Verify ECS tasks are registered

3. **VALIDATION**
   - [ ] Test each loader individually in AWS
   - [ ] Run full pipeline: `python3 run-all-loaders.py` (AWS environment)
   - [ ] Verify database has 1.5M+ price records
   - [ ] Test orchestrator execution
   - [ ] Test API endpoints
   - [ ] Test frontend

4. **MONITORING**
   - [ ] CloudWatch dashboards showing loader health
   - [ ] Alerts for failed loaders or stale data
   - [ ] Monitor trading algorithm execution
