# CIRCUIT BREAKER STALENESS DIAGNOSIS

**Status:** CONFIRMED - Frontend doesn't display when CB data is old  
**Severity:** HIGH - Users can't tell if displayed state is current or stale  
**Threshold:** Should fail-closed if data > 30 min old (per api_data_layer.py:360)

---

## ROOT CAUSE ANALYSIS

### The Problem
The circuit breaker panel in the dashboard **never shows staleness warnings** even when the underlying data is >30 minutes old. This violates fail-closed governance: users see "✓ ALL CLEAR" based on stale data without any indication the state is outdated.

### Code Path Flow (Current Broken State)

```
┌─ API Handler (lambda/api/routes/algo_handlers/dashboard.py:1004-1018)
│  └─ Calls: freshness = check_data_freshness(cur, "algo_portfolio_snapshots", "snapshot_date", warning_days=1)
│  └─ Returns: {"data_age_days": X, "is_stale": bool, "max_date": "YYYY-MM-DD", "warning": "..."}
│  └─ Response includes: "data_freshness": freshness (nested dict)
│
├─ API Response to Frontend
│  └─ Structure:
│     {
│       "breakers": [{triggered: bool, ...}],
│       "any_triggered": false,
│       "triggered_count": 0,
│       "data_freshness": {              ← NESTED HERE
│         "data_age_days": 2,
│         "is_stale": true,
│         "max_date": "2026-07-03",
│         "warning": "Data is 2 days old"
│       }
│     }
│
└─ Frontend Panel (dashboard/panels/circuit.py:82-89)
   └─ Line 89: cb_stale_warning = get_data_staleness_warning(cb, max_age_hours=1.0)
   └─ get_data_staleness_warning ONLY checks: data.get("timestamp")  ← LOOKS AT WRONG FIELD
   └─ Returns: "" (empty string) because "timestamp" field doesn't exist
   
   RESULT: Panel title shows no warning, users can't tell data is stale!
```

### Why This Happens

1. **Mismatch Between API Response and Frontend Expectations**
   - API returns `data_freshness` dict (nested structure)
   - Frontend function `get_data_staleness_warning()` looks for top-level `timestamp` field
   - These are incompatible structures

2. **Insufficient Staleness Check**
   - `get_data_staleness_warning()` (error_boundary.py:99-131) searches for `timestamp` field
   - If missing, returns empty string without warning
   - Silently fails instead of fail-fast behavior
   
3. **No Circuit Breaker for Data Staleness**
   - Data freshness is checked but never triggers a halt
   - No "data_staleness" breaker in the breakers list
   - Staleness is advisory-only, not safety-critical

---

## 30-MINUTE STALENESS THRESHOLD

From `dashboard/api_data_layer.py:360`:
```python
if age_seconds > 1800:  # 1800 seconds = 30 minutes
    raise RuntimeError(
        f"API {endpoint}: cached response too stale "
        f"(30+ min old, {int(age_seconds)}s). "
        "Cannot serve stale data in finance application..."
    )
```

**This is the circuit breaker staleness threshold for all finance data:**
- Cache age > 30 minutes → Considered stale
- Should trigger fail-closed halt
- Currently bypassed in circuit breaker display

---

## SPECIFIC CODE LOCATIONS

### 1. API Response (Correct Data Included)
**File:** `lambda/api/routes/algo_handlers/dashboard.py`  
**Line 1004-1018:**
```python
freshness = check_data_freshness(cur, "algo_portfolio_snapshots", "snapshot_date", warning_days=1)
...
cb_response = {
    "breakers": breakers,
    "any_triggered": any_halted,
    "triggered_count": triggered_count,
    "data_freshness": freshness,  # ← Has is_stale, data_age_days, warning
}
```

### 2. Frontend Panel (Ignores Freshness)
**File:** `dashboard/panels/circuit.py`  
**Line 82-89:**
```python
def panel_circuit(cb: Any) -> Panel:
    from ..error_boundary import get_data_staleness_warning

    err_panel = _error_panel("circuit breakers", cb, "CIRCUIT BREAKERS", border="blue")
    if err_panel:
        return err_panel

    # Check data freshness: warn if circuit breaker status is stale
    cb_stale_warning = get_data_staleness_warning(cb, max_age_hours=1.0) if isinstance(cb, dict) else ""
    # ↑ THIS RETURNS "" because cb has no "timestamp" field, only "data_freshness" dict
```

### 3. Staleness Check Function (Wrong Field)
**File:** `dashboard/error_boundary.py`  
**Line 99-131:**
```python
def get_data_staleness_warning(data: Any, max_age_hours: float = 24.0) -> str:
    """Get staleness warning text if data is older than threshold."""
    if not isinstance(data, dict):
        return ""

    timestamp_val = data.get("timestamp")  # ← ONLY CHECKS TOP-LEVEL timestamp
    if not timestamp_val:
        return ""  # ← RETURNS EMPTY STRING SILENTLY
    
    try:
        # ... calculate age and return warning ...
    except Exception:
        pass
    
    return ""
```

### 4. API Contract (Missing Timestamp Field)
**File:** `shared_contracts/dashboard_api_contract.py`  
**Line 319-335:**
```python
"cb": {
    "path": "/api/algo/circuit-breakers",
    "method": "GET",
    "description": "Circuit breaker status",
    "response_schema": ResponseSchema(
        required_fields=[],
        optional_fields=["breakers", "any_triggered", "triggered_count"],
        # ↑ NO MENTION OF data_freshness OR timestamp FIELD
        field_types={
            "breakers": list,
            "any_triggered": bool,
        },
    ),
    "freshness_max_age_seconds": 300,  # 5 minutes declared but not checked in response
    "strict_fields": [],
    "critical": False,
},
```

---

## DATA FLOW & DEPENDENCY CHAIN

### Current Flow
```
Phase 9 Reconciliation (nightly)
└─ Updates algo_portfolio_snapshots table
   ├─ snapshot_date
   ├─ total_portfolio_value
   └─ daily_return_pct, weekly_loss_pct, etc.

Circuit Breaker API Handler (on-demand)
├─ Runs at dashboard load time
├─ Queries algo_portfolio_snapshots
├─ Calls check_data_freshness(algo_portfolio_snapshots, snapshot_date)
│  └─ If portfolio data >1 day old → is_stale=true
└─ Returns CB response with data_freshness nested dict

Frontend Panel
├─ Receives CB response
├─ Calls get_data_staleness_warning(cb_response)
│  └─ Looks for cb_response.timestamp (NOT FOUND)
│  └─ Returns "" (empty string)
└─ Displays panel title WITHOUT staleness warning
```

### Why Data Gets Stale
1. **Portfolio snapshot timing**: Created at end of trading day (Phase 9)
2. **Intraday staleness**: If checking during day (say 10:00 AM), previous day's data is up to 15+ hours old
3. **Weekend staleness**: Friday's data shown as "fresh" through weekend only via holiday logic
4. **Logic gap**: If orchestrator runs before fresh data loads, CB shows old data as "current"

### When Should Staleness Trigger
- **Data age > 30 minutes** (per api_data_layer.py:360):
  - Should fail-closed
  - Should show warning in frontend
  - Should add data_staleness breaker entry
  
---

## FIX STRATEGY (3 Levels)

### LEVEL 1: Fix Frontend Panel to Use data_freshness (REQUIRED)
**File:** `dashboard/panels/circuit.py`  
**Changes:**
1. Update line 89 to check `cb.get("data_freshness")` instead of looking for `timestamp`
2. Extract `is_stale` from data_freshness dict
3. If `is_stale=true`, add warning to panel title
4. Show data age from `data_age_days` field

**Pseudocode:**
```python
# OLD (line 89):
cb_stale_warning = get_data_staleness_warning(cb, max_age_hours=1.0)

# NEW:
cb_stale_warning = ""
if isinstance(cb, dict):
    data_freshness = cb.get("data_freshness")
    if isinstance(data_freshness, dict) and data_freshness.get("is_stale"):
        age_days = data_freshness.get("data_age_days", "?")
        cb_stale_warning = f" ⚠ STALE (data {age_days}d old)"
```

**Benefit:** Users immediately see when CB data is outdated, enables informed decisions about trusting displayed state

---

### LEVEL 2: Add Timestamp to API Response (RECOMMENDED)
**File:** `lambda/api/routes/algo_handlers/dashboard.py`  
**Changes:**
1. Import datetime utilities
2. Add top-level `timestamp` field to cb_response (line 1014-1020)
3. Use ISO format: `datetime.now(timezone.utc).isoformat()`
4. Update contract to declare this field

**Pseudocode:**
```python
# Around line 1014:
from datetime import datetime, timezone

cb_response = {
    "breakers": breakers,
    "any_triggered": any_halted,
    "triggered_count": triggered_count,
    "data_freshness": freshness,
    "timestamp": datetime.now(timezone.utc).isoformat(),  # ADD THIS
}
```

**Update contract** in `shared_contracts/dashboard_api_contract.py`:
```python
"cb": {
    ...
    "optional_fields": ["breakers", "any_triggered", "triggered_count", "data_freshness", "timestamp"],
    ...
}
```

**Benefit:** Makes frontend function `get_data_staleness_warning()` work without change, provides response age

---

### LEVEL 3: Fail-Closed Circuit Breaker for Staleness (BEST PRACTICE)
**File:** `lambda/api/routes/algo_handlers/dashboard.py`  
**Changes:**
1. After fetching data_freshness (line 1004), check if it's stale
2. If `freshness.get("is_stale")`, add a data_staleness breaker to the list
3. Set `any_triggered=true` to halt trading when data is >30min old

**Pseudocode:**
```python
# Around line 1005, after freshness check:
if freshness.get("is_stale"):
    breakers.insert(0, {
        "id": "data_staleness",
        "label": "Circuit Breaker Data Stale",
        "triggered": True,
        "current": freshness.get("data_age_days"),
        "threshold": 1,  # max 1 day old for CB data
        "unit": "days",
        "description": f"Circuit breaker data is {freshness.get('data_age_days', '?')} days old. "
                      f"Cannot assess risk accurately — trading halted until fresh data available.",
    })
    any_halted = True
```

**Benefit:**
- Staleness becomes visible in breaker list alongside other halt conditions
- Failing closed: if we can't verify current risk state, we halt
- Matches governance rule: unknown state → halt
- Provides specific reason for halt

---

## VERIFICATION TEST PLAN

### Test 1: Manual Staleness Check (5 min)
```bash
# 1. Check database age:
psql -c "SELECT snapshot_date, MAX(snapshot_date) OVER() as latest FROM algo_portfolio_snapshots LIMIT 1"

# 2. Call API directly:
curl http://localhost:3001/api/algo/circuit-breakers | jq .data_freshness

# 3. Expected: data_age_days field shows staleness
```

### Test 2: Frontend Warning Display (10 min)
```
1. Open dashboard
2. Simulate old data: UPDATE algo_portfolio_snapshots SET snapshot_date='2026-07-01' WHERE id=1
3. Reload dashboard
4. Check circuit panel title for ⚠ STALE warning
```

### Test 3: Fail-Closed Halt (10 min)
```
1. Trigger stale data condition (>30min old)
2. Check that circuit panel shows data_staleness breaker triggered
3. Verify any_triggered=true in API response
4. Confirm orchestrator would halt on stale data
```

### Test 4: Edge Cases (15 min)
- Weekend/holiday staleness (3-day-old Friday data on Monday)
- First-run bootstrap (no portfolio history yet)
- Missing data_freshness field in response
- NULL data_age_days

---

## GOVERNANCE IMPLICATIONS

**Non-Negotiable Rule:** Circuit breaker data must never be served stale  
**Fail-Fast:** If data > 30 min old, must halt trading immediately  
**User Visibility:** Frontend MUST show when data is stale, not silent fallback  
**Current State:** VIOLATION - Users see stale CB without warning

---

## SUMMARY

| Aspect | Current | Expected |
|--------|---------|----------|
| **Staleness Check** | API computes but frontend ignores | Frontend displays warning |
| **30min Threshold** | Defined in api_data_layer.py | Applied in circuit breaker check |
| **User Visibility** | No warning shown | Clear ⚠ STALE indicator in panel title |
| **Fail-Closed** | No halt on stale data | Adds data_staleness breaker, halts trading |
| **Response Structure** | Nested data_freshness only | Top-level timestamp + nested data_freshness |
| **Governance** | BROKEN - silent staleness | FIXED - explicit stale marker + fail-closed |

---

## DEPENDENCY CHAIN
```
check_data_freshness(algo_portfolio_snapshots)
  └─ Returns is_stale, data_age_days, warning
     ├─ Used by API response (correct)
     └─ Ignored by frontend panel (broken)
        └─ get_data_staleness_warning() only checks timestamp
           └─ Should check data_freshness.is_stale
              └─ Should add to breaker list if stale
                 └─ Should set any_triggered=true
                    └─ Should fail-close trading
```

**To fix:** Update frontend panel + optionally add timestamp to response + optionally add fail-closed breaker
