# Order Reconciliation System - Complete Guide

**Status:** Ready to deploy  
**Components:** 3 modules + 1 integration  
**Time to deploy:** 30 minutes

---

## 🎯 Problem Solved

### Before: Order Blindness
```
14:30 → Algo places order for AAPL
14:30 → Order marked PENDING in database
        (Alpaca gets the order)
14:31 → Alpaca fills the order
        (We don't know yet)
17:00 → End-of-day reconciliation
        (Finally discover it was filled 2.5 hours ago)
```

**Risks:**
- If order is orphaned (network failure), we never know
- If order partially fills, we don't update position size
- If order gets stuck, we don't cancel it
- Slippage is invisible until day-end

### After: Real-Time Order Sync
```
14:30 → Algo places order for AAPL
14:30 → Order marked PENDING, logged with Alpaca order ID
        (structured log with trace_id)

14:31 → Alpaca fills the order
        (our monitoring will catch this)

14:33 → Reconciliation runs (every 5 min)
        • Compares local order vs Alpaca reality
        • Finds discrepancy: local pending, Alpaca filled
        • Logs alert: "AAPL filled, updating locally"
        • Updates database: mark as FILLED, record fill price
        • Records slippage: expected $150.25, filled $150.18 = +$0.07 slippage

14:35 → Dashboard query shows:
        • Order filled 2 min after placement
        • Filled price and slippage
        • P&L impact
```

---

## 📦 Three New Systems

### 1. Order Reconciler (`order_reconciler.py`)

**What it does:**
- Compares local algo_trades table vs Alpaca API
- Detects 5 types of discrepancies
- Recovers from stuck/orphaned orders

**Discrepancy Types:**
| Type | Local | Alpaca | Action |
|------|-------|--------|--------|
| ORPHANED | pending | not found | Alert: maybe network loss? |
| FILLED_UNKNOWN | pending | filled | Update DB: mark as filled |
| PARTIAL_FILL | pending | 50% filled | Alert: partial fill |
| STUCK | pending | pending (>30min) | Alert + allow manual cancel |
| CONFLICTING | state X | state Y | Alert: investigate |

**Usage:**
```bash
# Check all pending orders
python3 order_reconciler.py --check

# Manual recovery: cancel stuck order
python3 order_reconciler.py --cancel-order AAPL "abc123def456"

# Manual recovery: force-sell position
python3 order_reconciler.py --force-sell AAPL 100
```

**API:**
```python
from order_reconciler import get_reconciler

reconciler = get_reconciler()

# Periodic check (run every 5 min)
count, discrepancies = reconciler.reconcile_all()
if discrepancies:
    for disc in discrepancies:
        logger.warning(f"Discrepancy: {disc['type']} - {disc['message']}")

# Manual recovery
reconciler.cancel_order("AAPL", alpaca_order_id)
reconciler.force_sell("MSFT", 100)
```

---

### 2. Slippage Tracker (`slippage_tracker.py`)

**What it does:**
- Measures execution quality (expected vs actual fill price)
- Tracks per-symbol and per-trade slippage
- Alerts if slippage is bad

**Formula:**
```
For BUY orders:
  Slippage = Actual Price - Expected Price
  Negative is GOOD (filled cheaper)

For SELL orders:
  Slippage = Expected Price - Actual Price
  Positive is GOOD (filled higher)

Slippage % = Slippage / Expected Price * 100%
```

**Example:**
```
BUY 100 AAPL @ signal price $150.25
Actual fill: $150.18
Slippage: -$0.07 (negative = good, we got a better price)
Slippage %: -0.047%

SELL 100 MSFT @ target $425.00
Actual fill: $425.10
Slippage: +$0.10 (positive = good, we got a better price)
Slippage %: +0.024%
```

**Usage:**
```bash
# View slippage report for today
python3 slippage_tracker.py

# View for specific date
python3 slippage_tracker.py --date 2026-05-09

# Create table (one-time)
python3 slippage_tracker.py --create-table
```

**API:**
```python
from slippage_tracker import get_slippage_tracker

tracker = get_slippage_tracker()

# Record when order fills
tracker.record_slippage(
    symbol="AAPL",
    side="BUY",
    expected_price=150.25,
    actual_price=150.18,
    quantity=100,
    order_id=alpaca_order_id,
)

# Get daily stats
stats = tracker.get_daily_slippage(date.today())
# {
#   'overall': {
#     'trade_count': 5,
#     'avg_slippage': 0.05,
#     'avg_slippage_pct': 0.03,
#   },
#   'per_symbol': {
#     'AAPL': {'count': 2, 'avg_slippage': -0.07},
#     'MSFT': {'count': 3, 'avg_slippage': 0.08},
#   }
# }
```

---

### 3. Database Tables

**Create once:**
```bash
# For loader SLA tracking (if not already done)
psql -h localhost -U stocks -d stocks < create_loader_sla_table.sql

# For slippage tracking
python3 slippage_tracker.py --create-table
```

**Tables created:**
1. `order_slippage` — Track slippage per trade
2. Views for reporting

---

## 🔌 Integration: Wiring into Orchestrator

### Phase 6: Entry Execution

**After placing order:**
```python
# Phase 6: Entry Execution
def phase_6_entry_execution(self):
    for candidate in ranked_candidates:
        try:
            # Execute the trade
            alpaca_order = self.executor.execute_trade(candidate)
            
            # Log with full details
            logger.info("Order placed", extra={
                "symbol": candidate['symbol'],
                "side": "BUY",
                "quantity": candidate['shares'],
                "alpaca_order_id": alpaca_order.id,
                "signal_price": candidate['entry_price'],
            })
            
            # Record in DB with order ID
            self._record_trade(
                symbol=candidate['symbol'],
                alpaca_order_id=alpaca_order.id,
                status='PENDING',
            )
        except Exception as e:
            logger.error("Failed to place order", extra={
                "symbol": candidate['symbol'],
                "error": str(e),
            })
```

### Phase 3 or 4: Continuous Reconciliation

**Run periodically (every 5-10 minutes during market hours):**
```python
# New: Continuous order reconciliation
def reconcile_orders(self):
    """Check for order discrepancies every 5 min."""
    from order_reconciler import get_reconciler
    
    reconciler = get_reconciler()
    count, discrepancies = reconciler.reconcile_all()
    
    if count > 0:
        logger.warning(f"Found {count} order discrepancies")
        
        for disc in discrepancies:
            if disc['type'] == 'FILLED_UNKNOWN':
                # Order filled, update local DB
                reconciler.update_from_alpaca(disc)
                logger.info("Updated order from Alpaca", extra={
                    "symbol": disc['symbol'],
                    "type": disc['type'],
                })
            
            elif disc['type'] == 'STUCK':
                # Order stuck >30min, alert + ask for manual intervention
                from alert_router import alert_critical
                alert_critical(
                    "Stuck Order",
                    f"{disc['symbol']} order stuck for >30 min",
                    runbook="https://docs.example.com/stuck-order-recovery",
                )
            
            elif disc['type'] == 'ORPHANED':
                # Order not found in Alpaca, alert
                from alert_router import alert_error
                alert_error(
                    "Orphaned Order",
                    f"{disc['symbol']} not found in Alpaca",
                )
```

### Phase 7: Reconciliation & Record Fills

**When order fills, record slippage:**
```python
def phase_7_reconciliation(self):
    """Sync with Alpaca, record slippage."""
    from slippage_tracker import get_slippage_tracker
    
    tracker = get_slippage_tracker()
    
    # Get all filled orders from Alpaca
    filled_orders = self.alpaca.list_orders(status='closed')
    
    for alpaca_order in filled_orders:
        # Find in our local DB
        local_order = self._find_local_order(alpaca_order.id)
        if not local_order:
            continue
        
        # Record slippage
        tracker.record_slippage(
            symbol=alpaca_order.symbol,
            side=alpaca_order.side.upper(),
            expected_price=local_order['entry_price'],  # What we expected
            actual_price=float(alpaca_order.filled_avg_price),  # What we got
            quantity=int(alpaca_order.filled_qty),
            order_id=alpaca_order.id,
        )
        
        logger.info("Order reconciled", extra={
            "symbol": alpaca_order.symbol,
            "side": alpaca_order.side,
            "filled_price": alpaca_order.filled_avg_price,
            "slippage": float(alpaca_order.filled_avg_price) - local_order['entry_price'],
        })
```

---

## 🚀 Deployment Checklist

### One-Time Setup (5 min)
- [ ] Create `order_slippage` table: `python3 slippage_tracker.py --create-table`
- [ ] Verify Alpaca credentials are set: `echo $APCA_API_KEY_ID`

### Code Changes (15 min)
- [ ] Import in algo_orchestrator.py:
  ```python
  from order_reconciler import get_reconciler
  from slippage_tracker import get_slippage_tracker
  ```
- [ ] Add reconciliation check in Phase 3/4 (runs every cycle)
- [ ] Add slippage recording in Phase 7 (after fills)
- [ ] Update Phase 6 to log full order details

### Testing (10 min)
```bash
# Local test: place an order, reconcile
python3 algo_run_daily.py

# Check logs for order placement
grep "Order placed" algo-run-$(date +%Y%m%d).log

# Check reconciliation
python3 order_reconciler.py --check

# View slippage
python3 slippage_tracker.py
```

### Deploy to AWS (5 min)
```bash
git add -A
git commit -m "feat: Order reconciliation + slippage tracking"
gh workflow run deploy-algo-orchestrator.yml
```

---

## 🎯 Example Scenarios

### Scenario 1: Filled Order Discovered

**Timeline:**
```
14:30:45 → Order placed for AAPL: "Order placed" (trace_id=RUN-2026-05-09-143045-abc)
           └ logs: alpaca_order_id=xyz789, symbol=AAPL, quantity=100

14:30:50 → Alpaca fills order
           (we don't know yet)

14:35:00 → Reconciliation runs
           └ Calls order_reconciler.reconcile_all()
           └ Finds: local says PENDING, Alpaca says FILLED
           └ Type: FILLED_UNKNOWN
           └ Updates DB, records in audit log

14:35:05 → Logs: "Updated order from Alpaca" 
           └ phase=reconciliation, symbol=AAPL, type=FILLED_UNKNOWN

14:35:10 → Slippage recorded:
           └ Expected: $150.25 (signal price)
           └ Actual: $150.18 (filled avg price)
           └ Slippage: -$0.07 (GOOD - got cheaper)

Dashboard query:
  python3 audit_dashboard.py --symbol AAPL --date 2026-05-09
  
Output:
  AAPL BUY 100 @ $150.18
    Expected: $150.25
    Slippage: -$0.07 (-0.047%)
    Status: FILLED
    Time: 5 seconds
```

### Scenario 2: Stuck Order Recovery

**Timeline:**
```
14:30:45 → Order placed for MSFT
14:35:00 → Reconciliation: order still pending (5 min old) - OK
14:40:00 → Reconciliation: order still pending (10 min old) - OK
14:45:00 → Reconciliation: order still pending (15 min old) - OK
...
15:02:00 → Reconciliation: order still pending (32 min old) - STUCK!
           └ Type: STUCK
           └ Alert sent: CRITICAL "Stuck Order"
           └ Alert includes runbook link

Operator action:
  python3 order_reconciler.py --cancel-order MSFT xyz789
  
Result:
  └ Cancelled in Alpaca
  └ Marked as CANCELLED in DB
  └ Logged: "order_cancelled" (reason=manual_recovery)
  └ Position updated
```

### Scenario 3: Slippage Dashboard

```bash
$ python3 slippage_tracker.py --date 2026-05-09

================================================================================
SLIPPAGE REPORT - 2026-05-09
================================================================================

Overall Statistics:
  Trades: 5
  Avg Slippage: $0.035
  Avg Slippage %: 0.023%
  Best Trade: -$0.12 (AAPL BUY - got $0.12 cheaper)
  Worst Trade: $0.18 (TSLA SELL - market moved against us)
  Total Impact: $175.25

Per-Symbol Breakdown:
  AAPL: 2 trades, avg -$0.07 (-0.047%)
  MSFT: 2 trades, avg $0.06 (+0.014%)
  TSLA: 1 trades, avg $0.18 (+0.042%)

Worst Fills:
  TSLA SELL: Expected $4290.00, Filled $4289.82, Slippage -$0.18 (0.042%)
  MSFT BUY: Expected $425.00, Filled $425.08, Slippage -$0.08 (0.019%)
  AAPL BUY: Expected $150.25, Filled $150.18, Slippage -$0.07 (0.047%)
```

---

## 📊 Queries You Can Now Answer

1. **"Is my AAPL order filled yet?"**
   ```bash
   python3 audit_dashboard.py --symbol AAPL --date 2026-05-09
   ```

2. **"Why wasn't MSFT traded today?"**
   ```
   Query audit logs:
   - Was signal generated? (check buy_sell_daily)
   - Did it pass filters? (check filter scores)
   - Did it get ranked? (check phase 5 logs)
   - Why not entered? (check phase 6 logs)
   All with trace_id for that day
   ```

3. **"What's my average slippage?"**
   ```bash
   python3 slippage_tracker.py --date 2026-05-09
   ```

4. **"Are any orders stuck?"**
   ```bash
   python3 order_reconciler.py --check
   ```

---

## ✅ You Now Have

✓ Real-time order synchronization  
✓ Automatic detection of fills, partials, orphans  
✓ Manual recovery tools (cancel, force-sell)  
✓ Execution quality tracking (slippage)  
✓ Full audit trail (why wasn't it traded?)  

---

**Ready?** Start with integration checklist above. Takes 30 minutes to fully deploy.
