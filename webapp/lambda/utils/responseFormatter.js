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
      ...meta,
    },
    statusCode,
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
      service: details.service || "financial-platform",
      ...details,
    },
    statusCode,
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
      totalPages:
        pagination.totalPages ||
        Math.ceil((pagination.total || data.length) / (pagination.limit || 50)),
      hasNext: pagination.hasNext || false,
      hasPrev: pagination.hasPrev || false,
    },
    ...meta,
  });
};

/**
 * Format validation error response
 * @param {Array|Object} errors - Validation errors
 * @param {Object} troubleshooting - Troubleshooting details
 * @returns {Object} Formatted validation error response
 */
const validationError = (errors, troubleshooting = {}) => {
  return error("Validation failed", 422, {
    errors: Array.isArray(errors) ? errors : [errors],
    type: "validation_error",
    service: "financial-platform-validation",
    troubleshooting: {
      suggestion: "Check the provided data against the required format and constraints",
      requirements: "All required fields must be provided with valid values",
      steps: [
        "1. Review the specific validation errors listed above",
        "2. Ensure all required fields are included in your request",
        "3. Check data types and formats match the expected schema",
        "4. Verify numeric values are within acceptable ranges"
      ],
      ...troubleshooting
    }
  });
};

/**
 * Format not found response
 * @param {string} resource - Resource name that was not found
 * @param {Object} troubleshooting - Troubleshooting details
 * @returns {Object} Formatted not found response
 */
const notFound = (resource = "Resource", troubleshooting = {}) => {
  return error(`${resource} not found`, 404, {
    type: "not_found_error",
    service: "financial-platform",
    troubleshooting: {
      suggestion: `The requested ${resource.toLowerCase()} could not be located`,
      requirements: `${resource} must exist in the system and be accessible to your account`,
      steps: [
        "1. Verify the resource identifier (ID, symbol, etc.) is correct",
        "2. Check that you have permission to access this resource", 
        "3. Ensure the resource hasn't been moved or deleted",
        "4. Try refreshing the page or searching for the resource again"
      ],
      ...troubleshooting
    }
  });
};

/**
 * Format unauthorized response
 * @param {string} message - Custom unauthorized message
 * @param {Object} troubleshooting - Troubleshooting details
 * @returns {Object} Formatted unauthorized response
 */
const unauthorized = (message = "Unauthorized access", troubleshooting = {}) => {
  return error(message, 401, {
    type: "unauthorized_error",
    service: "financial-platform-auth",
    troubleshooting: {
      suggestion: "Verify that you are logged in and have a valid authentication token",
      requirements: "Valid JWT token in Authorization header (Bearer <token>)",
      steps: [
        "1. Check if you are logged in to the application",
        "2. Verify your session hasn't expired", 
        "3. Try refreshing the page or logging out and back in",
        "4. Contact support if the issue persists"
      ],
      ...troubleshooting
    }
  });
};

/**
 * Format forbidden response
 * @param {string} message - Custom forbidden message
 * @param {Object} troubleshooting - Troubleshooting details
 * @returns {Object} Formatted forbidden response
 */
const forbidden = (message = "Access forbidden", troubleshooting = {}) => {
  return error(message, 403, {
    type: "forbidden_error",
    service: "financial-platform-auth",
    troubleshooting: {
      suggestion: "Check that your account has the required permissions for this resource",
      requirements: "Sufficient user permissions or elevated access level",
      steps: [
        "1. Verify your account type and permissions",
        "2. Check if this feature requires premium access",
        "3. Contact administrator to request additional permissions",
        "4. Try accessing a different resource that matches your permission level"
      ],
      ...troubleshooting
    }
  });
};

/**
 * Format server error response
 * @param {string} message - Error message
 * @param {Object} details - Error details
 * @returns {Object} Formatted server error response
 */
const serverError = (message = "Internal server error", details = {}) => {
  return error(message, 500, {
    type: "server_error",
    service: "financial-platform",
    troubleshooting: {
      suggestion: "This is a temporary server issue. Please try again in a few moments",
      requirements: "Server should be operational - this may be a temporary outage",
      steps: [
        "1. Wait 30 seconds and try the request again",
        "2. Check if other features are working normally",
        "3. Clear your browser cache and cookies if the issue persists", 
        "4. Contact technical support if the error continues"
      ]
    },
    ...details,
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
  serverError,
};
