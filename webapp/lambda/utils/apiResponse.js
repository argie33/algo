// Canonical API Response Handlers - Single format across all endpoints
// Matches TypeScript type: { success: boolean, data?: T, error?: string, timestamp: ISO }

module.exports = {
  sendSuccess: (res, data, statusCode = 200) => {
    res.status(statusCode).json({
      success: true,
      data: data,
      timestamp: new Date().toISOString()
    });
  },

  sendError: (res, error, statusCode = 500) => {
    const errorMsg = typeof error === 'string' ? error : (error?.message || 'Internal server error');
    res.status(statusCode).json({
      success: false,
      error: errorMsg,
      timestamp: new Date().toISOString()
    });
  },

  sendPaginated: (res, items, pagination) => {
    res.status(200).json({
      success: true,
      data: {
        items: items
      },
      pagination: pagination,
      timestamp: new Date().toISOString()
    });
  }
};
