/**
 * Standardize API response handling across all pages
 * Single function to extract data regardless of response shape
 */

/**
 * Extract data from API response
 *
 * STANDARD API RESPONSE FORMATS (from Lambda routes):
 *   1. Paginated list: { statusCode: 200, items: [...], total: 10, limit?: N, offset?: N }
 *   2. Single object: { statusCode: 200, data: {...} }
 *   3. Error: { statusCode: 4xx|5xx, errorType: "...", message: "..." }
 *
 * LEGACY FORMATS (deprecated, but still supported):
 *   - { success: true, data: {...} }
 *   - { success: true, items: [...] }
 *
 * @param {object} response - axios/fetch response from API
 * @returns {object|array} the extracted data with full response envelope
 * @throws {Error} if response structure is invalid or status >= 400
 */
export const extractData = (response) => {
  if (!response) {
    throw new Error('Response is null or undefined');
  }

  // Handle axios response structure
  const data = response.data || response;

  if (!data) {
    throw new Error('Response data is null or undefined');
  }

  // If success is false (legacy format), throw error
  if (data.success === false) {
    throw new Error(data.message || 'API request failed');
  }

  // Check HTTP status from axios response object (statusCode was removed by lambda handler)
  const httpStatus = response.status !== undefined ? response.status : data.statusCode;
  if (httpStatus >= 400) {
    throw new Error(data.message || data.errorType || `API error: ${httpStatus}`);
  }

  // Priority order for extracting data:
  // 1. data.items (most common paginated response) — return full envelope so components can access .items, .total, .pagination
  if (Array.isArray(data.items)) {
    // Ensure items array is valid; filter out null/undefined entries
    const filteredItems = data.items.filter(item => item !== null && item !== undefined);
    return {
      ...data,
      items: filteredItems,
      total: data.total || data.items.length,
    };
  }

  // 2. data.data (nested structure)
  if (data.data !== null && data.data !== undefined) {
    // Check if data.data has items (double-nested)
    if (Array.isArray(data.data.items)) {
      const filteredItems = data.data.items.filter(item => item !== null && item !== undefined);
      return {
        ...data.data,
        items: filteredItems,
        total: data.data.total || data.data.items.length,
      };
    }
    // Return the data object itself (ensure it's an object)
    if (typeof data.data === 'object') {
      return data.data;
    }
  }

  // 3. The whole data object (if no items/data field)
  if (typeof data === 'object' && data !== null) {
    return data;
  }

  // Enhanced error for debugging: detect HTML responses (usually 404/error pages from CDN)
  const isHtml = typeof data === 'string' && data.includes('<');
  const preview = typeof data === 'string'
    ? data.substring(0, 150)
    : JSON.stringify(data).substring(0, 150);
  const statusCode = response.status ? ` (HTTP ${response.status})` : '';
  throw new Error(`Unable to extract data from response${statusCode}${isHtml ? ' (received HTML, likely 404 or CDN error)' : ''}: ${preview}`);
};

/**
 * Extract paginated response with metadata
 * @param {object} response - axios/fetch response
 * @returns {object} { items: [...], pagination: {...} }
 */
export const extractPaginatedData = (response) => {
  const data = response.data || response;

  // If success is false (legacy format), throw error
  if (data.success === false) {
    throw new Error(data.message || 'API request failed');
  }

  // Check HTTP status from axios response object (statusCode was removed by lambda handler)
  const httpStatus = response.status !== undefined ? response.status : data.statusCode;
  if (httpStatus >= 400) {
    throw new Error(data.message || data.errorType || `API error: ${httpStatus}`);
  }

  // Extract items (should be array, not full envelope) — filter out null/undefined entries, default to empty array for safety
  const items = Array.isArray(data.items) ? data.items.filter(item => item !== null && item !== undefined) : [];

  return {
    items,
    pagination: data.pagination || {
      limit: data.limit,
      offset: data.offset,
      total: data.total || items.length,
      page: data.page,
      totalPages: data.totalPages,
      hasNext: data.hasNext,
      hasPrev: data.hasPrev,
    },
  };
};

/**
 * Safe data extraction with fallback
 * @param {object} response - axios/fetch response
 * @param {*} fallback - value to return if extraction fails
 * @returns {object|array|*} extracted data or fallback
 */
export const extractDataOrFallback = (response, fallback = null) => {
  try {
    return extractData(response);
  } catch (error) {
    console.warn('Failed to extract data, returning fallback:', error.message);
    return fallback;
  }
};

export default {
  extractData,
  extractPaginatedData,
  extractDataOrFallback,
};

