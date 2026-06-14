# Connection Pool Underutilization Fix

**Status:** FIXED
**Date:** 2026-06-14
**Impact:** Eliminates connection exhaustion risk when 50+ loaders run concurrently

## Problem

### Original Issue
- 50 loaders running in parallel, each creating 5-10 `DatabaseContext()` instances
- Each context acquires a connection from the pool, then closes it immediately
- With max_connections=20 in the pool, this causes constant acquire/release churn
- Risk: Pool exhaustion under peak load (>20 concurrent contexts = queueing or failures)
- No backpressure: Loaders would fail immediately if pool exhausted

### Numbers
- **Before fix:** 250-500 connection creates/closes per loader run cycle
- **After fix:** 50 connection creates/closes per loader run cycle
- **Reduction:** 80-90% fewer connection operations

## Solution

### Architecture Overview

```
OptimalLoader.run()
  ├─ PooledConnectionManager.acquire()
  │   ├─ PoolSemaphore gates max 10 concurrent loaders (prevents thundering herd)
  │   └─ Gets connection from pool.getconn() with exponential backoff
  │
  ├─ set_pooled_connection(conn)  # Store in context variable for all DatabaseContext calls
  │
  ├─ All DatabaseContext("read"/"write") calls
  │   └─ Check get_pooled_connection() first → reuse instead of acquiring new
  │
  └─ PooledConnectionManager.release()  # Return to pool when done
      └─ set_pooled_connection(None)  # Clear context
```

### New Components

#### 1. `utils/db/pooled_connection_manager.py`
- **PoolSemaphore**: Threading-aware semaphore that gates loader concurrency
  - Max 10 concurrent loaders holding connections
  - Enforces backpressure: blocks/waits instead of failing
  - Leaves 10+ connections in pool for API and internal use
  
- **PooledConnectionManager**: Manages one connection for entire loader lifecycle
  - acquire(): Get from pool with semaphore gating + exponential backoff
  - release(): Return to pool + release semaphore slot

#### 2. `utils/db/pooled_context_var.py`
- Context variables (contextvars.ContextVar) to thread-safely track pooled connections
- set_pooled_connection(conn): Called at loader startup
- get_pooled_connection(): Checked by DatabaseContext on each operation
- has_pooled_connection(): Helper for testing/monitoring

#### 3. `utils/db/pooled_context.py`
- PooledDatabaseContext: Alternative cursor context for pre-acquired connections
- Does NOT close connections (externally managed)
- Still commits/rollbacks transactions properly

#### 4. Modified `utils/db/context.py` (DatabaseContext)
- New: Check for pooled connection first
- If found → reuse (set _externally_managed=True)
- If not found → normal flow (acquire new, will close)
- Exit behavior: Don't close externally-managed connections

#### 5. Modified `utils/optimal_loader.py`
- **run() method**: Acquire at startup, release in finally
- **load_global() method**: Same pattern
- All subloader methods reuse the single connection automatically

## How It Works

### Connection Lifecycle Example

```python
# Sector Ranking Loader
loader = SectorRankingLoader()
stats = loader.run(symbols=['AAPL', 'MSFT'], parallelism=1)

# Inside run():
# 1. Create PooledConnectionManager('sector_ranking')
# 2. conn = manager.acquire()  # Waits for semaphore slot, then gets from pool
# 3. set_pooled_connection(conn)  # Store in context variable

# 4. All sub-operations reuse this connection:
#    with DatabaseContext('read') as cur:  # ← Detects pooled_connection, reuses!
#        cur.execute("SELECT ...")
#
#    with DatabaseContext('write') as cur:  # ← Same, reuses!
#        cur.execute("INSERT ...")

# 5. finally: manager.release()  # Return to pool once

# Total: 1 connection acquired, held for entire loader run, released once
```

## Configuration

### Pool Sizing
- **Pool limits**: SimpleConnectionPool(minconn=2, maxconn=20)
  - minconn=2: Keep 2 warm connections for API
  - maxconn=20: Cap to prevent RDS exhaustion
  
- **Semaphore limits**: PoolSemaphore(max_concurrent=10, timeout_sec=30)
  - Max 10 loaders simultaneously holding connections
  - Remaining 10 connections reserved for API/heartbeat/internal use
  - Timeout 30s for loader to acquire semaphore slot

### Tuning (if needed)
```python
# In PooledConnectionManager: Change this line
_pool_semaphore = PoolSemaphore(max_concurrent=10, timeout_sec=30)

# Increase max_concurrent if you have >10 loaders and pool is underutilized
# Decrease if you see API latency spike (loaders starving API for connections)
# Adjust timeout_sec if loaders consistently timeout waiting for slots
```

## Benefits

| Aspect | Before | After |
|--------|--------|-------|
| Connections per loader | 5-10 creates/closes | 1 create, 1 release |
| Pool pressure | High churn, risk exhaustion | Steady 10 active max |
| Backpressure | None (fail if exhausted) | Graceful queueing with timeout |
| Transaction control | Per-operation (risky) | Loader-level (clean) |
| Connection warmth | Cold each time | Warm for entire run |
| Parallelism | Uncontrolled, can crash | Gated by semaphore |

## Backward Compatibility

✅ **Fully backward compatible:**
- Existing code using DatabaseContext("read"/"write") works unchanged
- Non-loader code continues acquiring fresh connections
- Pooled connection is invisible to normal DatabaseContext usage
- If no loader context set, falls back to normal acquire/release flow

## Testing

### Manual Test
```bash
# Run a loader and check logs
python -m loaders.load_sector_ranking

# Expected logs:
# [sector_ranking] Acquired pooled connection for entire loader lifecycle
# [POOL_SEMAPHORE] sector_ranking acquired slot (1/10 active)
# [DB_CONTEXT] Reusing pooled connection from OptimalLoader
# [sector_ranking] Released pooled connection after loader completion
# [POOL_SEMAPHORE] sector_ranking released slot (0/10 active)
```

### Monitoring
```python
# Check pool status programmatically
from utils.db import get_pool_status
status = get_pool_status()
# {
#   'semaphore': {
#       'active_count': 3,  # Currently 3 loaders holding connections
#       'max_concurrent': 10,
#       'available_slots': 7
#   },
#   'max_concurrent_loaders': 10,
#   'max_pool_connections': 20,
# }
```

## Debugging

### Symptoms and Solutions

**Symptom:** Loader timeout waiting for connection slot
```
[DB_CONNECT] timeout waiting for connection slot (9/10 active, waited 30s)
```
**Cause:** >10 loaders trying to run simultaneously
**Solution:** Reduce loader parallelism or check if a loader is stuck

**Symptom:** Connection not reused (seeing many "Pool exhausted" logs)
```
[DB_POOL] Pool exhausted (attempt 1/3), retrying in 1s
```
**Cause:** Pooled connection context not set (should not happen)
**Solution:** Check if OptimalLoader set/cleared context properly. Review logs for "Acquired pooled connection" message.

**Symptom:** Cursor not being created
```
[DB_CONTEXT_ERROR] Failed to get database connection
```
**Cause:** Connection was released before context creation
**Solution:** Ensure manager.release() is called only in finally, not during loader run.

## Rollback

If issues arise, revert these files:
```bash
git checkout HEAD~1 -- utils/db/context.py utils/optimal_loader.py
rm utils/db/pooled_connection_manager.py utils/db/pooled_context.py utils/db/pooled_context_var.py
```

## Deployment Notes

- No database schema changes
- No new infrastructure or configuration
- Works with existing RDS Proxy and pool settings
- No breaking changes to loader interfaces
- Gradual rollout: Can enable per-loader by wrapping in try/except

## References

- **Pool Documentation:** utils/db/connection.py (SimpleConnectionPool setup)
- **Monitoring:** utils/rds_pool_monitor.py (RDS connection tracking)
- **Loaders:** utils/optimal_loader.py (base class)
