const express = require('express');
const crypto = require('crypto');
const { query } = require('../utils/database');
const { authenticateToken } = require('../middleware/auth');

const router = express.Router();

// Apply authentication middleware to all settings routes
router.use(authenticateToken);

// Encryption utilities
const ALGORITHM = 'aes-256-gcm';

function encryptApiKey(apiKey, userSalt) {
  const secretKey = process.env.API_KEY_ENCRYPTION_SECRET || 'default-encryption-key-change-in-production';
  const key = crypto.scryptSync(secretKey, userSalt, 32);
  const iv = crypto.randomBytes(16);
  const cipher = crypto.createCipherGCM(ALGORITHM, key, iv);
  cipher.setAAD(Buffer.from(userSalt));
  
  let encrypted = cipher.update(apiKey, 'utf8', 'hex');
  encrypted += cipher.final('hex');
  const authTag = cipher.getAuthTag();
  
  return {
    encrypted: encrypted,
    iv: iv.toString('hex'),
    authTag: authTag.toString('hex')
  };
}

function decryptApiKey(encryptedData, userSalt) {
  const secretKey = process.env.API_KEY_ENCRYPTION_SECRET || 'default-encryption-key-change-in-production';
  const key = crypto.scryptSync(secretKey, userSalt, 32);
  const iv = Buffer.from(encryptedData.iv, 'hex');
  const decipher = crypto.createDecipherGCM(ALGORITHM, key, iv);
  decipher.setAAD(Buffer.from(userSalt));
  decipher.setAuthTag(Buffer.from(encryptedData.authTag, 'hex'));
  
  let decrypted = decipher.update(encryptedData.encrypted, 'hex', 'utf8');
  decrypted += decipher.final('utf8');
  
  return decrypted;
}

// Get all API keys for authenticated user
router.get('/api-keys', async (req, res) => {
  const userId = req.user.sub;
  
  try {
    const result = await query(`
      SELECT 
        id,
        provider,
        description,
        is_sandbox as "isSandbox",
        is_active as "isActive",
        created_at as "createdAt",
        last_used as "lastUsed"
      FROM user_api_keys 
      WHERE user_id = $1 
      ORDER BY created_at DESC
    `, [userId]);

    // Don't return the actual encrypted keys for security
    const apiKeys = result.rows.map(row => ({
      id: row.id,
      provider: row.provider,
      description: row.description,
      isSandbox: row.isSandbox,
      isActive: row.isActive,
      createdAt: row.createdAt,
      lastUsed: row.lastUsed,
      apiKey: '****' // Masked for security
    }));

    res.json({ 
      success: true, 
      apiKeys 
    });
  } catch (error) {
    console.error('Error fetching API keys:', error);
    res.status(500).json({ 
      success: false, 
      error: 'Failed to fetch API keys' 
    });
  }
});

// Add new API key
router.post('/api-keys', async (req, res) => {
  const userId = req.user.sub;
  const { provider, apiKey, apiSecret, isSandbox = true, description } = req.body;

  if (!provider || !apiKey) {
    return res.status(400).json({
      success: false,
      error: 'Provider and API key are required'
    });
  }

  try {
    // Generate user-specific salt
    const userSalt = crypto.randomBytes(16).toString('hex');
    
    // Encrypt API credentials
    const encryptedApiKey = encryptApiKey(apiKey, userSalt);
    const encryptedApiSecret = apiSecret ? encryptApiKey(apiSecret, userSalt) : null;

    // Insert into database
    const result = await query(`
      INSERT INTO user_api_keys (
        user_id, 
        provider, 
        encrypted_api_key, 
        key_iv, 
        key_auth_tag,
        encrypted_api_secret,
        secret_iv,
        secret_auth_tag,
        user_salt,
        is_sandbox, 
        description,
        is_active,
        created_at
      ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, true, NOW())
      RETURNING id, provider, description, is_sandbox as "isSandbox", created_at as "createdAt"
    `, [
      userId,
      provider,
      encryptedApiKey.encrypted,
      encryptedApiKey.iv,
      encryptedApiKey.authTag,
      encryptedApiSecret?.encrypted || null,
      encryptedApiSecret?.iv || null,
      encryptedApiSecret?.authTag || null,
      userSalt,
      isSandbox,
      description
    ]);

    res.json({
      success: true,
      message: 'API key added successfully',
      apiKey: result.rows[0]
    });
  } catch (error) {
    console.error('Error adding API key:', error);
    
    if (error.code === '23505') { // Unique constraint violation
      res.status(400).json({
        success: false,
        error: 'API key for this provider already exists'
      });
    } else {
      res.status(500).json({
        success: false,
        error: 'Failed to add API key'
      });
    }
  }
});

// Update API key
router.put('/api-keys/:keyId', async (req, res) => {
  const userId = req.user.sub;
  const { keyId } = req.params;
  const { description, isSandbox } = req.body;

  try {
    const result = await query(`
      UPDATE user_api_keys 
      SET 
        description = COALESCE($3, description),
        is_sandbox = COALESCE($4, is_sandbox),
        updated_at = NOW()
      WHERE id = $1 AND user_id = $2
      RETURNING id, provider, description, is_sandbox as "isSandbox"
    `, [keyId, userId, description, isSandbox]);

    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: 'API key not found'
      });
    }

    res.json({
      success: true,
      message: 'API key updated successfully',
      apiKey: result.rows[0]
    });
  } catch (error) {
    console.error('Error updating API key:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to update API key'
    });
  }
});

// Delete API key
router.delete('/api-keys/:keyId', async (req, res) => {
  const userId = req.user.sub;
  const { keyId } = req.params;

  try {
    const result = await query(`
      DELETE FROM user_api_keys 
      WHERE id = $1 AND user_id = $2
      RETURNING id, provider
    `, [keyId, userId]);

    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: 'API key not found'
      });
    }

    res.json({
      success: true,
      message: 'API key deleted successfully'
    });
  } catch (error) {
    console.error('Error deleting API key:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to delete API key'
    });
  }
});

// Test API key connection
router.post('/test-connection/:keyId', async (req, res) => {
  const userId = req.user.sub;
  const { keyId } = req.params;

  try {
    // Get encrypted API key
    const result = await query(`
      SELECT 
        provider,
        encrypted_api_key,
        key_iv,
        key_auth_tag,
        encrypted_api_secret,
        secret_iv,
        secret_auth_tag,
        user_salt,
        is_sandbox
      FROM user_api_keys 
      WHERE id = $1 AND user_id = $2 AND is_active = true
    `, [keyId, userId]);

    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: 'API key not found'
      });
    }

    const keyData = result.rows[0];
    
    // Decrypt API credentials
    const apiKey = decryptApiKey({
      encrypted: keyData.encrypted_api_key,
      iv: keyData.key_iv,
      authTag: keyData.key_auth_tag
    }, keyData.user_salt);

    const apiSecret = keyData.encrypted_api_secret ? decryptApiKey({
      encrypted: keyData.encrypted_api_secret,
      iv: keyData.secret_iv,
      authTag: keyData.secret_auth_tag
    }, keyData.user_salt) : null;

    // Test connection based on provider
    let connectionResult = { valid: false, error: 'Provider not supported' };
    
    if (keyData.provider === 'alpaca') {
      const AlpacaService = require('../utils/alpacaService');
      const alpaca = new AlpacaService(apiKey, apiSecret, keyData.is_sandbox);
      
      try {
        const account = await alpaca.getAccount();
        connectionResult = {
          valid: true,
          accountInfo: {
            accountId: account.id,
            portfolioValue: parseFloat(account.portfolio_value || 0),
            environment: keyData.is_sandbox ? 'sandbox' : 'live'
          }
        };
        
        // Update last_used timestamp
        await query(`
          UPDATE user_api_keys 
          SET last_used = NOW() 
          WHERE id = $1
        `, [keyId]);
        
      } catch (error) {
        connectionResult = {
          valid: false,
          error: error.message
        };
      }
    }

    res.json({
      success: true,
      connection: connectionResult
    });
  } catch (error) {
    console.error('Error testing connection:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to test connection'
    });
  }
});

module.exports = router;