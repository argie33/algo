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
 * Returns economic dashboard thresholds.
 *
 * Uses static defaults — the /api/settings/thresholds endpoint is protected
 * (requires auth) but EconomicDashboard is a public page, so calling it would
 * cause a 401 → login redirect for unauthenticated visitors. The defaults here
 * are the canonical values; update DEFAULT_THRESHOLDS if they need to change.
 *
 * Usage:
 *   const { thresholds } = useThresholds();
 *   if (value > thresholds.vix_critical) { ... }
 */
export const useThresholds = (_options = {}) => {
  return {
    thresholds: DEFAULT_THRESHOLDS,
    loading: false,
    error: null,
    isDefault: true,
  };
};

export default useThresholds;
