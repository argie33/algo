/**
 * Response formatting utilities for consistent API responses
 */

/**
 * Format successful response
 * @param {*} data - Response data
 * @param {number} statusCode - HTTP status code (default: 200)
 * @param {Object} meta - Additional metadata
 * @returns {Object} Formatted success response
 */
const success = (data, statusCode = 200, meta = {}) => {
  return {
    response: {
      success: true,
      data,
      timestamp: new Date().toISOString(),
      ...meta
    },
    statusCode
  };
};

/**
 * Format error response
 * @param {string} message - Error message
 * @param {number} statusCode - HTTP status code (default: 400)
 * @param {Object} details - Additional error details
 * @returns {Object} Formatted error response
 */
const error = (message, statusCode = 400, details = {}) => {
  return {
    response: {
      success: false,
      error: message,
      timestamp: new Date().toISOString(),
      ...details
    },
    statusCode
  };
};

/**
 * Format paginated response
 * @param {Array} data - Response data array
 * @param {Object} pagination - Pagination info
 * @param {Object} meta - Additional metadata
 * @returns {Object} Formatted paginated response
 */
const paginated = (data, pagination, meta = {}) => {
  return success({
    items: data,
    pagination: {
      page: pagination.page || 1,
      limit: pagination.limit || 50,
      total: pagination.total || data.length,
      totalPages: pagination.totalPages || Math.ceil((pagination.total || data.length) / (pagination.limit || 50)),
      hasNext: pagination.hasNext || false,
      hasPrev: pagination.hasPrev || false
    },
    ...meta
  });
};

/**
 * Format validation error response
 * @param {Array|Object} errors - Validation errors
 * @returns {Object} Formatted validation error response
 */
const validationError = (errors) => {
  return error('Validation failed', 422, {
    errors: Array.isArray(errors) ? errors : [errors],
    type: 'validation_error'
  });
};

/**
 * Format not found response
 * @param {string} resource - Resource name that was not found
 * @returns {Object} Formatted not found response
 */
const notFound = (resource = 'Resource') => {
  return error(`${resource} not found`, 404, {
    type: 'not_found_error'
  });
};

/**
 * Format unauthorized response
 * @param {string} message - Custom unauthorized message
 * @returns {Object} Formatted unauthorized response
 */
const unauthorized = (message = 'Unauthorized access') => {
  return error(message, 401, {
    type: 'unauthorized_error'
  });
};

/**
 * Format forbidden response
 * @param {string} message - Custom forbidden message
 * @returns {Object} Formatted forbidden response
 */
const forbidden = (message = 'Access forbidden') => {
  return error(message, 403, {
    type: 'forbidden_error'
  });
};

/**
 * Format server error response
 * @param {string} message - Error message
 * @param {Object} details - Error details
 * @returns {Object} Formatted server error response
 */
const serverError = (message = 'Internal server error', details = {}) => {
  return error(message, 500, {
    type: 'server_error',
    ...details
  });
};

module.exports = {
  success,
  error,
  paginated,
  validationError,
  notFound,
  unauthorized,
  forbidden,
  serverError
};