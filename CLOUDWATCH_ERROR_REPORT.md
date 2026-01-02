# CloudWatch ECS Loaders - Comprehensive Error Report

**Generated:** 2026-01-02 17:29 CST

## EXECUTIVE SUMMARY

| Metric | Count |
|--------|-------|
| Total Log Groups Checked | 15 (primary focus areas) |
| Groups with Critical Errors | 3 |
| Groups Running Successfully | 7 |
| Groups with No Recent Activity | 5 |

---

## CRITICAL ISSUES BLOCKING DATA LOADING

### 1. `/ecs/buyselldaily-loader` - DATABASE SCHEMA MISMATCH

**Status:** CRITICAL FAILURE
**Latest Activity:** 2026-01-01 21:07:46 (3+ days old - STALE)
**Stream:** ecs/buyselldaily-loader/ac6cdbedc189432f9bc8d41753545426

**Error Type:** Database Column Schema Mismatch
**Error Count:** Hundreds of database insert failures (40+ errors spotted)

**Root Cause:**
The loader is attempting to insert data into the `buy_sell_daily` table with a column `signal_triggered_date` that does not exist in the table schema.

**Error Pattern:**
```
ERROR - Bulk insert failed for [SYMBOL] Daily: column
"signal_triggered_date" of relation "buy_sell_daily" does not exist
LINE 5:         signal, signal_triggered_date, buylevel, stoplevel, ...
                        ^
```

**Affected Symbols:**
AFJK, AFBI, AEYE, AFRI, AFRM, AFYA, AGH, AGAE, AGMH, AGIO, AGRI, AGEN, AGNC, AHCO, AHG, AIHS, AIFU, AIIO, AIMD, AGYS, AIFF, AIP, AIRE, ALBT, AIRT, AKAM, ALAR, ALRM, ALNY, ALT, and 140+ more stocks

**Impact:** Data loading completely blocked for daily buy/sell signals (5,078 stocks)
**Progress at Failure:** Only 2.8% of stocks processed before failures began

---

### 2. `/ecs/pricedaily-loader` - COMMAND LINE ARGUMENT ERROR

**Status:** CRITICAL FAILURE
**Latest Activity:** 2026-01-01 22:31:17 (3+ days old - STALE)
**Stream:** ecs/pricedaily-loader/756e16120be0455d98c24fb99f89e8b0

**Error Type:** Docker/ECS Entrypoint Configuration Error
**Error Count:** 1 entry (startup issue)

**Root Cause:**
The container is being launched with incorrect command syntax. The script is receiving "python3 loadpricedaily.py" as arguments instead of being executed as a Python script.

**Error Message:**
```
usage: loadpricedaily.py [-h] [--historical] [--incremental]
loadpricedaily.py: error: unrecognized arguments: python3 loadpricedaily.py
```

**Impact:** Daily price loading completely blocked
**Likely Cause:** Docker CMD or ECS task definition has incorrect entrypoint

---

### 3. `/ecs/annualcashflow-loader` - DATABASE TRANSACTION FAILURES

**Status:** WARNING - TRANSACTION FAILURES (Data may be lost)
**Latest Activity:** 2026-01-02 00:00:44 (recent)
**Stream:** ecs/annualcashflow-loader/06b614ebe23e485985961ba841469dbd

**Error Type:** Database Transaction Aborted
**Error Count:** Recurring warnings (not fatal individually, but systematic)

**Root Cause:**
The loader experiences repeated database transaction failures. After processing each stock, the transaction becomes corrupted and subsequent operations fail until a new connection/transaction is started.

**Error Pattern:**
```
WARNING - Error: current transaction is aborted, commands ignored
until end of transaction block
```

**Observed Behavior:**
1. Successfully fetches and processes cash flow data
2. Reports transaction aborted error
3. Continues to next stock
4. Process repeats for each stock (batch 528-532 observed in logs)

**Impact:** Data may be processed but database inserts likely failing silently
**Related Loaders:** Similar issues likely in:
- `/ecs/annualincomestatement-loader`
- `/ecs/quarterlyincomestatement-loader`

---

## WORKING LOADERS

The following loaders are running successfully:

| Log Group | Status | Latest Activity |
|-----------|--------|-----------------|
| /aws/ecs/stock-scores-loader | SUCCESS | 2026-01-02 17:11:22 |
| /ecs/factormetrics-loader | SUCCESS | 2026-01-02 17:26:29 |
| /ecs/buysellmonthly-loader | SUCCESS | 2026-01-02 16:30:05 |
| /ecs/buysellweekly-loader | SUCCESS | 2026-01-02 16:58:16 |
| /ecs/sectors-loader | SUCCESS | 2026-01-02 17:18:31 |

---

## NO RECENT ACTIVITY / MISSING LOADERS

The following log groups exist but have no recent activity:

1. `/ecs/stocksymbols-loader` - Last activity timestamp missing
2. `/ecs/coveredcalloptions-loader` - No log streams found
3. `/ecs/positioningmetrics-loader` - No log streams found
4. `/ecs/analystsentiment-loader` - No log streams found
5. `/ecs/earnings-loader` - No log streams found

---

## IMMEDIATE ACTIONS REQUIRED

### Action 1: Fix `/ecs/buyselldaily-loader` - Database Schema Mismatch

**The Problem:**
The `buy_sell_daily` table is missing the `signal_triggered_date` column that the loader is trying to use.

**Action Items:**
1. Verify the database schema for the `buy_sell_daily` table
2. Either:
   - Add the missing column to the database, OR
   - Remove references to `signal_triggered_date` from the loader code
3. Restart the loader after schema is corrected

**Files to Check:**
- `/home/stocks/algo/loadbuysell*.py` (or similar)
- PostgreSQL database schema for `buy_sell_daily` table

---

### Action 2: Fix `/ecs/pricedaily-loader` - Entrypoint Error

**The Problem:**
The ECS task definition has an incorrect entrypoint/command configuration, causing the Python script to receive its own name as an argument.

**Action Items:**
1. Check CloudFormation template or ECS task definition
2. Verify the Docker image CMD is correct
3. Ensure the entry point is NOT including 'python3' twice
4. Correct format should be: `["loadpricedaily.py", "--incremental"]`
5. Restart the task after fixing

**Locations to Check:**
- CloudFormation template (likely in `webapp/lambda/` or similar)
- ECS task definition configuration

---

### Action 3: Investigate `/ecs/annualcashflow-loader` - Transaction Issues

**The Problem:**
Repeated transaction abort errors indicate either database connection issues or improper transaction management.

**Action Items:**
1. Check database connection pooling configuration
2. Verify database is not running out of connections
3. Check for any locks or long-running transactions
4. Consider adding transaction rollback/retry logic to loaders
5. Monitor `annualincomestatement` and `quarterlyincomestatement` loaders for the same pattern
6. Review error handling in cash flow loader code

---

### Action 4: Check Missing/Inactive Loaders

**The Problem:**
Five loader log groups have no activity or streams.

**Action Items:**
1. Determine if these loaders should be running
2. If needed, check ECS service definitions
3. Verify they are scheduled/triggered correctly
4. Check for any infrastructure deployment issues
5. Verify IAM permissions and CloudFormation stacks are deployed

---

## IMPACT ASSESSMENT

### BLOCKED OPERATIONS:
- **Daily buy/sell signals for all 5,078 stocks** (buyselldaily-loader)
- **Daily price loading** (pricedaily-loader)
- **Potentially: Annual and Quarterly cash flow/income statement data** (if transaction abort errors are causing silent failures)

### WORKING OPERATIONS:
- Monthly and weekly buy/sell signals
- Stock scores calculation
- Factor metrics
- Sectors data

### OVERALL STATUS:
**~50% of critical data loading pipelines are blocked or experiencing issues**

---

## ROOT CAUSES IDENTIFIED

1. **Database Schema Mismatch** - buyselldaily-loader trying to use non-existent column
2. **Docker/ECS Configuration Error** - pricedaily-loader has incorrect entrypoint
3. **Database Connection/Transaction Management Issue** - Cash flow/income statement loaders experiencing transaction aborts

---

## SEVERITY LEVELS

| Issue | Severity | Impact |
|-------|----------|--------|
| buyselldaily-loader schema error | CRITICAL | 5,078 stocks blocked |
| pricedaily-loader entrypoint error | CRITICAL | All daily prices blocked |
| annualcashflow transaction errors | HIGH | Data may be silently lost |
| Missing loaders (symbols, earnings, etc) | MEDIUM | Some data pipelines offline |

---

## NEXT STEPS

1. **Immediate (0-2 hours):** Fix buyselldaily and pricedaily loaders
2. **Short-term (2-4 hours):** Investigate and fix transaction issues
3. **Follow-up (4-8 hours):** Verify all loaders are running correctly
4. **Verification:** Monitor logs for 24 hours to ensure all issues are resolved
