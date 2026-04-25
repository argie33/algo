/**
 * Centralized pagination and limit configuration
 * Single source of truth for all API limits and pagination settings
 */

const config = {
  // Default pagination limit when not specified
  DEFAULT_LIMIT: 50,

  // Maximum allowed limits by endpoint type
  MAX_LIMIT_SMALL: 100,      // Used by: earnings, options, commodity
  MAX_LIMIT_MEDIUM: 500,     // Used by: economic, price history
  MAX_LIMIT_LARGE: 1000,     // Used by: stocks, signals
  MAX_LIMIT_XLARGE: 5000,    // Used by: deep value stocks

  // Specific endpoint limits
  LIMITS: {
    stocks: {
      default: 50,
      max: 1000
    },
    earnings: {
      default: 50,
      max: 100
    },
    financials: {
      default: 20,
      max: 100
    },
    technicals: {
      default: 50,
      max: 500
    },
    price: {
      default: 50,
      max: 500
    },
    signals: {
      default: 50,
      max: 1000
    },
    options: {
      default: 50,
      max: 200
    },
    commodities: {
      default: 50,
      max: 500
    },
    economic: {
      default: 50,
      max: 500
    },
    portfolio: {
      default: 50,
      max: 500
    },
    trades: {
      default: 50,
      max: 500
    },
    deepValue: {
      default: 100,
      max: 5000
    },
    sectors: {
      default: 20,
      max: 100
    },
    industries: {
      default: 20,
      max: 100
    }
  },

  // Helper function to get safe limit
  getLimit: function(resource, requestedLimit) {
    const resourceConfig = config.LIMITS[resource] || { default: config.DEFAULT_LIMIT, max: config.MAX_LIMIT_LARGE };
    const limit = parseInt(requestedLimit) || resourceConfig.default;
    return Math.min(limit, resourceConfig.max);
  },

  // Helper function to get safe offset
  getOffset: function(page, limit) {
    const pageNum = Math.max(1, parseInt(page) || 1);
    return (pageNum - 1) * limit;
  },

  // Helper function to calculate pagination metadata
  getPaginationMetadata: function(limit, offset, total) {
    const page = Math.floor(offset / limit) + 1;
    const totalPages = Math.ceil(total / limit);
    return {
      limit,
      offset,
      total,
      page,
      totalPages,
      hasNext: page < totalPages,
      hasPrev: page > 1
    };
  }
};

module.exports = config;
module.exports.getLimit = config.getLimit.bind(config);
module.exports.getOffset = config.getOffset.bind(config);
module.exports.getPaginationMetadata = config.getPaginationMetadata.bind(config);
