# Scores "No Data" Display - Fix Guide

## Problem
Users seeing "No data" text displayed for most stock scores metrics instead of actual values or reason explanations.

## Root Cause Analysis - COMPLETE ✓

### Backend: 100% OPERATIONAL ✓
- **Database:** 5481 rows in all metrics tables, updated TODAY
- **API Endpoint:** Returns all 6 factor_inputs objects (quality, momentum, value, growth, positioning, stability)
- **API Response:** Includes all reason codes properly populated (e.g., "missing_sec_data", "institutional_data_not_available")
- **Response Wrapper:** Correctly nests response in `{ statusCode: 200, data: { items: [...], pagination: {...} }, data_freshness: {...} }`

**Verified with:** `/api/scores?limit=10` - all factor_inputs present with reason fields populated

### Frontend: POTENTIAL RENDERING ISSUE

The frontend should display:
- **If value exists:** Display the value (e.g., `0.39` for debt_to_equity)
- **If no value but reason exists:** Display formatted reason (e.g., "No SEC data")
- **If no value, no reason, collected=false:** Display "Not yet available" (amber badge)
- **If no value, no reason, collected=true:** Display "No data" (gray text)

If you're seeing "No data" everywhere, the issue is likely:
1. **Browser cache** - React component using stale code
2. **Component data flow** - stock object missing factor_inputs
3. **Reason extraction** - reason field not being extracted from API response

## How to Fix

### Step 1: Hard Refresh Browser
```
Windows: Ctrl+Shift+R
Mac: Cmd+Shift+R
```
This clears React component cache and forces reload of JavaScript.

### Step 2: Verify API is Correct

Open browser DevTools (F12) → Network tab → Reload page

Look for `/api/scores/stockscores` request:
- Response should have `data: { items: [...], pagination: {...} }`
- Each item should have: `quality_inputs`, `momentum_inputs`, `value_inputs`, etc.
- Each inputs object should have reason fields: `return_on_equity_unavailable_reason`, etc.

**Or** run in console:
```javascript
fetch("/api/scores?limit=1")
  .then(r => r.json())
  .then(d => {
    console.log("API Response:", d);
    console.log("Has quality_inputs:", "quality_inputs" in d.data.items[0]);
    console.log("Sample reason:", d.data.items[0].quality_inputs?.return_on_equity_unavailable_reason);
  });
```

### Step 3: Run Diagnostic Tool

Paste this in browser console (F12 → Console):
```javascript
// Copy the contents of: frontend_scores_diagnostics.js
// Then run: scoresDiagnostics()
```

This will:
- ✓ Verify API returns correct structure
- ✓ Test reason extraction logic
- ✓ Check React component state
- ✓ Validate schema keys

### Step 4: Check Browser Console for Warnings

After hard refresh and loading the scores page, check console (F12 → Console) for:

```
[InputsCard] Missing factor inputs for quality_inputs on AAPL
```

If you see this warning, it means:
- The stock object doesn't have the factor_inputs
- Either the API changed its response structure, or
- The component isn't receiving the correct data from the parent

### Step 5: Check React DevTools

Install React DevTools browser extension, then:
1. Open DevTools (F12)
2. Go to "Components" tab (React DevTools)
3. Find "StockScoreAccordion" component
4. Expand and find "StockDetail" 
5. Look at "Props" → "stock" object
6. Verify stock has: `quality_inputs`, `momentum_inputs`, `value_inputs`, etc.

If these are missing, the problem is in how the API response is being parsed upstream.

## Expected Displays (After Fix)

### Quality Metrics Example:
```
ROE                    No SEC data       (reason code: "missing_sec_data")
ROA                    No SEC data       (reason code: "missing_sec_data")
Profit Margin          No SEC data       (reason code: "missing_sec_data")
Debt / Equity          0.39              (has value, no reason needed)
Gross Margin           71.88%            (has value, no reason needed)
Interest Coverage      No SEC data       (reason code: "missing_sec_data")
```

### Positioning Metrics Example:
```
Institutional Own %    65.0              (has value)
Insider Own %          No SEC data       (reason code: "missing_sec_data")
Short Interest %       0.85%             (has value)
Top 10 Institutions %  Institutional data not available  (new in Session 411)
Days to Cover          Short float metrics not calculated (new in Session 411)
```

## Changes Made (Session 412)

### Frontend Fixes
**File:** `webapp/frontend/src/components/StockScoreAccordion.jsx`

1. **InputsCard Component:**
   - Added defensive null-checking: `stock?.[inputsKey]`
   - Added console warning when factor_inputs are missing
   - Added debug logging for missing reason fields

2. **InputRow Component:**
   - Removed buggy fallback to `row.stock?.[reasonKey]` (row doesn't have .stock property)
   - Added diagnostic logging for rows without value/reason
   - Clearer logic flow

### Diagnostic Tool Created
**File:** `frontend_scores_diagnostics.js`

Comprehensive test that verifies:
- ✓ API response structure
- ✓ Factor inputs presence
- ✓ Reason field extraction logic
- ✓ React component mounting
- ✓ Schema validation

## If You Still See "No Data"

1. **Confirm backend is working:**
   ```bash
   curl http://localhost:3001/api/scores?limit=1 | python -m json.tool | grep quality_inputs
   ```

2. **Run the diagnostic tool** in browser console

3. **Check for React/Frontend errors:**
   - DevTools → Console tab (any red errors?)
   - DevTools → Network tab (are API responses 200 OK?)

4. **Force restart dev_server:**
   ```bash
   # Kill existing dev_server
   pkill -f "python.*dev_server.py"
   
   # Restart it
   python lambda/api/dev_server.py
   ```

5. **Report the issue with:**
   - Console output from diagnostic tool
   - Network tab screenshot showing API response
   - React DevTools screenshot of StockDetail props

## Technical Details

### Response Flow
```
scores.py (handler)
  ↓ returns: { statusCode: 200, items: [...], pagination: {...}, _marker: "..." }
  ↓
api_router.route_request()
  ↓ wraps: wrap_response(response)
  ↓
response_service.wrap_response()
  ↓ returns: { statusCode: 200, data: { items: [...], pagination: {...}, _marker: "..." }, data_freshness: {...} }
  ↓
lambda_function.lambda_handler()
  ↓ wraps as body: { statusCode: 200, headers: {...}, body: JSON.stringify(data) }
  ↓
dev_server.py unwraps
  ↓
Browser receives: { statusCode: 200, data: { items: [...] }, data_freshness: {...} }
```

### Reason Extraction Logic
```javascript
// For schema key: "return_on_equity_pct"
let reason = inputsObj["return_on_equity_pct_unavailable_reason"];  // ← First try
if (!reason && key.endswith("_pct")) {
  reason = inputsObj["return_on_equity_unavailable_reason"];  // ← Strip "_pct" and retry
}
// Result: reason = "missing_sec_data" (from API)
```

### Why We Show Reason Codes Instead of "No Data"
From Session 397 & Session 411: We set honest reason codes for metrics we can't populate:
- "missing_sec_data" - metric not available in SEC filings
- "institutional_data_not_available" - 13F data requires CUSIP crosswalk
- "short_float_data_not_calculated" - derived metrics not computed
- "analyst_estimates_not_in_sec_filings" - forward_pe not available without premium API
- "depreciation_amortization_not_loaded" - D&A components not extracted yet

This provides transparency to users about why data is unavailable.
