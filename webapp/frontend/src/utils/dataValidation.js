/**
 * Data validation utilities for safe component rendering
 * Prevents null reference errors when API returns incomplete data
 */

export const validateDataStructure = (
  data,
  requiredFields = [],
  fallback = {}
) => {
  if (!data || typeof data !== "object") {
    console.warn("[DataValidation] Invalid data structure:", data);
    return fallback;
  }

  const missing = requiredFields.filter((field) => !(field in data));
  if (missing.length > 0) {
    console.warn("[DataValidation] Missing required fields:", missing);
    return { ...fallback, ...data };
  }

  return data;
};

export const getNestedValue = (obj, path, defaultValue = null) => {
  try {
    const value = path.split(".").reduce((current, prop) => {
      if (current && typeof current === "object") {
        return current[prop];
      }
      return undefined;
    }, obj);
    return value !== undefined ? value : defaultValue;
  } catch (error) {
    console.warn(
      `[DataValidation] Error accessing path "${path}":`,
      error.message
    );
    return defaultValue;
  }
};

export const validateMarketData = (data) => {
  const fallback = {
    success: false,
    current: null,
    active_tier: {},
    history: [],
    sectors: [],
    market_health: null,
  };

  if (!data || typeof data !== "object") {
    return fallback;
  }

  const current =
    data.current && typeof data.current === "object" ? data.current : null;

  // Ensure nested objects within current exist
  if (current) {
    current.factors =
      current.factors && typeof current.factors === "object"
        ? current.factors
        : {};
  }

  return {
    success: data.success !== false,
    current,
    active_tier:
      data.active_tier && typeof data.active_tier === "object"
        ? data.active_tier
        : {},
    history: Array.isArray(data.history) ? data.history : [],
    sectors: Array.isArray(data.sectors) ? data.sectors : [],
    market_health:
      data.market_health && typeof data.market_health === "object"
        ? data.market_health
        : null,
  };
};

/**
 * Safely access nested market object properties with defaults
 * Prevents crashes from null/undefined in: factors, regime, vix_level, etc.
 */
export const safeGetMarketCurrent = (markets) => {
  if (!markets || typeof markets !== "object") return null;
  const current = markets.current;
  if (!current || typeof current !== "object") return null;

  return {
    exposure_pct:
      current.exposure_pct !== null && current.exposure_pct !== undefined
        ? current.exposure_pct
        : null,
    raw_score:
      current.raw_score !== null && current.raw_score !== undefined
        ? current.raw_score
        : null,
    regime: current.regime ?? "unknown",
    halt_reasons: current.halt_reasons ?? null,
    distribution_days:
      current.distribution_days !== null &&
      current.distribution_days !== undefined
        ? current.distribution_days
        : null,
    factors:
      current.factors && typeof current.factors === "object"
        ? current.factors
        : {},
  };
};

/**
 * Safely access nested factors with all sub-properties defaulted.
 * Spreads ALL raw factor keys so ExposureFactors can access any key
 * (trend_30wk, credit_spread, ad_line, aaii_sentiment, etc.) while
 * type-checking the known complex-object keys.
 */
export const safeGetFactors = (current) => {
  if (!current || !current.factors || typeof current.factors !== "object") {
    return {};
  }
  const f = current.factors;
  // 2026-08-23 pillar redesign (see algo/risk/market_exposure.py's module docstring):
  // the flat 19-key factors dict was replaced by 3 scored pillars (each carrying its
  // own sub-signal detail under "components"), a "macro_watch" section for signals
  // demoted to a slow veto-only role (Sahm Rule / Yield Curve / Inflation
  // Expectations - no longer composite-scored), and "vol_managed_scaling" (Layer 2,
  // currently inert). Guards below cover this new top-level shape; ...f still spreads
  // everything through so an unrecognized/future key survives unchanged rather than
  // being dropped.
  return {
    ...f,
    pillar_trend:
      f.pillar_trend && typeof f.pillar_trend === "object"
        ? f.pillar_trend
        : {},
    pillar_risk:
      f.pillar_risk && typeof f.pillar_risk === "object" ? f.pillar_risk : {},
    pillar_confirm:
      f.pillar_confirm && typeof f.pillar_confirm === "object"
        ? f.pillar_confirm
        : {},
    macro_watch:
      f.macro_watch && typeof f.macro_watch === "object" ? f.macro_watch : {},
    vol_managed_scaling:
      f.vol_managed_scaling && typeof f.vol_managed_scaling === "object"
        ? f.vol_managed_scaling
        : {},
  };
};

/**
 * Safely get sentiment data with null defaults
 */
export const safeGetSentimentData = (data) => {
  const defaults = {
    aaii: { history: [], data: [] },
    naaim: { current: null },
    fearGreed: { current: null },
  };

  if (!data || typeof data !== "object") return defaults;

  return {
    aaii:
      data.aaii && typeof data.aaii === "object" ? data.aaii : defaults.aaii,
    naaim:
      data.naaim && typeof data.naaim === "object"
        ? data.naaim
        : defaults.naaim,
    fearGreed:
      data.fearGreed && typeof data.fearGreed === "object"
        ? data.fearGreed
        : defaults.fearGreed,
  };
};

/**
 * Safely extract array from various response formats
 */
export const safeGetArray = (data, defaultKey = "items") => {
  if (Array.isArray(data)) return data;
  if (data && typeof data === "object" && Array.isArray(data[defaultKey])) {
    return data[defaultKey];
  }
  return [];
};

/**
 * Safely get object from API response (handles both direct object and { data: object } format)
 */
export const safeGetObject = (data, fallback = {}) => {
  if (!data || typeof data !== "object") return fallback;
  if (data.data && typeof data.data === "object" && !Array.isArray(data.data)) {
    return data.data;
  }
  return data;
};

export const validateListData = (data) => {
  const fallback = {
    items: [],
    pagination: {
      total: 0,
      limit: 50,
      offset: 0,
      page: 1,
      totalPages: 0,
    },
  };

  if (!data || typeof data !== "object") {
    return fallback;
  }

  return {
    items: Array.isArray(data.items) ? data.items : [],
    pagination:
      data.pagination && typeof data.pagination === "object"
        ? data.pagination
        : fallback.pagination,
  };
};

export const isSuccessResponse = (data) => {
  if (!data || typeof data !== "object") {
    return false;
  }

  if ("success" in data) {
    return data.success !== false;
  }

  return true;
};

export const getErrorMessage = (data) => {
  if (!data || typeof data !== "object") {
    return "Unknown error occurred";
  }

  return (
    data.message ||
    data.error ||
    data.errorType ||
    "An error occurred while loading data"
  );
};

/**
 * Safe numeric conversion preventing NaN renders
 */
export const safeGetNumber = (value, defaultValue = 0) => {
  const num = Number(value);
  return isNaN(num) ? defaultValue : num;
};

/**
 * Check if value can be safely displayed
 * Rejects null/undefined/NaN
 */
export const isSafeValue = (val) => {
  if (val === null || val === undefined) return false;
  if (typeof val === "number" && isNaN(val)) return false;
  return true;
};

/**
 * Safe fallback rendering for optional values
 */
export const renderOrFallback = (value, fallback = "—") => {
  return isSafeValue(value) ? value : fallback;
};

/**
 * Ensure array from various response formats
 * Handles {items: []}, {data: []}, [], null
 */
export const ensureArray = (data, defaultValue = []) => {
  if (Array.isArray(data)) return data;
  if (data && typeof data === "object") {
    if (Array.isArray(data.items)) return data.items;
    if (Array.isArray(data.data)) return data.data;
    if (Array.isArray(data.results)) return data.results;
  }
  return defaultValue;
};

/**
 * Phantom data check: stale OR empty OR has null values
 */
export const hasPhantomData = (data) => {
  if (!data) return true;
  if (typeof data !== "object") return true;
  if (data._isStale === true) return true;
  if (Array.isArray(data) && data.length === 0) return true;
  return false;
};

/**
 * Get safe numeric value from potentially phantom data
 * Used for percentages, prices, counts that render in display
 */
export const safeNumericValue = (data, keys = [], defaultValue = null) => {
  let current = data;
  for (const key of keys) {
    if (current == null || typeof current !== "object") return defaultValue;
    current = current[key];
  }
  if (current == null) return defaultValue;
  const num = Number(current);
  return isNaN(num) ? defaultValue : num;
};
