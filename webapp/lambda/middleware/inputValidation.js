/**
 * Input Validation and Sanitization Middleware
 * Comprehensive security validation for financial trading platform
 */

const validator = require('validator');
const { body, param, query, validationResult } = require('express-validator');

class InputValidationMiddleware {
    constructor() {
        this.maxStringLength = 1000;
        this.maxArrayLength = 100;
        this.allowedCurrencies = ['USD', 'EUR', 'GBP', 'JPY', 'CAD', 'AUD', 'CHF'];
        this.allowedTimeframes = ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w', '1M'];
    }

    /**
     * Sanitize and validate financial symbol
     */
    validateSymbol() {
        return [
            body('symbol')
                .optional()
                .isString()
                .isLength({ min: 1, max: 10 })
                .matches(/^[A-Z0-9.-]+$/)
                .withMessage('Symbol must be alphanumeric with dots/hyphens only'),
            param('symbol')
                .optional()
                .isString()
                .isLength({ min: 1, max: 10 })
                .matches(/^[A-Z0-9.-]+$/)
                .withMessage('Symbol must be alphanumeric with dots/hyphens only'),
            query('symbol')
                .optional()
                .isString()
                .isLength({ min: 1, max: 10 })
                .matches(/^[A-Z0-9.-]+$/)
                .withMessage('Symbol must be alphanumeric with dots/hyphens only')
        ];
    }

    /**
     * Validate financial amount/price
     */
    validateAmount() {
        return [
            body('amount')
                .optional()
                .isNumeric()
                .isFloat({ min: 0, max: 1000000000 })
                .withMessage('Amount must be a positive number under 1 billion'),
            body('price')
                .optional()
                .isNumeric()
                .isFloat({ min: 0.01, max: 100000 })
                .withMessage('Price must be between 0.01 and 100,000'),
            body('quantity')
                .optional()
                .isInt({ min: 1, max: 1000000 })
                .withMessage('Quantity must be an integer between 1 and 1,000,000')
        ];
    }

    /**
     * Validate date ranges
     */
    validateDateRange() {
        return [
            body('startDate')
                .optional()
                .isISO8601()
                .withMessage('Start date must be valid ISO8601 format'),
            body('endDate')
                .optional()
                .isISO8601()
                .withMessage('End date must be valid ISO8601 format'),
            query('startDate')
                .optional()
                .isISO8601()
                .withMessage('Start date must be valid ISO8601 format'),
            query('endDate')
                .optional()
                .isISO8601()
                .withMessage('End date must be valid ISO8601 format')
        ];
    }

    /**
     * Validate pagination parameters
     */
    validatePagination() {
        return [
            query('page')
                .optional()
                .isInt({ min: 1, max: 10000 })
                .withMessage('Page must be an integer between 1 and 10,000'),
            query('limit')
                .optional()
                .isInt({ min: 1, max: 1000 })
                .withMessage('Limit must be an integer between 1 and 1,000'),
            query('offset')
                .optional()
                .isInt({ min: 0, max: 100000 })
                .withMessage('Offset must be a non-negative integer under 100,000')
        ];
    }

    /**
     * Validate API key format
     */
    validateApiKey() {
        return [
            body('apiKey')
                .optional()
                .isString()
                .isLength({ min: 10, max: 200 })
                .matches(/^[A-Za-z0-9_-]+$/)
                .withMessage('API key must be alphanumeric with underscores/hyphens only'),
            body('apiSecret')
                .optional()
                .isString()
                .isLength({ min: 10, max: 200 })
                .matches(/^[A-Za-z0-9_-]+$/)
                .withMessage('API secret must be alphanumeric with underscores/hyphens only')
        ];
    }

    /**
     * Validate trading order parameters
     */
    validateTradingOrder() {
        return [
            body('orderType')
                .isIn(['market', 'limit', 'stop', 'stop_limit'])
                .withMessage('Order type must be market, limit, stop, or stop_limit'),
            body('side')
                .isIn(['buy', 'sell'])
                .withMessage('Side must be buy or sell'),
            body('timeInForce')
                .optional()
                .isIn(['day', 'gtc', 'ioc', 'fok'])
                .withMessage('Time in force must be day, gtc, ioc, or fok'),
            ...this.validateSymbol(),
            ...this.validateAmount()
        ];
    }

    /**
     * Validate portfolio parameters
     */
    validatePortfolio() {
        return [
            body('portfolioName')
                .optional()
                .isString()
                .isLength({ min: 1, max: 100 })
                .matches(/^[A-Za-z0-9\s_-]+$/)
                .withMessage('Portfolio name must be alphanumeric with spaces/underscores/hyphens'),
            body('currency')
                .optional()
                .isIn(this.allowedCurrencies)
                .withMessage(`Currency must be one of: ${this.allowedCurrencies.join(', ')}`),
            body('riskTolerance')
                .optional()
                .isIn(['conservative', 'moderate', 'aggressive'])
                .withMessage('Risk tolerance must be conservative, moderate, or aggressive')
        ];
    }

    /**
     * Validate technical analysis parameters
     */
    validateTechnicalAnalysis() {
        return [
            query('timeframe')
                .optional()
                .isIn(this.allowedTimeframes)
                .withMessage(`Timeframe must be one of: ${this.allowedTimeframes.join(', ')}`),
            query('indicators')
                .optional()
                .isArray({ max: 20 })
                .withMessage('Indicators must be an array with max 20 items'),
            body('period')
                .optional()
                .isInt({ min: 1, max: 500 })
                .withMessage('Period must be an integer between 1 and 500')
        ];
    }

    /**
     * Validate search parameters
     */
    validateSearch() {
        return [
            query('q')
                .optional()
                .isString()
                .isLength({ min: 1, max: 100 })
                .matches(/^[A-Za-z0-9\s.-]+$/)
                .withMessage('Search query must be alphanumeric with spaces/dots/hyphens'),
            query('category')
                .optional()
                .isIn(['stocks', 'crypto', 'forex', 'commodities', 'indices'])
                .withMessage('Category must be stocks, crypto, forex, commodities, or indices')
        ];
    }

    /**
     * Sanitize user input to prevent XSS and injection attacks
     */
    sanitizeInput() {
        return (req, res, next) => {
            // Sanitize string fields recursively
            const sanitizeObject = (obj) => {
                if (typeof obj === 'string') {
                    // Remove potential XSS patterns
                    return validator.escape(obj)
                        .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
                        .replace(/javascript:/gi, '')
                        .replace(/on\w+\s*=/gi, '')
                        .trim();
                } else if (Array.isArray(obj)) {
                    return obj.map(sanitizeObject).slice(0, this.maxArrayLength);
                } else if (obj && typeof obj === 'object') {
                    const sanitized = {};
                    for (const [key, value] of Object.entries(obj)) {
                        if (typeof key === 'string' && key.length <= 100) {
                            sanitized[key] = sanitizeObject(value);
                        }
                    }
                    return sanitized;
                }
                return obj;
            };

            // Sanitize request body, query, and params
            if (req.body) {
                req.body = sanitizeObject(req.body);
            }
            if (req.query) {
                req.query = sanitizeObject(req.query);
            }
            if (req.params) {
                req.params = sanitizeObject(req.params);
            }

            next();
        };
    }

    /**
     * Rate limiting validation
     */
    validateRateLimit() {
        return (req, res, next) => {
            // Check for suspicious request patterns
            const suspiciousPatterns = [
                /union\s+select/i,
                /drop\s+table/i,
                /'.*or.*'.*='.*'/i,
                /script\s*>/i,
                /javascript:/i
            ];

            const requestData = JSON.stringify({
                body: req.body,
                query: req.query,
                params: req.params
            });

            for (const pattern of suspiciousPatterns) {
                if (pattern.test(requestData)) {
                    console.warn(`🚨 Suspicious request pattern detected from ${req.ip}: ${pattern}`);
                    return res.status(400).json({
                        success: false,
                        error: 'Invalid request format',
                        code: 'SUSPICIOUS_PATTERN'
                    });
                }
            }

            next();
        };
    }

    /**
     * Handle validation errors
     */
    handleValidationErrors() {
        return (req, res, next) => {
            const errors = validationResult(req);
            
            if (!errors.isEmpty()) {
                const validationErrors = errors.array().map(error => ({
                    field: error.param,
                    message: error.msg,
                    value: error.value
                }));

                console.warn(`🚨 Validation errors for ${req.method} ${req.path}:`, validationErrors);

                return res.status(400).json({
                    success: false,
                    error: 'Validation failed',
                    code: 'VALIDATION_ERROR',
                    details: validationErrors
                });
            }

            next();
        };
    }

    /**
     * SQL injection prevention
     */
    preventSqlInjection() {
        return (req, res, next) => {
            const sqlPatterns = [
                /(\b(select|insert|update|delete|drop|create|alter|exec|execute)\b)/i,
                /(\b(union|having|group\s+by|order\s+by)\b)/i,
                /(;|\||\|\||&&)/,
                /('|(\\x27)|(\\x2D\\x2D))/i
            ];

            const checkForSql = (obj, path = '') => {
                if (typeof obj === 'string') {
                    for (const pattern of sqlPatterns) {
                        if (pattern.test(obj)) {
                            console.warn(`🚨 Potential SQL injection attempt at ${path}: ${obj.substring(0, 100)}`);
                            return true;
                        }
                    }
                } else if (Array.isArray(obj)) {
                    for (let i = 0; i < obj.length; i++) {
                        if (checkForSql(obj[i], `${path}[${i}]`)) return true;
                    }
                } else if (obj && typeof obj === 'object') {
                    for (const [key, value] of Object.entries(obj)) {
                        if (checkForSql(value, `${path}.${key}`)) return true;
                    }
                }
                return false;
            };

            if (checkForSql(req.body, 'body') || 
                checkForSql(req.query, 'query') || 
                checkForSql(req.params, 'params')) {
                
                return res.status(400).json({
                    success: false,
                    error: 'Invalid request format',
                    code: 'SECURITY_VIOLATION'
                });
            }

            next();
        };
    }

    /**
     * Get validation rules for specific endpoint types
     */
    getValidationRules(endpointType) {
        const rules = {
            trading: [
                ...this.validateTradingOrder(),
                this.handleValidationErrors()
            ],
            portfolio: [
                ...this.validatePortfolio(),
                ...this.validatePagination(),
                this.handleValidationErrors()
            ],
            market: [
                ...this.validateSymbol(),
                ...this.validateDateRange(),
                ...this.validatePagination(),
                this.handleValidationErrors()
            ],
            technical: [
                ...this.validateTechnicalAnalysis(),
                ...this.validateSymbol(),
                this.handleValidationErrors()
            ],
            search: [
                ...this.validateSearch(),
                ...this.validatePagination(),
                this.handleValidationErrors()
            ],
            auth: [
                ...this.validateApiKey(),
                this.handleValidationErrors()
            ]
        };

        return rules[endpointType] || [this.handleValidationErrors()];
    }

    /**
     * Universal security middleware stack
     */
    getSecurityMiddleware() {
        return [
            this.sanitizeInput(),
            this.validateRateLimit(),
            this.preventSqlInjection()
        ];
    }
}

module.exports = InputValidationMiddleware;