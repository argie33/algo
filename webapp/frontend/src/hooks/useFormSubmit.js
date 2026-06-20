import { useState, useCallback } from 'react';

/**
 * Form submission hook with proper error handling and rollback.
 *
 * PREVENTS optimistic state updates — only updates state AFTER API success.
 * If API fails, rolls back to previous state.
 *
 * Usage:
 *   const { submit, isSubmitting, error, success } = useFormSubmit(
 *     async (data) => {
 *       const res = await api.post('/api/trades', data);
 *       return res.data;
 *     }
 *   );
 *
 *   const handleSubmit = async (e) => {
 *     e.preventDefault();
 *     const result = await submit({ symbol: 'AAPL', qty: 100 });
 *     if (result.success) {
 *       // Only updates state here, after API confirms
 *       setLocalState(result.data);
 *     }
 *   };
 */
export const useFormSubmit = (submitFn, options = {}) => {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);
  const { onSuccess, onError, timeout = 30000 } = options;

  const submit = useCallback(
    async (data) => {
      // Reset state before submission
      setIsSubmitting(true);
      setError(null);
      setSuccess(false);

      try {
        // Call API with timeout protection
        const submitPromise = submitFn(data);
        const timeoutPromise = new Promise((_, reject) =>
          setTimeout(
            () => reject(new Error(`Form submission timeout after ${timeout}ms`)),
            timeout
          )
        );

        const result = await Promise.race([submitPromise, timeoutPromise]);

        // Only update state if result is valid
        if (!result) {
          throw new Error('No response from server');
        }

        // Check for API-level error
        if (result.error) {
          throw new Error(result.error);
        }

        // Success — now safe to update local state
        setSuccess(true);
        setError(null);

        // Call optional onSuccess callback
        if (onSuccess) {
          onSuccess(result);
        }

        return {
          success: true,
          data: result,
          error: null,
        };
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : String(err);

        // Update state with error
        setError(errorMsg);
        setSuccess(false);

        // Call optional onError callback
        if (onError) {
          onError(err);
        }

        return {
          success: false,
          data: null,
          error: errorMsg,
        };
      } finally {
        setIsSubmitting(false);
      }
    },
    [submitFn, onSuccess, onError, timeout]
  );

  return {
    submit,
    isSubmitting,
    error,
    success,
    reset: useCallback(() => {
      setError(null);
      setSuccess(false);
    }, []),
  };
};

export default useFormSubmit;
