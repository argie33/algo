const express = require("express");

const { query } = require("../utils/database");

const router = express.Router();

// Get buy signals
router.get("/buy", async (req, res) => {
  try {
    const timeframe = req.query.timeframe || "daily";
    const limit = parseInt(req.query.limit) || 25;
    const page = parseInt(req.query.page) || 1;
    const offset = (page - 1) * limit;

    // Validate timeframe
    const validTimeframes = ["daily", "weekly", "monthly"];
    if (!validTimeframes.includes(timeframe)) {
      return res.error("Invalid timeframe. Must be daily, weekly, or monthly", 400);
    }

    const tableName = `buy_sell_${timeframe}`;

    const buySignalsQuery = `
      SELECT 
        bs.symbol,
        cp.company_name,
        cp.sector,
        bs.signal,
        bs.date,
        md.current_price as current_price,
        md.market_cap,
        km.trailing_pe,
        km.dividend_yield
      FROM ${tableName} bs
      JOIN company_profile cp ON bs.symbol = cp.ticker
      LEFT JOIN market_data md ON bs.symbol = md.ticker
      LEFT JOIN key_metrics km ON bs.symbol = km.ticker
      WHERE bs.signal IS NOT NULL 
        AND bs.signal != '' 
        AND bs.signal IN ('BUY', 'SELL', 'HOLD')
      ORDER BY bs.symbol ASC, bs.signal DESC, bs.date DESC
      LIMIT $1 OFFSET $2
    `;

    const countQuery = `
      SELECT COUNT(*) as total
      FROM ${tableName} bs
      WHERE bs.signal IS NOT NULL 
        AND bs.signal != '' 
        AND bs.signal IN ('BUY', 'SELL', 'HOLD')
    `;

    const [signalsResult, countResult] = await Promise.all([
      query(buySignalsQuery, [limit, offset]),
      query(countQuery),
    ]);

    // Add null checking for database availability
    if (!signalsResult || !signalsResult.rows || !countResult || !countResult.rows) {
      console.warn("Buy signals query returned null result, database may be unavailable");
      return res.error("Trading signals temporarily unavailable - database connection issue", 500, {
        type: "service_unavailable",
        data: [],
        timeframe
      });
    }

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    // Transform data to camelCase - signal is text ('BUY', 'SELL', 'HOLD')
    const transformedData = signalsResult.rows.map(row => ({
      symbol: row.symbol,
      companyName: row.company_name,
      sector: row.sector,
      signal: row.signal,
      date: row.date,
      currentPrice: row.current_price,
      marketCap: row.market_cap,
      trailingPe: row.trailing_pe,
      dividendYield: row.dividend_yield,
    }));

    // Handle empty results with success response
    if (transformedData.length === 0) {
      return res.success({data: [],
        pagination: {
          total,
          page,
          limit,
          totalPages,
          hasNext: page < totalPages,
          hasPrev: page > 1,
        },
        timeframe,
        message: "No buy signals found",
      });
    }

    res.success({data: transformedData,
      timeframe,
      signal_type: "buy",
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1,
      },
    });
  } catch (error) {
    console.error("Error fetching buy signals:", error);
    return res.error("Failed to fetch buy signals", 500, {
      details: error.message
    });
  }
});

// Get sell signals
router.get("/sell", async (req, res) => {
  try {
    const timeframe = req.query.timeframe || "daily";
    const limit = parseInt(req.query.limit) || 25;
    const page = parseInt(req.query.page) || 1;
    const offset = (page - 1) * limit;

    // Validate timeframe
    const validTimeframes = ["daily", "weekly", "monthly"];
    if (!validTimeframes.includes(timeframe)) {
      return res.error("Invalid timeframe. Must be daily, weekly, or monthly", 400);
    }

    const tableName = `buy_sell_${timeframe}`;

    const sellSignalsQuery = `
      SELECT 
        bs.symbol,
        cp.company_name,
        cp.sector,
        bs.signal,
        bs.date,
        md.current_price as current_price,
        md.market_cap,
        km.trailing_pe,
        km.dividend_yield
      FROM ${tableName} bs
      JOIN company_profile cp ON bs.symbol = cp.ticker
      LEFT JOIN market_data md ON bs.symbol = md.ticker
      LEFT JOIN key_metrics km ON bs.symbol = km.ticker
      WHERE bs.signal IS NOT NULL 
        AND bs.signal != '' 
        AND bs.signal IN ('BUY', 'SELL', 'HOLD')
      ORDER BY bs.symbol ASC, bs.signal ASC, bs.date DESC
      LIMIT $1 OFFSET $2
    `;

    const countQuery = `
      SELECT COUNT(*) as total
      FROM ${tableName} bs
      WHERE bs.signal IS NOT NULL 
        AND bs.signal != '' 
        AND bs.signal IN ('BUY', 'SELL', 'HOLD')
    `;

    const [signalsResult, countResult] = await Promise.all([
      query(sellSignalsQuery, [limit, offset]),
      query(countQuery),
    ]);

    // Add null checking for database availability
    if (!signalsResult || !signalsResult.rows || !countResult || !countResult.rows) {
      console.warn("Sell signals query returned null result, database may be unavailable");
      return res.error("Sell signals temporarily unavailable - database connection issue", 500, {
        type: "service_unavailable",
        data: [],
        timeframe
      });
    }

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    // Transform data to camelCase - signal is text ('BUY', 'SELL', 'HOLD')
    const transformedData = signalsResult.rows.map(row => ({
      symbol: row.symbol,
      companyName: row.company_name,
      sector: row.sector,
      signal: row.signal,
      date: row.date,
      currentPrice: row.current_price,
      marketCap: row.market_cap,
      trailingPe: row.trailing_pe,
      dividendYield: row.dividend_yield,
    }));

    // Handle empty results with success response
    if (transformedData.length === 0) {
      return res.success({data: [],
        pagination: {
          total,
          page,
          limit,
          totalPages,
          hasNext: page < totalPages,
          hasPrev: page > 1,
        },
        timeframe,
        message: "No sell signals found",
      });
    }

    res.success({data: transformedData,
      timeframe,
      signal_type: "sell",
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1,
      },
    });
  } catch (error) {
    console.error("Error fetching sell signals:", error);
    return res.error("Failed to fetch sell signals", 500, {
      details: error.message
    });
  }
});

// Get recent signals
router.get("/recent", async (req, res) => {
  try {
    const { limit = 10, hours = 24 } = req.query;
    const timeframe = req.query.timeframe || "daily";

    console.log(`🔔 Recent signals requested, limit: ${limit}, hours: ${hours}`);

    // Validate timeframe
    const validTimeframes = ["daily", "weekly", "monthly"];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({
        success: false,
        error: "Invalid timeframe. Must be daily, weekly, or monthly"
      });
    }

    const tableName = `buy_sell_${timeframe}`;
    const hoursAgo = new Date();
    hoursAgo.setHours(hoursAgo.getHours() - parseInt(hours));

    const result = await query(
      `
      SELECT 
        bs.symbol,
        cp.company_name,
        cp.sector,
        bs.signal,
        bs.date,
        md.current_price as current_price,
        md.market_cap,
        km.trailing_pe,
        km.dividend_yield
      FROM ${tableName} bs
      JOIN company_profile cp ON bs.symbol = cp.ticker
      LEFT JOIN market_data md ON bs.symbol = md.ticker
      LEFT JOIN key_metrics km ON bs.symbol = km.ticker
      WHERE bs.signal IS NOT NULL 
        AND bs.signal != '' 
        AND bs.signal IN ('BUY', 'SELL', 'HOLD')
        AND bs.date >= $2
      ORDER BY bs.date DESC, bs.symbol ASC
      LIMIT $1
      `,
      [parseInt(limit), hoursAgo.toISOString()]
    );

    // Transform data to camelCase
    const transformedData = result.rows.map(row => ({
      symbol: row.symbol,
      companyName: row.company_name,
      sector: row.sector,
      signal: row.signal,
      date: row.date,
      currentPrice: row.current_price,
      marketCap: row.market_cap,
      trailingPe: row.trailing_pe,
      dividendYield: row.dividend_yield,
    }));

    res.json({
      success: true,
      data: transformedData,
      total: transformedData.length,
      filters: {
        limit: parseInt(limit),
        hours: parseInt(hours),
        timeframe: timeframe,
        since: hoursAgo.toISOString()
      },
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error("Recent signals error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch recent signals",
      details: error.message
    });
  }
});

// Get all signals (default route)
router.get("/", async (req, res) => {
  try {
    const timeframe = req.query.timeframe || "daily";
    const limit = parseInt(req.query.limit) || 25;
    const page = parseInt(req.query.page) || 1;
    const _offset = (page - 1) * limit;

    // Validate timeframe
    const validTimeframes = ["daily", "weekly", "monthly"];
    if (!validTimeframes.includes(timeframe)) {
      return res.error("Invalid timeframe. Must be daily, weekly, or monthly", 400);
    }

    const tableName = `buy_sell_${timeframe}`;

    // Get both buy and sell signals
    const [buySignalsQuery, sellSignalsQuery, countQuery] = [
      `
      SELECT 
        bs.symbol,
        cp.company_name,
        cp.sector,
        bs.signal,
        bs.date,
        md.current_price as current_price,
        md.market_cap,
        km.trailing_pe,
        km.dividend_yield,
        'buy' as signal_type
      FROM ${tableName} bs
      JOIN company_profile cp ON bs.symbol = cp.ticker
      LEFT JOIN market_data md ON bs.symbol = md.ticker
      LEFT JOIN key_metrics km ON bs.symbol = km.ticker
      WHERE bs.signal IS NOT NULL 
        AND bs.signal != '' 
        AND bs.signal IN ('BUY', 'SELL', 'HOLD')
      ORDER BY bs.signal DESC, bs.date DESC
      LIMIT $1
      `,
      `
      SELECT 
        bs.symbol,
        cp.company_name,
        cp.sector,
        bs.signal,
        bs.date,
        md.current_price as current_price,
        md.market_cap,
        km.trailing_pe,
        km.dividend_yield,
        'sell' as signal_type
      FROM ${tableName} bs
      JOIN company_profile cp ON bs.symbol = cp.ticker
      LEFT JOIN market_data md ON bs.symbol = md.ticker
      LEFT JOIN key_metrics km ON bs.symbol = km.ticker
      WHERE bs.signal IS NOT NULL 
        AND bs.signal != '' 
        AND bs.signal IN ('BUY', 'SELL', 'HOLD')
      ORDER BY bs.signal ASC, bs.date DESC
      LIMIT $1
      `,
      `
      SELECT COUNT(*) as total
      FROM ${tableName} bs
      WHERE bs.signal IS NOT NULL 
        AND bs.signal != ''
      `
    ];

    const [buyResult, sellResult, countResult] = await Promise.all([
      query(buySignalsQuery, [Math.ceil(limit/2)]),
      query(sellSignalsQuery, [Math.floor(limit/2)]),
      query(countQuery),
    ]);

    // Add null checking for database availability
    if (!buyResult || !buyResult.rows || !sellResult || !sellResult.rows || !countResult || !countResult.rows) {
      console.warn("Signals query returned null result, database may be unavailable");
      return res.error("Trading signals temporarily unavailable - database connection issue", 500, {
        type: "service_unavailable",
        data: {
          buy_signals: [],
          sell_signals: [],
          summary: {
            total_buy: 0,
            total_sell: 0,
            total_signals: 0
          }
        },
        timeframe
      });
    }

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    // Transform data to camelCase - signal is text ('BUY', 'SELL', 'HOLD')
    const buySignals = buyResult.rows.map(row => ({
      symbol: row.symbol,
      companyName: row.company_name,
      sector: row.sector,
      signal: row.signal,
      date: row.date,
      currentPrice: row.current_price,
      marketCap: row.market_cap,
      trailingPe: row.trailing_pe,
      dividendYield: row.dividend_yield,
      signalType: row.signal_type,
    }));

    const sellSignals = sellResult.rows.map(row => ({
      symbol: row.symbol,
      companyName: row.company_name,
      sector: row.sector,
      signal: row.signal,
      date: row.date,
      currentPrice: row.current_price,
      marketCap: row.market_cap,
      trailingPe: row.trailing_pe,
      dividendYield: row.dividend_yield,
      signalType: row.signal_type,
    }));

    res.success({data: {
        buy_signals: buySignals,
        sell_signals: sellSignals,
        summary: {
          total_buy: buySignals.length,
          total_sell: sellSignals.length,
          total_signals: buySignals.length + sellSignals.length
        }
      },
      timeframe,
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1,
      },
    });
  } catch (error) {
    console.error("Error fetching signals:", error);
    return res.error("Failed to fetch signals", 500, {
      details: error.message
    });
  }
});

// Get trading recommendations (comprehensive trading signals with analysis)
router.get("/recommendations", async (req, res) => {
  const { 
    limit = 20, 
    type = "all", 
    risk_level = "all",
    min_score = 0,
    sector
  } = req.query;

  console.log(`📈 Trading recommendations requested - type: ${type}, risk: ${risk_level}, limit: ${limit}`);

  return res.status(501).json({
    success: false,
    error: "Trading recommendations not available",
    message: "Trading recommendations require integration with institutional research and algorithmic trading data providers",
    details: "This endpoint requires institutional research data integration and multi-factor quantitative models",
    troubleshooting: {
      suggestion: "Trading recommendations require professional trading data integration",
      required_setup: [
        "Professional trading data feeds (Bloomberg, Refinitiv)",
        "Quantitative analysis algorithms",
        "Real-time technical indicator calculations",
        "Risk management scoring models",
        "Professional research analyst data"
      ],
      status: "Not implemented - requires institutional trading data integration"
    },
    filters: {
      type: type,
      risk_level: risk_level,
      min_score: parseInt(min_score),
      sector: sector || null,
      limit: parseInt(limit)
    },
    timestamp: new Date().toISOString()
  });
});

// Note: Helper functions removed as recommendations endpoint returns proper error response

// Momentum trading signals endpoint
router.get("/momentum", async (req, res) => {
  const { 
    symbol, 
    timeframe = "daily", 
    strength = "all",
    limit = 50, 
    page = 1,
    sortBy = "momentum_score",
    sortOrder = "desc"
  } = req.query;
  
  console.log(`📈 Momentum signals requested - symbol: ${symbol || 'all'}, timeframe: ${timeframe}, strength: ${strength}`);
  
  return res.status(501).json({
    success: false,
    error: "Momentum signals not available",
    message: "Momentum signals require integration with real-time technical analysis data providers",
    details: "This endpoint requires real-time technical indicator calculations, historical price/volume data feeds, advanced momentum detection algorithms, multi-timeframe analysis capabilities, and professional technical analysis infrastructure",
    troubleshooting: {
      suggestion: "Momentum signals require professional technical analysis data integration",
      required_setup: [
        "Real-time market data feeds (Bloomberg, Alpha Vantage, Polygon)",
        "Technical indicator calculation engine",
        "Multi-timeframe data aggregation",
        "Momentum scoring algorithms",
        "Signal strength classification models"
      ],
      status: "Not implemented - requires professional technical analysis integration"
    },
    filters: {
      symbol: symbol || "all",
      timeframe: timeframe,
      strength: strength,
      limit: parseInt(limit),
      page: parseInt(page),
      sortBy: sortBy,
      sortOrder: sortOrder
    },
    valid_parameters: {
      timeframe: ["intraday", "daily", "weekly", "monthly"],
      strength: ["all", "strong", "moderate", "weak"]
    },
    timestamp: new Date().toISOString()
  });
});

// Get trading alerts and signals
router.get("/alerts", async (req, res) => {
  try {
    const { 
      symbol, 
      type = "all", 
      severity = "all",
      status = "all",
      limit = 50,
      startDate,
      endDate
    } = req.query;

    console.log(`🚨 Trading alerts requested for symbol: ${symbol || 'all'}, type: ${type}, severity: ${severity}`);

    // Validate type
    const validTypes = ["all", "price", "volume", "technical", "fundamental", "news", "momentum", "reversal", "breakout"];
    if (!validTypes.includes(type)) {
      return res.status(400).json({
        success: false,
        error: "Invalid alert type. Must be one of: " + validTypes.join(", "),
        requested_type: type
      });
    }

    // Validate severity
    const validSeverities = ["all", "low", "medium", "high", "critical"];
    if (!validSeverities.includes(severity)) {
      return res.status(400).json({
        success: false,
        error: "Invalid severity. Must be one of: " + validSeverities.join(", "),
        requested_severity: severity
      });
    }

    // Validate status
    const validStatuses = ["all", "active", "triggered", "expired", "acknowledged"];
    if (!validStatuses.includes(status)) {
      return res.status(400).json({
        success: false,
        error: "Invalid status. Must be one of: " + validStatuses.join(", "),
        requested_status: status
      });
    }

    // Set default date range if not provided (last 24 hours)
    const defaultEndDate = new Date().toISOString();
    const defaultStartDate = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
    const finalStartDate = startDate || defaultStartDate;
    const finalEndDate = endDate || defaultEndDate;

    let whereClause = "WHERE 1=1";
    const queryParams = [];
    let paramCount = 0;

    if (symbol) {
      paramCount++;
      whereClause += ` AND symbol = $${paramCount}`;
      queryParams.push(symbol.toUpperCase());
    }

    if (type !== "all") {
      paramCount++;
      whereClause += ` AND alert_type = $${paramCount}`;
      queryParams.push(type);
    }

    if (severity !== "all") {
      paramCount++;
      whereClause += ` AND severity = $${paramCount}`;
      queryParams.push(severity);
    }

    if (status !== "all") {
      paramCount++;
      whereClause += ` AND status = $${paramCount}`;
      queryParams.push(status);
    }

    // Add date filtering
    paramCount++;
    whereClause += ` AND created_at >= $${paramCount}`;
    queryParams.push(finalStartDate);

    paramCount++;
    whereClause += ` AND created_at <= $${paramCount}`;
    queryParams.push(finalEndDate);

    // Add limit
    paramCount++;
    const limitClause = `LIMIT $${paramCount}`;
    queryParams.push(parseInt(limit));

    const alertsQuery = `
      SELECT 
        alert_id,
        symbol,
        alert_type,
        severity,
        status,
        title,
        description,
        trigger_price,
        current_price,
        trigger_condition,
        created_at,
        triggered_at,
        expires_at,
        acknowledged_at,
        metadata
      FROM trading_alerts
      ${whereClause}
      ORDER BY severity DESC, created_at DESC
      ${limitClause}
    `;

    const result = await query(alertsQuery, queryParams);

    if (!result || !result.rows || result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "No trading alerts found",
        message: "Trading alerts require integration with professional alert management systems",
        details: "No alerts found in trading_alerts table for the specified filters",
        troubleshooting: {
          suggestion: "Trading alerts require alert management system integration",
          required_setup: [
            "Trading alert management system",
            "Real-time price monitoring",
            "Technical analysis alert triggers",
            "Alert delivery and management infrastructure",
            "User alert preference management"
          ],
          status: "Database query returned no results"
        },
        filters: {
          symbol: symbol || 'all',
          type: type,
          severity: severity,
          status: status,
          limit: parseInt(limit),
          date_range: {
            start: finalStartDate,
            end: finalEndDate
          }
        },
        timestamp: new Date().toISOString()
      });
    }

    // Process database results
    const alertsData = result.rows;
    const totalAlerts = alertsData.length;

    const severityDistribution = {
      critical: alertsData.filter(a => a.severity === 'critical').length,
      high: alertsData.filter(a => a.severity === 'high').length,
      medium: alertsData.filter(a => a.severity === 'medium').length,
      low: alertsData.filter(a => a.severity === 'low').length
    };

    const statusDistribution = {
      active: alertsData.filter(a => a.status === 'active').length,
      triggered: alertsData.filter(a => a.status === 'triggered').length,
      expired: alertsData.filter(a => a.status === 'expired').length,
      acknowledged: alertsData.filter(a => a.acknowledged_at !== null).length
    };

    const typeDistribution = {};
    alertsData.forEach(alert => {
      typeDistribution[alert.alert_type] = (typeDistribution[alert.alert_type] || 0) + 1;
    });

    res.json({
      success: true,
      data: {
        alerts: alertsData,
        summary: {
          total_alerts: totalAlerts,
          active_alerts: statusDistribution.active,
          triggered_alerts: statusDistribution.triggered,
          severity_distribution: severityDistribution,
          status_distribution: statusDistribution,
          type_distribution: typeDistribution,
          symbols_covered: symbol ? 1 : new Set(alertsData.map(a => a.symbol)).size,
          time_range: {
            start: finalStartDate,
            end: finalEndDate
          }
        },
        filters: {
          symbol: symbol || 'all',
          type: type,
          severity: severity,
          status: status,
          limit: parseInt(limit)
        }
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Trading alerts error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch trading alerts",
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get social sentiment signals
router.get("/social", async (req, res) => {
  const {
    symbol,
    platform = "all",
    sentiment = "all", 
    timeframe = "24h",
    limit = 50,
    page = 1,
    sortBy = "timestamp",
    sortOrder = "desc"
  } = req.query;

  console.log(`📱 Social sentiment signals requested - symbol: ${symbol || 'all'}, platform: ${platform}, timeframe: ${timeframe}`);

  // Validate parameters
  const validPlatforms = ["all", "twitter", "reddit", "stocktwits", "discord", "telegram", "youtube"];
  const validSentiments = ["all", "bullish", "bearish", "neutral"];
  const validTimeframes = ["1h", "6h", "24h", "7d", "30d"];
  const validSortColumns = ["timestamp", "sentiment_score", "mention_count", "influence_score", "symbol"];

  if (!validPlatforms.includes(platform)) {
    return res.status(400).json({
      success: false,
      error: `Invalid platform. Must be one of: ${validPlatforms.join(', ')}`,
      validPlatforms
    });
  }

  if (!validSentiments.includes(sentiment)) {
    return res.status(400).json({
      success: false,
      error: `Invalid sentiment. Must be one of: ${validSentiments.join(', ')}`,
      validSentiments
    });
  }

  if (!validTimeframes.includes(timeframe)) {
    return res.status(400).json({
      success: false,
      error: `Invalid timeframe. Must be one of: ${validTimeframes.join(', ')}`,
      validTimeframes
    });
  }

  return res.status(501).json({
    success: false,
    error: "Social sentiment signals not available",
    message: "Social sentiment signals require integration with social media data providers and sentiment analysis services",
    details: "This endpoint requires:\n- Social media platform API integrations (Twitter, Reddit, StockTwits, Discord)\n- Natural language processing and sentiment analysis\n- Real-time social media data aggregation\n- Influence scoring and bot detection\n- Trending keyword and topic analysis",
    troubleshooting: {
      suggestion: "Social sentiment signals require social media data integration",
      required_setup: [
        "Social media platform APIs (Twitter, Reddit, StockTwits)",
        "Sentiment analysis ML models",
        "Real-time data streaming and aggregation",
        "Influence scoring algorithms",
        "Bot detection and spam filtering"
      ],
      status: "Not implemented - requires social media data integration"
    },
    filters: {
      symbol: symbol || "all",
      platform: platform,
      sentiment: sentiment,
      timeframe: timeframe,
      limit: parseInt(limit),
      page: parseInt(page),
      sortBy: sortBy,
      sortOrder: sortOrder
    },
    valid_parameters: {
      platform: validPlatforms,
      sentiment: validSentiments,
      timeframe: validTimeframes,
      sortBy: validSortColumns
    },
    timestamp: new Date().toISOString()
  });
});


router.get("/momentum/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    const { 
      timeframe = "daily", 
      strength = "all"
    } = req.query;
    
    console.log(`📈 Momentum signals requested for ${symbol} - timeframe: ${timeframe}, strength: ${strength}`);
    
    // Query momentum data from database using existing technical tables
    const tableMap = {
      'daily': 'technical_data_daily',
      'weekly': 'technical_data_weekly', 
      'monthly': 'technical_data_monthly'
    };
    
    const tableName = tableMap[timeframe] || 'technical_data_daily';
    
    const momentumQuery = `
      SELECT 
        symbol,
        rsi,
        macd,
        momentum,
        volume,
        date,
        fetched_at
      FROM ${tableName}
      WHERE symbol = $1
      ORDER BY date DESC
      LIMIT 1
    `;
    
    const result = await query(momentumQuery, [symbol]).catch(err => {
      console.warn("Technical indicators query failed:", err.message);
      return { rows: [] };
    });
    
    if (!result.rows.length) {
      return res.notFound(`No momentum data found for symbol ${symbol}`);
    }
    
    const data = result.rows[0];
    
    res.success({
      symbol: symbol,
      momentum_signals: [
        {
          signal_type: data.momentum > 0.5 ? "BULLISH_MOMENTUM" : "BEARISH_MOMENTUM",
          strength: data.momentum > 0.7 ? "STRONG" : data.momentum > 0.3 ? "MEDIUM" : "WEAK",
          timeframe: timeframe,
          score: parseFloat(data.momentum || 0.5),
          indicators: {
            rsi: parseFloat(data.rsi || 50),
            macd: parseFloat(data.macd || 0),
            momentum: parseFloat(data.momentum || 0.5),
            volume_trend: data.volume > 1000000 ? "INCREASING" : "DECREASING"
          },
          timestamp: data.fetched_at
        }
      ],
      metadata: {
        symbol: symbol,
        timeframe: timeframe,
        last_updated: data.created_at
      }
    });
  } catch (error) {
    console.error(`Error fetching momentum signals for ${req.params.symbol}:`, error);
    res.error("Failed to fetch momentum signals", 500);
  }
});

module.exports = router;
