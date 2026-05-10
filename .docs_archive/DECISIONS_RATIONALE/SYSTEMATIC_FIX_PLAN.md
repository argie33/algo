# Systematic Fix Plan - All 67 Exception-Masking Returns

## Priority Order (Fix in this order)

### PRIORITY 1: Core Algorithm Modules (8 files - HIGH RISK)
These are in the critical path and most impact system reliability:
1. algo_trade_executor.py (1 instance) - CRITICAL
2. algo_orchestrator.py (1 instance) - CRITICAL  
3. algo_signals.py (1 instance) - Already mostly fixed
4. algo_position_sizer.py (1 instance) - IMPORTANT
5. algo_advanced_filters.py (1 instance) - IMPORTANT
6. algo_paper_trading_gates.py (1 instance)
7. algo_wfo.py (1 instance)
8. algo_sector_rotation.py (1 instance)

**Time Estimate: 90 minutes**

### PRIORITY 2: Data Loaders (40+ files - MEDIUM RISK)
All follow same pattern: `return 0 if stats["symbols_failed"] == 0 else 1` in finally
These are lower risk since they're CLI tools, not library code
**Time Estimate: 90 minutes (batch fix)**

### PRIORITY 3: Utility Files (5 files - LOWER RISK)
- enable_timescaledb.py
- Others

**Time Estimate: 30 minutes**

---

## Fix Strategy

### For Core Modules:
```python
# BEFORE:
try:
    # ... operation ...
except Exception as e:
    # ... error handling ...
finally:
    return result  # WRONG - masks exception

# AFTER:
result = None
try:
    # ... operation ...
    result = value  # Assign here
except Exception as e:
    # ... error handling ...
    result = default_value  # Set on error
finally:
    # Cleanup only - NO RETURN
    self.cleanup()

return result  # After finally block
```

### For Data Loaders (Simpler Pattern):
```python
# BEFORE:
finally:
    return 0 if stats["symbols_failed"] == 0 else 1

# AFTER:
result = None
try:
    # ... operation ...
except Exception as e:
    # ... error handling ...
    result = 1
finally:
    # Cleanup only
    pass
    
if result is None:
    result = 0 if stats["symbols_failed"] == 0 else 1
return result
```

---

## Execution Steps

1. **Fix Priority 1 modules one by one** (90 min)
   - Read method completely
   - Identify return value logic
   - Restructure to move return before finally
   - Test each file with pytest
   - Commit with clear message

2. **Batch fix Priority 2 data loaders** (90 min)
   - Create script to fix all at once (same pattern)
   - Apply fix to all 40+ files
   - Test with sample loader run
   - Single commit for all data loaders

3. **Fix Priority 3 utilities** (30 min)
   - Handle remaining files
   - Final comprehensive test

4. **Full System Verification** (30 min)
   - Run all 14 signal methods
   - Run data quality checks
   - Run pytest suite
   - Verify no regressions

---

## Total Time Estimate: 4 hours for ALL exception-masking returns

**Status:** Ready to execute systematically
