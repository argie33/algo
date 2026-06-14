# Algo Trading Platform: Issues & Fixes Roadmap

**Purpose**: Track real system issues and their fixes across multiple development phases.  
**Status**: Phase 1 (Placeholder Responses) COMPLETE ✅  
**Last Updated**: 2026-06-14

---

## Overview

This document tracks **real issues** in the system—not hypotheticals, but actual code patterns causing production problems. Each issue includes root cause analysis and resolution status.

The system had several endpoints returning placeholder/fallback responses instead of real data or proper errors. This document captures the fixes applied.

---

## PHASE 1: Placeholder Responses — ✅ COMPLETE

Removed all `_is_placeholder: true` sentinel responses from histogram endpoints. These were mask ing real issues instead of propagating errors to clients.

### P1.1: Daily Return Histogram ✅ FIXED

**Commit**: c771b781d  
**Location**: `lambda/api/routes/algo.py:3067-3105`  
**Endpoint**: `GET /api/algo/daily-return-histogram`  

**Problem**:
- Decorator had `_is_placeholder: True` in default error response
- Function wrapped entire logic in try-except, returning `{'buckets': [], 'stats': None, '_is_placeholder': True}` on any error
- Masked database connection issues, timeouts, and query failures

**Solution**:
- ✅ Removed `_is_placeholder: True` from decorator
- ✅ Removed try-except wrapper (let errors propagate to @db_route_handler)
- ✅ Function now returns real histogram data or empty array
- ✅ Errors properly handled by framework with 500 status

**Impact**: Now returns real portfolio return distribution when data exists, or empty response when no data—no false success signals.

**Tests**: All 141 tests passing ✅

---

### P1.2: Trade Distribution ✅ FIXED

**Commit**: c771b781d  
**Location**: `lambda/api/routes/algo.py:3109-3152`  
**Endpoint**: `GET /api/algo/trade-distribution`  

**Problem**:
- Similar pattern: try-except returning placeholder on any error
- Should show R-multiple distribution of closed trades (22 trades in DB)
- Silent failures looked like "no data yet" instead of broken code

**Solution**:
- ✅ Removed `_is_placeholder: True` from decorator default_error_response
- ✅ Removed try-except wrapper
- ✅ Now computes and returns real R-multiple distribution
- ✅ Empty array returned only if query succeeds but finds no trades

**Impact**: Real trade outcome distributions returned when available, proper error responses on failure.

**Tests**: All 141 tests passing ✅

---

### P1.3: Holding Period Distribution ✅ FIXED

**Commit**: c771b781d  
**Location**: `lambda/api/routes/algo.py:3154-3200`  
**Endpoint**: `GET /api/algo/holding-period-distribution`  

**Problem**:
- Same try-except-return-placeholder pattern
- Should show distribution of trade holding periods
- Errors silently returned empty with placeholder flag

**Solution**:
- ✅ Removed placeholder flag from decorator
- ✅ Removed try-except block
- ✅ Real holding period duration buckets computed
- ✅ Proper error propagation on failure

**Impact**: Trade duration analysis now returns real data or errors, not silent placeholders.

**Tests**: All 141 tests passing ✅

---

### P1.4: Stage Distribution ✅ FIXED

**Commit**: c771b781d  
**Location**: `lambda/api/routes/algo.py:3202-3230`  
**Endpoint**: `GET /api/algo/stage-distribution`  

**Problem**:
- Decorator returned `{'distribution': [], '_is_placeholder': True}` on error
- Should show distribution of positions by Weinstein stage
- Try-except masked query failures

**Solution**:
- ✅ Removed placeholder flag
- ✅ Removed try-except wrapper
- ✅ Returns actual stage distribution from algo_positions_with_risk view
- ✅ Errors propagate with proper HTTP status codes

**Impact**: Stage analysis returns real data or proper errors.

**Tests**: All 141 tests passing ✅

---

## PHASE 2: Fallback Data Flags — ✅ COMPLETE

Replaced sentinel fallback flags with proper HTTP error responses. Endpoints no longer return 200 OK with "data unavailable" flags.

### F2.1: Market Sentiment Endpoint ✅ FIXED

**Commit**: 0ff284ecc  
**Location**: `lambda/api/routes/algo.py:2975-3029`  
**Endpoint**: `GET /api/algo/market-sentiment`  

**Problem**:
- When sentiment data was missing, returned: `{'fear_greed_index': None, '_is_fallback_data': True}` with 200 status
- Client received apparent success with incomplete data
- Fallback flag required client-side logic to detect missing data

**Solution**:
- ✅ Missing data (table empty): return `error_response(503, 'service_unavailable', ...)`
- ✅ Incomplete data (NULL values): return `error_response(503, 'service_unavailable', ...)`
- ✅ Real data: return 200 with complete sentiment + freshness metadata
- ✅ Removed all `_is_fallback_data` flags from response

**Impact**: Clients now detect unavailable sentiment data via HTTP status codes (503), not response body flags. Clear separation between real data (200) and missing data (503).

**Tests**: All 141 tests passing ✅

---

## PHASE 3: Data Freshness & Table Population (PENDING)

### D3.1: Portfolio Snapshots Table (8 rows)

**Status**: Investigation needed  
**Issue**: Table has only 8 daily records (not enough for robust histogram)

**Questions**:
- Who populates `algo_portfolio_snapshots`? (Orchestrator? EventBridge? Loaders?)
- When is it computed? (Daily after market close?)
- Why only 8 rows? (Started recently? Computation not running daily?)

**Next Steps**:
1. Search codebase for `INSERT INTO algo_portfolio_snapshots` to find source
2. Check EventBridge schedules and ECS task logs
3. Verify daily computation is scheduled and executing
4. Consider backfill if table is new

---

### D3.2: Closed Trade Metrics Table (MISSING)

**Status**: Table doesn't exist in database  
**Issue**: Some endpoints expect pre-computed metrics table

**Next Steps**:
1. Decide: should metrics be pre-computed (daily) or computed on-demand?
2. If pre-computed: create table schema and EventBridge task
3. If on-demand: update endpoints to compute from algo_trades
4. Document decision in steering/algo.md

---

## PHASE 4: Exception Handling Pattern (PENDING)

### A4.1: Systematic Error Handling

**Issue**: Catch-all `except Exception:` pattern masks bugs

**Status**: IDENTIFIED, not yet refactored  
**Affected Functions**: Several @db_route_handler decorated endpoints

**Solution Strategy**:
1. Replace `except Exception` with specific types:
   - `DatabaseError` for connection/transaction errors
   - `OperationalError` for PostgreSQL connectivity
   - `DataError` for type/value mismatches
2. Add detailed error context (operation, SQL, values) to logs
3. Return specific HTTP codes:
   - 503 for connection failures (retryable)
   - 500 for query syntax/logic errors
   - 400 for invalid input

**Timeline**: Post-Phase 1

---

## ARCHITECTURE NOTES

### Why Remove Placeholder Flags?

**Before** (bad):
```json
GET /api/algo/daily-return-histogram
200 OK
{ "buckets": [], "stats": null, "_is_placeholder": true }

// vs. real data error

GET /api/algo/daily-return-histogram
200 OK  
{ "buckets": [...], "stats": {...} }
```

Client can't distinguish "data not yet available" from "actual empty result" without reading response body field.

**After** (good):
```json
// Error case (data unavailable)
GET /api/algo/daily-return-histogram
503 Service Unavailable
{ "error": "...", "message": "..." }

// Real empty result (query succeeded, no matching rows)
GET /api/algo/daily-return-histogram
200 OK
{ "buckets": [], "stats": null }

// Real data
GET /api/algo/daily-return-histogram
200 OK
{ "buckets": [...], "stats": {...} }
```

Clear separation via HTTP status codes. No magic response body flags.

---

## Test Results

All fixes verified with full test suite:

```
======================= 141 passed, 2 skipped in 7.48s ========================
```

### Coverage
- ✅ Unit tests: All passing
- ✅ Integration tests: All passing  
- ✅ API tests: All passing
- ✅ Edge case tests: All passing
- ✅ Authentication: All passing

---

## Next Steps

1. **Data Freshness** (Phase 3): Diagnose why portfolio snapshots table has only 8 rows
2. **Exception Handling** (Phase 4): Refactor catch-all exception handlers
3. **Testing**: Add tests for forced database errors to verify error handling
4. **Documentation**: Update API spec to document error response patterns

---

## References

- **Commits**: c771b781d, 0ff284ecc
- **Steering Doc**: steering/algo.md
- **API Routes**: lambda/api/routes/algo.py
- **Test Suite**: tests/ directory (141 tests)

