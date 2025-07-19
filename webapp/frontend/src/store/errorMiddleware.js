/**
 * Redux Error Middleware - Integrates error handling with Redux state management
 * Captures and logs all Redux-related errors
 */

import ErrorManager from '../error/ErrorManager';
import { errorActions } from './errorReducer';

export const createErrorMiddleware = () => {
  return (store) => (next) => (action) => {
    try {
      // Log action start
      if (action.type && !action.type.startsWith('@@ERROR/')) {
        ErrorManager.handleError({
          type: 'redux_action_dispatched',
          message: `Redux action dispatched: ${action.type}`,
          category: ErrorManager.CATEGORIES.UI,
          severity: ErrorManager.SEVERITY.LOW,
          context: {
            actionType: action.type,
            hasPayload: !!action.payload,
            stateSize: JSON.stringify(store.getState()).length
          }
        });
      }

      const result = next(action);

      // Check for action errors
      if (action.error || (action.payload && action.payload.error)) {
        const error = action.error || action.payload.error;
        
        const enhancedError = ErrorManager.handleError({
          type: 'redux_action_error',
          message: `Redux action failed: ${action.type}`,
          error: error,
          category: ErrorManager.CATEGORIES.UI,
          severity: ErrorManager.SEVERITY.MEDIUM,
          context: {
            actionType: action.type,
            payload: action.payload,
            meta: action.meta
          }
        });

        // Dispatch to error store
        store.dispatch(errorActions.uiError(enhancedError));
      }

      return result;
    } catch (error) {
      const enhancedError = ErrorManager.handleError({
        type: 'redux_middleware_error',
        message: `Redux middleware error processing ${action.type}: ${error.message}`,
        error: error,
        category: ErrorManager.CATEGORIES.UI,
        severity: ErrorManager.SEVERITY.HIGH,
        context: {
          actionType: action.type,
          actionPayload: action.payload,
          stack: error.stack
        }
      });

      // Dispatch to error store
      store.dispatch(errorActions.criticalError(enhancedError));

      // Don't break the application, return the action
      return action;
    }
  };
};

export default createErrorMiddleware;