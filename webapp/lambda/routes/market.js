const express = require('express');
const { query } = require('../utils/database');

const router = express.Router();

// Debug endpoint to check market tables status
router.get('/debug', async (req, res) => {
  try {
    console.log('Market debug endpoint called');
    
    const tables = ['fear_greed_index', 'naaim_sentiment', 'aaii_sentiment', 'economic_data'];
    const results = {};
    
    for (const table of tables) {
      try {
        // Check if table exists
        const tableExistsQuery = `
          SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = '${table}'
          );
        `;
        
        const tableExists = await query(tableExistsQuery);
        console.log(`Table ${table} exists:`, tableExists.rows[0]);
        
        if (tableExists.rows[0].exists) {
          // Count total records
          const countQuery = `SELECT COUNT(*) as total FROM ${table}`;
          const countResult = await query(countQuery);
          
          // Get latest record
          let latestQuery;
          if (table === 'fear_greed_index') {
            latestQuery = `SELECT value, value_text, timestamp FROM ${table} ORDER BY timestamp DESC LIMIT 1`;
          } else if (table === 'naaim_sentiment') {
            latestQuery = `SELECT bullish_8100, bearish, average, week_ending FROM ${table} ORDER BY week_ending DESC LIMIT 1`;
          } else if (table === 'aaii_sentiment') {
            latestQuery = `SELECT bullish, neutral, bearish, date FROM ${table} ORDER BY date DESC LIMIT 1`;
          } else {
            latestQuery = `SELECT * FROM ${table} ORDER BY date DESC LIMIT 1`;
          }
          
          const latestResult = await query(latestQuery);
          
          results[table] = {
            exists: true,
            totalRecords: parseInt(countResult.rows[0].total),
            latestRecord: latestResult.rows[0] || null
          };
        } else {
          results[table] = {
            exists: false,
            message: `${table} table does not exist`
          };
        }
        
      } catch (error) {
        results[table] = {
          exists: false,
          error: error.message
        };
      }
    }
    
    res.json({
      tables: results,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error in market debug:', error);
    res.status(500).json({ 
      error: 'Debug check failed', 
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Simple test endpoint that returns raw data
router.get('/test', async (req, res) => {
  try {
    console.log('Market test endpoint called');
    
    const testQuery = `
      SELECT 
        'fear_greed' as indicator_type,
        value::text as current_value,
        value_text as description,
        timestamp as last_updated
      FROM fear_greed_index 
      ORDER BY timestamp DESC 
      LIMIT 1
    `;
    
    const result = await query(testQuery);
    
    res.json({
      success: true,
      count: result.rows.length,
      data: result.rows,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error in market test:', error);
    res.status(500).json({ 
      error: 'Test failed', 
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Basic ping endpoint
router.get('/ping', (req, res) => {
  res.json({
    status: 'ok',
    endpoint: 'market',
    timestamp: new Date().toISOString()
  });
});

// Get comprehensive market overview with sentiment indicators
router.get('/overview', async (req, res) => {
  try {
    console.log('Market overview endpoint called');
    
    // Get latest Fear & Greed index
    const fearGreedQuery = `
      SELECT value, value_text, timestamp
      FROM fear_greed_index 
      ORDER BY timestamp DESC 
      LIMIT 1
    `;

    // Get latest NAAIM sentiment
    const naaimQuery = `
      SELECT bullish_8100, bearish, average, week_ending
      FROM naaim_sentiment 
      ORDER BY week_ending DESC 
      LIMIT 1
    `;

    // Get latest AAII sentiment  
    const aaiiQuery = `
      SELECT bullish, neutral, bearish, date
      FROM aaii_sentiment 
      ORDER BY date DESC 
      LIMIT 1
    `;

    // Get economic indicators if available
    const econQuery = `
      SELECT indicator_name, value, date, description
      FROM economic_data 
      WHERE date >= CURRENT_DATE - INTERVAL '30 days'
      ORDER BY date DESC 
      LIMIT 10
    `;

    // Get overall market statistics
    const marketStatsQuery = `
      SELECT 
        COUNT(*) as total_stocks,
        COUNT(CASE WHEN md.regular_market_price > md.regular_market_previous_close THEN 1 END) as advancing_stocks,
        COUNT(CASE WHEN md.regular_market_price < md.regular_market_previous_close THEN 1 END) as declining_stocks,
        COUNT(CASE WHEN md.regular_market_price = md.regular_market_previous_close THEN 1 END) as unchanged_stocks,
        AVG((md.regular_market_price - md.regular_market_previous_close) / md.regular_market_previous_close * 100) as avg_change_percent,
        SUM(md.market_cap) as total_market_cap
      FROM market_data md
      WHERE md.regular_market_price IS NOT NULL 
        AND md.regular_market_previous_close IS NOT NULL 
        AND md.regular_market_previous_close > 0
    `;

    const [fearGreedResult, naaimResult, aaiiResult, econResult, marketStatsResult] = await Promise.all([
      query(fearGreedQuery),
      query(naaimQuery), 
      query(aaiiQuery),
      query(econQuery),
      query(marketStatsQuery)
    ]);

    const marketStats = marketStatsResult.rows[0];
    const advanceDeclineRatio = marketStats.advancing_stocks / Math.max(marketStats.declining_stocks, 1);

    res.json({
      sentiment_indicators: {
        fear_greed: fearGreedResult.rows[0] || null,
        naaim: naaimResult.rows[0] || null,
        aaii: aaiiResult.rows[0] || null
      },
      market_breadth: {
        total_stocks: parseInt(marketStats.total_stocks),
        advancing: parseInt(marketStats.advancing_stocks),
        declining: parseInt(marketStats.declining_stocks),
        unchanged: parseInt(marketStats.unchanged_stocks),
        advance_decline_ratio: parseFloat(advanceDeclineRatio.toFixed(2)),
        average_change_percent: parseFloat(marketStats.avg_change_percent || 0).toFixed(2)
      },
      market_cap: {
        total: parseFloat(marketStats.total_market_cap || 0)
      },
      economic_indicators: econResult.rows,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching market overview:', error);
    console.error('Error stack:', error.stack);
    res.status(500).json({ 
      error: 'Failed to fetch market overview', 
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get sentiment history over time
router.get('/sentiment/history', async (req, res) => {
  try {
    const days = parseInt(req.query.days) || 30;
    console.log(`Sentiment history endpoint called for ${days} days`);
    
    const fearGreedQuery = `
      SELECT value, value_text, timestamp
      FROM fear_greed_index 
      WHERE timestamp >= NOW() - INTERVAL '${days} days'
      ORDER BY timestamp DESC
      LIMIT 100
    `;

    const naaimQuery = `
      SELECT bullish_8100, bearish, average, week_ending
      FROM naaim_sentiment 
      WHERE week_ending >= NOW() - INTERVAL '${days} days'
      ORDER BY week_ending DESC
      LIMIT 100
    `;

    const aaiiQuery = `
      SELECT bullish, neutral, bearish, date
      FROM aaii_sentiment 
      WHERE date >= NOW() - INTERVAL '${days} days'
      ORDER BY date DESC
      LIMIT 100
    `;

    const [fearGreedResult, naaimResult, aaiiResult] = await Promise.all([
      query(fearGreedQuery),
      query(naaimQuery),
      query(aaiiQuery)
    ]);

    res.json({
      period_days: days,
      fear_greed_history: fearGreedResult.rows,
      naaim_history: naaimResult.rows,
      aaii_history: aaiiResult.rows,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching sentiment history:', error);
    res.status(500).json({ 
      error: 'Failed to fetch sentiment history',
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get sector performance aggregates (market-level view)
router.get('/sectors/performance', async (req, res) => {
  try {
    console.log('Sector performance endpoint called');
    
    const sectorQuery = `
      SELECT 
        cp.sector,
        COUNT(*) as stock_count,
        COUNT(CASE WHEN md.regular_market_price > md.regular_market_previous_close THEN 1 END) as advancing_count,
        COUNT(CASE WHEN md.regular_market_price < md.regular_market_previous_close THEN 1 END) as declining_count,
        AVG((md.regular_market_price - md.regular_market_previous_close) / md.regular_market_previous_close * 100) as avg_change_percent,
        AVG(km.trailing_pe) as avg_pe_ratio,
        SUM(md.market_cap) as sector_market_cap,
        AVG(km.dividend_yield) as avg_dividend_yield
      FROM company_profile cp
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      LEFT JOIN key_metrics km ON cp.ticker = km.ticker
      WHERE cp.sector IS NOT NULL
        AND md.regular_market_price IS NOT NULL 
        AND md.regular_market_previous_close IS NOT NULL 
        AND md.regular_market_previous_close > 0
      GROUP BY cp.sector
      HAVING COUNT(*) >= 5
      ORDER BY avg_change_percent DESC
    `;

    const result = await query(sectorQuery);

    // Calculate advance/decline ratios for each sector
    const sectorsWithRatios = result.rows.map(sector => ({
      ...sector,
      advance_decline_ratio: sector.declining_count > 0 
        ? parseFloat((sector.advancing_count / sector.declining_count).toFixed(2))
        : sector.advancing_count > 0 ? 99.99 : 0,
      avg_change_percent: parseFloat(sector.avg_change_percent || 0).toFixed(2),
      avg_pe_ratio: parseFloat(sector.avg_pe_ratio || 0).toFixed(2),
      sector_market_cap: parseFloat(sector.sector_market_cap || 0),
      avg_dividend_yield: parseFloat(sector.avg_dividend_yield || 0).toFixed(2)
    }));

    res.json({
      sectors: sectorsWithRatios,
      summary: {
        total_sectors: sectorsWithRatios.length,
        best_performing: sectorsWithRatios[0]?.sector || null,
        worst_performing: sectorsWithRatios[sectorsWithRatios.length - 1]?.sector || null
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching sector performance:', error);
    res.status(500).json({ 
      error: 'Failed to fetch sector performance',
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get market breadth indicators
router.get('/breadth', async (req, res) => {
  try {
    console.log('Market breadth endpoint called');
    
    // Current breadth
    const currentBreadthQuery = `
      SELECT 
        COUNT(*) as total_stocks,
        COUNT(CASE WHEN md.regular_market_price > md.regular_market_previous_close THEN 1 END) as advancing,
        COUNT(CASE WHEN md.regular_market_price < md.regular_market_previous_close THEN 1 END) as declining,
        COUNT(CASE WHEN md.regular_market_price = md.regular_market_previous_close THEN 1 END) as unchanged,
        COUNT(CASE WHEN (md.regular_market_price - md.regular_market_previous_close) / md.regular_market_previous_close * 100 > 5 THEN 1 END) as strong_gainers,
        COUNT(CASE WHEN (md.regular_market_price - md.regular_market_previous_close) / md.regular_market_previous_close * 100 < -5 THEN 1 END) as strong_decliners
      FROM market_data md
      WHERE md.regular_market_price IS NOT NULL 
        AND md.regular_market_previous_close IS NOT NULL 
        AND md.regular_market_previous_close > 0
    `;

    // New highs and lows (using 52-week data if available)
    const highLowQuery = `
      SELECT 
        COUNT(CASE WHEN md.regular_market_price >= md.fifty_two_week_high * 0.98 THEN 1 END) as near_52_week_high,
        COUNT(CASE WHEN md.regular_market_price <= md.fifty_two_week_low * 1.02 THEN 1 END) as near_52_week_low,
        COUNT(CASE WHEN md.regular_market_price = md.fifty_two_week_high THEN 1 END) as at_52_week_high,
        COUNT(CASE WHEN md.regular_market_price = md.fifty_two_week_low THEN 1 END) as at_52_week_low
      FROM market_data md
      WHERE md.regular_market_price IS NOT NULL 
        AND md.fifty_two_week_high IS NOT NULL
        AND md.fifty_two_week_low IS NOT NULL
    `;

    const [breadthResult, highLowResult] = await Promise.all([
      query(currentBreadthQuery),
      query(highLowQuery)
    ]);

    const breadth = breadthResult.rows[0];
    const highLow = highLowResult.rows[0];
    
    const advanceDeclineRatio = breadth.declining > 0 
      ? parseFloat((breadth.advancing / breadth.declining).toFixed(2))
      : breadth.advancing > 0 ? 99.99 : 0;

    res.json({
      current_breadth: {
        total_stocks: parseInt(breadth.total_stocks),
        advancing: parseInt(breadth.advancing),
        declining: parseInt(breadth.declining),
        unchanged: parseInt(breadth.unchanged),
        strong_gainers: parseInt(breadth.strong_gainers),
        strong_decliners: parseInt(breadth.strong_decliners),
        advance_decline_ratio: advanceDeclineRatio,
        advance_decline_percent: parseFloat((breadth.advancing / breadth.total_stocks * 100).toFixed(1))
      },
      new_highs_lows: {
        near_52_week_high: parseInt(highLow.near_52_week_high),
        near_52_week_low: parseInt(highLow.near_52_week_low),
        at_52_week_high: parseInt(highLow.at_52_week_high),
        at_52_week_low: parseInt(highLow.at_52_week_low)
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching market breadth:', error);
    res.status(500).json({ 
      error: 'Failed to fetch market breadth',
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get economic indicators
router.get('/economic', async (req, res) => {
  try {
    const days = parseInt(req.query.days) || 90;
    console.log(`Economic indicators endpoint called for ${days} days`);
    
    const econQuery = `
      SELECT 
        indicator_name,
        value,
        date,
        description,
        source,
        unit
      FROM economic_data 
      WHERE date >= CURRENT_DATE - INTERVAL '${days} days'
      ORDER BY date DESC, indicator_name ASC
      LIMIT 100
    `;

    const result = await query(econQuery);

    // Group by indicator type
    const indicators = {};
    result.rows.forEach(row => {
      if (!indicators[row.indicator_name]) {
        indicators[row.indicator_name] = [];
      }
      indicators[row.indicator_name].push(row);
    });

    res.json({
      period_days: days,
      indicators: indicators,
      total_data_points: result.rows.length,
      indicator_types: Object.keys(indicators),
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching economic indicators:', error);
    res.status(500).json({ 
      error: 'Failed to fetch economic indicators',
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

module.exports = router;
