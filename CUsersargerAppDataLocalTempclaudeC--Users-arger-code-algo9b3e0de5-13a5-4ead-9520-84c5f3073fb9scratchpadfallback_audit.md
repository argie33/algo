# CRITICAL FALLBACK & ERROR HANDLING AUDIT

## Tier 1: CRITICAL VIOLATIONS (Fail-Fast Required)

### Issue #1: optimal_loader.py - `load_global()` Fallback to FileLockManager
**File**: utils/optimal_loader.py (lines 581-612)
**Severity**: CRITICAL
**Problem**: 
- When DynamoDB is unavailable, `load_global()` falls back to FileLockManager with a warning
- Session 282 EXPLICITLY fixed `run()` to NOT do this (lines 416-429 with fail-fast)
- Comments on lines 434-436 state: "Fallback makes situation WORSE, not better"
- INCONSISTENCY: `run()` fails-fast, but `load_global()` still silently degrades

**Impact**: Race condition possible if DynamoDB fails during global loader execution
**Fix**: Apply same Session 282 fix to `load_global()` - fail fast, no FileLockManager fallback

---

### Issue #2: lambda/api/lambda_function.py - Skip Migrations on Credential Fetch Failure
**File**: lambda/api/lambda_function.py (lines 78-97)
**Severity**: CRITICAL
**Problem**:
- Line 79: "Could not fetch credentials... skipping migrations" 
- If migrations fail at startup, Lambda runs in potentially inconsistent state
- No exception raised - just logs warning and returns False

**Impact**: Schema might be missing critical tables, causing runtime errors later
**Fix**: Raise RuntimeError if migrations are skipped, don't continue

---

### Issue #3: lambda/api/dev_server.py - Fallback to Current Directory for Logs
**File**: lambda/api/dev_server.py (lines 174-181)
**Severity**: HIGH
**Problem**:
- If TEMP directory can't be created, falls back to current directory "."
- This masks permission/configuration issues that should be visible
- Log files silently end up in unexpected location

**Impact**: Debugging output lost or misplaced, operator confusion
**Fix**: Fail-fast if log directory can't be created, let caller handle it

---

### Issue #4: lambda/api/dev_server.py - Fallback to localhost on AWS Secrets Manager Failure
**File**: lambda/api/dev_server.py (lines 97-115)
**Severity**: MEDIUM-HIGH (context-dependent)
**Problem**:
- When AWS Secrets Manager fails, falls back to localhost credentials
- This is only okay for development, but code allows it to happen silently in production
- ENVIRONMENT variable is only checked on line 20-25, not during credential load

**Impact**: Could cause silent connection to wrong database if AWS config is incorrect
**Fix**: Check ENVIRONMENT and only allow fallback in dev mode; raise error in production

---

## Tier 2: WARNING-LEVEL ISSUES (Degradation But Not Silently Fatal)

### Issue #5: optimal_loader.py - False Fallback for expected_symbols=None
**File**: utils/optimal_loader.py (line 936)
**Severity**: MEDIUM
**Problem**:
- Line 936: "expected_symbols is None - using 0 as fallback (data completeness unknown)"
- This masks a bug - expected_symbols should NEVER be None
- Comment says "data completeness unknown" but we still proceed

**Impact**: Confuses loader completion tracking
**Fix**: Raise RuntimeError if expected_symbols is None instead of silently using 0

---

### Issue #6: dashboard/api_data_layer.py - Stale Cache Fallback Removed But Comment Remains Misleading
**File**: dashboard/api_data_layer.py (line 560)
**Severity**: LOW
**Problem**:
- Line 560: "If an operator wants to trade with stale data, that's their choice"
- This comment describes REMOVED fallback behavior (lines 562: "_try_stale_cache_fallback() function... was removed")
- Comment is stale and misleading - should be removed or clarified

**Impact**: Code review confusion, operator misunderstanding
**Fix**: Remove stale comment

---

## Tier 3: STRUCTURAL ISSUES (Better Error Context Needed)

### Issue #7: Multiple warning-on-error patterns without clear escalation
**Files**: 
- lambda/api/lambda_function.py (line 79)
- dashboard/api_data_layer.py (line 203)
- check_system_health.py

**Problem**: Logger.warning() used for initialization errors that should be critical
**Fix**: Use logger.critical() for startup failures, ensure they fail-close

---

## Summary

**Total Issues**: 7
- Critical (require fix): 4
- High (degradation): 2  
- Structural (consistency): 1

**Key Principle Violated**: Session 282 established that DynamoDB failures should NOT have fallbacks
- `run()` correctly implements fail-fast
- `load_global()` still has fallback - INCONSISTENT
- Lambda migrations skipped on error - UNSAFE

