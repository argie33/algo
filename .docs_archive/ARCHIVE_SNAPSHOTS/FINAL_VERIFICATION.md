# FINAL COMPREHENSIVE VERIFICATION

**Purpose**: Line-by-line check of plan vs delivery  
**Scope**: All 10 phases + integration + testing  
**Approach**: Not "does this exist" but "does this WORK"  

---

## PHASE 1: CRITICAL WIRING GAPS

### 1.1 Wire PositionSizer into live path
**Plan**: Replace inline sizing in FilterPipeline._tier5_portfolio_health() with PositionSizer call
**Delivery Check**:
- [ ] algo_filter_pipeline.py line 603: `sizer = PositionSizer(self.config)`
- [ ] algo_filter_pipeline.py line 605: `result = sizer.calculate_position_size(...)`
- [ ] PositionSizer receives entry_price, stop_loss_price, symbol
- [ ] PositionSizer returns shares to buy (actual integer, not float)
- [ ] Returned shares respect caps (max_position_size_pct, max_positions, drawdown cascade)

**ISSUE CHECK**: Does position sizer actually cap positions?
**TEST NEEDED**: Verify position size with drawdown_pct=50% produces half-size shares

### 1.2 Apply exposure tier risk_multiplier
**Plan**: Store risk_multiplier from phase_3b_exposure_policy(), pass to PositionSizer
**Delivery Check**:
- [ ] orchestrator.py phase_3b_exposure_policy() extracts `risk_multiplier` from constraints
- [ ] risk_multiplier stored as `self._exposure_risk_multiplier`
- [ ] FilterPipeline receives `exposure_risk_multiplier` parameter
- [ ] PositionSizer receives and applies exposure_risk_multiplier
- [ ] Position size = base_size × drawdown_mult × exposure_mult (verified formula)

**ISSUE CHECK**: Is exposure_risk_multiplier actually used in sizing math?
**TEST NEEDED**: Verify PRESSURE tier (0.5 mult) produces 50% smaller positions

### 1.3 Apply vix_caution_threshold risk reduction
**Plan**: When VIX > 25.0, reduce position size by 0.75x before hard halt at 35
**Delivery Check**:
- [ ] algo_circuit_breaker.py checks VIX level
- [ ] If VIX > vix_caution_threshold (25.0), sets exposure_risk_multiplier = 0.75
- [ ] This multiplier is passed to position sizer
- [ ] Hard halt still at vix_max_threshold (35.0)

**ISSUE CHECK**: Where is vix_caution_threshold actually read and applied?
**TEST NEEDED**: Trace code path: VIX read → caution check → sizer call

### 1.4 Add 18 missing config keys to DEFAULTS
**Plan**: Add exit_on_rs_line_break, switch_to_21ema, max_positions_per_sector, etc. to algo_config.py DEFAULTS
**Delivery Check**:
- [ ] All 18 keys present in algo_config.py
- [ ] Each key has correct type: ('value', 'type', 'description')
- [ ] Keys are used by their respective modules
- [ ] Example: exit_on_rs_line_break used by algo_exit_engine.py

**ISSUE CHECK**: Are all 18 keys actually used, or are some dead config?
**TEST NEEDED**: Grep each key in the modules that claim to use them

### 1.5 Validate stop_loss_price < entry_price at entry
**Plan**: Before order execution, reject if stop >= entry * 0.99
**Delivery Check**:
- [ ] algo_trade_executor.py line 161: `if stop_loss_price >= entry_price * 0.99`
- [ ] Returns `{'success': False, 'status': 'bad_stop'}`
- [ ] Alert sent with CRITICAL severity
- [ ] No position created

**ISSUE CHECK**: Does this check actually fire? Is alert sent?
**TEST NEEDED**: Mock bad stop, verify rejection

### 1.6 Handle Alpaca success + DB failure
**Plan**: If Alpaca fills but DB INSERT fails, cancel the Alpaca order
**Delivery Check**:
- [ ] algo_trade_executor.py exception handler catches DB failure after Alpaca success
- [ ] Calls `self._cancel_alpaca_order(alpaca_order_id)`
- [ ] Logs CRITICAL: "DB write failed after Alpaca fill — order cancelled"
- [ ] Database rollback happens
- [ ] No orphaned position created

**ISSUE CHECK**: Does cancel actually work? What if cancel fails?
**TEST NEEDED**: Mock both Alpaca fill + DB failure, verify order cancelled

### 1.7 Recalculate R and stop on actual fill price
**Plan**: After fill, recompute R using executed_price not signal price
**Delivery Check**:
- [ ] algo_trade_executor.py line 317: `actual_risk_per_share = executed_price - stop_loss_price`
- [ ] Stop loss NOT adjusted (same as planned)
- [ ] R-multiple arithmetic uses actual_risk_per_share
- [ ] executed_price stored as entry in algo_positions

**ISSUE CHECK**: Is R actually recomputed, or is this just logged?
**TEST NEEDED**: Verify algo_positions.entry_price = executed_price (not signal)

### 1.8 Fix duplicate Lambda trigger
**Plan**: Remove AlgoOrchestratorScheduleRule from template-loader-tasks.yml
**Delivery Check**:
- [ ] template-loader-tasks.yml does NOT have AlgoOrchestratorScheduleRule
- [ ] template-algo.yml has single EventBridge rule at 17:30 ET
- [ ] No double-execution risk

**ISSUE CHECK**: Were old deployment templates cleaned up?
**TEST NEEDED**: Grep for duplicate trigger patterns

### 1.9 Unify alerting — wire SNS
**Plan**: Add _publish_sns() to notifications.py, call for critical/error events
**Delivery Check**:
- [ ] algo_notifications.py has _publish_sns() function
- [ ] Reads ALERT_SNS_TOPIC_ARN from environment
- [ ] Called from notify() for severities 'critical' and 'error'
- [ ] SNS is actually publishing (not just mocked)

**ISSUE CHECK**: Does SNS integration actually work? Is topic ARN set?
**TEST NEEDED**: Check if ALERT_SNS_TOPIC_ARN environment variable exists

### 1.10 Add DLQ alarm and missed-execution detection
**Plan**: Two alarms in template-algo.yml: DLQDepthAlarm and AlgoNotRunningAlarm
**Delivery Check**:
- [ ] template-algo.yml has DLQDepthAlarm
- [ ] template-algo.yml has AlgoNotRunningAlarm
- [ ] DLQ threshold >= 1 message
- [ ] AlgoNotRunningAlarm checks for AlgoRunCompleted metric
- [ ] Both alarms send to SNS topic

**ISSUE CHECK**: Are alarms actually defined? Will they fire?
**TEST NEEDED**: CloudFormation validation on template

### 1.11 Audit-log skip-freshness bypass
**Plan**: Call self.log_phase_result(1, 'freshness_bypassed', ...) when --skip-freshness used
**Delivery Check**:
- [ ] algo_orchestrator.py lines 995-996: logs freshness_bypassed
- [ ] Log includes "--skip-freshness flag used" message
- [ ] This is in phase_1_data_freshness, in the bypass path

**ISSUE CHECK**: Is this actually called?
**TEST NEEDED**: Run with --skip-freshness, verify audit log entry

---

## PHASE 2: TEST SUITE

### 2.1 pytest Infrastructure
**Plan**: conftest.py with DB fixtures, Alpaca mocks
**Delivery Check**:
- [ ] tests/conftest.py exists
- [ ] conftest.py defines fixtures for: db_connection, alpaca_mock, config
- [ ] Fixtures are actually used in test files
- [ ] tests/fixtures/alpaca_mocks.py exists with mock factory

**ISSUE CHECK**: Can tests actually run?
**TEST NEEDED**: `pytest tests/unit/ -v` (if pytest installed)

### 2.2-2.5 Edge Cases & Backtest Regression
**Plan**: Test files for partial fills, order failures, orphans, backtest regression
**Delivery Check**:
- [ ] tests/edge_cases/test_partial_fills.py exists and has assertions
- [ ] tests/edge_cases/test_order_failures.py exists
- [ ] tests/edge_cases/test_orphaned_positions.py exists
- [ ] tests/backtest/test_backtest_regression.py exists
- [ ] tests/backtest/reference_metrics.json exists with baseline metrics

**ISSUE CHECK**: Are tests complete or just skeletons?
**TEST NEEDED**: Verify at least 3 assertions per test file

---

## PHASE 3: TCA

### 3.1 TCAEngine class
**Plan**: record_fill(), daily_report(), monthly_summary(), alert_if_excessive()
**Delivery Check**:
- [ ] algo_tca.py has TCAEngine class
- [ ] record_fill(trade_id, symbol, signal_price, fill_price, shares, side) implemented
- [ ] daily_report() computes avg slippage, worst fills, % fills > 50bps
- [ ] monthly_summary() aggregates monthly metrics
- [ ] alert_if_excessive() sends WARN at 100bps, ERROR at 300bps

**ISSUE CHECK**: Does record_fill actually INSERT to database?
**TEST NEEDED**: Trace code: does it call INSERT or just compute?

### 3.2 Wire TCA into TradeExecutor
**Plan**: After position created, call tca.record_fill()
**Delivery Check**:
- [ ] algo_trade_executor.py line 50-51: `from algo_tca import TCAEngine`
- [ ] algo_trade_executor.py `__init__`: `self.tca = TCAEngine(config)`
- [ ] algo_trade_executor.py line 456: `tca_result = self.tca.record_fill(...)`
- [ ] TCA record happens AFTER position creation but BEFORE return

**ISSUE CHECK**: What data is passed to record_fill? Is it correct?
**TEST NEEDED**: Verify all parameters match signature

### 3.3 Database table
**Plan**: algo_tca table with slippage_bps, execution_latency_ms, fill_rate_pct
**Delivery Check**:
- [ ] init_database.py has CREATE TABLE algo_tca
- [ ] Table has all fields: trade_id, symbol, signal_price, fill_price, slippage_bps, execution_latency_ms, fill_rate_pct, side
- [ ] Indexes exist: idx_algo_tca_trade_id, idx_algo_tca_symbol, idx_algo_tca_signal_date

**ISSUE CHECK**: Can table be created without errors?
**TEST NEEDED**: Run init_database.py --create-table algo_tca

---

## PHASE 4: LIVE PERFORMANCE

### 4.1 LivePerformance class
**Plan**: rolling_sharpe(252), win_rate(50), expectancy(), max_drawdown(), backtest_vs_live_comparison()
**Delivery Check**:
- [ ] algo_performance.py has LivePerformance class
- [ ] rolling_sharpe() reads algo_portfolio_snapshots, computes daily returns, annualizes
- [ ] win_rate() reads closed algo_trades, computes win% and avg R-multiple
- [ ] expectancy() = (win_rate × avg_win_R) - (loss_rate × avg_loss_R)
- [ ] max_drawdown() computes from portfolio snapshots
- [ ] All methods return None if insufficient data (< 30 days)

**ISSUE CHECK**: Is Sharpe actually annualized?
**TEST NEEDED**: Verify formula: daily_sharpe × sqrt(252)

### 4.2 Database table
**Plan**: algo_performance_daily with rolling_sharpe_252d, win_rate_50t, expectancy, max_drawdown_pct
**Delivery Check**:
- [ ] init_database.py has CREATE TABLE algo_performance_daily
- [ ] All required columns present
- [ ] Table is created in schema

**ISSUE CHECK**: Can table be created?
**TEST NEEDED**: Run init_database.py --create-table algo_performance_daily

### 4.3 Wire into orchestrator Phase 7
**Plan**: After reconciliation, call LivePerformance.generate_daily_report()
**Delivery Check**:
- [ ] orchestrator.py Phase 7 (lines ~915): imports LivePerformance
- [ ] Calls `perf = LivePerformance(self.config)`
- [ ] Calls `perf_report = perf.generate_daily_report(self.run_date)`
- [ ] Logs result to audit trail

**ISSUE CHECK**: Does this actually get called?
**TEST NEEDED**: Run orchestrator --dry-run, check Phase 7 output

---

## PHASE 5: PRE-TRADE CHECKS

### 5.1 PreTradeChecks class
**Plan**: 5 checks — fat-finger, velocity, notional cap, symbol tradeable, duplicate
**Delivery Check**:
- [ ] check_fat_finger(): entry_price within 5% of market price
- [ ] check_order_velocity(): max 3 orders per 60 seconds
- [ ] check_notional_hard_cap(): single order ≤ 15% portfolio
- [ ] check_symbol_tradeable(): checks Alpaca asset status, rejects halted/delisted
- [ ] check_duplicate_order_hard(): same symbol+side within 5 min blocks order
- [ ] run_all(): executes checks in sequence, returns (passed, reason)

**ISSUE CHECK**: Does fat-finger check actually call market price API?
**TEST NEEDED**: Verify check_fat_finger calls Alpaca

### 5.2 Wire into TradeExecutor
**Plan**: Call pretrade.run_all() before Alpaca order
**Delivery Check**:
- [ ] algo_trade_executor.py line 54-55: imports PreTradeChecks, instantiates
- [ ] algo_trade_executor.py line 140-151: calls `pretrade.run_all(...)`
- [ ] If pretrade fails, returns before Alpaca order placed
- [ ] Failed reason is logged and alert sent

**ISSUE CHECK**: What happens if pretrade fails? Is order actually blocked?
**TEST NEEDED**: Mock pretrade failure, verify order not sent to Alpaca

---

## PHASE 6: MARKET EVENTS

### 6.1 MarketEventHandler class
**Plan**: Detect halts, circuit breakers, delistings, early close
**Delivery Check**:
- [ ] check_single_stock_halt(symbol): queries Alpaca, detects status != ACTIVE
- [ ] check_market_circuit_breaker(): detects L1 (7%), L2 (13%), L3 (20%) declines
- [ ] check_early_close(): detects market close at 13:00 ET vs 16:00 ET
- [ ] check_delisting(symbol): detects delisted symbols
- [ ] handle_halt(), handle_cb(), handle_delisting(): appropriate actions

**ISSUE CHECK**: Are these checks actually connected to real data?
**TEST NEEDED**: Verify data sources (Alpaca API, market_health_daily table)

### 6.2 Wire into orchestrator
**Plan**: Phase 2 circuit breaker check + Phase 3 halt check
**Delivery Check**:
- [ ] orchestrator.py Phase 2: calls `meh.check_market_circuit_breaker()`
- [ ] orchestrator.py Phase 3: calls `meh.check_single_stock_halt()` for each position
- [ ] CB triggers halt at L1/L2/L3
- [ ] Halt triggers order cancellation

**ISSUE CHECK**: Are these wired correctly?
**TEST NEEDED**: Run orchestrator --dry-run, check Phase 2/3 output

---

## PHASE 7: WFO & PAPER GATES

### 7.1 WalkForwardOptimizer
**Plan**: walk_forward_backtest(), crisis_stress_test(), WFE calculation
**Delivery Check**:
- [ ] algo_wfo.py has WalkForwardOptimizer class
- [ ] walk_forward_backtest(): creates rolling windows (3yr train, 1yr test by default)
- [ ] Optimizes parameters on each train window
- [ ] Applies to OOS window
- [ ] Computes WFE = avg(OOS Sharpe) / avg(IS Sharpe)

**ISSUE CHECK**: Is WFE actually computed?
**TEST NEEDED**: Verify WFE formula in code

### 7.2 Crisis stress testing
**Plan**: Test on 2008, 2020, 2022 crisis periods
**Delivery Check**:
- [ ] crisis_stress_test(): tests on 4 periods
- [ ] Computes max_drawdown, Calmar, recovery time for each
- [ ] Returns comparative metrics

**ISSUE CHECK**: Are crisis dates hardcoded or parameterized?
**TEST NEEDED**: Verify date ranges in code

### 7.3 Paper mode gates
**Plan**: 7 formal acceptance criteria, all must pass
**Delivery Check**:
- [ ] PaperModeGates class has validate_paper_vs_backtest()
- [ ] Checks: Sharpe >= 70%, win_rate ±15%, max_dd <= 1.5×, fill_rate >= 95%, slippage <= 2×, zero CRITICAL, no orphans
- [ ] All gates must pass for production_readiness_checklist() to return READY

**ISSUE CHECK**: Are all 7 gates implemented?
**TEST NEEDED**: Count assertions in production_readiness_checklist()

---

## PHASE 8: VaR/CVaR

### 8.1 PortfolioRisk class
**Plan**: historical_var(), cvar(), stressed_var(), beta_exposure(), concentration_report()
**Delivery Check**:
- [ ] historical_var(0.95, 252): VaR from portfolio snapshots
- [ ] cvar(): Expected Shortfall, mean loss beyond VaR
- [ ] stressed_var(0.99): VaR from worst 12-month window
- [ ] beta_exposure(): portfolio beta vs SPY
- [ ] concentration_report(): top holdings %, sector breakdown

**ISSUE CHECK**: Do these actually query the right tables?
**TEST NEEDED**: Verify table names: algo_portfolio_snapshots, algo_trades

### 8.2 Database table & daily report
**Plan**: algo_risk_daily table, generate_daily_risk_report() writes to it
**Delivery Check**:
- [ ] algo_risk_daily table exists in schema
- [ ] generate_daily_risk_report() computes all metrics
- [ ] Inserts into algo_risk_daily
- [ ] Alerts when VaR > 2%, concentration > 30%, beta > 2.0

**ISSUE CHECK**: Are alerts actually triggered?
**TEST NEEDED**: Mock bad risk metrics, verify alerts

### 8.3 Wire into orchestrator Phase 7
**Plan**: After performance metrics, call PortfolioRisk.generate_daily_risk_report()
**Delivery Check**:
- [ ] orchestrator.py Phase 7: imports PortfolioRisk
- [ ] Calls `risk = PortfolioRisk(self.config)`
- [ ] Calls `risk_report = risk.generate_daily_risk_report()`
- [ ] Logs result

**ISSUE CHECK**: Is this wired?
**TEST NEEDED**: Run orchestrator --dry-run, check Phase 7 for risk metrics

---

## PHASE 9: MODEL GOVERNANCE

### 9.1 ModelGovernance class
**Plan**: register_model(), audit_config_change(), champion_challenger_test(), information_coefficient()
**Delivery Check**:
- [ ] register_model(): inserts into algo_model_registry with git commit, params, backtest metrics
- [ ] audit_config_change(): inserts every param change into algo_config_audit
- [ ] run_champion_challenger_test(): A/B test with Welch's t-test, inserts results
- [ ] compute_information_coefficient(): Pearson/Spearman IC, detects alpha decay

**ISSUE CHECK**: Are all 4 methods implemented?
**TEST NEEDED**: Count methods in ModelGovernance class

### 9.2-9.4 Database tables
**Plan**: 4 tables — algo_model_registry, algo_config_audit, algo_champion_challenger, algo_information_coefficient
**Delivery Check**:
- [ ] All 4 tables defined in init_database.py
- [ ] All required columns present
- [ ] Foreign keys correct (champion_challenger refs model_registry)

**ISSUE CHECK**: Are FK relationships correct?
**TEST NEEDED**: Check for FK constraints in schema

---

## PHASE 10: RUNBOOKS

### 10.1 TRADING_RUNBOOK.md
**Plan**: 477+ lines covering dailychecklist, halt protocols, error escalation, kill switch
**Delivery Check**:
- [ ] Section 1: Daily pre-market (T-60 min checklist)
- [ ] Section 2: Trading day procedures
- [ ] Section 3: Halt protocols (single-stock, CB L1/L2/L3)
- [ ] Section 4: Error escalation matrix (Level 1/2/3)
- [ ] Section 5: Position reconciliation
- [ ] Section 6: Manual intervention
- [ ] Section 7: After-market procedures
- [ ] Section 8: Kill switch activation with verbal authorization
- [ ] Appendix: On-call escalation chain

**ISSUE CHECK**: Are all 8 sections complete?
**TEST NEEDED**: Verify line count and completeness

### 10.2 ANNUAL_MODEL_REVIEW.md
**Plan**: 464+ lines covering performance, alpha decay, governance, sign-offs
**Delivery Check**:
- [ ] Section 1: Strategy performance review
- [ ] Section 2: Alpha decay assessment (IC trending)
- [ ] Section 3: Parameter sensitivity
- [ ] Section 4: Operational risk
- [ ] Section 5: Model robustness (WFE, stress tests)
- [ ] Section 6: Regulatory compliance (SEC Rule 15c3-5)
- [ ] Section 7: Model governance
- [ ] Section 8: Risk limits
- [ ] Section 9: Sign-off sheet with 4 approvers

**ISSUE CHECK**: Are all 9 sections complete?
**TEST NEEDED**: Verify sign-off template exists

---

## INTEGRATION VERIFICATION

### End-to-End Data Flow
**Plan**: Signal → PreTrade → Order → TCA → Position → Exit → Performance → Governance
**Delivery Check**:
- [ ] Each step calls the next step
- [ ] Data flows correctly (trade_id, symbol, price, shares)
- [ ] No orphan data (all trades have positions)
- [ ] No circular dependencies

**TEST NEEDED**: Trace full execution path in code

### Error Handling
**Plan**: Each phase handles exceptions gracefully
**Delivery Check**:
- [ ] No unhandled exceptions in critical path
- [ ] Exceptions logged with context
- [ ] Orchestrator continues on non-blocking failures

**TEST NEEDED**: Count exception handlers in each phase

### Database Consistency
**Plan**: All tables have proper relationships and constraints
**Delivery Check**:
- [ ] All FKs defined
- [ ] All indexes created
- [ ] No orphaned data possible
- [ ] Triggers auto-cleanup stale data (if any)

**TEST NEEDED**: Schema validation

---

## WHAT WE NEED TO VERIFY RIGHT NOW

Stop planning. Actually test these:

1. **Can orchestrator run end-to-end?** → `python algo_orchestrator.py --dry-run`
2. **Do all modules import without errors?** → `python -c "import algo_tca, algo_performance, ..."`
3. **Can database schema be initialized?** → `python init_database.py`
4. **Do all 7 new tables exist in schema?** → `psql ... \d algo_tca` etc.
5. **Are all Phase 1 wiring actually called?** → grep + trace execution
6. **Are PreTradeChecks blocking bad orders?** → unit test
7. **Are TCA records being written to DB?** → query algo_tca after execution
8. **Do performance metrics compute?** → run LivePerformance.rolling_sharpe()

---

## STATUS

CURRENT: All code written, modules compile, basic tests pass  
NEEDED: Systematic verification of each requirement  
GOAL: No more "we missed X" discoveries  

Start with the tests above. Report what fails.
