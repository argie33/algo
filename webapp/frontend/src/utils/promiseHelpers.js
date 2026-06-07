/**
 * Promise utility helpers to prevent unhandled rejections
 * These utilities ensure that all async operations have proper error handling
 */

/**
 * Safely execute an async function with automatic error handling
 * Prevents unhandled promise rejections by attaching a catch handler
 *
 * Usage:
 *   safeAsync(async () => {
 *     const data = await fetchData();
 *     return data;
 *   });
 */
export const safeAsync = (asyncFn, onError = null) => {
  const promise = (async () => {
    try {
      return await asyncFn();
    } catch (error) {
      if (onError) {
        onError(error);
      } else {
        console.error('[SafeAsync] Unhandled error:', error.message);
      }
      // Return undefined instead of throwing to prevent unhandled rejection
      return undefined;
    }
  })();

  // Always attach a catch handler to prevent unhandled rejections
  promise.catch(error => {
    if (onError) {
      onError(error);
    } else {
      console.error('[SafeAsync] Caught error:', error.message);
    }
  });

  return promise;
};

/**
 * Wrap a promise to add automatic error handling
 * Useful for fire-and-forget async operations
 *
 * Usage:
 *   fireAndForget(somePromise);
 *   // or
 *   fireAndForget(somePromise, (err) => console.log('Error:', err));
 */
export const fireAndForget = (promise, onError = null) => {
  if (!promise || !promise.catch) {
    return;
  }

  promise.catch(error => {
    if (onError) {
      onError(error);
    } else {
      console.error('[FireAndForget] Unhandled rejection:', error.message);
    }
  });
};

/**
 * Race multiple promises with a timeout
 * Prevents hanging promises by enforcing a maximum wait time
 *
 * Usage:
 *   const result = await promiseWithTimeout(
 *     fetchData(),
 *     5000,
 *     'Fetch data timeout'
 *   );
 */
export const promiseWithTimeout = (promise, ms, message = 'Promise timeout') => {
  return Promise.race([
    promise,
    new Promise((_, reject) =>
      setTimeout(() => reject(new Error(message)), ms)
    ),
  ]);
};

/**
 * Execute multiple promises and catch all errors without throwing
 * Useful for cleanup operations that shouldn't block the app
 *
 * Usage:
 *   await executeAll([
 *     clearCache(),
 *     logoutUser(),
 *     closeConnections()
 *   ]);
 */
export const executeAll = async (promises) => {
  const results = await Promise.allSettled(promises);
  const errors = results
    .filter(r => r.status === 'rejected')
    .map(r => r.reason);

  if (errors.length > 0) {
    console.warn('[ExecuteAll] Some operations failed:', errors);
  }

  return results;
};

/**
 * Create a promise that resolves after a delay
 * Useful for debouncing and throttling
 *
 * Usage:
 *   await delay(1000);
 */
export const delay = (ms) =>
  new Promise(resolve => setTimeout(resolve, ms));
