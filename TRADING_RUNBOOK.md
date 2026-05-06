# Institutional Trading Operations Runbook

**Version:** 1.0  
**Status:** Production Ready  
**Last Updated:** 2026-05-06  
**Maintained By:** Trading Operations Team

---

## Table of Contents

1. Daily Pre-Market Checklist
2. Trading Day Procedures
3. Halt & Circuit Breaker Protocols
4. Error Escalation Matrix
5. Position Reconciliation Procedures
6. Manual Intervention Checklist
7. After-Market Procedures
8. Kill Switch Activation

---

## Section 1: Daily Pre-Market Checklist (T-60 min)

Run 30 minutes before market open (9:30 AM ET).

### 1.1 Data Integrity Check
- [ ] **Data Feed Status**: Verify price data streaming (last update < 5 minutes ago)
  - Command: `SELECT MAX(date) FROM price_daily WHERE symbol='SPY'`
  - Expected: Today's date
  - Action if failed: Contact data team, do not trade until confirmed

- [ ] **Technical Data Updated**: Verify ATR, RSI, moving averages computed
  - Command: `SELECT MAX(date) FROM technical_data_daily WHERE symbol='SPY'`
  - Expected: Today's date
  - Action if failed: Re-run data patrol, fix missing data

- [ ] **Market Health Data**: Check VIX, market stage, sector data
  - Command: `SELECT * FROM market_health_daily WHERE date = TODAY ORDER BY date DESC LIMIT 1`
  - Expected: VIX value, stage 1-4, early_close flag
  - Action if failed: Alert data engineering

### 1.2 System Health Check
- [ ] **Database Connection**: Verify DB is responsive
  - Command: `SELECT 1` (should return instantly)
  - Action if failed: Check AWS RDS, contact DevOps

- [ ] **Alpaca Connection**: Verify paper trading endpoint is responsive
  - Command: `curl -H "APCA-API-KEY-ID: ..." https://paper-api.alpaca.markets/v2/account`
  - Expected: HTTP 200, account balance returned
  - Action if failed: Check Alpaca status page, verify credentials

- [ ] **Reconciliation Check**: Verify no orphaned positions from yesterday
  - Command: `SELECT COUNT(*) FROM algo_positions WHERE status='open' AND created_at < CURRENT_DATE`
  - Expected: 0 or all positions have corresponding DB records
  - Action if failed: Reconcile manually, contact DevOps

### 1.3 Configuration Validation
- [ ] **Circuit Breaker Thresholds**: Verify limits are correct
  - Expected: max_positions=10, max_sector_concentration=30%, risk_limit=2%
  - Action if incorrect: Update config, document change

- [ ] **Trading Enabled**: Verify `trading_enabled=true` in config
  - Command: `SELECT value FROM algo_config WHERE key='trading_enabled'`
  - Expected: true
  - Action if false: Check for scheduled maintenance, verify kill switch position

### 1.4 Alert System Status
- [ ] **SNS Topic Active**: Verify alerts can be sent
  - Command: Publish test alert, verify receipt in Slack/email within 30 seconds
  - Action if failed: Check SNS permissions, contact DevOps

- [ ] **Email Alerts Configured**: Verify recipient list
  - Expected: oncall@company.com subscribed to critical alerts
  - Action if missing: Add email to distribution list

### 1.5 Kill Switch Status
- [ ] **Kill Switch Armed**: Verify kill switch Lambda and EventBridge rule in place
  - Command: `aws lambda get-function --function-name algo-kill-switch`
  - Expected: Function exists and role has terminate permissions
  - Action if missing: Deploy kill switch Lambda before trading

---

## Section 2: Trading Day Procedures

### 2.1 Market Open (9:30 AM ET)
- Monitor first 5 minutes of trading for data quality issues
- Watch for unusual volume or price movements (halt triggers)
- Verify first orchestrator run completes (should be ~2 min)
- Check that first trades (if any) execute without errors

### 2.2 Continuous Monitoring (9:30 AM - 3:45 PM ET)
**Every 30 minutes:**
- [ ] Check position health: all positions have stops above worst 5-min lows
- [ ] Verify no CRITICAL alerts in past 30 minutes
- [ ] Monitor VIX: if VIX > 35, ensure circuit breaker halt is active
- [ ] Check order queue: no pending orders stuck > 1 hour
- [ ] Verify portfolio value hasn't dropped > 3% unexpectedly

**Hourly:**
- [ ] Check execution quality: slippage metrics from TCA
  - Alert if avg slippage > 50 bps (half of expected)
  - Alert if fill rate < 90% (execution problems)
- [ ] Verify no sector concentration > 30%
- [ ] Check portfolio beta: ensure < 2.0 (market risk reasonable)

### 2.3 Mid-Day Reconciliation (12:00 PM ET)
- [ ] Reconcile algo_trades vs. Alpaca: count and quantities match
- [ ] Verify all positions have corresponding trades
- [ ] Check for any rejected/cancelled orders (investigate if > 5% rejection rate)
- [ ] Review any WARNING alerts from data patrol

### 2.4 Market Close Preparation (3:30 PM ET)
- [ ] Check for early close flag (market closes 3 PM instead of 4 PM)
  - If yes: halt all new entries at 2:45 PM
- [ ] Verify no positions will be stuck overnight in earnings blackout
  - Check: any exiting tomorrow before earnings
  - Action: Close if days_to_earnings < 3
- [ ] Verify trailing stops are updated to reflect day's high/low
- [ ] Check position-count limits: should not exceed 10 concurrent positions

### 2.5 After-Hours Check (4:15 PM ET)
- [ ] Market closes at 4:00 PM — verify last bar is received
- [ ] Compute daily metrics: Sharpe, win rate, max DD, slippage
- [ ] Generate daily performance report
- [ ] Check for any "CRITICAL" severity alerts during the day
- [ ] Log day's summary in trading journal

---

## Section 3: Halt & Circuit Breaker Protocols

### 3.1 Single-Stock Halt Detected

**Trigger:** System detects Alpaca asset status != ACTIVE

**Immediate Actions (within 2 minutes):**
1. Cancel all pending orders for halted symbol
2. Log halt event in audit_log with timestamp
3. Send WARN alert: "Symbol {SYM} halted — pending orders cancelled"
4. Do NOT attempt to re-entry until halt clears

**Monitoring:**
- Check Alpaca asset status every 5 minutes until status = ACTIVE
- Do not re-entry until 1 full hour after halt clearance (volatility risk)
- Log clearance time in audit log

**Example Response:**
```
[HALT DETECTED] TSLA halted at 2:30 PM
[ACTION] Cancelled 2 pending orders
[ALERT] Sent to oncall
[WAIT] Monitoring for clearance...
[CLEAR] TSLA resumed trading at 2:45 PM
[WAIT] Holding 60 minutes before re-entry
[RESUME] OK to re-enter TSLA at 3:45 PM
```

### 3.2 Market Circuit Breaker L1 (7%+ down)

**Trigger:** S&P 500 down 7% intraday from open

**Immediate Actions (within 1 minute):**
1. Halt all new position entries
2. Tighten all existing stop losses by 50% (move stops closer)
3. Log CB L1 event as "CIRCUIT_BREAKER_L1"
4. Set trading halt timer: 15 minutes
5. Send ERROR alert: "Circuit Breaker L1 active — new entries halted 15 min"

**During 15-Minute Halt:**
- Monitor S&P 500 closely
- If next CB level triggered, escalate procedures
- If market stabilizes, resume entries at 15-min mark

**Resume Trading:**
- At 15-min mark: resume new entries if S&P still down 7-13%
- Maintain tightened stops for all open positions

### 3.3 Market Circuit Breaker L2 (13%+ down)

**Trigger:** S&P 500 down 13% intraday from open

**Immediate Actions (within 1 minute):**
1. Halt all new position entries (maintain halt)
2. Further tighten all stops by 25% more
3. Prepare for L3 contingency: have closing script ready
4. Log CB L2 event
5. Send CRITICAL alert: "Circuit Breaker L2 active — 15 min halt, prepare for L3"

**Monitoring:**
- Check S&P 500 every 2 minutes
- If approaches 20%, prepare for full market halt

### 3.4 Market Circuit Breaker L3 (20%+ down)

**Trigger:** S&P 500 down 20% intraday from open

**Immediate Actions (within 1 minute):**
1. Halt all new position entries
2. BEGIN FORCE-EXIT PROCESS
3. Close all positions immediately at market price
4. Log CB L3 event as "CIRCUIT_BREAKER_L3_MARKET_HALT"
5. Send CRITICAL alert: "Circuit Breaker L3 — market halt active, closing all positions"

**Force-Exit Procedure:**
1. For each open position:
   - Issue market sell order (not limit)
   - Log position close with reason="CIRCUIT_BREAKER_L3"
   - Verify fill within 2 minutes
2. After all positions closed: verify zero open positions
3. Alert: "All positions closed, portfolio flat"

**Post-Halt (market may halt for rest of day):**
- Do NOT attempt re-entry until next trading day
- Review why CB L3 triggered, assess market condition
- Consider reducing position sizing, risk limits for next day

---

## Section 4: Error Escalation Matrix

### Level 1: WARNING (Monitor, No Action Required)
- Slippage 100-150 bps on single fill
- Single order rejected (order itself was bad)
- Position concentration 25-30%
- Win rate dropped 5-7% from backtest
- VIX 20-25 (caution zone)

**Action:** Log in audit_log, no alert needed

### Level 2: ERROR (Investigate Within 1 Hour)
- Slippage > 150 bps on fill (execution problem)
- Fill rate dropping below 90% (Alpaca issues)
- Portfolio concentration > 30%
- Win rate dropped > 10% from backtest
- VIX 25-35 (activate caution multiplier)
- Data staleness > 12 hours for any symbol
- Position orphaned (DB mismatch with Alpaca)

**Action:**
1. Send ERROR alert to oncall
2. Investigate root cause within 60 minutes
3. Document findings in slack #algo-alerts
4. If unfixable: consider kill-switch activation
5. Notify trading manager

### Level 3: CRITICAL (Immediate Action Required, < 5 Minutes)
- Slippage > 300 bps (likely bad data or market halt)
- Fill rate < 80% (systematic rejection)
- Portfolio concentration > 40% (single sector)
- Orphaned order after Alpaca fill (DB failure recovery)
- Circuit breaker triggered (any level)
- Data unavailable > 30 minutes (data feed down)
- Kill switch activated by risk committee
- Negative daily slippage  (consistent losses to slippage)

**Action:**
1. Send CRITICAL alert immediately (SMS + Slack + Email)
2. Page oncall + trading manager within 30 seconds
3. Assess: continue trading or activate kill switch?
4. Document decision and timeline
5. If kill-switch: execute immediately, reconcile, communicate to team

---

## Section 5: Position Reconciliation Procedures

### 5.1 Daily Reconciliation (Pre-Market + Post-Market)

**Command:**
```sql
SELECT ap.symbol, ap.quantity, ap.current_price,
       (SELECT qty FROM alpaca_positions WHERE symbol = ap.symbol) as alpaca_qty
FROM algo_positions ap
WHERE ap.status = 'open'
```

**Expected:** DB quantity = Alpaca quantity for all open positions

**If Mismatch Found:**

1. **Alpaca qty = 0 (position closed in Alpaca but open in DB):**
   - This is normal: Alpaca filled our order, but DB still shows pending
   - Action: Mark position as `closed` in algo_positions, close corresponding trade

2. **Alpaca qty > DB qty (Alpaca has more shares):**
   - Possible: partial fill, additional buys from another system
   - Action: Investigate — if external buys, reject and align
   - Action: If our system: update DB to match Alpaca

3. **Alpaca qty < DB qty (DB has more shares):**
   - Possible: unfilled order, stock split (division)
   - Action if split: recompute stop loss / split_ratio, update quantity
   - Action if unfilled: check order status in Alpaca API

4. **Reconciliation Failure (can't match after 3 attempts):**
   - Action: Alert trading manager, escalate to Level 3 ERROR
   - Action: Do NOT attempt to trade that symbol until resolved
   - Action: Flat position manually if necessary

### 5.2 Post-Halt Reconciliation

After a single-stock halt clears:
```sql
SELECT * FROM algo_positions WHERE symbol = 'HALTED_SYMBOL'
```

Verify:
- [ ] No orphaned pending orders
- [ ] Quantity matches Alpaca
- [ ] Stop loss is reasonable (didn't gap down/up too much)
- [ ] Position is not stale (was it filled, or is it still pending?)

If stop is no longer reasonable due to gap:
- Close position (stop was broken by halt)
- Log: "Position closed due to gap from halt"

---

## Section 6: Manual Intervention Checklist

### 6.1 When to Manually Intervene

Never intervene unless:
- Kill switch activated
- System is down (not responding)
- Multiple CRITICAL errors in quick succession
- Data feed completely unavailable
- Alpaca API is down

### 6.2 Manual Position Close

If need to close a position manually:

1. **Record the action:**
   ```sql
   INSERT INTO algo_audit_log (action_type, details, severity, action_date)
   VALUES ('MANUAL_CLOSE', 'Symbol TSLA closed due to {REASON}', 'WARN', NOW())
   ```

2. **Close via Alpaca:**
   - Use Alpaca dashboard or CLI to sell at market price
   - Verify fill immediately

3. **Update algo_positions:**
   ```sql
   UPDATE algo_positions SET status='closed' WHERE symbol='TSLA'
   ```

4. **Update algo_trades:**
   ```sql
   UPDATE algo_trades SET status='closed', exit_price=FILLED_PRICE, 
           exit_reason='MANUAL_CLOSE', exit_date=NOW()
   WHERE symbol='TSLA' AND status='filled'
   ```

5. **Alert team:**
   - Slack: "#algo-alerts" with timestamp, symbol, reason
   - Email: trading manager with full details

### 6.3 Kill Switch Activation

**Authorized by:** Trading Manager, Risk Committee Lead

**Procedure:**
1. Verify authorization from trading manager (phone call, not email)
2. Execute Lambda: `aws lambda invoke --function-name algo-kill-switch /tmp/response.json`
3. Verify function response: should report "trading_halted: true"
4. Monitor Alpaca: all pending orders should be cancelled within 30 seconds
5. Verify portfolio: all positions should be marked for market close
6. Log: "Kill switch activated by {WHO} at {WHEN} due to {REASON}"
7. Notify team via email + Slack with full details

**After Kill Switch:**
- Do NOT attempt to resume trading without explicit approval
- Hold post-mortem meeting within 24 hours
- Document root cause analysis
- Update procedures to prevent recurrence

---

## Section 7: After-Market Procedures (After 4:00 PM ET)

### 7.1 Trade Execution Review (4:15 PM - 4:45 PM)
- [ ] Count daily trades: how many entries? exits?
- [ ] Review P&L: daily profit/loss, cumulative
- [ ] Analyze TCA: avg slippage, fill rate, worst fill
- [ ] Review performance: daily Sharpe, win rate

### 7.2 Alert Review
- [ ] List all WARN/ERROR/CRITICAL alerts from the day
- [ ] For each alert: document root cause and resolution
- [ ] Update runbook if new patterns emerge

### 7.3 Data Quality Check
- [ ] Verify all trades are recorded in algo_trades table
- [ ] Verify all positions are recorded in algo_positions table
- [ ] Verify portfolio snapshots captured (should be hourly)
- [ ] Check for any data anomalies in price_daily

### 7.4 Backup & Logging
- [ ] Export daily audit log
- [ ] Backup position state
- [ ] Generate daily report PDF for trading manager
- [ ] Verify overnight batch jobs are scheduled (e.g., backtest regression)

---

## Section 8: Kill Switch Activation

**DO NOT use without explicit verbal authorization.**

### 8.1 Kill Switch Trigger Conditions

Activate immediately if:
- Multiple unrecovered errors (> 3 CRITICAL in 10 min)
- Data feed down > 30 minutes
- Alpaca API down > 10 minutes
- Unexplained portfolio loss > 5% in 1 hour
- System is generating orphaned positions consistently
- Position reconciliation cannot be fixed
- Risk committee determines market conditions unsafe

### 8.2 Activation Procedure

1. **Get Verbal Authorization** (required):
   ```
   Call: [TRADING_MANAGER_PHONE]
   Say: "Kill switch request due to [REASON]. Authorization?"
   Wait for: "Yes, proceed"
   ```

2. **Activate Kill Switch:**
   ```bash
   aws lambda invoke \
     --function-name algo-kill-switch \
     --payload '{"action":"halt"}' \
     /tmp/response.json
   ```

3. **Verify Activation (within 30 seconds):**
   - Alpaca: all pending orders cancelled
   - Database: all positions marked "halting"
   - Alerts: CRITICAL "Kill switch activated" sent

4. **Document:**
   ```sql
   INSERT INTO algo_audit_log (action_type, details, severity)
   VALUES ('KILL_SWITCH_ACTIVATED', 
           'Activated by {YOUR_NAME} at {TIME} due to {REASON}',
           'CRITICAL');
   ```

5. **Post-Activation:**
   - Do NOT restart trading without:
     * Root cause analysis
     * Trading committee approval
     * All systems verified working
   - Hold incident review within 2 hours

---

## Appendix: On-Call Escalation Chain

| Time | Escalation | Contact |
|------|-----------|---------|
| Immediate (0-5 min) | Oncall Trader | oncall-trader@company.com / +1-555-TRADER |
| 5-15 minutes | Trading Manager | trading-mgr@company.com / +1-555-MGR |
| 15+ minutes | Risk Committee Lead | risk-lead@company.com / +1-555-RISK |
| System Down | DevOps Lead | devops@company.com / PagerDuty |

---

**Last Updated:** 2026-05-06  
**Next Review:** 2026-08-06  
**Approved By:** Trading Committee
