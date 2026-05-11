# Transaction Safety & Concurrency Guide

## Overview

This document outlines transaction patterns and concurrency safeguards for the algo system.
With EventBridge scheduler + ECS loaders + Lambda orchestrator, race conditions are possible.

## Risk Matrix

| Operation | Risk Level | Scenario | Mitigation |
|-----------|-----------|----------|-----------|
| INSERT into algo_trades | LOW | Two signals same symbol simultaneously | Unique trade_id + timestamp |
| UPDATE algo_positions | HIGH | Exit engine + position monitor reading same time | WHERE quantity = (optimistic lock) |
| INSERT swing_scores | LOW | Duplicate calculations per symbol/date | CONFLICT DO NOTHING |
| UPDATE algo_audit_log | LOW | Non-critical, append-only | No transaction needed |
| DELETE position on exit | MEDIUM | Concurrent exit + reload | Soft delete (mark closed) |

## Patterns

### 1. Optimistic Locking (Positions)

**Pattern:** Use current value in WHERE clause to detect changes

```python
current_qty = 100
new_qty = 100 - shares_sold

cur.execute("""
    UPDATE algo_positions
    SET quantity = %s
    WHERE position_id = %s AND quantity = %s  -- Detect if changed
""", (new_qty, pos_id, current_qty))

if cur.rowcount == 0:
    # Someone else modified position - retry or fail
    logger.warning(f"Position changed during exit - retry")
    raise PositionConflict()
```

**When to use:** Concurrent modifications to same row (likely)
**Downside:** May retry unnecessarily if other field changed

### 2. Row-Level Locking (Trades)

**Pattern:** SELECT FOR UPDATE to prevent concurrent modifications

```python
cur.execute("""
    SELECT trade_id, quantity, status FROM algo_trades
    WHERE trade_id = %s
    FOR UPDATE  -- Lock this row until commit
""")
trade = cur.fetchone()

if trade and trade['quantity'] > 0:
    cur.execute("""
        UPDATE algo_trades SET exit_price = %s
        WHERE trade_id = %s
    """, (price, trade_id))
    
conn.commit()  # Release lock
```

**When to use:** Critical operations that must be atomic (trade entry/exit)
**Downside:** Slow if many readers; must always commit/rollback

### 3. Conflict Resolution (Scores)

**Pattern:** UPSERT with CONFLICT clause

```python
cur.execute("""
    INSERT INTO stock_scores (symbol, score_date, signal_quality_score)
    VALUES (%s, %s, %s)
    ON CONFLICT (symbol, score_date) DO UPDATE
    SET signal_quality_score = EXCLUDED.signal_quality_score,
        updated_at = CURRENT_TIMESTAMP
""")
```

**When to use:** Duplicate calculations expected (loaders retry)
**Downside:** DB does extra work; may need conflict columns indexed

### 4. Append-Only Audit Log

**Pattern:** Only INSERT, never UPDATE/DELETE audit data

```python
cur.execute("""
    INSERT INTO algo_audit_log (action_type, symbol, details, created_at)
    VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
""")
conn.commit()
```

**When to use:** Historical record keeping (cannot lose data)
**Benefit:** No locks needed; reads don't block writes

---

## Current Implementation Status

### Safe (✅)

| Table | Operation | Pattern | Notes |
|-------|-----------|---------|-------|
| algo_trades | INSERT | Unique trade_id | Auto-generated, no race |
| algo_trades | UPDATE | WHERE trade_id = ? | Specific row, no collision |
| algo_trades | EXIT | WHERE quantity > 0 | Idempotent (safe to retry) |
| algo_audit_log | INSERT | Append-only | No locking needed |
| algo_positions | CLOSE | Soft delete (status=CLOSED) | Mark, don't delete |
| stock_scores | INSERT | ON CONFLICT DO UPDATE | Handles duplicates |
| sector_ranking | INSERT | ON CONFLICT DO NOTHING | Idempotent |

### At Risk (⚠️)

| Table | Operation | Issue | Mitigation |
|-------|-----------|-------|-----------|
| algo_positions | UPDATE qty | Optimistic lock uses old value | Refresh before update |
| algo_positions | CLOSE | Multiple checks before update | Add transaction (FOR UPDATE) |
| algo_trades | PARTIAL EXIT | Multiple exit_log appends | Use atomic CONCAT operation |

### Unverified (❓)

| Table | Operation | Notes |
|-------|-----------|-------|
| swing_trader_scores | INSERT | Check if duplicates possible |
| sector_rotation | UPDATE | Check if concurrent writers |

---

## Concurrency Scenarios

### Scenario 1: Exit Engine + Position Monitor (LIKELY)

**Setup:**
- 5:00pm: Exit engine running, partial exit on AAPL
- 5:01pm: Position monitor syncing positions from Alpaca
- Both reading/writing algo_positions simultaneously

**Safe?** 
⚠️ PARTIALLY - Exit uses WHERE quantity = %s (optimistic lock) so if position monitor updated it first, exit fails
✅ Safe recovery: Position monitor detects discrepancy and alerts

**Fix:**
```python
# In exit_engine, after reading quantity:
try:
    cur.execute("""
        UPDATE algo_positions SET quantity = %s
        WHERE position_id = %s AND quantity = %s
    """, (...))
    if cur.rowcount == 0:
        # Position changed - log alert and skip
        logger.warning(f"Position changed before exit")
        return False
except Exception as e:
    logger.error(f"Exit failed: {e}")
    return False
```

### Scenario 2: Two Signals Entering Same Stock (UNLIKELY)

**Setup:**
- Signal 1: Enters AAPL at 5:00pm signal batch
- Signal 2: Enters AAPL at 5:00pm (duplicate signal due to retry)
- Both hit OrderExecutor simultaneously

**Safe?** 
✅ YES - OrderExecutor checks Alpaca positions and won't double-enter

**No fix needed** - Application logic prevents double entry

### Scenario 3: Loader Duplicate Scores (LIKELY)

**Setup:**
- loadstockscores scheduled at 6pm
- 6:00pm: First instance starts
- 6:05pm: Retry (due to timeout) starts
- Both calculate same scores for same symbols/date

**Safe?**
✅ YES - stock_scores table has ON CONFLICT clause (UPSERT)

**No fix needed** - Schema handles it

---

## Deadlock Prevention

**Rule 1:** Always acquire locks in same order
```python
# GOOD: Always acquire trade lock before position lock
cur.execute("SELECT ... FROM algo_trades WHERE trade_id = %s FOR UPDATE")
cur.execute("SELECT ... FROM algo_positions WHERE symbol = %s FOR UPDATE")

# BAD: Different order in different functions can deadlock
```

**Rule 2:** Keep transaction scope small
```python
# GOOD: Lock only what's needed
cur.execute("SELECT ... FROM positions WHERE pos_id = ? FOR UPDATE")
# Do modification
conn.commit()

# BAD: Lock entire table
cur.execute("SELECT * FROM positions FOR UPDATE")
```

**Rule 3:** Always use timeout on locks
```python
# Set statement timeout to prevent hanging locks
cur.execute("SET statement_timeout = 30000")  # 30 seconds

try:
    cur.execute("SELECT ... FOR UPDATE")
except psycopg2.OperationalError:
    logger.error("Lock acquisition timeout - possible deadlock")
```

---

## Monitoring Checklist

- [ ] No UPDATE without WHERE clause (search codebase)
- [ ] All DELETE statements are soft deletes (mark status, don't remove)
- [ ] Critical paths (trades, positions) use row-level locks
- [ ] Long-running transactions have timeout
- [ ] Conflict operations have CONFLICT clause
- [ ] Audit log append-only (no updates allowed)
- [ ] Duplicate calculations idempotent

---

## Testing Concurrency

**Load Test:**
```bash
# Simulate 10 concurrent exit attempts on same position
for i in {1..10}; do
  python3 -c "from algo_trade_executor import OrderExecutor; OrderExecutor().exit_trade(...)" &
done
```

**Verify:**
- Only one exit succeeds (rowcount = 1)
- Others fail gracefully and log
- Position final state is correct
- No deadlocks detected
