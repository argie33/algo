# Code Smell & Technical Debt Audit

**Date:** 2026-07-10  
**Scope:** Full codebase audit focusing on cleanliness and proper patterns  
**Status:** Issues identified and categorized by severity

---

## 🚨 CRITICAL ISSUES (Fix Immediately)

### 1. **44 Diagnostic/Test Scripts Cluttering Repository Root**

**Files:** At root directory
- `check_*.py` (34 files): check_db_data.py, check_etf_loader_status.py, check_gates.py, check_last_run.py, check_loaders.py, etc.
- `verify_*.py` (10 files): verify_all.py, verify_fixes.py, verify_production_readiness.py, etc.
- `diagnose_*.py` (5 files): diagnose_api_issue.py, diagnose_dashboard_data.py, etc.
- `test_*.py` (5 files): test_db.py, test_market_endpoint.py, test_frontend_api.py, etc.
- Other scripts: audit_tables.py, comprehensive_audit.py, database_audit.py, dashboard_run.py, etc.

**Problem:**
- Makes repo look unfinished/cluttered
- Difficult to distinguish production code from tooling
- Violates project structure conventions
- Hinders discoverability of actual source code

**Impact:** High - First impression of codebase quality

**Fix:** Move to organized locations:
- Diagnostic scripts → `scripts/diagnostics/`
- Test scripts → `tests/manual/` or `scripts/test/`
- Verification scripts → `scripts/verify/`
- Migration scripts → `scripts/migrations/`

**Effort:** 1-2 hours

---

### 2. **Code Duplication: Error Handling & Response Formatting**

**Files:** `lambda/api/api_router.py`, `lambda/api/lambda_function.py`

**Duplicated Logic:**
- `_wrap_response()` (api_router.py:250) vs response wrapping in lambda_function.py:1728
- `_add_cors_headers()` (api_router.py:360) vs `get_cors_headers()` (lambda_function.py:713)
- Error categorization appears in both files
- Response formatting with `_json_default()` duplicated
- CORS/headers management duplicated across files

**Problem:**
- Violates DRY principle
- Bugs fixed in one place don't propagate to other
- Creates maintenance burden
- Inconsistent behavior between error paths

**Impact:** High - Bug fixes require changes in multiple places

**Fix:** Extract to shared service module `lambda/api/utils/response_service.py`:
- `wrap_response()`
- `add_cors_headers()`
- `format_json_value()`
- `build_error_response()`

**Effort:** 2-3 hours

---

### 3. **Extremely Long Functions (>200 lines)**

**Files & Line Counts:**
- `lambda/api/lambda_function.py::lambda_handler()` - 431 lines (lines 1371-1803)
- `lambda/api/lambda_function.py::_apply_critical_migrations()` - 256 lines (lines 62-318)
- `lambda/api/api_router.py::_format_handler_error()` - 190 lines (lines 577-767)
- `lambda/api/api_router.py::_wrap_response()` - 107 lines (lines 250-357)

**Problem:**
- Difficult to understand and maintain
- Hard to test individual concerns
- Increased cognitive load for developers
- More likely to contain bugs
- Violates single responsibility principle

**Impact:** Medium-High - Maintenance difficulty

**Fix:** Break down functions:
- `lambda_handler()` → Split into: request validation, auth check, route dispatch, response formatting
- `_apply_critical_migrations()` → Split into: table creation, column migration, validation
- `_format_handler_error()` → Extract to ErrorFormatter class with methods per error type
- `_wrap_response()` → Split into: validation, unwrapping, wrapping

**Effort:** 4-6 hours

---

### 4. **Ad-Hoc Global State Management with Manual Locks**

**Files:** `lambda/api/lambda_function.py`

**Global State Instances:**
```python
_JWKS_CACHE: dict[str, Any] = {}
_JWKS_CACHE_TIME = None
_JWKS_CACHE_LOCK = threading.Lock()

_ALLOWED_ORIGINS_CACHE = None
_ALLOWED_ORIGINS_LOCK = threading.Lock()

_COGNITO_ENABLED = None
_COGNITO_ENABLED_LOCK = threading.Lock()

_CLOUDFRONT_DOMAIN_CACHE = None
_CLOUDFRONT_DOMAIN_CACHE_TIME = None
_CLOUDFRONT_DOMAIN_CACHE_TTL_SECONDS = 86400
_CLOUDFRONT_DOMAIN_LOCK = threading.Lock()
```

**Problem:**
- 5+ separate lock/state pairs
- Inconsistent cache TTL management (10min, 24hr, module load)
- No centralized cache abstraction
- Manual double-check locking pattern repeated
- Error-prone: easy to forget to acquire locks
- Difficult to test (can't easily reset state)

**Impact:** Medium - Thread safety concerns, hard to maintain

**Fix:** Create `CacheManager` class with:
- Centralized lock management
- Consistent TTL handling
- Easy reset for testing
- Unified cache interface

**Effort:** 3-4 hours

---

### 5. **Brittle Route Registration System**

**Files:** `lambda/api/api_router.py`

**Current Approach:**
```python
_OPTIONAL_ROUTE_MODULES = ["algo", "openapi_spec", "logs", ...]  # 30+ hardcoded strings
PUBLIC_HANDLERS = {}
HANDLERS = {}

for module_name in _OPTIONAL_ROUTE_MODULES:
    try:
        module = __import__(f"routes.{module_name}", ...)
        _AVAILABLE_ROUTES[module_name] = module
    except Exception as e:
        _ROUTE_IMPORT_ERRORS[module_name] = error_msg
```

**Problems:**
- Maintains parallel data structures (list, dicts)
- Manual string-based route registration
- Error tracking split across dicts
- Route ordering and precedence implicit in code
- Hard to add new routes (requires editing multiple places)
- Public/private endpoint distinction scattered throughout

**Impact:** Medium - Difficult to extend, fragile

**Fix:** Replace with decorator-based system:
```python
@api_route("/api/algo", public=True)
def handle_algo(cur, path, method, params, body):
    ...

@api_route("/api/admin", public=False)
def handle_admin(cur, path, method, params, body):
    ...
```

Or use configuration file (YAML/JSON) with route definitions.

**Effort:** 4-5 hours

---

## ⚠️ HIGH-PRIORITY ISSUES (Fix Soon)

### 6. **Hardcoded Magic Values Scattered Throughout**

**Occurrences:**
- `_JWKS_CACHE_TTL_SECONDS = 3600` (line 44)
- `_CLOUDFRONT_DOMAIN_CACHE_TTL_SECONDS = 86400` (line 42)
- `cache_ttl = timedelta(minutes=10)` (line 850)
- `timeout=3` (line 546, 866)
- `MAX_REQUEST_BODY_SIZE = 1024 * 100` (line 593)
- `max_retries=0` (line 546)
- Multiple port numbers: 5173, 3000 (lines 706-707)
- Multiple hardcoded origin patterns

**Problem:**
- Difficult to adjust configuration
- Unclear intent of magic numbers
- No single source of truth for timeouts/limits
- Hard to test different configurations

**Impact:** Low-Medium - Configuration management

**Fix:** Create `lambda/api/utils/config_constants.py`:
```python
class CacheConfig:
    JWKS_TTL_SECONDS = 3600
    CLOUDFRONT_DOMAIN_TTL_SECONDS = 86400
    HEALTH_CHECK_TTL_SECONDS = 600

class RequestConfig:
    MAX_BODY_SIZE = 1024 * 100
    STATEMENT_TIMEOUT_SECONDS = 30
    DB_CONNECT_TIMEOUT_SECONDS = 3
```

**Effort:** 1-2 hours

---

### 7. **Inconsistent Error Handling Patterns**

**Patterns Found:**
- Some functions return `(success, error_msg)`
- Others return `(success, data, error_msg)`
- Others raise exceptions
- Others use custom exception types (APIException)
- Some use try/except, others use error tuples

**Files Affected:**
- `lambda/api/lambda_function.py` - multiple patterns
- `lambda/api/api_router.py` - multiple patterns
- Various routes in `lambda/api/routes/`

**Problem:**
- Callers must check different return signatures
- Easy to miss error conditions
- Inconsistent error propagation
- Hard to trace error flow

**Impact:** Medium - Error reliability

**Fix:** Standardize on exception-based error handling:
```python
class APIError(Exception):
    def __init__(self, status_code: int, error_type: str, message: str):
        self.status_code = status_code
        self.error_type = error_type
        self.message = message
```

Use consistent error paths throughout codebase.

**Effort:** 6-8 hours

---

### 8. **Complex Nested Conditionals (7+ levels)**

**File:** `lambda/api/lambda_function.py::require_auth()` (lines 1185-1337)

**Nesting Levels:**
```python
if path in (...):
    is_public = False
else:
    def matches_prefix(...):
        if p == prefix:
            ...
        if p.startswith(...):
            ...
        return False
    is_public = any(matches_prefix(path, prefix) for prefix in PUBLIC_PREFIXES)

if is_public:
    return (False, True, None, None)

if not path.startswith("/api/"):
    return (False, True, None, None)

with _COGNITO_ENABLED_LOCK:
    cognito_enabled = _COGNITO_ENABLED

if not cognito_enabled:
    try:
        from dev_auth import validate_dev_token
        token = get_bearer_token(event)
        if token:
            is_valid, claims, error = validate_dev_token(token)
            if is_valid:
                ...
```

**Problem:**
- Difficult to follow logic flow
- Multiple exit points
- Hidden assumptions
- Hard to unit test

**Impact:** Medium - Maintainability

**Fix:** Extract to separate functions:
```python
def is_public_endpoint(path: str) -> bool:
    ...

def validate_dev_mode_auth(event) -> tuple[bool, dict | None, str | None]:
    ...

def validate_cognito_auth(event) -> tuple[bool, dict | None, str | None]:
    ...
```

**Effort:** 2-3 hours

---

## 📋 MEDIUM-PRIORITY ISSUES (Fix When Convenient)

### 9. **Unused/Minimal Module Files**

**Files:**
- `lambda/api/utils/__init__.py` - likely empty
- `lambda/api/api_utils/__init__.py` - minimal exports
- Multiple `__init__.py` files with only `pass` or imports

**Problem:**
- Creates visual clutter
- Unclear what's exported vs internal
- Makes refactoring harder

**Impact:** Low - Code organization

**Fix:** Remove empty `__init__.py` files (Python 3.3+), add proper exports to necessary ones.

**Effort:** 1 hour

---

### 10. **Global Initialization Side Effects**

**File:** `lambda/api/lambda_function.py` (lines 1341-1368)

**Code:**
```python
if not IMPORT_ERROR:
    env_valid, env_errors, env_warnings = validate_environment()
    # ... multiple operations ...
    with _COGNITO_ENABLED_LOCK:
        _COGNITO_ENABLED = bool(os.getenv("COGNITO_USER_POOL_ID"))
        if not _COGNITO_ENABLED:
            is_production = "AWS_LAMBDA_FUNCTION_NAME" in os.environ
            if is_production:
                raise RuntimeError(...)
```

**Problem:**
- Module-level code has side effects (network calls, file I/O)
- Hard to test (module import triggers side effects)
- Initialization errors crash module load
- Not testable without mocking environment

**Impact:** Low-Medium - Testability

**Fix:** Move initialization to function, call explicitly on Lambda startup.

**Effort:** 2-3 hours

---

### 11. **Unclear Responsibility Separation**

**File:** `lambda/api/lambda_function.py` (431 lines)

**Responsibilities Mixed:**
1. Request routing & dispatching (lines 1546-1684)
2. Authentication & authorization (lines 1550-1556)
3. CORS header handling (lines 1558, 1596, 1619, etc.)
4. JSON parsing & validation (lines 1591-1638)
5. Rate limiting (comment at line 1581)
6. Error formatting (lines 1689-1713)
7. Response formatting (lines 1715-1761)
8. Logging (lines 1548, 1559, 1560, etc.)

**Problem:**
- Single function doing too many things
- Hard to test individual concerns
- Difficult to reuse components
- Changes to one concern affect others

**Impact:** Medium - Maintainability

**Fix:** Split into components:
- `RequestValidator` - parse & validate
- `AuthenticationService` - auth checks
- `ResponseFormatter` - format responses
- `RequestRouter` - route to handlers
- `CORSManager` - CORS logic

**Effort:** 5-7 hours

---

## 🔍 LOW-PRIORITY ISSUES (Code Quality)

### 12. **Repetitive Exception Attribute Extraction**

**File:** `lambda/api/api_router.py` (lines 591-600)

```python
exception_attrs = {}
for attr in ["args", "pgcode", "pgerror", "cursor", "filename", "lineno", "msg"]:
    if hasattr(e, attr):
        try:
            val = getattr(e, attr)
            exception_attrs[attr] = str(val)[:200]
        except Exception as attr_err:
            ...
```

**Problem:**
- Hardcoded list of attributes
- Defensive programming (try/except for each attr)
- Verbose implementation

**Impact:** Very Low - Logging

**Fix:** Use built-in exception introspection or extract to utility function.

**Effort:** 30 min

---

### 13. **Redundant Comments**

**Examples:**
- Line 11: `# Set up imports for Lambda API - ensures routes and api_utils are importable`
- Line 419: `# Issue #11 FIX: Use strict path matching...` (duplicates commit history)
- Multiple "GOVERNANCE" comments that could be in docs

**Problem:**
- Comments duplicating variable/function names
- Issue references belong in commit messages, not code
- Some comments explain "what" instead of "why"

**Impact:** Very Low - Code clarity

**Fix:** Remove redundant comments, keep only "why" comments.

**Effort:** 1 hour

---

### 14. **Overly Defensive Null Checks**

**File:** `lambda/api/lambda_function.py` (lines 1429-1433)

```python
_req_ctx = event.get("requestContext")
_req_ctx = _req_ctx if _req_ctx is not None else {}
http_ctx = _req_ctx.get("http")
http_ctx = http_ctx if http_ctx is not None else {}
```

**Problem:**
- Repetitive pattern
- Could be extracted to utility
- Makes code harder to read

**Impact:** Very Low - Code style

**Fix:** Extract to helper function `get_nested_dict()` or use `dict.get()` with defaults.

**Effort:** 30 min

---

## 📊 SUMMARY

| Severity | Count | Effort | Impact |
|----------|-------|--------|--------|
| CRITICAL | 5 | 12-20 hrs | High |
| HIGH | 3 | 13-18 hrs | Medium-High |
| MEDIUM | 4 | 8-11 hrs | Medium |
| LOW | 4 | 2-3 hrs | Low |
| **TOTAL** | **16** | **35-52 hrs** | - |

---

## 🎯 RECOMMENDED FIX ORDER

**Phase 1 (High Impact, Medium Effort):**
1. Move diagnostic/test scripts to proper directories (2 hrs)
2. Extract shared response/error handling (3 hrs)
3. Replace global state with CacheManager (3-4 hrs)
4. Create configuration constants file (1-2 hrs)

**Phase 2 (Medium Impact):**
5. Break down long functions (4-6 hrs)
6. Standardize error handling (6-8 hrs)
7. Simplify nested conditionals (2-3 hrs)

**Phase 3 (Code Quality):**
8. Improve responsibility separation (5-7 hrs)
9. Fix minor style issues (2-3 hrs)

---

## ✅ VERIFICATION APPROACH

After fixes, verify:
- ✅ All route imports still work (test each /api endpoint)
- ✅ Error handling paths still work (test error scenarios)
- ✅ Auth still enforces (test protected endpoints)
- ✅ CORS still works (test cross-origin requests)
- ✅ No performance regression (compare response times)
- ✅ All tests pass (run CI pipeline)

---

**Generated:** 2026-07-10  
**Status:** Ready for implementation
