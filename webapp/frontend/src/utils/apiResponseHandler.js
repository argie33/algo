/**
 * Standardized API response handler
 * Wraps axios responses and ensures consistent error handling
 */

import { extractData, extractPaginatedData } from "./responseNormalizer";

/**
 * Safe wrapper for API calls that handles both success and error cases
 * Ensures data is never undefined, even on errors
 */
export const safeExtractData = (response, fallback = null) => {
  try {
    if (!response) {
      return fallback;
    }
    return extractData(response) || fallback;
  } catch (error) {
    console.warn("[API_HANDLER] Data extraction failed:", error.message);
    return fallback;
  }
};

export const safeExtractPaginatedData = (
  response,
  fallback = { items: [], pagination: {} }
) => {
  try {
    if (!response) {
      return fallback;
    }
    const extracted = extractPaginatedData(response);
    return {
      items: Array.isArray(extracted?.items) ? extracted.items : [],
      pagination: extracted?.pagination || fallback.pagination,
    };
  } catch (error) {
    console.warn(
      "[API_HANDLER] Paginated data extraction failed:",
      error.message
    );
    return fallback;
  }
};

/**
 * Ensure array data is always an array, never undefined
 */
export const ensureArray = (data) => {
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.items)) return data.items;
  if (data && Array.isArray(data.data)) return data.data;
  return [];
};

/**
 * Ensure object data is never undefined
 */
export const ensureObject = (data, defaults = {}) => {
  if (!data || typeof data !== "object") return defaults;
  return { ...defaults, ...data };
};

export default {
  safeExtractData,
  safeExtractPaginatedData,
  ensureArray,
  ensureObject,
};
