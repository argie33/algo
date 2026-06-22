/**
 * Endpoint validation schemas
 * Defines required fields and validation rules for each API endpoint
 * Used by hooks to validate responses before returning to components
 */

/**
 * Schema definition for single-object endpoints
 * @typedef {object} SingleObjectSchema
 * @property {string} type - 'object'
 * @property {string[]} requiredFields - Fields that must exist and be non-null
 * @property {boolean} [requireNonEmpty=false] - If true, object must have at least one property
 *   Use this to distinguish between "no data available" (empty {}) and "data exists"
 *   Example: /api/algo/status should have requireNonEmpty: true
 *   Example: /api/algo/metrics can be empty and have requireNonEmpty: false
 */

/**
 * Schema definition for paginated endpoints
 * @typedef {object} PaginatedSchema
 * @property {string} type - 'paginated'
 * @property {string[]} itemFields - Fields each item in the items array must have
 * @property {string[]} [paginationFields] - Fields pagination object must have
 * @property {boolean} [requireNonEmptyList=false] - If true, items array must have at least one item
 *   Use this to distinguish between "no matching results" (items: []) and "results found"
 *   Example: /api/algo/positions can be empty if no positions (requireNonEmptyList: false)
 *   Example: /api/algo/trades can be empty if no trade history (requireNonEmptyList: false)
 */

/**
 * Schema definition for array endpoints
 * @typedef {object} ArraySchema
 * @property {string} type - 'array'
 * @property {string[]} itemFields - Fields each item must have
 * @property {boolean} [requireNonEmptyList=false] - If true, array must have at least one item
 */

/**
 * Map of endpoint patterns to their validation schemas
 * Pattern format: '/api/path' or '/api/path/*' for wildcards
 */
export const ENDPOINT_SCHEMAS = {
  // Algo orchestrator - status and execution
  "/api/algo/status": {
    type: "object",
    requiredFields: ["status", "last_run"],
    requireNonEmpty: true,
  },
  "/api/algo/execution/stats": {
    type: "object",
    requiredFields: [],
    requireNonEmpty: false,
  },
  "/api/algo/execution/recent": {
    type: "paginated",
    itemFields: ["id", "status"],
    paginationFields: ["page", "limit", "total"],
  },
  "/api/algo/circuit-breakers": {
    type: "object",
    requiredFields: [],
    requireNonEmpty: false,
    decimalFields: ["breakers.*.current", "breakers.*.threshold"],
  },

  // Trading positions and trades
  "/api/algo/positions": {
    type: "paginated",
    itemFields: ["id", "ticker"],
    paginationFields: ["page", "limit", "total"],
    requireNonEmptyList: false, // Can be empty if no open positions
    decimalFields: [
      "avg_entry_price",
      "current_price",
      "stop_loss_price",
      "target_1_price",
      "target_2_price",
      "target_3_price",
      "position_value",
      "open_risk_dollars",
      "unrealized_pnl_dollars",
      "unrealized_pnl_pct",
      "risk_pct",
      "quantity",
      "r_multiple",
      "distance_to_stop_pct",
      "distance_to_t1_pct",
      "distance_to_t2_pct",
      "distance_to_t3_pct",
      "pct_from_52w_low",
    ],
  },
  "/api/algo/trades": {
    type: "paginated",
    itemFields: ["id", "ticker", "side"],
    paginationFields: ["page", "limit", "total"],
    requireNonEmptyList: false, // Can be empty if no trade history
    decimalFields: [
      "entry_price",
      "exit_price",
      "quantity",
      "position_value",
      "profit_loss_pct",
      "profit_loss_dollars",
      "exit_r_multiple",
      "trade_duration_days",
    ],
  },
  "/api/algo/performance": {
    type: "object",
    requiredFields: ["total_return", "win_rate"],
    requireNonEmpty: true,
    decimalFields: [
      "total_return_pct",
      "sharpe_annualized",
      "sortino_annualized",
      "calmar_ratio",
      "profit_factor",
      "win_rate_pct",
      "win_rate_pct_adjusted",
      "avg_win_pct",
      "avg_loss_pct",
      "expectancy_r",
      "avg_win_r",
      "avg_loss_r",
      "avg_hold_days",
      "max_drawdown_pct",
      "total_pnl_dollars",
      "gross_win_dollars",
      "gross_loss_dollars",
      "total_open_losses_dollars",
      "total_pnl_pct",
      "avg_trade_pct",
      "best_trade_pct",
      "worst_trade_pct",
      "sharpe_ratio",
      "sortino_ratio",
      "win_rate",
    ],
  },
  "/api/algo/portfolio": {
    type: "object",
    requiredFields: [],
    requireNonEmpty: false,
    decimalFields: [
      "total_portfolio_value",
      "total_cash",
      "daily_return_pct",
      "unrealized_pnl.total_dollars",
      "unrealized_pnl.total_pct",
      "cumulative_return_pct",
      "max_drawdown_pct",
      "largest_position_pct",
    ],
  },

  // Swing scores and signals
  "/api/algo/swing-scores": {
    type: "paginated",
    itemFields: ["ticker", "score"],
    paginationFields: ["page", "limit", "total"],
    requireNonEmptyList: false, // Can have zero scores
  },
  "/api/algo/swing-scores-history": {
    type: "paginated",
    itemFields: ["date", "score"],
    paginationFields: ["page", "limit", "total"],
    requireNonEmptyList: false, // Can have no history
  },

  // Audit and notifications
  "/api/algo/audit-log": {
    type: "paginated",
    itemFields: ["id", "action_type", "timestamp"],
    paginationFields: ["page", "limit", "total"],
  },
  "/api/algo/notifications": {
    type: "paginated",
    itemFields: ["id", "type"],
    paginationFields: ["page", "limit", "total"],
  },

  // Portfolio metrics
  "/api/algo/markets": {
    type: "object",
    requiredFields: [],
    requireNonEmpty: false,
    decimalFields: [
      "current.exposure_pct",
      "current.raw_score",
      "market_health.vix_level",
    ],
  },
  "/api/algo/market-factors": {
    type: "object",
    requiredFields: [],
    requireNonEmpty: false,
    decimalFields: ["exposure_pct", "raw_score"],
  },
  "/api/algo/evaluate": {
    type: "object",
    requiredFields: [],
    requireNonEmpty: false,
    decimalFields: [
      "portfolio_health.today_return_pct",
      "portfolio_health.unrealized_pnl.total_dollars",
      "portfolio_health.unrealized_pnl.total_pct",
    ],
  },
  "/api/algo/equity-curve": {
    type: "paginated",
    itemFields: ["date", "value"],
    paginationFields: ["page", "limit", "total"],
    decimalFields: [
      "total_portfolio_value",
      "cash_balance",
      "position_value",
      "unrealized_pnl_dollars",
      "drawdown_pct",
    ],
  },
  "/api/algo/daily-return-histogram": {
    type: "object",
    requiredFields: [],
    requireNonEmpty: false,
  },
  "/api/algo/trade-distribution": {
    type: "object",
    requiredFields: [],
    requireNonEmpty: false,
  },
  "/api/algo/holding-period-distribution": {
    type: "object",
    requiredFields: [],
    requireNonEmpty: false,
  },
  "/api/algo/stage-distribution": {
    type: "object",
    requiredFields: [],
    requireNonEmpty: false,
  },

  // Backtests
  "/api/research/backtests": {
    type: "paginated",
    itemFields: ["id", "status"],
    paginationFields: ["page", "limit", "total"],
  },
  "/api/research/backtests/*": {
    type: "object",
    requiredFields: ["id", "status"],
    requireNonEmpty: true,
  },

  // Economic indicators
  "/api/economic/leading-indicators": {
    type: "object",
    requiredFields: [],
    requireNonEmpty: false,
  },
  "/api/economic/yield-curve-full": {
    type: "object",
    requiredFields: [],
    requireNonEmpty: false,
  },
  "/api/economic/calendar": {
    type: "paginated",
    itemFields: ["date", "name"],
    paginationFields: ["page", "limit", "total"],
  },

  // Market data
  "/api/market/naaim": {
    type: "object",
    requiredFields: [],
    requireNonEmpty: false,
  },
  "/api/stocks/deep-value": {
    type: "paginated",
    itemFields: ["symbol", "price"],
    paginationFields: ["page", "limit", "total"],
  },
  "/api/stocks/*": {
    type: "object",
    requiredFields: ["symbol"],
    requireNonEmpty: true,
  },

  // Prices and historical data
  "/api/prices/history/*": {
    type: "paginated",
    itemFields: ["date", "close"],
    paginationFields: ["page", "limit", "total"],
  },
  "/api/prices/batch-history": {
    type: "object",
    requiredFields: [],
    requireNonEmpty: false,
  },

  // Signals
  "/api/signals/stocks": {
    type: "paginated",
    itemFields: ["id", "symbol"],
    paginationFields: ["page", "limit", "total"],
  },

  // Scores
  "/api/scores/stockscores": {
    type: "paginated",
    itemFields: ["symbol", "composite_score"],
    paginationFields: ["page", "limit", "total"],
  },

  // Financial statements
  "/api/financials/*/key-metrics": {
    type: "object",
    requiredFields: ["symbol"],
    requireNonEmpty: true,
  },
  "/api/financials/*/income-statement": {
    type: "paginated",
    itemFields: [],
    paginationFields: ["page", "limit", "total"],
  },
  "/api/financials/*/balance-sheet": {
    type: "paginated",
    itemFields: [],
    paginationFields: ["page", "limit", "total"],
  },
  "/api/financials/*/cash-flow": {
    type: "paginated",
    itemFields: [],
    paginationFields: ["page", "limit", "total"],
  },

  // Sentiment
  "/api/sentiment/data": {
    type: "paginated",
    itemFields: ["symbol", "sentiment"],
    paginationFields: ["page", "limit", "total"],
  },
  "/api/sentiment/summary": {
    type: "object",
    requiredFields: [],
    requireNonEmpty: false,
  },
  "/api/sentiment/divergence": {
    type: "object",
    requiredFields: [],
    requireNonEmpty: false,
  },
  "/api/sentiment/analyst/insights/*": {
    type: "object",
    requiredFields: [],
    requireNonEmpty: false,
  },
};

/**
 * Find schema for an endpoint path
 * Handles both API paths (e.g., '/api/sectors') and cache key formats (e.g., 'sectors')
 * @param {string} endpoint - API endpoint path or cache key (e.g., '/api/sectors', 'sectors', or '/api/sectors?page=1')
 * @returns {object|null} Schema object or null if not found
 */
export function getEndpointSchema(endpoint) {
  if (!endpoint) return null;

  // Remove query parameters
  const basePath = endpoint.split("?")[0];

  // Exact match
  if (ENDPOINT_SCHEMAS[basePath]) {
    return ENDPOINT_SCHEMAS[basePath];
  }

  // If not an API path, try to match as cache key by converting to API path
  if (!basePath.startsWith("/")) {
    // Cache key format: try matching against endpoint paths
    // e.g., 'algo-positions' should match '/api/algo/positions'
    // e.g., 'swing-scores' should match '/api/algo/swing-scores'
    const cacheKeyNormalized = basePath.toLowerCase();

    for (const [pattern, schema] of Object.entries(ENDPOINT_SCHEMAS)) {
      // Remove /api/ prefix and * wildcards for comparison
      let patternPath = pattern.replace(/^\/api\//, "").replace(/\*$/, "");

      // Normalize: replace '/' with '-' to match hyphenated cache keys
      const patternNormalized = patternPath.replace(/\//g, "-").toLowerCase();

      if (patternNormalized === cacheKeyNormalized) {
        return schema;
      }

      // Also try single-segment matching for simple keys like 'positions' -> '/api/algo/positions'
      if (patternPath.includes("/")) {
        const lastSegment = patternPath.split("/").pop();
        if (lastSegment && lastSegment.toLowerCase() === cacheKeyNormalized) {
          return schema;
        }
      }
    }
  }

  // Wildcard match (simple pattern matching)
  for (const [pattern, schema] of Object.entries(ENDPOINT_SCHEMAS)) {
    if (pattern.includes("*")) {
      const regex = new RegExp(`^${pattern.replace("*", ".*")}$`);
      if (regex.test(basePath)) {
        return schema;
      }
    }
  }

  return null;
}

/**
 * Determine if an endpoint response should require non-empty data
 * By default, endpoints are assumed to allow empty responses unless explicitly required
 * @param {string} endpoint - API endpoint
 * @returns {boolean} Whether response must be non-empty
 */
export function isNonEmptyRequired(endpoint) {
  const schema = getEndpointSchema(endpoint);
  if (!schema) return false;

  if (schema.type === "object") {
    return schema.requireNonEmpty || false;
  }

  if (schema.type === "paginated") {
    // Paginated endpoints can have empty items by default
    return schema.requireNonEmptyList || false;
  }

  if (schema.type === "array") {
    return schema.requireNonEmptyList || false;
  }

  return false;
}

/**
 * Get required fields for an endpoint
 * @param {string} endpoint - API endpoint
 * @returns {string[]} Array of required field names
 */
export function getRequiredFields(endpoint) {
  const schema = getEndpointSchema(endpoint);
  if (!schema) return [];

  if (schema.type === "object") {
    return schema.requiredFields || [];
  }

  if (schema.type === "paginated") {
    return schema.itemFields || [];
  }

  if (schema.type === "array") {
    return schema.itemFields || [];
  }

  return [];
}

/**
 * Get item field requirements for paginated/array endpoints
 * @param {string} endpoint - API endpoint
 * @returns {string[]} Required fields for items in arrays
 */
export function getItemRequiredFields(endpoint) {
  const schema = getEndpointSchema(endpoint);
  if (schema?.type === "paginated") {
    return schema.itemFields || [];
  }
  if (schema?.type === "array") {
    return schema.itemFields || [];
  }
  return [];
}

/**
 * Get pagination schema for paginated endpoints
 * @param {string} endpoint - API endpoint
 * @returns {string[]} Required pagination fields
 */
export function getPaginationFields(endpoint) {
  const schema = getEndpointSchema(endpoint);
  if (schema?.type === "paginated") {
    return schema.paginationFields || [];
  }
  return [];
}

/**
 * Get decimal fields for an endpoint
 * These fields contain financial values that need precision handling
 * @param {string} endpoint - API endpoint
 * @returns {string[]} Field names that are financial (Decimal) values
 */
export function getDecimalFields(endpoint) {
  const schema = getEndpointSchema(endpoint);
  if (!schema) return [];
  return schema.decimalFields || [];
}

export default {
  ENDPOINT_SCHEMAS,
  getEndpointSchema,
  isNonEmptyRequired,
  getRequiredFields,
  getItemRequiredFields,
  getPaginationFields,
  getDecimalFields,
};
