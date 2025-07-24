/**
 * Unified API Keys Route
 * Simplified, reliable API key management for Alpaca
 * Replaces both portfolio and settings API key endpoints
 */

const express = require('express');
const { authenticateToken } = require('../middleware/auth');
const unifiedApiKeyService = require('../utils/unifiedApiKeyService');

const router = express.Router();

// Apply authentication to all routes
router.use(authenticateToken);

/**
 * Get user's API keys (Alpaca only for now)
 * GET /api/api-keys
 */
router.get('/', async (req, res) => {
  const requestId = res.locals.requestId || 'unknown';
  const userId = req.user?.sub;

  console.log(`🔐 [${requestId}] GET /api-keys for user: ${userId}`);

  try {
    if (!userId) {
      return res.status(401).json({
        success: false,
        error: 'User authentication required'
      });
    }

    const apiKeys = await unifiedApiKeyService.getApiKeySummary(userId);
    
    console.log(`✅ [${requestId}] Retrieved ${apiKeys.length} API keys`);
    
    res.json({
      success: true,
      data: apiKeys,
      count: apiKeys.length,
      message: apiKeys.length > 0 ? 'API keys retrieved successfully' : 'No API keys configured'
    });

  } catch (error) {
    console.error(`❌ [${requestId}] Error getting API keys:`, error);
    
    // Graceful degradation
    res.json({
      success: true,
      data: [],
      count: 0,
      message: 'API key service temporarily unavailable',
      error: error.message
    });
  }
});

/**
 * Add/Update Alpaca API key
 * POST /api/api-keys
 */
router.post('/', async (req, res) => {
  const requestId = res.locals.requestId || 'unknown';
  const userId = req.user?.sub;
  const { apiKey, secretKey, isSandbox = true } = req.body;

  console.log(`🔐 [${requestId}] POST /api-keys for user: ${userId}`);

  try {
    if (!userId) {
      return res.status(401).json({
        success: false,
        error: 'User authentication required'
      });
    }

    // Validate inputs
    if (!apiKey || !secretKey) {
      return res.status(400).json({
        success: false,
        error: 'API key and secret are required'
      });
    }

    // Validate Alpaca API key format
    if (!apiKey.startsWith('PK') || apiKey.length < 20) {
      return res.status(400).json({
        success: false,
        error: 'Invalid Alpaca API key format (must start with PK and be at least 20 characters)'
      });
    }

    // Validate secret format
    if (secretKey.length < 20 || secretKey.length > 80) {
      return res.status(400).json({
        success: false,
        error: 'Alpaca API secret must be 20-80 characters long'
      });
    }

    const result = await unifiedApiKeyService.saveAlpacaKey(userId, apiKey, secretKey, isSandbox);
    
    console.log(`✅ [${requestId}] API key saved successfully`);
    
    res.json({
      success: true,
      message: result.message,
      apiKey: {
        provider: 'alpaca',
        masked_api_key: unifiedApiKeyService.maskApiKey(apiKey),
        is_sandbox: isSandbox,
        created_at: new Date().toISOString()
      }
    });

  } catch (error) {
    console.error(`❌ [${requestId}] Error saving API key:`, error);
    
    res.status(500).json({
      success: false,
      error: 'Failed to save API key',
      message: error.message
    });
  }
});

/**
 * Remove API key
 * DELETE /api/api-keys
 */
router.delete('/', async (req, res) => {
  const requestId = res.locals.requestId || 'unknown';
  const userId = req.user?.sub;

  console.log(`🔐 [${requestId}] DELETE /api-keys for user: ${userId}`);

  try {
    if (!userId) {
      return res.status(401).json({
        success: false,
        error: 'User authentication required'
      });
    }

    const result = await unifiedApiKeyService.removeAlpacaKey(userId);
    
    console.log(`✅ [${requestId}] API key removed successfully`);
    
    res.json({
      success: true,
      message: result.message
    });

  } catch (error) {
    console.error(`❌ [${requestId}] Error removing API key:`, error);
    
    res.status(500).json({
      success: false,
      error: 'Failed to remove API key',
      message: error.message
    });
  }
});

/**
 * Check if user has API key
 * GET /api/api-keys/status
 */
router.get('/status', async (req, res) => {
  const requestId = res.locals.requestId || 'unknown';
  const userId = req.user?.sub;

  console.log(`🔐 [${requestId}] GET /api-keys/status for user: ${userId}`);

  try {
    if (!userId) {
      return res.status(401).json({
        success: false,
        error: 'User authentication required'
      });
    }

    const hasKey = await unifiedApiKeyService.hasAlpacaKey(userId);
    
    res.json({
      success: true,
      hasApiKey: hasKey,
      provider: hasKey ? 'alpaca' : null,
      message: hasKey ? 'API key is configured' : 'No API key configured'
    });

  } catch (error) {
    console.error(`❌ [${requestId}] Error checking API key status:`, error);
    
    res.json({
      success: true,
      hasApiKey: false,
      message: 'Unable to check API key status',
      error: error.message
    });
  }
});

/**
 * Get API key for internal use (by other services)
 * GET /api/api-keys/internal/:userId
 * This endpoint is for server-to-server communication
 */
router.get('/internal/:targetUserId', async (req, res) => {
  const requestId = res.locals.requestId || 'unknown';
  const { targetUserId } = req.params;
  const callingUserId = req.user?.sub;

  console.log(`🔐 [${requestId}] Internal API key request for user: ${targetUserId} by: ${callingUserId}`);

  try {
    // Security: Only allow users to get their own keys or admin access
    if (callingUserId !== targetUserId && !req.user?.groups?.includes('admin')) {
      return res.status(403).json({
        success: false,
        error: 'Access denied: Can only access your own API key'
      });
    }

    const keyData = await unifiedApiKeyService.getAlpacaKey(targetUserId);
    
    if (!keyData) {
      return res.status(404).json({
        success: false,
        error: 'No API key found for user'
      });
    }

    res.json({
      success: true,
      apiKey: keyData.keyId,
      secretKey: keyData.secretKey,
      provider: 'alpaca'
    });

  } catch (error) {
    console.error(`❌ [${requestId}] Error getting internal API key:`, error);
    
    res.status(500).json({
      success: false,
      error: 'Failed to retrieve API key',
      message: error.message
    });
  }
});

/**
 * Health check
 * GET /api/api-keys/health
 */
router.get('/health', async (req, res) => {
  try {
    const health = await unifiedApiKeyService.healthCheck();
    
    res.json({
      success: true,
      service: 'unified-api-keys',
      ...health
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      service: 'unified-api-keys',
      healthy: false,
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

module.exports = router;