/**
 * Validates API response structure and content
 * Ensures data integrity before components consume it
 */

/**
 * Validates that extracted data has proper envelope structure
 * @param {object} data - Data from extractData()
 * @param {string} context - Human-readable context (e.g., "sectors API")
 * @returns {object} { valid: boolean, errors: string[], warnings: string[], unwrapped: object }
 */
export const validateResponseEnvelope = (data, context = 'API') => {
  const errors = [];
  const warnings = [];
  let unwrapped = data;

  // Check that data exists
  if (!data || typeof data !== 'object') {
    errors.push(`${context}: Response is not an object (got ${typeof data})`);
    return { valid: false, errors, warnings, unwrapped: null };
  }

  // Check for envelope structure: {data: {...}, statusCode, success}
  if (data.data !== undefined) {
    // Has envelope
    if (data.data === null) {
      errors.push(`${context}: Response envelope has null data field`);
      unwrapped = null;
    } else if (Array.isArray(data.data)) {
      errors.push(`${context}: Response envelope.data is an array (expected object)`);
      unwrapped = null;
    } else if (typeof data.data !== 'object') {
      errors.push(`${context}: Response envelope.data is not an object (got ${typeof data.data})`);
      unwrapped = null;
    } else if (Object.keys(data.data).length === 0) {
      warnings.push(`${context}: Response envelope.data is empty object (no properties)`);
      unwrapped = data.data;
    } else {
      // Valid data object
      unwrapped = data.data;
    }
  } else if (data.items !== undefined) {
    // Paginated response
    if (!Array.isArray(data.items)) {
      errors.push(`${context}: Response items field is not an array (got ${typeof data.items})`);
      unwrapped = null;
    } else if (data.items.length === 0) {
      warnings.push(`${context}: Response items array is empty`);
      unwrapped = data.items;
    } else {
      unwrapped = data.items;
    }
  } else {
    // No standard structure
    warnings.push(`${context}: Response has no 'data' or 'items' envelope (will use as-is)`);
    unwrapped = data;
  }

  // Check for statusCode/success markers
  if (data.statusCode === undefined && data.success === undefined) {
    warnings.push(`${context}: Response missing statusCode and success markers (may not be normalized by backend)`);
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
    unwrapped,
  };
};

/**
 * Validates that unwrapped data has required fields
 * @param {object} data - Unwrapped data object
 * @param {array} requiredFields - Field names that must exist and be non-null
 * @param {string} context - Human-readable context
 * @returns {object} { valid: boolean, errors: string[], missingFields: string[] }
 */
export const validateDataFields = (data, requiredFields = [], context = 'Data') => {
  const errors = [];
  const missingFields = [];

  if (requiredFields.length === 0) {
    return { valid: true, errors, missingFields };
  }

  if (!data || typeof data !== 'object') {
    errors.push(`${context}: Data is not an object (got ${typeof data})`);
    return { valid: false, errors, missingFields };
  }

  requiredFields.forEach((field) => {
    if (!(field in data) || data[field] === null || data[field] === undefined) {
      missingFields.push(field);
    }
  });

  if (missingFields.length > 0) {
    errors.push(`${context}: Missing required fields: ${missingFields.join(', ')}`);
  }

  return {
    valid: missingFields.length === 0,
    errors,
    missingFields,
  };
};

/**
 * Validates array items for required fields
 * @param {array} items - Array of items
 * @param {array} requiredFields - Fields each item must have
 * @param {string} context - Human-readable context
 * @returns {object} { valid: boolean, errors: string[], invalidItems: array }
 */
export const validateArrayItems = (items, requiredFields = [], context = 'Items') => {
  const errors = [];
  const invalidItems = [];

  if (!Array.isArray(items)) {
    errors.push(`${context}: Expected array but got ${typeof items}`);
    return { valid: false, errors, invalidItems };
  }

  if (requiredFields.length === 0) {
    return { valid: true, errors, invalidItems };
  }

  items.forEach((item, idx) => {
    if (!item || typeof item !== 'object') {
      invalidItems.push({ index: idx, reason: `Item is not an object (got ${typeof item})` });
      return;
    }

    const missing = requiredFields.filter(
      (field) => !(field in item) || item[field] === null || item[field] === undefined
    );

    if (missing.length > 0) {
      invalidItems.push({ index: idx, missingFields: missing });
    }
  });

  if (invalidItems.length > 0) {
    errors.push(`${context}: ${invalidItems.length} of ${items.length} items missing required fields`);
  }

  return {
    valid: invalidItems.length === 0,
    errors,
    invalidItems,
  };
};

/**
 * Comprehensive validation for API response
 * Combines envelope check + field validation
 * @param {object} response - Response from extractData()
 * @param {object} options - Validation options
 *   - requiredFields: array of field names that must exist
 *   - requireNonEmpty: boolean, fail if data is empty object/array
 *   - context: string for error messages
 * @returns {object} { valid: boolean, errors: string[], data: unwrapped data }
 */
export const validateResponse = (
  response,
  {
    requiredFields = [],
    requireNonEmpty = false,
    context = 'Response',
  } = {}
) => {
  const errors = [];
  let unwrapped = response;

  // Step 1: Validate envelope
  const envelopeCheck = validateResponseEnvelope(response, context);
  errors.push(...envelopeCheck.errors);
  unwrapped = envelopeCheck.unwrapped;

  // If envelope validation failed, return early
  if (!envelopeCheck.valid) {
    return { valid: false, errors, data: null };
  }

  // Step 2: Check if data is empty when non-empty is required
  if (requireNonEmpty) {
    if (unwrapped === null) {
      errors.push(`${context}: Data is null but non-empty required`);
    } else if (typeof unwrapped === 'object' && !Array.isArray(unwrapped)) {
      if (Object.keys(unwrapped).length === 0) {
        errors.push(`${context}: Data is empty object but non-empty required`);
      }
    } else if (Array.isArray(unwrapped)) {
      if (unwrapped.length === 0) {
        errors.push(`${context}: Data array is empty but non-empty required`);
      }
    }
  }

  // Step 3: Validate required fields (only on non-array objects)
  if (requiredFields.length > 0 && unwrapped && typeof unwrapped === 'object' && !Array.isArray(unwrapped)) {
    const fieldCheck = validateDataFields(unwrapped, requiredFields, context);
    errors.push(...fieldCheck.errors);
  }

  return {
    valid: errors.length === 0,
    errors,
    data: errors.length === 0 ? unwrapped : null,
  };
};

/**
 * Safe response validation with fallback
 * @param {object} response - Response to validate
 * @param {*} fallback - Value to return if validation fails
 * @param {object} options - Validation options
 * @returns {*} Validated data or fallback
 */
export const validateResponseOrFallback = (response, fallback = null, options = {}) => {
  const validation = validateResponse(response, options);
  if (!validation.valid) {
    if (options.context) {
      console.warn(`[validateResponse] ${options.context} validation failed:`, validation.errors);
    }
    return fallback;
  }
  return validation.data;
};

export default {
  validateResponseEnvelope,
  validateDataFields,
  validateArrayItems,
  validateResponse,
  validateResponseOrFallback,
};
