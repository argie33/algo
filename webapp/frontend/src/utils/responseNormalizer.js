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

  // Check for error responses first
  if (data.success === false) {
    const errorMsg = data.error || data.message || 'API request failed';
    const error = new Error(errorMsg);
    error.code = data.errorType;
    error.status = data.statusCode || response.status;
    error.details = {
      originalMessage: data.error || data.message,
      errorType: data.errorType,
      statusCode: data.statusCode || response.status,
      timestamp: data.timestamp,
      requestId: data.requestId,
      context: data.context,
    };
    throw error;
  }

  // Check HTTP status codes
  const httpStatus = data.statusCode !== undefined ? data.statusCode : response.status;
  if (httpStatus >= 400) {
    const errorMsg = data.message || data.error || `API error: ${httpStatus}`;
    const error = new Error(errorMsg);
    error.status = httpStatus;
    error.code = data.errorType;
    error.details = {
      originalMessage: data.message || data.error,
      errorType: data.errorType,
      statusCode: httpStatus,
      timestamp: data.timestamp,
      requestId: data.requestId,
      context: data.context,
    };
    throw error;
  }

  // Handle direct array responses (e.g., from async queryFn returning array)
  // CRITICAL: If data itself is an array, return it as-is or wrap it in an items property
  if (Array.isArray(data)) {
    return {
      items: data,
      pagination: {
        limit: data.length,
        offset: 0,
        total: data.length,
        page: 1,
        totalPages: 1,
        hasNext: false,
        hasPrev: false,
      },
      statusCode: httpStatus,
      success: true,
    };
  }

  // Handle paginated responses (items + pagination)
  // CRITICAL: Check that items is actually an array (not null/undefined)
  // Use Array.isArray alone (not && data.items) to handle empty arrays correctly
  if (Array.isArray(data.items)) {
    // Filter out null/undefined items, but preserve falsy values like 0, false, ""
    const filteredItems = data.items.filter(item => item !== null && item !== undefined);
    return {
      items: filteredItems,
      pagination: data.pagination || {
        limit: data.limit || 50,
        offset: data.offset || 0,
        total: data.total || filteredItems.length,
        page: data.page || 1,
        totalPages: data.totalPages || Math.ceil((data.total || filteredItems.length) / (data.limit || 50)),
        hasNext: data.hasNext !== undefined ? data.hasNext : false,
        hasPrev: data.hasPrev !== undefined ? data.hasPrev : false,
      },
      statusCode: httpStatus,
      success: true,
    };
  }

  // Handle single object responses (data field)
  if (data.data !== null && data.data !== undefined) {
    // If data.data is an array, wrap it in items property
    if (Array.isArray(data.data)) {
      return {
        items: data.data,
        pagination: {
          limit: data.data.length,
          offset: 0,
          total: data.data.length,
          page: 1,
          totalPages: 1,
          hasNext: false,
          hasPrev: false,
        },
        statusCode: httpStatus,
        success: true,
      };
    }
    // For objects, return the data directly without spreading
    // Spreading could mask the actual data structure or overwrite fields
    return {
      data: data.data,
      statusCode: httpStatus,
      success: true,
    };
  }

  // Fallback: return the whole data object with statusCode if it's an object
  // Error responses with success: false are already caught by the statusCode check above
  if (typeof data === 'object' && data !== null && !Array.isArray(data)) {
    return {
      ...data,
      statusCode: httpStatus,
      success: true,
    };
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

  // Check for error responses
  if (data.success === false) {
    const errorMsg = data.error || data.message || 'API request failed';
    const error = new Error(errorMsg);
    error.code = data.errorType;
    error.status = data.statusCode || response.status;
    throw error;
  }

  // Check HTTP status
  const httpStatus = data.statusCode !== undefined ? data.statusCode : response.status;
  if (httpStatus >= 400) {
    const error = new Error(data.message || data.error || `API error: ${httpStatus}`);
    error.code = data.errorType;
    error.status = httpStatus;
    throw error;
  }

  // Handle direct items (new standardized format)
  if (Array.isArray(data.items)) {
    // Filter out null/undefined items but preserve other falsy values (0, false, "")
    const items = data.items.filter(item => item !== null && item !== undefined);
    return {
      items,
      pagination: data.pagination || {
        limit: data.limit || 100,
        offset: data.offset || 0,
        total: data.total || items.length,
        page: data.page || 1,
        totalPages: data.totalPages || Math.ceil((data.total || items.length) / (data.limit || 100)),
        hasNext: data.hasNext !== undefined ? data.hasNext : false,
        hasPrev: data.hasPrev !== undefined ? data.hasPrev : false,
      },
    };
  }

  // Handle nested data.items (for backward compatibility)
  if (data.data && Array.isArray(data.data.items)) {
    // Filter out null/undefined items but preserve other falsy values (0, false, "")
    const items = data.data.items.filter(item => item !== null && item !== undefined);
    return {
      items,
      pagination: data.data.pagination || {
        limit: data.limit || 100,
        offset: data.offset || 0,
        total: data.total || items.length,
        page: data.page || 1,
        totalPages: data.totalPages || Math.ceil((data.total || items.length) / (data.limit || 100)),
        hasNext: data.hasNext !== undefined ? data.hasNext : false,
        hasPrev: data.hasPrev !== undefined ? data.hasPrev : false,
      },
    };
  }

  // Invalid response format: no items array found at expected paths
  const preview = JSON.stringify(data).substring(0, 200);
  throw new Error(`Unable to extract paginated data: response must contain 'items' array or 'data.items' array. Received: ${preview}`);
};

/**
 * Validate that required fields exist in data items
 * @param {array} items - Array of data items
 * @param {array} requiredFields - Fields that must exist (non-null/non-empty)
 * @returns {object} { valid: boolean, invalidItems: array, missingFields: Set }
 */
export const validateItems = (items, requiredFields = []) => {
  if (!Array.isArray(items)) {
    const msg = `[validateItems] Expected array but got ${typeof items}`;
    console.error(msg);
    return { valid: false, invalidItems: [], missingFields: new Set() };
  }

  if (requiredFields.length === 0) {
    return { valid: true, invalidItems: [], missingFields: new Set() };
  }

  const missingFields = new Set();
  const invalidItems = items
    .map((item, idx) => {
      if (!item || typeof item !== 'object') {
        return idx;
      }
      const missing = requiredFields.filter(field => {
        const value = item?.[field];
        return value === null || value === undefined || value === '';
      });
      missing.forEach(f => missingFields.add(f));
      return missing.length > 0 ? idx : null;
    })
    .filter(idx => idx !== null);

  if (invalidItems.length > 0) {
    console.warn(`[validateItems] ${invalidItems.length} of ${items.length} items missing required fields:`, [...missingFields].join(', '));
  }

  return {
    valid: invalidItems.length === 0,
    invalidItems,
    missingFields,
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

