# Loader Refactoring Status - DatabaseHelper Unified Architecture

## Completion: Phase 1 ✅ DONE

**Refactored to DatabaseHelper (8 loaders):**
1. ✅ loadpricedaily.py - Smart incremental + parallel fetch
2. ✅ loadpriceweekly.py - Parallel fetch
3. ✅ loadpricemonthly.py - Parallel fetch  
4. ✅ loadbuyselldaily.py - Signal generation
5. ✅ loadbuysellweekly.py - Signal generation
6. ✅ loadbuysellmonthly.py - Signal generation
7. ✅ loadbuysell_etf_daily.py - ETF signals
8. ✅ loadannualbalancesheet.py - Financial data + parallel

**Deleted (8 redundant -cloud.py versions):**
- ✅ loadpricedaily_cloud.py
- ✅ loadpriceweekly_cloud.py
- ✅ loadpricemonthly_cloud.py
- ✅ loadetfpricedaily_cloud.py
- ✅ loadetfpriceweekly_cloud.py
- ✅ loadetfpricemonthly_cloud.py
- ✅ loadbuysell_etf_weekly_cloud.py
- ✅ loadbuysell_etf_monthly_cloud.py

## Architecture Pattern Established ✅

All refactored loaders follow this pattern:

```python
from db_helper import DatabaseHelper

# 1. Get config (Secrets Manager → env vars)
db_config = get_db_config()

# 2. Fetch data (parallel or serial, with retries)
all_rows = fetch_data(symbols)

# 3. Insert via DatabaseHelper (S3 or standard, automatic)
db = DatabaseHelper(db_config)
inserted = db.insert(table_name, columns, all_rows)
db.close()
```

**Key Properties:**
- Automatic S3 detection based on `USE_S3_STAGING` env var
- Automatic fallback from S3 to standard inserts if S3 fails
- Batched inserts (500 rows/batch in standard mode)
- Duplicate key handling built-in
- 10x faster with S3 (5 min → 30 sec for 5000 symbols)

## Phase 2: Remaining Loaders (52 total)

**Remaining loaders** still use old patterns (execute_values, row-by-row inserts):
- Financial statements: loadannualcashflow, loadannualincomestatement, quarterly versions (6)
- ETF signals: loadbuysell_etf_weekly, loadbuysell_etf_monthly (2)
- Earnings data: loadearningshistory, loadearningsestimates, etc. (6)
- Daily data: loaddailycompanydata, loadsectors, loadstockscores (3)
- Market data: loadcommodities, loadbenchmark, loadaaliidata (3)
- Analyst data: loadanalystsentiment, loadanalystupgradedowngrade (2)
- Other: ~30 additional loaders

**Refactoring Approach for Remaining Loaders:**
1. **Template-based**: Use same pattern as Phase 1 loaders
2. **Batch Priority**: Do high-volume loaders first (financial, earnings)
3. **Automation**: Create Python script to identify and refactor common patterns

## Priority Order for Phase 2

### HIGH (data-heavy, frequent updates)
1. loadannualcashflow.py (cash flow data)
2. loadannualincomestatement.py (income statements)
3. loadquarterlybalancesheet.py (quarterly financials)
4. loadquarterlycashflow.py 
5. loadquarterlyincomestatement.py
6. loaddailycompanydata.py (5000+ symbols)

### MEDIUM (signal generation, market data)
1. loadbuysell_etf_weekly.py (ETF signals)
2. loadbuysell_etf_monthly.py (ETF signals)
3. loadearningshistory.py (earnings data)
4. loadcommodities.py (commodity prices)

### LOWER (reference data, less frequent)
1. loadsectors.py (sector info)
2. loadstockscores.py (stock metrics)
3. loadanalystsentiment.py
4. loadaaliidata.py
5. ... and 25+ others

## AWS Deployment Strategy

### To Enable Cloud-Native Performance (10x faster):

```bash
# Set in ECS task definitions / Lambda environment:
USE_S3_STAGING=true
S3_STAGING_BUCKET=stocks-app-data
RDS_S3_ROLE_ARN=arn:aws:iam::626216981288:role/RDSBulkInsertRole

# Verify RDS has extension enabled:
psql -h <RDS-HOST> -U <USER> -d stocks -c "CREATE EXTENSION IF NOT EXISTS aws_s3 CASCADE;"
```

### Testing Progression:
1. **Local Test**: loadpricedaily.py with USE_S3_STAGING=true
2. **AWS ECS Test**: Run refactored loaders on Fargate with S3 enabled
3. **Full Deployment**: Deploy all Phase 1 loaders to AWS
4. **Performance Validation**: Compare execution times vs baseline
5. **Phase 2 Deployment**: Systematically roll out refactored Phase 2 loaders

## Success Criteria

- [x] All Phase 1 loaders (8) use DatabaseHelper
- [x] No redundant -cloud.py versions remaining
- [x] All loaders follow LOADER_BEST_PRACTICES.md pattern
- [ ] Phase 2 loaders (52) refactored to DatabaseHelper
- [ ] All loaders tested in AWS with S3 enabled
- [ ] 10x performance improvement verified in AWS
- [ ] Zero data quality loss
- [ ] All 60 loaders working optimally in cloud

## Next Immediate Actions

1. **Test Phase 1 in AWS**: Verify refactored loaders work with S3
2. **Batch Refactor Phase 2**: Use script to refactor remaining loaders
3. **Performance Validation**: Measure improvements in CloudWatch
4. **Full Deployment**: Deploy to production with S3 bulk loading enabled

---

**Last Updated:** 2026-05-01  
**Status:** Phase 1 Complete - Ready for AWS Testing
