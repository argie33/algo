# Performance Analysis Framework — Phase 1A Complete

**Status:** Template Ready. Live analysis will populate as closed trades accumulate.

**Current State:** 4 open trades, 0 closed trades (system is early)

---

## Live Trading Metrics (Will Update Automatically)

Your `algo_performance_analysis.py` script will auto-generate `PERFORMANCE_ANALYSIS_REPORT.md` once you have closed trades. This document shows the framework.

### Key Metrics to Track

| Metric | Target | Why | Action If Miss |
|--------|--------|-----|-----------------|
| **Sharpe Ratio** | > 1.0 | Risk-adjusted returns; <1.0 means too much volatility | Check if losses are too large relative to wins |
| **Max Drawdown** | < 20% | Portfolio safety; 20%+ indicates risky position sizing | Reduce max position size or tighten circuit breakers |
| **Win Rate** | > 50% | Margin of safety; below means losing positions too often | Review signal filters; possibly implement Phase 2 (Minervini + RS) |
| **Profit Factor** | > 1.5x | Winners should be 1.5x bigger than losers on aggregate | Either cut losses faster OR ride winners longer |
| **Calmar Ratio** | > 1.0 | Return per unit of drawdown; >2.0 is excellent | Focus on higher R:R entries or better signal quality |
| **Expectancy** | Positive | Average P&L per trade should be positive; {size}/trade is your expectancy | Improve signal quality or position sizing |

---

## Backtest vs Live Comparison

**Critical:** When you run `python3 algo_backtest.py --start 2026-01-01 --end 2026-05-08`, compare:

```
Backtest Results          →  Live Results           →  Gap Analysis
─────────────────────────────────────────────────────────────────
Sharpe: 1.8               vs  Sharpe: 1.4           → -22% (RED FLAG: overfitting)
Win Rate: 62%             vs  Win Rate: 55%         → -7% (acceptable)
Profit Factor: 2.1x       vs  Profit Factor: 1.8x   → -14% (acceptable)
Max DD: 8%                vs  Max DD: 15%           → +7% (WATCH: risk higher in live)
Total Return: 24%         vs  Total Return: 18%     → -6% (acceptable)
```

**Rule of Thumb:**
- Gap > 10%: Backtest is overfitted; signals may degrade over time
- Gap 5-10%: Normal; slight overfitting acceptable
- Gap < 5%: Excellent; backtest accurately models live conditions
- Live > Backtest: Impossible; usually indicates backtest data issues

---

## Daily Reconciliation (Runs Nightly at 5:31pm)

After each day's trading, `algo_orchestrator.py` Phase 7 calculates:

```python
Daily P&L = SUM(profit_loss_dollars) for trades closed today
Cumulative Return = Total P&L / Initial Capital * 100%
Portfolio Value = Initial Capital + Total P&L
Max DD = Peak Equity - Current Equity
```

These flow into `algo_audit_log` and will be visible on the dashboard.

---

## What to Monitor Weekly

Every Friday, run this command and review:

```bash
python3 algo_performance_analysis.py
# Generates PERFORMANCE_ANALYSIS_REPORT.md
# Shows: Sharpe, Max DD, Win Rate, Profit Factor for this week
```

### Red Flags to Watch

1. **Sharpe < 0.5:** System is being too aggressive; reduce position size
2. **Max DD > 25%:** Too much capital at risk per trade
3. **Win Rate < 40%:** Signal quality degrading; implement Phase 2 filters
4. **Profit Factor < 1.2x:** Losers too big; tighten stops or size down
5. **Consecutive losses > 5:** Market regime may have changed; check circuit breaker status

---

## Phase 1A → Phase 2 → Phase 3 Roadmap

### Phase 1A (This Week) — Foundation
- [x] Backtest vs Live analysis framework (this doc)
- [x] Performance analysis script (`algo_performance_analysis.py`)
- [ ] Earnings blackout filter (next)
- [ ] Daily performance dashboard (next)

### Phase 2 (Next Week) — Signal Quality
- [ ] Minervini Stage 2 filtering (discard Stage 1/3/4)
- [ ] RS > 70 requirement (outperforming market)
- [ ] Volume breakout confirmation
- [ ] Trendline support/resistance

**Expected Impact:** +10-15% Sharpe, +5% win rate, reduced drawdown

### Phase 3 (Month 2) — Monitoring
- [ ] Daily performance dashboard (embedded in frontend)
- [ ] P&L leakage detection (are commissions what we expect?)
- [ ] Stress testing (2008, 2020, 2022 data)
- [ ] Rolling Sharpe alerts

---

## Database Tables Involved

### algo_trades (Core Performance Data)
```sql
SELECT symbol, COUNT(*), AVG(profit_loss_pct), SUM(profit_loss_dollars)
FROM algo_trades
WHERE status = 'closed' AND exit_date >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY symbol
ORDER BY SUM(profit_loss_dollars) DESC
```

This shows: by symbol, how many trades, average return%, total P&L this week.

### algo_positions (Current Exposure)
```sql
SELECT symbol, quantity, entry_price, current_price, 
       (current_price - entry_price) * quantity AS unrealized_pnl
FROM algo_positions
WHERE status = 'open'
ORDER BY unrealized_pnl DESC
```

This shows: what's open, what's winning/losing right now.

### algo_audit_log (Decision Trail)
```sql
SELECT DATE(timestamp), event_type, SUM(CASE WHEN outcome='success' THEN 1 ELSE 0 END) as success_count
FROM algo_audit_log
WHERE DATE(timestamp) >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY DATE(timestamp), event_type
```

This shows: daily trade attempt counts, what succeeded, what failed.

---

## Expected First Results

With 50 closed trades (trading 1 month), you'll see patterns like:

**Example Results (Realistic 1-Month Sample):**
```
Total Trades: 47
Win Rate: 53%
Sharpe Ratio: 1.2
Max Drawdown: 12%
Total Return: 8.5%
Profit Factor: 1.7x
Expectancy: $180/trade
```

**Interpretation:**
- ✓ Win rate > 50%: good signal quality
- ✓ Sharpe > 1.0: acceptable risk-adjusted returns
- ✓ Profit Factor > 1.5x: winners > losers
- ⚠ Max DD 12%: acceptable but watch trend
- ✓ Expectancy > 0: system is profitable

---

## Next Steps (This Week)

1. **Today:** Understand this framework (you're reading it)
2. **Tomorrow:** Implement earnings blackout filter (Task 3)
3. **Day 3:** Build daily performance dashboard (Task 2)
4. **Day 5:** First live closed trade closes → script auto-generates report
5. **Weekly:** Review report, check for red flags

Once you have 20-30 closed trades, the metrics will stabilize and you'll see clear patterns.

---

## Debugging Performance

If Sharpe suddenly drops or Max DD spikes, check:

1. **Data Quality:** `SELECT MAX(date) FROM price_daily` — is data fresh?
2. **Signal Quality:** Count signals by base_type — are bad patterns sneaking in?
3. **Position Sizing:** Are we oversizing? Check `position_size_pct` in recent trades
4. **Market Regime:** Is VIX high? Are breadth indicators weak? (circuit breaker should handle)
5. **Slippage:** Compare `entry_price` to market price at `entry_time` — are we filling worse than expected?

---

**Framework Complete.** Script ready to analyze once closed trades exist.

Run weekly: `python3 algo_performance_analysis.py`

Last Updated: 2026-05-08
