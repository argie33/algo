# 📊 Data Loading Strategy: Complete Assessment

**Current Date**: April 23, 2026  
**Status**: Database ~15% populated, UI non-functional

---

## 🔴 Current State Analysis

### Database Populated vs. Expected
| Table | Current | Expected | Gap |
|-------|---------|----------|-----|
| price_daily | 307K | 22.2M+ | 97% missing |
| stock_symbols | 4,967 | 4,996 | ~99% complete |
| momentum_metrics | 4,943 | 4,989 | ~99% complete |
| **stock_scores** | **0** | **4,996** | **100% missing** |
| quality_metrics | 0 | 4,989 | 100% missing |
| buy_sell_daily | 0 | 133K+ | 100% missing |
| buy_sell_weekly | 0 | 24K+ | 100% missing |
| buy_sell_monthly | 0 | 7K+ | 100% missing |
| **sector_ranking** | **0** | **8,334** | **100% missing** |
| **analyst_upgrade_downgrade** | **0** | **1.3M** | **100% missing** |
| All financials (annual/quarterly) | 0 | 50K+ | 100% missing |

---

## 📋 Critical Blockers

### For UI to Work:
1. ❌ `stock_scores` - Main scoring algorithm results (dependency for all filtering)
2. ❌ `buy_sell_*` signals - Core trading data (daily/weekly/monthly)
3. ❌ `quality_metrics`, `stability_metrics` - Score component data
4. ❌ `analyst_upgrade_downgrade` - Analyst sentiment data
5. ⚠️ `price_daily` - Only 307K of 22M records (1.4% loaded)

### For Full Functionality:
6. Sector & industry rankings/performance
7. Financial statements (annual/quarterly)
8. Technical indicators
9. Economic data

---

## 🚀 Solution: Phased Loading Strategy

### Phase 1: CRITICAL - UI Core Data (2-3 hours)
**Objective**: Get UI displaying something useful

**Must Run** (in order):
```
1. loadpricedaily.py          → price_daily (22.2M records)
2. loadstockscores.py         → stock_scores (4,996 records) **BLOCKING**
3. loadbuyselldaily.py        → buy_sell_daily (133K records)
4. loadfactormetrics.py       → quality/growth/value metrics
5. loadanalystupgradedowngrade.py → analyst data (1.3M records)
```

**Why This Order:**
- Stock scores depend on prices
- Buy/sell signals depend on prices & scores
- Factor metrics (quality/stability/positioning) depend on data availability
- Analyst data is relatively independent

**Execution**:
```bash
# Sequential - ~1 hour per loader worst case
python3 loadpricedaily.py
python3 loadstockscores.py
python3 loadbuyselldaily.py
python3 loadfactormetrics.py
python3 loadanalystupgradedowngrade.py
```

### Phase 2: Functional - Trading Signals (1-2 hours)
**Objective**: Full timeframe signal coverage

```
6. loadbuysellweekly.py       → buy_sell_weekly (24K records)
7. loadbuysellmonthly.py      → buy_sell_monthly (7K records)
8. loadtechnicalindicators.py → technical_data_daily
```

### Phase 3: Complete - Financial Data (3-4 hours)
**Objective**: Full historical analysis capability

```
9. Annual financials (3 loaders)
10. Quarterly financials (3 loaders)
11. Sector/industry rankings (2 loaders)
12. Economic indicators
13. All ETF signals (3 loaders)
```

### Phase 4: Optional - Enhancement Data
- News sentiment (API-limited)
- Options chains (sparse coverage)
- Earnings history/surprises
- Calendar events

---

## ⚡ Optimization Strategies

### For Local Loading:
1. **Sequential Execution** (safe, proven)
   - One loader at a time
   - Prevents system crashes
   - Easy to debug failures
   - ~8-10 hours total time

2. **Parallel Execution** (faster, riskier)
   - Run Phase 1 loaders in parallel (5 processes)
   - Monitor system RAM/CPU
   - ~2-3 hours instead of 8-10
   - Requires more memory

3. **Smart Batching**
   - Load price data in symbol chunks (1000 at a time)
   - Prevents single massive query
   - Avoid OOM on 4GB RAM systems

### For AWS Deployment:
1. **ECS Task Parallelization**
   - Run independent loaders in parallel ECS tasks
   - Lower cost (shorter execution time)
   - Better resource utilization
   - ~1-2 hours instead of 8-10

2. **S3 Staging**
   - Loaders write to S3 instead of DB directly
   - Batch insert 100K records at a time
   - Avoid timeout on large imports
   - Better observability (progress tracking)

3. **RDS Considerations**
   - Increase max_connections for parallel loaders
   - Use connection pooling
   - Monitor CloudWatch metrics
   - Budget for enhanced monitoring

---

## 📊 Data Dependencies Map

```
price_daily
    ├─→ stock_scores (needs price history)
    │     ├─→ quality_metrics
    │     ├─→ momentum_metrics ✅ (already loaded)
    │     ├─→ stability_metrics
    │     └─→ positioning_metrics
    │
    ├─→ buy_sell_daily (needs scores)
    │     ├─→ buy_sell_weekly
    │     └─→ buy_sell_monthly
    │
    └─→ technical_indicators (independent)

analyst_upgrade_downgrade (independent)
stock_symbols ✅ (already loaded)
```

---

## ✅ Execution Checklist

### Before Loading:
- [ ] Backup current database (pg_dump)
- [ ] Verify disk space (need ~40GB for 311M records)
- [ ] Check RAM availability (ideally 8GB+)
- [ ] Verify API keys in environment (ALPACA, FRED optional)
- [ ] Set timeout in loadstocksymbols.py (already done in commit 583b809c8)

### Phase 1 Execution:
- [ ] `python3 loadpricedaily.py` (log to file)
- [ ] Verify price_daily row count: `SELECT COUNT(*) FROM price_daily`
- [ ] `python3 loadstockscores.py`
- [ ] Verify stock_scores: `SELECT COUNT(*) FROM stock_scores`
- [ ] `python3 loadbuyselldaily.py`
- [ ] `python3 loadfactormetrics.py`
- [ ] `python3 loadanalystupgradedowngrade.py`

### Validation:
- [ ] Test local API: `curl http://localhost:3001/api/stocks`
- [ ] Open frontend: `http://localhost:3001`
- [ ] Verify stock screening works
- [ ] Spot-check signal accuracy vs prices

---

## 🏗️ Architecture Recommendations

### Current Gap:
- Loaders exist but haven't been orchestrated
- No error recovery (failures need manual restart)
- No progress tracking across multiple loaders
- No validation between loader dependencies

### Recommended:
1. **Loader Orchestration Script**
   ```python
   # orchestrate.py
   loaders = [
       ('loadpricedaily.py', ['price_daily']),
       ('loadstockscores.py', ['stock_scores']),
       # ... etc
   ]
   
   for loader, tables in loaders:
       run_loader(loader)
       validate_tables(tables)  # Check row count
       on_failure: skip or retry
   ```

2. **Progress Tracking**
   - Log to `loaders.log`
   - Insert to `last_updated` table
   - Dashboard for real-time status

3. **Deployment Pipeline**
   - GitHub Actions trigger on `git push`
   - Parallel ECS tasks in AWS
   - Auto-rollback on validation failures
   - Slack notifications

---

## 📈 Expected Timeline

| Phase | Duration | When Ready |
|-------|----------|-----------|
| Phase 1 (Critical) | 2-3 hrs | Now |
| Phase 2 (Signals) | 1-2 hrs | +3-5 hrs |
| Phase 3 (Complete) | 3-4 hrs | +6-9 hrs |
| **Full Deployment** | **~10 hrs** | **Today afternoon** |

---

## 🎯 Next Steps

1. **Immediate** (Next 30 min):
   - [ ] Start Phase 1 loading
   - [ ] Monitor in parallel

2. **Short-term** (Next 3 hours):
   - [ ] Complete Phase 1
   - [ ] Verify UI displays data
   - [ ] Test all critical features

3. **Medium-term** (Next 6-9 hours):
   - [ ] Run Phases 2 & 3
   - [ ] Full data set loaded

4. **AWS Deployment**:
   - [ ] Create RDS PostgreSQL instance
   - [ ] Deploy Lambda API
   - [ ] Push frontend to CloudFront
   - [ ] Configure Route53 DNS
   - [ ] Set up monitoring

---

## 💾 Database Dump & Restore

For AWS deployment, use:
```bash
# Local
pg_dump -U stocks stocks > stocks-$(date +%Y%m%d).sql

# AWS
psql -h <rds-endpoint> -U stocks postgres < stocks-20260423.sql
```

Or use AWS Database Migration Service (DMS) for continuous sync.

---

**Recommendation**: Start Phase 1 NOW. Get critical data flowing, validate UI works, then run remaining phases in background.
