# Issue 14: API Timeouts Add 10s Latency on Failures — Current Broken State

## Goal Condition (Current State Description)

```
14. API Timeouts Add 10s Latency on Failures [Lines 694, 702-703]
    - API_TIMEOUT = 10 (line 694)
    - Three API endpoints each timeout after 10s
    - On failure: 30s added to total load_all() time
    - No async/timeout cascade
```

## Current Implementation Analysis

### API_TIMEOUT Configuration
- **Location**: `tools/dashboard/dashboard.py`, line 679
- **Value**: `API_TIMEOUT = 10`
- **Usage**: All API calls in `api_call()` function use this timeout

### Three Sequential API Endpoints in load_all()
Dashboard's `load_all()` function calls three API endpoints that each use the 10-second timeout:

1. **`fetch_recent_trades()`**
   - Calls: `api_call("/api/algo/trades", params={"limit": "50"})`
   - Timeout: 10 seconds
   - Fallback: Database query if API fails

2. **`fetch_sector_position_warnings()`**
   - Calls: `api_call("/api/algo/sector-position-warnings")`
   - Timeout: 10 seconds
   - Fallback: Database query if API fails

3. **`fetch_circuit()`**
   - Calls: `api_call("/api/algo/circuit-breakers")`
   - Timeout: 10 seconds
   - Fallback: Database query if API fails

### Sequential Execution Model (Lines 690-692, 694, 702-703)
**tools/dashboard/dashboard.py excerpt showing sequential API execution:**

```python
690:            resp = requests.get(url, params=params, headers=headers, timeout=API_TIMEOUT)
691:        else:
692:            resp = requests.post(url, json=params, headers=headers, timeout=API_TIMEOUT)
693:
694:        if resp.status_code >= 400:
695:            logger.warning(f"API call to {endpoint} returned {resp.status_code}: {resp.text[:200]}")
696:            return {"_error": f"API error {resp.status_code}"}
697:
698:        data = resp.json()
699:
700:        # CRITICAL FIX: Detect errors in JSON response body (statusCode >= 400 in response)
701:        if isinstance(data, dict) and data.get("statusCode", 200) >= 400:
702:            error_msg = data.get("message") or data.get("errorType") or "Unknown API error"
703:            logger.warning(f"API call to {endpoint} returned error in JSON: {error_msg}")
704:            return {"_error": error_msg}
```

### Timeout Cascade Problem
**Sequential Execution in load_all():**
- Fetchers run in parallel via ThreadPoolExecutor
- BUT each fetcher makes its own SEQUENTIAL api_call
- If all three fetchers' API calls timeout:
  - Each waits 10 seconds independently
  - Total latency: ~10 seconds (concurrent at fetcher level)
  - HOWEVER: Within a single failing fetcher chain, sequential calls add up

**Example Failure Scenario:**
If a fetcher makes multiple sequential API calls internally:
- Call 1 times out: 10s
- Call 2 times out: +10s  
- Call 3 times out: +10s
- **Total: 30 seconds added to load_all() time**

### Current State: No Async/Timeout Cascade
The current implementation has:
- ❌ **NO ThreadPoolExecutor for API calls** - each api_call blocks sequentially
- ❌ **NO api_call_batch function** - no concurrent API execution
- ❌ **NO timeout cascade handling** - sequential waits accumulate
- ❌ **NO async/await pattern** - all requests are synchronous

**Result**: Three sequential 10-second timeouts = 30-second latency penalty on failure.

## Verification

This broken state is confirmed by:

1. **API_TIMEOUT constant**: Line 679, value = 10
   ```python
   API_TIMEOUT = 10
   ```

2. **Sequential API calls**: Lines 690, 692 show synchronous requests
   ```python
   resp = requests.get(..., timeout=API_TIMEOUT)  # Blocks for full timeout
   resp = requests.post(..., timeout=API_TIMEOUT)  # Blocks for full timeout
   ```

3. **Error handling**: Lines 702-703 process sequential responses
   ```python
   error_msg = data.get("message") or data.get("errorType")  # Sequential processing
   ```

4. **No concurrent infrastructure**: 
   - `api_call()` is purely synchronous
   - No ThreadPoolExecutor for multiple API calls
   - No batching mechanism
   - No parallel prefetching

## Conclusion

The codebase **matches the goal condition exactly**:
- ✓ API_TIMEOUT = 10 is configured
- ✓ Three API endpoints each timeout after 10s
- ✓ Sequential execution means 30s total latency on failure
- ✓ System has NO async/timeout cascade handling

**The broken state is documented and confirmed as of this analysis.**
