/**
 * Data validation utilities to ensure components safely access API response properties
 * All functions handle null/undefined gracefully and never throw
 */

/**
 * Safely access nested properties with fallback
 * @param {object} obj - Object to access
 * @param {string} path - Dot-separated path (e.g., "market.active_tier.name")
 * @param {*} defaultValue - Value to return if path doesn't exist
 * @returns {*} Value at path or defaultValue
 */
export const safeGet = (obj, path, defaultValue = null) => {
  if (!obj || typeof obj !== 'object') return defaultValue;

  try {
    const value = path.split('.').reduce((current, prop) => {
      if (current == null || typeof current !== 'object') return undefined;
      return current[prop];
    }, obj);

    return value !== undefined ? value : defaultValue;
  } catch (err) {
    console.error('[DataValidation] Failed to access nested property:', err?.message || err);
    return defaultValue;
  }
};

/**
 * Ensure value is an array, handling null/undefined safely
 * @param {*} value - Value to ensure is array
 * @param {array} defaultArray - Default if value is not array
 * @returns {array} Value as array or default
 */
export const ensureArray = (value, defaultArray = []) => {
  return Array.isArray(value) ? value : defaultArray;
};

/**
 * Ensure value is an object, handling null/undefined safely
 * @param {*} value - Value to ensure is object
 * @param {object} defaultObj - Default if value is not object
 * @returns {object} Value as object or default
 */
export const ensureObject = (value, defaultObj = {}) => {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value;
  }
  if (value !== null && value !== undefined) {
    console.warn('[ensureObject] Expected object but got:', typeof value, value);
  }
  return defaultObj;
};

/**
 * Ensure value is a number, handling null/undefined/NaN safely
 * @param {*} value - Value to ensure is number
 * @param {number} defaultNum - Default if value is not valid number
 * @returns {number} Value as number or default
 */
export const ensureNumber = (value, defaultNum = 0) => {
  const num = Number(value);
  return isNaN(num) ? defaultNum : num;
};

/**
 * Ensure value is a string, handling null/undefined safely
 * @param {*} value - Value to ensure is string
 * @param {string} defaultStr - Default if value is not string
 * @returns {string} Value as string or default
 */
export const ensureString = (value, defaultStr = '') => {
  return typeof value === 'string' ? value : defaultStr;
};

/**
 * Extract items from paginated response, handling all formats safely
 * @param {object} data - Response data object
 * @returns {array} Items array, always safe to iterate
 */
export const getItemsArray = (data) => {
  if (Array.isArray(data)) return data;
  if (!data || typeof data !== 'object') return [];

  // Try common response formats
  if (Array.isArray(data.items)) return data.items;
  if (Array.isArray(data.data)) return data.data;
  if (data.data && Array.isArray(data.data.items)) return data.data.items;

  return [];
};

/**
 * Get pagination metadata, handling missing properties safely
 * @param {object} data - Response data object
 * @returns {object} Pagination object with all properties safe to use
 */
export const getPaginationMeta = (data) => {
  const items = getItemsArray(data);

  return {
    total: ensureNumber(safeGet(data, 'total') || safeGet(data, 'pagination.total') || items.length),
    limit: ensureNumber(safeGet(data, 'limit') || safeGet(data, 'pagination.limit')),
    offset: ensureNumber(safeGet(data, 'offset') || safeGet(data, 'pagination.offset')),
    page: ensureNumber(safeGet(data, 'page') || safeGet(data, 'pagination.page')),
    totalPages: ensureNumber(safeGet(data, 'totalPages') || safeGet(data, 'pagination.totalPages')),
    hasNext: Boolean(safeGet(data, 'hasNext', safeGet(data, 'pagination.hasNext'))),
    hasPrev: Boolean(safeGet(data, 'hasPrev', safeGet(data, 'pagination.hasPrev'))),
  };
};

/**
 * Safe object property access guard
 * Returns object with all properties guaranteed to exist (with defaults)
 * @param {object} data - Object to guard
 * @param {object} schema - Schema defining expected properties and defaults
 * @returns {object} Guarded object with all properties from schema
 */
export const guardObject = (data, schema) => {
  const result = {};

  if (!data || typeof data !== 'object') {
    // Return schema with all defaults if data is invalid
    Object.entries(schema).forEach(([key, defaultValue]) => {
      result[key] = typeof defaultValue === 'function' ? defaultValue() : defaultValue;
    });
    return result;
  }

  // Copy existing properties, falling back to defaults
  Object.entries(schema).forEach(([key, defaultValue]) => {
    result[key] = data[key] !== undefined
      ? data[key]
      : (typeof defaultValue === 'function' ? defaultValue() : defaultValue);
  });

  return result;
};

/**
 * Validate that required properties exist in object
 * @param {object} obj - Object to validate
 * @param {array} requiredProps - Array of required property names
 * @returns {object} { valid: boolean, missing: array }
 */
export const validateRequired = (obj, requiredProps = []) => {
  if (!obj || typeof obj !== 'object') {
    return { valid: false, missing: requiredProps };
  }

  const missing = requiredProps.filter(prop => obj[prop] === undefined || obj[prop] === null);
  return { valid: missing.length === 0, missing };
};

/**
 * Safe numeric calculation
 * @param {*} value - Value to use in calculation
 * @param {function} calculator - Function that takes numeric value and returns result
 * @param {*} defaultResult - Value to return if calculation fails
 * @returns {*} Result of calculation or default
 */
export const safeCalculate = (value, calculator, defaultResult = 0) => {
  try {
    const num = ensureNumber(value);
    const result = calculator(num);
    return isNaN(result) ? defaultResult : result;
  } catch (err) {
    console.error('[DataValidation] Safe calculation failed:', err?.message || err);
    return defaultResult;
  }
};

export default {
  safeGet,
  ensureArray,
  ensureObject,
  ensureNumber,
  ensureString,
  getItemsArray,
  getPaginationMeta,
  guardObject,
  validateRequired,
  safeCalculate,
};
