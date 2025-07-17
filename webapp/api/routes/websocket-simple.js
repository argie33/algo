const express = require('express');

const router = express.Router();

// Health endpoint
router.get('/health', (req, res) => {
  res.json({
    success: true,
    status: 'operational',
    service: 'WebSocket',
    timestamp: new Date().toISOString(),
    message: 'WebSocket service is running',
    type: 'http_polling_realtime_data'
  });
});

// Root endpoint  
router.get('/', (req, res) => {
  res.json({
    success: true,
    message: 'WebSocket API - Ready',
    timestamp: new Date().toISOString(),
    status: 'operational',
    available_endpoints: ['/status', '/stream', '/subscriptions', '/health'],
    service: 'WebSocket'
  });
});

// Status endpoint
router.get('/status', (req, res) => {
  res.json({
    success: true,
    service: 'WebSocket',
    status: 'operational',
    activeUsers: 0,
    cachedSymbols: 0,
    serverTime: new Date().toISOString(),
    uptime: process.uptime(),
    timestamp: new Date().toISOString()
  });
});

module.exports = router;