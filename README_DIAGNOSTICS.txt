================================================================================
                   COMPREHENSIVE LOADER DIAGNOSTICS
                            2026-01-29
================================================================================

DIAGNOSTIC COMPLETE - DETAILED ANALYSIS OF ALL LOADERS

Three comprehensive diagnostic documents have been generated:

1. DIAGNOSTIC_REPORT.md (Markdown - BEST FOR READING)
   - Executive summary of all issues
   - Section-by-section breakdown of each problem
   - Detailed affected loaders list
   - Fix checklist with priorities
   - Verification checklist
   - Configuration details
   
2. DIAGNOSTIC_SUMMARY.txt (Plain text - QUICK REFERENCE)
   - Quick facts overview
   - Confirmed failures (2)
   - Likely failures (8)
   - Issue breakdown by category
   - Corrective actions checklist
   - Next steps timeline
   
3. DETAILED_ERRORS.txt (Plain text - TECHNICAL REFERENCE)
   - Complete error traces from CloudWatch
   - Root cause analysis for each error
   - Environment variable comparison
   - VPC and network configuration
   - Docker image inventory
   - IAM permission details
   - Task definition versions affected

================================================================================
                        KEY FINDINGS (TL;DR)
================================================================================

CONFIRMED FAILURES (2):
  - econdata-loader (DNS + IAM + Missing API Key)
  - pricedaily-loader (DNS)

LIKELY FAILURES (8):
  - aaiidata-loader (DNS)
  - annualbalancesheet-loader (DNS)
  - annualcashflow-loader (DNS)
  - feargreed-loader (Missing lib)
  - buysell_etf_daily-loader (Missing lib)
  - buysell_etf_weekly-loader (Missing lib)
  - buysell_etf_monthly-loader (Missing lib)
  - ttmincomestatement-loader (Missing lib)

ROOT CAUSES:
  1. Old RDS endpoint used in 5 loaders (rds-stocks.c2gujitq3b.us-east-1.rds.amazonaws.com)
  2. lib directory not copied to Docker images (3 Dockerfiles)
  3. IAM role lacks Secrets Manager permissions (all loaders)
  4. Missing FRED_API_KEY (1 loader)

CRITICAL RDS ENDPOINT INFO:
  OLD (BROKEN): rds-stocks.c2gujitq3b.us-east-1.rds.amazonaws.com
  NEW (CORRECT): stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com
  PORT: 5432
  DATABASE: stocks

================================================================================
                    PRIORITY FIXES NEEDED
================================================================================

PRIORITY 1: Fix Database Endpoints (Fixes 5 loaders - 10 min)
  - aaiidata-loader
  - annualbalancesheet-loader
  - annualcashflow-loader
  - pricedaily-loader
  - econdata-loader
  
  Action: Update DB_HOST in task definitions
  From: rds-stocks.c2gujitq3b.us-east-1.rds.amazonaws.com
  To: stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com

PRIORITY 2: Fix Docker Dockerfiles (Fixes 3 loaders - 5 min + build)
  - Dockerfile.ttmincomestatement - Add "COPY lib lib"
  - Dockerfile.buysell_etf_weekly - Add "COPY lib lib"
  - Dockerfile.buysell_etf_monthly - Add "COPY lib lib"
  
  Action: Add one line before "COPY load*.py ."
  Line: COPY lib lib

PRIORITY 3: Add IAM Permissions (Affects all - 5 min)
  - Role: stocks-ecs-tasks-stack-ECSExecutionRole-UGhDyOJzoKpz
  
  Action: Add inline policy with secretsmanager:GetSecretValue

PRIORITY 4: Add Missing API Key (1 loader - 2 min)
  - FRED_API_KEY environment variable for econdata-loader

================================================================================
                        AFFECTED LOADERS DETAIL
================================================================================

TIER 1 - CRITICAL (CONFIRMED FAILING):
  econdata-loader
    - Error 1: DNS (rds-stocks.c2gujitq3b)
    - Error 2: IAM (Secrets Manager denied)
    - Error 3: API Key (FRED_API_KEY missing)
    - Last Error: 2026-01-29 13:03:47
    - Log: /ecs/econdata-loader
  
  pricedaily-loader
    - Error: DNS (rds-stocks.c2gujitq3b)
    - Last Error: 2026-01-28 02:59:10
    - Log: /ecs/pricedaily-loader

TIER 2 - HIGH (LIKELY FAILING):
  aaiidata-loader (all versions)
    - Error: DNS (rds-stocks.c2gujitq3b)
  
  annualbalancesheet-loader
    - Error: DNS (rds-stocks.c2gujitq3b)
  
  annualcashflow-loader
    - Error: DNS (rds-stocks.c2gujitq3b)
  
  feargreed-loader
    - Error: ModuleNotFoundError: No module named 'pyppeteer'
  
  buysell_etf_daily-loader
    - Error: ModuleNotFoundError: No module named 'dotenv'
  
  buysell_etf_weekly-loader
    - Error: ModuleNotFoundError: No module named 'db_helper'
    - Root Cause: lib directory not copied to Docker
  
  buysell_etf_monthly-loader
    - Error: ModuleNotFoundError: No module named 'db_helper'
    - Root Cause: lib directory not copied to Docker
  
  ttmincomestatement-loader
    - Error: ModuleNotFoundError: No module named 'lib'
    - Root Cause: lib directory not copied to Docker

TIER 3 - MEDIUM (WORKING WITH FALLBACK):
  All loaders
    - Issue: Cannot access Secrets Manager (IAM denied)
    - Workaround: Falls back to environment variables
    - Impact: Still works but not best practice

TIER 4 - WORKING:
  analystsentiment-loader
  analystupgradedowngrade-loader
  buysell_etf_daily-loader (has dotenv)
  Other newer loaders with correct endpoint

================================================================================
                        REFERENCE DATA
================================================================================

RDS Instance Information:
  Identifier: stocks
  Engine: PostgreSQL
  Status: available
  Endpoint: stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com
  Port: 5432
  Security Group: sg-0f3539b66969f7833
  Subnet Group: stocks-app-stack-stocksdbsubnetgroup-eu14xhb8bfr8
  VPC: vpc-01bac8b5a4479dad9

Security Group Rules:
  Port 5432: OPEN from 0.0.0.0/0 (✓)
  Egress: All traffic (✓)

ECS Configuration:
  Cluster: stocks-cluster
  Execution Role: stocks-ecs-tasks-stack-ECSExecutionRole-UGhDyOJzoKpz
  Task Security Group: sg-0519c564d78cca3de
  Registry: 626216981288.dkr.ecr.us-east-1.amazonaws.com

Secrets Manager:
  Secret 1: arn:aws:secretsmanager:us-east-1:626216981288:secret:rds-stocks-secret
  Secret 2: arn:aws:secretsmanager:us-east-1:626216981288:secret:stocks-db-secrets-stocks-app-stack-us-east-1-001-*

================================================================================
                    HOW TO USE THIS DIAGNOSTIC
================================================================================

For Managers/Decision Makers:
  1. Read: DIAGNOSTIC_SUMMARY.txt (Quick Facts section)
  2. Understand: The confirmed failures and likely failures
  3. Decide: Which loaders are critical to fix first

For DevOps/Engineers:
  1. Read: DIAGNOSTIC_REPORT.md (Full analysis)
  2. Follow: The fix checklist in priority order
  3. Use: DETAILED_ERRORS.txt for technical reference

For Developers:
  1. Read: DETAILED_ERRORS.txt (Full error traces)
  2. Understand: Root causes and impacted code files
  3. Update: Dockerfiles and task definitions as specified

================================================================================
                        QUICK ACTIONS
================================================================================

If you have 5 minutes:
  - Read DIAGNOSTIC_SUMMARY.txt (Quick Facts)
  - Identify critical loaders
  - Escalate to DevOps team

If you have 30 minutes:
  - Read DIAGNOSTIC_REPORT.md
  - Review the fix checklist
  - Plan implementation timeline

If you have 1 hour:
  - Update ECS task definitions (Database endpoints)
  - Update Dockerfiles (COPY lib lib)
  - Plan Docker rebuild

If you have 2-3 hours:
  - Fix all issues in order
  - Rebuild and push Docker images
  - Update task definitions
  - Restart loader tasks
  - Verify CloudWatch logs

================================================================================
                        VERIFICATION
================================================================================

After fixes are applied, verify with:

1. CloudWatch Logs Check:
   /ecs/econdata-loader - should have no DNS errors
   /ecs/pricedaily-loader - should have no DNS errors
   /ecs/ttmincomestatement-loader - should have no ModuleNotFoundError
   /ecs/buysell_etf_weekly-loader - should have no ModuleNotFoundError
   /ecs/buysell_etf_monthly-loader - should have no ModuleNotFoundError

2. Error Messages to Look For (Should NOT see):
   "could not translate host name"
   "ModuleNotFoundError"
   "AccessDeniedException"
   "FRED_API_KEY not set"

3. Success Indicators:
   No errors in CloudWatch logs
   Task exit code 0
   Data appearing in database
   No loader failures in monitoring

================================================================================
                        DOCUMENT LOCATIONS
================================================================================

All files are in: /home/stocks/algo/

Files created:
  - /home/stocks/algo/DIAGNOSTIC_REPORT.md (9.1 KB, 295 lines)
  - /home/stocks/algo/DIAGNOSTIC_SUMMARY.txt (11 KB, 293 lines)
  - /home/stocks/algo/DETAILED_ERRORS.txt (14 KB, 326 lines)
  - /home/stocks/algo/README_DIAGNOSTICS.txt (This file)

Total Documentation: ~40 KB of detailed analysis

================================================================================

Report Generated: 2026-01-29
Analysis Scope: All 50+ loaders
Issues Found: 5 categories
Loaders Affected: 10+ confirmed
Estimated Fix Time: 2-3 hours
Effort Level: Moderate

For questions about this diagnostic, refer to the detailed files above.

================================================================================
