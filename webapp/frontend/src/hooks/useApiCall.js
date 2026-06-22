import { useState, useEffect } from "react";

/**
 * Generic hook for async API calls with loading/error/data state
 * Eliminates ~30 lines of boilerplate from every page
 *
 * Usage:
 *   const { data, loading, error } = useApiCall(async () => {
 *     const r = await api.get('/api/sectors?limit=20');
 *     return r.data?.items || r.data?.data;
 *   });
 *
 * With validation:
 *   const { data, loading, error } = useApiCall(
 *     async () => api.get('/api/sectors'),
 *     [],
 *     { validateFn: (result) => validateResponse(result, { requiredFields: ['id', 'name'] }) }
 *   );
 */
export const useApiCall = (fn, deps = [], options = {}) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const { validateFn } = options;

  useEffect(() => {
    let isMounted = true;

    const fetchData = async () => {
      try {
        setLoading(true);
        setError(null);
        let result = await fn();

        // Optional validation
        if (validateFn) {
          const validation = validateFn(result);
          if (!validation.valid) {
            throw new Error(
              validation.errors?.join("; ") ||
                validation.error ||
                "Data validation failed"
            );
          }
          result = validation.data || result;
        }

        if (isMounted) {
          setData(result);
        }
      } catch (err) {
        if (isMounted) {
          setError(err instanceof Error ? err.message : String(err));
          setData(null);
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    fetchData();

    return () => {
      isMounted = false;
    };
  }, [fn, validateFn, ...deps]);

  return { data, loading, error };
};

export default useApiCall;
