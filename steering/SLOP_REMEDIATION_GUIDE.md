# Architectural Slops Remediation Guide

**Status:** Phase 1 of consolidation  
**Impact:** 24+ files with duplicated filtering logic  
**Objective:** Single source of truth for all database queries, status checks, and configuration

---

## What Are The Slops?

### SLOP #1: Status Filtering Duplicated 24+ Times
**Problem:** Every file has its own `WHERE status = 'open'` or `WHERE status = 'closed'`

**Files Affected (sampling):**
- `lambda/api/routes/algo_handlers/dashboard.py:85`
- `lambda/api/routes/trades.py:148-149`
- `algo/trading/position_sizer.py:390, 408, 445, 468`
- `algo/infrastructure/alpaca_sync_manager.py:212, 225`
- Plus 18+ more

**Impact:** Changing status definition requires editing 24 files. Risk of inconsistency (one file uses 'OPEN', another uses 'open').

**Solution:** Use `utils.data_queries.get_open_positions()`, `get_closed_positions()`, etc.

---

### SLOP #2: Status Strings Hardcoded (No Enums)
**Problem:** `status = 'open'` appears as a string literal throughout code. Typos cause runtime errors.

**Example:**
```python
# ❌ BAD: Typo risk, inconsistent casing
if position['status'] == 'OPEN':
    ...
elif position['status'] == 'open':  # Different code path, same intent
    ...
```

**Solution:** Use `PositionStatus` and `TradeStatus` enums from `algo.trading.constants`

```python
# ✅ GOOD: Type-safe, single definition
from algo.trading.constants import PositionStatus
if position['status'] == PositionStatus.OPEN:
    ...
```

---

### SLOP #3: Score Thresholds Hardcoded (Should Be in algo_config)
**Problem:** Hardcoded `score >= 70`, `score >= 60`, `score >= 80` in 5+ files

**Examples:**
- `lambda/api/routes/algo_handlers/dashboard.py:1091-1095` → `score >= 70`
- `algo/orchestrator/phase7_signal_generation.py:63` → `score >= 60`
- `loaders/load_sector_ranking.py:52` → `score >= 60`

**Impact:** Can't change thresholds without redeploying code. Should be runtime-configurable via `algo_config` table.

**Solution:** Read from `AlgoConfig` class instead of hardcoding

```python
# ❌ BAD: Hardcoded
qualifying = [s for s in signals if s['score'] >= 70]

# ✅ GOOD: Runtime configurable
from algo.infrastructure.config.main import AlgoConfig
config = AlgoConfig()
min_score = config.get("signal_score_threshold")  # default 60, can be changed in DB
qualifying = [s for s in signals if s['score'] >= min_score]
```

---

### SLOP #4: ETF Filtering Logic Scattered (10+ Variations)
**Problem:** 8 different WHERE clause patterns for the same ETF filter

**Example 1** (scores.py):
```python
WHERE (ss.symbol NOT IN (SELECT symbol FROM etf_symbols) 
       AND (ss.etf IS NULL OR ss.etf = 'N'))
```

**Example 2** (market.py):
```python
WHERE (ss.etf IS NULL OR ss.etf != 'Y')
```

**Problem:** When ETF definition changes, must update 8+ files. Inconsistency causes API/dashboard to return different symbol sets.

**Solution:** Centralized function already exists: `utils.symbol_filters.build_symbol_filter_clause()`

```python
# ✅ GOOD: Use centralized function
from utils.symbol_filters import build_symbol_filter_clause

where_clause = build_symbol_filter_clause()  # Returns SQL WHERE fragment
cur.execute(f"SELECT * FROM swing_trader_scores WHERE {where_clause}")
```

---

### SLOP #5: Data Transformation Logic in Wrong Layer (Dashboard Doing DB Work)
**Problem:** Dashboard computes `ladder_pct_*` and `stage_label` in Python instead of SQL

**Current flow (WRONG):**
```
DB (raw positions) → Dashboard (compute ladder_pct, stage_label) → Frontend
```

**Problem:** 
- Every API caller must do same transformations
- If ETL changes, dashboard must change
- Slow (fetch 1000, filter to 50, transform)

**Solution:** Move to database views

```sql
-- Create view once
CREATE VIEW algo_positions_enriched AS
SELECT ..., 
    ((price - stop) / (t3 - stop)) * 100 as ladder_pct_stop,
    CASE WHEN stage = 2 AND trend_score < 4 THEN 'Early Stage-2' ... END as stage_label
FROM algo_positions_with_risk;

-- Dashboard just queries view
cur.execute("SELECT * FROM algo_positions_enriched WHERE status = %s")
```

---

## How To Fix (Step-by-Step)

### STEP 1: Understand The New Pattern (5 min)

**Three new modules now exist:**

1. **`utils/data_queries.py`** — All database queries
   ```python
   from utils.data_queries import get_open_positions, get_signals_by_score
   
   positions = get_open_positions(cur)  # Returns [position, ...]
   signals = get_signals_by_score(cur, min_score=70)  # Returns [signal, ...]
   ```

2. **`algo/trading/constants.py`** — All status enums and thresholds
   ```python
   from algo.trading.constants import PositionStatus, SignalGrade, DEFAULT_SIGNAL_SCORE_THRESHOLD
   
   if status == PositionStatus.OPEN:  # Type-safe
   grade = SignalGrade.from_score(85)  # Returns SignalGrade.A
   ```

3. **`utils/symbol_filters.py`** — Already exists, must be used
   ```python
   from utils.symbol_filters import build_symbol_filter_clause
   ```

---

### STEP 2: Replace Filtering (High Priority)

**File: `lambda/api/routes/algo_handlers/dashboard.py`**

Line 85 — Current:
```python
cur.execute("""
    SELECT * FROM algo_positions_with_risk
    WHERE status = 'open'
    ORDER BY position_value DESC
    LIMIT 1000
""")
positions = cur.fetchall()
```

Replace with:
```python
from utils.data_queries import get_open_positions

positions = get_open_positions(cur)
# Same result, single source of truth
```

**File: `lambda/api/routes/trades.py`**

Lines 148-149 — Current:
```python
if status:
    valid_statuses = ["open", "closed", "halted", "cancelled"]
    if status not in valid_statuses:
        ...
    where_parts.append("status = %s")
    params.append(status)
```

Replace with:
```python
from utils.data_queries import get_trades_by_status

trades = get_trades_by_status(cur, status=status, limit=limit)
# Validation built-in, raises ValueError on invalid status
```

---

### STEP 3: Replace Status Hardcoding (Medium Priority)

**File: `algo/risk/circuit_breaker.py`** (multiple locations)

Current (multiple occurrences):
```python
cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = 'open'")
```

Replace with:
```python
from utils.data_queries import count_open_positions

count = count_open_positions(cur)
```

Current:
```python
if position["status"] != "open":
    ...
```

Replace with:
```python
from algo.trading.constants import PositionStatus

if position["status"] != PositionStatus.OPEN:
    ...
```

---

### STEP 4: Replace Score Thresholds (Low-Medium Priority)

**File: `algo/orchestrator/phase7_signal_generation.py`**

Current (line 63):
```python
if composite_score >= 60:
    ...
```

Replace with:
```python
from algo.infrastructure.config.main import AlgoConfig

config = AlgoConfig()
min_score = config.get("signal_score_threshold")  # Read from algo_config table
if composite_score >= min_score:
    ...
```

**Benefits:**
- Change thresholds without redeploying code
- Consistent across all modules (all read from same config)
- Audit trail: changes recorded in algo_config table

---

## Files To Update (Priority Order)

### PRIORITY 1: Dashboard & API Filtering (5 files)
1. `lambda/api/routes/algo_handlers/dashboard.py` — Replace line 85 query
2. `lambda/api/routes/trades.py` — Replace status validation
3. `lambda/api/routes/algo_handlers/signals.py` — Check for filtering
4. `lambda/api/routes/algo_handlers/metrics.py` — Check for filtering
5. `lambda/api/routes/algo_handlers/market.py` — Replace ETF filtering

### PRIORITY 2: Core Trading Logic (5 files)
6. `algo/trading/position_sizer.py` — Replace 4 status queries
7. `algo/risk/circuit_breaker.py` — Replace 5 status checks
8. `algo/infrastructure/alpaca_sync_manager.py` — Replace 2 status queries
9. `algo/monitoring/position_monitor.py` — Replace 3 status queries
10. `algo/risk/exposure_policy.py` — Check for filtering

### PRIORITY 3: Loaders & Orchestration (5-10 files)
11-20. Loaders (various) — Score thresholds
21-25. Orchestrator phases — Status checks

---

## Pre-Commit Hook

New hook prevents NEW violations:

```bash
python .pre-commit-scripts/check-no-hardcoded-patterns.py <files>
```

Blocks commits with:
- `status = 'open'` (must use constants)
- `score >= 60` (must use config)
- `completeness >= 0.70` (must use constants)

---

## Validation Checklist

- [ ] `utils/data_queries.py` created (queries module)
- [ ] `algo/trading/constants.py` created (enums module)
- [ ] `.pre-commit-scripts/check-no-hardcoded-patterns.py` created (lint hook)
- [ ] Dashboard filtering replaced → single `get_open_positions()` call
- [ ] API status validation replaced → use `TradeStatus` enum
- [ ] Score thresholds replaced → read from `AlgoConfig`
- [ ] Pre-commit hook added to `.pre-commit-config.yaml`
- [ ] Tests pass: `make test`
- [ ] Lint passes: `make lint`
- [ ] Type check passes: `make type-check`

---

## Rollout Plan

**Day 1:** Dashboard + API (highest impact)  
**Day 2:** Core trading logic  
**Day 3:** Loaders + orchestration  
**Day 4:** Verify + test  

**Rollback:** Git can revert any file if issues arise. Each commit is reversible.

---

## Why This Matters

**Today (Status Quo):**
- Change trading threshold → edit 15+ files → risk missing one → inconsistent behavior
- Dashboard shows open positions, API shows different set → user confusion
- Typo `'open'` vs `'OPEN'` → silent logic error → hard-to-find bugs

**After Remediation:**
- Change threshold → update `algo_config` table → takes effect next run (runtime configurable)
- Dashboard and API call same function → guaranteed consistency
- Typos impossible (enums enforce valid values)
- Code easier to reason about (no hidden assumptions)

---

## Questions?

See `steering/GOVERNANCE.md` for architecture principles.  
See `steering/OPERATIONS.md` for data freshness requirements.  
See `.pre-commit-scripts/` for validation enforcement.
