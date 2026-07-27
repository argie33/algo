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

module.exports = {
  createInputValidationMiddleware,
  inputSchemas,
};
