# DATA LOADER STATUS REPORT
**Report Generated:** 2026-01-03 07:20:00 CST

---

## EXECUTIVE SUMMARY

| Metric | Count |
|--------|-------|
| **RUNNING** | 1 |
| **ERROR** | 1 |
| **STOPPED** | 17 |
| **Total Loaders** | 19 |

---

## LOADER STATUS TABLE (Sorted: RUNNING → ERROR → STOPPED)

| Loader Name | Status | Errors Found | Last Activity | Error Type |
|---|---|---|---|---|
| **buysellweekly-loader** | **RUNNING** | 0 | 2026-01-03 13:19:51 | None |
| **stock-scores-loader** | **ERROR** | 14 | 2026-01-03 13:15:30 | Multiple (see below) |
| annualcashflow-loader | STOPPED | 0 | No activity (15m) | N/A |
| annualincomestatement-loader | STOPPED | 0 | No activity (15m) | N/A |
| buyselldaily-loader | STOPPED | 0 | No activity (15m) | N/A |
| buysellmonthly-loader | STOPPED | 0 | No activity (15m) | N/A |
| companyprofile-loader | STOPPED | 0 | No activity (15m) | N/A |
| earningsmetrics-loader | STOPPED | 0 | No activity (15m) | N/A |
| etfpricedaily-loader | STOPPED | 0 | No activity (15m) | N/A |
| factormetrics-loader | STOPPED | 0 | No activity (15m) | N/A |
| latestpricedaily-loader | STOPPED | 0 | No activity (15m) | N/A |
| momentum-loader | STOPPED | 0 | No activity (15m) | N/A |
| positioning-loader | STOPPED | 0 | No activity (15m) | N/A |
| pricedaily-loader | STOPPED | 0 | No activity (15m) | N/A |
| pricemonthly-loader | STOPPED | 0 | No activity (15m) | N/A |
| priceweekly-loader | STOPPED | 0 | No activity (15m) | N/A |
| quarterlyincomestatement-loader | STOPPED | 0 | No activity (15m) | N/A |
| sectors-loader | STOPPED | 0 | No activity (15m) | N/A |
| technicalsdaily-loader | STOPPED | 0 | No activity (15m) | N/A |

---

## CRITICAL FAILURES

### 1. STOCK-SCORES-LOADER - BLOCKED (14 Errors)

**Status:** ERROR - Loader continues to run but with critical failures

**Error Types Found:**

1. **TypeError: unsupported operand type(s) for +=: 'int' and 'NoneType'**
   - Location: `/app/loadstockscores.py`, line 3340
   - Issue: `margin_expansion_score += gross_margin_percentile`
   - Cause: `gross_margin_percentile` is returning `None` instead of numeric value
   - Affected Stocks: ANNX, AMRZ, ALLT, AKTX (multiple)
   - Impact: Cannot calculate margin expansion score for quality factors

2. **NameError: cannot access local variable 'composite_score' where it is not associated with a value**
   - Location: `/app/loadstockscores.py`, score calculation logic
   - Cause: Variable used before assignment when errors occur in margin calculation
   - Affected Stocks: ANNX, AMRZ
   - Impact: Complete score calculation failure for affected stocks

3. **Column "stability_score" does not exist in stock_scores table**
   - Location: Database table schema mismatch
   - Cause: Table definition missing `stability_score` column
   - Affected Stocks: A, AAMI, AAON, and others
   - Impact: Unable to save calculated scores to database
   - Count: Multiple occurrences (pre-existing issue)

4. **Column "bullish_count" does not exist in analyst_recommendations table**
   - Location: SQL query in analyst recommendations fetch
   - Cause: Table schema changed or missing column
   - Affected Stocks: AMS, ADGM, ADP, ADMA, ADT, ANPA, AAP, AAON, and many others
   - Impact: Cannot fetch analyst recommendation sentiment data
   - Count: ~20+ stocks affected

5. **Column "pm.short_interest_pct" does not exist in positioning_metrics table**
   - Location: Positioning metrics percentile ranking query
   - Hint: Column might be named "pm.short_interest_date"
   - Impact: Cannot fetch positioning metrics - CRITICAL DATA REQUIRED
   - Status: Blocks positioning score calculation

**Last Processing Activity:**
- Stock: ADP (as of 2026-01-03 13:15:30)
- Progress: Processing 5313 stocks (estimated completion percentage unknown due to errors)
- Stability Scores: Still being calculated despite database errors
- Issues: Non-blocking errors allowing partial processing to continue

---

## RUNNING LOADERS

### buysellweekly-loader
- **Status:** ACTIVELY RUNNING
- **Last Activity:** 2026-01-03 13:19:51 (within 15 minutes)
- **Current Processing:** MKSI (Weekly timeframe)
- **Progress:** Processing individual symbols through buy/sell signal generation
- **Sample Activity:**
  - Fetching symbol data from database
  - Processing technical signals
  - Calculating trade statistics (Win Rate, Profit Factor, Sharpe Ratio)
  - Inserting trade results with risk percentages
- **Error Status:** NONE - Healthy operation
- **Performance:** Recent stock MGNX processed successfully:
  - Trades: 11, Win Rate: 36.36%, Avg Return: 14.93%, Sharpe: 0.51

---

## STOPPED LOADERS

### All Other Loaders (17 total)
- No log entries in last 15 minutes
- Last activity timestamps not available for most
- Status: Scheduled or completed - currently idle
- No errors detected

**Loaders in STOPPED state:**
- /ecs/pricedaily-loader
- /ecs/buysellmonthly-loader
- /ecs/buyselldaily-loader
- /ecs/sectors-loader
- /ecs/annualcashflow-loader
- /ecs/annualincomestatement-loader
- /ecs/quarterlyincomestatement-loader
- /ecs/factormetrics-loader
- /ecs/positioning-loader
- /ecs/momentum-loader
- /ecs/latestpricedaily-loader
- /ecs/etfpricedaily-loader
- /ecs/technicalsdaily-loader
- /ecs/companyprofile-loader
- /ecs/earningsmetrics-loader
- /ecs/priceweekly-loader
- /ecs/pricemonthly-loader

---

## ROOT CAUSE ANALYSIS

### PRIMARY ISSUES:

1. **Database Schema Mismatches**
   - `stock_scores` table missing `stability_score` column
   - `analyst_recommendations` table missing `bullish_count` column
   - `positioning_metrics` table column naming: `short_interest_pct` → `short_interest_date`
   - These are NOT transient errors - indicative of schema version mismatch

2. **Data Quality Issues**
   - `gross_margin_percentile` returning `None` instead of numeric values
   - Affects margin_expansion_score calculation in Quality factor
   - Impacts multiple stocks in each loader run

3. **Code Logic Issues**
   - Error handling in score calculation creates NameError when exceptions occur
   - Variable `composite_score` used without initialization path after error
   - Suggests incomplete error handling in `/app/loadstockscores.py`

### BLOCKING ISSUES:

1. **CRITICAL:** Missing positioning metrics data prevents score completion
   - Query fails: "column pm.short_interest_pct does not exist"
   - This is marked as CRITICAL DATA REQUIRED in logs
   - Directly blocks positioning score calculation for ALL stocks

2. **CRITICAL:** Analyst recommendation data unavailable
   - ~20+ stocks failing due to missing `bullish_count` column
   - Affects sentiment component of scoring

3. **CRITICAL:** Database schema mismatch for score persistence
   - `stability_score` column missing from `stock_scores` table
   - Unable to save calculated scores even when partial data available

---

## RECOMMENDATIONS

### Immediate Actions:
1. **Fix Database Schema:**
   - Add `stability_score` column to `stock_scores` table
   - Add `bullish_count`, `bearish_count` columns to `analyst_recommendations` table
   - Verify `positioning_metrics` table column names match queries

2. **Fix Data Pipeline:**
   - Debug why `gross_margin_percentile` is returning None
   - Check quality metrics loader for missing data
   - Verify percentile ranking calculations

3. **Fix Error Handling:**
   - Initialize `composite_score` before try block
   - Add proper variable initialization guards
   - Improve exception handling to avoid NameError

### Secondary Actions:
1. Monitor buysellweekly-loader - currently only healthy loader
2. Restart other loaders after stock-scores-loader is fixed (dependencies exist)
3. Add data quality checks before score calculation
4. Implement schema version validation on startup

---

## LOGS ANALYSIS DETAILS

**Report Timestamp:** 2026-01-03 07:20:00 CST
**Data Collection Window:** Last 15 minutes
**Total Log Events Analyzed:** 100+ per loader group
**Error Detection Method:** Grep for ERROR, EXCEPTION, FAILED keywords
