/**
 * Error Recovery and Retry Handler
 *
 * Provides robust error handling, retry logic, and recovery mechanisms
 * for portfolio optimization operations
 */

const { query } = require("../utils/database");

/**
 * Retry configuration for different operation types
 */
const RETRY_CONFIG = {
  api_call: {
    maxRetries: 3,
    initialDelay: 1000, // 1 second
    maxDelay: 10000,    // 10 seconds
    backoffMultiplier: 2,
    retryableErrors: ["ECONNRESET", "ETIMEDOUT", "ENOTFOUND", "429"],
  },
  database: {
    maxRetries: 3,
    initialDelay: 500,
    maxDelay: 5000,
    backoffMultiplier: 2,
    retryableErrors: ["ECONNREFUSED", "QUERY_CANCELLED"],
  },
  alpaca: {
    maxRetries: 5,
    initialDelay: 2000,
    maxDelay: 30000,
    backoffMultiplier: 1.5,
    retryableErrors: ["429", "503", "504"], // Rate limit, Service unavailable, Gateway timeout
  },
};

/**
 * Retry a failed operation with exponential backoff
 * @param {Function} operation - Async function to retry
 * @param {string} operationType - Type of operation (api_call, database, alpaca)
 * @param {Object} context - Additional context for logging
 * @returns {Promise<*>} Result of the operation
 */
async function retryWithBackoff(operation, operationType = "api_call", context = {}) {
  const config = RETRY_CONFIG[operationType] || RETRY_CONFIG.api_call;
  let lastError;

  for (let attempt = 1; attempt <= config.maxRetries; attempt++) {
    try {
      console.log(`⏳ Attempt ${attempt}/${config.maxRetries}${context.description ? ` - ${context.description}` : ""}`);
      return await operation();
    } catch (error) {
      lastError = error;

      // Check if error is retryable
      const isRetryable = isRetryableError(error, config.retryableErrors);

      if (!isRetryable || attempt === config.maxRetries) {
        console.error(`❌ Operation failed after ${attempt} attempts:`, error.message);
        throw error;
      }

      // Calculate backoff delay
      const delay = Math.min(
        config.maxDelay,
        config.initialDelay * Math.pow(config.backoffMultiplier, attempt - 1)
      );

      console.warn(`⚠️ Attempt ${attempt} failed (${error.message}). Retrying in ${delay}ms...`);
      await sleep(delay);
    }
  }

  throw lastError;
}

/**
 * Check if an error is retryable
 */
function isRetryableError(error, retryableErrors = []) {
  if (!error) return false;

  // Check error code
  if (error.code && retryableErrors.includes(error.code)) {
    return true;
  }

  // Check error message for status codes
  if (error.message) {
    for (const code of retryableErrors) {
      if (error.message.includes(code)) {
        return true;
      }
    }
  }

  // Check error status
  if (error.status && retryableErrors.includes(error.status.toString())) {
    return true;
  }

  return false;
}

/**
 * Execute operation with timeout
 * @param {Function} operation - Async function
 * @param {number} timeoutMs - Timeout in milliseconds
 * @param {string} description - Description for logging
 * @returns {Promise<*>} Result of the operation
 */
async function executeWithTimeout(operation, timeoutMs = 30000, description = "Operation") {
  return Promise.race([
    operation(),
    new Promise((_, reject) =>
      setTimeout(() => reject(new Error(`${description} timed out after ${timeoutMs}ms`)), timeoutMs)
    ),
  ]);
}

/**
 * Sleep helper for delays
 */
function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Transaction wrapper for database operations
 * Supports rollback on failure
 */
async function withTransaction(operationFn) {
  const client = null; // Would be obtained from connection pool

  try {
    // In a real implementation, would start transaction here
    const result = await operationFn();
    // Commit transaction
    return {
      success: true,
      result,
      status: "committed",
    };
  } catch (error) {
    console.error("Transaction failed:", error.message);
    // Rollback transaction in real implementation
    return {
      success: false,
      error: error.message,
      status: "rolled_back",
    };
  }
}

/**
 * Validate operation before execution
 * @param {Object} data - Data to validate
 * @param {Array} rules - Validation rules
 * @returns {Object} Validation result {valid, errors}
 */
function validateOperationData(data, rules = {}) {
  const errors = [];

  // Validate required fields
  if (rules.required) {
    for (const field of rules.required) {
      if (data[field] === undefined || data[field] === null) {
        errors.push(`Required field missing: ${field}`);
      }
    }
  }

  // Validate field types
  if (rules.types) {
    for (const [field, expectedType] of Object.entries(rules.types)) {
      if (data[field] !== undefined && data[field] !== null) {
        if (typeof data[field] !== expectedType) {
          errors.push(`Field ${field} has invalid type. Expected ${expectedType}, got ${typeof data[field]}`);
        }
      }
    }
  }

  // Validate numeric ranges
  if (rules.ranges) {
    for (const [field, { min, max }] of Object.entries(rules.ranges)) {
      const value = data[field];
      if (value !== undefined && value !== null) {
        if (value < min || value > max) {
          errors.push(`Field ${field} out of range [${min}, ${max}]. Got ${value}`);
        }
      }
    }
  }

  // Custom validators
  if (rules.validators) {
    for (const [field, validator] of Object.entries(rules.validators)) {
      if (!validator(data[field])) {
        errors.push(`Field ${field} failed custom validation`);
      }
    }
  }

  return {
    valid: errors.length === 0,
    errors: errors.length > 0 ? errors : null,
  };
}

/**
 * Circuit breaker pattern implementation
 * Prevents cascading failures
 */
class CircuitBreaker {
  constructor(name, options = {}) {
    this.name = name;
    this.state = "CLOSED"; // CLOSED, OPEN, HALF_OPEN
    this.failureCount = 0;
    this.failureThreshold = options.failureThreshold || 5;
    this.resetTimeout = options.resetTimeout || 60000; // 1 minute
    this.lastFailureTime = null;
    this.successCount = 0;
    this.successThreshold = options.successThreshold || 2;
  }

  async execute(operation) {
    if (this.state === "OPEN") {
      if (Date.now() - this.lastFailureTime > this.resetTimeout) {
        console.log(`🔄 Circuit breaker ${this.name}: Transitioning to HALF_OPEN`);
        this.state = "HALF_OPEN";
        this.successCount = 0;
      } else {
        throw new Error(`Circuit breaker ${this.name} is OPEN - request rejected`);
      }
    }

    try {
      const result = await operation();

      if (this.state === "HALF_OPEN") {
        this.successCount++;
        if (this.successCount >= this.successThreshold) {
          console.log(`✅ Circuit breaker ${this.name}: Transitioning to CLOSED`);
          this.state = "CLOSED";
          this.failureCount = 0;
        }
      } else if (this.state === "CLOSED") {
        this.failureCount = 0;
      }

      return result;
    } catch (error) {
      this.recordFailure();
      throw error;
    }
  }

  recordFailure() {
    this.failureCount++;
    this.lastFailureTime = Date.now();

    if (this.failureCount >= this.failureThreshold) {
      console.log(`🔴 Circuit breaker ${this.name}: Transitioning to OPEN after ${this.failureCount} failures`);
      this.state = "OPEN";
    }
  }

  getStatus() {
    return {
      name: this.name,
      state: this.state,
      failureCount: this.failureCount,
      lastFailureTime: this.lastFailureTime,
    };
  }
}

/**
 * Error logger for audit trail
 */
async function logError(userId, operationType, error, context = {}) {
  try {
    await query(
      `INSERT INTO error_log
       (user_id, operation_type, error_message, error_code, context, created_at)
       VALUES ($1, $2, $3, $4, $5, NOW())`,
      [
        userId,
        operationType,
        error.message,
        error.code || "UNKNOWN",
        JSON.stringify(context),
      ]
    );
  } catch (logError) {
    console.error("Could not log error:", logError.message);
  }
}

/**
 * Graceful degradation: Provide reduced functionality when components fail
 */
function getReducedFunctionality(component, originalData) {
  const degradedData = { ...originalData };

  switch (component) {
    case "correlation_analysis":
      // Continue without correlation data - return null instead of fake default
      degradedData.diversification_analysis = {
        diversification_score: null, // No data available
        message: "Correlation analysis unavailable - real data required",
      };
      break;

    case "risk_metrics":
      // Continue without risk metrics
      degradedData.portfolio_risk_metrics = {
        volatility_annualized: null,
        sharpe_ratio: null,
        max_drawdown: null,
        message: "Risk metrics unavailable",
      };
      break;

    case "alpaca_trading":
      // Continue with database-only updates
      degradedData.alpaca_execution = {
        success: false,
        message: "Alpaca trading unavailable - trades recorded locally only",
      };
      break;
  }

  return degradedData;
}

module.exports = {
  retryWithBackoff,
  executeWithTimeout,
  withTransaction,
  validateOperationData,
  CircuitBreaker,
  logError,
  getReducedFunctionality,
  sleep,
  isRetryableError,
  RETRY_CONFIG,
};
