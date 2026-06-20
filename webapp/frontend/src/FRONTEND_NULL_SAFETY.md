# Frontend Null/Undefined Safety Fix

## Problem Statement

20+ stateful components with `useState`/`useCallback`/`useEffect` handle critical financial calculations (portfolio value, position P&L, target prices) without null/undefined safety. These components fail silently:

- Portfolio value renders as `undefined` or `NaN`
- Position P&L calculations divide by zero or null values
- Target price calculations show `NaN` in the UI without crashing
- No error visibility to users or developers

## Root Causes

1. **Unsafe arithmetic**: Division by zero, null operands, NaN propagation
2. **Unsafe array operations**: Reducing null values, filtering missing fields
3. **Unsafe property access**: Accessing nested fields without type checking
4. **No centralized validation**: Each component implements its own (inconsistent) null checks

## Solution Overview

### Three-Layer Approach

#### 1. **Safe Calculation Utilities** (`utils/safeCalculations.js`)

Provides functions that never throw and always return valid defaults:

```javascript
import {
  toSafeNumber,        // Converts value to number or returns default
  safeDivide,          // Division with zero-check
  safePercentage,      // (part / whole) * 100 with guards
  safeAccumulate,      // Sum array values safely
  safePnlPercentage,   // (pnl / value) * 100
  safeGet,             // Nested property access with defaults
} from '../utils/safeCalculations';

// Usage
const unrealizedPnl = toSafeNumber(data.pnl, 0);           // → 0 if null/NaN
const totalValue = safeAccumulate(positions, 'value', 0);  // → 0 if all null
const pnlPct = safePnlPercentage(unrealizedPnl, totalValue); // → null if invalid
```

#### 2. **Safe Data Hooks** (`hooks/useSafeFinancialData.js`)

Wraps `useApiQuery` with automatic schema validation and normalization:

```javascript
const { normalizedData } = useSafeFinancialData(
  ['positions'],
  () => api.get('/api/positions'),
  {
    schema: {
      positions: [],
      portfolio: { total_value: 0, unrealized_pnl_dollars: 0 }
    }
  }
);

// normalizedData is guaranteed to match schema, no nulls
```

#### 3. **Component Patterns**

Update components to use utilities:

**Before:**
```jsx
const totalValue = positions.reduce((s, p) => s + (p.position_value || 0), 0);
const pnlPct = totalValue > 0 ? (unrealizedPnl / totalValue * 100) : null;
```

**After:**
```jsx
import { safeAccumulate, safePnlPercentage } from '../utils/safeCalculations';

const totalValue = safeAccumulate(positions, 'position_value', 0);
const pnlPct = safePnlPercentage(unrealizedPnl, totalValue);
```

## Implementation Guide

### Step 1: Use Safe Calculations in Components

For arithmetic operations:

```javascript
// ❌ Before
const pnlPercent = unrealizedPnl / totalValue * 100;  // NaN if totalValue is null
const distance = target - current / current * 100;    // Divide by zero risk

// ✅ After
import { safeDivide, safePercentage } from '../utils/safeCalculations';

const pnlPercent = safePercentage(unrealizedPnl, totalValue);
const distance = safePercentage(target - current, current);
```

For array accumulation:

```javascript
// ❌ Before
const total = items.reduce((s, i) => s + i.value, 0);  // NaN if value is null

// ✅ After
import { safeAccumulate } from '../utils/safeCalculations';

const total = safeAccumulate(items, 'value', 0);
```

For property access:

```javascript
// ❌ Before
const price = data.position.current_price;  // Error if position is null

// ✅ After
import { safeGet } from '../utils/safeCalculations';

const price = safeGet(data, 'position.current_price', 0);
```

### Step 2: Validate Financial Data

When fetching position/portfolio data:

```javascript
import { useSafeFinancialData } from '../hooks/useSafeFinancialData';

const { normalizedData } = useSafeFinancialData(
  ['portfolio-data'],
  () => api.get('/api/portfolio'),
  {
    schema: {
      positions: [],
      portfolio: {
        total_value: 0,
        unrealized_pnl_dollars: 0,
        unrealized_pnl_pct: 0,
      }
    }
  }
);

// normalizedData guarantees all fields exist with correct types
const { positions, portfolio } = normalizedData;
```

### Step 3: Use High-Level Helpers

For common calculations:

```javascript
import { useSafePortfolioCalculations } from '../hooks/useSafeFinancialData';

const calculations = useSafePortfolioCalculations(positions, portfolio);

console.log(calculations.totalValue);      // Number, never NaN
console.log(calculations.pnlPct);          // Number or null, never NaN
console.log(calculations.positionCount);   // Number, never NaN
console.log(calculations.hasValidData);    // Boolean flag
```

## API Reference

### Safe Calculations

| Function | Input | Returns | Behavior |
|----------|-------|---------|----------|
| `toSafeNumber(val, default)` | any | number | NaN/null → default |
| `safeDivide(num, den, default)` | any, any, any | number | Divide by zero → default |
| `safePercentage(part, whole, default)` | any, any, any | number | 0/null → default |
| `safeSum(array, default)` | any[], any | number | Null values skipped |
| `safeAccumulate(items, accessor, default)` | any[], string/fn, any | number | Filters null |
| `safeGet(obj, path, default)` | any, string, any | any | Missing path → default |
| `safeGetArray(data, path, default)` | any, string, any[] | any[] | Invalid → default |

### Safe Hooks

| Hook | Purpose | Returns |
|------|---------|---------|
| `useSafeFinancialData()` | Schema-validated API data | `{ data, normalizedData, loading, error, refetch }` |
| `useSafePortfolioCalculations()` | Portfolio metrics | `{ totalValue, pnlPct, totalRisk, positionCount, hasValidData, ... }` |
| `useSafePerformanceMetrics()` | Performance metrics | `{ totalReturn, winRate, sharpe, sortino, ... }` |
| `useSafeFormatting()` | Display formatting | `{ formatPrice, formatPercent, formatNumber, formatRMultiple, ... }` |

## Migration Checklist

For each component handling financial data:

- [ ] Import safe calculation utilities
- [ ] Replace raw arithmetic with safe functions
- [ ] Replace direct property access with `safeGet()`
- [ ] Replace array reduce with `safeAccumulate()`
- [ ] Add unit tests for null/undefined inputs
- [ ] Test with incomplete API responses (missing fields)
- [ ] Verify no `NaN` or `undefined` renders in UI
- [ ] Check console for warnings about missing fields

## Testing

### Unit Tests

Created in `utils/safeCalculations.test.js`. Run with:

```bash
npm test -- safeCalculations.test.js
```

Coverage includes:
- ✅ Valid number conversions
- ✅ Null/undefined handling
- ✅ NaN rejection
- ✅ Division by zero
- ✅ Array accumulation with sparse data
- ✅ Nested property access with missing fields
- ✅ Integration tests (full portfolio calculations)

### Manual Testing Scenarios

#### Scenario 1: Null portfolio value
```javascript
// API returns
{ portfolio: { unrealized_pnl_dollars: 100, total_value: null } }

// Component should show
<div>Unrealized P&L: — (not "undefined" or "NaN")</div>
```

#### Scenario 2: Missing position fields
```javascript
// Position missing stop_loss_price
{ symbol: 'AAPL', current_price: 150, stop_loss_price: null }

// Calculation should handle gracefully
safeGet(position, 'stop_loss_price', 0)  // → 0
```

#### Scenario 3: Empty positions array
```javascript
// API returns empty positions
{ positions: [] }

// Calculations should not crash
const total = safeAccumulate([], 'position_value', 0);  // → 0
```

## Common Pitfalls

### ❌ Unsafe Patterns (Avoid)

```javascript
// Direct division
const ratio = a / b;  // NaN if b is null

// Chained property access
const price = data.position.current_price;  // Error if position is null

// Unsafe reduce
const sum = items.reduce((s, i) => s + i.val, 0);  // NaN if val is null

// Type coercion
const num = parseInt(value);  // NaN if value is non-numeric string

// Conditional without null check
value > 0 ? 'up' : 'down'  // Error if value is null
```

### ✅ Safe Patterns (Use)

```javascript
// Safe division
const ratio = safeDivide(a, b, 0);

// Safe property access
const price = safeGet(data, 'position.current_price', 0);

// Safe accumulation
const sum = safeAccumulate(items, 'val', 0);

// Safe conversion
const num = toSafeNumber(value, 0);

// Safe comparison
const direction = toSafeNumber(value, 0) > 0 ? 'up' : 'down';
```

## Performance Considerations

- **No runtime cost**: All functions are O(1) or O(n) with minimal overhead
- **Memoization**: Use `useMemo` for expensive calculations
- **Component updates**: Safe calculations don't trigger extra renders
- **Memory**: No circular references or memory leaks

## Deprecations & Removals

None. Safe calculation functions coexist with existing code. Migration is gradual:

1. New components use safe utilities
2. Existing components updated incrementally
3. Old patterns eventually phased out

## Related Documentation

- [Data Validation Guide](../utils/dataValidation.js)
- [Decimal Math Utilities](../utils/decimalMath.js)
- [Dashboard Formatters](../components/dashboard/shared/utils/dashboardFormatters.js)

## Support & Troubleshooting

### "Warning: Each child in a list should have a unique key prop"
- Not related to null safety, but often appears alongside. Use `index` as fallback: `<div key={index} />`

### "NaN is not a valid number"
- This means a calculation returned NaN. Check:
  1. Is the input null/undefined?
  2. Is there a divide by zero?
  3. Is a property missing from the object?
- Use `isValidCalculation()` to check before rendering.

### "Cannot read property 'X' of null"
- Missing null check. Use `safeGet(obj, 'X', default)` instead of `obj.X`.

### Test failures with incomplete mock data
- Add missing fields to mocks using the schema pattern
- Or use `buildSafeObject()` to create valid mocks

## Examples

See `/pages/PortfolioDashboard.jsx` for comprehensive migration example using:
- Safe portfolio calculations
- Safe formatting
- Safe data access patterns
- Complete null/undefined handling
