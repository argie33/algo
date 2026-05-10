# Data Validation Guide

**Created:** 2026-05-09  
**Purpose:** Ensure data integrity across all API endpoints

---

## Overview

This guide documents the runtime data validation system that:
- Validates API response data against defined schemas
- Sanitizes invalid values before sending to frontend
- Logs validation errors for debugging
- Prevents crashes from malformed data

---

## Architecture

### 1. Validation Rules (`utils/dataValidation.js`)

Pre-defined validation schemas for common data types:

```javascript
validationRules.signal = {
  symbol: v => typeof v === 'string' && v.length > 0,
  signal: v => ['BUY', 'SELL', 'HOLD', 'None'].includes(v),
  date: v => !isNaN(Date.parse(v)),
  entry_price: v => v === null || (typeof v === 'number' && v > 0),
  // ... more rules
}
```

### 2. Validation Functions

**validateField(value, rule)** - Validate single field
```javascript
const result = validateField(100, v => v > 0);
// Returns: { valid: true, errors: [] }
```

**validateObject(obj, schema)** - Validate entire object
```javascript
const result = validateObject(signal, validationRules.signal);
// Returns: { valid: true/false, errors: {...} }
```

**validateArray(arr, schema)** - Validate array of objects
```javascript
const result = validateArray(signals, validationRules.signal);
// Returns: { valid: true/false, errors: {...} }
```

### 3. Sanitization Functions

**sanitizeValue(value, rule)** - Replace invalid value with null
```javascript
const safe = sanitizeValue(-100, v => v > 0);
// Returns: null
```

**sanitizeObject(obj, schema)** - Remove invalid fields
```javascript
const clean = sanitizeObject(signal, validationRules.signal);
```

**sanitizeArray(arr, schema)** - Remove invalid array entries
```javascript
const clean = sanitizeArray(signals, validationRules.signal);
```

---

## Usage

### Adding Validation to an Endpoint

**Option 1: Manual Validation**

```javascript
const { validateArray } = require('../utils/dataValidation');

router.get('/signals', async (req, res) => {
  try {
    const result = await query('SELECT * FROM signals');
    const signals = result.rows;
    
    // Validate data
    const validation = validateArray(signals, validationRules.signal);
    if (!validation.valid) {
      console.warn('Invalid signals data:', validation.errors);
      // Sanitize before sending
      return sendPaginated(res, sanitizeArray(signals, validationRules.signal), {...});
    }
    
    return sendPaginated(res, signals, {...});
  } catch (error) {
    return sendError(res, error.message);
  }
});
```

**Option 2: Middleware-Based (Future)**

```javascript
const { createValidationMiddleware } = require('../middleware/dataValidationMiddleware');
const { validationRules } = require('../utils/dataValidation');

router.get('/signals',
  createValidationMiddleware(validationRules.signal),
  async (req, res) => {
    // validation happens automatically
  }
);
```

---

## Current Implementation Status

### ✅ Validation Framework Created
- [x] `utils/dataValidation.js` - Core validation logic
- [x] `middleware/dataValidationMiddleware.js` - Express middleware
- [x] Pre-defined schemas for common types

### ⏳ Integration Points (Optional)
Can be integrated into specific endpoints as needed:
- [ ] /api/signals endpoints
- [ ] /api/scores endpoints
- [ ] /api/financials endpoints
- [ ] Others as priority demands

### Recommended Priority for Integration
1. **High Priority:** Trading signals (most critical data)
2. **High Priority:** Portfolio positions (money-related)
3. **Medium Priority:** Financial metrics
4. **Medium Priority:** Market data

---

## Validation Rules by Type

### Stock/ETF Validation
```javascript
symbol: string, non-empty
price: number >= 0 or null
change: number or null
change_percent: number or null
```

### Trading Signal Validation
```javascript
symbol: string, non-empty
signal: one of [BUY, SELL, HOLD, None]
date: valid ISO date
entry_price: number > 0 or null
exit_price: number >= 0 or null
signal_quality_score: number 0-100 or null
```

### Position Validation
```javascript
symbol: string, non-empty
quantity: number > 0
entry_price: number > 0
current_price: number > 0
stop_loss: number > 0 or null
target_price: number > 0 or null
```

### Financial Metrics Validation
```javascript
symbol: string, non-empty
pe_ratio: number > 0 or null
pb_ratio: number > 0 or null
debt_to_equity: number >= 0 or null
current_ratio: number > 0 or null
roa: number or null
roe: number or null
```

### Market Data Validation
```javascript
vix: number >= 0 or null
breadth: number 0-100 or null
market_cap: number > 0 or null
```

---

## Error Handling

When validation fails, the system:
1. Logs the validation errors for debugging
2. Sanitizes the data (removes/nullifies invalid values)
3. Returns cleaned data to frontend
4. Prevents crashes from malformed data

Example log output:
```
Data validation failed for /api/signals: {
  0: {
    entry_price: ['Invalid value: -100']
  },
  2: {
    signal: ['Invalid value: "MAYBE"']
  }
}
```

---

## Adding New Validation Rules

To add validation for a new data type:

```javascript
// In utils/dataValidation.js
validationRules.myNewType = {
  field1: v => validation_rule_1,
  field2: v => validation_rule_2,
  // ...
};
```

Then use with:
```javascript
const result = validateObject(data, validationRules.myNewType);
```

---

## Testing

To test validation:

```javascript
const { validateArray, validationRules } = require('./utils/dataValidation');

const testSignals = [
  { symbol: 'AAPL', signal: 'BUY', date: '2026-05-09', entry_price: 100 },
  { symbol: 'TSLA', signal: 'INVALID', date: '2026-05-09', entry_price: -50 }
];

const result = validateArray(testSignals, validationRules.signal);
console.log(result);
// { valid: false, errors: { 1: { signal: [...], entry_price: [...] } } }
```

---

## Production Checklist

- [x] Validation utility created
- [x] Validation middleware created
- [x] Core validation rules defined
- [ ] Integrated into /api/signals endpoints
- [ ] Integrated into /api/positions endpoints
- [ ] Integrated into /api/financials endpoints
- [ ] Integrated into /api/scores endpoints
- [ ] Monitoring dashboard for validation errors
- [ ] Alerts for validation failures

---

## Future Enhancements

1. **Automated Schema Generation** - Auto-generate validation rules from database schema
2. **Validation Monitoring** - Dashboard showing validation errors over time
3. **Custom Validators** - Allow endpoints to define custom validation rules
4. **Type Guards** - TypeScript type guards for validated data
5. **Validation Metrics** - Track what data types fail validation most often

---

## Questions?

For questions about the validation system, see:
- `utils/dataValidation.js` - Implementation details
- `middleware/dataValidationMiddleware.js` - Middleware implementation
- Specific endpoints using validation
