/**
 * Settings API Keys Route
 * Connects the existing SettingsApiKeys UI with the new apiKeyService
 */

const express = require('express');
const router = express.Router();
const apiKeyService = require('../utils/apiKeyService');

/**
 * Get all API keys for a user
 * GET /api/settings/api-keys/:userId
 */
router.get('/:userId', async (req, res) => {
  try {
    const { userId } = req.params;
    
    console.log(`🔍 Fetching API keys for user: ${userId}`);
    
    // Get list of API keys from Parameter Store
    const apiKeys = await apiKeyService.listApiKeys(userId);
    
    // Transform to match frontend expectations
    const transformedKeys = apiKeys.map(key => ({
      id: `${userId}-${key.provider}`,
      provider: key.provider,
      apiKey: key.keyId,
      description: `${key.provider} API key`,
      isSandbox: true, // Default to sandbox for security
      isActive: !!key.keyId,
      created: key.created,
      lastUsed: null // We don't track usage yet
    }));

    res.json({
      success: true,
      apiKeys: transformedKeys,
      connectionStatus: {}, // Will be populated by connection tests
      note: `Found ${transformedKeys.length} API keys`
    });

  } catch (error) {
    console.error('❌ Error fetching API keys:', error.message);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch API keys',
      message: error.message,
      guidance: {
        title: 'API Key Retrieval Failed',
        description: 'Unable to retrieve your stored API keys. This may be due to AWS connectivity issues.'
      }
    });
  }
});

/**
 * Add a new API key
 * POST /api/settings/api-keys/:userId/:provider
 */
router.post('/:userId/:provider', async (req, res) => {
  try {
    const { userId, provider } = req.params;
    const { key, secret, description } = req.body;
    
    console.log(`🔐 Adding API key for user: ${userId}, provider: ${provider}`);
    
    // Validate provider
    const supportedProviders = ['alpaca', 'polygon', 'finnhub', 'iex'];
    if (!supportedProviders.includes(provider.toLowerCase())) {
      return res.status(400).json({
        success: false,
        error: `Unsupported provider: ${provider}`,
        supportedProviders
      });
    }

    // Store the API key
    const result = await apiKeyService.storeApiKey(
      userId,
      provider.toLowerCase(),
      key,
      secret || ''
    );

    if (result) {
      res.json({
        success: true,
        message: `${provider} API key stored successfully`,
        data: {
          id: `${userId}-${provider}`,
          provider: provider.toLowerCase(),
          keyId: key.substring(0, 4) + '***' + key.slice(-4),
          created: new Date().toISOString()
        }
      });
    } else {
      throw new Error('Failed to store API key');
    }

  } catch (error) {
    console.error('❌ Error adding API key:', error.message);
    res.status(500).json({
      success: false,
      error: 'Failed to add API key',
      message: error.message
    });
  }
});

/**
 * Test API key connection
 * POST /api/settings/api-keys/:userId/:provider/test
 */
router.post('/:userId/:provider/test', async (req, res) => {
  try {
    const { userId, provider } = req.params;
    
    console.log(`🧪 Testing API key connection for user: ${userId}, provider: ${provider}`);
    
    // Retrieve the API key
    const apiKey = await apiKeyService.getApiKey(userId, provider);
    
    if (!apiKey) {
      return res.status(404).json({
        success: false,
        error: `No API key found for provider: ${provider}`
      });
    }

    // Test connection based on provider
    let testResult;
    const startTime = Date.now();

    switch (provider.toLowerCase()) {
      case 'alpaca':
        testResult = await testAlpacaConnection(apiKey);
        break;
      case 'polygon':
        testResult = await testPolygonConnection(apiKey);
        break;
      case 'finnhub':
        testResult = await testFinnhubConnection(apiKey);
        break;
      default:
        testResult = { success: false, message: `Testing not implemented for ${provider}` };
    }

    const responseTime = Date.now() - startTime;

    res.json({
      success: testResult.success,
      message: testResult.message,
      responseTime,
      provider,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('❌ Error testing API key:', error.message);
    res.status(500).json({
      success: false,
      error: 'Connection test failed',
      message: error.message
    });
  }
});

/**
 * Delete API key
 * DELETE /api/settings/api-keys/:userId/:provider
 */
router.delete('/:userId/:provider', async (req, res) => {
  try {
    const { userId, provider } = req.params;
    
    console.log(`🗑️ Deleting API key for user: ${userId}, provider: ${provider}`);
    
    const result = await apiKeyService.deleteApiKey(userId, provider);
    
    if (result) {
      res.json({
        success: true,
        message: `${provider} API key deleted successfully`
      });
    } else {
      throw new Error('Failed to delete API key');
    }

  } catch (error) {
    console.error('❌ Error deleting API key:', error.message);
    res.status(500).json({
      success: false,
      error: 'Failed to delete API key',
      message: error.message
    });
  }
});

/**
 * Get API key service health
 * GET /api/settings/api-keys/health
 */
router.get('/health', async (req, res) => {
  try {
    const healthCheck = await apiKeyService.healthCheck();
    res.json(healthCheck);
  } catch (error) {
    res.status(500).json({
      status: 'unhealthy',
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// API Key Testing Functions

async function testAlpacaConnection(apiKey) {
  try {
    const axios = require('axios');
    
    const response = await axios.get('https://paper-api.alpaca.markets/v2/account', {
      headers: {
        'APCA-API-KEY-ID': apiKey.keyId,
        'APCA-API-SECRET-KEY': apiKey.secretKey
      },
      timeout: 10000
    });

    if (response.status === 200) {
      return {
        success: true,
        message: `Alpaca connection successful. Account: ${response.data.account_number}`
      };
    } else {
      return {
        success: false,
        message: 'Alpaca connection failed - invalid response'
      };
    }

  } catch (error) {
    return {
      success: false,
      message: `Alpaca connection failed: ${error.response?.data?.message || error.message}`
    };
  }
}

async function testPolygonConnection(apiKey) {
  try {
    const axios = require('axios');
    
    const response = await axios.get(`https://api.polygon.io/v3/reference/tickers?apikey=${apiKey.keyId}&limit=1`, {
      timeout: 10000
    });

    if (response.status === 200 && response.data.results) {
      return {
        success: true,
        message: 'Polygon connection successful'
      };
    } else {
      return {
        success: false,
        message: 'Polygon connection failed - invalid response'
      };
    }

  } catch (error) {
    return {
      success: false,
      message: `Polygon connection failed: ${error.response?.data?.message || error.message}`
    };
  }
}

async function testFinnhubConnection(apiKey) {
  try {
    const axios = require('axios');
    
    const response = await axios.get(`https://finnhub.io/api/v1/stock/profile2?symbol=AAPL&token=${apiKey.keyId}`, {
      timeout: 10000
    });

    if (response.status === 200 && response.data.name) {
      return {
        success: true,
        message: 'Finnhub connection successful'
      };
    } else {
      return {
        success: false,
        message: 'Finnhub connection failed - invalid response'
      };
    }

  } catch (error) {
    return {
      success: false,
      message: `Finnhub connection failed: ${error.response?.data?.message || error.message}`
    };
  }
}

module.exports = router;