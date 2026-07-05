/**
 * Runtime Data Validation Layer
 * Ensures data integrity and catches invalid values before returning to frontend
 */

const validationRules = {
  // Stock/ETF data validation
  stock: {
    symbol: (v) => typeof v === "string" && v.length > 0,
    price: (v) => v === null || (typeof v === "number" && v >= 0),
    change: (v) => v === null || typeof v === "number",
    change_percent: (v) => v === null || typeof v === "number",
  },

  // Trading signal validation
  signal: {
    symbol: (v) => typeof v === "string" && v.length > 0,
    signal: (v) => ["BUY", "SELL", "HOLD", "None"].includes(v),
    date: (v) => !isNaN(Date.parse(v)),
    entry_price: (v) => v === null || (typeof v === "number" && v > 0),
    exit_price: (v) => v === null || (typeof v === "number" && v >= 0),
    signal_quality_score: (v) =>
      v === null || (typeof v === "number" && v >= 0 && v <= 100),
  },

  // Position validation
  position: {
    symbol: (v) => typeof v === "string" && v.length > 0,
    quantity: (v) => typeof v === "number" && v > 0,
    entry_price: (v) => typeof v === "number" && v > 0,
    current_price: (v) => typeof v === "number" && v > 0,
    stop_loss: (v) => v === null || (typeof v === "number" && v > 0),
    target_price: (v) => v === null || (typeof v === "number" && v > 0),
  },

  // Financial metrics validation
  financial: {
    symbol: (v) => typeof v === "string" && v.length > 0,
    pe_ratio: (v) => v === null || (typeof v === "number" && v > 0),
    pb_ratio: (v) => v === null || (typeof v === "number" && v > 0),
    debt_to_equity: (v) => v === null || (typeof v === "number" && v >= 0),
    current_ratio: (v) => v === null || (typeof v === "number" && v > 0),
    roa: (v) => v === null || typeof v === "number",
    roe: (v) => v === null || typeof v === "number",
  },

  // Market data validation
  market: {
    vix: (v) => v === null || (typeof v === "number" && v >= 0),
    breadth: (v) => v === null || (typeof v === "number" && v >= 0 && v <= 100),
    market_cap: (v) => v === null || (typeof v === "number" && v > 0),
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
      errors: isValid ? [] : [`Invalid value: ${JSON.stringify(value)}`],
    };
  } catch (e) {
    return {
      valid: false,
      errors: [`Validation error: ${e.message}`],
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
      errors: ["Expected array"],
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
 * Logs all validation failures so callers have visibility into data quality issues
 */
function sanitizeValue(value, rule, fieldName = null) {
  if (value === null || value === undefined) {
    return null;
  }

  const validation = validateField(value, rule);
  if (!validation.valid) {
    const ctx = fieldName
      ? `field=${fieldName}`
      : `value=${JSON.stringify(value)}`;
    console.warn(
      `[VALIDATION] Invalid ${ctx}: ${validation.errors.join(", ")}`
    );
    return null; // Replace invalid values with null
  }

  return value;
}

/**
 * Sanitize an object - removes invalid fields
 * Logs field-level validation failures so callers can identify problematic data
 */
function sanitizeObject(obj, schema) {
  const sanitized = {};

  for (const [field, rule] of Object.entries(schema)) {
    if (Object.prototype.hasOwnProperty.call(obj, field)) {
      sanitized[field] = sanitizeValue(obj[field], rule, field);
    }
  }

  return sanitized;
}

/**
 * Sanitize an array of objects
 * Logs when objects are filtered out due to complete validation failure
 */
function sanitizeArray(arr, schema) {
  if (!Array.isArray(arr)) {
    console.warn(`[VALIDATION] Expected array but got ${typeof arr}`);
    return [];
  }

  let filtered = 0;
  const result = arr
    .map((obj) => sanitizeObject(obj, schema))
    .filter((obj) => {
      // Remove objects where all fields are null
      const hasValidField = Object.values(obj).some((v) => v !== null);
      if (!hasValidField) {
        filtered++;
      }
      return hasValidField;
    });

  if (filtered > 0) {
    console.warn(
      `[VALIDATION] Filtered out ${filtered}/${arr.length} objects where all fields failed validation`
    );
  }

  return result;
}

/**
 * Parse and validate pagination parameters from query string
 * Prevents DOS attacks via oversized requests
 * Logs when invalid limits are provided
 */
function parseLimit(queryLimit, defaultLimit = 500, maxLimit = 50000) {
  try {
    const parsed = parseInt(queryLimit, 10);
    if (isNaN(parsed)) {
      console.warn(
        `[PAGINATION] Invalid limit parameter: "${queryLimit}" is not numeric. Defaulting to ${defaultLimit}.`
      );
      return defaultLimit;
    }
    if (parsed < 1) {
      console.warn(
        `[PAGINATION] Invalid limit parameter: ${parsed} is less than 1. Defaulting to ${defaultLimit}.`
      );
      return defaultLimit;
    }
    if (parsed > maxLimit) {
      console.warn(
        `[PAGINATION] Limit ${parsed} exceeds maximum ${maxLimit}. Capping at ${maxLimit}.`
      );
    }
    return Math.min(parsed, maxLimit);
  } catch (error) {
    console.warn(
      `[PAGINATION] Failed to parse limit "${queryLimit}": ${error.message}. Defaulting to ${defaultLimit}.`
    );
    return defaultLimit;
  }
}

function parseOffset(queryOffset, maxOffset = 1000000) {
  try {
    const parsed = parseInt(queryOffset, 10);
    if (isNaN(parsed)) {
      console.warn(
        `[PAGINATION] Invalid offset parameter: "${queryOffset}" is not numeric. Defaulting to 0.`
      );
      return 0;
    }
    if (parsed < 0) {
      console.warn(
        `[PAGINATION] Invalid offset parameter: ${parsed} is negative. Defaulting to 0.`
      );
      return 0;
    }
    return Math.min(parsed, maxOffset);
  } catch (error) {
    console.warn(
      `[PAGINATION] Failed to parse offset "${queryOffset}": ${error.message}. Defaulting to 0.`
    );
    return 0;
  }
}

function parsePageNum(queryPage, defaultPage = 1) {
  try {
    const parsed = parseInt(queryPage, 10);
    if (isNaN(parsed)) {
      console.warn(
        `[PAGINATION] Invalid page parameter: "${queryPage}" is not numeric. Defaulting to ${defaultPage}.`
      );
      return defaultPage;
    }
    if (parsed < 1) {
      console.warn(
        `[PAGINATION] Invalid page parameter: ${parsed} is less than 1. Defaulting to ${defaultPage}.`
      );
      return defaultPage;
    }
    return parsed;
  } catch (error) {
    console.warn(
      `[PAGINATION] Failed to parse page "${queryPage}": ${error.message}. Defaulting to ${defaultPage}.`
    );
    return defaultPage;
  }
}

module.exports = {
  validationRules,
  validateField,
  validateObject,
  validateArray,
  sanitizeValue,
  sanitizeObject,
  sanitizeArray,
  parseLimit,
  parseOffset,
  parsePageNum,
};
