/**
 * Runtime Data Validation Layer
 * Ensures data integrity and catches invalid values before returning to frontend
 */

const validationRules = {
  // Stock/ETF data validation
  stock: {
    symbol: v => typeof v === 'string' && v.length > 0,
    price: v => v === null || (typeof v === 'number' && v >= 0),
    change: v => v === null || typeof v === 'number',
    change_percent: v => v === null || typeof v === 'number',
  },

  // Trading signal validation
  signal: {
    symbol: v => typeof v === 'string' && v.length > 0,
    signal: v => ['BUY', 'SELL', 'HOLD', 'None'].includes(v),
    date: v => !isNaN(Date.parse(v)),
    entry_price: v => v === null || (typeof v === 'number' && v > 0),
    exit_price: v => v === null || (typeof v === 'number' && v >= 0),
    signal_quality_score: v => v === null || (typeof v === 'number' && v >= 0 && v <= 100),
  },

  // Position validation
  position: {
    symbol: v => typeof v === 'string' && v.length > 0,
    quantity: v => typeof v === 'number' && v > 0,
    entry_price: v => typeof v === 'number' && v > 0,
    current_price: v => typeof v === 'number' && v > 0,
    stop_loss: v => v === null || (typeof v === 'number' && v > 0),
    target_price: v => v === null || (typeof v === 'number' && v > 0),
  },

  // Financial metrics validation
  financial: {
    symbol: v => typeof v === 'string' && v.length > 0,
    pe_ratio: v => v === null || (typeof v === 'number' && v > 0),
    pb_ratio: v => v === null || (typeof v === 'number' && v > 0),
    debt_to_equity: v => v === null || (typeof v === 'number' && v >= 0),
    current_ratio: v => v === null || (typeof v === 'number' && v > 0),
    roa: v => v === null || typeof v === 'number',
    roe: v => v === null || typeof v === 'number',
  },

  // Market data validation
  market: {
    vix: v => v === null || (typeof v === 'number' && v >= 0),
    breadth: v => v === null || (typeof v === 'number' && v >= 0 && v <= 100),
    market_cap: v => v === null || (typeof v === 'number' && v > 0),
  },
};

/**
 * Validates a single field against rules
 * Returns { valid: boolean, errors: string[] }
 */
function validateField(value, rule) {
  if (rule === undefined) {
    return { valid: true, errors: [] };
  }

  try {
    const isValid = rule(value);
    return {
      valid: isValid,
      errors: isValid ? [] : [`Invalid value: ${JSON.stringify(value)}`]
    };
  } catch (e) {
    return {
      valid: false,
      errors: [`Validation error: ${e.message}`]
    };
  }
}

/**
 * Validates an object against a schema
 * Returns { valid: boolean, errors: { field: [errors] } }
 */
function validateObject(obj, schema) {
  const errors = {};
  let valid = true;

  for (const [field, rule] of Object.entries(schema)) {
    const fieldValidation = validateField(obj[field], rule);
    if (!fieldValidation.valid) {
      errors[field] = fieldValidation.errors;
      valid = false;
    }
  }

  return { valid, errors };
}

/**
 * Validates an array of objects
 * Returns { valid: boolean, errors: { index: { field: [errors] } } }
 */
function validateArray(arr, schema) {
  if (!Array.isArray(arr)) {
    return {
      valid: false,
      errors: ['Expected array']
    };
  }

  const errors = {};
  let valid = true;

  arr.forEach((obj, idx) => {
    const objValidation = validateObject(obj, schema);
    if (!objValidation.valid) {
      errors[idx] = objValidation.errors;
      valid = false;
    }
  });

  return { valid, errors };
}

/**
 * Sanitize function - removes invalid/suspicious values
 */
function sanitizeValue(value, rule) {
  if (value === null || value === undefined) {
    return null;
  }

  const validation = validateField(value, rule);
  if (!validation.valid) {
    return null; // Replace invalid values with null
  }

  return value;
}

/**
 * Sanitize an object - removes invalid fields
 */
function sanitizeObject(obj, schema) {
  const sanitized = {};

  for (const [field, rule] of Object.entries(schema)) {
    if (obj.hasOwnProperty(field)) {
      sanitized[field] = sanitizeValue(obj[field], rule);
    }
  }

  return sanitized;
}

/**
 * Sanitize an array of objects
 */
function sanitizeArray(arr, schema) {
  if (!Array.isArray(arr)) {
    return [];
  }

  return arr.map(obj => sanitizeObject(obj, schema)).filter(obj => {
    // Remove objects where all fields are null
    return Object.values(obj).some(v => v !== null);
  });
}

module.exports = {
  validationRules,
  validateField,
  validateObject,
  validateArray,
  sanitizeValue,
  sanitizeObject,
  sanitizeArray,
};
