/**
 * Data validation utilities for safe component rendering
 * Prevents null reference errors when API returns incomplete data
 */

export const validateDataStructure = (data, requiredFields = [], fallback = {}) => {
  if (!data || typeof data !== 'object') {
    console.warn('[DataValidation] Invalid data structure:', data);
    return fallback;
  }

  const missing = requiredFields.filter(field => !(field in data));
  if (missing.length > 0) {
    console.warn('[DataValidation] Missing required fields:', missing);
    return { ...fallback, ...data };
  }

  return data;
};

export const getNestedValue = (obj, path, defaultValue = null) => {
  try {
    const value = path.split('.').reduce((current, prop) => {
      if (current && typeof current === 'object') {
        return current[prop];
      }
      return undefined;
    }, obj);
    return value !== undefined ? value : defaultValue;
  } catch (error) {
    console.warn(`[DataValidation] Error accessing path "${path}":`, error.message);
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

  if (!data || typeof data !== 'object') {
    return fallback;
  }

  return {
    success: data.success !== false,
    current: data.current && typeof data.current === 'object' ? data.current : null,
    active_tier: data.active_tier && typeof data.active_tier === 'object' ? data.active_tier : {},
    history: Array.isArray(data.history) ? data.history : [],
    sectors: Array.isArray(data.sectors) ? data.sectors : [],
    market_health: data.market_health && typeof data.market_health === 'object' ? data.market_health : null,
  };
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

  if (!data || typeof data !== 'object') {
    return fallback;
  }

  return {
    items: Array.isArray(data.items) ? data.items : [],
    pagination: data.pagination && typeof data.pagination === 'object' ? data.pagination : fallback.pagination,
  };
};

export const isSuccessResponse = (data) => {
  if (!data || typeof data !== 'object') {
    return false;
  }

  if ('success' in data) {
    return data.success !== false;
  }

  return true;
};

export const getErrorMessage = (data) => {
  if (!data || typeof data !== 'object') {
    return 'Unknown error occurred';
  }

  return (
    data.message ||
    data.error ||
    data.errorType ||
    'An error occurred while loading data'
  );
};
