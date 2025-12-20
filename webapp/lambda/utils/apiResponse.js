// Lean API Response Handlers - Proper wrapper format for frontend contract

module.exports = {
  sendSuccess: (res, data, statusCode = 200) => {
    res.status(statusCode).json({
      success: true,
      data: data,
      timestamp: new Date().toISOString()
    });
  },

  sendError: (res, error, statusCode = 500, message = null) => {
    res.status(statusCode).json({
      success: false,
      error: error,
      message: message || error,
      timestamp: new Date().toISOString()
    });
  }
};
