/**
 * Debug version of unified API keys route
 * Simple route without dependencies to test basic functionality
 */

const express = require('express');
const router = express.Router();

/**
 * Simple health check without dependencies
 */
router.get('/health', async (req, res) => {
  try {
    // Test if we can load the unified service
    let serviceStatus = 'unknown';
    let serviceError = null;
    
    try {
      const unifiedApiKeyService = require('../utils/unifiedApiKeyService');
      serviceStatus = 'loaded';
    } catch (error) {
      serviceStatus = 'failed';
      serviceError = error.message;
    }
    
    res.json({
      success: true,
      service: 'unified-api-keys-debug',
      status: 'healthy',
      diagnostics: {
        unifiedService: serviceStatus,
        error: serviceError,
        timestamp: new Date().toISOString()
      }
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: 'Debug endpoint failed',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * Test endpoint without authentication
 */
router.get('/test', async (req, res) => {
  res.json({
    success: true,
    message: 'Unified API Keys debug route is working',
    timestamp: new Date().toISOString()
  });
});

module.exports = router;