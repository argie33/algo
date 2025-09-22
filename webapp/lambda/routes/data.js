/**
 * Data Routes - General data access endpoints
 * Provides unified access to various data types (price, technical, fundamental)
 */

const express = require("express");

const router = express.Router();
const { query } = require("../utils/database");

/**
 * @route GET /api/data
 * @description Get general data API information
 * @access Public
 */
router.get("/", async (req, res) => {
  try {
    try {
      console.log("📊 Data API info requested");
    } catch (e) {
      // Ignore console logging errors
    }

    res.json({
      message: "Data API - Ready",
      timestamp: new Date().toISOString(),
      status: "operational",
      endpoints: [
        "/:symbol - Get comprehensive data for a symbol",
        "/historical/:symbol - Get historical data for a symbol",
        "/realtime/:symbol - Get real-time data for a symbol",
        "/bulk - Get data for multiple symbols",
      ],
    });
  } catch (error) {
    try {
      console.error("❌ Data API info error:", error);
    } catch (e) {
      // Ignore console logging errors
    }
    if (res.serverError) {
      res.serverError("Failed to get data API information");
    } else {
      res.status(500).json({
        success: false,
        error: "Failed to get data API information",
      });
    }
  }
});

/**
 * @route GET /api/data/bulk
 * @description Get data for multiple symbols
 * @access Public
 */
router.get("/bulk", async (req, res) => {
  const { symbols } = req.query;

  if (!symbols) {
    return res.status(400).json({
      success: false,
      error: "Validation error",
      message: "symbols parameter is required",
      timestamp: new Date().toISOString()
    });
  }

  const symbolsList = symbols.split(",").map((s) => s.trim().toUpperCase());
  try {
    console.log(
      `📊 [DATA] Fetching bulk data for ${symbolsList.length} symbols`
    );
  } catch (e) {
    // Ignore console logging errors
  }

  try {
    const bulkQuery = `
      SELECT symbol, date, open, high, low, close, adj_close, volume
      FROM price_daily 
      WHERE symbol = ANY($1) 
      AND date = (SELECT MAX(date) FROM price_daily WHERE symbol = price_daily.symbol)
    `;

    const result = await query(bulkQuery, [symbolsList]);

    const dataBySymbol = {};
    result.rows.forEach((row) => {
      dataBySymbol[row.symbol] = row;
    });

    try {
      console.log(
        `✅ [DATA] Retrieved bulk data for ${result.rows.length}/${symbolsList.length} symbols`
      );
    } catch (e) {
      // Ignore console logging errors
    }
    res.json({
      requested_symbols: symbolsList,
      found_symbols: Object.keys(dataBySymbol),
      data: dataBySymbol,
      count: result.rows.length,
    });
  } catch (error) {
    try {
      console.error("❌ [DATA] Error fetching bulk data:", error);
    } catch (e) {
      // Ignore console logging errors
    }
    res.status(500).json({
      success: false,
      error: "Failed to retrieve bulk data",
      details: {
        requested_symbols: symbolsList,
        error: error.message,
        service: "data-api",
      },
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * @route GET /api/data/etf-list
 * @description Get list of available ETFs
 * @access Public
 */
router.get("/etf-list", async (req, res) => {
  try {
    console.log("📊 [DATA] Fetching ETF list");

    // Query for ETFs from stocks table where sector is 'ETF'
    // Start with simple query to avoid column mismatch issues
    const etfQuery = `
      SELECT ticker as symbol, short_name as name, sector
      FROM company_profile
      WHERE sector = 'ETF' OR ticker IN ('SPY', 'QQQ', 'IWM', 'VTI', 'VOO', 'ARKK', 'XLF', 'XLK', 'XLE', 'XLV')
      ORDER BY ticker ASC
      LIMIT 100
    `;

    const result = await query(etfQuery);

    console.log(`✅ [DATA] Retrieved ${result.rows.length} ETFs`);

    res.json({
      success: true,
      data: {
        etfs: result.rows,
        count: result.rows.length,
        categories: {
          broad_market: result.rows.filter((etf) =>
            ["SPY", "QQQ", "IWM", "VTI", "VOO"].includes(etf.symbol)
          ),
          sector_specific: result.rows.filter((etf) =>
            ["XLF", "XLK", "XLE", "XLV"].includes(etf.symbol)
          ),
          thematic: result.rows.filter((etf) => ["ARKK"].includes(etf.symbol)),
        },
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("❌ [DATA] Error fetching ETF list:", error);
    res.status(500).json({
      success: false,
      error: "Failed to retrieve ETF list",
      message: error.message,
      service: "data-api",
      timestamp: new Date().toISOString(),
    });
  }
});

// Data sources - MOVED BEFORE :symbol route to prevent conflicts
router.get("/sources", async (req, res) => {
  try {
    res.json({
      success: true,
      data: {
        sources: [
          { name: "Alpha Vantage", status: "active" },
          { name: "Yahoo Finance", status: "active" },
          { name: "PostgreSQL", status: "connected" },
        ],
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: "Data sources unavailable",
      message: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Data status - MOVED BEFORE :symbol route to prevent conflicts
router.get("/status", async (req, res) => {
  try {
    res.json({
      success: true,
      data: {
        status: "operational",
        last_update: new Date().toISOString(),
        tables: {
          price_daily: "active",
          company_profile: "active",
        },
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: "Data status unavailable",
      message: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

/**
 * @route GET /api/data/:symbol
 * @description Get comprehensive data for a symbol (price + technical)
 * @access Public
 */
router.get("/:symbol", async (req, res) => {
  const { symbol } = req.params;
  const symbolUpper = symbol.toUpperCase();

  try {
    try {
      console.log(`📊 [DATA] Fetching comprehensive data for ${symbolUpper}`);
    } catch (e) {
      // Ignore console logging errors
    }

    // Get latest price data
    const priceQuery = `
      SELECT symbol, date, open, high, low, close, adj_close, volume
      FROM price_daily 
      WHERE symbol = $1 
      ORDER BY date DESC 
      LIMIT 1
    `;

    // Get latest technical data
    const technicalQuery = `
      SELECT symbol, date, rsi, macd, macd_signal, macd_hist,
             sma_20, sma_50, ema_4, ema_9, ema_21,
             bbands_upper, bbands_lower, bbands_middle,
             adx, atr
      FROM technical_data_daily 
      WHERE symbol = $1 
      ORDER BY date DESC 
      LIMIT 1
    `;

    const [priceResult, technicalResult] = await Promise.all([
      query(priceQuery, [symbolUpper]),
      query(technicalQuery, [symbolUpper]),
    ]);

    const priceData = priceResult.rows[0] || null;
    const technicalData = technicalResult.rows[0] || null;

    if (!priceData && !technicalData) {
      try {
        console.log(`❌ [DATA] No data found for symbol ${symbolUpper}`);
      } catch (e) {
        // Ignore console logging errors
      }
      if (res.notFound) {
        return res.notFound(`No data available for symbol ${symbolUpper}`);
      } else {
        return res.status(404).json({
          success: false,
          error: `No data available for symbol ${symbolUpper}`,
        });
      }
    }

    const responseData = {
      symbol: symbolUpper,
      price: priceData,
      technical: technicalData,
      timestamp: new Date().toISOString(),
    };

    try {
      console.log(`✅ [DATA] Successfully fetched data for ${symbolUpper}`);
    } catch (e) {
      // Ignore console logging errors
    }
    res.json(responseData);
  } catch (error) {
    try {
      console.error(`❌ [DATA] Error fetching data for ${symbolUpper}:`, error);
    } catch (e) {
      // Ignore console logging errors
    }
    if (res.serverError) {
      res.serverError(`Failed to retrieve data for ${symbolUpper}`, {
        symbol: symbolUpper,
        error: error.message,
        service: "data-api",
      });
    } else {
      res.status(500).json({
        success: false,
        error: `Failed to retrieve data for ${symbolUpper}`,
        symbol: symbolUpper,
        details: error.message,
        service: "data-api",
      });
    }
  }
});

/**
 * @route GET /api/data/historical/:symbol
 * @description Get historical data for a symbol
 * @access Public
 */
router.get("/historical/:symbol", async (req, res) => {
  const { symbol } = req.params;
  const { start, end, limit = 50 } = req.query;
  const symbolUpper = symbol.toUpperCase();

  try {
    console.log(`📊 [DATA] Fetching historical data for ${symbolUpper}`);
  } catch (e) {
    // Ignore console logging errors
  }

  try {
    let historicalQuery = `
      SELECT symbol, date, open, high, low, close, adj_close, volume
      FROM price_daily 
      WHERE symbol = $1
    `;

    const queryParams = [symbolUpper];

    if (start) {
      historicalQuery += ` AND date >= $${queryParams.length + 1}`;
      queryParams.push(start);
    }

    if (end) {
      historicalQuery += ` AND date <= $${queryParams.length + 1}`;
      queryParams.push(end);
    }

    historicalQuery += ` ORDER BY date DESC LIMIT $${queryParams.length + 1}`;
    queryParams.push(parseInt(limit));

    const result = await query(historicalQuery, queryParams);

    if (result.rows.length === 0) {
      try {
        console.log(
          `❌ [DATA] No historical data found for symbol ${symbolUpper}`
        );
      } catch (e) {
        // Ignore console logging errors
      }
      return res.notFound(
        `No historical data available for symbol ${symbolUpper}`
      );
    }

    try {
      console.log(
        `✅ [DATA] Retrieved ${result.rows.length} historical records for ${symbolUpper}`
      );
    } catch (e) {
      // Ignore console logging errors
    }
    res.json({
      symbol: symbolUpper,
      data: result.rows,
      count: result.rows.length,
      parameters: { start, end, limit },
    });
  } catch (error) {
    try {
      console.error(
        `❌ [DATA] Error fetching historical data for ${symbolUpper}:`,
        error
      );
    } catch (e) {
      // Ignore console logging errors
    }
    res.serverError(`Failed to retrieve historical data for ${symbolUpper}`, {
      symbol: symbolUpper,
      error: error.message,
      service: "data-api",
    });
  }
});

/**
 * @route GET /api/data/realtime/:symbol
 * @description Get real-time data for a symbol
 * @access Public
 */
router.get("/realtime/:symbol", async (req, res) => {
  const { symbol } = req.params;
  const { mock_live = "false" } = req.query;
  const symbolUpper = symbol.toUpperCase();

  try {
    console.log(`📊 [DATA] Fetching real-time data for ${symbolUpper}`);
  } catch (e) {
    // Ignore console logging errors
  }

  try {
    // Get the latest historical data as base
    const baseQuery = `
      SELECT symbol, date, open, high, low, close, adj_close, volume
      FROM price_daily 
      WHERE symbol = $1 
      ORDER BY date DESC 
      LIMIT 1
    `;

    const result = await query(baseQuery, [symbolUpper]);

    if (result.rows.length === 0) {
      try {
        console.log(`❌ [DATA] No data found for symbol ${symbolUpper}`);
      } catch (e) {
        // Ignore console logging errors
      }
      return res.notFound(
        `No real-time data available for symbol ${symbolUpper}`
      );
    }

    const baseData = result.rows[0];

    // Generate simulated real-time data based on historical prices
    if (mock_live === "true") {
      const now = new Date();
      const marketOpen = new Date(now);
      marketOpen.setUTCHours(14, 30, 0, 0); // 9:30 AM EST
      const marketClose = new Date(now);
      marketClose.setUTCHours(21, 0, 0, 0); // 4:00 PM EST

      const isMarketHours = now >= marketOpen && now <= marketClose;
      const lastPrice =
        parseFloat(baseData.close) || parseFloat(baseData.adj_close) || 100;

      // Generate realistic price movements (±0.5% typical intraday movement)
      const volatility = 0.005;
      const randomChange = (Math.random() - 0.5) * 2 * volatility;
      const currentPrice = lastPrice * (1 + randomChange);

      // Calculate day's change
      const dayChange = currentPrice - lastPrice;
      const dayChangePercent = ((currentPrice - lastPrice) / lastPrice) * 100;

      // Generate bid/ask spread (typically 0.01-0.05% for liquid stocks)
      const spread = currentPrice * 0.0001;
      const bid = currentPrice - spread / 2;
      const ask = currentPrice + spread / 2;

      // Simulate volume (random between 80-120% of daily average)
      const baseVolume = parseInt(baseData.volume) || 1000000;
      const currentVolume = Math.floor(
        baseVolume * (0.1 + Math.random() * 0.3)
      ); // Partial day volume

      const realtimeData = {
        symbol: symbolUpper,
        current_price: parseFloat(currentPrice.toFixed(2)),
        bid: parseFloat(bid.toFixed(2)),
        ask: parseFloat(ask.toFixed(2)),
        day_change: parseFloat(dayChange.toFixed(2)),
        day_change_percent: parseFloat(dayChangePercent.toFixed(2)),
        volume: currentVolume,
        last_trade_time: now.toISOString(),
        market_status: isMarketHours ? "open" : "closed",
        previous_close: lastPrice,
        day_high: Math.max(lastPrice, currentPrice * 1.002),
        day_low: Math.min(lastPrice, currentPrice * 0.998),
        real_time: true,
        data_source: "simulated_live",
        last_updated: now.toISOString(),
      };

      try {
        console.log(
          `✅ [DATA] Generated simulated real-time data for ${symbolUpper}`
        );
      } catch (e) {
        // Ignore console logging errors
      }
      res.json({
        symbol: symbolUpper,
        data: realtimeData,
        market_status: isMarketHours ? "open" : "closed",
        disclaimer:
          "Simulated real-time data for development - not actual market data",
      });
    } else {
      // Return latest historical data with proper formatting
      const data = {
        ...baseData,
        current_price:
          parseFloat(baseData.close) || parseFloat(baseData.adj_close),
        real_time: false,
        data_source: "historical",
        last_updated: new Date().toISOString(),
      };

      try {
        console.log(`✅ [DATA] Retrieved historical data for ${symbolUpper}`);
      } catch (e) {
        // Ignore console logging errors
      }
      res.json({
        symbol: symbolUpper,
        data: data,
        disclaimer:
          "Real-time data feed not implemented - showing latest historical data",
      });
    }
  } catch (error) {
    try {
      console.error(
        `❌ [DATA] Error fetching real-time data for ${symbolUpper}:`,
        error
      );
    } catch (e) {
      // Ignore console logging errors
    }
    res.serverError(`Failed to retrieve real-time data for ${symbolUpper}`, {
      symbol: symbolUpper,
      error: error.message,
      service: "data-api",
    });
  }
});

// NOTE: /sources and /status routes moved before /:symbol route to prevent conflicts

// Stock search endpoint
router.get("/stocks/search", async (req, res) => {
  try {
    const { q } = req.query;

    if (!q || q.trim().length === 0) {
      return res.status(400).json({
        success: false,
        error: "Search query required",
        message: "Query parameter 'q' is required",
        timestamp: new Date().toISOString(),
      });
    }

    const searchTerm = q.trim().toUpperCase();
    console.log(`🔍 Stock search requested for: "${searchTerm}"`);

    // Search for stocks in the database
    const searchQuery = `
      SELECT DISTINCT
        symbol,
        company_name as name,
        exchange,
        'Common Stock' as type,
        CASE
          WHEN UPPER(symbol) = $1 THEN 1.0
          WHEN UPPER(symbol) LIKE $1 || '%' THEN 0.9
          WHEN UPPER(company_name) LIKE '%' || $1 || '%' THEN 0.8
          ELSE 0.7
        END as match_score,
        sector as description
      FROM company_profile
      WHERE
        UPPER(symbol) LIKE '%' || $1 || '%'
        OR UPPER(company_name) LIKE '%' || $1 || '%'
      ORDER BY match_score DESC, symbol
      LIMIT 20
    `;

    const result = await query(searchQuery, [searchTerm]);

    if (!result || !Array.isArray(result.rows)) {
      return res.status(404).json({
        success: false,
        error: "No search results found",
        message: "No stocks found matching the search criteria",
        query: searchTerm,
        timestamp: new Date().toISOString(),
      });
    }

    res.json({
      success: true,
      data: {
        query: searchTerm,
        results: result.rows,
        count: result.rows.length,
        total_matches: result.rows.length,
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error(`❌ Error searching stocks for "${req.query.q}":`, error);
    res.status(500).json({
      success: false,
      error: "Stock search failed",
      message: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

module.exports = router;
