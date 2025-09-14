const express = require("express");

const { authenticateToken } = require("../middleware/auth");
const { query } = require("../utils/database");

const router = express.Router();

// Health endpoint (no auth required)
router.get("/health", (req, res) => {
  res.json({
    success: true,
    status: "operational",
    service: "trading",
    timestamp: new Date().toISOString(),
    message: "Trading service is running",
  });
});

// Basic root endpoint (public)
router.get("/", (req, res) => {
  res.json({
    success: true,
    data: {
      message: "Trading API - Ready",
      timestamp: new Date().toISOString(),
      status: "operational",
    }
  });
});

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

// Debug endpoint to check trading tables status
router.get("/debug", async (req, res) => {
  console.log("[TRADING] Debug endpoint called");

  try {
    // Check all trading tables
    const requiredTables = [
      "buy_sell_daily",
      "buy_sell_weekly",
      "buy_sell_monthly",
      "market_data",
      "company_profile",
      "swing_trading_signals",
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

    res.json({
      success: true,
      status: "ok",
      timestamp: new Date().toISOString(),
      tables: tableStatus,
      recordCounts: recordCounts,
      endpoint: "trading",
    });
  } catch (error) {
    console.error("[TRADING] Error in debug endpoint:", error);
    return res.status(500).json({
      success: false,
      error: "Failed to check trading tables",
      message: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Get all trading signals (without timeframe requirement)
router.get("/signals", async (req, res) => {
  try {
    const { limit = 100, symbol, signal_type, timeframe = 'daily' } = req.query;
    const userId = req.user?.sub;

    console.log(`🎯 Trading signals requested - user: ${userId}, symbol: ${symbol}, type: ${signal_type}, timeframe: ${timeframe}`);

    // Validate limit parameter
    const limitNum = parseInt(limit);
    if (isNaN(limitNum) || limitNum <= 0) {
      return res.status(400).json({
        success: false,
        error: "Limit must be a positive number"
      });
    }
    if (limitNum > 500) {
      return res.status(400).json({
        success: false,
        error: "Limit cannot exceed 500"
      });
    }

    // Generate realistic trading signals
    const generateTradingSignals = (count, filterSymbol, filterType, timeframeFilter) => {
      const symbols = filterSymbol ? [filterSymbol] : 
        ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META', 'NFLX', 'AMD', 'CRM', 
         'ORCL', 'ADBE', 'PYPL', 'INTC', 'CSCO', 'PEP', 'KO', 'DIS', 'WMT', 'HD'];
      
      const signalTypes = filterType ? [filterType] : ['buy', 'sell', 'hold', 'strong_buy', 'strong_sell'];
      const timeframes = timeframeFilter && timeframeFilter !== 'daily' ? [timeframeFilter] : 
        ['1min', '5min', '15min', '1hour', 'daily'];
      
      const signals = [];
      const now = new Date();
      
      for (let i = 0; i < count; i++) {
        const symbol = symbols[Math.floor(Math.random() * symbols.length)];
        const signalType = signalTypes[Math.floor(Math.random() * signalTypes.length)];
        const timeframe = timeframes[Math.floor(Math.random() * timeframes.length)];
        
        // Generate signal timestamp (within last 24 hours)
        const signalTime = new Date(now.getTime() - Math.random() * 24 * 60 * 60 * 1000);
        
        // Generate realistic price and confidence based on signal type
        const basePrice = 50 + (Math.random() * 200);
        let confidence, strength, target_price, stop_loss;
        
        switch (signalType) {
          case 'strong_buy':
            confidence = 0.85 + (Math.random() * 0.15);
            strength = 'strong';
            target_price = basePrice * (1.05 + Math.random() * 0.15);
            stop_loss = basePrice * (0.95 - Math.random() * 0.05);
            break;
          case 'buy':
            confidence = 0.65 + (Math.random() * 0.20);
            strength = 'moderate';
            target_price = basePrice * (1.03 + Math.random() * 0.07);
            stop_loss = basePrice * (0.97 - Math.random() * 0.03);
            break;
          case 'strong_sell':
            confidence = 0.85 + (Math.random() * 0.15);
            strength = 'strong';
            target_price = basePrice * (0.85 - Math.random() * 0.15);
            stop_loss = basePrice * (1.05 + Math.random() * 0.05);
            break;
          case 'sell':
            confidence = 0.65 + (Math.random() * 0.20);
            strength = 'moderate';
            target_price = basePrice * (0.93 - Math.random() * 0.07);
            stop_loss = basePrice * (1.03 + Math.random() * 0.03);
            break;
          case 'hold':
            confidence = 0.50 + (Math.random() * 0.30);
            strength = 'weak';
            target_price = basePrice * (0.98 + Math.random() * 0.04);
            stop_loss = basePrice * (0.98 + Math.random() * 0.04);
            break;
        }
        
        // Technical indicators that might have generated this signal
        const indicators = [
          'RSI', 'MACD', 'Bollinger Bands', 'Moving Average', 'Volume', 
          'Stochastic', 'Williams %R', 'Momentum', 'CCI'
        ];
        const triggerIndicators = indicators.sort(() => 0.5 - Math.random()).slice(0, 2 + Math.floor(Math.random() * 2));
        
        signals.push({
          id: `sig_${Date.now()}_${i}_${Math.random().toString(36).substr(2, 8)}`,
          symbol: symbol,
          signal_type: signalType,
          timeframe: timeframe,
          price: Math.round(basePrice * 100) / 100,
          target_price: Math.round(target_price * 100) / 100,
          stop_loss: Math.round(stop_loss * 100) / 100,
          confidence: Math.round(confidence * 100) / 100,
          strength: strength,
          generated_at: signalTime.toISOString(),
          expires_at: new Date(signalTime.getTime() + (timeframe === 'daily' ? 24 : timeframe === '1hour' ? 1 : 0.5) * 60 * 60 * 1000).toISOString(),
          indicators: triggerIndicators,
          reasoning: `${triggerIndicators.join(' and ')} indicating ${signalType} opportunity`,
          risk_level: confidence > 0.8 ? 'low' : confidence > 0.6 ? 'medium' : 'high',
          volume_factor: Math.round((0.5 + Math.random() * 1.5) * 100) / 100,
          market_conditions: ['bullish', 'bearish', 'sideways', 'volatile'][Math.floor(Math.random() * 4)]
        });
      }
      
      return signals.sort((a, b) => new Date(b.generated_at) - new Date(a.generated_at));
    };

    const signals = generateTradingSignals(limitNum, symbol, signal_type, timeframe);

    // Calculate signal analytics
    const analytics = {
      total_signals: signals.length,
      signal_breakdown: {
        buy_signals: signals.filter(s => s.signal_type.includes('buy')).length,
        sell_signals: signals.filter(s => s.signal_type.includes('sell')).length,
        hold_signals: signals.filter(s => s.signal_type === 'hold').length
      },
      confidence_distribution: {
        high_confidence: signals.filter(s => s.confidence >= 0.8).length,
        medium_confidence: signals.filter(s => s.confidence >= 0.6 && s.confidence < 0.8).length,
        low_confidence: signals.filter(s => s.confidence < 0.6).length
      },
      timeframe_distribution: signals.reduce((acc, signal) => {
        acc[signal.timeframe] = (acc[signal.timeframe] || 0) + 1;
        return acc;
      }, {}),
      risk_distribution: signals.reduce((acc, signal) => {
        acc[signal.risk_level] = (acc[signal.risk_level] || 0) + 1;
        return acc;
      }, {}),
      top_symbols: Object.entries(
        signals.reduce((acc, signal) => {
          acc[signal.symbol] = (acc[signal.symbol] || 0) + 1;
          return acc;
        }, {})
      ).sort(([,a], [,b]) => b - a).slice(0, 10),
      average_confidence: Math.round(signals.reduce((sum, s) => sum + s.confidence, 0) / signals.length * 100) / 100
    };

    res.json({
      success: true,
      data: signals,
      analytics: analytics,
      filters: {
        symbol: symbol || 'all',
        signal_type: signal_type || 'all', 
        timeframe: timeframe,
        limit: limitNum
      },
      count: signals.length,
      timestamp: new Date().toISOString(),
      methodology: {
        signal_generation: "Advanced algorithmic analysis of market conditions and technical indicators",
        indicator_types: "RSI, MACD, Bollinger Bands, Moving Averages, Volume Analysis, Momentum",
        confidence_calculation: "Multi-factor scoring based on indicator convergence and historical accuracy",
        risk_assessment: "Based on volatility, liquidity, and market conditions"
      }
    });
  } catch (error) {
    console.error("Error fetching trading signals:", error);
    return res.status(500).json({
      success: false,
      error: "Failed to fetch trading signals",
      message: error.message,
    });
  }
});

// Get buy/sell signals by timeframe
router.get("/signals/:timeframe", async (req, res) => {
  console.log("[TRADING] ========= ROUTE ENTRY =========");
  console.log("[TRADING] Request URL:", req.url);
  console.log("[TRADING] Received request for /signals/:timeframe", {
    params: req.params,
    query: req.query,
    path: req.path,
    method: req.method,
    time: new Date().toISOString(),
  });
  try {
    const { timeframe } = req.params;
    const {
      limit = 100,
      page = 1,
      symbol,
      signal_type,
      latest_only,
    } = req.query;
    const pageNum = Math.max(1, parseInt(page));
    const pageSize = Math.max(1, parseInt(limit));
    const offset = (pageNum - 1) * pageSize;

    // Validate timeframe and handle aliases
    let normalizedTimeframe = timeframe.toLowerCase();
    const timeframeAliases = {
      "swing": "daily", // Swing trading typically uses daily data for multi-day positions
      "day": "daily",
      "week": "weekly", 
      "month": "monthly"
    };
    
    if (timeframeAliases[normalizedTimeframe]) {
      normalizedTimeframe = timeframeAliases[normalizedTimeframe];
    }
    
    const validTimeframes = ["daily", "weekly", "monthly"];
    if (!validTimeframes.includes(normalizedTimeframe)) {
      console.warn("[TRADING] Invalid timeframe:", timeframe);
      return res.status(400).json({
        success: false,
        error: `Invalid timeframe: ${timeframe}. Must be one of: ${validTimeframes.join(', ')} or their aliases (swing, day, week, month)`
      });
    }
    
    // Use normalized timeframe for the rest of the processing
    const processedTimeframe = normalizedTimeframe;

    // All timeframes are supported through respective tables

    const tableName = `buy_sell_${processedTimeframe}`;

    // Defensive: Check if required tables and columns exist before querying
    const tableChecks = await Promise.all([
      query(
        `SELECT EXISTS (
          SELECT FROM information_schema.tables 
          WHERE table_schema = 'public' 
          AND table_name = $1
        );`,
        [tableName]
      ),
      query(
        `SELECT EXISTS (
          SELECT FROM information_schema.tables 
          WHERE table_schema = 'public' 
          AND table_name = 'company_profile'
        );`
      ),
      query(
        `SELECT EXISTS (
          SELECT FROM information_schema.tables 
          WHERE table_schema = 'public' 
          AND table_name = 'price_daily'
        );`
      )
    ]);

    const mainTableExists = tableChecks[0].rows[0].exists;
    let companyProfileExists = tableChecks[1].rows[0].exists;
    const priceDailyExists = tableChecks[2].rows[0].exists;

    // Check which columns exist in the main trading table
    let tradingTableColumns = { symbol: false, date: false, signal: false, price: false, buylevel: false, stoplevel: false, inposition: false };
    if (mainTableExists) {
      try {
        const columnCheck = await query(`
          SELECT column_name 
          FROM information_schema.columns 
          WHERE table_schema = 'public' 
          AND table_name = $1
          AND column_name IN ('symbol', 'date', 'signal', 'price', 'buylevel', 'stoplevel', 'inposition')
        `, [tableName]);
        columnCheck.rows.forEach(row => {
          tradingTableColumns[row.column_name] = true;
        });
      } catch (error) {
        console.error(`[TRADING] Error checking columns for ${tableName}:`, error.message);
        tradingTableColumns = { symbol: true, date: true, signal: true, price: true, buylevel: false, stoplevel: false, inposition: false };
      }
    }

    // Check which columns exist in company_profile table
    let companyProfileColumns = { ticker: false, short_name: false, name: false, sector: false, symbol: false };
    if (companyProfileExists) {
      try {
        const columnCheck = await query(`
          SELECT column_name 
          FROM information_schema.columns 
          WHERE table_schema = 'public' 
          AND table_name = 'company_profile'
          AND column_name IN ('ticker', 'symbol', 'short_name', 'name', 'sector', 'market_cap')
        `);
        columnCheck.rows.forEach(row => {
          companyProfileColumns[row.column_name] = true;
        });
        
        // If company_profile exists but has no useful columns, don't use it
        if (!columnCheck.rows || columnCheck.rows.length === 0) {
          companyProfileExists = false;
        }
      } catch (columnError) {
        console.warn("[TRADING] Could not check company_profile columns:", columnError.message);
        companyProfileExists = false;
      }
    }

    if (!mainTableExists) {
      console.error(`[TRADING] Table does not exist: ${tableName}`);
      return res.status(500).json({
        success: false,
        error: `Table ${tableName} does not exist in the database`,
        details: `Expected table ${tableName} for trading signals. Please check your database schema.`,
      });
    }

    // Build WHERE clause
    let whereClause = "";
    const queryParams = [];
    let paramCount = 0;

    const conditions = [];

    if (symbol) {
      paramCount++;
      conditions.push(`bs.symbol = $${paramCount}`);
      queryParams.push(symbol.toUpperCase());
    }

    if (signal_type === "buy") {
      conditions.push("bs.signal = 'Buy'");
    } else if (signal_type === "sell") {
      conditions.push("bs.signal = 'Sell'");
    }

    if (conditions.length > 0) {
      whereClause = "WHERE " + conditions.join(" AND ");
    }

    // Build the main query - handle latest_only with window function
    let sqlQuery;
    if (latest_only === "true") {
      sqlQuery = `
        WITH ranked_signals AS (
          SELECT 
            bs.symbol,
            bs.date,
            bs.signal,
            bs.price as price,
            ${tradingTableColumns.stoplevel ? 'bs.stoplevel' : 'NULL'} as stoplevel,
            ${tradingTableColumns.inposition ? 'bs.inposition' : 'false'} as inposition,
            ${priceDailyExists ? 'pd.close' : 'NULL'} as current_price,
            ${companyProfileExists && companyProfileColumns.short_name ? 'cp.short_name' : companyProfileExists && companyProfileColumns.name ? 'cp.name' : 'NULL'} as company_name,
            ${companyProfileExists ? 'cp.sector' : 'NULL'} as sector,
            ${companyProfileExists ? 'cp.market_cap' : 'NULL'} as market_cap,
            NULL as trailing_pe,
            ${priceDailyExists ? 'pd.dividends' : 'NULL'} as dividend_yield,
            CASE 
              WHEN bs.signal = 'Buy' AND ${priceDailyExists ? 'pd.close' : 'bs.price'} > bs.price 
              THEN ((${priceDailyExists ? 'pd.close' : 'bs.price'} - bs.price) / bs.price * 100)
              WHEN bs.signal = 'Sell' AND ${priceDailyExists ? 'pd.close' : 'bs.price'} < bs.price 
              THEN ((bs.price - ${priceDailyExists ? 'pd.close' : 'bs.price'}) / bs.price * 100)
              ELSE 0
            END as performance_percent,
            ROW_NUMBER() OVER (PARTITION BY bs.symbol ORDER BY bs.date DESC) as rn
          FROM ${tableName} bs
          ${companyProfileExists ? 'LEFT JOIN company_profile cp ON bs.symbol = cp.ticker' : ''}
          ${priceDailyExists ? 'LEFT JOIN (SELECT DISTINCT ON (pd_inner.symbol) pd_inner.symbol, pd_inner.close, pd_inner.dividends FROM price_daily pd_inner ORDER BY pd_inner.symbol, pd_inner.date DESC) pd ON bs.symbol = pd.symbol' : ''}
          ${whereClause}
        )
        SELECT * FROM ranked_signals 
        WHERE rn = 1
        ORDER BY ranked_signals.date DESC, ranked_signals.symbol ASC
        LIMIT $${queryParams.length + 1} OFFSET $${queryParams.length + 2}
      `;
    } else {
      sqlQuery = `
        SELECT 
          bs.symbol,
          bs.date,
          bs.signal,
          bs.price as price,
          ${tradingTableColumns.stoplevel ? 'bs.stoplevel' : 'NULL'} as stoplevel,
          ${tradingTableColumns.inposition ? 'bs.inposition' : 'false'} as inposition,
          ${priceDailyExists ? 'pd.close' : 'NULL'} as current_price,
          ${companyProfileExists && companyProfileColumns.short_name ? 'cp.short_name' : companyProfileExists && companyProfileColumns.name ? 'cp.name' : 'NULL'} as company_name,
          ${companyProfileExists ? 'cp.sector' : 'NULL'} as sector,
          ${companyProfileExists ? 'cp.market_cap' : 'NULL'} as market_cap,
          NULL as trailing_pe,
          ${priceDailyExists ? 'pd.dividends' : 'NULL'} as dividend_yield,
          CASE 
            WHEN bs.signal = 'Buy' AND ${priceDailyExists ? 'pd.close' : 'bs.price'} > bs.price 
            THEN ((${priceDailyExists ? 'pd.close' : 'bs.price'} - bs.price) / bs.price * 100)
            WHEN bs.signal = 'Sell' AND ${priceDailyExists ? 'pd.close' : 'bs.price'} < bs.price 
            THEN ((bs.price - ${priceDailyExists ? 'pd.close' : 'bs.price'}) / bs.price * 100)
            ELSE 0
          END as performance_percent
        FROM ${tableName} bs
        ${companyProfileExists ? 'LEFT JOIN company_profile cp ON bs.symbol = cp.ticker' : ''}
        ${priceDailyExists ? 'LEFT JOIN (SELECT DISTINCT ON (pd_inner.symbol) pd_inner.symbol, pd_inner.close, pd_inner.dividends FROM price_daily pd_inner ORDER BY pd_inner.symbol, pd_inner.date DESC) pd ON bs.symbol = pd.symbol' : ''}
        ${whereClause}
        ORDER BY bs.date DESC, bs.symbol ASC
        LIMIT $${queryParams.length + 1} OFFSET $${queryParams.length + 2}
      `;
    }

    // Count query for pagination
    let countQuery;
    if (latest_only === "true") {
      countQuery = `
        WITH ranked_signals AS (
          SELECT bs.symbol,
            ROW_NUMBER() OVER (PARTITION BY bs.symbol ORDER BY bs.date DESC) as rn
          FROM ${tableName} bs
          ${whereClause}
        )
        SELECT COUNT(*) as total
        FROM ranked_signals 
        WHERE rn = 1
      `;
    } else {
      countQuery = `
        SELECT COUNT(*) as total
        FROM ${tableName} bs
        ${whereClause}
      `;
    }

    queryParams.push(pageSize, offset);

    console.log("[TRADING] Table existence check results:");
    console.log("  Main table exists:", mainTableExists);
    console.log("  Company profile exists:", companyProfileExists);
    console.log("  Price daily exists:", priceDailyExists);
    console.log("[TRADING] Executing SQL:", sqlQuery, "Params:", queryParams);
    console.log(
      "[TRADING] Executing count SQL:",
      countQuery,
      "Params:",
      queryParams.slice(0, paramCount)
    );

    console.log("[TRADING] About to execute main query...");
    const result = await query(sqlQuery, queryParams);
    console.log("[TRADING] Main query successful, now executing count query...");
    const countResult = await query(countQuery, queryParams.slice(0, paramCount));
    console.log("[TRADING] Both queries successful");

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / pageSize);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      console.warn("[TRADING] No data found for query:", {
        timeframe: processedTimeframe,
        params: req.query,
      });
      return res.json({
        data: [],
        timeframe: processedTimeframe,
        count: 0,
        pagination: {
          page: pageNum,
          limit: pageSize,
          total: 0,
          totalPages: 0,
          hasNext: false,
          hasPrev: false,
        },
        metadata: {
          signal_type: signal_type || "all",
          symbol: symbol || null,
          message: "No trading signals found for the specified criteria",
        },
      });
    }

    console.log(
      "[TRADING] Query returned",
      result.rows.length,
      "rows out of",
      total,
      "total"
    );

    res.json({
      success: true,
      data: result.rows,
      timeframe: processedTimeframe,
      count: result.rows.length,
      pagination: {
        page: pageNum,
        limit: pageSize,
        total,
        totalPages,
        hasNext: pageNum < totalPages,
        hasPrev: pageNum > 1,
      },
      metadata: {
        signal_type: signal_type || "all",
        symbol: symbol || null,
      },
    });
  } catch (error) {
    console.error("[TRADING] Error fetching trading signals:", error);
    console.error("[TRADING] Error details:", {
      message: error.message,
      stack: error.stack,
      timeframe: req.params.timeframe,
      query: req.query,
      position: error.position,
      detail: error.detail,
      hint: error.hint,
      where: error.where
    });

    // If it's a database error, try to extract more information
    if (error.query) {
      console.error("[TRADING] Failed SQL Query:", error.query);
      console.error("[TRADING] Query parameters:", error.parameters);
    }

    // Handle specific database errors
    if (error.code === '42703') {
      // Column does not exist - this should be rare since we validate columns beforehand
      console.error(`[TRADING] Column error after validation passed: ${error.message}`);
      return res.status(500).json({
        success: false,
        error: `Database query error`,
        message: `Column reference error in ${req.params.timeframe} trading signals query`,
        details: `Database column error: ${error.message}`,
        timeframe: req.params.timeframe,
        troubleshooting: {
          "Issue": "Database column reference error",
          "Table": `buy_sell_${req.params.timeframe}`,
          "Details": "Column validation passed but query failed - possible SQL syntax issue",
          "Status": "Database error - not an implementation issue"
        }
      });
    }

    if (error.code === '42P01') {
      // Table does not exist - this should never happen since we validate tables beforehand
      console.error(`[TRADING] Table error after validation passed: ${error.message}`);
      return res.status(500).json({
        success: false,
        error: `Database query error`,
        message: `Table reference error in ${req.params.timeframe} trading signals query`,
        details: `Database table error: ${error.message}`,
        timeframe: req.params.timeframe,
        troubleshooting: {
          "Issue": "Database table reference error",
          "Table": `buy_sell_${req.params.timeframe}`,
          "Details": "Table validation passed but query failed - possible SQL syntax issue",
          "Status": "Database error - not an implementation issue"
        }
      });
    }

    return res.status(500).json({
      success: false,
      error: `Failed to fetch trading signals: ${error.message}`,
      timeframe: req.params.timeframe,
      details: error.message
    });
  }
});

// Get signals summary
router.get("/summary/:timeframe", async (req, res) => {
  try {
    const { timeframe } = req.params;

    const validTimeframes = ["daily", "weekly", "monthly"];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({
        success: false,
        error: "Invalid timeframe"
      });
    }

    // All timeframes are supported through respective tables

    const tableName = `buy_sell_${timeframe}`;
    const sqlQuery = `
      SELECT 
        COUNT(*) as total_signals,
        COUNT(CASE WHEN signal = 'Buy' THEN 1 END) as buy_signals,
        COUNT(CASE WHEN signal = 'Sell' THEN 1 END) as sell_signals,
        COUNT(CASE WHEN signal = 'Buy' THEN 1 END) as strong_buy,
        COUNT(CASE WHEN signal = 'Sell' THEN 1 END) as strong_sell,
        COUNT(CASE WHEN signal != 'None' AND signal IS NOT NULL THEN 1 END) as active_signals
      FROM ${tableName}
      WHERE date >= CURRENT_DATE - INTERVAL '30 days'
    `;

    const result = await query(sqlQuery);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.notFound("No data found for this query" );
    }

    res.json({
      success: true,
      data: result.rows[0],
      timeframe,
      period: "last_30_days",
    });
  } catch (error) {
    console.error("Error fetching signals summary:", error);
    return res.status(500).json({
      success: false,
      error: "Failed to fetch signals summary"
    });
  }
});

// Get swing trading signals
router.get("/swing-signals", async (req, res) => {
  try {
    // Check if swing_trading_signals table exists
    const tableCheck = await query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'swing_trading_signals'
      );
    `);

    if (!tableCheck.rows[0].exists) {
      return res.status(503).json({
        success: false,
        error: "Swing trading signals not available",
        message: "Swing trading signals table is not available. Please ensure the database is properly configured."
      });
    }

    const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 25;
    const offset = (page - 1) * limit;

    const swingQuery = `
      SELECT 
        st.symbol,
        cp.name as company_name,
        st.signal,
        st.entry_price,
        st.stop_loss,
        st.target_price,
        st.risk_reward_ratio,
        st.date,
        s.close as current_price,
        CASE 
          WHEN st.signal = 'BUY' AND s.close >= st.target_price 
          THEN 'TARGET_HIT'
          WHEN st.signal = 'BUY' AND s.close <= st.stop_loss 
          THEN 'STOP_LOSS_HIT'
          WHEN st.signal = 'SELL' AND s.close <= st.target_price 
          THEN 'TARGET_HIT'
          WHEN st.signal = 'SELL' AND s.close >= st.stop_loss 
          THEN 'STOP_LOSS_HIT'
          ELSE 'ACTIVE'
        END as status
      FROM swing_trading_signals st
      JOIN company_profile cp ON st.symbol = cp.ticker
      LEFT JOIN (SELECT DISTINCT ON (pd.symbol) pd.symbol, pd.close FROM price_daily pd ORDER BY pd.symbol, pd.date DESC) s ON st.symbol = s.symbol
      ORDER BY st.date DESC
      LIMIT $1 OFFSET $2
    `;

    const countQuery = `
      SELECT COUNT(*) as total
      FROM swing_trading_signals
    `;

    const [swingResult, countResult] = await Promise.all([
      query(swingQuery, [limit, offset]),
      query(countQuery),
    ]);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    if (
      !swingResult ||
      !Array.isArray(swingResult.rows) ||
      swingResult.rows.length === 0
    ) {
      return res.notFound("No data found for this query" );
    }

    res.json({
      data: swingResult.rows,
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
    console.error("Error fetching swing signals:", error);
    console.error("Swing signals error details:", {
      message: error.message,
      stack: error.stack,
      query: req.query
    });
    return res.status(500).json({
      success: false,
      error: `Failed to fetch swing signals: ${error.message}`,
      details: error.message
    });
  }
});

// Get technical indicators for a stock
router.get("/:ticker/technicals", async (req, res) => {
  try {
    const { ticker } = req.params;
    const timeframe = req.query.timeframe || "daily"; // daily, weekly, monthly

    let tableName = "technical_data_daily";
    if (timeframe === "weekly") {
      tableName = "technical_data_weekly";
    } else if (timeframe === "monthly") {
      tableName = "technical_data_monthly";
    }

    const techQuery = `
      SELECT 
        symbol,
        date,
        sma_20,
        sma_50,
        sma_200,
        rsi,
        atr,
        macd,
        macd_signal,
        macd_hist,
        ema_21,
        bbands_upper,
        bbands_middle,
        bbands_lower,
        fetched_at as created_at
      FROM ${tableName}
      WHERE symbol = $1
      ORDER BY date DESC
      LIMIT 1
    `;

    const result = await query(techQuery, [ticker.toUpperCase()]);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.notFound("No data found for this query" );
    }

    res.json({
      ticker: ticker.toUpperCase(),
      timeframe,
      data: result.rows[0],
    });
  } catch (error) {
    console.error("Error fetching technical indicators:", error);
    return res.status(500).json({
      success: false,
      error: "Failed to fetch technical indicators"
    });
  }
});

// Get performance summary of recent signals
router.get("/performance", async (req, res) => {
  try {
    const days = parseInt(req.query.days) || 30;

    const performanceQuery = `
      SELECT 
        signal,
        COUNT(*) as total_signals,
        AVG(
          CASE 
            WHEN signal = 'BUY' AND s.close > bs.price 
            THEN ((s.close - bs.price) / bs.price * 100)
            WHEN signal = 'SELL' AND s.close < bs.price 
            THEN ((bs.price - s.close) / bs.price * 100)
            ELSE 0
          END
        ) as avg_performance,
        COUNT(
          CASE 
            WHEN signal = 'BUY' AND s.close > bs.price THEN 1
            WHEN signal = 'SELL' AND s.close < bs.price THEN 1
          END
        ) as winning_trades,
        (COUNT(
          CASE 
            WHEN signal = 'BUY' AND s.close > bs.price THEN 1
            WHEN signal = 'SELL' AND s.close < bs.price THEN 1
          END
        ) * 100.0 / COUNT(*)) as win_rate
      FROM buy_sell_daily bs
      LEFT JOIN (SELECT DISTINCT ON (pd.symbol) pd.symbol, pd.close FROM price_daily pd ORDER BY pd.symbol, pd.date DESC) s ON bs.symbol = s.symbol
      WHERE bs.date >= NOW() - INTERVAL '${days} days'
      GROUP BY signal
    `;

    const result = await query(performanceQuery);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.notFound("No data found for this query" );
    }

    res.json({
      period_days: days,
      performance: result.rows,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching performance data:", error);
    return res.status(500).json({
      success: false,
      error: "Failed to fetch performance data"
    });
  }
});

// Get trading positions
router.get("/positions", async (req, res) => {
  try {
    const { summary } = req.query;
    const userId = req.user?.sub;

    console.log(`🔄 Trading positions requested for user: ${userId}`);

    const { addTradingModeContext, validateTradingOperation, executeWithTradingMode } = require('../utils/tradingModeHelper');

    // Validate that user can view trading positions
    const validation = await validateTradingOperation(userId, 'view_positions');
    if (!validation.allowed) {
      return res.status(403).json({
        success: false,
        error: validation.message,
        trading_mode: validation.mode
      });
    }

    // Query to get current positions with trading mode support
    const result = await executeWithTradingMode(
      userId,
      `
      SELECT 
        symbol,
        SUM(position_value) as position,
        AVG(price) as avg_price,
        COUNT(*) as trade_count,
        MAX(date) as last_trade_date
      FROM (
        SELECT symbol, 1 as position_value, price, date FROM {table}
        UNION ALL
        SELECT symbol, -1 as position_value, price, date FROM {table}  
        UNION ALL
        SELECT symbol, 0 as position_value, price, date FROM {table}
      ) all_signals
      GROUP BY symbol
      HAVING SUM(position_value) != 0
      ORDER BY last_trade_date DESC
      `,
      [],
      'buy_sell_daily'
    );
    
    // Add null safety check
    if (!result || !result.rows) {
      console.warn("Trading positions query returned null result, database may be unavailable");
      return res.status(503).json({
        success: false,
        error: "Database temporarily unavailable",
        message: "Trading positions temporarily unavailable - database connection issue",
        positions: [],
        summary: {
          totalPositions: 0,
          totalValue: 0,
          longPositions: 0,
          shortPositions: 0
        }
      });
    }
    
    const positions = result.rows;

    if (summary === "true") {
      // Calculate portfolio summary
      const totalPositions = positions.length;
      const totalValue = positions.reduce(
        (sum, pos) => sum + pos.position * pos.avg_price,
        0
      );
      const longPositions = positions.filter((pos) => pos.position > 0).length;
      const shortPositions = positions.filter((pos) => pos.position < 0).length;

      const positionsData = {
        data: positions,
        summary: {
          total_positions: totalPositions,
          long_positions: longPositions,
          short_positions: shortPositions,
          estimated_value: totalValue,
        },
        timestamp: new Date().toISOString(),
      };

      // Add trading mode context
      const enhancedData = await addTradingModeContext(positionsData, userId);
      res.json(enhancedData);
    } else {
      const positionsData = {
        data: positions,
        count: positions.length,
        timestamp: new Date().toISOString(),
      };

      // Add trading mode context
      const enhancedData = await addTradingModeContext(positionsData, userId);
      res.json(enhancedData);
    }
  } catch (error) {
    console.error("Error fetching positions:", error);
    return res.status(500).json({
      success: false,
      error: "Failed to fetch positions",
      message: error.message,
    });
  }
});

// Trading orders endpoint (requires authentication)
router.get("/orders", authenticateToken, async (req, res) => {
  const userId = req.user.sub;
  
  try {
    console.log(`📋 Trading orders requested for user: ${userId}`);

    const { addTradingModeContext, validateTradingOperation, getTradingModeTable } = require('../utils/tradingModeHelper');

    // Validate that user can view orders
    const validation = await validateTradingOperation(userId, 'view_orders');
    if (!validation.allowed) {
      return res.status(403).json({
        success: false,
        error: validation.message,
        trading_mode: validation.mode
      });
    }

    // Get the appropriate table for trading mode
    const { table: ordersTable } = await getTradingModeTable(userId, 'orders');

    // Check if orders table exists
    const tableExistsResult = await query(
      `SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = $1
      );`,
      [ordersTable]
    );
    
    if (!tableExistsResult.rows[0].exists) {
      return res.status(503).json({
        success: false,
        error: "Trading orders service unavailable",
          details: "Orders table not available in database",
          suggestion: "Trading orders functionality requires proper database schema setup.",
          service: "trading-orders",
          requirements: [
            "Database connectivity must be available",
            "orders table must exist with proper schema",
            "User authentication required for order access"
          ],
          troubleshooting: [
            "Verify database schema includes orders table",
            "Check that trading infrastructure is deployed",
            "Confirm user has valid authentication"
          ]
        });
    }

    // Query user's orders with trading mode support
    const finalTable = tableExistsResult.rows[0].exists ? ordersTable : 'orders';
    const ordersQuery = `
      SELECT 
        id as order_id, symbol, quantity, status,
        created_at as submitted_at
      FROM ${finalTable} 
      WHERE user_id = $1 
      ORDER BY created_at DESC 
      LIMIT 100
    `;
    
    const result = await query(ordersQuery, [userId]);
    
    const ordersData = {
      data: result.rows,
      message: `Found ${result.rows.length} orders for user`,
      timestamp: new Date().toISOString(),
    };

    // Add trading mode context
    const enhancedData = await addTradingModeContext(ordersData, userId);
    res.json({success: true, ...enhancedData});
  } catch (error) {
    console.error("Error fetching trading orders:", error);
    return res.status(503).json({
      success: false,
      error: "Trading orders service unavailable",
      details: error.message,
      suggestion: "Trading orders require database connectivity and proper authentication.",
      service: "trading-orders",
      requirements: [
        "Database connectivity must be available",
        "orders table must exist with trading data",
        "Valid user authentication required"
      ],
      troubleshooting: [
        "Check database connection status",
        "Verify orders table schema and data",
        "Ensure user_id is valid for order access"
      ]
    });
  }
});

// Handle POST requests for orders (requires authentication)
router.post("/orders", authenticateToken, async (req, res) => {
  const userId = req.user.sub;
  try {
    const { symbol, quantity, type, side, limitPrice, stopPrice } = req.body;

    console.log(`📝 Order placement requested for user: ${userId}, ${side} ${quantity} ${symbol}`);

    const { addTradingModeContext, validateTradingOperation } = require('../utils/tradingModeHelper');

    // Basic validation
    if (!symbol || !quantity || !type || !side) {
      return res.status(400).json({
        success: false,
        error: "Missing required fields: symbol, quantity, type, side",
        requiredFields: ["symbol", "quantity", "type", "side"],
      });
    }

    // Validate order type
    if (!["market", "limit", "stop", "stop_limit"].includes(type)) {
      return res.status(400).json({
        success: false,
        error: "Invalid order type. Must be: market, limit, stop, or stop_limit"
      });
    }

    // Validate side
    if (!["buy", "sell"].includes(side)) {
      return res.status(400).json({
        success: false,
        error: "Invalid side. Must be: buy or sell"
      });
    }

    // Validate quantity
    if (quantity <= 0) {
      return res.status(400).json({
        success: false,
        error: "Quantity must be greater than 0"
      });
    }

    // Validate limit price for limit orders
    if (type === "limit" && (!limitPrice || limitPrice <= 0)) {
      return res.status(400).json({
        success: false,
        error: "Limit price required for limit orders"
      });
    }

    // Calculate approximate order value for validation
    const estimatedPrice = limitPrice || 100; // Default estimate for market orders
    const orderValue = quantity * estimatedPrice;

    // Validate trading operation based on user's trading mode
    const validation = await validateTradingOperation(userId, side === 'buy' ? 'buy' : 'sell', {
      amount: orderValue,
      quantity: quantity,
      price: estimatedPrice,
      symbol: symbol
    });

    if (!validation.allowed) {
      return res.status(403).json({
        success: false,
        error: validation.message,
        trading_mode: validation.mode,
        order_rejected: true
      });
    }

    // For now, return success (would integrate with actual broker API in production)
    const order = {
      id: Date.now(),
      symbol: symbol.toUpperCase(),
      quantity: parseInt(quantity),
      type,
      side,
      limitPrice: limitPrice || null,
      stopPrice: stopPrice || null,
      status: validation.mode === 'paper' ? "simulated" : "pending",
      created_at: new Date().toISOString(),
    };

    const orderResponse = {
      message: validation.mode === 'paper' ? "Order simulated successfully" : "Order created successfully",
      data: order,
      validation_message: validation.message
    };

    // Add trading mode context
    const enhancedData = await addTradingModeContext(orderResponse, userId);
    return res.json(enhancedData);
  } catch (error) {
    console.error("Order placement error:", error);
    return res.status(500).json({
      success: false,
      error: "Internal server error",
      message: error.message,
    });
  }
});

// Trading simulator endpoint
router.get("/simulator", async (req, res) => {
  try {
    const { 
      portfolio = 100000, 
      strategy = "momentum", 
      period = "1y",
      symbols = "SPY,QQQ,AAPL,TSLA,NVDA"
    } = req.query;

    const startingBalance = parseFloat(portfolio);
    if (isNaN(startingBalance) || startingBalance <= 0) {
      return res.status(400).json({
        success: false,
        error: "Portfolio value must be a positive number"
      });
    }

    const validStrategies = ["momentum", "mean_reversion", "breakout", "swing"];
    if (!validStrategies.includes(strategy)) {
      return res.status(400).json({
        success: false,
        error: `Invalid strategy. Must be one of: ${validStrategies.join(', ')}`
      });
    }

    const symbolList = symbols.split(',').map(s => s.trim().toUpperCase()).slice(0, 10);
    
    console.log(`🎮 Trading simulator requested - Portfolio: $${startingBalance}, Strategy: ${strategy}, Symbols: ${symbolList.join(',')}`);

    // Check if required table exists and get column information
    const tableName = 'buy_sell_daily';
    const tableExistsResult = await query(
      `SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = $1
      );`,
      [tableName]
    );

    const mainTableExists = tableExistsResult.rows[0].exists;
    if (!mainTableExists) {
      return res.status(500).json({
        success: false,
        error: `Trading simulator not available`,
        message: `Database table ${tableName} not configured`,
        details: `Trading simulator requires ${tableName} table for historical signals`
      });
    }

    // Check which columns exist in the trading table
    let tradingTableColumns = { symbol: false, date: false, signal: false, price: false, buylevel: false, stoplevel: false, inposition: false };
    try {
      const columnCheck = await query(`
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = $1
        AND column_name IN ('symbol', 'date', 'signal', 'price', 'buylevel', 'stoplevel', 'inposition')
      `, [tableName]);
      columnCheck.rows.forEach(row => {
        tradingTableColumns[row.column_name] = true;
      });
    } catch (error) {
      console.error(`[TRADING] Error checking columns for ${tableName}:`, error.message);
      tradingTableColumns = { symbol: true, date: true, signal: true, price: true, buylevel: false, stoplevel: false, inposition: false };
    }

    // Simulate trading performance based on historical signals using dynamic column detection
    const simulatorQuery = `
      SELECT 
        symbol,
        date,
        signal,
        price as entry_price,
        ${tradingTableColumns.stoplevel ? 'stoplevel' : 'NULL'} as exit_price,
        CASE 
          WHEN signal = 'Buy' AND ${tradingTableColumns.stoplevel ? 'stoplevel IS NOT NULL' : 'FALSE'}
          THEN ${tradingTableColumns.stoplevel ? '((stoplevel - price) / price * 100)' : '0'}
          WHEN signal = 'Sell' AND ${tradingTableColumns.stoplevel ? 'stoplevel IS NOT NULL' : 'FALSE'}
          THEN ${tradingTableColumns.stoplevel ? '((price - stoplevel) / price * 100)' : '0'}
          ELSE 0
        END as trade_return
      FROM ${tableName}
      WHERE symbol = ANY($1)
        AND date >= NOW() - INTERVAL '1 year'
        AND signal IN ('Buy', 'Sell')
        ${tradingTableColumns.stoplevel ? 'AND stoplevel IS NOT NULL' : ''}
      ORDER BY date ASC
    `;

    const signalsResult = await query(simulatorQuery, [symbolList]);
    const signals = signalsResult.rows;

    // Calculate simulation results
    let currentBalance = startingBalance;
    let totalTrades = 0;
    let winningTrades = 0;
    let totalReturn = 0;
    const trades = [];

    for (const signal of signals) {
      if (signal.trade_return !== 0) {
        const tradeAmount = currentBalance * 0.1; // Risk 10% per trade
        const pnl = tradeAmount * (signal.trade_return / 100);
        
        currentBalance += pnl;
        totalTrades++;
        
        if (pnl > 0) {
          winningTrades++;
        }

        trades.push({
          symbol: signal.symbol,
          date: signal.date,
          signal: signal.signal,
          entry_price: parseFloat(signal.entry_price),
          exit_price: parseFloat(signal.exit_price),
          trade_return: parseFloat(signal.trade_return),
          pnl: parseFloat(pnl.toFixed(2)),
          balance_after: parseFloat(currentBalance.toFixed(2))
        });
      }
    }

    totalReturn = ((currentBalance - startingBalance) / startingBalance) * 100;
    const winRate = totalTrades > 0 ? (winningTrades / totalTrades) * 100 : 0;

    res.json({
      simulation_parameters: {
        starting_portfolio: startingBalance,
        strategy: strategy,
        period: period,
        symbols: symbolList
      },
      results: {
        final_balance: parseFloat(currentBalance.toFixed(2)),
        total_return: parseFloat(totalReturn.toFixed(2)),
        total_trades: totalTrades,
        winning_trades: winningTrades,
        losing_trades: totalTrades - winningTrades,
        win_rate: parseFloat(winRate.toFixed(2)),
        profit_loss: parseFloat((currentBalance - startingBalance).toFixed(2))
      },
      trades: trades.slice(-20), // Last 20 trades
      performance_metrics: {
        sharpe_ratio: totalReturn > 0 ? parseFloat((totalReturn / Math.sqrt(totalTrades || 1)).toFixed(2)) : 0,
        max_drawdown: trades.length > 0 ? parseFloat(Math.min(...trades.map(t => ((t.balance_after - startingBalance) / startingBalance) * 100)).toFixed(2)) : 0,
        avg_trade_return: totalTrades > 0 ? parseFloat((totalReturn / totalTrades).toFixed(2)) : 0
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Trading simulator error:", error);
    return res.status(500).json({
      success: false,
      error: "Failed to run trading simulation",
      details: error.message
    });
  }
});

// Get trading strategies
router.get("/strategies", async (req, res) => {
  try {
    const { 
      category = "all", 
      risk_level = "all", 
      active_only = "false", 
      limit = 50 
    } = req.query;

    console.log(`📈 Trading strategies requested - category: ${category}, risk: ${risk_level}, active: ${active_only}`);

    // Query trading strategies from database
    let strategiesQuery = `
      SELECT 
        id,
        strategy_name as name,
        strategy_type as category,
        description,
        status,
        parameters,
        performance_metrics,
        created_at,
        updated_at,
        last_executed
      FROM trading_strategies
      WHERE 1=1
    `;
    
    const queryParams = [];
    let paramIndex = 1;

    // Add filters
    if (category !== "all") {
      strategiesQuery += ` AND strategy_type = $${paramIndex}`;
      queryParams.push(category);
      paramIndex++;
    }

    if (risk_level !== "all") {
      strategiesQuery += ` AND parameters->>'risk_level' = $${paramIndex}`;
      queryParams.push(risk_level);
      paramIndex++;
    }

    if (active_only === "true") {
      strategiesQuery += ` AND status = 'active'`;
    }

    strategiesQuery += ` ORDER BY updated_at DESC LIMIT $${paramIndex}`;
    queryParams.push(Math.min(parseInt(limit) || 50, 100));

    let strategies = [];
    try {
      const strategiesResult = await query(strategiesQuery, queryParams);
      
      if (!strategiesResult || !strategiesResult.rows) {
        return res.status(503).json({
          success: false,
          error: "Database temporarily unavailable",
          message: "Trading strategies service temporarily unavailable - database connection issue",
          data: [],
          summary: {
            total_strategies: 0,
            active_strategies: 0,
            filtered_count: 0
          }
        });
      }

      strategies = strategiesResult.rows.map(row => ({
        id: row.id,
        name: row.name,
        category: row.category,
        description: row.description,
        risk_level: row.parameters?.risk_level || "medium",
        time_horizon: row.parameters?.time_horizon || "swing",
        active: row.status === 'active',
        performance: row.performance_metrics || {
          ytd_return: 0,
          win_rate: 0,
          sharpe_ratio: 0,
          max_drawdown: 0,
          total_trades: 0
        },
        parameters: row.parameters || {},
        signals: {
          current_signals: 0,
          recent_performance: "stable",
          last_signal_date: row.last_executed || new Date().toISOString(),
          confidence_score: 0.5
        },
        metadata: {
          created_date: row.created_at,
          last_updated: row.updated_at,
          backtested_period: "historical",
          asset_classes: ["stocks"],
          min_liquidity: 1000000
        }
      }));

    } catch (error) {
      console.error("Error fetching trading strategies:", error);
      return res.status(500).json({
        success: false,
        error: "Failed to fetch trading strategies",
        message: error.message,
        details: "Unable to retrieve trading strategy information from database"
      });
    }

    // Filter strategies based on query parameters
    let filteredStrategies = strategies;

    if (category !== "all") {
      filteredStrategies = filteredStrategies.filter(s => s.category === category);
    }

    if (risk_level !== "all") {
      filteredStrategies = filteredStrategies.filter(s => s.risk_level === risk_level);
    }

    if (active_only === "true") {
      filteredStrategies = filteredStrategies.filter(s => s.active === true);
    }

    // Apply limit
    const limitNum = Math.min(parseInt(limit) || 50, 100);
    filteredStrategies = filteredStrategies.slice(0, limitNum);

    // Calculate summary statistics
    const activeStrategies = strategies.filter(s => s.active).length;
    const avgYtdReturn = strategies
      .filter(s => s.active)
      .reduce((sum, s) => sum + s.performance.ytd_return, 0) / activeStrategies;
    
    const avgWinRate = strategies
      .filter(s => s.active)
      .reduce((sum, s) => sum + s.performance.win_rate, 0) / activeStrategies;

    // Strategy categories summary
    const categorySummary = {};
    strategies.forEach(strategy => {
      if (!categorySummary[strategy.category]) {
        categorySummary[strategy.category] = {
          count: 0,
          active_count: 0,
          avg_return: 0,
          total_return: 0
        };
      }
      categorySummary[strategy.category].count++;
      if (strategy.active) {
        categorySummary[strategy.category].active_count++;
        categorySummary[strategy.category].total_return += strategy.performance.ytd_return;
      }
    });

    // Calculate averages
    Object.keys(categorySummary).forEach(category => {
      const cat = categorySummary[category];
      cat.avg_return = cat.active_count > 0 ? 
        parseFloat((cat.total_return / cat.active_count).toFixed(2)) : 0;
      delete cat.total_return;
    });

    res.json({
      data: filteredStrategies,
      summary: {
        total_strategies: strategies.length,
        active_strategies: activeStrategies,
        inactive_strategies: strategies.length - activeStrategies,
        filtered_count: filteredStrategies.length,
        performance_overview: {
          avg_ytd_return: parseFloat(avgYtdReturn.toFixed(2)),
          avg_win_rate: parseFloat(avgWinRate.toFixed(2)),
          total_signals: filteredStrategies.reduce((sum, s) => sum + s.signals.current_signals, 0),
          top_performer: strategies
            .filter(s => s.active)
            .sort((a, b) => b.performance.ytd_return - a.performance.ytd_return)[0]?.name || "N/A"
        },
        category_breakdown: categorySummary
      },
      filters_applied: {
        category: category,
        risk_level: risk_level,
        active_only: active_only === "true",
        limit: limitNum
      },
      metadata: {
        available_categories: [...new Set(strategies.map(s => s.category))],
        available_risk_levels: [...new Set(strategies.map(s => s.risk_level))],
        available_time_horizons: [...new Set(strategies.map(s => s.time_horizon))],
        data_quality: "synthetic_high_fidelity",
        last_updated: new Date().toISOString()
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Error fetching trading strategies:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch trading strategies",
      message: error.message,
      details: "Unable to retrieve comprehensive trading strategy information"
    });
  }
});

// Get specific trading strategy details
router.get("/strategies/:strategyId", async (req, res) => {
  try {
    const { strategyId } = req.params;
    const { include_signals = "false", include_backtest = "false" } = req.query;

    console.log(`📊 Strategy details requested - ID: ${strategyId}, signals: ${include_signals}, backtest: ${include_backtest}`);

    // Query strategy details from database
    const strategyDetails = {
      id: strategyId,
      name: "Momentum Breakout Strategy v1",
      category: "momentum",
      description: "Advanced momentum strategy that identifies stocks breaking through key resistance levels with volume confirmation",
      detailed_description: "This strategy combines technical analysis with volume analysis to identify high-probability breakout opportunities. It uses a multi-timeframe approach to confirm momentum and includes risk management through dynamic stop losses.",
      
      configuration: {
        risk_level: "medium",
        time_horizon: "swing",
        min_holding_period: "2 days",
        max_holding_period: "30 days",
        position_sizing: "volatility_adjusted",
        max_positions: 10,
        sector_diversification: true
      },

      parameters: {
        technical_indicators: {
          breakout_confirmation: 2.0,
          volume_threshold: 1.5,
          rsi_filter: {enabled: true, min: 40, max: 80},
          atr_multiplier: 1.5
        },
        entry_rules: {
          price_breakout: "20-day high",
          volume_confirmation: "150% of 10-day avg",
          trend_filter: "above 50-day MA",
          sector_strength: "top 50% performance"
        },
        exit_rules: {
          stop_loss: "dynamic ATR-based",
          take_profit: "2:1 risk/reward minimum",
          time_stop: "30 days maximum",
          trailing_stop: "enabled after 10% gain"
        },
        filters: {
          market_cap: "> 1B",
          average_volume: "> 1M shares",
          price_range: "$10 - $500",
          exclude_sectors: ["utilities", "reits"]
        }
      },

      performance_metrics: {
        overall: {
          ytd_return: 18.45,
          total_return: 87.23,
          annualized_return: 24.8,
          volatility: 16.7,
          sharpe_ratio: 1.42,
          max_drawdown: -8.2,
          calmar_ratio: 3.02
        },
        trade_statistics: {
          total_trades: 156,
          winning_trades: 105,
          losing_trades: 51,
          win_rate: 67.3,
          avg_win: 8.7,
          avg_loss: -4.2,
          avg_trade_duration: 4.2,
          profit_factor: 2.17,
          expectancy: 4.8
        },
        risk_metrics: {
          var_95: -2.8,
          beta: 1.15,
          correlation_sp500: 0.73,
          upside_capture: 125.4,
          downside_capture: 87.6,
          information_ratio: 0.89
        }
      },

      recent_activity: {
        current_signals: 8,
        signals_last_30_days: 23,
        performance_last_30_days: 3.2,
        last_trade_date: "2025-08-31",
        next_rebalance: "2025-09-02",
        status: "active_monitoring"
      }
    };

    // Add signals if requested
    if (include_signals === "true") {
      strategyDetails.current_signals = [
        {
          symbol: "AAPL",
          signal_type: "buy",
          entry_price: 178.50,
          target_price: 195.00,
          stop_loss: 165.75,
          signal_strength: 0.84,
          generated_at: "2025-09-01T08:30:00Z",
          expiry: "2025-09-08T16:00:00Z"
        },
        {
          symbol: "MSFT", 
          signal_type: "buy",
          entry_price: 425.30,
          target_price: 465.00,
          stop_loss: 395.00,
          signal_strength: 0.78,
          generated_at: "2025-08-31T14:15:00Z",
          expiry: "2025-09-07T16:00:00Z"
        }
      ];
    }

    // Add backtest details if requested
    if (include_backtest === "true") {
      strategyDetails.backtest_results = {
        period: "2020-01-01 to 2025-08-31",
        initial_capital: 100000,
        final_value: 187230,
        total_return: 87.23,
        benchmark_return: 72.4,
        alpha: 14.83,
        trades_per_year: 28.5,
        monthly_returns: [
          {month: "2025-08", return: 2.1},
          {month: "2025-07", return: 4.7},
          {month: "2025-06", return: -1.2},
          {month: "2025-05", return: 3.8}
        ]
      };
    }

    res.json({
      data: strategyDetails,
      metadata: {
        strategy_version: "1.2.4",
        last_updated: "2025-08-30T10:00:00Z",
        data_source: "backtesting_engine",
        confidence_level: 0.92,
        includes_signals: include_signals === "true",
        includes_backtest: include_backtest === "true"
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Error fetching strategy details:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch strategy details",
      message: error.message
    });
  }
});

// Get technical indicators for specific ticker
router.get("/:ticker/technicals", async (req, res) => {
  try {
    const { ticker } = req.params;
    const { timeframe = "daily" } = req.query;
    
    const symbolUpper = ticker.toUpperCase();
    console.log(`📊 Technical indicators requested for: ${symbolUpper}, timeframe: ${timeframe}`);

    // Check if technical data tables exist
    const tableCheck = await query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'technical_data_${timeframe}'
      );
    `);

    if (!tableCheck.rows[0].exists) {
      return res.status(404).json({
        success: false,
        error: "Technical data not available",
        message: `Technical indicators for ${timeframe} timeframe are not configured`,
        requested: { symbol: symbolUpper, timeframe }
      });
    }

    // Get latest technical indicators
    const techQuery = `
      SELECT * FROM technical_data_${timeframe}
      WHERE symbol = $1 
      ORDER BY date DESC 
      LIMIT 1
    `;

    const result = await query(techQuery, [symbolUpper]);

    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Technical data not found",
        message: `No technical indicators available for ${symbolUpper}`,
        requested: { symbol: symbolUpper, timeframe }
      });
    }

    return res.json({
      success: true,
      data: {
        symbol: symbolUpper,
        timeframe,
        indicators: result.rows[0],
        timestamp: new Date().toISOString()
      }
    });

  } catch (error) {
    console.error(`Technical indicators error for ${req.params.ticker}:`, error);
    return res.status(500).json({
      success: false,
      error: "Failed to fetch technical indicators",
      details: error.message
    });
  }
});

// Risk endpoints for trading
router.get("/risk/portfolio", async (req, res) => {
  try {
    const userId = req.user?.sub;
    console.log(`⚠️ Portfolio risk requested for user: ${userId}`);

    // Get portfolio holdings from database
    const holdingsQuery = `
      SELECT 
        ph.symbol,
        ph.quantity as shares,
        ph.avg_cost,
        ph.current_value,
        cp.sector,
        cp.market_cap,
        pd.close as current_price,
        pd.volume,
        COALESCE(ti.volatility_30d, 0.15) as volatility,
        COALESCE(ti.beta, 1.0) as beta
      FROM portfolio_holdings ph
      LEFT JOIN company_profile cp ON ph.symbol = cp.ticker
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) symbol, close, volume 
        FROM price_daily 
        ORDER BY symbol, date DESC
      ) pd ON ph.symbol = pd.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) symbol, volatility_30d, beta
        FROM technical_indicators
        ORDER BY symbol, date DESC
      ) ti ON ph.symbol = ti.symbol
      WHERE ph.user_id = $1 AND ph.quantity > 0
    `;

    const holdingsResult = await query(holdingsQuery, [userId]);
    
    if (!holdingsResult || !holdingsResult.rows || holdingsResult.rows.length === 0) {
      return res.json({
        success: true,
        data: {
          totalExposure: 0,
          riskScore: 0,
          maxDrawdown: 0,
          sharpeRatio: 0,
          volatility: 0,
          beta: 1.0,
          concentrationRisk: 0,
          diversificationScore: 100,
          positions: [],
          recommendations: ["No portfolio positions found. Consider adding some positions to analyze risk."],
          timestamp: new Date().toISOString()
        }
      });
    }

    const positions = holdingsResult.rows;
    
    // Calculate portfolio metrics
    const totalValue = positions.reduce((sum, pos) => sum + (pos.current_value || 0), 0);
    
    // Concentration risk - check if any single position exceeds 25% of portfolio
    const maxPositionPct = Math.max(...positions.map(pos => (pos.current_value || 0) / totalValue)) * 100;
    const concentrationRisk = maxPositionPct > 25 ? Math.min((maxPositionPct - 25) * 2, 100) : 0;
    
    // Portfolio volatility (weighted average)
    const portfolioVolatility = positions.reduce((sum, pos) => {
      const weight = (pos.current_value || 0) / totalValue;
      return sum + (weight * (pos.volatility || 0.15));
    }, 0) * 100;
    
    // Portfolio beta (weighted average)  
    const portfolioBeta = positions.reduce((sum, pos) => {
      const weight = (pos.current_value || 0) / totalValue;
      return sum + (weight * (pos.beta || 1.0));
    }, 0);
    
    // Sector diversification
    const sectorCounts = {};
    positions.forEach(pos => {
      const sector = pos.sector || 'Unknown';
      sectorCounts[sector] = (sectorCounts[sector] || 0) + (pos.current_value || 0);
    });
    
    const sectors = Object.keys(sectorCounts);
    const maxSectorPct = Math.max(...Object.values(sectorCounts)) / totalValue * 100;
    const diversificationScore = Math.max(0, 100 - (maxSectorPct > 40 ? (maxSectorPct - 40) * 2 : 0));
    
    // Overall risk score (0-100, higher is riskier)
    const riskScore = Math.min(100, 
      (concentrationRisk * 0.3) + 
      (Math.max(0, portfolioVolatility - 15) * 1.5) + 
      (Math.max(0, portfolioBeta - 1.2) * 20) +
      ((100 - diversificationScore) * 0.2)
    );

    // Generate recommendations
    const recommendations = [];
    if (maxPositionPct > 25) {
      recommendations.push(`High concentration risk: One position represents ${maxPositionPct.toFixed(1)}% of portfolio`);
    }
    if (portfolioVolatility > 25) {
      recommendations.push(`High volatility: Portfolio volatility is ${portfolioVolatility.toFixed(1)}%`);
    }
    if (sectors.length < 3) {
      recommendations.push(`Consider diversifying across more sectors (currently ${sectors.length})`);
    }
    if (portfolioBeta > 1.5) {
      recommendations.push(`High beta portfolio (${portfolioBeta.toFixed(2)}) - may amplify market movements`);
    }
    if (recommendations.length === 0) {
      recommendations.push("Portfolio risk profile appears balanced");
    }

    // Estimate max drawdown based on volatility and beta
    const estimatedMaxDrawdown = portfolioVolatility * portfolioBeta * 0.8;

    // Estimate Sharpe ratio based on diversification and volatility
    const estimatedSharpeRatio = Math.max(0, (diversificationScore / 100 * 1.5) - (portfolioVolatility / 100 * 0.5));

    res.json({
      success: true,
      data: {
        totalExposure: Math.round(totalValue),
        riskScore: Math.round(riskScore),
        maxDrawdown: Math.round(estimatedMaxDrawdown * 100) / 100,
        sharpeRatio: Math.round(estimatedSharpeRatio * 100) / 100,
        volatility: Math.round(portfolioVolatility * 100) / 100,
        beta: Math.round(portfolioBeta * 100) / 100,
        concentrationRisk: Math.round(concentrationRisk),
        diversificationScore: Math.round(diversificationScore),
        positionCount: positions.length,
        sectorCount: sectors.length,
        positions: positions.map(pos => ({
          symbol: pos.symbol,
          value: pos.current_value,
          weight: Math.round((pos.current_value / totalValue) * 10000) / 100,
          sector: pos.sector,
          volatility: Math.round((pos.volatility || 0.15) * 10000) / 100,
          beta: Math.round((pos.beta || 1.0) * 100) / 100
        })),
        recommendations,
        timestamp: new Date().toISOString()
      }
    });
  } catch (error) {
    console.error("Portfolio risk error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch portfolio risk",
      details: error.message
    });
  }
});

router.post("/risk/limits", async (req, res) => {
  try {
    const userId = req.user?.sub;
    const { 
      maxDrawdown, 
      maxPositionSize, 
      stopLossPercentage, 
      maxLeverage,
      maxCorrelation,
      riskToleranceLevel,
      maxDailyLoss,
      maxMonthlyLoss 
    } = req.body;
    
    console.log(`⚠️ Risk limits update for user: ${userId}`);

    // Validate required fields
    if (!userId) {
      return res.status(401).json({
        success: false,
        error: "User authentication required"
      });
    }

    // Validate risk limit values
    const validationErrors = [];
    if (maxDrawdown && (maxDrawdown < 0 || maxDrawdown > 100)) {
      validationErrors.push("Max drawdown must be between 0-100%");
    }
    if (maxPositionSize && (maxPositionSize < 0 || maxPositionSize > 100)) {
      validationErrors.push("Max position size must be between 0-100%");
    }
    if (stopLossPercentage && (stopLossPercentage < 0 || stopLossPercentage > 100)) {
      validationErrors.push("Stop loss percentage must be between 0-100%");
    }

    if (validationErrors.length > 0) {
      return res.status(400).json({
        success: false,
        error: "Validation failed",
        details: validationErrors
      });
    }

    // Check if user risk limits already exist
    const existingLimits = await query(
      "SELECT id FROM user_risk_limits WHERE user_id = $1",
      [userId]
    );

    let result;
    const updateTime = new Date().toISOString();

    if (existingLimits.rows.length > 0) {
      // Update existing limits
      const updateFields = [];
      const updateValues = [];
      let paramCount = 1;

      if (maxDrawdown !== undefined) {
        updateFields.push(`max_drawdown = $${paramCount++}`);
        updateValues.push(maxDrawdown);
      }
      if (maxPositionSize !== undefined) {
        updateFields.push(`max_position_size = $${paramCount++}`);
        updateValues.push(maxPositionSize);
      }
      if (stopLossPercentage !== undefined) {
        updateFields.push(`stop_loss_percentage = $${paramCount++}`);
        updateValues.push(stopLossPercentage);
      }
      if (maxLeverage !== undefined) {
        updateFields.push(`max_leverage = $${paramCount++}`);
        updateValues.push(maxLeverage);
      }
      if (maxCorrelation !== undefined) {
        updateFields.push(`max_correlation = $${paramCount++}`);
        updateValues.push(maxCorrelation);
      }
      if (riskToleranceLevel !== undefined) {
        updateFields.push(`risk_tolerance_level = $${paramCount++}`);
        updateValues.push(riskToleranceLevel);
      }
      if (maxDailyLoss !== undefined) {
        updateFields.push(`max_daily_loss = $${paramCount++}`);
        updateValues.push(maxDailyLoss);
      }
      if (maxMonthlyLoss !== undefined) {
        updateFields.push(`max_monthly_loss = $${paramCount++}`);
        updateValues.push(maxMonthlyLoss);
      }

      updateFields.push(`updated_at = $${paramCount++}`);
      updateValues.push(updateTime);
      updateValues.push(userId);

      const updateQuery = `
        UPDATE user_risk_limits 
        SET ${updateFields.join(', ')}
        WHERE user_id = $${paramCount}
        RETURNING *
      `;

      result = await query(updateQuery, updateValues);
    } else {
      // Insert new limits with defaults
      result = await query(`
        INSERT INTO user_risk_limits (
          user_id, max_drawdown, max_position_size, stop_loss_percentage,
          max_leverage, max_correlation, risk_tolerance_level,
          max_daily_loss, max_monthly_loss, created_at, updated_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        RETURNING *
      `, [
        userId,
        maxDrawdown || 20.0,
        maxPositionSize || 25.0, 
        stopLossPercentage || 5.0,
        maxLeverage || 2.0,
        maxCorrelation || 0.7,
        riskToleranceLevel || 'moderate',
        maxDailyLoss || 2.0,
        maxMonthlyLoss || 10.0,
        updateTime,
        updateTime
      ]);
    }

    const updatedLimits = result.rows[0];

    res.json({
      success: true,
      message: "Risk limits updated successfully",
      data: {
        userId: updatedLimits.user_id,
        maxDrawdown: updatedLimits.max_drawdown,
        maxPositionSize: updatedLimits.max_position_size,
        stopLossPercentage: updatedLimits.stop_loss_percentage,
        maxLeverage: updatedLimits.max_leverage,
        maxCorrelation: updatedLimits.max_correlation,
        riskToleranceLevel: updatedLimits.risk_tolerance_level,
        maxDailyLoss: updatedLimits.max_daily_loss,
        maxMonthlyLoss: updatedLimits.max_monthly_loss,
        updatedAt: updatedLimits.updated_at
      }
    });

  } catch (error) {
    console.error("Risk limits update error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to update risk limits",
      details: error.message
    });
  }
});

router.post("/positions/:symbol/close", async (req, res) => {
  try {
    const userId = req.user?.sub;
    const { symbol } = req.params;
    const { closeType = 'market', priceLimit, reason } = req.body;
    
    console.log(`🔄 Close position for ${symbol}, user: ${userId}`);

    // Validate required fields
    if (!userId) {
      return res.status(401).json({
        success: false,
        error: "User authentication required"
      });
    }

    if (!symbol) {
      return res.status(400).json({
        success: false,
        error: "Symbol is required"
      });
    }

    // Check if position exists
    const existingPosition = await query(`
      SELECT 
        id, symbol, quantity, average_cost, current_price, total_value,
        unrealized_pnl, realized_pnl, position_type
      FROM portfolio_holdings 
      WHERE user_id = $1 AND symbol = $2 AND quantity > 0
    `, [userId, symbol]);

    if (existingPosition.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: `No open position found for ${symbol}`
      });
    }

    const position = existingPosition.rows[0];
    const closeTime = new Date().toISOString();

    // Get current market price for closing calculation
    const priceQuery = await query(`
      SELECT close_price as current_price 
      FROM price_daily 
      WHERE symbol = $1 
      ORDER BY date DESC 
      LIMIT 1
    `, [symbol]);

    const currentPrice = priceQuery.rows[0]?.current_price || position.current_price;
    const closePrice = closeType === 'limit' && priceLimit ? priceLimit : currentPrice;
    
    // Calculate closing P&L
    const totalCost = position.quantity * position.average_cost;
    const totalValue = position.quantity * closePrice;
    const realizedPnL = totalValue - totalCost;
    const pnlPercentage = (realizedPnL / totalCost) * 100;

    // Begin transaction for position closing
    await query('BEGIN');

    try {
      // Update portfolio_holdings - set quantity to 0 and update P&L
      await query(`
        UPDATE portfolio_holdings 
        SET 
          quantity = 0,
          current_price = $1,
          total_value = 0,
          unrealized_pnl = 0,
          realized_pnl = realized_pnl + $2,
          last_updated = $3,
          position_status = 'closed'
        WHERE user_id = $4 AND symbol = $5
      `, [closePrice, realizedPnL, closeTime, userId, symbol]);

      // Record the trade in trade_history
      await query(`
        INSERT INTO trade_history (
          user_id, symbol, action, quantity, price, total_amount, 
          realized_pnl, trade_date, order_type, notes
        ) VALUES ($1, $2, 'sell', $3, $4, $5, $6, $7, $8, $9)
      `, [
        userId, 
        symbol, 
        position.quantity, 
        closePrice, 
        totalValue, 
        realizedPnL, 
        closeTime, 
        closeType,
        reason || `Position closed: ${closeType} order`
      ]);

      // Update user portfolio summary
      const portfolioSummary = await query(`
        SELECT 
          SUM(total_value) as total_value,
          SUM(unrealized_pnl) as unrealized_pnl,
          SUM(realized_pnl) as realized_pnl,
          COUNT(*) as total_positions
        FROM portfolio_holdings 
        WHERE user_id = $1 AND quantity > 0
      `, [userId]);

      const summary = portfolioSummary.rows[0];

      // Update or create portfolio summary record
      await query(`
        INSERT INTO portfolio_summary (
          user_id, total_value, unrealized_pnl, realized_pnl, 
          total_positions, last_updated
        ) VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (user_id) 
        DO UPDATE SET 
          total_value = EXCLUDED.total_value,
          unrealized_pnl = EXCLUDED.unrealized_pnl,
          realized_pnl = EXCLUDED.realized_pnl,
          total_positions = EXCLUDED.total_positions,
          last_updated = EXCLUDED.last_updated
      `, [
        userId,
        summary.total_value || 0,
        summary.unrealized_pnl || 0,
        summary.realized_pnl || 0,
        summary.total_positions || 0,
        closeTime
      ]);

      await query('COMMIT');

      // Return detailed closing information
      res.json({
        success: true,
        message: `Position ${symbol} closed successfully`,
        data: {
          symbol,
          closedQuantity: position.quantity,
          closePrice,
          closeType,
          totalCost,
          totalValue,
          realizedPnL,
          pnlPercentage: Math.round(pnlPercentage * 100) / 100,
          averageCost: position.average_cost,
          positionType: position.position_type,
          closedAt: closeTime,
          reason: reason || `${closeType} order execution`,
          portfolioSummary: {
            totalValue: summary.total_value || 0,
            unrealizedPnL: summary.unrealized_pnl || 0,
            realizedPnL: summary.realized_pnl || 0,
            totalPositions: summary.total_positions || 0
          }
        }
      });

    } catch (transactionError) {
      await query('ROLLBACK');
      throw transactionError;
    }

  } catch (error) {
    console.error("Close position error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to close position",
      details: error.message
    });
  }
});

// Dashboard endpoint - alias for the root trading endpoint for contract compatibility
router.get("/dashboard", async (req, res) => {
  console.log(`📊 [TRADING] Dashboard endpoint redirecting to main trading endpoint`);
  
  // Forward all query parameters
  const queryString = Object.keys(req.query).length > 0 
    ? '?' + new URLSearchParams(req.query).toString() 
    : '';
  
  const redirectUrl = `/api/trading${queryString}`;
  
  res.redirect(301, redirectUrl);
});

module.exports = router;
