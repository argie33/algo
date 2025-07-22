/**
 * Error Handling System - Utilities Export
 * Non-React utilities for error handling
 */

import ErrorManager from './ErrorManager';
import apiErrorHandler, { 
  enhancedFetch, 
  get, 
  post, 
  put, 
  del 
} from './apiErrorHandler';

// Initialize error manager
ErrorManager.initialize();

export {
  // Core error management
  ErrorManager,
  
  // API utilities
  apiErrorHandler,
  enhancedFetch,
  get,
  post,
  put,
  del
};

export default ErrorManager;