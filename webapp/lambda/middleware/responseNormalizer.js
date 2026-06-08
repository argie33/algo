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

  // Paginated list with data key (convert to items)
  if (body?.pagination && !body?.items) {
    const itemsSource = body.data || body.results || [];
    // Check if extracted items contain an error object (e.g., nested { success: false })
    if (typeof itemsSource === 'object' && itemsSource !== null && itemsSource.success === false) {
      return {
        success: false,
        statusCode: body.statusCode || 500,
        error: itemsSource.error || itemsSource.message || 'Request failed',
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

  // Fallback: if no data/items structure, wrap body as data
  // This handles legacy responses that don't follow the standard format
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
    const itemsSource = body.data || body.results || [];
    // Check if extracted items contain an error object (e.g., nested { success: false })
    if (typeof itemsSource === 'object' && itemsSource !== null && itemsSource.success === false) {
      return {
        success: false,
        statusCode: statusCode,
        error: itemsSource.error || itemsSource.message || 'Request failed',
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

  // Default: wrap in data
  return {
    success: !isError,
    statusCode: statusCode,
    data: body || null,
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
