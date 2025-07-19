/**
 * useErrorBoundaryState - Comprehensive hooks for state management with error handling
 * Provides state management with automatic error recovery and logging
 */

import { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import ErrorManager from '../error/ErrorManager';

/**
 * Enhanced useState with error handling and validation
 */
export const useErrorBoundaryState = (initialState, options = {}) => {
  const {
    validateState = null,
    onStateChange = null,
    onError = null,
    stateName = 'unknown',
    enableLogging = true,
    enableRecovery = true,
    maxRetries = 3
  } = options;

  const [state, setState] = useState(initialState);
  const [error, setError] = useState(null);
  const [retryCount, setRetryCount] = useState(0);
  const stateHistory = useRef([initialState]);
  const errorHistory = useRef([]);

  const enhancedSetState = useCallback((newState) => {
    try {
      // Validate new state if validator provided
      if (validateState) {
        const validation = validateState(newState, state);
        if (!validation.valid) {
          throw new Error(`State validation failed for ${stateName}: ${validation.message}`);
        }
      }

      // Update state
      setState(newState);
      
      // Track state history
      stateHistory.current.push(newState);
      if (stateHistory.current.length > 10) {
        stateHistory.current.shift();
      }

      // Clear error on successful state change
      if (error) {
        setError(null);
        setRetryCount(0);
      }

      // Log state change
      if (enableLogging) {
        ErrorManager.handleError({
          type: 'state_change_success',
          message: `State ${stateName} updated successfully`,
          category: ErrorManager.CATEGORIES.UI,
          severity: ErrorManager.SEVERITY.LOW,
          context: {
            stateName,
            previousState: state,
            newState,
            stateSize: JSON.stringify(newState).length
          }
        });
      }

      // Call state change callback
      if (onStateChange) {
        onStateChange(newState, state);
      }

    } catch (stateError) {
      const enhancedError = ErrorManager.handleError({
        type: 'state_update_failed',
        message: `Failed to update state ${stateName}: ${stateError.message}`,
        error: stateError,
        category: ErrorManager.CATEGORIES.UI,
        severity: ErrorManager.SEVERITY.MEDIUM,
        context: {
          stateName,
          currentState: state,
          attemptedState: newState,
          retryCount,
          stateHistory: stateHistory.current.slice(-3)
        }
      });

      setError(enhancedError);
      errorHistory.current.push(enhancedError);
      
      if (onError) {
        onError(enhancedError, newState, state);
      }

      // Auto-recovery if enabled
      if (enableRecovery && retryCount < maxRetries) {
        setTimeout(() => {
          setRetryCount(prev => prev + 1);
          enhancedSetState(newState);
        }, 1000 * Math.pow(2, retryCount));
      }
    }
  }, [state, error, retryCount, validateState, onStateChange, onError, stateName, enableLogging, enableRecovery, maxRetries]);

  const recoverState = useCallback(() => {
    if (stateHistory.current.length > 1) {
      const previousState = stateHistory.current[stateHistory.current.length - 2];
      setState(previousState);
      setError(null);
      setRetryCount(0);
      
      ErrorManager.handleError({
        type: 'state_recovered',
        message: `State ${stateName} recovered to previous value`,
        category: ErrorManager.CATEGORIES.UI,
        severity: ErrorManager.SEVERITY.LOW,
        context: {
          stateName,
          recoveredState: previousState,
          errorCount: errorHistory.current.length
        }
      });
    }
  }, [stateName]);

  const resetState = useCallback(() => {
    setState(initialState);
    setError(null);
    setRetryCount(0);
    stateHistory.current = [initialState];
    errorHistory.current = [];
    
    ErrorManager.handleError({
      type: 'state_reset',
      message: `State ${stateName} reset to initial value`,
      category: ErrorManager.CATEGORIES.UI,
      severity: ErrorManager.SEVERITY.LOW,
      context: { stateName, initialState }
    });
  }, [initialState, stateName]);

  const getStateStats = useCallback(() => {
    return {
      currentState: state,
      error,
      retryCount,
      historyLength: stateHistory.current.length,
      errorCount: errorHistory.current.length,
      hasError: !!error,
      canRecover: stateHistory.current.length > 1,
      stateName
    };
  }, [state, error, retryCount, stateName]);

  return [state, enhancedSetState, { error, recoverState, resetState, getStateStats }];
};

/**
 * Enhanced useEffect with error boundary
 */
export const useErrorBoundaryEffect = (effect, deps, options = {}) => {
  const {
    effectName = 'unknown_effect',
    onError = null,
    enableLogging = true,
    catchAsync = true
  } = options;

  const effectId = useRef(0);

  useEffect(() => {
    const currentEffectId = ++effectId.current;
    
    const executeEffect = async () => {
      try {
        if (enableLogging) {
          ErrorManager.handleError({
            type: 'effect_started',
            message: `Effect ${effectName} started`,
            category: ErrorManager.CATEGORIES.UI,
            severity: ErrorManager.SEVERITY.LOW,
            context: {
              effectName,
              effectId: currentEffectId,
              depsLength: deps?.length || 0
            }
          });
        }

        const result = effect();

        // Handle async effects
        if (catchAsync && result && typeof result.then === 'function') {
          await result;
        }

        if (enableLogging) {
          ErrorManager.handleError({
            type: 'effect_completed',
            message: `Effect ${effectName} completed successfully`,
            category: ErrorManager.CATEGORIES.UI,
            severity: ErrorManager.SEVERITY.LOW,
            context: {
              effectName,
              effectId: currentEffectId
            }
          });
        }

      } catch (effectError) {
        const enhancedError = ErrorManager.handleError({
          type: 'effect_failed',
          message: `Effect ${effectName} failed: ${effectError.message}`,
          error: effectError,
          category: ErrorManager.CATEGORIES.UI,
          severity: ErrorManager.SEVERITY.MEDIUM,
          context: {
            effectName,
            effectId: currentEffectId,
            deps,
            stack: effectError.stack
          }
        });

        if (onError) {
          onError(enhancedError);
        }
      }
    };

    executeEffect();
  }, deps);
};

/**
 * Enhanced useCallback with error handling
 */
export const useErrorBoundaryCallback = (callback, deps, options = {}) => {
  const {
    callbackName = 'unknown_callback',
    onError = null,
    enableLogging = true,
    validateArgs = null
  } = options;

  return useCallback((...args) => {
    try {
      // Validate arguments if validator provided
      if (validateArgs) {
        const validation = validateArgs(...args);
        if (!validation.valid) {
          throw new Error(`Callback validation failed for ${callbackName}: ${validation.message}`);
        }
      }

      if (enableLogging) {
        ErrorManager.handleError({
          type: 'callback_invoked',
          message: `Callback ${callbackName} invoked`,
          category: ErrorManager.CATEGORIES.UI,
          severity: ErrorManager.SEVERITY.LOW,
          context: {
            callbackName,
            argCount: args.length,
            args: args.map(arg => typeof arg)
          }
        });
      }

      const result = callback(...args);

      // Handle async callbacks
      if (result && typeof result.then === 'function') {
        return result.catch(asyncError => {
          const enhancedError = ErrorManager.handleError({
            type: 'async_callback_failed',
            message: `Async callback ${callbackName} failed: ${asyncError.message}`,
            error: asyncError,
            category: ErrorManager.CATEGORIES.UI,
            severity: ErrorManager.SEVERITY.MEDIUM,
            context: {
              callbackName,
              args,
              asyncError: asyncError.message
            }
          });

          if (onError) {
            onError(enhancedError);
          }

          throw enhancedError;
        });
      }

      return result;

    } catch (callbackError) {
      const enhancedError = ErrorManager.handleError({
        type: 'callback_failed',
        message: `Callback ${callbackName} failed: ${callbackError.message}`,
        error: callbackError,
        category: ErrorManager.CATEGORIES.UI,
        severity: ErrorManager.SEVERITY.MEDIUM,
        context: {
          callbackName,
          args,
          stack: callbackError.stack
        }
      });

      if (onError) {
        onError(enhancedError);
      }

      throw enhancedError;
    }
  }, deps);
};

/**
 * Enhanced useMemo with error handling
 */
export const useErrorBoundaryMemo = (factory, deps, options = {}) => {
  const {
    memoName = 'unknown_memo',
    onError = null,
    enableLogging = true,
    fallbackValue = null
  } = options;

  return useMemo(() => {
    try {
      if (enableLogging) {
        ErrorManager.handleError({
          type: 'memo_computed',
          message: `Memo ${memoName} computing`,
          category: ErrorManager.CATEGORIES.UI,
          severity: ErrorManager.SEVERITY.LOW,
          context: {
            memoName,
            depsLength: deps?.length || 0
          }
        });
      }

      const result = factory();

      if (enableLogging) {
        ErrorManager.handleError({
          type: 'memo_completed',
          message: `Memo ${memoName} computed successfully`,
          category: ErrorManager.CATEGORIES.UI,
          severity: ErrorManager.SEVERITY.LOW,
          context: {
            memoName,
            resultType: typeof result
          }
        });
      }

      return result;

    } catch (memoError) {
      const enhancedError = ErrorManager.handleError({
        type: 'memo_failed',
        message: `Memo ${memoName} computation failed: ${memoError.message}`,
        error: memoError,
        category: ErrorManager.CATEGORIES.UI,
        severity: ErrorManager.SEVERITY.MEDIUM,
        context: {
          memoName,
          deps,
          stack: memoError.stack
        }
      });

      if (onError) {
        onError(enhancedError);
      }

      // Return fallback value instead of throwing
      if (fallbackValue !== null) {
        return fallbackValue;
      }

      throw enhancedError;
    }
  }, deps);
};

/**
 * Hook for managing component lifecycle errors
 */
export const useComponentErrorTracking = (componentName) => {
  const mountTime = useRef(Date.now());
  const renderCount = useRef(0);
  const errorCount = useRef(0);

  useEffect(() => {
    // Track component mount
    ErrorManager.handleError({
      type: 'component_mounted',
      message: `Component ${componentName} mounted`,
      category: ErrorManager.CATEGORIES.UI,
      severity: ErrorManager.SEVERITY.LOW,
      context: {
        componentName,
        mountTime: mountTime.current
      }
    });

    // Cleanup tracking
    return () => {
      const lifetime = Date.now() - mountTime.current;
      ErrorManager.handleError({
        type: 'component_unmounted',
        message: `Component ${componentName} unmounted`,
        category: ErrorManager.CATEGORIES.UI,
        severity: ErrorManager.SEVERITY.LOW,
        context: {
          componentName,
          lifetime,
          renderCount: renderCount.current,
          errorCount: errorCount.current
        }
      });
    };
  }, [componentName]);

  // Track renders
  useEffect(() => {
    renderCount.current++;
    
    if (renderCount.current > 100) {
      ErrorManager.handleError({
        type: 'excessive_renders',
        message: `Component ${componentName} has rendered ${renderCount.current} times`,
        category: ErrorManager.CATEGORIES.PERFORMANCE,
        severity: ErrorManager.SEVERITY.MEDIUM,
        context: {
          componentName,
          renderCount: renderCount.current,
          lifetime: Date.now() - mountTime.current
        }
      });
    }
  });

  const trackError = useCallback((error) => {
    errorCount.current++;
    ErrorManager.handleError({
      type: 'component_error_tracked',
      message: `Error tracked in component ${componentName}`,
      error: error,
      category: ErrorManager.CATEGORIES.UI,
      severity: ErrorManager.SEVERITY.MEDIUM,
      context: {
        componentName,
        errorCount: errorCount.current,
        renderCount: renderCount.current,
        lifetime: Date.now() - mountTime.current
      }
    });
  }, [componentName]);

  const getComponentStats = useCallback(() => {
    return {
      componentName,
      mountTime: mountTime.current,
      lifetime: Date.now() - mountTime.current,
      renderCount: renderCount.current,
      errorCount: errorCount.current
    };
  }, [componentName]);

  return { trackError, getComponentStats };
};

export default {
  useErrorBoundaryState,
  useErrorBoundaryEffect,
  useErrorBoundaryCallback,
  useErrorBoundaryMemo,
  useComponentErrorTracking
};