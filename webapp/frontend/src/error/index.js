/**
 * Error Handling System - Components Export
 * React components and hooks only for proper React Refresh HMR
 */

import GlobalErrorBoundary from './GlobalErrorBoundary';
import ErrorToastContainer from './ErrorToast';
import useErrorHandler, { 
  useApiErrorHandler, 
  useNetworkErrorHandler, 
  useAuthErrorHandler,
  useValidationErrorHandler 
} from './useErrorHandler';

export {
  // React components
  GlobalErrorBoundary,
  ErrorToastContainer,
  
  // React hooks
  useErrorHandler,
  useApiErrorHandler,
  useNetworkErrorHandler,
  useAuthErrorHandler,
  useValidationErrorHandler
};

export default GlobalErrorBoundary;