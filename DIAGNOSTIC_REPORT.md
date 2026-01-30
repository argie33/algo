# COMPREHENSIVE LOADER DIAGNOSTIC REPORT
**Date:** 2026-01-29

---

## EXECUTIVE SUMMARY

Diagnostic analysis of all loaders reveals **THREE CRITICAL ISSUES** affecting at least **10+ loaders**:

1. **Database Connection Errors** - Old RDS endpoint used in 5+ loaders (DNS failures)
2. **Missing Docker Dependencies** - lib directory not copied to 2 loaders
3. **IAM Permissions** - Secrets Manager access denied for all loaders

---

## ISSUE #1: DATABASE CONNECTION FAILURES (CRITICAL)

### Current Status
- **Active RDS Instance:** `stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com` (Available)
- **Old/Non-existent Endpoint:** `rds-stocks.c2gujitq3h1b.us-east-1.rds.amazonaws.com` (MISSING)

### Error Evidence
```
psycopg2.OperationalError: could not translate host name 
"rds-stocks.c2gujitq3h1b.us-east-1.rds.amazonaws.com" to address: 
Name or service not known
```

### Confirmed Failures
| Loader | Error | Evidence |
|--------|-------|----------|
| **econdata-loader** | DNS resolution failure | CloudWatch logs 2026-01-29 13:03:47 |
| **pricedaily-loader** | DNS resolution failure | CloudWatch logs 2026-01-28 02:59:10 |

### Likely Failures (Same Endpoint Configuration)
- aaiidata-loader (all versions)
- annualbalancesheet-loader
- annualcashflow-loader

### Root Cause
Task definitions contain environment variable:
```
DB_HOST=rds-stocks.c2gujitq3h1b.us-east-1.rds.amazonaws.com
```

This endpoint no longer exists in AWS. The correct endpoint is:
```
DB_HOST=stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com
```

### Fix Required
Update the following task definitions' environment variables:
- `aaiidata-loader:*` 
- `annualbalancesheet-loader:*`
- `annualcashflow-loader:*`
- `pricedaily-loader:1`
- `econdata-loader:1`

---

## ISSUE #2: MISSING PYTHON DEPENDENCIES IN DOCKER IMAGES (HIGH PRIORITY)

### Error Evidence
```
ModuleNotFoundError: No module named 'lib'
ModuleNotFoundError: No module named 'db_helper'
```

### Problem 1: TTM Income Statement Loader
**File:** `/home/stocks/algo/Dockerfile.ttmincomestatement`
**Status:** ❌ MISSING `lib` directory copy
**Error:** `from lib.db import get_connection, get_db_config`

**Current Dockerfile:**
```dockerfile
COPY loadttmincomestatement.py .
ENTRYPOINT ["python", "loadttmincomestatement.py"]
```

**Required Fix:**
```dockerfile
COPY lib lib
COPY loadttmincomestatement.py .
ENTRYPOINT ["python", "loadttmincomestatement.py"]
```

### Problem 2: Buy/Sell ETF Weekly Loader
**File:** `/home/stocks/algo/Dockerfile.buysell_etf_weekly`
**Status:** ❌ MISSING `lib` directory copy
**Error:** Imports from local modules but lib not included

**Current Dockerfile:**
```dockerfile
COPY loadbuysell_etf_weekly.py .
ENTRYPOINT ["python", "loadbuysell_etf_weekly.py"]
```

**Required Fix:**
```dockerfile
COPY lib lib
COPY loadbuysell_etf_weekly.py .
ENTRYPOINT ["python", "loadbuysell_etf_weekly.py"]
```

### Problem 3: Buy/Sell ETF Monthly Loader
**File:** `/home/stocks/algo/Dockerfile.buysell_etf_monthly`
**Status:** ❌ MISSING `lib` directory copy

**Required Fix:**
```dockerfile
COPY lib lib
COPY loadbuysell_etf_monthly.py .
ENTRYPOINT ["python", "loadbuysell_etf_monthly.py"]
```

### Note on Other Loaders
- ✓ **feargreed-loader**: HAS pyppeteer (correct)
- ✓ **buysell_etf_daily-loader**: HAS dotenv (correct)

---

## ISSUE #3: IAM SECRETS MANAGER PERMISSIONS (MEDIUM PRIORITY)

### Error Evidence
```
AccessDeniedException: User: arn:aws:sts::626216981288:assumed-role/
stocks-ecs-tasks-stack-ECSExecutionRole-UGhDyOJzoKpz/[task-id] 
is not authorized to perform: secretsmanager:GetSecretValue 
on resource: arn:aws:secretsmanager:us-east-1:626216981288:secret:rds-stocks-secret
```

### Current Configuration
- **ECS Execution Role:** `stocks-ecs-tasks-stack-ECSExecutionRole-UGhDyOJzoKpz`
- **Current Policy:** `AmazonECSTaskExecutionRolePolicy` (standard, no secrets access)
- **Result:** Falls back to environment variables

### Affected Resources
```
arn:aws:secretsmanager:us-east-1:626216981288:secret:rds-stocks-secret
arn:aws:secretsmanager:us-east-1:626216981288:secret:stocks-db-secrets-stocks-app-stack-us-east-1-001-*
```

### Required IAM Policy
Add inline policy to `stocks-ecs-tasks-stack-ECSExecutionRole-UGhDyOJzoKpz`:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "secretsmanager:GetSecretValue",
      "Resource": [
        "arn:aws:secretsmanager:us-east-1:626216981288:secret:rds-stocks-secret",
        "arn:aws:secretsmanager:us-east-1:626216981288:secret:stocks-db-secrets-stocks-app-stack-us-east-1-001*"
      ]
    }
  ]
}
```

### Impact
All loaders attempting to retrieve database credentials from Secrets Manager will fail and fall back to environment variables. This is currently working via environment variables but is not best practice.

---

## ISSUE #4: MISSING EXTERNAL API CONFIGURATION (LOW PRIORITY)

### FRED API Key
- **Loader:** econdata-loader
- **Message:** `FRED_API_KEY not set - using fallback calendar methods only`
- **Severity:** LOW (fallback methods available)
- **Fix:** Add `FRED_API_KEY` to task definition environment variables

---

## AFFECTED LOADERS SUMMARY

### Tier 1: CRITICAL (Confirmed Failures)
| Loader | Issue | Status |
|--------|-------|--------|
| econdata-loader | DNS + IAM Perms + Missing API Key | ❌ FAILING |
| pricedaily-loader | DNS | ❌ FAILING |

### Tier 2: HIGH (Likely Failures - Same Configuration)
| Loader | Issue | Status |
|--------|-------|--------|
| aaiidata-loader | DNS | ⚠️ LIKELY FAILING |
| annualbalancesheet-loader | DNS | ⚠️ LIKELY FAILING |
| annualcashflow-loader | DNS | ⚠️ LIKELY FAILING |
| buysell_etf_weekly-loader | Missing lib directory | ⚠️ LIKELY FAILING |
| buysell_etf_monthly-loader | Missing lib directory | ⚠️ LIKELY FAILING |
| ttmincomestatement-loader | Missing lib directory | ⚠️ LIKELY FAILING |

### Tier 3: MEDIUM (Workaround Exists)
| Loader | Issue | Status |
|--------|-------|--------|
| All loaders | IAM Secrets Manager | ⚠️ WORKING (env vars) |

### Tier 4: WORKING
- analystsentiment-loader
- analystupgradedowngrade-loader
- buysell_etf_daily-loader
- Other newer loaders with correct endpoint

---

## FIX CHECKLIST

### Priority 1: Fix Database Endpoints (Fixes 5 loaders)
- [ ] Update `aaiidata-loader` task definitions to use `stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com`
- [ ] Update `annualbalancesheet-loader` task definitions to use `stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com`
- [ ] Update `annualcashflow-loader` task definitions to use `stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com`
- [ ] Update `pricedaily-loader` task definition to use `stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com`
- [ ] Update `econdata-loader` task definition to use `stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com`

### Priority 2: Fix Missing Docker Dependencies (Fixes 3 loaders)
- [ ] Update `/home/stocks/algo/Dockerfile.ttmincomestatement` - Add `COPY lib lib`
- [ ] Update `/home/stocks/algo/Dockerfile.buysell_etf_weekly` - Add `COPY lib lib`
- [ ] Update `/home/stocks/algo/Dockerfile.buysell_etf_monthly` - Add `COPY lib lib`
- [ ] Rebuild and push Docker images to ECR

### Priority 3: Add IAM Permissions (Affects all loaders)
- [ ] Add secretsmanager:GetSecretValue policy to `stocks-ecs-tasks-stack-ECSExecutionRole-UGhDyOJzoKpz`

### Priority 4: Add Missing API Keys (Low priority)
- [ ] Add `FRED_API_KEY` to econdata-loader environment variables

---

## VERIFICATION CHECKLIST

After applying fixes, verify with:

1. **Database Connectivity:**
   - Check CloudWatch logs for econdata-loader (should not have DNS errors)
   - Check CloudWatch logs for pricedaily-loader (should not have DNS errors)

2. **Docker Dependencies:**
   - Verify new Docker images build successfully
   - Verify no ModuleNotFoundError in logs for ttmincomestatement-loader
   - Verify no ModuleNotFoundError in logs for buysell_etf_weekly-loader
   - Verify no ModuleNotFoundError in logs for buysell_etf_monthly-loader

3. **IAM Permissions:**
   - Should see Secrets Manager access succeed in logs
   - No AccessDeniedException errors

---

## CLOUDWATCH LOG LOCATIONS

All loader logs are stored in CloudWatch Log Groups:
- `/ecs/econdata-loader`
- `/ecs/feargreeddata-loader`
- `/ecs/pricedaily-loader`
- `/ecs/buysell_etf_daily-loader`
- `/ecs/buysell_etf_weekly-loader`
- `/ecs/buysell_etf_monthly-loader`
- `/ecs/ttmincomestatement-loader`
- And others for each loader

---

## RDS CONFIGURATION

| Parameter | Value |
|-----------|-------|
| DBInstanceIdentifier | stocks |
| Engine | postgres |
| Status | available |
| Endpoint | stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com |
| Port | 5432 |
| Security Group | sg-0f3539b66969f7833 |
| VPC | vpc-01bac8b5a4479dad9 |

---

## SECURITY GROUP CONFIGURATION

| Parameter | Value |
|-----------|-------|
| GroupId | sg-0f3539b66969f7833 |
| GroupName | stocks-app-stack-StocksDBSecurityGroup-30t651NxwdDC |
| Port 5432 | Open from 0.0.0.0/0 ✓ |
| Egress | All traffic allowed ✓ |

---

**Report Generated:** 2026-01-29
**Total Loaders Affected:** 10+
**Critical Issues:** 2
**High Priority Issues:** 1
**Medium Priority Issues:** 1
**Low Priority Issues:** 1

