# Phase Execution - Diagnostic Enhancement Proposal

## Current Gap Analysis

We're showing basic metrics, but missing **critical failure diagnostics**. This makes it hard to debug issues.

## What We Should Add

### For ALL Phases
- **Status indicator** (OK/WARNING/ERROR) - NOT just success/halted
- **Error message** (if failed) - WHY it failed
- **Failure reason** - What specific condition triggered it
- **Retry info** - How many retries, why it failed

### Phase 1: Data Freshness Check
**Currently showing:**
- Tables validated, fresh, stale count
- Stale table list (first 3)

**Should ADD:**
- Validation status (OK/WARN/FAIL)
- Which CRITICAL tables are missing/stale (highlight these!)
- Error message if validation failed
- Loader status (RUNNING/COMPLETED/FAILED/TIMEOUT)
- Specific failure reason (e.g., "price_daily timeout after 30m")
- Affected symbol count (how many missing)

### Phase 2: Circuit Breakers
**Currently showing:**
- Status, drawdown, daily loss, VIX, VaR

**Should ADD:**
- Which threshold was breached (DD or DL)
- How far past threshold (e.g., "DD: 20.5% (threshold 20%)")
- Margin to threshold (e.g., "DD: 18% (2% safe margin)")
- Trigger time (when did it breach)
- Is this a temporary spike or sustained breach

### Phase 3: Position Monitor
**Currently showing:**
- Open positions, age, max loss, P&L

**Should ADD:**
- Problem positions (losing money, too old)
- High-risk positions (flagged why)
- Average loss percentage
- Position with highest loss (symbol + %)
- Oldest position (symbol + days)
- Whether any positions exceed max loss threshold

### Phase 4: Broker Reconciliation
**Currently showing:**
- Syncs, match rate, errors

**Should ADD:**
- Which positions mismatched (symbol, expected vs actual)
- Error details (what's mismatched?)
- Sync failure reason (if any)
- Positions pending broker fill (these are normal, not errors!)
- Mismatch breakdown (qty off? price off? missing entirely?)

### Phase 5: Exposure Policy
**Currently showing:**
- Regime, entry status, slots, halt status

**Should ADD:**
- Halt status COLOR (RED if halted)
- Halt reason detail (specific condition)
- Time until halt expires (if timed)
- Regime explanation (why uptrend vs sideways vs downtrend)
- If entry is blocked - WHY (market, signal stale, pending orders)
- Current sector concentration vs max

### Phase 6: Exit Execution
**Currently showing:**
- Exits, success rate, profit, symbols

**Should ADD:**
- Failed exits count (WHY did they fail?)
- Partial fills (what's pending?)
- Unfilled orders (are they stale?)
- Lost money on exits (symbol + loss)
- Average exit slippage (entry vs actual exit)
- Exit failure reason (market moved, order rejected, etc)

### Phase 7: Signal Generation
**Currently showing:**
- Signal count, buy/sell split, strength, symbols

**Should ADD:**
- Signal quality (% STRONG vs WEAK)
- Screened vs generated (how many got filtered?)
- Failed/weak signals (which ones, why weak)
- If signal generation failed - reason
- Data quality issues affecting signals
- Signal conflict (buy vs sell on same symbol?)

### Phase 8: Entry Execution
**Currently showing:**
- Entries, success rate, price, symbols

**Should ADD:**
- Failed entries count (WHY?)
- Partial fills (what's pending?)
- Order rejections (symbol, reason)
- High-cost entries (slippage)
- Underweight positions (ordered 100 but got 50)
- Entry failure reasons (market moved, blocked by policy, etc)

### Phase 9: Portfolio Snapshot
**Currently showing:**
- Portfolio value, cash, returns, snapshot time

**Should ADD:**
- Previous portfolio value (delta)
- Buying power vs cash (margin status)
- Margin usage %
- P&L breakdown (realized + unrealized)
- Daily P&L (today vs overall)
- Gross vs net exposure
- Whether snapshot succeeded or failed (stale?)

---

## Implementation Priority

### MUST HAVE (Critical for debugging)
1. **Error messages** for failed phases
2. **Failure reasons** (specific condition, not just "failed")
3. **Status indicator** (OK/WARN/ERROR) - not just yes/no
4. **Which items failed** (position, order, table, etc)
5. **Threshold comparisons** (actual vs limit)

### SHOULD HAVE (Very helpful)
1. **Problem highlights** (which data is problematic)
2. **Mismatch details** (expected vs actual)
3. **Timing info** (when failures occurred)
4. **Retry info** (how many attempts)
5. **Breakdown percentages** (% success, % failed)

### NICE TO HAVE (Context)
1. **Trend info** (is it improving/degrading)
2. **Margin to threshold** (how safe are we)
3. **Previous values** (delta from last run)
4. **Breakdown by category** (by symbol, by sector, etc)

---

## Design for Panel

Keep the 2-column layout, but ADD:
- **Error sections** that expand only when there's a failure
- **Status badges** with color coding (OK=green, WARN=yellow, ERROR=red)
- **Failure details** indented under failed phases
- **Key problems highlighted** at top of each phase

Example:

```
Phase 2: Circuit Breakers  [RED: TRIGGERED]
  Status: TRIGGERED
  Breached: Drawdown (20.5% > 20% limit)
  Margin: 0.5% OVER threshold
  Trigger Time: 14:25:30
  Action: Halted trading
  
  vs currently:
  
Phase 2: Circuit Breakers  
  Status: TRIGGERED
  Drawdown: 20.5%
  Daily Loss: 0.5%
  VIX: 18.5
  VaR 95%: 2.10%
```

---

## Data Sources Available

From phase_results (execution log):
- phase (phase number)
- status (success/halted/warn/error/etc)
- name (phase name)
- summary (one-liner)
- error (error message if failed)

From execution_health:
- All current metrics
- But NOT error details (need to fetch from phase_results)

From database tables:
- More detailed metrics
- Historical data
- Threshold configs

---

## Recommendation

1. **Quick win**: Add error/reason/summary from phase_results
2. **Medium**: Add status badges and highlight failures
3. **Extended**: Add threshold comparisons and "problem" sections
4. **Future**: Add historical trend and delta info

Start with error messages since those are the biggest gap!
