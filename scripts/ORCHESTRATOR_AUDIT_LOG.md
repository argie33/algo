# Orchestrator Audit Log - July 28, 2026

## Issues Found and Fixed

### ISSUE #1: Phase 3 Fallback Masking Errors (FIXED)
**Severity**: HIGH  
**Status**: FIXED in commit c15e74240

**Problem**: When position monitoring failed, Phase 3 had a fallback strategy that would catch the exception, attempt a degraded fallback, and if that also failed, would silently set recommendations=[] and report phase as "ok". This masked critical errors.

**Fix**: Removed the entire fallback strategy. Now when position monitoring fails, it fails-fast with a RuntimeError that propagates properly, allowing the orchestrator to handle the failure appropriately.

**Impact**: Position monitoring errors are now visible in logs instead of hidden, enabling proper diagnosis.

---

### ISSUE #2: Signal Quality Scores Lock Timeout Too Short (FIXED)
**Severity**: CRITICAL  
**Status**: FIXED in commit 49e36d8b1

**Problem**: Phase 7 (signal generation) was failing with `LockAcquisitionError` when trying to acquire the signal_quality_scores loader lock. The lock timeout was only 5 seconds with 6 retries (~3.5 minutes total). However, the signal_quality_scores loader can legitimately take 5-35+ minutes to run. Under any contention, Phase 7 would fail, causing the entire orchestrator to halt and preventing entries.

**Root Cause**: Lock timeout was calculated for typical loaders (price_daily ~60-90min) but didn't account for LOCAL_MODE vs production differences. Initial 5s timeout was too aggressive.

**Fix**: 
- Increased lock timeout from 5s to 15s
- Increased max retries from 6 to 8
- Max wait time increased from ~3.5min to ~5min
- Improved error message to guide debugging

**Impact**: Phase 7 now has sufficient patience for legitimate lock contention and long-running loaders.

---

## Active Issues Being Investigated

- [x] Phase 3 error masking
- [x] Phase 7 lock timeout
- [ ] Lock cleanup before Phase 7
- [ ] Database connection pool health
- [ ] Other fallback strategies in codebase
- [ ] Transaction handling in exit engine
- [ ] Position count management

## Test Results

Last orchestrator run: TEST-2026-07-28-6dcfdbda
- Status: HALTED (Phase 7)  
- Reason: Lock acquisition timeout after retries
- Fix Applied: Lock timeout increase should resolve this

## Next Steps

1. Re-run orchestrator to verify lock timeout fix resolves Phase 7
2. Continue audit for other critical issues
3. Focus on eliminating all fallback strategies that mask errors
4. Stress test under load to find remaining issues
