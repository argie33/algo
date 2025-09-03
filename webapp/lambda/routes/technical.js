const express = require("express");

const { query } = require("../utils/database");

const router = express.Router();

// Basic ping endpoint
router.get("/ping", (req, res) => {
  res.success({
    status: "ok",
    endpoint: "technical",
    timestamp: new Date().toISOString(),
  });
});

// Main technical data endpoint - timeframe-based (daily, weekly, monthly)
/**
 * @route GET /api/technical/daily/:symbol
 * @desc Get daily technical indicators for a specific symbol
 */
router.get("/daily/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    const symbolUpper = symbol.toUpperCase();

    console.log(`📊 Daily technical analysis requested for: ${symbolUpper}`);

    // Get technical indicators from database
    const result = await query(
      `
      SELECT * FROM technicals_daily 
      WHERE symbol = $1 
      ORDER BY date DESC 
      LIMIT 30
      `,
      [symbolUpper]
    );

    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Technical data not found",
        message: `No daily technical data available for symbol ${symbolUpper}`
      });
    }

    res.json({
      success: true,
      data: {
        symbol: symbolUpper,
        timeframe: "daily",
        indicators: result.rows,
        total: result.rows.length
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error(`Technical analysis error for ${req.params.symbol}:`, error);
    res.status(500).json({
      success: false,
      error: "Technical analysis failed",
      details: error.message
    });
  }
});

// Technical indicators overview endpoint (must come before /:timeframe)
router.get("/indicators", async (req, res) => {
  try {
    const { symbol, limit = 10 } = req.query;

    console.log(`📊 Technical indicators overview requested - symbol: ${symbol || 'all'}, limit: ${limit}`);

    if (symbol) {
      // Get indicators for specific symbol using your actual database schema
      const indicatorsQuery = `
        SELECT 
          symbol, date,
          rsi, macd, macd_signal, macd_hist,
          sma_20, sma_50, sma_200,
          bbands_upper, bbands_middle, bbands_lower,
          ema_4, ema_9, ema_21, atr
        FROM technicals_daily 
        WHERE symbol = $1 
        ORDER BY date DESC 
        LIMIT $2
      `;

      const result = await query(indicatorsQuery, [symbol.toUpperCase(), parseInt(limit)]);

      if (!result.rows || result.rows.length === 0) {
        return res.success({
          data: [],
          message: `No technical indicators found for ${symbol}`,
          symbol: symbol.toUpperCase(),
          total: 0,
          timestamp: new Date().toISOString()
        });
      }

      return res.success({
        data: result.rows,
        symbol: symbol.toUpperCase(),
        total: result.rows.length,
        message: `Found ${result.rows.length} technical indicator records`,
        timestamp: new Date().toISOString()
      });

    } else {
      // Get overview of all indicators from your actual schema
      const overviewQuery = `
        SELECT DISTINCT ON (symbol) 
          symbol,
          date,
          rsi,
          macd,
          sma_20,
          sma_50,
          sma_200,
          bbands_upper,
          bbands_lower
        FROM technicals_daily 
        ORDER BY symbol, date DESC
        LIMIT $1
      `;

      const result = await query(overviewQuery, [parseInt(limit)]);

      return res.success({
        data: result.rows,
        total: (result.rows).length,
        filters: { symbol: null, limit: parseInt(limit) },
        message: `Technical indicators overview for ${(result.rows).length} symbols`,
        timestamp: new Date().toISOString()
      });
    }

  } catch (error) {
    console.error("Error fetching technical indicators:", error);
    res.error("Failed to fetch technical indicators", 500, {
      details: error.message
    });
  }
});

// Chart data endpoint - must come BEFORE the /:timeframe route
router.get("/chart", async (req, res) => {
  try {
    const { 
      symbol = "AAPL", 
      timeframe = "daily",
      period = "1m",
      indicators = "sma,rsi",
      limit = 100
    } = req.query;

    console.log(`📊 Technical chart requested - symbol: ${symbol}, timeframe: ${timeframe}, period: ${period}`);

    // Validate timeframe
    const validTimeframes = ["1m", "5m", "15m", "1h", "4h", "daily", "weekly", "monthly"];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({
        success: false,
        error: "Invalid timeframe. Must be one of: " + validTimeframes.join(", "),
        requested_timeframe: timeframe
      });
    }

    // Validate period
    const validPeriods = ["1d", "5d", "1m", "3m", "6m", "1y", "2y", "5y"];
    if (!validPeriods.includes(period)) {
      return res.status(400).json({
        success: false,
        error: "Invalid period. Must be one of: " + validPeriods.join(", "),
        requested_period: period
      });
    }

    // Parse indicators
    const requestedIndicators = indicators.split(",").map(i => i.trim().toLowerCase());
    const validIndicators = ["sma", "ema", "rsi", "macd", "bollinger", "stochastic", "adx", "volume"];
    const filteredIndicators = requestedIndicators.filter(i => validIndicators.includes(i));

    // Convert period to days for data generation
    const periodDays = {
      "1d": 1,
      "5d": 5,
      "1m": 30,
      "3m": 90,
      "6m": 180,
      "1y": 365,
      "2y": 730,
      "5y": 1825
    };

    const days = periodDays[period];
    const dataPoints = Math.min(parseInt(limit), days);

    // Query database for real technical chart data - no data generation
    const tableName = `technicals_${timeframe}`;
    
    // Build columns to select based on requested indicators
    let indicatorColumns = '';
    if (filteredIndicators.includes('sma')) indicatorColumns += ', sma_20, sma_50';
    if (filteredIndicators.includes('ema')) indicatorColumns += ', ema_4, ema_9, ema_21';
    if (filteredIndicators.includes('rsi')) indicatorColumns += ', rsi';
    if (filteredIndicators.includes('macd')) indicatorColumns += ', macd, macd_signal, macd_hist';
    if (filteredIndicators.includes('bollinger')) indicatorColumns += ', bbands_upper, bbands_middle, bbands_lower';
    if (filteredIndicators.includes('adx')) indicatorColumns += ', adx, plus_di, minus_di';

    const chartQuery = `
      SELECT t.date, p.open, p.high, p.low, p.close, p.volume${indicatorColumns}
      FROM ${tableName} t
      JOIN price_daily p ON t.symbol = p.symbol AND t.date = p.date
      WHERE t.symbol = $1
      ORDER BY t.date DESC
      LIMIT $2
    `;

    const chartResult = await query(chartQuery, [symbol.toUpperCase(), dataPoints]);
    
    if (!chartResult.rows || chartResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "No data found",
        message: `No technical chart data available for symbol ${symbol.toUpperCase()} in ${timeframe} timeframe`,
        details: {
          symbol: symbol.toUpperCase(),
          timeframe: timeframe,
          period: period,
          table_queried: tableName,
          requested_points: dataPoints
        }
      });
    }

    const chartData = chartResult.rows.reverse(); // Chronological order

    // Process real data from database - data is already sorted chronologically
    // No additional processing needed, database contains real OHLCV and indicator data

    // Calculate summary statistics from real database data
    const prices = chartData.map(d => parseFloat(d.close));
    const volumes = chartData.map(d => parseInt(d.volume) || 0);
    
    if (prices.length === 0) {
      return res.status(500).json({
        success: false,
        error: "Data processing error",
        message: "Retrieved data contains no valid price information"
      });
    }
    
    const highestPrice = Math.max(...prices);
    const lowestPrice = Math.min(...prices);
    const firstPrice = prices[0];
    const lastPrice = prices[prices.length - 1];
    const totalReturn = firstPrice > 0 ? ((lastPrice - firstPrice) / firstPrice) * 100 : 0;

    const summary = {
      symbol: symbol.toUpperCase(),
      timeframe: timeframe,
      period: period,
      data_points: chartData.length,
      price_range: {
        high: highestPrice,
        low: lowestPrice,
        current: lastPrice,
        first: firstPrice
      },
      performance: {
        total_return: parseFloat(totalReturn.toFixed(2)),
        total_return_percent: parseFloat(totalReturn.toFixed(2)) + '%'
      },
      volume: {
        average: Math.round(volumes.reduce((sum, vol) => sum + vol, 0) / volumes.length),
        max: Math.max(...volumes),
        min: Math.min(...volumes)
      },
      indicators_included: filteredIndicators
    };

    res.json({
      success: true,
      data: {
        symbol: symbol.toUpperCase(),
        timeframe: timeframe,
        period: period,
        chart_data: chartData,
        summary: summary,
        metadata: {
          data_source: "database_query",
          table_name: tableName,
          note: "Real technical chart data retrieved from database",
          query_timestamp: new Date().toISOString(),
          indicators_requested: filteredIndicators.join(', ')
        }
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Technical chart error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch chart data",
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Technical Screener Endpoint - filters stocks by multiple technical criteria  
// MUST BE BEFORE /:timeframe route to avoid parameter conflicts
router.get("/screener", async (req, res) => {
  try {
    const { 
      rsi_min = "0", 
      rsi_max = "100", 
      volume_min = "0", 
      price_min = "0", 
      price_max = "10000", 
      limit = "50",
      sector,
      market_cap_min = "0"
    } = req.query;
    
    const maxLimit = Math.min(parseInt(limit), 100);

    console.log(`🔍 Technical screener requested - RSI: ${rsi_min}-${rsi_max}, Volume: ${volume_min}+, Price: ${price_min}-${price_max}`);

    // Remove hardcoded stocks array - use database only

    // Query database for real technical screening - no data generation
    const screenQuery = `
      SELECT t.symbol, p.close as price, t.rsi, p.volume, 
             t.sma_50, t.sma_200, s.sector, s.market_cap, s.pe_ratio
      FROM technicals_daily t
      JOIN price_daily p ON t.symbol = p.symbol AND t.date = p.date
      LEFT JOIN stocks s ON t.symbol = s.symbol
      WHERE t.date = (SELECT MAX(date) FROM technicals_daily)
        AND t.rsi BETWEEN $1 AND $2
        AND p.close BETWEEN $3 AND $4  
        AND p.volume >= $5
        ${sector ? 'AND s.sector = $6' : ''}
        ${market_cap_min ? 'AND s.market_cap >= $' + (sector ? '7' : '6') : ''}
      ORDER BY p.volume DESC
      LIMIT $${sector ? (market_cap_min ? '8' : '7') : (market_cap_min ? '7' : '6')}
    `;

    const params = [parseFloat(rsi_min), parseFloat(rsi_max), parseFloat(price_min), parseFloat(price_max), parseFloat(volume_min)];
    if (sector) params.push(sector);
    if (market_cap_min) params.push(parseFloat(market_cap_min));
    params.push(maxLimit);

    const screenResult = await query(screenQuery, params);
    
    if (!screenResult.rows || screenResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "No results found", 
        message: "No stocks match the specified technical screening criteria",
        criteria: { rsi_range: `${rsi_min}-${rsi_max}`, price_range: `$${price_min}-$${price_max}`, min_volume: volume_min, sector: sector || "all" }
      });
    }

    const screenResults = screenResult.rows.map(row => ({
      ...row,
      change_percent: 0, // Would need price history for real calculation
      signal: row.rsi > 70 ? "OVERBOUGHT" : row.rsi < 30 ? "OVERSOLD" : "NEUTRAL"
    }));

    res.json({
      success: true,
      data: {
        stocks: screenResults.slice(0, parseInt(limit)),
        filters_applied: {
          rsi_range: `${rsi_min}-${rsi_max}`,
          price_range: `$${price_min}-$${price_max}`,
          min_volume: volume_min,
          min_market_cap: market_cap_min,
          sector: sector || "all"
        },
        summary: {
          total_matches: screenResults.length,
          overbought: screenResults.filter(s => s.signal === "OVERBOUGHT").length,
          oversold: screenResults.filter(s => s.signal === "OVERSOLD").length,
          neutral: screenResults.filter(s => s.signal === "NEUTRAL").length
        }
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Technical screener error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to run technical screener",
      message: error.message
    });
  }
});

// Technical analysis endpoint
router.get("/analysis", async (req, res) => {
  try {
    const { 
      symbol = "AAPL", 
      timeframe = "daily",
      indicators = "all"
    } = req.query;

    console.log(`📊 Technical analysis requested for ${symbol}, timeframe: ${timeframe}`);

    // Validate timeframe
    const validTimeframes = ["daily", "weekly", "monthly"];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({ 
        success: false,
        error: "Invalid timeframe. Use daily, weekly, or monthly." 
      });
    }

    // Get comprehensive technical analysis
    const result = await query(
      `
      SELECT * FROM technicals_daily 
      WHERE symbol = $1 
      ORDER BY date DESC 
      LIMIT 5
      `,
      [symbol.toUpperCase()]
    );

    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "No data found",
        message: `No technical analysis data available for symbol ${symbol.toUpperCase()}`,
        symbol: symbol.toUpperCase(),
        timeframe
      });
    }

    const analysisData = {
      symbol: symbol.toUpperCase(),
      timeframe,
      analysis_date: new Date().toISOString(),
      indicators: result.rows[0],
      // Real trend analysis, signals, and recommendations would be calculated here
      trend_analysis: null,
      signals: null,
      recommendation: null
    };

    res.json({
      success: true,
      data: analysisData,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Technical analysis error:", error);
    res.status(500).json({
      success: false,
      error: "Technical analysis failed",
      details: error.message
    });
  }
});

router.get("/:timeframe", async (req, res) => {
  const { timeframe } = req.params;
  const {
    page = 1,
    limit = 50,
    symbol,
    start_date,
    end_date,
    rsi_min,
    rsi_max,
    macd_min,
    macd_max,
    sma_min,
    sma_max,
  } = req.query;

  // Validate timeframe
  const validTimeframes = ["daily", "weekly", "monthly"];
  if (!validTimeframes.includes(timeframe)) {
    return res
      .status(400)
      .json({ error: "Invalid timeframe. Use daily, weekly, or monthly." });
  }

  try {
    const offset = (parseInt(page) - 1) * parseInt(limit);
    const maxLimit = Math.min(parseInt(limit), 200);

    // Build WHERE clause
    let whereClause = "WHERE 1=1";
    const params = [];
    let paramIndex = 1;

    // Symbol filter
    if (symbol && symbol.trim()) {
      whereClause += ` AND t.symbol = $${paramIndex}`;
      params.push(symbol.toUpperCase());
      paramIndex++;
    }

    // Date filters
    if (start_date) {
      whereClause += ` AND t.date >= $${paramIndex}`;
      params.push(start_date);
      paramIndex++;
    }

    if (end_date) {
      whereClause += ` AND t.date <= $${paramIndex}`;
      params.push(end_date);
      paramIndex++;
    }

    // Technical indicator filters
    if (rsi_min !== undefined && rsi_min !== "") {
      whereClause += ` AND t.rsi >= $${paramIndex}`;
      params.push(parseFloat(rsi_min));
      paramIndex++;
    }

    if (rsi_max !== undefined && rsi_max !== "") {
      whereClause += ` AND t.rsi <= $${paramIndex}`;
      params.push(parseFloat(rsi_max));
      paramIndex++;
    }

    if (macd_min !== undefined && macd_min !== "") {
      whereClause += ` AND t.macd >= $${paramIndex}`;
      params.push(parseFloat(macd_min));
      paramIndex++;
    }

    if (macd_max !== undefined && macd_max !== "") {
      whereClause += ` AND t.macd <= $${paramIndex}`;
      params.push(parseFloat(macd_max));
      paramIndex++;
    }

    if (sma_min !== undefined && sma_min !== "") {
      whereClause += ` AND t.sma_20 >= $${paramIndex}`;
      params.push(parseFloat(sma_min));
      paramIndex++;
    }

    if (sma_max !== undefined && sma_max !== "") {
      whereClause += ` AND t.sma_20 <= $${paramIndex}`;
      params.push(parseFloat(sma_max));
      paramIndex++;
    }

    // Determine table name based on timeframe
    const tableName = `technicals_${timeframe}`;

    // Check if table exists
    const tableExists = await query(
      `
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = $1
      );
    `,
      [tableName]
    );

    if (!tableExists || !tableExists.rows || !tableExists.rows[0].exists) {
      console.log(
        `Technical data table for ${timeframe} timeframe not found, returning empty data`
      );
      return res.success({data: [],
        pagination: {
          page: parseInt(page),
          limit: parseInt(limit),
          total: 0,
          totalPages: 0,
          hasNext: false,
          hasPrev: false,
        },
        metadata: {
          timeframe,
          filters: {
            symbol: symbol || null,
            start_date: start_date || null,
            end_date: end_date || null,
            rsi_min: rsi_min || null,
            rsi_max: rsi_max || null,
            macd_min: macd_min || null,
            macd_max: macd_max || null,
            sma_min: sma_min || null,
            sma_max: sma_max || null,
          },
          message: `No ${timeframe} technical data available`,
        },
      });
    }

    // Get total count
    const countQuery = `
      SELECT COUNT(*) as total
      FROM ${tableName} t
      LEFT JOIN price_daily p ON t.symbol = p.symbol AND t.date = p.date
      ${whereClause}
    `;
    const countResult = await query(countQuery, params);
    const total = countResult && countResult.rows ? parseInt(countResult.rows[0].total) : 0;

    // Get technical data - map column names from technicals_daily table
    const dataQuery = `
      SELECT 
        t.symbol,
        t.date,
        p.open,
        p.high,
        p.low,
        p.close,
        p.volume,
        t.rsi,
        t.macd,
        t.macd_signal,
        t.macd_histogram as macd_hist,
        t.sma_20,
        t.sma_50,
        t.sma_200,
        t.ema_12 as ema_4,
        t.ema_26 as ema_9,
        t.bollinger_upper as bbands_upper,
        t.bollinger_lower as bbands_lower,
        t.bollinger_middle as bbands_middle,
        t.adx,
        t.atr,
        t.stochastic_k,
        t.stochastic_d,
        t.williams_r,
        t.cci
      FROM ${tableName} t
      LEFT JOIN price_daily p ON t.symbol = p.symbol AND t.date = p.date
      ${whereClause.replace('WHERE 1=1', 'WHERE 1=1')}
      ORDER BY t.date DESC, t.symbol
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `;

    const finalParams = [...params, maxLimit, offset];
    const dataResult = await query(dataQuery, finalParams);

    const totalPages = Math.ceil(total / maxLimit);

    if (
      !dataResult ||
      !Array.isArray(dataResult.rows) ||
      dataResult.rows.length === 0
    ) {
      return res.success({data: [],
        pagination: {
          page: parseInt(page),
          limit: maxLimit,
          total: 0,
          totalPages: 0,
          hasNext: false,
          hasPrev: false,
        },
        metadata: {
          timeframe,
          filters: {
            symbol: symbol || null,
            start_date: start_date || null,
            end_date: end_date || null,
            rsi_min: rsi_min || null,
            rsi_max: rsi_max || null,
            macd_min: macd_min || null,
            macd_max: macd_max || null,
            sma_min: sma_min || null,
            sma_max: sma_max || null,
          },
        },
      });
    }

    res.success({data: dataResult.rows,
      pagination: {
        page: parseInt(page),
        limit: maxLimit,
        total,
        totalPages,
        hasNext: parseInt(page) < totalPages,
        hasPrev: parseInt(page) > 1,
      },
      metadata: {
        timeframe,
        filters: {
          symbol: symbol || null,
          start_date: start_date || null,
          end_date: end_date || null,
          rsi_min: rsi_min || null,
          rsi_max: rsi_max || null,
          macd_min: macd_min || null,
          macd_max: macd_max || null,
          sma_min: sma_min || null,
          sma_max: sma_max || null,
        },
      },
    });
  } catch (error) {
    console.error("Technical data error:", error);
    return res.error("Failed to retrieve technical analysis data", 500, {
      data: [],
      pagination: {
        page: parseInt(page) || 1,
        limit: parseInt(limit) || 50,
        total: 0,
        totalPages: 0,
        hasNext: false,
        hasPrev: false,
      },
      metadata: {
        timeframe,
        error: error.message,
      },
    });
  }
});

// Technical summary endpoint
router.get("/:timeframe/summary", async (req, res) => {
  const { timeframe } = req.params;

  // console.log(`Technical summary endpoint called for timeframe: ${timeframe}`);

  try {
    const tableName = `technicals_${timeframe}`;

    // Check if table exists
    const tableExists = await query(
      `
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = $1
      );
    `,
      [tableName]
    );

    if (!tableExists.rows[0].exists) {
      console.log(
        `Technical data table for ${timeframe} timeframe not found`
      );
      return res.error(`Technical data table for ${timeframe} timeframe not found`, {
        timeframe,
        summary: null,
        topSymbols: [],
        error: `No technical data available for timeframe: ${timeframe}`,
      }, 404);
    }

    // Get summary statistics
    const summaryQuery = `
      SELECT 
        COUNT(*) as total_records,
        COUNT(DISTINCT symbol) as unique_symbols,
        MIN(t.date) as earliest_date,
        MAX(t.date) as latest_date,
        AVG(t.rsi) as avg_rsi,
        AVG(t.macd) as avg_macd,
        AVG(t.sma_20) as avg_sma_20,
        AVG(p.volume) as avg_volume
      FROM ${tableName} t
      LEFT JOIN price_daily p ON t.symbol = p.symbol AND t.date = p.date
      WHERE t.rsi IS NOT NULL OR t.macd IS NOT NULL
    `;

    const summaryResult = await query(summaryQuery);
    const summary = summaryResult.rows[0];

    // Get top symbols by record count
    const topSymbolsQuery = `
      SELECT symbol, COUNT(*) as record_count
      FROM ${tableName}
      GROUP BY symbol
      ORDER BY record_count DESC
      LIMIT 10
    `;

    const topSymbolsResult = await query(topSymbolsQuery);

    res.success({
      timeframe,
      summary: {
        totalRecords: parseInt(summary.total_records),
        uniqueSymbols: parseInt(summary.unique_symbols),
        dateRange: {
          earliest: summary.earliest_date,
          latest: summary.latest_date,
        },
        averages: {
          rsi: summary.avg_rsi ? parseFloat(summary.avg_rsi).toFixed(2) : null,
          macd: summary.avg_macd
            ? parseFloat(summary.avg_macd).toFixed(4)
            : null,
          sma20: summary.avg_sma_20
            ? parseFloat(summary.avg_sma_20).toFixed(2)
            : null,
          volume: summary.avg_volume ? parseInt(summary.avg_volume) : null,
        },
      },
      topSymbols: topSymbolsResult.rows.map((row) => ({
        symbol: row.symbol,
        recordCount: parseInt(row.record_count),
      })),
    });
  } catch (error) {
    console.error("Error fetching technical summary:", error);
    return res.error("Failed to fetch technical summary", {
      timeframe,
      summary: null,
      topSymbols: [],
      error: error.message,
    }, 500);
  }
});

// Root technical endpoint - defaults to daily data
router.get("/", async (req, res) => {
  try {
    // Only fetch the latest technicals for each symbol (overview)
    const timeframe = req.query.timeframe || "daily";
    const validTimeframes = ["daily", "weekly", "monthly"];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({
        error: "Unsupported timeframe",
        message: `Supported timeframes: ${validTimeframes.join(", ")}, got: ${timeframe}`,
      });
    }
    const tableName = `technicals_${timeframe}`;

    // Check if table exists
    const tableExists = await query(
      `
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = $1
      );
    `,
      [tableName]
    );

    if (!tableExists.rows[0].exists) {
      console.error(`Technical data table for ${timeframe} timeframe not found`);
      return res.error("Technical data not available", 503, {
        message: `Technical data table for ${timeframe} timeframe does not exist`,
        service: "technical-overview",
        timeframe: timeframe
      });
    }

    // Subquery to get latest date per symbol
    const latestQuery = `
      SELECT t1.* FROM ${tableName} t1
      INNER JOIN (
        SELECT symbol, MAX(date) AS max_date
        FROM ${tableName}
        GROUP BY symbol
      ) t2 ON t1.symbol = t2.symbol AND t1.date = t2.max_date
      LEFT JOIN stock_symbols ss ON t1.symbol = ss.symbol
      ORDER BY t1.symbol ASC
      LIMIT 500
    `;
    const result = await query(latestQuery);
    res.success({data: result.rows,
      count: result.rows.length,
      metadata: {
        timeframe,
        timestamp: new Date().toISOString(),
      },
    });
  } catch (error) {
    console.error("Error in technical overview endpoint:", error);
    return res.error("Failed to retrieve technical overview data", 500, {
      type: "database_error",
      timeframe: req.query.timeframe || "daily",
      error: error.message
    });
  }
});

// Get technical data for a specific symbol
router.get("/data/:symbol", async (req, res) => {
  const { symbol } = req.params;
  console.log(`📊 [TECHNICAL] Fetching technical data for ${symbol}`);

  try {
    // Check if table exists
    const tableExists = await query(
      `
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'technicals_daily'
      );
    `,
      []
    );

    if (!tableExists.rows[0].exists) {
      console.log(`Technical data table not found for symbol ${symbol}`);
      
      return res.error(`Technical data table not found for symbol ${symbol}`, 404, {
        type: "table_not_found",
        symbol: symbol.toUpperCase(),
        error: "No technical data table available",
        troubleshooting: {
          "Database Connection": "Verify technicals_daily table exists",
          "Data Population": "Check if technical data has been populated for this symbol",
          "Symbol Validation": "Ensure symbol is valid and active"
        }
      });
    }

    // Get latest technical data for the symbol
    const dataQuery = `
      SELECT 
        t.symbol,
        t.date,
        p.open,
        p.high,
        p.low,
        p.close,
        p.volume,
        t.rsi,
        t.macd,
        t.macd_signal,
        t.macd_hist,
        t.sma_20,
        t.sma_50,
        t.ema_4,
        t.ema_9,
        t.ema_21,
        t.bbands_upper,
        t.bbands_lower,
        t.bbands_middle,
        t.adx,
        t.plus_di,
        t.minus_di,
        t.atr,
        t.mfi,
        t.roc,
        t.mom
      FROM technicals_daily t
      JOIN price_daily p ON t.symbol = p.symbol AND t.date = p.date
      WHERE t.symbol = $1
      ORDER BY t.date DESC
      LIMIT 1
    `;

    const result = await query(dataQuery, [symbol.toUpperCase()]);

    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: `No technical data found for symbol ${symbol}`,
      });
    }

    res.success({data: result.rows[0],
      symbol: symbol.toUpperCase(),
    });
  } catch (error) {
    console.error(
      `❌ [TECHNICAL] Error fetching technical data for ${symbol}:`,
      error
    );
    console.log(`Database error retrieving technical data for ${symbol}: ${error.message}`);

    return res.error(`Failed to retrieve technical data for ${symbol}`, 500, {
      type: "database_error",
      symbol: symbol.toUpperCase(),
      error: error.message,
      troubleshooting: {
        "Database Connection": "Check database connectivity",
        "Query Execution": "Verify technicals_daily table and data integrity",
        "Symbol Data": `Ensure technical data exists for symbol: ${symbol}`,
        "Error Details": error.message
      }
    });
  }
});

// Get technical indicators for a specific symbol
router.get("/indicators/:symbol", async (req, res) => {
  const { symbol } = req.params;
  console.log(`📈 [TECHNICAL] Fetching technical indicators for ${symbol}`);

  try {
    // Check if table exists
    const tableExists = await query(
      `
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'technicals_daily'
      );
    `,
      []
    );

    if (!tableExists || !tableExists.rows || !tableExists.rows[0].exists) {
      console.error(`Technical data table not found for symbol ${symbol}`);
      return res.error("Technical indicators not available", 503, {
        message: "Technical data table does not exist",
        symbol: symbol.toUpperCase(),
        service: "technical-indicators"
      });
    }

    // Get latest technical indicators for the symbol
    const indicatorsQuery = `
      SELECT 
        symbol,
        date,
        rsi,
        macd,
        macd_signal,
        macd_hist,
        sma_20,
        sma_50,
        ema_4,
        ema_9,
        ema_21,
        bbands_upper,
        bbands_lower,
        bbands_middle,
        adx,
        plus_di,
        minus_di,
        atr,
        mfi,
        roc,
        mom
      FROM technicals_daily
      WHERE symbol = $1
      ORDER BY date DESC
      LIMIT 30
    `;

    const result = await query(indicatorsQuery, [symbol.toUpperCase()]);

    if (!result || !result.rows || result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: `No technical indicators found for symbol ${symbol}`,
      });
    }

    res.success({data: result.rows,
      count: result.rows.length,
      symbol: symbol.toUpperCase(),
    });
  } catch (error) {
    console.error(
      `❌ [TECHNICAL] Error fetching technical indicators for ${symbol}:`,
      error
    );
    return res.error(`Failed to retrieve technical indicators for ${symbol}`, 500, {
      type: "database_error",
      symbol: symbol.toUpperCase(),
      error: error.message
    });
  }
});

// Get technical history for a specific symbol
router.get("/history/:symbol", async (req, res) => {
  const { symbol } = req.params;
  const { days = 90 } = req.query;
  console.log(
    `📊 [TECHNICAL] Fetching technical history for ${symbol} (${days} days)`
  );

  try {
    // Check if table exists
    const tableExists = await query(
      `
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'technicals_daily'
      );
    `,
      []
    );

    if (!tableExists.rows[0].exists) {
      console.error(`Technical data table not found for symbol ${symbol}`);
      return res.error("Technical history not available", 503, {
        message: "Technical data table does not exist",
        symbol: symbol.toUpperCase(),
        service: "technical-history"
      });
    }

    // Get technical history for the symbol
    const historyQuery = `
      SELECT 
        t.symbol,
        t.date,
        p.open,
        p.high,
        p.low,
        p.close,
        p.volume,
        t.rsi,
        t.macd,
        t.macd_signal,
        t.macd_hist,
        t.sma_20,
        t.sma_50,
        t.ema_4,
        t.ema_9,
        t.ema_21,
        t.bbands_upper,
        t.bbands_lower,
        t.bbands_middle,
        t.adx,
        t.plus_di,
        t.minus_di,
        t.atr,
        t.mfi,
        t.roc,
        t.mom
      FROM technicals_daily t
      JOIN price_daily p ON t.symbol = p.symbol AND t.date = p.date
      WHERE t.symbol = $1
        AND t.date >= CURRENT_DATE - INTERVAL '${days} days'
      ORDER BY t.date ASC
    `;

    const result = await query(historyQuery, [symbol.toUpperCase()]);

    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: `No technical history found for symbol ${symbol}`,
      });
    }

    res.success({data: result.rows,
      count: result.rows.length,
      symbol: symbol.toUpperCase(),
      period_days: days,
    });
  } catch (error) {
    console.error(
      `❌ [TECHNICAL] Error fetching technical history for ${symbol}:`,
      error
    );
    return res.error(`Failed to retrieve technical history for ${symbol}`, 500, {
      type: "database_error",
      symbol: symbol.toUpperCase(),
      period_days: parseInt(days),
      error: error.message
    });
  }
});

// Get support and resistance levels for a symbol
router.get("/support-resistance/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    const { timeframe = "daily" } = req.query;

    const validTimeframes = ["daily", "weekly", "monthly"];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({
        error: "Unsupported timeframe",
        message: `Supported timeframes: ${validTimeframes.join(", ")}, got: ${timeframe}`,
      });
    }

    const tableName = `technicals_${timeframe}`;

    // Check if table exists
    const tableExists = await query(
      `
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = $1
      );
    `,
      [tableName]
    );

    if (!tableExists.rows[0].exists) {
      console.log(
        `Technical data table for ${timeframe} timeframe not found for symbol ${symbol}`
      );
      return res.error(`Technical data table for ${timeframe} timeframe not found`, {
        symbol: symbol.toUpperCase(),
        timeframe,
        error: `No technical data available for ${symbol} on timeframe ${timeframe}`,
        support_levels: [],
        resistance_levels: [],
        current_price: null,
        last_updated: null,
      }, 404);
    }

    // Get recent price data and pivot points
    const pivotQuery = `
      SELECT 
        t.symbol,
        t.date,
        p.high,
        p.low,
        p.close,
        t.pivot_high,
        t.pivot_low,
        t.bbands_upper,
        t.bbands_lower,
        t.sma_20,
        t.sma_50,
        t.sma_200
      FROM ${tableName} t
      JOIN price_daily p ON t.symbol = p.symbol AND t.date = p.date
      WHERE t.symbol = $1
      ORDER BY t.date DESC
      LIMIT 50
    `;

    const result = await query(pivotQuery, [symbol.toUpperCase()]);

    if (result.rows.length === 0) {
      return res
        .status(404)
        .json({ error: "No technical data found for symbol" });
    }

    // Calculate support and resistance levels
    const latest = result.rows[0];
    const recentData = result.rows.slice(0, 20); // Last 20 periods

    const highs = recentData.map((d) => d.high).filter((h) => h !== null)
    const lows = recentData.map((d) => d.low).filter((l) => l !== null)

    const resistance = Math.max(...highs);
    const support = Math.min(...lows);

    res.success({
      symbol: symbol.toUpperCase(),
      timeframe,
      current_price: latest.close,
      support_levels: [
        { level: support, type: "dynamic", strength: "strong" },
        { level: latest.bbands_lower, type: "bollinger", strength: "medium" },
        { level: latest.sma_200, type: "moving_average", strength: "strong" },
      ],
      resistance_levels: [
        { level: resistance, type: "dynamic", strength: "strong" },
        { level: latest.bbands_upper, type: "bollinger", strength: "medium" },
        { level: latest.sma_50, type: "moving_average", strength: "medium" },
      ],
      last_updated: latest.date,
    });
  } catch (error) {
    console.error("Error fetching support resistance levels:", error);
    return res.error("Failed to fetch support and resistance levels", 500, {
      symbol: req.params.symbol.toUpperCase(),
      timeframe: req.query.timeframe || "daily",
      error: error.message,
      support_levels: [],
      resistance_levels: [],
      current_price: null,
      last_updated: null,
    });
  }
});

// Get technical data with filtering and pagination
router.get("/data", async (req, res) => {
  const {
    symbol,
    timeframe = "daily",
    limit = 25,
    page = 1,
    startDate,
    endDate,
    sortBy = "date",
    sortOrder = "desc",
  } = req.query;

  console.log(`📊 [TECHNICAL] Fetching technical data with params:`, {
    symbol,
    timeframe,
    limit,
    page,
    startDate,
    endDate,
    sortBy,
    sortOrder,
  });

  try {
    const offset = (parseInt(page) - 1) * parseInt(limit);
    const maxLimit = Math.min(parseInt(limit), 200);

    // Build WHERE clause
    let whereClause = "WHERE 1=1";
    const params = [];
    let paramIndex = 1;

    // Symbol filter
    if (symbol && symbol.trim()) {
      whereClause += ` AND symbol = $${paramIndex}`;
      params.push(symbol.toUpperCase());
      paramIndex++;
    }

    // Date filters
    if (startDate) {
      whereClause += ` AND date >= $${paramIndex}`;
      params.push(startDate);
      paramIndex++;
    }

    if (endDate) {
      whereClause += ` AND date <= $${paramIndex}`;
      params.push(endDate);
      paramIndex++;
    }

    // Determine table name based on timeframe
    const validTimeframes = ["daily", "weekly", "monthly"];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({
        success: false,
        error: "Invalid timeframe",
        message: `Supported timeframes: ${validTimeframes.join(", ")}, got: ${timeframe}`,
      });
    }

    const tableName = `technicals_${timeframe}`;

    // Check if table exists
    const tableExists = await query(
      `
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = $1
      );
    `,
      [tableName]
    );

    if (!tableExists.rows[0].exists) {
      console.log(
        `Technical data table for ${timeframe} timeframe not found`
      );
      
      return res.status(503).json({
        success: false,
        error: "Service unavailable",
        message: `Technical data table for ${timeframe} timeframe does not exist`,
        type: "table_not_found",
        timeframe,
        filters: {
          symbol: symbol || null,
          startDate: startDate || null,
          endDate: endDate || null
        },
        troubleshooting: {
          "Database Connection": "Verify technical data tables exist",
          "Data Population": "Check if technical data has been loaded",
          "Table Schema": `Expected table: technicals_${timeframe}`,
          "Supported Timeframes": "daily, weekly, monthly"
        }
      });
    }

    // Get total count
    const countQuery = `
      SELECT COUNT(*) as total
      FROM ${tableName} t
      JOIN price_daily p ON t.symbol = p.symbol AND t.date = p.date
      ${whereClause}
    `;
    const countResult = await query(countQuery, params);
    const total = parseInt(countResult.rows[0].total);

    // Validate sortBy field
    const validSortFields = [
      "date",
      "symbol",
      "open",
      "high",
      "low",
      "close",
      "volume",
      "rsi",
      "macd",
      "macd_signal",
      "macd_hist",
      "sma_20",
      "sma_50",
      "ema_4",
      "ema_9",
      "ema_21",
      "bbands_upper",
      "bbands_lower",
      "bbands_middle",
    ];
    const safeSortBy = validSortFields.includes(sortBy) ? sortBy : "date";
    const safeSortOrder = sortOrder.toLowerCase() === "asc" ? "ASC" : "DESC";

    // Get technical data
    const dataQuery = `
      SELECT 
        t.symbol,
        t.date,
        p.open,
        p.high,
        p.low,
        p.close,
        p.volume,
        t.rsi,
        t.macd,
        t.macd_signal,
        t.macd_hist,
        t.sma_10,
        t.sma_20,
        t.sma_50,
        t.sma_150,
        t.sma_200,
        t.ema_4,
        t.ema_9,
        t.ema_21,
        t.bbands_upper,
        t.bbands_lower,
        t.bbands_middle,
        t.adx,
        t.plus_di,
        t.minus_di,
        t.atr,
        t.mfi,
        t.roc,
        t.mom,
        t.ad,
        t.cmf,
        t.td_sequential,
        t.td_combo,
        t.marketwatch,
        t.dm,
        t.pivot_high,
        t.pivot_low,
        t.pivot_high_triggered,
        t.pivot_low_triggered
      FROM ${tableName} t
      JOIN price_daily p ON t.symbol = p.symbol AND t.date = p.date
      ${whereClause}
      ORDER BY ${safeSortBy.startsWith('t.') || safeSortBy.startsWith('p.') ? safeSortBy : (safeSortBy === 'symbol' || safeSortBy === 'date' ? 't.' + safeSortBy : (safeSortBy.includes('open') || safeSortBy.includes('high') || safeSortBy.includes('low') || safeSortBy.includes('close') || safeSortBy.includes('volume') ? 'p.' + safeSortBy : 't.' + safeSortBy))} ${safeSortOrder}
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `;

    const finalParams = [...params, maxLimit, offset];
    const dataResult = await query(dataQuery, finalParams);

    const totalPages = Math.ceil(total / maxLimit);

    console.log(
      `✅ [TECHNICAL] Data query completed: ${dataResult.rows.length} results, total: ${total}`
    );

    if (
      !dataResult ||
      !Array.isArray(dataResult.rows) ||
      dataResult.rows.length === 0
    ) {
      return res.success({
        data: [],
        total: 0,
        pagination: {
          page: parseInt(page),
          limit: maxLimit,
          total: 0,
          totalPages: 0,
          hasNext: false,
          hasPrev: false,
        },
        filters: {
          symbol: symbol || null,
          timeframe,
          startDate: startDate || null,
          endDate: endDate || null,
        },
        sorting: {
          sortBy: safeSortBy,
          sortOrder: safeSortOrder,
        },
      });
    }

    res.success({data: dataResult.rows,
      total: total,
      pagination: {
        page: parseInt(page),
        limit: maxLimit,
        total,
        totalPages,
        hasNext: parseInt(page) < totalPages,
        hasPrev: parseInt(page) > 1,
      },
      filters: {
        symbol: symbol || null,
        timeframe,
        startDate: startDate || null,
        endDate: endDate || null,
      },
      sorting: {
        sortBy: safeSortBy,
        sortOrder: safeSortOrder,
      },
    });
  } catch (error) {
    console.error("❌ [TECHNICAL] Technical data error:", error);
    
    return res.status(500).json({
      success: false,
      error: "Failed to retrieve filtered technical data",
      message: error.message,
      type: "database_error",
      timeframe,
      filters: {
        symbol: symbol || null,
        startDate: startDate || null,
        endDate: endDate || null
      },
      troubleshooting: {
        "Database Connection": "Check database connectivity",
        "Query Execution": "Verify technical data query and parameters",
        "Data Integrity": "Check for corrupted or missing technical data",
        "Filter Validation": "Ensure filter parameters are valid",
        "Error Details": error.message
      }
    });
  }
});

// Pattern Recognition Endpoint - with query parameter support
router.get("/patterns", async (req, res) => {
  const { symbol } = req.query;
  
  if (!symbol) {
    return res.status(400).json({
      success: false,
      error: "Missing required parameter",
      message: "Symbol parameter is required. Use ?symbol=AAPL"
    });
  }

  const { timeframe = "1D", limit = 10 } = req.query;

  console.log(
    `🔍 [PATTERNS] Analyzing patterns for ${symbol} on ${timeframe} timeframe (query param)`
  );

  try {
    // Define pattern analysis logic
    const patternAnalysis = await analyzePatterns(symbol, timeframe, limit);

    res.success({
      symbol: symbol.toUpperCase(),
      timeframe,
      patterns: patternAnalysis.patterns,
      summary: patternAnalysis.summary,
      confidence_score: patternAnalysis.overallConfidence,
      last_updated: new Date().toISOString(),
    });
  } catch (error) {
    console.error(
      `❌ [PATTERNS] Error analyzing patterns for ${symbol}:`,
      error
    );

    return res.error(`Failed to analyze patterns for ${symbol}`, 500, {
      type: "pattern_analysis_error",
      symbol: symbol.toUpperCase(),
      timeframe,
      error: error.message,
      troubleshooting: {
        "Data Availability": "Verify sufficient price data exists for pattern analysis",
        "Analysis Engine": "Check technical analysis algorithms and data processing",
        "Symbol Validation": "Ensure symbol is valid and has trading history",
        "Error Details": error.message
      }
    });
  }
});

// Pattern Recognition Endpoint - original path parameter version
router.get("/patterns/:symbol", async (req, res) => {
  const { symbol } = req.params;
  const { timeframe = "1D", limit = 10 } = req.query;

  console.log(
    `🔍 [PATTERNS] Analyzing patterns for ${symbol} on ${timeframe} timeframe`
  );

  try {
    // Define pattern analysis logic
    const patternAnalysis = await analyzePatterns(symbol, timeframe, limit);

    res.success({symbol: symbol.toUpperCase(),
      timeframe,
      patterns: patternAnalysis.patterns,
      summary: patternAnalysis.summary,
      confidence_score: patternAnalysis.overallConfidence,
      last_updated: new Date().toISOString(),
    });
  } catch (error) {
    console.error(
      `❌ [PATTERNS] Error analyzing patterns for ${symbol}:`,
      error
    );

    return res.error(`Failed to analyze patterns for ${symbol}`, 500, {
      type: "pattern_analysis_error",
      symbol: symbol.toUpperCase(),
      timeframe,
      error: error.message,
      troubleshooting: {
        "Data Availability": "Verify sufficient price data exists for pattern analysis",
        "Analysis Engine": "Check technical analysis algorithms and data processing",
        "Symbol Validation": "Ensure symbol is valid and has trading history",
        "Error Details": error.message
      }
    });
  }
});

// Pattern Analysis Algorithm
async function analyzePatterns(symbol, timeframe, limit) {
  // Get historical price data for pattern analysis
  const priceData = await getPriceDataForPatterns(symbol, timeframe);

  const patterns = [];
  const bullishPatterns = [
    "double_bottom",
    "cup_and_handle",
    "bullish_flag",
    "ascending_triangle",
  ];
  const bearishPatterns = [
    "double_top",
    "head_and_shoulders",
    "bearish_flag",
    "descending_triangle",
  ];

  // Pattern detection would require actual implementation with real data
  // No fallback pattern generation - return empty if no real data available
  if (!priceData || !priceData.priceHistory || priceData.priceHistory.length < 20) {
    throw new Error('Insufficient price data for pattern analysis');
  }
  
  // Real pattern analysis would go here - for now return empty patterns
  // when no valid patterns are detected

  // Sort patterns by confidence descending
  patterns.sort((a, b) => b.confidence - a.confidence);

  const bullishCount = patterns.filter((p) => p.direction === "bullish").length;
  const bearishCount = patterns.filter((p) => p.direction === "bearish").length;
  const avgConfidence =
    patterns.reduce((sum, p) => sum + p.confidence, 0) / patterns.length;

  return {
    patterns: patterns.slice(0, limit),
    summary: {
      total_patterns: patterns.length,
      bullish_patterns: bullishCount,
      bearish_patterns: bearishCount,
      average_confidence: Math.round(avgConfidence * 100) / 100,
      market_sentiment: bullishCount > bearishCount ? "bullish" : "bearish",
    },
    overallConfidence: Math.round(avgConfidence * 100) / 100,
  };
}

// Get price data for pattern analysis
async function getPriceDataForPatterns(symbol, _timeframe) {
  try {
    // Try to get real price data
    const tableName = "technicals_daily";
    const priceQuery = `
      SELECT p.close, p.high, p.low, t.date
      FROM ${tableName} t
      JOIN price_daily p ON t.symbol = p.symbol AND t.date = p.date
      WHERE t.symbol = $1
      ORDER BY t.date DESC
      LIMIT 50
    `;

    const result = await query(priceQuery, [symbol.toUpperCase()]);

    if (result.rows.length > 0) {
      const latest = result.rows[0];
      const prices = result.rows.map((row) => ({
        close: row.close,
        high: row.high,
        low: row.low,
        date: row.date,
      }));

      return {
        currentPrice: latest.close,
        priceHistory: prices,
        supportLevels: calculateSupport(prices),
        resistanceLevels: calculateResistance(prices),
      };
    }
  } catch (error) {
    console.error("Error getting price data for patterns:", error);
    throw new Error('Unable to retrieve price data for pattern analysis');
  }
  
  // If we reach here, no real data was available
  throw new Error('No price data available for pattern analysis');
}

// Calculate support levels from price history
function calculateSupport(prices) {
  const lows = prices.map((p) => p.low).filter((l) => l !== null)
  const minLow = Math.min(...lows);
  const avgLow = lows.reduce((sum, low) => sum + low, 0) / lows.length;

  return [minLow, avgLow * 0.98];
}

// Calculate resistance levels from price history
function calculateResistance(prices) {
  const highs = prices.map((p) => p.high).filter((h) => h !== null)
  const maxHigh = Math.max(...highs);
  const avgHigh = highs.reduce((sum, high) => sum + high, 0) / highs.length;

  return [maxHigh, avgHigh * 1.02];
}

// Calculate target price based on pattern
function calculateTargetPrice(currentPrice, isBullish, confidence) {
  const multiplier = isBullish ? 1 + confidence * 0.1 : 1 - confidence * 0.1;
  return Math.round(currentPrice * multiplier * 100) / 100;
}

// Calculate stop loss price
function calculateStopLoss(currentPrice, isBullish) {
  const stopMultiplier = isBullish ? 0.95 : 1.05;
  return Math.round(currentPrice * stopMultiplier * 100) / 100;
}

// Removed fallback price history generation - use real data only

// Technical trends endpoint
router.get("/trends/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    const { period = "1y" } = req.query;
    console.log(`📈 Technical trends requested for ${symbol}, period: ${period}`);

    // Technical trends analysis requires real data - no fallback generation
    return res.status(503).json({
      success: false,
      error: "Service unavailable",
      message: "Technical trends analysis is not available - requires real market data",
      symbol: symbol.toUpperCase(),
      period: period
    });

    // This code is unreachable due to early return above

  } catch (error) {
    console.error("Technical trends error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch technical trends",
      message: error.message
    });
  }
});

// Technical support levels endpoint
router.get("/support/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    const { lookback = 90 } = req.query;
    console.log(`📊 Support levels requested for ${symbol}, lookback: ${lookback} days`);

    // Support level analysis requires real market data - no fallback generation
    return res.status(503).json({
      success: false,
      error: "Service unavailable",
      message: "Support level analysis is not available - requires real market data",
      symbol: symbol.toUpperCase(),
      lookback_days: parseInt(lookback)
    });

    // This code is unreachable due to early return above

  } catch (error) {
    console.error("Technical support error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch support levels",
      message: error.message
    });
  }
});

// Technical resistance levels endpoint
router.get("/resistance/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    const { lookback = 90 } = req.query;
    console.log(`📊 Resistance levels requested for ${symbol}, lookback: ${lookback} days`);

    // Resistance level analysis requires real market data - no fallback generation
    return res.status(503).json({
      success: false,
      error: "Service unavailable",
      message: "Resistance level analysis is not available - requires real market data",
      symbol: symbol.toUpperCase(),
      lookback_days: parseInt(lookback)
    });

    // This code is unreachable due to early return above

  } catch (error) {
    console.error("Technical resistance error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch resistance levels", 
      message: error.message
    });
  }
});

module.exports = router;
