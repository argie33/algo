const express = require('express');
const router = express.Router();

// API keys endpoint that frontend expects
router.get('/api-keys', async (req, res) => {
  try {
    // For now, return empty array to prevent 404
    res.json({
      success: true,
      data: [],
      message: 'Portfolio API keys endpoint available (returning empty for now)'
    });
  } catch (error) {
    console.error('Portfolio API keys error:', error);
    res.status(500).json({
      success: false,
      error: 'Internal server error',
      message: error.message
    });
  }
});

// Basic portfolio health endpoint
router.get('/health', (req, res) => {
  res.json({
    success: true,
    service: 'Portfolio API', 
    status: 'healthy',
    timestamp: new Date().toISOString()
  });
});

// Portfolio calculation endpoint that frontend expects
router.post('/calculate-var', async (req, res) => {
  try {
    // Return demo calculation to prevent 404
    res.json({
      success: true,
      data: {
        var: 0.05,
        confidence: 0.95,
        message: 'Demo VaR calculation'
      }
    });
  } catch (error) {
    console.error('Portfolio VaR calculation error:', error);
    res.status(500).json({
      success: false,
      error: 'Internal server error',
      message: error.message
    });
  }
});

module.exports = router;