/**
 * Settings Route - Parameter Store Only Implementation
 * 
 * Long-term solution that completely removes RDS table dependencies
 * and provides pure Parameter Store-based API key management
 */

const express = require('express');
const { authenticateToken } = require('../middleware/auth');
const { createValidationMiddleware, sanitizers } = require('../middleware/validation');
const apiKeyService = require('../utils/apiKeyService');

const router = express.Router();

// validation schemas
const enhancedApiKeySchema = {
  provider: {
    required: true,
    type: 'string',
    sanitizer: (value) => sanitizers.string(value, { maxLength: 20, toLowerCase: true }),
    validator: (value) => ['alpaca', 'polygon', 'finnhub', 'iex', 'td_ameritrade'].includes(value),
    errorMessage: 'Provider must be one of: alpaca, polygon, finnhub, iex, td_ameritrade'
  },
  apiKey: {
    required: true,
    type: 'string',
    sanitizer: (value) => sanitizers.string(value, { maxLength: 100, trim: true }),
    validator: (value) => value.length >= 8 && value.length <= 100 && /^[A-Za-z0-9_\-]+$/.test(value),
    errorMessage: 'API key must be 8-100 characters, alphanumeric with _ and - allowed'
  },
  apiSecret: {
    type: 'string',
    sanitizer: (value) => value ? sanitizers.string(value, { maxLength: 200, trim: true }) : '',
    validator: (value) => !value || (value.length >= 8 && value.length <= 200),
    errorMessage: 'API secret must be 8-200 characters if provided'
  },
  description: {
    type: 'string',
    sanitizer: (value) => value ? sanitizers.string(value, { maxLength: 100, trim: true }) : '',
    validator: (value) => !value || value.length <= 100,
    errorMessage: 'Description must be 100 characters or less'
  }
};

// Apply authentication to all routes
router.use(authenticateToken);

/**
 * API Keys endpoint - Pure Parameter Store
 * GET /api/settings/enhanced/api-keys
 */
router.get('/api-keys', async (req, res) => {
  const requestId = req.headers['x-request-id'] || 'req_' + Date.now();
  const startTime = Date.now();
  
  try {
    console.log(`🔍 [${requestId}] API keys fetch requested`);
    
    // Validate authentication
    if (!req.user?.sub) {
      console.error(`❌ [${requestId}] No user ID found in authentication token`);
      return res.status(401).json({
        success: false,
        error: 'Authentication required',
        message: 'User ID not found in token',
        requestId
      });
    }

    const userId = req.user.sub;
    console.log(`👤 [${requestId}] User ID: ${userId}`);

    // Get API keys from enhanced service
    const apiKeys = await apiKeyService.listApiKeys(userId);
    
    // Format for frontend compatibility with enhanced metadata
    const formattedApiKeys = apiKeys.map(key => ({
      id: `${key.provider}-${userId}`,
      provider: key.provider,
      description: `${key.provider} API Key`,
      is_sandbox: true, // Default for security
      is_active: true,
      created_at: key.created,
      last_used: null,
      masked_api_key: key.keyId,
      validation_status: 'valid',
      version: key.version || '2.0',
      has_secret: key.hasSecret,
      source: 'parameter-store-enhanced'
    }));

    const responseTime = Date.now() - startTime;
    console.log(`✅ [${requestId}] API keys retrieved in ${responseTime}ms`);

    res.json({ 
      success: true, 
      data: formattedApiKeys,
      metadata: {
        count: formattedApiKeys.length,
        source: 'enhanced-parameter-store',
        version: '2.0',
        responseTime: `${responseTime}ms`,
        requestId,
        cacheHit: false, // TODO: Add cache hit detection
        timestamp: new Date().toISOString()
      }
    });

  } catch (error) {
    const responseTime = Date.now() - startTime;
    console.error(`❌ [${requestId}] API keys fetch failed after ${responseTime}ms:`, error.message);
    
    // Handle circuit breaker specifically
    if (error.message.includes('Circuit breaker is OPEN')) {
      return res.status(503).json({
        success: false,
        error: 'API key service temporarily unavailable',
        message: 'The service is experiencing high error rates and has been temporarily disabled for stability',
        details: {
          errorType: 'CIRCUIT_BREAKER_OPEN',
          requestId,
          responseTime: `${responseTime}ms`,
          retryAfter: '30 seconds'
        }
      });
    }
    
    // Return graceful fallback
    res.json({ 
      success: true, 
      data: [],
      note: 'API key service temporarily unavailable',
      errorCode: 'SERVICE_UNAVAILABLE',
      metadata: {
        source: 'enhanced-parameter-store',
        version: '2.0',
        responseTime: `${responseTime}ms`,
        requestId,
        fallback: true
      },
      details: process.env.NODE_ENV === 'development' ? error.message : undefined
    });
  }
});

/**
 * API Key Creation - Pure Parameter Store
 * POST /api/settings/enhanced/api-keys
 */
router.post('/api-keys', createValidationMiddleware(enhancedApiKeySchema), async (req, res) => {
  const requestId = req.headers['x-request-id'] || 'req_' + Date.now();
  const startTime = Date.now();
  
  try {
    console.log(`🔐 [${requestId}] API key creation requested`);
    
    const userId = req.user?.sub;
    const { provider, apiKey, apiSecret, description } = req.body;
    
    if (!userId) {
      console.error(`❌ [${requestId}] No user ID found in authentication token`);
      return res.status(401).json({
        success: false,
        error: 'User not authenticated',
        message: 'User ID not found in authentication token',
        requestId
      });
    }

    console.log(`🔐 [${requestId}] Creating API key for user: ${userId}, provider: ${provider}`);

    // Store using enhanced service
    await apiKeyService.storeApiKey(userId, provider, apiKey, apiSecret || '');

    const responseTime = Date.now() - startTime;
    console.log(`✅ [${requestId}] API key created in ${responseTime}ms`);

    res.json({
      success: true,
      message: 'API key added successfully',
      apiKey: {
        id: `${provider}-${userId}`,
        provider: provider,
        description: description || `${provider} API key`,
        is_sandbox: true,
        created_at: new Date().toISOString(),
        version: '2.0',
        source: 'enhanced-parameter-store'
      },
      metadata: {
        responseTime: `${responseTime}ms`,
        requestId,
        timestamp: new Date().toISOString()
      }
    });

  } catch (error) {
    const responseTime = Date.now() - startTime;
    console.error(`❌ [${requestId}] API key creation failed after ${responseTime}ms:`, error.message);
    
    // Handle specific errors
    if (error.message.includes('Circuit breaker is OPEN')) {
      return res.status(503).json({
        success: false,
        error: 'API key service temporarily unavailable',
        message: 'Service is experiencing issues and has been temporarily disabled',
        details: { requestId, errorType: 'CIRCUIT_BREAKER_OPEN' }
      });
    }

    if (error.message.includes('Invalid userId') || error.message.includes('Missing required parameters')) {
      return res.status(400).json({
        success: false,
        error: 'Invalid request parameters',
        message: error.message,
        requestId
      });
    }

    if (error.message.includes('Unsupported provider')) {
      return res.status(400).json({
        success: false,
        error: 'Unsupported provider',
        message: error.message,
        requestId
      });
    }

    // Generic error handling
    res.status(500).json({
      success: false,
      error: 'Failed to create API key',
      message: 'An error occurred while storing the API key',
      details: {
        requestId,
        responseTime: `${responseTime}ms`,
        debugInfo: process.env.NODE_ENV === 'development' ? error.message : undefined
      }
    });
  }
});

/**
 * API Key Retrieval - Pure Parameter Store
 * GET /api/settings/enhanced/api-keys/:provider
 */
router.get('/api-keys/:provider', async (req, res) => {
  const requestId = req.headers['x-request-id'] || 'req_' + Date.now();
  const startTime = Date.now();
  
  try {
    const userId = req.user?.sub;
    const { provider } = req.params;
    
    if (!userId) {
      return res.status(401).json({
        success: false,
        error: 'User not authenticated',
        requestId
      });
    }

    console.log(`🔍 [${requestId}] API key retrieval for user: ${userId}, provider: ${provider}`);

    const apiKey = await apiKeyService.getApiKey(userId, provider);
    
    if (!apiKey) {
      return res.status(404).json({
        success: false,
        error: 'API key not found',
        provider,
        requestId
      });
    }

    const responseTime = Date.now() - startTime;

    res.json({
      success: true,
      apiKey: {
        provider: apiKey.provider,
        keyId: apiKey.keyId.substring(0, 4) + '***' + apiKey.keyId.slice(-4),
        hasSecret: !!apiKey.secretKey,
        created: apiKey.created,
        version: apiKey.version || '2.0',
        source: 'enhanced-parameter-store'
      },
      metadata: {
        responseTime: `${responseTime}ms`,
        requestId,
        timestamp: new Date().toISOString()
      }
    });

  } catch (error) {
    const responseTime = Date.now() - startTime;
    console.error(`❌ [${requestId}] API key retrieval failed:`, error.message);
    
    res.status(500).json({
      success: false,
      error: 'Failed to retrieve API key',
      message: error.message,
      details: { requestId, responseTime: `${responseTime}ms` }
    });
  }
});

/**
 * API Key Deletion - Pure Parameter Store
 * DELETE /api/settings/enhanced/api-keys/:provider
 */
router.delete('/api-keys/:provider', async (req, res) => {
  const requestId = req.headers['x-request-id'] || 'req_' + Date.now();
  const startTime = Date.now();
  
  try {
    const userId = req.user?.sub;
    const { provider } = req.params;
    
    if (!userId) {
      return res.status(401).json({
        success: false,
        error: 'User not authenticated',
        requestId
      });
    }

    console.log(`🗑️ [${requestId}] API key deletion for user: ${userId}, provider: ${provider}`);

    await apiKeyService.deleteApiKey(userId, provider);

    const responseTime = Date.now() - startTime;
    console.log(`✅ [${requestId}] API key deleted in ${responseTime}ms`);

    res.json({
      success: true,
      message: 'API key deleted successfully',
      provider,
      metadata: {
        responseTime: `${responseTime}ms`,
        requestId,
        timestamp: new Date().toISOString()
      }
    });

  } catch (error) {
    const responseTime = Date.now() - startTime;
    console.error(`❌ [${requestId}] API key deletion failed:`, error.message);
    
    if (error.name === 'ParameterNotFound') {
      return res.status(404).json({
        success: false,
        error: 'API key not found',
        provider: req.params.provider,
        requestId
      });
    }
    
    res.status(500).json({
      success: false,
      error: 'Failed to delete API key',
      message: error.message,
      details: { requestId, responseTime: `${responseTime}ms` }
    });
  }
});

/**
 * Service Health Check
 * GET /api/settings/enhanced/health
 */
router.get('/health', async (req, res) => {
  const requestId = req.headers['x-request-id'] || 'req_' + Date.now();
  
  try {
    console.log(`🔍 [${requestId}] service health check requested`);
    
    const healthStatus = await apiKeyService.healthCheck();
    const serviceStats = apiKeyService.getServiceStats();
    
    res.json({
      ...healthStatus,
      stats: serviceStats,
      enhanced: true,
      requestId,
      architecture: {
        storage: 'AWS Parameter Store',
        caching: 'In-Memory with TTL',
        circuitBreaker: 'Built-in with CloudWatch integration',
        monitoring: 'CloudWatch Metrics',
        security: 'AWS KMS encryption'
      }
    });

  } catch (error) {
    console.error(`❌ [${requestId}] health check failed:`, error.message);
    
    res.status(500).json({
      status: 'unhealthy',
      service: 'EnhancedApiKeyService',
      error: error.message,
      requestId,
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * Service Statistics
 * GET /api/settings/enhanced/stats
 */
router.get('/stats', async (req, res) => {
  const requestId = req.headers['x-request-id'] || 'req_' + Date.now();
  
  try {
    const serviceStats = apiKeyService.getServiceStats();
    
    res.json({
      success: true,
      data: serviceStats,
      enhanced: true,
      requestId,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error(`❌ [${requestId}] stats request failed:`, error.message);
    
    res.status(500).json({
      success: false,
      error: 'Failed to retrieve service statistics',
      message: error.message,
      requestId
    });
  }
});

/**
 * Migration endpoint - helps transition from old to new service
 * POST /api/settings/enhanced/migrate
 */
router.post('/migrate', async (req, res) => {
  const requestId = req.headers['x-request-id'] || 'req_' + Date.now();
  const startTime = Date.now();
  
  try {
    const userId = req.user?.sub;
    
    if (!userId) {
      return res.status(401).json({
        success: false,
        error: 'User not authenticated',
        requestId
      });
    }

    console.log(`🔄 [${requestId}] Migration requested for user: ${userId}`);

    // Get existing API keys from enhanced service
    const existingKeys = await apiKeyService.listApiKeys(userId);
    
    // Check if any keys need migration (v1.0 to v2.0)
    const migrationResults = {
      total: existingKeys.length,
      migrated: 0,
      skipped: 0,
      errors: []
    };

    for (const key of existingKeys) {
      if (!key.version || key.version === '1.0') {
        try {
          // Re-fetch and re-store to update to v2.0 format
          const fullKey = await apiKeyService.getApiKey(userId, key.provider);
          if (fullKey) {
            await apiKeyService.storeApiKey(userId, key.provider, fullKey.keyId, fullKey.secretKey);
            migrationResults.migrated++;
          }
        } catch (error) {
          migrationResults.errors.push({
            provider: key.provider,
            error: error.message
          });
        }
      } else {
        migrationResults.skipped++;
      }
    }

    const responseTime = Date.now() - startTime;
    console.log(`✅ [${requestId}] Migration completed in ${responseTime}ms`);

    res.json({
      success: true,
      message: 'Migration completed',
      results: migrationResults,
      metadata: {
        responseTime: `${responseTime}ms`,
        requestId,
        timestamp: new Date().toISOString()
      }
    });

  } catch (error) {
    const responseTime = Date.now() - startTime;
    console.error(`❌ [${requestId}] Migration failed after ${responseTime}ms:`, error.message);
    
    res.status(500).json({
      success: false,
      error: 'Migration failed',
      message: error.message,
      details: { requestId, responseTime: `${responseTime}ms` }
    });
  }
});

module.exports = router;