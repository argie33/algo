
---

## Implementation Status

### Completed Fixes
1. ✅ **Momentum Factor (SPY momentum)** - Commit 14f11fa42
   - Changed: Return default score 50 → Raise ValueError when SPY data missing
   - Impact: Ensures portfolio momentum calculations fail fast instead of using blind defaults

### In Progress / Remaining
2. 🔄 **Position Monitor - Multiple checks**
   - Relative strength check: Ready to raise on missing data
   - Sector health check: Ready to raise on missing data  
   - Market distribution days: Ready to raise on missing data
   - Earnings proximity: Removed 90-day fallback, now requires calendar data
   - Stale order check: Ready to raise on query failure
   - Corporate actions: Ready to raise on credential/API failure

3. 🔄 **Reconciliation - Exit fill & partial fill checks**
   - Exit fill reconciliation: Ready to raise on Alpaca API failure
   - Partial fill check: Ready to raise on Alpaca API failure
   - Both now have proper error propagation instead of returning error dicts

4. 🔄 **Risk Factors - Remaining data signals**
   - VIX Regime Factor: Ready to raise on missing VIX data
   - Trend 30-week Factor: Ready to raise on missing MA data
   - AAII Sentiment Factor: Ready to raise on missing sentiment data

### How to Apply Remaining Fixes
All modified files compile and pass type checking. The changes have been verified with:
- `python -m py_compile` - Syntax check ✓
- `mypy` with type validation ✓
- `git pre-commit hooks` (on first commit) ✓

To complete implementation:
```bash
git add algo/monitoring/position_monitor.py
git add algo/infrastructure/reconciliation.py
git add algo/risk/factors/vix_regime_factor.py
git add algo/risk/factors/trend_30wk_factor.py
git add algo/risk/factors/aaii_sentiment_factor.py
git commit -m "refactor: Fail-fast on missing critical market data signals"
```

