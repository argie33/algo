/**
 * useApiWithState — Wrap useApiQuery/useApiPaginatedQuery with error state tracking
 *
 * Instead of extracting isLoading/error/data separately for each call,
 * this creates a normalized state object you can use with DataSection.
 *
 * Usage:
 *   const status = useApiWithState('algo-status', () => api.get('/api/algo/status'));
 *
 *   <DataSection
 *     isLoading={status.isLoading}
 *     error={status.error}
 *     isEmpty={!status.data}
 *   >
 *     {status.data && <StatusComponent {...status.data} />}
 *   </DataSection>
 */

import { useApiQuery, useApiPaginatedQuery } from './useApiQuery';

export function useApiWithState(key, queryFn, options = {}, paginated = false) {
  const hookFn = paginated ? useApiPaginatedQuery : useApiQuery;
  const result = hookFn([key], queryFn, options);

  // Normalize different response shapes
  const data = paginated ? result.items : result.data;
  const error = result.error || null;
  const isLoading = result.isLoading || result.loading || false;

  return {
    data,
    error,
    isLoading,
    refetch: result.refetch,
    status: isLoading ? 'loading' : error ? 'error' : !data ? 'empty' : 'success',
  };
}

/**
 * Batch multiple API calls and track overall state
 * Usage:
 *   const apis = useBatchApiState({
 *     status: ['algo-status', () => api.get('/api/algo/status')],
 *     markets: ['algo-markets', () => api.get('/api/algo/markets')],
 *     scores: ['algo-scores', () => api.get('/api/algo/swing-scores'), { paginated: true }],
 *   });
 *
 *   {apis.anyLoading && <Spinner />}
 *   {apis.anyError && <ErrorBanner errors={apis.errors} />}
 */
export function useBatchApiState(apiMap, options = {}) {
  const results = {};
  const errors = {};
  let anyLoading = false;
  let anyError = false;

  Object.entries(apiMap).forEach(([name, config]) => {
    const [key, queryFn, opts = {}] = config;
    const paginated = opts.paginated || false;
    const state = useApiWithState(key, queryFn, options, paginated);

    results[name] = state;
    if (state.isLoading) anyLoading = true;
    if (state.error) {
      anyError = true;
      errors[name] = state.error;
    }
  });

  return {
    ...results,
    anyLoading,
    anyError,
    errors,
    allReady: !anyLoading && !anyError,
  };
}
