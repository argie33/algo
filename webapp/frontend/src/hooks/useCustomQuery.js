/**
 * Custom React Query hook implementation that bypasses useSyncExternalStore issues
 * 
 * This provides the same API as useQuery but uses our custom sync external store
 * implementation to avoid the production useState error
 */
import React, { useContext, useCallback, useEffect, useState } from 'react';
import { useCustomSyncExternalStore } from './useCustomSyncExternalStore';

// We'll need to get the QueryClient from context
const QueryClientContext = React.createContext(undefined);

export function useCustomQueryClient() {
  const client = useContext(QueryClientContext);
  if (!client) {
    throw new Error('No QueryClient set, use QueryClientProvider to set one');
  }
  return client;
}

export function useCustomQuery(options) {
  const queryClient = useCustomQueryClient();
  
  // Create a stable query key
  const queryKey = Array.isArray(options) ? options : options.queryKey;
  const queryOptions = Array.isArray(options) ? { queryKey: options } : options;
  
  // Get the query instance
  const [query] = useState(() => {
    const defaultedOptions = queryClient.defaultQueryOptions(queryOptions);
    return queryClient.getQueryCache().build(queryClient, defaultedOptions);
  });

  // Subscribe to query state changes using our custom hook
  const queryState = useCustomSyncExternalStore(
    useCallback((onStoreChange) => {
      return query.subscribe((result) => {
        onStoreChange();
      });
    }, [query]),
    useCallback(() => {
      return query.getOptimisticResult(queryOptions);
    }, [query, queryOptions]),
    useCallback(() => {
      return query.getOptimisticResult(queryOptions);
    }, [query, queryOptions])
  );

  // Update query options when they change
  useEffect(() => {
    query.setOptions(queryOptions, { listeners: false });
  }, [query, queryOptions]);

  // Handle suspense and error boundaries
  if (queryState.isLoading && queryState.isFetching && !queryState.isStale) {
    // Don't throw promise in our custom implementation to avoid suspense issues
  }

  if (queryState.isError && !queryState.isFetching) {
    // Don't throw error in our custom implementation to avoid error boundary issues
    console.error('Query error:', queryState.error);
  }

  return queryState;
}

// Re-export for compatibility
export { useCustomSyncExternalStore } from './useCustomSyncExternalStore';