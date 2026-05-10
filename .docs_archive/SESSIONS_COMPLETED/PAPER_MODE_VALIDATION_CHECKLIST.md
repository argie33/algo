# Paper-Mode Testing Validation Checklist

**Purpose:** Verify system behavior before AWS deployment  
**Duration:** 5-10 trading days (multiple market conditions)  
**Mode:** Paper trading (no real money risk)  
**Success Criteria:** All checks pass consistently

---

## Daily Execution Checklist

### Phase 1: Data Freshness
- [ ] Latest price data loaded (within 1 hour)
- [ ] All required tables have recent data
- [ ] No CRITICAL data patrol findings
- [ ] Signal data current

**Expected:** PASS (allows orchestrator to continue)

### Phase 2: Circuit Breakers
- [ ] All 8 breakers evaluated
- [ ] No unexpected halts (unless market condition warrants)
- [ ] Drawdown calculation correct
- [ ] VIX check functional

**Expected:** Most days PASS (no halt), occasional halt is OK if justified

### Phase 3: Position Monitor
- [ ] All open positions evaluated
- [ ] Health flags detected correctly
- [ ] Early exit signals triggered for deteriorating positions
- [ ] P&L tracking accurate

**Expected:** PASS (positions monitored correctly)

### Phase 4: Exit Execution
- [ ] Stop losses properly set on existing positions
- [ ] Exits trigger at correct price levels
- [ ] Partial exit targets evaluated
- [ ] Stop ratchets work correctly

**Expected:** Varies (exits happen when conditions met)

### Phase 4b: Pyramid Adds
- [ ] Qualifying positions identified
- [ ] Risk ceiling enforced (combined risk <= 1R)
- [ ] Add sizes correct (50%/25%/15%)
- [ ] No over-leveraging

**Expected:** 0-2 adds per day (when conditions met)

### Phase 5: Signal Generation
- [ ] All 6 tiers evaluated
- [ ] Weak signals rejected (good!)
- [ ] Strong signals qualified
- [ ] Swing scores calculated

**Expected:** 0-4 qualified trades (depends on market)

### Phase 6: Entry Execution
- [ ] Entries respect tier limits (max entries/day)
- [ ] Position sizing correct (all adjustments applied)
- [ ] Orders sent to Alpaca
- [ ] Stop losses and targets set

**Expected:** 0-4 entries (respects tier max)

### Phase 7: Reconciliation
- [ ] Positions synced with Alpaca
- [ ] P&L calculations accurate
- [ ] Portfolio snapshot created
- [ ] Drift detection working

**Expected:** PASS (always)

---

## Decision Quality Validation

### Entry Decisions
For each entry made, verify:
- [ ] Signal meets all hard gates (trend template >=7, stage 2, no earnings within 5 days, etc.)
- [ ] Swing score passes tier requirement
- [ ] Position size appropriate (base risk 0.75%, adjusted for drawdown/exposure)
- [ ] Entry price is reasonable (not extended)
- [ ] Stop loss is rational (not too tight, proper base-type placement)

**Action:** Review each trade in `algo_trades` table

### Exit Decisions
For each position, verify:
- [ ] Exit reason is valid (hard stop, Minervini break, time limit, etc.)
- [ ] Exit price is correct
- [ ] Partial exits follow the rules (T1/T2/T3 targets)
- [ ] Stop ratchets up properly (never down)

**Action:** Review closed positions and exit history

### Pyramid Add Decisions
For each add, verify:
- [ ] Position is profitable enough (+1R, +2R, +3R progression)
- [ ] Combined risk respects 1R ceiling
- [ ] Add size correct (50%, 25%, 15% of original)
- [ ] Max 3 adds enforced

**Action:** Check `algo_trade_adds` table

### Rejection Decisions (Most Important!)
For each signal that was REJECTED, verify rejection was correct:
- [ ] Grade too low? (Tier requires A or A+) ✓ Correct to reject
- [ ] Score too low? (Tier requires 60+) ✓ Correct to reject
- [ ] Market exposure too weak? (Caution/correction tier) ✓ Correct to reject
- [ ] Earnings within 5 days? ✓ Correct to reject
- [ ] Max entries already reached? ✓ Correct to reject
- [ ] Sector already overweight? ✓ Correct to reject

**Action:** Verify bad signals were actually blocked (conservative is good!)

---

## Risk Management Validation

### Position Sizing
For each entry, verify calculation:
- [ ] Risk dollars = portfolio × 0.75% × drawdown adjustment × exposure mult × phase mult
- [ ] Shares = risk dollars / (entry - stop)
- [ ] Position size <= 15% of portfolio
- [ ] Total concentration <= 50%
- [ ] Total positions <= 6

**Formula Check:** Risk dollars should be reasonable given portfolio size

### Drawdown Protection
- [ ] At -5%: Risk multiplier = 0.75 (reduce size 25%)
- [ ] At -10%: Risk multiplier = 0.5 (reduce size 50%)
- [ ] At -15%: Risk multiplier = 0.25 (reduce size 75%)
- [ ] At -20%: Trading halted completely

**Test:** Should see smaller position sizes if drawdown increases

### Exposure Policy Tier
- [ ] Market exposure 80-100%: 1.0x risk, 5 new/day (confirmed_uptrend)
- [ ] Market exposure 60-80%: 0.85x risk, 4 new/day (healthy_uptrend)
- [ ] Market exposure 40-60%: 0.5x risk, 2 new/day (pressure)
- [ ] Market exposure 20-40%: 0.25x risk, 1 new/day (caution)
- [ ] Market exposure 0-20%: 0.0x risk, 0 new/day (correction)

**Test:** Entry frequency and size should match tier

### Pyramid Add Risk Ceiling
For each add, verify:
- [ ] Combined risk = existing position risk + new add risk
- [ ] Combined risk <= original 1R
- [ ] If combined > 1R, reduce add size to fit
- [ ] Never allow over-leveraging

**Test:** Run scenario with position at +1.5R, verify add is constrained

---

## Market Condition Response

### Bull Market (Exposure 80-100%)
- [ ] System enters frequently (4-5/day)
- [ ] Position sizes normal
- [ ] Takes full profit targets
- [ ] Pyramid adds active

**Expected:** Aggressive but controlled

### Weak Market (Exposure 20-40%)
- [ ] System enters rarely (0-1/day)
- [ ] Position sizes halved
- [ ] Takes profits early
- [ ] Fewer pyramid adds

**Expected:** Defensive but not paranoid

### Correction (Exposure 0-20%)
- [ ] System blocks all NEW entries
- [ ] Manages existing positions only
- [ ] Tightens stops on winners
- [ ] Prepared for exits

**Expected:** Full defense mode

---

## Error Handling & Safety

### Database Errors
- [ ] Position sizer returns conservative value (no zeros)
- [ ] Breaker defaults to HALT if uncertain
- [ ] No position created if order fails
- [ ] Errors logged but don't crash system

**Test:** Check that failures are handled gracefully

### Order Rejection
- [ ] Order rejected by Alpaca → no position created ✓
- [ ] Trade record created, position not created ✓
- [ ] CRITICAL alert sent ✓

**Test:** Verify trade record exists but position doesn't

### Partial Fills
- [ ] Actual filled qty tracked (not requested qty)
- [ ] Risk calcs use actual qty
- [ ] Pyramid adds base on actual shares

**Test:** Check that system handles Alpaca partial fills

### Data Corruption
- [ ] Negative prices detected and floored
- [ ] NULL values handled (fallback to entry price)
- [ ] NaN values clamped to 0
- [ ] Division by zero prevented

**Test:** Verify defensive checks working

---

## P&L Tracking Validation

### Position P&L Calculation
For each position, verify:
- [ ] Entry price recorded correctly
- [ ] Current price fetched correctly (not stale)
- [ ] Unrealized P&L = (current - entry) × qty
- [ ] Percentage return calculated correctly

**Test:** Calculate manually for 1 position, compare with database

### Portfolio Snapshot
- [ ] Created after each orchestrator run
- [ ] Total portfolio value = cash + position values
- [ ] Unrealized P&L = sum of all position P&Ls
- [ ] Daily return = current value - previous day value

**Test:** Check that snapshots make sense

### Reconciliation Accuracy
- [ ] Alpaca positions synced to database
- [ ] No drift between systems (>0.1 share difference)
- [ ] P&L matches across systems

**Test:** Compare Alpaca account summary with database snapshot

---

## Integration Validation

### Orchestrator Flow
- [ ] All 8 phases execute in sequence
- [ ] Data flows correctly between phases
- [ ] No data loss or corruption
- [ ] Each phase's output is next phase's input

**Test:** Run orchestrator, check that each phase uses correct data

### Idempotency
- [ ] Running orchestrator twice doesn't double-enter
- [ ] Duplicate check prevents duplicate trades
- [ ] Position updates are atomic (all-or-nothing)

**Test:** Run orchestrator twice in a row, check for duplicates

### Logging & Audit Trail
- [ ] Every decision logged
- [ ] Every order logged
- [ ] Every position change logged
- [ ] Can audit any trade decision

**Test:** Pick a trade, verify you can trace entire decision path

---

## Success Criteria

### Daily Pass (✅ All Systems Go)
- [ ] All 8 phases executed
- [ ] 0 unexpected errors
- [ ] Entry decisions correct (quality > quantity)
- [ ] Exit logic working
- [ ] P&L tracking accurate
- [ ] No safety violations

### Week Pass (✅ Ready for AWS)
- [ ] 5+ consecutive days of PASS
- [ ] Multiple market conditions tested
- [ ] At least 1 pyramid add executed correctly
- [ ] At least 1 early exit triggered correctly
- [ ] P&L profitable or small loss (not system error)
- [ ] Zero critical bugs found

### Failure (❌ Issues Found)
- [ ] Stop execution
- [ ] Investigate issue
- [ ] Fix bug in code
- [ ] Re-test that specific scenario
- [ ] Resume testing once fixed

---

## Daily Test Command

```bash
python paper_mode_testing.py
```

**Output:** Daily report with:
- Phase execution status
- Trade decisions made
- Risk metrics
- Any issues detected

**Save:** Reports stored in `paper_mode_reports/` with date

---

## Sign-Off

Once you've run 5-10 days of testing and confirmed:
- ✅ All phases executing correctly
- ✅ Decisions are high-quality (rejecting bad signals)
- ✅ Risk management working properly
- ✅ P&L tracking accurate
- ✅ Zero critical issues

**Then:** System is ready for AWS Lambda deployment

---

## Notes for Testing

1. **Be patient with signal rejections** - System is designed to reject weak signals. This is GOOD, not a bug.

2. **Watch for over-trading** - If system is entering 5+ trades per day in weak market, something is wrong.

3. **Monitor P&L** - Paper trading should be roughly break-even or slightly profitable. Consistent losses may indicate issue.

4. **Check logs** - Every trade should be logged in `algo_audit_log`. No silent failures.

5. **Verify Alpaca sync** - Orders should appear in Alpaca paper account with correct prices/stops/targets.

6. **Test breaker triggers** - Manually check that circuit breakers would trigger at correct thresholds.

---

## Debugging Guide

| Issue | Check | Fix |
|-------|-------|-----|
| Too many entries | Market exposure tier, signal scores | Tighten score thresholds |
| No entries ever | Breaker halting?, signals too strict? | Manually check signals |
| Wrong stop prices | Base type logic, signal data | Verify base type classification |
| P&L doesn't match | Entry/current price stale? | Refresh price data |
| Orders not in Alpaca | Alpaca credentials?, paper mode? | Check `EXECUTION_MODE` env var |
| Positions drift | Sync issue, partial fills | Check reconciliation logic |

