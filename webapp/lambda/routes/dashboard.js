const express = require('express');
const { query, initializeDatabase } = require('../utils/database');

const router = express.Router();

// Initialize database on module load
initializeDatabase().catch(err => {
    console.error('Failed to initialize database in dashboard routes:', err);
});

/**
 * GET /api/dashboard/summary
 * Get dashboard summary data
 */
router.get('/summary', async (req, res) => {
    try {
        console.log('📊 Dashboard summary request received');
        
        // Get market overview data
        const marketQuery = `
            SELECT 
                symbol,
                close_price,
                volume,
                change_percent,
                updated_at
            FROM latest_price_daily 
            WHERE symbol IN ('SPY', 'QQQ', 'IWM', 'DIA')
            ORDER BY updated_at DESC
            LIMIT 4
        `;
        
        // Get recent earnings
        const earningsQuery = `
            SELECT 
                symbol,
                actual_eps,
                estimated_eps,
                surprise_percent,
                report_date
            FROM earnings_history 
            WHERE report_date >= CURRENT_DATE - INTERVAL '30 days'
            ORDER BY report_date DESC
            LIMIT 10
        `;
        
        // Get market sentiment
        const sentimentQuery = `
            SELECT 
                fear_greed_value,
                fear_greed_classification,
                updated_at
            FROM fear_greed 
            ORDER BY updated_at DESC 
            LIMIT 1
        `;
        
        console.log('🔍 Executing dashboard queries...');
        
        const [marketResult, earningsResult, sentimentResult] = await Promise.all([
            query(marketQuery),
            query(earningsQuery),
            query(sentimentQuery)
        ]);
        
        console.log(`✅ Dashboard queries completed: ${marketResult.rowCount} market, ${earningsResult.rowCount} earnings, ${sentimentResult.rowCount} sentiment`);
        
        const summary = {
            market_overview: marketResult.rows,
            recent_earnings: earningsResult.rows,
            market_sentiment: sentimentResult.rows[0] || null,
            timestamp: new Date().toISOString()
        };
        
        console.log('📤 Sending dashboard summary response');
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
 * Get portfolio holdings data
 */
router.get('/holdings', async (req, res) => {
    try {
        console.log('💼 Holdings request received');
        
        const holdingsQuery = `
            SELECT 
                symbol,
                shares,
                avg_price,
                current_price,
                total_value,
                gain_loss,
                gain_loss_percent,
                updated_at
            FROM portfolio_holdings 
            ORDER BY total_value DESC
        `;
        
        console.log('🔍 Executing holdings query...');
        const result = await query(holdingsQuery);
        
        console.log(`✅ Holdings query completed: ${result.rowCount} holdings found`);
        
        res.json({
            success: true,
            data: result.rows,
            count: result.rowCount
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
 * Get portfolio performance data
 */
router.get('/performance', async (req, res) => {
    try {
        console.log('📈 Performance request received');
        
        const performanceQuery = `
            SELECT 
                date,
                total_value,
                daily_return,
                cumulative_return
            FROM portfolio_performance 
            WHERE date >= CURRENT_DATE - INTERVAL '30 days'
            ORDER BY date ASC
        `;
        
        console.log('🔍 Executing performance query...');
        const result = await query(performanceQuery);
        
        console.log(`✅ Performance query completed: ${result.rowCount} data points`);
        
        res.json({
            success: true,
            data: result.rows,
            count: result.rowCount
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
 * Get trading alerts and signals
 */
router.get('/alerts', async (req, res) => {
    try {
        console.log('🚨 Alerts request received');
        
        const alertsQuery = `
            SELECT 
                symbol,
                alert_type,
                message,
                price,
                created_at
            FROM trading_alerts 
            WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
            ORDER BY created_at DESC
            LIMIT 20
        `;
        
        console.log('🔍 Executing alerts query...');
        const result = await query(alertsQuery);
        
        console.log(`✅ Alerts query completed: ${result.rowCount} alerts found`);
        
        res.json({
            success: true,
            data: result.rows,
            count: result.rowCount
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
            'trading_alerts'
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
                    (SELECT COUNT(*) FROM fear_greed) as sentiment_count
            `);
            debugData.sample_data = sampleResult.rows[0];
        } catch (error) {
            debugData.sample_data = `error: ${error.message}`;
        }
        
        console.log('🔧 Debug data collected:', debugData);
        
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