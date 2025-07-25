/**
 * Enhanced Portfolio Routes with Complete Alpaca Integration
 * Replaces portfolio.js with full database integration and real-time sync
 */

const express = require('express');
const { authenticateToken } = require('../middleware/auth');
const { createValidationMiddleware, sanitizers } = require('../middleware/validation');
const AlpacaService = require('../utils/alpacaService');
const portfolioDb = require('../utils/portfolioDatabaseService');
const portfolioSyncService = require('../utils/portfolioSyncService');
const apiKeyService = require('../utils/apiKeyService');

const router = express.Router();

// Apply authentication to ALL portfolio routes
router.use(authenticateToken);

// Validation schemas for portfolio endpoints
const portfolioValidationSchemas = {
  holdings: {
    includeMetadata: {
      type: 'boolean',
      sanitizer: (value) => sanitizers.boolean(value, { defaultValue: false }),
      validator: (value) => typeof value === 'boolean',
      errorMessage: 'includeMetadata must be true or false'
    },
    accountType: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { defaultValue: 'paper' }),
      validator: (value) => ['paper', 'live'].includes(value),
      errorMessage: 'accountType must be paper or live'
    },
    force: {
      type: 'boolean',
      sanitizer: (value) => sanitizers.boolean(value, { defaultValue: false }),
      validator: (value) => typeof value === 'boolean',
      errorMessage: 'force must be true or false'
    }
  }
};

// Helper function to get user API key with proper error handling
const getUserApiKey = async (userId, provider) => {
  try {
    const credentials = await apiKeyService.getApiKey(userId, provider);
    if (!credentials) {
      return null;
    }
    
    return {
      apiKey: credentials.keyId,
      apiSecret: credentials.secretKey,
      isSandbox: credentials.version === '1.0' // Default to sandbox for v1.0
    };
  } catch (error) {
    console.error(`Failed to get API key for ${provider}:`, error);
    return null;
  }
};

// Helper function to get sample data fallback
const getSamplePortfolioData = (accountType) => {
  const { getSamplePortfolioData } = require('../utils/sample-portfolio-store');
  return getSamplePortfolioData(accountType);
};

/**
 * Portfolio Health Check
 * GET /api/portfolio/health
 */
router.get('/health', (req, res) => {
  res.json({
    success: true,
    status: 'operational',
    service: 'portfolio-enhanced',
    timestamp: new Date().toISOString(),
    features: {
      alpacaIntegration: true,
      databaseStorage: true,
      realTimeSync: true,
      circuitBreaker: true
    }
  });
});

/**
 * Portfolio Holdings with Enhanced Integration
 * GET /api/portfolio/holdings
 */
router.get('/holdings', createValidationMiddleware(portfolioValidationSchemas.holdings), async (req, res) => {
  const startTime = Date.now();
  const userId = req.user?.sub;
  const { accountType = 'paper', force = false, includeMetadata = false } = req.query;
  
  if (!userId) {
    return res.status(401).json({
      success: false,
      error: 'User authentication required'
    });
  }
  
  console.log(`🔄 Enhanced portfolio holdings request for user ${userId}, account: ${accountType}, force: ${force}`);

  try {
    // 1. Try to get fresh cached data first (unless force refresh)
    if (!force) {
      const cachedData = await portfolioDb.getCachedPortfolioData(userId, accountType);
      
      if (cachedData && !portfolioDb.isDataStale(cachedData, 5 * 60 * 1000)) {
        console.log(`✅ Returning fresh cached data for user ${userId}`);
        return res.json({
          success: true,
          data: cachedData,
          source: 'database',
          responseTime: Date.now() - startTime,
          message: 'Portfolio data from cache'
        });
      }
    }

    // 2. Check if user has API keys
    const alpacaCredentials = await getUserApiKey(userId, 'alpaca');
    
    if (!alpacaCredentials) {
      console.log(`⚠️ No API keys found for user ${userId}, returning empty portfolio state`);
      
      return res.json({
        success: true,
        data: {
          account: {
            equity: 0,
            cash: 0,
            buying_power: 0,
            portfolio_value: 0,
            account_number: null,
            status: 'not_configured'
          },
          holdings: [],
          summary: {
            total_equity: 0,
            total_positions: 0,
            total_unrealized_pl: 0,
            total_unrealized_plpc: 0,
            portfolio_performance: {
              day_change: 0,
              day_change_percent: 0
            }
          },
          accountType: 'none',
          lastUpdated: new Date().toISOString()
        },
        source: 'empty',
        responseTime: Date.now() - startTime,
        message: 'No portfolio data available - configure Alpaca API keys to view your portfolio',
        actionRequired: {
          action: 'configure_api_keys',
          description: 'Add your Alpaca API keys in Settings to access enhanced portfolio features',
          url: '/settings',
          features: [
            'Real-time portfolio sync',
            'Advanced performance analytics',
            'Portfolio rebalancing tools',
            'Risk analysis and recommendations'
          ]
        }
      });
    }

    // 3. Sync portfolio data from Alpaca
    console.log(`📡 Syncing portfolio data from Alpaca for user ${userId}`);
    
    try {
      const syncResult = await portfolioSyncService.syncUserPortfolio(userId, {
        force,
        accountType
      });

      // 4. Get the freshly synced data
      const freshData = await portfolioDb.getCachedPortfolioData(userId, accountType);
      
      if (freshData) {
        console.log(`✅ Successfully synced and retrieved portfolio data for user ${userId}`);
        return res.json({
          success: true,
          data: freshData,
          source: 'alpaca',
          responseTime: Date.now() - startTime,
          syncInfo: {
            syncId: syncResult.syncId,
            duration: syncResult.duration,
            recordsUpdated: syncResult.result?.summary?.totalRecordsProcessed || 0
          },
          message: `Portfolio data synced from ${accountType} account`
        });
      }

    } catch (syncError) {
      console.error(`❌ Portfolio sync failed for user ${userId}:`, syncError);
      
      // 5. Try to return stale cached data if sync fails
      const staleData = await portfolioDb.getCachedPortfolioData(userId, accountType);
      if (staleData) {
        console.log(`📋 Returning stale cached data for user ${userId} due to sync failure`);
        return res.json({
          success: true,
          data: staleData,
          source: 'database_stale',
          responseTime: Date.now() - startTime,
          warning: 'Data may be outdated due to sync failure',
          syncError: syncError.message,
          message: 'Portfolio data from cache (sync failed)'
        });
      }

      // 6. Final fallback to empty state
      console.log(`⚠️ All data sources failed for user ${userId}, returning empty state`);
      
      return res.json({
        success: true,
        data: {
          account: {
            equity: 0,
            cash: 0,
            buying_power: 0,
            portfolio_value: 0,
            account_number: null,
            status: 'sync_failed'
          },
          holdings: [],
          summary: {
            total_equity: 0,
            total_positions: 0,
            total_unrealized_pl: 0,
            total_unrealized_plpc: 0,
            portfolio_performance: {
              day_change: 0,
              day_change_percent: 0
            }
          },
          accountType: accountType,
          lastUpdated: new Date().toISOString()
        },
        source: 'empty_fallback',
        responseTime: Date.now() - startTime,
        error: 'Portfolio sync failed - unable to retrieve data',
        syncError: syncError.message,
        message: 'Portfolio sync failed - please try again or contact support',
        actionRequired: {
          action: 'retry_or_contact_support',
          description: 'Portfolio sync failed. Try refreshing or check API key configuration.',
          suggestions: [
            'Refresh the page to retry sync',
            'Check your Alpaca API key configuration',
            'Verify your internet connection',
            'Contact support if the issue persists'
          ]
        }
      });
    }

  } catch (error) {
    console.error(`❌ Error in enhanced portfolio holdings endpoint for user ${userId}:`, error);
    
    // Emergency fallback to sample data
    try {
      const sampleData = getSamplePortfolioData(accountType);
      return res.json({
        success: true,
        data: sampleData.data,
        source: 'sample_emergency',
        responseTime: Date.now() - startTime,
        warning: 'System error, showing sample data',
        error: error.message,
        message: 'Portfolio data from sample data (system error)'
      });
    } catch (fallbackError) {
      console.error(`❌ Even sample data fallback failed:`, fallbackError);
      return res.status(500).json({
        success: false,
        error: 'Failed to retrieve portfolio data',
        details: error.message,
        responseTime: Date.now() - startTime
      });
    }
  }
});

/**
 * Portfolio Sync Endpoint
 * POST /api/portfolio/sync
 */
router.post('/sync', async (req, res) => {
  const startTime = Date.now();
  const userId = req.user?.sub;
  const { force = false, accountType = 'paper' } = req.body;
  
  if (!userId) {
    return res.status(401).json({
      success: false,
      error: 'User authentication required'
    });
  }

  console.log(`🔄 Manual portfolio sync requested for user ${userId}, account: ${accountType}, force: ${force}`);

  try {
    // Check if user has API keys
    const alpacaCredentials = await getUserApiKey(userId, 'alpaca');
    
    if (!alpacaCredentials) {
      return res.status(400).json({
        success: false,
        error: 'No API keys configured',
        message: 'Please configure your Alpaca API keys in settings before syncing'
      });
    }

    // Perform the sync
    const syncResult = await portfolioSyncService.syncUserPortfolio(userId, {
      force,
      accountType
    });

    console.log(`✅ Manual sync completed for user ${userId}`);
    
    res.json({
      success: true,
      message: 'Portfolio synchronized successfully',
      syncInfo: {
        syncId: syncResult.syncId,
        duration: syncResult.duration,
        recordsUpdated: syncResult.result?.summary?.totalRecordsProcessed || 0,
        conflictsResolved: syncResult.result?.summary?.totalConflictsResolved || 0
      },
      responseTime: Date.now() - startTime
    });

  } catch (error) {
    console.error(`❌ Manual sync failed for user ${userId}:`, error);
    
    res.status(500).json({
      success: false,
      error: 'Portfolio sync failed',
      details: error.message,
      responseTime: Date.now() - startTime
    });
  }
});

/**
 * Portfolio Sync Status
 * GET /api/portfolio/sync-status
 */
router.get('/sync-status', async (req, res) => {
  const userId = req.user?.sub;
  
  if (!userId) {
    return res.status(401).json({
      success: false,
      error: 'User authentication required'
    });
  }

  try {
    const syncStatus = await portfolioSyncService.getSyncStatus(userId);
    
    res.json({
      success: true,
      syncStatus: syncStatus || { status: 'never_synced' },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error(`❌ Error getting sync status for user ${userId}:`, error);
    
    res.status(500).json({
      success: false,
      error: 'Failed to get sync status',
      details: error.message
    });
  }
});

/**
 * API Keys Status for Portfolio
 * GET /api/portfolio/api-keys
 */
router.get('/api-keys', async (req, res) => {
  const userId = req.user?.sub;
  
  if (!userId) {
    return res.status(401).json({
      success: false,
      error: 'User authentication required'
    });
  }

  console.log(`🔍 API keys check for user ${userId}`);
  
  try {
    // Check API key availability
    const alpacaCredentials = await getUserApiKey(userId, 'alpaca');
    
    const response = {
      success: true,
      data: alpacaCredentials ? [
        {
          id: 'alpaca-key',
          provider: 'alpaca',
          isActive: true,
          environment: alpacaCredentials.isSandbox ? 'paper' : 'live',
          configured: true
        }
      ] : [],
      providers: {
        alpaca: {
          configured: !!alpacaCredentials,
          environment: alpacaCredentials?.isSandbox ? 'paper' : 'live'
        }
      }
    };

    console.log(`✅ API keys status for user ${userId}: ${response.data.length} keys found`);
    res.json(response);
    
  } catch (error) {
    console.error(`❌ Error checking API keys for user ${userId}:`, error);
    
    res.status(500).json({ 
      success: false,
      error: 'Failed to check API keys',
      details: error.message
    });
  }
});

/**
 * Available Trading Accounts
 * GET /api/portfolio/accounts
 */
router.get('/accounts', async (req, res) => {
  const userId = req.user?.sub;
  
  if (!userId) {
    return res.status(401).json({
      success: false,
      error: 'User authentication required'
    });
  }

  console.log(`📊 Available accounts request for user ${userId}`);
  
  try {
    // Check if user has API keys configured
    const alpacaCredentials = await getUserApiKey(userId, 'alpaca');
    
    const accounts = [];
    
    if (alpacaCredentials) {
      // User has API keys - provide both paper and live options
      accounts.push(
        {
          id: 'paper',
          name: 'Paper Trading',
          type: 'paper',
          description: 'Virtual trading with real market data',
          available: true,
          provider: 'alpaca'
        },
        {
          id: 'live',
          name: 'Live Trading',
          type: 'live',
          description: 'Real money trading account',
          available: !alpacaCredentials.isSandbox, // Only available if not sandbox-only
          provider: 'alpaca'
        }
      );
    } else {
      // No API keys - only demo account available
      accounts.push({
        id: 'demo',
        name: 'Demo Account',
        type: 'demo',
        description: 'Sample portfolio data for demonstration',
        available: true,
        provider: 'sample'
      });
    }

    res.json({
      success: true,
      accounts,
      message: alpacaCredentials 
        ? 'Trading accounts available based on your API key configuration'
        : 'Configure API keys to access live trading accounts'
    });
    
  } catch (error) {
    console.error(`❌ Error getting accounts for user ${userId}:`, error);
    
    res.status(500).json({ 
      success: false,
      error: 'Failed to get available accounts',
      details: error.message
    });
  }
});

/**
 * Portfolio Performance History
 * GET /api/portfolio/performance
 */
router.get('/performance', async (req, res) => {
  const userId = req.user?.sub;
  const { days = 30 } = req.query;
  
  if (!userId) {
    return res.status(401).json({
      success: false,
      error: 'User authentication required'
    });
  }

  try {
    const performanceHistory = await portfolioDb.getPerformanceHistory(
      userId, 
      parseInt(days)
    );

    res.json({
      success: true,
      data: performanceHistory,
      period: `${days} days`,
      message: `Portfolio performance history for ${days} days`
    });

  } catch (error) {
    console.error(`❌ Error getting performance history for user ${userId}:`, error);
    
    res.status(500).json({
      success: false,
      error: 'Failed to get performance history',
      details: error.message
    });
  }
});

module.exports = router;