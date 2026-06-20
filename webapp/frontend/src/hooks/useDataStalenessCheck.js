import { useMemo } from 'react';

/**
 * Hook to check staleness across multiple data queries and prevent phantom data display
 * Returns metadata about which data sources are stale and which are safe to display
 * Defensive: handles missing/null data sources safely
 *
 * Usage:
 *   const { canShowPositions, staleSections, hasCriticalStale } = useDataStalenessCheck({
 *     positions: { data: posData, error: posError },
 *     performance: { data: perfData, error: perfError },
 *   });
 */
export const useDataStalenessCheck = (dataSources = {}) => {
  const stalnessMetadata = useMemo(() => {
    const result = {
      staleSections: [],
      phantomSections: [],
      canShowCritical: true,
      canShowPositions: true,
      canShowTradeData: true,
      dataAges: {},
      hasCriticalStale: false,
      shouldBlockCritical: false,
    };

    if (!dataSources || typeof dataSources !== 'object') {
      return result;
    }

    for (const [key, source] of Object.entries(dataSources)) {
      if (!source || typeof source !== 'object') continue;

      const data = source.data;
      if (!data || typeof data !== 'object') continue;

      const isStale = data._isStale === true;
      const isFromCache = data._fromCache === true;
      const age = typeof data._age === 'number' && data._age >= 0 ? data._age : 0;

      result.dataAges[key] = { isStale, isFromCache, age };

      if (isStale) {
        result.phantomSections.push(key);
        if (key === 'positions' || key === 'algo-positions') {
          result.canShowPositions = false;
        }
        if (key === 'trades' || key === 'algo-trades' || key === 'algo-equity-curve') {
          result.canShowTradeData = false;
        }
        if (['status', 'positions', 'markets'].includes(key)) {
          result.canShowCritical = false;
        }
      }

      if (isFromCache) {
        result.staleSections.push(key);
      }
    }

    result.shouldBlockCritical = !result.canShowCritical;
    result.hasCriticalStale = result.phantomSections.length > 0;

    return result;
  }, [dataSources]);

  return stalnessMetadata;
};

/**
 * Filter phantom positions from display
 * Positions are phantom if data is >2 hours old
 */
export const filterPhantomPositions = (positions, data) => {
  if (!Array.isArray(positions)) return [];
  if (!data || data._isStale !== true) return positions;

  // Don't show positions if data is stale
  console.warn('[Portfolio] Hiding phantom positions - data is stale:', data._age);
  return [];
};

/**
 * Safe accessor for data that might be phantom
 * Returns empty array if data is stale (phantom) or null/undefined
 * Defensive: all checks are type-safe and handle edge cases
 */
export const safeGetNonPhantomArray = (data, defaultValue = []) => {
  if (!data) return Array.isArray(defaultValue) ? defaultValue : [];
  if (data._isStale === true) return Array.isArray(defaultValue) ? defaultValue : [];
  if (Array.isArray(data)) return data;
  if (data.data && Array.isArray(data.data)) return data.data;
  return Array.isArray(defaultValue) ? defaultValue : [];
};

/**
 * Check if array is safe to display (not phantom, has content, or is legitimately empty)
 * Returns true if safe to show, false if likely phantom/incomplete
 */
export const isArraySafe = (data) => {
  if (!data) return false;
  if (typeof data !== 'object') return false;
  if (data._isStale === true) return false;
  if (Array.isArray(data)) return true;
  return false;
};

/**
 * Ensure safe object access with defaults
 * Handles null/undefined/wrong-type at each level
 */
export const safeGetValue = (obj, path, defaultValue = null) => {
  if (!obj || typeof obj !== 'object') return defaultValue;
  if (typeof path !== 'string') return defaultValue;

  const keys = path.split('.');
  let current = obj;
  for (const key of keys) {
    if (current == null || typeof current !== 'object') return defaultValue;
    current = current[key];
  }
  return current ?? defaultValue;
};

export default {
  useDataStalenessCheck,
  filterPhantomPositions,
  safeGetNonPhantomArray,
  isArraySafe,
  safeGetValue,
};
