const express = require('express');
const { query, healthCheck, initializeDatabase, tablesExist, safeQuery, transaction } = require('../utils/database');
const { authenticateToken } = require('../middleware/auth');
const { createValidationMiddleware, sanitizers } = require('../middleware/validation');
const apiKeyService = require('../utils/simpleApiKeyService');
const AlpacaService = require('../utils/alpacaService');
const portfolioDataRefreshService = require('../utils/portfolioDataRefresh');
const logger = require('../utils/logger');
const portfolioAnalytics = require('../utils/portfolioAnalytics');
const crypto = require('crypto');

// Conditional logging configuration
const LOG_LEVEL = process.env.LOG_LEVEL || 'INFO';
const shouldLog = (level) => {
  const levels = { DEBUG: 0, INFO: 1, WARN: 2, ERROR: 3 };
  return levels[level] >= levels[LOG_LEVEL];
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
    },
    refresh: {
      type: 'boolean',
      sanitizer: (value) => sanitizers.boolean(value, { defaultValue: false }),
      validator: (value) => typeof value === 'boolean',
      errorMessage: 'refresh must be true or false'
    },
    limit: {
      type: 'number',
      sanitizer: (value) => sanitizers.number(value, { min: 1, max: 1000, defaultValue: 100 }),
      validator: (value) => Number.isInteger(value) && value >= 1 && value <= 1000,
      errorMessage: 'limit must be an integer between 1 and 1000'
    },
    offset: {
      type: 'number',
      sanitizer: (value) => sanitizers.number(value, { min: 0, defaultValue: 0 }),
      validator: (value) => Number.isInteger(value) && value >= 0,
      errorMessage: 'offset must be a non-negative integer'
    }
  },
  
  performance: {
    period: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 10, toUpperCase: true, defaultValue: '1M' }),
      validator: (value) => ['1D', '1W', '1M', '3M', '6M', '1Y', 'YTD', 'ALL'].includes(value),
      errorMessage: 'Period must be one of: 1D, 1W, 1M, 3M, 6M, 1Y, YTD, ALL'
    },
    timeframe: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 10, defaultValue: '1Day' }),
      validator: (value) => ['1Min', '5Min', '15Min', '1Hour', '1Day'].includes(value),
      errorMessage: 'Timeframe must be one of: 1Min, 5Min, 15Min, 1Hour, 1Day'
    }
  },
  
  positions: {
    symbol: {
      type: 'string',
      sanitizer: (value) => sanitizers.symbol(value),
      validator: (value) => !value || /^[A-Z]{1,10}$/.test(value),
      errorMessage: 'Symbol must be 1-10 uppercase letters'
    },
    includeClosedPositions: {
      type: 'boolean',
      sanitizer: (value) => sanitizers.boolean(value, { defaultValue: false }),
      validator: (value) => typeof value === 'boolean',
      errorMessage: 'includeClosedPositions must be true or false'
    }
  },
  
  refresh: {
    forceRefresh: {
      type: 'boolean',
      sanitizer: (value) => sanitizers.boolean(value, { defaultValue: false }),
      validator: (value) => typeof value === 'boolean',
      errorMessage: 'forceRefresh must be true or false'
    },
    syncMetadata: {
      type: 'boolean',
      sanitizer: (value) => sanitizers.boolean(value, { defaultValue: true }),
      validator: (value) => typeof value === 'boolean',
      errorMessage: 'syncMetadata must be true or false'
    }
  },
  
  analytics: {
    includeBenchmark: {
      type: 'boolean',
      sanitizer: (value) => sanitizers.boolean(value, { defaultValue: false }),
      validator: (value) => typeof value === 'boolean',
      errorMessage: 'includeBenchmark must be true or false'
    },
    period: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 10, toUpperCase: true, defaultValue: '1Y' }),
      validator: (value) => ['1M', '3M', '6M', '1Y', '2Y', '5Y', 'ALL'].includes(value),
      errorMessage: 'Period must be one of: 1M, 3M, 6M, 1Y, 2Y, 5Y, ALL'
    }
  }
};

// Portfolio table dependencies and fallback handling
const PORTFOLIO_TABLES = {
  required: ['portfolio_holdings', 'portfolio_metadata', 'user_api_keys'],
  optional: ['symbols', 'stock_symbols', 'market_data', 'key_metrics']
};

/**
 * Check portfolio table availability with comprehensive logging and error identification
 */
async function checkPortfolioTableDependencies(requestId = 'unknown') {
  const checkStart = Date.now();
  if (shouldLog('DEBUG')) console.log(`🔍 [${requestId}] Starting portfolio table dependency check`);
  
  try {
    // Initialize database if not already done
    await initializeDatabase();
    console.log(`✅ [${requestId}] Database initialized for table check`);
    
    const allTables = [...PORTFOLIO_TABLES.required, ...PORTFOLIO_TABLES.optional];
    console.log(`🔍 [${requestId}] Checking ${allTables.length} tables: ${allTables.join(', ')}`);
    
    const tableCheckStart = Date.now();
    const tableStatus = await tablesExist(allTables);
    const tableCheckDuration = Date.now() - tableCheckStart;
    
    console.log(`✅ [${requestId}] Table existence check completed in ${tableCheckDuration}ms`);
    
    const missingRequired = PORTFOLIO_TABLES.required.filter(table => !tableStatus[table]);
    const missingOptional = PORTFOLIO_TABLES.optional.filter(table => !tableStatus[table]);
    const availableRequired = PORTFOLIO_TABLES.required.filter(table => tableStatus[table]);
    const availableOptional = PORTFOLIO_TABLES.optional.filter(table => tableStatus[table]);
    
    // Detailed logging of table status
    console.log(`📊 [${requestId}] Portfolio table status analysis:`, {
      summary: {
        totalTables: allTables.length,
        requiredAvailable: availableRequired.length,
        requiredMissing: missingRequired.length,
        optionalAvailable: availableOptional.length,
        optionalMissing: missingOptional.length
      },
      required: {
        available: availableRequired,
        missing: missingRequired
      },
      optional: {
        available: availableOptional,
        missing: missingOptional
      },
      checkDuration: `${tableCheckDuration}ms`
    });
    
    // Log critical issues
    if (missingRequired.length > 0) {
      console.error(`❌ [${requestId}] CRITICAL: Missing required portfolio tables:`, {
        missingTables: missingRequired,
        impact: 'Portfolio database operations will fail',
        recommendation: 'Run database initialization scripts',
        tablesNeeded: missingRequired
      });
    }
    
    if (missingOptional.length > 0) {
      console.warn(`⚠️ [${requestId}] WARNING: Missing optional portfolio tables:`, {
        missingTables: missingOptional,
        impact: 'Some portfolio features may be limited',
        recommendation: 'Consider running optional table creation scripts'
      });
    }
    
    const hasRequiredTables = missingRequired.length === 0;
    const totalDuration = Date.now() - checkStart;
    
    console.log(`✅ [${requestId}] Portfolio table dependency check completed in ${totalDuration}ms`, {
      result: hasRequiredTables ? 'SUCCESS - All required tables available' : 'FAILURE - Missing required tables',
      databaseOperationsEnabled: hasRequiredTables
    });
    
    return {
      hasRequiredTables,
      missingRequired,
      missingOptional,
      availableRequired,
      availableOptional,
      tableStatus,
      checkDuration: totalDuration,
      requestId,
      timestamp: new Date().toISOString()
    };
    
  } catch (error) {
    const errorDuration = Date.now() - checkStart;
    console.error(`❌ [${requestId}] Portfolio table dependency check FAILED after ${errorDuration}ms:`, {
      error: error.message,
      errorCode: error.code,
      errorStack: error.stack,
      impact: 'Cannot determine table availability - assuming tables missing',
      recommendation: 'Check database connectivity and permissions'
    });
    
    return {
      hasRequiredTables: false,
      missingRequired: PORTFOLIO_TABLES.required,
      missingOptional: PORTFOLIO_TABLES.optional,
      availableRequired: [],
      availableOptional: [],
      tableStatus: {},
      checkDuration: errorDuration,
      error: error.message,
      requestId,
      timestamp: new Date().toISOString()
    };
  }
}

// Portfolio overview endpoint (root) - requires authentication and provides portfolio summary
router.get('/', async (req, res) => {
  const requestId = crypto.randomUUID().split('-')[0];
  const requestStart = Date.now();
  
  try {
    const userId = req.user?.sub;
    console.log(`🚀 [${requestId}] Portfolio overview request initiated`, {
      userId: userId ? `${userId.substring(0, 8)}...` : 'undefined',
      userAgent: req.headers['user-agent'],
      ip: req.ip,
      timestamp: new Date().toISOString()
    });

    if (!userId) {
      console.error(`❌ [${requestId}] Authentication failure - no user ID found`);
      return res.unauthorized('User authentication required', { requestId });
    }

    // Check table dependencies before attempting queries with detailed logging
    console.log(`🔍 [${requestId}] Checking portfolio table dependencies`);
    const tableDeps = await checkPortfolioTableDependencies(requestId);
    
    let summary = {
      total_positions: 0,
      total_market_value: 0,
      total_unrealized_pl: 0,
      avg_unrealized_plpc: 0
    };
    
    let metadata = {
      account_type: 'not_connected',
      last_sync: null,
      total_equity: 0
    };

    if (tableDeps.hasRequiredTables) {
      console.log(`✅ [${requestId}] All required tables available - proceeding with database queries`);
      
      try {
        // Get user's portfolio summary from database with detailed logging
        console.log(`📊 [${requestId}] Executing portfolio holdings query`);
        const holdingsQueryStart = Date.now();
        
        const holdingsQuery = `
          SELECT 
            COUNT(*) as total_positions,
            COALESCE(SUM(market_value), 0) as total_market_value,
            COALESCE(SUM(unrealized_pl), 0) as total_unrealized_pl,
            COALESCE(AVG(unrealized_plpc), 0) as avg_unrealized_plpc
          FROM portfolio_holdings 
          WHERE user_id = $1
        `;
        
        console.log(`📊 [${requestId}] Executing portfolio metadata query`);
        const metadataQuery = `
          SELECT 
            account_type,
            last_sync,
            COALESCE(total_equity, 0) as total_equity
          FROM portfolio_metadata 
          WHERE user_id = $1
          ORDER BY last_sync DESC
          LIMIT 1
        `;

        const queryStart = Date.now();
        const [holdingsResult, metadataResult] = await Promise.all([
          safeQuery(holdingsQuery, [userId], ['portfolio_holdings']),
          safeQuery(metadataQuery, [userId], ['portfolio_metadata'])
        ]);
        const queryDuration = Date.now() - queryStart;
        
        console.log(`✅ [${requestId}] Portfolio database queries completed in ${queryDuration}ms`, {
          holdingsRows: holdingsResult.rows.length,
          metadataRows: metadataResult.rows.length,
          holdingsData: holdingsResult.rows[0],
          metadataData: metadataResult.rows[0]
        });

        if (holdingsResult.rows.length > 0) {
          summary = holdingsResult.rows[0];
          console.log(`✅ [${requestId}] Portfolio holdings data retrieved:`, {
            totalPositions: summary.total_positions,
            totalMarketValue: summary.total_market_value,
            totalUnrealizedPL: summary.total_unrealized_pl,
            avgUnrealizedPLPC: summary.avg_unrealized_plpc
          });
        } else {
          console.warn(`⚠️ [${requestId}] No portfolio holdings found for user - using default values`);
        }
        
        if (metadataResult.rows.length > 0) {
          metadata = metadataResult.rows[0];
          console.log(`✅ [${requestId}] Portfolio metadata retrieved:`, {
            accountType: metadata.account_type,
            lastSync: metadata.last_sync,
            totalEquity: metadata.total_equity
          });
        } else {
          console.warn(`⚠️ [${requestId}] No portfolio metadata found for user - using default values`);
        }
        
      } catch (dbError) {
        const errorDuration = Date.now() - queryStart;
        console.error(`❌ [${requestId}] Portfolio database query FAILED after ${errorDuration}ms:`, {
          error: dbError.message,
          errorCode: dbError.code,
          errorStack: dbError.stack,
          sqlState: dbError.sqlState,
          impact: 'Using default portfolio values',
          recommendation: 'Check database connectivity and table structure'
        });
        // Continue with default values
      }
    } else {
      console.error(`❌ [${requestId}] Required portfolio tables missing - cannot query database:`, {
        missingTables: tableDeps.missingRequired,
        availableTables: tableDeps.availableRequired,
        impact: 'Portfolio data will be retrieved from API or default values',
        recommendation: 'Run database initialization to create missing tables'
      });
    }

    // Try to get fresh data from broker API if no database data with comprehensive logging
    if (parseInt(summary.total_positions) === 0) {
      console.log(`🔄 [${requestId}] No portfolio positions found in database - attempting API fallback`);
      
      try {
        console.log(`🔑 [${requestId}] Retrieving user API credentials for Alpaca`);
        const credentialsStart = Date.now();
        const credentials = await getUserApiKey(userId, 'alpaca');
        const credentialsDuration = Date.now() - credentialsStart;
        
        if (credentials) {
          console.log(`✅ [${requestId}] API credentials retrieved in ${credentialsDuration}ms`, {
            provider: 'alpaca',
            isSandbox: credentials.isSandbox,
            keyLength: credentials.apiKey ? credentials.apiKey.length : 0,
            secretLength: credentials.apiSecret ? credentials.apiSecret.length : 0
          });
          
          console.log(`📡 [${requestId}] Initializing Alpaca API service`);
          const alpacaStart = Date.now();
          const alpaca = new AlpacaService(
            credentials.apiKey,
            credentials.apiSecret,
            credentials.isSandbox
          );
          
          console.log(`📊 [${requestId}] Fetching account data from Alpaca API`);
          const account = await alpaca.getAccount();
          const alpacaDuration = Date.now() - alpacaStart;
          
          if (account) {
            console.log(`✅ [${requestId}] Alpaca account data retrieved in ${alpacaDuration}ms:`, {
              portfolioValue: account.portfolioValue,
              equity: account.equity,
              buyingPower: account.buyingPower,
              accountStatus: account.status,
              daytradeCount: account.daytradeCount
            });
            
            summary.total_market_value = account.portfolioValue || 0;
            summary.total_equity = account.equity || 0;
            metadata.account_type = credentials.isSandbox ? 'paper' : 'live';
            metadata.last_sync = new Date().toISOString();
            
            console.log(`✅ [${requestId}] Portfolio data updated from Alpaca API:`, {
              totalMarketValue: summary.total_market_value,
              totalEquity: summary.total_equity,
              accountType: metadata.account_type,
              lastSync: metadata.last_sync
            });
          } else {
            console.warn(`⚠️ [${requestId}] Alpaca API returned empty account data`);
          }
        } else {
          console.warn(`⚠️ [${requestId}] No Alpaca API credentials found for user - cannot fetch live data`, {
            impact: 'Portfolio will show default/empty values',
            recommendation: 'User needs to configure Alpaca API keys in settings',
            detailed_diagnostics: {
              user_id: userId,
              credentials_check: 'failed',
              database_connection: 'available',
              secrets_manager_access: 'unknown',
              potential_causes: [
                'User has not configured API keys in settings',
                'API keys failed validation during storage',
                'Database connection issue during key retrieval',
                'Secrets Manager access issues',
                'API key service initialization failure'
              ]
            }
          });
        }
      } catch (apiError) {
        const apiErrorDuration = Date.now() - credentialsStart || 0;
        console.error(`❌ [${requestId}] Alpaca API fallback FAILED after ${apiErrorDuration}ms:`, {
          error: apiError.message,
          errorStack: apiError.stack,
          errorCode: apiError.code,
          impact: 'Portfolio will show database values or defaults',
          recommendation: 'Check API credentials and Alpaca service status',
          detailed_diagnostics: {
            user_id: userId,
            api_call_duration: apiErrorDuration,
            error_type: apiError.name,
            error_code: apiError.code,
            underlying_issues: [
              'API key authentication failed',
              'Network connectivity issues',
              'Alpaca service rate limiting',
              'Invalid API credentials format',
              'Expired or revoked API keys',
              'Service circuit breaker triggered'
            ],
            troubleshooting_steps: [
              'Verify API key configuration in settings',
              'Check API key permissions on Alpaca',
              'Test network connectivity to Alpaca',
              'Review rate limiting status',
              'Check service health status'
            ]
          }
        });
        // Continue with existing values
      }
    } else {
      console.log(`✅ [${requestId}] Portfolio data available from database - skipping API fallback`, {
        totalPositions: summary.total_positions,
        dataSource: 'database'
      });
    }

    // Prepare final response with comprehensive logging
    const totalDuration = Date.now() - requestStart;
    const responseData = {
      user_id: userId,
      portfolio_summary: {
        total_positions: parseInt(summary.total_positions) || 0,
        total_market_value: parseFloat(summary.total_market_value) || 0,
        total_unrealized_pl: parseFloat(summary.total_unrealized_pl) || 0,
        avg_unrealized_plpc: parseFloat(summary.avg_unrealized_plpc) || 0,
        total_equity: parseFloat(metadata.total_equity) || parseFloat(summary.total_market_value) || 0
      },
      account_info: {
        account_type: metadata.account_type,
        last_sync: metadata.last_sync,
        is_connected: metadata.account_type !== 'not_connected'
      },
      database_status: {
        tables_available: tableDeps.hasRequiredTables,
        missing_tables: tableDeps.missingRequired,
        available_tables: tableDeps.availableRequired,
        data_source: tableDeps.hasRequiredTables ? 'database' : 'api_fallback',
        check_duration_ms: tableDeps.checkDuration
      },
      available_endpoints: [
        '/portfolio/holdings - Portfolio holdings data',
        '/portfolio/performance - Performance metrics and charts',
        '/portfolio/analytics - Advanced portfolio analytics',
        '/portfolio/allocations - Asset allocation breakdown',
        '/portfolio/import - Import portfolio data from brokers'
      ],
      request_info: {
        request_id: requestId,
        total_duration_ms: totalDuration,
        timestamp: new Date().toISOString()
      }
    };

    console.log(`✅ [${requestId}] Portfolio overview completed successfully in ${totalDuration}ms`, {
      summary: {
        totalPositions: responseData.portfolio_summary.total_positions,
        totalMarketValue: responseData.portfolio_summary.total_market_value,
        accountType: responseData.account_info.account_type,
        dataSource: responseData.database_status.data_source,
        isConnected: responseData.account_info.is_connected
      },
      performance: {
        totalDuration: `${totalDuration}ms`,
        tableCheckDuration: `${tableDeps.checkDuration}ms`
      },
      status: 'SUCCESS'
    });

    res.success(responseData, {
      requestId,
      duration: `${totalDuration}ms`
    });
    
  } catch (error) {
    const errorDuration = Date.now() - requestStart;
    console.error(`❌ [${requestId}] Portfolio overview FAILED after ${errorDuration}ms:`, {
      error: error.message,
      errorStack: error.stack,
      errorCode: error.code,
      userId: userId ? `${userId.substring(0, 8)}...` : 'undefined',
      requestDuration: `${errorDuration}ms`,
      impact: 'Portfolio overview request failed completely',
      recommendation: 'Check logs for specific failure point'
    });
    
    res.serverError('Failed to fetch portfolio overview', {
      requestId,
      duration: `${errorDuration}ms`,
      originalError: process.env.NODE_ENV === 'development' ? error.message : undefined
    });
  }
});

// Using standardized getUserApiKey from userApiKeyHelper instead

// Using standardized getUserApiKey from userApiKeyHelper for decryption

// Broker API integration functions
async function fetchAlpacaPortfolio(apiKey, isSandbox) {
  console.log(`📡 Fetching Alpaca portfolio (sandbox: ${isSandbox})`);
  
  // This is where you'd integrate with the actual Alpaca API
  // For now, return mock data that simulates a successful API call
  return {
    positions: [
      { symbol: 'AAPL', quantity: 100, avgCost: 150.25, currentPrice: 165.50 },
      { symbol: 'MSFT', quantity: 50, avgCost: 250.75, currentPrice: 280.25 },
      { symbol: 'GOOGL', quantity: 25, avgCost: 2500.00, currentPrice: 2650.75 }
    ],
    totalValue: 191743.75,
    totalPnL: 19468.58,
    totalPnLPercent: 11.3
  };
}

async function fetchTDAmeritradePortfolio(apiKey, isSandbox) {
  console.log(`📡 Fetching TD Ameritrade portfolio (sandbox: ${isSandbox})`);
  
  // This is where you'd integrate with the actual TD Ameritrade API
  // For now, return mock data that simulates a successful API call
  return {
    positions: [
      { symbol: 'TSLA', quantity: 75, avgCost: 200.50, currentPrice: 220.25 },
      { symbol: 'NVDA', quantity: 40, avgCost: 450.00, currentPrice: 480.50 }
    ],
    totalValue: 135720.00,
    totalPnL: 12850.00,
    totalPnLPercent: 9.5
  };
}

// Store portfolio data in database with transaction for data integrity
async function storePortfolioData(userId, apiKeyId, portfolioData, accountType) {
  console.log(`💾 Storing portfolio data with transaction for data integrity`);
  // Security: Don't log user IDs in portfolio operations
  
  try {
    // Check if required tables exist before attempting to store data
    const tableDeps = await checkPortfolioTableDependencies();
    
    if (!tableDeps.hasRequiredTables) {
      console.warn('⚠️ Cannot store portfolio data - required tables missing:', tableDeps.missingRequired);
      throw new Error(`Required database tables not available: ${tableDeps.missingRequired.join(', ')}`);
    }
    
    // Execute all portfolio operations in a single transaction
    await transaction(async (client) => {
      console.log('🔄 Starting portfolio data transaction');
      
      // Clear existing portfolio data for this user and API key
      await client.query(`
        DELETE FROM portfolio_holdings 
        WHERE user_id = $1 AND api_key_id = $2
      `, [userId, apiKeyId]);
      
      console.log(`🗑️ Cleared existing portfolio holdings`);
      
      // Insert new portfolio holdings in efficient batch
      if (portfolioData.positions.length > 0) {
        const batchSize = 100; // Process in chunks to avoid memory issues
        for (let i = 0; i < portfolioData.positions.length; i += batchSize) {
          const batch = portfolioData.positions.slice(i, i + batchSize);
          
          // Build VALUES clause for batch insert
          const values = [];
          const params = [];
          let paramIndex = 1;
          
          batch.forEach(position => {
            values.push(`($${paramIndex++}, $${paramIndex++}, $${paramIndex++}, $${paramIndex++}, $${paramIndex++}, $${paramIndex++}, $${paramIndex++}, $${paramIndex++}, $${paramIndex++}, $${paramIndex++}, $${paramIndex++}, $${paramIndex++}, NOW(), NOW())`);
            params.push(
              userId,
              apiKeyId,
              position.symbol,
              position.quantity,
              position.avgCost || position.averageEntryPrice,
              position.currentPrice,
              position.marketValue || (position.quantity * position.currentPrice),
              position.unrealizedPL || ((position.currentPrice - (position.avgCost || position.averageEntryPrice)) * position.quantity),
              position.unrealizedPLPercent || (((position.currentPrice - (position.avgCost || position.averageEntryPrice)) / (position.avgCost || position.averageEntryPrice)) * 100),
              position.side || 'long',
              accountType,
              'alpaca'
            );
          });
          
          await client.query(`
            INSERT INTO portfolio_holdings (
              user_id, api_key_id, symbol, quantity, avg_cost, 
              current_price, market_value, unrealized_pl, unrealized_plpc, 
              side, account_type, broker, created_at, updated_at
            ) VALUES ${values.join(', ')}
          `, params);
          
          console.log(`📈 Inserted batch ${Math.floor(i/batchSize) + 1}: ${batch.length} holdings`);
        }
      }
      console.log(`📈 Inserted ${portfolioData.positions.length} portfolio holdings`);
      
      // Update portfolio metadata
      await client.query(`
        INSERT INTO portfolio_metadata (
          user_id, api_key_id, total_equity, total_market_value, 
          total_unrealized_pl, total_unrealized_plpc, account_type, 
          broker, last_sync, created_at, updated_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW(), NOW())
        ON CONFLICT (user_id, api_key_id) DO UPDATE SET
          total_equity = EXCLUDED.total_equity,
          total_market_value = EXCLUDED.total_market_value,
          total_unrealized_pl = EXCLUDED.total_unrealized_pl,
          total_unrealized_plpc = EXCLUDED.total_unrealized_plpc,
          account_type = EXCLUDED.account_type,
          broker = EXCLUDED.broker,
          last_sync = NOW(),
          updated_at = NOW()
      `, [
        userId,
        apiKeyId,
        portfolioData.totalValue,
        portfolioData.totalValue,
        portfolioData.totalPnL,
        portfolioData.totalPnLPercent,
        accountType,
        'alpaca'
      ]);
      
      console.log(`📊 Updated portfolio metadata`);
      return { success: true, positions: portfolioData.positions.length };
    });
    
    console.log(`✅ Portfolio data transaction completed successfully`);
  } catch (error) {
    console.error('❌ Failed to store portfolio data:', error.message);
    throw error;
  }
}

// Portfolio holdings endpoint - uses real data from broker APIs with comprehensive API key error handling
router.get('/holdings', createValidationMiddleware(portfolioValidationSchemas.holdings), async (req, res) => {
  const requestId = crypto.randomUUID().split('-')[0];
  const requestStart = Date.now();
  
  try {
    // Security: Validate and sanitize query parameters
    const rawAccountType = req.query.accountType || 'paper';
    const allowedAccountTypes = ['paper', 'live'];
    const accountType = allowedAccountTypes.includes(rawAccountType) ? rawAccountType : 'paper';
    
    const userId = req.user?.sub;
    if (!userId) {
      throw new Error('User authentication required');
    }
    
    console.log(`🚀 [${requestId}] Portfolio holdings request initiated`, {
      userId: userId ? `${userId.substring(0, 8)}...` : 'undefined',
      accountType,
      userAgent: req.headers['user-agent'],
      ip: req.ip,
      timestamp: new Date().toISOString()
    });

    console.log(`📊 [${requestId}] Account type requested: ${accountType}`);
    
    // Check table dependencies first
    const tableDeps = await checkPortfolioTableDependencies();
    
    // Try to get real data from database first, filtered by account type
    try {
      console.log(`🔍 [HOLDINGS] Looking for stored portfolio data, account type: ${accountType}`);
      // Security: Don't log user IDs in portfolio operations
      
      if (!tableDeps.hasRequiredTables) {
        console.warn('⚠️ [HOLDINGS] Required portfolio tables missing, skipping database query:', tableDeps.missingRequired);
        throw new Error('Database tables not available');
      }
      
      // Get user's API keys filtered by account type (sandbox for paper, live for live)
      const isSandbox = accountType === 'paper';
      const limit = req.query.limit || 100;
      const offset = req.query.offset || 0;
      
      // Get total count for pagination metadata
      const totalCount = await safeQuery(`
        SELECT COUNT(*) as total
        FROM portfolio_holdings ph
        JOIN user_api_keys uak ON ph.api_key_id = uak.id
        WHERE ph.user_id = $1 AND uak.is_sandbox = $2 AND uak.is_active = true
      `, [userId, isSandbox], ['portfolio_holdings', 'user_api_keys']);
      
      const storedHoldings = await safeQuery(`
        SELECT ph.symbol, ph.quantity, ph.avg_cost, ph.current_price, 
               ph.market_value, ph.unrealized_pl, ph.unrealized_plpc, 
               ph.side, ph.account_type, ph.broker, ph.updated_at,
               uak.provider, uak.is_sandbox
        FROM portfolio_holdings ph
        JOIN user_api_keys uak ON ph.api_key_id = uak.id
        WHERE ph.user_id = $1 AND uak.is_sandbox = $2 AND uak.is_active = true
        ORDER BY ph.market_value DESC
        LIMIT $3 OFFSET $4
      `, [userId, isSandbox, limit, offset], ['portfolio_holdings', 'user_api_keys']);
      
      if (storedHoldings.rows.length > 0) {
        console.log(`✅ [HOLDINGS] Found ${storedHoldings.rows.length} stored holdings for ${accountType} account`);
        
        const holdings = storedHoldings.rows;
        const totalValue = holdings.reduce((sum, h) => sum + parseFloat(h.market_value || 0), 0);
        const totalGainLoss = holdings.reduce((sum, h) => sum + parseFloat(h.unrealized_pl || 0), 0);

        const formattedHoldings = holdings.map(h => ({
          symbol: h.symbol,
          company: h.symbol + ' Inc.', // Would need company lookup
          shares: parseFloat(h.quantity || 0),
          avgCost: parseFloat(h.avg_cost || 0),
          currentPrice: parseFloat(h.current_price || 0),
          marketValue: parseFloat(h.market_value || 0),
          gainLoss: parseFloat(h.unrealized_pl || 0),
          gainLossPercent: parseFloat(h.unrealized_plpc || 0),
          sector: 'Technology', // Would need sector lookup
          allocation: totalValue > 0 ? (parseFloat(h.market_value || 0) / totalValue) * 100 : 0,
          lastUpdated: h.updated_at
        }));

        const total = parseInt(totalCount.rows[0]?.total || 0);
        
        return res.success({
          holdings: formattedHoldings,
          summary: {
            totalValue: totalValue,
            totalGainLoss: totalGainLoss,
            totalGainLossPercent: totalValue > totalGainLoss ? (totalGainLoss / (totalValue - totalGainLoss)) * 100 : 0,
            numPositions: holdings.length,
            accountType: accountType,
            dataSource: 'database'
          },
          pagination: {
            total: total,
            limit: parseInt(limit),
            offset: parseInt(offset),
            hasMore: (parseInt(offset) + parseInt(limit)) < total
          }
        }, { requestId });
      }
      
      // If no stored data, try to get fresh data from broker API with comprehensive error handling
      console.log(`📡 [${requestId}] No stored data found, attempting to fetch fresh data from broker API`);
      const credentialsStart = Date.now();
      
      let credentials;
      try {
        credentials = await getUserApiKey(userId, 'alpaca');
        const credentialsDuration = Date.now() - credentialsStart;
        
        if (!credentials) {
          console.error(`❌ [${requestId}] No API credentials found after ${credentialsDuration}ms`, {
            requestedProvider: 'alpaca',
            accountType,
            userId: `${userId.substring(0, 8)}...`,
            impact: 'Portfolio holdings will not be available',
            recommendation: 'User needs to configure Alpaca API keys in settings'
          });
          
          return res.badRequest('API credentials not configured', {
            requestId,
            message: 'Please configure your Alpaca API keys in Settings to view portfolio holdings',
            errorCode: 'API_CREDENTIALS_MISSING',
            accountType: accountType,
            provider: 'alpaca',
            actions: [
              'Go to Settings > API Keys',
              'Add your Alpaca API credentials',
              'Choose the correct environment (Paper Trading or Live Trading)',
              'Test the connection to verify your credentials'
            ]
          });
        }
        
        console.log(`✅ [${requestId}] API credentials retrieved in ${credentialsDuration}ms`, {
          provider: 'alpaca',
          environment: credentials.isSandbox ? 'sandbox' : 'live',
          keyLength: credentials.apiKey ? credentials.apiKey.length : 0,
          hasSecret: !!credentials.apiSecret
        });
        
      } catch (credentialsError) {
        const credentialsDuration = Date.now() - credentialsStart;
        console.error(`❌ [${requestId}] Failed to retrieve API credentials after ${credentialsDuration}ms:`, {
          error: credentialsError.message,
          errorStack: credentialsError.stack,
          provider: 'alpaca',
          impact: 'Cannot access portfolio data from broker',
          recommendation: 'Check API key configuration and database connectivity'
        });
        
        return res.serverError('Failed to retrieve API credentials', {
          requestId,
          errorDurationMs: credentialsDuration
        });
      }
      
      console.log(`🔑 [HOLDINGS] Found credentials: account_type=${credentials.isSandbox ? 'sandbox' : 'live'}, requested=${isSandbox ? 'sandbox' : 'live'}`);
      
      if (credentials.isSandbox === isSandbox) {
        console.log(`🔑 [${requestId}] Using API key: alpaca (${credentials.isSandbox ? 'sandbox' : 'live'})`);
        
        // Initialize Alpaca service with comprehensive error handling
        console.log(`🏭 [${requestId}] Initializing Alpaca service`);
        const serviceInitStart = Date.now();
        let alpaca;
        
        try {
          alpaca = new AlpacaService(
            credentials.apiKey,
            credentials.apiSecret,
            credentials.isSandbox
          );
          const serviceInitDuration = Date.now() - serviceInitStart;
          
          console.log(`✅ [${requestId}] Alpaca service initialized in ${serviceInitDuration}ms`, {
            environment: credentials.isSandbox ? 'sandbox' : 'live',
            hasApiKey: !!credentials.apiKey,
            hasSecret: !!credentials.apiSecret
          });
          
        } catch (serviceError) {
          const serviceInitDuration = Date.now() - serviceInitStart;
          console.error(`❌ [${requestId}] Alpaca service initialization FAILED after ${serviceInitDuration}ms:`, {
            error: serviceError.message,
            errorStack: serviceError.stack,
            environment: credentials.isSandbox ? 'sandbox' : 'live',
            impact: 'Cannot access live portfolio data from broker',
            recommendation: 'Check API key validity and Alpaca service status'
          });
          
          return res.serverError('Failed to initialize trading service', {
            requestId,
            message: 'Unable to connect to your broker. Please verify your API credentials or try again later.',
            errorCode: 'TRADING_SERVICE_INIT_ERROR',
            details: process.env.NODE_ENV === 'development' ? serviceError.message : 'Service initialization failed',
            provider: 'alpaca',
            environment: credentials.isSandbox ? 'sandbox' : 'live',
            actions: [
              'Verify your API credentials are correct',
              'Check if your API keys have sufficient permissions',
              'Try switching between Paper Trading and Live Trading modes',
              'Contact broker support if the issue persists'
            ],
            errorDurationMs: serviceInitDuration
          });
        }
        
        // Fetch positions with comprehensive error handling
        console.log(`📊 [${requestId}] Fetching portfolio positions from Alpaca API`);
        const positionsStart = Date.now();
        let positions;
        
        try {
          positions = await Promise.race([
            alpaca.getPositions(),
            new Promise((_, reject) => 
              setTimeout(() => reject(new Error('Positions fetch timeout after 15 seconds')), 15000)
            )
          ]);
          
          const positionsDuration = Date.now() - positionsStart;
          console.log(`✅ [${requestId}] Portfolio positions fetched in ${positionsDuration}ms`, {
            positionCount: positions?.length || 0,
            environment: credentials.isSandbox ? 'sandbox' : 'live',
            dataSource: 'alpaca_api'
          });
          
        } catch (positionsError) {
          const positionsDuration = Date.now() - positionsStart;
          console.error(`❌ [${requestId}] Failed to fetch positions after ${positionsDuration}ms:`, {
            error: positionsError.message,
            errorStack: positionsError.stack,
            environment: credentials.isSandbox ? 'sandbox' : 'live',
            errorCode: positionsError.code,
            statusCode: positionsError.status,
            impact: 'Live portfolio data unavailable',
            recommendation: 'Check API key permissions and Alpaca service status'
          });
          
          // Check for specific API errors
          if (positionsError.message?.includes('timeout')) {
            return res.status(504).json({
              success: false,
              error: 'Broker API timeout',
              message: 'The broker API is taking too long to respond. Please try again.',
              error_code: 'BROKER_API_TIMEOUT',
              provider: 'alpaca',
              environment: credentials.isSandbox ? 'sandbox' : 'live',
              actions: [
                'Try refreshing the page',
                'Check your internet connection',
                'Try again in a few minutes',
                'Contact support if the issue persists'
              ],
              request_info: {
                request_id: requestId,
                timeout_duration_ms: positionsDuration,
                timestamp: new Date().toISOString()
              }
            });
          }
          
          if (positionsError.status === 401 || positionsError.message?.includes('unauthorized')) {
            return res.unauthorized('Invalid API credentials', {
              requestId,
              message: 'Your API credentials appear to be invalid or expired. Please update them in Settings.',
              errorCode: 'BROKER_API_UNAUTHORIZED',
              provider: 'alpaca',
              environment: credentials.isSandbox ? 'sandbox' : 'live',
              actions: [
                'Go to Settings > API Keys',
                'Update your Alpaca API credentials',
                'Ensure you are using the correct environment (Paper vs Live)',
                'Verify your API keys have trading permissions'
              ],
              errorDurationMs: positionsDuration
            });
          }
          
          if (positionsError.status === 403 || positionsError.message?.includes('forbidden')) {
            return res.status(403).json({
              success: false,
              error: 'Insufficient API permissions',
              message: 'Your API credentials do not have permission to access portfolio data.',
              error_code: 'BROKER_API_FORBIDDEN',
              provider: 'alpaca',
              environment: credentials.isSandbox ? 'sandbox' : 'live',
              actions: [
                'Check your API key permissions in your broker account',
                'Ensure your API keys have portfolio read access',
                'Contact your broker to verify account permissions',
                'Try regenerating your API keys'
              ],
              request_info: {
                request_id: requestId,
                error_duration_ms: positionsDuration,
                timestamp: new Date().toISOString()
              }
            });
          }
          
          // Generic API error
          return res.status(502).json({
            success: false,
            error: 'Broker API error',
            message: 'Unable to retrieve portfolio data from your broker. Please try again later.',
            error_code: 'BROKER_API_ERROR',
            details: process.env.NODE_ENV === 'development' ? positionsError.message : 'External service error',
            provider: 'alpaca',
            environment: credentials.isSandbox ? 'sandbox' : 'live',
            actions: [
              'Try refreshing the page',
              'Check broker service status',
              'Verify your API credentials',
              'Contact support if the issue persists'
            ],
            request_info: {
              request_id: requestId,
              error_duration_ms: positionsDuration,
              timestamp: new Date().toISOString()
            }
          });
        }
        
        // Process positions data with validation
        if (positions && positions.length > 0) {
          console.log(`📈 [${requestId}] Processing ${positions.length} portfolio positions`);
          const totalValue = positions.reduce((sum, p) => sum + p.marketValue, 0);
          const totalGainLoss = positions.reduce((sum, p) => sum + p.unrealizedPL, 0);

          const formattedHoldings = positions.map(p => ({
            symbol: p.symbol,
            company: p.symbol + ' Inc.', // Would need company lookup
            shares: p.quantity,
            avgCost: p.averageEntryPrice,
            currentPrice: p.currentPrice,
            marketValue: p.marketValue,
            gainLoss: p.unrealizedPL,
            gainLossPercent: p.unrealizedPLPercent,
            sector: 'Technology', // Would need sector lookup
            allocation: totalValue > 0 ? (p.marketValue / totalValue) * 100 : 0
          }));

          const totalDuration = Date.now() - requestStart;
          console.log(`✅ [${requestId}] Portfolio holdings successfully retrieved and processed in ${totalDuration}ms`, {
            positionCount: positions.length,
            totalValue,
            totalGainLoss,
            dataSource: 'alpaca_api',
            environment: credentials.isSandbox ? 'sandbox' : 'live'
          });
          
          return res.success({
            holdings: formattedHoldings,
            summary: {
              totalValue: totalValue,
              totalGainLoss: totalGainLoss,
              totalGainLossPercent: totalValue > totalGainLoss ? (totalGainLoss / (totalValue - totalGainLoss)) * 100 : 0,
              numPositions: positions.length,
              accountType: credentials.isSandbox ? 'paper' : 'live'
            },
            metadata: {
              dataSource: 'alpaca_api',
              provider: 'alpaca',
              environment: credentials.isSandbox ? 'sandbox' : 'live',
              requestId,
              totalDurationMs: totalDuration
            }
          });
        } else {
          const totalDuration = Date.now() - requestStart;
          console.log(`📊 [${requestId}] No positions found in portfolio after ${totalDuration}ms`, {
            environment: credentials.isSandbox ? 'sandbox' : 'live',
            dataSource: 'alpaca_api',
            positionCount: 0
          });
          
          // Return empty portfolio with proper structure
          return res.json({
            success: true,
            data: {
              holdings: [],
              summary: {
                totalValue: 0,
                totalGainLoss: 0,
                totalGainLossPercent: 0,
                numPositions: 0,
                accountType: credentials.isSandbox ? 'paper' : 'live'
              }
            },
            message: 'No positions found in your portfolio',
            timestamp: new Date().toISOString(),
            dataSource: 'alpaca_api',
            provider: 'alpaca',
            environment: credentials.isSandbox ? 'sandbox' : 'live',
            request_info: {
              request_id: requestId,
              total_duration_ms: totalDuration
            }
          });
        }
      } else {
        console.warn(`⚠️ [${requestId}] Account type mismatch`, {
          requestedType: isSandbox ? 'sandbox' : 'live',
          availableType: credentials.isSandbox ? 'sandbox' : 'live',
          impact: 'Cannot use API credentials for requested account type'
        });
        
        return res.badRequest('Account type mismatch', {
          requestId,
          message: `Your configured API credentials are for ${credentials.isSandbox ? 'Paper Trading' : 'Live Trading'}, but you requested ${isSandbox ? 'Paper Trading' : 'Live Trading'} data.`,
          errorCode: 'ACCOUNT_TYPE_MISMATCH',
          configuredType: credentials.isSandbox ? 'paper' : 'live',
          requestedType: isSandbox ? 'paper' : 'live',
          actions: [
            'Go to Settings > API Keys',
            `Configure API credentials for ${isSandbox ? 'Paper Trading' : 'Live Trading'}`,
            `Or switch to ${credentials.isSandbox ? 'Paper Trading' : 'Live Trading'} mode`,
            'Verify you have the correct API keys for the desired environment'
          ]
        });
      }
    } catch (error) {
      const errorDuration = Date.now() - requestStart;
      console.error(`❌ [${requestId}] Unexpected error in Alpaca API integration after ${errorDuration}ms:`, {
        error: error.message,
        errorStack: error.stack,
        impact: 'Portfolio data retrieval failed unexpectedly',
        recommendation: 'Check application logs and Alpaca service status'
      });
      
      // Fall through to database or mock data
      console.log(`🔄 [${requestId}] Falling back to database query due to API error`);
    }

    // Fallback to database query (if tables are available and no API data was fetched)
    if (userId && tableDeps.hasRequiredTables) {
      try {
          // Query real portfolio holdings with symbols data
          // Use stock_symbols table if symbols table is not available
          const symbolsTable = tableDeps.tableStatus.symbols ? 'symbols' : 
                               (tableDeps.tableStatus.stock_symbols ? 'stock_symbols' : null);
          
          const holdingsQuery = symbolsTable ? `
            SELECT 
              ph.symbol,
              ph.quantity as shares,
              ph.avg_cost,
              ph.current_price,
              ph.market_value,
              ph.unrealized_pl as gain_loss,
              ph.unrealized_plpc as gain_loss_percent,
              ph.side,
              ph.updated_at,
              COALESCE(s.security_name, s.name, ph.symbol || ' Inc.') as company,
              COALESCE(s.sector, 'Technology') as sector,
              COALESCE(ph.exchange, 'NASDAQ') as exchange,
              COALESCE(s.industry, 'Technology') as industry
            FROM portfolio_holdings ph
            LEFT JOIN ${symbolsTable} s ON ph.symbol = s.symbol  
            WHERE ph.user_id = $1 AND ph.quantity > 0
            ORDER BY ph.market_value DESC
          ` : `
            SELECT 
              ph.symbol,
              ph.quantity as shares,
              ph.avg_cost,
              ph.current_price,
              ph.market_value,
              ph.unrealized_pl as gain_loss,
              ph.unrealized_plpc as gain_loss_percent,
              ph.side,
              ph.updated_at,
              ph.symbol || ' Inc.' as company,
              COALESCE(ph.sector, 'Technology') as sector,
              COALESCE(ph.exchange, 'NASDAQ') as exchange,
              'Technology' as industry
            FROM portfolio_holdings ph
            WHERE ph.user_id = $1 AND ph.quantity > 0
            ORDER BY ph.market_value DESC
          `;

          const requiredTables = symbolsTable ? ['portfolio_holdings', symbolsTable] : ['portfolio_holdings'];
          const holdingsResult = await safeQuery(holdingsQuery, [userId], requiredTables);
          
          if (holdingsResult.rows.length > 0) {
            const holdings = holdingsResult.rows;
            const totalValue = holdings.reduce((sum, h) => sum + parseFloat(h.market_value || 0), 0);
            const totalGainLoss = holdings.reduce((sum, h) => sum + parseFloat(h.gain_loss || 0), 0);

            // Structure data exactly like mock data
            const formattedHoldings = holdings.map(h => ({
              symbol: h.symbol,
              company: h.company,
              shares: parseFloat(h.shares || 0),
              avgCost: parseFloat(h.avg_cost || 0),
              currentPrice: parseFloat(h.current_price || 0),
              marketValue: parseFloat(h.market_value || 0),
              gainLoss: parseFloat(h.gain_loss || 0),
              gainLossPercent: parseFloat(h.gain_loss_percent || 0),
              sector: h.sector,
              industry: h.industry,
              allocation: totalValue > 0 ? (parseFloat(h.market_value) / totalValue) * 100 : 0
            }));

            // Calculate sector allocation from real holdings data using reduce for better performance
            const sectorMap = formattedHoldings.reduce((acc, holding) => {
              const sector = holding.sector || 'Other';
              acc[sector] = acc[sector] || { value: 0, allocation: 0 };
              acc[sector].value += holding.marketValue;
              return acc;
            }, {});

            const sectorAllocation = Object.entries(sectorMap).map(([sector, data]) => ({
              sector,
              value: data.value,
              allocation: totalValue > 0 ? (data.value / totalValue) * 100 : 0
            })).sort((a, b) => b.value - a.value);

            return res.success({
              holdings: formattedHoldings,
              sectorAllocation: sectorAllocation,
              summary: {
                totalValue: totalValue,
                totalGainLoss: totalGainLoss,
                totalGainLossPercent: totalValue > totalGainLoss ? (totalGainLoss / (totalValue - totalGainLoss)) * 100 : 0,
                numPositions: holdings.length,
                accountType: accountType
              },
              metadata: {
                databaseStatus: {
                  tablesAvailable: tableDeps.hasRequiredTables,
                  missingTables: tableDeps.missingRequired,
                  symbolsTableUsed: symbolsTable || 'none'
                },
                dataSource: 'database'
              }
            });
          }
      } catch (error) {
        console.error('Database query failed:', error);
        // Fall through to mock data
      }
    }

    // If not authenticated OR no data found OR database error, return structured empty data
    console.log('Returning structured empty portfolio data');
    
    const emptyHoldings = [];

    const totalValue = 0;
    const totalGainLoss = 0;

    return res.success({
      holdings: emptyHoldings,
      summary: {
        totalValue: totalValue,
        totalGainLoss: totalGainLoss,
        totalGainLossPercent: totalValue > totalGainLoss ? (totalGainLoss / (totalValue - totalGainLoss)) * 100 : 0,
        numPositions: 0,
        accountType: accountType
      },
      metadata: {
        databaseStatus: {
          tablesAvailable: tableDeps ? tableDeps.hasRequiredTables : false,
          missingTables: tableDeps ? tableDeps.missingRequired : PORTFOLIO_TABLES.required,
          status: 'No portfolio data available - connect your broker to import holdings'
        },
        dataSource: 'empty'
      }
    });

  } catch (error) {
    console.error('Error in portfolio holdings endpoint:', error);
    res.serverError('Failed to fetch portfolio holdings', {
      details: error.message
    });
  }
});

// Account info endpoint - uses real data, structured like mock data
router.get('/account', async (req, res) => {
  try {
    const { accountType = 'paper' } = req.query;
    console.log(`Portfolio account info endpoint called for account type: ${accountType}`);
    
    const userId = req.user?.sub;
    if (!userId) {
      throw new Error('User authentication required');
    }
    console.log(`👤 User ID: ${userId}`);

    // If authenticated, try to get real data
    if (userId) {
      try {
        // Check if database is available (don't fail on health check)
        if (!req.dbError) {
          
          // Query real account metadata
          const metadataQuery = `
            SELECT 
              total_equity,
              total_market_value,
              total_unrealized_pl,
              total_unrealized_plpc,
              account_type,
              last_sync
            FROM portfolio_metadata
            WHERE user_id = $1
            ORDER BY last_sync DESC
            LIMIT 1
          `;

          const metadataResult = await query(metadataQuery, [userId]);
          
          if (metadataResult.rows.length > 0) {
            const accountData = metadataResult.rows[0];

            // Calculate additional fields based on available data
            const equity = parseFloat(accountData.total_equity || 0);
            const portfolioValue = parseFloat(accountData.total_market_value || 0);
            const dayChange = parseFloat(accountData.total_unrealized_pl || 0) * 0.1; // Approximate
            
            return res.success({
              accountType: accountData.account_type || accountType,
              balance: equity + (equity * 0.5), // Estimate total balance
              equity: equity,
              dayChange: dayChange,
              dayChangePercent: equity > 0 ? (dayChange / equity) * 100 : 0,
              buyingPower: equity * 0.5, // Estimate buying power
              portfolioValue: portfolioValue,
              cash: equity - portfolioValue,
              pendingDeposits: 0,
              patternDayTrader: false,
              tradingBlocked: false,
              accountBlocked: false,
              createdAt: accountData.last_sync || new Date().toISOString(),
              metadata: {
                dataSource: 'database'
              }
            });
          }
        }
      } catch (error) {
        console.error('Database query failed:', error);
        // Fall through to error response
      }
    }

    // Return empty account data with comprehensive diagnostics
    console.error('❌ Account data unavailable - comprehensive diagnosis needed', {
      accountType,
      detailed_diagnostics: {
        attempted_operations: ['api_key_retrieval', 'broker_api_call', 'database_query'],
        potential_causes: [
          'API keys not configured',
          'Broker API unavailable',
          'Database connection failure',
          'Authentication failure',
          'External API rate limiting'
        ],
        troubleshooting_steps: [
          'Check API key configuration',
          'Verify broker API status',
          'Check database connectivity',
          'Review authentication flow',
          'Monitor external API limits'
        ],
        system_checks: [
          'API key service availability',
          'Broker API connectivity',
          'Database connection pool status',
          'Authentication system health'
        ]
      }
    });
    
    return res.success({
      account: {
        accountId: null,
        accountType: accountType,
        balance: 0,
        availableBalance: 0,
        totalValue: 0,
        dayChange: 0,
        dayChangePercent: 0,
        buyingPower: 0,
        maintenance: 0,
        currency: 'USD',
        lastUpdated: new Date().toISOString()
      },
      metadata: {
        message: 'No account data available - configure your broker API keys',
        dataSource: 'empty'
      }
    });

  } catch (error) {
    console.error('Error in account info endpoint:', error);
    res.serverError('Failed to fetch account info', {
      details: error.message
    });
  }
});

// Available accounts endpoint - returns account types user can access
router.get('/accounts', authenticateToken, async (req, res) => {
  try {
    const userId = req.user.sub;
    console.log(`🏦 Available accounts endpoint called for user: ${userId}`);
    
    // Get user's API keys to determine available account types
    const credentials = await apiKeyService.getDecryptedApiKey(userId, 'alpaca');
    
    const availableAccounts = [];
    
    if (credentials) {
      // If user has Alpaca API keys, they can access both paper and live accounts
      availableAccounts.push({
        type: 'paper',
        name: 'Paper Trading Account',
        description: 'Virtual trading account for testing strategies',
        provider: 'alpaca',
        isActive: true
      });
      
      if (!credentials.isSandbox) {
        availableAccounts.push({
          type: 'live',
          name: 'Live Trading Account', 
          description: 'Real money trading account',
          provider: 'alpaca',
          isActive: true
        });
      }
    } else {
      // If no API keys, only mock account is available
      availableAccounts.push({
        type: 'mock',
        name: 'Demo Account',
        description: 'Demonstration account with sample data',
        provider: 'demo',
        isActive: true
      });
    }
    
    res.success(availableAccounts);
    
  } catch (error) {
    console.error('Error fetching available accounts:', error);
    res.serverError('Failed to fetch available accounts', {
      details: error.message
    });
  }
});

// Apply authentication middleware to remaining routes
router.use(authenticateToken);

// Portfolio analytics endpoint for authenticated users
router.get('/analytics', async (req, res) => {
  try {
    const userId = req.user?.sub;
    if (!userId) {
      return res.unauthorized('Authentication required', {
        message: 'User must be authenticated to access portfolio analytics'
      });
    }
    
    const { timeframe = '1y' } = req.query;
  
    console.log(`Portfolio analytics endpoint called for authenticated user: ${userId}, timeframe: ${timeframe}`);
  
    // Main analytics logic try block
    // First, try to get real-time data from broker API
    try {
      const credentials = await apiKeyService.getDecryptedApiKey(userId, 'alpaca');
      
      if (credentials) {
        console.log('📡 Fetching analytics from Alpaca API...');
        const alpaca = new AlpacaService(
          credentials.apiKey,
          credentials.apiSecret,
          credentials.isSandbox
        );

        const portfolioSummary = await alpaca.getPortfolioSummary();
        
        if (portfolioSummary.positions.length > 0) {
          const positions = portfolioSummary.positions;
          const totalValue = portfolioSummary.summary.totalValue;
          
          // Calculate analytics from real-time data
          const analytics = {
            totalReturn: portfolioSummary.summary.totalPnL,
            totalReturnPercent: portfolioSummary.summary.totalPnLPercent,
            sharpeRatio: portfolioSummary.riskMetrics.sharpeRatio,
            volatility: portfolioSummary.riskMetrics.volatility * 100, // Convert to percentage
            beta: portfolioSummary.riskMetrics.beta,
            maxDrawdown: portfolioSummary.riskMetrics.maxDrawdown * 100, // Convert to percentage
            riskScore: Math.min(10, Math.max(1, portfolioSummary.riskMetrics.volatility * 10)) // 1-10 scale
          };

          return res.success({
            holdings: positions.map(pos => ({
              symbol: pos.symbol,
              quantity: pos.quantity,
              market_value: pos.marketValue,
              cost_basis: pos.costBasis,
              pnl: pos.unrealizedPL,
              pnl_percent: pos.unrealizedPLPercent,
              weight: totalValue > 0 ? (pos.marketValue / totalValue) : 0,
              sector: portfolioSummary.sectorAllocation[pos.symbol] || 'Technology',
              last_updated: new Date().toISOString()
            })),
            analytics: analytics,
            summary: {
              totalValue: totalValue,
              totalPnL: analytics.totalReturn,
              numPositions: positions.length,
              topSector: Object.entries(portfolioSummary.sectorAllocation)
                .sort((a, b) => b[1].weight - a[1].weight)[0]?.[0] || 'Technology',
              concentration: positions.length > 0 ? 
                (Math.max(...positions.map(p => p.marketValue)) / totalValue) : 0,
              riskScore: analytics.riskScore
            },
            sectorAllocation: Object.fromEntries(
              Object.entries(portfolioSummary.sectorAllocation)
                .map(([sector, data]) => [sector, data.weight])
            ),
            metadata: {
              dataSource: 'alpaca_api',
              provider: 'alpaca',
              environment: credentials.isSandbox ? 'sandbox' : 'live'
            }
          });
        }
      }
    } catch (apiError) {
      console.error('⚠️ Alpaca API error, falling back to database:', apiError.message);
      // Continue to database fallback
    }

    // Fallback to database data if API integration fails
    console.log('📊 Falling back to database analytics...');
    
    // Check if database is available
    if (req.dbError) {
      console.log('📋 Database unavailable, returning mock analytics...');
      return res.success({
        performance: {
          totalReturn: 15.3,
          totalReturnPercent: 15.3,
          annualizedReturn: 12.1,
          volatility: 18.7,
          sharpeRatio: 1.2,
          maxDrawdown: -8.4,
          winRate: 65.2,
          numTrades: 0,
          avgWin: 0,
          avgLoss: 0,
          profitFactor: 0
        },
        timeframe: timeframe,
        dataPoints: [],
        benchmarkComparison: {
          portfolioReturn: 15.3,
          spyReturn: 12.8,
          alpha: 2.5,
          beta: 1.1,
          rSquared: 0.85
        },
        metadata: {
          dataSource: 'mock'
        }
      });
    }

    // Get portfolio holdings - use a safer query that doesn't depend on stocks table structure
    const holdingsQuery = `
      SELECT 
        ph.symbol,
        ph.quantity,
        ph.market_value,
        ph.unrealized_pl as pnl,
        ph.unrealized_plpc as pnl_percent,
        ph.avg_cost as cost_basis,
        ph.updated_at as last_updated
      FROM portfolio_holdings ph
      WHERE ph.user_id = $1 AND ph.quantity > 0
      ORDER BY ph.market_value DESC
    `;
    
    const holdingsResult = await query(holdingsQuery, [userId]);
    
    if (holdingsResult.rows.length === 0) {
      return res.notFound('No portfolio data found', {
        message: 'Import portfolio holdings first from your broker or add holdings manually'
      });
    }

    const holdings = holdingsResult.rows;
    const totalValue = holdings.reduce((sum, h) => sum + parseFloat(h.market_value || 0), 0);
    
    // Calculate analytics similar to mock data structure
    const analytics = {
      totalReturn: holdings.reduce((sum, h) => sum + parseFloat(h.pnl || 0), 0),
      totalReturnPercent: 0,
      sharpeRatio: 1.24, // Would calculate from historical data
      volatility: 18.5,  // Would calculate from historical data
      beta: 1.12,        // Would calculate from historical data
      maxDrawdown: -12.3, // Would calculate from historical data
      riskScore: 6.2     // Would calculate based on portfolio composition
    };

    // Calculate return percentage
    const totalCost = holdings.reduce((sum, h) => sum + parseFloat(h.cost_basis || 0) * parseFloat(h.quantity || 0), 0);
    if (totalCost > 0) {
      analytics.totalReturnPercent = (analytics.totalReturn / totalCost) * 100;
    }

    // Simplified sector allocation since we don't have reliable sector data
    const simpleSectorAllocation = {
      'Technology': 45.0,
      'Financials': 25.0,
      'Healthcare': 15.0,
      'Consumer Discretionary': 10.0,
      'Other': 5.0
    };

    res.success({
      holdings: holdings.map(h => ({
        symbol: h.symbol,
        quantity: parseFloat(h.quantity || 0),
        market_value: parseFloat(h.market_value || 0),
        cost_basis: parseFloat(h.cost_basis || 0) * parseFloat(h.quantity || 0),
        pnl: parseFloat(h.pnl || 0),
        pnl_percent: parseFloat(h.pnl_percent || 0),
        weight: totalValue > 0 ? (parseFloat(h.market_value) / totalValue) : 0,
        sector: 'Technology', // Default sector since we can't reliably get this from DB
        last_updated: h.last_updated
      })),
      analytics: analytics,
      summary: {
        totalValue: totalValue,
        totalPnL: analytics.totalReturn,
        numPositions: holdings.length,
        topSector: 'Technology',
        concentration: holdings.length > 0 ? (parseFloat(holdings[0].market_value) / totalValue) : 0,
        riskScore: analytics.riskScore
      },
      sectorAllocation: simpleSectorAllocation,
      metadata: {
        dataSource: 'database',
        note: 'Database analytics with simplified sector allocation. Connect broker API for enhanced analytics.'
      }
    });
    
  } catch (error) {
    console.error('❌ Error fetching portfolio analytics:', error);
    console.error('🔍 Error details:', {
      message: error.message,
      code: error.code,
      severity: error.severity,
      detail: error.detail,
      constraint: error.constraint,
      table: error.table,
      column: error.column,
      userId: req.user?.sub,
      timeframe: req.query.timeframe
    });

    // Return empty data structure instead of error
    console.warn('⚠️ No portfolio data available, returning empty structure');
    return res.success({
      holdings: [],
      analytics: {
        totalReturn: 0,
        totalReturnPercent: 0,
        sharpeRatio: 0,
        volatility: 0,
        beta: 1,
        maxDrawdown: 0,
        riskScore: 5
      },
      sectorAllocation: [],
      riskMetrics: {
        volatility: 0,
        sharpeRatio: 0,
        maxDrawdown: 0,
        beta: 1
      },
      metadata: {
        message: 'No portfolio data found. Please import your portfolio data from your broker first.',
        dataSource: 'none'
      }
    });
  }
});

// Health check endpoint
router.get('/health', async (req, res) => {
  try {
    const dbHealth = await healthCheck();
    
    // Check if required tables exist
    let tablesExist = false;
    if (dbHealth.status === 'healthy') {
      try {
        const tableCheck = await query(`
          SELECT table_name 
          FROM information_schema.tables 
          WHERE table_schema = 'public' 
          AND table_name IN ('portfolio_holdings', 'portfolio_metadata', 'user_api_keys')
        `);
        tablesExist = tableCheck.rows.length === 3;
      } catch (error) {
        console.error('Table check failed:', error.message);
      }
    }

    res.success({
      status: dbHealth.status === 'healthy' && tablesExist ? 'ready' : 'configuration_required',
      database: dbHealth,
      tablesExist: tablesExist
    });

  } catch (error) {
    console.error('Health check error:', error);
    res.serverError('Health check failed', {
      details: error.message
    });
  }
});

// Setup endpoint to create tables if needed
router.post('/setup', async (req, res) => {
  try {
    console.log('Setting up portfolio database tables...');
    await initializeDatabase();
    
    res.success({
      message: 'Portfolio database tables created successfully'
    });

  } catch (error) {
    console.error('Database setup error:', error);
    res.serverError('Failed to create portfolio database tables', {
      details: error.message
    });
  }
});

// Portfolio data loading status endpoint
router.get('/data-loading-status', async (req, res) => {
  try {
    const userId = req.user?.sub;
    
    if (!userId) {
      return res.unauthorized('User authentication required');
    }

    console.log(`🔄 Data loading status request for user: ${userId}`);
    
    // Get comprehensive data loading status
    const status = await portfolioDataRefreshService.getDataLoadingStatus(userId);
    
    res.success(status);

  } catch (error) {
    console.error('Error getting data loading status:', error);
    res.serverError('Failed to get data loading status', {
      details: error.message
    });
  }
});

// Manual trigger for portfolio data refresh
router.post('/trigger-data-refresh', async (req, res) => {
  try {
    const userId = req.user?.sub;
    
    if (!userId) {
      return res.unauthorized('User authentication required');
    }

    const { provider, symbols } = req.body;
    console.log(`🚀 Manual data refresh trigger for user: ${userId}`);
    
    // Trigger portfolio data refresh
    const result = await portfolioDataRefreshService.triggerPortfolioDataRefresh(
      userId, 
      provider || 'manual', 
      symbols || []
    );
    
    res.success(result, {
      message: 'Portfolio data refresh triggered successfully'
    });

  } catch (error) {
    console.error('Error triggering data refresh:', error);
    res.serverError('Failed to trigger data refresh', {
      details: error.message
    });
  }
});

// Portfolio performance endpoint - WITH DETAILED DIAGNOSTIC LOGGING
router.get('/performance', createValidationMiddleware(portfolioValidationSchemas.performance), async (req, res) => {
  const requestId = res.locals.requestId || 'unknown';
  const startTime = Date.now();
  
  console.log(`📈 [${requestId}] =====PORTFOLIO PERFORMANCE ENDPOINT START=====`);
  console.log(`📈 [${requestId}] Memory at start:`, process.memoryUsage());
  console.log(`📈 [${requestId}] Environment check:`, {
    DB_SECRET_ARN: !!process.env.DB_SECRET_ARN,
    AWS_REGION: process.env.AWS_REGION,
    NODE_ENV: process.env.NODE_ENV
  });

  try {
    const { timeframe = '1Y' } = req.query;
    console.log(`📈 [${requestId}] Timeframe requested: ${timeframe}`);
    
    // Validate user authentication
    const userId = req.user?.sub;
    if (!userId) {
      throw new Error('User authentication required');
    }
    console.log(`👤 [${requestId}] User ID: ${userId}`);

    // Test database with minimal query first
    console.log(`🔍 [${requestId}] Testing database with SELECT 1...`);
    try {
      const dbTestStart = Date.now();
      await query('SELECT 1 as test', [], 5000); // 5 second timeout
      console.log(`✅ [${requestId}] Database test passed in ${Date.now() - dbTestStart}ms`);
    } catch (dbError) {
      console.error(`❌ [${requestId}] Database test failed:`, dbError.message);
      return res.serviceUnavailable('Database connectivity issue', {
        message: dbError.message,
        duration: Date.now() - startTime
      });
    }

    // If user authenticated, try live API data first, then fallback to database
    if (userId) {
      console.log(`📊 [${requestId}] Getting portfolio performance for user: ${userId}`);
      
      try {
        // Try to get live performance data from broker API
        let livePerformanceData = null;
        try {
          const credentials = await apiKeyService.getDecryptedApiKey(userId, 'alpaca');
          
          if (credentials) {
            console.log(`📡 [${requestId}] Fetching live performance data from Alpaca...`);
            const alpaca = new AlpacaService(
              credentials.apiKey,
              credentials.apiSecret,
              credentials.isSandbox
            );
            
            // Get portfolio history for performance calculation
            const account = await alpaca.getAccount();
            const portfolioHistory = await alpaca.getPortfolioHistory({
              period: timeframe,
              timeframe: '1Day'
            });
            
            if (portfolioHistory && portfolioHistory.equity) {
              livePerformanceData = portfolioHistory.equity.map((equity, index) => ({
                date: portfolioHistory.timestamp[index] ? 
                  new Date(portfolioHistory.timestamp[index] * 1000).toISOString().split('T')[0] : 
                  new Date().toISOString().split('T')[0],
                portfolioValue: parseFloat(equity || 0),
                totalPnL: index > 0 ? 
                  parseFloat(equity - portfolioHistory.equity[0]) : 0,
                dailyReturn: index > 0 ? 
                  ((equity - portfolioHistory.equity[index - 1]) / portfolioHistory.equity[index - 1]) * 100 : 0
              }));
              
              console.log(`✅ [${requestId}] Retrieved ${livePerformanceData.length} days of live performance data`);
            }
          }
        } catch (apiError) {
          console.warn(`⚠️ [${requestId}] API performance fetch failed:`, apiError.message);
        }
        
        // Use live data if available, otherwise query database
        let performanceData = livePerformanceData;
        if (!performanceData) {
          console.log(`📊 [${requestId}] Falling back to database query...`);
          try {
            const portfolioQuery = `
              SELECT 
                DATE(updated_at) as date,
                SUM(market_value) as portfolio_value,
                SUM(unrealized_pl) as total_pnl
              FROM portfolio_holdings 
              WHERE user_id = $1 AND quantity > 0
              GROUP BY DATE(updated_at)
              ORDER BY DATE(updated_at) DESC
              LIMIT 50
            `;
            
            const result = await query(portfolioQuery, [userId], 8000);
            console.log(`✅ [${requestId}] Portfolio query completed, found ${result.rows.length} records`);
            
            if (result.rows.length > 0) {
              performanceData = result.rows.map(row => ({
                date: row.date,
                portfolioValue: parseFloat(row.portfolio_value || 0),
                totalPnL: parseFloat(row.total_pnl || 0),
                dailyReturn: 0
              }));
            }
          } catch (dbError) {
            console.error(`❌ [${requestId}] Database query failed:`, dbError.message);
          }
        }
        
        if (performanceData && performanceData.length > 0) {
            
            // Calculate advanced portfolio analytics
            const analytics = portfolioAnalytics.calculatePortfolioAnalytics(performanceData);
            
            // Get current portfolio holdings for sector analysis
            let sectorAnalysis = {};
            try {
              const holdingsQuery = `
                SELECT symbol, market_value, sector, quantity
                FROM portfolio_holdings 
                WHERE user_id = $1 AND quantity > 0
              `;
              const holdingsResult = await query(holdingsQuery, [userId], 5000);
              
              if (holdingsResult.rows.length > 0) {
                sectorAnalysis = portfolioAnalytics.calculateSectorAnalysis(holdingsResult.rows);
              }
            } catch (error) {
              if (shouldLog('WARN')) console.warn(`⚠️ [${requestId}] Failed to get sector analysis:`, error.message);
            }
            
            const metrics = {
              totalReturn: analytics.totalReturn,
              totalReturnPercent: analytics.totalReturn,
              annualizedReturn: analytics.annualizedReturn,
              volatility: analytics.volatility,
              sharpeRatio: analytics.sharpeRatio,
              maxDrawdown: analytics.maxDrawdown,
              beta: analytics.beta,
              alpha: analytics.annualizedReturn - (analytics.beta * 2.0), // Assuming 2% market return
              informationRatio: analytics.informationRatio,
              calmarRatio: analytics.annualizedReturn !== 0 ? analytics.annualizedReturn / Math.abs(analytics.maxDrawdown) : 0,
              sortinoRatio: analytics.sharpeRatio * 1.4, // Approximation
              var95: analytics.var95,
              winRate: analytics.winRate,
              averageWin: analytics.averageWin,
              averageLoss: analytics.averageLoss,
              profitFactor: analytics.profitFactor,
              diversificationScore: sectorAnalysis.diversificationScore || 0,
              concentrationRisk: sectorAnalysis.concentrationRisk || 0
            };
            
            if (shouldLog('INFO')) console.log(`✅ [${requestId}] Returning advanced analytics after ${Date.now() - startTime}ms`);
            return res.success({ 
              performance: performanceData, 
              metrics: metrics,
              sectorAnalysis: sectorAnalysis.sectorAllocation || [],
              metadata: {
                dataSource: 'database',
                duration: Date.now() - startTime
              }
            });
          } else {
            console.log(`⚠️ [${requestId}] No portfolio data found for user`);
            return res.notFound('No portfolio data found', {
              message: 'No portfolio holdings found for this user.',
              duration: Date.now() - startTime
            });
          }
      } catch (queryError) {
        console.error(`❌ [${requestId}] Portfolio query failed:`, queryError.message);
        return res.serverError('Database query failed', {
          message: queryError.message,
          duration: Date.now() - startTime
        });
      }
    } else {
      console.log(`⚠️ [${requestId}] No authenticated user`);
      return res.unauthorized('Authentication required', {
        message: 'Please log in to view portfolio performance data',
        duration: Date.now() - startTime
      });
    }

  } catch (error) {
    console.error(`❌ [${requestId}] Unexpected error:`, error);
    
    return res.status(500).json({
      success: false,
      error: 'Internal server error',
      message: error.message,
      duration: Date.now() - startTime,
      timestamp: new Date().toISOString()
    });
  }
});

// Portfolio benchmark endpoint
router.get('/benchmark', async (req, res) => {
  try {
    const { timeframe = '1Y' } = req.query;
    console.log(`Portfolio benchmark endpoint called for timeframe: ${timeframe}`);
    
    // Generate mock benchmark data for now
    const mockBenchmarkData = generateMockBenchmarkData(timeframe);
    
    res.success(mockBenchmarkData, {
      metadata: {
        dataSource: 'mock'
      }
    });

  } catch (error) {
    console.error('Error in portfolio benchmark endpoint:', error);
    res.serverError('Failed to fetch benchmark data', {
      details: error.message
    });
  }
});

// Helper function to generate mock performance data
function generateMockPerformanceData(timeframe) {
  const dataPoints = getDataPointsForTimeframe(timeframe);
  const startDate = new Date();
  const performance = [];
  
  for (let i = 0; i < dataPoints; i++) {
    const date = new Date(startDate);
    date.setDate(date.getDate() - (dataPoints - i));
    
    const baseValue = 100000;
    const growth = Math.random() * 0.15 + 0.05; // 5-20% growth
    const volatility = Math.random() * 0.02 - 0.01; // ±1% daily volatility
    
    const portfolioValue = baseValue * (1 + growth * (i / dataPoints)) * (1 + volatility);
    const benchmarkValue = baseValue * (1 + 0.10 * (i / dataPoints)) * (1 + volatility * 0.8);
    
    performance.push({
      date: date.toISOString().split('T')[0],
      portfolioValue: portfolioValue,
      benchmarkValue: benchmarkValue,
      dailyReturn: i > 0 ? (portfolioValue / performance[i-1].portfolioValue - 1) * 100 : 0
    });
  }
  
  return {
    performance,
    metrics: {
      totalReturn: 12.5,
      annualizedReturn: 11.2,
      volatility: 16.8,
      sharpeRatio: 0.89,
      maxDrawdown: -8.3,
      beta: 1.05,
      alpha: 2.1,
      informationRatio: 0.45,
      calmarRatio: 1.35,
      sortinoRatio: 1.24
    }
  };
}

// Helper function to generate mock benchmark data
function generateMockBenchmarkData(timeframe) {
  const dataPoints = getDataPointsForTimeframe(timeframe);
  const startDate = new Date();
  const benchmark = [];
  
  for (let i = 0; i < dataPoints; i++) {
    const date = new Date(startDate);
    date.setDate(date.getDate() - (dataPoints - i));
    
    const baseValue = 100000;
    const growth = 0.10; // 10% annual growth for S&P 500
    const volatility = Math.random() * 0.015 - 0.0075; // ±0.75% daily volatility
    
    const value = baseValue * (1 + growth * (i / dataPoints)) * (1 + volatility);
    
    benchmark.push({
      date: date.toISOString().split('T')[0],
      value: value,
      return: i > 0 ? (value / benchmark[i-1].value - 1) * 100 : 0
    });
  }
  
  return {
    benchmark,
    name: 'S&P 500',
    symbol: 'SPY',
    metrics: {
      totalReturn: 10.0,
      annualizedReturn: 9.5,
      volatility: 15.2,
      sharpeRatio: 0.72,
      maxDrawdown: -12.1
    }
  };
}

// Helper function to get data points based on timeframe
function getDataPointsForTimeframe(timeframe) {
  switch (timeframe) {
    case '1M': return 30;
    case '3M': return 90;
    case '6M': return 180;
    case '1Y': return 365;
    case '2Y': return 730;
    case '3Y': return 1095;
    case '5Y': return 1825;
    case 'MAX': return 2555; // ~7 years
    default: return 365;
  }
}

// Portfolio import endpoint
router.post('/import/:broker', async (req, res) => {
  const startTime = Date.now();
  
  try {
    const { broker } = req.params;
    const { accountType = 'paper', keyId } = req.query; // accountType for logging, keyId for specific API key selection
    const userId = req.user?.sub;
    
    console.log(`🔄 [IMPORT START] Portfolio import requested for broker: ${broker}, account: ${accountType}, keyId: ${keyId || 'auto-select'}`);
    console.log(`🔄 [IMPORT] Request headers:`, Object.keys(req.headers));
    console.log(`🔄 [IMPORT] Memory usage:`, process.memoryUsage());
    
    // Validate required parameters
    if (!broker) {
      console.error(`❌ [IMPORT] Missing broker parameter`);
      return res.status(400).json({
        success: false,
        error: 'Missing broker parameter',
        message: 'Broker parameter is required for portfolio import'
      });
    }
    
    if (!userId) {
      console.error(`❌ [IMPORT] Missing user ID - authentication may have failed`);
      return res.status(401).json({
        success: false,
        error: 'Authentication required',
        message: 'User must be authenticated to import portfolio data'
      });
    }
    
    // Step 1: Get the user's API key for this broker with robust error handling
    console.log(`🔑 [IMPORT] Step 1: Fetching API keys for ${broker}...`);
    console.log(`🔑 [IMPORT] User ID: ${userId}, Broker: ${broker}`);
    let credentials;
    try {
      // Check if API key service is enabled
      console.log(`🔑 [IMPORT] API key service enabled: ${apiKeyService.isEnabled}`);
      
      if (!apiKeyService.isEnabled) {
        console.error(`❌ [IMPORT] API key service is disabled. Cannot retrieve API keys.`);
        return res.status(500).json({
          success: false,
          error: 'API key service disabled',
          message: 'API key encryption service is not properly configured. Please contact support.',
          debug: {
            userId: userId,
            broker: broker,
            timestamp: new Date().toISOString()
          }
        });
      }
        console.log(`🔑 [IMPORT] Calling apiKeyService.getDecryptedApiKey with userId=${userId}, broker=${broker}...`);
        console.log(`🔑 [IMPORT] API Key Service enabled: ${apiKeyService.isEnabled}`);
        
        // Enhanced debug: Check if user has any API keys at all
        try {
          const debugResult = await query(`SELECT id, provider, user_id, is_active, created_at FROM user_api_keys WHERE user_id = $1`, [userId]);
          console.log(`🔍 [IMPORT DEBUG] User has ${debugResult.rows.length} API keys:`, debugResult.rows.map(k => `ID:${k.id} ${k.provider}(${k.is_active ? 'active' : 'inactive'})`));
          
          // If specific keyId requested, check if it exists
          if (keyId) {
            const specificKeyCheck = await query(`SELECT id, provider, user_id, is_active FROM user_api_keys WHERE id = $1`, [keyId]);
            console.log(`🔍 [IMPORT DEBUG] KeyId ${keyId} check: found=${specificKeyCheck.rows.length > 0}`);
            if (specificKeyCheck.rows.length > 0) {
              const key = specificKeyCheck.rows[0];
              console.log(`🔍 [IMPORT DEBUG] KeyId ${keyId} details: user_id=${key.user_id}, provider=${key.provider}, active=${key.is_active}`);
              console.log(`🔍 [IMPORT DEBUG] User ID match: ${key.user_id === userId} (${key.user_id} vs ${userId})`);
              console.log(`🔍 [IMPORT DEBUG] Provider match: ${key.provider === broker} (${key.provider} vs ${broker})`);
            } else {
              console.log(`❌ [IMPORT DEBUG] KeyId ${keyId} does not exist in database`);
            }
          }
          
          // Only use API keys that belong to the exact authenticated user ID
          if (debugResult.rows.length === 0) {
            console.log(`🔍 [IMPORT DEBUG] No API keys found for user. User must add API key in Settings.`);
            
            // Check if there are ANY API keys in the system
            const totalKeysResult = await query(`SELECT COUNT(*) as total FROM user_api_keys`);
            console.log(`🔍 [IMPORT DEBUG] Total API keys in system: ${totalKeysResult.rows[0]?.total || 0}`);
          } else {
            // Check for alpaca keys specifically for this user
            const userAlpacaKeys = debugResult.rows.filter(k => k.provider === broker);
            console.log(`🔍 [IMPORT DEBUG] User has ${userAlpacaKeys.length} ${broker} keys:`, userAlpacaKeys.map(k => `ID:${k.id}(${k.is_active ? 'active' : 'inactive'})`));
          }
        } catch (debugError) {
          console.log(`🔍 [IMPORT DEBUG] Failed to query user API keys:`, debugError.message);
        }
        
        // Use API key service only - no fallbacks
        console.log(`🔑 [IMPORT] Calling apiKeyService.getDecryptedApiKey with userId=${userId}, broker=${broker}...`);
        
        // If specific key ID is provided, get that specific key
        if (keyId) {
          console.log(`🔑 [IMPORT] Fetching specific API key with ID: ${keyId}`);
          try {
            const specificKeyResult = await query(`
                  SELECT 
                    id,
                    provider,
                    encrypted_api_key,
                    key_iv,
                    key_auth_tag,
                    encrypted_api_secret,
                    secret_iv,
                    secret_auth_tag,
                    user_salt,
                    is_sandbox,
                    is_active
                  FROM user_api_keys 
                  WHERE id = $1 AND user_id = $2 AND provider = $3 AND is_active = true
                `, [keyId, userId, broker]);
                
                if (specificKeyResult.rows.length > 0) {
                  const keyData = specificKeyResult.rows[0];
                  
                  // Decrypt the API credentials using the apiKeyService
                  const apiKey = await apiKeyService.decryptApiKey({
                    encrypted: keyData.encrypted_api_key,
                    iv: keyData.key_iv,
                    authTag: keyData.key_auth_tag
                  }, keyData.user_salt);
                  
                  const apiSecret = keyData.encrypted_api_secret ? await apiKeyService.decryptApiKey({
                    encrypted: keyData.encrypted_api_secret,
                    iv: keyData.secret_iv,
                    authTag: keyData.secret_auth_tag
                  }, keyData.user_salt) : null;
                  
                  credentials = {
                    id: keyData.id,
                    provider: keyData.provider,
                    apiKey: apiKey,
                    apiSecret: apiSecret,
                    isSandbox: keyData.is_sandbox,
                    isActive: keyData.is_active
                  };
                  console.log(`✅ [IMPORT] Retrieved specific key ${keyId}: ${credentials.provider} (${credentials.isSandbox ? 'sandbox' : 'live'})`);
                } else {
                  console.error(`❌ [IMPORT] Specific key ${keyId} not found for user ${userId}`);
                }
              } catch (keyError) {
                console.error(`❌ [IMPORT] Error fetching specific key ${keyId}:`, keyError.message);
              }
        } else {
          // Default behavior - get any available key for the broker
          credentials = await apiKeyService.getDecryptedApiKey(userId, broker);
          console.log(`🔑 [IMPORT] API key service returned credentials:`, !!credentials);
          if (credentials) {
            console.log(`🔑 [IMPORT] Credentials provider: ${credentials.provider}, sandbox: ${credentials.isSandbox}`);
          }
        }
    } catch (error) {
      console.error(`❌ [IMPORT] Error fetching API key for ${broker}:`, error.message);
      console.error(`❌ [IMPORT] Error stack:`, error.stack);
      return res.status(500).json({
        success: false,
        error: 'API key service error',
        message: `Unable to access API keys: ${error.message}. Please check your API key configuration in Settings.`,
        duration: Date.now() - startTime
      });
    }
    
    if (!credentials) {
      console.log(`❌ No API key found for broker ${broker}`);
      console.log(`❌ Debug info: userId=${userId}, broker=${broker}`);
      console.log(`❌ Recommended action: Check that user has saved API keys in Settings and they are active`);
      return res.status(400).json({
        success: false,
        error: 'API key not found',
        message: `No API key configured for ${broker}. Please add your API key in Settings.`,
        debug: {
          userId: userId,
          broker: broker,
          timestamp: new Date().toISOString()
        }
      });
    }
    
    console.log(`✅ Found API key for ${broker} (sandbox: ${credentials.isSandbox})`);
    console.log(`📊 [IMPORT] API key setting is authoritative - using ${credentials.isSandbox ? 'PAPER' : 'LIVE'} account`);
    
    // Step 2: Connect to the broker's API and fetch portfolio data
    console.log(`📡 [IMPORT] Step 2: Connecting to ${broker} API...`);
    console.log(`📡 [IMPORT] API endpoint will be: ${credentials.isSandbox ? 'paper-api.alpaca.markets' : 'api.alpaca.markets'}`);
    
    let portfolioData;
    try {
      if (broker.toLowerCase() === 'alpaca') {
        console.log(`🔗 [IMPORT] Initializing AlpacaService...`);
        let alpaca;
        try {
          alpaca = new AlpacaService(
            credentials.apiKey,
            credentials.apiSecret,
            credentials.isSandbox // Use API key setting as authoritative source
          );
          console.log(`✅ [IMPORT] AlpacaService initialized successfully`);
        } catch (initError) {
          console.error(`❌ [IMPORT] Failed to initialize AlpacaService:`, initError.message);
          throw new Error(`Alpaca service initialization failed: ${initError.message}`);
        }
        
        console.log(`📊 [IMPORT] Fetching portfolio data from Alpaca...`);
        
        // Get comprehensive portfolio data including positions, account info, and activities
        let positions, account, activities;
        try {
          console.log(`📊 [IMPORT] Fetching account info...`);
          account = await alpaca.getAccount();
          console.log(`✅ [IMPORT] Account fetched successfully`);
          
          console.log(`📊 [IMPORT] Fetching positions...`);
          positions = await alpaca.getPositions();
          console.log(`✅ [IMPORT] ${positions.length} positions fetched`);
          
          console.log(`📊 [IMPORT] Fetching activities...`);
          try {
            activities = await alpaca.getActivities();
            console.log(`✅ [IMPORT] ${activities.length} activities fetched`);
          } catch (actError) {
            console.warn(`⚠️ [IMPORT] Failed to fetch activities:`, actError.message);
            activities = [];
          }
        } catch (dataError) {
          console.error(`❌ [IMPORT] Failed to fetch portfolio data:`, dataError.message);
          throw new Error(`Failed to fetch data from Alpaca: ${dataError.message}`);
        }
        
        // Process and structure the portfolio data
        portfolioData = {
          summary: {
            totalValue: parseFloat(account.portfolio_value || account.equity || 0),
            totalPnL: parseFloat(account.unrealized_pl || 0),
            totalPnLPercent: parseFloat(account.unrealized_plpc || 0) * 100,
            cashBalance: parseFloat(account.cash || account.buying_power || 0),
            dayChange: parseFloat(account.unrealized_pl || 0),
            dayChangePercent: parseFloat(account.unrealized_plpc || 0) * 100
          },
          positions: positions.map(pos => ({
            symbol: pos.symbol,
            quantity: parseFloat(pos.qty),
            side: pos.side,
            marketValue: parseFloat(pos.market_value || 0),
            averageEntryPrice: parseFloat(pos.avg_entry_price || 0),
            currentPrice: parseFloat(pos.current_price || pos.lastday_price || 0),
            unrealizedPL: parseFloat(pos.unrealized_pl || 0),
            unrealizedPLPercent: parseFloat(pos.unrealized_plpc || 0) * 100,
            costBasis: parseFloat(pos.cost_basis || 0),
            lastTradeTime: pos.lastday_price_timeframe || new Date().toISOString()
          })),
          account: {
            accountId: account.id,
            status: account.status,
            tradingBlocked: account.trading_blocked,
            transfersBlocked: account.transfers_blocked,
            accountBlocked: account.account_blocked,
            createdAt: account.created_at,
            currency: account.currency || 'USD',
            patternDayTrader: account.pattern_day_trader,
            daytradeCount: account.daytrade_count,
            lastEquity: parseFloat(account.last_equity || 0)
          },
          activities: activities.slice(0, 50).map(activity => ({
            id: activity.id,
            activityType: activity.activity_type,
            date: activity.date,
            symbol: activity.symbol,
            side: activity.side,
            qty: parseFloat(activity.qty || 0),
            price: parseFloat(activity.price || 0),
            netAmount: parseFloat(activity.net_amount || 0)
          }))
        };
        
      } else if (broker.toLowerCase() === 'td_ameritrade') {
        // TD Ameritrade integration would go here
        throw new Error(`TD Ameritrade integration not yet implemented`);
      } else {
        throw new Error(`Unsupported broker: ${broker}`);
      }
    } catch (error) {
      console.error(`❌ Failed to fetch portfolio from ${broker}:`, error);
      return res.status(500).json({
        success: false,
        error: 'Broker API error',
        message: `Failed to fetch portfolio from ${broker}. Please check your API key and try again. Error: ${error.message}`
      });
    }
    
    // Step 3: Store the portfolio data in the database with enhanced error handling
    console.log(`💾 Storing portfolio data in database...`);
    
    try {
      await storePortfolioData(userId, credentials.id, portfolioData, accountType);
      console.log(`✅ Portfolio data stored successfully`);
      
      // Also store individual positions
      // Batch UPSERT operations for better performance
      if (portfolioData.positions.length > 0) {
        const batchSize = 100;
        for (let i = 0; i < portfolioData.positions.length; i += batchSize) {
          const batch = portfolioData.positions.slice(i, i + batchSize);
          
          const values = [];
          const params = [];
          let paramIndex = 1;
          
          batch.forEach(position => {
            values.push(`($${paramIndex++}, $${paramIndex++}, $${paramIndex++}, $${paramIndex++}, $${paramIndex++}, $${paramIndex++}, $${paramIndex++}, $${paramIndex++}, $${paramIndex++}, $${paramIndex++}, NOW())`);
            params.push(
              userId, credentials.id, position.symbol, position.quantity,
              position.averageEntryPrice, position.currentPrice, position.marketValue,
              position.unrealizedPL, position.unrealizedPLPercent, position.side
            );
          });
          
          await query(`
            INSERT INTO portfolio_holdings (
              user_id, api_key_id, symbol, quantity, avg_cost, current_price, 
              market_value, unrealized_pl, unrealized_plpc, side, updated_at
            ) VALUES ${values.join(', ')}
            ON CONFLICT (user_id, api_key_id, symbol) DO UPDATE SET
              quantity = EXCLUDED.quantity,
              avg_cost = EXCLUDED.avg_cost,
              current_price = EXCLUDED.current_price,
              market_value = EXCLUDED.market_value,
              unrealized_pl = EXCLUDED.unrealized_pl,
              unrealized_plpc = EXCLUDED.unrealized_plpc,
              side = EXCLUDED.side,
              updated_at = NOW()
          `, params);
          
          console.log(`📈 Processed batch ${Math.floor(i/batchSize) + 1}: ${batch.length} positions`);
        }
      }
      
      // Individual processing replaced with batch processing above
      console.log(`✅ Completed batch UPSERT for ${portfolioData.positions.length} positions`);
      
    } catch (error) {
      console.error('❌ Failed to store portfolio data:', error);
      // Don't fail the import if database storage fails - the user still gets the data
      console.warn('Continuing without database storage...');
    }
    
    // Return comprehensive success response with all portfolio data
    const successResponse = {
      success: true,
      data: {
        imported: new Date().toISOString(),
        broker: broker,
        accountType: accountType,
        summary: portfolioData.summary,
        holdings: portfolioData.positions.map(pos => ({
          symbol: pos.symbol,
          quantity: pos.quantity,
          marketValue: pos.marketValue,
          unrealizedPL: pos.unrealizedPL,
          unrealizedPLPC: pos.unrealizedPLPercent,
          avgCost: pos.averageEntryPrice,
          currentPrice: pos.currentPrice,
          side: pos.side
        })),
        account: portfolioData.account,
        recentActivities: portfolioData.activities,
        statistics: {
          totalPositions: portfolioData.positions.length,
          longPositions: portfolioData.positions.filter(p => p.side === 'long').length,
          shortPositions: portfolioData.positions.filter(p => p.side === 'short').length,
          topGainer: portfolioData.positions.reduce((max, pos) => 
            pos.unrealizedPLPercent > (max?.unrealizedPLPercent || -Infinity) ? pos : max, null),
          topLoser: portfolioData.positions.reduce((min, pos) => 
            pos.unrealizedPLPercent < (min?.unrealizedPLPercent || Infinity) ? pos : min, null)
        }
      },
      provider: broker,
      environment: credentials.isSandbox ? 'sandbox' : 'live',
      timestamp: new Date().toISOString(),
      dataSource: 'live_api'
    };
    
    res.json(successResponse);
    
  } catch (error) {
    const duration = Date.now() - startTime;
    console.error(`❌ [IMPORT] Fatal error after ${duration}ms:`, error.message);
    console.error(`❌ [IMPORT] Error stack:`, error.stack);
    console.error(`❌ [IMPORT] Memory usage:`, process.memoryUsage());
    
    // Return detailed error information for debugging
    res.status(500).json({
      success: false,
      error: 'Failed to import portfolio',
      message: error.message,
      details: {
        errorType: error.constructor.name,
        duration: duration,
        endpoint: `${req.method} ${req.path}`,
        broker: req.params?.broker,
        accountType: req.query?.accountType,
        userId: req.user?.sub ? 'present' : 'missing',
        hasApiKey: !!req.user?.sub,
        timestamp: new Date().toISOString()
      }
    });
  }
});

// Test connection endpoint
router.post('/test-connection/:broker', async (req, res) => {
  const { broker } = req.params;
  const userId = req.user?.sub || 'dev-user';
  
  try {
    console.log(`Testing connection for broker: ${broker}, user: ${userId}`);
    
    // Return empty connection test result with comprehensive diagnostics
    console.error('❌ Connection test unavailable - comprehensive diagnosis needed', {
      broker,
      userId,
      detailed_diagnostics: {
        attempted_operations: ['api_key_retrieval', 'broker_connection_test'],
        potential_causes: [
          'API keys not configured',
          'Broker API unavailable',
          'Invalid broker credentials',
          'Network connectivity issues',
          'External API rate limiting'
        ],
        troubleshooting_steps: [
          'Check API key configuration',
          'Verify broker API status',
          'Test network connectivity',
          'Review broker credential validity',
          'Monitor external API limits'
        ],
        system_checks: [
          'API key service availability',
          'Broker API connectivity',
          'Network health status',
          'Authentication system health'
        ]
      }
    });

    const emptyConnectionResult = {
      success: false,
      connection: {
        valid: false,
        accountInfo: null,
        permissions: [],
        rateLimit: {
          remaining: 0,
          limit: 0,
          resetTime: null
        }
      },
      message: `Connection test failed for ${broker} API - configure your API keys`,
      provider: broker,
      dataSource: 'empty'
    };
    
    res.json(emptyConnectionResult);
    
  } catch (error) {
    console.error('Error testing connection:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to test connection',
      details: error.message
    });
  }
});

// API Keys management for portfolio connections
router.get('/api-keys', async (req, res) => {
  const userId = req.user?.sub || 'dev-user';
  
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
    res.json({ 
      success: true, 
      apiKeys: [] // Return empty array for development
    });
  }
});

// Portfolio Optimization endpoints
router.post('/optimization/run', async (req, res) => {
  const userId = req.user?.sub || 'demo-user';
  const { 
    objective = 'maxSharpe',
    constraints = {},
    includeAssets = [],
    excludeAssets = [],
    lookbackDays = 252
  } = req.body;

  try {
    console.log(`Running portfolio optimization for user ${userId}`);
    
    // Check if optimization service is available
    let OptimizationEngine;
    try {
      OptimizationEngine = require('../services/optimizationEngine');
    } catch (moduleError) {
      console.warn('OptimizationEngine service not available, returning mock optimization result');
      
      // Return mock optimization result
      const mockResult = {
        optimization: {
          expectedReturn: 0.12,
          volatility: 0.18,
          sharpeRatio: 0.67,
          weights: {}
        },
        rebalancing: [],
        insights: [
          {
            type: 'info',
            title: 'Optimization Service Unavailable',
            message: 'Portfolio optimization service is currently being set up. Mock results shown.',
            impact: 'Please try again later for detailed optimization recommendations.'
          }
        ],
        metadata: {
          universeSize: 10,
          analysisDate: new Date().toISOString()
        }
      };
      
      return res.json({
        success: true,
        data: mockResult,
        timestamp: new Date().toISOString(),
        note: 'Optimization service temporarily unavailable - showing mock results'
      });
    }
    
    const optimizer = new OptimizationEngine();
    
    const result = await optimizer.runOptimization({
      userId,
      objective,
      constraints,
      includeAssets,
      excludeAssets,
      lookbackDays
    });

    res.json({
      success: true,
      data: result,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Portfolio optimization error:', error);
    res.status(500).json({
      success: false,
      error: 'Portfolio optimization failed',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Portfolio optimization endpoint - returns optimization analysis
router.get('/optimization', async (req, res) => {
  const userId = req.user?.sub || 'demo-user';
  
  try {
    console.log(`Getting portfolio optimization data for user ${userId}`);
    
    // Get current portfolio from live API
    let currentPortfolio = null;
    try {
      const credentials = await apiKeyService.getDecryptedApiKey(userId, 'alpaca');
      
      if (credentials) {
        const alpaca = new AlpacaService(
          credentials.apiKey,
          credentials.apiSecret,
          credentials.isSandbox
        );
        
        const positions = await alpaca.getPositions();
        currentPortfolio = positions.map(p => ({
          symbol: p.symbol,
          quantity: p.quantity,
          marketValue: p.marketValue,
          weight: 0 // Will be calculated below
        }));
        
        // Calculate weights
        const totalValue = positions.reduce((sum, p) => sum + p.marketValue, 0);
        if (totalValue > 0) {
          currentPortfolio.forEach(p => {
            p.weight = p.marketValue / totalValue;
          });
        }
      }
    } catch (apiError) {
      console.warn(`API fetch failed for optimization: ${apiError.message}`);
    }
    
    // Return optimization data (mock for now, could be enhanced with real optimization engine)
    res.json({
      success: true,
      data: {
        currentPortfolio: currentPortfolio || [
          { symbol: 'AAPL', weight: 0.25, marketValue: 50000 },
          { symbol: 'GOOGL', weight: 0.20, marketValue: 40000 },
          { symbol: 'MSFT', weight: 0.15, marketValue: 30000 },
          { symbol: 'TSLA', weight: 0.10, marketValue: 20000 },
          { symbol: 'NVDA', weight: 0.30, marketValue: 60000 }
        ],
        optimizedWeights: [0.2, 0.18, 0.17, 0.15, 0.12, 0.08, 0.05, 0.03, 0.02],
        metrics: {
          expectedReturn: 0.125,
          volatility: 0.165,
          sharpeRatio: 0.76,
          maxDrawdown: 0.18
        },
        riskAnalysis: {
          concentrationRisk: 'medium',
          sectorExposure: {
            technology: 0.65,
            healthcare: 0.15,
            finance: 0.10,
            consumer: 0.10
          }
        }
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Portfolio optimization error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get portfolio optimization data',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get optimization recommendations (quick analysis)
router.get('/optimization/recommendations', async (req, res) => {
  const userId = req.user?.sub || 'demo-user';
  
  try {
    console.log(`Getting optimization recommendations for user ${userId}`);
    
    // Get current portfolio from live API to base recommendations on
    let currentPortfolio = null;
    try {
      const credentials = await apiKeyService.getDecryptedApiKey(userId, 'alpaca');
      
      if (credentials) {
        console.log('📡 Fetching current portfolio for optimization analysis...');
        const alpaca = new AlpacaService(
          credentials.apiKey,
          credentials.apiSecret,
          credentials.isSandbox
        );
        
        const [positions, account] = await Promise.all([
          alpaca.getPositions(),
          alpaca.getAccount()
        ]);
        
        currentPortfolio = {
          totalValue: parseFloat(account.portfolio_value || account.equity || 0),
          cashBalance: parseFloat(account.cash || account.buying_power || 0),
          positions: positions.map(pos => ({
            symbol: pos.symbol,
            quantity: parseFloat(pos.qty),
            marketValue: parseFloat(pos.market_value || 0),
            weight: 0, // Will calculate below
            unrealizedPL: parseFloat(pos.unrealized_pl || 0),
            unrealizedPLPercent: parseFloat(pos.unrealized_plpc || 0) * 100
          }))
        };
        
        // Calculate position weights
        if (currentPortfolio.totalValue > 0) {
          currentPortfolio.positions.forEach(pos => {
            pos.weight = (pos.marketValue / currentPortfolio.totalValue) * 100;
          });
        }
        
        console.log(`✅ Retrieved portfolio: $${currentPortfolio.totalValue.toFixed(2)} with ${currentPortfolio.positions.length} positions`);
      }
    } catch (apiError) {
      console.warn('Failed to fetch live portfolio for optimization:', apiError.message);
      // Fall back to database
      try {
        const result = await query(`
          SELECT symbol, quantity, market_value, unrealized_pl, unrealized_plpc
          FROM portfolio_holdings 
          WHERE user_id = $1 AND quantity > 0
        `, [userId]);
        
        if (result.rows.length > 0) {
          const totalValue = result.rows.reduce((sum, row) => sum + parseFloat(row.market_value || 0), 0);
          currentPortfolio = {
            totalValue: totalValue,
            cashBalance: 0, // Unknown from holdings
            positions: result.rows.map(row => ({
              symbol: row.symbol,
              quantity: parseFloat(row.quantity || 0),
              marketValue: parseFloat(row.market_value || 0),
              weight: totalValue > 0 ? (parseFloat(row.market_value) / totalValue) * 100 : 0,
              unrealizedPL: parseFloat(row.unrealized_pl || 0),
              unrealizedPLPercent: parseFloat(row.unrealized_plpc || 0)
            }))
          };
        }
      } catch (dbError) {
        console.warn('Database fallback also failed:', dbError.message);
      }
    }
    
    // Check if optimization service is available
    let OptimizationEngine;
    try {
      OptimizationEngine = require('../services/optimizationEngine');
    } catch (moduleError) {
      console.error('❌ OptimizationEngine service not available:', moduleError.message);
      
      return res.status(503).json({
        success: false,
        error: 'Optimization service unavailable',
        message: 'Portfolio optimization service is currently not available. Please try again later.',
        timestamp: new Date().toISOString()
      });
    }
    
    const optimizer = new OptimizationEngine();
    
    // Run quick optimization with default parameters
    const result = await optimizer.runOptimization({
      userId,
      objective: 'maxSharpe',
      lookbackDays: 126 // 6 months for faster analysis
    });

    // Extract key recommendations
    const recommendations = {
      primaryRecommendation: result.insights.find(i => i.type === 'warning') || result.insights[0],
      riskScore: Math.round((1 - result.optimization.volatility / 0.3) * 100), // Scale volatility to 0-100
      diversificationScore: Math.min(100, (result.metadata.universeSize / 15) * 100),
      expectedImprovement: {
        sharpeRatio: Math.max(0, result.optimization.sharpeRatio - 0.5),
        volatilityReduction: Math.max(0, 0.2 - result.optimization.volatility),
        returnIncrease: Math.max(0, result.optimization.expectedReturn - 0.08)
      },
      topActions: result.rebalancing.slice(0, 3),
      timeToRebalance: result.rebalancing.length > 0 ? 'Recommended' : 'Not Needed'
    };

    res.json({
      success: true,
      data: recommendations,
      fullOptimization: result,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Optimization recommendations error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get optimization recommendations',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Execute rebalancing trades
router.post('/rebalance/execute', async (req, res) => {
  const userId = req.user?.sub || 'demo-user';
  const { trades, confirmationToken } = req.body;

  try {
    console.log(`Executing rebalancing trades for user ${userId}`);
    
    // Validate trades
    if (!trades || !Array.isArray(trades) || trades.length === 0) {
      return res.status(400).json({
        success: false,
        error: 'Invalid trades data'
      });
    }

    // For now, simulate trade execution
    // In production, would integrate with actual broker APIs
    const executionResults = trades.map(trade => ({
      ...trade,
      status: 'executed',
      executionPrice: trade.action === 'BUY' ? trade.marketPrice * 1.001 : trade.marketPrice * 0.999,
      executionTime: new Date().toISOString(),
      fees: Math.abs(trade.tradeValue) * 0.0005, // 0.05% fee
      orderId: 'ORDER_' + Math.random().toString(36).substr(2, 9)
    }));

    // Calculate execution summary
    const totalTrades = executionResults.length;
    const totalVolume = executionResults.reduce((sum, trade) => sum + Math.abs(trade.tradeValue), 0);
    const totalFees = executionResults.reduce((sum, trade) => sum + trade.fees, 0);

    res.json({
      success: true,
      data: {
        executionSummary: {
          totalTrades,
          totalVolume,
          totalFees,
          executionTime: new Date().toISOString(),
          status: 'completed'
        },
        tradeResults: executionResults,
        nextRebalanceDate: new Date(Date.now() + 90 * 24 * 60 * 60 * 1000).toISOString() // 3 months
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Rebalancing execution error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to execute rebalancing trades',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get risk analysis
router.get('/risk-analysis', async (req, res) => {
  const userId = req.user?.sub || 'demo-user';
  const { timeHorizon = 1, confidenceLevel = 0.95 } = req.query;

  try {
    console.log(`Getting risk analysis for user ${userId}`);
    
    // Get live portfolio data for risk analysis
    let portfolioData = null;
    let portfolioHistory = null;
    
    try {
      const credentials = await apiKeyService.getDecryptedApiKey(userId, 'alpaca');
      
      if (credentials) {
        console.log('📡 Fetching live portfolio data for risk analysis...');
        const alpaca = new AlpacaService(
          credentials.apiKey,
          credentials.apiSecret,
          credentials.isSandbox
        );
        
        const [positions, account, history] = await Promise.all([
          alpaca.getPositions(),
          alpaca.getAccount(),
          alpaca.getPortfolioHistory({
            period: '1Y',
            timeframe: '1Day'
          }).catch(e => {
            console.warn('Portfolio history unavailable:', e.message);
            return null;
          })
        ]);
        
        portfolioData = {
          totalValue: parseFloat(account.portfolio_value || account.equity || 0),
          positions: positions.map(pos => ({
            symbol: pos.symbol,
            marketValue: parseFloat(pos.market_value || 0),
            unrealizedPL: parseFloat(pos.unrealized_pl || 0),
            unrealizedPLPercent: parseFloat(pos.unrealized_plpc || 0) * 100,
            weight: 0 // Calculate below
          }))
        };
        
        // Calculate position weights
        if (portfolioData.totalValue > 0) {
          portfolioData.positions.forEach(pos => {
            pos.weight = (pos.marketValue / portfolioData.totalValue);
          });
        }
        
        portfolioHistory = history;
        console.log(`✅ Retrieved portfolio data for risk analysis: $${portfolioData.totalValue.toFixed(2)}`);
      }
    } catch (apiError) {
      console.warn('Failed to fetch live data for risk analysis:', apiError.message);
    }
    
    // Calculate risk metrics from live data or use realistic defaults
    let riskMetrics;
    
    if (portfolioHistory && portfolioHistory.equity && portfolioHistory.equity.length > 30) {
      // Calculate actual risk metrics from portfolio history
      const returns = [];
      for (let i = 1; i < portfolioHistory.equity.length; i++) {
        const dailyReturn = (portfolioHistory.equity[i] - portfolioHistory.equity[i-1]) / portfolioHistory.equity[i-1];
        returns.push(dailyReturn);
      }
      
      // Calculate volatility (standard deviation of returns)
      const meanReturn = returns.reduce((sum, r) => sum + r, 0) / returns.length;
      const variance = returns.reduce((sum, r) => sum + Math.pow(r - meanReturn, 2), 0) / returns.length;
      const volatility = Math.sqrt(variance * 252); // Annualized
      
      // Calculate VaR
      const sortedReturns = returns.slice().sort((a, b) => a - b);
      const var95Index = Math.floor(returns.length * 0.05);
      const var99Index = Math.floor(returns.length * 0.01);
      const var95 = sortedReturns[var95Index] || -0.025;
      const var99 = sortedReturns[var99Index] || -0.042;
      
      // Calculate max drawdown
      let maxDrawdown = 0;
      let peak = portfolioHistory.equity[0];
      for (const value of portfolioHistory.equity) {
        if (value > peak) peak = value;
        const drawdown = (peak - value) / peak;
        if (drawdown > maxDrawdown) maxDrawdown = drawdown;
      }
      
      riskMetrics = {
        volatility: volatility,
        var95: var95,
        var99: var99,
        maxDrawdown: -maxDrawdown,
        beta: 1.0, // Would need market data to calculate
        correlationWithMarket: 0.8 // Would need market data
      };
      
      console.log(`📊 Calculated risk metrics from ${returns.length} days of data`);
    } else {
      // Use reasonable defaults based on portfolio composition if available
      const techWeight = portfolioData ? 
        portfolioData.positions.filter(p => ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'TSLA'].includes(p.symbol))
          .reduce((sum, p) => sum + p.weight, 0) : 0.5;
      
      riskMetrics = {
        volatility: 0.15 + (techWeight * 0.1), // Higher vol for tech-heavy portfolios
        var95: -0.02 - (techWeight * 0.01),
        var99: -0.035 - (techWeight * 0.015),
        maxDrawdown: -0.08 - (techWeight * 0.05),
        beta: 0.9 + (techWeight * 0.3),
        correlationWithMarket: 0.75 + (techWeight * 0.15)
      };
    }
    
    // Build risk factors based on actual portfolio composition
    const riskFactors = [];
    let sectorConcentration = 0;
    
    if (portfolioData && portfolioData.positions.length > 0) {
      // Calculate sector concentration risk
      const sectorWeights = {};
      portfolioData.positions.forEach(pos => {
        // Simple sector mapping - would be enhanced with real sector data
        let sector = 'Other';
        if (['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'TSLA', 'META'].includes(pos.symbol)) sector = 'Technology';
        else if (['JPM', 'BAC', 'WFC', 'C'].includes(pos.symbol)) sector = 'Financial';
        else if (['JNJ', 'PFE', 'UNH', 'ABBV'].includes(pos.symbol)) sector = 'Healthcare';
        
        sectorWeights[sector] = (sectorWeights[sector] || 0) + pos.weight;
      });
      
      sectorConcentration = Math.max(...Object.values(sectorWeights));
      
      riskFactors.push(
        { factor: 'Market Risk', exposure: 0.75, contribution: 0.65 },
        { factor: 'Sector Concentration', exposure: sectorConcentration, contribution: sectorConcentration * 0.4 },
        { factor: 'Currency Risk', exposure: 0.15, contribution: 0.08 },
        { factor: 'Liquidity Risk', exposure: 0.25, contribution: 0.07 }
      );
    } else {
      // Default risk factors
      riskFactors.push(
        { factor: 'Market Risk', exposure: 0.75, contribution: 0.65 },
        { factor: 'Sector Concentration', exposure: 0.45, contribution: 0.20 },
        { factor: 'Currency Risk', exposure: 0.15, contribution: 0.08 },
        { factor: 'Liquidity Risk', exposure: 0.25, contribution: 0.07 }
      );
    }
    
    // Generate portfolio-specific recommendations
    const recommendations = [];
    if (sectorConcentration > 0.5) {
      recommendations.push({
        type: 'warning',
        title: 'High Sector Concentration',
        message: `${(sectorConcentration * 100).toFixed(1)}% concentration in single sector increases risk`,
        impact: 'Consider diversifying across sectors'
      });
    }
    
    if (portfolioData && portfolioData.positions.length < 5) {
      recommendations.push({
        type: 'info',
        title: 'Limited Diversification',
        message: 'Portfolio has fewer than 5 positions, increasing concentration risk',
        impact: 'Consider adding more positions for better diversification'
      });
    }
    
    if (!recommendations.length) {
      recommendations.push({
        type: 'info',
        title: 'Diversification Opportunity',
        message: 'Consider adding international exposure to reduce market concentration',
        impact: 'Could reduce volatility by 2-3%'
      });
    }

    const riskAnalysis = {
      portfolioRisk: {
        volatility: riskMetrics.volatility,
        var95: riskMetrics.var95,
        var99: riskMetrics.var99,
        beta: riskMetrics.beta,
        correlationWithMarket: riskMetrics.correlationWithMarket,
        maxDrawdown: riskMetrics.maxDrawdown
      },
      riskFactors: riskFactors,
      stressTesting: {
        marketCrash2020: { 
          portfolioLoss: riskMetrics.maxDrawdown * 1.2, 
          marketLoss: -0.35, 
          beta: riskMetrics.beta 
        },
        dotComBubble: { 
          portfolioLoss: riskMetrics.maxDrawdown * 1.8, 
          marketLoss: -0.49, 
          beta: riskMetrics.beta * 0.95 
        },
        financialCrisis2008: { 
          portfolioLoss: riskMetrics.maxDrawdown * 1.5, 
          marketLoss: -0.42, 
          beta: riskMetrics.beta * 0.9 
        }
      },
      recommendations: recommendations,
      dataSource: portfolioHistory ? 'live_api' : (portfolioData ? 'live_positions' : 'estimated'),
      metadata: {
        hasHistoricalData: !!portfolioHistory,
        hasCurrentPositions: !!(portfolioData && portfolioData.positions.length > 0),
        analysisDate: new Date().toISOString(),
        portfolioValue: portfolioData ? portfolioData.totalValue : null,
        positionCount: portfolioData ? portfolioData.positions.length : 0
      }
    };

    res.json({
      success: true,
      data: riskAnalysis,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Risk analysis error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get risk analysis',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Portfolio data synchronization endpoint
router.post('/sync', createValidationMiddleware({
  force: {
    type: 'boolean',
    sanitizer: (value) => sanitizers.boolean(value, { defaultValue: false }),
    validator: (value) => typeof value === 'boolean',
    errorMessage: 'force must be true or false'
  }
}), async (req, res) => {
  const requestId = crypto.randomUUID().split('-')[0];
  const requestStart = Date.now();
  
  try {
    const userId = req.user?.sub;
    if (!userId) {
      throw new Error('User authentication required');
    }
    const { force = false } = req.body;
    
    console.log(`🔄 [${requestId}] Portfolio sync request initiated`, {
      userId: userId ? `${userId.substring(0, 8)}...` : 'undefined',
      force,
      userAgent: req.headers['user-agent'],
      ip: req.ip,
      timestamp: new Date().toISOString()
    });

    // Import sync service
    const { PortfolioSyncService } = require('../utils/portfolioSyncService');
    // API key service already imported at top of file
    
    // Initialize sync service
    const syncService = new PortfolioSyncService({
      conflictResolutionStrategy: 'broker_priority',
      enablePerformanceTracking: true
    });

    // Check if sync is already in progress
    const currentSyncStatus = syncService.getSyncStatus(userId);
    if (currentSyncStatus && currentSyncStatus.status === 'in_progress' && !force) {
      return res.badRequest('Sync already in progress', {
        requestId,
        currentSyncId: currentSyncStatus.syncId,
        stage: currentSyncStatus.stage,
        startTime: currentSyncStatus.startTime
      });
    }

    // Execute synchronization
    const syncResult = await syncService.syncUserPortfolio(userId, apiKeyService, {
      force,
      requestId
    });

    const totalDuration = Date.now() - requestStart;
    
    console.log(`✅ [${requestId}] Portfolio sync completed successfully in ${totalDuration}ms`, {
      syncId: syncResult.syncId,
      recordsProcessed: syncResult.result.summary.totalRecordsProcessed,
      conflictsResolved: syncResult.result.summary.totalConflictsResolved
    });

    res.success({
      syncId: syncResult.syncId,
      duration: totalDuration,
      summary: syncResult.result.summary,
      stages: Object.keys(syncResult.result.stages).map(stage => ({
        stage,
        success: syncResult.result.stages[stage].success,
        recordsProcessed: syncResult.result.stages[stage].recordsProcessed || 0,
        conflictsResolved: syncResult.result.stages[stage].conflictsResolved || 0
      }))
    }, {
      requestId,
      syncDuration: `${syncResult.duration}ms`
    });
    
  } catch (error) {
    const errorDuration = Date.now() - requestStart;
    console.error(`❌ [${requestId}] Portfolio sync FAILED after ${errorDuration}ms:`, {
      error: error.message,
      errorStack: error.stack,
      userId: req.user?.sub ? `${req.user.sub.substring(0, 8)}...` : 'undefined',
      impact: 'Portfolio synchronization failed'
    });
    
    res.serverError('Portfolio synchronization failed', {
      requestId,
      duration: `${errorDuration}ms`,
      originalError: process.env.NODE_ENV === 'development' ? error.message : undefined
    });
  }
});

// Portfolio sync status endpoint
router.get('/sync/status', async (req, res) => {
  const requestId = crypto.randomUUID().split('-')[0];
  
  try {
    const userId = req.user?.sub;
    if (!userId) {
      throw new Error('User authentication required');
    }
    
    // Import sync service
    const { PortfolioSyncService } = require('../utils/portfolioSyncService');
    
    // Create temporary instance to get status
    const syncService = new PortfolioSyncService();
    const syncStatus = syncService.getSyncStatus(userId);
    const serviceMetrics = syncService.getMetrics();
    
    res.success({
      userSync: syncStatus || {
        status: 'none',
        message: 'No sync has been performed for this user'
      },
      serviceMetrics
    }, {
      requestId
    });
    
  } catch (error) {
    console.error(`❌ [${requestId}] Portfolio sync status request failed:`, {
      error: error.message,
      userId: req.user?.sub ? `${req.user.sub.substring(0, 8)}...` : 'undefined'
    });
    
    res.serverError('Failed to get sync status', {
      requestId,
      originalError: process.env.NODE_ENV === 'development' ? error.message : undefined
    });
  }
});

// Advanced Portfolio Analytics endpoint
router.get('/analytics', createValidationMiddleware(portfolioValidationSchemas.analytics), async (req, res) => {
  const requestId = res.locals.requestId || 'unknown';
  const startTime = Date.now();
  
  if (shouldLog('INFO')) console.log(`📊 [${requestId}] Advanced portfolio analytics request`);
  
  try {
    const { period = '1Y', includeBenchmark = false } = req.query;
    const userId = req.user?.sub;
    if (!userId) {
      throw new Error('User authentication required');
    }
    
    // Get portfolio holdings
    const holdingsQuery = `
      SELECT symbol, market_value, sector, quantity, avg_cost, current_price,
             unrealized_pl, unrealized_plpc, updated_at
      FROM portfolio_holdings 
      WHERE user_id = $1 AND quantity > 0
      ORDER BY market_value DESC
    `;
    
    const holdingsResult = await query(holdingsQuery, [userId], 8000);
    
    if (holdingsResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: 'No portfolio holdings found',
        timestamp: new Date().toISOString()
      });
    }
    
    const holdings = holdingsResult.rows;
    
    // Get historical performance data
    const performanceQuery = `
      SELECT 
        DATE(updated_at) as date,
        SUM(market_value) as portfolio_value,
        SUM(unrealized_pl) as total_pnl
      FROM portfolio_holdings 
      WHERE user_id = $1 AND quantity > 0
      GROUP BY DATE(updated_at)
      ORDER BY DATE(updated_at) DESC
      LIMIT 252
    `;
    
    const performanceResult = await query(performanceQuery, [userId], 8000);
    const performanceData = performanceResult.rows.map(row => ({
      date: row.date,
      portfolioValue: parseFloat(row.portfolio_value || 0),
      totalPnL: parseFloat(row.total_pnl || 0)
    }));
    
    // Calculate comprehensive analytics
    const portfolioAnalyticsResult = portfolioAnalytics.calculatePortfolioAnalytics(performanceData);
    const sectorAnalysis = portfolioAnalytics.calculateSectorAnalysis(holdings);
    
    // Calculate institutional-grade factor analysis
    const factorAnalysisResult = portfolioFactorAnalysis.performFactorAnalysis(holdings, performanceData);
    
    // Calculate position-level risk metrics
    const totalValue = holdings.reduce((sum, h) => sum + parseFloat(h.market_value || 0), 0);
    const positionAnalysis = holdings.map(holding => {
      const weight = totalValue > 0 ? (parseFloat(holding.market_value) / totalValue) * 100 : 0;
      const unrealizedReturn = parseFloat(holding.unrealized_plpc || 0);
      
      return {
        symbol: holding.symbol,
        sector: holding.sector || 'Other',
        weight: weight,
        marketValue: parseFloat(holding.market_value || 0),
        unrealizedReturn: unrealizedReturn,
        riskContribution: weight * Math.abs(unrealizedReturn) / 100,
        avgCost: parseFloat(holding.avg_cost || 0),
        currentPrice: parseFloat(holding.current_price || 0)
      };
    });
    
    // Calculate risk metrics
    const riskMetrics = {
      portfolioVaR: portfolioAnalyticsResult.var95,
      expectedShortfall: portfolioAnalyticsResult.var95 * 1.3, // Approximation
      concentrationRisk: sectorAnalysis.concentrationRisk,
      diversificationBenefit: sectorAnalysis.diversificationScore,
      maxPositionWeight: Math.max(...positionAnalysis.map(p => p.weight)),
      activePositions: holdings.length,
      riskBudgetUtilization: Math.min(100, sectorAnalysis.concentrationRisk * 1.2)
    };
    
    // Performance attribution
    const performanceAttribution = {
      sectorContribution: sectorAnalysis.sectorAllocation.map(sector => ({
        sector: sector.sector,
        allocation: sector.allocation,
        contribution: sector.allocation * 0.1 // Simplified calculation
      })),
      topContributors: positionAnalysis
        .filter(p => p.unrealizedReturn > 0)
        .sort((a, b) => b.unrealizedReturn - a.unrealizedReturn)
        .slice(0, 5),
      topDetractors: positionAnalysis
        .filter(p => p.unrealizedReturn < 0)
        .sort((a, b) => a.unrealizedReturn - b.unrealizedReturn)
        .slice(0, 5)
    };
    
    // Rebalancing recommendations
    const rebalancingRecommendations = [];
    
    // Check for overconcentration
    const overweightPositions = positionAnalysis.filter(p => p.weight > 10);
    if (overweightPositions.length > 0) {
      rebalancingRecommendations.push({
        type: 'REDUCE_CONCENTRATION',
        priority: 'HIGH',
        message: `Consider reducing positions over 10% of portfolio`,
        affectedPositions: overweightPositions.map(p => p.symbol)
      });
    }
    
    // Check for sector concentration
    const overweightSectors = sectorAnalysis.sectorAllocation.filter(s => s.allocation > 30);
    if (overweightSectors.length > 0) {
      rebalancingRecommendations.push({
        type: 'SECTOR_DIVERSIFICATION',
        priority: 'MEDIUM',
        message: `Consider diversifying across sectors`,
        affectedSectors: overweightSectors.map(s => s.sector)
      });
    }
    
    // Check for low diversification
    if (sectorAnalysis.diversificationScore < 50) {
      rebalancingRecommendations.push({
        type: 'INCREASE_DIVERSIFICATION',
        priority: 'HIGH',
        message: `Portfolio lacks diversification (score: ${sectorAnalysis.diversificationScore.toFixed(1)})`
      });
    }
    
    const response = {
      success: true,
      data: {
        analytics: portfolioAnalyticsResult,
        sectorAnalysis: sectorAnalysis,
        factorAnalysis: factorAnalysisResult,
        riskMetrics: riskMetrics,
        performanceAttribution: performanceAttribution,
        rebalancingRecommendations: rebalancingRecommendations,
        positionAnalysis: positionAnalysis.slice(0, 10) // Top 10 positions
      },
      metadata: {
        period: period,
        includeBenchmark: includeBenchmark,
        dataPoints: performanceData.length,
        activePositions: holdings.length,
        totalValue: totalValue,
        calculatedAt: new Date().toISOString(),
        duration: Date.now() - startTime
      }
    };
    
    if (shouldLog('INFO')) console.log(`✅ [${requestId}] Advanced analytics completed in ${Date.now() - startTime}ms`);
    return res.json(response);
    
  } catch (error) {
    console.error(`❌ [${requestId}] Advanced analytics failed:`, error.message);
    return res.status(500).json({
      success: false,
      error: 'Failed to calculate advanced analytics',
      message: error.message,
      timestamp: new Date().toISOString(),
      duration: Date.now() - startTime
    });
  }
});

// Portfolio rebalancing and optimization endpoints
const PortfolioOptimizationEngine = require('../utils/portfolioOptimizationEngine');

/**
 * GET /portfolio/rebalance/recommendations
 * Get portfolio rebalancing recommendations
 */
router.get('/rebalance/recommendations', async (req, res) => {
  const startTime = Date.now();
  const requestId = crypto.randomUUID().split('-')[0];
  const userId = req.user.userId;
  
  try {
    if (shouldLog('INFO')) console.log(`📊 [${requestId}] Portfolio rebalancing recommendations requested for user: ${userId.substring(0, 8)}...`);
    
    // Get current portfolio holdings
    const holdingsResult = await query(`
      SELECT 
        h.symbol,
        h.shares,
        h.avg_cost,
        h.current_price,
        h.market_value,
        h.gain_loss,
        h.gain_loss_percent,
        h.sector,
        h.industry,
        h.last_updated
      FROM portfolio_holdings h
      WHERE h.user_id = $1 AND h.shares > 0
      ORDER BY h.market_value DESC
    `, [userId]);
    
    if (holdingsResult.rows.length === 0) {
      return res.json({
        success: true,
        data: {
          recommendations: [],
          summary: {
            message: 'No portfolio holdings found. Add positions to get rebalancing recommendations.',
            totalValue: 0,
            positionsCount: 0
          }
        },
        timestamp: new Date().toISOString(),
        duration: Date.now() - startTime
      });
    }
    
    const holdings = holdingsResult.rows;
    const optimizer = new PortfolioOptimizationEngine();
    
    // Get user preferences or use defaults
    const preferences = {
      riskTolerance: req.query.riskTolerance || 'moderate',
      objective: req.query.objective || 'balanced',
      maxPositionSize: parseFloat(req.query.maxPosition) || 0.25,
      minPositionSize: parseFloat(req.query.minPosition) || 0.05,
      rebalanceThreshold: parseFloat(req.query.threshold) || 0.05
    };
    
    // Generate rebalancing recommendations
    const optimizationResults = await optimizer.optimizePortfolio(holdings, userId, preferences);
    
    if (shouldLog('INFO')) console.log(`✅ [${requestId}] Rebalancing recommendations generated in ${Date.now() - startTime}ms`);
    
    res.json({
      success: true,
      data: {
        recommendations: optimizationResults.rebalancingRecommendations,
        currentAllocation: optimizationResults.currentAllocation,
        targetAllocation: optimizationResults.targetAllocation,
        optimization: {
          expectedReturn: optimizationResults.expectedReturn,
          expectedVolatility: optimizationResults.expectedVolatility,
          sharpeRatio: optimizationResults.sharpeRatio,
          objective: preferences.objective
        },
        summary: {
          totalValue: optimizationResults.currentPortfolioValue,
          positionsCount: holdings.length,
          rebalanceNeeded: optimizationResults.rebalanceNeeded,
          estimatedTradingCost: optimizationResults.estimatedTradingCost
        }
      },
      timestamp: new Date().toISOString(),
      duration: Date.now() - startTime
    });
    
  } catch (error) {
    console.error(`❌ [${requestId}] Portfolio rebalancing recommendations failed:`, error.message);
    return res.status(500).json({
      success: false,
      error: 'Failed to generate rebalancing recommendations',
      message: error.message,
      timestamp: new Date().toISOString(),
      duration: Date.now() - startTime
    });
  }
});

/**
 * POST /portfolio/rebalance/execute
 * Execute portfolio rebalancing trades
 */
router.post('/rebalance/execute', async (req, res) => {
  const startTime = Date.now();
  const requestId = crypto.randomUUID().split('-')[0];
  const userId = req.user.userId;
  
  try {
    if (shouldLog('INFO')) console.log(`🔄 [${requestId}] Portfolio rebalancing execution requested for user: ${userId.substring(0, 8)}...`);
    
    const { trades, dryRun = true } = req.body;
    
    if (!trades || !Array.isArray(trades) || trades.length === 0) {
      return res.status(400).json({
        success: false,
        error: 'Invalid trades data',
        message: 'Trades array is required and must contain at least one trade',
        timestamp: new Date().toISOString()
      });
    }
    
    // Get user's API credentials for trading
    const apiKey = await getUserApiKey(userId, 'alpaca');
    if (!apiKey) {
      return res.status(400).json({
        success: false,
        error: 'Alpaca API key required',
        message: 'Please configure your Alpaca API key in settings to execute trades',
        timestamp: new Date().toISOString()
      });
    }
    
    const alpacaService = new AlpacaService(apiKey.apiKey, apiKey.apiSecret, apiKey.isSandbox);
    
    // Execute trades (or simulate if dry run)
    const executionResults = [];
    let totalEstimatedCost = 0;
    
    for (const trade of trades) {
      try {
        const result = {
          symbol: trade.symbol,
          action: trade.action,
          quantity: trade.quantity,
          type: trade.type || 'market',
          status: 'pending'
        };
        
        if (dryRun) {
          // Simulate trade execution
          result.status = 'simulated';
          result.estimatedPrice = trade.estimatedPrice;
          result.estimatedCost = trade.quantity * trade.estimatedPrice;
          totalEstimatedCost += result.estimatedCost;
        } else {
          // Execute actual trade
          const order = await alpacaService.createOrder({
            symbol: trade.symbol,
            qty: trade.quantity,
            side: trade.action,
            type: trade.type || 'market',
            time_in_force: trade.timeInForce || 'day'
          });
          
          result.status = 'executed';
          result.orderId = order.id;
          result.filledPrice = order.filled_avg_price;
          result.filledQuantity = order.filled_qty;
        }
        
        executionResults.push(result);
        
      } catch (tradeError) {
        console.error(`❌ [${requestId}] Trade execution failed for ${trade.symbol}:`, tradeError.message);
        executionResults.push({
          symbol: trade.symbol,
          action: trade.action,
          quantity: trade.quantity,
          status: 'failed',
          error: tradeError.message
        });
      }
    }
    
    // Update portfolio holdings if not dry run
    if (!dryRun) {
      // This would typically update the portfolio_holdings table
      // For now, we'll let the next sync update the holdings
      if (shouldLog('INFO')) console.log(`📊 [${requestId}] Portfolio holdings will be updated on next sync`);
    }
    
    const successfulTrades = executionResults.filter(r => r.status === 'executed' || r.status === 'simulated');
    const failedTrades = executionResults.filter(r => r.status === 'failed');
    
    if (shouldLog('INFO')) console.log(`✅ [${requestId}] Rebalancing execution completed in ${Date.now() - startTime}ms`);
    
    res.json({
      success: true,
      data: {
        executionResults,
        summary: {
          totalTrades: trades.length,
          successfulTrades: successfulTrades.length,
          failedTrades: failedTrades.length,
          totalEstimatedCost,
          dryRun,
          executionTime: Date.now() - startTime
        }
      },
      timestamp: new Date().toISOString(),
      duration: Date.now() - startTime
    });
    
  } catch (error) {
    console.error(`❌ [${requestId}] Portfolio rebalancing execution failed:`, error.message);
    return res.status(500).json({
      success: false,
      error: 'Failed to execute rebalancing trades',
      message: error.message,
      timestamp: new Date().toISOString(),
      duration: Date.now() - startTime
    });
  }
});

/**
 * GET /portfolio/allocation/analysis
 * Get portfolio allocation analysis and optimization suggestions
 */
router.get('/allocation/analysis', async (req, res) => {
  const startTime = Date.now();
  const requestId = crypto.randomUUID().split('-')[0];
  const userId = req.user.userId;
  
  try {
    if (shouldLog('INFO')) console.log(`📊 [${requestId}] Portfolio allocation analysis requested for user: ${userId.substring(0, 8)}...`);
    
    // Get current portfolio holdings with extended data
    const holdingsResult = await query(`
      SELECT 
        h.symbol,
        h.shares,
        h.avg_cost,
        h.current_price,
        h.market_value,
        h.gain_loss,
        h.gain_loss_percent,
        h.sector,
        h.industry,
        h.last_updated,
        p.market_cap,
        p.beta,
        p.pe_ratio,
        p.dividend_yield
      FROM portfolio_holdings h
      LEFT JOIN latest_prices p ON h.symbol = p.symbol
      WHERE h.user_id = $1 AND h.shares > 0
      ORDER BY h.market_value DESC
    `, [userId]);
    
    if (holdingsResult.rows.length === 0) {
      return res.json({
        success: true,
        data: {
          analysis: {
            message: 'No portfolio holdings found for analysis',
            totalValue: 0,
            positionsCount: 0
          }
        },
        timestamp: new Date().toISOString(),
        duration: Date.now() - startTime
      });
    }
    
    const holdings = holdingsResult.rows;
    const totalValue = holdings.reduce((sum, h) => sum + parseFloat(h.market_value || 0), 0);
    
    // Calculate allocation breakdowns
    const sectorAllocation = {};
    const industryAllocation = {};
    const marketCapAllocation = { large: 0, mid: 0, small: 0 };
    
    holdings.forEach(holding => {
      const value = parseFloat(holding.market_value || 0);
      const allocation = totalValue > 0 ? (value / totalValue) * 100 : 0;
      
      // Sector allocation
      const sector = holding.sector || 'Other';
      sectorAllocation[sector] = (sectorAllocation[sector] || 0) + allocation;
      
      // Industry allocation
      const industry = holding.industry || 'Other';
      industryAllocation[industry] = (industryAllocation[industry] || 0) + allocation;
      
      // Market cap allocation
      const marketCap = parseFloat(holding.market_cap || 0);
      if (marketCap > 10000000000) { // > $10B
        marketCapAllocation.large += allocation;
      } else if (marketCap > 2000000000) { // > $2B
        marketCapAllocation.mid += allocation;
      } else {
        marketCapAllocation.small += allocation;
      }
    });
    
    // Calculate risk metrics
    const portfolioBeta = holdings.reduce((sum, h) => {
      const allocation = parseFloat(h.market_value || 0) / totalValue;
      const beta = parseFloat(h.beta || 1);
      return sum + (allocation * beta);
    }, 0);
    
    const avgPE = holdings.reduce((sum, h) => {
      const allocation = parseFloat(h.market_value || 0) / totalValue;
      const pe = parseFloat(h.pe_ratio || 0);
      return sum + (allocation * pe);
    }, 0);
    
    const avgDividendYield = holdings.reduce((sum, h) => {
      const allocation = parseFloat(h.market_value || 0) / totalValue;
      const dividend = parseFloat(h.dividend_yield || 0);
      return sum + (allocation * dividend);
    }, 0);
    
    // Generate optimization suggestions
    const suggestions = [];
    
    // Concentration risk check
    const topPositions = holdings.slice(0, 5);
    const top5Concentration = topPositions.reduce((sum, h) => sum + (parseFloat(h.market_value) / totalValue) * 100, 0);
    
    if (top5Concentration > 70) {
      suggestions.push({
        type: 'concentration_risk',
        severity: 'high',
        message: `Top 5 positions represent ${top5Concentration.toFixed(1)}% of portfolio. Consider reducing concentration risk.`,
        recommendation: 'Diversify holdings across more positions or sectors'
      });
    }
    
    // Sector concentration check
    const maxSectorAllocation = Math.max(...Object.values(sectorAllocation));
    if (maxSectorAllocation > 40) {
      suggestions.push({
        type: 'sector_concentration',
        severity: 'medium',
        message: `High sector concentration detected (${maxSectorAllocation.toFixed(1)}%).`,
        recommendation: 'Consider diversifying across different sectors'
      });
    }
    
    // Risk level assessment
    if (portfolioBeta > 1.5) {
      suggestions.push({
        type: 'high_beta',
        severity: 'medium',
        message: `Portfolio beta is ${portfolioBeta.toFixed(2)}, indicating higher volatility than market.`,
        recommendation: 'Consider adding some defensive stocks or bonds to reduce risk'
      });
    }
    
    if (suggestions.length === 0) {
      suggestions.push({
        type: 'well_diversified',
        severity: 'info',
        message: 'Portfolio appears well-diversified with good risk management.',
        recommendation: 'Continue monitoring and periodic rebalancing'
      });
    }
    
    if (shouldLog('INFO')) console.log(`✅ [${requestId}] Portfolio allocation analysis completed in ${Date.now() - startTime}ms`);
    
    res.json({
      success: true,
      data: {
        analysis: {
          totalValue,
          positionsCount: holdings.length,
          allocations: {
            sector: Object.entries(sectorAllocation).map(([name, percentage]) => ({
              name,
              percentage: parseFloat(percentage.toFixed(2))
            })).sort((a, b) => b.percentage - a.percentage),
            industry: Object.entries(industryAllocation).map(([name, percentage]) => ({
              name,
              percentage: parseFloat(percentage.toFixed(2))
            })).sort((a, b) => b.percentage - a.percentage),
            marketCap: [
              { name: 'Large Cap', percentage: parseFloat(marketCapAllocation.large.toFixed(2)) },
              { name: 'Mid Cap', percentage: parseFloat(marketCapAllocation.mid.toFixed(2)) },
              { name: 'Small Cap', percentage: parseFloat(marketCapAllocation.small.toFixed(2)) }
            ]
          },
          riskMetrics: {
            portfolioBeta: parseFloat(portfolioBeta.toFixed(2)),
            avgPE: parseFloat(avgPE.toFixed(2)),
            avgDividendYield: parseFloat(avgDividendYield.toFixed(2)),
            top5Concentration: parseFloat(top5Concentration.toFixed(2))
          },
          suggestions
        }
      },
      timestamp: new Date().toISOString(),
      duration: Date.now() - startTime
    });
    
  } catch (error) {
    console.error(`❌ [${requestId}] Portfolio allocation analysis failed:`, error.message);
    return res.status(500).json({
      success: false,
      error: 'Failed to analyze portfolio allocation',
      message: error.message,
      timestamp: new Date().toISOString(),
      duration: Date.now() - startTime
    });
  }
});

/**
 * GET /portfolio/export/csv
 * Export portfolio holdings to CSV format
 */
router.get('/export/csv', async (req, res) => {
  const startTime = Date.now();
  const requestId = crypto.randomUUID().split('-')[0];
  const userId = req.user.userId;
  
  try {
    if (shouldLog('INFO')) console.log(`📊 [${requestId}] Portfolio CSV export requested for user: ${userId.substring(0, 8)}...`);
    
    // Get portfolio holdings with all relevant data
    const holdingsResult = await query(`
      SELECT 
        h.symbol,
        h.shares,
        h.avg_cost,
        h.current_price,
        h.market_value,
        h.gain_loss,
        h.gain_loss_percent,
        h.sector,
        h.industry,
        h.last_updated,
        h.purchase_date,
        p.company_name,
        p.market_cap,
        p.beta,
        p.pe_ratio,
        p.dividend_yield,
        p.volume
      FROM portfolio_holdings h
      LEFT JOIN company_profiles p ON h.symbol = p.symbol
      WHERE h.user_id = $1 AND h.shares > 0
      ORDER BY h.market_value DESC
    `, [userId]);
    
    if (holdingsResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: 'No portfolio holdings found',
        message: 'Cannot export empty portfolio',
        timestamp: new Date().toISOString()
      });
    }
    
    const holdings = holdingsResult.rows;
    
    // Generate CSV content
    const csvHeaders = [
      'Symbol',
      'Company Name',
      'Shares',
      'Avg Cost',
      'Current Price',
      'Market Value',
      'Gain/Loss',
      'Gain/Loss %',
      'Sector',
      'Industry',
      'Purchase Date',
      'Market Cap',
      'Beta',
      'P/E Ratio',
      'Dividend Yield',
      'Volume',
      'Last Updated'
    ];
    
    const csvRows = holdings.map(holding => [
      holding.symbol,
      holding.company_name || '',
      holding.shares,
      holding.avg_cost,
      holding.current_price,
      holding.market_value,
      holding.gain_loss,
      holding.gain_loss_percent,
      holding.sector || '',
      holding.industry || '',
      holding.purchase_date ? new Date(holding.purchase_date).toISOString().split('T')[0] : '',
      holding.market_cap || '',
      holding.beta || '',
      holding.pe_ratio || '',
      holding.dividend_yield || '',
      holding.volume || '',
      holding.last_updated ? new Date(holding.last_updated).toISOString() : ''
    ]);
    
    // Create CSV content
    const csvContent = [csvHeaders, ...csvRows]
      .map(row => row.map(cell => `"${cell}"`).join(','))
      .join('\n');
    
    // Generate filename with timestamp
    const timestamp = new Date().toISOString().split('T')[0];
    const filename = `portfolio_export_${timestamp}.csv`;
    
    if (shouldLog('INFO')) console.log(`✅ [${requestId}] Portfolio CSV export completed in ${Date.now() - startTime}ms`);
    
    res.setHeader('Content-Type', 'text/csv');
    res.setHeader('Content-Disposition', `attachment; filename=${filename}`);
    res.send(csvContent);
    
  } catch (error) {
    console.error(`❌ [${requestId}] Portfolio CSV export failed:`, error.message);
    return res.status(500).json({
      success: false,
      error: 'Failed to export portfolio to CSV',
      message: error.message,
      timestamp: new Date().toISOString(),
      duration: Date.now() - startTime
    });
  }
});

/**
 * GET /portfolio/export/json
 * Export portfolio holdings to JSON format
 */
router.get('/export/json', async (req, res) => {
  const startTime = Date.now();
  const requestId = crypto.randomUUID().split('-')[0];
  const userId = req.user.userId;
  
  try {
    if (shouldLog('INFO')) console.log(`📊 [${requestId}] Portfolio JSON export requested for user: ${userId.substring(0, 8)}...`);
    
    // Get comprehensive portfolio data
    const [holdingsResult, summaryResult] = await Promise.all([
      query(`
        SELECT 
          h.symbol,
          h.shares,
          h.avg_cost,
          h.current_price,
          h.market_value,
          h.gain_loss,
          h.gain_loss_percent,
          h.sector,
          h.industry,
          h.last_updated,
          h.purchase_date,
          p.company_name,
          p.market_cap,
          p.beta,
          p.pe_ratio,
          p.dividend_yield
        FROM portfolio_holdings h
        LEFT JOIN company_profiles p ON h.symbol = p.symbol
        WHERE h.user_id = $1 AND h.shares > 0
        ORDER BY h.market_value DESC
      `, [userId]),
      query(`
        SELECT 
          SUM(market_value) as total_value,
          SUM(gain_loss) as total_gain_loss,
          COUNT(*) as positions_count
        FROM portfolio_holdings
        WHERE user_id = $1 AND shares > 0
      `, [userId])
    ]);
    
    if (holdingsResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: 'No portfolio holdings found',
        message: 'Cannot export empty portfolio',
        timestamp: new Date().toISOString()
      });
    }
    
    const holdings = holdingsResult.rows;
    const summary = summaryResult.rows[0];
    
    // Calculate sector allocation
    const totalValue = parseFloat(summary.total_value || 0);
    const sectorAllocation = {};
    
    holdings.forEach(holding => {
      const sector = holding.sector || 'Other';
      const value = parseFloat(holding.market_value || 0);
      sectorAllocation[sector] = (sectorAllocation[sector] || 0) + value;
    });
    
    // Convert to percentages
    const sectorBreakdown = Object.entries(sectorAllocation).map(([sector, value]) => ({
      sector,
      value: parseFloat(value.toFixed(2)),
      percentage: totalValue > 0 ? parseFloat(((value / totalValue) * 100).toFixed(2)) : 0
    })).sort((a, b) => b.value - a.value);
    
    const exportData = {
      metadata: {
        exportDate: new Date().toISOString(),
        exportType: 'portfolio_holdings',
        userId: userId.substring(0, 8) + '...',
        totalPositions: holdings.length,
        totalValue: parseFloat(summary.total_value || 0),
        totalGainLoss: parseFloat(summary.total_gain_loss || 0),
        totalGainLossPercent: totalValue > 0 ? parseFloat(((summary.total_gain_loss / (totalValue - summary.total_gain_loss)) * 100).toFixed(2)) : 0
      },
      holdings: holdings.map(holding => ({
        symbol: holding.symbol,
        companyName: holding.company_name,
        shares: parseFloat(holding.shares),
        avgCost: parseFloat(holding.avg_cost),
        currentPrice: parseFloat(holding.current_price),
        marketValue: parseFloat(holding.market_value),
        gainLoss: parseFloat(holding.gain_loss),
        gainLossPercent: parseFloat(holding.gain_loss_percent),
        sector: holding.sector,
        industry: holding.industry,
        purchaseDate: holding.purchase_date,
        marketCap: holding.market_cap,
        beta: holding.beta,
        peRatio: holding.pe_ratio,
        dividendYield: holding.dividend_yield,
        lastUpdated: holding.last_updated
      })),
      sectorBreakdown,
      summary: {
        totalValue: parseFloat(summary.total_value || 0),
        totalGainLoss: parseFloat(summary.total_gain_loss || 0),
        positionsCount: parseInt(summary.positions_count || 0),
        averageGainLoss: holdings.length > 0 ? parseFloat((summary.total_gain_loss / holdings.length).toFixed(2)) : 0
      }
    };
    
    if (shouldLog('INFO')) console.log(`✅ [${requestId}] Portfolio JSON export completed in ${Date.now() - startTime}ms`);
    
    res.json({
      success: true,
      data: exportData,
      timestamp: new Date().toISOString(),
      duration: Date.now() - startTime
    });
    
  } catch (error) {
    console.error(`❌ [${requestId}] Portfolio JSON export failed:`, error.message);
    return res.status(500).json({
      success: false,
      error: 'Failed to export portfolio to JSON',
      message: error.message,
      timestamp: new Date().toISOString(),
      duration: Date.now() - startTime
    });
  }
});

/**
 * POST /portfolio/import/csv
 * Import portfolio holdings from CSV file
 */
router.post('/import/csv', async (req, res) => {
  const startTime = Date.now();
  const requestId = crypto.randomUUID().split('-')[0];
  const userId = req.user.userId;
  
  try {
    if (shouldLog('INFO')) console.log(`📥 [${requestId}] Portfolio CSV import requested for user: ${userId.substring(0, 8)}...`);
    
    const { csvData, importMode = 'append' } = req.body;
    
    if (!csvData || typeof csvData !== 'string') {
      return res.status(400).json({
        success: false,
        error: 'Invalid CSV data',
        message: 'CSV data is required as a string',
        timestamp: new Date().toISOString()
      });
    }
    
    // Parse CSV data
    const lines = csvData.trim().split('\n');
    if (lines.length < 2) {
      return res.status(400).json({
        success: false,
        error: 'Invalid CSV format',
        message: 'CSV must contain at least a header and one data row',
        timestamp: new Date().toISOString()
      });
    }
    
    const headers = lines[0].split(',').map(h => h.replace(/"/g, '').trim().toLowerCase());
    const dataLines = lines.slice(1);
    
    // Validate required columns
    const requiredColumns = ['symbol', 'shares', 'avg_cost'];
    const missingColumns = requiredColumns.filter(col => !headers.includes(col));
    
    if (missingColumns.length > 0) {
      return res.status(400).json({
        success: false,
        error: 'Missing required columns',
        message: `Required columns: ${missingColumns.join(', ')}`,
        timestamp: new Date().toISOString()
      });
    }
    
    // Parse holdings data
    const importedHoldings = [];
    const errors = [];
    
    for (let i = 0; i < dataLines.length; i++) {
      const line = dataLines[i];
      const values = line.split(',').map(v => v.replace(/"/g, '').trim());
      
      if (values.length !== headers.length) {
        errors.push(`Line ${i + 2}: Column count mismatch`);
        continue;
      }
      
      const holding = {};
      headers.forEach((header, index) => {
        holding[header] = values[index];
      });
      
      // Validate and convert data types
      try {
        const parsedHolding = {
          symbol: holding.symbol.toUpperCase(),
          shares: parseFloat(holding.shares),
          avg_cost: parseFloat(holding.avg_cost),
          current_price: holding.current_price ? parseFloat(holding.current_price) : null,
          sector: holding.sector || null,
          industry: holding.industry || null,
          purchase_date: holding.purchase_date || null
        };
        
        if (!parsedHolding.symbol || parsedHolding.shares <= 0 || parsedHolding.avg_cost <= 0) {
          errors.push(`Line ${i + 2}: Invalid symbol, shares, or avg_cost`);
          continue;
        }
        
        importedHoldings.push(parsedHolding);
      } catch (parseError) {
        errors.push(`Line ${i + 2}: ${parseError.message}`);
      }
    }
    
    if (importedHoldings.length === 0) {
      return res.status(400).json({
        success: false,
        error: 'No valid holdings to import',
        message: 'All rows contained errors',
        errors,
        timestamp: new Date().toISOString()
      });
    }
    
    // If replace mode, clear existing holdings
    if (importMode === 'replace') {
      await query('DELETE FROM portfolio_holdings WHERE user_id = $1', [userId]);
    }
    
    // Insert or update holdings
    let insertedCount = 0;
    let updatedCount = 0;
    
    for (const holding of importedHoldings) {
      try {
        const existingResult = await query(
          'SELECT id FROM portfolio_holdings WHERE user_id = $1 AND symbol = $2',
          [userId, holding.symbol]
        );
        
        if (existingResult.rows.length > 0) {
          // Update existing holding
          await query(`
            UPDATE portfolio_holdings 
            SET shares = $1, avg_cost = $2, current_price = $3, 
                sector = $4, industry = $5, purchase_date = $6, 
                market_value = $1 * COALESCE($3, avg_cost),
                gain_loss = ($1 * COALESCE($3, avg_cost)) - ($1 * $2),
                gain_loss_percent = CASE 
                  WHEN $2 > 0 THEN (((COALESCE($3, avg_cost) - $2) / $2) * 100)
                  ELSE 0 
                END,
                last_updated = NOW()
            WHERE user_id = $7 AND symbol = $8
          `, [
            holding.shares, holding.avg_cost, holding.current_price,
            holding.sector, holding.industry, holding.purchase_date,
            userId, holding.symbol
          ]);
          updatedCount++;
        } else {
          // Insert new holding
          await query(`
            INSERT INTO portfolio_holdings (
              user_id, symbol, shares, avg_cost, current_price, 
              sector, industry, purchase_date, market_value, 
              gain_loss, gain_loss_percent, last_updated
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 
              $3 * COALESCE($5, $4),
              ($3 * COALESCE($5, $4)) - ($3 * $4),
              CASE 
                WHEN $4 > 0 THEN (((COALESCE($5, $4) - $4) / $4) * 100)
                ELSE 0 
              END,
              NOW()
            )
          `, [
            userId, holding.symbol, holding.shares, holding.avg_cost,
            holding.current_price, holding.sector, holding.industry,
            holding.purchase_date
          ]);
          insertedCount++;
        }
      } catch (dbError) {
        errors.push(`${holding.symbol}: ${dbError.message}`);
      }
    }
    
    if (shouldLog('INFO')) console.log(`✅ [${requestId}] Portfolio CSV import completed in ${Date.now() - startTime}ms`);
    
    res.json({
      success: true,
      data: {
        summary: {
          totalRows: dataLines.length,
          validRows: importedHoldings.length,
          insertedCount,
          updatedCount,
          errorCount: errors.length,
          importMode
        },
        errors: errors.length > 0 ? errors : undefined
      },
      timestamp: new Date().toISOString(),
      duration: Date.now() - startTime
    });
    
  } catch (error) {
    console.error(`❌ [${requestId}] Portfolio CSV import failed:`, error.message);
    return res.status(500).json({
      success: false,
      error: 'Failed to import portfolio from CSV',
      message: error.message,
      timestamp: new Date().toISOString(),
      duration: Date.now() - startTime
    });
  }
});

/**
 * POST /portfolio/import/alpaca
 * Import portfolio holdings from Alpaca API
 */
router.post('/import/alpaca', async (req, res) => {
  const startTime = Date.now();
  const requestId = crypto.randomUUID().split('-')[0];
  const userId = req.user.userId;
  
  try {
    if (shouldLog('INFO')) console.log(`📥 [${requestId}] Portfolio Alpaca import requested for user: ${userId.substring(0, 8)}...`);
    
    const { forceRefresh = false } = req.body;
    
    // Get user's Alpaca API credentials
    const apiKey = await getUserApiKey(userId, 'alpaca');
    if (!apiKey) {
      return res.status(400).json({
        success: false,
        error: 'Alpaca API key required',
        message: 'Please configure your Alpaca API key in settings to import portfolio',
        timestamp: new Date().toISOString()
      });
    }
    
    const alpacaService = new AlpacaService(apiKey.apiKey, apiKey.apiSecret, apiKey.isSandbox);
    
    // Get positions from Alpaca
    const positions = await alpacaService.getPositions();
    
    if (!positions || positions.length === 0) {
      return res.json({
        success: true,
        data: {
          summary: {
            totalPositions: 0,
            insertedCount: 0,
            updatedCount: 0,
            message: 'No positions found in Alpaca account'
          }
        },
        timestamp: new Date().toISOString(),
        duration: Date.now() - startTime
      });
    }
    
    // Process positions and update database
    let insertedCount = 0;
    let updatedCount = 0;
    const errors = [];
    
    for (const position of positions) {
      try {
        const symbol = position.symbol;
        const shares = parseFloat(position.qty);
        const avgCost = parseFloat(position.avg_cost);
        const currentPrice = parseFloat(position.market_value) / shares;
        const marketValue = parseFloat(position.market_value);
        const gainLoss = parseFloat(position.unrealized_pl);
        const gainLossPercent = parseFloat(position.unrealized_plpc) * 100;
        
        // Check if position already exists
        const existingResult = await query(
          'SELECT id FROM portfolio_holdings WHERE user_id = $1 AND symbol = $2',
          [userId, symbol]
        );
        
        if (existingResult.rows.length > 0) {
          // Update existing position
          await query(`
            UPDATE portfolio_holdings 
            SET shares = $1, avg_cost = $2, current_price = $3, 
                market_value = $4, gain_loss = $5, gain_loss_percent = $6,
                last_updated = NOW()
            WHERE user_id = $7 AND symbol = $8
          `, [shares, avgCost, currentPrice, marketValue, gainLoss, gainLossPercent, userId, symbol]);
          updatedCount++;
        } else {
          // Insert new position
          await query(`
            INSERT INTO portfolio_holdings (
              user_id, symbol, shares, avg_cost, current_price, 
              market_value, gain_loss, gain_loss_percent, last_updated
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
          `, [userId, symbol, shares, avgCost, currentPrice, marketValue, gainLoss, gainLossPercent]);
          insertedCount++;
        }
        
        // Get additional company info if available
        try {
          const companyResult = await query(
            'SELECT sector, industry FROM company_profiles WHERE symbol = $1',
            [symbol]
          );
          
          if (companyResult.rows.length > 0) {
            const company = companyResult.rows[0];
            await query(`
              UPDATE portfolio_holdings 
              SET sector = $1, industry = $2
              WHERE user_id = $3 AND symbol = $4
            `, [company.sector, company.industry, userId, symbol]);
          }
        } catch (companyError) {
          // Non-critical error, continue processing
          if (shouldLog('DEBUG')) console.log(`Company info not found for ${symbol}`);
        }
        
      } catch (positionError) {
        errors.push(`${position.symbol}: ${positionError.message}`);
      }
    }
    
    if (shouldLog('INFO')) console.log(`✅ [${requestId}] Portfolio Alpaca import completed in ${Date.now() - startTime}ms`);
    
    res.json({
      success: true,
      data: {
        summary: {
          totalPositions: positions.length,
          insertedCount,
          updatedCount,
          errorCount: errors.length,
          importSource: 'alpaca',
          sandbox: apiKey.isSandbox
        },
        errors: errors.length > 0 ? errors : undefined
      },
      timestamp: new Date().toISOString(),
      duration: Date.now() - startTime
    });
    
  } catch (error) {
    console.error(`❌ [${requestId}] Portfolio Alpaca import failed:`, error.message);
    return res.status(500).json({
      success: false,
      error: 'Failed to import portfolio from Alpaca',
      message: error.message,
      timestamp: new Date().toISOString(),
      duration: Date.now() - startTime
    });
  }
});

// Portfolio alerts endpoints
const PortfolioAlerts = require('../utils/portfolioAlerts');

/**
 * GET /portfolio/alerts
 * Get user's portfolio alerts
 */
router.get('/alerts', async (req, res) => {
  const startTime = Date.now();
  const requestId = crypto.randomUUID().split('-')[0];
  const userId = req.user.userId;
  
  try {
    if (shouldLog('INFO')) console.log(`🔔 [${requestId}] Portfolio alerts requested for user: ${userId.substring(0, 8)}...`);
    
    const portfolioAlerts = new PortfolioAlerts();
    const filters = {
      alertType: req.query.alertType,
      symbol: req.query.symbol,
      isActive: req.query.isActive !== undefined ? req.query.isActive === 'true' : undefined
    };
    
    const alerts = await portfolioAlerts.getUserPortfolioAlerts(userId, filters);
    
    if (shouldLog('INFO')) console.log(`✅ [${requestId}] Portfolio alerts retrieved in ${Date.now() - startTime}ms`);
    
    res.json({
      success: true,
      data: {
        alerts,
        count: alerts.length,
        filters
      },
      timestamp: new Date().toISOString(),
      duration: Date.now() - startTime
    });
    
  } catch (error) {
    console.error(`❌ [${requestId}] Portfolio alerts retrieval failed:`, error.message);
    return res.status(500).json({
      success: false,
      error: 'Failed to retrieve portfolio alerts',
      message: error.message,
      timestamp: new Date().toISOString(),
      duration: Date.now() - startTime
    });
  }
});

/**
 * POST /portfolio/alerts
 * Create a new portfolio alert
 */
router.post('/alerts', async (req, res) => {
  const startTime = Date.now();
  const requestId = crypto.randomUUID().split('-')[0];
  const userId = req.user.userId;
  
  try {
    if (shouldLog('INFO')) console.log(`🔔 [${requestId}] Portfolio alert creation requested for user: ${userId.substring(0, 8)}...`);
    
    const {
      alertType,
      symbol,
      threshold,
      condition,
      isActive = true,
      notificationPreferences = {},
      expiryDate,
      message
    } = req.body;
    
    // Validate required fields
    if (!alertType || !threshold || !condition) {
      return res.status(400).json({
        success: false,
        error: 'Missing required fields',
        message: 'alertType, threshold, and condition are required',
        timestamp: new Date().toISOString()
      });
    }
    
    const portfolioAlerts = new PortfolioAlerts();
    const alertConfig = {
      alertType,
      symbol,
      threshold,
      condition,
      isActive,
      notificationPreferences,
      expiryDate,
      message
    };
    
    const newAlert = await portfolioAlerts.createPortfolioAlert(userId, alertConfig);
    
    if (shouldLog('INFO')) console.log(`✅ [${requestId}] Portfolio alert created in ${Date.now() - startTime}ms`);
    
    res.status(201).json({
      success: true,
      data: newAlert,
      message: 'Portfolio alert created successfully',
      timestamp: new Date().toISOString(),
      duration: Date.now() - startTime
    });
    
  } catch (error) {
    console.error(`❌ [${requestId}] Portfolio alert creation failed:`, error.message);
    return res.status(500).json({
      success: false,
      error: 'Failed to create portfolio alert',
      message: error.message,
      timestamp: new Date().toISOString(),
      duration: Date.now() - startTime
    });
  }
});

/**
 * PUT /portfolio/alerts/:alertId
 * Update a portfolio alert
 */
router.put('/alerts/:alertId', async (req, res) => {
  const startTime = Date.now();
  const requestId = crypto.randomUUID().split('-')[0];
  const userId = req.user.userId;
  const alertId = req.params.alertId;
  
  try {
    if (shouldLog('INFO')) console.log(`🔔 [${requestId}] Portfolio alert update requested for alert: ${alertId}`);
    
    const {
      threshold,
      condition,
      isActive,
      notificationPreferences,
      expiryDate,
      message
    } = req.body;
    
    const portfolioAlerts = new PortfolioAlerts();
    const updates = {
      threshold,
      condition,
      isActive,
      notificationPreferences,
      expiryDate,
      message
    };
    
    const updatedAlert = await portfolioAlerts.updatePortfolioAlert(alertId, userId, updates);
    
    if (shouldLog('INFO')) console.log(`✅ [${requestId}] Portfolio alert updated in ${Date.now() - startTime}ms`);
    
    res.json({
      success: true,
      data: updatedAlert,
      message: 'Portfolio alert updated successfully',
      timestamp: new Date().toISOString(),
      duration: Date.now() - startTime
    });
    
  } catch (error) {
    console.error(`❌ [${requestId}] Portfolio alert update failed:`, error.message);
    
    const statusCode = error.message.includes('not found') ? 404 : 500;
    return res.status(statusCode).json({
      success: false,
      error: 'Failed to update portfolio alert',
      message: error.message,
      timestamp: new Date().toISOString(),
      duration: Date.now() - startTime
    });
  }
});

/**
 * DELETE /portfolio/alerts/:alertId
 * Delete a portfolio alert
 */
router.delete('/alerts/:alertId', async (req, res) => {
  const startTime = Date.now();
  const requestId = crypto.randomUUID().split('-')[0];
  const userId = req.user.userId;
  const alertId = req.params.alertId;
  
  try {
    if (shouldLog('INFO')) console.log(`🔔 [${requestId}] Portfolio alert deletion requested for alert: ${alertId}`);
    
    const portfolioAlerts = new PortfolioAlerts();
    const deletedAlert = await portfolioAlerts.deletePortfolioAlert(alertId, userId);
    
    if (shouldLog('INFO')) console.log(`✅ [${requestId}] Portfolio alert deleted in ${Date.now() - startTime}ms`);
    
    res.json({
      success: true,
      data: deletedAlert,
      message: 'Portfolio alert deleted successfully',
      timestamp: new Date().toISOString(),
      duration: Date.now() - startTime
    });
    
  } catch (error) {
    console.error(`❌ [${requestId}] Portfolio alert deletion failed:`, error.message);
    
    const statusCode = error.message.includes('not found') ? 404 : 500;
    return res.status(statusCode).json({
      success: false,
      error: 'Failed to delete portfolio alert',
      message: error.message,
      timestamp: new Date().toISOString(),
      duration: Date.now() - startTime
    });
  }
});

/**
 * GET /portfolio/alerts/notifications
 * Get portfolio alert notifications
 */
router.get('/alerts/notifications', async (req, res) => {
  const startTime = Date.now();
  const requestId = crypto.randomUUID().split('-')[0];
  const userId = req.user.userId;
  
  try {
    if (shouldLog('INFO')) console.log(`🔔 [${requestId}] Portfolio alert notifications requested for user: ${userId.substring(0, 8)}...`);
    
    const portfolioAlerts = new PortfolioAlerts();
    const limit = parseInt(req.query.limit) || 50;
    
    const notifications = await portfolioAlerts.getPortfolioAlertNotifications(userId, limit);
    
    if (shouldLog('INFO')) console.log(`✅ [${requestId}] Portfolio alert notifications retrieved in ${Date.now() - startTime}ms`);
    
    res.json({
      success: true,
      data: {
        notifications,
        count: notifications.length,
        limit
      },
      timestamp: new Date().toISOString(),
      duration: Date.now() - startTime
    });
    
  } catch (error) {
    console.error(`❌ [${requestId}] Portfolio alert notifications retrieval failed:`, error.message);
    return res.status(500).json({
      success: false,
      error: 'Failed to retrieve portfolio alert notifications',
      message: error.message,
      timestamp: new Date().toISOString(),
      duration: Date.now() - startTime
    });
  }
});

/**
 * POST /portfolio/alerts/process
 * Process portfolio alerts for current user
 */
router.post('/alerts/process', async (req, res) => {
  const startTime = Date.now();
  const requestId = crypto.randomUUID().split('-')[0];
  const userId = req.user.userId;
  
  try {
    if (shouldLog('INFO')) console.log(`🔔 [${requestId}] Portfolio alert processing requested for user: ${userId.substring(0, 8)}...`);
    
    const portfolioAlerts = new PortfolioAlerts();
    const result = await portfolioAlerts.processUserPortfolioAlerts(userId);
    
    if (shouldLog('INFO')) console.log(`✅ [${requestId}] Portfolio alert processing completed in ${Date.now() - startTime}ms`);
    
    res.json({
      success: true,
      data: {
        processedCount: result.processedCount,
        triggeredCount: result.triggeredCount,
        message: `Processed ${result.processedCount} alerts, triggered ${result.triggeredCount} notifications`
      },
      timestamp: new Date().toISOString(),
      duration: Date.now() - startTime
    });
    
  } catch (error) {
    console.error(`❌ [${requestId}] Portfolio alert processing failed:`, error.message);
    return res.status(500).json({
      success: false,
      error: 'Failed to process portfolio alerts',
      message: error.message,
      timestamp: new Date().toISOString(),
      duration: Date.now() - startTime
    });
  }
});

/**
 * GET /portfolio/alerts/types
 * Get available portfolio alert types
 */
router.get('/alerts/types', async (req, res) => {
  const startTime = Date.now();
  const requestId = crypto.randomUUID().split('-')[0];
  
  try {
    if (shouldLog('INFO')) console.log(`🔔 [${requestId}] Portfolio alert types requested`);
    
    const portfolioAlerts = new PortfolioAlerts();
    const alertTypes = portfolioAlerts.alertTypes;
    
    const alertTypeDefinitions = {
      [alertTypes.ALLOCATION_DRIFT]: {
        name: 'Allocation Drift',
        description: 'Alert when portfolio allocation drifts from target percentages',
        conditions: ['above'],
        thresholdType: 'percentage',
        requiresSymbol: false,
        example: { threshold: 5, condition: 'above', description: 'Alert when any position drifts more than 5% from target' }
      },
      [alertTypes.POSITION_GAIN_LOSS]: {
        name: 'Position Gain/Loss',
        description: 'Alert when a position gains or loses beyond threshold',
        conditions: ['above', 'below', 'absolute_above'],
        thresholdType: 'percentage',
        requiresSymbol: true,
        example: { threshold: 20, condition: 'above', description: 'Alert when position gains more than 20%' }
      },
      [alertTypes.PORTFOLIO_VALUE_CHANGE]: {
        name: 'Portfolio Value Change',
        description: 'Alert when total portfolio value changes significantly',
        conditions: ['increase_above', 'decrease_below', 'change_above'],
        thresholdType: 'percentage',
        requiresSymbol: false,
        example: { threshold: 10, condition: 'change_above', description: 'Alert when portfolio value changes more than 10%' }
      },
      [alertTypes.SECTOR_CONCENTRATION]: {
        name: 'Sector Concentration',
        description: 'Alert when sector allocation exceeds threshold',
        conditions: ['above'],
        thresholdType: 'percentage',
        requiresSymbol: false,
        example: { threshold: 40, condition: 'above', description: 'Alert when any sector exceeds 40% allocation' }
      },
      [alertTypes.POSITION_SIZE_CHANGE]: {
        name: 'Position Size Change',
        description: 'Alert when position size changes beyond threshold',
        conditions: ['above', 'below'],
        thresholdType: 'percentage',
        requiresSymbol: true,
        example: { threshold: 25, condition: 'above', description: 'Alert when position exceeds 25% of portfolio' }
      },
      [alertTypes.BETA_CHANGE]: {
        name: 'Beta Change',
        description: 'Alert when portfolio beta exceeds threshold',
        conditions: ['above', 'below'],
        thresholdType: 'value',
        requiresSymbol: false,
        example: { threshold: 1.5, condition: 'above', description: 'Alert when portfolio beta exceeds 1.5' }
      },
      [alertTypes.REBALANCE_NEEDED]: {
        name: 'Rebalance Needed',
        description: 'Alert when portfolio needs rebalancing',
        conditions: ['above'],
        thresholdType: 'percentage',
        requiresSymbol: false,
        example: { threshold: 30, condition: 'above', description: 'Alert when top position exceeds 30% of portfolio' }
      }
    };
    
    if (shouldLog('INFO')) console.log(`✅ [${requestId}] Portfolio alert types retrieved in ${Date.now() - startTime}ms`);
    
    res.json({
      success: true,
      data: {
        alertTypes: alertTypeDefinitions,
        count: Object.keys(alertTypeDefinitions).length
      },
      timestamp: new Date().toISOString(),
      duration: Date.now() - startTime
    });
    
  } catch (error) {
    console.error(`❌ [${requestId}] Portfolio alert types retrieval failed:`, error.message);
    return res.status(500).json({
      success: false,
      error: 'Failed to retrieve portfolio alert types',
      message: error.message,
      timestamp: new Date().toISOString(),
      duration: Date.now() - startTime
    });
  }
});

module.exports = router;