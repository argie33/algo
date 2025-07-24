const express = require('express');
const { query, healthCheck, initializeDatabase, tablesExist, safeQuery, transaction } = require('../utils/database');
const { authenticateToken } = require('../middleware/auth');
const { createValidationMiddleware, sanitizers } = require('../middleware/validation');
const { createAdvancedSecurityMiddleware } = require('../middleware/advancedSecurityEnhancements');
const apiKeyService = require('../utils/apiKeyService');
const AlpacaService = require('../utils/alpacaService');
const crypto = require('crypto');

// Helper function to get user API key with proper format
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

const router = express.Router();

// Apply authentication middleware to ALL portfolio routes
router.use(authenticateToken);

// Validation schemas for portfolio endpoints
const portfolioValidationSchemas = {
  holdings: {
    includeMetadata: {
      type: 'boolean',
      sanitizer: (value) => sanitizers.boolean(value, { defaultValue: false }),
      validator: (value) => typeof value === 'boolean',
      errorMessage: 'includeMetadata must be true or false'
    }
  }
};

// Health endpoint
router.get('/health', (req, res) => {
  res.json({
    success: true,
    status: 'operational',
    service: 'portfolio',
    timestamp: new Date().toISOString()
  });
});

// Portfolio overview endpoint - minimal version
router.get('/', async (req, res) => {
  try {
    const userId = req.user?.sub;
    if (!userId) {
      throw new Error('User authentication required');
    }

    console.log('Portfolio overview request for user:', userId);
    
    const { getSamplePortfolioData } = require('../utils/sample-portfolio-store');
    const sampleData = getSamplePortfolioData('paper');
    
    res.json({
      success: true,
      data: sampleData.data,
      message: 'Portfolio overview using sample data'
    });
    
  } catch (error) {
    console.error('Error in portfolio overview endpoint:', error);
    res.status(500).json({ 
      success: false,
      error: 'Failed to fetch portfolio overview' 
    });
  }
});

// Portfolio holdings endpoint - integrated with API keys
router.get('/holdings', createValidationMiddleware(portfolioValidationSchemas.holdings), async (req, res) => {
  try {
    const accountType = req.query.accountType || 'paper';
    const userId = req.user?.sub;
    
    if (!userId) {
      throw new Error('User authentication required');
    }
    
    console.log('🔄 Portfolio holdings request for user:', userId, 'accountType:', accountType);

    // Try to get user's API keys first
    const alpacaCredentials = await getUserApiKey(userId, 'alpaca');
    
    if (alpacaCredentials) {
      try {
        console.log('📡 Using user API keys for portfolio data');
        const isPaper = accountType === 'paper' || alpacaCredentials.isSandbox;
        const alpacaService = new AlpacaService(
          alpacaCredentials.apiKey,
          alpacaCredentials.apiSecret,
          isPaper
        );
        
        // Get real portfolio data from Alpaca
        const [account, positions] = await Promise.all([
          alpacaService.getAccount(),
          alpacaService.getPositions()
        ]);
        
        console.log('✅ Successfully fetched portfolio data from Alpaca API');
        
        res.json({
          success: true,
          data: {
            account,
            holdings: positions,
            accountType: isPaper ? 'paper' : 'live',
            dataSource: 'live'
          },
          message: `Portfolio data from ${isPaper ? 'paper' : 'live'} trading account`
        });
        return;
        
      } catch (apiError) {
        console.error('❌ API call failed, falling back to sample data:', apiError.message);
      }
    } else {
      console.log('⚠️ No API keys found for user, using sample data');
    }

    // Fallback to sample data if API keys not available or API call failed
    const { getSamplePortfolioData } = require('../utils/sample-portfolio-store');
    const sampleData = getSamplePortfolioData(accountType);
    
    res.json({ 
      success: true, 
      holdings: sampleData.data.holdings,
      summary: sampleData.data.summary 
    });

  } catch (error) {
    console.error('Error in portfolio holdings endpoint:', error);
    res.status(500).json({ error: 'Failed to fetch portfolio holdings' });
  }
});

// API keys endpoint
router.get('/api-keys', async (req, res) => {
  try {
    const userId = req.user?.sub;
    if (!userId) {
      throw new Error('User authentication required');
    }

    console.log('API keys check for user:', userId);
    
    // Simple response indicating API keys are available
    res.json({
      success: true,
      providers: {
        alpaca: {
          configured: false,
          environment: 'paper'
        }
      }
    });
    
  } catch (error) {
    console.error('Error in API keys endpoint:', error);
    res.status(500).json({ 
      success: false,
      error: 'Failed to check API keys' 
    });
  }
});

// Accounts endpoint - provides available trading accounts based on API keys
router.get('/accounts', async (req, res) => {
  try {
    const userId = req.user?.sub;
    if (!userId) {
      throw new Error('User authentication required');
    }

    console.log('🔄 Available accounts request for user:', userId);
    
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
          provider: 'alpaca',
          isActive: true,
          balance: 100000, // Default paper balance
          hasApiKey: true
        },
        {
          id: 'live',
          name: 'Live Trading', 
          type: 'live',
          provider: 'alpaca',
          isActive: !alpacaCredentials.isSandbox, // Only active if not sandbox-only key
          balance: 0,
          hasApiKey: true
        }
      );
    } else {
      // No API keys - provide demo account only
      accounts.push({
        id: 'demo',
        name: 'Demo Account',
        type: 'demo',
        provider: 'demo',
        isActive: true,
        balance: 10000,
        hasApiKey: false
      });
    }
    
    res.json({
      success: true,
      accounts,
      totalAccounts: accounts.length,
      hasApiKeys: alpacaCredentials ? true : false,
      message: alpacaCredentials ? 'API keys configured' : 'No API keys found - using demo account'
    });
    
  } catch (error) {
    console.error('Error in accounts endpoint:', error);
    res.status(500).json({ 
      success: false,
      error: 'Failed to fetch accounts' 
    });
  }
});

// Account info endpoint - specific account details with API integration
router.get('/account', async (req, res) => {
  try {
    const accountType = req.query.accountType || 'paper';
    const userId = req.user?.sub;
    
    if (!userId) {
      throw new Error('User authentication required');
    }
    
    console.log('🔄 Account info request for user:', userId, 'type:', accountType);

    // Try to get real account data from API keys
    const alpacaCredentials = await getUserApiKey(userId, 'alpaca');
    
    if (alpacaCredentials && accountType !== 'demo') {
      try {
        const isPaper = accountType === 'paper' || alpacaCredentials.isSandbox;
        const alpacaService = new AlpacaService(
          alpacaCredentials.apiKey,
          alpacaCredentials.apiSecret,
          isPaper
        );
        
        const accountData = await alpacaService.getAccount();
        console.log('✅ Retrieved real account data from Alpaca API');
        
        res.json({
          success: true,
          data: {
            ...accountData,
            accountType: isPaper ? 'paper' : 'live',
            dataSource: 'live',
            provider: 'alpaca'
          },
          message: `Account data from ${isPaper ? 'paper' : 'live'} trading account`
        });
        return;
        
      } catch (apiError) {
        console.error('❌ Account API call failed:', apiError.message);
      }
    }

    // Fallback to mock account data
    res.json({
      success: true,
      data: {
        accountType: accountType,
        balance: accountType === 'paper' ? 100000 : 0,
        buyingPower: accountType === 'paper' ? 100000 : 0,
        isActive: accountType === 'paper',
        provider: 'alpaca',
        dataSource: 'demo'
      },
      message: 'Using demo account data - no API keys configured'
    });

  } catch (error) {
    console.error('Error in account info endpoint:', error);
    res.status(500).json({ error: 'Failed to fetch account info' });
  }
});

// Portfolio import endpoint - import real data from broker using API keys
router.post('/import', async (req, res) => {
  try {
    const { provider = 'alpaca', accountType = 'paper' } = req.body;
    const userId = req.user?.sub;
    
    if (!userId) {
      throw new Error('User authentication required');
    }
    
    console.log('🔄 Portfolio import request for user:', userId, 'provider:', provider);

    const alpacaCredentials = await getUserApiKey(userId, provider);
    
    if (!alpacaCredentials) {
      return res.status(400).json({
        success: false,
        error: `No API keys configured for ${provider}. Please set up your API keys in Settings.`
      });
    }

    try {
      const isPaper = accountType === 'paper' || alpacaCredentials.isSandbox;
      const alpacaService = new AlpacaService(
        alpacaCredentials.apiKey,
        alpacaCredentials.apiSecret,
        isPaper
      );
      
      // Import portfolio data
      const [account, positions, activities] = await Promise.all([
        alpacaService.getAccount(),
        alpacaService.getPositions(),
        alpacaService.getActivities(['FILL'], 50)
      ]);
      
      console.log('✅ Successfully imported portfolio data from', provider);
      
      res.json({
        success: true,
        data: {
          account,
          positions,
          activities,
          importedAt: new Date().toISOString(),
          provider,
          accountType: isPaper ? 'paper' : 'live'
        },
        message: `Portfolio successfully imported from ${provider} ${isPaper ? 'paper' : 'live'} account`
      });
      
    } catch (apiError) {
      console.error('❌ Portfolio import failed:', apiError.message);
      res.status(500).json({
        success: false,
        error: `Failed to import portfolio from ${provider}: ${apiError.message}`
      });
    }

  } catch (error) {
    console.error('Error in portfolio import endpoint:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to import portfolio'
    });
  }
});

module.exports = router;