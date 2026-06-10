import { useQuery } from '@tanstack/react-query';
import { api } from '../services/api';

const DEFAULT_THRESHOLDS = {
  // Sahm Rule (unemployment-based recession indicator)
  sahm_critical: 0.5,
  sahm_warning: 0.3,

  // Yield curve spread (10Y-3M or 10Y-2Y)
  spread_critical: -0.5,
  spread_warning: 0,

  // HY Credit Spread (default risk)
  hy_spread_critical: 8,
  hy_spread_warning: 5,

  // IG Credit Spread (financial stress)
  ig_spread_critical: 2.5,
  ig_spread_warning: 1.5,

  // Jobless Claims 6-month change
  claims_critical: 30,
  claims_warning: 20,

  // VIX Volatility (equity fear gauge)
  vix_critical: 35,
  vix_warning: 25,

  // Financial Stress Index (St. Louis Fed)
  stress_critical: 1.5,
  stress_warning: 0.5,

  // CFNAI Composite (85-indicator activity index)
  cfnai_critical: -0.7,
  cfnai_warning: -0.3,
};

/**
 * Fetch economic dashboard thresholds from API
 * Falls back to defaults if API unavailable
 *
 * Usage:
 *   const { thresholds, loading, error } = useThresholds();
 *   if (value > thresholds.vix_critical) { ... }
 */
export const useThresholds = (options = {}) => {
  const {
    staleTime = 30 * 60 * 1000, // 30 minutes
    retry = 2,
    enabled = true,
  } = options;

  const { data: fetchedThresholds, isLoading, error } = useQuery({
    queryKey: ['settings-thresholds'],
    queryFn: async () => {
      try {
        const response = await api.get('/api/settings/thresholds');
        // Merge fetched values with defaults (in case API is missing some)
        return {
          ...DEFAULT_THRESHOLDS,
          ...(response.data?.thresholds || response.data || {}),
        };
      } catch (err) {
        console.warn('[useThresholds] Failed to fetch thresholds, using defaults:', err.message);
        throw err; // This will trigger fallback to default
      }
    },
    staleTime,
    gcTime: 30 * 60 * 1000,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    retry: retry === false ? false : retry,
    enabled,
  });

  // Always return valid thresholds object (use defaults if fetch fails)
  const thresholds = fetchedThresholds || DEFAULT_THRESHOLDS;

  return {
    thresholds,
    loading: isLoading,
    error: error ? {
      message: error?.message || 'Failed to load thresholds',
      status: error?.response?.status,
    } : null,
    isDefault: !fetchedThresholds, // Indicates if we're using defaults
  };
};

export default useThresholds;
