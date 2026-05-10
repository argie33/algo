import { useState, useEffect } from 'react';

/**
 * Generic hook for async API calls with loading/error/data state
 * Eliminates ~30 lines of boilerplate from every page
 *
 * Usage:
 *   const { data, loading, error } = useApiCall(async () => {
 *     const r = await api.get('/api/sectors?limit=20');
 *     return r.data?.items || r.data?.data;
 *   });
 */
export const useApiCall = (fn, deps = []) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let isMounted = true;

    const fetchData = async () => {
      try {
        setLoading(true);
        setError(null);
        const result = await fn();
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
  }, [fn, ...deps]);

  return { data, loading, error };
};

export default useApiCall;
