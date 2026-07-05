/**
 * Error Envelope System
 *
 * Allows API to return valid HTTP 200 responses with error metadata
 * so frontend can distinguish "missing data error" from "successful null value".
 * This is essential for finance applications where NULL and 0 have different meanings.
 */

/**
 * DataError: Represents a data validation failure (missing, invalid, or calculation failed)
 * Discriminator flag isDataError=true allows frontend to pattern-match
 */
class DataError {
  constructor(field, reason, details = {}) {
    this.isDataError = true; // Discriminator for frontend pattern-matching
    this.field = field; // Which field failed (e.g., 'price', 'exposure_pct')
    this.reason = reason; // 'missing', 'invalid', 'calculation_failed', 'out_of_range'
    this.details = details; // Additional context { value, expected, min, max, why }
    this.timestamp = new Date().toISOString();
  }

  toJSON() {
    return {
      isDataError: this.isDataError,
      field: this.field,
      reason: this.reason,
      details: this.details,
      timestamp: this.timestamp,
    };
  }
}

/**
 * Wrap errors in response envelope that frontend can pattern-match
 * Returns HTTP 200 with error metadata (not a server error)
 *
 * @param {Array<DataError>} errors - Array of DataError objects
 * @param {number} statusCode - HTTP status (default 200 for partial data errors)
 * @returns {Object} Error response envelope
 */
function createErrorResponse(errors, statusCode = 200) {
  const normalizedErrors = errors
    .filter(Boolean) // Remove nulls
    .map((e) =>
      e instanceof DataError ? e : new DataError("unknown", "error", e)
    );

  return {
    success: true, // HTTP 200 - not a server error
    statusCode,
    data: null, // No valid data to return
    errors: normalizedErrors,
    timestamp: new Date().toISOString(),
  };
}

/**
 * Create a partial success response when some fields are valid, some failed
 *
 * @param {Object} validData - Object with valid fields
 * @param {Array<DataError>} errors - Array of field errors
 * @returns {Object} Response envelope with mixed valid/error data
 */
function createPartialResponse(validData = {}, errors = []) {
  const normalizedErrors = errors
    .filter(Boolean)
    .map((e) =>
      e instanceof DataError ? e : new DataError("unknown", "error", e)
    );

  return {
    success: true,
    statusCode: 200,
    data: validData,
    errors: normalizedErrors,
    hasErrors: normalizedErrors.length > 0,
    timestamp: new Date().toISOString(),
  };
}

/**
 * Check if a value is a DataError
 * Use in validation: if (isDataError(value)) to check before using
 */
function isDataError(value) {
  return value && typeof value === "object" && value.isDataError === true;
}

/**
 * Collect errors from an object of potential DataErrors or values
 * Returns array of DataErrors, filters out valid values
 *
 * @param {Object} results - Object where values might be DataError instances
 * @returns {Array<DataError>} Array of only DataError objects
 */
function collectErrors(results) {
  return Object.entries(results)
    .filter(([_, value]) => isDataError(value))
    .map(([field, error]) => {
      // Ensure field name is set
      if (!error.field) {
        error.field = field;
      }
      return error;
    });
}

module.exports = {
  DataError,
  createErrorResponse,
  createPartialResponse,
  isDataError,
  collectErrors,
};
