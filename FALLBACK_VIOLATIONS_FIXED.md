# Fallback Violations Audit - Session [Current]

## Overview

**Goal:** Eliminate silent fallbacks that cause "sometimes works, sometimes doesn't" behavior in the finance app.

**Result:** Found and fixed 6 critical configuration fallback violations where `alpaca_paper_trading` and related trading mode configs had conflicting defaults across different modules.

---

## Critical Violations Fixed

### 1. **CRITICAL: `alpaca_paper_trading` Configuration Inconsistency**

**Problem:** Different modules used `.get()` with conflicting defaults for the same config key:

| Module | Config Key | Default | Impact |
|--------|-----------|---------|--------|
| `reconciliation.py:49` | `alpaca_paper_trading` | **True** | Paper mode enabled |
| `alpaca_sync_manager.py:34` | `alpaca_paper_trading` | **False** | Live mode attempted |
| `phase8_entry_execution.py:554` | `alpaca_paper_trading` | **False** | Live mode attempted |
| `phase6_exit_execution.py:64` | `alpaca_paper_trading` | **False** | Live mode attempted |
| `orchestrator.py:162` | `alpaca_paper_trading` | **None** | KeyError risk |

**Root Cause:** Each module independently loaded config and applied defaults instead of requiring explicit configuration. Since different paths might execute in different order (depending on conditions), the trading mode was non-deterministic.

**Risk:** System could silently switch between paper and live trading depending on which code path ran first, creating:
- Unintended live trades when expecting paper mode
- Silent failure to execute when credentials missing but no explicit error
- Non-reproducible behavior ("sometimes works")

**Fix Applied:**
- `reconciliation.py`: Now requires explicit `alpaca_paper_trading` in config, fails-fast with clear error if missing
- `alpaca_sync_manager.py`: Now requires explicit `alpaca_paper_trading` in config, fails-fast if missing
- `phase6_exit_execution.py`: Now requires explicit `alpaca_paper_trading` in config, fails-fast if missing
- `phase8_entry_execution.py`: Now requires explicit `alpaca_paper_trading` in config, fails-fast if missing
- `orchestrator.py`: Already had proper None check (no fix needed)

**Validation:** All fixes added explicit `if "key" not in config: raise ValueError(...)` before accessing config.

**Status:** ✅ FIXED in commit e5d995361

---

### 2. **Configuration Defaults for Data Staleness Thresholds (Phase 1)**

**Problem:** Phase 1 data freshness checks used `.get()` with hardcoded defaults for critical timing thresholds:

```python
# BEFORE (line 177-179)
phase1_recent_cutoff_days = config.get("phase1_recent_cutoff_days", 2)
phase1_prior_cutoff_days = config.get("phase1_prior_cutoff_days", 2)  
phase1_halt_table_max_tolerance_days = config.get("phase1_halt_table_max_tolerance_days", 1)
```

**Root Cause:** These timing parameters directly control whether the system halts trading when data is stale, but were using silent fallbacks to hardcoded values.

**Risk:** If config table row missing or deleted, system would use hardcoded defaults instead of failing with clear error. This could cause:
- Stale price data trading (when Phase 1 is supposed to halt)
- Inconsistent behavior if config changed in database (fallback would ignore changes)

**Fix Applied:**
- Now requires ALL three keys to be explicitly present in config
- Fails-fast with clear error if any missing
- Error message states which keys are missing

**Status:** ✅ FIXED in commit e5d995361

---

### 3. **`is_paper_trading` Configuration Check (Phase 3)**

**Problem:** Phase 3 position monitor used `.get()` with silent False default:

```python
# BEFORE (line 209)
if config.get("is_paper_trading", False):
```

**Root Cause:** Inconsistent with phase6/phase8/etc which use `alpaca_paper_trading`. Also silently defaults to False (live mode) if missing, creating risk.

**Fix Applied:**
- Changed to require explicit config key
- Fails-fast if missing
- Clarifies which key is expected

**Status:** ✅ FIXED in commit e5d995361

---

## Validation Performed

### Code Review Results
✅ **Configuration fallback patterns:** All critical trading-mode configs now require explicit values
✅ **Exception handlers:** Verified critical paths use specific exception types (not bare `except Exception`)
✅ **Financial data validation:** Checked for silent numeric defaults (0, 0.0) on required fields
✅ **Phase 9 reconciliation:** Verified explicit NULL checks for critical fields (portfolio_value, positions, unrealized_pnl)
✅ **Dashboard resilience:** Confirmed dashboard has intentional fallbacks with explicit logging (not silent)

### Tests Needed
- [ ] Verify orchestrator startup fails if `alpaca_paper_trading` missing from algo_config
- [ ] Verify Phase 1 fails if timing thresholds missing from algo_config
- [ ] Verify config hotreload still works with explicit requirements
- [ ] Test paper vs live mode detection across all entry/exit phases

---

## Pattern Enforcement Rules

### For Configuration Loading
**Rule:** Never use `.get(key, default)` for required trading/safety config.

**Do:**
```python
if "trading_mode" not in config:
    raise ValueError("[MODULE] Config missing required 'trading_mode'. Must be explicit.")
value = config["trading_mode"]
```

**Don't:**
```python
value = config.get("trading_mode", "paper")  # WRONG: Silent fallback
```

### For Financial Data
**Rule:** Explicit NULL/None checks required; never use falsy checks on prices/values.

**Do:**
```python
if price is None or price <= 0:
    raise ValueError(f"Invalid price: {price}")
```

**Don't:**
```python
if not price:  # WRONG: 0.00 is valid for some fields, silently rejects
    price = fallback_value
```

### For Required Data Fields
**Rule:** All required fields must be validated before use.

**Do:**
```python
if "entry_price" not in data or data["entry_price"] is None:
    raise ValueError("entry_price required")
entry_price = float(data["entry_price"])
```

**Don't:**
```python
entry_price = float(data.get("entry_price", 0))  # WRONG: Defaults to $0
```

---

## Impact Summary

**Files Modified:** 6  
**Lines Changed:** +65 insertions, -10 deletions  
**Commits:** 1 (e5d995361)  
**Risk Reduction:** HIGH - Eliminates non-deterministic trading mode behavior

**Before Fix:** System could silently switch between paper/live trading based on code path execution order
**After Fix:** Trading mode must be explicitly configured; system fails-fast with clear errors if misconfigured

---

## Related Documentation

- **CLAUDE.md:** Non-Negotiable Rule: "Data integrity: Explicit data_unavailable flags (no silent fallbacks)"
- **steering/GOVERNANCE.md:** "Finance app requires fail-fast on all critical paths"
- **Session 127:** PsycopgCursor regression that showed real outage from silent import failures
- **Session 120-123:** Fallback elimination campaigns (400+ violations eliminated)

---

## Next Steps

1. ✅ Commit critical fixes
2. [ ] Run orchestrator with missing config keys to verify failures
3. [ ] Update CLAUDE.md with explicit rule about `alpaca_paper_trading` consistency
4. [ ] Add pre-commit check for .get() patterns on trading config
5. [ ] Document config schema validation to catch schema drift

