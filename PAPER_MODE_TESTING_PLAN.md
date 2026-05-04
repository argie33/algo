# Paper-Mode Testing Plan

**Before AWS Deployment:** 5-10 days of local testing  
**Goal:** Verify system behavior matches design intent  
**Risk Level:** ZERO (paper trading, no real money)  
**Success Criteria:** All checks pass consistently

---

## Why Paper-Mode Testing?

✅ Validate decisions with real market data  
✅ Test multiple market conditions (bull, flat, bearish)  
✅ Verify P&L tracking is accurate  
✅ Catch edge cases before AWS  
✅ Build confidence in system behavior  

---

## Testing Schedule

### Day 1: Baseline Test
Run full orchestrator, verify:
- All 8 phases execute without errors
- Portfolio snapshot created
- P&L calculations match expected
- No unexpected trades (or expected trades match plan)

### Days 2-4: Varied Market Conditions
- Bull day (high exposure tier): Verify entries respected at tier max
- Flat/uncertain day: Verify position sizing is conservative
- Bearish pressure: Verify circuit breaker doesn't trigger falsely, entries reduce

### Days 5-7: Edge Cases
- Zero signals day: System manages existing positions, no harm
- Multiple signals same day: Verify tier max is respected
- Position approaching profit target: Verify partial exit works
- Pyramid add eligible: Verify risk ceiling enforced

### Days 8-10: Stress Test
- Large move up: Verify stops ratchet, pyramids add correctly
- Large move down: Verify stops work, early exits trigger
- High volatility: Verify no false breaker triggers
- Mixed winners/losers: Verify portfolio P&L tracking

---

## Daily Testing Procedure

### Step 1: Morning (Before Market Close)

```bash
# Check if system will run today
python -c "from algo_orchestrator import Orchestrator; from algo_config import get_config; print('Ready to run')"
```

### Step 2: At Market Close (After 4pm ET)

```bash
# Run the orchestrator
python algo_orchestrator.py
```

This will:
- Execute all 8 phases
- Create/update positions
- Log all decisions
- Generate portfolio snapshot

### Step 3: After Execution

```bash
# Run paper-mode test harness
python paper_mode_testing.py
```

This will:
- Validate execution quality
- Check decision logic
- Generate daily report
- Compare with baseline

### Step 4: Review Report

Check the report in `paper_mode_reports/test_{date}.json`:
- Verify all phases: PASS
- Verify entry decisions quality (not quantity)
- Verify risk metrics reasonable
- Note any unexpected behaviors

### Step 5: Validation Checklist

Use `PAPER_MODE_VALIDATION_CHECKLIST.md`:
- [ ] All 8 phases executed?
- [ ] Decisions high quality?
- [ ] Risk metrics reasonable?
- [ ] P&L tracking accurate?
- [ ] No errors/warnings?

---

## What to Monitor

### Decision Quality

**Good Signs:**
- System rejects more signals than it accepts (conservative)
- Entries are high-grade (B+ or better)
- Entry prices not extended (not 20%+ from 52w low)
- Stop losses are rational, not too tight
- Position sizes match tier constraints

**Bad Signs:**
- System entering 10+ trades per day (too aggressive)
- Entering D-grade signals (quality too low)
- Stop losses extremely tight (<2% risk per share)
- Ignoring tier constraints
- No pyramid adds even when eligible

### Risk Management

**Good Signs:**
- Position sizes scale with drawdown
- Total positions never exceed 6
- Concentration never exceeds 50%
- Entry frequency matches tier (4/day in strong, 1/day in weak)
- Risk multipliers apply correctly

**Bad Signs:**
- Same size regardless of market exposure
- Portfolio holds 8+ positions
- One stock >50% of portfolio
- Entering same frequency regardless of tier
- Drawdown adjustments not working

### P&L Tracking

**Good Signs:**
- Winners show increasing P&L
- Losers show decreasing P&L
- Portfolio value updates daily
- Unrealized P&L = sum of position P&Ls
- Partial exits reduce position correctly

**Bad Signs:**
- P&L frozen or not updating
- Numbers don't add up
- Reconciliation shows large drift
- Losing money consistently (system issue, not market)

---

## Exit Conditions

### Stop Testing If:
- ❌ Unrecoverable error (database, Alpaca connection)
- ❌ Silent failures (trades not logged, positions not tracked)
- ❌ Data corruption (P&L incorrect, position count wrong)
- ❌ Safety failure (system enters when circuit breaker should halt)

### Continue Testing If:
- ✅ Normal operational issues (can be fixed in code)
- ✅ Market-driven losses (not system error)
- ✅ Unexpected but correct behavior

---

## Go/No-Go Criteria

### GO to AWS ✅
After 5-10 days if:
- [ ] All 8 phases execute every day without errors
- [ ] Entry decisions are high-quality (rejecting bad signals)
- [ ] Risk management enforced properly
- [ ] P&L tracking accurate
- [ ] Pyramid adds work when eligible
- [ ] Circuit breakers don't trigger falsely
- [ ] Zero critical bugs found
- [ ] System behaves as designed in strategy

### NO-GO / Investigate ❌
If:
- [ ] Unexpected errors or crashes
- [ ] Silent failures (no log, no record)
- [ ] Risk management not enforced
- [ ] P&L tracking broken
- [ ] Too many false entries/exits
- [ ] Data corruption detected

---

## Testing Dashboard

Track these metrics daily:

```
Date        Entries Exits Adds P&L     Portfolio  Drawdown  Tier
----        ------- ----- ---- ------  ---------  --------  ----
2026-05-05  2       0     0    +340    75,516    0.0%      healthy
2026-05-06  1       1     1    -123    75,393    0.0%      healthy
2026-05-07  0       0     0    +156    75,549    0.0%      pressure
2026-05-08  3       0     0    +890    76,439    0.0%      confirmed
2026-05-09  0       2     0    +450    76,889    0.0%      pressure
```

**Dashboard captures:**
- Entry/exit/add counts
- Daily P&L
- Portfolio value progression
- Drawdown trend
- Market tier (exposure policy)

---

## Reports Generated

### Daily Report: `paper_mode_reports/test_{date}.json`
```json
{
  "test_date": "2026-05-05",
  "status": "PASS",
  "phases": {
    "data_freshness": "OK",
    "circuit_breakers": "OK",
    "position_monitor": "OK",
    "exit_execution": "OK",
    "pyramid_adds": "OK",
    "signal_generation": "OK",
    "entry_execution": "OK",
    "reconciliation": "OK"
  },
  "metrics": {
    "open_positions": 4,
    "portfolio_value": 75516.23,
    "entries_today": 2,
    "unrealized_pnl": 340.50
  }
}
```

### Weekly Summary
After 5 days, review:
- All daily reports pass? ✓
- Consistent behavior across market conditions? ✓
- P&L tracking accurate? ✓
- No critical issues found? ✓

---

## Troubleshooting Guide

### If entries are too aggressive (10+ per day)
**Likely cause:** Exposure tier not constraining properly  
**Fix:** Check `algo_market_exposure_policy.py`, verify max_new_positions_per_day

### If P&L doesn't match expected
**Likely cause:** Price data stale or incorrect  
**Fix:** Check `algo_position_monitor.py`, verify current_price lookup

### If same-day duplicate entries
**Likely cause:** Idempotency check not working  
**Fix:** Check `algo_trade_executor.py`, verify duplicate detection

### If stops don't adjust
**Likely cause:** Stop ratchet logic not firing  
**Fix:** Check `algo_exit_engine.py`, verify chandelier trail calculation

---

## Once Testing Complete ✅

1. **Document results**
   - All 5+ days passed
   - No critical issues
   - P&L tracking accurate
   - Risk management working

2. **Prepare for AWS**
   - Get AWS account ready
   - Set up CloudFormation
   - Configure EventBridge scheduler
   - Prepare environment variables

3. **Deploy**
   - Run CloudFormation template
   - Set Lambda environment vars
   - Configure EventBridge (5:30pm ET daily)
   - Run first AWS execution

4. **Monitor AWS**
   - Check CloudWatch logs
   - Verify Alpaca orders created
   - Monitor for errors
   - Compare with local testing

---

## Timeline

| Phase | Days | Action | Gate |
|-------|------|--------|------|
| Local Setup | 1 | Install deps, verify DB | Ready? |
| Baseline | 1 | Run single day test | Pass? |
| Validation | 4-6 | Test multiple conditions | 5+ passes |
| Review | 1 | Analyze all reports | Go? |
| AWS Deploy | 1 | Move to Lambda | Done! |

**Total:** 7-10 calendar days (6-8 trading days)

---

## Success Definition

System is ready for AWS when:
1. ✅ All 8 orchestrator phases execute daily without errors
2. ✅ Entries are high-quality (grades B or better)
3. ✅ Risk management properly constrains position sizes
4. ✅ P&L tracking matches across database and Alpaca
5. ✅ Pyramid adds work correctly when eligible
6. ✅ Exits trigger at correct prices/conditions
7. ✅ Circuit breakers work without false positives
8. ✅ Zero critical bugs or silent failures

**If all 8 are true:** Deploy to AWS with confidence  
**If any are false:** Fix in code, restart testing

---

## Questions During Testing?

1. **Entry doesn't look right?** → Check PAPER_MODE_VALIDATION_CHECKLIST.md
2. **P&L calculation off?** → Verify price data, check formula
3. **Unexpected exit?** → Review exit priority chain (11 rules)
4. **Risk sizing wrong?** → Check drawdown adjustment, exposure multiplier
5. **Something else?** → Check algo_audit_log for detailed execution trace

---

## Next Steps

1. **Today:** Run `python paper_mode_testing.py` once to baseline
2. **Tomorrow:** Review output, confirm system is running
3. **Days 2-10:** Run daily, monitor for issues
4. **Day 11:** Review all reports, make GO/NO-GO decision
5. **Day 12+:** If GO, proceed to AWS deployment

**Command to start:**
```bash
python paper_mode_testing.py
```

**Command to deploy after testing:**
```bash
# When ready for AWS:
aws cloudformation create-stack --template-body file://template-webapp-lambda.yml ...
```

---

**Ready?** Start paper-mode testing now. System is built, tested locally, and ready to validate with real market data.
