# Data Patrol & Monitoring System

Complete documentation of what's monitored, when alerts fire, and what to do.

---

## System Overview

Three layers of continuous monitoring:

1. **Data Patrol** (16 checks) — Validates all loaded data is correct and usable
2. **Position Monitor** — Reviews every open position, proposes adjustments
3. **Position Reconciliation** — Ensures DB positions match actual Alpaca holdings

All issues trigger **alerts to email + SMS + Slack** based on severity.

---

## Data Patrol Checks (P1-P16)

Runs before orchestrator phases 1-7. Fails **closed on CRITICAL**, blocks trading on **ERROR** (>2).

### Critical Path (Always Run)

| Check | What | Severity | Action |
|-------|------|----------|--------|
| **P1** | Data staleness (price/signals >7d old) | CRIT if >7d | HALT trading |
| **P3** | Zero/identical OHLC (API limit hit) | ERROR if >30 symbols | Log only, continue |
| **P3b** | >30% 1-day drop (splits/halts/delisting) | WARN | Log only |
| **P7** | Universe coverage <90% | ERROR | HALT trading |
| **P9** | DB constraint violations (NULL keys) | ERROR | HALT trading |

### Data Quality (Full Run)

| Check | What | Threshold | Alert On |
|-------|------|-----------|----------|
| **P2** | NULL value spike in OHLC | >5% on latest date | ERROR |
| **P4** | Price sanity (>50% 1-day moves) | >10 symbols | WARN |
| **P5** | Volume <1M (new pattern) or >100M | >50 new low-vol | WARN |
| **P5b** | OHLC broken (High < Low) | Any negative | CRIT |
| **P6** | Top symbols vs Alpaca/Yahoo | >5% mismatch | WARN |
| **P6b** | Signals missing price/tech data | Any orphaned | ERROR |
| **P8** | Price sequence gaps (SPY) | >3 day gaps | WARN |
| **P10** | Scores older than price | Lag >1 day | WARN |
| **P11** | Loader contracts (min rows) | Below threshold | ERROR |
| **P12** | Earnings data freshness | >14d old | WARN |
| **P13** | ETF data freshness/coverage | >3d old | ERROR |
| **P14** | Symbol alignment (price vs tech/signals) | <95% | WARN/ERROR |
| **P15** | Fundamentals data age | >45d old | WARN |
| **P16** | Trade→price alignment (orphaned trades) | Any missing | ERROR |

---

## Alert Types & Response

### CRITICAL — **DROP EVERYTHING**

Sent to: **Email + SMS + Slack** (all channels)

**Examples:**
- OHLC corruption (negative prices, High < Low)
- Data stale >7 days
- >30% symbols with universe drop-off
- Untracked Alpaca position (reconciliation)

**What to do:**
1. **Stop the algorithm immediately** (kill orchestrator)
2. Read the alert message for the specific issue
3. Check patrol results in DB: `SELECT * FROM data_patrol_log WHERE severity = 'critical' ORDER BY created_at DESC LIMIT 5`
4. Fix the root cause:
   - If stale data → re-run loader
   - If price corruption → check data source API
   - If reconciliation → manually compare Alpaca vs DB
5. Run `python3 test_patrol_system.py` to verify
6. Restart orchestrator

---

### ERROR — **Investigate Promptly**

Sent to: **Email + Slack** (no SMS to avoid spam)

**Examples:**
- Data 5 days old
- 500K rows missing from price_daily load
- Signals missing matching price data
- 10+ stale orders pending >1 hour
- 2+ position divergences (qty mismatch)

**What to do:**
1. Check what type of ERROR (see patrol log)
2. Decide: can we trade with this issue? Probably not.
3. If yes → acknowledge in Slack, monitor closely
4. If no → run diagnosis:
   ```bash
   # See detailed findings
   psql stocks -c "SELECT check_name, target_table, message, details 
                    FROM data_patrol_log 
                    WHERE severity='error' 
                    ORDER BY created_at DESC LIMIT 10"
   ```
5. Fix root cause and re-run patrol
6. When clear → continue or restart

---

### WARN — **Log & Monitor**

Sent to: **Email + Slack only** (no SMS)

**Examples:**
- 5 symbols with unusual volume patterns (new low-vol)
- 3 symbols with extreme 1-day moves (real events or pump)
- Sector ranking 10 days old (still acceptable)
- RSI giving back 30% of gains (normal volatility)
- 1-2 pending orders in market

**What to do:**
1. Read the message
2. If pattern is new → understand why (check recent market news)
3. Otherwise → note it, continue running
4. Alerts disappear after ~1 week if not recurring

---

### INFO — **No Alert Sent**

These don't trigger notifications, just logged for audit:
- All checks passing
- Data freshness within window
- Positions healthy
- No constraint violations

---

## Position Monitor (3a)

Runs after circuit breakers. Reviews every open position for:

1. **Current price & P&L** — refreshed from latest price_daily
2. **Trailing stop** — recomputed daily (only goes UP)
3. **Health flags** — RS weakening, sector weak, giving back gains, time decay, earnings proximity, distribution stress
4. **Decision** — HOLD / RAISE_STOP / EARLY_EXIT

### Alert Examples

| Condition | Alert Type | Action |
|-----------|-----------|--------|
| Pending order >1 hour | ERROR | Check order status, may be stuck |
| Stop price > current price | ERROR | Data issue, stop clamped |
| >2 health flags fired | EARLY_EXIT | Exit position today |
| Earnings in 1-2 days | EARLY_EXIT | Flatten before report |
| RS degrading vs SPY | FLAG | Monitor, may be beginning of exit |

---

## Position Reconciliation (3a)

Runs daily. Compares DB `algo_positions` with Alpaca account.

### Findings

| Issue | Severity | Cause | Fix |
|-------|----------|-------|-----|
| DB has open 100 shares, Alpaca has 0 | ERROR | Position closed in Alpaca but not DB | Manually close in DB |
| Alpaca has 50 shares, DB has none | CRITICAL | Order filled outside our workflow or manual trade | Add to DB or contact broker |
| DB qty=100, Alpaca qty=50 | WARN | Partial fill? Divergence? | Investigate & sync |

**What to do on divergence:**
1. Query Alpaca directly: `alpaca.get_all_positions()`
2. Check DB open positions
3. If DB is wrong → update it manually
4. If Alpaca is wrong → contact support
5. Run reconciliation again to verify

---

## How Alerts Flow

```
Data Patrol runs (phase_1)
    ↓
Checks 16 aspects of data
    ↓
Writes results to data_patrol_log
    ↓
If CRITICAL/ERROR found:
    ├→ Email to argeropolos@gmail.com
    ├→ SMS to +1-312-307-8620
    └→ Slack #trading-alerts
    ↓
Orchestrator phase_1 checks latest patrol
    ├→ If CRITICAL/ERROR: HALT (don't trade)
    └→ If WARN only: continue, log warning
    ↓
Phase 3a: Reconciliation runs
    ├→ Alert on CRITICAL divergences
    └→ Log ERROR/WARN mismatches
    ↓
Phase 3: Position Monitor runs
    ├→ Alert on stale orders
    ├→ Alert on stop price issues
    └→ Propose exits/stops
    ↓
Continue to phases 4-7 (trading)
```

---

## Running the System

### Option 1: Full Production Run

```bash
# Set credentials in .env.local first (see ALERT_SETUP.md)

# Run orchestrator (includes patrol, alerts, reconciliation)
python3 algo_orchestrator.py

# Check results in DB
psql stocks -c "SELECT * FROM data_patrol_log ORDER BY created_at DESC LIMIT 20"
psql stocks -c "SELECT * FROM algo_audit_log WHERE action_type LIKE 'phase%' ORDER BY created_at DESC LIMIT 10"
```

### Option 2: Test First (Recommended)

```bash
# Test all components without trading
python3 test_patrol_system.py

# Test with actual alert send
python3 test_patrol_system.py --send-test-alert

# Just run patrol to see what it finds
python3 algo_data_patrol.py

# Just review positions
python3 -c "from algo_position_monitor import PositionMonitor; from algo_config import get_config; PositionMonitor(get_config()).review_positions()"

# Just check reconciliation
python3 algo_reconciliation.py
```

### Option 3: Quick Health Check

```bash
# Run patrol with critical checks only
python3 algo_data_patrol.py --quick

# Cross-validate top symbols
python3 algo_data_patrol.py --validate-alpaca
```

---

## Common Issues & Fixes

### Issue: Data stale >7 days

```bash
# Root cause: loader hasn't run
# Fix: re-run the loader
python3 load_prices.py  # or whatever your loader is

# Verify
python3 algo_data_patrol.py --quick
```

### Issue: OHLC broken (High < Low)

```bash
# Likely bad data from source
# Check latest price_daily
SELECT * FROM price_daily WHERE high < low ORDER BY date DESC LIMIT 10

# If recent: delete and re-load
DELETE FROM price_daily WHERE date >= '2025-05-05'
python3 load_prices.py
```

### Issue: Untracked Alpaca position

```bash
# Manual position or order filled outside our system
# Option 1: Close it manually in Alpaca
# Option 2: Add to DB
INSERT INTO algo_positions (symbol, quantity, avg_entry_price, status, position_id)
VALUES ('SYMBOL', 100, 45.50, 'open', gen_random_uuid());
```

### Issue: Stale orders pending >1 hour

```bash
# Check order status
SELECT trade_id, symbol, entry_price, status, created_at 
FROM algo_trades WHERE status='pending' AND created_at < NOW() - INTERVAL '1 hour'

# Try to fill/cancel via Alpaca API
alpaca.cancel_order(order_id)

# Mark as failed in DB
UPDATE algo_trades SET status='failed' WHERE trade_id = 'XXX'
```

---

## Key Metrics to Monitor

**Weekly checklist:**

- [ ] Patrol runs daily without CRITICAL issues
- [ ] Position reconciliation matches (or divergences are understood)
- [ ] No consistent ERROR patterns (same failure twice = systemic)
- [ ] Average data age <3 days
- [ ] <5 WARN alerts per day (normal market noise)
- [ ] 0 stale orders (if any, investigate API issues)

**Monthly review:**

- [ ] Review patrol_log for trends (improving or degrading?)
- [ ] Check loader performance (speed, consistency)
- [ ] Validate signal quality (do high-scoring signals actually trade well?)
- [ ] Audit any manual DB updates (keeps accountability)

---

## Further Reading

- **ALERT_SETUP.md** — Email + SMS + Slack configuration
- **algo_data_patrol.py** — Source code for all 16 checks
- **algo_position_monitor.py** — Stop computation, health scoring
- **algo_reconciliation.py** — DB-to-Alpaca matching
- **test_patrol_system.py** — Full system test harness
