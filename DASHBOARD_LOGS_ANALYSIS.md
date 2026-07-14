# Dashboard Logs Analysis - Session 142

**Date:** 2026-07-14  
**Log File:** `~/.algo/logs/dashboard.log`  
**File Size:** 512KB (indicates high-frequency repeating errors)

## Executive Summary

The "flashing logs" you observed are **15+ ERROR/WARNING messages repeating every dashboard refresh cycle**. These are real data issues that need fixing.

### Quick Fix Priority

| Priority | Issue | Impact | Fix | Est. Time |
|----------|-------|--------|-----|-----------|
| 🔴 P0 | Put/Call ratio missing | Market header + exposure degraded | Check `/api/algo/market-exposure` endpoint | 15 min |
| 🟡 P1 | 11 market factors missing | Exposure panel incomplete | Same endpoint issue | 15 min |
| 🟡 P2 | Phase data None/invalid | Health panel shows "unavailable" | Check orchestrator run + `/api/algo/last-run` | 30 min |
| 🟢 P3 | Empty positions | Sector rotation unavailable | Normal when portfolio flat | N/A |

---

## Detailed Error Analysis

### ERROR #1: Put/Call Ratio Missing (Critical)

**Frequency:** Every 0.5 seconds (per render cycle)  
**Source:** `dashboard.panels.market:ERROR`

```
2026-07-14 16:20:55,040 - dashboard.panels.market - ERROR - [MARKET_HEADER] Put/Call ratio missing - critical sentiment data unavailable
2026-07-14 16:20:55,156 - dashboard.panels.market - ERROR - [MARKET_HEADER] Put/Call ratio missing - critical sentiment data unavailable
2026-07-14 16:20:55,240 - dashboard.panels.market - ERROR - [MARKET_HEADER] Put/Call ratio missing - critical sentiment data unavailable
2026-07-14 16:20:55,286 - dashboard.panels.market - ERROR - [MARKET_HEADER] Put/Call ratio missing - critical sentiment data unavailable
```

**Root Cause:** The `/api/algo/market-exposure` response does not include `put_call_ratio` field.

**What's Broken:**
- Market header cannot render sentiment indicator
- Exposure panel shows degraded position sizing (cannot factor in put/call data)
- Dashboard shows RED indicators instead of sentiment data

**What to Check:**
1. API endpoint: `curl -s http://localhost:3001/api/algo/market-exposure | jq .put_call_ratio`
2. Check if orchestrator Phase 5+ has run recently (sentiment loaders)
3. Verify sentiment data source (AAII, Trader Sentiment, etc.)

**Code Location:** `dashboard/panels/market.py:line ~200`

---

### ERROR #2: Exposure Risk Factor Missing

**Frequency:** Every 0.5 seconds  
**Source:** `dashboard.panels.exposure:ERROR`

```
2026-07-14 16:20:55,157 - dashboard.panels.exposure - ERROR - [EXPOSURE] Risk factor missing: put_call_ratio unavailable. reason=no_data. Position sizing will be degraded.
```

**Root Cause:** Same as ERROR #1 — put_call_ratio field missing from market data response.

**Impact:** Position sizing recommendations are incomplete (uses fallback calculations only).

---

### WARNING #1: 12 Missing Market Exposure Factors

**Frequency:** Every 0.5 seconds  
**Source:** `dashboard.panels.exposure:WARNING`

```
2026-07-14 16:20:55,258 - dashboard.panels.exposure - WARNING - [EXPOSURE] factor trend_30wk not in response
2026-07-14 16:20:55,258 - dashboard.panels.exposure - WARNING - [EXPOSURE] factor spy_momentum not in response
2026-07-14 16:20:55,258 - dashboard.panels.exposure - WARNING - [EXPOSURE] factor breadth_200dma not in response
2026-07-14 16:20:55,258 - dashboard.panels.exposure - WARNING - [EXPOSURE] factor distribution_days not in response
2026-07-14 16:20:55,258 - dashboard.panels.exposure - WARNING - [EXPOSURE] factor vix_regime missing pts field
2026-07-14 16:20:55,258 - dashboard.panels.exposure - WARNING - [EXPOSURE] factor credit_spread not in response
2026-07-14 16:20:55,258 - dashboard.panels.exposure - WARNING - [EXPOSURE] factor put_call_ratio not in response
2026-07-14 16:20:55,258 - dashboard.panels.exposure - WARNING - [EXPOSURE] factor new_highs_lows not in response
2026-07-14 16:20:55,258 - dashboard.panels.exposure - WARNING - [EXPOSURE] factor ad_line not in response
2026-07-14 16:20:55,258 - dashboard.panels.exposure - WARNING - [EXPOSURE] factor breadth_50dma not in response
2026-07-14 16:20:55,258 - dashboard.panels.exposure - WARNING - [EXPOSURE] factor naaim not in response
2026-07-14 16:20:55,258 - dashboard.panels.exposure - WARNING - [EXPOSURE] factor aaii_sentiment not in response
```

**Root Cause:** `/api/algo/market-exposure` endpoint returning incomplete response (missing factors).

**Impact:** Exposure panel shows missing data for:
- Market breadth (50/200 DMA)
- Market momentum (trend_30wk, spy_momentum)
- Market structure (distribution_days, new_highs_lows, AD line)
- Volatility (VIX regime)
- Risk (credit spread)
- Sentiment (AAII, put/call, NAAIM)

**What to Check:**
```bash
# Check what's actually being returned
curl -s http://localhost:3001/api/algo/market-exposure | jq 'keys'

# Expected to include: put_call_ratio, trend_30wk, spy_momentum, etc.
```

**Code Location:** `dashboard/panels/exposure.py:line ~150`

---

### WARNING #2: Phase Data None/Invalid

**Frequency:** Every 0.5 seconds  
**Source:** `dashboard.panels.health:WARNING`

```
2026-07-14 16:20:55,159 - dashboard.panels.health - DEBUG - [HEALTH] Phase data raw is None or invalid type, returning unavailability marker
2026-07-14 16:20:55,159 - dashboard.panels.health - WARNING - Phase all_tables_fresh_degraded metrics incomplete: signals_generated missing from phase data
2026-07-14 16:20:55,159 - dashboard.panels.health - WARNING - Phase CIRCUIT BREAKERS metrics incomplete: signals_generated missing from phase data
2026-07-14 16:20:55,159 - dashboard.panels.health - WARNING - Phase POSITION MONITOR metrics incomplete: signals_generated missing from phase data
[... repeats for all 9+ phases ...]
```

**Root Cause:** `/api/algo/last-run` or `/api/algo/data-status` is not returning valid phase data.

**Impact:**
- Health panel shows "Data not available" for all phases
- Cannot see orchestrator progress
- Cannot verify that loaders/signals/trades are running

**What to Check:**
```bash
# Check last run status
curl -s http://localhost:3001/api/algo/last-run | jq .

# Expected fields: phases (array), status, started_at, completed_at, etc.
# If phases is empty or None, orchestrator didn't run
```

**Code Location:** `dashboard/panels/health.py:line ~200`

---

### WARNING #3: Invalid Data Type in Signals

**Frequency:** Every 0.5 seconds  
**Source:** `dashboard.panels.data_extractors:WARNING`

```
2026-07-14 16:20:55,162 - dashboard.panels.data_extractors - WARNING - safe_get_list: Expected dict or list but got int (value=0). Returning unavailability marker.
```

**Root Cause:** Signal data structure mismatch — field is integer when list is expected.

**Impact:** Signals panel cannot display buy/sell signals.

**What to Check:**
```bash
# Check signal response structure
curl -s http://localhost:3001/api/algo/signals | jq '.scored_with_signals | type'
# Should be "array", not "number"
```

---

### WARNING #4: Empty Positions

**Frequency:** Every 0.5 seconds  
**Source:** `dashboard.panels.sectors:WARNING`

```
2026-07-14 16:20:55,163 - dashboard.panels.sectors - WARNING - Cannot compute sector aggregation: Cannot compute sector aggregation: positions data is empty
```

**Root Cause:** No open positions in portfolio (expected if flat/cash).

**Impact:** Sector rotation panel shows "No Data" (this is NORMAL when holding no positions).

---

## Root Cause Summary

### Primary Issues (Both Stem from Same API Endpoint)

**Endpoint:** `/api/algo/market-exposure`  
**Problem:** Response is missing 12 required fields

**Missing Fields:**
- `put_call_ratio` (CRITICAL - causes ERROR logs)
- `trend_30wk`
- `spy_momentum`
- `breadth_200dma`
- `breadth_50dma`
- `distribution_days`
- `new_highs_lows`
- `ad_line`
- `vix_regime` (exists but missing 'pts' subfield)
- `credit_spread`
- `aaii_sentiment`
- `naaim`

**Check If Endpoint Exists:**
```bash
curl -s http://localhost:3001/api/algo/market-exposure | head -20
```

**If 404/Error:** Endpoint is broken or data hasn't loaded  
**If Response:** Check which fields are missing

### Secondary Issues

**Issue:** Health panel shows "Phase data unavailable"  
**Endpoint:** `/api/algo/last-run`  
**Check:**
```bash
curl -s http://localhost:3001/api/algo/last-run | jq '.'
```

Should return recent orchestrator run with phase completion status.

---

## Action Plan

### Step 1: Verify Dev Server Status (5 min)
```bash
# Terminal 1: Check if dev_server is running
python lambda/api/dev_server.py &

# Terminal 2: Test endpoints
curl -s http://localhost:3001/api/algo/health | jq '.status'
curl -s http://localhost:3001/api/algo/market-exposure | jq 'keys' | head -20
curl -s http://localhost:3001/api/algo/last-run | jq '.phase_results | length'
```

### Step 2: Identify Missing Endpoint
If `/api/algo/market-exposure` returns 404, need to check:
- `lambda/api/endpoints/` for market exposure route
- Data loaders for market factors (Phase 5?)
- Database tables for technical indicators

### Step 3: Check Orchestrator
```bash
# See when last run occurred
curl -s http://localhost:3001/api/algo/last-run | jq '.started_at, .completed_at'

# See what phases completed
curl -s http://localhost:3001/api/algo/last-run | jq '.phases'
```

If no recent run, data loaders may not be running.

### Step 4: Manual Data Refresh (if needed)
```bash
# Run orchestrator locally to refresh data
python3 scripts/run_local_orchestrator.py --morning

# Or trigger via AWS Lambda
python3 scripts/trigger_orchestrator.py --run morning --mode paper
```

---

## FAQ

**Q: Why are logs 512KB and repeating?**  
A: Dashboard refresh cycle (~0.5s) renders 15+ ERROR/WARNING messages each cycle. At -w 30 (refresh every 30s), dashboard runs 60 render cycles, generating ~900 log lines per minute.

**Q: Will these errors break the dashboard?**  
A: No, dashboard degrades gracefully:
- Missing market data → Shows empty/unavailable indicators
- Missing phases → Shows "Data not available" in health panel
- Empty positions → Shows "No sector data available" (normal)

**Q: Should I clear the logs?**  
A: Yes, once you fix the underlying issues:
```bash
rm ~/.algo/logs/dashboard.log
# Logs will rotate automatically at 10MB
```

**Q: Why only ERROR + WARNING, no ERROR causing 503?**  
A: ERROR/WARNING logs are at dashboard rendering layer (per-panel), not API response layer. API still returns 200, but with incomplete data. Critical fetcher errors (affecting API response) would show different ERROR pattern.

---

## Next Steps

1. **Run dashboard with logs visible:** Keep watching the logs while you investigate
2. **Test API endpoints:** Verify `/api/algo/market-exposure` and `/api/algo/last-run`
3. **Check data freshness:** See when orchestrator last ran
4. **Fix missing data:** Likely needs data loader or endpoint fix

Let me know what the endpoint returns when you test it!
