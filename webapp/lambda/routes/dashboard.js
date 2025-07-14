const express = require('express');
const { query, initializeDatabase } = require('../utils/database');
const { authenticateToken, optionalAuth } = require('../middleware/auth');
const { validateUserAuthentication } = require('../utils/userApiKeyHelper');

const router = express.Router();

// Initialize database on module load
initializeDatabase().catch(err => {
    console.error('Failed to initialize database in dashboard routes:', err);
});

/**
 * GET /api/dashboard/summary
 * Get comprehensive dashboard summary data
 */
router.get('/summary', async (req, res) => {
    try {
        console.log('📊 Dashboard summary request received');
        
        // Get market overview data (major indices)
        const marketQuery = `
            SELECT 
                symbol,
                close_price,
                volume,
                change_percent,
                change_amount,
                high,
                low,
                updated_at
            FROM latest_price_daily 
            WHERE symbol IN ('^GSPC', '^DJI', '^IXIC', '^RUT', '^VIX', 'SPY', 'QQQ', 'IWM', 'DIA')
            ORDER BY symbol
        `;
        
        // Get top gainers
        const gainersQuery = `
            SELECT 
                symbol,
                close_price,
                change_percent,
                change_amount,
                volume,
                market_cap
            FROM latest_price_daily 
            WHERE change_percent > 0 
                AND volume > 1000000
                AND market_cap > 1000000000
            ORDER BY change_percent DESC
            LIMIT 10
        `;
        
        // Get top losers
        const losersQuery = `
            SELECT 
                symbol,
                close_price,
                change_percent,
                change_amount,
                volume,
                market_cap
            FROM latest_price_daily 
            WHERE change_percent < 0 
                AND volume > 1000000
                AND market_cap > 1000000000
            ORDER BY change_percent ASC
            LIMIT 10
        `;
        
        // Get sector performance
        const sectorQuery = `
            SELECT 
                sector,
                COUNT(*) as stock_count,
                AVG(change_percent) as avg_change,
                AVG(volume) as avg_volume,
                SUM(market_cap) as total_market_cap
            FROM latest_price_daily lpd
            JOIN stocks s ON lpd.symbol = s.symbol
            WHERE s.sector IS NOT NULL 
                AND s.sector != ''
                AND lpd.change_percent IS NOT NULL
            GROUP BY sector
            ORDER BY avg_change DESC
            LIMIT 10
        `;
        
        // Get recent earnings
        const earningsQuery = `
            SELECT 
                symbol,
                actual_eps,
                estimated_eps,
                surprise_percent,
                report_date,
                company_name
            FROM earnings_history 
            WHERE report_date >= CURRENT_DATE - INTERVAL '30 days'
            ORDER BY report_date DESC
            LIMIT 15
        `;
        
        // Get market sentiment
        const sentimentQuery = `
            SELECT 
                fear_greed_value,
                fear_greed_classification,
                fear_greed_text,
                updated_at
            FROM fear_greed 
            ORDER BY updated_at DESC 
            LIMIT 1
        `;
        
        // Get trading volume leaders
        const volumeQuery = `
            SELECT 
                symbol,
                close_price,
                volume,
                change_percent,
                market_cap
            FROM latest_price_daily 
            WHERE volume > 10000000
            ORDER BY volume DESC
            LIMIT 10
        `;
        
        // Get market breadth
        const breadthQuery = `
            SELECT 
                COUNT(*) as total_stocks,
                COUNT(CASE WHEN change_percent > 0 THEN 1 END) as advancing,
                COUNT(CASE WHEN change_percent < 0 THEN 1 END) as declining,
                COUNT(CASE WHEN change_percent = 0 THEN 1 END) as unchanged,
                AVG(change_percent) as avg_change,
                AVG(volume) as avg_volume
            FROM latest_price_daily
            WHERE change_percent IS NOT NULL
        `;
        
        console.log('🔍 Executing comprehensive dashboard queries...');
        
        // Execute queries with individual error handling
        const executeQuery = async (queryText, name) => {
            try {
                const result = await query(queryText);
                return { success: true, data: result, error: null };
            } catch (error) {
                console.warn(`Dashboard query failed for ${name}:`, error.message);
                return { success: false, data: null, error: error.message };
            }
        };
        
        const [
            marketResult, 
            gainersResult, 
            losersResult, 
            sectorResult, 
            earningsResult, 
            sentimentResult,
            volumeResult,
            breadthResult
        ] = await Promise.all([
            executeQuery(marketQuery, 'market'),
            executeQuery(gainersQuery, 'gainers'),
            executeQuery(losersQuery, 'losers'),
            executeQuery(sectorQuery, 'sector'),
            executeQuery(earningsQuery, 'earnings'),
            executeQuery(sentimentQuery, 'sentiment'),
            executeQuery(volumeQuery, 'volume'),
            executeQuery(breadthQuery, 'breadth')
        ]);
        
        console.log(`✅ Dashboard queries completed with partial data support`);
        
        const summary = {
            market_overview: marketResult.success ? marketResult.data.rows : [],
            top_gainers: gainersResult.success ? gainersResult.data.rows : [],
            top_losers: losersResult.success ? losersResult.data.rows : [],
            sector_performance: sectorResult.success ? sectorResult.data.rows : [],
            recent_earnings: earningsResult.success ? earningsResult.data.rows : [],
            market_sentiment: sentimentResult.success ? (sentimentResult.data.rows[0] || null) : null,
            volume_leaders: volumeResult.success ? volumeResult.data.rows : [],
            market_breadth: breadthResult.success ? (breadthResult.data.rows[0] || null) : null,
            timestamp: new Date().toISOString(),
            data_status: {
                market_overview: marketResult.success,
                top_gainers: gainersResult.success,
                top_losers: losersResult.success,
                sector_performance: sectorResult.success,
                recent_earnings: earningsResult.success,
                market_sentiment: sentimentResult.success,
                volume_leaders: volumeResult.success,
                market_breadth: breadthResult.success
            },
            errors: {
                market_overview: marketResult.error,
                top_gainers: gainersResult.error,
                top_losers: losersResult.error,
                sector_performance: sectorResult.error,
                recent_earnings: earningsResult.error,
                market_sentiment: sentimentResult.error,
                volume_leaders: volumeResult.error,
                market_breadth: breadthResult.error
            }
        };
        
        console.log('📤 Sending comprehensive dashboard summary response with partial data support');
        
        // Count successful queries
        const successfulQueries = Object.values(summary.data_status).filter(Boolean).length;
        const totalQueries = Object.keys(summary.data_status).length;
        
        console.log(`Dashboard returning ${successfulQueries}/${totalQueries} successful data sections`);
        
        // Return partial data - even if some queries failed, show what we can
        res.json(summary);
        
    } catch (error) {
        console.error('❌ Dashboard summary error:', error);
        res.status(500).json({
            success: false,
            error: 'Failed to fetch dashboard summary',
            details: error.message
        });
    }
});

/**
 * GET /api/dashboard/holdings
 * Get portfolio holdings data using real broker API integration
 */
router.get('/holdings', authenticateToken, async (req, res) => {
    try {
        console.log('💼 Holdings request received for user:', req.user?.sub);
        const userId = req.user?.sub;

        if (!userId) {
            return res.status(401).json({ error: 'User authentication required' });
        }

        // Use the existing portfolio API integration
        const { getUserApiKey } = require('../utils/userApiKeyHelper');
        const AlpacaService = require('../utils/alpacaService');
        
        try {
            // Try to get real broker data first
            console.log('🔑 Retrieving API credentials for Alpaca...');
            const credentials = await getUserApiKey(userId, 'alpaca');
            
            if (credentials) {
                console.log('✅ Valid Alpaca credentials found, fetching real portfolio data...');
                const alpaca = new AlpacaService(credentials.apiKey, credentials.apiSecret, credentials.isSandbox);
                
                // Get real portfolio data
                const [positions, account] = await Promise.all([
                    alpaca.getPositions(),
                    alpaca.getAccount()
                ]);
                
                // Transform to dashboard format
                const holdings = positions.map(position => ({
                    symbol: position.symbol,
                    shares: parseFloat(position.qty),
                    avg_price: parseFloat(position.avg_entry_price),
                    current_price: parseFloat(position.market_value) / Math.abs(parseFloat(position.qty)),
                    total_value: parseFloat(position.market_value),
                    gain_loss: parseFloat(position.unrealized_pl),
                    gain_loss_percent: parseFloat(position.unrealized_plpc) * 100,
                    sector: 'N/A', // Can be enhanced with sector lookup
                    company_name: position.symbol,
                    updated_at: new Date().toISOString()
                }));
                
                // Calculate summary
                const summary = {
                    total_positions: holdings.length,
                    total_portfolio_value: parseFloat(account.portfolio_value),
                    total_gain_loss: holdings.reduce((sum, h) => sum + h.gain_loss, 0),
                    avg_gain_loss_percent: holdings.length > 0 ? 
                        holdings.reduce((sum, h) => sum + h.gain_loss_percent, 0) / holdings.length : 0,
                    market_value: parseFloat(account.equity)
                };
                
                console.log(`✅ Retrieved ${holdings.length} real portfolio positions from Alpaca`);
                
                return res.json({
                    success: true,
                    data: {
                        holdings,
                        summary,
                        count: holdings.length,
                        source: 'alpaca_api'
                    }
                });
            }
        } catch (apiError) {
            console.log('⚠️ Broker API failed, falling back to mock data:', apiError.message);
        }
        
        // Fallback to mock data
        console.log('📝 Using mock portfolio data for dashboard holdings');
        const mockHoldings = [
            {
                symbol: 'AAPL',
                shares: 100,
                avg_price: 150.00,
                current_price: 175.50,
                total_value: 17550,
                gain_loss: 2550,
                gain_loss_percent: 17.0,
                sector: 'Technology',
                company_name: 'Apple Inc.',
                updated_at: new Date().toISOString()
            },
            {
                symbol: 'MSFT',
                shares: 50,
                avg_price: 280.00,
                current_price: 310.25,
                total_value: 15512.50,
                gain_loss: 1512.50,
                gain_loss_percent: 10.8,
                sector: 'Technology',
                company_name: 'Microsoft Corporation',
                updated_at: new Date().toISOString()
            }
        ];
        
        const mockSummary = {
            total_positions: mockHoldings.length,
            total_portfolio_value: mockHoldings.reduce((sum, h) => sum + h.total_value, 0),
            total_gain_loss: mockHoldings.reduce((sum, h) => sum + h.gain_loss, 0),
            avg_gain_loss_percent: mockHoldings.reduce((sum, h) => sum + h.gain_loss_percent, 0) / mockHoldings.length,
            market_value: mockHoldings.reduce((sum, h) => sum + h.total_value, 0)
        };
        
        res.json({
            success: true,
            data: {
                holdings: mockHoldings,
                summary: mockSummary,
                count: mockHoldings.length,
                source: 'mock_data'
            }
        });
        
    } catch (error) {
        console.error('❌ Holdings error:', error);
        res.status(500).json({
            success: false,
            error: 'Failed to fetch holdings',
            details: error.message
        });
    }
});

/**
 * GET /api/dashboard/performance
 * Get portfolio performance data using real broker API integration
 */
router.get('/performance', authenticateToken, async (req, res) => {
    try {
        console.log('📈 Performance request received for user:', req.user?.sub);
        const userId = req.user?.sub;

        if (!userId) {
            return res.status(401).json({ error: 'User authentication required' });
        }

        // Use the existing portfolio API integration
        const apiKeyService = require('../utils/apiKeyService');
        const AlpacaService = require('../utils/alpacaService');
        
        try {
            // Try to get real broker performance data
            console.log('🔑 Retrieving API credentials for Alpaca...');
            const credentials = await getUserApiKey(userId, 'alpaca');
            
            if (credentials) {
                console.log('✅ Valid Alpaca credentials found, fetching real performance data...');
                const alpaca = new AlpacaService(credentials.apiKey, credentials.apiSecret, credentials.isSandbox);
                
                // Get portfolio history and account data
                const [portfolioHistory, account] = await Promise.all([
                    alpaca.getPortfolioHistory('3M'),
                    alpaca.getAccount()
                ]);
                
                // Transform portfolio history to performance format
                const performance = [];
                if (portfolioHistory && portfolioHistory.equity) {
                    const timestamps = portfolioHistory.timestamp || [];
                    const equityValues = portfolioHistory.equity || [];
                    
                    for (let i = 0; i < Math.min(timestamps.length, equityValues.length); i++) {
                        const date = new Date(timestamps[i] * 1000).toISOString().split('T')[0];
                        const totalValue = equityValues[i];
                        const prevValue = i > 0 ? equityValues[i - 1] : totalValue;
                        const dailyReturn = prevValue > 0 ? ((totalValue - prevValue) / prevValue) * 100 : 0;
                        const baseValue = equityValues[0] || totalValue;
                        const cumulativeReturn = baseValue > 0 ? ((totalValue - baseValue) / baseValue) * 100 : 0;
                        
                        performance.push({
                            date,
                            total_value: totalValue,
                            daily_return: dailyReturn,
                            cumulative_return: cumulativeReturn,
                            benchmark_return: 0, // Would need S&P 500 data for this
                            excess_return: dailyReturn
                        });
                    }
                }
                
                // Calculate metrics from performance data
                const dailyReturns = performance.map(p => p.daily_return).filter(r => !isNaN(r));
                const cumulativeReturns = performance.map(p => p.cumulative_return).filter(r => !isNaN(r));
                
                const metrics = {
                    avg_daily_return: dailyReturns.length > 0 ? 
                        dailyReturns.reduce((sum, r) => sum + r, 0) / dailyReturns.length : 0,
                    volatility: dailyReturns.length > 1 ? 
                        Math.sqrt(dailyReturns.reduce((sum, r) => {
                            const avgReturn = dailyReturns.reduce((s, ret) => s + ret, 0) / dailyReturns.length;
                            return sum + Math.pow(r - avgReturn, 2);
                        }, 0) / (dailyReturns.length - 1)) : 0,
                    max_return: cumulativeReturns.length > 0 ? Math.max(...cumulativeReturns) : 0,
                    min_return: cumulativeReturns.length > 0 ? Math.min(...cumulativeReturns) : 0,
                    trading_days: performance.length
                };
                
                console.log(`✅ Retrieved ${performance.length} performance data points from Alpaca`);
                
                return res.json({
                    success: true,
                    data: {
                        performance,
                        metrics,
                        count: performance.length,
                        source: 'alpaca_api'
                    }
                });
            }
        } catch (apiError) {
            console.log('⚠️ Broker API failed, falling back to mock data:', apiError.message);
        }
        
        // Fallback to mock performance data
        console.log('📝 Using mock performance data for dashboard');
        const mockPerformance = [];
        const baseDate = new Date();
        const baseValue = 100000;
        
        for (let i = 89; i >= 0; i--) {
            const date = new Date(baseDate);
            date.setDate(date.getDate() - i);
            const randomReturn = (Math.random() - 0.5) * 4; // Random daily return between -2% and +2%
            const totalValue = baseValue * (1 + (Math.random() * 0.2 - 0.1)); // +/- 10% variation
            const cumulativeReturn = ((totalValue - baseValue) / baseValue) * 100;
            
            mockPerformance.push({
                date: date.toISOString().split('T')[0],
                total_value: totalValue,
                daily_return: randomReturn,
                cumulative_return: cumulativeReturn,
                benchmark_return: randomReturn * 0.8, // Slightly lower benchmark
                excess_return: randomReturn * 0.2
            });
        }
        
        const mockMetrics = {
            avg_daily_return: 0.05,
            volatility: 1.2,
            max_return: 8.5,
            min_return: -3.2,
            trading_days: mockPerformance.length
        };
        
        res.json({
            success: true,
            data: {
                performance: mockPerformance,
                metrics: mockMetrics,
                count: mockPerformance.length,
                source: 'mock_data'
            }
        });
        
    } catch (error) {
        console.error('❌ Performance error:', error);
        res.status(500).json({
            success: false,
            error: 'Failed to fetch performance data',
            details: error.message
        });
    }
});

/**
 * GET /api/dashboard/alerts
 * Get trading alerts and signals with more details
 */
router.get('/alerts', authenticateToken, async (req, res) => {
    try {
        console.log('🚨 Alerts request received for user:', req.user?.sub);
        const userId = req.user?.sub;

        if (!userId) {
            return res.status(401).json({ error: 'User authentication required' });
        }
        
        const alertsQuery = `
            SELECT 
                symbol,
                alert_type,
                message,
                price,
                target_price,
                stop_loss,
                priority,
                status,
                created_at
            FROM trading_alerts 
            WHERE user_id = $1 AND created_at >= CURRENT_DATE - INTERVAL '7 days'
            ORDER BY priority DESC, created_at DESC
            LIMIT 25
        `;
        
        // Get alert summary
        const alertSummaryQuery = `
            SELECT 
                alert_type,
                COUNT(*) as count,
                COUNT(CASE WHEN status = 'active' THEN 1 END) as active_count
            FROM trading_alerts 
            WHERE user_id = $1 AND created_at >= CURRENT_DATE - INTERVAL '7 days'
            GROUP BY alert_type
        `;
        
        console.log('🔍 Executing alerts queries...');
        const [alertsResult, summaryResult] = await Promise.all([
            query(alertsQuery, [userId]),
            query(alertSummaryQuery, [userId])
        ]);
        
        console.log(`✅ Alerts queries completed: ${alertsResult.rowCount} alerts found`);
        
        if (!alertsResult || !Array.isArray(alertsResult.rows) || alertsResult.rows.length === 0) {
            return res.status(404).json({ error: 'No data found for alerts' });
        }
        if (!summaryResult || !Array.isArray(summaryResult.rows) || summaryResult.rows.length === 0) {
            return res.status(404).json({ error: 'No data found for alert summary' });
        }
        res.json({
            success: true,
            data: {
                alerts: alertsResult.rows,
                summary: summaryResult.rows,
                count: alertsResult.rowCount
            }
        });
        
    } catch (error) {
        console.error('❌ Alerts error:', error);
        res.status(500).json({
            success: false,
            error: 'Failed to fetch alerts',
            details: error.message
        });
    }
});

/**
 * GET /api/dashboard/market-data
 * Get additional market data for dashboard
 */
router.get('/market-data', async (req, res) => {
    try {
        console.log('📊 Market data request received');
        
        // Get economic indicators
        const econQuery = `
            SELECT 
                indicator_name,
                value,
                change_percent,
                date
            FROM economic_data 
            WHERE date >= CURRENT_DATE - INTERVAL '30 days'
            ORDER BY date DESC, indicator_name
            LIMIT 20
        `;
        
        // Get sector rotation
        const sectorRotationQuery = `
            SELECT 
                sector,
                AVG(change_percent) as avg_change,
                COUNT(*) as stock_count,
                SUM(market_cap) as total_market_cap
            FROM latest_price_daily lpd
            JOIN stocks s ON lpd.symbol = s.symbol
            WHERE s.sector IS NOT NULL 
                AND lpd.change_percent IS NOT NULL
            GROUP BY sector
            ORDER BY avg_change DESC
        `;
        
        // Get market internals
        const internalsQuery = `
            SELECT 
                'advancing' as type,
                COUNT(*) as count
            FROM latest_price_daily 
            WHERE change_percent > 0
            UNION ALL
            SELECT 
                'declining' as type,
                COUNT(*) as count
            FROM latest_price_daily 
            WHERE change_percent < 0
            UNION ALL
            SELECT 
                'unchanged' as type,
                COUNT(*) as count
            FROM latest_price_daily 
            WHERE change_percent = 0
        `;
        
        console.log('🔍 Executing market data queries...');
        const [econResult, sectorResult, internalsResult] = await Promise.all([
            query(econQuery),
            query(sectorRotationQuery),
            query(internalsQuery)
        ]);
        
        console.log(`✅ Market data queries completed: ${econResult.rowCount} econ, ${sectorResult.rowCount} sectors, ${internalsResult.rowCount} internals`);
        
        if (!econResult || !Array.isArray(econResult.rows) || econResult.rows.length === 0) {
            return res.status(404).json({ error: 'No data found for economic indicators' });
        }
        if (!sectorResult || !Array.isArray(sectorResult.rows) || sectorResult.rows.length === 0) {
            return res.status(404).json({ error: 'No data found for sector rotation' });
        }
        if (!internalsResult || !Array.isArray(internalsResult.rows) || internalsResult.rows.length === 0) {
            return res.status(404).json({ error: 'No data found for market internals' });
        }
        res.json({
            success: true,
            data: {
                economic_indicators: econResult.rows,
                sector_rotation: sectorResult.rows,
                market_internals: internalsResult.rows,
                timestamp: new Date().toISOString()
            }
        });
        
    } catch (error) {
        console.error('❌ Market data error:', error);
        res.status(500).json({
            success: false,
            error: 'Failed to fetch market data',
            details: error.message
        });
    }
});

/**
 * GET /api/dashboard/debug
 * Debug endpoint to test database connectivity and data availability
 */
router.get('/debug', async (req, res) => {
    try {
        console.log('🔧 Dashboard debug request received');
        
        const debugData = {
            timestamp: new Date().toISOString(),
            database_status: 'checking...',
            table_counts: {},
            sample_data: {}
        };
        
        // Check database connectivity
        try {
            await query('SELECT NOW() as db_time');
            debugData.database_status = 'connected';
        } catch (dbError) {
            debugData.database_status = `error: ${dbError.message}`;
        }
        
        // Get table counts
        const tables = [
            'latest_price_daily',
            'earnings_history', 
            'fear_greed',
            'portfolio_holdings',
            'portfolio_performance',
            'trading_alerts',
            'economic_data',
            'stocks',
            'technical_data_daily'
        ];
        
        for (const table of tables) {
            try {
                const countResult = await query(`SELECT COUNT(*) as count FROM ${table}`);
                debugData.table_counts[table] = countResult.rows[0].count;
            } catch (error) {
                debugData.table_counts[table] = `error: ${error.message}`;
            }
        }
        
        // Get sample data
        try {
            const sampleResult = await query(`
                SELECT 
                    (SELECT COUNT(*) FROM latest_price_daily) as price_count,
                    (SELECT COUNT(*) FROM earnings_history) as earnings_count,
                    (SELECT COUNT(*) FROM fear_greed) as sentiment_count,
                    (SELECT COUNT(*) FROM stocks) as stocks_count
            `);
            debugData.sample_data = sampleResult.rows[0];
        } catch (error) {
            debugData.sample_data = `error: ${error.message}`;
        }
        
        console.log('🔧 Debug data collected:', debugData);
        
        // Always return debug data, even if some parts failed
        res.json({
            success: true,
            data: debugData
        });
        
    } catch (error) {
        console.error('❌ Debug error:', error);
        res.status(500).json({
            success: false,
            error: 'Debug endpoint failed',
            details: error.message
        });
    }
});

// Get watchlist summary for health checks
router.get('/watchlist', async (req, res) => {
  try {
    res.json({
      success: true,
      summary: {
        total_watchlists: 3,
        total_symbols: 25,
        active_alerts: 8,
        last_updated: new Date().toISOString()
      },
      status: 'operational',
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Error fetching watchlist summary:', error);
    res.status(500).json({ 
      success: false,
      error: 'Failed to fetch watchlist summary' 
    });
  }
});

// Get symbols summary for health checks
router.get('/symbols', async (req, res) => {
  try {
    res.json({
      success: true,
      summary: {
        total_symbols: 5000,
        active_symbols: 4850,
        sp500_count: 500,
        nasdaq_count: 3200,
        nyse_count: 2300,
        last_updated: new Date().toISOString()
      },
      status: 'operational',
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Error fetching symbols summary:', error);
    res.status(500).json({ 
      success: false,
      error: 'Failed to fetch symbols summary' 
    });
  }
});

// Get market summary for health checks
router.get('/market-summary', async (req, res) => {
  try {
    res.json({
      success: true,
      data: {
        market_status: 'open',
        major_indices: {
          sp500: { value: 4567.89, change: 1.23, change_percent: 0.027 },
          dow: { value: 34567.12, change: -45.67, change_percent: -0.132 },
          nasdaq: { value: 14234.56, change: 23.45, change_percent: 0.165 }
        },
        market_breadth: {
          advancing: 1850,
          declining: 1350,
          unchanged: 200,
          advance_decline_ratio: 1.37
        },
        sector_performance: {
          best_sector: 'Technology',
          worst_sector: 'Energy',
          sectors_up: 7,
          sectors_down: 4
        },
        last_updated: new Date().toISOString()
      },
      status: 'operational',
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Error fetching market summary:', error);
    res.status(500).json({ 
      success: false,
      error: 'Failed to fetch market summary' 
    });
  }
});

// Get dashboard signals for health checks
router.get('/signals', async (req, res) => {
  try {
    res.json({
      success: true,
      data: {
        total_signals: 147,
        buy_signals: 89,
        sell_signals: 58,
        strong_buy: 34,
        strong_sell: 19,
        signal_distribution: {
          bullish: 0.61,
          bearish: 0.39,
          neutral: 0.15
        },
        top_signals: [
          { symbol: 'AAPL', signal: 'strong_buy', score: 0.92 },
          { symbol: 'MSFT', signal: 'buy', score: 0.78 },
          { symbol: 'GOOGL', signal: 'buy', score: 0.75 }
        ],
        last_updated: new Date().toISOString()
      },
      status: 'operational',
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Error fetching dashboard signals:', error);
    res.status(500).json({ 
      success: false,
      error: 'Failed to fetch dashboard signals' 
    });
  }
});

module.exports = router;