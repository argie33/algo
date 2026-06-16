# Data Model Architecture

## Single Source of Truth: algo_trades

The system tracks trading activity through a single source of truth: **algo_trades table**. All other data is derived from this table.

### Core Principle

```
algo_trades (atomic, source of truth)
  ↓
algo_positions (computed view, derived)
  ↓
Dashboard + Reports (read-only consumers)
```

**Why?** Maintaining separate `algo_trades` and `algo_positions` tables causes drift. When a trade executes, it updates `algo_trades` atomically. The position table must always reflect the current state of the trade, so positions are now computed from trades, not stored separately.

---

## Tables

### algo_trades

**Authoritative table for all trading activity.**

| Column | Purpose |
|--------|---------|
| trade_id | Unique identifier |
| symbol | Stock symbol |
| status | `pending` → `open` → `filled` → `closed` or `cancelled` |
| entry_date, entry_price, entry_quantity | When/where we entered |
| exit_date, exit_price | When/where we exited (NULL if still open) |
| profit_loss_dollars, profit_loss_pct | Result (only when closed) |
| stop_loss_price, target_1/2/3_price | Risk/reward levels |
| signal_date, swing_score, base_type | Entry signal metadata |
| exit_reason | Why we exited (e.g., "target_1", "stop", "time") |
| mfe_pct, mae_pct | Max favorable/adverse excursion |

**Key facts:**
- Status transitions: `pending` → `open` → (`filled` or `partially_filled`) → `closed`
- A trade with `status='closed'` and `exit_date NOT NULL` is a completed, closed trade
- A trade with `status IN ('open', 'filled', 'partially_filled')` represents an active position
- All updates are atomic: entry + position record OR exit + position close all in one transaction

### algo_positions

**Current state: Still exists for backward compatibility. Gradually being replaced by computed views.**

Do NOT write to `algo_positions` directly. It should be updated only when `algo_trades` records change.

**Planned deprecation:**
1. Phase 1 (now): Derive positions from trades in queries
2. Phase 2: Materialized view `algo_positions_computed` is source of truth
3. Phase 3: `algo_positions` table is read-only cache, refreshed after trades execute
4. Phase 4: Remove `algo_positions` table entirely

### algo_portfolio_snapshots

**Daily portfolio summaries.** Derived from:
- Current open positions (from `algo_trades`)
- Closed trades of the day (from `algo_trades`)
- Cash balance (from reconciliation with Alpaca)

---

## Dashboard Data Flow

### Query Pattern: ALWAYS query algo_trades directly

**Wrong:** Separate queries from algo_positions and algo_trades → data drift.  
**Right:** All queries derive from algo_trades only. Status transitions (`open` → `closed`) and position counts come from the same authoritative source.

```sql
-- Correct: Positions from algo_trades
SELECT symbol FROM algo_trades WHERE status IN ('open', 'filled', 'partially_filled');
-- Correct: Performance from algo_trades  
SELECT symbol FROM algo_trades WHERE status='closed' AND exit_date IS NOT NULL;
```

---

## Data Consistency Checks

Run the consistency checker to detect drift:

```bash
python -m utils.position_sync_checker
```

This verifies:
- No orphaned positions (in `algo_positions` but not `algo_trades`)
- No stale positions (marked open but trade is closed)
- No missing positions (trade is open but no position record)
- Quantity matches between `algo_positions` and `algo_trades`

---

## Trade Lifecycle

### Entry (Phase 3: Positions)

```python
# TradeExecutor.execute_trade()
1. INSERT INTO algo_trades (status='pending', entry_price, entry_quantity, ...)
   Get trade_id

2. Send order to Alpaca
   Get alpaca_order_id

3. Wait for fill, then UPDATE algo_trades:
   SET status='filled', alpaca_order_id=..., entry_time=...

4. INSERT INTO algo_positions (status='open', trade_ids_arr=[trade_id], ...)
   OR UPDATE algo_positions SET trade_ids_arr = array_append(...)
```

**Atomic:** All in one transaction per trade.

### Exit (Phase 4: Exits)

```python
# TradeExecutor.exit_trade()
1. UPDATE algo_trades
   SET status='closed', exit_date, exit_price, exit_reason, profit_loss_dollars, ...

2. UPDATE algo_positions
   SET status='closed', quantity=0, closed_at=CURRENT_TIMESTAMP
   WHERE position_id matches the exited trade
```

**Atomic:** One transaction per exit.

### Key Invariants

- **Invariant 1:** If `algo_trades.status='closed'` and `exit_date IS NOT NULL`, position is fully exited.
- **Invariant 2:** If `algo_trades.status IN ('open', 'filled')`, position is still held.
- **Invariant 3:** `algo_positions.status` should mirror the algo_trades status of the underlying trade(s).

If these invariants are violated → **position sync has drifted** → run the checker and fix.

---

## Performance Metrics Query Patterns

**Historical performance (closed trades only):**

```sql
SELECT COUNT(*) FILTER (WHERE profit_loss_dollars > 0) as wins,
       COUNT(*) as total,
       SUM(profit_loss_dollars) as realized_pnl,
       AVG(CASE WHEN profit_loss_dollars > 0 THEN ABS(profit_loss_dollars) END) as avg_win
FROM algo_trades
WHERE status='closed' AND exit_date IS NOT NULL
```

**Current positions (open trades):**

```sql
SELECT symbol, SUM(entry_quantity) as total_qty, AVG(entry_price) as avg_entry,
       SUM((current_price - entry_price) * entry_quantity) as unrealized_pnl
FROM algo_trades
WHERE status IN ('open', 'filled', 'partially_filled')
GROUP BY symbol
```

---

## Troubleshooting

**Q: Dashboard shows 9 positions but 3 closed trades. Is that wrong?**

A: No, that's correct. It means you've entered 12 trades total, 9 are still open, 3 are closed. You can verify with:

```sql
SELECT COUNT(*) FROM algo_trades WHERE status IN ('open', 'filled', 'partially_filled');  -- Should be 9
SELECT COUNT(*) FROM algo_trades WHERE status='closed' AND exit_date IS NOT NULL;         -- Should be 3
```

**Q: Why do the numbers not match?**

A: Run the consistency checker:

```bash
python -m utils.position_sync_checker
```

This will identify orphaned or missing position records.

**Q: Can I manually edit algo_positions?**

A: No. Only update it through TradeExecutor. Manual edits will cause drift. If you must fix data, update algo_trades (the source), then refresh the positions view.

---

## References

- **TradeExecutor:** `algo/algo_trade_executor.py` — Entry/exit logic
- **DailyReconciliation:** `algo/algo_daily_reconciliation.py` — Daily sync
- **Consistency Checker:** `utils/position_sync_checker.py` — Drift detection
- **Dashboard:** `tools/dashboard/dashboard.py` — Display layer
