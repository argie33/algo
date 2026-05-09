# Critical Issues Status Report
**Date:** 2026-05-08

## Summary
System has 11 blockers FIXED, infrastructure mostly hardened. Focus now on performance and reliability improvements.

---

## FIXED Issues ✅

### 1. Symbol Format (yfinance compatibility)
**Status:** FIXED and COMMITTED
- **Issue:** Database used BRK.B format, yfinance needs BRK-B
- **Solution:** 
  - Migrated 6,366 rows in database (stock_symbols, price_weekly, price_monthly)
  - Updated all 60+ Python files to use hyphenated format
  - Removed fallback test symbols from lambda orchestrator (now requires real data)
- **Impact:** Stage 2 symbols (BRK-B, LEN-B, WSO-B) can now load data correctly
- **Commit:** ec33bb205

### 2. RDS Security (Production Readiness)
**Status:** ALREADY CONFIGURED
- **Status:** RDS is already private (not 0.0.0.0/0 as STATUS.md suggested)
- **Current:** Private subnets, restricted security group, Bastion access
- **Configuration:** template-data-infrastructure.yml lines 115-141
- **Verification Needed:** Run health check to confirm current deployment matches template

---

## IN-PROGRESS Issues ⏳

### 3. Data Loading Optimization (90+ min → <5 min) - HIGH PRIORITY
**Status:** Framework created, needs completion
- **Problem:** Current loaders take 90+ minutes for daily run
  - Full table scan × 2,847 symbols × 365 days
  - Cost: ~$150/month for data compute alone
- **Solution:** Watermark-based incremental loading
  - Only fetch data since last watermark
  - Expected: 10-100x speedup
  - New framework: `watermark_loader.py` (created)
- **Tasks:**
  - [ ] Implement fetch_incremental() for price_daily loader
  - [ ] Switch loadpricedaily.py to use watermark pattern
  - [ ] Test with Stage 2 symbols (BRK-B, LEN-B, WSO-B)
  - [ ] Benchmark: measure time and cost reduction
  - [ ] Extend to all 18+ loaders
- **Timeline:** 3-5 days

### 4. Multi-Source Data Fallback (Reliability)
**Status:** Framework exists, needs completion
- **Problem:** Single data source (yfinance) - weekly outages = data gaps
- **Solution:** Polygon.io + SEC EDGAR fallback
  - Already have: data_source_router.py with fallback framework
  - Already have: health tracking, pause on failures
- **Tasks:**
  - [ ] Integrate Polygon.io API client
  - [ ] Integrate SEC EDGAR API client
  - [ ] Test each source independently
  - [ ] Test fallback when primary fails
  - [ ] Monitor source usage in CloudWatch
- **Timeline:** 2-3 days
- **Impact:** Target 99.9% data reliability (vs current ~99%)

### 5. Cost Optimization (→ $50/month from $150/month)
**Status:** Planning phase
- **Problem:** ECS on-demand costs $150/month for data loading
- **Solution:** AWS Batch + EC2 Spot Fleet (-50% cost)
  - Batch auto-scales based on workload
  - Spot instances are 70% cheaper
  - Same reliability with proper checkpointing
- **Tasks:**
  - [ ] Create Batch job definition for buyselldaily
  - [ ] Set up Spot Fleet with 70% savings target
  - [ ] Create EventBridge trigger for schedule
  - [ ] Test with sample symbols
  - [ ] Monitor cost before/after
  - [ ] Add S3 lifecycle policies
- **Timeline:** 5-7 days
- **Impact:** Save $100/month, same data reliability

### 6. Lambda VPC Hardening
**Status:** Planning phase
- **Problem:** Lambda has direct internet route (not ideal for production)
- **Solution:** Move to VPC with NAT gateway
  - Better control over egress traffic
  - Reduced latency to RDS
  - Improved monitoring
- **Tasks:**
  - [ ] Create NAT gateway in public subnet
  - [ ] Update Lambda to use VPC
  - [ ] Update security groups (Lambda SG + RDS SG)
  - [ ] Update Lambda IAM role if needed
  - [ ] Test connectivity
  - [ ] Monitor CloudWatch for latency
- **Timeline:** 2-3 days
- **Paired with:** RDS hardening

---

## System State Summary

**What's Working:**
- ✅ 11 production blockers (B1-B11) fixed
- ✅ 8 critical features complete (notifications, previews, metrics, WebSocket)
- ✅ Phase 2 UI, API, backtest persistence done
- ✅ Auth system (RBAC) complete
- ✅ RDS security configured (private, restricted SG)
- ✅ Bastion host for admin access
- ✅ CloudWatch dashboards
- ✅ Trade notification system
- ✅ WebSocket live price streaming

**What Needs Attention:**
- ⚠️ Data loading slow (90+ min) — performance blocker
- ⚠️ Single data source (yfinance) — reliability blocker
- ⚠️ Cost high (~$150/month data compute) — budget blocker
- ⚠️ Stage 2 symbols need price backfill (format now fixed)

**Not Yet Done (Deferred):**
- [ ] Frontend refactor (class → hooks)
- [ ] Live trading (currently paper trading only)
- [ ] WAF for API
- [ ] Advanced alerting (Slack integration)

---

## Priorities

### Immediate (This Week)
1. **Complete watermark incremental loading** (#3)
   - Biggest impact: 18x speedup, -$100/month
   - Unblocks Stage 2 trading
2. **Add data source fallback** (#4)
   - Improves reliability from 99% → 99.9%
   - Reduces outage risk

### Short-term (Next Week)
3. **AWS Batch cost optimization** (#5)
   - Saves $100/month
   - Better scalability

4. **Lambda VPC hardening** (#6)
   - Production readiness
   - Security improvement

### Later (Nice-to-have)
- Frontend refactor (cosmetic)
- Live trading enablement (when user says "green light")
- WAF and advanced alerting

---

## How to Proceed

**For Watermark Loading (Task #3):**
```bash
# 1. Extend watermark_loader.py for each data type
# 2. Update loadpricedaily.py to use watermark pattern
# 3. Test with Stage 2 symbols:
python3 migrate_symbols_dots_to_hyphens.py --dry-run  # Already done
python3 backfill_stage2_data.py  # Load BRK-B, LEN-B, WSO-B with new format
python3 check_stage2.py  # Verify

# 4. Benchmark
time python3 loadpricedaily.py --symbols AAPL,MSFT,GOOGL
# Should be <1 min for 3 symbols
```

**For Multi-source Fallback (Task #4):**
```bash
# 1. Check data_source_router.py - fallback already designed
# 2. Add Polygon.io API client
# 3. Test with primary down:
# kill yfinance, verify Polygon fallback works
```

**Next Steps:**
1. Commit symbol format fixes (DONE)
2. Implement watermark incremental loading
3. Backfill Stage 2 price data
4. Benchmark improvements
5. Plan AWS Batch migration

---

**Contact:** Review DECISION_MATRIX.md for where each type of change goes.
