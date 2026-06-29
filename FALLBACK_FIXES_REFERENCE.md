# Fallback Fixes — Quick Reference Checklist

**Quick Lookup for Implementation Progress**  
**Use This Document While Coding/Testing**

---

## Tier 1: Critical Fixes (COMPLETED ✅)

### Fix 1: load_quality_metrics.py

| Aspect | Details |
|--------|---------|
| **File** | `loaders/load_quality_metrics.py` |
| **Lines** | 67-83, 88-102 |
| **What** | Return explicit `data_unavailable=True` records when SEC data missing |
| **Status** | ✅ DONE |
| **Check** | Grep for `data_unavailable` in fetch_incremental method |
| **Test** | `python3 load_quality_metrics.py --symbols PENNY,OTC` → verify data_unavailable=True |

**Code Pattern:**
```python
if not income_row:
    return [{
        'symbol': symbol,
        'data_unavailable': True,
        'reason': '...',
    }]
```

---

### Fix 2: load_stock_scores.py

| Aspect | Details |
|--------|---------|
| **File** | `loaders/load_stock_scores.py` |
| **Lines** | 108-117 |
| **What** | Enforce `min_required_metrics = 3` (no single-metric scores) |
| **Status** | ✅ DONE |
| **Check** | Grep for `min_required_metrics` |
| **Test** | `psql -c "SELECT COUNT(*) FROM stock_scores WHERE data_completeness < 50;"` → 0 |

**Code Pattern:**
```python
min_required_metrics = 3

if data_count < min_required_metrics:
    logger.warning(f"{symbol}: insufficient metrics ({data_count}/6)")
    return None  # Skip, don't return degraded score
```

---

### Fix 3: load_positioning_metrics.py

| Aspect | Details |
|--------|---------|
| **File** | `loaders/load_positioning_metrics.py` |
| **Lines** | 148-156 |
| **What** | Remove `shortRatio` fallback (incompatible metric) |
| **Status** | ✅ DONE |
| **Check** | Grep for `shortRatio` → should have NOTE only |
| **Test** | `psql -c "SELECT MAX(short_interest_percent) FROM positioning_metrics;"` → <100 |

**Code Pattern:**
```python
if "shortPercentOfFloat" in info and info["shortPercentOfFloat"] is not None:
    short_interest_percent = float(info["shortPercentOfFloat"]) * 100
# NOTE: shortRatio removed - it's days, not percentage
```

---

## Tier 2: High Priority (COMPLETED ✅)

### Fix 4: market_health_daily.py (Partial)

| Aspect | Details |
|--------|---------|
| **File** | `loaders/load_market_health_daily.py` |
| **Status** | ✅ Working, ⚠️ Needs provenance tracking |
| **Issue** | SPY SMA fallback from price_daily has no source flag |
| **Action** | Add `sma_source` field (tracking) OR fail-fast (strict) |
| **Priority** | Low (fallback works, but visibility needed) |

**Option A: Add Provenance (Recommended)**
```python
if has_technical_data:
    sma_source = 'technical_data_daily'
else:
    sma_source = 'price_daily_fallback'  # NEW: Mark source
```

**Option B: Strict Fail-Fast**
```python
if not has_technical_data:
    return [{'data_unavailable': True, 'reason': 'technical_data_daily unavailable'}]
```

---

### Fix 5: lambda/api/routes/scores.py (Dashboard API)

| Aspect | Details |
|--------|---------|
| **File** | `lambda/api/routes/scores.py` |
| **Lines** | 152-155 (explicit checks), 250-266 (fail-fast) |
| **What** | Return explicit data_unavailable flags; fail if >50% data missing |
| **Status** | ✅ DONE |
| **Check** | Grep for `_financial_data_unavailable` |
| **Test** | `curl /api/scores \| jq '.[0]._financial_data_unavailable'` |

**Code Pattern:**
```python
# Explicit flags in SELECT
(qm.data_unavailable = TRUE) AS _financial_data_unavailable,

# Fail-fast on missing prices
if d.get("current_price") is None:
    prices_missing_count += 1
    continue

# Return 503 if threshold exceeded
if filter_rate > 0.5:
    return error_response(503, "data_unavailable", "...")
```

---

## Tier 3: Medium Priority (Code Review)

### Fix 6: algo/orchestrator/phase7_signal_generation.py

| Aspect | Details |
|--------|---------|
| **File** | `algo/orchestrator/phase7_signal_generation.py` |
| **Issue** | Swing score not explicitly verified for pass=True |
| **Action** | Add `if not swing.get('pass'): continue` before using score |
| **Priority** | Medium (discipline/code review) |
| **Test** | Grep for swing score usage, verify explicit pass check |

---

### Fix 7: Position Sizing / Risk Calculations

| Aspect | Details |
|--------|---------|
| **Files** | Various (algo/*, utils/risk/*) |
| **Issue** | Data completeness not checked before computing position size |
| **Action** | Add validation: `if data_completeness < 50: raise ValueError` |
| **Priority** | Medium (code review) |
| **Test** | Grep for `position_size`, verify data_unavailable check present |

---

## Spot-Check Commands

### Verify All Fixes Deployed

```bash
# 1. Check quality_metrics has data_unavailable records
psql -c "SELECT COUNT(CASE WHEN data_unavailable THEN 1 END) FROM quality_metrics;" | grep -E '^[1-9]'

# 2. Verify stock_scores has no <50% completeness
psql -c "SELECT COUNT(*) FROM stock_scores WHERE data_completeness < 50;" | grep '^0$'

# 3. Check positioning_metrics short_interest valid range
psql -c "SELECT COUNT(CASE WHEN short_interest_percent > 100 THEN 1 END) FROM positioning_metrics;" | grep '^0$'

# 4. Verify API returns data_unavailable flags
curl -s http://localhost:8000/api/scores?limit=1 | jq '.data[0] | has("_financial_data_unavailable")'

# 5. Check logs for [DATA_UNAVAILABLE] markers
grep -c '\[DATA_UNAVAILABLE\]' logs/loaders.log
```

### Quick Test Suite

```bash
#!/bin/bash
# Run this to verify all fixes in place

echo "=== Checking Fix 1: quality_metrics data_unavailable ==="
psql -c "SELECT COUNT(*) as data_unavailable_count FROM quality_metrics WHERE data_unavailable = TRUE LIMIT 1;"

echo "=== Checking Fix 2: stock_scores minimum metrics ==="
psql -c "SELECT COUNT(*) as count_below_50pct FROM stock_scores WHERE data_completeness < 50;"

echo "=== Checking Fix 3: positioning_metrics short range ==="
psql -c "SELECT MAX(short_interest_percent) as max_short FROM positioning_metrics WHERE short_interest_percent IS NOT NULL;"

echo "=== Checking Fix 5: API has flags ==="
curl -s http://localhost:8000/api/scores?limit=1 | jq -r '.data[0]._financial_data_unavailable // "MISSING"'

echo "=== Done ==="
```

---

## Testing Checklist

### Before Commit
- [ ] Run quality_metrics loader with micro-cap symbols
- [ ] Run stock_scores loader, verify no incomplete scores
- [ ] Run positioning_metrics loader, check short_interest range
- [ ] Test API endpoint, verify flags returned
- [ ] Grep for shortRatio in positioning_metrics (should be 0)

### Before Deployment
- [ ] Run full test suite against production database schema
- [ ] Spot-check 50+ random symbols across all metric tables
- [ ] Verify logs show [DATA_UNAVAILABLE] for expected symbols
- [ ] Monitor API response times (baseline before/after)
- [ ] Check 503 error rate on /api/scores (should be <1%)

### Post-Deployment
- [ ] Wait 2 hours, check that all loaders completed
- [ ] Run verification queries above
- [ ] Check CloudWatch logs for errors
- [ ] Monitor trading signals - should reflect updated quality

---

## Log Markers to Watch For

**When fixes are working correctly, you should see:**

```
[QUALITY_METRICS] [SEC_DATA_UNAVAILABLE] PENNY: no SEC filing data
[STOCK_SCORES] TICKER: insufficient metrics (1/6, 16% complete). Skipping stock
[POSITIONING_METRICS] No positioning data available for SYMBOL — metrics unavailable
[DATA_UNAVAILABLE] Check logs for which metrics failed
Scores endpoint: X scores filtered due to missing price data
```

**Red flags (fixes not working):**

```
[ERROR] Value conversion failed for None  ← Should return data_unavailable=True instead
[WARNING] Returning score with 1 metric  ← Should skip (min_required_metrics=3)
shortRatio stored in short_interest_percent  ← Should never happen
All scores returned (no filtering)  ← API should filter/fail-fast
```

---

## File Locations Quick Map

```
loaders/
  ├── load_quality_metrics.py        ✅ FIX 1 (lines 67-83, 88-102)
  ├── load_stock_scores.py           ✅ FIX 2 (lines 108-117)
  ├── load_positioning_metrics.py    ✅ FIX 3 (lines 148-156)
  └── load_market_health_daily.py    ⚠️ FIX 4 (needs provenance)

lambda/api/
  └── routes/scores.py               ✅ FIX 5 (lines 152-155, 250-266)

algo/orchestrator/
  └── phase7_signal_generation.py    📋 FIX 6 (review pending)

algo/risk/
  └── position_sizing.py             📋 FIX 7 (review pending)
```

---

## Related Git Commits

```
b438b6fbb - Initial audit + 5 critical fixes
4f9a7b6c5 - SPY SMA fallback (needs provenance tracking)
77ee108cf - BreadthFetcher validation (fail-fast on missing price data)
```

---

## Success Indicators

✅ **Fix is working when:**
- Quality metrics returns explicit data_unavailable records for micro-caps
- Stock scores has no rows with <50% data completeness
- Positioning metrics short_interest always ≤ 100%
- API /scores endpoint returns explicit _*_unavailable flags
- Logs show [DATA_UNAVAILABLE] markers for expected symbols

⚠️ **Review needed when:**
- market_health_daily has SPY without sma_source flag
- Signal generation doesn't check swing score pass=True
- Position sizing doesn't validate data_completeness

