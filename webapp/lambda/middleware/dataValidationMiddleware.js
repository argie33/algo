/**
 * Data Validation Middleware
 * Automatically validates API responses before sending to client
 * Prevents invalid data from reaching frontend
 */

const { validateArray, validateObject, sanitizeArray } = require('../utils/dataValidation');

/**
 * Wraps res.json() to validate data before sending
 */
function createValidatingResponseHandler(req, res, dataSchema) {
  const originalJson = res.json.bind(res);

  res.json = function(data) {
    // If there's a schema, validate the response
    if (dataSchema && data && data.success) {
      // Validate items array
      if (Array.isArray(data.items)) {
        const validation = validateArray(data.items, dataSchema);
        if (!validation.valid) {
          // Log validation errors for debugging
          console.warn(`Data validation failed for ${req.path}:`, validation.errors);
          // Sanitize the data to remove invalid entries
          data.items = sanitizeArray(data.items, dataSchema);
        }
      }
      // Validate single object response
      else if (data.data && !Array.isArray(data.data)) {
        const validation = validateObject(data.data, dataSchema);
        if (!validation.valid) {
          console.warn(`Data validation failed for ${req.path}:`, validation.errors);
        }
      }
    }

    return originalJson(data);
  };

  return res;
}

/**
 * Creates middleware for a specific route with schema validation
 */
function createValidationMiddleware(dataSchema) {
  return (req, res, next) => {
    createValidatingResponseHandler(req, res, dataSchema);
    next();
  };
}

module.exports = {
  createValidatingResponseHandler,
  createValidationMiddleware,
};
