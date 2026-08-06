# Comprehensive Orchestrator Issue Audit - 2026-08-06

## Current Status
- **Latest Run:** 2026-08-06 Evening (--force flag)
- **All 9 Phases:** Executed successfully
- **Dry-Run Mode:** Phase 6/8 skipped (expected)
- **Test Coverage:** Evening runs only - needs morning market-hours testing

## Known Fixes Applied (Verify)
1. Phase 6 constraint passthrough - SUPPOSEDLY FIXED 2026-08-06
   - File: algo/orchestration/orchestrator.py:1786
   - Check: Does Phase 6 actually receive exposure_constraints from Phase 5?

2. Phase 7 exposure_constraints dependency - SUPPOSEDLY FIXED 2026-08-06  
   - File: algo/orchestrator/phase7_signal_generation.py:1598
   - Check: Halts if constraints not provided? Correct behavior?

3. Phase 8 exposure_constraints parameter - SUPPOSEDLY FIXED (Commit 35c9b36db)
   - File: algo/orchestrator/phase8_entry_execution.py
   - Check: Uses parameter when executor unavailable?

## Actual Issues Found
- Permission denied on materialized view refresh (Phase 9) - EXPECTED in LOCAL_MODE

## Missing Test Coverage
- [ ] Market hours real execution test (--morning flag)
- [ ] Phase 6 exit execution in REAL mode (not dry-run)
- [ ] Phase 8 entry execution in REAL mode with actual trade execution
- [ ] Phase 6 concentration limit enforcement (sector/position size)
- [ ] Phase 6 stop-loss calculation with actual positions
- [ ] Phase 7 halt detection when market regime "CORRECTION"
- [ ] Phase 8 pre-trade checks with insufficient cash
- [ ] Phase 8 earnings blackout filtering
- [ ] Race condition: concurrent Phase 6/8 writes during high-volatility execution

## Critical Path to Bulletproof
1. Run orchestrator in REAL mode (execution_mode='auto', alpaca_paper_trading=True initially)
2. Instrument Phase 6/8 logging for trade execution decisions
3. Verify database state after each execution
4. Check for orphaned trades, position mismatches
5. Validate stop-loss calculations against live market data
6. Test concentration limit enforcement with multi-position portfolio
7. Test earnings blackout during signal generation
8. Test market hours guards during edge times (9:29 AM, 3:59 PM, 4:01 PM)

## Next Steps  
1. Check if recent Phase 6/8 "fixes" actually work in real execution mode
2. Find incomplete implementations (particularly around constraint passing)
3. Fix all found issues properly
4. Re-test with real execution
5. Iterate until no new issues found
