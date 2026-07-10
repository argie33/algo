/**
 * Shared retry strategy for API calls
 * Eliminates duplication between useApiQuery and useApiPaginatedQuery
 *
 * Usage:
 *   retry: getApiRetryStrategy({ maxRetries: 3 })
 *   retryDelay: getApiRetryDelay
 */

export const getApiRetryStrategy = ({ maxRetries = 3 } = {}) => {
  return (failureCount, err) => {
    const status = err?.response?.status ?? err?.status;
    const errorMsg = err?.message || "";

    // Never retry on explicit auth failures (user not logged in)
    if (status === 401 || status === 403) {
      // EXCEPTION: If auth token is being refreshed, allow ONE retry
      // (token refresh happens in background, request might succeed on next attempt)
      if (
        errorMsg.includes("token") ||
        errorMsg.includes("auth") ||
        errorMsg.includes("refresh")
      ) {
        if (failureCount < 1) {
          console.warn(
            "[API Retry] Auth token refresh in progress, retrying once:",
            err.message
          );
          return true;
        }
      }
      return false;
    }

    // Never retry on not found (resource doesn't exist)
    if (status === 404) return false;

    // Retry on 5xx errors with BALANCED retries (fail fast if API is down)
    // Allow up to 3 retries (4 total attempts) for backend recovery
    if (status >= 500) {
      if (failureCount < maxRetries) {
        console.warn(
          `[API Retry] Server error (${status}), retrying (attempt ${failureCount + 1}/${maxRetries})`,
          errorMsg
        );
        return true;
      }
      return false;
    }

    // Retry on network errors and timeouts with LIMITED attempts
    // Aggressive retry strategy: fail fast if API is truly down
    if (
      errorMsg.includes("timeout") ||
      errorMsg.includes("Network") ||
      errorMsg.includes("ECONNREFUSED") ||
      errorMsg.includes("502") ||
      errorMsg.includes("503")
    ) {
      if (failureCount < maxRetries) {
        console.warn(
          `[API Retry] Network error, retrying (attempt ${failureCount + 1}/${maxRetries}):`,
          errorMsg
        );
        return true;
      }
      return false;
    }

    // Default: no retry for unknown errors
    return false;
  };
};

export const getApiRetryDelay = (attemptIndex) => {
  // Aggressive backoff: 200ms, 500ms, 1s (capped at 5s)
  // Total wait time: 0.2+0.5+1 = 1.7s for 3 retries (fail fast if API is down)
  const baseWait = 200 * Math.pow(2, attemptIndex);
  const cappedWait = Math.min(baseWait, 5000);
  return cappedWait;
};
