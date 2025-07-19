/**
 * Error Handling System - Main Export File
 * Comprehensive error handling solution for React applications
 */

import ErrorManager from './ErrorManager';
import GlobalErrorBoundary from './GlobalErrorBoundary';
import ErrorToastContainer from './ErrorToast';
import useErrorHandler, { 
  useApiErrorHandler, 
  useNetworkErrorHandler, 
  useAuthErrorHandler,
  useValidationErrorHandler 
} from './useErrorHandler';
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
  
  // React components
  GlobalErrorBoundary,
  ErrorToastContainer,
  
  // React hooks
  useErrorHandler,
  useApiErrorHandler,
  useNetworkErrorHandler,
  useAuthErrorHandler,
  useValidationErrorHandler,
  
  // API utilities
  apiErrorHandler,
  enhancedFetch,
  get,
  post,
  put,
  del
};

export default ErrorManager;