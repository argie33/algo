// UNIFIED API Response Format - Used by ALL endpoints
// Format: { success, data?, items?, pagination?, error?, timestamp }

module.exports = {
  // Standard success response
  sendSuccess: (res, data, statusCode = 200) => {
    res.status(statusCode).json({
      success: true,
      data: data || null,
      timestamp: new Date().toISOString()
    });
  },

  // Standard error response with optional detailed context
  sendError: (res, error, statusCode = 500, details = null) => {
    const errorMsg = typeof error === 'string' ? error : (error?.message || 'Internal server error');
    const response = {
      success: false,
      error: errorMsg,
      timestamp: new Date().toISOString()
    };

    // Include detailed error context in development mode
    if (process.env.NODE_ENV === 'development' && details) {
      response.details = details;
    }

    res.status(statusCode).json(response);
  },

  // Paginated list response - UNIFIED FORMAT
  // Returns: { success, items: [], pagination: {...}, timestamp }
  sendPaginated: (res, items, pagination, statusCode = 200) => {
    res.status(statusCode).json({
      success: true,
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

  // Not found response
  sendNotFound: (res, message = 'Resource not found') => {
    res.status(404).json({
      success: false,
      error: message,
      timestamp: new Date().toISOString()
    });
  },

  // Bad request response
  sendBadRequest: (res, error) => {
    const errorMsg = typeof error === 'string' ? error : (error?.message || 'Bad request');
    res.status(400).json({
      success: false,
      error: errorMsg,
      timestamp: new Date().toISOString()
    });
  },

  // Unauthorized response
  sendUnauthorized: (res, message = 'Unauthorized') => {
    res.status(401).json({
      success: false,
      error: message,
      timestamp: new Date().toISOString()
    });
  }
};
