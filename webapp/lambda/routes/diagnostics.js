const express = require('express');
const responseFormatter = require('../utils/responseFormatter');

const router = express.Router();

// Basic health endpoint for diagnostics service
router.get('/health', (req, res) => {
  res.json(responseFormatter.success({
    status: 'operational',
    service: 'diagnostics',
    timestamp: new Date().toISOString(),
    message: 'Diagnostics service is running'
  }));
});

// System diagnostics endpoint
router.get('/system', (req, res) => {
  const systemInfo = {
    uptime: process.uptime(),
    memory: process.memoryUsage(),
    platform: process.platform,
    nodeVersion: process.version,
    environment: process.env.NODE_ENV || 'development',
    lambda: {
      functionName: process.env.AWS_LAMBDA_FUNCTION_NAME || 'local',
      functionVersion: process.env.AWS_LAMBDA_FUNCTION_VERSION || 'local',
      memorySize: process.env.AWS_LAMBDA_FUNCTION_MEMORY_SIZE || 'unknown',
      region: process.env.AWS_REGION || 'unknown'
    }
  };

  res.json(responseFormatter.success(systemInfo));
});

// Route diagnostics endpoint
router.get('/routes', (req, res) => {
  // This would be populated with actual route health data
  const routeHealth = {
    total: 26,
    healthy: 15,
    unhealthy: 11,
    status: 'partial',
    lastCheck: new Date().toISOString()
  };

  res.json(responseFormatter.success(routeHealth));
});

module.exports = router;