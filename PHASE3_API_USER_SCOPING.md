# Phase 3: API User Scoping Implementation

**Status:** Infrastructure Ready, Route Updates Required  
**Priority:** CRITICAL for new user support  
**Estimated Time:** 30 minutes (can be done incrementally)

## Overview

All API routes must scope database queries to the authenticated user to prevent cross-user data access. This document shows which routes are critical and how to update them.

## Critical Routes (Must Update)

These routes serve user-specific data and MUST be scoped by user:

### 1. `/api/algo/*` - Portfolio and Trading Data
**File:** `lambda/api/routes/algo.py` (2122 lines)

**What to update:**
- Portfolio holdings queries
- Position queries
- Trade history queries
- P&L calculation queries
- Risk dashboard queries

**Pattern:**
```python
from routes.user_isolation import require_user, scope_query

def handle(cur, path, method, params, body=None, jwt_claims=None, user_id=None):
    try:
        user_id = require_user(jwt_claims)  # Raise 401 if not auth'd
    except ValueError as e:
        return {"statusCode": 401, "errorType": "unauthorized", "message": str(e)}

    # Query positions - NOW SCOPED BY USER
    sql = "SELECT * FROM algo_positions WHERE symbol = %s"
    scoped_sql, _ = scope_query(sql, user_id, table_alias='ap')
    cur.execute(scoped_sql, (symbol, user_id))
    positions = cur.fetchall()

    return {"statusCode": 200, "body": positions}
```

### 2. `/api/trades` - Trade History
**File:** `lambda/api/routes/trades.py` (130 lines)

**What to update:**
- Trade list queries
- Trade detail queries
- Trade statistics queries

**Pattern:** Same as above - use `scope_query()` for all algo_trades queries

### 3. `/api/settings` - User Settings
**File:** `lambda/api/routes/settings.py` (105 lines)

**What to update:**
- User preference/settings queries
- Dashboard configuration

### 4. `/api/audit` - Audit Logs
**File:** `lambda/api/routes/audit.py` (107 lines)

**What to update:**
- Audit trail queries
- Event history queries

### 5. `/api/admin` - Admin Functions
**File:** `lambda/api/routes/admin.py` (315 lines)

**Note:** Admin endpoints serve system-wide data but should validate user is in admin group
- Notifications (user-specific - must scope)
- User management (admin-only - must check admin role)

## Non-Critical Routes (Can Skip for MVP)

These serve system-wide or public data, not user-specific:
- `/api/stocks` - Stock data
- `/api/prices` - Price data
- `/api/signals` - Signal data
- `/api/market` - Market data
- `/api/scores` - Score data
- `/api/research` - Research/backtest data

## Implementation Steps

### Step 1: Update Core Routes (10 minutes)
Start with `/api/algo` since it's the most critical:
1. Import `require_user`, `scope_query` from `user_isolation`
2. Add `user_id` parameter to handler function
3. Wrap database queries with `scope_query()`
4. Test each query works correctly

### Step 2: Update Trade Routes (5 minutes)
Update `/api/trades` using same pattern

### Step 3: Update Admin Routes (5 minutes)
Update `/api/admin` for user-specific data like notifications

### Step 4: Update Settings Routes (5 minutes)
Update `/api/settings` for per-user settings

### Step 5: Test (5 minutes)
- Login as admin user (argeropolos@gmail.com)
- Verify dashboard shows admin's portfolio
- Verify can't access other users' data
- Create test user, verify isolation

## Example: Updating `/api/algo`

Find all database queries in `lambda/api/routes/algo.py` that access user-specific tables:
- `algo_positions`
- `algo_trades`
- `algo_portfolio_snapshots`
- `algo_trade_adds`

For each query, add user scoping:

**Before:**
```python
cur.execute("SELECT * FROM algo_positions WHERE symbol = %s", (symbol,))
```

**After:**
```python
from routes.user_isolation import scope_query

scoped_sql, _ = scope_query(
    "SELECT * FROM algo_positions WHERE symbol = %s",
    user_id,
    table_alias='ap'
)
cur.execute(scoped_sql, (symbol, user_id))
```

## Database Tables That MUST Be Scoped

- `algo_positions` - User's open positions
- `algo_trades` - User's trade history
- `algo_portfolio_snapshots` - User's portfolio snapshots
- `algo_trade_adds` - User's pyramid adds

All others are system-wide data (not user-specific).

## Testing Checklist

After updating routes:

- [ ] Admin can log in and see their portfolio
- [ ] Admin sees correct positions and trades
- [ ] Admin cannot access non-existent user data (404 instead of error)
- [ ] Create second test user via Cognito
- [ ] Second user has isolated portfolio (empty)
- [ ] Second user cannot see admin's data
- [ ] Portfolio endpoints return 401 when not authenticated

## Rollback

If issues arise, routes will fall back to system-wide queries (current behavior) until fully migrated.

## Next After Phase 3

- Phase 4: Run `scripts/setup-user-isolation.ps1` to finalize database setup
- Phase 5: End-to-end testing with new user account
