# Incomplete Implementations & Stub Code Audit

**Goal:** Identify all places where we have samplers, mocks, placeholders, or incomplete implementations instead of real wired-up functionality.

**Last Updated:** 2026-06-13

---

## 1. EMPTY TEST FUNCTIONS (Not Actually Testing Anything)

### Location: `tests/integration/test_cognito_endpoints.py:154-172`
**Issue:** Four test methods have bodies that are just `pass` — they document tests but don't execute them.

```python
def test_api_health_allows_all(self):
    """Public health endpoint should allow unauthenticated access."""
    pass  # ← NOT TESTING ANYTHING

def test_api_algo_markets_allows_all(self):
    """Public markets endpoint should allow all authenticated users."""
    pass  # ← NOT TESTING ANYTHING

def test_api_scores_allows_all(self):
    """Public scores endpoint should allow all authenticated users."""
    pass  # ← NOT TESTING ANYTHING

def test_api_prices_allows_all(self):
    """Public prices endpoint should allow all authenticated users."""
    pass  # ← NOT TESTING ANYTHING
```

**Severity:** MEDIUM — These are documented but unimplemented tests  
**Fix:** Actually test these endpoints (call them, validate responses)  
**Status:** STUB — intent clear, implementation missing

---

### Location: `tests/unit/test_jwt_flow.py:149`
**Issue:** Test `test_public_endpoints_allow_all_authenticated()` has only a `pass` statement.

```python
def test_public_endpoints_allow_all_authenticated(self):
    """Verify public endpoints allow all authenticated users.
    
    Public endpoints (no group check):
    - /api/health
    - /api/algo/markets
    - /api/scores
    - /api/prices
    - /api/market
    
    These endpoints do NOT call _check_admin_access()
    """
    # Both admin and trader can access public endpoints
    # (These endpoints don't call _check_admin_access at all)
    pass  # ← NO ACTUAL TEST
```

**Severity:** MEDIUM — Documented but not implemented  
**Fix:** Add assertions to verify public endpoints are accessible  
**Status:** STUB

---

## 2. HARDCODED FALLBACK PLACEHOLDER VALUES

### Location: `utils/fallback_registry.py:220-230`
**Issue:** When performance metrics API fails, system returns hardcoded all-zero placeholder data instead of attempting real recovery.

```python
name="hardcoded_defaults",
description="All-zero placeholder metrics: total_trades=0, win_rate=0%, profit_factor=0, sharpe=0, max_drawdown=0%, etc.",
logs_with="[METRICS] CRITICAL - using hardcoded defaults (all zeros)",
hardcoded_values={
    'total_trades': 0,
    'win_rate_pct': 0,
    'profit_factor': 0.0,
    'sharpe_ratio': 0.0,
    'max_drawdown_pct': 0.0,
    # ... etc
}
```

**Severity:** HIGH — Users see fake metrics (all zeros) when API fails  
**Detection:** `/api/algo/performance` returns `_is_placeholder=True` and `_fallback_reason`  
**Issue:** Users can't tell if they're seeing real data or placeholders  
**Real Fix Needed:** 
- Implement retry logic with exponential backoff
- Cache last good performance metrics
- Fall back to database historical view (not zeros)

---

### Location: `lambda/api/routes/algo.py:635-651`
**Issue:** When performance API fails, code returns hardcoded placeholder values.

```python
if perf.get('_error'):
    log_fallback_usage('performance_metrics', 'hardcoded_defaults', FallbackTrigger.PRIMARY_UNAVAILABLE, error=perf.get('_error'))
    fallback_values = get_hardcoded_fallback_values('performance_metrics', 'hardcoded_defaults')
    # ...
    '_is_placeholder': True,
    '_fallback_reason': 'Performance data unavailable - using all-zero placeholder metrics',
```

**Severity:** HIGH  
**Status:** WORKAROUND — functional but shows fake data

---

## 3. ADMIN USER PLACEHOLDER (Not Real Cognito Sub)

### Location: `migrations/versions/014_finalize_user_isolation_admin_setup.py:17-30`
**Issue:** Admin user is `'admin-user'` (hardcoded placeholder) instead of real Cognito `sub`.

```python
def up():
    """Update admin-user placeholder to real Cognito sub in all tables (if available)"""
    with DatabaseContext('write') as cur:
        # Admin's real Cognito sub - will be populated via setup script
        # For now, keep the 'admin-user' placeholder
        # The setup script (scripts/setup-user-isolation.ps1) will populate this after Cognito setup
        # Tables already have 'admin-user' placeholder from previous migrations
        pass  # ← MIGRATION IS A NO-OP
```

### Also: `migrations/versions/013_add_user_isolation.py:47`
```python
admin_cognito_sub = 'admin-user'  # ← HARDCODED PLACEHOLDER
```

**Severity:** HIGH — Admin user is not actually isolated/identified  
**Affected Tables:**
- Users have `created_by = 'admin-user'` instead of real Cognito sub
- Audit logs can't identify who (which real user) made changes
- Real Cognito sub from `setup-user-isolation.ps1` should populate this

**Real Fix Needed:**
1. Update all `'admin-user'` entries to real admin Cognito `sub`
2. Run setup script to capture real admin sub
3. Verify admin can log in with real Cognito credentials

---

## 4. SOCIAL SENTIMENT ENDPOINT NOT IMPLEMENTED

### Location: `lambda/api/routes/sentiment.py:165-170`
**Issue:** `/api/sentiment/social/insights/` endpoint returns 501 (Not Implemented) with placeholder response.

```python
elif path.startswith('/api/sentiment/social/insights/'):
    # Social sentiment not yet implemented
    return json_response(501, {
        'status': 'not_implemented',
        'message': 'Social sentiment feature coming soon. Requires external API integration (not yet configured).'
    })
```

**Severity:** MEDIUM — Endpoint exists but returns "not implemented"  
**Status:** PLANNED BUT NOT WIRED UP  
**Real Fix Needed:**
- Integrate external social sentiment API (Twitter, Seeking Alpha, etc.)
- Document which API (configure endpoint, credentials)
- Implement actual data fetch and transformation
- Add to dashboard if needed

---

## 5. INCOMPLETE VALIDATORS

### Location: `utils/data_validation_registry.py:18`
**Issue:** `safe_int()` has no strict variant implemented.

```python
├─ int: safe_int() [default=0] (strict variant not yet implemented)
```

**Severity:** LOW — Rarely needed strict int validation  
**Status:** DOCUMENTED BUT NOT IMPLEMENTED

---

## 6. SKIPPED CIRCUIT BREAKER CHECKS

### Location: `algo/algo_circuit_breaker.py` (multiple)
**Issue:** Some checks return `skipped` status instead of actual checks.

```python
if not latest or not prior or prior <= 0:
    return {'halted': False, 'reason': f'check skipped (insufficient data)'}
```

**Severity:** LOW — Intended graceful degradation but still hides incomplete data  
**Status:** DESIGNED AS FALLBACK (not a bug, but incomplete)

---

## 7. INCOMPLETE TEST SUITES

### Location: `tests/test_end_to_end_integration.py:208, 417`
**Issue:** End-to-end tests skip verification steps with notes like "will test in AWS".

```python
logger.info("  (Verification skipped - will test in AWS)")
logger.info("  (Health endpoint verification incomplete - will test in AWS)")
```

**Severity:** MEDIUM — Some behaviors not tested locally  
**Status:** PARTIALLY STUBBED

---

## 8. EXECUTION MONITOR MAY SKIP ALPACA

### Location: `lambda/execution-monitor/index.py:97`
**Issue:** If `alpaca_trade_api` package not installed, monitor skips trade checking.

```python
try:
    import alpaca_trade_api as tradeapi
except ImportError:
    return {'error': 'alpaca_trade_api not installed', 'status': 'skipped'}
```

**Severity:** MEDIUM — Missing dependency causes silent skip  
**Status:** DEGRADATION MODE (not tested)

---

## 9. FALLBACK REGISTRY IS SELF-DOCUMENTING BUT...

### Location: `utils/fallback_registry.py`
**Overall Issue:** While this module does document ALL fallback chains clearly, it also reveals that many parts of the system have fallbacks instead of real implementations.

**Examples:**
- VIX data has 3 fallback layers (live API → historical → estimation → neutral 20.0)
- Price loading has watermark-based incremental load fallback
- Market data falls back to previous day's data if today unavailable

**Question:** How many of these fallbacks are actually exercised? Are they hiding real data gaps?

---

## SUMMARY TABLE

| Category | Count | Severity | Status |
|----------|-------|----------|--------|
| Empty Test Functions | 5 | MEDIUM | STUB |
| Hardcoded Placeholders | 2 | HIGH | WORKAROUND |
| Placeholder Admin User | 2 | HIGH | INCOMPLETE |
| Not Implemented Endpoints | 1 | MEDIUM | PLANNED |
| Incomplete Validators | 1 | LOW | DOCUMENTED |
| Skipped Checks | ~10+ | LOW | FALLBACK |
| Incomplete Tests | 2+ | MEDIUM | PARTIAL |
| Fallback Dependencies | 7+ | MEDIUM | DOCUMENTED |

---

## NEXT STEPS

1. **IMMEDIATE (HIGH Priority):**
   - [ ] Replace `'admin-user'` placeholder with real Cognito sub
   - [ ] Implement actual /api/sentiment/social/insights/ endpoint or remove it
   - [ ] Replace hardcoded all-zero performance metrics with real fallback logic

2. **MEDIUM Priority:**
   - [ ] Implement the 5 empty test functions (actually test public endpoints)
   - [ ] Add retry logic to performance metrics API instead of placeholder fallback
   - [ ] Verify alpaca_trade_api is installed or handle gracefully

3. **LOW Priority:**
   - [ ] Implement strict int validator variant
   - [ ] Complete end-to-end test verification (move from AWS-only to local)
   - [ ] Review all 7+ fallback chains to see if they hide real issues
