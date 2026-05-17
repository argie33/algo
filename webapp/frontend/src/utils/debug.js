/**
 * Debug logging utility for production code
 * Only logs when VITE_DEBUG environment variable is set
 */

const DEBUG_ENABLED = import.meta.env.VITE_DEBUG === 'true';

export const debug = {
  log: (...args) => {
    if (DEBUG_ENABLED) console.log(...args);
  },
  error: (...args) => {
    if (DEBUG_ENABLED) console.error(...args);
  },
  warn: (...args) => {
    if (DEBUG_ENABLED) console.warn(...args);
  },
  info: (...args) => {
    if (DEBUG_ENABLED) console.info(...args);
  },

  // For errors that should ALWAYS be logged (security/critical issues)
  error_critical: (...args) => {
    console.error(...args);
  },
};

export default debug;
