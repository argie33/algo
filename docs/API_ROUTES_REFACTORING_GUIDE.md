# API Routes DatabaseContext Refactoring Guide

## Status
**In Progress** — Health endpoint pattern established. 21 remaining routes need migration.

## The Pattern - Before and After

### BEFORE (Current - 22 route files)
```python
def handle(cur, path: str, method: str, params: Dict, body: Dict = None, jwt_claims: Dict = None) -> Dict:
    """Handle /api/endpoint*"""
    try:
        cur.execute("SELECT * FROM table")
        result = cur.fetchone()
        # ... more code
```

### AFTER (Target - DatabaseContext pattern)
```python
from utils.database_context import DatabaseContext

def handle(path: str, method: str, params: Dict, body: Dict = None, jwt_claims: Dict = None) -> Dict:
    """Handle /api/endpoint*"""
    try:
        with DatabaseContext('read') as cur:  # 'read' for GET/HEAD, 'write' for POST/PATCH/DELETE
            cur.execute("SELECT * FROM table")
            result = cur.fetchone()
            # ... more code
```

## How to Refactor a Route

1. **Add import** at top of file:
   ```python
   from utils.database_context import DatabaseContext
   ```

2. **Remove `cur,` from function signature**:
   ```python
   # OLD: def handle(cur, path, method, params, body=None, jwt_claims=None)
   # NEW: def handle(path, method, params, body=None, jwt_claims=None)
   ```

3. **Wrap database operations in try block**:
   ```python
   try:
       # Determine mode based on HTTP method
       mode = 'write' if method in ['POST', 'PATCH', 'DELETE', 'PUT'] else 'read'
       with DatabaseContext(mode) as cur:
           # All cur.execute() calls here
   except Exception as e:
       # error handling
   ```

4. **Handle nested functions**: If your route calls helper functions that take `cur`:
   ```python
   # OLD: result = _helper_function(cur, param1)
   # NEW: result = _helper_function(cur, param1)  # Still need to pass cur within the context
   # No change needed! cur is still available within the 'with' block
   ```

## Routes to Refactor (21 remaining)

- [ ] admin.py — Check `_get_runtime_config`, `_set_runtime_config` helper functions
- [ ] algo.py — Large file, multiple helper functions like `_get_algo_trades`, `_get_algo_positions`
- [ ] audit.py
- [ ] contact.py
- [ ] data_coverage.py
- [ ] earnings.py
- [ ] economic.py
- [ ] financials.py
- [ ] industries.py
- [ ] market.py
- [ ] prices.py
- [ ] research.py
- [ ] risk_dashboard.py
- [ ] scores.py
- [ ] sectors.py
- [ ] sentiment.py
- [ ] settings.py
- [ ] signals.py
- [ ] stocks.py
- [ ] trades.py
- [ ] utils.py

## DatabaseContext Behavior

- **'read' mode**: Creates transaction, no auto-commit (safe for reads)
- **'write' mode**: Creates transaction, auto-commits on success, rolls back on exception
- **Timeout**: Default 60s, configurable
- **Cursor type**: RealDictCursor by default (dict-like rows)
- **Connection pooling**: Via RDS Proxy (configured in terraform)

## Testing After Refactoring

1. Run health check: `curl https://api.algo.local/health`
2. Run affected endpoint tests: `npm test`
3. Verify database connectivity hasn't changed
4. Check CloudWatch logs for any new errors

## Why This Refactoring?

- **Consistency**: All database access through single, standardized context
- **Resource safety**: Guaranteed cleanup (connection/transaction)
- **Error handling**: Standardized retry logic and logging
- **Monitoring**: Easy to add metrics/tracing at context manager level
- **Thread safety**: Context manager handles thread-local state

## When to Do This

- [ ] As part of next maintenance cycle
- [ ] Incrementally as routes are modified (don't wait for all-at-once)
- [ ] Prioritize: health → algo → signals (most used endpoints)

## Not Urgent Because

- Current code **works correctly**
- API Lambda tests pass (56/56)
- No performance impact
- Refactoring is for code quality, not bug fix
