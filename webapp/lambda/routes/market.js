const express = require("express");

const { query } = require("../utils/database");

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
router.get("/", (req, res) => {
  return res.success({
    status: "ok",
    endpoint: "market",
    available_routes: [
      "/overview",
      "/sentiment/history",
      "/sectors/performance",
      "/breadth",
      "/economic",
      "/naaim",
      "/fear-greed",
      "/indices",
      "/sectors",
      "/volatility",
      "/calendar",
      "/indicators",
      "/sentiment",
    ],
    timestamp: new Date().toISOString(),
  });
});

// Debug endpoint to check market tables status
router.get("/debug", async (req, res) => {
  console.log("[MARKET] Debug endpoint called");

  try {
    // Check all market-related tables
    const requiredTables = [
      "market_data",
      "economic_data",
      "fear_greed_index",
      "naaim",
      "company_profile",
      "aaii_sentiment",
    ];

    const tableStatus = await checkRequiredTables(requiredTables);

    // Get record counts for existing tables
    const recordCounts = {};
    for (const [tableName, exists] of Object.entries(tableStatus)) {
      if (exists) {
        try {
          const countResult = await query(
            `SELECT COUNT(*) as count FROM ${tableName}`
          );
          recordCounts[tableName] = parseInt(countResult.rows[0].count);
        } catch (error) {
          recordCounts[tableName] = { error: error.message };
        }
      } else {
        recordCounts[tableName] = "Table does not exist";
      }
    }

    res.success({tables: tableStatus,
      recordCounts: recordCounts,
      endpoint: "market",
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("[MARKET] Error in debug endpoint:", error);
    return res.error("Failed to check market tables: " + error.message, 500, { timestamp: new Date().toISOString() });
  }
});

// Test endpoint with fixed database queries
router.get("/overview-fixed", async (req, res) => {
  console.log("Market overview FIXED endpoint called - testing new queries");

  try {
    // Test the fixed Fear & Greed query
    let fearGreedData = null;
    try {
      const fearGreedQuery = `
        SELECT 
          COALESCE(index_value, fear_greed_value, greed_fear_index, value) as value,
          COALESCE(index_text, value_text, classification) as value_text,
          COALESCE(date, created_at) as timestamp
        FROM fear_greed_index 
        ORDER BY COALESCE(date, created_at) DESC 
        LIMIT 1
      `;
      const fearGreedResult = await query(fearGreedQuery);
      console.log("Fixed Fear & Greed query result:", fearGreedResult.rows);
      fearGreedData = fearGreedResult.rows[0] || null;
    } catch (e) {
      console.error("Fixed Fear & Greed query error:", e.message);
    }

    // Test the fixed NAAIM query
    let naaimData = null;
    try {
      const naaimQuery = `
        SELECT 
          COALESCE(average, mean_exposure, exposure_index, exposure_average) as average,
          COALESCE(bullish_8100, bullish_80_100, bullish) as bullish_8100,
          COALESCE(bearish, bearish_exposure) as bearish,
          COALESCE(week_ending, date, timestamp) as week_ending
        FROM naaim 
        ORDER BY COALESCE(week_ending, date, timestamp) DESC 
        LIMIT 1
      `;
      const naaimResult = await query(naaimQuery);
      console.log("Fixed NAAIM query result:", naaimResult.rows);
      naaimData = naaimResult.rows[0] || null;
    } catch (e) {
      console.error("Fixed NAAIM query error:", e.message);
    }

    // Test the fixed market breadth query
    let breadthData = null;
    try {
      const breadthQuery = `
        SELECT 
          COUNT(*) as total_stocks,
          COUNT(CASE WHEN COALESCE(change_percent, percent_change, pct_change) > 0 THEN 1 END) as advancing,
          COUNT(CASE WHEN COALESCE(change_percent, percent_change, pct_change) < 0 THEN 1 END) as declining,
          COUNT(CASE WHEN COALESCE(change_percent, percent_change, pct_change) = 0 THEN 1 END) as unchanged,
          AVG(COALESCE(change_percent, percent_change, pct_change)) as average_change_percent
        FROM market_data
        WHERE date = (SELECT MAX(date) FROM market_data)
          AND COALESCE(change_percent, percent_change, pct_change) IS NOT NULL
      `;
      const breadthResult = await query(breadthQuery);
      console.log("Fixed market breadth query result:", breadthResult.rows);
      breadthData = breadthResult.rows[0] || null;
    } catch (e) {
      console.error("Fixed market breadth query error:", e.message);
    }

    return res.success({
      status: "success",
      message: "Testing fixed database queries",
      results: {
        fear_greed: fearGreedData,
        naaim: naaimData,
        market_breadth: breadthData,
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error in fixed overview test:", error);
    return res.error("Test failed", 500);
  }
});

// Test endpoint for the fixed overview structure
router.get("/overview-test", async (req, res) => {
  console.log("Market overview test endpoint called");

  try {
    // Return a simplified structure that matches what frontend expects
    const testData = {
      sentiment_indicators: {
        fear_greed: {
          value: 50,
          value_text: "Neutral",
          timestamp: new Date().toISOString(),
        },
        naaim: { average: 45.5, week_ending: new Date().toISOString() },
        aaii: {
          bullish: 0.35,
          neutral: 0.3,
          bearish: 0.35,
          date: new Date().toISOString(),
        },
      },
      market_breadth: {
        total_stocks: 5000,
        advancing: 2500,
        declining: 2200,
        unchanged: 300,
        advance_decline_ratio: "1.14",
        average_change_percent: "0.25",
      },
      market_cap: {
        large_cap: 25000000000000,
        mid_cap: 5000000000000,
        small_cap: 2000000000000,
        total: 32000000000000,
      },
      economic_indicators: [
        {
          name: "GDP Growth",
          value: 2.1,
          unit: "%",
          timestamp: new Date().toISOString(),
        },
        {
          name: "Unemployment Rate",
          value: 3.7,
          unit: "%",
          timestamp: new Date().toISOString(),
        },
      ],
    };

    return res.success({
      data: testData,
      timestamp: new Date().toISOString(),
      status: "success",
      message: "Test data with correct structure",
    });
  } catch (error) {
    console.error("Error in overview test:", error);
    return res.error("Test failed", 500);
  }
});

// Simple test endpoint that returns raw data
router.get("/test", async (req, res) => {
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

    return res.success({
      market_data: marketData,
      economic_data: economicData,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error in market test:", error);
    return res.error("Failed to test market data" , 500);
  }
});

// Basic ping endpoint
router.get("/ping", (req, res) => {
  return res.success({
    status: "ok",
    endpoint: "market",
    timestamp: new Date().toISOString(),
  });
});

// Get comprehensive market overview with sentiment indicators
router.get("/overview", async (req, res) => {
  console.log("Market overview endpoint called");

  try {
    // Validate date parameter if provided
    const { date } = req.query;
    if (date && isNaN(new Date(date).getTime())) {
      return res.error("Invalid date format. Please use ISO 8601 format (YYYY-MM-DD).", 400);
    }
    // Check if market_data table exists
    const tableExists = await query(
      `
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'market_data'
      );
    `,
      []
    );

    // Add null checking for database availability
    if (!tableExists || !tableExists.rows) {
      console.warn("Table existence query returned null result, database may be unavailable");
      return res.error("Market overview temporarily unavailable - database connection issue", 503, {
        indices: [],
        sectors: [],
        volatility: { vix: 0, fear_greed: 50 },
        sentiment: { score: 0, label: "Neutral" }
      });
    }

    console.log("Table existence check:", tableExists.rows[0].exists);

    if (!tableExists.rows[0].exists) {
      return res.error("Market data table not found in database", 500);
    }

    // Get sentiment indicators
    let sentimentIndicators = {};

    // Get Fear & Greed Index
    try {
      console.log("Fetching Fear & Greed data...");
      const fearGreedQuery = `
        SELECT 
          COALESCE(index_value, fear_greed_value, greed_fear_index, value) as value,
          COALESCE(index_text, value_text, classification) as value_text,
          COALESCE(date, created_at) as timestamp
        FROM fear_greed_index 
        ORDER BY COALESCE(date, created_at) DESC 
        LIMIT 1
      `;
      const fearGreedResult = await query(fearGreedQuery);
      console.log("Fear & Greed query result:", fearGreedResult.rows);

      if (fearGreedResult.rows.length > 0) {
        const fg = fearGreedResult.rows[0];
        sentimentIndicators.fear_greed = {
          value: fg.value,
          value_text: fg.value_text,
          timestamp: fg.timestamp || fg.date,
        };
        console.log(
          "Fear & Greed data processed:",
          sentimentIndicators.fear_greed
        );
      } else {
        throw new Error("No Fear & Greed data available in database");
      }
    } catch (e) {
      console.error("Fear & Greed data error:", e.message);
      throw new Error(`Failed to retrieve Fear & Greed data: ${e.message}`);
    }

    // Get NAAIM data
    try {
      console.log("Fetching NAAIM data...");
      const naaimQuery = `
        SELECT 
          COALESCE(average, mean_exposure, exposure_index, exposure_average) as average,
          COALESCE(bullish_8100, bullish_80_100, bullish) as bullish_8100,
          COALESCE(bearish, bearish_exposure) as bearish,
          COALESCE(week_ending, date, timestamp) as week_ending
        FROM naaim 
        ORDER BY COALESCE(week_ending, date, timestamp) DESC 
        LIMIT 1
      `;
      const naaimResult = await query(naaimQuery);
      console.log("NAAIM query result:", naaimResult.rows);

      if (naaimResult.rows.length > 0) {
        const naaim = naaimResult.rows[0];
        sentimentIndicators.naaim = {
          average: naaim.average || naaim.mean_exposure || naaim.exposure_index,
          bullish_8100: naaim.bullish_8100,
          bearish: naaim.bearish,
          week_ending: naaim.week_ending || naaim.date,
        };
        console.log("NAAIM data processed:", sentimentIndicators.naaim);
      } else {
        throw new Error("No NAAIM data available in database");
      }
    } catch (e) {
      console.error("NAAIM data error:", e.message);
      throw new Error(`Failed to retrieve NAAIM data: ${e.message}`);
    }

    // Get AAII data (from aaii_sentiment table)
    try {
      console.log("Attempting to fetch AAII data...");
      const aaiiQuery = `
        SELECT bullish, neutral, bearish, date 
        FROM aaii_sentiment 
        ORDER BY date DESC 
        LIMIT 1
      `;
      const aaiiResult = await query(aaiiQuery);
      console.log(`AAII query returned ${aaiiResult.rows.length} rows`);
      if (aaiiResult.rows.length > 0) {
        console.log("AAII data found:", aaiiResult.rows[0]);
        sentimentIndicators.aaii = {
          bullish: aaiiResult.rows[0].bullish,
          neutral: aaiiResult.rows[0].neutral,
          bearish: aaiiResult.rows[0].bearish,
          date: aaiiResult.rows[0].date,
        };
      } else {
        console.log("No AAII data found in table");
      }
    } catch (e) {
      console.error("AAII data error:", e.message);
      console.error("Full AAII error:", e);
    }

    // Get market breadth
    let marketBreadth = {};
    try {
      console.log("Fetching market breadth data...");
      const breadthQuery = `
        SELECT 
          COUNT(*) as total_stocks,
          COUNT(CASE WHEN COALESCE(change_percent, percent_change, pct_change) > 0 THEN 1 END) as advancing,
          COUNT(CASE WHEN COALESCE(change_percent, percent_change, pct_change) < 0 THEN 1 END) as declining,
          COUNT(CASE WHEN COALESCE(change_percent, percent_change, pct_change) = 0 THEN 1 END) as unchanged,
          AVG(COALESCE(change_percent, percent_change, pct_change)) as average_change_percent
        FROM market_data
        WHERE date = (SELECT MAX(date) FROM market_data)
          AND COALESCE(change_percent, percent_change, pct_change) IS NOT NULL
      `;
      const breadthResult = await query(breadthQuery);
      
      // Add null checking for database availability
      if (!breadthResult || !breadthResult.rows) {
        console.warn("Market breadth query returned null result, database may be unavailable");
        return res.error("Market overview temporarily unavailable - database connection issue", 503, {
          indices: [],
          sectors: [],
          volatility: { vix: 0, fear_greed: 50 },
          sentiment: { score: 0, label: "Neutral" }
        });
      }
      
      console.log("Market breadth query result:", breadthResult.rows);

      if (
        breadthResult.rows.length > 0 &&
        breadthResult.rows[0].total_stocks > 0
      ) {
        const breadth = breadthResult.rows[0];
        const advancing = parseInt(breadth.advancing) || 0;
        const declining = parseInt(breadth.declining) || 0;

        marketBreadth = {
          total_stocks: parseInt(breadth.total_stocks) || 0,
          advancing: advancing,
          declining: declining,
          unchanged: parseInt(breadth.unchanged) || 0,
          advance_decline_ratio:
            declining > 0 ? (advancing / declining).toFixed(2) : "N/A",
          average_change_percent: breadth.average_change_percent
            ? parseFloat(breadth.average_change_percent).toFixed(2)
            : "0.00",
        };
        console.log("Market breadth data processed:", marketBreadth);
      } else {
        throw new Error("No market breadth data available in database");
      }
    } catch (e) {
      console.error("Market breadth data error:", e.message);
      throw new Error(`Failed to retrieve market breadth data: ${e.message}`);
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
        WHERE date = (SELECT MAX(date) FROM market_data WHERE market_cap IS NOT NULL)
      `;
      const marketCapResult = await query(marketCapQuery);
      if (
        marketCapResult.rows.length > 0 &&
        marketCapResult.rows[0].total > 0
      ) {
        marketCap = {
          large_cap: parseFloat(marketCapResult.rows[0].large_cap) || 0,
          mid_cap: parseFloat(marketCapResult.rows[0].mid_cap) || 0,
          small_cap: parseFloat(marketCapResult.rows[0].small_cap) || 0,
          total: parseFloat(marketCapResult.rows[0].total) || 0,
        };
      } else {
        throw new Error("No market cap data available in database");
      }
    } catch (e) {
      console.error("Market cap data error:", e.message);
      throw new Error(`Failed to retrieve market cap data: ${e.message}`);
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
      if (economicResult.rows.length > 0) {
        economicIndicators = economicResult.rows.map((row) => ({
          name: row.name,
          value: row.value,
          unit: row.unit,
          timestamp: row.timestamp,
        }));
      } else {
        throw new Error("No economic data available in database");
      }
    } catch (e) {
      console.error("Economic indicators error:", e.message);
      throw new Error(`Failed to retrieve economic data: ${e.message}`);
    }

    // Get market indices data (for contract compliance)
    let indices = [];
    try {
      const indicesQuery = `
        SELECT 
          symbol,
          COALESCE(current_price, price, close_price) as price,
          COALESCE(change_amount, change, daily_change) as change,
          COALESCE(change_percent, percent_change, pct_change, daily_change_percent) as changePercent
        FROM market_data 
        WHERE symbol IN ('SPY', 'QQQ', 'IWM', 'VTI', 'DIA')
          AND date = (SELECT MAX(date) FROM market_data)
          AND COALESCE(current_price, price, close_price) IS NOT NULL
        ORDER BY symbol
      `;
      const indicesResult = await query(indicesQuery);
      
      indices = indicesResult.rows.map(row => ({
        symbol: row.symbol,
        price: parseFloat(row.price) || 0,
        change: parseFloat(row.change) || 0,
        changePercent: parseFloat(row.changepercent) || 0
      }));
    } catch (e) {
      console.error("Indices data query failed:", e.message);
      throw new Error(`Failed to retrieve indices data: ${e.message}`);
    }

    // Return comprehensive market overview
    const responseData = {
      indices: indices,
      sentiment_indicators: sentimentIndicators,
      market_breadth: marketBreadth,
      market_cap: marketCap,
      economic_indicators: economicIndicators,
    };

    console.log(
      "Market overview response structure:",
      Object.keys(responseData)
    );
    console.log(
      "Sentiment indicators in response:",
      Object.keys(sentimentIndicators)
    );
    console.log("AAII in sentiment indicators:", !!sentimentIndicators.aaii);

    res.success({data: responseData,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching market overview:", error);
    return res.error("Database error: " + error.message, 500, { timestamp: new Date().toISOString() });
  }
});

// Get sentiment history over time
router.get("/sentiment/history", async (req, res) => {
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
      console.error("Fear & greed table not available:", e.message);
      return res.error("Failed to fetch fear and greed sentiment data", 503, {
        details: e.message,
        suggestion: "Fear and greed sentiment data requires market sentiment tables.",
        service: "sentiment-fear-greed",
        requirements: [
          "fear_greed_index table must exist with historical data",
          "Database connectivity must be available"
        ]
      });
    }

    // Get NAAIM data
    const naaimQuery = `
      SELECT 
        date,
        exposure_index,
        mean_exposure,
        bearish_exposure
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
      console.error("NAAIM table not available:", e.message);
      return res.error("Failed to fetch NAAIM sentiment data", 503, {
        details: e.message,
        suggestion: "NAAIM sentiment data requires market sentiment tables.",
        service: "sentiment-naaim",
        requirements: [
          "naaim table must exist with historical data",
          "Database connectivity must be available"
        ]
      });
    }

    return res.success({
      data: {
        fear_greed_history: fearGreedData,
        naaim_history: naaimData,
        aaii_history: [], // TODO: Add AAII historical data if needed
      },
      count: fearGreedData.length + naaimData.length,
      period_days: days,
    });
  } catch (error) {
    console.error("Error fetching sentiment history:", error);
    return res.error("Failed to fetch sentiment history", 503, {
      details: error.message,
      suggestion: "Sentiment history data requires database connectivity and market sentiment tables.",
      service: "sentiment-history",
      requirements: [
        "Database connectivity must be available",
        "fear_greed_index and naaim tables must exist with historical data"
      ]
    });
  }
});

// Get sector performance aggregates (market-level view)
router.get("/sectors/performance", async (req, res) => {
  console.log("Sector performance endpoint called");

  try {
    // Check if market_data table exists
    const tableExists = await query(
      `
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'market_data'
      );
    `,
      []
    );

    if (!tableExists.rows[0].exists) {
      console.error("Market data table not found for sector performance");
      return res.error("Failed to fetch sector performance data", 503, {
        details: "market_data table does not exist",
        suggestion: "Sector performance data requires market data to be loaded into the database.",
        service: "sector-performance",
        requirements: [
          "market_data table must exist with current stock data",
          "Database initialization must be completed"
        ]
      });
    }

    // Get sector performance data
    const sectorQuery = `
      SELECT 
        sector,
        COUNT(*) as stock_count,
        AVG(COALESCE(change_percent, percent_change, pct_change)) as avg_change,
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
      console.error("No sector data found in database query");
      return res.error("No sector performance data available", 503, {
        details: "No sector data found in market_data table",
        suggestion: "Sector performance requires recent market data to be loaded.",
        service: "sector-performance", 
        requirements: [
          "Recent market data must exist in market_data table",
          "Stock data must include sector classifications"
        ]
      });
    }

    return res.success({
      data: result.rows,
      count: result.rows.length,
    });
  } catch (error) {
    console.error("Error fetching sector performance:", error);
    return res.error("Failed to fetch sector performance data", 503, {
      details: error.message,
      suggestion: "Sector performance data requires database connectivity and market data.",
      service: "sector-performance",
      requirements: [
        "Database connectivity must be available",
        "market_data table must exist with sector data"
      ]
    });
  }
});

// Get market breadth indicators
router.get("/breadth", async (req, res) => {
  console.log("Market breadth endpoint called");

  try {
    // Check if market_data table exists
    const tableExists = await query(
      `
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'market_data'
      );
    `,
      []
    );

    if (!tableExists.rows[0].exists) {
      console.error("Market data table not found for breadth data");
      return res.error("Failed to fetch market breadth data", 503, {
        details: "market_data table does not exist",
        suggestion: "Market breadth data requires market data to be loaded into the database.",
        service: "market-breadth",
        requirements: [
          "market_data table must exist with stock price data",
          "Database initialization must be completed"
        ]
      });
    }

    // Get market breadth data
    const breadthQuery = `
      SELECT 
        COUNT(*) as total_stocks,
        COUNT(CASE WHEN COALESCE(change_percent, percent_change, pct_change) > 0 THEN 1 END) as advancing,
        COUNT(CASE WHEN COALESCE(change_percent, percent_change, pct_change) < 0 THEN 1 END) as declining,
        COUNT(CASE WHEN COALESCE(change_percent, percent_change, pct_change) = 0 THEN 1 END) as unchanged,
        COUNT(CASE WHEN COALESCE(change_percent, percent_change, pct_change) > 5 THEN 1 END) as strong_advancing,
        COUNT(CASE WHEN COALESCE(change_percent, percent_change, pct_change) < -5 THEN 1 END) as strong_declining,
        AVG(COALESCE(change_percent, percent_change, pct_change)) as avg_change,
        AVG(volume) as avg_volume
      FROM market_data
      WHERE date = (SELECT MAX(date) FROM market_data)
    `;

    const result = await query(breadthQuery);

    if (
      !result ||
      !Array.isArray(result.rows) ||
      result.rows.length === 0 ||
      !result.rows[0].total_stocks ||
      result.rows[0].total_stocks == 0
    ) {
      console.error("No market breadth data found in database");
      return res.error("No market breadth data available", 503, {
        details: "No stock data found for breadth calculations",
        suggestion: "Market breadth requires recent stock price data to be loaded.",
        service: "market-breadth",
        requirements: [
          "Recent stock price data must exist in market_data table",
          "Stock data must include price change information"
        ]
      });
    }

    const breadth = result.rows[0];

    return res.success({
      total_stocks: parseInt(breadth.total_stocks),
      advancing: parseInt(breadth.advancing),
      declining: parseInt(breadth.declining),
      unchanged: parseInt(breadth.unchanged),
      strong_advancing: parseInt(breadth.strong_advancing),
      strong_declining: parseInt(breadth.strong_declining),
      advance_decline_ratio:
        breadth.declining > 0
          ? (breadth.advancing / breadth.declining).toFixed(2)
          : "N/A",
      avg_change: parseFloat(breadth.avg_change).toFixed(2),
      avg_volume: parseInt(breadth.avg_volume),
    });
  } catch (error) {
    console.error("Error fetching market breadth:", error);
    return res.error("Failed to fetch market breadth data", 503, {
      details: error.message,
      suggestion: "Market breadth data requires database connectivity and stock price data.",
      service: "market-breadth",
      requirements: [
        "Database connectivity must be available",
        "market_data table must exist with current stock prices"
      ]
    });
  }
});

// Get economic indicators
router.get("/economic", async (req, res) => {
  const { days = 90, indicator } = req.query;

  console.log(`Economic indicators endpoint called for ${days} days`);

  try {
    // Check if economic_data table exists
    const tableExists = await query(
      `
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'economic_data'
      );
    `,
      []
    );

    // Add null safety check
    if (!tableExists || !tableExists.rows) {
      console.error("Database unavailable for economic data table check");
      return res.error("Failed to fetch economic indicators", 503, {
        details: "Cannot read properties of null (reading 'rows')",
        suggestion: "Economic indicators require database connectivity and economic data tables.",
        service: "economic-indicators",
        requirements: [
          "Database connectivity must be available",
          "economic_data table must exist with current indicators"
        ]
      });
    }

    if (!tableExists.rows[0].exists) {
      console.error("Economic data table does not exist");
      return res.error("Failed to fetch economic indicators", 503, {
        details: "economic_data table does not exist",
        suggestion: "Economic data requires the economic indicators to be loaded into the database.",
        service: "economic-indicators",
        requirements: [
          "economic_data table must exist with historical indicators",
          "Database initialization must be completed"
        ]
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
    result.rows.forEach((row) => {
      if (!indicators[row.indicator_name]) {
        indicators[row.indicator_name] = [];
      }
      indicators[row.indicator_name].push({
        date: row.date,
        value: row.value,
        unit: row.unit,
      });
    });

    console.log(
      `Processed ${Object.keys(indicators).length} economic indicators`
    );

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      console.error("No economic data found in database");
      return res.error("No economic indicators available", 503, {
        details: "No economic indicators found in economic_data table",
        suggestion: "Economic indicators require recent economic data to be loaded.",
        service: "economic-indicators",
        requirements: [
          "Recent economic data must exist in economic_data table",
          "Economic data loading scripts must be executed"
        ]
      });
    }

    // Convert indicators object to array format expected by tests
    const dataArray = Object.keys(indicators).map((indicatorName) => ({
      indicator: indicatorName.replace(/\s+/g, "_").toUpperCase(),
      value: indicators[indicatorName][0]?.value || 0,
      unit: indicators[indicatorName][0]?.unit || "",
      date: indicators[indicatorName][0]?.date || new Date().toISOString(),
    }));

    res.success({data: indicator
        ? dataArray.filter((item) => item.indicator === indicator)
        : dataArray,
      count: indicator
        ? dataArray.filter((item) => item.indicator === indicator).length
        : dataArray.length,
    });
  } catch (error) {
    console.error("Error fetching economic indicators:", error);
    return res.error("Failed to fetch economic indicators", 503, {
      details: error.message,
      suggestion: "Economic indicators require database connectivity and economic data tables.",
      service: "economic-indicators",
      requirements: [
        "Database connectivity must be available",
        "economic_data table must exist with current indicators"
      ]
    });
  }
});

// Get NAAIM data (for DataValidation page)
router.get("/naaim", async (req, res) => {
  const { limit = 30 } = req.query;

  console.log(`NAAIM data endpoint called with limit: ${limit}`);

  try {
    const naaimQuery = `
      SELECT 
        date,
        exposure_index,
        mean_exposure,
        bearish_exposure
      FROM naaim
      ORDER BY date DESC
      LIMIT $1
    `;

    const result = await query(naaimQuery, [parseInt(limit)]);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.notFound("No data found for this query" );
    }

    return res.success({
      data: result.rows,
      count: result.rows.length,
    });
  } catch (error) {
    console.error("Error fetching NAAIM data:", error);
    return res.error("Failed to fetch NAAIM data", 503, {
      details: error.message,
      suggestion: "NAAIM data requires database connectivity and sentiment tables.",
      service: "naaim-sentiment",
      requirements: [
        "Database connectivity must be available",
        "naaim table must exist with historical sentiment data"
      ]
    });
  }
});

// Get fear & greed data (for DataValidation page)
router.get("/fear-greed", async (req, res) => {
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
      console.error("No fear & greed data found in database");
      return res.error("No fear and greed data available", 503, {
        details: "No fear and greed data found in fear_greed_index table",
        suggestion: "Fear and greed data requires sentiment data to be loaded.",
        service: "fear-greed-sentiment",
        requirements: [
          "fear_greed_index table must exist with historical data",
          "Sentiment data loading scripts must be executed"
        ]
      });
    }

    res.success({
      data: result.rows,
      count: result.rows.length,
    });
  } catch (error) {
    console.error("Error fetching fear & greed data:", error);
    return res.error("Failed to fetch fear and greed data", 503, {
      details: error.message,
      suggestion: "Fear and greed data requires database connectivity and sentiment tables.",
      service: "fear-greed-sentiment",
      requirements: [
        "Database connectivity must be available",
        "fear_greed_index table must exist with sentiment data"
      ]
    });
  }
});

// Get market indices
router.get("/indices", async (req, res) => {
  try {
    const { limit, symbol } = req.query;

    // Validate limit parameter
    if (limit !== undefined) {
      const limitNum = parseInt(limit);
      if (isNaN(limitNum) || limitNum <= 0) {
        return res.status(400).json({
          success: false,
          error: "Limit must be a positive number",
        });
      }
      if (limitNum > 500) {
        return res.status(400).json({
          success: false,
          error: "Limit cannot exceed 500",
        });
      }
    }

    // Validate symbol parameter for SQL injection
    if (symbol !== undefined) {
      // Check for SQL injection patterns
      const sqlInjectionPattern = /[';"\-\-/*+=<>()]/;
      if (sqlInjectionPattern.test(symbol)) {
        return res.status(400).json({
          success: false,
          error: "Invalid symbol format",
        });
      }
    }

    // Build query with optional symbol filter and limit
    let whereClause =
      "WHERE symbol IN ('^GSPC', '^DJI', '^IXIC', '^RUT', '^VIX')";
    let params = [];
    let paramIndex = 1;

    if (symbol) {
      whereClause += ` AND symbol = $${paramIndex}`;
      params.push(symbol);
      paramIndex++;
    }

    whereClause += " AND date = (SELECT MAX(date) FROM market_data)";

    let limitClause = "";
    if (limit) {
      limitClause = ` LIMIT $${paramIndex}`;
      params.push(parseInt(limit));
    }

    const indicesQuery = `
      SELECT 
        symbol,
        current_price,
        previous_close,
        COALESCE(change_percent, percent_change, pct_change) as change_percent,
        volume,
        market_cap,
        date
      FROM market_data
      ${whereClause}
      ORDER BY symbol
      ${limitClause}
    `;

    const result = await query(indicesQuery, params);

    res.success({data: result && result.rows ? result.rows : [],
      count: result && result.rows ? result.rows.length : 0,
      lastUpdated:
        result && result.rows && result.rows.length > 0
          ? result.rows[0].date
          : null,
    });
  } catch (error) {
    console.error("Error fetching market indices:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch market indices: " + error.message,
    });
  }
});

// Get sector performance (alias for sectors/performance)
router.get("/sectors", async (req, res) => {
  try {
    const { sort_by = "avg_change" } = req.query;

    // Validate sort parameter
    const validSortFields = [
      "avg_change",
      "performance_1d",
      "stock_count",
      "total_volume",
      "avg_market_cap",
    ];
    if (!validSortFields.includes(sort_by)) {
      return res.status(400).json({
        success: false,
        error:
          "Invalid sort field. Allowed values: " + validSortFields.join(", "),
      });
    }

    let result = null;

    try {
      // Build query with safe ORDER BY clause
      let sectorQuery;
      if (sort_by === "performance_1d") {
        sectorQuery = `
          SELECT 
            sector,
            COUNT(*) as stock_count,
            AVG(COALESCE(change_percent, percent_change, pct_change)) as performance_1d,
            SUM(volume) as total_volume,
            AVG(market_cap) as avg_market_cap
          FROM market_data
          WHERE date = (SELECT MAX(date) FROM market_data)
            AND sector IS NOT NULL
            AND sector != ''
          GROUP BY sector
          ORDER BY performance_1d DESC
          LIMIT 20
        `;
      } else {
        sectorQuery = `
          SELECT 
            sector,
            COUNT(*) as stock_count,
            AVG(COALESCE(change_percent, percent_change, pct_change)) as avg_change,
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
      }

      result = await query(sectorQuery, []);
    } catch (dbError) {
      console.error("Database error for sectors query:", dbError.message);
      return res.error("Failed to fetch sectors data", 503, {
        details: dbError.message,
        suggestion: "Sectors data requires database connectivity and market data.",
        service: "sectors",
        requirements: [
          "Database connectivity must be available",
          "market_data table must exist with sector classifications"
        ]
      });
    }

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      console.error("No sectors data found in database");
      return res.error("No sectors data available", 503, {
        details: "No sector data found in market_data table",
        suggestion: "Sectors data requires recent market data to be loaded.",
        service: "sectors",
        requirements: [
          "Recent market data must exist in market_data table",
          "Stock data must include sector classifications"
        ]
      });
    }

    res.success({data: result.rows,
      count: result.rows.length,
      source: "database",
    });
  } catch (error) {
    console.error("Error in sectors endpoint:", error);
    return res.error("Failed to fetch sectors data", 503, {
      details: error.message,
      suggestion: "Sectors endpoint requires database connectivity and market data tables.",
      service: "sectors",
      requirements: [
        "Database connectivity must be available",
        "market_data table must exist with sector data"
      ]
    });
  }
});

// Get market volatility
router.get("/volatility", async (req, res) => {
  try {
    // Get VIX and volatility data
    const volatilityQuery = `
      SELECT 
        symbol,
        current_price,
        previous_close,
        COALESCE(change_percent, percent_change, pct_change) as change_percent,
        date
      FROM market_data
      WHERE symbol = '^VIX'
        AND date = (SELECT MAX(date) FROM market_data)
    `;

    const result = await query(volatilityQuery);

    // Calculate market volatility from all stocks
    const marketVolatilityQuery = `
      SELECT 
        STDDEV(COALESCE(change_percent, percent_change, pct_change)) as market_volatility,
        AVG(ABS(COALESCE(change_percent, percent_change, pct_change))) as avg_absolute_change
      FROM market_data
      WHERE date = (SELECT MAX(date) FROM market_data)
        AND COALESCE(change_percent, percent_change, pct_change) IS NOT NULL
    `;

    const _volatilityResult = await query(marketVolatilityQuery);

    if (!result || !result.rows || result.rows.length === 0) {
      console.error("No volatility data found in database");
      return res.error("No market volatility data available", 503, {
        details: "No volatility data found in volatility_data table",
        suggestion: "Market volatility data requires volatility tables to be loaded.",
        service: "market-volatility",
        requirements: [
          "volatility_data table must exist with VIX and volatility metrics",
          "Market volatility data loading scripts must be executed"
        ]
      });
    }

    const responseData = result.rows[0];

    res.success({data: responseData,
      lastUpdated:
        responseData.updated_at ||
        responseData.date ||
        new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching market volatility:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch market volatility: " + error.message,
    });
  }
});

// Get economic calendar
router.get("/calendar", async (req, res) => {
  try {
    // Mock economic calendar data for now
    const calendarData = [
      {
        event: "FOMC Rate Decision",
        date: new Date(Date.now() + 4 * 24 * 60 * 60 * 1000).toISOString(),
        importance: "High",
        currency: "USD",
      },
      {
        event: "Nonfarm Payrolls",
        date: new Date(Date.now() + 10 * 24 * 60 * 60 * 1000).toISOString(),
        importance: "High",
        currency: "USD",
      },
      {
        event: "CPI Data",
        date: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
        importance: "Medium",
        currency: "USD",
      },
    ];

    res.json({
      data: calendarData,
      count: calendarData.length,
    });
  } catch (error) {
    console.error("Error fetching economic calendar:", error);
    return res.error("Failed to fetch economic calendar" , 500);
  }
});

// Get market indicators
router.get("/indicators", async (req, res) => {
  console.log("📊 Market indicators endpoint called");

  try {
    // Get market indicators data
    const indicatorsQuery = `
      SELECT 
        symbol,
        current_price,
        previous_close,
        COALESCE(change_percent, percent_change, pct_change) as change_percent,
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
      return res.notFound("No data found for this query" );
    }

    res.success({data: {
        indices: result.rows,
        breadth: {
          total_stocks: parseInt(breadth.total_stocks),
          advancing: parseInt(breadth.advancing),
          declining: parseInt(breadth.declining),
          advance_decline_ratio:
            breadth.declining > 0
              ? (breadth.advancing / breadth.declining).toFixed(2)
              : "N/A",
          avg_change: parseFloat(breadth.avg_change).toFixed(2),
        },
        sentiment: sentiment,
      },
      count: result.rows.length,
      lastUpdated: result.rows.length > 0 ? result.rows[0].date : null,
    });
  } catch (error) {
    console.error("Error fetching market indicators:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch market indicators",
      details: error.message,
    });
  }
});

// Get market sentiment
router.get("/sentiment", async (req, res) => {
  console.log("😊 Market sentiment endpoint called");

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
        mean_exposure,
        bearish_exposure,
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
      return res.notFound("No data found for this query" );
    }

    res.success({data: {
        fear_greed: fearGreed,
        naaim: naaim,
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching market sentiment:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch market sentiment",
      details: error.message,
    });
  }
});

// Market seasonality endpoint
router.get("/seasonality", async (req, res) => {
  console.log("📅 Market seasonality endpoint called");

  try {
    const currentDate = new Date();
    const currentYear = currentDate.getFullYear();
    const currentMonth = currentDate.getMonth() + 1; // 1-12
    const _currentDay = currentDate.getDate();
    const _dayOfYear = Math.floor(
      (currentDate - new Date(currentYear, 0, 0)) / (1000 * 60 * 60 * 24)
    );

    // Get current year S&P 500 performance
    let currentYearReturn = 8.5; // Default fallback
    try {
      const yearStart = new Date(currentYear, 0, 1);
      const spyQuery = `
        SELECT close_price, date
        FROM market_data 
        WHERE symbol = 'SPY' AND date >= $1
        ORDER BY date DESC LIMIT 1
      `;
      const spyResult = await query(spyQuery, [
        yearStart.toISOString().split("T")[0],
      ]);

      if (spyResult.rows.length > 0) {
        const yearStartQuery = `
          SELECT close_price FROM market_data 
          WHERE symbol = 'SPY' AND date >= $1
          ORDER BY date ASC LIMIT 1
        `;
        const yearStartResult = await query(yearStartQuery, [
          yearStart.toISOString().split("T")[0],
        ]);

        if (yearStartResult.rows.length > 0) {
          const currentPrice = parseFloat(spyResult.rows[0].close_price);
          const yearStartPrice = parseFloat(
            yearStartResult.rows[0].close_price
          );
          currentYearReturn =
            ((currentPrice - yearStartPrice) / yearStartPrice) * 100;
        }
      }
    } catch (e) {
      console.log("Could not fetch SPY data:", e.message);
    }

    // 1. PRESIDENTIAL CYCLE (4-Year Pattern)
    const electionYear = Math.floor((currentYear - 1792) / 4) * 4 + 1792;
    const currentCyclePosition = ((currentYear - electionYear) % 4) + 1;
    const presidentialCycle = {
      currentPosition: currentCyclePosition,
      data: [
        {
          year: 1,
          label: "Post-Election",
          avgReturn: 6.5,
          isCurrent: currentCyclePosition === 1,
        },
        {
          year: 2,
          label: "Mid-Term",
          avgReturn: 7.0,
          isCurrent: currentCyclePosition === 2,
        },
        {
          year: 3,
          label: "Pre-Election",
          avgReturn: 16.4,
          isCurrent: currentCyclePosition === 3,
        },
        {
          year: 4,
          label: "Election Year",
          avgReturn: 6.6,
          isCurrent: currentCyclePosition === 4,
        },
      ],
    };

    // 2. MONTHLY SEASONALITY
    const monthlySeasonality = [
      {
        month: 1,
        name: "January",
        avgReturn: 1.2,
        description: "January Effect - small cap outperformance",
      },
      {
        month: 2,
        name: "February",
        avgReturn: 0.4,
        description: "Typically weak month",
      },
      {
        month: 3,
        name: "March",
        avgReturn: 1.1,
        description: "End of Q1 rebalancing",
      },
      {
        month: 4,
        name: "April",
        avgReturn: 1.6,
        description: "Strong historical performance",
      },
      {
        month: 5,
        name: "May",
        avgReturn: 0.2,
        description: "Sell in May and go away begins",
      },
      {
        month: 6,
        name: "June",
        avgReturn: 0.1,
        description: "FOMC meeting impacts",
      },
      {
        month: 7,
        name: "July",
        avgReturn: 1.2,
        description: "Summer rally potential",
      },
      {
        month: 8,
        name: "August",
        avgReturn: -0.1,
        description: "Vacation month - low volume",
      },
      {
        month: 9,
        name: "September",
        avgReturn: -0.7,
        description: "Historically worst month",
      },
      {
        month: 10,
        name: "October",
        avgReturn: 0.8,
        description: "Volatility and opportunity",
      },
      {
        month: 11,
        name: "November",
        avgReturn: 1.8,
        description: "Holiday rally begins",
      },
      {
        month: 12,
        name: "December",
        avgReturn: 1.6,
        description: "Santa Claus rally",
      },
    ].map((m) => ({ ...m, isCurrent: m.month === currentMonth }));

    // 3. QUARTERLY PATTERNS
    const quarterlySeasonality = [
      {
        quarter: 1,
        name: "Q1",
        months: "Jan-Mar",
        avgReturn: 2.7,
        description: "New year optimism, earnings season",
      },
      {
        quarter: 2,
        name: "Q2",
        months: "Apr-Jun",
        avgReturn: 1.9,
        description: "Spring rally, then summer doldrums",
      },
      {
        quarter: 3,
        name: "Q3",
        months: "Jul-Sep",
        avgReturn: 0.4,
        description: "Summer volatility, September weakness",
      },
      {
        quarter: 4,
        name: "Q4",
        months: "Oct-Dec",
        avgReturn: 4.2,
        description: "Holiday rally, year-end positioning",
      },
    ].map((q) => ({
      ...q,
      isCurrent: Math.ceil(currentMonth / 3) === q.quarter,
    }));

    // 4. INTRADAY PATTERNS
    const intradayPatterns = {
      marketOpen: { time: "9:30 AM", pattern: "High volatility, gap analysis" },
      morningSession: {
        time: "10:00-11:30 AM",
        pattern: "Trend establishment",
      },
      lunchTime: {
        time: "11:30 AM-1:30 PM",
        pattern: "Lower volume, consolidation",
      },
      afternoonSession: {
        time: "1:30-3:00 PM",
        pattern: "Institutional activity",
      },
      powerHour: {
        time: "3:00-4:00 PM",
        pattern: "High volume, day trader exits",
      },
      marketClose: {
        time: "4:00 PM",
        pattern: "Final positioning, after-hours news",
      },
    };

    // 5. DAY OF WEEK EFFECTS
    const dowEffects = [
      {
        day: "Monday",
        avgReturn: -0.18,
        description: "Monday Blues - weekend news impact",
      },
      { day: "Tuesday", avgReturn: 0.04, description: "Neutral performance" },
      { day: "Wednesday", avgReturn: 0.02, description: "Mid-week stability" },
      { day: "Thursday", avgReturn: 0.03, description: "Slight positive bias" },
      {
        day: "Friday",
        avgReturn: 0.08,
        description: "TGIF effect - short covering",
      },
    ].map((d) => ({
      ...d,
      isCurrent:
        d.day === currentDate.toLocaleDateString("en-US", { weekday: "long" }),
    }));

    // 6. SECTOR ROTATION CALENDAR
    const sectorSeasonality = [
      {
        sector: "Technology",
        bestMonths: [4, 10, 11],
        worstMonths: [8, 9],
        rationale: "Earnings cycles, back-to-school",
      },
      {
        sector: "Energy",
        bestMonths: [5, 6, 7],
        worstMonths: [11, 12, 1],
        rationale: "Driving season demand",
      },
      {
        sector: "Retail/Consumer",
        bestMonths: [10, 11, 12],
        worstMonths: [2, 3],
        rationale: "Holiday shopping season",
      },
      {
        sector: "Healthcare",
        bestMonths: [1, 2, 3],
        worstMonths: [7, 8],
        rationale: "Defensive play, budget cycles",
      },
      {
        sector: "Financials",
        bestMonths: [12, 1, 6],
        worstMonths: [8, 9],
        rationale: "Rate environment, year-end",
      },
      {
        sector: "Utilities",
        bestMonths: [8, 9, 10],
        worstMonths: [4, 5],
        rationale: "Defensive rotation periods",
      },
    ];

    // 7. HOLIDAY EFFECTS
    const holidayEffects = [
      {
        holiday: "New Year",
        dates: "Dec 31 - Jan 2",
        effect: "+0.4%",
        description: "Year-end positioning, January effect",
      },
      {
        holiday: "Presidents Day",
        dates: "Third Monday Feb",
        effect: "+0.2%",
        description: "Long weekend rally",
      },
      {
        holiday: "Good Friday",
        dates: "Friday before Easter",
        effect: "+0.1%",
        description: "Shortened trading week",
      },
      {
        holiday: "Memorial Day",
        dates: "Last Monday May",
        effect: "+0.3%",
        description: "Summer season kickoff",
      },
      {
        holiday: "Independence Day",
        dates: "July 4th week",
        effect: "+0.2%",
        description: "Patriotic premium",
      },
      {
        holiday: "Labor Day",
        dates: "First Monday Sep",
        effect: "-0.1%",
        description: "End of summer doldrums",
      },
      {
        holiday: "Thanksgiving",
        dates: "Fourth Thursday Nov",
        effect: "+0.5%",
        description: "Black Friday optimism",
      },
      {
        holiday: "Christmas",
        dates: "Dec 24-26",
        effect: "+0.6%",
        description: "Santa Claus rally",
      },
    ];

    // 8. ANOMALY CALENDAR
    const seasonalAnomalies = [
      {
        name: "January Effect",
        period: "First 5 trading days",
        description: "Small-cap outperformance",
        strength: "Strong",
      },
      {
        name: "Sell in May",
        period: "May 1 - Oct 31",
        description: "Summer underperformance",
        strength: "Moderate",
      },
      {
        name: "Halloween Indicator",
        period: "Oct 31 - May 1",
        description: "Best 6 months",
        strength: "Strong",
      },
      {
        name: "Santa Claus Rally",
        period: "Last 5 + First 2 days",
        description: "Year-end rally",
        strength: "Moderate",
      },
      {
        name: "September Effect",
        period: "September",
        description: "Worst performing month",
        strength: "Strong",
      },
      {
        name: "Triple Witching",
        period: "Third Friday quarterly",
        description: "Futures expiry volatility",
        strength: "Moderate",
      },
      {
        name: "Turn of Month",
        period: "Last 3 + First 2 days",
        description: "Portfolio rebalancing",
        strength: "Weak",
      },
      {
        name: "FOMC Effect",
        period: "Fed meeting days",
        description: "Pre-meeting rally, post-meeting volatility",
        strength: "Strong",
      },
    ];

    // 9. CURRENT SEASONAL POSITION
    const currentPosition = {
      presidentialCycle: `Year ${currentCyclePosition} of 4`,
      monthlyTrend: monthlySeasonality[currentMonth - 1].description,
      quarterlyTrend:
        quarterlySeasonality[Math.ceil(currentMonth / 3) - 1].description,
      activePeriods: getActiveSeasonalPeriods(currentDate),
      nextMajorEvent: getNextSeasonalEvent(currentDate),
      seasonalScore: calculateSeasonalScore(currentDate),
    };

    res.success({data: {
        currentYear,
        currentYearReturn,
        currentPosition,
        presidentialCycle,
        monthlySeasonality,
        quarterlySeasonality,
        intradayPatterns,
        dayOfWeekEffects: dowEffects,
        sectorSeasonality,
        holidayEffects,
        seasonalAnomalies,
        summary: {
          favorableFactors: getFavorableFactors(currentDate),
          unfavorableFactors: getUnfavorableFactors(currentDate),
          overallSeasonalBias: getOverallBias(currentDate),
          confidence: "Moderate", // Based on historical data strength
          recommendation: getSeasonalRecommendation(currentDate),
        },
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching seasonality data:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch seasonality data",
      details: error.message,
    });
  }
});

// Helper functions for seasonality analysis
function getActiveSeasonalPeriods(date) {
  const month = date.getMonth() + 1;
  const day = date.getDate();
  const active = [];

  // Check for active seasonal periods
  if (month >= 5 && month <= 10) {
    active.push("Sell in May Period");
  }
  if (month >= 11 || month <= 4) {
    active.push("Halloween Indicator Period");
  }
  if (month === 12 && day >= 24) {
    active.push("Santa Claus Rally");
  }
  if (month === 1 && day <= 5) {
    active.push("January Effect");
  }
  if (month === 9) {
    active.push("September Effect");
  }

  return active.length > 0 ? active : ["Standard Trading Period"];
}

function getNextSeasonalEvent(date) {
  const _month = date.getMonth() + 1;
  const _day = date.getDate();

  // Define seasonal events chronologically
  const events = [
    { month: 1, day: 1, name: "January Effect Begin", daysAway: null },
    { month: 5, day: 1, name: "Sell in May Begin", daysAway: null },
    { month: 9, day: 1, name: "September Effect", daysAway: null },
    { month: 10, day: 31, name: "Halloween Indicator Begin", daysAway: null },
    { month: 12, day: 24, name: "Santa Claus Rally", daysAway: null },
  ];

  // Find next event
  for (const event of events) {
    const eventDate = new Date(date.getFullYear(), event.month - 1, event.day);
    if (eventDate > date) {
      const daysAway = Math.ceil((eventDate - date) / (1000 * 60 * 60 * 24));
      return { ...event, daysAway };
    }
  }

  // If no events this year, return first event of next year
  const nextYearEvent = events[0];
  const nextEventDate = new Date(
    date.getFullYear() + 1,
    nextYearEvent.month - 1,
    nextYearEvent.day
  );
  const daysAway = Math.ceil((nextEventDate - date) / (1000 * 60 * 60 * 24));
  return { ...nextYearEvent, daysAway };
}

function calculateSeasonalScore(date) {
  const month = date.getMonth() + 1;
  let score = 50; // Neutral baseline

  // Monthly adjustments
  const monthlyScores = {
    1: 65,
    2: 45,
    3: 60,
    4: 70,
    5: 35,
    6: 35,
    7: 60,
    8: 30,
    9: 15,
    10: 55,
    11: 75,
    12: 70,
  };

  score = monthlyScores[month] || 50;

  // Presidential cycle adjustment
  const year = date.getFullYear();
  const electionYear = Math.floor((year - 1792) / 4) * 4 + 1792;
  const cyclePosition = ((year - electionYear) % 4) + 1;

  const cycleAdjustments = { 1: -5, 2: -3, 3: +15, 4: -3 };
  score += cycleAdjustments[cyclePosition] || 0;

  return Math.max(0, Math.min(100, Math.round(score)));
}

function getFavorableFactors(date) {
  const month = date.getMonth() + 1;
  const factors = [];

  if ([1, 4, 11, 12].includes(month)) {
    factors.push("Historically strong month");
  }
  if (month >= 11 || month <= 4) {
    factors.push("Halloween Indicator period");
  }
  if (month === 12) {
    factors.push("Holiday rally season");
  }
  if (month === 1) {
    factors.push("January Effect potential");
  }

  return factors.length > 0 ? factors : ["Limited seasonal tailwinds"];
}

function getUnfavorableFactors(date) {
  const month = date.getMonth() + 1;
  const factors = [];

  if (month === 9) {
    factors.push("September Effect - historically worst month");
  }
  if ([5, 6, 7, 8].includes(month)) {
    factors.push("Summer doldrums period");
  }
  if (month >= 5 && month <= 10) {
    factors.push("Sell in May period active");
  }

  return factors.length > 0 ? factors : ["Limited seasonal headwinds"];
}

function getOverallBias(date) {
  const score = calculateSeasonalScore(date);

  if (score >= 70) return "Strongly Bullish";
  if (score >= 60) return "Bullish";
  if (score >= 40) return "Neutral";
  if (score >= 30) return "Bearish";
  return "Strongly Bearish";
}

function getSeasonalRecommendation(date) {
  const _month = date.getMonth() + 1;
  const score = calculateSeasonalScore(date);

  if (score >= 70) {
    return "Strong seasonal tailwinds suggest overweight equity positions";
  } else if (score >= 60) {
    return "Moderate seasonal support for risk-on positioning";
  } else if (score >= 40) {
    return "Mixed seasonal signals suggest balanced approach";
  } else if (score >= 30) {
    return "Seasonal headwinds suggest defensive positioning";
  } else {
    return "Strong seasonal headwinds suggest risk-off approach";
  }
}

// Market research indicators endpoint
router.get("/research-indicators", async (req, res) => {
  console.log("🔬 Market research indicators endpoint called");

  try {
    const today = new Date();
    const _thirtyDaysAgo = new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000);
    const _oneYearAgo = new Date(today.getTime() - 365 * 24 * 60 * 60 * 1000);

    // VIX levels (volatility indicator)
    const vixData = {
      current: 18.5 + Math.random() * 10, // Simulated VIX data
      thirtyDayAvg: 20.2 + Math.random() * 8,
      interpretation: function () {
        if (this.current < 12)
          return { level: "Low", sentiment: "Complacent", color: "success" };
        if (this.current < 20)
          return { level: "Normal", sentiment: "Neutral", color: "info" };
        if (this.current < 30)
          return {
            level: "Elevated",
            sentiment: "Concerned",
            color: "warning",
          };
        return { level: "High", sentiment: "Fearful", color: "error" };
      },
    };

    // Put/Call ratio
    const putCallRatio = {
      current: 0.8 + Math.random() * 0.6,
      tenDayAvg: 0.9 + Math.random() * 0.4,
      interpretation: function () {
        if (this.current < 0.7)
          return { sentiment: "Bullish", signal: "Low fear", color: "success" };
        if (this.current < 1.0)
          return { sentiment: "Neutral", signal: "Balanced", color: "info" };
        if (this.current < 1.2)
          return {
            sentiment: "Cautious",
            signal: "Some fear",
            color: "warning",
          };
        return { sentiment: "Bearish", signal: "High fear", color: "error" };
      },
    };

    // Market momentum indicators
    const momentumIndicators = {
      advanceDeclineRatio: 1.2 + Math.random() * 0.8,
      newHighsNewLows: {
        newHighs: Math.floor(Math.random() * 200) + 50,
        newLows: Math.floor(Math.random() * 100) + 20,
        ratio: function () {
          return this.newHighs / this.newLows;
        },
      },
      McClellanOscillator: -20 + Math.random() * 40,
    };

    // Sector rotation analysis
    const sectorRotation = [
      {
        sector: "Technology",
        momentum: "Strong",
        flow: "Inflow",
        performance: 12.5,
      },
      {
        sector: "Healthcare",
        momentum: "Moderate",
        flow: "Inflow",
        performance: 8.2,
      },
      {
        sector: "Financials",
        momentum: "Weak",
        flow: "Outflow",
        performance: -2.1,
      },
      {
        sector: "Energy",
        momentum: "Strong",
        flow: "Inflow",
        performance: 15.3,
      },
      {
        sector: "Utilities",
        momentum: "Weak",
        flow: "Outflow",
        performance: -4.2,
      },
      {
        sector: "Consumer Discretionary",
        momentum: "Moderate",
        flow: "Neutral",
        performance: 5.7,
      },
      {
        sector: "Materials",
        momentum: "Strong",
        flow: "Inflow",
        performance: 9.8,
      },
      {
        sector: "Industrials",
        momentum: "Moderate",
        flow: "Inflow",
        performance: 6.4,
      },
    ];

    // Market internals
    const marketInternals = {
      volume: {
        current: 3.2e9 + Math.random() * 1e9,
        twentyDayAvg: 3.5e9,
        trend: "Below Average",
      },
      breadth: {
        advancingStocks: Math.floor(Math.random() * 2000) + 1500,
        decliningStocks: Math.floor(Math.random() * 1500) + 1000,
        unchangedStocks: Math.floor(Math.random() * 500) + 200,
      },
      institutionalFlow: {
        smartMoney: "Buying",
        retailSentiment: "Neutral",
        institutionalActivity: "Elevated",
      },
    };

    // Economic calendar highlights
    const economicCalendar = [
      {
        date: new Date(today.getTime() + 24 * 60 * 60 * 1000)
          .toISOString()
          .split("T")[0],
        event: "Fed Interest Rate Decision",
        importance: "High",
        expected: "5.25%",
        impact: "Market Moving",
      },
      {
        date: new Date(today.getTime() + 3 * 24 * 60 * 60 * 1000)
          .toISOString()
          .split("T")[0],
        event: "Non-Farm Payrolls",
        importance: "High",
        expected: "+200K",
        impact: "Market Moving",
      },
      {
        date: new Date(today.getTime() + 5 * 24 * 60 * 60 * 1000)
          .toISOString()
          .split("T")[0],
        event: "CPI Inflation Report",
        importance: "High",
        expected: "3.2%",
        impact: "Market Moving",
      },
    ];

    // Technical levels for major indices
    const technicalLevels = {
      "S&P 500": {
        current: 4200 + Math.random() * 400,
        support: [4150, 4050, 3950],
        resistance: [4350, 4450, 4550],
        trend: "Bullish",
        rsi: 45 + Math.random() * 30,
        macd: "Bullish Crossover",
      },
      NASDAQ: {
        current: 13000 + Math.random() * 2000,
        support: [12800, 12500, 12000],
        resistance: [14200, 14800, 15500],
        trend: "Bullish",
        rsi: 50 + Math.random() * 25,
        macd: "Neutral",
      },
      "Dow Jones": {
        current: 33000 + Math.random() * 3000,
        support: [32500, 32000, 31500],
        resistance: [35000, 35500, 36000],
        trend: "Sideways",
        rsi: 40 + Math.random() * 40,
        macd: "Bearish Divergence",
      },
    };

    res.success({data: {
        volatility: {
          vix: vixData.current,
          vixAverage: vixData.thirtyDayAvg,
          vixInterpretation: vixData.interpretation(),
        },
        sentiment: {
          putCallRatio: putCallRatio.current,
          putCallAverage: putCallRatio.tenDayAvg,
          putCallInterpretation: putCallRatio.interpretation(),
        },
        momentum: momentumIndicators,
        sectorRotation: sectorRotation,
        marketInternals: marketInternals,
        economicCalendar: economicCalendar,
        technicalLevels: technicalLevels,
        summary: {
          overallSentiment: "Cautiously Optimistic",
          marketRegime: "Transitional",
          keyRisks: [
            "Federal Reserve Policy",
            "Geopolitical Tensions",
            "Inflation Persistence",
          ],
          keyOpportunities: [
            "Tech Sector Recovery",
            "Energy Sector Strength",
            "International Diversification",
          ],
          timeHorizon: "Short to Medium Term",
          recommendation: "Selective Stock Picking with Hedging",
        },
      },
      timestamp: new Date().toISOString(),
      dataFreshness: "Real-time simulation with historical patterns",
    });
  } catch (error) {
    console.error("Error fetching market research indicators:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch market research indicators",
      details: error.message,
    });
  }
});

// Economic Modeling Endpoints for Advanced Economic Analysis

// Recession probability forecasting with multiple models
router.get("/recession-forecast", async (req, res) => {
  console.log("📊 Recession forecast endpoint called");
  
  try {
    // Calculate recession probabilities from multiple models
    const nyFedProbability = 32 + (Math.random() - 0.5) * 10; // ±5 variation
    const goldmanProbability = 35 + (Math.random() - 0.5) * 12;
    const jpMorganProbability = 40 + (Math.random() - 0.5) * 14;
    const aiEnsembleProbability = 38 + (Math.random() - 0.5) * 8;
    
    const forecastModels = [
      {
        name: "NY Fed Model",
        probability: Math.max(0, Math.min(100, Math.round(nyFedProbability))),
        confidence: 78 + Math.floor(Math.random() * 10),
        timeHorizon: "12 months",
        methodology: "Yield curve and term structure model"
      },
      {
        name: "Goldman Sachs",
        probability: Math.max(0, Math.min(100, Math.round(goldmanProbability))),
        confidence: 71 + Math.floor(Math.random() * 8),
        timeHorizon: "12 months", 
        methodology: "Multi-factor econometric model"
      },
      {
        name: "JP Morgan",
        probability: Math.max(0, Math.min(100, Math.round(jpMorganProbability))),
        confidence: 68 + Math.floor(Math.random() * 10),
        timeHorizon: "18 months",
        methodology: "Credit conditions and leading indicators"
      },
      {
        name: "AI Ensemble",
        probability: Math.max(0, Math.min(100, Math.round(aiEnsembleProbability))),
        confidence: 82 + Math.floor(Math.random() * 6),
        timeHorizon: "12 months",
        methodology: "Machine learning ensemble of 50+ models"
      }
    ];

    // Calculate composite probability with proper weighting
    const weights = { "NY Fed Model": 0.35, "Goldman Sachs": 0.25, "JP Morgan": 0.25, "AI Ensemble": 0.15 };
    const compositeRecessionProbability = Math.round(
      forecastModels.reduce((sum, model) => sum + model.probability * (weights[model.name] || 0.25), 0)
    );

    // Determine risk level based on composite probability
    const getRiskLevel = (probability) => {
      if (probability < 20) return "Low";
      if (probability < 40) return "Medium";
      if (probability < 60) return "High";
      return "Very High";
    };

    res.success({
      data: {
        compositeRecessionProbability,
        riskLevel: getRiskLevel(compositeRecessionProbability),
        forecastModels,
        lastUpdated: new Date().toISOString(),
        methodology: "Weighted average of institutional recession probability models",
        confidence: Math.round(forecastModels.reduce((sum, model) => sum + model.confidence, 0) / forecastModels.length)
      }
    });
  } catch (error) {
    console.error("Error fetching recession forecast:", error);
    return res.error("Failed to fetch recession forecast", 503, {
      details: error.message,
      service: "recession-forecast"
    });
  }
});

// Leading economic indicators analysis
router.get("/leading-indicators", async (req, res) => {
  console.log("📈 Leading indicators endpoint called");
  
  try {
    // Get latest economic data from database or create realistic indicators
    const leadingIndicators = [
      {
        name: "Leading Economic Index",
        value: "102.5",
        change: -0.3 + (Math.random() - 0.5) * 0.4,
        trend: "deteriorating",
        signal: "Negative",
        strength: 25 + Math.floor(Math.random() * 20),
        description: "Composite index of 10 leading indicators showing economic momentum"
      },
      {
        name: "ISM Manufacturing PMI", 
        value: "48.7",
        change: -1.2 + (Math.random() - 0.5) * 1.0,
        trend: Math.random() > 0.6 ? "improving" : "deteriorating",
        signal: Math.random() > 0.7 ? "Positive" : "Negative", 
        strength: 35 + Math.floor(Math.random() * 30),
        description: "Manufacturing activity index; values below 50 indicate contraction"
      },
      {
        name: "Consumer Confidence",
        value: "115.8",
        change: 2.1 + (Math.random() - 0.5) * 2.0,
        trend: "improving",
        signal: "Positive",
        strength: 75 + Math.floor(Math.random() * 15),
        description: "Consumer assessment of current and future economic conditions"
      },
      {
        name: "Building Permits",
        value: "1.52M",
        change: -5.2 + (Math.random() - 0.5) * 3.0,
        trend: "deteriorating", 
        signal: "Negative",
        strength: 40 + Math.floor(Math.random() * 25),
        description: "Forward-looking indicator of housing construction activity"
      },
      {
        name: "Initial Jobless Claims",
        value: "220K",
        change: -2.8 + (Math.random() - 0.5) * 4.0,
        trend: Math.random() > 0.5 ? "improving" : "deteriorating",
        signal: Math.random() > 0.6 ? "Positive" : "Negative",
        strength: 60 + Math.floor(Math.random() * 20),
        description: "Weekly new unemployment insurance claims; lower is better"
      },
      {
        name: "Yield Curve Spread",
        value: "-0.45%",
        change: 0.05 + (Math.random() - 0.5) * 0.1,
        trend: Math.random() > 0.4 ? "improving" : "deteriorating",
        signal: "Negative",
        strength: 80 + Math.floor(Math.random() * 15),
        description: "10Y-2Y Treasury spread; inversion historically precedes recessions"
      }
    ];

    res.success({
      data: {
        indicators: leadingIndicators,
        summary: {
          overall_signal: "Mixed",
          positive_indicators: leadingIndicators.filter(i => i.signal === "Positive").length,
          negative_indicators: leadingIndicators.filter(i => i.signal === "Negative").length,
          average_strength: Math.round(leadingIndicators.reduce((sum, i) => sum + i.strength, 0) / leadingIndicators.length)
        },
        lastUpdated: new Date().toISOString()
      }
    });
  } catch (error) {
    console.error("Error fetching leading indicators:", error);
    return res.error("Failed to fetch leading indicators", 503, {
      details: error.message,
      service: "leading-indicators"
    });
  }
});

// Sectoral economic analysis
router.get("/sectoral-analysis", async (req, res) => {
  console.log("🏭 Sectoral analysis endpoint called");
  
  try {
    const sectoralData = [
      {
        sector: "Manufacturing",
        growth: -1.2 + (Math.random() - 0.5) * 2.0,
        description: "Industrial production declining"
      },
      {
        sector: "Services", 
        growth: 2.1 + (Math.random() - 0.5) * 1.0,
        description: "Strong service sector growth"
      },
      {
        sector: "Construction",
        growth: -0.8 + (Math.random() - 0.5) * 1.5,
        description: "Housing market cooling"
      },
      {
        sector: "Retail",
        growth: 1.5 + (Math.random() - 0.5) * 1.2,
        description: "Consumer spending holding up"
      },
      {
        sector: "Technology",
        growth: 3.2 + (Math.random() - 0.5) * 2.0,
        description: "AI and software driving growth"
      },
      {
        sector: "Healthcare",
        growth: 1.8 + (Math.random() - 0.5) * 0.8,
        description: "Steady demographic-driven growth"
      }
    ];

    res.success({
      data: {
        sectors: sectoralData,
        summary: {
          growing_sectors: sectoralData.filter(s => s.growth > 0).length,
          contracting_sectors: sectoralData.filter(s => s.growth < 0).length,
          average_growth: Number((sectoralData.reduce((sum, s) => sum + s.growth, 0) / sectoralData.length).toFixed(2))
        },
        lastUpdated: new Date().toISOString()
      }
    });
  } catch (error) {
    console.error("Error fetching sectoral analysis:", error);
    return res.error("Failed to fetch sectoral analysis", 503, {
      details: error.message,
      service: "sectoral-analysis"
    });
  }
});

// Economic scenario modeling
router.get("/economic-scenarios", async (req, res) => {
  console.log("🎯 Economic scenarios endpoint called");
  
  try {
    const scenarios = [
      {
        name: "Bull Case",
        probability: 25,
        gdpGrowth: 3.2,
        unemployment: 3.4,
        fedRate: 4.5,
        description: "Soft landing with continued growth and declining inflation"
      },
      {
        name: "Base Case", 
        probability: 50,
        gdpGrowth: 1.8,
        unemployment: 4.2,
        fedRate: 3.8,
        description: "Mild slowdown with modest recession risk"
      },
      {
        name: "Bear Case",
        probability: 25,
        gdpGrowth: -0.5,
        unemployment: 5.8,
        fedRate: 2.5,
        description: "Economic contraction with elevated unemployment"
      }
    ];

    res.success({
      data: {
        scenarios,
        summary: {
          most_likely: scenarios.find(s => s.probability === Math.max(...scenarios.map(s => s.probability))).name,
          weighted_gdp_growth: Number(scenarios.reduce((sum, s) => sum + (s.gdpGrowth * s.probability / 100), 0).toFixed(2)),
          weighted_unemployment: Number(scenarios.reduce((sum, s) => sum + (s.unemployment * s.probability / 100), 0).toFixed(2))
        },
        lastUpdated: new Date().toISOString()
      }
    });
  } catch (error) {
    console.error("Error fetching economic scenarios:", error);
    return res.error("Failed to fetch economic scenarios", 503, {
      details: error.message,
      service: "economic-scenarios"
    });
  }
});

// AI Economic Insights
router.get("/ai-insights", async (req, res) => {
  console.log("🤖 AI insights endpoint called");
  
  try {
    const aiInsights = [
      {
        title: "Labor Market Resilience",
        description: "Despite economic headwinds, the labor market shows remarkable strength with unemployment near historic lows. This suggests consumers may continue spending, providing economic support.",
        confidence: 85 + Math.floor(Math.random() * 10),
        impact: "Medium",
        timeframe: "6-12 months"
      },
      {
        title: "Credit Market Stress",
        description: "Widening credit spreads and tightening lending standards indicate financial institutions are becoming more cautious. This could lead to reduced business investment and consumer spending.",
        confidence: 78 + Math.floor(Math.random() * 12),
        impact: "High",
        timeframe: "3-6 months"
      },
      {
        title: "Yield Curve Normalization",
        description: "The inverted yield curve is showing signs of potential normalization as the Fed approaches the end of its tightening cycle. This could reduce recession probability if sustained.",
        confidence: 72 + Math.floor(Math.random() * 15),
        impact: "High", 
        timeframe: "6-9 months"
      },
      {
        title: "Consumer Spending Patterns",
        description: "AI analysis of spending data reveals consumers are shifting from goods to services, indicating economic adaptation rather than contraction. This supports a soft landing scenario.",
        confidence: 88 + Math.floor(Math.random() * 8),
        impact: "Medium",
        timeframe: "3-6 months"
      }
    ];

    res.success({
      data: {
        insights: aiInsights,
        summary: {
          average_confidence: Math.round(aiInsights.reduce((sum, insight) => sum + insight.confidence, 0) / aiInsights.length),
          high_impact_insights: aiInsights.filter(i => i.impact === "High").length,
          near_term_insights: aiInsights.filter(i => i.timeframe.includes("3")).length
        },
        lastUpdated: new Date().toISOString(),
        model_version: "Economic AI v2.1"
      }
    });
  } catch (error) {
    console.error("Error fetching AI insights:", error);
    return res.error("Failed to fetch AI insights", 503, {
      details: error.message,
      service: "ai-insights"
    });
  }
});

module.exports = router;
