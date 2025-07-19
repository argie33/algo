/**
 * Business Validation Middleware
 * Provides financial business rule validation with standardized error responses
 */

const { body, param, query, validationResult } = require('express-validator');
const { logError, formatErrorResponse } = require('./universalErrorHandler');

/**
 * Enhanced validation result handler that integrates with universal error handling
 */
function handleValidationResult(req, res, next) {
  const errors = validationResult(req);
  
  if (!errors.isEmpty()) {
    const validationError = new Error('Business validation failed');
    validationError.name = 'BusinessValidationError';
    validationError.status = 400;
    validationError.validationErrors = formatValidationErrors(errors.array());
    
    // Log validation error with enhanced context
    logError(validationError, req, {
      validationErrors: validationError.validationErrors,
      requestBody: req.body,
      requestParams: req.params,
      requestQuery: req.query,
      businessRule: 'INPUT_VALIDATION'
    });
    
    // Format comprehensive error response
    const { statusCode, response } = formatErrorResponse(validationError, req);
    
    // Add validation-specific details
    response.error.validation = validationError.validationErrors;
    response.error.code = 'BUSINESS_VALIDATION_ERROR';
    
    return res.status(statusCode).json(response);
  }
  
  next();
}

/**
 * Format validation errors with business context
 */
function formatValidationErrors(errors) {
  return errors.map(error => ({
    field: error.param || error.path,
    message: error.msg,
    value: error.value,
    location: error.location,
    businessRule: error.businessRule || 'FIELD_VALIDATION'
  }));
}

/**
 * Financial business validation schemas
 */
const financialValidation = {
  // Email validation for financial services
  email: body('email')
    .isEmail()
    .normalizeEmail()
    .withMessage('Valid email address is required for account verification')
    .custom(async (value, { req }) => {
      // Business rule: Check for disposable email domains
      const disposableDomains = ['tempmail.org', '10minutemail.com', 'guerrillamail.com'];
      const domain = value.split('@')[1];
      if (disposableDomains.includes(domain)) {
        throw new Error('Disposable email addresses are not allowed for financial accounts');
      }
      return true;
    }),

  // Password validation for financial security requirements
  password: body('password')
    .isLength({ min: 12 })
    .withMessage('Password must be at least 12 characters for financial account security')
    .matches(/^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]/)
    .withMessage('Password must contain uppercase, lowercase, number, and special character')
    .custom(async (value, { req }) => {
      // Business rule: Check against common financial passwords
      const commonPasswords = ['password123', 'trading123', 'finance123'];
      if (commonPasswords.includes(value.toLowerCase())) {
        throw new Error('Password is too common for financial account security');
      }
      return true;
    }),

  // Financial amount validation with business rules
  amount: (field = 'amount', options = {}) => body(field)
    .isFloat({ gt: 0 })
    .withMessage(`${field} must be a positive number`)
    .custom(async (value, { req }) => {
      // Business rule: Check maximum transaction limits
      const maxAmount = options.maxAmount || 100000;
      if (value > maxAmount) {
        const error = new Error(`${field} exceeds maximum allowed transaction amount of $${maxAmount}`);
        error.businessRule = 'TRANSACTION_LIMIT';
        throw error;
      }
      
      // Business rule: Check minimum meaningful amounts
      const minAmount = options.minAmount || 0.01;
      if (value < minAmount) {
        const error = new Error(`${field} below minimum meaningful amount of $${minAmount}`);
        error.businessRule = 'MINIMUM_AMOUNT';
        throw error;
      }
      
      // Business rule: Check for suspicious round numbers (potential testing)
      if (value >= 1000 && value % 1000 === 0 && !options.allowRoundNumbers) {
        const error = new Error(`${field} appears to be a test amount - please use actual transaction amount`);
        error.businessRule = 'SUSPICIOUS_AMOUNT';
        throw error;
      }
      
      return true;
    }),

  // Stock quantity validation with position limits
  quantity: (field = 'quantity', options = {}) => body(field)
    .isInt({ gt: 0 })
    .withMessage(`${field} must be a positive integer`)
    .custom(async (value, { req }) => {
      // Business rule: Check position limits
      const maxQuantity = options.maxQuantity || 10000;
      if (value > maxQuantity) {
        const error = new Error(`${field} exceeds maximum position limit of ${maxQuantity} shares`);
        error.businessRule = 'POSITION_LIMIT';
        throw error;
      }
      
      // Business rule: Check for odd lots in certain contexts
      if (options.requireEvenLots && value % 100 !== 0) {
        const error = new Error(`${field} must be in round lots (multiples of 100 shares)`);
        error.businessRule = 'ODD_LOT_RESTRICTION';
        throw error;
      }
      
      return true;
    }),

  // Stock symbol validation with exchange rules
  symbol: (field = 'symbol') => body(field)
    .matches(/^[A-Z]{1,5}$/)
    .withMessage('Stock symbol must be 1-5 uppercase letters')
    .custom(async (value, { req }) => {
      // Business rule: Check against reserved symbols
      const reservedSymbols = ['TEST', 'FAKE', 'NULL'];
      if (reservedSymbols.includes(value)) {
        const error = new Error(`Symbol ${value} is reserved and cannot be traded`);
        error.businessRule = 'RESERVED_SYMBOL';
        throw error;
      }
      
      // Business rule: Symbol format validation for different exchanges
      if (value.length === 1 && !['A', 'T', 'F', 'X'].includes(value)) {
        const error = new Error(`Single-letter symbol ${value} is not valid for retail trading`);
        error.businessRule = 'INVALID_SYMBOL_FORMAT';
        throw error;
      }
      
      return true;
    }),

  // Portfolio name with business requirements
  portfolioName: body('name')
    .isLength({ min: 1, max: 100 })
    .trim()
    .withMessage('Portfolio name must be 1-100 characters')
    .custom(async (value, { req }) => {
      // Business rule: Check for duplicate portfolio names for user
      const userId = req.user?.sub;
      if (userId) {
        // TODO: Check database for existing portfolio names
        // This would involve a database query to check for duplicates
      }
      
      // Business rule: Prevent misleading portfolio names
      const misleadingTerms = ['test', 'demo', 'fake', 'sample'];
      if (misleadingTerms.some(term => value.toLowerCase().includes(term))) {
        const error = new Error('Portfolio name cannot contain test or demo terminology');
        error.businessRule = 'MISLEADING_NAME';
        throw error;
      }
      
      return true;
    }),

  // Trading order validation with market rules
  orderValidation: [
    body('orderType')
      .isIn(['market', 'limit', 'stop', 'stop_limit'])
      .withMessage('Invalid order type'),
    
    body('side')
      .isIn(['buy', 'sell'])
      .withMessage('Order side must be buy or sell'),
    
    body('timeInForce')
      .isIn(['day', 'gtc', 'ioc', 'fok'])
      .withMessage('Invalid time in force value'),
    
    body().custom(async (value, { req }) => {
      const { orderType, side, quantity, limitPrice, stopPrice } = req.body;
      
      // Business rule: Limit orders must have limit price
      if (orderType === 'limit' && !limitPrice) {
        const error = new Error('Limit orders must specify a limit price');
        error.businessRule = 'MISSING_LIMIT_PRICE';
        throw error;
      }
      
      // Business rule: Stop orders must have stop price
      if ((orderType === 'stop' || orderType === 'stop_limit') && !stopPrice) {
        const error = new Error('Stop orders must specify a stop price');
        error.businessRule = 'MISSING_STOP_PRICE';
        throw error;
      }
      
      // Business rule: Stop limit orders need both prices
      if (orderType === 'stop_limit' && (!stopPrice || !limitPrice)) {
        const error = new Error('Stop limit orders must specify both stop and limit prices');
        error.businessRule = 'MISSING_STOP_LIMIT_PRICES';
        throw error;
      }
      
      // Business rule: Price relationship validation
      if (orderType === 'stop_limit' && side === 'buy' && stopPrice > limitPrice) {
        const error = new Error('For buy stop limit orders, stop price must be less than or equal to limit price');
        error.businessRule = 'INVALID_PRICE_RELATIONSHIP';
        throw error;
      }
      
      if (orderType === 'stop_limit' && side === 'sell' && stopPrice < limitPrice) {
        const error = new Error('For sell stop limit orders, stop price must be greater than or equal to limit price');
        error.businessRule = 'INVALID_PRICE_RELATIONSHIP';
        throw error;
      }
      
      return true;
    })
  ],

  // Risk tolerance validation
  riskTolerance: body('riskTolerance')
    .isIn(['conservative', 'moderate', 'aggressive'])
    .withMessage('Risk tolerance must be conservative, moderate, or aggressive')
    .custom(async (value, { req }) => {
      // Business rule: Age-based risk tolerance validation
      const userAge = req.body.age || req.user?.age;
      if (userAge && userAge > 65 && value === 'aggressive') {
        const error = new Error('Aggressive risk tolerance may not be suitable for investors over 65');
        error.businessRule = 'AGE_RISK_MISMATCH';
        throw error;
      }
      
      return true;
    }),

  // API key validation with security requirements
  apiKey: (provider = 'alpaca') => body(`${provider}Key`)
    .isLength({ min: 20, max: 200 })
    .withMessage(`${provider} API key format is invalid`)
    .custom(async (value, { req }) => {
      // Business rule: API key format validation by provider
      if (provider === 'alpaca' && !/^[A-Z0-9]{20,40}$/.test(value)) {
        const error = new Error('Alpaca API key must be 20-40 uppercase alphanumeric characters');
        error.businessRule = 'INVALID_API_KEY_FORMAT';
        throw error;
      }
      
      // Business rule: Prevent test API keys in production
      if (process.env.NODE_ENV === 'production' && value.includes('test')) {
        const error = new Error('Test API keys cannot be used in production environment');
        error.businessRule = 'TEST_KEY_IN_PRODUCTION';
        throw error;
      }
      
      return true;
    }),

  // Date range validation for financial data
  dateRange: (startField = 'startDate', endField = 'endDate') => [
    body(startField).isISO8601().withMessage(`${startField} must be a valid date`),
    body(endField).isISO8601().withMessage(`${endField} must be a valid date`),
    body().custom(async (value, { req }) => {
      const start = new Date(req.body[startField]);
      const end = new Date(req.body[endField]);
      const now = new Date();
      
      // Business rule: Start date must be before end date
      if (start >= end) {
        const error = new Error(`${startField} must be before ${endField}`);
        error.businessRule = 'INVALID_DATE_ORDER';
        throw error;
      }
      
      // Business rule: Cannot request future data
      if (start > now || end > now) {
        const error = new Error('Cannot request data from future dates');
        error.businessRule = 'FUTURE_DATE_REQUEST';
        throw error;
      }
      
      // Business rule: Limit historical data range
      const maxDaysBack = 365 * 5; // 5 years
      const daysDiff = (now - start) / (1000 * 60 * 60 * 24);
      if (daysDiff > maxDaysBack) {
        const error = new Error(`Historical data limited to ${maxDaysBack} days`);
        error.businessRule = 'EXCESSIVE_HISTORICAL_RANGE';
        throw error;
      }
      
      // Business rule: Prevent excessive date ranges that could impact performance
      const requestedDays = (end - start) / (1000 * 60 * 60 * 24);
      if (requestedDays > 365) {
        const error = new Error('Date range cannot exceed 365 days');
        error.businessRule = 'EXCESSIVE_DATE_RANGE';
        throw error;
      }
      
      return true;
    })
  ]
};

/**
 * Route-specific validation bundles with business rules
 */
const businessValidationBundles = {
  // User registration with financial compliance
  register: [
    financialValidation.email,
    financialValidation.password,
    body('firstName').isLength({ min: 1, max: 50 }).trim().escape()
      .custom(async (value) => {
        // Business rule: Name validation for compliance
        if (value.toLowerCase() === 'test' || value.toLowerCase() === 'demo') {
          throw new Error('Test names are not allowed for financial accounts');
        }
        return true;
      }),
    body('lastName').isLength({ min: 1, max: 50 }).trim().escape(),
    body('dateOfBirth').isISO8601().withMessage('Valid date of birth required')
      .custom(async (value) => {
        const birthDate = new Date(value);
        const age = (Date.now() - birthDate.getTime()) / (1000 * 60 * 60 * 24 * 365);
        
        // Business rule: Age verification for financial services
        if (age < 18) {
          const error = new Error('Must be 18 or older to open a financial account');
          error.businessRule = 'AGE_RESTRICTION';
          throw error;
        }
        
        if (age > 120) {
          const error = new Error('Invalid date of birth');
          error.businessRule = 'INVALID_AGE';
          throw error;
        }
        
        return true;
      }),
    handleValidationResult
  ],

  // Portfolio creation with business rules
  createPortfolio: [
    financialValidation.portfolioName,
    financialValidation.riskTolerance,
    body('description').optional().isLength({ max: 500 }).trim().escape(),
    body('initialBalance').optional().custom(async (value) => {
      if (value !== undefined) {
        const balance = parseFloat(value);
        if (balance < 100) {
          const error = new Error('Initial portfolio balance must be at least $100');
          error.businessRule = 'MINIMUM_PORTFOLIO_BALANCE';
          throw error;
        }
      }
      return true;
    }),
    handleValidationResult
  ],

  // Trading order placement with comprehensive business rules
  placeOrder: [
    financialValidation.symbol(),
    financialValidation.quantity('quantity', { maxQuantity: 10000 }),
    ...financialValidation.orderValidation,
    body().custom(async (value, { req }) => {
      // Business rule: Market hours validation
      const now = new Date();
      const hour = now.getHours();
      const isWeekend = now.getDay() === 0 || now.getDay() === 6;
      
      // Extended hours trading requires special handling
      if (isWeekend) {
        const error = new Error('Trading is not allowed on weekends');
        error.businessRule = 'WEEKEND_TRADING_RESTRICTION';
        throw error;
      }
      
      // Regular market hours: 9:30 AM - 4:00 PM ET
      if (hour < 9 || hour >= 16) {
        // Allow but warn for extended hours
        req.extendedHours = true;
      }
      
      return true;
    }),
    handleValidationResult
  ],

  // Settings update with security validations
  updateSettings: [
    body('notifications').optional().isObject(),
    body('preferences').optional().isObject(),
    body('riskSettings').optional().isObject()
      .custom(async (value) => {
        if (value && value.maxDailyLoss) {
          const maxLoss = parseFloat(value.maxDailyLoss);
          if (maxLoss <= 0 || maxLoss > 100000) {
            const error = new Error('Daily loss limit must be between $1 and $100,000');
            error.businessRule = 'INVALID_RISK_LIMIT';
            throw error;
          }
        }
        return true;
      }),
    handleValidationResult
  ],

  // API key updates with validation
  updateApiKeys: [
    financialValidation.apiKey('alpaca'),
    body('alpacaSecret').optional().custom(value => {
      if (value && !/^[A-Za-z0-9\/\+]{40,}$/.test(value)) {
        const error = new Error('Invalid Alpaca secret key format');
        error.businessRule = 'INVALID_SECRET_FORMAT';
        throw error;
      }
      return true;
    }),
    handleValidationResult
  ],

  // Historical data requests with business limits
  getHistoricalData: [
    financialValidation.symbol(),
    ...financialValidation.dateRange(),
    query('timeframe')
      .optional()
      .isIn(['1min', '5min', '15min', '30min', '1hour', '1day', '1week', '1month'])
      .withMessage('Invalid timeframe'),
    handleValidationResult
  ],

  // Watchlist operations
  addToWatchlist: [
    financialValidation.symbol(),
    body('notes').optional().isLength({ max: 200 }).trim().escape(),
    body().custom(async (value, { req }) => {
      // Business rule: Watchlist size limits
      const userId = req.user?.sub;
      if (userId) {
        // TODO: Check current watchlist size from database
        // Limit to reasonable number like 100 symbols
      }
      return true;
    }),
    handleValidationResult
  ],

  // Generic validations
  requireUserId: [
    param('userId').isUUID().withMessage('Invalid user ID format'),
    handleValidationResult
  ],
  
  requirePortfolioId: [
    param('portfolioId').isUUID().withMessage('Invalid portfolio ID format'),
    handleValidationResult
  ]
};

/**
 * Advanced business rule validator for complex financial logic
 */
function createFinancialBusinessValidator(validatorFn, errorMessage, businessRuleCode) {
  return async (req, res, next) => {
    try {
      const validation = await validatorFn(req);
      
      if (!validation.isValid) {
        const error = new Error(errorMessage);
        error.name = 'FinancialBusinessRuleError';
        error.status = 400;
        error.businessRule = businessRuleCode;
        error.details = validation.details;
        
        logError(error, req, {
          businessRule: businessRuleCode,
          validationDetails: validation.details,
          requestData: {
            body: req.body,
            params: req.params,
            query: req.query,
            user: req.user?.sub
          }
        });
        
        const { statusCode, response } = formatErrorResponse(error, req);
        response.error.businessRule = businessRuleCode;
        response.error.details = validation.details;
        
        return res.status(statusCode).json(response);
      }
      
      next();
    } catch (error) {
      next(error);
    }
  };
}

module.exports = {
  financialValidation,
  businessValidationBundles,
  handleValidationResult,
  createFinancialBusinessValidator,
  formatValidationErrors
};