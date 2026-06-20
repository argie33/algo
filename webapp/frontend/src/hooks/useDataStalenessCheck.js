import { useMemo } from 'react';

/**
 * Hook to check staleness across multiple data queries and prevent phantom data display
 * Returns metadata about which data sources are stale and which are safe to display
 *
 * Usage:
 *   const { canShowPositions, staleSections, shouldBlockCritical } = useDataStalenessCheck({
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
    };

    for (const [key, source] of Object.entries(dataSources)) {
      if (!source || !source.data) continue;

      const data = source.data;
      const isStale = data?._isStale === true;
      const isFromCache = data?._fromCache === true;
      const age = data?._age || 0;

      result.dataAges[key] = { isStale, isFromCache, age };

      if (isStale) {
        result.phantomSections.push(key);
        // Don't show positions/trade data if stale
        if (key === 'positions' || key === 'algo-positions') {
          result.canShowPositions = false;
        }
        if (key === 'trades' || key === 'algo-trades' || key === 'algo-equity-curve') {
          result.canShowTradeData = false;
        }
        // Critical sections block rendering
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
 * Returns empty array if data is stale (phantom)
 */
export const safeGetNonPhantomArray = (data, defaultValue = []) => {
  if (!data) return defaultValue;
  if (data._isStale === true) return defaultValue;
  if (Array.isArray(data)) return data;
  return defaultValue;
};

export default {
  useDataStalenessCheck,
  filterPhantomPositions,
  safeGetNonPhantomArray,
};
