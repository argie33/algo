/**
 * Standardized API response handler
 * Wraps axios responses and ensures consistent error handling
 */

import { extractData, extractPaginatedData } from "./responseNormalizer";

/**
 * Extract data from API response, raising on validation failure.
 *
 * FINANCE SAFETY: This function does NOT provide fallback values. Missing or
 * malformed data must be explicitly handled at the call site. Silently returning
 * empty arrays or null values masks data integrity issues.
 *
 * Use this when API data is required for correct UI rendering.
 */
export const safeExtractData = (response, fallback = null) => {
  if (!response) {
    throw new Error(
      "[API_HANDLER] Response is null/undefined. Cannot extract data. " +
      "Caller must check API status before using response."
    );
  }
  try {
    const extracted = extractData(response);
    if (extracted === undefined) {
      throw new Error(
        "[API_HANDLER] Data extraction returned undefined. " +
        "Response structure may not match expected schema."
      );
    }
    return extracted;
  } catch (error) {
    throw new Error(
      `[API_HANDLER] Data extraction failed: ${error.message}. ` +
      "Cannot proceed with undefined data structure. " +
      "Check API response schema."
    );
  }
};

/**
 * Extract paginated data from API response, raising on validation failure.
 *
 * FINANCE SAFETY: This function does NOT provide fallback empty arrays.
 * Missing items or pagination metadata must be explicitly handled.
 *
 * Use this when paginated data is required for complete UI rendering.
 */
export const safeExtractPaginatedData = (
  response,
  fallback = { items: [], pagination: {} }
) => {
  if (!response) {
    throw new Error(
      "[API_HANDLER] Response is null/undefined. Cannot extract paginated data. " +
      "Caller must check API status before using response."
    );
  }
  try {
    const extracted = extractPaginatedData(response);
    if (!extracted) {
      throw new Error("[API_HANDLER] extractPaginatedData returned null");
    }
    if (!Array.isArray(extracted?.items)) {
      throw new Error(
        `[API_HANDLER] Paginated 'items' field is not an array, got ${typeof extracted?.items}`
      );
    }
    return {
      items: extracted.items,
      pagination: extracted.pagination || {},
    };
  } catch (error) {
    throw new Error(
      `[API_HANDLER] Paginated data extraction failed: ${error.message}. ` +
      "Cannot render paginated content with missing data structure."
    );
  }
};

/**
 * Ensure array data is an array, raising if not.
 *
 * FINANCE SAFETY: Raises if data is not a valid array. Do not use as a
 * silent fallback to empty arrays.
 */
export const ensureArray = (data) => {
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.items)) return data.items;
  if (data && Array.isArray(data.data)) return data.data;
  throw new TypeError(
    `[API_HANDLER] Expected array data, got ${typeof data}. ` +
    "Response structure does not match expected schema."
  );
};

/**
 * Ensure object data is an object, raising if not.
 *
 * FINANCE SAFETY: Raises if data is not a valid object. Do not use as a
 * silent fallback to empty objects.
 */
export const ensureObject = (data, defaults = {}) => {
  if (data && typeof data === "object") {
    return { ...defaults, ...data };
  }
  throw new TypeError(
    `[API_HANDLER] Expected object data, got ${typeof data}. ` +
    "Response structure does not match expected schema."
  );
};

export default {
  safeExtractData,
  safeExtractPaginatedData,
  ensureArray,
  ensureObject,
};
