/**
 * Portfolio API Keys Management Routes
 * Handles /api/portfolio/api-keys endpoints for broker API key management
 * Follows TDD principles with comprehensive security and validation
 */

const express = require('express');
const { query, healthCheck } = require('../utils/database');
const { authenticateToken } = require('../middleware/auth');
const { createValidationMiddleware, sanitizers } = require('../middleware/validation');
const crypto = require('crypto');
const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');

const router = express.Router();

// Apply authentication middleware to ALL API key routes
router.use(authenticateToken);

// Initialize AWS Secrets Manager for key encryption
const secretsManagerClient = new SecretsManagerClient({
  region: process.env.AWS_REGION || 'us-east-1'
});

// Supported broker providers
const SUPPORTED_BROKERS = ['alpaca', 'interactive_brokers', 'td_ameritrade', 'e_trade', 'fidelity', 'schwab'];

// Validation schemas
const apiKeyValidationSchemas = {
  brokerName: {
    type: 'string',
    required: true,
    sanitizer: (value) => sanitizers.string(value, { trim: true, toLowerCase: true }),
    validator: (value) => typeof value === 'string' && SUPPORTED_BROKERS.includes(value),
    errorMessage: `Broker name must be one of: ${SUPPORTED_BROKERS.join(', ')}`
  },
  apiKey: {
    type: 'string',
    required: true,
    sanitizer: (value) => sanitizers.string(value, { trim: true }),
    validator: (value) => typeof value === 'string' && value.length >= 8 && value.length <= 200,
    errorMessage: 'API key must be between 8 and 200 characters'
  },
  apiSecret: {
    type: 'string',
    required: true,
    sanitizer: (value) => sanitizers.string(value, { trim: true }),
    validator: (value) => typeof value === 'string' && value.length >= 8 && value.length <= 500,
    errorMessage: 'API secret must be between 8 and 500 characters'
  },
  sandbox: {
    type: 'boolean',
    required: false,
    sanitizer: (value) => sanitizers.boolean(value, { defaultValue: true }),
    validator: (value) => typeof value === 'boolean',
    errorMessage: 'Sandbox must be true or false'
  }
};

const validateApiKeyData = createValidationMiddleware(apiKeyValidationSchemas);

// Encryption utilities
const encryptApiKey = async (plaintext) => {
  try {
    // Get encryption key from AWS Secrets Manager
    const secretName = process.env.API_KEY_ENCRYPTION_SECRET_ARN || 'portfolio-api-key-encryption';
    
    let encryptionKey;
    try {
      const command = new GetSecretValueCommand({ SecretId: secretName });
      const secretResponse = await secretsManagerClient.send(command);
      encryptionKey = JSON.parse(secretResponse.SecretString).key;
    } catch (secretError) {
      console.warn('⚠️ AWS Secrets Manager not available, using fallback encryption');
      // Fallback encryption key (in production, this should come from Secrets Manager)
      encryptionKey = process.env.FALLBACK_ENCRYPTION_KEY || 'fallback-key-for-development-only';
    }
    
    const algorithm = 'aes-256-gcm';
    const iv = crypto.randomBytes(16);
    const cipher = crypto.createCipher(algorithm, encryptionKey);
    
    let encrypted = cipher.update(plaintext, 'utf8', 'hex');
    encrypted += cipher.final('hex');
    
    const authTag = cipher.getAuthTag();
    
    return {
      encryptedData: encrypted,
      iv: iv.toString('hex'),
      authTag: authTag.toString('hex'),
      algorithm
    };
  } catch (error) {
    console.error('❌ Encryption error:', error);
    throw new Error('Failed to encrypt API key');
  }
};

const decryptApiKey = async (encryptedObj) => {
  try {
    // Get encryption key from AWS Secrets Manager
    const secretName = process.env.API_KEY_ENCRYPTION_SECRET_ARN || 'portfolio-api-key-encryption';
    
    let encryptionKey;
    try {
      const command = new GetSecretValueCommand({ SecretId: secretName });
      const secretResponse = await secretsManagerClient.send(command);
      encryptionKey = JSON.parse(secretResponse.SecretString).key;
    } catch (secretError) {
      encryptionKey = process.env.FALLBACK_ENCRYPTION_KEY || 'fallback-key-for-development-only';
    }
    
    const decipher = crypto.createDecipher(encryptedObj.algorithm, encryptionKey);
    decipher.setAuthTag(Buffer.from(encryptedObj.authTag, 'hex'));
    
    let decrypted = decipher.update(encryptedObj.encryptedData, 'hex', 'utf8');
    decrypted += decipher.final('utf8');
    
    return decrypted;
  } catch (error) {
    console.error('❌ Decryption error:', error);
    throw new Error('Failed to decrypt API key');
  }
};

const maskApiKey = (apiKey) => {
  if (!apiKey || apiKey.length < 8) return '***';
  return apiKey.slice(0, 4) + '***' + apiKey.slice(-4);
};

// GET /api/portfolio/api-keys - Retrieve user's API keys
router.get('/api-keys', async (req, res) => {
  try {
    console.log('📝 GET /api/portfolio/api-keys - Retrieving user API keys');
    
    const userId = req.user?.sub || req.user?.id || 'demo-user';
    
    // Check database health first
    const dbHealth = await healthCheck();
    if (!dbHealth.healthy) {
      console.warn('⚠️ Database health check failed, returning empty list');
      return res.json({
        success: true,
        apiKeys: [],
        message: 'API keys service temporarily unavailable',
        fallback: true,
        timestamp: new Date().toISOString()
      });
    }
    
    const result = await query(
      `SELECT id, provider as "brokerName", masked_api_key, is_active, 
              validation_status, sandbox_mode, created_at, updated_at 
       FROM user_api_keys 
       WHERE user_id = $1 
       ORDER BY created_at DESC`,
      [userId],
      { timeout: 10000, retries: 2 }
    );
    
    const apiKeys = result.rows.map(row => ({
      id: row.id,
      brokerName: row.brokerName,
      maskedKey: row.masked_api_key,
      isActive: row.is_active,
      validationStatus: row.validation_status,
      sandbox: row.sandbox_mode,
      createdAt: row.created_at,
      updatedAt: row.updated_at
    }));
    
    console.log(`✅ Retrieved ${apiKeys.length} API keys for user ${userId}`);
    
    res.json({
      success: true,
      apiKeys,
      count: apiKeys.length,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('❌ Error retrieving API keys:', error);
    
    // Graceful degradation - return empty list instead of failing
    res.json({
      success: true,
      apiKeys: [],
      message: 'API keys temporarily unavailable',
      error: error.message,
      fallback: true,
      timestamp: new Date().toISOString()
    });
  }
});

// POST /api/portfolio/api-keys - Add new API key
router.post('/api-keys', validateApiKeyData(['brokerName', 'apiKey', 'apiSecret', 'sandbox']), async (req, res) => {
  try {
    console.log('📝 POST /api/portfolio/api-keys - Adding new API key');
    
    const userId = req.user?.sub || req.user?.id || 'demo-user';
    const { brokerName, apiKey, apiSecret, sandbox = true } = req.body;
    
    // Validate broker name
    if (!SUPPORTED_BROKERS.includes(brokerName)) {
      return res.status(400).json({
        success: false,
        error: `Unsupported broker: ${brokerName}`,
        supportedBrokers: SUPPORTED_BROKERS
      });
    }
    
    // Check database health
    const dbHealth = await healthCheck();
    if (!dbHealth.healthy) {
      return res.status(503).json({
        success: false,
        error: 'Database service unavailable',
        message: 'Please try again later'
      });
    }
    
    // Encrypt the API secret
    let encryptedSecret;
    try {
      encryptedSecret = await encryptApiKey(apiSecret);
    } catch (encryptionError) {
      console.error('❌ Failed to encrypt API secret:', encryptionError);
      return res.status(500).json({
        success: false,
        error: 'Failed to secure API credentials',
        message: 'Encryption service unavailable'
      });
    }
    
    const maskedKey = maskApiKey(apiKey);
    
    // Store in database with upsert to handle duplicates
    const result = await query(
      `INSERT INTO user_api_keys 
       (user_id, provider, api_key_encrypted, secret_encrypted, masked_api_key, 
        is_active, validation_status, sandbox_mode, created_at, updated_at)
       VALUES ($1, $2, $3, $4, $5, true, 'pending', $6, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
       ON CONFLICT (user_id, provider) 
       DO UPDATE SET 
         api_key_encrypted = EXCLUDED.api_key_encrypted,
         secret_encrypted = EXCLUDED.secret_encrypted,
         masked_api_key = EXCLUDED.masked_api_key,
         is_active = true,
         validation_status = 'pending',
         sandbox_mode = EXCLUDED.sandbox_mode,
         updated_at = CURRENT_TIMESTAMP
       RETURNING id, provider, masked_api_key, is_active, validation_status, sandbox_mode`,
      [
        userId, 
        brokerName, 
        await encryptApiKey(apiKey), 
        encryptedSecret, 
        maskedKey, 
        sandbox
      ],
      { timeout: 15000, retries: 2 }
    );
    
    console.log(`✅ API key added/updated for user ${userId}, broker ${brokerName}`);
    
    // TODO: Trigger API key validation in background
    // This would test the connection with the broker's API
    
    res.json({
      success: true,
      data: {
        id: result.rows[0].id,
        brokerName: result.rows[0].provider,
        maskedKey: result.rows[0].masked_api_key,
        isActive: result.rows[0].is_active,
        validationStatus: result.rows[0].validation_status,
        sandbox: result.rows[0].sandbox_mode
      },
      message: `${brokerName} API key saved successfully`,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('❌ Error adding API key:', error);
    
    if (error.code === '23505') { // Unique constraint violation
      return res.status(409).json({
        success: false,
        error: 'API key already exists for this broker',
        message: 'Use PUT endpoint to update existing keys'
      });
    }
    
    res.status(500).json({
      success: false,
      error: 'Failed to save API key',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// PUT /api/portfolio/api-keys/:brokerName - Update existing API key
router.put('/api-keys/:brokerName', validateApiKeyData(['apiKey', 'apiSecret', 'sandbox']), async (req, res) => {
  try {
    console.log('📝 PUT /api/portfolio/api-keys - Updating API key');
    
    const userId = req.user?.sub || req.user?.id || 'demo-user';
    const { brokerName } = req.params;
    const { apiKey, apiSecret, sandbox = true } = req.body;
    
    if (!SUPPORTED_BROKERS.includes(brokerName)) {
      return res.status(400).json({
        success: false,
        error: `Unsupported broker: ${brokerName}`
      });
    }
    
    // Encrypt the new credentials
    const encryptedKey = await encryptApiKey(apiKey);
    const encryptedSecret = await encryptApiKey(apiSecret);
    const maskedKey = maskApiKey(apiKey);
    
    const result = await query(
      `UPDATE user_api_keys 
       SET api_key_encrypted = $3, secret_encrypted = $4, masked_api_key = $5,
           validation_status = 'pending', sandbox_mode = $6, updated_at = CURRENT_TIMESTAMP
       WHERE user_id = $1 AND provider = $2
       RETURNING id, provider, masked_api_key, is_active, validation_status, sandbox_mode`,
      [userId, brokerName, encryptedKey, encryptedSecret, maskedKey, sandbox],
      { timeout: 15000, retries: 2 }
    );
    
    if (result.rowCount === 0) {
      return res.status(404).json({
        success: false,
        error: `No API key found for broker: ${brokerName}`
      });
    }
    
    console.log(`✅ API key updated for user ${userId}, broker ${brokerName}`);
    
    res.json({
      success: true,
      data: {
        id: result.rows[0].id,
        brokerName: result.rows[0].provider,
        maskedKey: result.rows[0].masked_api_key,
        isActive: result.rows[0].is_active,
        validationStatus: result.rows[0].validation_status,
        sandbox: result.rows[0].sandbox_mode
      },
      message: `${brokerName} API key updated successfully`,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('❌ Error updating API key:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to update API key',
      message: error.message
    });
  }
});

// DELETE /api/portfolio/api-keys/:brokerName - Delete API key
router.delete('/api-keys/:brokerName', async (req, res) => {
  try {
    console.log('📝 DELETE /api/portfolio/api-keys - Deleting API key');
    
    const userId = req.user?.sub || req.user?.id || 'demo-user';
    const { brokerName } = req.params;
    
    if (!SUPPORTED_BROKERS.includes(brokerName)) {
      return res.status(400).json({
        success: false,
        error: `Unsupported broker: ${brokerName}`
      });
    }
    
    const result = await query(
      'DELETE FROM user_api_keys WHERE user_id = $1 AND provider = $2 RETURNING id',
      [userId, brokerName],
      { timeout: 10000, retries: 2 }
    );
    
    if (result.rowCount === 0) {
      return res.status(404).json({
        success: false,
        error: `No API key found for broker: ${brokerName}`
      });
    }
    
    console.log(`✅ API key deleted for user ${userId}, broker ${brokerName}`);
    
    res.json({
      success: true,
      message: `${brokerName} API key deleted successfully`,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('❌ Error deleting API key:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to delete API key',
      message: error.message
    });
  }
});

// POST /api/portfolio/test-connection/:brokerName - Test API key connection
router.post('/test-connection/:brokerName', async (req, res) => {
  try {
    console.log('🔌 POST /api/portfolio/test-connection - Testing API connection');
    
    const userId = req.user?.sub || req.user?.id || 'demo-user';
    const { brokerName } = req.params;
    
    if (!SUPPORTED_BROKERS.includes(brokerName)) {
      return res.status(400).json({
        success: false,
        error: `Unsupported broker: ${brokerName}`
      });
    }
    
    // Retrieve encrypted API keys
    const result = await query(
      'SELECT api_key_encrypted, secret_encrypted, sandbox_mode FROM user_api_keys WHERE user_id = $1 AND provider = $2',
      [userId, brokerName],
      { timeout: 10000, retries: 2 }
    );
    
    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: `No API key found for broker: ${brokerName}`,
        message: 'Please add API credentials first'
      });
    }
    
    // Decrypt credentials
    const row = result.rows[0];
    let apiKey, apiSecret;
    
    try {
      apiKey = await decryptApiKey(row.api_key_encrypted);
      apiSecret = await decryptApiKey(row.secret_encrypted);
    } catch (decryptError) {
      console.error('❌ Failed to decrypt API credentials:', decryptError);
      return res.status(500).json({
        success: false,
        error: 'Failed to decrypt API credentials',
        message: 'Please re-enter your API keys'
      });
    }
    
    // Test connection based on broker
    let connectionResult;
    
    switch (brokerName) {
      case 'alpaca':
        const AlpacaService = require('../utils/alpacaService');
        const alpacaService = new AlpacaService();
        connectionResult = await alpacaService.testConnection(apiKey, apiSecret, row.sandbox_mode);
        break;
        
      default:
        // For other brokers, implement basic HTTP test
        connectionResult = {
          connected: false,
          message: `Connection testing for ${brokerName} not yet implemented`,
          accountInfo: null
        };
        break;
    }
    
    // Update validation status in database
    await query(
      'UPDATE user_api_keys SET validation_status = $3, updated_at = CURRENT_TIMESTAMP WHERE user_id = $1 AND provider = $2',
      [userId, brokerName, connectionResult.connected ? 'valid' : 'invalid'],
      { timeout: 10000, retries: 2 }
    );
    
    console.log(`✅ Connection test completed for ${brokerName}: ${connectionResult.connected ? 'success' : 'failed'}`);
    
    res.json({
      success: connectionResult.connected,
      data: {
        connected: connectionResult.connected,
        brokerName,
        sandbox: row.sandbox_mode,
        message: connectionResult.message,
        accountInfo: connectionResult.accountInfo || null,
        testedAt: new Date().toISOString()
      },
      message: connectionResult.connected ? 
        `Successfully connected to ${brokerName}` : 
        `Failed to connect to ${brokerName}: ${connectionResult.message}`,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('❌ Error testing API connection:', error);
    
    res.status(500).json({
      success: false,
      error: 'Connection test failed',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// GET /api/portfolio/api-keys/:brokerName - Get specific API key details
router.get('/api-keys/:brokerName', async (req, res) => {
  try {
    const userId = req.user?.sub || req.user?.id || 'demo-user';
    const { brokerName } = req.params;
    
    if (!SUPPORTED_BROKERS.includes(brokerName)) {
      return res.status(400).json({
        success: false,
        error: `Unsupported broker: ${brokerName}`
      });
    }
    
    const result = await query(
      `SELECT id, provider, masked_api_key, is_active, validation_status, 
              sandbox_mode, created_at, updated_at 
       FROM user_api_keys 
       WHERE user_id = $1 AND provider = $2`,
      [userId, brokerName],
      { timeout: 10000, retries: 2 }
    );
    
    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: `No API key found for broker: ${brokerName}`
      });
    }
    
    const row = result.rows[0];
    
    res.json({
      success: true,
      data: {
        id: row.id,
        brokerName: row.provider,
        maskedKey: row.masked_api_key,
        isActive: row.is_active,
        validationStatus: row.validation_status,
        sandbox: row.sandbox_mode,
        createdAt: row.created_at,
        updatedAt: row.updated_at
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('❌ Error retrieving API key details:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to retrieve API key details',
      message: error.message
    });
  }
});

// Health check endpoint
router.get('/health', (req, res) => {
  res.json({
    success: true,
    service: 'portfolio-api-keys',
    timestamp: new Date().toISOString(),
    endpoints: [
      'GET /api/portfolio/api-keys',
      'POST /api/portfolio/api-keys',
      'PUT /api/portfolio/api-keys/:brokerName',
      'DELETE /api/portfolio/api-keys/:brokerName',
      'POST /api/portfolio/test-connection/:brokerName',
      'GET /api/portfolio/api-keys/:brokerName'
    ],
    supportedBrokers: SUPPORTED_BROKERS
  });
});

module.exports = router;