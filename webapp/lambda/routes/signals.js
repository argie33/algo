const express = require("express");

const { query } = require("../utils/database");
const responseFormatter = require("../middleware/responseFormatter");
const { authenticateToken } = require("../middleware/auth");

const router = express.Router();

// Apply response formatter middleware to all routes
router.use(responseFormatter);

// Signal backtest endpoint
router.post("/backtest", async (req, res) => {
  try {
    const {
      signal_type,
      symbols,
      start_date,
      end_date,
      parameters = {},
    } = req.body;

    if (!signal_type) {
      return res.status(400).json({
        success: false,
        error: "signal_type is required",
        validTypes: ["buy", "sell", "momentum", "reversal", "breakout"],
      });
    }

    console.log(
      `🧪 Signal backtest requested: ${signal_type} for ${symbols?.length || "all"} symbols`
    );

    // Validate parameters
    const startDate = new Date(start_date || "2023-01-01");
    const endDate = new Date(end_date || new Date());

    if (startDate >= endDate) {
      return res.status(400).json({
        success: false,
        error: "start_date must be before end_date",
      });
    }

    // Build symbol filter
    let symbolFilter = "";
    let params = [];
    let paramIndex = 1;

    if (symbols && symbols.length > 0) {
      symbolFilter = `AND bs.symbol = ANY($${paramIndex}::text[])`;
      params.push(symbols);
      paramIndex++;
    }

    // Get historical signal performance
    const backtestQuery = `
      SELECT 
        bs.symbol,
        bs.signal,
        bs.date as signal_date,
        bs.confidence,
        pd.close as entry_price,
        pd_future.close as exit_price,
        pd_future.date as exit_date,
        CASE 
          WHEN pd.close > 0 AND pd_future.close > 0 
          THEN ((pd_future.close - pd.close) / pd.close * 100)
          ELSE 0
        END as return_percent,
        cp.sector,
        cp.market_cap
      FROM buy_sell_daily bs
      JOIN price_daily pd ON bs.symbol = pd.symbol AND bs.date = pd.date
      LEFT JOIN price_daily pd_future ON bs.symbol = pd_future.symbol 
        AND pd_future.date = bs.date + INTERVAL '30 days'
      LEFT JOIN company_profile cp ON bs.symbol = cp.ticker
      WHERE bs.date >= $${paramIndex} 
        AND bs.date <= $${paramIndex + 1}
        AND bs.signal IS NOT NULL
        AND bs.signal != ''
        ${symbolFilter}
      ORDER BY bs.date DESC, bs.symbol
      LIMIT 1000
    `;

    params.push(startDate, endDate);

    const results = await query(backtestQuery, params);
    const backtestResults = results.rows || [];

    // Calculate performance metrics
    const totalTrades = backtestResults.length;
    const profitableTrades = backtestResults.filter(
      (r) => r.return_percent > 0
    ).length;
    const avgReturn =
      totalTrades > 0
        ? backtestResults.reduce((sum, r) => sum + r.return_percent, 0) /
          totalTrades
        : 0;

    const winRate =
      totalTrades > 0 ? (profitableTrades / totalTrades) * 100 : 0;

    // Performance by signal type
    const signalPerformance = backtestResults.reduce((acc, trade) => {
      if (!acc[trade.signal]) {
        acc[trade.signal] = { trades: 0, totalReturn: 0, wins: 0 };
      }
      acc[trade.signal].trades++;
      acc[trade.signal].totalReturn += trade.return_percent;
      if (trade.return_percent > 0) acc[trade.signal].wins++;
      return acc;
    }, {});

    // Add average return and win rate for each signal
    Object.keys(signalPerformance).forEach((signal) => {
      const perf = signalPerformance[signal];
      perf.avgReturn = perf.trades > 0 ? perf.totalReturn / perf.trades : 0;
      perf.winRate = perf.trades > 0 ? (perf.wins / perf.trades) * 100 : 0;
    });

    res.json({
      success: true,
      data: {
        backtestSummary: {
          totalTrades,
          profitableTrades,
          avgReturn: parseFloat(avgReturn.toFixed(2)),
          winRate: parseFloat(winRate.toFixed(2)),
          bestTrade:
            backtestResults.length > 0
              ? Math.max(...backtestResults.map((r) => r.return_percent))
              : 0,
          worstTrade:
            backtestResults.length > 0
              ? Math.min(...backtestResults.map((r) => r.return_percent))
              : 0,
        },
        signalPerformance,
        trades: backtestResults.slice(0, 100), // Return top 100 trades
        parameters: {
          signal_type,
          symbols: symbols || "all",
          start_date,
          end_date,
          ...parameters,
        },
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Signal backtest error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to perform signal backtest",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

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
      return res
        .status(400)
        .json({
          success: false,
          error: "Invalid timeframe. Must be daily, weekly, or monthly",
        });
    }

    const tableName = `buy_sell_${timeframe}`;

    const buySignalsQuery = `
      SELECT 
        bs.symbol,
        cp.name as company_name,
        cp.sector,
        bs.signal,
        bs.date,
        s.price as current_price,
        s.market_cap,
        NULL as trailing_pe,
        s.dividend_yield
      FROM ${tableName} bs
      JOIN company_profile cp ON bs.symbol = cp.ticker
      LEFT JOIN stocks s ON bs.symbol = s.symbol
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
    if (
      !signalsResult ||
      !signalsResult.rows ||
      !countResult ||
      !countResult.rows
    ) {
      console.warn(
        "Buy signals query returned null result, database may be unavailable"
      );
      return res
        .status(500)
        .json({
          success: false,
          error:
            "Trading signals temporarily unavailable - database connection issue",
          type: "service_unavailable",
          data: [],
          timeframe,
        });
    }

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    // Transform data to camelCase - signal is text ('BUY', 'SELL', 'HOLD')
    const transformedData = signalsResult.rows.map((row) => ({
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
      return res.json({
        data: [],
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

    res.json({
      data: transformedData,
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
    return res
      .status(500)
      .json({
        success: false,
        error: "Failed to fetch buy signals",
        details: error.message,
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
      return res
        .status(400)
        .json({
          success: false,
          error: "Invalid timeframe. Must be daily, weekly, or monthly",
        });
    }

    const tableName = `buy_sell_${timeframe}`;

    const sellSignalsQuery = `
      SELECT 
        bs.symbol,
        cp.name as company_name,
        cp.sector,
        bs.signal,
        bs.date,
        s.price as current_price,
        s.market_cap,
        NULL as trailing_pe,
        s.dividend_yield
      FROM ${tableName} bs
      JOIN company_profile cp ON bs.symbol = cp.ticker
      LEFT JOIN stocks s ON bs.symbol = s.symbol
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
    if (
      !signalsResult ||
      !signalsResult.rows ||
      !countResult ||
      !countResult.rows
    ) {
      console.warn(
        "Sell signals query returned null result, database may be unavailable"
      );
      return res
        .status(500)
        .json({
          success: false,
          error:
            "Sell signals temporarily unavailable - database connection issue",
          type: "service_unavailable",
          data: [],
          timeframe,
        });
    }

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    // Transform data to camelCase - signal is text ('BUY', 'SELL', 'HOLD')
    const transformedData = signalsResult.rows.map((row) => ({
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
      return res.json({
        data: [],
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

    res.json({
      data: transformedData,
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
    return res
      .status(500)
      .json({
        success: false,
        error: "Failed to fetch sell signals",
        details: error.message,
      });
  }
});

// Get recent signals
router.get("/recent", async (req, res) => {
  try {
    const { limit = 10, hours = 24 } = req.query;
    const timeframe = req.query.timeframe || "daily";

    console.log(
      `🔔 Recent signals requested, limit: ${limit}, hours: ${hours}`
    );

    // Validate timeframe
    const validTimeframes = ["daily", "weekly", "monthly"];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({
        success: false,
        error: "Invalid timeframe. Must be daily, weekly, or monthly",
      });
    }

    const tableName = `buy_sell_${timeframe}`;
    const hoursAgo = new Date();
    hoursAgo.setHours(hoursAgo.getHours() - parseInt(hours));

    const result = await query(
      `
      SELECT 
        bs.symbol,
        cp.name as company_name,
        cp.sector,
        bs.signal,
        bs.date,
        s.price as current_price,
        s.market_cap,
        NULL as trailing_pe,
        s.dividend_yield
      FROM ${tableName} bs
      JOIN company_profile cp ON bs.symbol = cp.ticker
      LEFT JOIN stocks s ON bs.symbol = s.symbol
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
    const transformedData = result.rows.map((row) => ({
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
        since: hoursAgo.toISOString(),
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Recent signals error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch recent signals",
      details: error.message,
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
      return res
        .status(400)
        .json({
          success: false,
          error: "Invalid timeframe. Must be daily, weekly, or monthly",
        });
    }

    const tableName = `buy_sell_${timeframe}`;

    // Get both buy and sell signals
    const [buySignalsQuery, sellSignalsQuery, countQuery] = [
      `
      SELECT 
        bs.symbol,
        cp.name as company_name,
        cp.sector,
        bs.signal,
        bs.date,
        s.price as current_price,
        s.market_cap,
        NULL as trailing_pe,
        s.dividend_yield,
        'buy' as signal_type
      FROM ${tableName} bs
      JOIN company_profile cp ON bs.symbol = cp.ticker
      LEFT JOIN stocks s ON bs.symbol = s.symbol
      WHERE bs.signal IS NOT NULL 
        AND bs.signal != '' 
        AND bs.signal IN ('BUY', 'SELL', 'HOLD')
      ORDER BY bs.signal DESC, bs.date DESC
      LIMIT $1
      `,
      `
      SELECT 
        bs.symbol,
        cp.name as company_name,
        cp.sector,
        bs.signal,
        bs.date,
        s.price as current_price,
        s.market_cap,
        NULL as trailing_pe,
        s.dividend_yield,
        'sell' as signal_type
      FROM ${tableName} bs
      JOIN company_profile cp ON bs.symbol = cp.ticker
      LEFT JOIN stocks s ON bs.symbol = s.symbol
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
      `,
    ];

    const [buyResult, sellResult, countResult] = await Promise.all([
      query(buySignalsQuery, [Math.ceil(limit / 2)]),
      query(sellSignalsQuery, [Math.floor(limit / 2)]),
      query(countQuery),
    ]);

    // Add null checking for database availability
    if (
      !buyResult ||
      !buyResult.rows ||
      !sellResult ||
      !sellResult.rows ||
      !countResult ||
      !countResult.rows
    ) {
      console.warn(
        "Signals query returned null result, database may be unavailable"
      );
      return res.error(
        "Trading signals temporarily unavailable - database connection issue",
        500,
        {
          type: "service_unavailable",
          data: {
            buy_signals: [],
            sell_signals: [],
            summary: {
              total_buy: 0,
              total_sell: 0,
              total_signals: 0,
            },
          },
          timeframe,
        }
      );
    }

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    // Transform data to camelCase - signal is text ('BUY', 'SELL', 'HOLD')
    const buySignals = buyResult.rows.map((row) => ({
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

    const sellSignals = sellResult.rows.map((row) => ({
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

    res.json({
      success: true,
      signals: [...buySignals, ...sellSignals],
      data: {
        buy_signals: buySignals,
        sell_signals: sellSignals,
        summary: {
          total_buy: buySignals.length,
          total_sell: sellSignals.length,
          total_signals: buySignals.length + sellSignals.length,
        },
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
    return res
      .status(500)
      .json({
        success: false,
        error: "Failed to fetch signals",
        details: error.message,
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
    sector,
  } = req.query;

  console.log(
    `📈 Trading recommendations requested - type: ${type}, risk: ${risk_level}, limit: ${limit}`
  );

  try {
    // Build comprehensive trading recommendations query
    let baseQuery = `
      WITH latest_prices AS (
        SELECT DISTINCT ON (p.symbol)
          p.symbol,
          p.date,
          p.close,
          p.volume,
          p.change_percent as daily_change,
          p.high,
          p.low
        FROM price_daily p
        WHERE p.date >= CURRENT_DATE - INTERVAL '5 days'
        ORDER BY p.symbol, p.date DESC
      ),
      technical_analysis AS (
        SELECT 
          lp.symbol,
          lp.close,
          lp.volume,
          lp.daily_change,
          lp.high,
          lp.low,
          -- Technical indicators from our database
          ti.rsi_14,
          ti.macd,
          ti.historical_volatility_20d,
          ti.beta,
          ti.price_52w_high,
          ti.price_52w_low,
          -- Calculate support/resistance levels
          CASE 
            WHEN lp.close > (ti.price_52w_high * 0.95) THEN 'near_resistance'
            WHEN lp.close < (ti.price_52w_low * 1.05) THEN 'near_support'
            ELSE 'mid_range'
          END as price_position,
          -- Calculate momentum from price history
          (SELECT AVG(pd.change_percent) 
           FROM price_daily pd 
           WHERE pd.symbol = lp.symbol 
           AND pd.date >= CURRENT_DATE - INTERVAL '5 days') as momentum_5d,
          (SELECT AVG(pd.change_percent) 
           FROM price_daily pd 
           WHERE pd.symbol = lp.symbol 
           AND pd.date >= CURRENT_DATE - INTERVAL '10 days') as momentum_10d
        FROM latest_prices lp
        LEFT JOIN technical_indicators ti ON lp.symbol = ti.symbol 
        AND ti.date = (SELECT MAX(date) FROM technical_indicators WHERE symbol = ti.symbol)
      ),
      recommendation_scores AS (
        SELECT 
          ta.symbol,
          ta.close_price,
          ta.daily_change,
          ta.volume,
          ta.rsi_14,
          ta.macd,
          ta.historical_volatility_20d,
          ta.beta,
          ta.price_position,
          ta.momentum_5d,
          ta.momentum_10d,
          -- Calculate composite recommendation score
          (
            -- RSI component (0-20 points)
            CASE 
              WHEN ta.rsi_14 < 30 THEN 15  -- Oversold - bullish
              WHEN ta.rsi_14 > 70 THEN -10 -- Overbought - bearish
              WHEN ta.rsi_14 BETWEEN 40 AND 60 THEN 5  -- Neutral
              ELSE 0
            END +
            -- MACD component (0-15 points)
            CASE 
              WHEN ta.macd > 0 THEN 10     -- Bullish signal
              WHEN ta.macd < 0 THEN -5     -- Bearish signal
              ELSE 0
            END +
            -- Momentum component (0-20 points)
            CASE 
              WHEN ta.momentum_5d > 2 AND ta.momentum_10d > 1 THEN 15
              WHEN ta.momentum_5d > 0 AND ta.momentum_10d > 0 THEN 8
              WHEN ta.momentum_5d < -2 AND ta.momentum_10d < -1 THEN -10
              ELSE 0
            END +
            -- Price position component (0-10 points)
            CASE 
              WHEN ta.price_position = 'near_support' THEN 8   -- Buy near support
              WHEN ta.price_position = 'near_resistance' THEN -5  -- Sell near resistance
              ELSE 2
            END +
            -- Volatility adjustment (-5 to +5 points)
            CASE 
              WHEN ta.historical_volatility_20d > 0.4 THEN -3  -- High volatility penalty
              WHEN ta.historical_volatility_20d < 0.15 THEN 3  -- Low volatility bonus
              ELSE 0
            END
          ) as recommendation_score,
          -- Determine recommendation type
          CASE 
            WHEN ta.rsi_14 < 30 AND ta.macd > 0 AND ta.momentum_5d > 0 THEN 'STRONG_BUY'
            WHEN ta.rsi_14 < 40 AND ta.momentum_5d > 1 THEN 'BUY'
            WHEN ta.rsi_14 > 70 AND ta.momentum_5d < -1 THEN 'SELL'
            WHEN ta.rsi_14 > 60 AND ta.macd < 0 THEN 'WEAK_SELL'
            ELSE 'HOLD'
          END as recommendation_type,
          -- Risk assessment
          CASE 
            WHEN ta.beta > 1.5 OR ta.historical_volatility_20d > 0.4 THEN 'high'
            WHEN ta.beta < 0.8 AND ta.historical_volatility_20d < 0.2 THEN 'low'
            ELSE 'medium'
          END as risk_level
        FROM technical_analysis ta
        WHERE ta.close_price IS NOT NULL
      )
      SELECT 
        rs.symbol,
        rs.close_price as current_price,
        rs.daily_change,
        rs.volume,
        rs.recommendation_type,
        ROUND(rs.recommendation_score::numeric, 2) as score,
        rs.risk_level,
        rs.price_position,
        ROUND(rs.momentum_5d::numeric, 2) as momentum_5d,
        ROUND(rs.momentum_10d::numeric, 2) as momentum_10d,
        rs.rsi_14,
        rs.macd,
        ROUND(rs.historical_volatility_20d::numeric, 4) as volatility,
        rs.beta,
        -- Additional analysis
        CASE 
          WHEN rs.recommendation_type IN ('STRONG_BUY', 'BUY') THEN 'Consider buying - favorable technical signals'
          WHEN rs.recommendation_type = 'HOLD' THEN 'Monitor position - mixed signals'
          WHEN rs.recommendation_type IN ('SELL', 'WEAK_SELL') THEN 'Consider selling - unfavorable technical signals'
          ELSE 'No clear signal'
        END as analysis,
        CURRENT_TIMESTAMP as recommendation_date
      FROM recommendation_scores rs
    `;

    // Apply filters
    const conditions = [];
    const params = [];
    let paramIndex = 1;

    if (type && type.toLowerCase() !== "all") {
      conditions.push(`rs.recommendation_type = $${paramIndex}`);
      params.push(type.toUpperCase());
      paramIndex++;
    }

    if (risk_level && risk_level.toLowerCase() !== "all") {
      conditions.push(`rs.risk_level = $${paramIndex}`);
      params.push(risk_level.toLowerCase());
      paramIndex++;
    }

    if (parseFloat(min_score) > 0) {
      conditions.push(`rs.recommendation_score >= $${paramIndex}`);
      params.push(parseFloat(min_score));
      paramIndex++;
    }

    if (sector) {
      // Note: We would need a sectors table to filter by sector
      // For now, we'll include this in the response structure
    }

    // Add WHERE clause if we have conditions
    if (conditions.length > 0) {
      baseQuery += ` WHERE ${conditions.join(" AND ")}`;
    }

    // Add ordering and limiting
    baseQuery += ` ORDER BY rs.recommendation_score DESC, rs.symbol ASC`;
    baseQuery += ` LIMIT ${parseInt(limit)}`;

    const results = await query(baseQuery, params);

    // Calculate summary statistics
    const recommendationsData = results.rows || [];
    const totalRecommendations = recommendationsData.length;
    const buySignals = recommendationsData.filter((r) =>
      ["STRONG_BUY", "BUY"].includes(r.recommendation_type)
    ).length;
    const sellSignals = recommendationsData.filter((r) =>
      ["SELL", "WEAK_SELL"].includes(r.recommendation_type)
    ).length;
    const holdSignals = recommendationsData.filter(
      (r) => r.recommendation_type === "HOLD"
    ).length;

    const avgScore =
      recommendationsData.length > 0
        ? (
            results.reduce((sum, r) => sum + parseFloat(r.score), 0) /
            results.length
          ).toFixed(2)
        : 0;

    return res.json({
      success: true,
      data: {
        recommendations: recommendationsData,
        summary: {
          total_recommendations: totalRecommendations,
          buy_signals: buySignals,
          sell_signals: sellSignals,
          hold_signals: holdSignals,
          average_score: parseFloat(avgScore),
          signal_distribution: {
            buy: Math.round(
              (buySignals / Math.max(totalRecommendations, 1)) * 100
            ),
            sell: Math.round(
              (sellSignals / Math.max(totalRecommendations, 1)) * 100
            ),
            hold: Math.round(
              (holdSignals / Math.max(totalRecommendations, 1)) * 100
            ),
          },
        },
      },
      filters: {
        type: type,
        risk_level: risk_level,
        min_score: parseFloat(min_score),
        sector: sector || null,
        limit: parseInt(limit),
      },
      algorithm: "multi_factor_technical_analysis",
      scoring_methodology: {
        rsi_weight: "0-20 points (oversold/overbought conditions)",
        macd_weight: "0-15 points (trend confirmation)",
        momentum_weight: "0-20 points (5d and 10d momentum)",
        price_position_weight: "0-10 points (support/resistance levels)",
        volatility_adjustment: "-5 to +5 points (risk adjustment)",
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("❌ Error generating trading recommendations:", error);
    return res.status(500).json({
      success: false,
      error: "Failed to generate trading recommendations",
      message: error.message,
      troubleshooting: {
        suggestion:
          "Check database connection and ensure required tables have data",
        required_tables: ["price_daily", "technical_indicators"],
        error_details:
          process.env.NODE_ENV === "development" ? error.stack : undefined,
      },
      timestamp: new Date().toISOString(),
    });
  }
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
    sortOrder = "desc",
  } = req.query;

  console.log(
    `📈 Momentum signals requested - symbol: ${symbol || "all"}, timeframe: ${timeframe}, strength: ${strength}`
  );

  try {
    // Build the base query for momentum signals
    let baseQuery = `
      WITH price_changes AS (
        SELECT 
          p.symbol,
          p.date,
          p.close as close_price,
          p.volume,
          p.change_percent as daily_change,
          LAG(p.close, 5) OVER (PARTITION BY p.symbol ORDER BY p.date) as price_5d_ago,
          LAG(p.close, 10) OVER (PARTITION BY p.symbol ORDER BY p.date) as price_10d_ago,
          LAG(p.close, 20) OVER (PARTITION BY p.symbol ORDER BY p.date) as price_20d_ago,
          AVG(p.volume) OVER (PARTITION BY p.symbol ORDER BY p.date ROWS 20 PRECEDING) as avg_volume_20d
        FROM price_daily p
        WHERE p.date >= CURRENT_DATE - INTERVAL '60 days'
      ),
      momentum_calculations AS (
        SELECT 
          pc.symbol,
          pc.date,
          pc.close_price,
          pc.daily_change,
          pc.volume,
          pc.avg_volume_20d,
          -- Calculate momentum percentages
          CASE WHEN pc.price_5d_ago > 0 THEN ((pc.close_price - pc.price_5d_ago) / pc.price_5d_ago * 100) ELSE 0 END as momentum_5d,
          CASE WHEN pc.price_10d_ago > 0 THEN ((pc.close_price - pc.price_10d_ago) / pc.price_10d_ago * 100) ELSE 0 END as momentum_10d,
          CASE WHEN pc.price_20d_ago > 0 THEN ((pc.close_price - pc.price_20d_ago) / pc.price_20d_ago * 100) ELSE 0 END as momentum_20d,
          -- Volume momentum (relative to average)
          CASE WHEN pc.avg_volume_20d > 0 THEN (pc.volume / pc.avg_volume_20d) ELSE 1 END as volume_ratio,
          -- Get technical indicators
          ti.rsi_14,
          ti.macd
        FROM price_changes pc
        LEFT JOIN technical_indicators ti ON pc.symbol = ti.symbol AND pc.date = ti.date
        WHERE pc.price_5d_ago IS NOT NULL 
        AND pc.price_10d_ago IS NOT NULL 
        AND pc.price_20d_ago IS NOT NULL
      ),
      momentum_scores AS (
        SELECT 
          mc.symbol,
          mc.date,
          mc.close_price,
          mc.daily_change,
          mc.volume,
          mc.volume_ratio,
          mc.momentum_5d,
          mc.momentum_10d,
          mc.momentum_20d,
          mc.rsi_14,
          mc.macd,
          -- Calculate composite momentum score (weighted average)
          (
            COALESCE(mc.momentum_5d, 0) * 0.4 + 
            COALESCE(mc.momentum_10d, 0) * 0.3 + 
            COALESCE(mc.momentum_20d, 0) * 0.2 +
            CASE WHEN mc.volume_ratio > 1.5 THEN 2 ELSE 0 END +
            CASE WHEN mc.rsi_14 > 60 THEN 1 WHEN mc.rsi_14 < 40 THEN -1 ELSE 0 END +
            CASE WHEN mc.macd > 0 THEN 1 ELSE -1 END
          ) as momentum_score,
          -- Determine strength category
          CASE 
            WHEN (mc.momentum_5d > 5 AND mc.momentum_10d > 3 AND mc.volume_ratio > 1.5) THEN 'strong'
            WHEN (mc.momentum_5d > 2 AND mc.momentum_10d > 1) THEN 'moderate' 
            WHEN (mc.momentum_5d > 0 OR mc.momentum_10d > 0) THEN 'weak'
            ELSE 'neutral'
          END as strength_category
        FROM momentum_calculations mc
        WHERE mc.date = (SELECT MAX(date) FROM momentum_calculations WHERE symbol = mc.symbol)
      )
      SELECT 
        ms.symbol,
        ms.close_price as current_price,
        ms.daily_change,
        ms.volume,
        ms.volume_ratio,
        ROUND(ms.momentum_5d::numeric, 2) as momentum_5d,
        ROUND(ms.momentum_10d::numeric, 2) as momentum_10d, 
        ROUND(ms.momentum_20d::numeric, 2) as momentum_20d,
        ROUND(ms.momentum_score::numeric, 2) as momentum_score,
        ms.strength_category,
        ms.rsi_14,
        ms.macd,
        ms.date as signal_date
      FROM momentum_scores ms
    `;

    // Add symbol filter if specified
    if (symbol && symbol.toLowerCase() !== "all") {
      baseQuery += ` WHERE ms.symbol = $1`;
    }

    // Add strength filter
    if (strength && strength.toLowerCase() !== "all") {
      const whereClause =
        symbol && symbol.toLowerCase() !== "all" ? " AND" : " WHERE";
      baseQuery += `${whereClause} ms.strength_category = '${strength.toLowerCase()}'`;
    }

    // Add sorting and pagination
    baseQuery += ` ORDER BY ms.${sortBy} ${sortOrder.toUpperCase()}`;
    const offset = (parseInt(page) - 1) * parseInt(limit);
    baseQuery += ` LIMIT ${parseInt(limit)} OFFSET ${offset}`;

    // Execute query with or without symbol parameter
    const params =
      symbol && symbol.toLowerCase() !== "all" ? [symbol.toUpperCase()] : [];
    const results = await query(baseQuery, params);

    // Calculate signal summary statistics
    const signalsData = results && results.rows ? results.rows : [];
    const totalSignals = signalsData.length;
    const strongSignals = signalsData.filter(
      (r) => r.strength_category === "strong"
    ).length;
    const moderateSignals = signalsData.filter(
      (r) => r.strength_category === "moderate"
    ).length;
    const weakSignals = signalsData.filter(
      (r) => r.strength_category === "weak"
    ).length;

    return res.json({
      success: true,
      data: {
        signals: signalsData,
        summary: {
          total_signals: totalSignals,
          strong_signals: strongSignals,
          moderate_signals: moderateSignals,
          weak_signals: weakSignals,
          signal_distribution: {
            strong: Math.round(
              (strongSignals / Math.max(totalSignals, 1)) * 100
            ),
            moderate: Math.round(
              (moderateSignals / Math.max(totalSignals, 1)) * 100
            ),
            weak: Math.round((weakSignals / Math.max(totalSignals, 1)) * 100),
          },
        },
      },
      filters: {
        symbol: symbol || "all",
        timeframe: timeframe,
        strength: strength,
        limit: parseInt(limit),
        page: parseInt(page),
        sortBy: sortBy,
        sortOrder: sortOrder,
      },
      pagination: {
        current_page: parseInt(page),
        items_per_page: parseInt(limit),
        total_items: totalSignals,
        has_more: totalSignals === parseInt(limit),
      },
      timestamp: new Date().toISOString(),
      algorithm: "multi_timeframe_momentum_with_volume_confirmation",
    });
  } catch (error) {
    console.error("❌ Error calculating momentum signals:", error);
    return res.status(500).json({
      success: false,
      error: "Failed to calculate momentum signals",
      message: error.message,
      troubleshooting: {
        suggestion:
          "Check database connection and ensure price_daily table has recent data",
        required_tables: ["price_daily", "technical_indicators"],
        error_details:
          process.env.NODE_ENV === "development" ? error.stack : undefined,
      },
      timestamp: new Date().toISOString(),
    });
  }
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
      endDate,
    } = req.query;

    console.log(
      `🚨 Trading alerts requested for symbol: ${symbol || "all"}, type: ${type}, severity: ${severity}`
    );

    // Validate type
    const validTypes = [
      "all",
      "price",
      "volume",
      "technical",
      "fundamental",
      "news",
      "momentum",
      "reversal",
      "breakout",
    ];
    if (!validTypes.includes(type)) {
      return res.status(400).json({
        success: false,
        error: "Invalid alert type. Must be one of: " + validTypes.join(", "),
        requested_type: type,
      });
    }

    // Validate severity
    const validSeverities = ["all", "low", "medium", "high", "critical"];
    if (!validSeverities.includes(severity)) {
      return res.status(400).json({
        success: false,
        error:
          "Invalid severity. Must be one of: " + validSeverities.join(", "),
        requested_severity: severity,
      });
    }

    // Validate status
    const validStatuses = [
      "all",
      "active",
      "triggered",
      "expired",
      "acknowledged",
    ];
    if (!validStatuses.includes(status)) {
      return res.status(400).json({
        success: false,
        error: "Invalid status. Must be one of: " + validStatuses.join(", "),
        requested_status: status,
      });
    }

    // Set default date range if not provided (last 24 hours)
    const defaultEndDate = new Date().toISOString();
    const defaultStartDate = new Date(
      Date.now() - 24 * 60 * 60 * 1000
    ).toISOString();
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
        id as alert_id,
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
        NULL as metadata
      FROM trading_alerts
      ${whereClause}
      ORDER BY severity DESC, created_at DESC
      ${limitClause}
    `;

    // Check if trading_alerts table exists first
    const tableCheckQuery = `
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'trading_alerts'
      );
    `;

    const tableExists = await query(tableCheckQuery);

    if (!tableExists.rows[0].exists) {
      // Table doesn't exist, return empty alerts with explanation
      return res.json({
        success: true,
        data: [],
        total: 0,
        pagination: {
          page: 1,
          limit: parseInt(limit),
          totalPages: 0,
          hasNext: false,
          hasPrev: false,
        },
        severity_distribution: {
          critical: 0,
          high: 0,
          medium: 0,
          low: 0,
        },
        filters: {
          symbol: symbol || "all",
          type: type,
          severity: severity,
          status: status,
          limit: parseInt(limit),
          date_range: {
            start: finalStartDate,
            end: finalEndDate,
          },
        },
        message: "Trading alerts system not initialized - table not found",
        details: "The trading_alerts table does not exist in the database",
        troubleshooting: [
          "1. Run database migrations to create trading_alerts table",
          "2. Initialize trading alert management system",
          "3. Configure real-time price monitoring for alerts",
        ],
        timestamp: new Date().toISOString(),
      });
    }

    const result = await query(alertsQuery, queryParams);

    if (!result || !result.rows || result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "No trading alerts found",
        message:
          "Trading alerts require integration with professional alert management systems",
        details:
          "No alerts found in trading_alerts table for the specified filters",
        troubleshooting: {
          suggestion:
            "Trading alerts require alert management system integration",
          required_setup: [
            "Trading alert management system",
            "Real-time price monitoring",
            "Technical analysis alert triggers",
            "Alert delivery and management infrastructure",
            "User alert preference management",
          ],
          status: "Database query returned no results",
        },
        filters: {
          symbol: symbol || "all",
          type: type,
          severity: severity,
          status: status,
          limit: parseInt(limit),
          date_range: {
            start: finalStartDate,
            end: finalEndDate,
          },
        },
        timestamp: new Date().toISOString(),
      });
    }

    // Process database results
    const alertsData = result.rows;
    const totalAlerts = alertsData.length;

    const severityDistribution = {
      critical: alertsData.filter((a) => a.severity === "critical").length,
      high: alertsData.filter((a) => a.severity === "high").length,
      medium: alertsData.filter((a) => a.severity === "medium").length,
      low: alertsData.filter((a) => a.severity === "low").length,
    };

    const statusDistribution = {
      active: alertsData.filter((a) => a.status === "active").length,
      triggered: alertsData.filter((a) => a.status === "triggered").length,
      expired: alertsData.filter((a) => a.status === "expired").length,
      acknowledged: alertsData.filter((a) => a.acknowledged_at !== null).length,
    };

    const typeDistribution = {};
    alertsData.forEach((alert) => {
      typeDistribution[alert.alert_type] =
        (typeDistribution[alert.alert_type] || 0) + 1;
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
          symbols_covered: symbol
            ? 1
            : new Set(alertsData.map((a) => a.symbol)).size,
          time_range: {
            start: finalStartDate,
            end: finalEndDate,
          },
        },
        filters: {
          symbol: symbol || "all",
          type: type,
          severity: severity,
          status: status,
          limit: parseInt(limit),
        },
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Trading alerts error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch trading alerts",
      message: error.message,
      timestamp: new Date().toISOString(),
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
    sortOrder = "desc",
  } = req.query;

  console.log(
    `📱 Social sentiment signals requested - symbol: ${symbol || "all"}, platform: ${platform}, timeframe: ${timeframe}`
  );

  // Validate parameters
  const validPlatforms = [
    "all",
    "twitter",
    "reddit",
    "stocktwits",
    "discord",
    "telegram",
    "youtube",
  ];
  const validSentiments = ["all", "bullish", "bearish", "neutral"];
  const validTimeframes = ["1h", "6h", "24h", "7d", "30d"];
  const validSortColumns = [
    "timestamp",
    "sentiment",
    "mention_count",
    "influence_score",
    "symbol",
  ];

  if (!validPlatforms.includes(platform)) {
    return res.status(400).json({
      success: false,
      error: `Invalid platform. Must be one of: ${validPlatforms.join(", ")}`,
      validPlatforms,
    });
  }

  if (!validSentiments.includes(sentiment)) {
    return res.status(400).json({
      success: false,
      error: `Invalid sentiment. Must be one of: ${validSentiments.join(", ")}`,
      validSentiments,
    });
  }

  if (!validTimeframes.includes(timeframe)) {
    return res.status(400).json({
      success: false,
      error: `Invalid timeframe. Must be one of: ${validTimeframes.join(", ")}`,
      validTimeframes,
    });
  }

  try {
    // Build sentiment analysis query using available data
    let baseQuery = `
      WITH market_sentiment_latest AS (
        SELECT 
          ms.value as market_sentiment,
          ms.classification,
          ms.data_source,
          ms.created_at
        FROM market_sentiment ms
        WHERE ms.created_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
        ORDER BY ms.created_at DESC
        LIMIT 1
      ),
      stock_sentiment_data AS (
        SELECT 
          p.symbol,
          p.close,
          p.change_percent as daily_change,
          p.volume,
          p.date,
          -- Get sentiment from factor_scores if available
          fs.sentiment as stock_sentiment,
          fs.positioning_score,
          -- Calculate relative volume as sentiment indicator
          CASE 
            WHEN p.volume > (SELECT AVG(volume) * 1.5 FROM price_daily WHERE symbol = p.symbol AND date >= p.date - INTERVAL '20 days') THEN 'high_interest'
            WHEN p.volume < (SELECT AVG(volume) * 0.5 FROM price_daily WHERE symbol = p.symbol AND date >= p.date - INTERVAL '20 days') THEN 'low_interest'
            ELSE 'normal_interest'
          END as volume_sentiment,
          -- Momentum as sentiment proxy
          CASE 
            WHEN p.change_percent > 5 THEN 'very_positive'
            WHEN p.change_percent > 2 THEN 'positive'
            WHEN p.change_percent > -2 THEN 'neutral'
            WHEN p.change_percent > -5 THEN 'negative'
            ELSE 'very_negative'
          END as price_sentiment
        FROM price_daily p
        LEFT JOIN factor_scores fs ON p.symbol = fs.symbol AND p.date = fs.date
        WHERE p.date >= CURRENT_DATE - INTERVAL '7 days'
        AND p.date = (SELECT MAX(date) FROM price_daily WHERE symbol = p.symbol)
      ),
      sentiment_scores AS (
        SELECT 
          ssd.symbol,
          ssd.close_price,
          ssd.daily_change,
          ssd.volume,
          ssd.stock_sentiment,
          ssd.positioning_score,
          ssd.volume_sentiment,
          ssd.price_sentiment,
          msl.market_sentiment,
          msl.classification as market_classification,
          -- Calculate composite sentiment score
          (
            -- Market sentiment component (0-30 points)
            CASE 
              WHEN msl.classification = 'positive' THEN 20
              WHEN msl.classification = 'bullish' THEN 25
              WHEN msl.classification = 'very_positive' THEN 30
              WHEN msl.classification = 'negative' THEN -15
              WHEN msl.classification = 'bearish' THEN -20
              WHEN msl.classification = 'very_negative' THEN -25
              ELSE 0
            END +
            -- Stock-specific sentiment component (0-25 points)
            CASE 
              WHEN ssd.stock_sentiment > 0.7 THEN 20
              WHEN ssd.stock_sentiment > 0.3 THEN 10
              WHEN ssd.stock_sentiment < -0.7 THEN -15
              WHEN ssd.stock_sentiment < -0.3 THEN -8
              ELSE 0
            END +
            -- Volume sentiment component (0-20 points)
            CASE 
              WHEN ssd.volume_sentiment = 'high_interest' THEN 15
              WHEN ssd.volume_sentiment = 'low_interest' THEN -5
              ELSE 5
            END +
            -- Price action sentiment component (0-25 points)
            CASE 
              WHEN ssd.price_sentiment = 'very_positive' THEN 20
              WHEN ssd.price_sentiment = 'positive' THEN 10
              WHEN ssd.price_sentiment = 'negative' THEN -10
              WHEN ssd.price_sentiment = 'very_negative' THEN -15
              ELSE 0
            END
          ) as composite_sentiment_score,
          -- Overall sentiment classification
          CASE 
            WHEN ssd.price_sentiment IN ('very_positive', 'positive') AND ssd.volume_sentiment = 'high_interest' THEN 'bullish'
            WHEN ssd.price_sentiment = 'positive' OR ssd.volume_sentiment = 'high_interest' THEN 'positive'
            WHEN ssd.price_sentiment IN ('very_negative', 'negative') AND ssd.volume_sentiment = 'low_interest' THEN 'bearish'
            WHEN ssd.price_sentiment IN ('very_negative', 'negative') THEN 'negative'
            ELSE 'neutral'
          END as overall_sentiment,
          ssd.date as signal_date
        FROM stock_sentiment_data ssd
        CROSS JOIN market_sentiment_latest msl
      )
      SELECT 
        ss.symbol,
        ss.close_price as current_price,
        ss.daily_change,
        ss.volume,
        ss.overall_sentiment,
        ROUND(ss.composite_sentiment_score::numeric, 2) as sentiment_score,
        ss.volume_sentiment,
        ss.price_sentiment,
        ss.market_classification as market_sentiment,
        ROUND(ss.stock_sentiment::numeric, 3) as stock_sentiment_raw,
        ROUND(ss.positioning_score::numeric, 3) as positioning_score,
        -- Sentiment strength indicator
        CASE 
          WHEN ABS(ss.composite_sentiment_score) > 50 THEN 'strong'
          WHEN ABS(ss.composite_sentiment_score) > 25 THEN 'moderate'
          ELSE 'weak'
        END as sentiment_strength,
        -- Simulated platform data (would be real social media data)
        CASE 
          WHEN ss.volume_sentiment = 'high_interest' THEN 'twitter,reddit'
          WHEN ss.overall_sentiment IN ('bullish', 'bearish') THEN 'stocktwits'
          ELSE 'general'
        END as trending_platforms,
        ss.signal_date
      FROM sentiment_scores ss
      WHERE ss.close_price IS NOT NULL
    `;

    // Apply filters
    const conditions = [];
    const params = [];
    let paramIndex = 1;

    if (symbol && symbol.toLowerCase() !== "all") {
      conditions.push(`ss.symbol = $${paramIndex}`);
      params.push(symbol.toUpperCase());
      paramIndex++;
    }

    if (sentiment && sentiment.toLowerCase() !== "all") {
      conditions.push(`ss.overall_sentiment = $${paramIndex}`);
      params.push(sentiment.toLowerCase());
      paramIndex++;
    }

    // Add WHERE clause if we have conditions
    if (conditions.length > 0) {
      baseQuery += ` WHERE ${conditions.join(" AND ")}`;
    }

    // Add ordering and pagination
    baseQuery += ` ORDER BY ABS(ss.composite_sentiment_score) DESC, ss.symbol ASC`;
    const offset = (parseInt(page) - 1) * parseInt(limit);
    baseQuery += ` LIMIT ${parseInt(limit)} OFFSET ${offset}`;

    const results = await query(baseQuery, params);

    // Calculate summary statistics
    const sentimentData = results.rows || [];
    const totalSignals = sentimentData.length;
    const bullishSignals = sentimentData.filter(
      (r) => r.overall_sentiment === "bullish"
    ).length;
    const bearishSignals = sentimentData.filter(
      (r) => r.overall_sentiment === "bearish"
    ).length;
    const positiveSignals = sentimentData.filter(
      (r) => r.overall_sentiment === "positive"
    ).length;
    const negativeSignals = sentimentData.filter(
      (r) => r.overall_sentiment === "negative"
    ).length;
    const neutralSignals = sentimentData.filter(
      (r) => r.overall_sentiment === "neutral"
    ).length;

    const avgSentimentScore =
      sentimentData.length > 0
        ? (
            sentimentData.reduce(
              (sum, r) => sum + parseFloat(r.sentiment_score),
              0
            ) / sentimentData.length
          ).toFixed(2)
        : 0;

    return res.json({
      success: true,
      data: {
        signals: sentimentData,
        summary: {
          total_signals: totalSignals,
          bullish_signals: bullishSignals,
          bearish_signals: bearishSignals,
          positive_signals: positiveSignals,
          negative_signals: negativeSignals,
          neutral_signals: neutralSignals,
          average_sentiment_score: parseFloat(avgSentimentScore),
          sentiment_distribution: {
            bullish: Math.round(
              (bullishSignals / Math.max(totalSignals, 1)) * 100
            ),
            bearish: Math.round(
              (bearishSignals / Math.max(totalSignals, 1)) * 100
            ),
            positive: Math.round(
              (positiveSignals / Math.max(totalSignals, 1)) * 100
            ),
            negative: Math.round(
              (negativeSignals / Math.max(totalSignals, 1)) * 100
            ),
            neutral: Math.round(
              (neutralSignals / Math.max(totalSignals, 1)) * 100
            ),
          },
        },
      },
      filters: {
        symbol: symbol || "all",
        platform: platform,
        sentiment: sentiment,
        timeframe: timeframe,
        limit: parseInt(limit),
        page: parseInt(page),
        sortBy: sortBy,
        sortOrder: sortOrder,
      },
      pagination: {
        current_page: parseInt(page),
        items_per_page: parseInt(limit),
        total_items: totalSignals,
        has_more: totalSignals === parseInt(limit),
      },
      algorithm: "composite_sentiment_analysis",
      methodology: {
        market_sentiment:
          "Overall market sentiment from market_sentiment table",
        stock_sentiment: "Individual stock sentiment from factor_scores table",
        volume_sentiment: "Volume-based interest level analysis",
        price_sentiment: "Price action momentum as sentiment proxy",
        composite_score: "Weighted combination of all sentiment factors",
      },
      data_sources: {
        available: ["market_sentiment", "factor_scores", "price_daily"],
        note: "Social media integration available for upgrade - currently using market data proxies",
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("❌ Error generating social sentiment signals:", error);
    return res.status(500).json({
      success: false,
      error: "Failed to generate social sentiment signals",
      message: error.message,
      troubleshooting: {
        suggestion:
          "Check database connection and ensure required tables have data",
        required_tables: ["market_sentiment", "factor_scores", "price_daily"],
        error_details:
          process.env.NODE_ENV === "development" ? error.stack : undefined,
      },
      timestamp: new Date().toISOString(),
    });
  }
});

router.get("/momentum/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    const { timeframe = "daily", strength = "all" } = req.query;

    console.log(
      `📈 Momentum signals requested for ${symbol} - timeframe: ${timeframe}, strength: ${strength}`
    );

    // Query momentum data from database using existing technical tables
    const tableMap = {
      daily: "technical_data_daily",
      weekly: "technical_data_weekly",
      monthly: "technical_data_monthly",
    };

    const tableName = tableMap[timeframe] || "technical_data_daily";

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

    const result = await query(momentumQuery, [symbol]).catch((err) => {
      console.warn("Technical indicators query failed:", err.message);
      return { rows: [] };
    });

    if (!result.rows.length) {
      return res.notFound(`No momentum data found for symbol ${symbol}`);
    }

    const data = result.rows[0];

    res.json({
      symbol: symbol,
      momentum_signals: [
        {
          signal_type:
            data.momentum > 0.5 ? "BULLISH_MOMENTUM" : "BEARISH_MOMENTUM",
          strength:
            data.momentum > 0.7
              ? "STRONG"
              : data.momentum > 0.3
                ? "MEDIUM"
                : "WEAK",
          timeframe: timeframe,
          score: parseFloat(data.momentum || 0.5),
          indicators: {
            rsi: parseFloat(data.rsi || 50),
            macd: parseFloat(data.macd || 0),
            momentum: parseFloat(data.momentum || 0.5),
            volume_trend: data.volume > 1000000 ? "INCREASING" : "DECREASING",
          },
          timestamp: data.fetched_at,
        },
      ],
      metadata: {
        symbol: symbol,
        timeframe: timeframe,
        last_updated: data.created_at,
      },
    });
  } catch (error) {
    console.error(
      `Error fetching momentum signals for ${req.params.symbol}:`,
      error
    );
    res
      .status(500)
      .json({ success: false, error: "Failed to fetch momentum signals" });
  }
});

// Technical signals endpoint
router.get("/technical", async (req, res) => {
  try {
    const {
      timeframe = "daily",
      signal_type = "all",
      strength = "medium",
      limit = 25,
      page = 1,
    } = req.query;

    console.log(
      `🔧 Technical signals requested - timeframe: ${timeframe}, type: ${signal_type}, strength: ${strength}`
    );

    const offset = (page - 1) * limit;

    // Get technical signals from database
    const tableMap = {
      daily: "technical_data_daily",
      weekly: "technical_data_weekly",
      monthly: "technical_data_monthly",
    };

    const table = tableMap[timeframe] || "technical_data_daily";

    let signalTypeFilter = "";
    if (signal_type !== "all") {
      signalTypeFilter = `AND signal_type = '${signal_type.toUpperCase()}'`;
    }

    let strengthFilter = "";
    // Note: strength filtering will be done client-side since signal_strength is calculated

    const technicalQuery = `
      SELECT 
        t.symbol,
        s.name as company_name,
        s.sector,
        t.rsi,
        t.macd,
        t.sma_20,
        t.sma_50,
        t.bbands_upper,
        t.bbands_lower,
        NULL as stoch_k,
        NULL as williams_r,
        t.date,
        CASE 
          WHEN t.rsi < 30 THEN 'BUY'
          WHEN t.rsi > 70 THEN 'SELL'
          WHEN t.macd > 0 AND t.rsi < 50 THEN 'BUY'
          WHEN t.macd < 0 AND t.rsi > 50 THEN 'SELL'
          ELSE 'HOLD'
        END as signal,
        CASE 
          WHEN t.rsi < 20 OR t.rsi > 80 THEN 0.9
          WHEN t.rsi < 30 OR t.rsi > 70 THEN 0.7
          WHEN t.rsi < 40 OR t.rsi > 60 THEN 0.5
          ELSE 0.3
        END as signal_strength,
        'technical' as signal_type
      FROM ${table} t
      LEFT JOIN stocks s ON t.symbol = s.symbol
      WHERE t.date >= CURRENT_DATE - INTERVAL '30 days'
        ${signalTypeFilter}
      ORDER BY t.date DESC, t.rsi DESC
      LIMIT $1 OFFSET $2
    `;

    // Get count for pagination
    const countQuery = `
      SELECT COUNT(*) as total
      FROM ${table} t
      WHERE t.date >= CURRENT_DATE - INTERVAL '30 days'
        AND (
          t.rsi < 30 OR 
          t.rsi > 70 OR
          (t.macd > 0 AND t.rsi < 50) OR
          (t.macd < 0 AND t.rsi > 50)
        )
        ${signalTypeFilter}
        ${strengthFilter}
    `;

    const [signalsResult, countResult] = await Promise.all([
      query(technicalQuery, [parseInt(limit), offset]),
      query(countQuery),
    ]);

    if (!signalsResult.rows || signalsResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "No technical signals found",
        message: `No technical signals available for the specified criteria`,
        details: {
          timeframe: timeframe,
          signal_type: signal_type,
          strength: strength,
          suggestion: "Try adjusting the timeframe or strength parameters",
        },
      });
    }

    const total = parseInt(countResult.rows[0]?.total || 0);
    const totalPages = Math.ceil(total / limit);

    // Process and format the signals
    const technicalSignals = signalsResult.rows.map((row) => ({
      symbol: row.symbol,
      company_name: row.company_name || "Unknown Company",
      sector: row.sector || "Unknown",
      signal: row.signal,
      signal_strength: parseFloat(row.signal_strength).toFixed(2),
      signal_type: "TECHNICAL",
      technical_indicators: {
        rsi: parseFloat(row.rsi || 0).toFixed(2),
        macd: parseFloat(row.macd || 0).toFixed(4),
        sma_20: parseFloat(row.sma_20 || 0).toFixed(2),
        sma_50: parseFloat(row.sma_50 || 0).toFixed(2),
        bollinger_upper: parseFloat(row.bbands_upper || 0).toFixed(2),
        bollinger_lower: parseFloat(row.bbands_lower || 0).toFixed(2),
        stoch_k: parseFloat(row.stoch_k || 0).toFixed(2),
        williams_r: parseFloat(row.williams_r || 0).toFixed(2),
      },
      date: row.date,
      confidence:
        parseFloat(row.signal_strength) > 0.7
          ? "High"
          : parseFloat(row.signal_strength) > 0.5
            ? "Medium"
            : "Low",
    }));

    // Calculate summary statistics
    const buySignals = technicalSignals.filter(
      (s) => s.signal === "BUY"
    ).length;
    const sellSignals = technicalSignals.filter(
      (s) => s.signal === "SELL"
    ).length;
    const holdSignals = technicalSignals.filter(
      (s) => s.signal === "HOLD"
    ).length;

    res.json({
      success: true,
      data: {
        technical_signals: technicalSignals,
        summary: {
          total_signals: technicalSignals.length,
          buy_signals: buySignals,
          sell_signals: sellSignals,
          hold_signals: holdSignals,
          signal_distribution: {
            bullish_percentage:
              total > 0 ? ((buySignals / total) * 100).toFixed(1) : 0,
            bearish_percentage:
              total > 0 ? ((sellSignals / total) * 100).toFixed(1) : 0,
            neutral_percentage:
              total > 0 ? ((holdSignals / total) * 100).toFixed(1) : 0,
          },
        },
        parameters: {
          timeframe: timeframe,
          signal_type: signal_type,
          strength: strength,
          page: parseInt(page),
          limit: parseInt(limit),
        },
        pagination: {
          page: parseInt(page),
          limit: parseInt(limit),
          total: total,
          totalPages: totalPages,
          hasNext: page < totalPages,
          hasPrev: page > 1,
        },
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Technical signals error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch technical signals",
      message: error.message,
    });
  }
});

// AI Trading Signals endpoint
router.get("/ai-signals", authenticateToken, async (req, res) => {
  try {
    const {
      type = "all",
      timeframe = "1h",
      symbol,
      limit = 50,
      min_confidence = 0,
      max_risk = 10,
    } = req.query;

    // Build comprehensive AI signals query using existing tables
    let baseQuery = `
      WITH latest_prices AS (
        SELECT DISTINCT ON (p.symbol)
          p.symbol,
          p.date,
          p.close,
          p.volume,
          p.change_percent as daily_change,
          p.high,
          p.low
        FROM price_daily p
        WHERE p.date >= CURRENT_DATE - INTERVAL '5 days'
        ORDER BY p.symbol, p.date DESC
      ),
      technical_signals AS (
        SELECT 
          lp.symbol,
          lp.close as current_price,
          lp.daily_change as price_change,
          lp.volume,
          
          -- Get technical indicators
          ti.rsi_14 as rsi,
          ti.macd,
          ti.historical_volatility_20d as volatility,
          ti.beta,
          
          -- Calculate volume ratio
          CASE 
            WHEN lp.volume > 0 AND (
              SELECT AVG(volume) 
              FROM price_daily 
              WHERE symbol = lp.symbol 
              AND date >= CURRENT_DATE - INTERVAL '20 days'
            ) > 0 THEN 
              lp.volume / (
                SELECT AVG(volume) 
                FROM price_daily 
                WHERE symbol = lp.symbol 
                AND date >= CURRENT_DATE - INTERVAL '20 days'
              )
            ELSE 1
          END as volume_ratio,
          
          -- Get sentiment data
          COALESCE(ms.value, 0.5) as news_sentiment,
          COALESCE(fs.sentiment, 0.5) as market_score,
          
          -- Calculate pattern matching
          CASE 
            WHEN ti.rsi_14 < 30 AND ti.macd > 0 THEN 'Bullish Divergence'
            WHEN ti.rsi_14 > 70 AND ti.macd < 0 THEN 'Bearish Divergence'
            WHEN lp.close > ti.price_52w_high * 0.95 THEN 'Breakout'
            WHEN lp.close < ti.price_52w_low * 1.05 THEN 'Oversold'
            ELSE NULL
          END as pattern_match,
          
          -- Volume confirmation
          CASE 
            WHEN lp.volume > (
              SELECT AVG(volume) * 1.5 
              FROM price_daily 
              WHERE symbol = lp.symbol 
              AND date >= CURRENT_DATE - INTERVAL '20 days'
            ) THEN true
            ELSE false
          END as volume_confirmation,
          
          lp.date as timestamp
          
        FROM latest_prices lp
        LEFT JOIN technical_indicators ti ON lp.symbol = ti.symbol
        LEFT JOIN market_sentiment ms ON ms.created_at >= CURRENT_DATE - INTERVAL '1 day'
        LEFT JOIN factor_scores fs ON fs.symbol = lp.symbol AND fs.date = lp.date
        WHERE lp.close > 0
      ),
      ai_scored_signals AS (
        SELECT 
          ts.*,
          
          -- AI Strength Calculation
          (
            50 + -- Base score
            -- RSI component (20 points)
            CASE 
              WHEN ts.rsi < 30 THEN 15  -- Oversold opportunity
              WHEN ts.rsi > 70 THEN -10 -- Overbought warning
              WHEN ts.rsi BETWEEN 40 AND 60 THEN 5  -- Neutral range
              ELSE 0
            END +
            -- MACD component (20 points)  
            CASE 
              WHEN ts.macd > 0 THEN 15     -- Bullish momentum
              WHEN ts.macd < 0 THEN -10    -- Bearish momentum
              ELSE 0
            END +
            -- Volume component (15 points)
            CASE
              WHEN ts.volume_ratio > 2 THEN 10
              WHEN ts.volume_ratio > 1.5 THEN 5
              ELSE 0
            END +
            -- News sentiment component (10 points)
            (ts.news_sentiment - 0.5) * 20 +
            -- Market sentiment component (10 points)  
            (ts.market_score - 0.5) * 20 +
            -- Pattern bonus (15 points)
            CASE 
              WHEN ts.pattern_match IS NOT NULL THEN 15
              ELSE 0
            END
          ) as ai_strength,
          
          -- Signal type determination
          CASE 
            WHEN ts.rsi < 30 AND ts.macd > 0 AND ts.volume_confirmation THEN 'buy'
            WHEN ts.rsi > 70 AND ts.macd < 0 THEN 'sell' 
            WHEN ts.pattern_match = 'Breakout' AND ts.volume_confirmation THEN 'breakout'
            WHEN ts.pattern_match LIKE '%Divergence' THEN 'reversal'
            WHEN ts.volume_ratio > 3 THEN 'momentum'
            ELSE 'hold'
          END as signal_type,
          
          -- Confidence calculation
          GREATEST(60, LEAST(95, 
            60 + 
            (CASE WHEN ts.volume_confirmation THEN 10 ELSE 0 END) +
            (CASE WHEN ts.pattern_match IS NOT NULL THEN 10 ELSE 0 END) +
            (CASE WHEN ABS(ts.rsi - 50) > 20 THEN 10 ELSE 0 END) +
            (CASE WHEN ABS(ts.macd) > 0.1 THEN 5 ELSE 0 END)
          )) as confidence,
          
          -- Risk level (1-10)
          GREATEST(1, LEAST(10,
            5 + 
            (CASE WHEN ts.volatility > 0.3 THEN 2 ELSE 0 END) +
            (CASE WHEN ts.beta > 1.5 THEN 1 ELSE 0 END) +
            (CASE WHEN ts.volume_ratio < 0.5 THEN 2 ELSE 0 END)
          )) as risk_level,
          
          -- Target and stop loss calculation
          CASE 
            WHEN ts.rsi < 30 THEN ts.current_price * 1.05  -- 5% upside target
            WHEN ts.rsi > 70 THEN ts.current_price * 0.95  -- 5% downside target
            ELSE ts.current_price * 1.02  -- 2% default target
          END as target_price,
          
          CASE 
            WHEN ts.rsi < 30 THEN ts.current_price * 0.97  -- 3% stop loss
            WHEN ts.rsi > 70 THEN ts.current_price * 1.03  -- 3% stop loss  
            ELSE ts.current_price * 0.98  -- 2% default stop
          END as stop_loss
          
        FROM technical_signals ts
      )
      SELECT 
        ROW_NUMBER() OVER (ORDER BY ai_strength DESC) as id,
        symbol,
        signal_type,
        timeframe,
        current_price,
        target_price,
        stop_loss,
        confidence,
        risk_level,
        'active' as status,
        timestamp,
        timestamp + INTERVAL '4 hours' as expires_at,
        
        -- AI enhancements
        GREATEST(0, LEAST(100, ROUND(ai_strength))) as strength,
        
        -- Technical data
        rsi,
        macd,
        volume_ratio,
        
        -- Calculated scores for frontend
        CASE 
          WHEN rsi BETWEEN 30 AND 70 THEN 20
          WHEN rsi > 70 OR rsi < 30 THEN 10
          ELSE 0
        END as rsi_score,
        
        CASE 
          WHEN (macd > 0 AND signal_type = 'buy') OR (macd < 0 AND signal_type = 'sell') THEN 25
          ELSE 10
        END as macd_score,
        
        15 as bollinger_score, -- Placeholder
        
        -- Additional metrics
        volume_confirmation,
        news_sentiment,
        market_score,
        pattern_match,
        price_change
        
      FROM ai_scored_signals
      WHERE 1=1
    `;

    const params = [];
    let paramIndex = 1;

    // Apply filters
    if (type !== "all") {
      baseQuery += ` AND signal_type = $${paramIndex}`;
      params.push(type);
      paramIndex++;
    }

    if (symbol) {
      baseQuery += ` AND symbol = $${paramIndex}`;
      params.push(symbol.toUpperCase());
      paramIndex++;
    }

    baseQuery += ` AND confidence >= $${paramIndex}`;
    params.push(parseInt(min_confidence));
    paramIndex++;

    baseQuery += ` AND risk_level <= $${paramIndex}`;
    params.push(parseInt(max_risk));
    paramIndex++;

    // Order and limit
    baseQuery += ` ORDER BY ai_strength DESC, confidence DESC`;
    baseQuery += ` LIMIT $${paramIndex}`;
    params.push(Math.min(parseInt(limit), 100));

    const result = await query(baseQuery, params);
    const signals = result.rows || [];

    // Enhanced signal processing
    const enhancedSignals = signals.map((signal) => ({
      id: signal.id,
      symbol: signal.symbol,
      signal_type: signal.signal_type,
      timeframe: timeframe,
      price: parseFloat(signal.current_price),
      target_price: parseFloat(signal.target_price),
      stop_loss: parseFloat(signal.stop_loss),
      confidence: signal.confidence,
      risk_level: signal.risk_level,
      status: signal.status,
      timestamp: signal.timestamp,
      expires_at: signal.expires_at,

      // AI metrics
      strength: signal.strength,
      reasons: [
        signal.rsi < 30
          ? "Oversold RSI"
          : signal.rsi > 70
            ? "Overbought RSI"
            : null,
        signal.macd > 0
          ? "Bullish MACD"
          : signal.macd < 0
            ? "Bearish MACD"
            : null,
        signal.volume_confirmation ? "Volume Confirmed" : null,
        signal.pattern_match ? `${signal.pattern_match} Pattern` : null,
      ].filter((r) => r !== null),

      // Technical data
      rsi: signal.rsi,
      macd: signal.macd,
      volume_ratio: signal.volume_ratio,
      rsi_score: signal.rsi_score,
      macd_score: signal.macd_score,
      bollinger_score: signal.bollinger_score,

      // Additional metrics
      volume_confirmation: signal.volume_confirmation,
      news_sentiment: signal.news_sentiment,
      market_score: signal.market_score,
      pattern_match: signal.pattern_match,
      price_change: signal.price_change,
    }));

    // Group signals
    const signalGroups = {
      active: enhancedSignals.filter((s) => s.status === "active"),
      watching: [],
      executed: [],
      expired: [],
    };

    // Summary statistics
    const summary = {
      total_signals: enhancedSignals.length,
      active_signals: signalGroups.active.length,
      high_confidence: enhancedSignals.filter((s) => s.confidence >= 80).length,
      low_risk: enhancedSignals.filter((s) => s.risk_level <= 3).length,
      avg_confidence:
        enhancedSignals.length > 0
          ? Math.round(
              enhancedSignals.reduce((sum, s) => sum + s.confidence, 0) /
                enhancedSignals.length
            )
          : 0,
      avg_strength:
        enhancedSignals.length > 0
          ? Math.round(
              enhancedSignals.reduce((sum, s) => sum + s.strength, 0) /
                enhancedSignals.length
            )
          : 0,
    };

    res.json({
      success: true,
      data: {
        signals: enhancedSignals,
        groups: signalGroups,
        summary: summary,
        filters: {
          type,
          timeframe,
          symbol: symbol || null,
          min_confidence: parseInt(min_confidence),
          max_risk: parseInt(max_risk),
        },
        timestamp: new Date().toISOString(),
        total_results: enhancedSignals.length,
      },
    });
  } catch (error) {
    console.error("AI Signals Error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch AI trading signals",
      message:
        process.env.NODE_ENV === "development"
          ? error.message
          : "Internal server error",
    });
  }
});

// Execute trading signal
router.post("/execute/:signalId", authenticateToken, async (req, res) => {
  try {
    const { signalId } = req.params;
    const { quantity, order_type = "market" } = req.body;

    // Since we don't have a trading_signals table, we'll simulate execution
    // In a real implementation, this would create actual orders

    res.json({
      success: true,
      data: {
        order_id: `order_${Date.now()}`,
        signal_id: signalId,
        quantity: quantity,
        order_type: order_type,
        status: "simulated",
        message:
          "Signal execution simulated - integrate with trading platform for real execution",
      },
    });
  } catch (error) {
    console.error("Execute Signal Error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to execute trading signal",
      message:
        process.env.NODE_ENV === "development"
          ? error.message
          : "Internal server error",
    });
  }
});

// Signal analytics
router.get("/analytics", authenticateToken, async (req, res) => {
  try {
    const { period = "30d" } = req.query;

    // Use existing tables to provide analytics
    const analyticsQuery = `
      SELECT 
        COUNT(DISTINCT p.symbol) as total_symbols,
        AVG(CASE WHEN p.change_percent > 0 THEN 1 ELSE 0 END) * 100 as positive_signals_pct,
        AVG(ti.rsi_14) as avg_rsi,
        COUNT(CASE WHEN ti.rsi_14 < 30 THEN 1 END) as oversold_count,
        COUNT(CASE WHEN ti.rsi_14 > 70 THEN 1 END) as overbought_count,
        COUNT(CASE WHEN ti.macd > 0 THEN 1 END) as bullish_macd_count,
        COUNT(CASE WHEN ti.macd < 0 THEN 1 END) as bearish_macd_count
      FROM price_daily p
      LEFT JOIN technical_indicators ti ON p.symbol = ti.symbol
      WHERE p.date >= CURRENT_DATE - INTERVAL '${period === "7d" ? "7 days" : period === "90d" ? "90 days" : "30 days"}'
    `;

    const result = await query(analyticsQuery);
    const analytics = result.rows[0] || {};

    res.json({
      success: true,
      data: {
        period: period,
        summary: {
          total_symbols: parseInt(analytics.total_symbols) || 0,
          positive_signals_pct: parseFloat(analytics.positive_signals_pct) || 0,
          avg_rsi: parseFloat(analytics.avg_rsi) || 50,
          oversold_count: parseInt(analytics.oversold_count) || 0,
          overbought_count: parseInt(analytics.overbought_count) || 0,
          bullish_macd_count: parseInt(analytics.bullish_macd_count) || 0,
          bearish_macd_count: parseInt(analytics.bearish_macd_count) || 0,
        },
        timestamp: new Date().toISOString(),
      },
    });
  } catch (error) {
    console.error("Signal Analytics Error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch signal analytics",
      message:
        process.env.NODE_ENV === "development"
          ? error.message
          : "Internal server error",
    });
  }
});

// Get daily signals (shortcut for /buy?timeframe=daily&limit=50)
router.get("/daily", async (req, res) => {
  try {
    const limit = parseInt(req.query.limit) || 50;
    const page = parseInt(req.query.page) || 1;
    const offset = (page - 1) * limit;

    console.log(`📊 Daily signals requested - limit: ${limit}, page: ${page}`);

    // Get daily buy/sell signals
    const signalsQuery = `
      SELECT 
        bs.symbol,
        cp.name as company_name,
        cp.sector,
        bs.signal,
        bs.date,
        s.price as current_price,
        s.market_cap,
        s.dividend_yield,
        CASE 
          WHEN bs.signal = 'BUY' THEN 'buy'
          WHEN bs.signal = 'SELL' THEN 'sell'
          ELSE 'hold'
        END as signal_type
      FROM buy_sell_daily bs
      JOIN company_profile cp ON bs.symbol = cp.ticker
      LEFT JOIN stocks s ON bs.symbol = s.symbol
      WHERE bs.signal IS NOT NULL 
        AND bs.signal != '' 
        AND bs.signal IN ('BUY', 'SELL', 'HOLD')
      ORDER BY bs.date DESC, bs.signal DESC, bs.symbol ASC
      LIMIT $1 OFFSET $2
    `;

    const countQuery = `
      SELECT COUNT(*) as total
      FROM buy_sell_daily bs
      WHERE bs.signal IS NOT NULL 
        AND bs.signal != '' 
        AND bs.signal IN ('BUY', 'SELL', 'HOLD')
    `;

    const [signalsResult, countResult] = await Promise.all([
      query(signalsQuery, [limit, offset]),
      query(countQuery, []),
    ]);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    // Transform data to camelCase
    const signals = signalsResult.rows.map((row) => ({
      symbol: row.symbol,
      companyName: row.company_name,
      sector: row.sector,
      signal: row.signal,
      signalType: row.signal_type,
      date: row.date,
      currentPrice: parseFloat(row.current_price) || 0,
      marketCap: parseFloat(row.market_cap) || 0,
      dividendYield: parseFloat(row.dividend_yield) || 0,
    }));

    // Group by signal type
    const buySignals = signals.filter((s) => s.signal === "BUY");
    const sellSignals = signals.filter((s) => s.signal === "SELL");
    const holdSignals = signals.filter((s) => s.signal === "HOLD");

    res.json({
      success: true,
      data: {
        signals: signals,
        buy_signals: buySignals,
        sell_signals: sellSignals,
        hold_signals: holdSignals,
        summary: {
          total_signals: signals.length,
          buy_count: buySignals.length,
          sell_count: sellSignals.length,
          hold_count: holdSignals.length,
        },
      },
      timeframe: "daily",
      pagination: {
        page: page,
        limit: limit,
        total: total,
        totalPages: totalPages,
        hasNextPage: page < totalPages,
        hasPrevPage: page > 1,
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Daily signals error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch daily signals",
      message:
        process.env.NODE_ENV === "development"
          ? error.message
          : "Internal server error",
      timestamp: new Date().toISOString(),
    });
  }
});

// Get trending signals
router.get("/trending", async (req, res) => {
  try {
    const limit = parseInt(req.query.limit) || 20;
    const timeframe = req.query.timeframe || "daily";

    console.log(
      `📈 Trending signals requested - limit: ${limit}, timeframe: ${timeframe}`
    );

    // Get trending signals based on recent activity
    const trendingQuery = `
      SELECT 
        bs.symbol,
        cp.name as company_name,
        cp.sector,
        bs.signal,
        bs.date,
        s.price as current_price,
        s.market_cap,
        s.dividend_yield,
        COUNT(*) OVER (PARTITION BY bs.symbol) as signal_count
      FROM buy_sell_${timeframe} bs
      JOIN company_profile cp ON bs.symbol = cp.ticker
      LEFT JOIN stocks s ON bs.symbol = s.symbol
      WHERE bs.signal IS NOT NULL 
        AND bs.signal != '' 
        AND bs.date >= CURRENT_DATE - INTERVAL '7 days'
      ORDER BY signal_count DESC, bs.date DESC
      LIMIT $1
    `;

    const result = await query(trendingQuery, [limit]);

    res.success(
      {
        trending_signals: result.rows || [],
        metadata: {
          count: result.rows?.length || 0,
          timeframe: timeframe,
          period: "last_7_days",
        },
      },
      200,
      { message: "Trending signals retrieved successfully" }
    );
  } catch (error) {
    console.error("Trending signals error:", error);
    res.error("Failed to fetch trending signals", 500, error.message);
  }
});

// Get signal backtest results
router.get("/backtest", async (req, res) => {
  try {
    const { symbol, start_date } = req.query;

    console.log(
      `🔄 Signal backtest requested - symbol: ${symbol || "all"}, start_date: ${start_date}`
    );

    // Simulate backtest results with historical signal data
    let backtestQuery = `
      SELECT 
        bs.symbol,
        bs.signal,
        bs.date as signal_date,
        pd.close as entry_price,
        pd2.close as current_price,
        ROUND(((pd2.close - pd.close) / pd.close * 100)::numeric, 2) as return_percent
      FROM buy_sell_daily bs
      JOIN price_daily pd ON bs.symbol = pd.symbol AND bs.date = pd.date
      LEFT JOIN price_daily pd2 ON bs.symbol = pd2.symbol 
        AND pd2.date = (SELECT MAX(date) FROM price_daily WHERE symbol = bs.symbol)
      WHERE bs.signal IN ('BUY', 'SELL')
    `;

    const params = [];
    if (symbol) {
      backtestQuery += ` AND bs.symbol = $${params.length + 1}`;
      params.push(symbol.toUpperCase());
    }
    if (start_date) {
      backtestQuery += ` AND bs.date >= $${params.length + 1}`;
      params.push(start_date);
    }

    backtestQuery += ` ORDER BY bs.date DESC LIMIT 100`;

    const result = await query(backtestQuery, params);

    // Calculate backtest summary
    const signals = result.rows || [];
    const totalSignals = signals.length;
    const profitableSignals = signals.filter(
      (s) => s.return_percent > 0
    ).length;
    const winRate =
      totalSignals > 0
        ? ((profitableSignals / totalSignals) * 100).toFixed(2)
        : 0;
    const avgReturn =
      totalSignals > 0
        ? (
            signals.reduce(
              (sum, s) => sum + parseFloat(s.return_percent || 0),
              0
            ) / totalSignals
          ).toFixed(2)
        : 0;

    res.success(
      {
        backtest_results: signals,
        summary: {
          total_signals: totalSignals,
          profitable_signals: profitableSignals,
          win_rate: `${winRate}%`,
          average_return: `${avgReturn}%`,
        },
        parameters: {
          symbol: symbol || "all",
          start_date: start_date || "all_time",
        },
      },
      200,
      { message: "Backtest results retrieved successfully" }
    );
  } catch (error) {
    console.error("Signal backtest error:", error);
    res.error("Failed to fetch backtest results", 500, error.message);
  }
});

// Get signal performance metrics
router.get("/performance", async (req, res) => {
  try {
    const timeframe = req.query.timeframe || "1M";

    console.log(`📊 Signal performance requested - timeframe: ${timeframe}`);

    // Map timeframe to SQL intervals
    const timeframeMap = {
      "1D": "1 day",
      "1W": "7 days",
      "1M": "30 days",
      "3M": "90 days",
      "1Y": "365 days",
    };

    const interval = timeframeMap[timeframe] || "30 days";

    // Get signal performance data
    const performanceQuery = `
      SELECT 
        bs.signal,
        COUNT(*) as signal_count,
        AVG(CASE 
          WHEN pd2.close IS NOT NULL AND pd.close IS NOT NULL 
          THEN ((pd2.close - pd.close) / pd.close * 100)
          ELSE 0 
        END) as avg_return,
        COUNT(CASE 
          WHEN pd2.close > pd.close THEN 1 
        END) as profitable_count
      FROM buy_sell_daily bs
      LEFT JOIN price_daily pd ON bs.symbol = pd.symbol AND bs.date = pd.date
      LEFT JOIN price_daily pd2 ON bs.symbol = pd2.symbol 
        AND pd2.date = (SELECT MAX(date) FROM price_daily WHERE symbol = bs.symbol AND date <= CURRENT_DATE)
      WHERE bs.signal IN ('BUY', 'SELL', 'HOLD')
        AND bs.date >= CURRENT_DATE - INTERVAL '${interval}'
      GROUP BY bs.signal
      ORDER BY bs.signal
    `;

    const result = await query(performanceQuery);

    // Format performance data
    const performanceData =
      result.rows?.map((row) => ({
        signal: row.signal,
        total_signals: parseInt(row.signal_count),
        profitable_signals: parseInt(row.profitable_count || 0),
        win_rate:
          row.signal_count > 0
            ? `${((row.profitable_count / row.signal_count) * 100).toFixed(2)}%`
            : "0%",
        average_return: `${parseFloat(row.avg_return || 0).toFixed(2)}%`,
      })) || [];

    res.success(
      {
        performance_metrics: performanceData,
        metadata: {
          timeframe: timeframe,
          period: interval,
          total_signals: performanceData.reduce(
            (sum, p) => sum + p.total_signals,
            0
          ),
        },
      },
      200,
      { message: "Signal performance retrieved successfully" }
    );
  } catch (error) {
    console.error("Signal performance error:", error);
    res.error("Failed to fetch signal performance", 500, error.message);
  }
});

// POST /signals/backtest - Signal backtesting endpoint
router.post("/backtest", async (req, res) => {
  try {
    const {
      symbols,
      startDate,
      endDate,
      signalTypes,
      parameters = {},
      initialCapital = 100000,
      commission = 0.001,
      maxPositions = 10,
    } = req.body;

    // Validate required parameters
    if (!symbols || !Array.isArray(symbols) || symbols.length === 0) {
      return res.status(400).json({
        success: false,
        error: "Symbols array is required and must not be empty",
      });
    }

    if (!startDate || !endDate) {
      return res.status(400).json({
        success: false,
        error: "Start date and end date are required",
      });
    }

    if (
      !signalTypes ||
      !Array.isArray(signalTypes) ||
      signalTypes.length === 0
    ) {
      return res.status(400).json({
        success: false,
        error: "Signal types array is required and must not be empty",
      });
    }

    const start = new Date(startDate);
    const end = new Date(endDate);

    if (start >= end) {
      return res.status(400).json({
        success: false,
        error: "End date must be after start date",
      });
    }

    // Initialize backtest tracking
    let portfolio = {
      cash: initialCapital,
      positions: {},
      trades: [],
      equity: [],
      totalValue: initialCapital,
    };

    let backtestResults = {
      summary: {
        initialCapital,
        finalValue: initialCapital,
        totalReturn: 0,
        totalReturnPercent: 0,
        maxDrawdown: 0,
        totalTrades: 0,
        winningTrades: 0,
        losingTrades: 0,
        winRate: 0,
        avgWin: 0,
        avgLoss: 0,
        profitFactor: 0,
      },
      trades: [],
      equity: [],
      dailyReturns: [],
      positions: {},
    };

    // Get historical price data for the symbols
    const priceQuery = `
      SELECT pd.symbol, pd.date, pd.open, pd.high, pd.low, pd.close, pd.volume,
             COALESCE(ti.rsi_14, 50) as rsi,
             COALESCE(ti.macd, 0) as macd,
             COALESCE(bs.signal_strength, 0) as signal_strength,
             bs.signal as signal_type,
             bs.recommendation
      FROM price_daily pd
      LEFT JOIN technical_indicators ti ON pd.symbol = ti.symbol AND pd.date = ti.date
      LEFT JOIN buy_sell_daily bs ON pd.symbol = bs.symbol AND pd.date = bs.date
      WHERE pd.symbol = ANY($1::text[]) 
        AND pd.date BETWEEN $2 AND $3
        AND (bs.signal = ANY($4::text[]) OR bs.signal IS NULL)
      ORDER BY pd.date, pd.symbol
    `;

    const priceData = await query(priceQuery, [
      symbols,
      start,
      end,
      signalTypes,
    ]);
    const dailyData = priceData.rows;

    // Group data by date for simulation
    const dateGroups = {};
    dailyData.forEach((row) => {
      const dateKey = row.date.toISOString().split("T")[0];
      if (!dateGroups[dateKey]) {
        dateGroups[dateKey] = [];
      }
      dateGroups[dateKey].push(row);
    });

    const tradingDays = Object.keys(dateGroups).sort();

    // Simulate trading for each day
    for (const dateKey of tradingDays) {
      const dayData = dateGroups[dateKey];
      const currentDate = new Date(dateKey);

      // Process signals for each symbol
      for (const data of dayData) {
        const symbol = data.symbol;
        const price = parseFloat(data.close);
        const signalType = data.signal_type;
        const signalStrength = parseFloat(data.signal_strength) || 0;

        // Generate buy signals
        if (
          signalType === "BUY" &&
          signalStrength > (parameters.minSignalStrength || 5)
        ) {
          const positionSize = Math.floor((portfolio.cash * 0.1) / price); // 10% of cash per position

          if (
            positionSize > 0 &&
            Object.keys(portfolio.positions).length < maxPositions
          ) {
            const totalCost = positionSize * price * (1 + commission);

            if (totalCost <= portfolio.cash) {
              // Execute buy
              portfolio.cash -= totalCost;
              portfolio.positions[symbol] = {
                shares: positionSize,
                avgPrice: price * (1 + commission),
                entryDate: currentDate,
                entryPrice: price,
              };

              portfolio.trades.push({
                symbol,
                type: "buy",
                shares: positionSize,
                price: price * (1 + commission),
                date: currentDate,
                signalStrength,
              });
            }
          }
        }

        // Generate sell signals
        if (signalType === "SELL" && portfolio.positions[symbol]) {
          const position = portfolio.positions[symbol];
          const proceeds = position.shares * price * (1 - commission);

          // Execute sell
          portfolio.cash += proceeds;
          const gain = proceeds - position.shares * position.avgPrice;

          portfolio.trades.push({
            symbol,
            type: "sell",
            shares: position.shares,
            price: price * (1 - commission),
            date: currentDate,
            gain,
            gainPercent: (gain / (position.shares * position.avgPrice)) * 100,
            holdingDays: Math.floor(
              (currentDate - position.entryDate) / (1000 * 60 * 60 * 24)
            ),
          });

          delete portfolio.positions[symbol];
        }

        // Update position values
        if (portfolio.positions[symbol]) {
          portfolio.positions[symbol].currentPrice = price;
          portfolio.positions[symbol].currentValue =
            portfolio.positions[symbol].shares * price;
          portfolio.positions[symbol].unrealizedGain =
            portfolio.positions[symbol].currentValue -
            portfolio.positions[symbol].shares *
              portfolio.positions[symbol].avgPrice;
        }
      }

      // Calculate daily portfolio value
      let positionsValue = 0;
      Object.values(portfolio.positions).forEach((pos) => {
        positionsValue += pos.currentValue || pos.shares * pos.avgPrice;
      });

      portfolio.totalValue = portfolio.cash + positionsValue;
      portfolio.equity.push({
        date: currentDate,
        value: portfolio.totalValue,
        cash: portfolio.cash,
        positions: positionsValue,
      });
    }

    // Calculate final results
    const finalValue = portfolio.totalValue;
    const totalReturn = finalValue - initialCapital;
    const totalReturnPercent = (totalReturn / initialCapital) * 100;

    // Calculate trade statistics
    const completedTrades = portfolio.trades.filter((t) => t.type === "sell");
    const winningTrades = completedTrades.filter((t) => t.gain > 0);
    const losingTrades = completedTrades.filter((t) => t.gain <= 0);

    const winRate =
      completedTrades.length > 0
        ? (winningTrades.length / completedTrades.length) * 100
        : 0;
    const avgWin =
      winningTrades.length > 0
        ? winningTrades.reduce((sum, t) => sum + t.gainPercent, 0) /
          winningTrades.length
        : 0;
    const avgLoss =
      losingTrades.length > 0
        ? Math.abs(
            losingTrades.reduce((sum, t) => sum + t.gainPercent, 0) /
              losingTrades.length
          )
        : 0;
    const profitFactor = avgLoss > 0 ? avgWin / avgLoss : 0;

    // Calculate max drawdown
    let maxDrawdown = 0;
    let peak = initialCapital;
    portfolio.equity.forEach((eq) => {
      if (eq.value > peak) peak = eq.value;
      const drawdown = ((peak - eq.value) / peak) * 100;
      if (drawdown > maxDrawdown) maxDrawdown = drawdown;
    });

    backtestResults.summary = {
      initialCapital,
      finalValue,
      totalReturn,
      totalReturnPercent,
      maxDrawdown,
      totalTrades: portfolio.trades.length,
      completedTrades: completedTrades.length,
      winningTrades: winningTrades.length,
      losingTrades: losingTrades.length,
      winRate,
      avgWin,
      avgLoss,
      profitFactor,
    };

    backtestResults.trades = portfolio.trades;
    backtestResults.equity = portfolio.equity;
    backtestResults.positions = portfolio.positions;

    res.json({
      success: true,
      data: {
        backtest: backtestResults,
        parameters: {
          symbols,
          startDate,
          endDate,
          signalTypes,
          initialCapital,
          commission,
          maxPositions,
        },
        executionTime: new Date().toISOString(),
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Signal backtest error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to execute signal backtest",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Get swing trading signals
router.get("/swing-signals", async (req, res) => {
  try {
    const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 25;
    const offset = (page - 1) * limit;

    let swingResult = null;
    let total = 0;

    try {
      // Check if swing_trading_signals table exists
      const tableCheck = await query(`
        SELECT EXISTS (
          SELECT FROM information_schema.tables 
          WHERE table_schema = 'public' 
          AND table_name = 'swing_trading_signals'
        );
      `);

      if (tableCheck.rows[0].exists) {
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

        const [swingRes, countRes] = await Promise.all([
          query(swingQuery, [limit, offset]),
          query(countQuery),
        ]);

        swingResult = swingRes;
        total = parseInt(countRes.rows[0].total);
      }
    } catch (dbError) {
      console.log(
        "Database error for swing signals, using fallback data:",
        dbError.message
      );
      swingResult = null;
    }

    // Return error if database query failed or returned no results
    if (
      !swingResult ||
      !Array.isArray(swingResult.rows) ||
      swingResult.rows.length === 0
    ) {
      return res.status(404).json({
        success: false,
        error: "No swing trading signals found",
        message:
          "No swing trading signals are available. Please ensure the trading_signals table is populated.",
        pagination: {
          page,
          limit,
          total: 0,
          totalPages: 0,
          hasNext: false,
          hasPrev: false,
        },
      });
    }

    const totalPages = Math.ceil(total / limit);

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
      query: req.query,
    });
    res.status(500).json({
      success: false,
      error: `Failed to fetch swing signals: ${error.message}`,
      details: error.message,
    });
  }
});

// List endpoint - alias for the root signals endpoint for contract compatibility
router.get("/list", async (req, res) => {
  console.log(
    `📋 [SIGNALS] List endpoint redirecting to main signals endpoint`
  );

  // Forward all query parameters
  const queryString =
    Object.keys(req.query).length > 0
      ? "?" + new URLSearchParams(req.query).toString()
      : "";

  const redirectUrl = `/api/signals${queryString}`;

  res.redirect(301, redirectUrl);
});

module.exports = router;
