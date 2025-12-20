/**
 * useData Hook - React Query replacement
 * Provides React Query-like interface using native fetch and React state
 */

import { useState, useEffect, useCallback, useRef } from "react";
import dataService from "../services/dataService";

// Main data fetching hook
export function useData(url, options = {}) {
  const [state, setState] = useState({
    data: null,
    isLoading: true,
    error: null,
    isStale: false,
  });

  const optionsRef = useRef(options);
  optionsRef.current = options;

  const fetchData = useCallback(async () => {
    if (!url || optionsRef.current.enabled === false) {
      setState((prev) => ({ ...prev, isLoading: false }));
      return;
    }

    try {
      const result = await dataService.fetchData(url, optionsRef.current);
      setState(result);
    } catch (error) {
      setState({
        data: null,
        isLoading: false,
        error,
        isStale: false,
      });
    }
  }, [url]);

  const refetch = useCallback(async () => {
    if (!url) return;

    setState((prev) => ({ ...prev, isLoading: true, error: null }));
    try {
      const result = await dataService.refetch(url, optionsRef.current);
      setState(result);
      return result;
    } catch (error) {
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error,
      }));
      throw error;
    }
  }, [url]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Subscribe to data changes
  useEffect(() => {
    if (!url) return;

    const cacheKey = dataService.getCacheKey(url, optionsRef.current);
    return dataService.subscribe(cacheKey, setState);
  }, [url]);

  return {
    data: state?.data,
    isLoading: state.isLoading,
    error: state.error,
    isStale: state.isStale,
    refetch,
  };
}

// Query hook with React Query-like interface
export function useQuery(options) {
  const {
    queryKey: _queryKey,
    queryFn,
    enabled = true,
    staleTime,
    cacheTime,
    ...otherOptions
  } = options;

  // Build URL from queryKey if it's an array (URL not used in current implementation)

  // Custom fetch function handling
  const [state, setState] = useState({
    data: null,
    isLoading: enabled,
    error: null,
    isStale: false,
  });

  const optionsRef = useRef({ enabled, staleTime, cacheTime, ...otherOptions });
  optionsRef.current = { enabled, staleTime, cacheTime, ...otherOptions };

  const fetchData = useCallback(async () => {
    if (!enabled || !queryFn) {
      setState((prev) => ({ ...prev, isLoading: false }));
      return;
    }

    setState((prev) => ({ ...prev, isLoading: true, error: null }));

    try {
      const data = await queryFn();
      setState({
        data,
        isLoading: false,
        error: null,
        isStale: false,
      });
    } catch (error) {
      setState({
        data: null,
        isLoading: false,
        error,
        isStale: false,
      });
    }
  }, [queryFn, enabled]);

  const refetch = useCallback(async () => {
    if (!queryFn) return;

    setState((prev) => ({ ...prev, isLoading: true, error: null }));
    try {
      const data = await queryFn();
      setState({
        data,
        isLoading: false,
        error: null,
        isStale: false,
      });
      return { data };
    } catch (error) {
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error,
      }));
      throw error;
    }
  }, [queryFn]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return {
    data: state?.data,
    isLoading: state.isLoading,
    error: state.error,
    isStale: state.isStale,
    refetch,
  };
}

// Mutation hook for POST/PUT/DELETE operations
export function useMutation(mutationFn, options = {}) {
  const [state, setState] = useState({
    data: null,
    isLoading: false,
    error: null,
  });

  const mutate = useCallback(
    async (variables) => {
      setState({ data: null, isLoading: true, error: null });

      try {
        const data = await mutationFn(variables);
        setState({ data, isLoading: false, error: null });

        if (options.onSuccess) {
          options.onSuccess(data, variables);
        }

        return data;
      } catch (error) {
        setState({ data: null, isLoading: false, error });

        if (options.onError) {
          options.onError(error, variables);
        }

        throw error;
      }
    },
    [mutationFn, options]
  );

  return {
    mutate,
    data: state?.data,
    isLoading: state.isLoading,
    error: state.error,
  };
}

// Infinite query hook (simplified version)
export function useInfiniteQuery(options) {
  const {
    queryKey: _queryKey,
    queryFn,
    getNextPageParam,
    enabled = true,
  } = options;

  const [state, setState] = useState({
    data: { pages: [], pageParams: [] },
    isLoading: enabled,
    error: null,
    hasNextPage: false,
    isFetchingNextPage: false,
  });

  const fetchNextPage = useCallback(async () => {
    if (!queryFn || state.isFetchingNextPage) return;

    setState((prev) => ({ ...prev, isFetchingNextPage: true }));

    try {
      const lastPage = state?.data.pages[(state?.data.pages?.length || 0) - 1];
      const nextPageParam = getNextPageParam
        ? getNextPageParam(lastPage)
        : undefined;

      if (nextPageParam === undefined) {
        setState((prev) => ({ ...prev, isFetchingNextPage: false }));
        return;
      }

      const newPage = await queryFn({ pageParam: nextPageParam });

      setState((prev) => ({
        ...prev,
        data: {
          pages: [...(prev?.data?.pages || []), newPage],
          pageParams: [...(prev?.data?.pageParams || []), nextPageParam],
        },
        isFetchingNextPage: false,
        hasNextPage: getNextPageParam
          ? getNextPageParam(newPage) !== undefined
          : false,
      }));
    } catch (error) {
      setState((prev) => ({
        ...prev,
        error,
        isFetchingNextPage: false,
      }));
    }
  }, [queryFn, getNextPageParam, state?.data.pages, state.isFetchingNextPage]);

  const fetchFirstPage = useCallback(async () => {
    if (!enabled || !queryFn) {
      setState((prev) => ({ ...prev, isLoading: false }));
      return;
    }

    setState((prev) => ({ ...prev, isLoading: true, error: null }));

    try {
      const firstPage = await queryFn({ pageParam: undefined });
      setState({
        data: { pages: [firstPage], pageParams: [undefined] },
        isLoading: false,
        error: null,
        hasNextPage: getNextPageParam
          ? getNextPageParam(firstPage) !== undefined
          : false,
        isFetchingNextPage: false,
      });
    } catch (error) {
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error,
      }));
    }
  }, [queryFn, enabled, getNextPageParam]);

  useEffect(() => {
    fetchFirstPage();
  }, [fetchFirstPage]);

  return {
    data: state?.data,
    isLoading: state.isLoading,
    error: state.error,
    hasNextPage: state.hasNextPage,
    fetchNextPage,
    isFetchingNextPage: state.isFetchingNextPage,
  };
}

export default { useData, useQuery, useMutation, useInfiniteQuery };
