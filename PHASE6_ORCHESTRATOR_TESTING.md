# Phase 6: End-to-End Orchestrator & Trade Execution Testing

**Objective:** Verify the complete 7-phase orchestrator runs without errors and trades execute correctly.

**Duration:** 30-60 minutes (depends on market data availability)

---

## 📋 PRE-REQUISITES

Before starting:
```bash
# 1. Ensure database is fully populated
python3 run-all-loaders.py  # Or verify recent load completed

# 2. Verify SQS backfill completed (from Phase 2)
python3 phase2_verify_sqs.py

# 3. Check data freshness
python3 algo_data_patrol.py  # Should see all green
```

**Expected Output:**
- Stock symbols: 10,167 ✓
- Price data: 1.5M+ rows ✓
- Signals: 12,996 rows ✓
- Economic data: 100K+ rows ✓
- Market health: Current ✓

---

## 🚀 EXECUTION PLAN

### Phase 1: Dry-Run (No Real Trades)

```bash
# Run orchestrator in dry-run mode
python3 algo_orchestrator.py --mode paper --dry-run
```

**Expected Output:**
```
====================================
ORCHESTRATOR START
====================================

PHASE 1: DATA FRESHNESS CHECK
  Status: PASS
  message: All data fresh within window
  Symbols with data: 254+
  Days of coverage: 252+

PHASE 2: CIRCUIT BREAKERS
  Status: PASS or HALT (depends on market conditions)
  Drawdown: 0% (new account)
  Daily loss: 0% (new account)
  Market stage: Stage 2 (if market in uptrend)

PHASE 3: POSITION MONITOR
  Status: PASS
  Positions monitored: 0 (new account)
  Exits proposed: 0

PHASE 4: EXIT EXECUTION
  Status: PASS
  Exits executed: 0

PHASE 5: SIGNAL GENERATION
  Status: PASS
  Candidates evaluated: 261
  Passed Tier 1: 261 (100%)
  Passed Tier 2: 261 (100%) [if market is Stage 2]
  Passed Tier 3: 74 (28%) [Minervini filters]
  Passed Tier 4: 54 (73%) [Signal Quality]
  Passed Tier 5: 54 (100%) [Portfolio fit]
  Final signals: 54 (HIGH QUALITY)

PHASE 6: ENTRY EXECUTION
  Status: PASS
  Dry-run mode: No actual trades executed
  Would-be trades: 5-10 (depending on max_positions config)

PHASE 7: RECONCILIATION
  Status: PASS
  Portfolio value: $100,000
  Positions: 0 (dry-run)
  P&L: $0 (dry-run)

ORCHESTRATOR COMPLETE: SUCCESS
Duration: 1m 41s
====================================
```

**Success Criteria for Phase 1:**
- [ ] All 7 phases run without errors
- [ ] Phase 1 shows "PASS" (data is fresh)
- [ ] Phase 5 generates 10+ qualified signals
- [ ] No exceptions thrown
- [ ] Execution time < 5 minutes

**If Failures Occur:**
- Check data freshness: `python3 algo_data_patrol.py`
- Check log files: `tail -f algo_orchestrator.log`
- Verify database connection: `psql -h localhost -U stocks -d stocks`

---

### Phase 2: Paper Trading Mode (Simulated Trades)

```bash
# Run in paper mode (no real money, but simulated execution)
python3 algo_orchestrator.py --mode paper --date 2026-05-15
```

**Expected Behavior:**
- Orchestrator evaluates signals
- Generates buy/sell orders
- Logs simulated fills to database
- Records trades in `algo_trades` table
- Calculates simulated P&L

**Verification Queries:**
```sql
-- Check trades were recorded
SELECT COUNT(*), MAX(trade_date), AVG(entry_price) 
FROM algo_trades 
WHERE strategy='paper';

-- Should see: count > 0, recent dates, real prices

-- Check positions tracking
SELECT symbol, entry_price, current_price, 
       ROUND(100*(current_price-entry_price)/entry_price,2) as pnl_pct
FROM algo_positions
WHERE status='open';

-- Check portfolio history
SELECT * FROM portfolio_history ORDER BY date DESC LIMIT 5;
```

**Success Criteria for Phase 2:**
- [ ] Trades record to `algo_trades` table
- [ ] Positions tracked in `algo_positions`
- [ ] P&L calculations sensible (not NaN or extreme)
- [ ] Portfolio value updated
- [ ] Trade count matches signal count (accounting for position limits)

---

### Phase 3: Circuit Breaker Testing

**Objective:** Verify kill-switches work when conditions trigger

#### Test 3A: Market Stage Gating

```python
# Manually set market to Stage 1 (consolidation - no trading)
python3 << 'EOF'
import psycopg2
from datetime import date
from credential_helper import get_db_config

conn = psycopg2.connect(**get_db_config())
cur = conn.cursor()

# Set market to Stage 1 (should halt trading)
cur.execute("""
    INSERT INTO market_health_daily (date, market_symbol, market_stage, distribution_days)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT (date, market_symbol) DO UPDATE 
    SET market_stage = 1
""", (date.today(), '^GSPC', 1, 0))

conn.commit()
cur.close()
conn.close()
print("Market set to Stage 1 (no trading)")
EOF

# Run orchestrator - should halt at Phase 2
python3 algo_orchestrator.py --mode paper --dry-run

# Expected: Phase 2 halts with "Market not in uptrend"
```

**Expected Output:**
```
PHASE 2: CIRCUIT BREAKERS
  Status: HALT
  Reason: Market stage 1 (consolidation) - trading halted
```

**Success Criteria:**
- [ ] Phase 2 detects Stage 1 correctly
- [ ] Halts trading as designed
- [ ] No signals generated after halt

#### Test 3B: Drawdown Circuit Breaker

```python
# Simulate a losing position to test drawdown breaker
python3 << 'EOF'
import psycopg2
from datetime import date
from credential_helper import get_db_config

conn = psycopg2.connect(**get_db_config())
cur = conn.cursor()

# Record a losing trade
cur.execute("""
    INSERT INTO algo_trades 
    (symbol, trade_date, entry_price, shares, exit_price, pnl_pct, status)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
""", ('TEST', date.today(), 100, 100, 90, -10.0, 'closed'))

# Update portfolio history to show 10% loss
cur.execute("""
    INSERT INTO portfolio_history (date, total_value, cash, positions_count, drawdown_pct)
    VALUES (%s, %s, %s, %s, %s)
""", (date.today(), 90000, 9000, 1, -10.0))

conn.commit()
cur.close()
conn.close()
print("Simulated 10% drawdown")
EOF

# Run orchestrator - should check if drawdown exceeds limit
python3 algo_orchestrator.py --mode paper --dry-run
```

**Expected Behavior:**
- If max drawdown > threshold (e.g., 15%), Phase 2 halts
- Logs "Drawdown circuit breaker fired"
- No new trades until drawdown recovers

---

### Phase 4: Risk Calculation Verification

**Check Position Sizing:**
```sql
-- Verify position sizing logic
SELECT 
    symbol, 
    entry_price, 
    shares,
    entry_price * shares as position_value,
    ROUND(100 * (entry_price * shares) / 100000, 2) as pct_of_portfolio
FROM algo_positions
WHERE status = 'open'
ORDER BY position_value DESC
LIMIT 10;

-- Expected: Each position < 5% of portfolio, total < 50%
```

**Check Exposure Policy:**
```sql
-- Verify market exposure stays within limits
SELECT 
    date, 
    exposure_pct, 
    regime,
    CASE 
        WHEN exposure_pct > 80 THEN 'HIGH EXPOSURE'
        WHEN exposure_pct > 50 THEN 'MODERATE'
        ELSE 'LOW'
    END as exposure_level
FROM market_exposure_daily
ORDER BY date DESC
LIMIT 5;
```

**Success Criteria:**
- [ ] Position sizes reasonable (< 5% each)
- [ ] Total exposure < 50% in paper mode
- [ ] No individual position > $5,000
- [ ] Concentration limit respected

---

### Phase 5: Signal Quality Verification

**Check Tier Filtering:**
```sql
-- Count signals at each filter tier
SELECT 
    COUNT(*) as total_signals,
    SUM(CASE WHEN tier1_data_completeness THEN 1 ELSE 0 END) as tier1_pass,
    SUM(CASE WHEN tier2_market_health THEN 1 ELSE 0 END) as tier2_pass,
    SUM(CASE WHEN tier3_trend_template THEN 1 ELSE 0 END) as tier3_pass,
    SUM(CASE WHEN tier4_signal_quality THEN 1 ELSE 0 END) as tier4_pass,
    SUM(CASE WHEN tier5_portfolio_health THEN 1 ELSE 0 END) as tier5_pass
FROM buy_sell_daily
WHERE date = (SELECT MAX(date) FROM buy_sell_daily);

-- Expected output (example):
-- total | tier1 | tier2 | tier3 | tier4 | tier5
-- ------|-------|-------|-------|-------|-------
--   261 |   261 |   261 |    74 |    54 |    54
```

**Interpretation:**
- Tier 1: 100% (data quality gate)
- Tier 2: 100% (market health gate - if Stage 2)
- Tier 3: 28% (Minervini trend filter)
- Tier 4: 73% (Signal quality score)
- Tier 5: 100% (Portfolio fit)

**Success Criteria:**
- [ ] Tier 3 rejects 50-70% (Minervini is strict)
- [ ] Tier 4 rejects 10-30% (quality filtering)
- [ ] Final signals 10-50 (reasonable count)
- [ ] No tier passes 100% (gates are working)

---

### Phase 6: P&L Calculation Verification

**For Test Trades:**
```sql
-- Verify P&L is calculated correctly
SELECT 
    symbol,
    entry_price,
    exit_price,
    shares,
    ROUND(100 * (exit_price - entry_price) / entry_price, 2) as calculated_pnl_pct,
    pnl_pct,  -- From algo_trades
    CASE 
        WHEN ABS(pnl_pct - ROUND(100 * (exit_price - entry_price) / entry_price, 2)) < 0.01 THEN 'OK'
        ELSE 'MISMATCH'
    END as verification
FROM algo_trades
WHERE status = 'closed'
LIMIT 5;
```

**Expected:** All rows show "OK"

**Success Criteria:**
- [ ] P&L calculations match formula: (exit - entry) / entry * 100
- [ ] Commissions not double-counted
- [ ] Slippage factored correctly

---

## 🎯 FINAL VERIFICATION

### Run Complete Integration Test:

```bash
# Clean start
python3 << 'EOF'
import psycopg2
from credential_helper import get_db_config

conn = psycopg2.connect(**get_db_config())
cur = conn.cursor()

# Count current state
cur.execute("SELECT COUNT(*) FROM stock_symbols")
symbols = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM price_daily")
prices = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM buy_sell_daily")
signals = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM stock_scores")
scores = cur.fetchone()[0]

cur.close()
conn.close()

print(f"\nSystem State:")
print(f"  Symbols: {symbols}")
print(f"  Price records: {prices:,}")
print(f"  Signals: {signals:,}")
print(f"  Stock scores: {scores:,}")
EOF

# Run full orchestrator
python3 algo_orchestrator.py --mode paper --dry-run 2>&1 | tee orchestrator_test.log

# Parse results
python3 << 'EOF'
import re

with open('orchestrator_test.log', 'r') as f:
    log = f.read()

phases = ['PHASE 1', 'PHASE 2', 'PHASE 3', 'PHASE 4', 'PHASE 5', 'PHASE 6', 'PHASE 7']
results = {}

for phase in phases:
    if phase in log:
        status_match = re.search(f'{phase}.*?Status: ([A-Z]+)', log)
        if status_match:
            results[phase] = status_match.group(1)

print("\nOrchestrator Results:")
for phase, status in results.items():
    symbol = "✓" if status == "PASS" else "✗" if status == "FAIL" else "!"
    print(f"  {symbol} {phase}: {status}")
EOF
```

---

## ✅ PHASE 6 SUCCESS CRITERIA

**ALL of the following must be true:**

- [ ] Orchestrator runs Phase 1-7 without exceptions
- [ ] Phase 1: Data freshness check PASSES
- [ ] Phase 2: Circuit breaker logic PASSES (or HALTS correctly if market conditions warrant)
- [ ] Phase 5: Signal generation produces 10+ qualified signals
- [ ] Phase 6: Trades are logged to `algo_trades` table
- [ ] Phase 7: Portfolio history recorded
- [ ] P&L calculations are correct
- [ ] No "NaN" or "null" values in position tracking
- [ ] Orchestrator completes in < 5 minutes
- [ ] All logs are clean (no critical errors)

**If ANY of these FAIL:**
- Check error logs: `tail -100 algo_orchestrator.log`
- Verify database: `python3 algo_data_patrol.py`
- Re-run Phase 2 backfill if needed

---

## 📊 EXPECTED RESULTS

**After running all phases:**

| Component | Expected | Actual | Status |
|-----------|----------|--------|--------|
| Orchest phases | 7/7 | _____ | _____ |
| Signals generated | 10-50 | _____ | _____ |
| Trades recorded | > 0 | _____ | _____ |
| Positions tracked | > 0 | _____ | _____ |
| Portfolio value | $100K | _____ | _____ |
| Execution time | < 5 min | _____ | _____ |
| Errors | 0 | _____ | _____ |

---

## 🔗 NEXT STEPS

If Phase 6 PASSES:
1. System is ready for live paper trading
2. Run orchestrator daily for 5-10 trading days
3. Monitor for calculation drift or edge cases
4. Proceed to Phase 7 (Standardize connections)

If Phase 6 FAILS:
1. Check specific phase failure
2. Review logs for root cause
3. Identify schema or calculation mismatch
4. Re-test that phase
5. Document issue in STATUS.md

---

Date: 2026-05-16
Prepared for: Production Readiness Verification
