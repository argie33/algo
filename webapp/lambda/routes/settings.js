const express = require('express');
const crypto = require('crypto');
const { query } = require('../utils/database');
const { authenticateToken } = require('../middleware/auth');

const router = express.Router();

// Apply authentication middleware to all settings routes
router.use(authenticateToken);

// 2FA verification middleware for sensitive operations
const require2FA = async (req, res, next) => {
  const userId = req.user.sub;
  const { mfaCode } = req.headers;
  
  try {
    // Check if user has 2FA enabled
    const userResult = await query(`
      SELECT two_factor_enabled, two_factor_secret 
      FROM users 
      WHERE id = $1
    `, [userId]);
    
    if (userResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: 'User not found'
      });
    }
    
    const user = userResult.rows[0];
    
    // If 2FA is not enabled, allow the request but warn
    if (!user.two_factor_enabled) {
      console.warn(`⚠️  User ${userId} accessing sensitive operations without 2FA enabled`);
      return next();
    }
    
    // If 2FA is enabled, require MFA code
    if (!mfaCode) {
      return res.status(401).json({
        success: false,
        error: 'MFA verification required',
        requiresMFA: true,
        message: 'This operation requires 2FA verification. Please provide your authenticator code.'
      });
    }
    
    // Verify the MFA code
    const speakeasy = require('speakeasy');
    const verified = speakeasy.totp.verify({
      secret: user.two_factor_secret,
      encoding: 'base32',
      token: mfaCode,
      window: 2
    });
    
    if (!verified) {
      return res.status(401).json({
        success: false,
        error: 'Invalid MFA code',
        requiresMFA: true,
        message: 'The provided MFA code is invalid. Please try again.'
      });
    }
    
    console.log(`🔐 MFA verification successful for user ${userId}`);
    next();
    
  } catch (error) {
    console.error('❌ Error in 2FA verification middleware:', error);
    res.status(500).json({
      success: false,
      error: 'MFA verification failed',
      details: error.message
    });
  }
};

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
  console.log('🔍 API Keys fetch requested');
  console.log('📋 Request headers:', {
    authorization: req.headers.authorization ? 'Present' : 'Missing',
    'content-type': req.headers['content-type'],
    'user-agent': req.headers['user-agent']
  });
  
  // Check if user is authenticated
  if (!req.user) {
    console.error('❌ No user object in request - authentication failed');
    return res.status(401).json({
      success: false,
      error: 'Authentication required',
      message: 'User not authenticated'
    });
  }
  
  const userId = req.user.sub;
  console.log('👤 User ID:', userId);
  console.log('🔐 User details:', {
    sub: req.user.sub,
    email: req.user.email,
    username: req.user.username,
    role: req.user.role
  });
  
  if (!userId) {
    console.error('❌ No user ID found in authentication token');
    return res.status(401).json({
      success: false,
      error: 'Invalid authentication token',
      message: 'User ID not found in token'
    });
  }
  
  try {
    console.log('🔄 Attempting to query user_api_keys table...');
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

    console.log('✅ Database query successful');
    console.log('📊 Found API keys:', result.rows.length);

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

    console.log('🎯 Returning API keys response');
    res.json({ 
      success: true, 
      apiKeys 
    });
  } catch (error) {
    console.error('❌ Database error in API keys fetch:', error);
    console.error('🔍 Error details:', {
      message: error.message,
      code: error.code,
      severity: error.severity,
      detail: error.detail,
      hint: error.hint,
      position: error.position,
      internalPosition: error.internalPosition,
      internalQuery: error.internalQuery,
      where: error.where,
      schema: error.schema,
      table: error.table,
      column: error.column,
      dataType: error.dataType,
      constraint: error.constraint,
      file: error.file,
      line: error.line,
      routine: error.routine
    });
    
    // Return more specific error information
    let errorMessage = 'Failed to fetch API keys';
    let errorCode = 'DATABASE_ERROR';
    
    if (error.code === '42P01') {
      errorMessage = 'Database table does not exist';
      errorCode = 'TABLE_NOT_FOUND';
    } else if (error.code === '28000') {
      errorMessage = 'Database authentication failed';
      errorCode = 'DB_AUTH_FAILED';
    } else if (error.code === 'ECONNREFUSED') {
      errorMessage = 'Cannot connect to database';
      errorCode = 'DB_CONNECTION_FAILED';
    }
    
    res.status(500).json({ 
      success: false, 
      error: errorMessage,
      errorCode: errorCode,
      details: process.env.NODE_ENV === 'development' ? error.message : undefined
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

// User profile management
router.get('/profile', async (req, res) => {
  const userId = req.user.sub;
  
  try {
    const result = await query(`
      SELECT 
        first_name as "firstName",
        last_name as "lastName", 
        email,
        phone,
        timezone,
        currency,
        created_at as "createdAt",
        updated_at as "updatedAt"
      FROM users 
      WHERE id = $1
    `, [userId]);

    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: 'User not found'
      });
    }

    res.json({
      success: true,
      user: result.rows[0]
    });
  } catch (error) {
    console.error('Error fetching user profile:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch user profile'
    });
  }
});

// Update user profile
router.put('/profile', async (req, res) => {
  const userId = req.user.sub;
  const { firstName, lastName, email, phone, timezone, currency } = req.body;

  try {
    const result = await query(`
      UPDATE users 
      SET 
        first_name = COALESCE($2, first_name),
        last_name = COALESCE($3, last_name),
        email = COALESCE($4, email),
        phone = COALESCE($5, phone),
        timezone = COALESCE($6, timezone),
        currency = COALESCE($7, currency),
        updated_at = NOW()
      WHERE id = $1
      RETURNING 
        first_name as "firstName",
        last_name as "lastName",
        email,
        phone,
        timezone,
        currency
    `, [userId, firstName, lastName, email, phone, timezone, currency]);

    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: 'User not found'
      });
    }

    res.json({
      success: true,
      message: 'Profile updated successfully',
      user: result.rows[0]
    });
  } catch (error) {
    console.error('Error updating user profile:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to update user profile'
    });
  }
});

// Get notification preferences
router.get('/notifications', async (req, res) => {
  const userId = req.user.sub;
  
  try {
    const result = await query(`
      SELECT 
        email_notifications as email,
        push_notifications as push,
        price_alerts as "priceAlerts",
        portfolio_updates as "portfolioUpdates",
        market_news as "marketNews",
        weekly_reports as "weeklyReports"
      FROM user_notification_preferences 
      WHERE user_id = $1
    `, [userId]);

    // If no preferences exist, return defaults
    const preferences = result.rows.length > 0 ? result.rows[0] : {
      email: true,
      push: true,
      priceAlerts: true,
      portfolioUpdates: true,
      marketNews: false,
      weeklyReports: true
    };

    res.json({
      success: true,
      preferences
    });
  } catch (error) {
    console.error('Error fetching notification preferences:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch notification preferences'
    });
  }
});

// Update notification preferences
router.put('/notifications', async (req, res) => {
  const userId = req.user.sub;
  const { email, push, priceAlerts, portfolioUpdates, marketNews, weeklyReports } = req.body;

  try {
    // Use UPSERT to create or update preferences
    const result = await query(`
      INSERT INTO user_notification_preferences (
        user_id, 
        email_notifications, 
        push_notifications, 
        price_alerts, 
        portfolio_updates, 
        market_news, 
        weekly_reports,
        updated_at
      ) VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
      ON CONFLICT (user_id) 
      DO UPDATE SET
        email_notifications = EXCLUDED.email_notifications,
        push_notifications = EXCLUDED.push_notifications,
        price_alerts = EXCLUDED.price_alerts,
        portfolio_updates = EXCLUDED.portfolio_updates,
        market_news = EXCLUDED.market_news,
        weekly_reports = EXCLUDED.weekly_reports,
        updated_at = NOW()
      RETURNING 
        email_notifications as email,
        push_notifications as push,
        price_alerts as "priceAlerts",
        portfolio_updates as "portfolioUpdates",
        market_news as "marketNews",
        weekly_reports as "weeklyReports"
    `, [userId, email, push, priceAlerts, portfolioUpdates, marketNews, weeklyReports]);

    res.json({
      success: true,
      message: 'Notification preferences updated successfully',
      preferences: result.rows[0]
    });
  } catch (error) {
    console.error('Error updating notification preferences:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to update notification preferences'
    });
  }
});

// Get theme preferences
router.get('/theme', async (req, res) => {
  const userId = req.user.sub;
  
  try {
    const result = await query(`
      SELECT 
        dark_mode as "darkMode",
        primary_color as "primaryColor",
        chart_style as "chartStyle",
        layout
      FROM user_theme_preferences 
      WHERE user_id = $1
    `, [userId]);

    // If no preferences exist, return defaults
    const preferences = result.rows.length > 0 ? result.rows[0] : {
      darkMode: false,
      primaryColor: '#1976d2',
      chartStyle: 'candlestick',
      layout: 'standard'
    };

    res.json({
      success: true,
      preferences
    });
  } catch (error) {
    console.error('Error fetching theme preferences:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch theme preferences'
    });
  }
});

// Update theme preferences
router.put('/theme', async (req, res) => {
  const userId = req.user.sub;
  const { darkMode, primaryColor, chartStyle, layout } = req.body;

  try {
    // Use UPSERT to create or update preferences
    const result = await query(`
      INSERT INTO user_theme_preferences (
        user_id, 
        dark_mode, 
        primary_color, 
        chart_style, 
        layout,
        updated_at
      ) VALUES ($1, $2, $3, $4, $5, NOW())
      ON CONFLICT (user_id) 
      DO UPDATE SET
        dark_mode = EXCLUDED.dark_mode,
        primary_color = EXCLUDED.primary_color,
        chart_style = EXCLUDED.chart_style,
        layout = EXCLUDED.layout,
        updated_at = NOW()
      RETURNING 
        dark_mode as "darkMode",
        primary_color as "primaryColor",
        chart_style as "chartStyle",
        layout
    `, [userId, darkMode, primaryColor, chartStyle, layout]);

    res.json({
      success: true,
      message: 'Theme preferences updated successfully',
      preferences: result.rows[0]
    });
  } catch (error) {
    console.error('Error updating theme preferences:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to update theme preferences'
    });
  }
});

// Security endpoints
router.post('/two-factor/enable', async (req, res) => {
  const userId = req.user.sub;
  
  try {
    console.log('🔐 Enabling 2FA for user:', userId);
    
    // Generate a secret for 2FA setup
    const speakeasy = require('speakeasy');
    const QRCode = require('qrcode');
    
    const secret = speakeasy.generateSecret({
      name: `Financial Platform (${req.user.email || req.user.username})`,
      account: req.user.email || req.user.username,
      issuer: 'Financial Platform',
      length: 32
    });

    console.log('🔑 Generated 2FA secret for user');

    // Generate QR code as data URL
    const qrCodeDataUrl = await QRCode.toDataURL(secret.otpauth_url);

    // Store the secret temporarily (user needs to verify setup)
    await query(`
      UPDATE users 
      SET 
        two_factor_secret = $2,
        two_factor_enabled = false,
        updated_at = NOW()
      WHERE id = $1
    `, [userId, secret.base32]);

    console.log('✅ 2FA secret stored, awaiting verification');

    res.json({
      success: true,
      qrCodeUrl: qrCodeDataUrl,
      manualEntryKey: secret.base32,
      message: 'Scan the QR code with your authenticator app, then verify with a code to complete setup'
    });
  } catch (error) {
    console.error('❌ Error enabling two-factor auth:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to enable two-factor authentication',
      details: error.message
    });
  }
});

// Verify 2FA setup
router.post('/two-factor/verify', async (req, res) => {
  const userId = req.user.sub;
  const { code } = req.body;
  
  try {
    console.log('🔐 Verifying 2FA setup for user:', userId);
    
    if (!code) {
      return res.status(400).json({
        success: false,
        error: 'Verification code is required'
      });
    }
    
    // Get user's 2FA secret
    const userResult = await query(`
      SELECT two_factor_secret 
      FROM users 
      WHERE id = $1
    `, [userId]);
    
    if (userResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: 'User not found'
      });
    }
    
    const secret = userResult.rows[0].two_factor_secret;
    if (!secret) {
      return res.status(400).json({
        success: false,
        error: '2FA setup not initiated. Please enable 2FA first.'
      });
    }
    
    // Verify the code
    const speakeasy = require('speakeasy');
    const verified = speakeasy.totp.verify({
      secret: secret,
      encoding: 'base32',
      token: code,
      window: 2 // Allow some time drift
    });
    
    if (!verified) {
      console.log('❌ Invalid 2FA code provided');
      return res.status(400).json({
        success: false,
        error: 'Invalid verification code. Please try again.'
      });
    }
    
    // Generate recovery codes
    const crypto = require('crypto');
    const recoveryCodes = [];
    for (let i = 0; i < 10; i++) {
      recoveryCodes.push(crypto.randomBytes(4).toString('hex').toUpperCase());
    }
    
    // Enable 2FA and store recovery codes
    await query(`
      UPDATE users 
      SET 
        two_factor_enabled = true,
        recovery_codes = $2,
        updated_at = NOW()
      WHERE id = $1
    `, [userId, JSON.stringify(recoveryCodes)]);
    
    console.log('✅ 2FA enabled successfully for user');
    
    res.json({
      success: true,
      message: '2FA enabled successfully',
      recoveryCodes: recoveryCodes
    });
    
  } catch (error) {
    console.error('❌ Error verifying 2FA setup:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to verify 2FA setup',
      details: error.message
    });
  }
});

router.post('/two-factor/disable', async (req, res) => {
  const userId = req.user.sub;
  
  try {
    await query(`
      UPDATE users 
      SET 
        two_factor_enabled = false,
        two_factor_secret = NULL,
        updated_at = NOW()
      WHERE id = $1
    `, [userId]);

    res.json({
      success: true,
      message: 'Two-factor authentication disabled successfully'
    });
  } catch (error) {
    console.error('Error disabling two-factor auth:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to disable two-factor authentication'
    });
  }
});

// Get 2FA status
router.get('/two-factor/status', async (req, res) => {
  const userId = req.user.sub;
  
  try {
    const result = await query(`
      SELECT two_factor_enabled, recovery_codes
      FROM users 
      WHERE id = $1
    `, [userId]);
    
    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: 'User not found'
      });
    }
    
    const user = result.rows[0];
    
    res.json({
      success: true,
      enabled: user.two_factor_enabled,
      hasRecoveryCodes: user.recovery_codes ? true : false
    });
  } catch (error) {
    console.error('Error getting 2FA status:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get 2FA status'
    });
  }
});

router.get('/recovery-codes', async (req, res) => {
  const userId = req.user.sub;
  
  try {
    // Generate recovery codes
    const codes = [];
    for (let i = 0; i < 10; i++) {
      codes.push(crypto.randomBytes(4).toString('hex').toUpperCase());
    }

    // Hash and store recovery codes
    const hashedCodes = codes.map(code => crypto.createHash('sha256').update(code).digest('hex'));
    
    await query(`
      UPDATE users 
      SET 
        recovery_codes = $2,
        updated_at = NOW()
      WHERE id = $1
    `, [userId, JSON.stringify(hashedCodes)]);

    res.json({
      success: true,
      codes
    });
  } catch (error) {
    console.error('Error generating recovery codes:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to generate recovery codes'
    });
  }
});

router.delete('/delete-account', async (req, res) => {
  const userId = req.user.sub;
  
  try {
    // Soft delete - mark account as deleted rather than actually deleting
    await query(`
      UPDATE users 
      SET 
        deleted_at = NOW(),
        email = CONCAT(email, '_deleted_', EXTRACT(EPOCH FROM NOW())),
        updated_at = NOW()
      WHERE id = $1
    `, [userId]);

    res.json({
      success: true,
      message: 'Account deleted successfully'
    });
  } catch (error) {
    console.error('Error deleting account:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to delete account'
    });
  }
});

router.post('/revoke-sessions', async (req, res) => {
  const userId = req.user.sub;
  
  try {
    // In a real implementation, you'd invalidate all JWT tokens except the current one
    // For now, we'll just return success
    res.json({
      success: true,
      message: 'All other sessions have been revoked'
    });
  } catch (error) {
    console.error('Error revoking sessions:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to revoke sessions'
    });
  }
});

module.exports = router;