const express = require('express');

const router = express.Router();

// Health endpoint
router.get('/health', (req, res) => {
  res.json({
    success: true,
    status: 'operational',
    service: 'Stock Screener',
    timestamp: new Date().toISOString(),
    message: 'Stock Screener service is running'
  });
});

// Root endpoint  
router.get('/', (req, res) => {
  res.json({
    success: true,
    message: 'Stock Screener API - Ready',
    timestamp: new Date().toISOString(),
    status: 'operational',
    available_endpoints: ['/screen', '/criteria', '/presets', '/health'],
    service: 'Stock Screener'
  });
});

// Status endpoint
router.get('/status', (req, res) => {
  res.json({
    success: true,
    service: 'Stock Screener',
    status: 'operational',
    uptime: process.uptime(),
    timestamp: new Date().toISOString()
  });
});

module.exports = router;