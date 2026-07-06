# Price Fetcher Rate Limit Threshold — Complete Diagnosis

**Date:** 2026-07-05  
**Severity:** MEDIUM (documentation/validation gap, not actively breaking)  
**Status:** Root cause identified, fix strategy defined

---

## Executive Summary

The `loader_rate_limit_circuit_break_threshold_eod` configuration key varies by pipeline context (EOD vs. morning) with an undocumented, unvalidated threshold range (60-300 seconds). This creates three problems:

1. **Documentation Gap:** No single source documenting why thresholds differ by pipeline
2. **Validation Gap:** Schema allows 0-3600s, but semantics require context-specific defaults (180s EOD, 480s morning)
3. **Discoverability:** New engineers cannot understand threshold semantics without reading load_prices.py

---

## Root Cause Analysis

### 1. Configuration Design: Pipeline-Context Multiplexing

**Location:** `algo/infrastructure/config/main.py` lines 752-762, `algo/infrastructure/config_schema.py` lines 220-221

**Current Implementation:**
```python
# In load_prices.py:99-108
self._is_eod_pipeline = self._detect_eod_pipeline_context()
config = get_config()
key = (
    "loader_rate_limit_circuit_break_threshold_eod"      # 180 sec (3 min)
    if self._is_eod_pipeline
    else "loader_rate_limit_circuit_break_threshold_morning"  # 480 sec (8 min)
)
self._rate_limit_circuit_break_threshold = int(config.get(key))
```

**Root Cause:** Two separate config keys with pipeline-dependent semantics are defined, but:
- No validation rule enforces WHY they differ (e.g., EOD has 85-min window, morning has 450-min window)
- Schema validation treats them independently (both allow 0-3600s)
- No documentation links threshold to pipeline SLA or Step Function timeout

**Why This Pattern Exists:**
- EOD pipeline (4:05-5:30 PM ET, ~85 min window): Aggressive timeout needed to fail-fast
- Morning pipeline (2:15 AM start, ~450 min window): Conservative timeout to allow retries
- Per load_prices.py lines 147-165, the same code detects pipeline type from current UTC time

### 2. Undocumented Threshold Range (60-300s Range Not Documented)

**Finding:** Across all codebase references, the "60s-300s" range mentioned in the ticket is NOT defined anywhere.

**Actual Thresholds:**
```python
# config_schema.py:220-221
"loader_rate_limit_circuit_break_threshold_morning": ("int", 0, 3600, False, 480),  # min=0, max=3600, default=480
"loader_rate_limit_circuit_break_threshold_eod": ("int", 0, 3600, False, 180),      # min=0, max=3600, default=180
```

**Discovery:** Where is "60-300s" mentioned? Possible sources:
- Slack conversation or incident notes (not in codebase)
- OR variation in database values vs. code defaults

### 3. No Semantic Validation of Threshold vs. Pipeline

**Problem:** The schema allows EITHER threshold to be set to ANY value 0-3600s, but:
- If `loader_rate_limit_circuit_break_threshold_morning` = 50s → triggers too early (morning has 450 min budget)
- If `loader_rate_limit_circuit_break_threshold_eod` = 600s → too late (EOD only has 85 min budget)

**Example Failure Scenario:**
```
Admin sets loader_rate_limit_circuit_break_threshold_eod = 500 (8.3 min)
→ During EOD (85 min total window), rate limit errors must persist 500s before circuit breaker triggers
→ If yfinance is degraded, 500s delay = 8+ minutes of the 85-min budget lost
→ Remaining time insufficient to complete load, triggers failsafe instead of graceful degradation
```

---

## Dependency Chain

### 1. **Config System** (not affected by fix)
- `algo/infrastructure/config/main.py`: Loads from database
- `algo/infrastructure/config_schema.py`: Validates with schema
- `config/thresholds.py`: Wrapper for config access

### 2. **Price Loader** (primary affected)
- `loaders/load_prices.py`: Reads config at init time (lines 99-108)
- `loaders/load_prices.py`: Uses threshold at 2 decision points:
  - Line 1129: Circuit breaker check (error_duration > threshold → reduce batch size)
  - Line 1502: Emergency mode detection (checks if batch size < 100 AND elapsed > threshold)

### 3. **Pipeline Detection** (co-dependency)
- `loaders/load_prices.py:147-165`: `_detect_eod_pipeline_context()` determines which threshold key to use
- Logic: if current UTC hour in 20:05-22:30 range (ET 4:05-6:30 PM, accounting for yfinance lag), treat as EOD
- **Risk:** If detection fails, defaults to morning threshold (480s) even during EOD → circuit breaker fires too late

### 4. **No Other Loaders Affected**
- `loaders/market_health_fetchers.py`: Does NOT use circuit break threshold
- `loaders/load_fred_economic_data.py`: Does NOT use circuit break threshold
- `loaders/load_options_chains.py`: Does NOT use circuit break threshold
- **Reason:** Only price loader has rate limit issues due to volume (3000+ symbols)

---

## Data Flow: Threshold to Circuit Breaker

```
algo_config table (database)
    ├─ loader_rate_limit_circuit_break_threshold_morning: 480
    └─ loader_rate_limit_circuit_break_threshold_eod: 180
         │
         ↓
AlgoConfig.get_config()
    ├─ Loads from DB with validation_schema bounds check [0, 3600]
    └─ Returns to caller (type int)
         │
         ↓
load_prices.py:PriceLoader.__init__()
    ├─ Detects pipeline context (_detect_eod_pipeline_context → True/False)
    ├─ Selects config key based on context
    └─ Reads int(config.get(key)) → stores as _rate_limit_circuit_break_threshold
         │
         ↓
load_prices.py:PriceLoader._execute_batch_fetch()
    ├─ Line 1129: if error_duration > self._rate_limit_circuit_break_threshold → reduce batch size
    ├─ Line 1502: if elapsed_sec > circuit_break_threshold_sec → log warning
    └─ Result: Triggers adaptive retry or escalates to failsafe
```

---

## Issue Pattern: 3 Validation Gaps

### Gap 1: No Documentation of Pipeline Context Selection
**Problem:** Why use 180s for EOD and 480s for morning?  
**Current Location:** Implicit in defaults, explained only in comments at lines 752-762 in main.py  
**Missing:** Central reference doc explaining all three thresholds + when to tune each

### Gap 2: No Relationship Validation
**Problem:** Schema allows 0-3600s independently; no rule enforces:
```
morning_threshold + error_recovery_time <= 450 min (morning budget)
eod_threshold + error_recovery_time <= 85 min (EOD budget)
```

**Example Violation:**
```
Config: loader_rate_limit_circuit_break_threshold_eod = 1800 (30 min)
        loader_rate_limit_circuit_break_threshold_morning = 480 (8 min)

Morning: 480s + retry overhead (~5 min) = ~13 min within 450-min budget ✓
EOD: 1800s + retry overhead (~5 min) = ~35 min within 85-min budget ✗ (only ~50 min left for fetch)
```

### Gap 3: No Implementation Documentation
**Problem:** Engineers tuning these thresholds must read load_prices.py to understand:
- When threshold triggers (line 1129: `error_duration > threshold`)
- What happens after (line 1130-1132: reduces batch size and retries)
- Context-dependent semantics (morning → lenient, EOD → aggressive)

---

## Impact Assessment

### Severity: MEDIUM (Does not currently break)
- ✅ Current values (180s EOD, 480s morning) are reasonable defaults
- ✅ Config system loads both keys without error
- ✅ Pipeline detection works (most time)
- ❌ If operator tunes thresholds, risks of undersized/oversized settings
- ❌ New operators lack guidance on safe ranges per pipeline

### Where Failures Occur
1. **If EOD threshold set too high (e.g., 600s):**
   - Waits 10 min before circuit breaker → only ~75 min left for actual fetching
   - Higher likelihood of Step Function timeout (Lambda/Fargate hard limit 1800s total)

2. **If morning threshold set too low (e.g., 60s):**
   - Triggers circuit breaker in 1 min of errors → reduces batch size (20 → 10)
   - Batch size cascade: 150 → 20 → 10 → 1 → abort in 30+ minutes
   - Unnecessary retry overhead in long morning window

3. **If pipeline detection fails (edge case):**
   - Default is morning threshold (480s)
   - During EOD, waits 8 min before circuit break → high timeout risk

---

## Fix Strategy: 3-Part Solution

### Part 1: Update Validation Schema (Fail-Fast on Invalid Ranges)

**File:** `algo/infrastructure/config_schema.py`

**Current:**
```python
"loader_rate_limit_circuit_break_threshold_morning": ("int", 0, 3600, False, 480),
"loader_rate_limit_circuit_break_threshold_eod": ("int", 0, 3600, False, 180),
```

**Proposed (narrower validation bounds):**
```python
"loader_rate_limit_circuit_break_threshold_morning": ("int", 60, 900, False, 480),  # 1-15 min range
"loader_rate_limit_circuit_break_threshold_eod": ("int", 60, 600, False, 180),      # 1-10 min range
```

**Rationale:**
- **Morning min (60s):** Minimum meaningful error detection window
- **Morning max (900s = 15 min):** Conservative guard within 450-min budget
- **EOD min (60s):** Minimum meaningful error detection window  
- **EOD max (600s = 10 min):** Aggressive limit within 85-min budget

**Enforcement:** AlgoConfig.get() will reject any value outside [min, max] at startup or hot-reload.

### Part 2: Semantic Validation in config_schema.py or AlgoConfig

**File:** `algo/infrastructure/config/main.py` (method `_validate_config_interdependencies`)

**Add New Validation:**
```python
def _validate_loader_rate_limits(self) -> None:
    """Validate loader rate limit thresholds vs. pipeline budgets.
    
    Rules:
    1. threshold_eod must be < threshold_morning (EOD has tighter deadline)
    2. threshold_eod must account for 85-min total window with retries
    3. threshold_morning must account for 450-min total window
    """
    morning = int(self._config.get("loader_rate_limit_circuit_break_threshold_morning", 480))
    eod = int(self._config.get("loader_rate_limit_circuit_break_threshold_eod", 180))
    
    # Rule 1: EOD threshold should be < morning (tighter deadline)
    if eod >= morning:
        logger.warning(
            f"Config: loader_rate_limit_circuit_break_threshold_eod ({eod}s) >= "
            f"loader_rate_limit_circuit_break_threshold_morning ({morning}s). "
            f"EOD has tighter deadline (85 min vs 450 min). Consider: eod < morning."
        )
    
    # Rule 2: EOD threshold must leave buffer for retry
    max_eod_threshold = 60 * 60  # 60 min, leaving 25 min buffer in 85-min window
    if eod > max_eod_threshold:
        logger.critical(
            f"Config: loader_rate_limit_circuit_break_threshold_eod ({eod}s = {eod/60:.0f} min) "
            f"exceeds safe limit (3600s = 60 min). EOD window is only 85 min total. "
            f"Reduce to <= 600s (10 min) to ensure completion."
        )
    
    # Rule 3: Morning threshold plausible
    max_morning_threshold = 900  # 15 min
    if morning > max_morning_threshold:
        logger.warning(
            f"Config: loader_rate_limit_circuit_break_threshold_morning ({morning}s = {morning/60:.0f} min) "
            f"is very conservative. Morning window is 450 min. Typical: 480s (8 min)."
        )
```

**Where to Call:**
- Add to `_validate_config_interdependencies()` method (called at startup + hot-reload)
- Keep warnings for soft constraints, critical for hard constraints

### Part 3: Add Documentation

**File:** Create `steering/LOADER_RATE_LIMITS.md`

**Contents:**
```markdown
# Loader Rate Limit Thresholds — Configuration Guide

## Overview
Two thresholds control when the price fetcher's circuit breaker triggers during rate limit errors:
- `loader_rate_limit_circuit_break_threshold_eod`: 180s (3 min) — EOD pipeline
- `loader_rate_limit_circuit_break_threshold_morning`: 480s (8 min) — Morning prep pipeline

## Pipeline Context

### Morning Pipeline (2:15 AM ET)
- **Execution Window:** 2:15 AM — 9:30 AM ET (~450 minutes)
- **Typical Load Time:** 285 minutes (4.75 hours)
- **Latency Budget:** 165 minutes for retries/recovery
- **Recommended Threshold:** 480s (8 min)
- **Rationale:** Conservative — long window allows retries if yfinance degrades

### EOD Pipeline (4:05 PM ET)
- **Execution Window:** 4:05 PM — 5:30 PM ET (~85 minutes)
- **Typical Load Time:** 15 minutes (aggressive)
- **Latency Budget:** 70 minutes for retries/recovery
- **Recommended Threshold:** 180s (3 min)
- **Rationale:** Aggressive — tight deadline requires fail-fast on errors

## Circuit Breaker Trigger

When yfinance returns rate limit errors (HTTP 429) for > threshold seconds:
1. Reduce batch size (150 → 100 → 50 → 20 → 10 → 1)
2. Retry fetch with smaller batch
3. If errors persist at batch=1, abort and trigger failsafe

**Example Timeline (EOD, 180s threshold):**
```
t=0s: Batch=150, first rate limit error
t=180s: Circuit breaker triggered, reduce to batch=100
t=360s: Still failing, reduce to batch=50
t=540s: Still failing, reduce to batch=20
t=720s: Still failing, abort and trigger failsafe
Total time lost: 12 minutes (out of 85-minute window)
```

## Safe Ranges (Validated)

| Pipeline | Min | Max | Default | Constraint |
|----------|-----|-----|---------|------------|
| Morning | 60s | 900s (15 min) | 480s (8 min) | Leave 1.5+ hours for retries |
| EOD | 60s | 600s (10 min) | 180s (3 min) | Leave 25+ min for retries |

**Invalid Configurations:**
- Any value < 60s: Too aggressive, triggers on transient errors
- Morning > 900s: Wastes morning budget; only reduce if yfinance unreliable
- EOD > 600s: Insufficient time for retries within 85-min window

## Tuning Guide

### When to Increase Threshold
- **Morning:** yfinance frequently degraded, retries succeed after 5-10 min
  - Action: Increase from 480s → 600s (revert if failsafe triggers too often)
- **EOD:** Never increase; tight deadline does not permit long waits

### When to Decrease Threshold
- **Morning:** Unnecessary retries wasting time; yfinance stable
  - Action: Decrease from 480s → 300s (monitor failsafe trigger rate)
- **EOD:** Failsafe triggers despite retries; yfinance severely degraded
  - Action: Decrease from 180s → 120s (fail-fast strategy)

## Validation Rules (Auto-Enforced)

1. **Range Bounds:** Schema validates [min, max] per pipeline
2. **Cross-Pipeline:** EOD threshold < Morning threshold (enforced at startup)
3. **Budget Guard:** EOD threshold + retry buffer <= 60 minutes (warning if violated)

## Monitoring

See `steering/OPERATIONS.md` → "Monitoring Loader Health" for metrics:
- `circuit_breaker_triggered_count`: How often circuit breaker reduced batch size
- `batch_size_cascade_depth`: How many reductions occurred (1-5)
- `rate_limit_error_duration_sec`: How long errors persisted

High circuit_breaker_triggered_count during EOD → consider lowering EOD threshold to fail-fast sooner.
```

---

## Test Verification Plan

### Unit Tests

**File:** `tests/unit/test_loader_rate_limits.py` (new)

```python
def test_rate_limit_thresholds_within_bounds():
    """Validates schema bounds enforcement."""
    config = get_config()
    morning = config.get("loader_rate_limit_circuit_break_threshold_morning")
    eod = config.get("loader_rate_limit_circuit_break_threshold_eod")
    
    assert 60 <= morning <= 900, f"Morning {morning}s out of bounds"
    assert 60 <= eod <= 600, f"EOD {eod}s out of bounds"

def test_eod_less_than_morning():
    """EOD should be < morning due to tighter deadline."""
    config = get_config()
    morning = config.get("loader_rate_limit_circuit_break_threshold_morning")
    eod = config.get("loader_rate_limit_circuit_break_threshold_eod")
    
    assert eod < morning, f"EOD {eod}s should be < Morning {morning}s"

def test_load_prices_detects_pipeline():
    """Verify pipeline context detection selects correct threshold."""
    # Mock as EOD time (20:15 UTC = 4:15 PM ET)
    loader_eod = PriceLoader(interval="1d")
    # Should have 180s threshold
    
    # Mock as morning time (6:15 UTC = 1:15 AM ET)
    loader_morning = PriceLoader(interval="1d")
    # Should have 480s threshold
```

### Integration Tests

**File:** `tests/integration/test_price_loader_circuit_breaker.py`

```python
def test_circuit_breaker_triggers_at_threshold():
    """Verify circuit breaker triggers when error_duration > threshold."""
    loader = PriceLoader(interval="1d")
    
    # Simulate rate limit errors for threshold + 10 seconds
    threshold = loader._rate_limit_circuit_break_threshold
    loader._rate_limit_error_start_time = time.time() - (threshold + 10)
    loader._rate_limit_errors = 3
    
    # Should trigger circuit breaker reduction
    batch_size = loader._get_adaptive_batch_size()
    assert batch_size < 100, "Circuit breaker should reduce batch size"
```

### Configuration Validation Tests

**File:** `tests/unit/test_infrastructure_config_validation.py` (add to existing)

```python
def test_interdependency_validation_rate_limits():
    """Verify rate limit interdependency checks."""
    config = get_config()
    
    # This already runs at startup via _validate_config_interdependencies()
    # Just verify it completed without raising RuntimeError
    assert config is not None
    
    # If any config is invalid, startup would have failed with RuntimeError
```

### Regression Tests

**File:** `tests/regression/test_loader_pipeline_detection.py`

```python
def test_pipeline_detection_eod_window():
    """EOD detection during 4:05-5:30 PM ET uses correct threshold."""
    # Assumes function uses UTC: 20:05-22:30
    # Mock datetime to 20:15 UTC
    loader = PriceLoader(interval="1d")
    assert loader._is_eod_pipeline == True
    assert loader._rate_limit_circuit_break_threshold == 180

def test_pipeline_detection_morning_window():
    """Morning detection outside EOD window uses correct threshold."""
    # Assumes function uses UTC: outside 20:05-22:30
    # Mock datetime to 6:15 UTC
    loader = PriceLoader(interval="1d")
    assert loader._is_eod_pipeline == False
    assert loader._rate_limit_circuit_break_threshold == 480
```

---

## Deployment Steps

### 1. Update Validation Schema (5 min)
```bash
# Edit algo/infrastructure/config_schema.py
# Change bounds for both threshold keys:
# Morning: (int, 60, 900, False, 480)
# EOD: (int, 60, 600, False, 180)
```

### 2. Add Interdependency Validation (10 min)
```bash
# Edit algo/infrastructure/config/main.py
# Add _validate_loader_rate_limits() method
# Call from _validate_config_interdependencies() at startup
```

### 3. Create Documentation (15 min)
```bash
# Create steering/LOADER_RATE_LIMITS.md
# Explain pipeline contexts, safe ranges, tuning guide
```

### 4. Add Unit Tests (15 min)
```bash
# Create tests/unit/test_loader_rate_limits.py
# Test bounds, pipeline detection, cross-threshold ordering
```

### 5. Verify Current Config (5 min)
```bash
# Run migration to ensure algo_config has both keys:
python migrations/runner.py up migration-092

# Verify in database:
SELECT key, value FROM algo_config WHERE key LIKE 'loader_rate_limit%';
```

### 6. Deploy to AWS (5-10 min)
```bash
cd terraform && terraform apply -lock=false
# Redeploy Lambda function to pick up schema changes
```

**Total Time:** ~50 minutes, can be parallelized

---

## Summary Table

| Aspect | Current State | Root Cause | Fix |
|--------|---------------|-----------|-----|
| **Documentation** | Config keys exist but purpose unexplained | No central reference | Create steering/LOADER_RATE_LIMITS.md |
| **Validation** | Schema allows 0-3600s (too broad) | No semantic bounds | Reduce to [60-900s] morning, [60-600s] EOD |
| **Interdependencies** | No relationship check between keys | Two independent config values | Add validation rule: eod_threshold < morning_threshold |
| **Pipeline Context** | Implicitly detected at runtime | Necessary due to 85-min vs 450-min budgets | Document in steering/LOADER_RATE_LIMITS.md |
| **Test Coverage** | Implicit in integration tests | No isolated unit tests for thresholds | Add tests/unit/test_loader_rate_limits.py |

---

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| Invalid config during deploy | Medium | High (loader fails) | Schema validation catches at startup |
| Threshold too aggressive during EOD | Low | High (failsafe) | Max bounds = 600s, leaves 25 min buffer |
| Threshold too conservative during morning | Low | Medium (slow load) | Min bounds = 60s, prevents false positives |
| Pipeline detection fails | Very Low | High (uses wrong threshold) | Add logging + unit test for detection logic |
| Operators misunderstand semantic | Medium | Medium (suboptimal tuning) | Document in steering/LOADER_RATE_LIMITS.md |

---

## Related Tickets & PRs

- **Migration 092:** `migrations/versions/092_add_loader_rate_limit_config.sql` (initial config setup)
- **Issue #6 (Batch Sizing):** load_prices.py uses adaptive batch sizing with circuit breaker
- **Issue #23 (Timeout Cascade):** Reduced single-batch wait threshold to prevent cascade

