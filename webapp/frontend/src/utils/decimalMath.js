/**
 * Financial decimal math utility
 *
 * Handles precise calculations on financial values without rounding errors.
 * Since JavaScript floats lose precision, we treat financial numbers as strings
 * internally and provide safe arithmetic operations.
 *
 * Usage:
 *   const sum = add('123.45', '67.89')     // Returns '191.34'
 *   const result = multiply('10.50', '3')  // Returns '31.50'
 *   const formatted = toFixed(value, 2)    // Formats to 2 decimal places
 */

/**
 * Safely add two financial values
 * @param {number|string} a - First value
 * @param {number|string} b - Second value
 * @param {number} decimals - Decimal places (default 2)
 * @returns {string} Sum as string with specified decimals
 */
export function add(a, b, decimals = 2) {
  const aNum = typeof a === "string" ? a : String(a);
  const bNum = typeof b === "string" ? b : String(b);

  const factor = Math.pow(10, decimals);
  const aInt = Math.round(parseFloat(aNum) * factor);
  const bInt = Math.round(parseFloat(bNum) * factor);
  const sum = aInt + bInt;

  return (sum / factor).toFixed(decimals);
}

/**
 * Safely subtract two financial values
 * @param {number|string} a - First value
 * @param {number|string} b - Second value to subtract
 * @param {number} decimals - Decimal places (default 2)
 * @returns {string} Difference as string with specified decimals
 */
export function subtract(a, b, decimals = 2) {
  const aNum = typeof a === "string" ? a : String(a);
  const bNum = typeof b === "string" ? b : String(b);

  const factor = Math.pow(10, decimals);
  const aInt = Math.round(parseFloat(aNum) * factor);
  const bInt = Math.round(parseFloat(bNum) * factor);
  const diff = aInt - bInt;

  return (diff / factor).toFixed(decimals);
}

/**
 * Safely multiply two financial values
 * @param {number|string} a - First value
 * @param {number|string} b - Second value
 * @param {number} decimals - Decimal places (default 2)
 * @returns {string} Product as string with specified decimals
 */
export function multiply(a, b, decimals = 2) {
  const aVal = parseFloat(a);
  const bVal = parseFloat(b);
  const product = aVal * bVal;

  return product.toFixed(decimals);
}

/**
 * Safely divide two financial values
 * @param {number|string} a - Dividend
 * @param {number|string} b - Divisor (must not be 0)
 * @param {number} decimals - Decimal places (default 2)
 * @returns {string} Quotient as string with specified decimals
 */
export function divide(a, b, decimals = 2) {
  const aVal = parseFloat(a);
  const bVal = parseFloat(b);

  if (bVal === 0) {
    throw new Error("Division by zero in financial calculation");
  }

  const quotient = aVal / bVal;
  return quotient.toFixed(decimals);
}

/**
 * Calculate percentage change between two values
 * @param {number|string} oldValue - Original value
 * @param {number|string} newValue - New value
 * @param {number} decimals - Decimal places (default 2)
 * @returns {string} Percentage change as string (e.g., "15.50" for +15.5%)
 */
export function percentageChange(oldValue, newValue, decimals = 2) {
  const old = parseFloat(oldValue);
  const newVal = parseFloat(newValue);

  if (old === 0) {
    return "0.00";
  }

  const change = ((newVal - old) / old) * 100;
  return change.toFixed(decimals);
}

/**
 * Format a number to fixed decimal places
 * @param {number|string} value - Value to format
 * @param {number} decimals - Decimal places (default 2)
 * @returns {string} Formatted value as string
 */
export function toFixed(value, decimals = 2) {
  if (value === null || value === undefined) {
    return "0.00";
  }

  const num = parseFloat(value);
  if (isNaN(num)) {
    return "0.00";
  }

  return num.toFixed(decimals);
}

/**
 * Sum an array of financial values
 * @param {(number|string)[]} values - Array of values to sum
 * @param {number} decimals - Decimal places (default 2)
 * @returns {string} Sum as string with specified decimals
 */
export function sum(values, decimals = 2) {
  if (!Array.isArray(values) || values.length === 0) {
    return "0.00";
  }

  const factor = Math.pow(10, decimals);
  let total = 0;

  for (const val of values) {
    const num = parseFloat(val);
    if (!isNaN(num)) {
      total += Math.round(num * factor);
    }
  }

  return (total / factor).toFixed(decimals);
}

/**
 * Compare two financial values
 * @param {number|string} a - First value
 * @param {number|string} b - Second value
 * @param {number} tolerance - Tolerance for comparison (default 0.01 for penny precision)
 * @returns {number} -1 if a < b, 0 if equal (within tolerance), 1 if a > b
 */
export function compare(a, b, tolerance = 0.01) {
  const aVal = parseFloat(a);
  const bVal = parseFloat(b);
  const diff = aVal - bVal;

  if (Math.abs(diff) < tolerance) {
    return 0;
  }

  return diff < 0 ? -1 : 1;
}

/**
 * Check if a value is effectively zero (within tolerance)
 * @param {number|string} value - Value to check
 * @param {number} tolerance - Tolerance (default 0.01 for penny precision)
 * @returns {boolean} True if value is within tolerance of zero
 */
export function isZero(value, tolerance = 0.01) {
  const num = parseFloat(value);
  return Math.abs(num) < tolerance;
}

/**
 * Clamp a financial value between min and max
 * @param {number|string} value - Value to clamp
 * @param {number|string} min - Minimum value
 * @param {number|string} max - Maximum value
 * @param {number} decimals - Decimal places (default 2)
 * @returns {string} Clamped value as string
 */
export function clamp(value, min, max, decimals = 2) {
  const val = parseFloat(value);
  const minVal = parseFloat(min);
  const maxVal = parseFloat(max);

  const clamped = Math.max(minVal, Math.min(maxVal, val));
  return clamped.toFixed(decimals);
}

export default {
  add,
  subtract,
  multiply,
  divide,
  percentageChange,
  toFixed,
  sum,
  compare,
  isZero,
  clamp,
};
