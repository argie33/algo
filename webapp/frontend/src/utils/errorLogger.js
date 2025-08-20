/**
 * Centralized error logging utility for consistent error handling across all pages
 */

/**
 * Log API/network error with detailed context
 * @param {string} component - The component/page name (e.g., 'StockExplorer', 'AnalystInsights')
 * @param {string} operation - The operation that failed (e.g., 'fetchStockData', 'loadAnalystRatings')
 * @param {Error|any} error - The error object or message
 * @param {object} context - Additional context (URL, params, etc.)
 */
export const logApiError = (component, operation, error, context = {}) => {
  const timestamp = new Date().toISOString();
  const errorMessage = error?.message || error?.toString() || "Unknown error";
  const errorStack = error?.stack || "No stack trace available";

  // Log structured error information
  console.group(`❌ ${component} - ${operation} failed`);
  console.error(`🕒 Timestamp: ${timestamp}`);
  console.error(`📍 Component: ${component}`);
  console.error(`🔄 Operation: ${operation}`);
  console.error(`💥 Error: ${errorMessage}`);

  // Log additional context if provided
  if (context.url) console.error(`🌐 URL: ${context.url}`);
  if (context.params) console.error(`📋 Params:`, context.params);
  if (context.response) console.error(`📡 Response:`, context.response);
  if (context.status) console.error(`🚦 Status: ${context.status}`);

  // Log full error details
  console.error(`📄 Full Error:`, error);
  console.error(`📚 Stack Trace:`, errorStack);

  console.groupEnd();

  // Also log a simple version for easier searching
  console.error(`❌ ${component} - ${operation} failed:`, {
    error: errorMessage,
    context,
    timestamp,
  });
};

/**
 * Log query error from React Query with additional context
 * @param {string} component - The component/page name
 * @param {string} queryKey - The query key or operation name
 * @param {Error} error - The query error
 * @param {object} context - Additional context
 */
export const logQueryError = (component, queryKey, error, context = {}) => {
  logApiError(component, `Query[${queryKey}]`, error, {
    queryKey,
    ...context,
  });
};

/**
 * Log successful API operation (for debugging/monitoring)
 * @param {string} component - The component/page name
 * @param {string} operation - The operation that succeeded
 * @param {object} result - The result data (optional)
 * @param {object} context - Additional context
 */
export const logApiSuccess = (
  component,
  operation,
  result = null,
  context = {}
) => {
  const timestamp = new Date().toISOString();

  console.log(`✅ ${component} - ${operation} succeeded`, {
    timestamp,
    component,
    operation,
    resultSize: result
      ? Array.isArray(result)
        ? result.length
        : Object.keys(result).length
      : "N/A",
    context,
  });
};

/**
 * Create an error logger bound to a specific component
 * @param {string} component - The component name
 * @returns {object} Object with logging methods bound to the component
 */
export const createComponentLogger = (component) => ({
  error: (operation, error, context) =>
    logApiError(component, operation, error, context),
  queryError: (queryKey, error, context) =>
    logQueryError(component, queryKey, error, context),
  success: (operation, result, context) =>
    logApiSuccess(component, operation, result, context),
});

export default {
  logApiError,
  logQueryError,
  logApiSuccess,
  createComponentLogger,
};
