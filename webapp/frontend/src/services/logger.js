/**
 * Centralized logging service for the entire app
 * Single place to control log levels, format, and behavior
 */

let logLevel = 'info'; // 'debug' | 'info' | 'warn' | 'error'

const LogLevels = {
  DEBUG: 0,
  INFO: 1,
  WARN: 2,
  ERROR: 3,
};

const levelToString = {
  0: 'DEBUG',
  1: 'INFO',
  2: 'WARN',
  3: 'ERROR',
};

/**
 * Create a logger for a component or service
 * @param {string} name - Component/service name for logging context
 * @returns {object} logger object with debug/info/warn/error methods
 */
export const getLogger = (name) => {
  const currentLevelValue = LogLevels[logLevel.toUpperCase()] || LogLevels.INFO;

  const shouldLog = (level) => LogLevels[level] >= currentLevelValue;

  const safeStringify = (obj) => {
    try {
      return JSON.stringify(obj);
    } catch {
      return String(obj);
    }
  };

  const formatMessage = (level, message, data) => {
    const timestamp = new Date().toISOString();
    const prefix = `[${timestamp}] [${name}] [${levelToString[level]}]`;
    return data ? `${prefix} ${message} ${safeStringify(data)}` : `${prefix} ${message}`;
  };

  return {
    debug: (message, data) => {
      if (shouldLog('DEBUG')) {
        console.log(formatMessage(LogLevels.DEBUG, message, data));
      }
    },

    info: (message, data) => {
      if (shouldLog('INFO')) {
        console.log(formatMessage(LogLevels.INFO, message, data));
      }
    },

    warn: (message, data) => {
      if (shouldLog('WARN')) {
        console.warn(formatMessage(LogLevels.WARN, message, data));
      }
    },

    error: (message, error, context) => {
      if (shouldLog('ERROR')) {
        const errorData = {
          message: error?.message || String(error),
          code: error?.code,
          stack: error?.stack?.substring(0, 200),
          context,
        };
        console.error(formatMessage(LogLevels.ERROR, message, errorData));
      }
    },
  };
};

/**
 * Set global log level
 * @param {string} level - 'debug' | 'info' | 'warn' | 'error'
 */
export const setLogLevel = (level) => {
  if (LogLevels[level.toUpperCase()]) {
    logLevel = level.toLowerCase();
  }
};

/**
 * Get current log level
 * @returns {string}
 */
export const getLogLevel = () => logLevel;

/**
 * Capture error with standardized format
 * @param {Error} error - The error to capture
 * @param {object} context - Additional context about the error
 * @returns {object} formatted error object
 */
export const captureError = (error, context = {}) => {
  return {
    timestamp: new Date().toISOString(),
    message: error?.message || String(error),
    code: error?.code,
    stack: error?.stack,
    context,
  };
};

export default {
  getLogger,
  setLogLevel,
  getLogLevel,
  captureError,
};
