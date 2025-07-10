const express = require('express');
const { healthCheck } = require('../utils/database');

const router = express.Router();

// Simple robust health check endpoint
router.get('/', async (req, res) => {
  try {
    // Quick health check without database
    if (req.query.quick === 'true') {
      return res.json({
        status: 'healthy',
        healthy: true,
        service: 'Financial Dashboard API',
        timestamp: new Date().toISOString(),
        environment: process.env.ENVIRONMENT || 'dev',
        memory: process.memoryUsage(),
        uptime: process.uptime(),
        note: 'Quick health check - database not tested',
        database: { status: 'not_tested' },
        api: { version: '1.0.0', environment: process.env.ENVIRONMENT || 'dev' },
        config: {
          hasDbSecret: !!process.env.DB_SECRET_ARN,
          hasDbEndpoint: !!process.env.DB_ENDPOINT,
          hasAwsRegion: !!process.env.AWS_REGION
        }
      });
    }

    // Full health check with database
    const dbHealth = await healthCheck();
    const isHealthy = dbHealth.status === 'healthy';

    return res.status(isHealthy ? 200 : 503).json({
      status: isHealthy ? 'healthy' : 'unhealthy',
      healthy: isHealthy,
      service: 'Financial Dashboard API',
      timestamp: new Date().toISOString(),
      environment: process.env.ENVIRONMENT || 'dev',
      database: dbHealth,
      api: { version: '1.0.0', environment: process.env.ENVIRONMENT || 'dev' },
      memory: process.memoryUsage(),
      uptime: process.uptime()
    });

  } catch (error) {
    console.error('Health check failed:', error);
    res.status(503).json({
      status: 'unhealthy',
      healthy: false,
      timestamp: new Date().toISOString(),
      error: error.message,
      database: { status: 'error', error: error.message },
      api: { version: '1.0.0', environment: process.env.ENVIRONMENT || 'dev' },
      memory: process.memoryUsage(),
      uptime: process.uptime()
    });
  }
});

module.exports = router;