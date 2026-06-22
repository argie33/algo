/**
 * Data Validation Middleware
 * Validates both request input and response output
 */

const { sendError } = require("../utils/apiResponse");
const { validateObject } = require("../utils/dataValidation");

/**
 * Creates middleware to validate incoming request body
 * @param {Object} schema - Validation schema for request body fields
 * @returns {Function} Express middleware
 */
function createInputValidationMiddleware(schema) {
  return (req, res, next) => {
    const validation = validateObject(req.body || {}, schema);

    if (!validation.valid) {
      // Format error messages
      const errorMessages = [];
      for (const [field, errors] of Object.entries(validation.errors)) {
        errorMessages.push(`${field}: ${errors.join(", ")}`);
      }

      return sendError(
        res,
        `Validation error: ${errorMessages.join("; ")}`,
        400
      );
    }

    next();
  };
}

/**
 * Request body validation schemas
 */
const inputSchemas = {
  contact: {
    name: (v) =>
      typeof v === "string" && v.trim().length > 0 && v.trim().length <= 100,
    email: (v) => typeof v === "string" && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v),
    subject: (v) =>
      v === null ||
      v === undefined ||
      (typeof v === "string" && v.trim().length <= 200),
    message: (v) =>
      typeof v === "string" && v.trim().length > 0 && v.trim().length <= 5000,
  },

  manualTrade: {
    symbol: (v) => typeof v === "string" && v.trim().length > 0,
    trade_type: (v) =>
      typeof v === "string" && ["buy", "sell"].includes(v.toLowerCase()),
    quantity: (v) => typeof v === "number" && v > 0,
    price: (v) => typeof v === "number" && v > 0,
    execution_date: (v) =>
      typeof v === "string" &&
      !isNaN(Date.parse(v)) &&
      new Date(v) <= new Date(),
    commission: (v) =>
      v === null || v === undefined || (typeof v === "number" && v >= 0),
  },
};

/**
 * Wraps res.json() to validate response data before sending
 */
function createValidatingResponseHandler(req, res, dataSchema) {
  const originalJson = res.json.bind(res);

  res.json = function (data) {
    // If there's a schema, validate the response
    if (dataSchema && data && data.success) {
      // Validate items array
      if (Array.isArray(data.items)) {
        const validation = validateObject(data.items[0] || {}, dataSchema);
        if (!validation.valid) {
          console.warn(
            `Response validation failed for ${req.path}:`,
            validation.errors
          );
        }
      }
      // Validate single object response
      else if (data.data && !Array.isArray(data.data)) {
        const validation = validateObject(data.data, dataSchema);
        if (!validation.valid) {
          console.warn(
            `Response validation failed for ${req.path}:`,
            validation.errors
          );
        }
      }
    }

    return originalJson(data);
  };

  return res;
}

/**
 * Creates middleware for response validation (deprecated - kept for backwards compatibility)
 */
function createValidationMiddleware(dataSchema) {
  return (req, res, next) => {
    createValidatingResponseHandler(req, res, dataSchema);
    next();
  };
}

module.exports = {
  createInputValidationMiddleware,
  createValidatingResponseHandler,
  createValidationMiddleware,
  inputSchemas,
};
