/**
 * Validation middleware for API endpoints
 * Provides comprehensive input validation and sanitization
 */

const { validationError } = require("../utils/responseFormatter");

/**
 * Sanitize string input
 */
function sanitizeString(value, maxLength = 100) {
  if (typeof value !== "string") return "";
  return value.trim().slice(0, maxLength);
}

/**
 * Sanitize number input
 */
function sanitizeNumber(value, min = null, max = null) {
  const num = parseFloat(value);
  if (isNaN(num)) return null;
  if (min !== null && num < min) return min;
  if (max !== null && num > max) return max;
  return num;
}

/**
 * Sanitize integer input
 */
function sanitizeInteger(value, min = null, max = null) {
  const num = parseInt(value, 10);
  if (isNaN(num)) return null;
  if (min !== null && num < min) return min;
  if (max !== null && num > max) return max;
  return num;
}

/**
 * Sanitize array input
 */
function sanitizeArray(value, maxLength = 100) {
  if (!Array.isArray(value)) return [];
  return value.slice(0, maxLength);
}

/**
 * Validate email format
 */
function isValidEmail(email) {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return emailRegex.test(email);
}

/**
 * Validate stock symbol
 */
function isValidSymbol(symbol) {
  if (typeof symbol !== "string") return false;
  return /^[A-Z]{1,10}$/.test(symbol.toUpperCase());
}

/**
 * Validate date string
 */
function isValidDate(dateString) {
  const date = new Date(dateString);
  return !isNaN(date.getTime());
}

/**
 * Common validation schemas
 */
const validationSchemas = {
  // Stock symbol validation
  symbol: {
    required: true,
    type: "string",
    sanitizer: (value) => {
      if (typeof value !== "string") return "";
      return value
        .trim()
        .toUpperCase()
        .replace(/[^A-Z0-9]/g, "");
    },
    validator: (value) => /^[A-Z]{1,10}$/.test(value),
    errorMessage: "Symbol must be 1-10 uppercase letters",
  },

  // Multiple symbols (comma-separated)
  symbols: {
    required: true,
    type: "string",
    sanitizer: (value) => {
      if (typeof value !== "string") return "";
      return value
        .split(",")
        .map((s) =>
          s
            .trim()
            .toUpperCase()
            .replace(/[^A-Z0-9]/g, "")
        )
        .filter((s) => s.length > 0)
        .slice(0, 50) // Limit to 50 symbols
        .join(",");
    },
    validator: (value) => {
      if (!value) return false;
      const symbols = value.split(",");
      return (
        symbols.length > 0 &&
        symbols.length <= 50 &&
        symbols.every((s) => /^[A-Z]{1,10}$/.test(s.trim()))
      );
    },
    errorMessage:
      "Symbols must be comma-separated list of 1-50 valid stock symbols",
  },

  // Pagination limit
  limit: {
    required: false,
    type: "number",
    sanitizer: (value) => sanitizeInteger(value, 1, 1000),
    validator: (value) => value >= 1 && value <= 1000,
    errorMessage: "Limit must be between 1 and 1000",
    default: 50,
  },

  // Pagination offset
  offset: {
    required: false,
    type: "number",
    sanitizer: (value) => sanitizeInteger(value, 0),
    validator: (value) => value >= 0,
    errorMessage: "Offset must be non-negative",
    default: 0,
  },

  // Date validation
  date: {
    required: false,
    type: "string",
    sanitizer: (value) => {
      if (!value) return null;
      const date = new Date(value);
      return isNaN(date.getTime()) ? null : date.toISOString().split("T")[0];
    },
    validator: (value) => !value || isValidDate(value),
    errorMessage: "Date must be in valid format (YYYY-MM-DD)",
  },

  // Price range validation
  priceMin: {
    required: false,
    type: "number",
    sanitizer: (value) => sanitizeNumber(value, 0),
    validator: (value) => value >= 0,
    errorMessage: "Minimum price must be non-negative",
  },

  priceMax: {
    required: false,
    type: "number",
    sanitizer: (value) => sanitizeNumber(value, 0),
    validator: (value) => value >= 0,
    errorMessage: "Maximum price must be non-negative",
  },

  // Market cap validation
  marketCapMin: {
    required: false,
    type: "number",
    sanitizer: (value) => sanitizeNumber(value, 0),
    validator: (value) => value >= 0,
    errorMessage: "Minimum market cap must be non-negative",
  },

  marketCapMax: {
    required: false,
    type: "number",
    sanitizer: (value) => sanitizeNumber(value, 0),
    validator: (value) => value >= 0,
    errorMessage: "Maximum market cap must be non-negative",
  },

  // Sector validation
  sector: {
    required: false,
    type: "string",
    sanitizer: (value) => sanitizeString(value, 50),
    validator: (value) => !value || value.length <= 50,
    errorMessage: "Sector must be 50 characters or less",
  },

  // Industry validation
  industry: {
    required: false,
    type: "string",
    sanitizer: (value) => sanitizeString(value, 100),
    validator: (value) => !value || value.length <= 100,
    errorMessage: "Industry must be 100 characters or less",
  },

  // Sort field validation
  sortBy: {
    required: false,
    type: "string",
    sanitizer: (value) => sanitizeString(value, 50),
    validator: (value) => {
      if (!value) return true;
      const validSortFields = [
        "symbol",
        "price",
        "marketCap",
        "volume",
        "change",
        "changePercent",
        "pe",
        "eps",
        "dividend",
        "beta",
        "rsi",
        "ma50",
        "ma200",
      ];
      return validSortFields.includes(value);
    },
    errorMessage: "Invalid sort field",
  },

  // Sort order validation
  sortOrder: {
    required: false,
    type: "string",
    sanitizer: (value) => {
      if (typeof value !== "string") return "asc";
      return value.toLowerCase() === "desc" ? "desc" : "asc";
    },
    validator: (value) => ["asc", "desc"].includes(value),
    errorMessage: 'Sort order must be "asc" or "desc"',
    default: "asc",
  },

  // Timeframe validation
  timeframe: {
    required: false,
    type: "string",
    sanitizer: (value) => sanitizeString(value, 10),
    validator: (value) => {
      if (!value) return true;
      const validTimeframes = [
        "1Min",
        "5Min",
        "15Min",
        "1Hour",
        "1Day",
        "1Week",
        "1Month",
      ];
      return validTimeframes.includes(value);
    },
    errorMessage: "Invalid timeframe",
    default: "1Day",
  },
};

/**
 * Create validation middleware for specific fields
 */
function createValidationMiddleware(fieldSchemas) {
  return (req, res, next) => {
    const errors = [];
    const validatedData = {};

    // Process each field in the schema
    for (const [fieldName, schema] of Object.entries(fieldSchemas)) {
      let value =
        req.query[fieldName] || req.body[fieldName] || req.params[fieldName];

      // Check required fields
      if (
        schema.required &&
        (value === undefined || value === null || value === "")
      ) {
        errors.push({
          field: fieldName,
          message: schema.errorMessage || `${fieldName} is required`,
          code: "REQUIRED_FIELD_MISSING",
        });
        continue;
      }

      // Apply default value if not provided
      if (value === undefined || value === null || value === "") {
        if (schema.default !== undefined) {
          value = schema.default;
        } else if (!schema.required) {
          continue; // Skip optional fields that are not provided
        }
      }

      // Sanitize the value
      if (schema.sanitizer && typeof schema.sanitizer === "function") {
        value = schema.sanitizer(value);
      }

      // Validate the sanitized value
      if (schema.validator && typeof schema.validator === "function") {
        if (!schema.validator(value)) {
          errors.push({
            field: fieldName,
            message: schema.errorMessage || `Invalid ${fieldName}`,
            code: "VALIDATION_FAILED",
            value: value,
          });
          continue;
        }
      }

      // Store validated and sanitized value
      validatedData[fieldName] = value;
    }

    // If there are validation errors, return them
    if (errors.length > 0) {
      return res.status(422).json(validationError(errors).response);
    }

    // Add validated data to request object
    req.validated = validatedData;
    next();
  };
}

/**
 * Validate request body against schema
 */
function validateBody(schema) {
  return (req, res, next) => {
    const errors = [];
    const validatedData = {};

    for (const [fieldName, fieldSchema] of Object.entries(schema)) {
      const value = req.body[fieldName];

      if (fieldSchema.required && (value === undefined || value === null)) {
        errors.push({
          field: fieldName,
          message: `${fieldName} is required`,
          code: "REQUIRED_FIELD_MISSING",
        });
        continue;
      }

      if (value !== undefined && value !== null) {
        if (fieldSchema.sanitizer) {
          validatedData[fieldName] = fieldSchema.sanitizer(value);
        } else {
          validatedData[fieldName] = value;
        }

        if (
          fieldSchema.validator &&
          !fieldSchema.validator(validatedData[fieldName])
        ) {
          errors.push({
            field: fieldName,
            message: fieldSchema.errorMessage || `Invalid ${fieldName}`,
            code: "VALIDATION_FAILED",
          });
        }
      }
    }

    if (errors.length > 0) {
      return res.status(422).json(validationError(errors).response);
    }

    req.validatedBody = validatedData;
    next();
  };
}

/**
 * Validate query parameters against schema
 */
function validateQuery(schema) {
  return (req, res, next) => {
    const errors = [];
    const validatedData = {};

    for (const [fieldName, fieldSchema] of Object.entries(schema)) {
      let value = req.query[fieldName];

      if (
        fieldSchema.required &&
        (value === undefined || value === null || value === "")
      ) {
        errors.push({
          field: fieldName,
          message: `${fieldName} is required`,
          code: "REQUIRED_FIELD_MISSING",
        });
        continue;
      }

      if (value !== undefined && value !== null && value !== "") {
        if (fieldSchema.sanitizer) {
          value = fieldSchema.sanitizer(value);
        }

        if (fieldSchema.validator && !fieldSchema.validator(value)) {
          errors.push({
            field: fieldName,
            message: fieldSchema.errorMessage || `Invalid ${fieldName}`,
            code: "VALIDATION_FAILED",
            value: value,
          });
          continue;
        }

        validatedData[fieldName] = value;
      } else if (fieldSchema.default !== undefined) {
        validatedData[fieldName] = fieldSchema.default;
      }
    }

    if (errors.length > 0) {
      return res.status(422).json(validationError(errors).response);
    }

    req.validatedQuery = validatedData;
    next();
  };
}

/**
 * Common validation middleware presets
 */
const commonValidations = {
  // Pagination validation
  pagination: createValidationMiddleware({
    limit: validationSchemas.limit,
    offset: validationSchemas.offset,
  }),

  // Stock symbol validation
  symbolParam: createValidationMiddleware({
    symbol: validationSchemas.symbol,
  }),

  // Multiple symbols validation
  symbolsParam: createValidationMiddleware({
    symbols: validationSchemas.symbols,
  }),

  // Date range validation
  dateRange: createValidationMiddleware({
    startDate: validationSchemas.date,
    endDate: validationSchemas.date,
  }),

  // Screening filters validation
  screeningFilters: createValidationMiddleware({
    priceMin: validationSchemas.priceMin,
    priceMax: validationSchemas.priceMax,
    marketCapMin: validationSchemas.marketCapMin,
    marketCapMax: validationSchemas.marketCapMax,
    sector: validationSchemas.sector,
    industry: validationSchemas.industry,
    sortBy: validationSchemas.sortBy,
    sortOrder: validationSchemas.sortOrder,
    limit: validationSchemas.limit,
    offset: validationSchemas.offset,
  }),
};

/**
 * Sanitizers object for backwards compatibility
 * Provides the API expected by stocks.js route
 */
const sanitizers = {
  string: (value, options = {}) => {
    if (typeof value !== "string") return "";
    
    let sanitized = value.trim();
    
    // Apply maxLength if provided
    if (options.maxLength) {
      sanitized = sanitized.slice(0, options.maxLength);
    }
    
    // Apply alphaNumOnly filter if specified
    if (options.alphaNumOnly === true) {
      sanitized = sanitized.replace(/[^a-zA-Z0-9]/g, "");
    }
    
    // Apply escapeHTML if specified
    if (options.escapeHTML === true) {
      sanitized = sanitized
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#x27;");
    }
    
    return sanitized;
  },
  
  number: sanitizeNumber,
  integer: sanitizeInteger,
  array: sanitizeArray,
};

module.exports = {
  createValidationMiddleware,
  validateBody,
  validateQuery,
  validationSchemas,
  commonValidations,
  sanitizers,
  sanitizeString,
  sanitizeNumber,
  sanitizeInteger,
  sanitizeArray,
  isValidEmail,
  isValidSymbol,
  isValidDate,
};
