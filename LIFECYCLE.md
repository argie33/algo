# Trade Lifecycle Documentation

Complete documentation of the trade lifecycle from signal generation through exit.
This documents the STATE MACHINE and DATA FLOW for each trade.

---

## Overview: 3-Phase Trade Lifecycle

Every trade progresses through three phases:
1. **ENTRY** — Signal generation through position entry
2. **MONITORING** — Daily P&L tracking and stop recalculation
3. **EXIT** — Exit decision through position closure

Each phase has specific data, preconditions, and post-conditions.

---

## PHASE 1: ENTRY (Signal → Position)

### Timeline
- **T-1 day (evening):** Daily loaders populate tables with latest market data
- **T (morning/early afternoon):** Orchestrator runs signal generation pipeline
- **T (2-5pm ET):** Entry execution against live market (paper trading)

### Data Created

#### buy_sell_daily (Signal Generated)
Signal computation occurs in `algo_signals.py` → `loadbuyselldaily.py`

```
symbol:    'AAPL'
date:      2026-05-10  (eval_date, the date the signal was computed)
signal:    'BUY'       (RSI < 30 + MACD crossover OR other patterns)
rsi:       28.5
macd:      0.15
reason:    'RSI<30 + MACD golden cross'
```

**Precondition:** Technical data loaded (price_daily, technical_data_daily populated)

#### signal_quality_scores (Quality Assessed)
Signal filtering occurs in `algo_filter_pipeline.py`

```
symbol:           'AAPL'
date:             2026-05-10
quality_score:    78.5      (0-100 composite score across 6 tiers)
tier_1_pass:      true      (data quality)
tier_2_pass:      true      (market conditions)
tier_3_pass:      true      (trend template)
tier_4_pass:      true      (signal quality score)
tier_5_pass:      true      (portfolio fit)
tier_6_pass:      true      (advanced filters)
```

#### swing_trader_scores (Swing Scoring)
Swing scoring occurs in `algo_swing_score.py`

```
symbol:              'AAPL'
eval_date:           2026-05-10
swing_score:         82.3        (0-100)
grade:               'A'         (A+, A, B, C, D, F)
setup_pts:           23/25       (base quality, patterns)
trend_pts:           19/20       (Minervini 8-point, Weinstein stage)
momentum_pts:        18/20       (RS, returns)
volume_pts:          11/12       (breakout vol, accumulation)
fundamentals_pts:    8/10        (EPS/revenue growth)
sector_pts:          7/8         (industry/sector rank)
multi_tf_pts:        4/5         (weekly/monthly alignment)
```

#### algo_positions (Entry Created)
Trade execution occurs in `trade_executor.py` → `algo_orchestrator.py` Phase 6

```
symbol:              'AAPL'
entry_date:          2026-05-10
entry_price:         189.35      (market price at execution)
quantity:            50
entry_reason:        'RSI<30 + MACD + swing_score=82'
entry_signal_date:   2026-05-10  (when signal was generated)
stop_price:          180.85      (entry_price * 0.955, from base_type_stop)
target_price:        201.40      (risk/reward: 1:2 on $8.50 risk)
kelly_fraction:      0.08        (8% per CAGR/drawdown calibration)
position_status:     'OPEN'
created_at:          2026-05-10 14:23:45 UTC
```

**Precondition:** Swing score passes hard gates, portfolio has available capital/slots

**Post-Condition:** Position now in MONITORING phase

---

## PHASE 2: MONITORING (Daily P&L Tracking)

### Timeline
- **Every trading day (orchestrator Phase 3):** Monitor existing positions
- **Duration:** From entry_date through exit_date (could be days, weeks)

### Data Updated Daily

#### algo_positions (Updated Daily)
Position monitor in `algo_orchestrator.py` Phase 3 updates positions

```
symbol:              'AAPL'
entry_date:          2026-05-10
current_price:       192.10      (refreshed daily)
days_held:           3
current_pnl_usd:     142.50      (192.10 * 50 - 189.35 * 50)
current_pnl_pct:     1.45%
peak_price:          195.75      (high water mark for trailing stop)
trailing_stop:       186.00      (ratchets up on new peaks, never down)
stop_reason:         null        (reason if stop triggered, otherwise null)
exit_date:           null        (populated when position exits)
exit_price:          null
exit_reason:         null        (e.g., 'stop_loss', 'target_hit', 'minervini_break')
position_status:     'OPEN'      (or 'CLOSING' or 'CLOSED')
last_monitored:      2026-05-13 16:30:00 UTC
```

#### algo_audit_log (Event Log)
Daily monitoring events logged

```
timestamp:           2026-05-13 16:30:00 UTC
symbol:              'AAPL'
event_type:          'position_monitor'
event_detail:        'P&L: +1.45%, peak_price: 195.75, trailing_stop: 186.00'
action_taken:        'hold'   (hold, raise_stop, early_exit, halt_entry)
```

### Key Monitoring Checks

1. **P&L Check** — Daily profit/loss
   - Triggers: Max daily loss (2%), max weekly loss (5%), max total risk
   - Action: Exit full position or partial

2. **Stop Loss Check** — Stop triggered?
   - If `current_price <= trailing_stop`: EXIT immediately
   - Reason: 'stop_loss'

3. **Target Check** — Target price hit?
   - If `current_price >= target_price`: EXIT full position
   - Reason: 'target_hit'

4. **Minervini Break Check** — Trend broken?
   - If `current_price <= sma_20` for 2 consecutive days: EXIT
   - Reason: 'minervini_break'

5. **Time Decay Check** — Held too long?
   - If `days_held > max_holding_days` (30 by default): EXIT
   - Reason: 'time_decay_max'

6. **Earnings Check** — Earnings approaching?
   - If earnings within 5 trading days: Consider early exit
   - Reason: 'earnings_proximity'

7. **Sector/RS Check** — Lost relative strength?
   - If RS percentile drops below 30: Flag for early exit
   - Reason: 'rs_deterioration'

8. **Halt Check** — Circuit breaker tripped?
   - If halt_drawdown fires: CLOSE all positions
   - Reason: 'circuit_breaker'

---

## PHASE 3: EXIT (Exit Decision → Closure)

### Exit Trigger Events

Any of these trigger exit logic:

1. **Stop Loss Triggered** (Hard Stop)
   - `current_price <= trailing_stop`
   - Action: EXIT 100% at market
   - Reason: 'stop_loss'

2. **Target Price Hit** (Profit Target)
   - `current_price >= target_price`
   - Action: EXIT 100% at market
   - Reason: 'target_hit'

3. **Trend Break** (Minervini Rule)
   - 2 consecutive closes below SMA-20
   - Action: EXIT 100%
   - Reason: 'minervini_break'

4. **Time Decay** (Max Hold)
   - `days_held > 30` (configurable)
   - Action: EXIT 100%
   - Reason: 'time_decay_max'

5. **Earnings Event** (Event Risk)
   - Earnings released during hold
   - Action: EXIT 100% or partial
   - Reason: 'earnings_announcement'

6. **Circuit Breaker** (Portfolio Risk)
   - Drawdown > 15% OR daily loss > 2%
   - Action: EXIT all open positions
   - Reason: 'circuit_breaker'

7. **Manual Exit** (User Override)
   - User closes position manually
   - Action: EXIT 100%
   - Reason: 'manual_close'

8. **Pyramid Add** (Partial Close)
   - Profit > 50% target, scale out 25%
   - Action: EXIT 25% at target
   - Reason: 'pyramid_scale_out'

### Data Finalized at Exit

#### algo_positions (Closed)
```
symbol:              'AAPL'
entry_date:          2026-05-10
exit_date:           2026-05-17         (exit_date NOW POPULATED)
entry_price:         189.35
exit_price:          196.80             (market price at exit)
quantity:            50
days_held:           7
pnl_usd:             375.00             ((196.80 - 189.35) * 50)
pnl_pct:             3.92%
risk_taken_pct:      4.48%              ((189.35 - 180.85) / 189.35)
reward_earned_pct:   3.92%
r_multiple:          0.87               (reward_earned_pct / risk_taken_pct)
exit_reason:         'target_hit'       (e.g., target_hit, stop_loss, etc.)
position_status:     'CLOSED'
```

#### algo_audit_log (Exit Event)
```
timestamp:           2026-05-17 09:45:00 UTC
symbol:              'AAPL'
event_type:          'position_exit'
event_detail:        'Exited at 196.80 (target hit), P&L: +3.92%'
action_taken:        'exit'
```

#### algo_daily_reconciliation (P&L Recorded)
Post-trade analysis occurs in `algo_daily_reconciliation.py`

```
symbol:              'AAPL'
trade_date:          2026-05-10        (entry date)
exit_date:           2026-05-17
entry_price:         189.35
exit_price:          196.80
pnl_usd:             375.00
pnl_pct:             3.92%
mae_pct:             -2.15%            (max adverse excursion during hold)
mfe_pct:             +3.95%            (max favorable excursion during hold)
holding_days:        7
win_loss_category:   'win'             (win if pnl_pct > 0, else loss)
```

---

## CONCURRENT SCENARIOS: Entry ↔ Exit Race Condition

### Scenario: Exit During Entry

**Timeline:**
- 2:15pm: Entry signal fires, trade_executor starts placing order
- 2:16pm: Circuit breaker triggers (market down 3%)
- 2:17pm: Entry order fills, position created
- 2:18pm: Circuit breaker exit logic runs, sees new position, exits immediately

**Resolution:**
- Entry creates position with `position_status = 'OPEN'`
- Exit checks for positions with `position_status = 'OPEN'`
- Exit executes immediately after entry
- Final state: `position_status = 'CLOSED'`, very short P&L

**Key:** Use transaction isolation (SERIALIZABLE) to guarantee consistent state

---

## State Machine Diagram

```
   ┌─────────────────────────────────────────────┐
   │            ENTRY PHASE                      │
   │                                             │
   │  buy_sell_daily: BUY signal generated       │
   │         ↓                                   │
   │  signal_quality_scores: Tier 1-5 pass      │
   │         ↓                                   │
   │  swing_trader_scores: Grade A/B/C          │
   │         ↓                                   │
   │  trade_executor: Place order at market     │
   │         ↓                                   │
   │  algo_positions: CREATED (status='OPEN')   │
   └─────────────────────────────────────────────┘
                        ↓
   ┌─────────────────────────────────────────────┐
   │         MONITORING PHASE                    │
   │    (Daily, duration: 1-30+ days)            │
   │                                             │
   │  Daily checks:                              │
   │    • P&L within limits?                     │
   │    • Stop loss triggered?                   │
   │    • Target hit?                            │
   │    • Minervini break?                       │
   │    • Time decay?                            │
   │    • Earnings? / Circuit breaker?           │
   │                                             │
   │  Actions:                                   │
   │    • HOLD: conditions OK                    │
   │    • RAISE_STOP: new peak detected          │
   │    • EARLY_EXIT: risk detected              │
   │    → algo_positions: Updated daily          │
   └─────────────────────────────────────────────┘
                        ↓
   ┌─────────────────────────────────────────────┐
   │          EXIT PHASE                         │
   │                                             │
   │  Exit trigger fires:                        │
   │    • stop_loss / target_hit / time_decay    │
   │    • minervini_break / earnings / halt      │
   │         ↓                                   │
   │  trade_executor: Place exit order           │
   │         ↓                                   │
   │  algo_positions: Updated to CLOSED          │
   │    • exit_date, exit_price, exit_reason    │
   │    • final pnl_usd, pnl_pct, r_multiple    │
   │         ↓                                   │
   │  algo_daily_reconciliation:                 │
   │    • Compute MAE, MFE                       │
   │    • Record win/loss for analysis           │
   └─────────────────────────────────────────────┘
```

---

## Key Implementation Points

### Entry Phase
- **File:** `algo_orchestrator.py` Phase 5 (signal generation), Phase 6 (entry execution)
- **Key Classes:** `FilterPipeline`, `TradeExecutor`, `SwingTraderScore`
- **Invariant:** A position can only be created once per symbol per date
- **Safety:** Check for duplicates before entry (in `trade_executor.execute_trade()`)

### Monitoring Phase
- **File:** `algo_orchestrator.py` Phase 3 (position monitor)
- **Key Classes:** `PositionMonitor`, `AlgoExitEngine`
- **Invariant:** `trailing_stop` never decreases
- **Safety:** Use `row_level_lock` or `optimistic_locking` on position updates

### Exit Phase
- **File:** `algo_exit_engine.py` (exit decision), `trade_executor.py` (exit execution)
- **Key Classes:** `ExitEngine`, `TradeExecutor`, `DailyReconciliation`
- **Invariant:** Position can only close once (idempotent)
- **Safety:** Use `position_status = 'CLOSING'` to prevent double-closes

---

## Column Name Standards

To prevent silent bugs from schema mismatches:
- Entry date: `entry_date` (not `date`, not `entry_timestamp`)
- Exit date: `exit_date` (not `close_date`)
- Trade date: `trade_date` (in algo_trades)
- Signal date: `signal_date` (in buy_sell_daily)
- Record date: `created_at` or `last_updated` (audit trail)

See `schema_mapping.json` for complete schema documentation.

---

## Testing Checklist

- [ ] Entry phase: Signal generated → Position created
- [ ] Monitoring phase: Daily checks update position
- [ ] Exit phase: Stop/target/break trigger → Position closed
- [ ] Concurrent: Entry during exit → Position closes immediately after
- [ ] Idempotency: Re-run exit logic → No double-closes
- [ ] Data consistency: All dependent tables updated together
- [ ] P&L accuracy: Entry price, exit price, MAE/MFE computed correctly
- [ ] Time handling: Days held, holding window, expiration calculated right

---

## References

- `algo_orchestrator.py`: Orchestrates all phases
- `algo_exit_engine.py`: Exit decision logic
- `trade_executor.py`: Places orders (entry/exit)
- `algo_daily_reconciliation.py`: Post-trade analysis
- `schema_mapping.json`: Complete schema documentation
- `TRANSACTION_SAFETY.md`: Concurrency and locking patterns
