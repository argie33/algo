/**
 * Response Structure Validation
 * Validates database query results have expected structure before returning to clients
 * - Ensures result.rows is present and is an array
 * - Validates required fields exist in rows
 * - Provides type coercion for numeric fields
 */

/**
 * Validates that a database query result has expected structure
 * Throws error if result is invalid
 * @param {Object} result - Query result from pool.query()
 * @param {Object} options - Validation options
 * @returns {Object} result - Pass-through for chaining
 */
function validateQueryResult(result, options = {}) {
  const { requireRows = false, minRows = 0, maxRows = null } = options;

  // Check result object exists
  if (!result || typeof result !== 'object') {
    throw new Error('Database query returned invalid result structure');
  }

  // Check rows array exists
  if (result.rows === undefined || result.rows === null) {
    if (requireRows) {
      throw new Error('Database query returned no rows');
    }
    // Safe default: convert missing rows to empty array
    result.rows = [];
  }

  // Check rows is an array
  if (!Array.isArray(result.rows)) {
    throw new Error(`Database query returned invalid rows type: ${typeof result.rows}`);
  }

  // Check row count constraints
  if (result.rows.length < minRows) {
    throw new Error(`Database query returned ${result.rows.length} rows, expected at least ${minRows}`);
  }

  if (maxRows !== null && result.rows.length > maxRows) {
    throw new Error(`Database query returned ${result.rows.length} rows, expected at most ${maxRows}`);
  }

  return result;
}

/**
 * Ensures a value coerced to a specific type
 * @param {*} value - Value to coerce
 * @param {string} type - Target type: 'int', 'float', 'string', 'bool', 'date'
 * @param {*} defaultValue - Default if value is null/undefined
 * @returns {*} Coerced value
 */
function coerceValue(value, type = 'string', defaultValue = null) {
  if (value === null || value === undefined) {
    return defaultValue;
  }

  switch (type) {
    case 'int':
    case 'integer':
      return isNaN(value) ? defaultValue : parseInt(value, 10);
    case 'float':
    case 'number':
      return isNaN(value) ? defaultValue : parseFloat(value);
    case 'bool':
    case 'boolean':
      if (typeof value === 'boolean') return value;
      if (typeof value === 'string') {
        return ['true', '1', 'yes', 'on'].includes(value.toLowerCase());
      }
      return Boolean(value);
    case 'date':
      return value instanceof Date ? value : new Date(value);
    case 'raw':
      return value;
    case 'string':
    default:
      return String(value);
  }
}

/**
 * Validates that required fields exist in a row object
 * @param {Object} row - Row to validate
 * @param {string[]} requiredFields - Fields that must exist
 * @returns {Object} row - Pass-through for chaining
 */
function validateRowFields(row, requiredFields = []) {
  if (!row || typeof row !== 'object') {
    throw new Error('Row is not an object');
  }

  const missing = requiredFields.filter(field => !(field in row));
  if (missing.length > 0) {
    throw new Error(`Row missing required fields: ${missing.join(', ')}`);
  }

  return row;
}

/**
 * Transforms a row by coercing field types
 * @param {Object} row - Row to transform
 * @param {Object} fieldTypes - Map of field -> type
 * @returns {Object} Transformed row
 */
function transformRowTypes(row, fieldTypes = {}) {
  if (!row || typeof row !== 'object') {
    return row;
  }

  const transformed = { ...row };

  for (const [field, type] of Object.entries(fieldTypes)) {
    if (field in transformed) {
      transformed[field] = coerceValue(transformed[field], type);
    }
  }

  return transformed;
}

/**
 * Validates a single row from query result
 * @param {Object} row - Row to validate
 * @param {Object} schema - Validation schema { field: { type, required, default } }
 * @returns {Object} Validated and coerced row
 */
function validateAndCoerceRow(row, schema = {}) {
  if (!row || typeof row !== 'object') {
    throw new Error('Invalid row object');
  }

  const validated = {};

  for (const [field, fieldConfig] of Object.entries(schema)) {
    const { type = 'string', required = false, defaultValue = null } = fieldConfig;

    if (!(field in row)) {
      if (required) {
        throw new Error(`Row missing required field: ${field}`);
      }
      validated[field] = defaultValue;
      continue;
    }

    const value = row[field];
    if (value === null || value === undefined) {
      if (required) {
        throw new Error(`Field ${field} is null but is required`);
      }
      validated[field] = defaultValue;
      continue;
    }

    validated[field] = coerceValue(value, type, defaultValue);
  }

  // Include any additional fields not in schema
  for (const [field, value] of Object.entries(row)) {
    if (!(field in schema)) {
      validated[field] = value;
    }
  }

  return validated;
}

/**
 * Validates all rows in query result
 * @param {Object} result - Query result with rows array
 * @param {Object} schema - Validation schema
 * @returns {Object[]} Array of validated and coerced rows
 */
function validateAndCoerceRows(result, schema = {}) {
  validateQueryResult(result, { requireRows: false });

  return result.rows.map((row, index) => {
    try {
      return validateAndCoerceRow(row, schema);
    } catch (error) {
      throw new Error(`Row ${index}: ${error.message}`);
    }
  });
}

/**
 * Safe single-row extract with coercion
 * @param {Object} result - Query result
 * @param {Object} schema - Validation schema
 * @param {Object} defaultValue - Default row if empty
 * @returns {Object} First row or default
 */
function extractSingleRow(result, schema = {}, defaultValue = null) {
  validateQueryResult(result, { requireRows: false });

  if (result.rows.length === 0) {
    return defaultValue;
  }

  return validateAndCoerceRow(result.rows[0], schema);
}

/**
 * Extract count from aggregation query
 * @param {Object} result - Query result from COUNT(*) query
 * @param {string} countField - Field name containing count (default: 'count')
 * @returns {number} Count value
 */
function extractCount(result, countField = 'count') {
  validateQueryResult(result, { minRows: 1, maxRows: 1 });

  const row = result.rows[0];
  const count = row[countField];

  if (count === null || count === undefined) {
    throw new Error(`Count field ${countField} not found in result`);
  }

  return coerceValue(count, 'int', 0);
}

module.exports = {
  validateQueryResult,
  coerceValue,
  validateRowFields,
  transformRowTypes,
  validateAndCoerceRow,
  validateAndCoerceRows,
  extractSingleRow,
  extractCount,
};
