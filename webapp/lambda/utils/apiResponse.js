// UNIFIED API Response Format - Used by ALL endpoints
// CRITICAL: All responses must be consistent for frontend. NO exceptions.
// - Single object: { success: true, data: {...} }
// - Array/paginated: { success: true, items: [...], pagination: {...} }
// - Never wrap in extra "data" key. Never use raw res.json().

module.exports = {
  // Single object response (wrapped in "data" key for consistency)
  sendData: (res, data, statusCode = 200) => {
    return res.status(statusCode).json({
      success: true,
      statusCode: statusCode,
      data: data,
      timestamp: new Date().toISOString()
    });
  },

  // Standard success response - intelligently handles different data types
  sendSuccess: (res, data, statusCode = 200) => {
    // If data is an array, return as paginated response
    if (Array.isArray(data)) {
      return res.status(statusCode).json({
        success: true,
        statusCode: statusCode,
        items: data,
        pagination: {
          limit: data.length,
          offset: 0,
          total: data.length,
          page: 1,
          totalPages: 1,
          hasNext: false,
          hasPrev: false
        },
        timestamp: new Date().toISOString()
      });
    }

    // For objects, wrap under "data" key for consistent envelope
    return res.status(statusCode).json({
      success: true,
      statusCode: statusCode,
      data: data,
      timestamp: new Date().toISOString()
    });
  },

  // Standard error response with optional detailed context
  // Format: { success: false, statusCode, error: "code", message: "details", timestamp }
  sendError: (res, error, statusCode = 500, details = null) => {
    let errorMsg = typeof error === 'string' ? error : (error?.message || 'Internal server error');

    // Sanitize error messages in production (don't leak internal details)
    let sanitized = errorMsg;
    let errorCode = 'error';

    if (process.env.NODE_ENV === 'production' && statusCode === 500) {
      const sensitivePatterns = [
        { pattern: /ENOENT|EACCES|permission denied/i, code: 'permission_error' },
        { pattern: /column|table|database|schema/i, code: 'database_error' },
        { pattern: /connection|timeout|ECONNREFUSED/i, code: 'connection_error' },
        { pattern: /password|secret|token|api[_-]key/i, code: 'security_error' },
        { pattern: /\/[a-z]/i, code: 'system_error' }
      ];

      const matched = sensitivePatterns.find(p => p.pattern.test(errorMsg));
      if (matched) {
        errorCode = matched.code;
        sanitized = 'An error occurred processing your request';
      }
    }

    // Map HTTP status to error code if not already set
    if (statusCode === 400) errorCode = 'bad_request';
    else if (statusCode === 401) errorCode = 'unauthorized';
    else if (statusCode === 403) errorCode = 'forbidden';
    else if (statusCode === 404) errorCode = 'not_found';
    else if (statusCode === 409) errorCode = 'conflict';
    else if (statusCode === 429) errorCode = 'rate_limited';
    else if (statusCode === 500) errorCode = 'internal_error';
    else if (statusCode === 503) errorCode = 'service_unavailable';

    const response = {
      success: false,
      statusCode: statusCode,
      error: errorCode,
      message: sanitized,
      timestamp: new Date().toISOString()
    };

    // Include detailed error context in development mode
    if (process.env.NODE_ENV === 'development' && details) {
      response.details = details;
    }

    return res.status(statusCode).json(response);
  },

  // Paginated list response - UNIFIED FORMAT
  // Returns: { success, statusCode, items: [], pagination: {...}, timestamp }
  sendPaginated: (res, items, pagination, statusCode = 200) => {
    return res.status(statusCode).json({
      success: true,
      statusCode: statusCode,
      items: items || [],
      pagination: {
        limit: pagination?.limit || 100,
        offset: pagination?.offset || 0,
        total: pagination?.total || 0,
        page: pagination?.page || 1,
        totalPages: pagination?.totalPages || Math.ceil((pagination?.total || 0) / (pagination?.limit || 1)),
        hasNext: (pagination?.offset || 0) + (pagination?.limit || 0) < (pagination?.total || 0),
        hasPrev: (pagination?.offset || 0) > 0
      },
      timestamp: new Date().toISOString()
    });
  },

  // Simple list response (no pagination, just items)
  // Returns: { success, statusCode, items: [], timestamp }
  sendList: (res, items, statusCode = 200) => {
    return res.status(statusCode).json({
      success: true,
      statusCode: statusCode,
      items: items || [],
      timestamp: new Date().toISOString()
    });
  },

  // Not found response
  sendNotFound: (res, message = 'Resource not found') => {
    return res.status(404).json({
      success: false,
      statusCode: 404,
      error: 'not_found',
      message: message,
      timestamp: new Date().toISOString()
    });
  },

  // Bad request response
  sendBadRequest: (res, error) => {
    const errorMsg = typeof error === 'string' ? error : (error?.message || 'Bad request');
    return res.status(400).json({
      success: false,
      statusCode: 400,
      error: 'bad_request',
      message: errorMsg,
      timestamp: new Date().toISOString()
    });
  },

  // Unauthorized response
  sendUnauthorized: (res, message = 'Unauthorized') => {
    return res.status(401).json({
      success: false,
      statusCode: 401,
      error: 'unauthorized',
      message: message,
      timestamp: new Date().toISOString()
    });
  }
};
