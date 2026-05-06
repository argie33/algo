# Annual Model Review Checklist

**Based on:** SEC Rule 15c3-5 (Regulation SHO), SR 11-7, CFA Risk Management Standards  
**Requirement:** Complete annually (or after major code changes)  
**Next Review Date:** 2027-05-06  
**Reviewed By:** [Trading Committee Sign-Off Required]

---

## Executive Summary

This checklist ensures the algo trading system remains compliant with regulatory standards and performs according to specifications. Review must be completed before year-end and signed off by trading committee.

---

## 1. Strategy Performance Review

### 1.1 Live Performance vs. Backtest

**Metric:** Rolling Sharpe Ratio (252-day annualized)
- [ ] Query: `SELECT rolling_sharpe_252d FROM algo_performance_daily ORDER BY report_date DESC LIMIT 30`
- [ ] Backtest Sharpe: _____ (from reference_metrics.json)
- [ ] Current Live Sharpe: _____
- [ ] Ratio (Live/Backtest): _____
- [ ] **Pass Criteria:** Live >= 70% of backtest
  - [ ] PASS  /  [ ] FAIL

**Metric:** Win Rate (50-trade rolling)
- [ ] Backtest Win Rate: ____%
- [ ] Current Live Win Rate: ____%
- [ ] Difference: ____%
- [ ] **Pass Criteria:** Within ±15% of backtest
  - [ ] PASS  /  [ ] FAIL

**Metric:** Maximum Drawdown
- [ ] Backtest Max DD: ____%
- [ ] Current Live Max DD: ____%
- [ ] Ratio (Live/Backtest): _____
- [ ] **Pass Criteria:** Live <= 1.5× backtest
  - [ ] PASS  /  [ ] FAIL

**Metric:** Expectancy (E = (WR × Avg Win R) - (LR × Avg Loss R))
- [ ] Backtest Expectancy: _____ R
- [ ] Current Live Expectancy: _____ R
- [ ] **Assessment:** ________________

**Summary:**
- [ ] Live performance in line with backtest expectations
- [ ] No unexplained performance degradation
- [ ] Alpha is stable or improving

### 1.2 Forward Returns Analysis

**Metric:** 30-Day Forward Returns (Walk-Forward Efficiency)
- [ ] Query: `SELECT return_pct FROM algo_performance_daily WHERE report_date >= CURRENT_DATE - INTERVAL '30 days'`
- [ ] Average return: ____%
- [ ] Volatility (std dev): ____%
- [ ] Sharpe: _____
- [ ] **Assessment:** Returns in line with medium-term expectations? YES / NO

**Metric:** Year-to-Date vs. Same Period Last Year
- [ ] YTD Return: ____%
- [ ] Prior Year YTD: ____%
- [ ] Difference: ____% (better/worse)
- [ ] **Assessment:** Trend is positive / neutral / negative

### 1.3 Tail Risk Assessment

**Metric:** Worst 10 Single-Day Returns
- [ ] Query: `SELECT PERCENTILE_CONT(0.1) WITHIN GROUP (ORDER BY daily_return) FROM portfolio_daily_returns`
- [ ] 10th percentile return (worst 10%): ____%
- [ ] **Assessment:** Consistent with backtest assumptions? YES / NO

**Metric:** Value at Risk (VaR 95%)
- [ ] Query: `SELECT var_pct_95 FROM algo_risk_daily WHERE report_date >= CURRENT_DATE - INTERVAL '30 days' ORDER BY report_date DESC LIMIT 1`
- [ ] Current VaR 95%: ____%
- [ ] **Pass Criteria:** <= 2% of portfolio daily
  - [ ] PASS  /  [ ] FAIL

**Metric:** Conditional VaR (Expected Shortfall)
- [ ] Query: `SELECT cvar_pct_95 FROM algo_risk_daily ...`
- [ ] Current CVaR 95%: ____%
- [ ] **Assessment:** Tail risk under control? YES / NO

---

## 2. Alpha Decay Assessment

### 2.1 Information Coefficient (IC) Trend

**Current IC Metrics:**
- [ ] Query: `SELECT ic_pearson, ic_spearman FROM algo_information_coefficient ORDER BY ic_date DESC LIMIT 1`
- [ ] Pearson IC (current): _____
- [ ] Spearman IC (current): _____
- [ ] 90-day trend (improving/stable/declining): _____________

**IC Interpretation:**
- IC > 0.05: Meaningful (alpha present)
- IC 0.02-0.05: Weak (alpha degrading)
- IC < 0.02: Minimal (alpha nearly exhausted)
- IC < 0: Degraded (signal broken)

**Current Status:** [ ] Meaningful  [ ] Weak  [ ] Minimal  [ ] Degraded

**Assessment:** Signal quality is ________________

### 2.2 Historical IC (12-Month Trend)

- [ ] Average IC (past 12 months): _____
- [ ] IC 12 months ago: _____
- [ ] Change: _____ (declining by X%)
- [ ] **Trend:** Improving / Stable / Declining / Degrading
- [ ] **Alert if:** IC declined > 30% in past year, or now < 0.03

**Action Items:**
- [ ] If declining: investigate signal degradation, retrain model
- [ ] If stable: no action, monitor quarterly
- [ ] If minimal/degraded: escalate to strategy review committee

### 2.3 Signal Quality Deep Dive

**Component: Swing Score**
- [ ] Historical predictive value (correlation to 5-day forward return): _____
- [ ] Current predictive value: _____
- [ ] Degradation: _____% (if any)
- [ ] Status: [ ] STRONG  [ ] OK  [ ] WEAK  [ ] BROKEN

**Component: Relative Strength**
- [ ] Win rate on high RS signals: ____%
- [ ] Win rate on low RS signals: ____%
- [ ] Difference (should be > 5% for meaningful signal): ____%
- [ ] Status: [ ] PREDICTIVE  [ ] WEAK  [ ] NOT PREDICTIVE

**Component: Market Stage**
- [ ] Win rate in Stage 2 (uptrend): ____%
- [ ] Win rate in Stage 1/3 (sideways/downtrend): ____%
- [ ] Difference (should be > 10%): ____%
- [ ] Status: [ ] PREDICTIVE  [ ] WEAK  [ ] NOT PREDICTIVE

---

## 3. Parameter Sensitivity Analysis

### 3.1 Risk-Critical Parameters

**Parameter: Drawdown Risk Reduction Cascade**
- [ ] Config values: -5% → 0.75×, -10% → 0.5×, -15% → 0.25×, -20% → 0.0×
- [ ] Tested in past year: YES / NO
- [ ] Effectiveness: Does cascade prevent > 20% DD? _____
- [ ] Status: [ ] EFFECTIVE  [ ] NEEDS TUNING

**Parameter: VIX Caution Threshold**
- [ ] Current config: VIX > 25 triggers 0.75× multiplier
- [ ] Effectiveness: Does multiplier reduce losses in 25-35 VIX range? _____
- [ ] Historical data: % of trades in caution zone: ____%
- [ ] Status: [ ] EFFECTIVE  [ ] INEFFECTIVE

**Parameter: Position Limits**
- [ ] Max concurrent positions: _____
- [ ] Max per-sector concentration: ____%
- [ ] Max notional per trade: ____%
- [ ] Breaches in past year: _____
- [ ] Status: [ ] APPROPRIATE  [ ] TOO LOOSE  [ ] TOO TIGHT

### 3.2 Entry-Exit Parameters

**Parameter: Entry Stop Distance (% from entry)**
- [ ] Current config: ____%
- [ ] Average actual stop distance in closed trades: ____%
- [ ] Comparison: Expected ____%, Actual ____%, Variance ____%
- [ ] Effectiveness: Does stop distance correlate to trade outcomes? _____
- [ ] Status: [ ] APPROPRIATE  [ ] NEEDS ADJUSTMENT

**Parameter: Exit Targets (R-multiples)**
- [ ] Target 1: _____ R
- [ ] Target 2: _____ R
- [ ] Target 3: _____ R
- [ ] Actual avg win R (when targets hit): _____ R
- [ ] Actual avg loss R (when stopped out): _____ R
- [ ] Are targets realistic? YES / NO

**Parameter: Trailing Stop ATR Multiplier**
- [ ] Current config: _____ × ATR
- [ ] Effectiveness: % of positions where trailing stop raises: ____%
- [ ] Impact on profitability: Improves / Neutral / Worsens
- [ ] Status: [ ] EFFECTIVE  [ ] NEEDS TUNING

---

## 4. Operational Risk Assessment

### 4.1 Data Quality

**Data Freshness:**
- [ ] Last 365 days: % of days with complete price data: ____%
- [ ] Missing days or symbols: _____
- [ ] Data patrol critical findings (past year): _____
- [ ] Status: [ ] ACCEPTABLE  [ ] NEEDS INVESTIGATION

**Data Accuracy:**
- [ ] Reconciliation errors (actual vs. loaded): _____
- [ ] Large price gaps (> 10% unexplained): _____
- [ ] Status: [ ] ACCURATE  [ ] DISCREPANCIES FOUND

### 4.2 Execution Quality (TCA)

**Slippage:**
- [ ] Average slippage (past 90 days): _____ bps
- [ ] Median slippage: _____ bps
- [ ] 95th percentile (worst 5%): _____ bps
- [ ] Fills exceeding 100 bps: ____%
- [ ] Status: [ ] WITHIN EXPECTATION  [ ] DEGRADED

**Fill Rate:**
- [ ] % of orders fully filled: ____%
- [ ] % of orders partially filled: ____%
- [ ] % of orders rejected/cancelled: ____%
- [ ] Status: [ ] ACCEPTABLE (> 95% filled)  [ ] NEEDS IMPROVEMENT

**Execution Latency:**
- [ ] Average order send → fill time: _____ ms
- [ ] 95th percentile latency: _____ ms
- [ ] Status: [ ] ACCEPTABLE (< 1 second)  [ ] NEEDS INVESTIGATION

### 4.3 Risk Controls

**Circuit Breakers (8 total):**
- [ ] Drawdown >= 20%: ____ tested/year, ____ triggered
- [ ] Daily loss >= 2%: ____ tested/year, ____ triggered
- [ ] Consecutive losses >= 3: ____ tested/year, ____ triggered
- [ ] Open risk >= 4% portfolio: ____ tested/year, ____ triggered
- [ ] VIX > 35: ____ tested/year, ____ triggered
- [ ] Market stage 4 (downtrend): ____ tested/year, ____ triggered
- [ ] Weekly loss >= 5%: ____ tested/year, ____ triggered
- [ ] Data staleness > 3 days: ____ tested/year, ____ triggered

**Assessment:**
- [ ] All circuit breakers functioning correctly
- [ ] Circuit breaker thresholds appropriate for AUM
- [ ] No false positives blocking legitimate trading

---

## 5. Model Robustness

### 5.1 Walk-Forward Efficiency (WFE)

**Test Parameters:**
- [ ] In-sample window: _____ years
- [ ] Out-of-sample window: _____ years
- [ ] Windows tested: _____
- [ ] Average WFE: _____

**WFE Interpretation:**
- WFE > 0.8: Excellent (minimal overfitting)
- WFE 0.5-0.8: Acceptable (normal overfitting)
- WFE 0.3-0.5: Concerning (significant overfitting)
- WFE < 0.3: Failed (likely curve-fit)

**Status:** [ ] EXCELLENT  [ ] ACCEPTABLE  [ ] CONCERNING  [ ] FAILED

**Action if CONCERNING/FAILED:**
- [ ] Investigate overfitting in parameter optimization
- [ ] Re-train with expanded data
- [ ] Consider parameter relaxation or new approach

### 5.2 Stress Testing (Historical Crisis Periods)

**Test: 2008-09 GFC (Sep 2008 - Mar 2009; -58% S&P)**
- [ ] Max drawdown during period: ____%
- [ ] Sharpe ratio: _____
- [ ] Status: [ ] ACCEPTABLE (DD < 40%)  [ ] SEVERE (DD > 40%)

**Test: 2020 COVID (Feb-Apr 2020; -34% S&P)**
- [ ] Max drawdown during period: ____%
- [ ] Sharpe ratio: _____
- [ ] Status: [ ] ACCEPTABLE  [ ] SEVERE

**Test: 2022 Rate Shock (Jan-Dec 2022; -19% S&P, high volatility)**
- [ ] Max drawdown during period: ____%
- [ ] Sharpe ratio: _____
- [ ] Status: [ ] ACCEPTABLE  [ ] SEVERE

**Test: 2000-02 Dot-Com (Jan 2000 - Dec 2002; NASDAQ -78%)**
- [ ] Max drawdown during period: ____%
- [ ] Sharpe ratio: _____
- [ ] Status: [ ] ACCEPTABLE  [ ] SEVERE

**Overall Stress Assessment:** [ ] PASSES STRESS TESTS  [ ] NEEDS REVIEW

---

## 6. Regulatory & Compliance Review

### 6.1 SEC Rule 15c3-5 Compliance

**Pre-Trade Risk Controls:**
- [ ] Fat-finger check (>5% divergence from market): IMPLEMENTED
- [ ] Order velocity limit (max 3/60s): IMPLEMENTED
- [ ] Position size hard cap (15% portfolio max): IMPLEMENTED
- [ ] Symbol tradeable check (not halted/delisted): IMPLEMENTED
- [ ] Duplicate prevention (same symbol/side within 5 min): IMPLEMENTED

**Post-Trade Risk Controls:**
- [ ] Orphaned order prevention (cancel if DB fails): IMPLEMENTED
- [ ] Position reconciliation (daily, Alpaca vs. DB): IMPLEMENTED
- [ ] Mark-to-market enforcement (current prices): IMPLEMENTED

**Assessment:** [ ] COMPLIANT  [ ] GAPS IDENTIFIED

### 6.2 Market Abuse Prevention

**Order Cancellation Rate:**
- [ ] % of orders cancelled: ____%
- [ ] Acceptable threshold: < 5%
- [ ] Status: [ ] ACCEPTABLE  [ ] INVESTIGATE

**Wash Trading Prevention:**
- [ ] Same entry/exit on same day for same symbol: _____instances
- [ ] Pattern detected? YES / NO
- [ ] Status: [ ] NO PATTERN  [ ] NEEDS REVIEW

---

## 7. Model Governance

### 7.1 Version Control

**Current Deployed Model:**
- [ ] Git commit: _____
- [ ] Deployment date: _____
- [ ] Deployed by: _____
- [ ] Status: [ ] ACTIVE  [ ] RETIRED  [ ] CHALLENGER

**Model Registry:**
- [ ] Total models deployed (all-time): _____
- [ ] Currently active models: _____
- [ ] Parameter change audit log entries: _____
- [ ] Status: [ ] COMPLETE  [ ] GAPS FOUND

### 7.2 Parameter Change Audit

**Major Changes (Past 12 Months):**
- [ ] Risk reduction cascade values changed? NO / YES → Reason: _____
- [ ] Entry/exit targets changed? NO / YES → Reason: _____
- [ ] Position limits changed? NO / YES → Reason: _____
- [ ] Circuit breaker thresholds changed? NO / YES → Reason: _____

**Change Documentation:**
- [ ] All changes logged in algo_config_audit table
- [ ] Rationale documented for each change
- [ ] Impact on performance analyzed
- [ ] Status: [ ] WELL DOCUMENTED  [ ] GAPS FOUND

### 7.3 A/B Testing (Champion/Challenger)

**Challenger Tests Run (Past 12 Months):** _____

**Most Recent Test:**
- [ ] Dates: _____ to _____
- [ ] Champion vs. Challenger: Champion _____ vs. Challenger _____
- [ ] Winner: _____
- [ ] Statistical significance: p-value = _____
- [ ] Recommendation: [ ] Promote Challenger  [ ] Keep Champion

**Assessment:** [ ] RIGOROUS  [ ] NEEDS MORE TESTING

---

## 8. Risk Limit Appropriateness

### 8.1 Current AUM and Risk Scaling

**Current AUM:** $_______
**Risk Per Trade (% of portfolio):** _____%
**Max Total Open Risk:** _____%

**Assessment:**
- [ ] Risk limits appropriate for current AUM
- [ ] Daily max loss limit appropriate (current: ___%)
- [ ] If AUM changed > 50% this year: [ ] YES  [ ] NO
  - [ ] If YES: recompute risk limits proportionally

### 8.2 Portfolio Concentration

**Current Portfolio State:**
- [ ] Total open positions: _____
- [ ] Top 5 holdings concentration: ____%
- [ ] Sector concentration (max any sector): ____%
- [ ] Max sector concentration limit: ____%
- [ ] Status: [ ] WITHIN LIMITS  [ ] EXCEEDS LIMITS

---

## 9. Sign-Off & Recommendations

### 9.1 Overall Assessment

**Performance vs. Backtest:**
- [ ] COMPLIANT (meets all gates)  /  [ ] NON-COMPLIANT (needs improvement)

**Risk Controls:**
- [ ] ADEQUATE (all checks passing)  /  [ ] NEEDS REVIEW (gaps found)

**Parameter Sensitivity:**
- [ ] ROBUST (parameters stable)  /  [ ] SENSITIVE (needs tuning)

**Alpha Quality:**
- [ ] STRONG (IC > 0.05)  /  [ ] DECLINING (IC 0.02-0.05)  /  [ ] EXHAUSTED (IC < 0.02)

### 9.2 Recommendations

1. ______________________________________________________
2. ______________________________________________________
3. ______________________________________________________

### 9.3 Required Actions (Before Next Year)

- [ ] Action 1: ____________ (by _____)
- [ ] Action 2: ____________ (by _____)
- [ ] Action 3: ____________ (by _____)

### 9.4 Sign-Off

**Reviewed By (Data Science/Analytics):**
- Name: _____________________
- Date: _____________________
- Signature: _____________________

**Reviewed By (Trading Operations):**
- Name: _____________________
- Date: _____________________
- Signature: _____________________

**Approved By (Trading Committee Lead):**
- Name: _____________________
- Date: _____________________
- Signature: _____________________

**Approved By (Risk Committee Lead):**
- Name: _____________________
- Date: _____________________
- Signature: _____________________

---

## Appendix A: Performance Benchmarks

| Metric | Target | Acceptable | Concerning |
|--------|--------|-----------|-----------|
| Sharpe Ratio | > 1.0 | 0.7-1.0 | < 0.7 |
| Win Rate | > 55% | 50-55% | < 50% |
| Max Drawdown | < 15% | 15-25% | > 25% |
| Information Coefficient | > 0.05 | 0.02-0.05 | < 0.02 |
| Fill Rate | > 97% | 95-97% | < 95% |
| Slippage (avg) | < 25 bps | 25-50 bps | > 50 bps |
| Walk-Forward Efficiency | > 0.8 | 0.5-0.8 | < 0.5 |

---

**Document Version:** 1.0  
**Last Updated:** 2026-05-06  
**Template for:** Annual Reviews (Complete Annually)  
**Next Review Due:** 2027-05-06
