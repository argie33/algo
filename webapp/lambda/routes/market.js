const express = require('express');
const { query } = require('../utils/database');

const router = express.Router();

// Helper function to check if required tables exist
async function checkRequiredTables(tableNames) {
  const results = {};
  for (const tableName of tableNames) {
    try {
      const tableExistsResult = await query(
        `SELECT EXISTS (
          SELECT FROM information_schema.tables 
          WHERE table_schema = 'public' 
          AND table_name = $1
        );`,
        [tableName]
      );
      results[tableName] = tableExistsResult.rows[0].exists;
    } catch (error) {
      console.error(`Error checking table ${tableName}:`, error.message);
      results[tableName] = false;
    }
  }
  return results;
}

// Root endpoint for testing
router.get('/', (req, res) => {
  res.json({
    status: 'ok',
    endpoint: 'market',
    available_routes: [
      '/overview',
      '/sentiment/history',
      '/sectors/performance',
      '/breadth',
      '/economic',
      '/naaim',
      '/fear-greed',
      '/indices',
      '/sectors',
      '/volatility',
      '/calendar',
      '/indicators',
      '/sentiment'
    ],
    timestamp: new Date().toISOString()
  });
});

// Debug endpoint to check market tables status
router.get('/debug', async (req, res) => {
  console.log('[MARKET] Debug endpoint called');
  
  try {
    // Check all market-related tables
    const requiredTables = [
      'market_data', 'economic_data', 'fear_greed_index', 'naaim', 
      'company_profile', 'aaii_sentiment'
    ];
    
    const tableStatus = await checkRequiredTables(requiredTables);
    
    // Get record counts for existing tables
    const recordCounts = {};
    for (const [tableName, exists] of Object.entries(tableStatus)) {
      if (exists) {
        try {
          const countResult = await query(`SELECT COUNT(*) as count FROM ${tableName}`);
          recordCounts[tableName] = parseInt(countResult.rows[0].count);
        } catch (error) {
          recordCounts[tableName] = { error: error.message };
        }
      } else {
        recordCounts[tableName] = 'Table does not exist';
      }
    }

    res.json({
      status: 'ok',
      timestamp: new Date().toISOString(),
      tables: tableStatus,
      recordCounts: recordCounts,
      endpoint: 'market'
    });
  } catch (error) {
    console.error('[MARKET] Error in debug endpoint:', error);
    res.status(500).json({ 
      error: 'Failed to check market tables', 
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Test endpoint for the fixed overview structure
router.get('/overview-test', async (req, res) => {
  console.log('Market overview test endpoint called');
  
  try {
    // Return a simplified structure that matches what frontend expects
    const testData = {
      sentiment_indicators: {
        fear_greed: { value: 50, value_text: 'Neutral', timestamp: new Date().toISOString() },
        naaim: { average: 45.5, week_ending: new Date().toISOString() },
        aaii: { bullish: 0.35, neutral: 0.30, bearish: 0.35, date: new Date().toISOString() }
      },
      market_breadth: {
        total_stocks: 5000,
        advancing: 2500,
        declining: 2200,
        unchanged: 300,
        advance_decline_ratio: '1.14',
        average_change_percent: '0.25'
      },
      market_cap: {
        large_cap: 25000000000000,
        mid_cap: 5000000000000,
        small_cap: 2000000000000,
        total: 32000000000000
      },
      economic_indicators: [
        { name: 'GDP Growth', value: 2.1, unit: '%', timestamp: new Date().toISOString() },
        { name: 'Unemployment Rate', value: 3.7, unit: '%', timestamp: new Date().toISOString() }
      ]
    };
    
    res.json({
      data: testData,
      timestamp: new Date().toISOString(),
      status: 'success',
      message: 'Test data with correct structure'
    });
  } catch (error) {
    console.error('Error in overview test:', error);
    res.status(500).json({ error: 'Test failed', details: error.message });
  }
});

// Simple test endpoint that returns raw data
router.get('/test', async (req, res) => {
  // console.log('Market test endpoint called');
  
  try {
    // Test market data table
    const marketDataQuery = `
      SELECT 
        COUNT(*) as total_records,
        COUNT(DISTINCT symbol) as unique_symbols,
        MIN(date) as earliest_date,
        MAX(date) as latest_date
      FROM market_data
      LIMIT 1
    `;

    let marketData = null;
    try {
      const marketResult = await query(marketDataQuery);
      marketData = marketResult.rows[0];
    } catch (e) {
      marketData = { error: e.message };
    }

    // Test economic data table
    const economicDataQuery = `
      SELECT 
        COUNT(*) as total_records,
        MIN(date) as earliest_date,
        MAX(date) as latest_date
      FROM economic_data
      LIMIT 1
    `;

    let economicData = null;
    try {
      const economicResult = await query(economicDataQuery);
      economicData = economicResult.rows[0];
    } catch (e) {
      economicData = { error: e.message };
    }

    res.json({
      market_data: marketData,
      economic_data: economicData,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Error in market test:', error);
    res.status(500).json({ error: 'Failed to test market data' });
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
  console.log('Market overview endpoint called');
  
  try {
    // Check if market_data table exists
    const tableExists = await query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'market_data'
      );
    `, []);

    console.log('Table existence check:', tableExists.rows[0].exists);

    if (!tableExists.rows[0].exists) {
      return res.status(500).json({ error: 'Market data table not found in database' });
    }

    // Get sentiment indicators
    let sentimentIndicators = {};
    
    // Get Fear & Greed Index
    try {
      const fearGreedQuery = `
        SELECT value, value_text, timestamp 
        FROM fear_greed_index 
        ORDER BY timestamp DESC 
        LIMIT 1
      `;
      const fearGreedResult = await query(fearGreedQuery);
      if (fearGreedResult.rows.length > 0) {
        sentimentIndicators.fear_greed = {
          value: fearGreedResult.rows[0].value,
          value_text: fearGreedResult.rows[0].value_text,
          timestamp: fearGreedResult.rows[0].timestamp
        };
      }
    } catch (e) {
      console.log('Fear & Greed data not available:', e.message);
    }

    // Get NAAIM data
    try {
      const naaimQuery = `
        SELECT average, bullish_8100, bearish, week_ending 
        FROM naaim 
        ORDER BY week_ending DESC 
        LIMIT 1
      `;
      const naaimResult = await query(naaimQuery);
      if (naaimResult.rows.length > 0) {
        sentimentIndicators.naaim = {
          average: naaimResult.rows[0].average,
          bullish_8100: naaimResult.rows[0].bullish_8100,
          bearish: naaimResult.rows[0].bearish,
          week_ending: naaimResult.rows[0].week_ending
        };
      }
    } catch (e) {
      console.log('NAAIM data not available:', e.message);
    }

    // Get AAII data (from aaii_sentiment table)
    try {
      console.log('Attempting to fetch AAII data...');
      const aaiiQuery = `
        SELECT bullish, neutral, bearish, date 
        FROM aaii_sentiment 
        ORDER BY date DESC 
        LIMIT 1
      `;
      const aaiiResult = await query(aaiiQuery);
      console.log(`AAII query returned ${aaiiResult.rows.length} rows`);
      if (aaiiResult.rows.length > 0) {
        console.log('AAII data found:', aaiiResult.rows[0]);
        sentimentIndicators.aaii = {
          bullish: aaiiResult.rows[0].bullish,
          neutral: aaiiResult.rows[0].neutral,
          bearish: aaiiResult.rows[0].bearish,
          date: aaiiResult.rows[0].date
        };
      } else {
        console.log('No AAII data found in table');
      }
    } catch (e) {
      console.error('AAII data error:', e.message);
      console.error('Full AAII error:', e);
    }

    // Get market breadth
    let marketBreadth = {};
    try {
      const breadthQuery = `
        SELECT 
          COUNT(*) as total_stocks,
          COUNT(CASE WHEN change_percent > 0 THEN 1 END) as advancing,
          COUNT(CASE WHEN change_percent < 0 THEN 1 END) as declining,
          COUNT(CASE WHEN change_percent = 0 THEN 1 END) as unchanged,
          AVG(change_percent) as average_change_percent
        FROM market_data
        WHERE date = (SELECT MAX(date) FROM market_data)
      `;
      const breadthResult = await query(breadthQuery);
      if (breadthResult.rows.length > 0) {
        const breadth = breadthResult.rows[0];
        marketBreadth = {
          total_stocks: parseInt(breadth.total_stocks),
          advancing: parseInt(breadth.advancing),
          declining: parseInt(breadth.declining),
          unchanged: parseInt(breadth.unchanged),
          advance_decline_ratio: breadth.declining > 0 ? (breadth.advancing / breadth.declining).toFixed(2) : 'N/A',
          average_change_percent: parseFloat(breadth.average_change_percent).toFixed(2)
        };
      }
    } catch (e) {
      console.log('Market breadth data not available:', e.message);
    }

    // Get market cap distribution
    let marketCap = {};
    try {
      const marketCapQuery = `
        SELECT 
          SUM(CASE WHEN market_cap >= 10000000000 THEN market_cap ELSE 0 END) as large_cap,
          SUM(CASE WHEN market_cap >= 2000000000 AND market_cap < 10000000000 THEN market_cap ELSE 0 END) as mid_cap,
          SUM(CASE WHEN market_cap < 2000000000 THEN market_cap ELSE 0 END) as small_cap,
          SUM(market_cap) as total
        FROM market_data
        WHERE date = (SELECT MAX(date) FROM market_data)
          AND market_cap IS NOT NULL
      `;
      const marketCapResult = await query(marketCapQuery);
      if (marketCapResult.rows.length > 0) {
        marketCap = {
          large_cap: parseFloat(marketCapResult.rows[0].large_cap) || 0,
          mid_cap: parseFloat(marketCapResult.rows[0].mid_cap) || 0,
          small_cap: parseFloat(marketCapResult.rows[0].small_cap) || 0,
          total: parseFloat(marketCapResult.rows[0].total) || 0
        };
      }
    } catch (e) {
      console.log('Market cap data not available:', e.message);
    }

    // Get economic indicators
    let economicIndicators = [];
    try {
      const economicQuery = `
        SELECT name, value, unit, timestamp 
        FROM economic_data 
        ORDER BY timestamp DESC 
        LIMIT 10
      `;
      const economicResult = await query(economicQuery);
      economicIndicators = economicResult.rows.map(row => ({
        name: row.name,
        value: row.value,
        unit: row.unit,
        timestamp: row.timestamp
      }));
    } catch (e) {
      console.log('Economic indicators not available:', e.message);
    }

    // Return comprehensive market overview
    const responseData = {
      sentiment_indicators: sentimentIndicators,
      market_breadth: marketBreadth,
      market_cap: marketCap,
      economic_indicators: economicIndicators
    };

    console.log('Market overview response structure:', Object.keys(responseData));
    console.log('Sentiment indicators in response:', Object.keys(sentimentIndicators));
    console.log('AAII in sentiment indicators:', !!sentimentIndicators.aaii);
    
    res.json({
      data: responseData,
      timestamp: new Date().toISOString(),
      status: 'success'
    });
    
  } catch (error) {
    console.error('Error fetching market overview:', error);
    res.status(500).json({ 
      error: 'Database error', 
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get sentiment history over time
router.get('/sentiment/history', async (req, res) => {
  const { days = 30 } = req.query;
  
  console.log(`Sentiment history endpoint called for ${days} days`);
  
  try {
    // Get fear & greed data
    const fearGreedQuery = `
      SELECT 
        date,
        value,
        classification
      FROM fear_greed_index
      WHERE date >= NOW() - INTERVAL '${days} days'
      ORDER BY date DESC
      LIMIT 100
    `;

    let fearGreedData = [];
    try {
      const fearGreedResult = await query(fearGreedQuery);
      fearGreedData = fearGreedResult.rows;
    } catch (e) {
      console.log('Fear & greed table not available, using fallback data');
      // Generate fallback fear & greed data
      for (let i = 0; i < 30; i++) {
        const date = new Date();
        date.setDate(date.getDate() - i);
        fearGreedData.push({
          date: date.toISOString(),
          value: Math.floor(Math.random() * 100),
          classification: ['Extreme Fear', 'Fear', 'Neutral', 'Greed', 'Extreme Greed'][Math.floor(Math.random() * 5)]
        });
      }
    }

    // Get NAAIM data
    const naaimQuery = `
      SELECT 
        date,
        exposure_index,
        long_exposure,
        short_exposure
      FROM naaim
      WHERE date >= NOW() - INTERVAL '${days} days'
      ORDER BY date DESC
      LIMIT 100
    `;

    let naaimData = [];
    try {
      const naaimResult = await query(naaimQuery);
      naaimData = naaimResult.rows;
    } catch (e) {
      console.log('NAAIM table not available, using fallback data');
      // Generate fallback NAAIM data
      for (let i = 0; i < 30; i++) {
        const date = new Date();
        date.setDate(date.getDate() - i);
        naaimData.push({
          date: date.toISOString(),
          exposure_index: Math.floor(Math.random() * 100),
          long_exposure: Math.floor(Math.random() * 100),
          short_exposure: Math.floor(Math.random() * 50)
        });
      }
    }

    res.json({
      data: {
        fear_greed: fearGreedData,
        naaim: naaimData
      },
      count: fearGreedData.length + naaimData.length,
      period_days: days
    });
  } catch (error) {
    console.error('Error fetching sentiment history:', error);
    // Return fallback data on error
    const fallbackData = {
      fear_greed: [],
      naaim: []
    };
    
    // Generate fallback data
    for (let i = 0; i < 30; i++) {
      const date = new Date();
      date.setDate(date.getDate() - i);
      fallbackData.fear_greed.push({
        date: date.toISOString(),
        value: Math.floor(Math.random() * 100),
        classification: ['Extreme Fear', 'Fear', 'Neutral', 'Greed', 'Extreme Greed'][Math.floor(Math.random() * 5)]
      });
      fallbackData.naaim.push({
        date: date.toISOString(),
        exposure_index: Math.floor(Math.random() * 100),
        long_exposure: Math.floor(Math.random() * 100),
        short_exposure: Math.floor(Math.random() * 50)
      });
    }
    
    res.json({
      data: fallbackData,
      count: 60,
      period_days: days,
      error: 'Database error, using fallback data',
      details: error.message
    });
  }
});

// Get sector performance aggregates (market-level view)
router.get('/sectors/performance', async (req, res) => {
  console.log('Sector performance endpoint called');
  
  try {
    // Check if market_data table exists
    const tableExists = await query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'market_data'
      );
    `, []);

    if (!tableExists.rows[0].exists) {
      console.log('Market data table not found, returning fallback sector data');
      // Return fallback sector data
      const fallbackSectors = [
        { sector: 'Technology', stock_count: 150, avg_change: 2.5, total_volume: 5000000000, avg_market_cap: 50000000000 },
        { sector: 'Healthcare', stock_count: 120, avg_change: 1.8, total_volume: 3000000000, avg_market_cap: 40000000000 },
        { sector: 'Financial', stock_count: 100, avg_change: 0.9, total_volume: 2500000000, avg_market_cap: 35000000000 },
        { sector: 'Consumer Discretionary', stock_count: 80, avg_change: 1.2, total_volume: 2000000000, avg_market_cap: 30000000000 },
        { sector: 'Industrial', stock_count: 90, avg_change: 0.7, total_volume: 1800000000, avg_market_cap: 25000000000 }
      ];
      
      return res.json({
        data: fallbackSectors,
        count: fallbackSectors.length,
        message: 'Using fallback data - market_data table not available'
      });
    }

    // Get sector performance data
    const sectorQuery = `
      SELECT 
        sector,
        COUNT(*) as stock_count,
        AVG(change_percent) as avg_change,
        SUM(volume) as total_volume,
        AVG(market_cap) as avg_market_cap
      FROM market_data
      WHERE date = (SELECT MAX(date) FROM market_data)
        AND sector IS NOT NULL
        AND sector != ''
      GROUP BY sector
      ORDER BY avg_change DESC
      LIMIT 20
    `;

    const result = await query(sectorQuery);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.status(404).json({ error: 'No data found for this query' });
    }

    res.json({
      data: result.rows,
      count: result.rows.length
    });
  } catch (error) {
    console.error('Error fetching sector performance:', error);
    // Return fallback data on error
    const fallbackSectors = [
      { sector: 'Technology', stock_count: 150, avg_change: 2.5, total_volume: 5000000000, avg_market_cap: 50000000000 },
      { sector: 'Healthcare', stock_count: 120, avg_change: 1.8, total_volume: 3000000000, avg_market_cap: 40000000000 },
      { sector: 'Financial', stock_count: 100, avg_change: 0.9, total_volume: 2500000000, avg_market_cap: 35000000000 }
    ];
    
    res.json({
      data: fallbackSectors,
      count: fallbackSectors.length,
      error: 'Database error, using fallback data',
      details: error.message
    });
  }
});

// Get market breadth indicators
router.get('/breadth', async (req, res) => {
  console.log('Market breadth endpoint called');
  
  try {
    // Check if market_data table exists
    const tableExists = await query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'market_data'
      );
    `, []);

    if (!tableExists.rows[0].exists) {
      console.log('Market data table not found, returning fallback breadth data');
      // Return fallback breadth data
      return res.json({
        total_stocks: 5000,
        advancing: 2800,
        declining: 2000,
        unchanged: 200,
        strong_advancing: 450,
        strong_declining: 320,
        advance_decline_ratio: '1.40',
        avg_change: '0.85',
        avg_volume: 2500000,
        message: 'Using fallback data - market_data table not available'
      });
    }

    // Get market breadth data
    const breadthQuery = `
      SELECT 
        COUNT(*) as total_stocks,
        COUNT(CASE WHEN change_percent > 0 THEN 1 END) as advancing,
        COUNT(CASE WHEN change_percent < 0 THEN 1 END) as declining,
        COUNT(CASE WHEN change_percent = 0 THEN 1 END) as unchanged,
        COUNT(CASE WHEN change_percent > 5 THEN 1 END) as strong_advancing,
        COUNT(CASE WHEN change_percent < -5 THEN 1 END) as strong_declining,
        AVG(change_percent) as avg_change,
        AVG(volume) as avg_volume
      FROM market_data
      WHERE date = (SELECT MAX(date) FROM market_data)
    `;

    const result = await query(breadthQuery);
    const breadth = result.rows[0];

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.status(404).json({ error: 'No data found for this query' });
    }

    res.json({
      total_stocks: parseInt(breadth.total_stocks),
      advancing: parseInt(breadth.advancing),
      declining: parseInt(breadth.declining),
      unchanged: parseInt(breadth.unchanged),
      strong_advancing: parseInt(breadth.strong_advancing),
      strong_declining: parseInt(breadth.strong_declining),
      advance_decline_ratio: breadth.declining > 0 ? (breadth.advancing / breadth.declining).toFixed(2) : 'N/A',
      avg_change: parseFloat(breadth.avg_change).toFixed(2),
      avg_volume: parseInt(breadth.avg_volume)
    });
  } catch (error) {
    console.error('Error fetching market breadth:', error);
    // Return fallback data on error
    res.json({
      total_stocks: 5000,
      advancing: 2800,
      declining: 2000,
      unchanged: 200,
      strong_advancing: 450,
      strong_declining: 320,
      advance_decline_ratio: '1.40',
      avg_change: '0.85',
      avg_volume: 2500000,
      error: 'Database error, using fallback data',
      details: error.message
    });
  }
});

// Get economic indicators
router.get('/economic', async (req, res) => {
  const { days = 90 } = req.query;
  
  console.log(`Economic indicators endpoint called for ${days} days`);
  
  try {
    // Check if economic_data table exists
    const tableExists = await query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'economic_data'
      );
    `, []);

    if (!tableExists.rows[0].exists) {
      console.log('Economic data table does not exist, returning fallback data');
      // Return fallback economic data
      const fallbackIndicators = {
        'GDP Growth Rate': [
          { date: new Date().toISOString(), value: 2.1, unit: '%' },
          { date: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString(), value: 1.9, unit: '%' }
        ],
        'Unemployment Rate': [
          { date: new Date().toISOString(), value: 3.7, unit: '%' },
          { date: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString(), value: 3.8, unit: '%' }
        ],
        'Inflation Rate': [
          { date: new Date().toISOString(), value: 3.2, unit: '%' },
          { date: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString(), value: 3.4, unit: '%' }
        ],
        'Federal Funds Rate': [
          { date: new Date().toISOString(), value: 5.25, unit: '%' },
          { date: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString(), value: 5.00, unit: '%' }
        ]
      };
      
      return res.json({
        data: fallbackIndicators,
        count: Object.keys(fallbackIndicators).length,
        total_points: 8,
        message: 'Using fallback data - economic_data table not available'
      });
    }

    // Get economic indicators
    const economicQuery = `
      SELECT 
        date,
        indicator_name,
        value,
        unit,
        frequency
      FROM economic_data
      WHERE date >= NOW() - INTERVAL '${days} days'
      ORDER BY date DESC, indicator_name
      LIMIT 500
    `;

    const result = await query(economicQuery);
    console.log(`Found ${result.rows.length} economic data points`);

    // Group by indicator
    const indicators = {};
    result.rows.forEach(row => {
      if (!indicators[row.indicator_name]) {
        indicators[row.indicator_name] = [];
      }
      indicators[row.indicator_name].push({
        date: row.date,
        value: row.value,
        unit: row.unit
      });
    });

    console.log(`Processed ${Object.keys(indicators).length} economic indicators`);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.status(404).json({ error: 'No data found for this query' });
    }

    res.json({
      data: indicators,
      count: Object.keys(indicators).length,
      total_points: result.rows.length
    });
  } catch (error) {
    console.error('Error fetching economic indicators:', error);
    // Return fallback data on error
    const fallbackIndicators = {
      'GDP Growth Rate': [
        { date: new Date().toISOString(), value: 2.1, unit: '%' }
      ],
      'Unemployment Rate': [
        { date: new Date().toISOString(), value: 3.7, unit: '%' }
      ],
      'Inflation Rate': [
        { date: new Date().toISOString(), value: 3.2, unit: '%' }
      ]
    };
    
    res.json({
      data: fallbackIndicators,
      count: Object.keys(fallbackIndicators).length,
      total_points: 3,
      error: 'Database error, using fallback data',
      details: error.message
    });
  }
});

// Get NAAIM data (for DataValidation page)
router.get('/naaim', async (req, res) => {
  const { limit = 30 } = req.query;
  
  console.log(`NAAIM data endpoint called with limit: ${limit}`);
  
  try {
    const naaimQuery = `
      SELECT 
        date,
        exposure_index,
        long_exposure,
        short_exposure
      FROM naaim
      ORDER BY date DESC
      LIMIT $1
    `;

    const result = await query(naaimQuery, [parseInt(limit)]);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.status(404).json({ error: 'No data found for this query' });
    }

    res.json({
      data: result.rows,
      count: result.rows.length
    });
  } catch (error) {
    console.error('Error fetching NAAIM data:', error);
    // Return fallback data on error
    const fallbackData = [];
    for (let i = 0; i < Math.min(limit, 30); i++) {
      const date = new Date();
      date.setDate(date.getDate() - i);
      fallbackData.push({
        date: date.toISOString(),
        exposure_index: Math.floor(Math.random() * 100),
        long_exposure: Math.floor(Math.random() * 100),
        short_exposure: Math.floor(Math.random() * 50)
      });
    }
    
    res.json({
      data: fallbackData,
      count: fallbackData.length,
      error: 'Database error, using fallback data',
      details: error.message
    });
  }
});

// Get fear & greed data (for DataValidation page)
router.get('/fear-greed', async (req, res) => {
  const { limit = 30 } = req.query;
  
  console.log(`Fear & Greed data endpoint called with limit: ${limit}`);
  
  try {
    const fearGreedQuery = `
      SELECT 
        date,
        value,
        classification
      FROM fear_greed_index
      ORDER BY date DESC
      LIMIT $1
    `;

    const result = await query(fearGreedQuery, [parseInt(limit)]);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.status(404).json({ error: 'No data found for this query' });
    }

    res.json({
      data: result.rows,
      count: result.rows.length
    });
  } catch (error) {
    console.error('Error fetching fear & greed data:', error);
    // Return fallback data on error
    const fallbackData = [];
    const classifications = ['Extreme Fear', 'Fear', 'Neutral', 'Greed', 'Extreme Greed'];
    for (let i = 0; i < Math.min(limit, 30); i++) {
      const date = new Date();
      date.setDate(date.getDate() - i);
      fallbackData.push({
        date: date.toISOString(),
        value: Math.floor(Math.random() * 100),
        classification: classifications[Math.floor(Math.random() * classifications.length)]
      });
    }
    
    res.json({
      data: fallbackData,
      count: fallbackData.length,
      error: 'Database error, using fallback data',
      details: error.message
    });
  }
});

// Get market indices
router.get('/indices', async (req, res) => {
  try {
    // Get major market indices
    const indicesQuery = `
      SELECT 
        symbol,
        current_price,
        previous_close,
        change_percent,
        volume,
        market_cap,
        date
      FROM market_data
      WHERE symbol IN ('^GSPC', '^DJI', '^IXIC', '^RUT', '^VIX')
        AND date = (SELECT MAX(date) FROM market_data)
      ORDER BY symbol
    `;

    const result = await query(indicesQuery);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.status(404).json({ error: 'No data found for this query' });
    }

    res.json({
      data: result.rows,
      count: result.rows.length,
      lastUpdated: result.rows.length > 0 ? result.rows[0].date : null
    });
  } catch (error) {
    console.error('Error fetching market indices:', error);
    res.status(500).json({ error: 'Failed to fetch market indices' });
  }
});

// Get sector performance (alias for sectors/performance)
router.get('/sectors', async (req, res) => {
  try {
    // Get sector performance data
    const sectorQuery = `
      SELECT 
        sector,
        COUNT(*) as stock_count,
        AVG(change_percent) as avg_change,
        SUM(volume) as total_volume,
        AVG(market_cap) as avg_market_cap
      FROM market_data
      WHERE date = (SELECT MAX(date) FROM market_data)
        AND sector IS NOT NULL
        AND sector != ''
      GROUP BY sector
      ORDER BY avg_change DESC
      LIMIT 20
    `;

    const result = await query(sectorQuery);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.status(404).json({ error: 'No data found for this query' });
    }

    res.json({
      data: result.rows,
      count: result.rows.length
    });
  } catch (error) {
    console.error('Error fetching sector performance:', error);
    res.status(500).json({ error: 'Failed to fetch sector performance' });
  }
});

// Get market volatility
router.get('/volatility', async (req, res) => {
  try {
    // Get VIX and volatility data
    const volatilityQuery = `
      SELECT 
        symbol,
        current_price,
        previous_close,
        change_percent,
        date
      FROM market_data
      WHERE symbol = '^VIX'
        AND date = (SELECT MAX(date) FROM market_data)
    `;

    const result = await query(volatilityQuery);

    // Calculate market volatility from all stocks
    const marketVolatilityQuery = `
      SELECT 
        STDDEV(change_percent) as market_volatility,
        AVG(ABS(change_percent)) as avg_absolute_change
      FROM market_data
      WHERE date = (SELECT MAX(date) FROM market_data)
        AND change_percent IS NOT NULL
    `;

    const volatilityResult = await query(marketVolatilityQuery);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.status(404).json({ error: 'No data found for this query' });
    }

    res.json({
      data: {
        vix: result.rows[0] || null,
        market_volatility: volatilityResult.rows[0]?.market_volatility || 0,
        avg_absolute_change: volatilityResult.rows[0]?.avg_absolute_change || 0
      },
      lastUpdated: result.rows.length > 0 ? result.rows[0].date : null
    });
  } catch (error) {
    console.error('Error fetching market volatility:', error);
    res.status(500).json({ error: 'Failed to fetch market volatility' });
  }
});

// Get economic calendar
router.get('/calendar', async (req, res) => {
  try {
    // Mock economic calendar data for now
    const calendarData = [
      {
        event: 'FOMC Rate Decision',
        date: new Date(Date.now() + 4 * 24 * 60 * 60 * 1000).toISOString(),
        importance: 'High',
        currency: 'USD'
      },
      {
        event: 'Nonfarm Payrolls',
        date: new Date(Date.now() + 10 * 24 * 60 * 60 * 1000).toISOString(),
        importance: 'High',
        currency: 'USD'
      },
      {
        event: 'CPI Data',
        date: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
        importance: 'Medium',
        currency: 'USD'
      }
    ];

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.status(404).json({ error: 'No data found for this query' });
    }

    res.json({
      data: calendarData,
      count: calendarData.length
    });
  } catch (error) {
    console.error('Error fetching economic calendar:', error);
    res.status(500).json({ error: 'Failed to fetch economic calendar' });
  }
});

// Get market indicators
router.get('/indicators', async (req, res) => {
  console.log('📊 Market indicators endpoint called');
  
  try {
    // Get market indicators data
    const indicatorsQuery = `
      SELECT 
        symbol,
        current_price,
        previous_close,
        change_percent,
        volume,
        market_cap,
        sector,
        date
      FROM market_data
      WHERE symbol IN ('^GSPC', '^DJI', '^IXIC', '^RUT', '^VIX', 'SPY', 'QQQ', 'IWM', 'DIA')
        AND date = (SELECT MAX(date) FROM market_data)
      ORDER BY symbol
    `;

    const result = await query(indicatorsQuery);

    // Get market breadth
    const breadthQuery = `
      SELECT 
        COUNT(*) as total_stocks,
        COUNT(CASE WHEN change_percent > 0 THEN 1 END) as advancing,
        COUNT(CASE WHEN change_percent < 0 THEN 1 END) as declining,
        AVG(change_percent) as avg_change
      FROM market_data
      WHERE date = (SELECT MAX(date) FROM market_data)
    `;

    const breadthResult = await query(breadthQuery);
    const breadth = breadthResult.rows[0];

    // Get latest sentiment data
    const sentimentQuery = `
      SELECT 
        value,
        classification,
        date
      FROM fear_greed_index
      ORDER BY date DESC
      LIMIT 1
    `;

    let sentiment = null;
    try {
      const sentimentResult = await query(sentimentQuery);
      sentiment = sentimentResult.rows[0] || null;
    } catch (e) {
      // Sentiment table might not exist
    }

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.status(404).json({ error: 'No data found for this query' });
    }

    res.json({
      success: true,
      data: {
        indices: result.rows,
        breadth: {
          total_stocks: parseInt(breadth.total_stocks),
          advancing: parseInt(breadth.advancing),
          declining: parseInt(breadth.declining),
          advance_decline_ratio: breadth.declining > 0 ? (breadth.advancing / breadth.declining).toFixed(2) : 'N/A',
          avg_change: parseFloat(breadth.avg_change).toFixed(2)
        },
        sentiment: sentiment
      },
      count: result.rows.length,
      lastUpdated: result.rows.length > 0 ? result.rows[0].date : null
    });
  } catch (error) {
    console.error('Error fetching market indicators:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch market indicators',
      details: error.message
    });
  }
});

// Get market sentiment
router.get('/sentiment', async (req, res) => {
  console.log('😊 Market sentiment endpoint called');
  
  try {
    // Get latest fear & greed data
    const fearGreedQuery = `
      SELECT 
        value,
        classification,
        date
      FROM fear_greed_index
      ORDER BY date DESC
      LIMIT 1
    `;

    let fearGreed = null;
    try {
      const fearGreedResult = await query(fearGreedQuery);
      fearGreed = fearGreedResult.rows[0] || null;
    } catch (e) {
      // Table might not exist
    }

    // Get latest NAAIM data
    const naaimQuery = `
      SELECT 
        exposure_index,
        long_exposure,
        short_exposure,
        date
      FROM naaim
      ORDER BY date DESC
      LIMIT 1
    `;

    let naaim = null;
    try {
      const naaimResult = await query(naaimQuery);
      naaim = naaimResult.rows[0] || null;
    } catch (e) {
      // Table might not exist
    }

    if (!fearGreed || !naaim) {
      return res.status(404).json({ error: 'No data found for this query' });
    }

    res.json({
      success: true,
      data: {
        fear_greed: fearGreed,
        naaim: naaim
      },
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Error fetching market sentiment:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch market sentiment',
      details: error.message
    });
  }
});

module.exports = router;
