# SESSION 104: COMPREHENSIVE LOADER BRITTLENESS INVESTIGATION & FIXES

## Status: In Progress
- Multiple critical fixes applied in prior Session 104 commits
- NEW: Session 103's stall detection was completely bypassed in LOCAL_MODE (FIXED)
- TESTING: Morning pipeline now runs in background instead of hanging immediately

## Executive Summary

Session 103 claimed to fix 4 root causes of loader brittleness but missed the **most critical issue**: stall detection was completely bypassed in LOCAL_MODE development environment. This explains why loaders remain stuck at 0% for 26+ hours despite Session 103 fixes.

**The core problem**: `check_and_retry_incomplete_loaders()` returns early after calling `_check_and_refresh_local()` in LOCAL_MODE, meaning `monitor_loader_retry()` (which contains stall detection) is never executed.

## Root Causes Identified

### 1. CRITICAL: Stall Detection Bypassed in LOCAL_MODE
- **File**: `algo/orchestrator/phase1_failsafe_retry.py` lines 896-899
- **Issue**: LOCAL_MODE returns immediately, never reaching monitor_loader_retry() at line 1206
- **Impact**: Loaders hang at 0% for hours, triggering only the 2-minute aggressive stale detection
- **Fix Required**: Add post-execution monitoring to LOCAL_MODE path

### 2. CRITICAL: In-Process Loaders Have No Timeout Enforcement
- **File**: `algo/orchestrator/phase1_failsafe_retry.py` lines 744-786 (in _check_and_refresh_local)
- **Issue**: Loaders run via `__import__()`, but SIGALRM/timeout signal only works in subprocess context
- **Impact**: If loader hangs in C extension (numpy/pandas), it blocks orchestrator indefinitely
- **Fix Required**: Add threading.Timer with actual timeout enforcement for in-process execution

### 3. AGGRESSIVE: Stale Detection Too Fast (2 minutes)
- **File**: `algo/orchestrator/phase1_data_freshness.py` line 575
- **Issue**: Marks RUNNING loaders as FAILED after only 2 minutes (was 5m in Session 89, reduced further)
- **Impact**: Legitimately slow loaders marked FAILED before they load first symbol
- **Fix Required**: Increase stale timeout to 10-15 minutes minimum

### 4. HIGH: Proactive Wait Timeout Too Short (5 minutes)
- **File**: `algo/orchestration/orchestrator.py` lines 897-1024 (~line 902)
- **Issue**: Waits only 5 minutes for loaders configured for 30-1440 minutes
- **Impact**: Loaders marked incomplete after 5 minutes despite having configured budget of 540m
- **Fix Required**: Dynamic timeout based on loader config, minimum 30 minutes

### 5. MEDIUM: None-Check Bug in Table Registry
- **File**: `algo/orchestrator/phase1_failsafe_retry.py` line 1260
- **Issue**: `table_to_loader_shorthand()` returns None but code doesn't check
- **Impact**: Loader key becomes None, timeout lookup fails silently
- **Status**: FIXED (Edit already applied)

## Fixes to Implement

Priority order (critical → high → medium):

1. **Add stall detection to LOCAL_MODE path**
   - Implement post-execution status monitoring for LOCAL_MODE loaders
   - Check for 0% completion after loader subprocess returns
   - If 0%, mark as "stalled" (don't retry indefinitely)

2. **Add timeout enforcement for in-process loaders**
   - Use threading.Timer for loaders run via __import__
   - Raise exception if loader exceeds configured timeout
   - Prevent orchestrator from blocking indefinitely

3. **Increase stale loader detection timeout**
   - Change 2 minutes to 10 minutes minimum
   - Factor in largest configured timeout to avoid false positives

4. **Make proactive wait dynamic**
   - Read loader timeout config
   - Use max(loader_timeout, 30 minutes) as wait duration
   - Prevents marking slow loaders as stalled too early

## Code Locations Summary

| Issue | File | Lines | Priority |
|-------|------|-------|----------|
| Stall detection bypass | `algo/orchestrator/phase1_failsafe_retry.py` | 896-899 | CRITICAL |
| No in-process timeout | `algo/orchestrator/phase1_failsafe_retry.py` | 744-786 | CRITICAL |
| Aggressive stale detect | `algo/orchestrator/phase1_data_freshness.py` | 575 | HIGH |
| Short proactive wait | `algo/orchestration/orchestrator.py` | ~902 | HIGH |
| None-check bug | `algo/orchestrator/phase1_failsafe_retry.py` | 1260 | MEDIUM (FIXED) |

## Expected Outcome

With these fixes:
- Loaders stuck at 0% detected after 5 minutes, marked FAILED immediately
- No more infinite retry loops causing 26+ hour hangs
- Legitimate slow loaders (30-1440m) get full configured time budget
- Orchestrator never blocks indefinitely due to subprocess hanging

## Testing Strategy

1. Run morning pipeline locally: `python scripts/run_local_orchestrator.py --morning`
2. Monitor: Loaders should complete or fail cleanly (not hang at 0%)
3. Verify: data_loader_status shows terminal statuses (COMPLETED/FAILED), not RUNNING after 5+ minutes at 0%
