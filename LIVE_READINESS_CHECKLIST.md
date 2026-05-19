# Live Trading Readiness Checklist (Market Opens 9:30 AM ET - 8 hour deadline)

**Status: IN PROGRESS (2026-05-19 03:57 AM)**  
**Goal:** Switch from dry-run (`--dry-run`) mode to **LIVE PAPER TRADING** on Alpaca

---

## PHASE 1: CREDENTIALS & CONFIGURATION (Target: 04:15 AM - 20 min)

### 1a. Alpaca Credentials
- [ ] **NEW API KEYS NEEDED** - Previous keys compromised in git history
  - Go to: https://app.alpaca.markets/settings/keys
  - Generate new API Key ID and Secret Key
  - Add to GitHub Secrets: `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY`
  - Verify in AWS Secrets Manager: `algo/alpaca` (JSON format)
  - Test: `python3 config/credential_validator.py`

### 1b. Database Credentials
- [ ] Verify in environment: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
- [ ] AWS Secrets Manager: `algo/database` (must have JSON with credentials)
- [ ] Test connection: `python3 config/credential_validator.py`

### 1c. FRED API (Economic Data)
- [ ] Add `FRED_API_KEY` to environment or GitHub Secrets
- [ ] Used for recession analysis in Phase 2 circuit breakers

### 1d. Configuration Files
- [ ] Review `algo/algo_config.py` - all defaults correct for live mode?
- [ ] Position limits: `max_positions=10` (adjust for portfolio size)
- [ ] Risk limits: Check drawdown/daily loss/VIX thresholds
- [ ] Entry/exit targets: Verify Minervini percentages

---

## PHASE 2: CODE READINESS (Target: 05:00 AM - 45 min)

### 2a. Uncommitted Changes (CRITICAL!)
- [ ] **COMMIT these changes:**
  ```
  M algo/algo_advanced_filters.py   (earnings date query fixes)
  M algo/algo_liquidity_checks.py   (SQL subquery fixes)
  M algo/orchestrator/phase5_signal_generation.py (eval_date fix)
  ```
  Commit message: "fix: refine earnings query fallbacks and liquidity SQL aggregations"

### 2b. Dry-Run Mode Removal
- [ ] Check `algo/algo_orchestrator.py` - `self.dry_run` flag correctly initialized
- [ ] Verify Phase 3a (position reconciliation) handles Alpaca unavailable gracefully
- [ ] Verify Phase 4 (exit execution) is skipped when no positions (expected behavior)
- [ ] Verify Phase 6 (entry execution) actually calls `TradeExecutor.execute_trade()`

### 2c. Data Freshness
- [ ] All loaders configured and passing:
  - Price data: `price_daily` (need today's market data)
  - Technical indicators: `technical_data_daily` (RSI, SMA, ATR, etc.)
  - Buy/Sell signals: `buy_sell_daily` (today's signals with rich technical data)
  - Trend data: `trend_template_data` (market stage detection)
  - Earnings: `earnings_calendar`, `earnings_estimates`, `earnings_history`

### 2d. Feature Flags & Circuit Breakers
- [ ] All feature flags reviewed in `utils/feature_flags.py`
- [ ] All 13 circuit breakers enabled and tested
- [ ] VIX calculation: `_compute_vix_safe()` includes fallback logic

---

## PHASE 3: DATA PIPELINE READY (Target: 05:45 AM - 45 min)

### 3a. Run All Loaders
```bash
# Load historical data + latest
python3 run-all-loaders.py
```
- [ ] Loaders complete without errors
- [ ] Check `data_loader_status` table - all recent loaders green
- [ ] **Critical tables populated:**
  - `stock_symbols`: 10K+ symbols
  - `price_daily`: 8M+ rows, latest through TODAY
  - `technical_data_daily`: Complete through TODAY
  - `buy_sell_daily`: Today's signals available (needed for Phase 5)
  - `trend_template_data`: Market stage available

### 3b. Data Freshness Verification
```bash
python3 -c "
import psycopg2
from config.credential_helper import get_db_config
from datetime import date
conn = psycopg2.connect(**get_db_config())
cur = conn.cursor()

tables = ['price_daily', 'technical_data_daily', 'buy_sell_daily', 'trend_template_data']
for tbl in tables:
    cur.execute(f'SELECT MAX(date) FROM {tbl}')
    max_date = cur.fetchone()[0]
    print(f'{tbl}: {max_date} (today={date.today()}, OK={max_date == date.today()})')
"
```
- [ ] All critical tables have TODAY's date
- [ ] No stale data (> 1 day old)

### 3c. Edge Cases in Data
- [ ] **Earnings near signals**: Check `earnings_blackout` is working (5-day window)
- [ ] **Thinly traded stocks**: Check `liquidity_checks` (min $500K ADV)
- [ ] **Extended above 50-DMA**: Hard-fail gate active (>15% extension)
- [ ] **Halted/delisted symbols**: No buy signals for halted stocks
- [ ] **Gap days**: Handle opening gaps in price/volume correctly

---

## PHASE 4: ORCHESTRATOR DRY-RUN WITH LIVE DATA (Target: 06:30 AM - 45 min)

### 4a. Run Orchestrator in Dry-Run Mode
```bash
python3 algo/algo_orchestrator.py --dry-run --verbose
```
- [ ] Phase 1 (Data Freshness): PASS ✓
- [ ] Phase 2 (Circuit Breakers): PASS ✓
- [ ] Phase 3 (Position Monitor): PASS ✓ (0 positions expected)
- [ ] Phase 3b (Exposure Policy): PASS ✓
- [ ] Phase 4 (Exit Execution): PASS ✓ (skipped, no positions)
- [ ] Phase 5 (Signal Generation): PASS ✓ (should have today's signals)
- [ ] Phase 6 (Entry Execution): PASS ✓ (DRY-RUN skips actual trades)
- [ ] Phase 7 (Reconciliation): PASS ✓

### 4b. Review Orchestrator Logs
- [ ] Check `algo_audit_log` table for today's run
- [ ] Verify signal waterfall: how many signals passed each tier?
  - Tier 1 (data quality): X signals
  - Tier 2 (market health): Y signals
  - Tier 3 (trend template): Z signals (should be Stage 2 only)
  - Tier 4 (signal quality): N signals
  - Tier 5 (portfolio): M signals
  - Tier 6 (advanced filters): K signals (final candidates)
- [ ] Check for any warnings or errors
- [ ] Verify position sizing math (50% exposure, etc.)

### 4c. Review Generated Signals
```bash
python3 -c "
import psycopg2
from config.credential_helper import get_db_config
from datetime import date
conn = psycopg2.connect(**get_db_config())
cur = conn.cursor()

# Get today's candidates
cur.execute('''
    SELECT symbol, signal_date, composite_score, rsi, sma_50, stage_number
    FROM buy_sell_daily
    WHERE signal_date = %s
    ORDER BY composite_score DESC
    LIMIT 10
''', (date.today(),))

print('Top 10 candidates for today:')
for row in cur.fetchall():
    print(f'{row[0]}: score={row[2]:.1f}, rsi={row[3]}, sma_50={row[4]}, stage={row[5]}')
"
```
- [ ] At least some qualified signals (ideally 5-20)
- [ ] Technical indicators populated (rsi, sma_50, etc.)
- [ ] Composite scores make sense (high quality = high score)

---

## PHASE 5: LIVE MODE SWITCH (Target: 07:30 AM - 1 hour)

### 5a. Remove --dry-run Flag
- [ ] Change command from: `algo/algo_orchestrator.py --dry-run`
- [ ] To: `algo/algo_orchestrator.py` (no flag)
- [ ] Or use environment: `DRY_RUN=false`

### 5b. Pre-Flight Checks (Read-Only)
- [ ] Alpaca credentials work: `python3 -c "import alpaca; print(alpaca.REST(...)"`
- [ ] Account is PAPER account (not LIVE)
- [ ] Buying power is reasonable (>$10K for testing)
- [ ] No existing open positions in Alpaca (start clean)
- [ ] No existing open orders in Alpaca

### 5c. Alert Configuration (OPTIONAL but RECOMMENDED)
- [ ] Email alerts: Check `AlertManager` configuration
  - [ ] SMTP credentials correct
  - [ ] Recipient emails specified
- [ ] Slack alerts (if using):
  - [ ] Webhook URL configured
  - [ ] Channel specified
- [ ] SMS alerts (if using):
  - [ ] Phone numbers configured
  - [ ] Service credentials working

### 5d. Monitoring Setup
- [ ] CloudWatch dashboard created for:
  - [ ] Orchestrator phase durations
  - [ ] Signal count waterfall
  - [ ] Position P&L
  - [ ] Trade execution status
- [ ] Error alerting configured
- [ ] Log aggregation working

---

## PHASE 6: LIVE EXECUTION TEST (Target: 08:30 AM - 1 hour before market)

### 6a. First Live Run (Still Paper Trading)
```bash
# Start with today's data loaded
python3 algo/algo_orchestrator.py --verbose
```
- [ ] All 7 phases complete successfully
- [ ] Phase 5: Real signals generated (not dry-run)
- [ ] Phase 6: Real trade orders submitted to Alpaca
- [ ] No errors in logs
- [ ] Audit log shows real execution (not simulation)

### 6b. Verify Trades Executed
```bash
python3 -c "
import alpaca.trading.client as tc
api = tc.TradingClient(...)
positions = api.get_all_positions()
print(f'Open positions: {len(positions)}')
for p in positions:
    print(f'{p.symbol}: {p.qty} shares @ {p.avg_fill_price}')
"
```
- [ ] Orders appear in Alpaca
- [ ] Positions open (if signals qualified)
- [ ] Entry prices match strategy
- [ ] Position sizing matches formula

### 6c. Verify Position Monitoring
- [ ] Phase 3 runs and updates positions correctly
- [ ] Trailing stops calculated
- [ ] P&L computed
- [ ] Risk metrics updated

### 6d. Verify Exit Logic
- [ ] Phase 4 evaluates exits
- [ ] Stop losses functional (would execute if breached)
- [ ] Partial profit-taking logic functional
- [ ] Time-based exits scheduled

---

## PHASE 7: SAFETY CHECKS (Target: 09:00 AM - 30 min before open)

### 7a. Risk Management Validation
- [ ] Max position size: Never > $50K per trade (or configured limit)
- [ ] Portfolio exposure: Never > 50% (or configured limit)
- [ ] Daily loss limit: Would halt if exceeded
- [ ] Drawdown limit: Would halt if exceeded
- [ ] VIX circuit breaker: Would block entries if VIX > 30 (or configured)

### 7b. Edge Case Handling
- [ ] Test: What happens if Alpaca API is slow? (Timeouts graceful)
- [ ] Test: What happens if a stock halts? (Position monitoring graceful)
- [ ] Test: What happens if earnings announced overnight? (Blackout enforced)
- [ ] Test: What happens if market crashes? (Circuit breaker halts execution)

### 7c. Database Integrity
- [ ] Check for orphaned/duplicate trades
- [ ] Verify position count matches Alpaca
- [ ] Verify cash balance matches Alpaca
- [ ] No pending transactions

### 7d. Logging & Auditing
- [ ] Verify all trades logged to `algo_audit_log`
- [ ] Verify all signals logged with scores
- [ ] Verify all rejections logged with reasons
- [ ] Verify all errors logged with context

---

## PHASE 8: GO/NO-GO DECISION (Target: 09:20 AM - 10 min before open)

### 8a. Final Checklist
- [ ] **Tests Passing**: 302 unit tests + integrations ✓
- [ ] **Data Fresh**: All critical tables through TODAY ✓
- [ ] **Credentials**: Alpaca + DB + FRED working ✓
- [ ] **Orchestrator**: Dry-run with real data successful ✓
- [ ] **Live Test**: First orders executed on Alpaca ✓
- [ ] **Risk Limits**: All circuit breakers armed ✓
- [ ] **Monitoring**: CloudWatch + logs operational ✓
- [ ] **Code**: All 3 modified files committed ✓

### 8b. Known Limitations / Workarounds
- [ ] Alpaca paper trading only (not live money)
- [ ] Max 10 simultaneous positions
- [ ] No short selling
- [ ] Position limits: $50K max per trade
- [ ] Document any other constraints

### 8c. Rollback Plan (if needed)
- [ ] Keep recent DB backup
- [ ] Can revert to `--dry-run` mode instantly
- [ ] Can halt execution with `halt` flag
- [ ] Can close all positions via `force_exit_all` command
- [ ] Process: Document incident → Review logs → Fix → Test → Resume

### 8d. Post-Market Monitoring
- [ ] Check cloud metrics hourly during market hours
- [ ] Monitor email/Slack for alerts
- [ ] Check position P&L mid-day
- [ ] Verify exit logic triggers correctly
- [ ] Log any anomalies for review

---

## SUMMARY

**Time Budget Remaining:** ~5 hours (plenty of buffer)

**Critical Path:**
1. ✅ Rotate Alpaca credentials (20 min)
2. ✅ Commit code changes (10 min)
3. ✅ Load today's data (30 min)
4. ✅ Verify data freshness (15 min)
5. ✅ Run dry-run test (20 min)
6. ✅ Review orchestrator logs (10 min)
7. ✅ First live execution (30 min)
8. ✅ Verify trades in Alpaca (10 min)
9. ✅ Risk management final check (10 min)
10. ✅ GO/NO-GO decision (10 min)

**Total: ~2.5 hours, leaving 2.5-hour safety buffer before market open**

---

## Next Action
👉 **START: Rotate Alpaca API keys now**

Once new keys are in GitHub Secrets + AWS Secrets Manager, the full automation pipeline can begin.
