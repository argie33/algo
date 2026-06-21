# Codebase Governance

## QUICK START

AWS credential error? Run: `scripts/refresh-aws-credentials.ps1`

For system architecture and config, see `steering/system.md`.

## STEERING RULES

1. **Content:** System map, procedures, architecture, troubleshooting. NO live status, timestamps, or incident logs.
2. **Clarity:** Complete sentences. Spell out times (4:00 AM ET).
3. **Procedures:** Document "how to debug X" with verifiable steps, never "X is broken" (stale status).
4. **Updates:** Code changes + steering updates in same commit. No async updates.

## Where Information Goes

| What | Where | Why |
|------|-------|-----|
| System design, procedures, config | `steering/system.md` | Single source of truth |
| Current state, errors happening now | GitHub Actions logs, AWS console | Real-time |
| What happened and why | `git log` with good commit messages | Permanent record |

**NEVER in steering:** Live status, timestamps, incident logs, "as of", blockers.

## Code Cleanliness (Pre-Commit Enforced)

**Blocks commits:**
- `.env` files (use AWS Secrets Manager)
- `pdb`, `ipdb`, `breakpoint()` left in code
- `print()` statements in library code (use logging)
- Files > 1MB (binaries, artifacts)

**Allowed:**
- `print()` in: `algo_loader_*.py`, `algo_daily_report.py`, `scripts/`, `tests/`

**Type checking & imports (enforced):**
- Type errors from mypy BLOCK commits
- Code must be importable (no NameError)
- Before committing: `python -m mypy <file>.py --ignore-missing-imports`

## Error Handling & Exception Hierarchy (Unified Standard)

**Exception Base:** All exceptions inherit from `AlgoError` (see `algo/exceptions.py`)
- Provides: category (TRANSIENT/PERMANENT/DATA_QUALITY), retry eligibility, recovery suggestions
- API responses use `.to_dict()` for structured error info
- Never silently default to None/0/{}—fail loudly with actionable errors

**When to Use Each Exception:**
- `DataLoadError`: Failed to fetch data from database, API, files. Set `retry_eligible=True` for network issues, `False` for schema issues
- `ValidationError`: Field missing, type error, or business logic violation
- `ConfigError`: Configuration key missing or invalid (never recoverable)
- `CircuitBreakerError`: Too many failures—automatic retry will wait for recovery
- `PortfolioError`: Portfolio/cash/position state inconsistency
- `PositionError`: Position-specific trading error

**Error Handling Patterns:**

**Pattern 1: Fail-Fast (Critical Data)**
```python
# For critical data (prices, portfolio value, config)
try:
    value = fetch_data(...)  # Returns dict or raises DataLoadError
except DataLoadError as e:
    logger.error(f"Critical data unavailable: {e.message}")
    raise  # Let orchestrator decide retry
```

**Pattern 2: Graceful Degradation (Optional Enrichments)**
```python
# For optional data (VIX, put/call, yield curve)
try:
    vix = fetch_vix_data(...)
except DataLoadError as e:
    logger.warning(f"VIX unavailable, continuing without: {e.message}")
    vix = None  # Continue with None, signal handles it
```

**Pattern 3: Validation with Context**
```python
# Never use .get() defaults—validate explicitly
if symbol is None or symbol == "":
    raise ValidationError(
        field="symbol",
        value=symbol,
        expected="non-empty string",
        context={"source": "API response"}
    )
```

**Error Responses in APIs:**
- On validation/data error: Return `{"_error": "message", "_context": {...}}`
- Never mix error dict with success fields (no `{"_error": "...", "field1": None, ...}`)
- Client checks `has_error(data)` before accessing fields
- Dashboard panels use error boundary: `if has_error(data): return error_panel()`

## Documentation Lifecycle

**Steering docs** (`steering/system.md`): PERMANENT only.
- ✅ Architecture, procedures, thresholds, troubleshooting
- ❌ Status, incident logs, "completed/fixed" with dates

**Memory files** (`.claude/projects/*/memory/*.md`): Actionable NOW or delete.
- ✅ Ongoing feedback, current context, references
- ❌ Historical incidents, completed fixes (they're in git log)

**Rule:** After a fix ships → delete the memory file. Git log is the record.

## Security Baseline

- NO `.env` files. Ever.
- Credentials: AWS Secrets Manager (production), PowerShell profile (local)
- CI: GitHub Secrets for deploy tokens only
- Rotate quarterly (first Monday), immediately if leaked
- Auditable: All secrets in Secrets Manager, never in code or config files

See `steering/system.md` → **Credentials & Secrets** for procedures.

## Dashboard API Validation Strategy

**Problem:** API responses can drift from expected schema. Old approach: Dashboard panels use 775+ `.get()` calls with None defaults, silently masking missing fields and showing placeholder data.

**Solution:** Fail-fast strategy at all layers prevents schema drift and hidden failures.

**Three-Layer Architecture:**

1. **API Boundary** (`api_data_layer.py:api_call()`): All API calls validated before returning
   - Implements retry logic with exponential backoff
   - Circuit breaker pattern prevents hammering downed APIs
   - Caches responses for fallback during outages
   - On failure: returns `{"_error": "message"}` only

2. **Endpoint Validators** (`response_validators.py`): 15+ validators for critical endpoints
   - Portfolio, Performance, Positions, Trades, Signals
   - Markets, Last-Run, Risk Metrics, Config
   - Health, Circuit Breakers, Sector Rotation
   - On validation failure: returns `{"_error": "message"}` to halt processing

3. **Fetchers** (`fetchers.py`): Enforce fail-fast, NO fallback dictionaries
   - Check `_is_api_error(data)` → return error dict immediately, no placeholder fields
   - Validate critical fields (e.g., Markets requires SPY & VIX)
   - On stale data (>freshness threshold) → return `{"_error": "...", "_data_stale": True}`
   - On missing required fields → return `{"_error": "..."}` 
   - On exception → return `{"_error": "..."}` (never {"_error": "...", field1: None, field2: None, ...})

**Key Rule:** Fetchers return ONLY `{"_error": "message"}` on failure, NO fallback structures with None values. This surfaces data issues immediately in the error panel.

**Critical Endpoints (Must Never Be None):**
- Portfolio: `total_portfolio_value`, `total_cash`, `position_count`
- Performance: `total_trades`, `winning_trades`, `losing_trades`
- Markets: `spy_close`, `vix_level` (both required for position sizing)
- Last-Run: `run_id`, `success`

**When Adding New Endpoints:**
1. Update `shared_contracts/dashboard_api_contract.py` with schema
2. Add validator in `tools/dashboard/response_validators.py`
3. Register endpoint path in `VALIDATORS` mapping
4. In fetchers.py: validate critical fields BEFORE returning success
5. Return only `{"_error": "..."}` if validation fails (no fallback fields)
6. Document which fields are critical (must never be None)

**Panel Best Practices:**
- Always check `error_boundary.has_error(data)` first (returns True if `_error` set)
- If error: display `error_boundary.error_summary_panel()` to user
- Only access fields if no error (validation guaranteed they exist)
- Use direct access for critical fields: `data["field_name"]`
- Use `.get()` only for truly optional fields

## Data Loader Outage Handling - Standardized Circuit Breaker Pattern

**Problem**: Loaders handle API outages inconsistently—some fail fast, some use stale cache silently, some degrade gracefully. Users can't distinguish between fresh data and 9-day-old VIX.

**Solution**: Three-tier circuit breaker pattern per `steering/circuit_breaker_patterns.md`:

1. **CRITICAL DATA** (VIX, portfolio value, prices): Fail-fast, no stale cache
2. **REQUIRED DATA** (technical indicators, financials): Fail with context, retry later
3. **OPTIONAL ENRICHMENTS** (put/call, yield curve): Graceful degradation, warn, continue with None

**When Adding/Modifying Loaders**:
1. Identify data criticality: Is it used for position sizing? (CRITICAL), computation? (REQUIRED), or enrichment? (OPTIONAL)
2. Use `CircuitBreaker` from `utils.infrastructure.circuit_breaker` for consistent retry/recovery
3. Use `FreshnessValidator` from `utils.validation.data_freshness` to prevent stale data usage
4. Document criticality in loader docstring
5. For OPTIONAL data: always check for None before using; for CRITICAL/REQUIRED: let exceptions propagate to orchestrator

**Example**:
```python
from utils.infrastructure.circuit_breaker import CircuitBreaker, DataImportance

self._vix_breaker = CircuitBreaker(
    name="yfinance_vix",
    importance=DataImportance.OPTIONAL  # Missing is OK, continue with None
)

vix = self._vix_breaker.execute(
    fetch_func=lambda: self._fetch_vix_data(start, end),
    fallback_value={}
)
```

See `steering/circuit_breaker_patterns.md` for full implementation guide, migration timeline, and testing procedures.

## Circuit Breaker Consolidation & Governance

Three circuit breaker implementations exist in the codebase. **Use the canonical version for new code:**

| Implementation | Purpose | Use Case | Status |
|---|---|---|---|
| `utils.infrastructure.circuit_breaker:CircuitBreaker` | General-purpose data loader outage handling | All new code, all data loaders | **CANONICAL** ✅ |
| `algo.risk.circuit_breaker:CircuitBreaker` | Pre-trade risk management gate | Risk checks before new position entry | Domain-specific |
| `utils.external.yfinance_circuit_breaker:YFinanceIPCircuitBreaker` | Distributed rate-limit coordination | yfinance IP bans across ECS tasks | Specialized |

**Which to use:**
- **Adding a data loader or fetching API data?** → Use `utils.infrastructure.circuit_breaker:CircuitBreaker` with `DataImportance` enum
- **Adding trading risk limits?** → Use `algo.risk.circuit_breaker:CircuitBreaker` and call it from `phase2_circuit_breakers.py`
- **Calling yfinance across multiple containers?** → Use `utils.external.yfinance_circuit_breaker:get_circuit_breaker()`

**Old simple circuit breaker removed**: `utils.contexts:CircuitBreaker` was a simple failure counter with basic recovery. It has been removed as redundant (canonical version is more robust).

## Response Validator Architecture

**See `steering/api_validation_strategy.md` for comprehensive validation strategy, migration timeline, and implementation patterns.**

**Two validators serve different purposes — do not conflate:**

1. **Dashboard Validator** (`tools/dashboard/response_validators.py`) — CANONICAL for dashboard
   - Specialization: 15+ endpoint-specific validators with business logic
   - Approach: Fail-fast with StrictValidationError (prevents silent data corruption)
   - Integration: Uses `safe_float()/safe_int()` from `tools/dashboard/data_validation.py`
   - Used by: Dashboard API data layer (`tools/dashboard/api_data_layer.py`)
   - Purpose: Validate inbound API responses at dashboard boundary

2. **Lambda Validator** (`shared_contracts/response_validator.py`) — CANONICAL for Lambda API routes
   - Specialization: Generic schema-based validation against contract schemas
   - Approach: Configurable strict/permissive with boolean return values
   - Integration: No external validation utilities (self-contained)
   - Used by: Lambda API routes for outbound response validation (`lambda/api/routes/utils.py`)
   - Purpose: Validate outbound responses conform to published API contract

**When adding endpoints:**
- Dashboard: Add specialized validator in `tools/dashboard/response_validators.py`, register in `VALIDATORS` dict
- Lambda API: Update schema in `shared_contracts/dashboard_api_contract.py`, optionally add to `ResponseValidator`

**Do NOT:**
- Use Lambda validator in dashboard code
- Use dashboard validator in Lambda routes
- Conflate the two for the same endpoint
