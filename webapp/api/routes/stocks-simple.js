const express = require('express');

const router = express.Router();

// Health endpoint
router.get('/health', (req, res) => {
  res.json({
    success: true,
    status: 'operational',
    service: 'Stocks',
    timestamp: new Date().toISOString(),
    message: 'Stocks service is running'
  });
});

// Root endpoint  
router.get('/', (req, res) => {
  res.json({
    success: true,
    message: 'Stocks API - Ready',
    timestamp: new Date().toISOString(),
    status: 'operational',
    available_endpoints: ['/sectors', '/search', '/profile', '/health'],
    service: 'Stocks',
    note: 'Authentication required for full functionality'
  });
});

// Status endpoint
router.get('/status', (req, res) => {
  res.json({
    success: true,
    service: 'Stocks',
    status: 'operational',
    uptime: process.uptime(),
    memory: {
      used: Math.round(process.memoryUsage().heapUsed / 1024 / 1024),
      total: Math.round(process.memoryUsage().heapTotal / 1024 / 1024)
    },
    timestamp: new Date().toISOString()
  });
});

module.exports = router;