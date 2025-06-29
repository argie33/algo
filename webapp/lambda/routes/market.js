const express = require('express');
const { query } = require('../utils/database');

const router = express.Router();

// Debug endpoint to check market tables status
router.get('/debug', async (req, res) => {
  try {
    console.log('Market debug endpoint called');
    
    const tables = ['fear_greed_index', 'naaim', 'aaii_sentiment', 'economic_data'];
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
          let latestQuery;          if (table === 'fear_greed_index') {
            latestQuery = `SELECT index_value, rating, date FROM ${table} ORDER BY date DESC LIMIT 1`;
          } else if (table === 'naaim') {
            latestQuery = `SELECT naaim_number_mean as mean_exposure, bearish as bearish_exposure, bullish as bullish_exposure, date FROM ${table} ORDER BY date DESC LIMIT 1`;
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
    
    // Check if required tables exist
    const requiredTables = ['fear_greed_index', 'naaim', 'stock_symbols', 'aaii_sentiment'];
    const tableExists = {};
    
    for (const table of requiredTables) {
      try {
        const tableCheck = await query(`
          SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = '${table}'
          );
        `);
        
        tableExists[table] = tableCheck.rows[0].exists;
      } catch (checkError) {
        console.error(`Error checking table ${table}:`, checkError);
        tableExists[table] = false;
      }
    }
    
    console.log('Table existence check:', tableExists);
    
    // Initialize default results
    let fearGreedResult = { rows: [] };
    let naaimResult = { rows: [] };
    let aaiiResult = { rows: [] };
    let marketStatsResult = { rows: [{ 
      total_stocks: 0, 
      advancing_stocks: 0, 
      declining_stocks: 0, 
      unchanged_stocks: 0 
    }] };
    
    // Get data from tables that exist
    const promises = [];
    
    if (tableExists['fear_greed_index']) {
      const fearGreedQuery = `
        SELECT index_value, rating, date
        FROM fear_greed_index 
        ORDER BY date DESC 
        LIMIT 1
      `;
      promises.push(query(fearGreedQuery).then(result => ({ type: 'feargreed', result })));
    }

    if (tableExists['naaim']) {
      const naaimQuery = `
        SELECT naaim_number_mean as mean_exposure, bearish as bearish_exposure, bullish as bullish_exposure, date
        FROM naaim 
        ORDER BY date DESC 
        LIMIT 1
      `;
      promises.push(query(naaimQuery).then(result => ({ type: 'naaim', result })));
    }

    if (tableExists['aaii_sentiment']) {
      const aaiiQuery = `
        SELECT bullish, neutral, bearish, date
        FROM aaii_sentiment
        ORDER BY date DESC
        LIMIT 1
      `;
      promises.push(query(aaiiQuery).then(result => ({ type: 'aaii', result })));
    }
    
    if (tableExists['stock_symbols']) {
      const marketStatsQuery = `
        SELECT 
          COUNT(*) as total_stocks,
          0 as advancing_stocks,
          0 as declining_stocks,
          0 as unchanged_stocks,
          0 as avg_change_percent,
          0 as total_market_cap
        FROM stock_symbols
        WHERE etf = 'N'
      `;
      promises.push(query(marketStatsQuery).then(result => ({ type: 'marketstats', result })));
    }
    
    // Execute all available queries
    const results = await Promise.all(promises);
    
    // Process results
    results.forEach(({ type, result }) => {
      switch (type) {
        case 'feargreed':
          fearGreedResult = result;
          break;
        case 'naaim':
          naaimResult = result;
          break;
        case 'aaii':
          aaiiResult = result;
          break;
        case 'marketstats':
          marketStatsResult = result;
          break;
      }
    });

    const marketStats = marketStatsResult.rows[0];    const advanceDeclineRatio = marketStats.advancing_stocks / Math.max(marketStats.declining_stocks, 1);

    // Map backend fields to frontend expectations for sentiment_indicators
    function mapFearGreed(row) {
      if (!row) return null;
      return {
        value: row.index_value,
        value_text: row.rating,
        timestamp: row.date
      };
    }
    function mapNaaim(row) {
      if (!row) return null;
      return {
        average: row.mean_exposure,
        bullish_8100: row.bullish_exposure,
        bearish: row.bearish_exposure,
        week_ending: row.date
      };
    }
    function mapAaii(row) {
      if (!row) return null;
      return {
        bullish: row.bullish,
        neutral: row.neutral,
        bearish: row.bearish,
        week_ending: row.date
      };
    }
    // --- Economic indicators: REMOVE from overview ---
    // let economicIndicators = [];
    // try {
    //   const days = 90; // Default period for overview
    //   // Hardcoded metadata for economic indicators (reuse from /economic)
    //   const indicatorMeta = {
    //     CPI: { name: 'Consumer Price Index', unit: '%', category: 'Inflation' },
    //     CPILFESL: { name: 'Core CPI', unit: '%', category: 'Inflation' },
    //     PPIACO: { name: 'Producer Price Index', unit: '%', category: 'Inflation' },
    //     CUSR0000SA0L1E: { name: 'Core PPI', unit: '%', category: 'Inflation' },
    //     UNRATE: { name: 'Unemployment Rate', unit: '%', category: 'Labor' },
    //     NFP: { name: 'Nonfarm Payrolls', unit: 'K', category: 'Labor' },
    //     GDP: { name: 'Gross Domestic Product', unit: 'B', category: 'Growth' },
    //     GDPC1: { name: 'Real GDP', unit: 'B', category: 'Growth' },
    //     FEDFUNDS: { name: 'Fed Funds Rate', unit: '%', category: 'Rates' },
    //     DGS10: { name: '10Y Treasury Yield', unit: '%', category: 'Rates' },
    //     PCE: { name: 'Personal Consumption Expenditures', unit: '%', category: 'Inflation' },
    //     CP: { name: 'Consumer Confidence', unit: '', category: 'Sentiment' },
    //     RETAIL: { name: 'Retail Sales', unit: '%', category: 'Consumption' },
    //     INDPRO: { name: 'Industrial Production', unit: '%', category: 'Production' },
    //     ISM: { name: 'ISM Manufacturing', unit: '', category: 'Manufacturing' },
    //     ISMNONMAN: { name: 'ISM Services', unit: '', category: 'Services' },
    //     DURABLE: { name: 'Durable Goods Orders', unit: '%', category: 'Manufacturing' },
    //     HOUSING: { name: 'Housing Starts', unit: 'K', category: 'Housing' },
    //     PERMITS: { name: 'Building Permits', unit: 'K', category: 'Housing' },
    //     M2: { name: 'M2 Money Supply', unit: 'B', category: 'Money Supply' },
    //     T10Y2Y: { name: '10Y-2Y Treasury Spread', unit: '%', category: 'Rates' },
    //     T10Y3M: { name: '10Y-3M Treasury Spread', unit: '%', category: 'Rates' },
    //     VIXCLS: { name: 'VIX Volatility Index', unit: '', category: 'Volatility' },
    //     SP500: { name: 'S&P 500 Index', unit: '', category: 'Equities' },
    //     DJIA: { name: 'Dow Jones Industrial Average', unit: '', category: 'Equities' },
    //     NASDAQ: { name: 'NASDAQ Composite', unit: '', category: 'Equities' },
    //     CRB: { name: 'CRB Commodity Index', unit: '', category: 'Commodities' },
    //     OIL: { name: 'Crude Oil Price', unit: '$', category: 'Commodities' },
    //     GOLD: { name: 'Gold Price', unit: '$', category: 'Commodities' },
    //     SILVER: { name: 'Silver Price', unit: '$', category: 'Commodities' },
    //     COPPER: { name: 'Copper Price', unit: '$', category: 'Commodities' },
    //   };
    //   const econQuery = `
    //     SELECT 
    //       series_id,
    //       date,
    //       value
    //     FROM economic_data 
    //     WHERE date >= CURRENT_DATE - INTERVAL '${days} days'
    //     ORDER BY date DESC, series_id ASC
    //     LIMIT 100
    //   `;
    //   const econResult = await query(econQuery);
    //   // Group by series_id for previous value lookup
    //   const grouped = {};
    //   for (const row of econResult.rows) {
    //     if (!grouped[row.series_id]) grouped[row.series_id] = [];
    //     grouped[row.series_id].push(row);
    //   }
    //   // Build enriched indicators
    //   for (const [series_id, rows] of Object.entries(grouped)) {
    //     const meta = indicatorMeta[series_id] || { name: series_id, unit: '', category: 'Other' };
    //     const current = rows[0];
    //     const previous = rows[1];
    //     let change_percent = null;
    //     if (current && previous && previous.value != null && previous.value !== 0) {
    //       change_percent = ((current.value - previous.value) / Math.abs(previous.value)) * 100;
    //     }
    //     economicIndicators.push({
    //       series_id,
    //       name: meta.name,
    //       unit: meta.unit,
    //       category: meta.category,
    //       value: current.value,
    //       previous_value: previous ? previous.value : null,
    //       change_percent,
    //       timestamp: current.date
    //     });
    //   }
    // } catch (econError) {
    //   console.error('Error fetching economic indicators for overview:', econError);
    //   economicIndicators = [];
    // }
    // --- Wrap the response in a 'data' property for frontend compatibility ---
    res.json({
      data: {
        sentiment_indicators: {
          fear_greed: mapFearGreed(fearGreedResult.rows[0]),
          naaim: mapNaaim(naaimResult.rows[0]),
          aaii: mapAaii(aaiiResult.rows[0])
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
        // economic_indicators: economicIndicators, // REMOVED from overview
        data_availability: {
          tables_checked: requiredTables,
          tables_available: Object.keys(tableExists).filter(table => tableExists[table]),
          tables_missing: Object.keys(tableExists).filter(table => !tableExists[table])
        },
        timestamp: new Date().toISOString()
      }
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
    
    // Get current values first
    const currentFearGreedQuery = `
      SELECT index_value, rating, date
      FROM fear_greed_index 
      ORDER BY date DESC 
      LIMIT 1
    `;

    const currentNaaimQuery = `
      SELECT naaim_number_mean as mean_exposure, bearish as bearish_exposure, bullish as bullish_exposure, date
      FROM naaim 
      ORDER BY date DESC 
      LIMIT 1
    `;

    const currentAaiiQuery = `
      SELECT bullish, neutral, bearish, date
      FROM aaii_sentiment 
      ORDER BY date DESC 
      LIMIT 1
    `;

    // Get historical data
    const fearGreedQuery = `
      SELECT index_value, rating, date
      FROM fear_greed_index 
      WHERE date >= NOW() - INTERVAL '${days} days'
      ORDER BY date DESC
      LIMIT 100
    `;

    const naaimQuery = `
      SELECT naaim_number_mean as mean_exposure, bearish as bearish_exposure, bullish as bullish_exposure, date
      FROM naaim 
      WHERE date >= NOW() - INTERVAL '${days} days'
      ORDER BY date DESC
      LIMIT 100
    `;

    const aaiiQuery = `
      SELECT bullish, neutral, bearish, date
      FROM aaii_sentiment 
      WHERE date >= NOW() - INTERVAL '${days} days'
      ORDER BY date DESC
      LIMIT 100
    `;

    const [
      currentFearGreed, currentNaaim, currentAaii,
      fearGreedHistory, naaimHistory, aaiiHistory
    ] = await Promise.all([
      query(currentFearGreedQuery),
      query(currentNaaimQuery),
      query(currentAaiiQuery),
      query(fearGreedQuery),
      query(naaimQuery),
      query(aaiiQuery)
    ]);

    res.json({
      period_days: days,
      fear_greed: {
        current: currentFearGreed.rows[0] || null,
        history: fearGreedHistory.rows || []
      },
      naaim: {
        current: currentNaaim.rows[0] || null,
        history: naaimHistory.rows || []
      },
      aaii: {
        current: currentAaii.rows[0] || null,
        history: aaiiHistory.rows || []
      },
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

    // Hardcoded metadata for economic indicators
    const indicatorMeta = {
      CPI: { name: 'Consumer Price Index', unit: '%', category: 'Inflation', description: 'Measures changes in the price level of a weighted average market basket of consumer goods and services' },
      CPILFESL: { name: 'Core CPI', unit: '%', category: 'Inflation', description: 'Consumer Price Index excluding food and energy' },
      PPIACO: { name: 'Producer Price Index', unit: '%', category: 'Inflation', description: 'Measures average changes in prices received by domestic producers' },
      CUSR0000SA0L1E: { name: 'Core PPI', unit: '%', category: 'Inflation', description: 'Producer Price Index excluding food and energy' },
      UNRATE: { name: 'Unemployment Rate', unit: '%', category: 'Labor', description: 'Percentage of the labor force that is unemployed' },
      NFP: { name: 'Nonfarm Payrolls', unit: 'K', category: 'Labor', description: 'Total number of paid U.S. workers excluding farm workers' },
      GDP: { name: 'Gross Domestic Product', unit: 'B', category: 'Growth', description: 'Total monetary value of all finished goods and services produced within a country' },
      GDPC1: { name: 'Real GDP', unit: 'B', category: 'Growth', description: 'GDP adjusted for inflation' },
      FEDFUNDS: { name: 'Fed Funds Rate', unit: '%', category: 'Rates', description: 'Target interest rate set by the Federal Reserve' },
      DGS10: { name: '10Y Treasury Yield', unit: '%', category: 'Rates', description: 'Yield on 10-year Treasury notes' },
      PCE: { name: 'Personal Consumption Expenditures', unit: '%', category: 'Inflation', description: 'Primary measure of consumer spending on goods and services' },
      CP: { name: 'Consumer Confidence', unit: '', category: 'Sentiment', description: 'Measure of consumer optimism about the economy' },
      RETAIL: { name: 'Retail Sales', unit: '%', category: 'Consumption', description: 'Total receipts at stores that sell merchandise and related services' },
      INDPRO: { name: 'Industrial Production', unit: '%', category: 'Production', description: 'Measures real output of manufacturing, mining, and utilities' },
      ISM: { name: 'ISM Manufacturing', unit: '', category: 'Manufacturing', description: 'Institute for Supply Management Manufacturing Index' },
      ISMNONMAN: { name: 'ISM Services', unit: '', category: 'Services', description: 'Institute for Supply Management Services Index' },
      DURABLE: { name: 'Durable Goods Orders', unit: '%', category: 'Manufacturing', description: 'Orders for goods expected to last more than three years' },
      HOUSING: { name: 'Housing Starts', unit: 'K', category: 'Housing', description: 'Number of new residential construction projects' },
      PERMITS: { name: 'Building Permits', unit: 'K', category: 'Housing', description: 'Number of building permits issued for new construction' },
      M2: { name: 'M2 Money Supply', unit: 'B', category: 'Money Supply', description: 'Measure of money supply including cash and checking deposits' },
      T10Y2Y: { name: '10Y-2Y Treasury Spread', unit: '%', category: 'Rates', description: 'Difference between 10-year and 2-year Treasury yields' },
      T10Y3M: { name: '10Y-3M Treasury Spread', unit: '%', category: 'Rates', description: 'Difference between 10-year and 3-month Treasury yields' },
      VIXCLS: { name: 'VIX Volatility Index', unit: '', category: 'Volatility', description: 'Market volatility index based on S&P 500 options' },
      SP500: { name: 'S&P 500 Index', unit: '', category: 'Equities', description: 'Market-capitalization-weighted index of 500 large-cap stocks' },
      DJIA: { name: 'Dow Jones Industrial Average', unit: '', category: 'Equities', description: 'Price-weighted index of 30 large-cap stocks' },
      NASDAQ: { name: 'NASDAQ Composite', unit: '', category: 'Equities', description: 'Market-capitalization-weighted index of NASDAQ-listed stocks' },
      CRB: { name: 'CRB Commodity Index', unit: '', category: 'Commodities', description: 'Commodity Research Bureau Index tracking commodity prices' },
      OIL: { name: 'Crude Oil Price', unit: '$', category: 'Commodities', description: 'Price of crude oil per barrel' },
      GOLD: { name: 'Gold Price', unit: '$', category: 'Commodities', description: 'Price of gold per ounce' },
      SILVER: { name: 'Silver Price', unit: '$', category: 'Commodities', description: 'Price of silver per ounce' },
      COPPER: { name: 'Copper Price', unit: '$', category: 'Commodities', description: 'Price of copper per pound' },
    };

    // Check if economic_data table exists
    const tableCheck = await query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'economic_data'
      );
    `);

    if (!tableCheck.rows[0].exists) {
      console.log('Economic data table does not exist, returning empty data');
      return res.json({
        period_days: days,
        data: [],
        total_data_points: 0,
        timestamp: new Date().toISOString(),
        message: 'Economic data table not available'
      });
    }

    // Query the latest 2 records per series_id for change calculation
    const econQuery = `
      SELECT 
        series_id,
        date,
        value
      FROM economic_data 
      WHERE date >= CURRENT_DATE - INTERVAL '${days} days'
      ORDER BY date DESC, series_id ASC
      LIMIT 200
    `;

    const result = await query(econQuery);
    console.log(`Found ${result.rows.length} economic data points`);

    // Group by series_id for previous value lookup
    const grouped = {};
    for (const row of result.rows) {
      if (!grouped[row.series_id]) grouped[row.series_id] = [];
      grouped[row.series_id].push(row);
    }

    // Build enriched indicators
    const indicators = [];
    for (const [series_id, rows] of Object.entries(grouped)) {
      const meta = indicatorMeta[series_id] || { 
        name: series_id, 
        unit: '', 
        category: 'Other',
        description: `Economic indicator: ${series_id}`
      };
      const current = rows[0];
      const previous = rows[1];
      
      let change_percent = null;
      if (current && previous && previous.value != null && previous.value !== 0) {
        change_percent = ((current.value - previous.value) / Math.abs(previous.value)) * 100;
      }

      indicators.push({
        series_id,
        name: meta.name,
        unit: meta.unit,
        category: meta.category,
        description: meta.description,
        value: current.value,
        previous_value: previous ? previous.value : null,
        change_percent,
        timestamp: current.date
      });
    }

    console.log(`Processed ${indicators.length} economic indicators`);

    res.json({
      period_days: days,
      data: indicators,
      total_data_points: result.rows.length,
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

// Get NAAIM data (for DataValidation page)
router.get('/naaim', async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 50, 100);
    console.log(`NAAIM data endpoint called with limit: ${limit}`);
    
    const naaimQuery = `
      SELECT naaim_number_mean, bearish, bullish, date
      FROM naaim 
      ORDER BY date DESC 
      LIMIT $1
    `;
    
    const result = await query(naaimQuery, [limit]);
    
    res.json({
      data: result.rows,
      count: result.rows.length,
      limit: limit,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error fetching NAAIM data:', error);
    res.status(500).json({ 
      error: 'Failed to fetch NAAIM data',
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get fear & greed data (for DataValidation page)
router.get('/fear-greed', async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 50, 100);
    console.log(`Fear & Greed data endpoint called with limit: ${limit}`);
    
    const fearGreedQuery = `
      SELECT index_value, rating, date
      FROM fear_greed_index 
      ORDER BY date DESC 
      LIMIT $1
    `;
    
    const result = await query(fearGreedQuery, [limit]);
    
    res.json({
      data: result.rows,
      count: result.rows.length,
      limit: limit,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error fetching fear & greed data:', error);
    res.status(500).json({ 
      error: 'Failed to fetch fear & greed data',
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get economic data (for DataValidation page)
router.get('/economic', async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 50, 100);
    console.log(`Economic data endpoint called with limit: ${limit}`);
    
    const economicQuery = `
      SELECT series_id, date, value
      FROM economic_data 
      ORDER BY date DESC, series_id ASC
      LIMIT $1
    `;
    
    const result = await query(economicQuery, [limit]);
    
    res.json({
      data: result.rows,
      count: result.rows.length,
      limit: limit,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error fetching economic data:', error);
    res.status(500).json({ 
      error: 'Failed to fetch economic data',
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

module.exports = router;
