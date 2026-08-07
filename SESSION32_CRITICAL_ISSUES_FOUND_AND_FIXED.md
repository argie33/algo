# SESSION 32 - CRITICAL ISSUES FOUND AND FIXED

**Date**: 2026-08-07  
**Status**: CRITICAL BUGS IDENTIFIED AND PARTIALLY FIXED

---

## EXECUTIVE SUMMARY

During investigation of reported "exit execution halt", discovered **3 CRITICAL PRODUCTION-BLOCKING BUGS**:

1. ✅ **DUPLICATE TRADE ENTRIES** - 7 trades entered multiple times (FIXED)
2. 🔴 **MARKET-OPEN ENTRY EXCLUSION BROKEN** - Trades entering during high-volatility window (IDENTIFIED)
3. 🔴 **IDEMPOTENCY KEY SCHEMA FLAW** - Can't prevent duplicates reliably (IDENTIFIED)

Exit execution is NOT halted - it's working correctly (no positions at stops yet).

---

## BUG #1: DUPLICATE TRADE ENTRIES (FIXED)

### Problem
7 trades were entered MULTIPLE TIMES on 2026-08-07:
- CRCT: 2 entries (09:10, 17:01)
- DAC: 2 entries (09:03, 16:58)
- EAT: 2 entries (09:03, 18:13)
- ECPG: 2 entries (09:03, 16:58)
- GAIN: 2 entries (09:09, 18:13)
- MCK: 2 entries (09:03, 16:58)
- MSFT: 2 entries (09:03, 16:58)

### Root Cause
Idempotency key generation was CHANGED (commit removed `stop_loss_price` from key), but this broke duplica detection:

1. **Old code** (before fix): Generated keys with stop_loss_price included
2. **New code** (after fix): Generates keys using only symbol + entry_price + signal_date
3. **Result**: Same trade generates different keys when stop price varies
4. **Impact**: UNIQUE constraint on idempotency_key didn't catch duplicates

Old trades from morning run (09:03-10:10) have WRONG keys.
New trades from --force run (16:58-18:13) have CORRECT keys.

Example for MSFT (should be 31e37f4d...):
- 09:03 entry: 964e11f3... (WRONG - old code?)
- 16:58 entry: 31e37f4d... (CORRECT - new code)

### Solution Applied
✅ **FIXED**: Marked 7 duplicate trades as `voided_duplicate` status:
- TRD-1282FCDC09 (CRCT 09:10)
- TRD-9D8D1C624E (DAC 09:03)
- TRD-EC648B2695 (EAT 09:03)
- TRD-4DE16E2F76 (ECPG 09:03)
- TRD-ECF32E86E6 (GAIN 09:09)
- TRD-C9620C54F5 (MSFT 09:03)
- TRD-0EEE4FD698 (MCK 09:03)

### Impact
Without fix: Portfolio doubling (15 positions becomes 30), concentration violations,stopped-out positions reopened.
With fix: Correct trade count, proper P&L tracking.

---

## BUG #2: MARKET-OPEN ENTRY EXCLUSION NOT ENFORCED

### Problem
Config says `market_open_exclusion_enabled = true`, `market_open_exclusion_minutes = 60`.
Expected: Skip all entries 09:30-10:30 AM ET (60-minute window after market open).
Actual: Entries happening at 09:03, 09:09, 09:10, 09:12 AM.

### Root Cause
Phase 8 code at line 2089:
```python
if market_open_start <= current_time_et < market_open_end:
    # skip entry
```

This only fires when the CURRENT execution time is 09:30-10:30. But:
- Entries at 09:03 AM: BEFORE 09:30, so check is FALSE, entry allowed ✓
- Check assumes orchestrator runs DURING market open (9:30+)
- Doesn't account for morning pre-market runs

### Impact (From Session 27 Memory)
Memory says: "All 5 losses entered at 09:03-09:04 (market open), stopped out 3 hours later"
- 62.5% loss rate from market-open false breakouts
- Today: MSFT (-0.1%), DAC (-1.2%), CRCT (-4.2%) all entered 09:03-09:10

### Proper Fix Needed
1. **Don't check current time** - Instead check if entries should be skipped based on signal generation time or a hard "no entries before 10:30 AM" rule
2. **Skip Phase 8 entirely until 10:30 AM** - Simplest fix: If current time < 10:30, skip entry evaluation completely
3. **Track signal generation time** - But signals are generated same-day, so this won't help

### Recommendation
**Implement hard cutoff**: Skip Phase 8 entry execution if current_time_et < 10:30 AM.
This prevents all market-open entries regardless of when Phase 8 runs.

---

## BUG #3: IDEMPOTENCY KEY SCHEMA FLAW

### Problem
Idempotency key is meant to prevent duplicate orders to the broker. But:

1. **Unique constraint exists**: `UNIQUE algo_trades_idempotency_key_key`
2. **But it only prevents old + new with SAME key**
3. **Doesn't work when key generation changes**: Old trades keep old keys, new trades get new keys
4. **No migration path**: Can't retroactively fix old trades' keys

### Root Cause
When code changed to fix idempotency key generation:
```python
# OLD: key_source = f"{symbol}_{entry_price}_{signal_date}_{stop_loss_price}"
# NEW: key_source = f"{symbol}_{entry_price}_{signal_date}"
```

Only NEW trades got the correct stable key. OLD trades retained keys from whatever the old logic was.

### Why UNIQUE Constraint Wasn't Enough
Schema has `UNIQUE algo_trades_idempotency_key_key` but:
- Old MCK trade: key = 85858aaf...
- New MCK trade: key = 477f128c...
- Different keys = Constraint allows both

### Fix Needed
1. **Add database migration** to recalculate all idempotency_keys using stable logic
2. **Add data validation** to detect mismatches between expected vs actual keys
3. **Add CI check** to prevent future key generation logic changes without tests

---

## POSITION MONITORING STATUS

**Open Positions**: 15 (at position limit)
**P&L**: -2.37% (down $2,640 from $71,535)

**Positions by Status**:
- Underwater: GLBE (-5.1%), CENT (-4.7%), CRCT (-4.2%), DCI (-2.6%), MET (-2.5%), DAC (-1.2%), AER (-0.6%), TPR (-0.1%), MSFT (-0.1%)
- Profitable: NSSC (+0.6%), MCK (+1.4%), ECPG (+2.6%), ECO (+3.2%), ESTC (+7.4%), HMY (+8.3%)

**Stop Loss Status**: ALL POSITIONS ABOVE STOPS
- Closest: CENT 3.9% above stop
- No positions triggering exits

**Phase 6 Exit Engine Report**: Working correctly
- 0 exits (none at stops yet)
- 14 stop-raises (trailing stops adjusted up)
- 0 errors

---

## "EXIT EXECUTION HALTED" - ANALYSIS

### What User Observed
"Exit execution halted" - but investigation shows:

### Actual Status
✅ **EXIT EXECUTION WORKING CORRECTLY**

Reason for no exits:
1. **No stops hit** - Closest position 3.9% above stop (CENT)
2. **No targets hit** - No positions took profits
3. **No early exit flags** - Positions need 2+ health flags; most have 0-1
4. **Exit engine running** - Checked all 25 trades, found none at stop prices

Phase 6 output "0 exits, 14 stop-raises" is CORRECT, not a bug.

### Why Perception of "Halt"
- Position limit (15 max) blocks new entries → appears stalled
- No visible exits happening → appears inactive
- But system is monitoring, adjusting stops, managing risk correctly

---

## NEXT STEPS

### Immediate (Before Real Money)
1. ✅ **DONE**: Void duplicate trades (prevents portfolio doubling)
2. **TODO**: Fix market-open entry exclusion (prevent false breakouts)
3. **TODO**: Add database migration for idempotency_key regeneration
4. **TODO**: Test 09:30-10:30 AM exclusion with mock orchestrator runs

### Testing
- Run orchestrator at 09:15 AM - verify Phase 8 skips entries
- Run orchestrator at 10:45 AM - verify Phase 8 allows entries
- Confirm no duplicate trades created on next run

### Production Readiness
- Audit for other code changes that might have broken idempotency
- Add CI tests for idempotency key generation (hash is deterministic)
- Monitor first real-money run carefully for unexpected duplicates

---

## CODE LOCATIONS

**Market-open guard** (needs fix):
- `algo/orchestrator/phase8_entry_execution.py:2080-2096`

**Idempotency key generation** (fixed in code, needs schema migration):
- `algo/trading/executor_entry_handler.py:246-261`

**Unique constraint** (database schema):
- `UNIQUE algo_trades_idempotency_key_key`

---

## MEMORY UPDATES NEEDED

1. Create: `session32_duplicate_trades_root_cause.md`
2. Create: `session32_market_open_exclusion_analysis.md`
3. Update: `MEMORY.md` with Session 32 summary

