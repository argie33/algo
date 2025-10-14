# Backend API Requirements: Value Components

## Overview
The frontend `ScoresDashboard.jsx` has been updated to display a comprehensive 5-component value score breakdown. The backend `/api/scores` endpoint needs to be enhanced to return the `value_components` object with detailed value metrics.

## Current State

### Frontend Expectations (ScoresDashboard.jsx lines 1405-1610)
The frontend expects each stock object to include a `value_components` object with:

**Component Scores (0-100 scale):**
- `pe_relative` - PE ratio relative to sector median score (max 20 points)
- `pb_relative` - PB ratio relative to sector median score (max 15 points)
- `ev_relative` - EV/EBITDA relative to sector median score (max 15 points)
- `peg_score` - PEG ratio score (max 25 points)
- `dcf_score` - DCF intrinsic value score (max 25 points)

**Sector Benchmarks:**
- `sector_pe` - Sector median PE ratio
- `sector_pb` - Sector median PB ratio
- `sector_ev` - Sector median EV/EBITDA

**Valuation Metrics:**
- `pb_ratio` - Price-to-Book ratio
- `ev_ebitda` - Enterprise Value / EBITDA
- `peg_ratio` - PEG ratio (PE / earnings_growth_pct)
- `dcf_intrinsic` - DCF intrinsic value per share
- `dcf_discount` - Discount/premium vs current price (as decimal, e.g., 0.25 = 25% undervalued)

### Current Backend Implementation (routes/scores.js)
Currently, the `/api/scores` endpoint returns (lines 142-186):
```javascript
{
  value_score: parseFloat(row.value_score) || 0,
  pe_ratio: parseFloat(row.pe_ratio) || null
}
```

And in the detailed view (lines 342-344):
```javascript
value: {
  score: parseFloat(row.value_score) || 0,
  components: { peRatio: parseFloat(row.pe_ratio) || null }
}
```

**This is insufficient for the frontend's needs.**

## Required Changes

### 1. Database Query Enhancement (routes/scores.js)

The SQL query needs to join additional tables to fetch the required data:

```sql
-- Add to the SELECT clause in both "/" and "/:symbol" routes:

-- From key_metrics table (already joined via stock_scores)
ss.trailing_pe,
km.price_to_book,
km.ev_to_ebitda,
km.price_to_sales_ttm,
km.earnings_growth_pct,

-- From company_profile for sector
cp.sector,

-- From sector_benchmarks
sb.pe_ratio as sector_pe_median,
sb.price_to_book as sector_pb_median,
sb.ev_to_ebitda as sector_ev_median,

-- From value_metrics for DCF intrinsic value
vm.dcf_intrinsic_value,
vm.fair_value

-- Add JOINs:
LEFT JOIN key_metrics km ON ss.symbol = km.ticker
LEFT JOIN sector_benchmarks sb ON cp.sector = sb.sector
LEFT JOIN (
  SELECT DISTINCT ON (symbol)
    symbol,
    dcf_intrinsic_value,
    fair_value,
    date
  FROM value_metrics
  ORDER BY symbol, date DESC
) vm ON ss.symbol = vm.symbol
```

**Note:** The `key_metrics` table uses `ticker` column, not `symbol`.

### 2. Response Mapping Enhancement

Update the response mapping in both routes to include:

```javascript
// In "/" route (list view), add to each stock object:
value_components: {
  // Component scores (calculated by loadstockscores.py, stored in stock_scores table)
  pe_relative: parseFloat(row.value_pe_relative) || null,
  pb_relative: parseFloat(row.value_pb_relative) || null,
  ev_relative: parseFloat(row.value_ev_relative) || null,
  peg_score: parseFloat(row.value_peg_score) || null,
  dcf_score: parseFloat(row.value_dcf_score) || null,

  // Sector benchmarks
  sector_pe: parseFloat(row.sector_pe_median) || null,
  sector_pb: parseFloat(row.sector_pb_median) || null,
  sector_ev: parseFloat(row.sector_ev_median) || null,

  // Valuation metrics
  pb_ratio: parseFloat(row.price_to_book) || null,
  ev_ebitda: parseFloat(row.ev_to_ebitda) || null,
  peg_ratio: row.earnings_growth_pct && row.trailing_pe
    ? parseFloat(row.trailing_pe) / parseFloat(row.earnings_growth_pct)
    : null,
  dcf_intrinsic: parseFloat(row.dcf_intrinsic_value) || null,
  dcf_discount: row.dcf_intrinsic_value && row.current_price
    ? (parseFloat(row.dcf_intrinsic_value) - parseFloat(row.current_price)) / parseFloat(row.current_price)
    : null
}
```

```javascript
// In "/:symbol" route (detail view), update factors.value:
factors: {
  value: {
    score: parseFloat(row.value_score) || 0,
    components: {
      // Component scores
      pe_relative: parseFloat(row.value_pe_relative) || null,
      pb_relative: parseFloat(row.value_pb_relative) || null,
      ev_relative: parseFloat(row.value_ev_relative) || null,
      peg_score: parseFloat(row.value_peg_score) || null,
      dcf_score: parseFloat(row.value_dcf_score) || null,

      // Sector benchmarks
      sector_pe: parseFloat(row.sector_pe_median) || null,
      sector_pb: parseFloat(row.sector_pb_median) || null,
      sector_ev: parseFloat(row.sector_ev_median) || null,

      // Valuation metrics
      pb_ratio: parseFloat(row.price_to_book) || null,
      ev_ebitda: parseFloat(row.ev_to_ebitda) || null,
      peg_ratio: row.earnings_growth_pct && row.trailing_pe
        ? parseFloat(row.trailing_pe) / parseFloat(row.earnings_growth_pct)
        : null,
      dcf_intrinsic: parseFloat(row.dcf_intrinsic_value) || null,
      dcf_discount: row.dcf_intrinsic_value && row.current_price
        ? (parseFloat(row.dcf_intrinsic_value) - parseFloat(row.current_price)) / parseFloat(row.current_price)
        : null
    }
  },
  // ... other factors
}
```

### 3. Alternative Approach: Store Components in Database

**Recommended:** Instead of calculating component scores in the API layer, store them in the `stock_scores` table when `loadstockscores.py` runs.

Add these columns to `stock_scores` table:
```sql
ALTER TABLE stock_scores ADD COLUMN IF NOT EXISTS value_pe_relative DOUBLE PRECISION;
ALTER TABLE stock_scores ADD COLUMN IF NOT EXISTS value_pb_relative DOUBLE PRECISION;
ALTER TABLE stock_scores ADD COLUMN IF NOT EXISTS value_ev_relative DOUBLE PRECISION;
ALTER TABLE stock_scores ADD COLUMN IF NOT EXISTS value_peg_score DOUBLE PRECISION;
ALTER TABLE stock_scores ADD COLUMN IF NOT EXISTS value_dcf_score DOUBLE PRECISION;
```

Then modify `loadstockscores.py` (lines 637-803) to store the component scores:
```python
# After calculating value_score, store components
cur.execute("""
    UPDATE stock_scores
    SET
        value_pe_relative = %s,
        value_pb_relative = %s,
        value_ev_relative = %s,
        value_peg_score = %s,
        value_dcf_score = %s
    WHERE symbol = %s
""", (pe_score, pb_score, ev_score, peg_score, dcf_score, symbol))
```

**Benefits:**
- Simpler API code (just SELECT and map)
- Consistent with how `momentum_components` and `positioning_components` work
- Easier debugging (component scores visible in database)
- Better performance (no calculation in API)

## Data Sources

### Tables Required
1. **stock_scores** - Main scores table (contains `value_score`)
2. **key_metrics** - Contains `trailing_pe`, `price_to_book`, `ev_to_ebitda`, `earnings_growth_pct`
   - ⚠️ Uses `ticker` column, not `symbol`
3. **company_profile** - Contains `sector`, `short_name`
   - ⚠️ Uses `ticker` column, not `symbol`
4. **sector_benchmarks** - Contains sector medians: `pe_ratio`, `price_to_book`, `ev_to_ebitda`
5. **value_metrics** - Contains `dcf_intrinsic_value`, `fair_value`

### Type Conversions
⚠️ **Important:** PostgreSQL returns `DOUBLE PRECISION` columns as JavaScript `Decimal` objects. Always use `parseFloat()` when mapping to response objects.

## Testing

After implementing changes:

1. **Test list endpoint:**
   ```bash
   curl http://localhost:3001/api/scores | jq '.data.stocks[0].value_components'
   ```

   Expected output:
   ```json
   {
     "pe_relative": 7.1,
     "pb_relative": 0.0,
     "ev_relative": 0.0,
     "peg_score": 12.5,
     "dcf_score": 12.5,
     "sector_pe": 25.3,
     "sector_pb": 3.2,
     "sector_ev": 15.7,
     "pb_ratio": 39.5,
     "ev_ebitda": 31.7,
     "peg_ratio": 1.15,
     "dcf_intrinsic": 180.50,
     "dcf_discount": 0.05
   }
   ```

2. **Test detail endpoint:**
   ```bash
   curl http://localhost:3001/api/scores/AAPL | jq '.data.factors.value'
   ```

   Expected output:
   ```json
   {
     "score": 42.1,
     "components": {
       "pe_relative": 7.1,
       "pb_relative": 0.0,
       // ... all value_components fields
     }
   }
   ```

3. **Frontend integration test:**
   - Open `http://localhost:3000/scores` in browser
   - Click on any stock to view details
   - Verify "Value Assessment (5-Component)" section shows:
     - Component breakdown list
     - Valuation ratios with sector comparisons
     - 5-component bar chart
     - Detailed component table

## Implementation Priority

### Phase 1: Database Schema (if using recommended approach)
1. Add component columns to `stock_scores` table
2. Modify `loadstockscores.py` to store component scores
3. Run `loadstockscores.py` locally to populate data

### Phase 2: API Enhancement
1. Add JOINs to fetch valuation metrics and sector benchmarks
2. Map `value_components` object in response
3. Test with curl and verify JSON structure

### Phase 3: Frontend Verification
1. Test frontend display with real data
2. Verify charts render correctly
3. Confirm sector comparisons display properly

## Related Files

- **Frontend:** `/home/stocks/algo/webapp/frontend/src/pages/ScoresDashboard.jsx` (lines 1405-1610)
- **Backend API:** `/home/stocks/algo/webapp/lambda/routes/scores.js` (lines 21-417)
- **Score Calculator:** `/home/stocks/algo/loadstockscores.py` (lines 637-803)
- **Value Metrics Loader:** `/home/stocks/algo/calculate_value_metrics.py` (entire file)

## Questions?

Contact the development team or refer to the conversation history for implementation details and test results.

---
**Last Updated:** 2025-10-12
**Status:** Documentation Complete - Implementation Pending
