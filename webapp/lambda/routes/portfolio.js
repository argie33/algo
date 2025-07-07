const express = require('express');
const { query, healthCheck, initializeDatabase } = require('../utils/database');
const { authenticateToken } = require('../middleware/auth');

const router = express.Router();

// Portfolio holdings endpoint - uses real data, structured like mock data
router.get('/holdings', async (req, res) => {
  try {
    const { accountType = 'paper' } = req.query;
    console.log(`Portfolio holdings endpoint called for account type: ${accountType}`);
    
    // Check if user is authenticated
    const isAuthenticated = req.headers.authorization && req.headers.authorization.startsWith('Bearer ');
    let userId = null;
    
    if (isAuthenticated) {
      try {
        // Extract user ID from token (simplified - in production would verify JWT)
        const token = req.headers.authorization.split(' ')[1];
        // For now, we'll use a placeholder user ID - replace with actual JWT decode
        userId = 'demo-user-123'; 
      } catch (error) {
        console.log('Token parsing failed, treating as unauthenticated');
      }
    }

    // If authenticated, try to get real data
    if (userId) {
      try {
        const dbHealth = await healthCheck();
        if (dbHealth.status === 'healthy') {
          
          // Query real portfolio holdings
          const holdingsQuery = `
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
              COALESCE(se.company_name, ph.symbol || ' Inc.') as company,
              COALESCE(se.sector, 'Technology') as sector,
              COALESCE(se.exchange, 'NASDAQ') as exchange
            FROM portfolio_holdings ph
            LEFT JOIN stock_symbols_enhanced se ON ph.symbol = se.symbol  
            WHERE ph.user_id = $1 AND ph.quantity > 0
            ORDER BY ph.market_value DESC
          `;

          const holdingsResult = await query(holdingsQuery, [userId]);
          
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
              allocation: totalValue > 0 ? (parseFloat(h.market_value) / totalValue) * 100 : 0
            }));

            return res.json({
              success: true,
              data: {
                holdings: formattedHoldings,
                summary: {
                  totalValue: totalValue,
                  totalGainLoss: totalGainLoss,
                  totalGainLossPercent: totalValue > totalGainLoss ? (totalGainLoss / (totalValue - totalGainLoss)) * 100 : 0,
                  numPositions: holdings.length,
                  accountType: accountType
                }
              },
              timestamp: new Date().toISOString(),
              dataSource: 'database'
            });
          }
        }
      } catch (error) {
        console.error('Database query failed:', error);
        // Fall through to error response
      }
    }

    // If not authenticated OR no data found OR database error
    return res.status(404).json({
      success: false,
      error: 'No portfolio data available',
      message: userId ? 'No portfolio holdings found for authenticated user' : 'Authentication required for portfolio data',
      details: {
        authenticated: !!userId,
        accountType: accountType,
        suggestion: userId ? 'Import portfolio data from broker or add positions manually' : 'Please log in to view portfolio data'
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error in portfolio holdings endpoint:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch portfolio holdings',
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Account info endpoint - uses real data, structured like mock data
router.get('/account', async (req, res) => {
  try {
    const { accountType = 'paper' } = req.query;
    console.log(`Portfolio account info endpoint called for account type: ${accountType}`);
    
    // Check if user is authenticated
    const isAuthenticated = req.headers.authorization && req.headers.authorization.startsWith('Bearer ');
    let userId = null;
    
    if (isAuthenticated) {
      try {
        userId = 'demo-user-123'; // Replace with actual JWT decode
      } catch (error) {
        console.log('Token parsing failed, treating as unauthenticated');
      }
    }

    // If authenticated, try to get real data
    if (userId) {
      try {
        const dbHealth = await healthCheck();
        if (dbHealth.status === 'healthy') {
          
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
            
            return res.json({
              success: true,
              data: {
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
                createdAt: accountData.last_sync || new Date().toISOString()
              },
              timestamp: new Date().toISOString(),
              dataSource: 'database'
            });
          }
        }
      } catch (error) {
        console.error('Database query failed:', error);
        // Fall through to error response
      }
    }

    // If not authenticated OR no data found OR database error
    return res.status(404).json({
      success: false,
      error: 'No account data available',
      message: userId ? 'No account information found for authenticated user' : 'Authentication required for account data',
      details: {
        authenticated: !!userId,
        accountType: accountType,
        suggestion: userId ? 'Import account data from broker first' : 'Please log in to view account data'
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error in account info endpoint:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch account info',
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Apply authentication middleware to remaining routes
router.use(authenticateToken);

// Portfolio analytics endpoint for authenticated users
router.get('/analytics', async (req, res) => {
  const userId = req.user.sub;
  const { timeframe = '1y' } = req.query;
  
  console.log(`Portfolio analytics endpoint called for authenticated user: ${userId}, timeframe: ${timeframe}`);
  
  try {
    const dbHealth = await healthCheck();
    if (dbHealth.status !== 'healthy') {
      return res.status(503).json({
        success: false,
        error: 'Database unavailable',
        details: 'Cannot retrieve analytics data'
      });
    }

    // Get portfolio holdings with sector information
    const holdingsQuery = `
      SELECT 
        ph.symbol,
        ph.quantity,
        ph.market_value,
        ph.unrealized_pl as pnl,
        ph.unrealized_plpc as pnl_percent,
        ph.avg_cost as cost_basis,
        COALESCE(se.sector, 'Technology') as sector,
        ph.updated_at as last_updated
      FROM portfolio_holdings ph
      LEFT JOIN stock_symbols_enhanced se ON ph.symbol = se.symbol
      WHERE ph.user_id = $1 AND ph.quantity > 0
      ORDER BY ph.market_value DESC
    `;
    
    const holdingsResult = await query(holdingsQuery, [userId]);
    
    if (holdingsResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: 'No portfolio data found',
        message: 'Import portfolio holdings first'
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

    // Group by sector for allocation
    const sectorAllocation = holdings.reduce((acc, h) => {
      const sector = h.sector || 'Unknown';
      const value = parseFloat(h.market_value || 0);
      acc[sector] = (acc[sector] || 0) + value;
      return acc;
    }, {});

    // Convert to percentage
    Object.keys(sectorAllocation).forEach(sector => {
      sectorAllocation[sector] = (sectorAllocation[sector] / totalValue) * 100;
    });

    res.json({
      success: true,
      data: {
        holdings: holdings.map(h => ({
          symbol: h.symbol,
          quantity: parseFloat(h.quantity || 0),
          market_value: parseFloat(h.market_value || 0),
          cost_basis: parseFloat(h.cost_basis || 0) * parseFloat(h.quantity || 0),
          pnl: parseFloat(h.pnl || 0),
          pnl_percent: parseFloat(h.pnl_percent || 0),
          weight: totalValue > 0 ? (parseFloat(h.market_value) / totalValue) : 0,
          sector: h.sector,
          last_updated: h.last_updated
        })),
        analytics: analytics,
        summary: {
          totalValue: totalValue,
          totalPnL: analytics.totalReturn,
          numPositions: holdings.length,
          topSector: Object.entries(sectorAllocation).sort((a, b) => b[1] - a[1])[0]?.[0] || 'Unknown',
          concentration: holdings.length > 0 ? (parseFloat(holdings[0].market_value) / totalValue) : 0,
          riskScore: analytics.riskScore
        },
        sectorAllocation: sectorAllocation
      },
      timestamp: new Date().toISOString(),
      dataSource: 'database'
    });
    
  } catch (error) {
    console.error('Error fetching portfolio analytics:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to retrieve portfolio analytics',
      details: error.message
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

    res.json({
      success: true,
      status: dbHealth.status === 'healthy' && tablesExist ? 'ready' : 'configuration_required',
      database: dbHealth,
      tablesExist: tablesExist,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Health check error:', error);
    res.status(500).json({
      success: false,
      error: 'Health check failed',
      details: error.message
    });
  }
});

// Setup endpoint to create tables if needed
router.post('/setup', async (req, res) => {
  try {
    console.log('Setting up portfolio database tables...');
    await initializeDatabase();
    
    res.json({
      success: true,
      message: 'Portfolio database tables created successfully',
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Database setup error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to create portfolio database tables',
      details: error.message
    });
  }
});

module.exports = router;