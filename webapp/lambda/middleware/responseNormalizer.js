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
    // If already normalized, just send it
    if (body?.success !== undefined && body?.timestamp) {
      console.log(`✅ Response already normalized, passing through:`, {
        path: req.path,
        hasSuccess: body?.success !== undefined,
        hasTimestamp: !!body?.timestamp,
        hasItems: Array.isArray(body?.items),
        hasPagination: !!body?.pagination
      });
      return originalJson.call(this, body);
    }

    // Normalize the response
    console.log(`🔄 Normalizing response for ${req.path}:`, {
      receivedKeys: Object.keys(body || {}),
      statusCode: res.statusCode
    });
    const normalized = normalizeResponse(body, res.statusCode);
    console.log(`📤 Normalized response:`, {
      path: req.path,
      resultKeys: Object.keys(normalized)
    });
    return originalJson.call(this, normalized);
  };

  next();
};

/**
 * Normalize any response format to our standard
 */
function normalizeResponse(body, statusCode) {
  // If it's already properly formatted, return as-is
  if (body?.success !== undefined && body?.timestamp) {
    return body;
  }

  // Determine if this is an error
  const isError = statusCode >= 400;

  // If it's a list/paginated response
  if (Array.isArray(body?.items) || (body?.items && !body?.success)) {
    return {
      success: !isError,
      items: body.items || [],
      pagination: body.pagination || normalizePagination(body),
      error: isError ? (body.error || 'Request failed') : null,
      timestamp: new Date().toISOString()
    };
  }

  // If it has pagination but items under different key
  if (body?.pagination && !body?.items) {
    const items = body.data || body.results || [];
    return {
      success: !isError,
      items: Array.isArray(items) ? items : [items],
      pagination: body.pagination,
      error: isError ? (body.error || 'Request failed') : null,
      timestamp: new Date().toISOString()
    };
  }

  // Single object response
  if (body?.data && !body?.success && !Array.isArray(body.data)) {
    return {
      success: !isError,
      data: body.data,
      error: isError ? (body.error || 'Request failed') : null,
      timestamp: new Date().toISOString()
    };
  }

  // Error response
  if (body?.error || isError) {
    return {
      success: false,
      error: body?.error || body?.message || 'Request failed',
      timestamp: new Date().toISOString()
    };
  }

  // Default: wrap in data
  return {
    success: !isError,
    data: body || null,
    timestamp: new Date().toISOString()
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
