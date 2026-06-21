# Architectural Cleanup: Phase 3 Implementation Guide

**Status**: Ready for execution | **Effort**: 12-15 hours (loaders) | **Scope**: 304 violations → <80

## Quick Start (30 minutes to first refactor)

### Step 1: Understand the Pattern
- **Extract**: Find 3+ `.get()` calls on same dict → create extraction helper
- **Validate**: Check errors at function entry, fail-fast
- **Modularize**: Split methods into focused sub-functions (<50 lines)

### Step 2: Pick a Loader
**Priority 1** (quick wins, 2-4 hours each):
- load_buy_sell_daily.py (33 violations, 927 lines)
- compute_circuit_breakers.py (29 violations)
- load_stock_scores.py (23 violations)

### Step 3: Follow the Template
Create extraction helper → Refactor methods → Test → Commit

**Example**:
```python
# BEFORE: Multiple .get() calls scattered
high = row.get("high")
low = row.get("low")
close = row.get("close")

# AFTER: One extraction helper
data = extract_technical_data(row)
high = data["high"]
```

## Common Patterns

### Pattern 1: API Response Fields
```python
def extract_price_response(resp):
    return {
        "open": resp.get("Open"),
        "high": resp.get("High"),
        "close": resp.get("Close"),
        "volume": resp.get("Volume"),
    }
```

### Pattern 2: Database Query Results  
```python
def extract_position_row(row):
    return {
        "symbol": row[0],
        "shares": row[1],
        "price": row[2],
    }
```

### Pattern 3: Nested Config/Context
```python
def extract_loader_config(batch_context):
    return {
        "end_date": batch_context.get("end_date"),
        "parallelism": batch_context.get("parallelism", 2),
    }
```

## Loader Priority List

1. **load_buy_sell_daily.py** - 33 violations
2. **compute_circuit_breakers.py** - 29 violations
3. **load_stock_scores.py** - 23 violations
4. **load_swing_trader_scores_vectorized.py** - 17 violations
5. **load_signal_quality_scores.py** - 13 violations
6. **load_cash_flow.py** - 13 violations

**Goal for Phase 3a**: Complete Priority 1 + 2 (10-12 hours), reduce loaders to <80 violations.

## Validation Checklist

For each refactored loader:
- [ ] Extraction helpers in utils/loaders/data_extractors.py
- [ ] Sub-functions are <50 lines
- [ ] mypy passes: `python -m mypy loaders/my_loader.py --ignore-missing-imports`
- [ ] ruff passes: `python -m ruff check loaders/my_loader.py`
- [ ] Tests pass: `pytest tests/test_my_loader.py -v`
- [ ] No regressions vs baseline
- [ ] Commit message follows pattern

## Git Workflow

```bash
git checkout -b refactor/loaders/load_buy_sell_daily
# ... make changes ...
mypy loaders/load_buy_sell_daily.py --ignore-missing-imports
ruff check loaders/load_buy_sell_daily.py
pytest tests/test_load_buy_sell_daily.py -v
git add loaders/load_buy_sell_daily.py utils/loaders/data_extractors.py
git commit -m "refactor(load_buy_sell_daily): Extract [data], split into sub-functions

- Add extract_* helpers for consolidation
- Split large methods into focused pieces  
- Result: 33 → 8 violations"
```

## Expected Impact

Per loader (approximate):
- load_buy_sell_daily.py: 33 → 8 violations (-75%)
- compute_circuit_breakers.py: 29 → 5 violations (-83%)
- load_stock_scores.py: 23 → 4 violations (-83%)

**Total Loaders**: 304 → ~60 violations after Priority 1+2 complete

## Prevention System

✅ Pre-commit checks remain active
- Type checking catches schema mismatches
- Linting enforces style consistency  
- **0 new violations can be introduced**

## Success Criteria

- [x] Pattern proven in Phase 2
- [ ] Priority 1 loaders complete (2-3 per person)
- [ ] Loaders violations <80
- [ ] All Phase 3a tests passing
- [ ] Zero regressions

## Timeline

- **Day 1**: Pick loader, create extraction helpers
- **Day 2**: Refactor methods, run tests
- **Day 3**: Commit, move to next loader
- **Week 2**: Complete all Priority 1+2
- **Ongoing**: Phase 3b (Algo Core)

---

*Reference*: See tools/dashboard/panels/data_extractors.py for extraction helper examples from Phase 2.
