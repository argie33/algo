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
 *
 * NOTE: This function has a limitation: object keys must be in a stable order
 * (alphabetical). If keys are added/removed dynamically, the hook call order
 * may change, violating Rules of Hooks. Callers should pass a stable apiMap object.
 *
 * Usage:
 *   const apis = useBatchApiState({
 *     markets: ['algo-markets', () => api.get('/api/algo/markets')],
 *     scores: ['algo-scores', () => api.get('/api/algo/swing-scores'), { paginated: true }],
 *     status: ['algo-status', () => api.get('/api/algo/status')],
 *   });
 *
 *   {apis.anyLoading && <Spinner />}
 *   {apis.anyError && <ErrorBanner errors={apis.errors} />}
 */
import { useMemo } from 'react';

export function useBatchApiState(apiMap, options = {}) {
  // Sort keys to ensure deterministic hook call order (prevent Rules of Hooks violation)
  const sortedKeys = useMemo(() => Object.keys(apiMap).sort(), [apiMap]);

  // Call hooks in sorted key order to ensure stability
  const results = {};
  sortedKeys.forEach((name) => {
    const config = apiMap[name];
    const [key, queryFn, opts = {}] = config;
    const paginated = opts.paginated || false;
    results[name] = useApiWithState(key, queryFn, options, paginated);
  });

  // Compute aggregate state
  const anyLoading = Object.values(results).some(s => s.isLoading);
  const anyError = Object.values(results).some(s => s.error);
  const errors = Object.fromEntries(
    Object.entries(results).filter(([_, s]) => s.error).map(([name, s]) => [name, s.error])
  );

  return {
    ...results,
    anyLoading,
    anyError,
    errors,
    allReady: !anyLoading && !anyError,
  };
}

