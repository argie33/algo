# Paper Trading Runbook - Production Safeguards Validation

**Status**: Ready to deploy  
**Date**: 2026-05-08  
**Duration**: 1 week (5 trading days minimum)

---

## Pre-Deployment Checklist

- [x] Earnings blackout enforcement verified (5/5 entries blocked correctly)
- [x] Economic calendar integrated and ready
- [x] Orchestrator initialized with safeguard wiring
- [x] Margin monitoring code deployed
- [x] Filter pipeline tier 5 updated with liquidity + earnings checks

---

## Step 1: Configure Alpaca Paper Trading (5 minutes)

If not already configured, set up Alpaca credentials:

```bash
# Verify .env.local has these settings
ALPACA_API_KEY=<your_paper_api_key>
ALPACA_SECRET_KEY=<your_paper_secret_key>
ALPACA_PAPER=true
ALPACA_BASE_URL=https://paper-api.alpaca.markets
```

Test connection:
```bash
python -c "
from algo_margin_monitor import MarginMonitor
mm = MarginMonitor()
info = mm.get_margin_usage()
if info:
    print(f'[OK] Alpaca connected. Margin: {info[\"margin_usage_pct\"]:.1f}%')
else:
    print('[FAIL] Cannot connect to Alpaca')
"
```

---

## Step 2: Run First Dry-Run (10 minutes)

Validate all safeguards before live paper trading:

```bash
# Run validation suite
python validate_safeguards.py

# Expected output:
# - Earnings blackout: BLOCKED entries near earnings
# - Economic calendar: Entry gates functional
# - Orchestrator: Ready
```

---

## Step 3: Deploy Orchestrator in Paper Mode (Day 1)

```bash
# Run orchestrator in paper trading mode (dry run first)
python algo_orchestrator.py --date 2026-05-08 --dry-run --verbose

# Check output for:
# - Phase 1 (DATA FRESHNESS): Margin check should run
# - Phase 5 (SIGNAL GENERATION): Filter tiers should show earnings blocks
# - Phase 6 (ENTRY EXECUTION): Margin gate should be evaluated
```

Expected behavior:
```
[OK] Margin: 35.2% usage
[OK] Margin gate: Can enter new positions
PHASE 5: SIGNAL GENERATION
  Tier 5: Liquidity check...
  Tier 5: Earnings blackout...
```

---

## Step 4: Monitor Safeguard Behavior (Days 1-5)

### Daily Monitoring Checklist

Each trading day, log these metrics:

**Morning (before market open):**
- [ ] Run: `python validate_safeguards.py`
- [ ] Check margin status
- [ ] Verify no system errors in logs

**During market hours:**
- [ ] Monitor orchestrator output for safeguard triggers
- [ ] Log any entries blocked by liquidity check
- [ ] Log any entries blocked by earnings blackout
- [ ] Track margin usage throughout day

**End of day:**
- [ ] Check orchestrator summary
- [ ] Review any alerts from margin monitoring
- [ ] Document false positives or unexpected blocks

### What to Monitor

| Safeguard | Metric | Expected | Alert if |
|-----------|--------|----------|----------|
| Liquidity | Entries blocked | 1-3/week | >5/day |
| Earnings | Entries blocked | 1-2/week | 0 (no rejections) |
| Margin | Usage % | 20-50% | >75% |
| Margin | Entry gate | Mostly open | Closed >1x/day |
| Economic | Entry gate | Mostly open | Closed frequently |

---

## Step 5: Collect Data (5 Trading Days)

### Log Template (Daily)

```
Date: 2026-05-09
Market Status: OPEN/CLOSED/PAUSED

Safeguard Activations:
  Earnings blocks: CSCO (approaching 5/13 earnings)
  Liquidity blocks: PENNY_STOCK_XYZ (volume < 1M)
  Margin alerts: None
  Margin gates: None
  Economic gates: None

Account Status:
  Margin: 32.5%
  Equity: $25,000
  Cash: $12,500
  Positions: 3 open

Issues/Notes:
  - None

```

---

## Step 6: Evaluate Results (After 5 Days)

### Success Criteria

✓ **Earnings blackout**: Blocks ALL entries 7 days before earnings
✓ **Liquidity checks**: Rejects <2% of signals (mostly illiquid stocks)
✓ **Margin monitoring**: Alerts when >70%, blocks when >80%
✓ **No false positives**: System allows valid entries through

### Post-Analysis Questions

1. **Earnings blocking**: Were ALL earnings windows respected?
   - If no: Adjust `earnings_blackout_days_before/after` in config

2. **Liquidity rejections**: Did system reject penny stocks?
   - If no: Lower `min_daily_volume_shares` threshold
   - If too many rejections: Raise threshold

3. **Margin monitoring**: Did margins stay healthy?
   - If alerts triggered: Review position sizing
   - If gate blocked entries: Check portfolio concentration

4. **False positives**: Did valid signals get blocked?
   - If yes: Adjust thresholds in `algo_config.py`

---

## Step 7: Adjust Configuration (If Needed)

Based on paper trading results, fine-tune thresholds:

```python
# In algo_config.py:

# If liquidity check too strict:
'min_daily_volume_shares': 500000.0,  # Loosen from 1M
'max_spread_pct': 1.0,                # Loosen from 0.5%

# If earnings blocking too aggressive:
'earnings_blackout_days_before': 5,   # Tighten from 7
'earnings_blackout_days_after': 5,    # Tighten from 7

# If margin gate blocking entries:
'margin_halt_pct': 85.0,              # Raise from 80%
```

---

## Step 8: Deploy to Live (After Validation)

Once satisfied with paper trading results:

```bash
# Update execution mode in config
# Change: execution_mode = 'paper' → 'live'

# Deploy with monitoring
python algo_orchestrator.py --date 2026-05-15 --verbose

# Keep close eye on:
# - Safeguard alerts
# - Margin monitoring
# - Trade execution
```

---

## Troubleshooting

| Problem | Diagnosis | Fix |
|---------|-----------|-----|
| Earnings blocks all symbols | Check earnings_calendar table | Verify dates are correct |
| Liquidity check crashes | Missing price_daily data | Load price data via loader |
| Margin shows 0% | Alpaca API not responding | Check API credentials |
| Economic gate blocks all entries | Check economic_calendar dates | Verify release dates in future |
| Filter pipeline errors | Missing tier 5 integration | Re-run integration commits |

---

## Rollback Plan

If safeguards cause issues:

```bash
# Disable liquidity checks
# Edit algo_filter_pipeline.py, comment out lq.run_all() call

# Disable earnings blackout
# Edit algo_filter_pipeline.py, comment out eb.run() call

# Disable margin gate
# Edit algo_orchestrator.py, comment out MarginMonitor calls

# Or: Simply set thresholds to never-trigger values
'min_daily_volume_shares': 1,       # Accept any volume
'earnings_blackout_days_before': 0, # No blackout
'margin_halt_pct': 99.0,            # Never block on margin
```

---

## Success Metrics

After 1 week of paper trading with safeguards:

- **0 unexpected liquidations** (margin gates working)
- **0 earnings whipsaws** (blackout working)
- **<2% false positive rejections** (liquidity thresholds right)
- **System uptime >99%** (no crashes)
- **All alerts logged** (monitoring working)

If all metrics passed: **Ready for live deployment** ✓

---

## Next Actions

1. Configure Alpaca credentials
2. Run validation suite: `python validate_safeguards.py`
3. Monitor for 5 trading days
4. Collect results in daily log
5. Adjust configuration if needed
6. Deploy to live with confidence

**Estimated timeline**: 1-2 weeks from today
