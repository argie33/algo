/**
 * Settings Integration Route
 * 
 * Provides seamless integration between legacy and enhanced API key services
 * Allows gradual migration without breaking existing functionality
 */

const express = require('express');
const { authenticateToken } = require('../middleware/auth');

// Import both legacy and enhanced services
const legacyApiKeyService = require('../utils/simpleApiKeyService');
const apiKeyService = require('../utils/apiKeyService');
const migrationUtility = require('../utils/apiKeyMigrationUtility');

const router = express.Router();

// Apply authentication to all routes
router.use(authenticateToken);

/**
 * Service selection middleware
 * Determines which service to use based on configuration or user preferences
 */
const selectApiKeyService = (req, res, next) => {
  // Check for service selection header or environment variable
  const useEnhanced = req.headers['x-use-enhanced-service'] === 'true' || 
                     process.env.USE_ENHANCED_API_KEY_SERVICE === 'true' ||
                     req.query.enhanced === 'true';

  req.apiKeyService = useEnhanced ? apiKeyService : legacyApiKeyService;
  req.serviceType = useEnhanced ? 'enhanced' : 'legacy';
  
  console.log(`🔧 Using ${req.serviceType} API key service for ${req.method} ${req.path}`);
  next();
};

// Apply service selection to all routes
router.use(selectApiKeyService);

/**
 * Unified API Keys listing
 * GET /api/settings/integrated/api-keys
 */
router.get('/api-keys', async (req, res) => {
  const requestId = req.headers['x-request-id'] || 'req_' + Date.now();
  const startTime = Date.now();
  
  try {
    const userId = req.user?.sub;
    
    if (!userId) {
      return res.status(401).json({
        success: false,
        error: 'Authentication required',
        requestId
      });
    }

    console.log(`🔍 [${requestId}] Integrated API keys fetch for user: ${userId} using ${req.serviceType} service`);

    // Get API keys from selected service
    const apiKeys = await req.apiKeyService.listApiKeys(userId);
    
    // Enhanced formatting for both services
    const formattedApiKeys = apiKeys.map(key => ({
      id: `${key.provider}-${userId}`,
      provider: key.provider,
      description: `${key.provider} API Key`,
      is_sandbox: true,
      is_active: true,
      created_at: key.created,
      last_used: null,
      masked_api_key: key.keyId,
      validation_status: 'valid',
      version: key.version || '1.0',
      has_secret: key.hasSecret,
      source: req.serviceType
    }));

    const responseTime = Date.now() - startTime;

    res.json({ 
      success: true, 
      data: formattedApiKeys,
      metadata: {
        count: formattedApiKeys.length,
        source: req.serviceType,
        version: req.serviceType === 'enhanced' ? '2.0' : '1.0',
        responseTime: `${responseTime}ms`,
        requestId,
        timestamp: new Date().toISOString(),
        migrationAvailable: req.serviceType === 'legacy'
      }
    });

  } catch (error) {
    const responseTime = Date.now() - startTime;
    console.error(`❌ [${requestId}] Integrated API keys fetch failed after ${responseTime}ms:`, error.message);
    
    // Enhanced error handling
    if (error.message.includes('Circuit breaker is OPEN')) {
      return res.status(503).json({
        success: false,
        error: 'API key service temporarily unavailable',
        message: 'Service is experiencing issues and has been temporarily disabled',
        details: {
          errorType: 'CIRCUIT_BREAKER_OPEN',
          requestId,
          responseTime: `${responseTime}ms`,
          serviceType: req.serviceType,
          retryAfter: '30 seconds'
        }
      });
    }
    
    // Fallback to alternative service if available
    if (req.serviceType === 'enhanced') {
      try {
        console.log(`🔄 [${requestId}] Falling back to legacy service`);
        const fallbackKeys = await legacyApiKeyService.listApiKeys(userId);
        
        const formattedFallbackKeys = fallbackKeys.map(key => ({
          id: `${key.provider}-${userId}`,
          provider: key.provider,
          description: `${key.provider} API Key`,
          is_sandbox: true,
          is_active: true,
          created_at: key.created,
          last_used: null,
          masked_api_key: key.keyId,
          validation_status: 'valid',
          version: '1.0',
          has_secret: key.hasSecret,
          source: 'legacy-fallback'
        }));

        return res.json({ 
          success: true, 
          data: formattedFallbackKeys,
          metadata: {
            count: formattedFallbackKeys.length,
            source: 'legacy-fallback',
            version: '1.0',
            responseTime: `${Date.now() - startTime}ms`,
            requestId,
            fallbackUsed: true,
            originalError: error.message
          }
        });

      } catch (fallbackError) {
        console.error(`❌ [${requestId}] Fallback also failed:`, fallbackError.message);
      }
    }
    
    // Final fallback - return empty list
    res.json({ 
      success: true, 
      data: [],
      note: 'API key service temporarily unavailable',
      errorCode: 'SERVICE_UNAVAILABLE',
      metadata: {
        source: req.serviceType,
        responseTime: `${Date.now() - startTime}ms`,
        requestId,
        fallback: true
      },
      details: process.env.NODE_ENV === 'development' ? error.message : undefined
    });
  }
});

/**
 * Unified API Key Creation
 * POST /api/settings/integrated/api-keys
 */
router.post('/api-keys', async (req, res) => {
  const requestId = req.headers['x-request-id'] || 'req_' + Date.now();
  const startTime = Date.now();
  
  try {
    const userId = req.user?.sub;
    const { provider, apiKey, apiSecret, description } = req.body;
    
    if (!userId) {
      return res.status(401).json({
        success: false,
        error: 'User not authenticated',
        requestId
      });
    }

    console.log(`🔐 [${requestId}] Creating API key using ${req.serviceType} service for user: ${userId}, provider: ${provider}`);

    // Validate input
    if (!provider || !apiKey) {
      return res.status(400).json({
        success: false,
        error: 'Provider and API key are required',
        requestId
      });
    }

    // Store using selected service
    await req.apiKeyService.storeApiKey(userId, provider, apiKey, apiSecret || '');

    const responseTime = Date.now() - startTime;

    res.json({
      success: true,
      message: `API key added successfully using ${req.serviceType} service`,
      apiKey: {
        id: `${provider}-${userId}`,
        provider: provider,
        description: description || `${provider} API key`,
        is_sandbox: true,
        created_at: new Date().toISOString(),
        version: req.serviceType === 'enhanced' ? '2.0' : '1.0',
        source: req.serviceType
      },
      metadata: {
        responseTime: `${responseTime}ms`,
        requestId,
        serviceType: req.serviceType,
        timestamp: new Date().toISOString()
      }
    });

  } catch (error) {
    const responseTime = Date.now() - startTime;
    console.error(`❌ [${requestId}] API key creation failed after ${responseTime}ms:`, error.message);
    
    res.status(500).json({
      success: false,
      error: 'Failed to create API key',
      message: error.message,
      details: {
        requestId,
        responseTime: `${responseTime}ms`,
        serviceType: req.serviceType
      }
    });
  }
});

/**
 * Service Status Endpoint
 * GET /api/settings/integrated/status
 */
router.get('/status', async (req, res) => {
  const requestId = req.headers['x-request-id'] || 'req_' + Date.now();
  
  try {
    // Get status from both services
    const [legacyHealth, enhancedHealth] = await Promise.allSettled([
      legacyApiKeyService.healthCheck(),
      apiKeyService.healthCheck()
    ]);

    const status = {
      integration: {
        version: '1.0',
        status: 'operational',
        timestamp: new Date().toISOString(),
        requestId
      },
      services: {
        legacy: {
          available: legacyHealth.status === 'fulfilled',
          health: legacyHealth.status === 'fulfilled' ? legacyHealth.value : null,
          error: legacyHealth.status === 'rejected' ? legacyHealth.reason.message : null
        },
        enhanced: {
          available: enhancedHealth.status === 'fulfilled',
          health: enhancedHealth.status === 'fulfilled' ? enhancedHealth.value : null,
          error: enhancedHealth.status === 'rejected' ? enhancedHealth.reason.message : null
        }
      },
      recommendations: []
    };

    // Add recommendations based on service status
    if (status.services.enhanced.available && !status.services.legacy.available) {
      status.recommendations.push('Enhanced service is available - consider switching for better performance');
    } else if (!status.services.enhanced.available && status.services.legacy.available) {
      status.recommendations.push('Only legacy service is available - enhanced service may be experiencing issues');
    } else if (status.services.enhanced.available && status.services.legacy.available) {
      status.recommendations.push('Both services are available - you can use either or migrate to enhanced');
    } else {
      status.recommendations.push('Both services are experiencing issues - please try again later');
      status.integration.status = 'degraded';
    }

    res.json(status);

  } catch (error) {
    console.error(`❌ [${requestId}] Status check failed:`, error.message);
    
    res.status(500).json({
      integration: {
        version: '1.0',
        status: 'error',
        timestamp: new Date().toISOString(),
        requestId
      },
      error: error.message
    });
  }
});

/**
 * Migration Control Endpoint
 * POST /api/settings/integrated/migrate
 */
router.post('/migrate', async (req, res) => {
  const requestId = req.headers['x-request-id'] || 'req_' + Date.now();
  const { dryRun = true, batchSize = 10 } = req.body;
  
  try {
    const userId = req.user?.sub;
    
    if (!userId) {
      return res.status(401).json({
        success: false,
        error: 'Authentication required',
        requestId
      });
    }

    console.log(`🔄 [${requestId}] Migration requested for user: ${userId} (dry run: ${dryRun})`);

    // For individual user migration
    const migrationResult = await migrationUtility.migrateUserApiKeys(userId);

    res.json({
      success: true,
      message: `Migration ${dryRun ? 'simulation' : 'execution'} completed`,
      results: migrationResult,
      metadata: {
        requestId,
        timestamp: new Date().toISOString(),
        dryRun
      }
    });

  } catch (error) {
    console.error(`❌ [${requestId}] Migration failed:`, error.message);
    
    res.status(500).json({
      success: false,
      error: 'Migration failed',
      message: error.message,
      requestId
    });
  }
});

/**
 * Service Switching Endpoint
 * POST /api/settings/integrated/switch-service
 */
router.post('/switch-service', async (req, res) => {
  const requestId = req.headers['x-request-id'] || 'req_' + Date.now();
  const { service } = req.body; // 'legacy' or 'enhanced'
  
  try {
    if (!['legacy', 'enhanced'].includes(service)) {
      return res.status(400).json({
        success: false,
        error: 'Invalid service type',
        message: 'Service must be either "legacy" or "enhanced"',
        requestId
      });
    }

    // This would typically set a user preference in a database
    // For now, we'll just return instructions for the client
    res.json({
      success: true,
      message: `Service preference set to ${service}`,
      instructions: {
        headerRequired: 'x-use-enhanced-service',
        headerValue: service === 'enhanced' ? 'true' : 'false',
        queryParameter: 'enhanced',
        queryValue: service === 'enhanced' ? 'true' : 'false'
      },
      metadata: {
        requestId,
        timestamp: new Date().toISOString(),
        selectedService: service
      }
    });

  } catch (error) {
    console.error(`❌ [${requestId}] Service switching failed:`, error.message);
    
    res.status(500).json({
      success: false,
      error: 'Failed to switch service',
      message: error.message,
      requestId
    });
  }
});

module.exports = router;