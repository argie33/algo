/**
 * Redux Error Reducer - Centralized state management for errors
 * Handles all error states across the application
 */

import ErrorManager from '../error/ErrorManager';

const initialState = {
  errors: [],
  globalError: null,
  networkErrors: [],
  authErrors: [],
  validationErrors: {},
  retryableErrors: [],
  criticalErrors: [],
  isOffline: false,
  lastError: null,
  errorStats: {
    totalErrors: 0,
    errorsByCategory: {},
    errorsByComponent: {},
    recentErrors: []
  }
};

export const errorReducer = (state = initialState, action) => {
  switch (action.type) {
    case '@@ERROR/GLOBAL_ERROR':
      return {
        ...state,
        globalError: action.payload,
        lastError: action.payload,
        errors: [action.payload, ...state.errors].slice(0, 100), // Keep last 100 errors
        errorStats: {
          ...state.errorStats,
          totalErrors: state.errorStats.totalErrors + 1,
          recentErrors: [action.payload, ...state.errorStats.recentErrors].slice(0, 10)
        }
      };

    case '@@ERROR/API_ERROR':
      return {
        ...state,
        networkErrors: [action.payload, ...state.networkErrors].slice(0, 20),
        lastError: action.payload,
        errors: [action.payload, ...state.errors].slice(0, 100),
        errorStats: {
          ...state.errorStats,
          totalErrors: state.errorStats.totalErrors + 1,
          errorsByCategory: {
            ...state.errorStats.errorsByCategory,
            [action.payload.category]: (state.errorStats.errorsByCategory[action.payload.category] || 0) + 1
          }
        }
      };

    case '@@ERROR/UI_ERROR':
      return {
        ...state,
        lastError: action.payload,
        errors: [action.payload, ...state.errors].slice(0, 100),
        errorStats: {
          ...state.errorStats,
          totalErrors: state.errorStats.totalErrors + 1,
          errorsByComponent: {
            ...state.errorStats.errorsByComponent,
            [action.payload.context?.componentName]: (state.errorStats.errorsByComponent[action.payload.context?.componentName] || 0) + 1
          }
        }
      };

    case '@@ERROR/AUTH_ERROR':
      return {
        ...state,
        authErrors: [action.payload, ...state.authErrors].slice(0, 10),
        lastError: action.payload,
        errors: [action.payload, ...state.errors].slice(0, 100)
      };

    case '@@ERROR/VALIDATION_ERROR':
      return {
        ...state,
        validationErrors: {
          ...state.validationErrors,
          [action.payload.field]: action.payload.error
        },
        lastError: action.payload
      };

    case '@@ERROR/CRITICAL_ERROR':
      return {
        ...state,
        criticalErrors: [action.payload, ...state.criticalErrors].slice(0, 5),
        globalError: action.payload,
        lastError: action.payload
      };

    case '@@ERROR/RETRYABLE_ERROR':
      return {
        ...state,
        retryableErrors: [action.payload, ...state.retryableErrors].slice(0, 10),
        lastError: action.payload
      };

    case '@@ERROR/NETWORK_STATUS':
      return {
        ...state,
        isOffline: action.payload.isOffline
      };

    case '@@ERROR/CLEAR_ERROR':
      if (action.payload?.errorId) {
        return {
          ...state,
          errors: state.errors.filter(error => error.id !== action.payload.errorId),
          globalError: state.globalError?.id === action.payload.errorId ? null : state.globalError
        };
      }
      return {
        ...state,
        globalError: null,
        lastError: null
      };

    case '@@ERROR/CLEAR_VALIDATION_ERROR':
      const newValidationErrors = { ...state.validationErrors };
      delete newValidationErrors[action.payload.field];
      return {
        ...state,
        validationErrors: newValidationErrors
      };

    case '@@ERROR/CLEAR_ALL_ERRORS':
      return {
        ...initialState,
        errorStats: state.errorStats // Preserve stats
      };

    case '@@ERROR/MARK_ERROR_RESOLVED':
      return {
        ...state,
        errors: state.errors.map(error => 
          error.id === action.payload.errorId 
            ? { ...error, resolved: true, resolvedAt: Date.now() }
            : error
        )
      };

    default:
      return state;
  }
};

// Action creators
export const errorActions = {
  globalError: (error) => ({
    type: '@@ERROR/GLOBAL_ERROR',
    payload: error
  }),

  apiError: (error) => ({
    type: '@@ERROR/API_ERROR',
    payload: error
  }),

  uiError: (error) => ({
    type: '@@ERROR/UI_ERROR',
    payload: error
  }),

  authError: (error) => ({
    type: '@@ERROR/AUTH_ERROR',
    payload: error
  }),

  validationError: (field, error) => ({
    type: '@@ERROR/VALIDATION_ERROR',
    payload: { field, error }
  }),

  criticalError: (error) => ({
    type: '@@ERROR/CRITICAL_ERROR',
    payload: error
  }),

  retryableError: (error) => ({
    type: '@@ERROR/RETRYABLE_ERROR',
    payload: error
  }),

  networkStatus: (isOffline) => ({
    type: '@@ERROR/NETWORK_STATUS',
    payload: { isOffline }
  }),

  clearError: (errorId = null) => ({
    type: '@@ERROR/CLEAR_ERROR',
    payload: { errorId }
  }),

  clearValidationError: (field) => ({
    type: '@@ERROR/CLEAR_VALIDATION_ERROR',
    payload: { field }
  }),

  clearAllErrors: () => ({
    type: '@@ERROR/CLEAR_ALL_ERRORS'
  }),

  markErrorResolved: (errorId) => ({
    type: '@@ERROR/MARK_ERROR_RESOLVED',
    payload: { errorId }
  })
};

// Selectors
export const errorSelectors = {
  getAllErrors: (state) => state.errors?.errors || [],
  getGlobalError: (state) => state.errors?.globalError,
  getNetworkErrors: (state) => state.errors?.networkErrors || [],
  getAuthErrors: (state) => state.errors?.authErrors || [],
  getValidationErrors: (state) => state.errors?.validationErrors || {},
  getCriticalErrors: (state) => state.errors?.criticalErrors || [],
  getRetryableErrors: (state) => state.errors?.retryableErrors || [],
  getIsOffline: (state) => state.errors?.isOffline || false,
  getLastError: (state) => state.errors?.lastError,
  getErrorStats: (state) => state.errors?.errorStats || {},
  hasErrors: (state) => (state.errors?.errors?.length || 0) > 0,
  hasValidationErrors: (state) => Object.keys(state.errors?.validationErrors || {}).length > 0,
  getErrorsByComponent: (state, componentName) => 
    (state.errors?.errors || []).filter(error => error.context?.componentName === componentName),
  getErrorsByCategory: (state, category) =>
    (state.errors?.errors || []).filter(error => error.category === category),
  getUnresolvedErrors: (state) =>
    (state.errors?.errors || []).filter(error => !error.resolved)
};

export default errorReducer;