const express = require('express');
const { query, initializeDatabase } = require('../utils/database');
const { authenticateToken, optionalAuth } = require('../middleware/auth');

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
            query(marketQuery),
            query(gainersQuery),
            query(losersQuery),
            query(sectorQuery),
            query(earningsQuery),
            query(sentimentQuery),
            query(volumeQuery),
            query(breadthQuery)
        ]);
        
        console.log(`✅ Dashboard queries completed: ${marketResult.rowCount} market, ${gainersResult.rowCount} gainers, ${losersResult.rowCount} losers, ${sectorResult.rowCount} sectors, ${earningsResult.rowCount} earnings, ${sentimentResult.rowCount} sentiment, ${volumeResult.rowCount} volume, ${breadthResult.rowCount} breadth`);
        
        const summary = {
            market_overview: marketResult.rows,
            top_gainers: gainersResult.rows,
            top_losers: losersResult.rows,
            sector_performance: sectorResult.rows,
            recent_earnings: earningsResult.rows,
            market_sentiment: sentimentResult.rows[0] || null,
            volume_leaders: volumeResult.rows,
            market_breadth: breadthResult.rows[0] || null,
            timestamp: new Date().toISOString()
        };
        
        console.log('📤 Sending comprehensive dashboard summary response');
        if (!marketResult || !Array.isArray(marketResult.rows) || marketResult.rows.length === 0) {
            return res.status(404).json({ error: 'No data found for market overview' });
        }
        if (!gainersResult || !Array.isArray(gainersResult.rows) || gainersResult.rows.length === 0) {
            return res.status(404).json({ error: 'No data found for top gainers' });
        }
        if (!losersResult || !Array.isArray(losersResult.rows) || losersResult.rows.length === 0) {
            return res.status(404).json({ error: 'No data found for top losers' });
        }
        if (!sectorResult || !Array.isArray(sectorResult.rows) || sectorResult.rows.length === 0) {
            return res.status(404).json({ error: 'No data found for sector performance' });
        }
        if (!earningsResult || !Array.isArray(earningsResult.rows) || earningsResult.rows.length === 0) {
            return res.status(404).json({ error: 'No data found for recent earnings' });
        }
        if (!sentimentResult || !Array.isArray(sentimentResult.rows) || sentimentResult.rows.length === 0) {
            return res.status(404).json({ error: 'No data found for market sentiment' });
        }
        if (!volumeResult || !Array.isArray(volumeResult.rows) || volumeResult.rows.length === 0) {
            return res.status(404).json({ error: 'No data found for volume leaders' });
        }
        if (!breadthResult || !Array.isArray(breadthResult.rows) || breadthResult.rows.length === 0) {
            return res.status(404).json({ error: 'No data found for market breadth' });
        }
        res.json({
            success: true,
            data: summary
        });
        
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
 * Get portfolio holdings data with more details
 */
router.get('/holdings', authenticateToken, async (req, res) => {
    try {
        console.log('💼 Holdings request received for user:', req.user?.sub);
        const userId = req.user?.sub;

        if (!userId) {
            return res.status(401).json({ error: 'User authentication required' });
        }
        
        const holdingsQuery = `
            SELECT 
                symbol,
                shares,
                avg_price,
                current_price,
                total_value,
                gain_loss,
                gain_loss_percent,
                sector,
                company_name,
                updated_at
            FROM portfolio_holdings ph
            LEFT JOIN stocks s ON ph.symbol = s.symbol
            WHERE ph.user_id = $1
            ORDER BY total_value DESC
        `;
        
        // Get portfolio summary
        const summaryQuery = `
            SELECT 
                COUNT(*) as total_positions,
                SUM(total_value) as total_portfolio_value,
                SUM(gain_loss) as total_gain_loss,
                AVG(gain_loss_percent) as avg_gain_loss_percent,
                SUM(shares * current_price) as market_value
            FROM portfolio_holdings
            WHERE user_id = $1
        `;
        
        console.log('🔍 Executing holdings queries...');
        const [holdingsResult, summaryResult] = await Promise.all([
            query(holdingsQuery, [userId]),
            query(summaryQuery, [userId])
        ]);
        
        console.log(`✅ Holdings queries completed: ${holdingsResult.rowCount} holdings found`);
        
        if (!holdingsResult || !Array.isArray(holdingsResult.rows) || holdingsResult.rows.length === 0) {
            return res.status(404).json({ error: 'No data found for holdings' });
        }
        if (!summaryResult || !Array.isArray(summaryResult.rows) || summaryResult.rows.length === 0) {
            return res.status(404).json({ error: 'No data found for portfolio summary' });
        }
        res.json({
            success: true,
            data: {
                holdings: holdingsResult.rows,
                summary: summaryResult.rows[0] || null,
                count: holdingsResult.rowCount
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
 * Get portfolio performance data with charts
 */
router.get('/performance', authenticateToken, async (req, res) => {
    try {
        console.log('📈 Performance request received for user:', req.user?.sub);
        const userId = req.user?.sub;

        if (!userId) {
            return res.status(401).json({ error: 'User authentication required' });
        }
        
        const performanceQuery = `
            SELECT 
                date,
                total_value,
                daily_return,
                cumulative_return,
                benchmark_return,
                excess_return
            FROM portfolio_performance 
            WHERE user_id = $1 AND date >= CURRENT_DATE - INTERVAL '90 days'
            ORDER BY date ASC
        `;
        
        // Get performance metrics
        const metricsQuery = `
            SELECT 
                AVG(daily_return) as avg_daily_return,
                STDDEV(daily_return) as volatility,
                MAX(cumulative_return) as max_return,
                MIN(cumulative_return) as min_return,
                COUNT(*) as trading_days
            FROM portfolio_performance 
            WHERE user_id = $1 AND date >= CURRENT_DATE - INTERVAL '30 days'
        `;
        
        console.log('🔍 Executing performance queries...');
        const [performanceResult, metricsResult] = await Promise.all([
            query(performanceQuery, [userId]),
            query(metricsQuery, [userId])
        ]);
        
        console.log(`✅ Performance queries completed: ${performanceResult.rowCount} data points`);
        
        if (!performanceResult || !Array.isArray(performanceResult.rows) || performanceResult.rows.length === 0) {
            return res.status(404).json({ error: 'No data found for performance' });
        }
        if (!metricsResult || !Array.isArray(metricsResult.rows) || metricsResult.rows.length === 0) {
            return res.status(404).json({ error: 'No data found for performance metrics' });
        }
        res.json({
            success: true,
            data: {
                performance: performanceResult.rows,
                metrics: metricsResult.rows[0] || null,
                count: performanceResult.rowCount
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
        
        if (!debugData || !Array.isArray(debugData.table_counts) || Object.keys(debugData.table_counts).length === 0) {
            return res.status(404).json({ error: 'No table counts found' });
        }
        if (!debugData || !Array.isArray(debugData.sample_data) || Object.keys(debugData.sample_data).length === 0) {
            return res.status(404).json({ error: 'No sample data found' });
        }
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

module.exports = router;