# Data Model Architecture

## Single Source of Truth: algo_trades

The system tracks trading activity through a single source of truth: **algo_trades table**. All other data is derived from this table.

**Principle:** Single source of truth: `algo_trades`. All other data derived from it. Maintains consistency, eliminates drift.

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

**Current state: Read-only cache for backward compatibility.**

Do NOT write to `algo_positions` directly. It is updated only when `algo_trades` records change. All new queries should derive positions from `algo_trades` directly.

### algo_portfolio_snapshots

**Daily portfolio summaries.** Derived from:
- Current open positions (from `algo_trades`)
- Closed trades of the day (from `algo_trades`)
- Cash balance (from reconciliation with Alpaca)

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

**Entry:** INSERT algo_trades (status='pending') → Send order to Alpaca → UPDATE status='filled' + alpaca_order_id. Atomic per trade.

**Exit:** UPDATE algo_trades (status='closed', exit_date, exit_price, profit_loss). Atomic per trade.

**Invariants:** `status='closed'` + `exit_date IS NOT NULL` = fully exited. `status IN ('open', 'filled')` = still held. Violations indicate drift—run consistency checker.

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
