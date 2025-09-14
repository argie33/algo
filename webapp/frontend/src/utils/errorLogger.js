/**
 * Centralized error logging utility for consistent error handling across all pages
 * Enhanced with circular reference protection and comprehensive error details
 */

/**
 * Safely stringify an object, handling circular references
 * @param {any} obj - Object to stringify
 * @param {number} maxDepth - Maximum depth to traverse
 * @returns {string} Safe JSON string
 */
const safeStringify = (obj, _maxDepth = 3) => {
  const seen = new WeakSet();
  
  return JSON.stringify(obj, (key, value) => {
    if (value === null || value === undefined) return value;
    
    if (typeof value === 'function') {
      return `[Function: ${value.name || 'anonymous'}]`;
    }
    
    if (typeof value === 'object') {
      if (seen.has(value)) {
        return '[Circular Reference]';
      }
      seen.add(value);
      
      // Handle special objects safely
      if (value instanceof Error) {
        return {
          name: value.name,
          message: value.message,
          stack: value.stack,
          code: value.code
        };
      }
      
      if (value instanceof Date) {
        return value.toISOString();
      }
      
      if (value instanceof Element) {
        return `[Element: ${value.tagName}]`;
      }
    }
    
    return value;
  }, 2);
};

/**
 * Log API/network error with detailed context
 * @param {string} component - The component/page name (e.g., 'StockExplorer', 'Dashboard')
 * @param {string} operation - The operation that failed (e.g., 'fetchStockData', 'loadAnalystRatings')
 * @param {Error|any} error - The error object or message
 * @param {object} context - Additional context (URL, params, etc.)
 */
export const logApiError = (component, operation, error, context = {}) => {
  const timestamp = new Date().toISOString();
  const errorMessage = error?.message || error?.toString() || "Unknown error";
  const errorStack = error?.stack || "No stack trace available";

  // Log structured error information (using console.log to avoid recursion)
  if (import.meta.env && import.meta.env.DEV) {
    console.group(`❌ ${component} - ${operation} failed`);
    console.log(`🕒 Timestamp: ${timestamp}`);
    console.log(`📍 Component: ${component}`);
    console.log(`🔄 Operation: ${operation}`);
    console.log(`💥 Error: ${errorMessage}`);

    // Log additional context if provided (with safe stringification)
    if (context.url) console.log(`🌐 URL: ${context.url}`);
    if (context.params) console.log(`📋 Params:`, safeStringify(context.params));
    if (context.response) console.log(`📡 Response:`, safeStringify(context.response));
    if (context.status) console.log(`🚦 Status: ${context.status}`);

    // Log full error details safely (avoid circular references)
    try {
      console.log(`📄 Full Error Details:`, safeStringify(error));
    } catch (stringifyError) {
      console.log(`📄 Full Error (safe fallback):`, {
        name: error?.name,
        message: error?.message,
        code: error?.code,
        isAxiosError: error?.isAxiosError
      });
    }
    
    console.log(`📚 Stack Trace:`, errorStack);
  }
  
  // Additional axios error details if available (with safe stringification)
  if (error?.isAxiosError) {
    const axiosDetails = {
      url: error.config?.url,
      method: error.config?.method,
      baseURL: error.config?.baseURL,
      timeout: error.config?.timeout,
      status: error.response?.status,
      statusText: error.response?.statusText,
      responseData: error.response?.data
    };
    if (import.meta.env && import.meta.env.DEV) {
      console.log(`🌐 Axios Error Details:`, safeStringify(axiosDetails));
    }
  }

  if (import.meta.env && import.meta.env.DEV) {
    console.groupEnd();

    // Also log a simple version for easier searching (with safe stringification)
    const simplifiedLog = {
      error: errorMessage,
      context: safeStringify(context),
      timestamp,
    };
    console.log(`❌ ${component} - ${operation} failed:`, safeStringify(simplifiedLog));
  }
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

  const successLog = {
    timestamp,
    component,
    operation,
    resultSize: result
      ? Array.isArray(result)
        ? (result?.length || 0)
        : Object.keys(result).length
      : "N/A",
    context,
  };
  if (import.meta.env && import.meta.env.DEV) {
    console.log(`✅ ${component} - ${operation} succeeded`, safeStringify(successLog));
  }
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
  info: (message, context) => 
    import.meta.env && import.meta.env.DEV && console.log(`ℹ️ [${component}] ${message}`, context),
});

export default {
  logApiError,
  logQueryError,
  logApiSuccess,
  createComponentLogger,
};
