# Live Trading Readiness Checklist

**Purpose:** Validate system is production-ready before enabling real-money trades via Alpaca.

## ⚠️ CRITICAL: Alpaca Account & Authorization

- [ ] Alpaca account created and verified (brokerage account, not paper)
- [ ] Alpaca API keys generated with **live trading permissions**
- [ ] Test API call succeeds: `curl -H "APCA-API-KEY-ID: $KEY" https://api.alpaca.markets/v2/account`
- [ ] Account has minimum $2,000 to pass PDT rule (day trading)
- [ ] Account **NOT** in restricted mode or pending verification
- [ ] Review Alpaca terms: understanding PDT rules, margin requirements, fees
- [ ] Demo run completed on paper trading (`ALPACA_PAPER_TRADING=true`)

## Data Pipeline Ready

### Phase 1: Data Freshness

- [ ] Phase 1 data freshness check passes with >= 70% coverage
  - Current setting: 5% (temporary demo mode) → **Must revert to 70% for live**
  - [ ] Fix in `algo/algo_data_patrol.py`: Change `if pct < 5:` back to `if pct < 70:`
- [ ] Price data (`price_daily`) updated daily for >= 4,000 symbols
- [ ] Market health (`market_health_daily`) computed daily
- [ ] Signals (`buy_sell_daily`) generated daily
- [ ] At least 14 days of historical data present (for technical indicators)

### Phase 2: Circuit Breakers

- [ ] All 5 circuit breakers tested and understood:
  - [ ] CB1: Drawdown limit (default: 20%)
  - [ ] CB2: Daily loss limit (default: -2%)
  - [ ] CB3: Consecutive loss limit (default: 3)
  - [ ] CB4: Total open risk limit (default: 5 positions max)
  - [ ] CB5: VIX spike (default: > 35)
- [ ] Drawdown tracking enabled in database
- [ ] Position limit matches account size (start with 3-5 positions)

### Phase 3-4: Position Monitoring & Exit Execution

- [ ] Exit rules tested in paper mode:
  - [ ] Trailing stop logic executes correctly
  - [ ] Time-based exits work (e.g., 30-day hold limit)
  - [ ] Partial exits trigger at profit targets
- [ ] Position health scoring returns valid data
- [ ] Sector/stock correlation data available for risk calculations

### Phase 5: Signal Generation

- [ ] Signal tiers all passing (Tier 1-6):
  - [ ] Tier 1: Data quality checks
  - [ ] Tier 2: Market regime filter (SMA200, VIX)
  - [ ] Tier 3: Trend template scores >= threshold
  - [ ] Tier 4: Signal quality scores >= 40
  - [ ] Tier 5: Portfolio fit (no duplicate sectors)
  - [ ] Tier 6: Multi-factor filters (momentum, quality, catalyst)
- [ ] Signal audit log shows >= 10 qualified signals on test run
- [ ] No duplicate signals (same symbol multiple times in day)

### Phase 6: Entry Execution

- [ ] Pre-flight checks working:
  - [ ] Duplicate check prevents re-entry
  - [ ] Position limit enforced
  - [ ] Margin check passes
  - [ ] Alpaca order acceptance verified
- [ ] Bracket orders created correctly (entry + stop loss + target)
- [ ] Order status tracked in database (`trade_log`, `trade_execution_detail`)
- [ ] Paper-mode test shows 0 errors in trade execution

### Phase 7: Reconciliation

- [ ] Alpaca account sync works:
  - [ ] Live account balance retrieved correctly
  - [ ] Open positions match database
  - [ ] P&L calculated accurately
- [ ] Portfolio snapshot created daily
- [ ] Historical trade performance calculated

## Environment Configuration

- [ ] **CRITICAL:** `ALGO_LIVE_TRADING` **NOT YET SET** (pending final approval)
- [ ] `ALPACA_PAPER_TRADING=false` configured in AWS Secrets Manager
- [ ] `APCA_API_BASE_URL=https://api.alpaca.markets` (live endpoint, not paper)
- [ ] `DB_HOST` points to production RDS instance
- [ ] `FRED_API_KEY` configured for economic data
- [ ] Logging level set to `INFO` (audit trail for all trades)
- [ ] Alert email configured for critical events

## Risk Management & Position Limits

- [ ] **Max position size:** 2-4% of account per trade
- [ ] **Max concurrent positions:** 3-5 (verified in Phase 2 CB4)
- [ ] **Max sector exposure:** No single sector > 40% of portfolio
- [ ] **Correlation check:** No highly correlated stocks (R² > 0.7)
- [ ] **Daily loss limit:** -2% (trigger circuit breaker CB2)
- [ ] **Stop loss level:** Minimum -8% per position (hard stop)
- [ ] **Take profit target:** Tiered exits (25%, 50%, 100% at 8%, 15%, 25% gains)

## Testing Checklist

### Paper Trading Test (72 hours minimum)

- [ ] Run orchestrator with `ALPACA_PAPER_TRADING=true`
- [ ] Execute at least 3 full trading cycles (3 days)
- [ ] Verify:
  - [ ] Data loads without errors
  - [ ] Signals generated daily
  - [ ] Trades executed (expect 5-10 per day on paper)
  - [ ] Exit logic working (trailing stops, time exits)
  - [ ] P&L calculated correctly
  - [ ] No orphaned orders in Alpaca
- [ ] Check logs for warnings/errors: `grep -i "error\|failed\|exception" logs/`

### Dry-Run Mode (1 day)

- [ ] Run orchestrator with `--dry-run` flag
- [ ] Verify:
  - [ ] All phases execute
  - [ ] Signals identified but **NOT SENT** to Alpaca
  - [ ] Database records created for audit
  - [ ] Exit signals computed but not executed

### Pre-Live Rehearsal (1 day before go-live)

- [ ] Set `ALPACA_PAPER_TRADING=false` in **test environment only**
- [ ] Run against **paper account credentials** with live endpoint configured
- [ ] Verify Alpaca API responds with live URLs
- [ ] Execute 1-2 small test trades
- [ ] Confirm bracket order structure correct
- [ ] Monitor for any 401/403 auth errors

## Monitoring & Alerting

- [ ] CloudWatch dashboard created:
  - [ ] Orchestrator execution time
  - [ ] Lambda error rate (target: 0%)
  - [ ] Data freshness per table
  - [ ] Trade execution count & status
  - [ ] Alpaca API latency
- [ ] Alerts configured for:
  - [ ] Lambda errors (email + Slack)
  - [ ] Phase 1 failures (halt trading)
  - [ ] Circuit breaker triggers
  - [ ] Stale data (> 1 day old)
  - [ ] Failed trades
- [ ] Daily reconciliation report sent (positions, P&L, alerts)

## Documentation & Runbook

- [ ] Documented escalation procedure if issues occur
- [ ] Manual order entry steps (if Alpaca down)
- [ ] Position exit procedure (emergency unwind)
- [ ] Rollback steps (disable trading, revert to paper)
- [ ] Contact list: Alpaca support, AWS support, personal
- [ ] Trading rules and risk limits documented

## Final Authorization

- [ ] System owner reviewed all items above
- [ ] Risk tolerance and account size understood
- [ ] Commitment to monitor first 2 weeks (check logs daily)
- [ ] Plan to review performance weekly
- [ ] Plan to increase position size incrementally

## Go-Live Procedure

1. **Verify all items checked above**
2. **Set `ALGO_LIVE_TRADING=I_UNDERSTAND_REAL_MONEY`** in AWS Secrets Manager
3. Deploy via `deploy-all-infrastructure.yml` workflow
4. Monitor CloudWatch logs for first orchestrator run
5. Verify first trade executed in Alpaca account
6. Check daily P&L and adjust position size if needed

## Monitoring During First Week

- [ ] Check logs every morning: Any errors or halts?
- [ ] Verify trades placed yesterday: Correct symbols, quantities, prices?
- [ ] Monitor Alpaca account daily: Open positions, P&L, margin %?
- [ ] Check Phase 1 coverage: Is data freshness stable?
- [ ] Review portfolio heat: Any unexpected drawdowns?

---

**Last Updated:** 2026-05-25  
**Status:** DEMO MODE (5% coverage) — Ready for production after Phase 1 threshold reverted to 70%
