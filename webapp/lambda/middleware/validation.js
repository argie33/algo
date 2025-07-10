/**
 * Input Validation and Sanitization Middleware
 * Provides comprehensive input validation for API endpoints
 */

const rateLimit = require('express-rate-limit');
const slowDown = require('express-slow-down');
const helmet = require('helmet');
const validator = require('validator');

/**
 * Rate limiting configurations for different endpoint types
 */
const rateLimitConfigs = {
    // Strict rate limiting for authentication endpoints
    auth: rateLimit({
        windowMs: 15 * 60 * 1000, // 15 minutes
        max: 5, // 5 attempts per window
        message: {
            error: 'Too many authentication attempts, please try again later',
            retryAfter: 15 * 60 // 15 minutes in seconds
        },
        standardHeaders: true,
        legacyHeaders: false,
        skip: (req) => {
            // Skip rate limiting in development mode
            return process.env.NODE_ENV === 'development';
        }
    }),

    // Moderate rate limiting for API endpoints
    api: rateLimit({
        windowMs: 60 * 1000, // 1 minute
        max: 100, // 100 requests per minute
        message: {
            error: 'Too many API requests, please slow down',
            retryAfter: 60
        },
        standardHeaders: true,
        legacyHeaders: false,
        skip: (req) => {
            return process.env.NODE_ENV === 'development';
        }
    }),

    // Lenient rate limiting for trading endpoints (higher frequency needed)
    trading: rateLimit({
        windowMs: 60 * 1000, // 1 minute
        max: 200, // 200 requests per minute
        message: {
            error: 'Trading API rate limit exceeded',
            retryAfter: 60
        },
        standardHeaders: true,
        legacyHeaders: false,
        skip: (req) => {
            return process.env.NODE_ENV === 'development';
        }
    }),

    // Very strict rate limiting for resource-intensive endpoints
    heavy: rateLimit({
        windowMs: 5 * 60 * 1000, // 5 minutes
        max: 10, // 10 requests per 5 minutes
        message: {
            error: 'Rate limit exceeded for resource-intensive operation',
            retryAfter: 5 * 60
        },
        standardHeaders: true,
        legacyHeaders: false
    })
};

/**
 * Slow down configurations to add delays before hard rate limits
 */
const slowDownConfigs = {
    api: slowDown({
        windowMs: 60 * 1000, // 1 minute
        delayAfter: 50, // After 50 requests
        delayMs: 500, // Add 500ms delay
        maxDelayMs: 5000, // Maximum 5 second delay
        skip: (req) => {
            return process.env.NODE_ENV === 'development';
        }
    }),

    trading: slowDown({
        windowMs: 60 * 1000, // 1 minute
        delayAfter: 100, // After 100 requests
        delayMs: 200, // Add 200ms delay
        maxDelayMs: 2000, // Maximum 2 second delay
        skip: (req) => {
            return process.env.NODE_ENV === 'development';
        }
    })
};

/**
 * Input sanitization functions
 */
const sanitizers = {
    // Sanitize string input - remove dangerous characters
    string: (value, options = {}) => {
        if (typeof value !== 'string') return '';
        
        let sanitized = value.trim();
        
        // Remove null bytes
        sanitized = sanitized.replace(/\0/g, '');
        
        // Optional: escape HTML
        if (options.escapeHTML) {
            sanitized = validator.escape(sanitized);
        }
        
        // Optional: remove/replace special characters
        if (options.alphaNumOnly) {
            sanitized = sanitized.replace(/[^a-zA-Z0-9\s]/g, '');
        }
        
        // Length limit
        if (options.maxLength) {
            sanitized = sanitized.slice(0, options.maxLength);
        }
        
        return sanitized;
    },

    // Sanitize email input
    email: (value) => {
        if (!value || typeof value !== 'string') return '';
        return validator.normalizeEmail(value.trim()) || '';
    },

    // Sanitize numeric input
    number: (value, options = {}) => {
        const num = parseFloat(value);
        if (isNaN(num)) return options.defaultValue || 0;
        
        if (options.min !== undefined && num < options.min) return options.min;
        if (options.max !== undefined && num > options.max) return options.max;
        
        return num;
    },

    // Sanitize integer input
    integer: (value, options = {}) => {
        const num = parseInt(value);
        if (isNaN(num)) return options.defaultValue || 0;
        
        if (options.min !== undefined && num < options.min) return options.min;
        if (options.max !== undefined && num > options.max) return options.max;
        
        return num;
    },

    // Sanitize stock symbol
    symbol: (value) => {
        if (!value || typeof value !== 'string') return '';
        return value.trim().toUpperCase().replace(/[^A-Z]/g, '').slice(0, 10);
    },

    // Sanitize boolean input
    boolean: (value) => {
        if (typeof value === 'boolean') return value;
        if (typeof value === 'string') {
            return ['true', '1', 'yes', 'on'].includes(value.toLowerCase());
        }
        return Boolean(value);
    }
};

/**
 * Validation schemas for different types of requests
 */
const validationSchemas = {
    // Stock symbol validation
    stockSymbol: {
        symbol: {
            required: true,
            type: 'string',
            sanitizer: sanitizers.symbol,
            validator: (value) => /^[A-Z]{1,10}$/.test(value),
            errorMessage: 'Symbol must be 1-10 uppercase letters'
        }
    },

    // Pagination validation
    pagination: {
        page: {
            type: 'integer',
            sanitizer: (value) => sanitizers.integer(value, { min: 1, defaultValue: 1 }),
            validator: (value) => value >= 1,
            errorMessage: 'Page must be a positive integer'
        },
        limit: {
            type: 'integer',
            sanitizer: (value) => sanitizers.integer(value, { min: 1, max: 200, defaultValue: 50 }),
            validator: (value) => value >= 1 && value <= 200,
            errorMessage: 'Limit must be between 1 and 200'
        }
    },

    // User input validation
    userInput: {
        email: {
            required: true,
            type: 'string',
            sanitizer: sanitizers.email,
            validator: validator.isEmail,
            errorMessage: 'Invalid email format'
        },
        username: {
            required: true,
            type: 'string',
            sanitizer: (value) => sanitizers.string(value, { maxLength: 50, alphaNumOnly: false }),
            validator: (value) => /^[a-zA-Z0-9_-]{3,50}$/.test(value),
            errorMessage: 'Username must be 3-50 characters, alphanumeric, underscore, or dash'
        }
    },

    // Trading validation
    trade: {
        quantity: {
            required: true,
            type: 'number',
            sanitizer: (value) => sanitizers.number(value, { min: 0.001 }),
            validator: (value) => value > 0 && value <= 1000000,
            errorMessage: 'Quantity must be between 0.001 and 1,000,000'
        },
        price: {
            type: 'number',
            sanitizer: (value) => sanitizers.number(value, { min: 0.01 }),
            validator: (value) => value > 0 && value <= 100000,
            errorMessage: 'Price must be between 0.01 and 100,000'
        }
    }
};

/**
 * Generic validation middleware factory
 */
function createValidationMiddleware(schema, options = {}) {
    return (req, res, next) => {
        const errors = [];
        const sanitized = {};

        // Determine source of data (query, body, params)
        const sources = ['query', 'body', 'params'];
        
        for (const [fieldName, rules] of Object.entries(schema)) {
            let value = null;
            let found = false;

            // Find the field in request sources
            for (const source of sources) {
                if (req[source] && req[source][fieldName] !== undefined) {
                    value = req[source][fieldName];
                    found = true;
                    break;
                }
            }

            // Check if required field is missing
            if (rules.required && (!found || value === null || value === undefined || value === '')) {
                errors.push(`${fieldName} is required`);
                continue;
            }

            // Skip validation if field is not required and not provided
            if (!found && !rules.required) {
                continue;
            }

            // Sanitize the value
            if (rules.sanitizer) {
                value = rules.sanitizer(value);
            }

            // Validate the sanitized value
            if (rules.validator && !rules.validator(value)) {
                errors.push(rules.errorMessage || `${fieldName} is invalid`);
                continue;
            }

            // Store sanitized value
            sanitized[fieldName] = value;
        }

        // If there are validation errors, return them
        if (errors.length > 0) {
            return res.status(400).json({
                error: 'Validation failed',
                details: errors
            });
        }

        // Attach sanitized data to request
        req.validated = sanitized;
        next();
    };
}

/**
 * Request size limiting middleware
 */
const requestSizeLimit = (limit = '1mb') => {
    return (req, res, next) => {
        // This would typically be handled by express.json({ limit })
        // But we can add additional checks here
        const contentLength = req.get('content-length');
        if (contentLength) {
            const sizeInBytes = parseInt(contentLength);
            const limitInBytes = limit.includes('mb') ? 
                parseInt(limit) * 1024 * 1024 : 
                parseInt(limit);
            
            if (sizeInBytes > limitInBytes) {
                return res.status(413).json({
                    error: 'Request too large',
                    maxSize: limit
                });
            }
        }
        next();
    };
};

/**
 * SQL injection prevention middleware
 */
const sqlInjectionPrevention = (req, res, next) => {
    const checkForSqlInjection = (value) => {
        if (typeof value !== 'string') return false;
        
        const sqlPatterns = [
            /(\s|^)(select|insert|update|delete|drop|create|alter|exec|execute|sp_|xp_)/i,
            /(union\s+select|or\s+1\s*=\s*1|and\s+1\s*=\s*1)/i,
            /('|\";|--|\/\*|\*\/)/,
            /(script|javascript|vbscript|onload|onerror)/i
        ];
        
        return sqlPatterns.some(pattern => pattern.test(value));
    };

    const checkObject = (obj) => {
        for (const [key, value] of Object.entries(obj)) {
            if (typeof value === 'string' && checkForSqlInjection(value)) {
                return key;
            }
            if (typeof value === 'object' && value !== null) {
                const nestedCheck = checkObject(value);
                if (nestedCheck) return `${key}.${nestedCheck}`;
            }
        }
        return null;
    };

    // Check query parameters, body, and params
    const sources = [req.query, req.body, req.params].filter(Boolean);
    
    for (const source of sources) {
        const suspiciousField = checkObject(source);
        if (suspiciousField) {
            return res.status(400).json({
                error: 'Invalid input detected',
                field: suspiciousField
            });
        }
    }

    next();
};

/**
 * XSS prevention middleware
 */
const xssPrevention = (req, res, next) => {
    const checkForXss = (value) => {
        if (typeof value !== 'string') return false;
        
        const xssPatterns = [
            /<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi,
            /<iframe\b[^<]*(?:(?!<\/iframe>)<[^<]*)*<\/iframe>/gi,
            /javascript:/gi,
            /on\w+\s*=/gi,
            /<\s*img[^>]+src[^>]*>/gi
        ];
        
        return xssPatterns.some(pattern => pattern.test(value));
    };

    const sanitizeValue = (value) => {
        if (typeof value === 'string') {
            return validator.escape(value);
        }
        return value;
    };

    const sanitizeObject = (obj) => {
        for (const [key, value] of Object.entries(obj)) {
            if (typeof value === 'string') {
                if (checkForXss(value)) {
                    obj[key] = sanitizeValue(value);
                }
            } else if (typeof value === 'object' && value !== null) {
                sanitizeObject(value);
            }
        }
    };

    // Sanitize inputs
    [req.query, req.body, req.params].filter(Boolean).forEach(sanitizeObject);
    
    next();
};

module.exports = {
    rateLimitConfigs,
    slowDownConfigs,
    sanitizers,
    validationSchemas,
    createValidationMiddleware,
    requestSizeLimit,
    sqlInjectionPrevention,
    xssPrevention
};