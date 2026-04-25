# Critical Issues Found & Status

**Date**: 2026-04-24  
**Last Updated**: Now

---

## FIXED ✅

### 1. Trading Signals Not Displaying
**Status**: ✅ FIXED (commit c3dd09730)  
**Issue**: Frontend was filtering out all 900+ signals because they lacked OHLC price data  
**Root Cause**: `hasRealData()` function required `close` price, but `buy_sell_*` tables only store signal data  
**Fix**: Updated filter to require only symbol, signal type, and strength  
**Impact**: TradingSignals page now shows daily/weekly/monthly signals

---

## IN PROGRESS 🔄

### 2. AWS Lambda CORS Enhancements Removed
**Status**: ⚠️ NEEDS REVIEW  
**Issue**: 52 lines of CORS middleware deleted from `webapp/lambda/index.js`  
**Impact**: 
- Basic CORS still works (via cors middleware)
- AWS Lambda context injection removed
- CloudFront domain support removed  
- Might cause issues in AWS production deployment
**Fix**: Restore AWS-specific CORS enhancements or document why they were removed

### 3. Unusual Package Changes
**Status**: ⚠️ NEEDS INVESTIGATION  
**Issue**: `package.json` modified, `package-lock.json` has 19 line changes  
**Impact**: Unknown - need to check what was added/removed  
**Action**: Review package changes to ensure no security issues

---

## KNOWN ISSUES (Architecture)

### 4. Dual API Implementation
**Status**: ⚠️ NOT FIXED (architectural issue)  
**Details**:
- Two incompatible API servers: `local-server.js` and `webapp/lambda/*`
- Different response formats
- Different database configuration methods
- Different error handling approaches
**Impact**: Causes confusion, deployment ambiguity, maintenance nightmares
**Effort to Fix**: 2-3 days (Phase 1: Unify APIs)

### 5. Inconsistent Database Configuration
**Status**: ⚠️ NOT FIXED  
**Details**:
- Three different ways to load DB config (Secrets Manager, env vars, hardcoded)
- Different connection pooling settings per implementation
- No single source of truth
**Impact**: Race conditions, deployment issues, debugging difficult
**Effort to Fix**: 1 day (centralize config)

### 6. No Unified Response Format
**Status**: ⚠️ NOT FIXED  
**Details**:
- Different endpoints return different response shapes
- Some include timestamps, some don't
- Error responses inconsistent
**Impact**: Frontend must handle multiple formats, no type safety
**Effort to Fix**: 1 day (standardize all responses)

### 7. Missing Data vs Real Data
**Status**: ⚠️ PARTIALLY ADDRESSED  
**Details**:
- Some endpoints return NULL for missing data (good)
- Some return fake defaults like COALESCE(val, 0) (bad)
- Hard to tell if data is real or fallback
**Impact**: Silent data integrity failures, broken analytics
**Action**: Audit all queries for fake defaults

---

## TESTING NEEDED ✋

### 8. Trading Signals Frontend Display
**Status**: ⏳ NEEDS TESTING IN BROWSER  
**Action**: Open TradingSignals page, verify signals display with correct counts

### 9. API Health & Connectivity
**Status**: ⏳ NEEDS TESTING  
**Action**: Test all major endpoints for 500 errors and missing data

### 10. AWS Deployment Path
**Status**: ⏳ NEEDS VERIFICATION  
**Action**: Confirm Lambda deployment still works with CORS changes

---

## Priority for Next Sprint

### High Priority (Do First)
1. ✅ Fix trading signals (DONE)
2. ⏳ Test signals work in browser
3. ⏳ Restore or document CORS changes
4. ⚠️ Check package.json changes for security

### Medium Priority (This Week)
5. ⚠️ Audit database queries for fake defaults
6. ⚠️ Standardize response format across endpoints
7. ⚠️ Add comprehensive error handling

### Low Priority (Architecture Debt)
8. ⚠️ Unify dual API implementations
9. ⚠️ Centralize database configuration
10. ⚠️ Document deployment architecture

---

## Reproduction Steps

### Test Trading Signals Fix
```bash
# 1. Check API returns data
curl http://localhost:3001/api/signals/stocks?timeframe=daily&limit=10

# 2. Open frontend in browser
http://localhost:5173/trading-signals

# Expected: Signals display in table
# Before fix: Empty table (signals filtered out)
# After fix: 20-50 signals visible
```

### Test CORS in AWS
```bash
# Lambda test payload
{
  "path": "/api/signals/stocks",
  "httpMethod": "GET",
  "headers": {
    "origin": "https://d1copuy2oqlazx.cloudfront.net"
  }
}

# Expected: Response includes Access-Control-Allow-Origin header
```

---

## Questions for User

1. **Deployment Model**: Is this Lambda-only? Express.js? Both?
2. **AWS Status**: Is this running in production AWS or local-only?
3. **CORS Removal**: Was CORS enhancement intentionally removed or accidental?
4. **Package Changes**: What was added/removed in package.json?
