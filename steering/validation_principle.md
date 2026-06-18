# Critical Validation Principle: Explicit vs Implicit Failures

## The Core Issue

Our codebase conflates two types of checks:
1. **Critical Validation** (authoritative): Must pass or we fail fast
2. **Best Effort** (heuristic): Can fall back to alternatives

The problem: Most checks are **written as critical** but **treated as best effort**.

## Examples from Codebase

### Example 1: Upstream Completeness Check
```python
# WHAT IT SAYS (comment):
"""Loaders depend on upstream. If upstream <95% complete, downstream should not proceed."""

# HOW IT'S IMPLEMENTED (code):
except Exception as e:
    return True  # Proceed anyway on exception
```

**Mismatch**: The design says "MUST check", but the implementation says "try to check, but proceed anyway"

### Example 2: Market Close Data Availability
```python
# WHAT IT SAYS (comment):
"""Check if SPY close data is available. Don't proceed without it."""

# HOW IT'S IMPLEMENTED (code):
if elapsed < 2400:
    return False  # Proceed with stale data
else:
    raise RuntimeError(...)
```

**Mismatch**: The design says "MUST verify", but the implementation says "wait 40 minutes, then proceed with fallback"

### Example 3: Watermark Read
```python
# WHAT IT SAYS (comment):
"""Determine incremental load point from watermark."""

# HOW IT'S IMPLEMENTED (code):
except Exception:
    return None  # Fall back to full refresh
```

**Mismatch**: The design is ambiguous — is full refresh a fallback or intended?

## The Pattern

**Pattern**: Check is written as "must validate" but implemented as "try to validate, fall back if needed"

**Why it happens**:
- Original developer intended partial/best-effort, added error handling
- Later developer assumes it's authoritative, relies on it
- Silent fallback masks infrastructure problems (which should fail fast)

## The Finance Principle

For a financial trading system:

### Authoritative Checks (MUST PASS)
- Data quality validation (no stale prices, no incomplete upstream)
- Infrastructure health (can we reach the database?)
- Configuration read (do we have operational parameters?)
- Upstream dependency completeness (is upstream 95%+?)

**Property**: Silent fallback to defaults is **unacceptable**
**Policy**: Must fail with explicit error

### Best Effort (CAN FALLBACK)
- Batch size optimization (try large, fall back to small)
- Source routing (yfinance unavailable, try Alpaca)
- Metric publication (nice to have, not critical)
- Heartbeat updates (monitoring info, not core data)

**Property**: Fallback to alternative is **acceptable**
**Policy**: Document and monitor the fallback

## How to Distinguish

### Authoritative Check
Ask these questions:
1. "If this fails, is the data quality compromised?" → YES = Authoritative
2. "Should downstream trust us if we skip this?" → NO = Authoritative
3. "Is this a security/compliance boundary?" → YES = Authoritative

### Best Effort
Ask these questions:
1. "Is there a documented alternative if this fails?" → YES = Best Effort
2. "Is skipping this a known performance/operational pattern?" → YES = Best Effort
3. "Does downstream have fallback logic for this?" → YES = Best Effort

## Code Patterns

### Pattern: Authoritative Check
```python
def check_critical_validation():
    """Validate something that blocks downstream processing."""
    try:
        result = query_database(critical_config)
        if result is None:
            logger.error("CRITICAL: Config missing from database")
            raise RuntimeError("Config not found")
        return result
    except DatabaseError as e:
        logger.critical("CRITICAL: Could not verify config due to DB error")
        raise RuntimeError(f"Config validation failed: {e}")
```

**Characteristics**:
- Exceptions are raised, not caught and ignored
- Missing data is explicit error, not silent fallback
- Clear log messages: "CRITICAL", "Cannot proceed"

### Pattern: Best Effort Check
```python
def try_optimize_batch_size():
    """Optimize batch size, but fall back to safe default if unsuccessful."""
    try:
        recent_latency = get_recent_request_latency()
        if recent_latency > 1.0:
            return 50  # Smaller batch
        return 100
    except Exception as e:
        logger.warning(f"Could not get latency: {e}, using default batch=100")
        return 100  # Safe fallback documented
```

**Characteristics**:
- Exceptions are caught and handled
- Fallback is **documented** and **expected**
- Log level is WARNING (not ERROR/CRITICAL)
- Fallback value is safe/reasonable

## Implementation Rules

### Rule 1: Authoritative Checks Must Have Clear Failure Path
**Bad**:
```python
try:
    validate_upstream()
except:
    logger.debug("...")
    proceed()
```

**Good**:
```python
try:
    validate_upstream()
except ValidationError as e:
    logger.critical(f"Validation failed: {e}")
    raise RuntimeError("Cannot proceed without validation")
```

### Rule 2: Best Effort Must Document Fallback
**Bad**:
```python
try:
    return compute_optimal_value()
except:
    return default_value
```

**Good**:
```python
try:
    return compute_optimal_value()
except ComputeError as e:
    logger.warning(f"Could not compute optimal: {e}. Using safe default.")
    return default_value  # Documented fallback
```

### Rule 3: Distinguish Query Failure from Missing Data
**Bad** (conflates two cases):
```python
try:
    result = db.query(key)
except:
    return default
# Doesn't know if: (a) DB failed or (b) key missing
```

**Good** (separates them):
```python
try:
    result = db.query(key)
except DatabaseError as e:
    logger.critical(f"Database error: {e}")
    raise  # Query failed — hard error
except KeyNotFoundError:
    logger.warning(f"Key '{key}' not in database, using default")
    return default  # Key missing — use default
```

## Audit Questions

For each exception handler in data/loader/orchestration code:

1. **Why are we catching this exception?**
   - To handle expected error? (Best Effort)
   - To hide infrastructure problem? (Bad)
   - To provide informative error? (Good)

2. **What happens if we re-raise instead of catching?**
   - Does Phase 1 detect loader failure? (Yes = re-raise)
   - Does downstream break without fallback? (No = can fallback)

3. **Is this check authoritative or best-effort?**
   - Does comment say "must validate"? (Authoritative)
   - Is fallback documented? (Best Effort)

4. **Can we tell from logs which path was taken?**
   - Clear ERROR/CRITICAL for auth failures? (Yes = good)
   - Clear WARNING for best-effort fallbacks? (Yes = good)

## References

For implementation details on the 9 specific issues, see [[fail_fast_audit]] in memory.
