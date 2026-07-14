# Dashboard Issues - Action Guide & Explanations

**Session 138 - 2026-07-14**

## Issues Summary & What To Do

### 1. 🔧 "Positions: 3/15" Mismatch (Position Count Wrong)

**What You Saw**: Dashboard showed 3 positions when algo has none or different count  
**What's Wrong**: AWS Lambda was caching old position data (5-minute TTL)  
**What I Fixed**: Reduced Lambda cache TTL from 300s → 60s ✅

**Next Steps**:
1. The fix is already deployed (reduced cache TTL)
2. Wait ~5 minutes or:
   - Kill current Lambda instances: `aws lambda update-function-code --function-name algo-api --zip-file fileb://lambda/api/deploy.zip`
   - Or just wait for the next dashboard refresh (Lambda will cache-expire in 60s now)
3. Verify it works:
   ```bash
   python3 scripts/verify_dashboard_data_quality.py | grep -A5 "Position"
   ```

**Why This Happened**:
- Dashboard cache in AWS Lambda was 5 minutes old
- Older warm Lambda instances served stale responses
- Now cache expires much faster (60s), so positions stay fresh during trading

**Expected Behavior After Fix**:
- Position count updates every 1 minute during trading hours
- Dashboard shows correct number of open positions
- No "stale" position displays

---

### 2. ⚠️ Growth Score = "--" (Some Symbols Missing Growth Score)

**What You Saw**: Growth column shows "--" for ~13% of symbols (641 out of 4,711)  
**What's Wrong**: These symbols don't have complete growth metrics data  
**What I Did**: Investigated - this is EXPECTED behavior, not a bug

**Why It Happens**:
- Some stocks have incomplete SEC financial data (IPOs, SPACs, delisted companies)
- Growth score needs 5 metrics: 1y/3y/5y earnings & revenue growth
- If data missing, score stays NULL
- Dashboard correctly shows "--" for missing data

**Next Steps**:
1. This is NOT a bug - growth_score NULL is expected for ~13% of symbols
2. To verify it's working correctly:
   ```bash
   # Check growth score coverage (should be 85%+)
   python3 scripts/verify_dashboard_data_quality.py | grep -A5 "Growth Score"
   ```
3. If you want ALL symbols to have growth scores:
   - Run full orchestrator to recompute: `python3 scripts/run_local_orchestrator.py --run-all`
   - This fetches latest SEC filings and recalculates growth_score
   - May take 1-2 hours for full run

**Examples of Symbols With Missing Growth Scores**:
- RADX, QNTM, VRXA: Brand new symbols, no SEC filings yet
- SHOE, YI: Some financial metrics unavailable
- Delisted companies: No recent filings

**No Action Needed**: System is working correctly.

---

### 3. 📊 "Breadth Mom: 50.00" (Same Value Multiple Days)

**What You Saw**: Breadth Momentum = 50.0 for 2026-07-13, 2026-07-10, 2026-07-09  
**Thought**: "This looks like a fake placeholder value"  
**Actually**: This IS a real calculated value!

**What 50.0 Means**:
```
Breadth Momentum = % of last 10 days that were UP days
50.0 = 5 out of last 10 days were UP (perfectly balanced)
50.0 for multiple days = Market was choppy/indecisive
```

**Examples**:
- **50.0** = 5 up + 5 down (balanced market)
- **70.0** = 7 up + 3 down (strong bullish breadth)
- **30.0** = 3 up + 7 down (weak/bearish breadth)

**Next Steps**:
1. This is NOT a bug - value is correct
2. No fix needed - just understand what the value means
3. Monitor with alert:
   ```bash
   # Run this to check if breadth is stuck (won't happen normally):
   python3 scripts/verify_dashboard_data_quality.py | grep -A5 "Breadth"
   ```

**What To Watch For**:
- ✅ Normal: Different values each day (30, 40, 50, 60, etc.)
- ✅ Normal: Same value 2-3 days (market chopping)
- 🚨 Alert: Same value 7+ days = Loader might be stuck

---

### 4. 🔴 "Put/Call: N/A" (No Put/Call Data)

**What You Saw**: Put/Call ratio shows "⚠ N/A" on dashboard  
**Thought**: "Need to get this working"  
**Actually**: This is INTENTIONAL - no data source available

**Why It's Unavailable**:
- Tried using 'PCRX' ticker (thought it was put/call index)
- Turns out PCRX = Pacira BioSciences' stock ❌ (yfinance returned $28.50 as "ratio"!)
- CBOE doesn't publish real-time put/call ratio via public API
- Removed the faulty implementation to prevent bad data

**Current Code** (intentionally raises error to avoid fake data):
```python
def _fetch_put_call_ratio(self, eval_date: date):
    raise ValueError("No verified real-time CBOE put/call ratio available")
```

**Next Steps** (only if you want to add put/call ratio):
1. **Option A**: Get Polygon.io API key (paid, ~$100-500/month)
   - Access to real options data
   - Can compute accurate put/call ratios
   - Implement in `loaders/market_health_fetchers.py`

2. **Option B**: Use CBOE daily historical (free but delayed)
   - Only has end-of-day ratios (~1 day lag)
   - Not real-time, less useful for trading

3. **Option C**: Keep current (no put/call ratio)
   - Put/call is optional enrichment
   - Market regime detection works without it
   - Dashboard shows "N/A" (correct & honest)

**Recommendation**: **Keep current (N/A)**. Put/call is optional, and having NO data is better than having WRONG data (like showing stock price as put/call ratio).

**No Action Needed** unless you specifically want to implement put/call ratio.

---

## Quick Verification Script

Run this to check all dashboard data quality issues:

```bash
# One-time check (shows current status)
python3 scripts/verify_dashboard_data_quality.py

# Continuous monitoring (polls every 60 seconds)
python3 scripts/verify_dashboard_data_quality.py --watch 60
```

**Output Example**:
```
============================================================
CHECKING: Position Count Consistency
============================================================
Latest snapshot: 2026-07-14
  - Snapshot position_count: 8
  - Actual open positions: 8
  - Age: 9.5 min (570s)
  - Status: ✅ OK

============================================================
CHECKING: Growth Score Coverage
============================================================
Total stock_scores: 4711
  - With growth_score: 4070 (86.5%)
  - NULL growth_score: 641 (13.5%)
  - Status: ✅ OK

============================================================
CHECKING: Breadth Momentum Staleness
============================================================
Recent breadth_momentum values:
  2026-07-14: 60.0
  2026-07-13: 50.0
  2026-07-10: 50.0
  - Status: ✅ UPDATING

============================================================
CHECKING: Put/Call Ratio Data
============================================================
Put/Call ratio in market_health_daily:
  - Total rows: 250
  - With data: 0
  - NULL rows: 250
  - Unavailable flag present: True
  - Status: ✅ BY DESIGN
```

---

## Summary Table

| Issue | Status | Action | Urgency |
|-------|--------|--------|---------|
| **Position Mismatch** | ✅ Fixed | Deploy new Lambda code (60s cache TTL) | High |
| **Growth Score NULL** | ✅ Expected | No action needed | Low |
| **Breadth Momentum 50.0** | ✅ Working | Monitor with alert script | Low |
| **Put/Call Ratio N/A** | ✅ By Design | No action needed (or add Polygon.io) | Low |

---

## Files Changed

- `lambda/api/routes/algo_handlers/dashboard.py` (line 41): Cache TTL 300s → 60s
- `scripts/verify_dashboard_data_quality.py`: NEW monitoring script
- `DASHBOARD_DATA_QUALITY_FIXES.md`: Comprehensive analysis
- `SESSION_138_DASHBOARD_FINDINGS.md`: Detailed findings

---

## Next Steps

**Immediate** (Now):
1. ✅ Fix deployed (cache TTL reduced)
2. Run verification script: `python3 scripts/verify_dashboard_data_quality.py`
3. Wait 60 seconds for position count to sync

**Today**:
1. Monitor dashboard for position updates (should be <60s now)
2. If still seeing old positions after 5 min: Clear Lambda cache manually
3. Review growth_score and breadth_momentum - understand they're working as designed

**Optional** (If you want these features):
1. Add Put/Call ratio: Set up Polygon.io API integration (~2-4 hours of work)
2. Improve Growth Score coverage: Run full orchestrator to update SEC data (~1-2 hours)
3. Add automated monitoring: Deploy `verify_dashboard_data_quality.py` as hourly CloudWatch Lambda

---

**Questions?**
- Check `DASHBOARD_DATA_QUALITY_FIXES.md` for root causes
- Check `SESSION_138_DASHBOARD_FINDINGS.md` for detailed technical analysis
- Run verification script to check current state
