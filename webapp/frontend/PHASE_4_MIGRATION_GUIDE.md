# Phase 4: Frontend Data Validation Migration Guide

## Overview

This guide explains how to systematically replace `?? 0` fallback patterns with the new `SafeMetric` infrastructure for proper data validation in React components.

## Completed Infrastructure

### 1. **useDataValidation Hook** (`src/hooks/useDataValidation.js`)

Validates API response data and checks for DataError discriminator pattern.

```javascript
import { useDataValidation, useHasDataErrors } from '../hooks/useDataValidation';

// Check if a single value is valid
const { isValid, hasError, value, error } = useDataValidation(apiData, 'portfolio.value');

// Check multiple fields
const { isValid, errors, values } = useDataValidationMultiple({
  price: data.price,
  quantity: data.quantity,
});

// Quick check for error responses
if (useHasDataErrors(response)) {
  // Handle error state
}
```

### 2. **SafeMetric Components** (`src/components/SafeMetric.jsx`)

Three components for safe metric display:

#### SafeMetric (Full Component)
```javascript
import { SafeMetric } from '../components/SafeMetric';

<SafeMetric
  value={portfolio.value}
  label="Portfolio Value"
  formatter="money"
  fallback="—"
  showError={dataError !== null}
  errorMessage={dataError?.message}
/>
```

#### SafeMetricValue (String Only)
```javascript
import { SafeMetricValue } from '../components/SafeMetric';

const formatted = SafeMetricValue({
  value: perf?.win_rate,
  formatter: 'percentage',
  fallback: '—'
});

// In JSX:
{formatted}%
```

#### SafeMetricInline (Label + Value)
```javascript
import { SafeMetricInline } from '../components/SafeMetric';

<SafeMetricInline
  label="Win Rate"
  value={perf?.win_rate}
  formatter="percentage"
/>
```

## Migration Patterns

### Pattern 1: Direct JSX Output

**Before:**
```javascript
<span className="mono">{perf?.win_rate ?? 0}%</span>
```

**After:**
```javascript
import { SafeMetricValue } from '../components/SafeMetric';

<span className="mono">
  {SafeMetricValue({ value: perf?.win_rate, fallback: '0' })}%
</span>
```

### Pattern 2: Template Strings

**Before:**
```javascript
sub={`${metrics.reddit?.mention_count ?? 0} mentions`}
```

**After:**
```javascript
import { SafeMetricValue } from '../components/SafeMetric';

sub={`${SafeMetricValue({ value: metrics.reddit?.mention_count, fallback: '0' })} mentions`}
```

### Pattern 3: Variable Assignment + Calculation

**Before:**
```javascript
const vixValue = market.vix ?? 0;
const distDays = market.distribution_days ?? 0;
```

**After:**
```javascript
import { SafeMetricValue } from '../components/SafeMetric';

const vixValue = SafeMetricValue({ value: market.vix, fallback: 0 });
const distDays = SafeMetricValue({ value: market.distribution_days, fallback: 0 });
```

### Pattern 4: Formatter Functions

**Before:**
```javascript
<span className="mono">
  {fmtMoneyShort(perf?.total_losses_dollars ?? 0)}
</span>
```

**After:**
```javascript
import { SafeMetricValue } from '../components/SafeMetric';

<span className="mono">
  {fmtMoneyShort(
    SafeMetricValue({ value: perf?.total_losses_dollars, fallback: 0 })
  )}
</span>
```

## Formatter Options

`SafeMetricValue` supports shortcut formatters:

- `formatter="percentage"` → `"12.34%"`
- `formatter="money"` → `"$1,234.56"`
- `formatter="number"` → `"1,234"`
- `formatter="decimal2"` → `"12.34"`

Or custom formatter function:
```javascript
SafeMetricValue({
  value: data,
  format: (v) => `${v} units`
})
```

## Fallback Values

Choose fallbacks that make sense for the data:

- **Missing percentages**: `fallback: '0'` (string for display)
- **Missing counts**: `fallback: '0'` (string for display)
- **Missing prices/currency**: `fallback: 0` (number for calculations)
- **Missing text**: `fallback: '—'` (em dash for UI)

## Files Requiring Migration

### High Priority (Display-Critical)
1. `StockDetail.jsx` - 7 instances
2. `EconomicDashboard.jsx` - 3 instances
3. `TradingSignals.jsx` - 2 instances

### Medium Priority (Data Calculation)
1. `BacktestResults.jsx` - 2 instances
2. `SwingCandidates.jsx` - 1 instance

### Utility Files (Data Processing)
1. `utils/dataValidation.js` - 3 instances
2. `utils/safeCalculations.js` - 1 instance
3. `utils/responseNormalizer.js` - 4 instances

### Already Completed ✅
- `PortfolioDashboard.jsx` - 8/12 instances updated
- `Sentiment.jsx` - 11/12 instances updated
- `MarketsHealth.jsx` - Import added, ready for updates

## Migration Checklist

- [ ] Review the file for all `?? 0` patterns (use `grep -n "?? 0" filename.jsx`)
- [ ] Add import: `import { SafeMetricValue } from '../components/SafeMetric';`
- [ ] Identify the pattern type (direct output, template, variable, formatter)
- [ ] Apply the corresponding migration pattern
- [ ] Test in dev server to ensure display is correct
- [ ] Run `npm run lint` to check for linting issues
- [ ] Verify that error states are handled properly

## Testing Strategies

### 1. Visual Regression Testing
```bash
# Run dev server and manually verify charts/metrics look correct
npm run dev
```

### 2. Error Response Testing
```javascript
// Verify components handle DataError responses gracefully
const mockErrorResponse = {
  isDataError: true,
  message: 'Price data unavailable'
};

// Component should display fallback or error message
```

### 3. Edge Cases
- Test with `null` values
- Test with `undefined` values
- Test with `0` values (should display "0", not fallback)
- Test with DataError objects

## Integration with Error Boundaries

SafeMetric works seamlessly with existing error boundaries:

```javascript
import { SafeMetric } from '../components/SafeMetric';
import ErrorBoundary from '../components/ErrorBoundary';

<ErrorBoundary>
  <SafeMetric
    value={data?.price}
    label="Price"
    showError={hasDataError}
  />
</ErrorBoundary>
```

## Performance Considerations

- `SafeMetricValue` is memoized internally
- For high-frequency updates (charts), extract values once outside render
- Use `SafeMetricInline` for string-only metrics to avoid JSX overhead

```javascript
// ✅ Good: Extract once
const displayValue = SafeMetricValue({ value: perf?.win_rate, fallback: '0' });
return <span>{displayValue}%</span>;

// ❌ Avoid: Recalculating in every render
return <span>{SafeMetricValue({ value: perf?.win_rate, fallback: '0' })}%</span>;
```

## Common Mistakes to Avoid

1. **Fallback type mismatch**: Don't mix string/number fallbacks
   ```javascript
   // ❌ Wrong
   SafeMetricValue({ value: count, fallback: '—' }) // Passing string to formatter="number"
   
   // ✅ Correct
   SafeMetricValue({ value: count, fallback: '0', formatter: 'number' })
   ```

2. **Forgetting import**: Always import from `../components/SafeMetric`

3. **Double-wrapping**: Don't wrap SafeMetricValue in another safety layer
   ```javascript
   // ❌ Wrong
   const safe = SafeMetricValue({ ... }) ?? 0;
   
   // ✅ Correct
   const safe = SafeMetricValue({ ... }); // Already safe
   ```

4. **Conditional rendering**: SafeMetricValue handles null/undefined, no need for extra checks
   ```javascript
   // ❌ Unnecessary
   {data?.value ? SafeMetricValue({ value: data.value }) : '—'}
   
   // ✅ Cleaner
   {SafeMetricValue({ value: data?.value, fallback: '—' })}
   ```

## Next Steps

1. **Immediate**: Update remaining 50+ components using this guide
2. **Testing**: Run full dashboard test suite with error scenarios
3. **Documentation**: Add SafeMetric usage to component library docs
4. **Monitoring**: Track data validation errors in production logs

## Support & Questions

Refer to:
- `useDataValidation.js` - Hook implementation with JSDoc comments
- `SafeMetric.jsx` - Component implementation with examples
- `PortfolioDashboard.jsx` - Real-world usage example
- `Sentiment.jsx` - Template string patterns example

## Success Criteria

✅ All `?? 0` patterns replaced with `SafeMetricValue`
✅ No silent data masking when values are missing
✅ Components render correctly with fallback values
✅ Error states display properly
✅ No performance regression in dashboard load time
✅ All tests pass (unit + integration + E2E)
