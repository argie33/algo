/**
 * Standardize API response handling across all pages
 * Single function to extract data regardless of response shape
 */

/**
 * Extract data from API response
 * Handles multiple response formats:
 * - { success: true, data: {...}, items: [...] }
 * - { success: true, data: { items: [...] } }
 * - { success: true, items: [...] }
 * - { success: true, data: {...} }
 *
 * @param {object} response - axios/fetch response
 * @returns {object|array} the extracted data
 * @throws {Error} if response structure is unexpected
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

  // If success is false, throw error
  if (data.success === false) {
    throw new Error(data.message || 'API request failed');
  }

  // Priority order for extracting data:
  // 1. data.items (most common paginated response)
  if (data.items) {
    return data.items;
  }

  // 2. data.data (nested structure)
  if (data.data) {
    // Check if data.data has items (double-nested)
    if (data.data.items) {
      return data.data.items;
    }
    // Return the data object itself
    return data.data;
  }

  // 3. The whole data object (if no items/data field)
  if (typeof data === 'object' && data !== null) {
    return data;
  }

  throw new Error(`Unable to extract data from response: ${JSON.stringify(data).substring(0, 100)}`);
};

/**
 * Extract paginated response with metadata
 * @param {object} response - axios/fetch response
 * @returns {object} { items: [...], pagination: {...} }
 */
export const extractPaginatedData = (response) => {
  const data = response.data || response;

  return {
    items: extractData(response),
    pagination: data.pagination || {
      limit: data.limit,
      offset: data.offset,
      total: data.total,
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
