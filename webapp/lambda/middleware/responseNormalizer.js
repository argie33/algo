/**
 * Response Normalizer Middleware
 *
 * Intercepts ALL responses and normalizes them to our standard format,
 * even if routes use raw res.json() instead of the helpers.
 *
 * This is a safety net that ensures responses are always consistent.
 */

module.exports = (req, res, next) => {
  const originalJson = res.json.bind(res);

  // Override res.json to normalize all responses
  res.json = function(body) {
    // If already properly formatted by sendSuccess/sendError, just send it
    // Properly formatted = has success flag, statusCode, and timestamp
    if (body?.success !== undefined && body?.statusCode !== undefined && body?.timestamp) {
      return originalJson.call(this, body);
    }

    // If has success flag but missing statusCode/timestamp, normalize it
    if (body?.success !== undefined) {
      const normalized = normalizeSuccessResponse(body, res.statusCode);
      return originalJson.call(this, normalized);
    }

    // Fallback: normalize any response without success flag
    const normalized = normalizeResponse(body, res.statusCode);
    return originalJson.call(this, normalized);
  };

  next();
};

/**
 * Normalize responses that already have success flag but are missing statusCode/timestamp
 */
function normalizeSuccessResponse(body, httpStatusCode) {
  const timestamp = new Date().toISOString();
  const statusCode = body.statusCode || httpStatusCode || 200;

  // Error response (success: false)
  if (body.success === false) {
    return {
      success: false,
      statusCode: body.statusCode || httpStatusCode || 500,
      error: body.error || body.message || 'Request failed',
      timestamp
    };
  }

  // Paginated list with items key
  if (Array.isArray(body?.items)) {
    return {
      success: true,
      statusCode: statusCode,
      items: body.items,
      pagination: body.pagination || normalizePagination(body),
      timestamp
    };
  }

  // Paginated list with custom key (signals, patterns, results, data, etc.)
  if (body?.pagination && !body?.items) {
    // Look for array data in common keys: data, results, signals, patterns, records, etc.
    let itemsSource = body.data || body.results || body.signals || body.patterns || body.records || [];

    // Check if extracted items contain an error object (e.g., nested { success: false })
    if (typeof itemsSource === 'object' && itemsSource !== null && itemsSource.success === false) {
      return {
        success: false,
        statusCode: body.statusCode || 500,
        error: itemsSource.error || itemsSource.message || 'Request failed',
        timestamp
      };
    }

    // If nothing found in common keys, return body as-is with pagination preserved
    // (it might use a custom key or have data at a different level)
    if (!itemsSource || itemsSource.length === 0) {
      return {
        success: true,
        statusCode: statusCode,
        ...body,  // Preserve all properties
        timestamp
      };
    }

    const items = Array.isArray(itemsSource) ? itemsSource : [];
    return {
      success: true,
      statusCode: statusCode,
      items: items,
      pagination: body.pagination,
      timestamp
    };
  }

  // Single object response - should have data key
  if (body.data !== undefined) {
    return {
      success: true,
      statusCode: statusCode,
      data: body.data,
      timestamp
    };
  }

  // Fallback: if no data/items structure detected, check for other array keys first
  // to avoid losing data from responses with custom array keys
  const arrayKeys = ['signals', 'patterns', 'records', 'results', 'transactions'];
  for (const key of arrayKeys) {
    if (Array.isArray(body?.[key])) {
      // Return as-is to preserve the custom key structure
      return {
        success: true,
        statusCode: statusCode,
        ...body,
        timestamp
      };
    }
  }

  // Finally, wrap non-standard responses in data
  return {
    success: true,
    statusCode: statusCode,
    data: body,
    timestamp
  };
}

/**
 * Normalize any response format to our standard
 */
function normalizeResponse(body, statusCode) {
  // If it's already properly formatted, return as-is
  if (body?.success !== undefined && body?.statusCode !== undefined && body?.timestamp) {
    return body;
  }

  const timestamp = new Date().toISOString();
  const isError = statusCode >= 400;

  // If it's a list/paginated response
  if (Array.isArray(body?.items) || (body?.items && !body?.success)) {
    return {
      success: !isError,
      statusCode: statusCode,
      items: body.items || [],
      pagination: body.pagination || normalizePagination(body),
      error: isError ? (body.error || 'Request failed') : null,
      timestamp
    };
  }

  // If it has pagination but items under different key
  if (body?.pagination && !body?.items) {
    // Look for array data in common keys: data, results, signals, patterns, records, etc.
    let itemsSource = body.data || body.results || body.signals || body.patterns || body.records || [];

    // Check if extracted items contain an error object (e.g., nested { success: false })
    if (typeof itemsSource === 'object' && itemsSource !== null && itemsSource.success === false) {
      return {
        success: false,
        statusCode: statusCode,
        error: itemsSource.error || itemsSource.message || 'Request failed',
        timestamp
      };
    }

    // If nothing found in common keys, return body as-is with pagination preserved
    if (!itemsSource || itemsSource.length === 0) {
      return {
        success: !isError,
        statusCode: statusCode,
        ...body,  // Preserve all properties including custom keys
        error: isError ? (body.error || 'Request failed') : null,
        timestamp
      };
    }

    const items = Array.isArray(itemsSource) ? itemsSource : [];
    return {
      success: !isError,
      statusCode: statusCode,
      items: items,
      pagination: body.pagination,
      error: isError ? (body.error || 'Request failed') : null,
      timestamp
    };
  }

  // Single object response (including falsy values like 0, false, "")
  if ('data' in body && !body?.success && !Array.isArray(body.data)) {
    return {
      success: !isError,
      statusCode: statusCode,
      data: body.data,
      error: isError ? (body.error || 'Request failed') : null,
      timestamp
    };
  }

  // Error response
  if (body?.error || isError) {
    return {
      success: false,
      statusCode: statusCode,
      error: body?.error || body?.message || 'Request failed',
      timestamp
    };
  }

  // Before wrapping in data, check for responses with custom array keys (signals, patterns, etc.)
  // to preserve their structure instead of losing them in a data wrapper
  const customArrayKeys = ['signals', 'patterns', 'records', 'results', 'transactions', 'events'];
  for (const key of customArrayKeys) {
    if (Array.isArray(body?.[key])) {
      // Return as-is to preserve the custom key structure
      return {
        success: !isError,
        statusCode: statusCode,
        ...body,
        error: isError ? (body.error || 'Request failed') : null,
        timestamp
      };
    }
  }

  // Default: wrap truly unstructured responses in data
  return {
    success: !isError,
    statusCode: statusCode,
    data: body || null,
    error: isError ? (body.error || 'Request failed') : null,
    timestamp
  };
}

/**
 * Extract pagination info from various response formats
 */
function normalizePagination(body) {
  if (body?.pagination) {
    return body.pagination;
  }

  return {
    limit: body?.limit || 100,
    offset: body?.offset || 0,
    total: body?.total || 0,
    page: body?.page || 1,
    hasNext: false,
    hasPrev: false
  };
}
