/**
 * Schema Validation Utilities for API Contract Testing
 * 
 * Provides reusable schema validators for consistent API response validation.
 * Ensures all endpoints maintain expected data structures and types.
 */

/**
 * Standard API response wrapper schema
 */
export const standardResponseSchema = {
  success: 'boolean',
  timestamp: 'string', // ISO 8601 format
  data: 'object', // Present on success
  error: 'string', // Present on failure
  warnings: 'array' // Optional warnings array
};

/**
 * Health endpoint schemas
 */
export const healthSchemas = {
  basic: {
    status: ['healthy', 'degraded', 'unhealthy'],
    timestamp: 'string',
    uptime: 'number',
    version: 'string' // semver format
  },
  
  database: {
    status: ['connected', 'disconnected', 'error'],
    responseTime: 'number',
    activeConnections: 'number',
    maxConnections: 'number'
  },
  
  detailed: {
    status: ['healthy', 'degraded', 'unhealthy'],
    timestamp: 'string',
    uptime: 'number',
    version: 'string',
    services: {
      database: 'object',
      cache: 'object',
      external_apis: 'object'
    },
    metrics: {
      memory: 'object',
      cpu: 'object',
      requests: 'object'
    }
  }
};

/**
 * Portfolio endpoint schemas
 */
export const portfolioSchemas = {
  holdings: {
    totalValue: 'number',
    totalGainLoss: 'number',
    totalGainLossPercent: 'number',
    dayGainLoss: 'number',
    dayGainLossPercent: 'number',
    lastUpdated: 'string',
    holdings: {
      type: 'array',
      items: {
        symbol: 'string',
        quantity: 'number',
        avgPrice: 'number',
        currentPrice: 'number',
        totalValue: 'number',
        gainLoss: 'number',
        gainLossPercent: 'number',
        sector: 'string',
        lastUpdated: 'string'
      }
    }
  },
  
  summary: {
    totalValue: 'number',
    totalGainLoss: 'number',
    totalGainLossPercent: 'number',
    lastUpdated: 'string',
    topPerformers: {
      type: 'array',
      items: {
        symbol: 'string',
        gainLossPercent: 'number',
        totalValue: 'number'
      }
    },
    sectorAllocation: {
      type: 'array',
      items: {
        sector: 'string',
        percentage: 'number',
        value: 'number',
        gainLoss: 'number'
      }
    }
  },
  
  performance: {
    periods: {
      '1D': 'number',
      '1W': 'number', 
      '1M': 'number',
      '3M': 'number',
      '6M': 'number',
      '1Y': 'number',
      'YTD': 'number'
    },
    benchmarkComparison: {
      portfolio: 'number',
      sp500: 'number',
      outperformance: 'number'
    },
    riskMetrics: {
      volatility: 'number',
      sharpeRatio: 'number',
      beta: 'number',
      maxDrawdown: 'number'
    }
  }
};

/**
 * Market data endpoint schemas
 */
export const marketSchemas = {
  overview: {
    indices: 'object', // Dynamic keys for different indices
    sectors: {
      type: 'array',
      items: {
        name: 'string',
        performance: 'number',
        trend: ['up', 'down', 'neutral'],
        volume: 'number'
      }
    },
    marketSentiment: ['bullish', 'bearish', 'neutral'],
    vixLevel: 'number',
    lastUpdated: 'string'
  },
  
  stockPrice: {
    symbol: 'string',
    price: 'number',
    change: 'number',
    changePercent: 'number',
    volume: 'number',
    high: 'number',
    low: 'number',
    open: 'number',
    previousClose: 'number',
    marketCap: 'number',
    peRatio: 'number',
    dividendYield: 'number',
    lastUpdated: 'string'
  },
  
  historicalData: {
    symbol: 'string',
    period: 'string',
    data: {
      type: 'array',
      items: {
        date: 'string',
        open: 'number',
        high: 'number', 
        low: 'number',
        close: 'number',
        volume: 'number',
        adjustedClose: 'number'
      }
    }
  }
};

/**
 * Settings endpoint schemas
 */
export const settingsSchemas = {
  apiKeys: {
    configured: {
      type: 'array',
      items: ['alpaca', 'polygon', 'finnhub', 'alpha_vantage', 'iex']
    },
    valid: {
      type: 'array', 
      items: ['alpaca', 'polygon', 'finnhub', 'alpha_vantage', 'iex']
    },
    lastValidated: 'string'
  },
  
  userPreferences: {
    currency: ['USD', 'EUR', 'GBP', 'CAD'],
    timezone: 'string',
    dateFormat: 'string',
    numberFormat: 'string',
    theme: ['light', 'dark', 'auto'],
    notifications: {
      email: 'boolean',
      push: 'boolean',
      priceAlerts: 'boolean',
      newsAlerts: 'boolean'
    }
  },
  
  profile: {
    username: 'string',
    email: 'string',
    name: 'string',
    avatar: 'string',
    createdAt: 'string',
    lastLogin: 'string',
    subscription: {
      plan: ['free', 'premium', 'professional'],
      expiresAt: 'string',
      features: 'array'
    }
  }
};

/**
 * Pagination schema
 */
export const paginationSchema = {
  page: 'number',
  limit: 'number',
  total: 'number',
  pages: 'number',
  hasNext: 'boolean',
  hasPrev: 'boolean'
};

/**
 * Error response schemas
 */
export const errorSchemas = {
  validation: {
    success: false,
    error: 'string',
    details: {
      field: 'string',
      message: 'string',
      value: 'any'
    },
    timestamp: 'string'
  },
  
  authentication: {
    success: false,
    error: 'string',
    code: ['INVALID_TOKEN', 'EXPIRED_TOKEN', 'MISSING_TOKEN'],
    timestamp: 'string'
  },
  
  authorization: {
    success: false, 
    error: 'string',
    code: ['INSUFFICIENT_PERMISSIONS', 'RESOURCE_ACCESS_DENIED'],
    requiredPermissions: 'array',
    timestamp: 'string'
  },
  
  rateLimit: {
    success: false,
    error: 'string',
    retryAfter: 'number',
    limit: 'number',
    remaining: 'number',
    reset: 'string',
    timestamp: 'string'
  },
  
  server: {
    success: false,
    error: 'string',
    correlationId: 'string',
    timestamp: 'string'
  }
};

/**
 * Schema validation utility functions
 */
export class SchemaValidator {
  /**
   * Validate object against schema definition
   */
  static validate(obj, schema, path = '') {
    const errors = [];
    
    for (const [key, expectedType] of Object.entries(schema)) {
      const fullPath = path ? `${path}.${key}` : key;
      const value = obj[key];
      
      if (value === undefined || value === null) {
        errors.push(`Missing required field: ${fullPath}`);
        continue;
      }
      
      if (typeof expectedType === 'string') {
        if (!this.validateType(value, expectedType)) {
          errors.push(`Invalid type for ${fullPath}: expected ${expectedType}, got ${typeof value}`);
        }
      } else if (Array.isArray(expectedType)) {
        if (!expectedType.includes(value)) {
          errors.push(`Invalid value for ${fullPath}: expected one of [${expectedType.join(', ')}], got ${value}`);
        }
      } else if (expectedType.type === 'array') {
        if (!Array.isArray(value)) {
          errors.push(`Invalid type for ${fullPath}: expected array, got ${typeof value}`);
        } else if (expectedType.items) {
          value.forEach((item, index) => {
            const itemErrors = this.validate(item, expectedType.items, `${fullPath}[${index}]`);
            errors.push(...itemErrors);
          });
        }
      } else if (typeof expectedType === 'object') {
        if (typeof value !== 'object' || Array.isArray(value)) {
          errors.push(`Invalid type for ${fullPath}: expected object, got ${typeof value}`);
        } else {
          const nestedErrors = this.validate(value, expectedType, fullPath);
          errors.push(...nestedErrors);
        }
      }
    }
    
    return errors;
  }
  
  /**
   * Validate primitive type
   */
  static validateType(value, expectedType) {
    switch (expectedType) {
      case 'string':
        return typeof value === 'string';
      case 'number':
        return typeof value === 'number' && !isNaN(value);
      case 'boolean':
        return typeof value === 'boolean';
      case 'object':
        return typeof value === 'object' && value !== null && !Array.isArray(value);
      case 'array':
        return Array.isArray(value);
      case 'any':
        return true;
      default:
        return false;
    }
  }
  
  /**
   * Validate standard response wrapper
   */
  static validateStandardResponse(response) {
    const errors = [];
    
    // Check required success field
    if (typeof response.success !== 'boolean') {
      errors.push('Missing or invalid success field');
    }
    
    // Check timestamp format
    if (!response.timestamp || !this.validateISO8601(response.timestamp)) {
      errors.push('Missing or invalid timestamp field');
    }
    
    // Success responses should have data
    if (response.success && !response.data) {
      errors.push('Success response missing data field');
    }
    
    // Error responses should have error message
    if (!response.success && !response.error) {
      errors.push('Error response missing error field');
    }
    
    return errors;
  }
  
  /**
   * Validate ISO 8601 timestamp
   */
  static validateISO8601(timestamp) {
    const iso8601Regex = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/;
    return iso8601Regex.test(timestamp) && !isNaN(Date.parse(timestamp));
  }
  
  /**
   * Validate semantic version
   */
  static validateSemVer(version) {
    const semverRegex = /^\d+\.\d+\.\d+(-[a-zA-Z0-9.-]+)?(\+[a-zA-Z0-9.-]+)?$/;
    return semverRegex.test(version);
  }
  
  /**
   * Validate stock symbol format
   */
  static validateStockSymbol(symbol) {
    const symbolRegex = /^[A-Z]{1,5}(\.[A-Z]{1,2})?$/;
    return symbolRegex.test(symbol);
  }
  
  /**
   * Validate email format
   */
  static validateEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  }
  
  /**
   * Validate currency code
   */
  static validateCurrency(currency) {
    const validCurrencies = ['USD', 'EUR', 'GBP', 'CAD', 'AUD', 'JPY'];
    return validCurrencies.includes(currency);
  }
  
  /**
   * Validate pagination parameters
   */
  static validatePagination(pagination) {
    const errors = [];
    
    if (!Number.isInteger(pagination.page) || pagination.page < 1) {
      errors.push('Page must be a positive integer');
    }
    
    if (!Number.isInteger(pagination.limit) || pagination.limit < 1 || pagination.limit > 1000) {
      errors.push('Limit must be between 1 and 1000');
    }
    
    if (!Number.isInteger(pagination.total) || pagination.total < 0) {
      errors.push('Total must be a non-negative integer');
    }
    
    if (!Number.isInteger(pagination.pages) || pagination.pages !== Math.ceil(pagination.total / pagination.limit)) {
      errors.push('Pages calculation incorrect');
    }
    
    if (pagination.hasNext !== (pagination.page < pagination.pages)) {
      errors.push('HasNext calculation incorrect');
    }
    
    if (pagination.hasPrev !== (pagination.page > 1)) {
      errors.push('HasPrev calculation incorrect');
    }
    
    return errors;
  }
  
  /**
   * Validate financial calculations
   */
  static validateFinancialMath(holding) {
    const errors = [];
    const tolerance = 0.01; // Penny tolerance for floating point
    
    // Total value = quantity * current price
    const expectedTotalValue = holding.quantity * holding.currentPrice;
    if (Math.abs(holding.totalValue - expectedTotalValue) > tolerance) {
      errors.push(`Total value calculation incorrect: expected ${expectedTotalValue}, got ${holding.totalValue}`);
    }
    
    // Gain/loss = total value - (quantity * avg price)
    const expectedGainLoss = holding.totalValue - (holding.quantity * holding.avgPrice);
    if (Math.abs(holding.gainLoss - expectedGainLoss) > tolerance) {
      errors.push(`Gain/loss calculation incorrect: expected ${expectedGainLoss}, got ${holding.gainLoss}`);
    }
    
    // Gain/loss percent = (gain/loss / cost basis) * 100
    const costBasis = holding.quantity * holding.avgPrice;
    const expectedGainLossPercent = (holding.gainLoss / costBasis) * 100;
    if (Math.abs(holding.gainLossPercent - expectedGainLossPercent) > tolerance) {
      errors.push(`Gain/loss percent calculation incorrect: expected ${expectedGainLossPercent}, got ${holding.gainLossPercent}`);
    }
    
    return errors;
  }
  
  /**
   * Validate price relationships
   */
  static validatePriceData(priceData) {
    const errors = [];
    
    // High should be >= low
    if (priceData.high < priceData.low) {
      errors.push(`High price (${priceData.high}) cannot be less than low price (${priceData.low})`);
    }
    
    // Current price should be between high and low
    if (priceData.price < priceData.low || priceData.price > priceData.high) {
      errors.push(`Current price (${priceData.price}) should be between low (${priceData.low}) and high (${priceData.high})`);
    }
    
    // Change should equal current - previous close
    const expectedChange = priceData.price - priceData.previousClose;
    if (Math.abs(priceData.change - expectedChange) > 0.01) {
      errors.push(`Change calculation incorrect: expected ${expectedChange}, got ${priceData.change}`);
    }
    
    // Change percent should equal (change / previous close) * 100
    const expectedChangePercent = (priceData.change / priceData.previousClose) * 100;
    if (Math.abs(priceData.changePercent - expectedChangePercent) > 0.01) {
      errors.push(`Change percent calculation incorrect: expected ${expectedChangePercent}, got ${priceData.changePercent}`);
    }
    
    return errors;
  }
}

/**
 * Jest matchers for schema validation
 */
export const schemaMatchers = {
  toMatchSchema(received, schema) {
    const errors = SchemaValidator.validate(received, schema);
    
    const pass = errors.length === 0;
    const message = pass
      ? () => `Expected object not to match schema`
      : () => `Schema validation failed:\n${errors.join('\n')}`;
    
    return { message, pass };
  },
  
  toBeValidStandardResponse(received) {
    const errors = SchemaValidator.validateStandardResponse(received);
    
    const pass = errors.length === 0;
    const message = pass
      ? () => `Expected response not to be valid standard format`
      : () => `Standard response validation failed:\n${errors.join('\n')}`;
    
    return { message, pass };
  },
  
  toHaveValidFinancialMath(received) {
    const errors = SchemaValidator.validateFinancialMath(received);
    
    const pass = errors.length === 0;
    const message = pass
      ? () => `Expected holding not to have valid financial calculations`
      : () => `Financial calculation validation failed:\n${errors.join('\n')}`;
    
    return { message, pass };
  }
};

