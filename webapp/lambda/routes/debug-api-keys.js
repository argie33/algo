const express = require('express');
const { query } = require('../utils/database');
const { authenticateToken } = require('../middleware/auth');
const apiKeyService = require('../utils/apiKeyService');

const router = express.Router();

// Debug endpoint to test API key retrieval flow
router.get('/debug/api-keys/:broker', authenticateToken, async (req, res) => {
  const { broker } = req.params;
  const userId = req.user?.sub;
  
  console.log(`🔍 [DEBUG] Starting API key debug for user: ${userId}, broker: ${broker}`);
  
  const debug = {
    userId: userId,
    broker: broker,
    timestamp: new Date().toISOString(),
    steps: []
  };
  
  try {
    // Step 1: Check user authentication
    debug.steps.push({
      step: 1,
      name: 'User Authentication',
      userId: userId,
      userObject: req.user ? 'Present' : 'Missing',
      status: userId ? 'PASS' : 'FAIL'
    });
    
    if (!userId) {
      return res.json({
        success: false,
        error: 'Authentication failed',
        debug: debug
      });
    }
    
    // Step 2: Check if API key service is enabled
    debug.steps.push({
      step: 2,
      name: 'API Key Service Status',
      enabled: apiKeyService.isEnabled,
      encryptionSecret: !!process.env.API_KEY_ENCRYPTION_SECRET,
      status: apiKeyService.isEnabled ? 'PASS' : 'FAIL'
    });
    
    // Step 3: Raw database query to check if user has API keys
    const rawKeysResult = await query(`
      SELECT id, provider, user_id, is_active, created_at, description,
             CASE WHEN encrypted_api_key IS NOT NULL THEN 'Present' ELSE 'Missing' END as api_key_status,
             CASE WHEN encrypted_api_secret IS NOT NULL THEN 'Present' ELSE 'Missing' END as api_secret_status
      FROM user_api_keys 
      WHERE user_id = $1
      ORDER BY created_at DESC
    `, [userId]);
    
    debug.steps.push({
      step: 3,
      name: 'Raw Database Check',
      totalKeys: rawKeysResult.rows.length,
      keys: rawKeysResult.rows,
      status: rawKeysResult.rows.length > 0 ? 'PASS' : 'FAIL'
    });
    
    // Step 4: Check for specific broker
    const brokerKeys = rawKeysResult.rows.filter(k => k.provider === broker && k.is_active);
    debug.steps.push({
      step: 4,
      name: 'Broker-Specific Keys',
      broker: broker,
      activeKeys: brokerKeys.length,
      keys: brokerKeys,
      status: brokerKeys.length > 0 ? 'PASS' : 'FAIL'
    });
    
    // Step 5: Test API key service retrieval
    let serviceResult = null;
    let serviceError = null;
    try {
      serviceResult = await apiKeyService.getDecryptedApiKey(userId, broker);
      debug.steps.push({
        step: 5,
        name: 'API Key Service Retrieval',
        result: serviceResult ? 'Success' : 'No result',
        hasApiKey: !!serviceResult?.apiKey,
        hasApiSecret: !!serviceResult?.apiSecret,
        provider: serviceResult?.provider,
        isSandbox: serviceResult?.isSandbox,
        status: serviceResult ? 'PASS' : 'FAIL'
      });
    } catch (error) {
      serviceError = error;
      debug.steps.push({
        step: 5,
        name: 'API Key Service Retrieval',
        error: error.message,
        stack: error.stack,
        status: 'FAIL'
      });
    }
    
    // Step 6: Test if we can decrypt at least one key manually
    if (brokerKeys.length > 0 && apiKeyService.isEnabled) {
      try {
        const testKey = brokerKeys[0];
        const decryptedKey = apiKeyService.decryptApiKey({
          encrypted: testKey.encrypted_api_key,
          iv: testKey.key_iv,
          authTag: testKey.key_auth_tag
        }, testKey.user_salt);
        
        debug.steps.push({
          step: 6,
          name: 'Manual Decryption Test',
          keyId: testKey.id,
          decryptionWorked: !!decryptedKey,
          status: decryptedKey ? 'PASS' : 'FAIL'
        });
      } catch (decryptError) {
        debug.steps.push({
          step: 6,
          name: 'Manual Decryption Test',
          error: decryptError.message,
          status: 'FAIL'
        });
      }
    }
    
    // Summary
    const allStepsPassed = debug.steps.every(step => step.status === 'PASS');
    
    res.json({
      success: allStepsPassed,
      message: allStepsPassed ? 'All API key retrieval steps working' : 'Issues found in API key retrieval',
      debug: debug,
      recommendation: allStepsPassed ? 
        'API key retrieval should work. Issue may be elsewhere.' :
        'Fix failed steps above to enable portfolio import.'
    });
    
  } catch (error) {
    console.error('Debug endpoint error:', error);
    res.status(500).json({
      success: false,
      error: 'Debug endpoint failed',
      message: error.message,
      debug: debug
    });
  }
});

module.exports = router;