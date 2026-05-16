# EXECUTION ROADMAP — SESSION 51 CONTINUATION

## Current Status
- ✅ **9 critical bugs fixed** (Sector rotation, SMA window, RS gate, TD Sequential, scores.js route, response shape, volume ratio, accumulation)
- ⏳ **21 remaining bugs identified** and prioritized
- 📋 **4 comprehensive tasks created** (Task #2-5)

## Recommended Execution Strategy

### PHASE 1: HIGH-IMPACT BUG FIXES (2-3 hours)
Focus on CRITICAL bugs that affect trading decisions:

**CRITICAL (5 bugs) — Do these**:
1. ✓ Signal age gate staleness (FIXED)
2. **TD Sequential rule numbering** — 15 min (comments only, no logic change)
3. **stage2_phase dips skipping** — 30 min (fix loop condition)
4. **base_detection peak logic** — 45 min (understanding + testing)
5. **pocket_pivot double-count** — 15 min (simple index fix)

**HIGH (6 bugs) — Do these**:
- _period_return calendar days (30 min)
- volume_dryup windows comparison (30 min)
- Trend component missing slope (45 min - might skip if low impact)
- three_weeks_tight off-by-one (15 min)
- [DEFER] SMA-150 DESC ordering (5 min - low risk since it works by accident)
- [DEFER] TD Sequential last_9_date (complex, low-impact since rule catches other cases)

**Estimate**: 3-4 hours to fix all CRITICAL + HIGH bugs

### PHASE 2: LOCAL VERIFICATION (3-4 hours)
Once bugs fixed:
1. **Data Pipeline** — python3 run-all-loaders.py (30 min)
2. **Orchestrator** — python3 algo_orchestrator.py --mode paper --dry-run (30 min)
3. **Frontend** — Manual test all 30+ pages (2 hours)
4. **Edge Cases** — Test portfolio states (30 min)

### PHASE 3: AWS DEPLOYMENT (20 min deploy + 1-2 hours validation)
1. **Push to main** — Triggers GitHub Actions (20 min auto-deploy)
2. **Validation** — CloudWatch logs, API tests, Alpaca connection (1 hour)
3. **Monitoring** — Live trading for 24-48 hours (passive)

## Decision Points

### IF Short on Time (need to ship soon):
**Skip to Phase 3** with just the 9 bugs already fixed:
- The 9 bugs fixed are the highest-impact (sector rotation, SMA window, RS gate, etc.)
- Remaining 21 bugs are mostly edge cases or documentation mismatches
- System is already "production ready" per prior assessments
- Risk: Some edge cases in TD Sequential, stage detection, etc. won't fire

### IF Want Maximum Confidence (proper approach):
**Do all 3 phases** — 8-10 hours total work:
- Complete all fixes (4 hours)
- Thorough local testing (4 hours)  
- Deploy + validate (2 hours)
- Result: Production-ready with extremely high confidence

## My Recommendation

**Do Phases 1 + 2 + 3** (8-10 hours, properly paced):
- Fixes: 3-4 hours (hit CRITICAL + HIGH bugs)
- Testing: 3-4 hours (full pipeline verification)
- Deploy: 1-2 hours (AWS + validation)

This gives you:
✅ All critical bugs fixed
✅ Full end-to-end verification
✅ Live system running on AWS
✅ Confidence the system actually works in production
✅ Ready for real money trading

## Remaining Medium/Low Priority Bugs
- Documentation mismatches (pivot/accumulation) — Cosmetic
- Exit rule labeling — Cosmetic
- vol_decay 60d labeling — Documentation
- Orphaned endpoints — Can clean up later
- Can address in future optimization sessions

## Next Steps
1. Pick strategy (short/thorough)
2. Start Phase 1: Hit CRITICAL bugs one by one
3. Document progress in STATUS.md
4. Deploy once Phase 1-2 complete
