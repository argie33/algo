/**
 * Strict Validators - Replace || 0 and ?? 0 patterns
 *
 * For finance applications, missing or invalid data must raise errors, not default.
 * These validators return either a valid value or a DataError object.
 *
 * Usage: const price = requirePrice(symbol, value); if (isDataError(price)) check error flag
 */

const { DataError, isDataError } = require('./errorEnvelopes');

/**
 * Require a numeric field to be present and valid
 * Replaces: value || 0, value ?? 0, parseFloat(value) || 0
 *
 * @param {*} value - Value to validate
 * @param {string} fieldName - Field name for error reporting
 * @param {Object} opts - { min, max, allowZero }
 * @returns {number|DataError} Valid number or DataError
 */
function requireNumericField(value, fieldName, opts = {}) {
  const { min, max, allowZero = true } = opts;

  // Check for missing value
  if (value === null || value === undefined) {
    return new DataError(fieldName, 'missing', {
      expected: 'number',
      why: 'Field is required'
    });
  }

  // Parse to number
  const parsed = parseFloat(value);
  if (isNaN(parsed)) {
    return new DataError(fieldName, 'invalid', {
      value,
      expected: 'number',
      why: 'Value cannot be converted to a number'
    });
  }

  // Check zero constraint
  if (!allowZero && parsed === 0) {
    return new DataError(fieldName, 'invalid', {
      value: parsed,
      why: 'Field cannot be zero'
    });
  }

  // Check min/max bounds
  if (min !== undefined && parsed < min) {
    return new DataError(fieldName, 'out_of_range', {
      value: parsed,
      min,
      why: `Must be >= ${min}`
    });
  }

  if (max !== undefined && parsed > max) {
    return new DataError(fieldName, 'out_of_range', {
      value: parsed,
      max,
      why: `Must be <= ${max}`
    });
  }

  return parsed;
}

/**
 * Require a price field (stricter than requireNumericField)
 * Prices must be positive, cannot use || 150 fallback
 *
 * @param {string} symbol - Stock symbol (for error context)
 * @param {*} price - Price value to validate
 * @param {string} context - Where this price is used (e.g., 'order_cost_estimation')
 * @returns {number|DataError} Valid price or DataError
 */
function requirePrice(symbol, price, context = '') {
  if (!price || isNaN(price) || price <= 0) {
    return new DataError('price', 'invalid', {
      symbol,
      value: price,
      context,
      min: 0.01,
      why: 'Price data missing or invalid - cannot use estimated fallback in finance context'
    });
  }

  return parseFloat(price);
}

/**
 * Require portfolio value to be present and positive
 * Portfolio value missing = cannot calculate exposures, positions, metrics
 *
 * @param {*} value - Portfolio value
 * @returns {number|DataError}
 */
function requirePortfolioValue(value) {
  if (value === null || value === undefined) {
    return new DataError('portfolio_value', 'missing', {
      why: 'Cannot calculate metrics without portfolio value'
    });
  }

  const parsed = parseFloat(value);
  if (isNaN(parsed) || parsed <= 0) {
    return new DataError('portfolio_value', 'invalid', {
      value,
      min: 0.01,
      why: 'Portfolio value must be positive'
    });
  }

  return parsed;
}

/**
 * Require a signal quality metric
 * Quality score cannot default to 0 (looks like "no signal")
 *
 * @param {*} value - Raw quality score
 * @returns {number|DataError}
 */
function requireSignalQuality(value) {
  if (value === null || value === undefined) {
    return new DataError('raw_score', 'missing', {
      why: 'Signal quality score not calculated'
    });
  }

  const parsed = parseFloat(value);
  if (isNaN(parsed)) {
    return new DataError('raw_score', 'invalid', {
      value,
      why: 'Signal quality must be numeric'
    });
  }

  // Quality scores are typically -100 to 100 or 0 to 100
  if (parsed < -100 || parsed > 100) {
    return new DataError('raw_score', 'out_of_range', {
      value: parsed,
      min: -100,
      max: 100,
      why: 'Signal quality score out of expected range'
    });
  }

  return parsed;
}

/**
 * Require market exposure percentage
 * Exposure cannot default to 0% (misleads about risk)
 *
 * @param {*} value - Exposure percentage (0-100 or 0-1)
 * @returns {number|DataError}
 */
function requireExposure(value) {
  if (value === null || value === undefined) {
    return new DataError('exposure_pct', 'missing', {
      why: 'Market exposure percentage not available'
    });
  }

  const parsed = parseFloat(value);
  if (isNaN(parsed)) {
    return new DataError('exposure_pct', 'invalid', {
      value,
      why: 'Exposure must be numeric'
    });
  }

  // Typically 0-100 for percentage, or 0-1 for decimal
  if (parsed < 0 || parsed > 100) {
    if (parsed < 0 || parsed > 1) {
      // If it's not in either range, it's invalid
      return new DataError('exposure_pct', 'out_of_range', {
        value: parsed,
        expected_range: '0-100% or 0-1.0',
        why: 'Exposure percentage out of valid range'
      });
    }
  }

  return parsed;
}

/**
 * Require position count to be valid
 * Position count cannot be NULL or negative
 *
 * @param {*} value - Number of positions
 * @returns {number|DataError}
 */
function requirePositionCount(value) {
  if (value === null || value === undefined) {
    return new DataError('position_count', 'missing', {
      why: 'Position count not available'
    });
  }

  const parsed = parseInt(value, 10);
  if (isNaN(parsed) || parsed < 0) {
    return new DataError('position_count', 'invalid', {
      value,
      min: 0,
      why: 'Position count must be non-negative integer'
    });
  }

  return parsed;
}

/**
 * Require unrealized P&L percentage to be valid
 * Unrealized P&L missing = cannot calculate portfolio performance
 *
 * @param {*} value - Unrealized P&L percentage
 * @returns {number|DataError}
 */
function requireUnrealizedPnl(value) {
  if (value === null || value === undefined) {
    return new DataError('unrealized_pnl_pct', 'missing', {
      why: 'Unrealized P&L not available'
    });
  }

  const parsed = parseFloat(value);
  if (isNaN(parsed)) {
    return new DataError('unrealized_pnl_pct', 'invalid', {
      value,
      why: 'Unrealized P&L must be numeric'
    });
  }

  // P&L can be very large (200%+) or very negative (-100%)
  if (parsed < -1000 || parsed > 10000) {
    return new DataError('unrealized_pnl_pct', 'out_of_range', {
      value: parsed,
      why: 'Unrealized P&L out of expected range'
    });
  }

  return parsed;
}

/**
 * Require a boolean field (for signal patterns, halt flags, etc.)
 * Cannot treat false as falsy/missing
 *
 * @param {*} value - Boolean value
 * @param {string} fieldName - Field name
 * @returns {boolean|DataError}
 */
function requireBooleanField(value, fieldName) {
  if (value === null || value === undefined) {
    return new DataError(fieldName, 'missing', {
      expected: 'boolean',
      why: 'Boolean field is required'
    });
  }

  if (typeof value !== 'boolean' && value !== 0 && value !== 1) {
    return new DataError(fieldName, 'invalid', {
      value,
      expected: 'boolean',
      why: 'Must be true/false or 0/1'
    });
  }

  return Boolean(value);
}

/**
 * Require a timestamp to be valid
 * Timestamps cannot be 0 or missing in trading context
 *
 * @param {*} value - Timestamp (Unix ms, ISO string, or Date)
 * @param {string} fieldName - Field name
 * @returns {number|DataError} Unix timestamp in milliseconds
 */
function requireTimestamp(value, fieldName) {
  if (value === null || value === undefined) {
    return new DataError(fieldName, 'missing', {
      expected: 'timestamp',
      why: 'Timestamp is required'
    });
  }

  let timestamp;
  if (typeof value === 'number') {
    timestamp = value;
  } else if (typeof value === 'string') {
    timestamp = new Date(value).getTime();
  } else if (value instanceof Date) {
    timestamp = value.getTime();
  } else {
    return new DataError(fieldName, 'invalid', {
      value,
      expected: 'ISO string, Unix ms, or Date object',
      why: 'Timestamp format not recognized'
    });
  }

  if (isNaN(timestamp) || timestamp === 0) {
    return new DataError(fieldName, 'invalid', {
      value,
      why: 'Timestamp is zero or invalid'
    });
  }

  return timestamp;
}

/**
 * Validate an array is non-empty
 * Empty arrays treated as missing data
 *
 * @param {*} value - Array to validate
 * @param {string} fieldName - Field name
 * @returns {Array|DataError}
 */
function requireNonEmptyArray(value, fieldName) {
  if (!Array.isArray(value)) {
    return new DataError(fieldName, 'invalid', {
      expected: 'array',
      why: 'Value must be an array'
    });
  }

  if (value.length === 0) {
    return new DataError(fieldName, 'missing', {
      why: 'Array is empty'
    });
  }

  return value;
}

module.exports = {
  requireNumericField,
  requirePrice,
  requirePortfolioValue,
  requireSignalQuality,
  requireExposure,
  requirePositionCount,
  requireUnrealizedPnl,
  requireBooleanField,
  requireTimestamp,
  requireNonEmptyArray,
  isDataError
};
