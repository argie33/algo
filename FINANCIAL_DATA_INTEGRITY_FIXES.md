# FINANCIAL DATA INTEGRITY - DETAILED FIXES

## CRITICAL FIX #1: Remove 999999 Placeholder from Swing Low Detection
**File:** `loaders/load_buy_sell_daily.py` lines 335-340  
**Current Code (BROKEN):**
```python
lookback_ok = all(rows[k].get("low", 999999) is not None and
                 (rows[k].get("low", 999999) > rows[j].get("low", 999999) or k >= j)
                 for k in range(max(0, j-3), j))
lookforward_ok = all(rows[k].get("low", 999999) is not None and
                    rows[k].get("low", 999999) > rows[j].get("low", 999999)
                    for k in range(j+1, min(len(rows), j+4)))
```

**Problem:** 
- If row[k]["low"] is None/missing, default 999999 is used
- 999999 > any real stock low price, making all comparisons true
- Incorrectly detects "swing lows" when data is actually missing
- Creates false buy signals with wrong stop losses

**Fix Option A: REJECT INVALID DATA (Recommended)**
```python
lookback_ok = all(rows[k].get("low") is not None and
                 (rows[k].get("low") > rows[j].get("low") or k >= j)
                 for k in range(max(0, j-3), j))
lookforward_ok = all(rows[k].get("low") is not None and
                    rows[k].get("low") > rows[j].get("low")
                    for k in range(j+1, min(len(rows), j+4)))
# If both fail, skip signal generation for this row
if not (lookback_ok and lookforward_ok) and recent_swing_low is None:
    # Don't generate signal if can't find valid swing low with complete data
    continue  # Skip to next row
```

**Fix Option B: MARK AS LOW-CONFIDENCE (Fallback allowed)**
```python
lookback_ok = all(rows[k].get("low") is not None and
                 (rows[k].get("low") > rows[j].get("low") or k >= j)
                 for k in range(max(0, j-3), j))
lookforward_ok = all(rows[k].get("low") is not None and
                    rows[k].get("low") > rows[j].get("low")
                    for k in range(j+1, min(len(rows), j+4)))
# Count missing lows
missing_lows = sum(1 for k in range(max(0, j-5), min(len(rows), j+5)) 
                   if rows[k].get("low") is None)
if missing_lows > 3:  # More than 3 missing lows in window
    signal["_data_quality"] = "incomplete_historical_data"
    signal["_missing_lows_in_window"] = missing_lows
```

**Recommendation:** Use Fix Option A (REJECT) - financial data integrity is critical.

---

## CRITICAL FIX #2: Handle Value Capping with User Awareness
**File:** `loaders/load_buy_sell_daily.py` line 373  
**Current Code:**
```python
vol_surge = round(min(raw_surge, 9999.0), 2)
```

**Problem:**
- 9999% surge gets capped to 9999% silently
- Users don't know if signal is from 9999% surge (capped 15000%) or real 9999%
- Dashboard quality scores unaffected by truncation
- Extreme volatility (when signals matter most) is masked

**Fix:**
```python
RAW_VOL_SURGE = raw_surge  # Keep original
vol_surge = round(min(raw_surge, 9999.0), 2)
vol_surge_capped = raw_surge > 9999.0

# In signal dict:
signals.append({
    ...
    "volume_surge_pct": vol_surge,
    "_volume_surge_original": RAW_VOL_SURGE if vol_surge_capped else None,
    "_volume_surge_capped": vol_surge_capped,
    ...
})
```

**With Dashboard Detection:**
```python
# In tools/dashboard/panels.py signal display
if sig.get("_volume_surge_capped"):
    reason = f"⚠️ Volume surge capped (actual: {sig.get('_volume_surge_original'):.0f}%)"
    # Reduce signal confidence or add warning
```

---

## CRITICAL FIX #3: Eliminate All-Zero Hardcoded Fallback
**File:** `utils/fallback_registry.py` lines 224-251  
**Current Code:**
```python
FallbackStep(
    name="hardcoded_defaults",
    priority=2,
    hardcoded_values={
        "total_trades": 0,
        "win_rate_pct": 0.0,
        ...
    }
)
```

**Problem:**
- Returns all zeros when API and cache both fail
- Users can't tell if it's "algo has 0 trades" (good) or "no data available" (bad)
- Signals false confidence in empty algorithm state

**Fix: Replace with Error Response**
```python
# In lambda/api/routes/algo.py around line 672
# BEFORE: return hardcoded_defaults
# AFTER:
logger.error(f"CRITICAL: Performance metrics unavailable. API failed: {perf.get('_error')}, Cache missing.")

# Return error, not fake data
return json_response(503, {
    '_error': 'Performance Metrics Unavailable',
    '_fallback_reason': 'API failed and no cache available',
    '_error_timestamp': datetime.now(EASTERN_TZ).isoformat(),
    'data': None,  # NOT hardcoded zeros
})
```

**Dashboard Handling:**
```python
# In tools/dashboard/panels.py
if resp.get('statusCode') == 503 and resp.get('data') is None:
    return Panel(
        Text("⚠️ PERFORMANCE METRICS UNAVAILABLE\n(API/cache failure)", 
             style="bold red"),
        title="[bold red]ERROR - NO DATA[/]",
        border_style="red"
    )
```

---

## HIGH FIX #4: Config Default Validation
**File:** `algo/algo_data_patrol.py` line 182  
**Current Code:**
```python
max_days = self._get_config_value(cur, config_key, 7)  # Hardcoded default 7
```

**Problem:**
- If config table missing/corrupted, uses 7 days silently
- No validation that 7 days is correct for this environment
- Could accept stale data for weeks if config is wrong

**Fix:**
```python
max_days = self._get_config_value(cur, config_key, default=None)
if max_days is None:
    logger.error(f"CRITICAL: Config key '{config_key}' missing from algo_config table. "
                 f"Cannot determine staleness threshold. Stopping patrol.")
    raise ValueError(f"Missing required config: {config_key}")

# Only use hardcoded default if we explicitly choose to
SAFE_DEFAULT = 7  # Documented fallback, use only if explicitly configured
if max_days is None and ALLOW_DEFAULT_FALLBACK:
    logger.warning(f"Using documented default {SAFE_DEFAULT} days for {config_key}")
    max_days = SAFE_DEFAULT
```

---

## HIGH FIX #5: Consolidation Range Fallback  
**File:** `loaders/load_trend_criteria_data.py` line 197  
**Current Code:**
```python
rng = (recent.max() - recent.min()) / mean_price if mean_price > 0 else 999.0
```

**Problem:**
- Returns fake 999.0 range when recent data missing
- 999.0 > any real consolidation range, triggers false consolidation detection

**Fix:**
```python
if mean_price > 0:
    rng = (recent.max() - recent.min()) / mean_price
else:
    # Don't return fake value—skip consolidation check or use None
    rng = None
    consolidation = None  # Don't detect consolidation if data missing

# Later in code:
if consolidation is None:
    row['consolidation'] = None
    row['_consolidation_data_quality'] = 'insufficient_data'
else:
    row['consolidation'] = consolidation
```

---

## HIGH FIX #6: Data Age Calculation Fallback
**File:** `loaders/load_technical_data_daily.py` line 176  
**Current Code:**
```python
except Exception as e:
    logger.warning(f"Could not calculate {source_table} age for {symbol}: {e}")
return 999  # Fallback age
```

**Problem:**
- Returns 999 on error, indistinguishable from "data is 999 days old" (true return)
- Filters can't tell if 999 is real or error

**Fix:**
```python
except Exception as e:
    logger.error(f"CRITICAL: Could not calculate {source_table} age for {symbol}: {e}")
    return None  # Explicit None for error case, not 999

# In calling code:
age_days = self._calculate_data_source_age_days(...)
if age_days is None:
    logger.warning(f"{symbol}: Cannot determine data age—skipping age-based filtering")
    return []  # Don't proceed without knowing data age
elif age_days > 999:
    logger.warning(f"{symbol}: Data is {age_days} days old—likely stale")
    return []
```

---

## MEDIUM FIX #7: SEC Edgar Hardcoded Cache Versioning
**File:** `utils/sec_edgar_client.py` lines 75-394, 908-910  
**Current Code:**
```python
_FALLBACK_TICKERS = {
    "AAPL": "0000320193",
    ...
}

def symbol_to_cik(self, symbol: str) -> Optional[str]:
    """Falls back to hardcoded cache, then returns placeholder for unknown symbols."""
    if ... or time.time() - self._ticker_cache_time > self._cache_ttl:
        # Fetch fresh
    else:
        return self._FALLBACK_TICKERS.get(symbol)  # Use hardcoded
```

**Problem:**
- Hardcoded cache never updated without code deploy
- Unknown staleness of data
- New symbols won't be recognized

**Fix: Add Version and Timestamp**
```python
class SecEdgarClient:
    _FALLBACK_TICKERS = { ... }
    _FALLBACK_TICKERS_VERSION = "2026-01-15"  # When this was frozen
    _FALLBACK_TICKERS_COUNT = 10365
    
    def symbol_to_cik(self, symbol: str) -> Optional[str]:
        """Convert ticker to CIK.
        
        Falls back to cached tickers (frozen 2026-01-15) if API unavailable.
        Returns None for unknown symbols (not placeholder).
        """
        try:
            # Try fresh fetch first
            cik = self._fetch_cik_from_api(symbol)
            if cik:
                return cik
        except Exception as e:
            logger.warning(f"SEC API unavailable, using fallback cache: {e}")
        
        # Fallback: use hardcoded cache
        if symbol in self._FALLBACK_TICKERS:
            logger.warning(f"CIK for {symbol} from frozen cache (v{self._FALLBACK_TICKERS_VERSION})")
            return self._FALLBACK_TICKERS[symbol]
        
        # Unknown symbol—return None, not placeholder
        logger.error(f"Unknown symbol {symbol} (not in API, not in fallback v{self._FALLBACK_TICKERS_VERSION})")
        return None
```

---

## MEDIUM FIX #8: Realtime Price Fallback Transparency
**File:** `algo/algo_realtime_prices.py` lines 80, 214-220  
**Current Code:**
```python
if not self.is_market_hours():
    return self._get_fallback_prices(symbols)  # Silent fallback to daily

def _get_fallback_prices(self, symbols: List[str]) -> Dict[str, float]:
    """Fallback: use cached or daily prices from database."""
```

**Fix: Mark Fallback Clearly**
```python
def get_latest_prices(self, symbols: List[str], metadata: bool = False) -> Dict:
    """Get latest prices with metadata about data freshness.
    
    Returns:
        If metadata=True: {"symbol": {"price": 123.45, "source": "realtime|daily|cached"}}
        If metadata=False: {"symbol": 123.45}
    """
    prices = {}
    metadata_dict = {}
    
    if not self.is_market_hours():
        # Fallback to daily prices
        logger.info(f"Market closed, using daily prices instead of realtime")
        daily_prices = self._get_fallback_prices(symbols)
        for sym, price in daily_prices.items():
            prices[sym] = price
            metadata_dict[sym] = {
                'source': 'daily',
                'is_fallback': True,
                'reason': 'market_closed',
            }
    else:
        # Normal realtime fetch
        for sym, price in prices.items():
            metadata_dict[sym] = {
                'source': 'realtime',
                'is_fallback': False,
            }
    
    if metadata:
        return {'prices': prices, 'metadata': metadata_dict}
    return prices
```

---

## TESTING CHANGES

### Test 1: Verify 999999 Placeholder is Removed
```python
def test_swing_low_detection_rejects_missing_data():
    """Verify swing low detection fails cleanly when data missing."""
    rows = [
        {"date": "2024-01-01", "low": 100.0},
        {"date": "2024-01-02", "low": None},  # Missing
        {"date": "2024-01-03", "low": 98.0},
        {"date": "2024-01-04", "low": 99.0},
    ]
    
    # Should NOT find swing low when data missing
    signals = loader._generate_signals("TEST", rows)
    assert len(signals) == 0  # No signals with incomplete data
```

### Test 2: Verify Value Capping is Marked
```python
def test_volume_surge_capping_marked():
    """Verify extreme volume surges are marked as capped."""
    row = {"volume": 50000000, "recent_avg": 100000}  # 500x surge
    
    signal = loader._generate_signals(...)[0]
    assert signal["_volume_surge_capped"] == True
    assert signal["_volume_surge_original"] == 50000.0
    assert signal["volume_surge_pct"] == 9999.0  # Capped display
```

### Test 3: Verify Fallback Metrics Return Error
```python
def test_performance_metrics_fallback_returns_error():
    """Verify no all-zero fallback—returns error instead."""
    # Mock API failure and no cache
    with patch("api.get_performance_metrics", side_effect=Exception("API down")):
        response = api_handler.get_performance_metrics()
        
        assert response['statusCode'] == 503
        assert response['data'] is None  # NOT hardcoded zeros
        assert '_fallback_reason' in response
```

---

## DEPLOYMENT CHECKLIST

- [ ] Code review all 8 fixes with senior engineer
- [ ] Run unit tests for each fix
- [ ] Run integration tests with real data
- [ ] Verify dashboard still displays correctly with new data structures
- [ ] Verify API responses still valid JSON (backward compatibility)
- [ ] Load test: ensure no performance regression
- [ ] Smoke test: run morning prep pipeline
- [ ] Verify no trades placed on fallback/invalid data during testing
- [ ] Update API documentation with new `_data_quality` fields
- [ ] Update dashboard help text explaining fallback warnings

---

## ROLLBACK PLAN

If issues occur post-deployment:
1. Revert code to previous commit
2. Verify signals stop being generated (safe state)
3. Investigate root cause
4. Create hot-fix on bugfix branch
5. Test thoroughly before re-deploy

**Safety:** These changes RESTRICT signal generation (make it harder), so rollback is safe.

---

## IMPLEMENTATION STATUS (as of 2026-06-13)

### ✅ COMPLETED IMMEDIATE FIXES

1. **Fix 999999 placeholder in swing low/high detection**
   - Commit: c440543d2
   - Status: DEPLOYED
   - Testing: Requires integration test with real data

2. **Add volume surge capping flag**
   - Commit: c440543d2 (code), b3d827b42 (migration)
   - Status: DEPLOYED
   - Migration: `migrations/versions/049_add_data_integrity_tracking.sql`
   - Requires: `python migrations/run.py apply --all`

3. **Fix consolidation range fake 999.0**
   - Commit: c440543d2
   - Status: DEPLOYED

4. **Fix technical data age sentinel (999 → -1)**
   - Commit: c440543d2
   - Status: DEPLOYED

5. **Add ROC capping warnings**
   - Commit: c440543d2
   - Status: DEPLOYED
   - Logging added for visibility into metric truncation

### ✅ COMPLETED DOCUMENTATION

6. **Configuration defaults registry**
   - File: `config/defaults_registry.md`
   - Commit: c0470600a
   - Status: DEPLOYED

7. **Signal rejection categories taxonomy**
   - File: `docs/SIGNAL_REJECTION_CATEGORIES.md`
   - Commit: c0470600a
   - Status: DEPLOYED

### ⏳ PENDING WORK

- Run migration 049 in database
- Create fallback data integration test
- Test volume_surge_capped display in dashboard
- Implement data provenance tracking for API responses

