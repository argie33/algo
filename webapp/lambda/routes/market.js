const express = require('express');
const { query } = require('../utils/database');

const router = express.Router();

// Debug endpoint to check market tables status
router.get('/debug', async (req, res) => {
  // console.log('Market debug endpoint called');
  
  try {
    const db = await getDatabase();
    if (!db) {
      return res.status(503).json({ error: 'Database unavailable' });
    }

    // Check table existence
    const tables = ['market_data', 'economic_data', 'fear_greed_index', 'naaim'];
    const tableStatus = {};

    for (const table of tables) {
      const tableExists = await db.query(`
        SELECT EXISTS (
          SELECT FROM information_schema.tables 
          WHERE table_schema = 'public' 
          AND table_name = $1
        );
      `, [table]);
      
      // console.log(`Table ${table} exists:`, tableExists.rows[0]);
      tableStatus[table] = tableExists.rows[0].exists;
    }

    res.json({
      tables: tableStatus,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Error in market debug:', error);
    res.status(500).json({ error: 'Failed to check market tables' });
  }
});

// Simple test endpoint that returns raw data
router.get('/test', async (req, res) => {
  // console.log('Market test endpoint called');
  
  try {
    const db = await getDatabase();
    if (!db) {
      return res.status(503).json({ error: 'Database unavailable' });
    }

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
      const marketResult = await db.query(marketDataQuery);
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
      const economicResult = await db.query(economicDataQuery);
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
  // console.log('Market overview endpoint called');
  
  try {
    const db = await getDatabase();
    if (!db) {
      return res.status(503).json({ error: 'Database unavailable' });
    }

    // Check if market_data table exists
    const tableExists = await db.query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'market_data'
      );
    `, []);

    // console.log('Table existence check:', tableExists);

    if (!tableExists.rows[0].exists) {
      return res.status(404).json({ 
        error: 'Market data table not found',
        message: 'Market data has not been loaded yet'
      });
    }

    // Get market overview data
    const overviewQuery = `
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
      WHERE date = (SELECT MAX(date) FROM market_data)
      ORDER BY ABS(change_percent) DESC
      LIMIT 50
    `;

    const result = await db.query(overviewQuery);

    res.json({
      data: result.rows,
      count: result.rows.length,
      lastUpdated: result.rows.length > 0 ? result.rows[0].date : null
    });
  } catch (error) {
    console.error('Error fetching market overview:', error);
    res.status(500).json({ error: 'Failed to fetch market overview' });
  }
});

// Get sentiment history over time
router.get('/sentiment/history', async (req, res) => {
  const { days = 30 } = req.query;
  
  // console.log(`Sentiment history endpoint called for ${days} days`);
  
  try {
    const db = await getDatabase();
    if (!db) {
      return res.status(503).json({ error: 'Database unavailable' });
    }

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
      const fearGreedResult = await db.query(fearGreedQuery);
      fearGreedData = fearGreedResult.rows;
    } catch (e) {
      // Table might not exist
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
      const naaimResult = await db.query(naaimQuery);
      naaimData = naaimResult.rows;
    } catch (e) {
      // Table might not exist
    }

    res.json({
      fear_greed: fearGreedData,
      naaim: naaimData,
      days: parseInt(days)
    });
  } catch (error) {
    console.error('Error fetching sentiment history:', error);
    res.status(500).json({ error: 'Failed to fetch sentiment history' });
  }
});

// Get sector performance aggregates (market-level view)
router.get('/sectors/performance', async (req, res) => {
  // console.log('Sector performance endpoint called');
  
  try {
    const db = await getDatabase();
    if (!db) {
      return res.status(503).json({ error: 'Database unavailable' });
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

    const result = await db.query(sectorQuery);

    res.json({
      data: result.rows,
      count: result.rows.length
    });
  } catch (error) {
    console.error('Error fetching sector performance:', error);
    res.status(500).json({ error: 'Failed to fetch sector performance' });
  }
});

// Get market breadth indicators
router.get('/breadth', async (req, res) => {
  // console.log('Market breadth endpoint called');
  
  try {
    const db = await getDatabase();
    if (!db) {
      return res.status(503).json({ error: 'Database unavailable' });
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

    const result = await db.query(breadthQuery);
    const breadth = result.rows[0];

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
    res.status(500).json({ error: 'Failed to fetch market breadth' });
  }
});

// Get economic indicators
router.get('/economic/indicators', async (req, res) => {
  const { days = 90 } = req.query;
  
  // console.log(`Economic indicators endpoint called for ${days} days`);
  
  try {
    const db = await getDatabase();
    if (!db) {
      return res.status(503).json({ error: 'Database unavailable' });
    }

    // Check if economic_data table exists
    const tableExists = await db.query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'economic_data'
      );
    `, []);

    if (!tableExists.rows[0].exists) {
      // console.log('Economic data table does not exist, returning empty data');
      return res.json({
        data: [],
        count: 0,
        message: 'Economic data not available'
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

    const result = await db.query(economicQuery);
    // console.log(`Found ${result.rows.length} economic data points`);

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

    // console.log(`Processed ${Object.keys(indicators).length} economic indicators`);

    res.json({
      data: indicators,
      count: Object.keys(indicators).length,
      total_points: result.rows.length
    });
  } catch (error) {
    console.error('Error fetching economic indicators:', error);
    res.status(500).json({ error: 'Failed to fetch economic indicators' });
  }
});

// Get NAAIM data (for DataValidation page)
router.get('/naaim', async (req, res) => {
  const { limit = 30 } = req.query;
  
  // console.log(`NAAIM data endpoint called with limit: ${limit}`);
  
  try {
    const db = await getDatabase();
    if (!db) {
      return res.status(503).json({ error: 'Database unavailable' });
    }

    const query = `
      SELECT 
        date,
        exposure_index,
        long_exposure,
        short_exposure
      FROM naaim
      ORDER BY date DESC
      LIMIT $1
    `;

    const result = await db.query(query, [parseInt(limit)]);

    res.json({
      data: result.rows,
      count: result.rows.length
    });
  } catch (error) {
    console.error('Error fetching NAAIM data:', error);
    res.status(500).json({ error: 'Failed to fetch NAAIM data' });
  }
});

// Get fear & greed data (for DataValidation page)
router.get('/fear-greed', async (req, res) => {
  const { limit = 30 } = req.query;
  
  // console.log(`Fear & Greed data endpoint called with limit: ${limit}`);
  
  try {
    const db = await getDatabase();
    if (!db) {
      return res.status(503).json({ error: 'Database unavailable' });
    }

    const query = `
      SELECT 
        date,
        value,
        classification
      FROM fear_greed_index
      ORDER BY date DESC
      LIMIT $1
    `;

    const result = await db.query(query, [parseInt(limit)]);

    res.json({
      data: result.rows,
      count: result.rows.length
    });
  } catch (error) {
    console.error('Error fetching Fear & Greed data:', error);
    res.status(500).json({ error: 'Failed to fetch Fear & Greed data' });
  }
});

// Get economic data (for DataValidation page)
router.get('/economic', async (req, res) => {
  const { limit = 30 } = req.query;
  
  // console.log(`Economic data endpoint called with limit: ${limit}`);
  
  try {
    const db = await getDatabase();
    if (!db) {
      return res.status(503).json({ error: 'Database unavailable' });
    }

    const query = `
      SELECT 
        date,
        indicator_name,
        value,
        unit,
        frequency
      FROM economic_data
      ORDER BY date DESC, indicator_name
      LIMIT $1
    `;

    const result = await db.query(query, [parseInt(limit)]);

    res.json({
      data: result.rows,
      count: result.rows.length
    });
  } catch (error) {
    console.error('Error fetching economic data:', error);
    res.status(500).json({ error: 'Failed to fetch economic data' });
  }
});

module.exports = router;
