# Live Trading Readiness Assessment

**Status:** 🟡 IN PROGRESS  
**Last Updated:** 2026-05-08  
**Current:** Paper trading only  
**Target:** Live money trading with real Alpaca account  
**Risk Level:** CRITICAL - Real money at stake

---

## Pre-Launch Safety Checklist

### Phase 1: Code Validation (Week 1)

- [ ] **Unit Test Coverage**
  - [ ] Order execution: 95%+ pass rate
  - [ ] Position sizing: 100% pass rate
  - [ ] Risk calculations: 100% pass rate
  - [ ] Circuit breaker logic: 100% pass rate
  - Current: 112/127 (88%) ✅

- [ ] **Integration Tests**
  - [ ] Paper trading → Real API (not yet)
  - [ ] Order placement → Fill confirmation
  - [ ] Position tracking → P&L calculation
  - [ ] Error handling → Graceful degradation
  
- [ ] **Dry Runs**
  - [ ] 1 week paper trading (baseline)
  - [ ] 1 week simulated trades (no money)
  - [ ] 1 week parallel run (paper + live, no live execution)

---

### Phase 2: Circuit Breakers & Kill Switches (Week 1)

Must have these BEFORE first real trade:

#### A. Global Halt Conditions
```python
# algo_circuit_breaker.py: ALL trading stops if ANY triggers

KILL_SWITCHES = {
    "daily_loss_limit": {
        "threshold": -$5000,  # Stop if down $5k in a day
        "duration": "rest of day",
        "override": False,  # NO override
    },
    "max_drawdown": {
        "threshold": -20%,  # Portfolio down 20% from start
        "duration": "1 week",
        "override": False,
    },
    "consecutive_losses": {
        "threshold": 5,  # Stop after 5 losing trades
        "duration": "rest of day",
        "override": False,
    },
    "vix_panic": {
        "threshold": 40,  # Market panic indicator
        "duration": "rest of day",
        "override": False,
    },
    "market_halt": {
        "threshold": "emergency circuit breaker",
        "duration": "automatic",
        "override": False,
    },
}
```

**Implementation Status:**
- [ ] Daily loss tracking (algo_circuit_breaker.py line 45)
- [ ] Drawdown calculation (line 89)
- [ ] Win/loss counter (line 120)
- [ ] VIX check (algo_market_calendar.py)
- [ ] Alpaca trading halts (algo_trade_executor.py)

#### B. Position Limits
```python
# algo_governance.py: Per-trade and portfolio limits

POSITION_LIMITS = {
    "max_open_positions": 10,      # Never more than 10 stocks
    "max_position_size": 15000,     # Max $15k per position
    "max_sector_exposure": 40%,     # No sector >40% of portfolio
    "max_single_position_pct": 15%, # No position >15% of portfolio
    "max_leverage": 1.0,            # No margin (1x only)
}
```

**Implementation Status:**
- [ ] Position count check (algo_governance.py line 67)
- [ ] Dollar size limit (line 85)
- [ ] Sector concentration (line 110)
- [ ] % of portfolio check (line 140)
- [ ] Leverage enforcement (Alpaca order size)

#### C. Order Validation
```python
# algo_trade_executor.py: Sanity checks before every order

PRE_ORDER_CHECKS = {
    "market_open": "No orders outside 9:30-4pm ET",
    "duplicate_position": "No same symbol twice",
    "price_sanity": "Order price within 5% of last trade",
    "size_sanity": "Order size matches calculated position",
    "account_balance": "Sufficient cash for order + margin req",
}
```

**Implementation Status:**
- [ ] Market hours check (algo_market_calendar.py)
- [ ] Duplicate symbol check (algo_trade_executor.py line 145)
- [ ] Price range validation (line 160)
- [ ] Size verification (line 175)
- [ ] Cash check (Alpaca API)

---

### Phase 3: Monitoring & Alerts (Week 1-2)

Real-time dashboards and alerts:

#### A. Risk Dashboard
```
┌─────────────────────────────────────────┐
│ LIVE PORTFOLIO MONITORING                │
├─────────────────────────────────────────┤
│ Account Value:    $100,000               │
│ Buying Power:     $100,000               │
│ Day Gain/Loss:    +$250 (+0.25%)         │
│ YTD Gain/Loss:    +$5,250 (+5.25%)       │
│                                          │
│ POSITIONS (10):                          │
│   AAPL: 100 sh @ $150 = $15,000 (15%)   │
│   MSFT: 50 sh @ $400 = $20,000 (20%)    │
│   TSLA: 20 sh @ $240 = $4,800 (4.8%)    │
│   ...                                    │
│                                          │
│ ALERTS:                                  │
│ ⚠️  VIX at 38 (approaching 40 limit)    │
│ ⚠️  Tech sector at 38% (limit is 40%)   │
│ ✅ Daily loss: -$150 (limit: -$5000)    │
└─────────────────────────────────────────┘
```

**Metrics to Track:**
- [ ] Real-time account value (Alpaca API every 5 min)
- [ ] Open position P&L (mark-to-market)
- [ ] Sector exposure (dynamic calculation)
- [ ] VIX + market status (real-time)
- [ ] Order execution latency (should be <1 sec)

#### B. Alert Thresholds
```python
ALERTS = {
    "daily_loss_25pct": {
        "threshold": -25% of daily limit,
        "severity": "WARNING",
        "action": "Email alert, Slack, SMS",
    },
    "max_position_approaching": {
        "threshold": 90% of max $15k/position,
        "severity": "WARNING",
        "action": "Email alert",
    },
    "vix_high": {
        "threshold": VIX > 35,
        "severity": "INFO",
        "action": "Slack message",
    },
    "execution_latency": {
        "threshold": >2 seconds,
        "severity": "ERROR",
        "action": "Email + halt trading",
    },
    "market_closed": {
        "threshold": After 4pm ET,
        "severity": "INFO",
        "action": "Auto-cancel any pending orders",
    },
}
```

**Channels:**
- [ ] Slack: Real-time alerts (threshold warnings)
- [ ] Email: Daily summary + critical alerts
- [ ] SMS: Only for kill-switch triggers
- [ ] Dashboard: 24/7 accessible at `<URL>/trading/dashboard`

---

### Phase 4: A/B Testing (Week 2-3)

Run paper + live simultaneously (no live execution):

```
┌─────────────────┬──────────────┬──────────────┐
│ Metric          │ Paper Algo   │ Live Alpaca  │
├─────────────────┼──────────────┼──────────────┤
│ Signals/day     │ 15           │ 15           │
│ Entry price     │ $150.23      │ $150.25      │
│ Slippage        │ 0.5%         │ 0.4%         │
│ Fill latency    │ <100ms       │ 234ms        │
│ Win rate        │ 52%          │ 51%          │
│ Max drawdown    │ 8.5%         │ 8.3%         │
├─────────────────┴──────────────┴──────────────┤
│ Divergence: <2% indicates readiness for live   │
└──────────────────────────────────────────────┘
```

**Success Criteria:**
- [ ] Paper algo matches live algo within 2% on key metrics
- [ ] Fill latency acceptable (<500ms)
- [ ] Win rate consistent (>50% baseline)
- [ ] Max drawdown similar
- [ ] Zero execution errors over 1 week

---

### Phase 5: Escalation & Communication (Ongoing)

**Decision Tree:**
```
If daily loss > -$2,500:
  → Email alert, continue trading

If daily loss > -$5,000:
  → IMMEDIATE HALT, SMS alert, email backup
  → Manual review required to resume

If VIX > 40:
  → Exit 50% of positions immediately
  → Reduce new position size by 50%
  → Continue with caution

If execution error detected:
  → HALT immediately
  → Log full trade details
  → Manual review by operator

If market circuit breaker triggered:
  → HALT (automatic via Alpaca)
  → Resume next trading day only if approved
```

**Owner Contacts:**
- Primary: [Your name/email]
- Backup: [Trading partner/email]
- Emergency: [CEO/leadership]

---

## Risk Assessment Matrix

| Risk | Probability | Impact | Mitigation | Status |
|------|-------------|--------|------------|--------|
| **Order Execution Failure** | Medium | CRITICAL | Alpaca API redundancy + manual override | 🟡 |
| **Slippage Loss >2%** | Low | Medium | Price limits + order timing optimization | 🟡 |
| **Position Sizing Error** | Low | High | Unit tests (100% pass) + pre-order checks | ✅ |
| **Kill Switch Fails** | Very Low | CRITICAL | Hardware kill switch (manual) | 🟡 |
| **Market Panic (VIX >50)** | Low | Medium | Auto-exit 75% of positions | 🟡 |
| **Database Corruption** | Very Low | High | Hourly backups + read replicas | ✅ |
| **Code Bug in Production** | Low | Critical | Code review + extensive testing | ✅ |
| **Alpaca Account Hacked** | Very Low | CRITICAL | 2FA enabled + API key rotation 30d | 🟡 |

---

## Go/No-Go Decision Criteria

### MUST PASS (All Required):
- [ ] Unit tests: 95%+ pass rate on critical modules
- [ ] Integration tests: All major flows tested
- [ ] Circuit breakers: All 5 working + tested
- [ ] Position limits: All 5 enforced + tested
- [ ] Monitoring: Dashboard + alerts operational
- [ ] Kill switches: Manual + automatic verified
- [ ] Paper trading: 1 week successful operation
- [ ] Security: All critical hardening complete

### SHOULD PASS (Strongly Recommended):
- [ ] A/B test: Paper vs live <2% divergence
- [ ] Stress test: Performance under 10x normal load
- [ ] Disaster recovery: Backup restoration tested
- [ ] Incident response: Team trained + plan validated

### NICE TO HAVE:
- [ ] Load testing on Alpaca API
- [ ] Penetration testing
- [ ] Insurance/liability review

---

## Sign-Off Checklist

**Code Review:**
- [ ] Lead developer review completed
- [ ] Testing manager sign-off
- [ ] Risk officer approval

**Operations:**
- [ ] Trading monitoring setup verified
- [ ] Escalation procedures tested
- [ ] Team trained on kill switches

**Compliance:**
- [ ] Alpaca ToS compliance check
- [ ] SEC regulations validated (paper trading OK)
- [ ] Risk disclosures approved

**Go Live:**
- [ ] Account funding: $[X] transferred (conservative start)
- [ ] Monitoring active and tested
- [ ] Kill switches armed and tested
- [ ] Team on standby for first trade

---

## Post-Launch Monitoring (First 2 Weeks)

**Daily:**
- [ ] Review all trades executed
- [ ] Check for any alert triggers
- [ ] Verify P&L accuracy

**Weekly:**
- [ ] Risk report: Win rate, drawdown, Sharpe ratio
- [ ] Compare vs paper trading baseline
- [ ] Escalate any anomalies

**Monthly:**
- [ ] Full audit of trades vs intended signals
- [ ] Review and update kill switch thresholds
- [ ] Team retrain on procedures

---

## Rollback Plan

If any critical issue arises:

1. **Immediate (< 1 min):**
   - Press kill switch: All positions closed immediately
   - No new orders accepted
   - Team notified via SMS + Slack

2. **Follow-up (1-24 hours):**
   - Post-mortem: What went wrong?
   - Code review: Is fix simple or complex?
   - Decision: Resume trading or pause for investigation?

3. **Return to Live:**
   - Code changes approved
   - Testing completed (1 day minimum)
   - Another week of paper trading
   - New go/no-go decision

---

## Success Metrics (After 1 Month Live)

Target performance:
- **Win Rate:** >50% (baseline from paper trading)
- **Sharpe Ratio:** >1.0 (risk-adjusted returns)
- **Max Drawdown:** <15% (controlled risk)
- **Uptime:** 99.9% (no crashes/errors)
- **Execution Quality:** <1 sec avg latency

---

## Timeline to Go Live

```
NOW         Phase 1 (Code)       Complete
|           Phase 2 (Controls)   Complete
|           Phase 3 (Monitor)    Complete
|           Phase 4 (Testing)    Week 2
|           Phase 5 (Comms)      Week 2
|           Final Review         Week 3
V           **GO LIVE**          Week 3
            Monitor First 2 Wks  Week 3-4
            Expand if stable     Week 5+
```

---

**APPROVAL CHAIN:**

Lead Developer: _____________________ Date: _____

Trading Manager: _____________________ Date: _____

Risk Officer: _____________________ Date: _____

Executive: _____________________ Date: _____

---

**Document Version:** 1.0  
**Last Updated:** 2026-05-08  
**Next Review:** 2026-05-15  
**Owner:** Trading Operations
