const apiKeyService = require('./apiKeyService');
const AlpacaService = require('./alpacaService');
const { query } = require('./database');
const logger = require('./logger');

class ApiKeyValidationService {
  constructor() {
    this.validationCache = new Map();
    this.cacheTimeout = 5 * 60 * 1000; // 5 minutes
  }

  // Real-time API key validation with detailed status reporting
  async validateApiKey(userId, provider, apiKeyId = null) {
    const requestId = `val-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    const startTime = Date.now();
    
    try {
      logger.info(`🔐 [${requestId}] Starting API key validation`, {
        userId: userId ? `${userId.substring(0, 8)}...` : 'unknown',
        provider,
        apiKeyId,
        timestamp: new Date().toISOString()
      });

      // Check cache first
      const cacheKey = `${userId}-${provider}-${apiKeyId || 'default'}`;
      if (this.validationCache.has(cacheKey)) {
        const cached = this.validationCache.get(cacheKey);
        if (Date.now() - cached.timestamp < this.cacheTimeout) {
          logger.info(`⚡ [${requestId}] Using cached validation result`, {
            cacheAge: Date.now() - cached.timestamp,
            result: cached.result.isValid
          });
          return cached.result;
        }
      }

      // Get API key credentials
      const credentials = await apiKeyService.getDecryptedApiKey(userId, provider);
      if (!credentials) {
        const result = {
          isValid: false,
          status: 'NOT_FOUND',
          message: 'No API key found for provider',
          provider,
          timestamp: new Date().toISOString(),
          validationTime: Date.now() - startTime
        };
        
        logger.warn(`❌ [${requestId}] API key not found`, { result });
        return result;
      }

      // Validate based on provider
      let validationResult;
      switch (provider.toLowerCase()) {
        case 'alpaca':
          validationResult = await this.validateAlpacaApiKey(credentials, requestId);
          break;
        default:
          validationResult = {
            isValid: false,
            status: 'UNSUPPORTED_PROVIDER',
            message: `Provider ${provider} is not supported for validation`,
            provider,
            timestamp: new Date().toISOString(),
            validationTime: Date.now() - startTime
          };
      }

      // Cache the result
      this.validationCache.set(cacheKey, {
        result: validationResult,
        timestamp: Date.now()
      });

      // Update database with validation result
      await this.updateValidationStatus(credentials.id, validationResult);

      logger.info(`✅ [${requestId}] API key validation completed`, {
        isValid: validationResult.isValid,
        status: validationResult.status,
        totalTime: Date.now() - startTime
      });

      return validationResult;
    } catch (error) {
      const result = {
        isValid: false,
        status: 'VALIDATION_ERROR',
        message: 'Validation service error',
        error: error.message,
        provider,
        timestamp: new Date().toISOString(),
        validationTime: Date.now() - startTime
      };

      logger.error(`❌ [${requestId}] API key validation failed`, {
        error: error.message,
        errorStack: error.stack,
        totalTime: Date.now() - startTime
      });

      return result;
    }
  }

  // Alpaca-specific validation
  async validateAlpacaApiKey(credentials, requestId) {
    const startTime = Date.now();
    
    try {
      logger.info(`🔧 [${requestId}] Initializing Alpaca validation`, {
        provider: credentials.provider,
        isSandbox: credentials.isSandbox,
        hasSecret: !!credentials.apiSecret
      });

      const alpaca = new AlpacaService(credentials.apiKey, credentials.apiSecret, credentials.isSandbox);
      
      // Test connection by fetching account info
      const accountStart = Date.now();
      const account = await alpaca.getAccount();
      const accountTime = Date.now() - accountStart;
      
      if (!account || !account.id) {
        return {
          isValid: false,
          status: 'INVALID_CREDENTIALS',
          message: 'Invalid API credentials - no account data returned',
          provider: 'alpaca',
          environment: credentials.isSandbox ? 'sandbox' : 'live',
          timestamp: new Date().toISOString(),
          validationTime: Date.now() - startTime,
          connectionTime: accountTime
        };
      }

      // Validate account status
      const accountStatus = account.status;
      const isAccountActive = accountStatus === 'ACTIVE';
      
      // Get additional account metrics
      const portfolioValue = parseFloat(account.portfolio_value || account.equity || 0);
      const buyingPower = parseFloat(account.buying_power || 0);
      const daytradeCount = account.daytradeCount || 0;
      const patternDayTrader = account.pattern_day_trader || false;

      // Test positions access
      let positionsAccess = false;
      try {
        const positionsStart = Date.now();
        const positions = await alpaca.getPositions();
        positionsAccess = true;
        logger.info(`📊 [${requestId}] Positions access verified`, {
          positionsCount: positions ? positions.length : 0,
          accessTime: Date.now() - positionsStart
        });
      } catch (posError) {
        logger.warn(`⚠️ [${requestId}] Positions access limited`, {
          error: posError.message
        });
      }

      // Test orders access
      let ordersAccess = false;
      try {
        const ordersStart = Date.now();
        const orders = await alpaca.getOrders({ limit: 1, status: 'all' });
        ordersAccess = true;
        logger.info(`📋 [${requestId}] Orders access verified`, {
          accessTime: Date.now() - ordersStart
        });
      } catch (ordError) {
        logger.warn(`⚠️ [${requestId}] Orders access limited`, {
          error: ordError.message
        });
      }

      const result = {
        isValid: isAccountActive,
        status: isAccountActive ? 'VALID' : 'ACCOUNT_INACTIVE',
        message: isAccountActive ? 'API key is valid and account is active' : `Account status: ${accountStatus}`,
        provider: 'alpaca',
        environment: credentials.isSandbox ? 'sandbox' : 'live',
        timestamp: new Date().toISOString(),
        validationTime: Date.now() - startTime,
        connectionTime: accountTime,
        accountInfo: {
          id: account.id,
          status: accountStatus,
          portfolioValue,
          buyingPower,
          daytradeCount,
          patternDayTrader,
          currency: account.currency || 'USD',
          createdAt: account.created_at,
          accountBlocked: account.account_blocked || false,
          tradingBlocked: account.trading_blocked || false
        },
        permissions: {
          positionsAccess,
          ordersAccess,
          accountAccess: true
        },
        compliance: {
          patternDayTrader,
          daytradeCount,
          accountBlocked: account.account_blocked || false,
          tradingBlocked: account.trading_blocked || false
        }
      };

      logger.info(`✅ [${requestId}] Alpaca validation completed`, {
        isValid: result.isValid,
        accountStatus,
        portfolioValue,
        permissions: result.permissions,
        totalTime: Date.now() - startTime
      });

      return result;
    } catch (error) {
      logger.error(`❌ [${requestId}] Alpaca validation failed`, {
        error: error.message,
        errorCode: error.code,
        errorStack: error.stack,
        validationTime: Date.now() - startTime
      });

      // Determine error type
      let status = 'VALIDATION_ERROR';
      let message = 'Validation service error';
      
      if (error.message.includes('authentication') || error.message.includes('unauthorized')) {
        status = 'INVALID_CREDENTIALS';
        message = 'Invalid API credentials';
      } else if (error.message.includes('network') || error.message.includes('timeout')) {
        status = 'NETWORK_ERROR';
        message = 'Network connection error';
      } else if (error.message.includes('rate limit')) {
        status = 'RATE_LIMITED';
        message = 'API rate limit exceeded';
      }

      return {
        isValid: false,
        status,
        message,
        error: error.message,
        provider: 'alpaca',
        environment: credentials.isSandbox ? 'sandbox' : 'live',
        timestamp: new Date().toISOString(),
        validationTime: Date.now() - startTime
      };
    }
  }

  // Update validation status in database
  async updateValidationStatus(apiKeyId, validationResult) {
    try {
      await query(`
        UPDATE user_api_keys 
        SET 
          validation_status = $2,
          validation_message = $3,
          last_validated = NOW(),
          validation_details = $4
        WHERE id = $1
      `, [
        apiKeyId,
        validationResult.status,
        validationResult.message,
        JSON.stringify({
          isValid: validationResult.isValid,
          validationTime: validationResult.validationTime,
          accountInfo: validationResult.accountInfo || null,
          permissions: validationResult.permissions || null,
          compliance: validationResult.compliance || null,
          timestamp: validationResult.timestamp
        })
      ]);
    } catch (error) {
      logger.error('Failed to update validation status in database', {
        error: error.message,
        apiKeyId
      });
    }
  }

  // Get validation status for user's API keys
  async getValidationStatus(userId, provider = null) {
    try {
      const whereClause = provider 
        ? 'WHERE user_id = $1 AND provider = $2 AND is_active = true'
        : 'WHERE user_id = $1 AND is_active = true';
      
      const params = provider ? [userId, provider] : [userId];
      
      const result = await query(`
        SELECT 
          id,
          provider,
          description,
          is_sandbox as "isSandbox",
          validation_status as "validationStatus",
          validation_message as "validationMessage",
          validation_details as "validationDetails",
          last_validated as "lastValidated",
          last_used as "lastUsed",
          created_at as "createdAt"
        FROM user_api_keys 
        ${whereClause}
        ORDER BY created_at DESC
      `, params);

      return result.rows.map(row => ({
        ...row,
        validationDetails: row.validationDetails ? JSON.parse(row.validationDetails) : null
      }));
    } catch (error) {
      logger.error('Failed to get validation status', {
        error: error.message,
        userId: userId ? `${userId.substring(0, 8)}...` : 'unknown',
        provider
      });
      return [];
    }
  }

  // Validate all API keys for a user
  async validateAllUserApiKeys(userId) {
    try {
      const apiKeys = await this.getValidationStatus(userId);
      const results = [];

      for (const key of apiKeys) {
        const result = await this.validateApiKey(userId, key.provider, key.id);
        results.push({
          ...key,
          currentValidation: result
        });
      }

      return results;
    } catch (error) {
      logger.error('Failed to validate all user API keys', {
        error: error.message,
        userId: userId ? `${userId.substring(0, 8)}...` : 'unknown'
      });
      return [];
    }
  }

  // Clear validation cache
  clearCache(userId = null, provider = null) {
    if (userId && provider) {
      const cacheKey = `${userId}-${provider}`;
      this.validationCache.delete(cacheKey);
    } else if (userId) {
      // Clear all cache entries for user
      for (const [key] of this.validationCache) {
        if (key.startsWith(`${userId}-`)) {
          this.validationCache.delete(key);
        }
      }
    } else {
      // Clear all cache
      this.validationCache.clear();
    }
  }
}

module.exports = new ApiKeyValidationService();