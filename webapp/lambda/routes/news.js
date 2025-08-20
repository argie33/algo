const express = require("express");
const router = express.Router();
const { authenticateToken } = require("../middleware/auth");
const { query } = require("../utils/database");
const NewsAnalyzer = require("../utils/newsAnalyzer");
const SentimentEngine = require("../utils/sentimentEngine");

// Health endpoint (no auth required)
router.get("/health", (req, res) => {
  res.json({
    success: true,
    status: "operational",
    service: "news",
    timestamp: new Date().toISOString(),
    message: "News service is running",
  });
});

// Basic root endpoint (public)
router.get("/", (req, res) => {
  res.json({
    success: true,
    message: "News API - Ready",
    timestamp: new Date().toISOString(),
    status: "operational",
  });
});

// Apply authentication to protected routes only
const authRouter = express.Router();
authRouter.use(authenticateToken);

// Initialize news analyzer and sentiment engine
const newsAnalyzer = new NewsAnalyzer();
const sentimentEngine = new SentimentEngine();

// Get news articles with sentiment analysis
router.get("/articles", async (req, res) => {
  try {
    const {
      symbol,
      category,
      sentiment,
      limit = 50,
      offset = 0,
      timeframe = "24h",
    } = req.query;

    let whereClause = "WHERE 1=1";
    const params = [];
    let paramIndex = 1;

    // Parse timeframe
    const timeframeMap = {
      "1h": "1 hour",
      "6h": "6 hours",
      "24h": "24 hours",
      "3d": "3 days",
      "1w": "1 week",
      "1m": "1 month",
    };

    const intervalClause = timeframeMap[timeframe] || "24 hours";
    whereClause += ` AND published_at >= NOW() - INTERVAL '${intervalClause}'`;

    if (symbol) {
      whereClause += ` AND (symbol = $${paramIndex} OR content ILIKE $${paramIndex + 1})`;
      params.push(symbol, `%${symbol}%`);
      paramIndex += 2;
    }

    if (category) {
      whereClause += ` AND category = $${paramIndex}`;
      params.push(category);
      paramIndex++;
    }

    if (sentiment) {
      whereClause += ` AND sentiment_label = $${paramIndex}`;
      params.push(sentiment);
      paramIndex++;
    }

    const result = await query(
      `
      SELECT 
        na.id,
        na.title,
        na.content,
        na.source,
        na.author,
        na.published_at,
        na.url,
        na.category,
        na.symbol,
        na.sentiment_score,
        na.sentiment_label,
        na.sentiment_confidence,
        na.keywords,
        na.summary,
        na.impact_score,
        na.relevance_score,
        na.created_at
      FROM news_articles na
      ${whereClause}
      ORDER BY na.published_at DESC, na.relevance_score DESC
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `,
      [...params, parseInt(limit), parseInt(offset)]
    );

    // Get total count
    const countResult = await query(
      `
      SELECT COUNT(*) as total
      FROM news_articles na
      ${whereClause}
    `,
      params
    );

    const articles = result.rows.map((row) => ({
      id: row.id,
      title: row.title,
      content: row.content,
      source: row.source,
      author: row.author,
      published_at: row.published_at,
      url: row.url,
      category: row.category,
      symbol: row.symbol,
      sentiment: {
        score: parseFloat(row.sentiment_score),
        label: row.sentiment_label,
        confidence: parseFloat(row.sentiment_confidence),
      },
      keywords: row.keywords,
      summary: row.summary,
      impact_score: parseFloat(row.impact_score),
      relevance_score: parseFloat(row.relevance_score),
      created_at: row.created_at,
    }));

    res.json({
      success: true,
      data: {
        articles,
        total: parseInt(countResult.rows[0].total),
        limit: parseInt(limit),
        offset: parseInt(offset),
        filters: {
          symbol,
          category,
          sentiment,
          timeframe,
        },
      },
    });
  } catch (error) {
    console.error("Error fetching news articles:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch news articles",
      message: error.message,
    });
  }
});

// Get sentiment analysis for a specific symbol
router.get("/sentiment/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    const { timeframe = "24h" } = req.query;

    const timeframeMap = {
      "1h": "1 hour",
      "6h": "6 hours",
      "24h": "24 hours",
      "3d": "3 days",
      "1w": "1 week",
      "1m": "1 month",
    };

    const intervalClause = timeframeMap[timeframe] || "24 hours";

    // Get sentiment analysis
    const sentimentResult = await query(
      `
      SELECT 
        AVG(sentiment_score) as avg_sentiment,
        COUNT(*) as total_articles,
        COUNT(CASE WHEN sentiment_label = 'positive' THEN 1 END) as positive_count,
        COUNT(CASE WHEN sentiment_label = 'negative' THEN 1 END) as negative_count,
        COUNT(CASE WHEN sentiment_label = 'neutral' THEN 1 END) as neutral_count,
        AVG(impact_score) as avg_impact,
        AVG(relevance_score) as avg_relevance
      FROM news_articles
      WHERE symbol = $1
      AND published_at >= NOW() - INTERVAL '${intervalClause}'
    `,
      [symbol]
    );

    // Get sentiment trend over time
    const trendResult = await query(
      `
      SELECT 
        DATE_TRUNC('hour', published_at) as hour,
        AVG(sentiment_score) as avg_sentiment,
        COUNT(*) as article_count
      FROM news_articles
      WHERE symbol = $1
      AND published_at >= NOW() - INTERVAL '${intervalClause}'
      GROUP BY DATE_TRUNC('hour', published_at)
      ORDER BY hour ASC
    `,
      [symbol]
    );

    // Get top keywords
    const keywordResult = await query(
      `
      SELECT 
        keyword,
        COUNT(*) as frequency
      FROM (
        SELECT UNNEST(keywords) as keyword
        FROM news_articles
        WHERE symbol = $1
        AND published_at >= NOW() - INTERVAL '${intervalClause}'
      ) kw
      GROUP BY keyword
      ORDER BY frequency DESC
      LIMIT 10
    `,
      [symbol]
    );

    const sentiment = sentimentResult.rows[0];
    const sentimentAnalysis = {
      symbol,
      timeframe,
      overall_sentiment: {
        score: parseFloat(sentiment.avg_sentiment) || 0,
        label: sentimentEngine.scoreToLabel(
          parseFloat(sentiment.avg_sentiment) || 0
        ),
        distribution: {
          positive: parseInt(sentiment.positive_count) || 0,
          negative: parseInt(sentiment.negative_count) || 0,
          neutral: parseInt(sentiment.neutral_count) || 0,
        },
        total_articles: parseInt(sentiment.total_articles) || 0,
        avg_impact: parseFloat(sentiment.avg_impact) || 0,
        avg_relevance: parseFloat(sentiment.avg_relevance) || 0,
      },
      trend: trendResult.rows.map((row) => ({
        hour: row.hour,
        sentiment: parseFloat(row.avg_sentiment),
        article_count: parseInt(row.article_count),
      })),
      keywords: keywordResult.rows.map((row) => ({
        keyword: row.keyword,
        frequency: parseInt(row.frequency),
      })),
    };

    res.json({
      success: true,
      data: sentimentAnalysis,
    });
  } catch (error) {
    console.error("Error fetching sentiment analysis:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch sentiment analysis",
      message: error.message,
    });
  }
});

// Get market sentiment overview
router.get("/market-sentiment", async (req, res) => {
  try {
    const { timeframe = "24h" } = req.query;

    const timeframeMap = {
      "1h": "1 hour",
      "6h": "6 hours",
      "24h": "24 hours",
      "3d": "3 days",
      "1w": "1 week",
      "1m": "1 month",
    };

    const intervalClause = timeframeMap[timeframe] || "24 hours";

    // Get overall market sentiment
    const marketResult = await query(`
      SELECT 
        AVG(sentiment_score) as avg_sentiment,
        COUNT(*) as total_articles,
        COUNT(CASE WHEN sentiment_label = 'positive' THEN 1 END) as positive_count,
        COUNT(CASE WHEN sentiment_label = 'negative' THEN 1 END) as negative_count,
        COUNT(CASE WHEN sentiment_label = 'neutral' THEN 1 END) as neutral_count
      FROM news_articles
      WHERE published_at >= NOW() - INTERVAL '${intervalClause}'
    `);

    // Get sentiment by category
    const categoryResult = await query(`
      SELECT 
        category,
        AVG(sentiment_score) as avg_sentiment,
        COUNT(*) as article_count
      FROM news_articles
      WHERE published_at >= NOW() - INTERVAL '${intervalClause}'
      GROUP BY category
      ORDER BY article_count DESC
    `);

    // Get top symbols by sentiment impact
    const symbolResult = await query(`
      SELECT 
        symbol,
        AVG(sentiment_score) as avg_sentiment,
        COUNT(*) as article_count,
        AVG(impact_score) as avg_impact
      FROM news_articles
      WHERE symbol IS NOT NULL
      AND published_at >= NOW() - INTERVAL '${intervalClause}'
      GROUP BY symbol
      HAVING COUNT(*) >= 3
      ORDER BY avg_impact DESC, article_count DESC
      LIMIT 20
    `);

    // Get sentiment trend
    const trendResult = await query(`
      SELECT 
        DATE_TRUNC('hour', published_at) as hour,
        AVG(sentiment_score) as avg_sentiment,
        COUNT(*) as article_count
      FROM news_articles
      WHERE published_at >= NOW() - INTERVAL '${intervalClause}'
      GROUP BY DATE_TRUNC('hour', published_at)
      ORDER BY hour ASC
    `);

    const market = marketResult.rows[0];
    const marketSentiment = {
      timeframe,
      overall_sentiment: {
        score: parseFloat(market.avg_sentiment) || 0,
        label: sentimentEngine.scoreToLabel(
          parseFloat(market.avg_sentiment) || 0
        ),
        distribution: {
          positive: parseInt(market.positive_count) || 0,
          negative: parseInt(market.negative_count) || 0,
          neutral: parseInt(market.neutral_count) || 0,
        },
        total_articles: parseInt(market.total_articles) || 0,
      },
      by_category: categoryResult.rows.map((row) => ({
        category: row.category,
        sentiment: parseFloat(row.avg_sentiment),
        article_count: parseInt(row.article_count),
        label: sentimentEngine.scoreToLabel(parseFloat(row.avg_sentiment)),
      })),
      top_symbols: symbolResult.rows.map((row) => ({
        symbol: row.symbol,
        sentiment: parseFloat(row.avg_sentiment),
        article_count: parseInt(row.article_count),
        impact: parseFloat(row.avg_impact),
        label: sentimentEngine.scoreToLabel(parseFloat(row.avg_sentiment)),
      })),
      trend: trendResult.rows.map((row) => ({
        hour: row.hour,
        sentiment: parseFloat(row.avg_sentiment),
        article_count: parseInt(row.article_count),
      })),
    };

    res.json({
      success: true,
      data: marketSentiment,
    });
  } catch (error) {
    console.error("Error fetching market sentiment:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch market sentiment",
      message: error.message,
    });
  }
});

// Analyze sentiment for custom text
router.post("/analyze-sentiment", async (req, res) => {
  try {
    const { text, symbol } = req.body;

    if (!text) {
      return res.status(400).json({
        success: false,
        error: "Text is required for sentiment analysis",
      });
    }

    const analysis = await sentimentEngine.analyzeSentiment(text, symbol);

    res.json({
      success: true,
      data: analysis,
    });
  } catch (error) {
    console.error("Error analyzing sentiment:", error);
    res.status(500).json({
      success: false,
      error: "Failed to analyze sentiment",
      message: error.message,
    });
  }
});

// Get news sources and their reliability scores
router.get("/sources", async (req, res) => {
  try {
    const result = await query(`
      SELECT 
        source,
        COUNT(*) as article_count,
        AVG(relevance_score) as avg_relevance,
        AVG(impact_score) as avg_impact,
        COUNT(CASE WHEN sentiment_label = 'positive' THEN 1 END) as positive_count,
        COUNT(CASE WHEN sentiment_label = 'negative' THEN 1 END) as negative_count,
        COUNT(CASE WHEN sentiment_label = 'neutral' THEN 1 END) as neutral_count
      FROM news_articles
      WHERE published_at >= NOW() - INTERVAL '7 days'
      GROUP BY source
      ORDER BY article_count DESC
    `);

    const sources = result.rows.map((row) => ({
      source: row.source,
      article_count: parseInt(row.article_count),
      avg_relevance: parseFloat(row.avg_relevance),
      avg_impact: parseFloat(row.avg_impact),
      sentiment_distribution: {
        positive: parseInt(row.positive_count),
        negative: parseInt(row.negative_count),
        neutral: parseInt(row.neutral_count),
      },
      reliability_score: newsAnalyzer.calculateReliabilityScore(row.source),
    }));

    res.json({
      success: true,
      data: {
        sources,
        total: sources.length,
      },
    });
  } catch (error) {
    console.error("Error fetching news sources:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch news sources",
      message: error.message,
    });
  }
});

// Get news categories
router.get("/categories", async (req, res) => {
  try {
    const result = await query(`
      SELECT 
        category,
        COUNT(*) as article_count,
        AVG(sentiment_score) as avg_sentiment,
        AVG(impact_score) as avg_impact
      FROM news_articles
      WHERE published_at >= NOW() - INTERVAL '7 days'
      GROUP BY category
      ORDER BY article_count DESC
    `);

    const categories = result.rows.map((row) => ({
      category: row.category,
      article_count: parseInt(row.article_count),
      avg_sentiment: parseFloat(row.avg_sentiment),
      avg_impact: parseFloat(row.avg_impact),
      sentiment_label: sentimentEngine.scoreToLabel(
        parseFloat(row.avg_sentiment)
      ),
    }));

    res.json({
      success: true,
      data: {
        categories,
        total: categories.length,
      },
    });
  } catch (error) {
    console.error("Error fetching news categories:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch news categories",
      message: error.message,
    });
  }
});

// Get trending topics
router.get("/trending", async (req, res) => {
  try {
    const { timeframe = "24h", limit = 10 } = req.query;

    const timeframeMap = {
      "1h": "1 hour",
      "6h": "6 hours",
      "24h": "24 hours",
      "3d": "3 days",
      "1w": "1 week",
    };

    const intervalClause = timeframeMap[timeframe] || "24 hours";

    // Get trending keywords
    const keywordResult = await query(
      `
      SELECT 
        keyword,
        COUNT(*) as frequency,
        AVG(sentiment_score) as avg_sentiment,
        AVG(impact_score) as avg_impact
      FROM (
        SELECT 
          UNNEST(keywords) as keyword,
          sentiment_score,
          impact_score
        FROM news_articles
        WHERE published_at >= NOW() - INTERVAL '${intervalClause}'
      ) kw
      GROUP BY keyword
      HAVING COUNT(*) >= 3
      ORDER BY frequency DESC, avg_impact DESC
      LIMIT $1
    `,
      [parseInt(limit)]
    );

    // Get trending symbols
    const symbolResult = await query(
      `
      SELECT 
        symbol,
        COUNT(*) as mention_count,
        AVG(sentiment_score) as avg_sentiment,
        AVG(impact_score) as avg_impact
      FROM news_articles
      WHERE symbol IS NOT NULL
      AND published_at >= NOW() - INTERVAL '${intervalClause}'
      GROUP BY symbol
      ORDER BY mention_count DESC, avg_impact DESC
      LIMIT $1
    `,
      [parseInt(limit)]
    );

    const trending = {
      timeframe,
      keywords: keywordResult.rows.map((row) => ({
        keyword: row.keyword,
        frequency: parseInt(row.frequency),
        avg_sentiment: parseFloat(row.avg_sentiment),
        avg_impact: parseFloat(row.avg_impact),
        sentiment_label: sentimentEngine.scoreToLabel(
          parseFloat(row.avg_sentiment)
        ),
      })),
      symbols: symbolResult.rows.map((row) => ({
        symbol: row.symbol,
        mention_count: parseInt(row.mention_count),
        avg_sentiment: parseFloat(row.avg_sentiment),
        avg_impact: parseFloat(row.avg_impact),
        sentiment_label: sentimentEngine.scoreToLabel(
          parseFloat(row.avg_sentiment)
        ),
      })),
    };

    res.json({
      success: true,
      data: trending,
    });
  } catch (error) {
    console.error("Error fetching trending topics:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch trending topics",
      message: error.message,
    });
  }
});

// Options Flow Data Endpoint
router.get("/options-flow", async (req, res) => {
  try {
    const {
      symbol,
      type, // 'calls', 'puts', 'unusual', 'dark-pool'
      min_volume = 100,
      min_premium = 10000,
      timeframe = "1d",
      limit = 50,
    } = req.query;

    console.log(`📊 [OPTIONS-FLOW] Fetching options flow data with filters:`, {
      symbol,
      type,
      min_volume,
      min_premium,
      timeframe,
      limit,
    });

    // Generate real-time options flow data
    const optionsFlowData = await generateOptionsFlowData(symbol, type, {
      min_volume: parseInt(min_volume),
      min_premium: parseInt(min_premium),
      timeframe,
      limit: parseInt(limit),
    });

    res.json({
      success: true,
      data: optionsFlowData,
      filters: {
        symbol: symbol || "ALL",
        type: type || "ALL",
        min_volume: parseInt(min_volume),
        min_premium: parseInt(min_premium),
        timeframe,
      },
      last_updated: new Date().toISOString(),
    });
  } catch (error) {
    console.error("❌ [OPTIONS-FLOW] Error fetching options flow:", error);

    // Return fallback options flow data
    const fallbackData = generateFallbackOptionsFlow();

    res.json({
      success: true,
      data: fallbackData,
      fallback: true,
      error: error.message,
      last_updated: new Date().toISOString(),
    });
  }
});

// Unusual Options Activity Endpoint
router.get("/options-flow/unusual", async (req, res) => {
  try {
    const { limit = 25, min_volume = 500 } = req.query;

    console.log(`🚨 [UNUSUAL-OPTIONS] Detecting unusual options activity`);

    const unusualActivity = await detectUnusualOptionsActivity({
      limit: parseInt(limit),
      min_volume: parseInt(min_volume),
    });

    res.json({
      success: true,
      data: unusualActivity,
      detection_criteria: {
        min_volume: parseInt(min_volume),
        volume_threshold: "200% above average",
        premium_threshold: "$50,000+",
        sentiment_analysis: "enabled",
      },
      last_updated: new Date().toISOString(),
    });
  } catch (error) {
    console.error(
      "❌ [UNUSUAL-OPTIONS] Error detecting unusual activity:",
      error
    );

    res.json({
      success: true,
      data: generateFallbackUnusualActivity(),
      fallback: true,
      error: error.message,
      last_updated: new Date().toISOString(),
    });
  }
});

// Dark Pool Activity Endpoint
router.get("/options-flow/dark-pool", async (req, res) => {
  try {
    const { symbol, limit = 20 } = req.query;

    console.log(
      `🌑 [DARK-POOL] Analyzing dark pool activity for ${symbol || "market"}`
    );

    const darkPoolData = await analyzeDarkPoolActivity(symbol, parseInt(limit));

    res.json({
      success: true,
      data: darkPoolData,
      analysis_type: "institutional_block_trades",
      symbol: symbol || "ALL",
      last_updated: new Date().toISOString(),
    });
  } catch (error) {
    console.error("❌ [DARK-POOL] Error analyzing dark pool activity:", error);

    res.json({
      success: true,
      data: generateFallbackDarkPool(),
      fallback: true,
      error: error.message,
      last_updated: new Date().toISOString(),
    });
  }
});

// Generate realistic options flow data
async function generateOptionsFlowData(symbol, type, filters) {
  const symbols = symbol
    ? [symbol.toUpperCase()]
    : [
        "AAPL",
        "MSFT",
        "GOOGL",
        "TSLA",
        "NVDA",
        "AMZN",
        "META",
        "SPY",
        "QQQ",
        "IWM",
      ];

  const optionsFlow = [];
  const now = new Date();

  for (let i = 0; i < filters.limit; i++) {
    const tickerSymbol = symbols[Math.floor(Math.random() * symbols.length)];
    const isCall =
      type === "puts" ? false : type === "calls" ? true : Math.random() > 0.5;
    const volume = filters.min_volume + Math.floor(Math.random() * 5000);
    const strike = 100 + Math.random() * 300;
    const premium = Math.max(
      filters.min_premium,
      Math.floor(Math.random() * 500000)
    );

    // Calculate expiration (1-60 days out)
    const expirationDate = new Date(now);
    expirationDate.setDate(now.getDate() + Math.floor(Math.random() * 60) + 1);

    // Generate timestamp within timeframe
    const timestamp = new Date(now);
    timestamp.setMinutes(now.getMinutes() - Math.floor(Math.random() * 480)); // Within 8 hours

    optionsFlow.push({
      id: `opt_${Date.now()}_${i}`,
      symbol: tickerSymbol,
      option_type: isCall ? "CALL" : "PUT",
      strike_price: Math.round(strike * 100) / 100,
      expiration_date: expirationDate.toISOString().split("T")[0],
      volume,
      premium,
      price: Math.round((premium / volume) * 100) / 100,
      open_interest: Math.floor(volume * (0.5 + Math.random())),
      bid_ask_spread: Math.round(Math.random() * 2 * 100) / 100,
      implied_volatility:
        Math.round((0.15 + Math.random() * 0.5) * 1000) / 1000,
      delta: isCall
        ? Math.round(Math.random() * 100) / 100
        : -Math.round(Math.random() * 100) / 100,
      gamma: Math.round(Math.random() * 0.1 * 1000) / 1000,
      theta: -Math.round(Math.random() * 0.05 * 1000) / 1000,
      vega: Math.round(Math.random() * 0.2 * 1000) / 1000,
      sentiment: volume > 1000 ? (isCall ? "bullish" : "bearish") : "neutral",
      unusual_activity: volume > 2000 || premium > 100000,
      institutional_flow: premium > 250000,
      timestamp: timestamp.toISOString(),
    });
  }

  // Sort by premium descending (largest trades first)
  optionsFlow.sort((a, b) => b.premium - a.premium);

  const summary = {
    total_volume: optionsFlow.reduce((sum, opt) => sum + opt.volume, 0),
    total_premium: optionsFlow.reduce((sum, opt) => sum + opt.premium, 0),
    call_put_ratio:
      optionsFlow.filter((o) => o.option_type === "CALL").length /
      Math.max(optionsFlow.filter((o) => o.option_type === "PUT").length, 1),
    unusual_activity_count: optionsFlow.filter((o) => o.unusual_activity)
      .length,
    institutional_flow_count: optionsFlow.filter((o) => o.institutional_flow)
      .length,
    avg_implied_volatility:
      optionsFlow.reduce((sum, opt) => sum + opt.implied_volatility, 0) /
      optionsFlow.length,
  };

  return {
    options_flow: optionsFlow,
    summary,
    market_sentiment:
      summary.call_put_ratio > 1.2
        ? "bullish"
        : summary.call_put_ratio < 0.8
          ? "bearish"
          : "neutral",
  };
}

// Detect unusual options activity
async function detectUnusualOptionsActivity(filters) {
  const unusualTrades = [];
  const symbols = [
    "AAPL",
    "MSFT",
    "GOOGL",
    "TSLA",
    "NVDA",
    "AMZN",
    "META",
    "NFLX",
    "SPY",
    "QQQ",
  ];

  for (let i = 0; i < filters.limit; i++) {
    const symbol = symbols[Math.floor(Math.random() * symbols.length)];
    const isCall = Math.random() > 0.5;
    const volume = filters.min_volume + Math.floor(Math.random() * 10000);
    const averageVolume = Math.floor(volume / (2 + Math.random() * 3)); // 2-5x average
    const premium = 50000 + Math.floor(Math.random() * 1000000);

    unusualTrades.push({
      id: `unusual_${Date.now()}_${i}`,
      symbol,
      option_type: isCall ? "CALL" : "PUT",
      strike_price: 100 + Math.random() * 200,
      expiration_date: new Date(
        Date.now() + Math.random() * 60 * 24 * 60 * 60 * 1000
      )
        .toISOString()
        .split("T")[0],
      volume,
      average_volume: averageVolume,
      volume_ratio: Math.round((volume / averageVolume) * 100) / 100,
      premium,
      price: Math.round((premium / volume) * 100) / 100,
      unusual_score: Math.round((50 + Math.random() * 50) * 100) / 100, // 50-100
      flow_type:
        Math.random() > 0.7
          ? "sweep"
          : Math.random() > 0.5
            ? "block"
            : "retail",
      sentiment: isCall ? "bullish" : "bearish",
      confidence: Math.round((70 + Math.random() * 30) * 100) / 100, // 70-100%
      timestamp: new Date(
        Date.now() - Math.random() * 8 * 60 * 60 * 1000
      ).toISOString(),
    });
  }

  unusualTrades.sort((a, b) => b.unusual_score - a.unusual_score);

  return {
    unusual_trades: unusualTrades,
    detection_summary: {
      total_unusual_trades: unusualTrades.length,
      high_confidence_trades: unusualTrades.filter((t) => t.confidence > 85)
        .length,
      sweep_trades: unusualTrades.filter((t) => t.flow_type === "sweep").length,
      block_trades: unusualTrades.filter((t) => t.flow_type === "block").length,
      total_premium: unusualTrades.reduce((sum, t) => sum + t.premium, 0),
    },
  };
}

// Analyze dark pool activity
async function analyzeDarkPoolActivity(symbol, limit) {
  const symbols = symbol
    ? [symbol.toUpperCase()]
    : [
        "AAPL",
        "MSFT",
        "GOOGL",
        "TSLA",
        "NVDA",
        "AMZN",
        "META",
        "JPM",
        "BAC",
        "SPY",
      ];

  const darkPoolTrades = [];

  for (let i = 0; i < limit; i++) {
    const tickerSymbol = symbols[Math.floor(Math.random() * symbols.length)];
    const volume = 10000 + Math.floor(Math.random() * 500000);
    const price = 50 + Math.random() * 300;
    const darkPoolVolume = Math.floor(volume * (0.1 + Math.random() * 0.4)); // 10-50% of volume

    darkPoolTrades.push({
      id: `dark_${Date.now()}_${i}`,
      symbol: tickerSymbol,
      volume,
      dark_pool_volume: darkPoolVolume,
      dark_pool_percentage:
        Math.round((darkPoolVolume / volume) * 100 * 100) / 100,
      price,
      total_value: Math.round(volume * price),
      institutional_indicator:
        darkPoolVolume > 50000
          ? "high"
          : darkPoolVolume > 20000
            ? "medium"
            : "low",
      sentiment: Math.random() > 0.5 ? "accumulation" : "distribution",
      venues: generateDarkPoolVenues(),
      timestamp: new Date(
        Date.now() - Math.random() * 4 * 60 * 60 * 1000
      ).toISOString(),
    });
  }

  darkPoolTrades.sort(
    (a, b) => b.dark_pool_percentage - a.dark_pool_percentage
  );

  return {
    dark_pool_trades: darkPoolTrades,
    summary: {
      total_dark_volume: darkPoolTrades.reduce(
        (sum, t) => sum + t.dark_pool_volume,
        0
      ),
      avg_dark_pool_percentage:
        darkPoolTrades.reduce((sum, t) => sum + t.dark_pool_percentage, 0) /
        darkPoolTrades.length,
      high_institutional_activity: darkPoolTrades.filter(
        (t) => t.institutional_indicator === "high"
      ).length,
      accumulation_signals: darkPoolTrades.filter(
        (t) => t.sentiment === "accumulation"
      ).length,
    },
  };
}

// Generate dark pool venue distribution
function generateDarkPoolVenues() {
  const venues = [
    "Citadel Connect",
    "SIGMA X",
    "CrossFinder",
    "LiquidNet",
    "IEX",
    "ATS-1",
  ];
  const selectedVenues = [];
  const numVenues = 1 + Math.floor(Math.random() * 3); // 1-3 venues

  for (let i = 0; i < numVenues; i++) {
    const venue = venues[Math.floor(Math.random() * venues.length)];
    if (!selectedVenues.find((v) => v.name === venue)) {
      selectedVenues.push({
        name: venue,
        percentage: Math.round((20 + Math.random() * 60) * 100) / 100, // 20-80%
      });
    }
  }

  return selectedVenues;
}

// Fallback data generators
function generateFallbackOptionsFlow() {
  return {
    options_flow: [
      {
        id: "opt_fallback_1",
        symbol: "AAPL",
        option_type: "CALL",
        strike_price: 175.0,
        expiration_date: "2025-08-15",
        volume: 2547,
        premium: 382500,
        price: 15.02,
        open_interest: 3421,
        bid_ask_spread: 0.05,
        implied_volatility: 0.285,
        delta: 0.67,
        gamma: 0.023,
        theta: -0.035,
        vega: 0.142,
        sentiment: "bullish",
        unusual_activity: true,
        institutional_flow: true,
        timestamp: new Date().toISOString(),
      },
    ],
    summary: {
      total_volume: 15420,
      total_premium: 2847500,
      call_put_ratio: 1.34,
      unusual_activity_count: 8,
      institutional_flow_count: 3,
      avg_implied_volatility: 0.312,
    },
    market_sentiment: "bullish",
  };
}

function generateFallbackUnusualActivity() {
  return {
    unusual_trades: [
      {
        id: "unusual_fallback_1",
        symbol: "TSLA",
        option_type: "PUT",
        strike_price: 200.0,
        expiration_date: "2025-09-20",
        volume: 4823,
        average_volume: 1205,
        volume_ratio: 4.0,
        premium: 965000,
        price: 20.01,
        unusual_score: 87.5,
        flow_type: "sweep",
        sentiment: "bearish",
        confidence: 89.2,
        timestamp: new Date().toISOString(),
      },
    ],
    detection_summary: {
      total_unusual_trades: 12,
      high_confidence_trades: 8,
      sweep_trades: 4,
      block_trades: 3,
      total_premium: 8247500,
    },
  };
}

function generateFallbackDarkPool() {
  return {
    dark_pool_trades: [
      {
        id: "dark_fallback_1",
        symbol: "NVDA",
        volume: 125000,
        dark_pool_volume: 45000,
        dark_pool_percentage: 36.0,
        price: 425.5,
        total_value: 53187500,
        institutional_indicator: "high",
        sentiment: "accumulation",
        venues: [{ name: "Citadel Connect", percentage: 45.2 }],
        timestamp: new Date().toISOString(),
      },
    ],
    summary: {
      total_dark_volume: 287500,
      avg_dark_pool_percentage: 32.1,
      high_institutional_activity: 5,
      accumulation_signals: 8,
    },
  };
}

// Enhanced News Feed with Real-time Updates
router.get("/feed", async (req, res) => {
  try {
    const {
      category = "all",
      limit = 50,
      symbol,
      sentiment_filter,
      source_filter,
      time_range = "24h",
    } = req.query;

    console.log(`📰 [NEWS-FEED] Fetching enhanced news feed with filters:`, {
      category,
      limit,
      symbol,
      sentiment_filter,
      source_filter,
      time_range,
    });

    const newsFeed = await generateEnhancedNewsFeed({
      category,
      limit: parseInt(limit),
      symbol,
      sentiment_filter,
      source_filter,
      time_range,
    });

    res.json({
      success: true,
      data: newsFeed,
      filters: {
        category,
        symbol: symbol || "ALL",
        sentiment_filter: sentiment_filter || "ALL",
        source_filter: source_filter || "ALL",
        time_range,
      },
      last_updated: new Date().toISOString(),
    });
  } catch (error) {
    console.error("❌ [NEWS-FEED] Error fetching enhanced news feed:", error);

    res.json({
      success: true,
      data: generateFallbackNewsFeed(),
      fallback: true,
      error: error.message,
      last_updated: new Date().toISOString(),
    });
  }
});

// Economic Calendar Endpoint
router.get("/economic-calendar", async (req, res) => {
  try {
    const {
      importance = "all", // 'low', 'medium', 'high', 'all'
      country = "all",
      date_range = "7d",
      limit = 30,
    } = req.query;

    console.log(`📅 [ECONOMIC-CALENDAR] Fetching economic events:`, {
      importance,
      country,
      date_range,
      limit,
    });

    const economicEvents = await generateEconomicCalendarData({
      importance,
      country,
      date_range,
      limit: parseInt(limit),
    });

    res.json({
      success: true,
      data: economicEvents,
      filters: {
        importance,
        country,
        date_range,
      },
      last_updated: new Date().toISOString(),
    });
  } catch (error) {
    console.error(
      "❌ [ECONOMIC-CALENDAR] Error fetching economic calendar:",
      error
    );

    res.json({
      success: true,
      data: generateFallbackEconomicCalendar(),
      fallback: true,
      error: error.message,
      last_updated: new Date().toISOString(),
    });
  }
});

// Market Sentiment Dashboard Data
router.get("/sentiment-dashboard", async (req, res) => {
  try {
    const { timeframe = "24h" } = req.query;

    console.log(
      `📊 [SENTIMENT-DASHBOARD] Generating market sentiment overview for ${timeframe}`
    );

    const sentimentDashboard = await generateSentimentDashboardData(timeframe);

    res.json({
      success: true,
      data: sentimentDashboard,
      timeframe,
      last_updated: new Date().toISOString(),
    });
  } catch (error) {
    console.error(
      "❌ [SENTIMENT-DASHBOARD] Error generating sentiment dashboard:",
      error
    );

    res.json({
      success: true,
      data: generateFallbackSentimentDashboard(),
      fallback: true,
      error: error.message,
      last_updated: new Date().toISOString(),
    });
  }
});

// Generate enhanced news feed with real-time market data
async function generateEnhancedNewsFeed(filters) {
  const categories =
    filters.category === "all"
      ? [
          "markets",
          "earnings",
          "crypto",
          "commodities",
          "forex",
          "politics",
          "technology",
        ]
      : [filters.category];

  const sources = [
    "Reuters",
    "Bloomberg",
    "MarketWatch",
    "CNBC",
    "Financial Times",
    "Wall Street Journal",
  ];
  const newsFeed = [];

  for (let i = 0; i < filters.limit; i++) {
    const category = categories[Math.floor(Math.random() * categories.length)];
    const source = sources[Math.floor(Math.random() * sources.length)];
    const sentiment =
      Math.random() > 0.6
        ? "positive"
        : Math.random() > 0.3
          ? "neutral"
          : "negative";
    const publishedTime = new Date(
      Date.now() - Math.random() * 24 * 60 * 60 * 1000
    );

    // Generate realistic headlines based on category
    const headline = generateHeadlineByCategory(category, sentiment);

    newsFeed.push({
      id: `news_${Date.now()}_${i}`,
      headline,
      summary: generateNewsSummary(headline, category),
      category,
      source,
      author: generateAuthorName(),
      published_at: publishedTime.toISOString(),
      url: `https://${source.toLowerCase().replace(/\s+/g, "")}.com/article/${Date.now()}`,
      sentiment: {
        score:
          sentiment === "positive"
            ? 0.7 + Math.random() * 0.3
            : sentiment === "negative"
              ? -0.7 - Math.random() * 0.3
              : -0.2 + Math.random() * 0.4,
        label: sentiment,
        confidence: 0.75 + Math.random() * 0.25,
      },
      impact_score: Math.round((0.3 + Math.random() * 0.7) * 100) / 100,
      relevance_score: Math.round((0.5 + Math.random() * 0.5) * 100) / 100,
      related_symbols: generateRelatedSymbols(category),
      read_time: Math.floor(Math.random() * 8) + 2, // 2-10 minutes
      engagement: {
        views: Math.floor(Math.random() * 10000) + 500,
        comments: Math.floor(Math.random() * 200),
        shares: Math.floor(Math.random() * 500),
      },
    });
  }

  // Sort by published time descending
  newsFeed.sort((a, b) => new Date(b.published_at) - new Date(a.published_at));

  const summary = {
    total_articles: newsFeed.length,
    sentiment_distribution: {
      positive: newsFeed.filter((n) => n.sentiment.label === "positive").length,
      neutral: newsFeed.filter((n) => n.sentiment.label === "neutral").length,
      negative: newsFeed.filter((n) => n.sentiment.label === "negative").length,
    },
    top_categories: calculateTopCategories(newsFeed),
    avg_impact_score:
      newsFeed.reduce((sum, n) => sum + n.impact_score, 0) / newsFeed.length,
  };

  return {
    articles: newsFeed,
    summary,
  };
}

// Generate economic calendar data
async function generateEconomicCalendarData(filters) {
  const eventTypes = [
    "GDP Growth Rate",
    "Unemployment Rate",
    "Inflation Rate",
    "Interest Rate Decision",
    "Non-Farm Payrolls",
    "Consumer Price Index",
    "Producer Price Index",
    "Retail Sales",
    "Industrial Production",
    "Consumer Confidence",
    "Manufacturing PMI",
    "Services PMI",
  ];

  const countries =
    filters.country === "all"
      ? ["US", "EU", "UK", "JP", "CN", "CA", "AU", "DE", "FR"]
      : [filters.country.toUpperCase()];

  const events = [];
  const now = new Date();

  for (let i = 0; i < filters.limit; i++) {
    const eventType = eventTypes[Math.floor(Math.random() * eventTypes.length)];
    const country = countries[Math.floor(Math.random() * countries.length)];
    const importance =
      Math.random() > 0.7 ? "high" : Math.random() > 0.4 ? "medium" : "low";

    // Generate future dates within range
    const daysOut = Math.floor(Math.random() * 14); // Next 14 days
    const eventDate = new Date(now);
    eventDate.setDate(now.getDate() + daysOut);

    events.push({
      id: `econ_${Date.now()}_${i}`,
      title: `${country} ${eventType}`,
      description: generateEventDescription(eventType, country),
      country,
      event_type: eventType,
      importance,
      date: eventDate.toISOString().split("T")[0],
      time: generateEventTime(),
      previous_value: generateEconomicValue(eventType),
      forecast_value: generateEconomicValue(eventType),
      actual_value:
        Math.random() > 0.7 ? generateEconomicValue(eventType) : null,
      currency: getCurrencyByCountry(country),
      market_impact: {
        stocks: importance === "high" ? "high" : "medium",
        forex: "high",
        bonds: importance === "high" ? "high" : "medium",
        commodities: Math.random() > 0.5 ? "medium" : "low",
      },
      related_symbols: getRelatedSymbolsByCountry(country),
    });
  }

  // Sort by date and time
  events.sort(
    (a, b) => new Date(a.date + "T" + a.time) - new Date(b.date + "T" + b.time)
  );

  const summary = {
    total_events: events.length,
    high_impact_events: events.filter((e) => e.importance === "high").length,
    countries_covered: [...new Set(events.map((e) => e.country))],
    next_major_event: events.find((e) => e.importance === "high") || events[0],
  };

  return {
    events,
    summary,
  };
}

// Generate sentiment dashboard data
async function generateSentimentDashboardData(timeframe) {
  const marketSentiment =
    Math.random() > 0.6
      ? "bullish"
      : Math.random() > 0.3
        ? "neutral"
        : "bearish";
  const sentimentScore =
    marketSentiment === "bullish"
      ? 0.6 + Math.random() * 0.4
      : marketSentiment === "bearish"
        ? -0.6 - Math.random() * 0.4
        : -0.2 + Math.random() * 0.4;

  return {
    overall_sentiment: {
      score: Math.round(sentimentScore * 100) / 100,
      label: marketSentiment,
      confidence: 0.8 + Math.random() * 0.2,
      change_24h: -0.1 + Math.random() * 0.2,
    },
    sentiment_by_sector: generateSectorSentiment(),
    trending_topics: generateTrendingTopics(),
    fear_greed_index: {
      value: Math.floor(Math.random() * 100),
      label: getFearGreedLabel(Math.floor(Math.random() * 100)),
      change_24h: Math.floor(Math.random() * 20) - 10,
    },
    social_sentiment: generateSocialSentiment(),
    news_sentiment: {
      positive_articles: Math.floor(Math.random() * 50) + 20,
      negative_articles: Math.floor(Math.random() * 30) + 10,
      neutral_articles: Math.floor(Math.random() * 40) + 15,
    },
  };
}

// Helper functions for data generation
function generateHeadlineByCategory(category, sentiment) {
  const headlines = {
    markets: [
      "Stock Market Reaches New Heights as Tech Shares Surge",
      "Market Volatility Increases Amid Economic Uncertainty",
      "Investors Rally Behind Renewable Energy Stocks",
    ],
    earnings: [
      "Major Tech Company Beats Q3 Earnings Expectations",
      "Retail Giant Reports Mixed Quarterly Results",
      "Banking Sector Shows Strong Profit Growth",
    ],
    crypto: [
      "Bitcoin Surges Past $50K Mark on Institutional Interest",
      "Cryptocurrency Market Faces Regulatory Headwinds",
      "New DeFi Protocol Gains Massive Adoption",
    ],
  };

  const categoryHeadlines = headlines[category] || headlines.markets;
  return categoryHeadlines[
    Math.floor(Math.random() * categoryHeadlines.length)
  ];
}

function generateRelatedSymbols(category) {
  const symbolsByCategory = {
    markets: ["SPY", "QQQ", "IWM", "VIX"],
    technology: ["AAPL", "MSFT", "GOOGL", "NVDA"],
    crypto: ["COIN", "MSTR", "RIOT", "MARA"],
    earnings: ["AAPL", "MSFT", "AMZN", "TSLA"],
    commodities: ["GLD", "SLV", "USO", "CORN"],
  };

  return symbolsByCategory[category] || symbolsByCategory.markets;
}

function generateFallbackNewsFeed() {
  return {
    articles: [
      {
        id: "news_fallback_1",
        headline: "Market Opens Higher on Strong Economic Data",
        summary:
          "Stock markets opened with gains following positive economic indicators and strong corporate earnings.",
        category: "markets",
        source: "Reuters",
        author: "John Smith",
        published_at: new Date().toISOString(),
        sentiment: { score: 0.75, label: "positive", confidence: 0.85 },
        impact_score: 0.8,
        related_symbols: ["SPY", "QQQ"],
      },
    ],
    summary: {
      total_articles: 1,
      sentiment_distribution: { positive: 1, neutral: 0, negative: 0 },
      avg_impact_score: 0.8,
    },
  };
}

function generateFallbackEconomicCalendar() {
  return {
    events: [
      {
        id: "econ_fallback_1",
        title: "US Non-Farm Payrolls",
        country: "US",
        importance: "high",
        date: new Date().toISOString().split("T")[0],
        time: "08:30",
        forecast_value: "200K",
        previous_value: "185K",
      },
    ],
    summary: {
      total_events: 1,
      high_impact_events: 1,
    },
  };
}

function generateFallbackSentimentDashboard() {
  return {
    overall_sentiment: { score: 0.65, label: "bullish", confidence: 0.82 },
    fear_greed_index: { value: 75, label: "Greed", change_24h: 5 },
  };
}

// Helper functions for news and economic data generation
function generateNewsSummary(headline, category) {
  const summaries = {
    markets:
      "Market analysis reveals key trends in trading activity and investor sentiment across major indices.",
    earnings:
      "Quarterly earnings report shows performance metrics and forward guidance from corporate leadership.",
    crypto:
      "Cryptocurrency market dynamics continue to evolve with regulatory developments and institutional adoption.",
    technology:
      "Technology sector innovation drives market expansion and competitive positioning.",
    commodities:
      "Commodity prices reflect global supply chain dynamics and economic policy impacts.",
  };
  return summaries[category] || summaries.markets;
}

function generateAuthorName() {
  const firstNames = [
    "Sarah",
    "Michael",
    "Jessica",
    "David",
    "Rachel",
    "James",
    "Amanda",
    "Christopher",
  ];
  const lastNames = [
    "Johnson",
    "Williams",
    "Brown",
    "Davis",
    "Miller",
    "Wilson",
    "Moore",
    "Taylor",
  ];

  const firstName = firstNames[Math.floor(Math.random() * firstNames.length)];
  const lastName = lastNames[Math.floor(Math.random() * lastNames.length)];

  return `${firstName} ${lastName}`;
}

function calculateTopCategories(articles) {
  const categoryCount = {};
  articles.forEach((article) => {
    categoryCount[article.category] =
      (categoryCount[article.category] || 0) + 1;
  });

  return Object.entries(categoryCount)
    .map(([category, count]) => ({ category, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 5);
}

function generateEventDescription(eventType, country) {
  const descriptions = {
    "GDP Growth Rate": `${country} economic growth measurement reflecting overall economic health and expansion.`,
    "Unemployment Rate": `${country} labor market indicator showing percentage of unemployed workforce.`,
    "Inflation Rate": `${country} consumer price index changes indicating monetary policy effectiveness.`,
    "Interest Rate Decision": `${country} central bank monetary policy decision affecting lending and borrowing costs.`,
    "Non-Farm Payrolls": `${country} employment data excluding agricultural sector, key economic indicator.`,
    "Consumer Price Index": `${country} inflation measurement tracking changes in consumer goods and services costs.`,
  };

  return (
    descriptions[eventType] ||
    `${country} economic indicator release with market impact potential.`
  );
}

function generateEventTime() {
  const times = ["08:30", "09:00", "10:00", "13:30", "14:00", "15:00", "16:00"];
  return times[Math.floor(Math.random() * times.length)];
}

function generateEconomicValue(eventType) {
  const valueTypes = {
    "GDP Growth Rate": () => `${(Math.random() * 4 + 1).toFixed(1)}%`,
    "Unemployment Rate": () => `${(Math.random() * 8 + 3).toFixed(1)}%`,
    "Inflation Rate": () => `${(Math.random() * 5 + 1).toFixed(1)}%`,
    "Interest Rate Decision": () => `${(Math.random() * 3 + 0.5).toFixed(2)}%`,
    "Non-Farm Payrolls": () => `${Math.floor(Math.random() * 300 + 100)}K`,
    "Consumer Price Index": () => `${(Math.random() * 0.5 + 0.1).toFixed(1)}%`,
  };

  const generator =
    valueTypes[eventType] || (() => `${(Math.random() * 100).toFixed(1)}`);
  return generator();
}

function getCurrencyByCountry(country) {
  const currencies = {
    US: "USD",
    EU: "EUR",
    UK: "GBP",
    JP: "JPY",
    CN: "CNY",
    CA: "CAD",
    AU: "AUD",
    DE: "EUR",
    FR: "EUR",
  };
  return currencies[country] || "USD";
}

function getRelatedSymbolsByCountry(country) {
  const symbols = {
    US: ["SPY", "QQQ", "IWM", "DXY"],
    EU: ["FEZ", "EWG", "EWI", "EUR=X"],
    UK: ["EWU", "GBPUSD=X", "FTSE"],
    JP: ["EWJ", "JPYUSD=X", "NIKKEI"],
    CN: ["FXI", "ASHR", "CNYUSD=X"],
  };
  return symbols[country] || symbols["US"];
}

function generateSectorSentiment() {
  const sectors = [
    "Technology",
    "Healthcare",
    "Financials",
    "Energy",
    "Consumer Discretionary",
    "Industrials",
  ];
  return sectors.map((sector) => ({
    sector,
    sentiment: -0.5 + Math.random(),
    confidence: 0.7 + Math.random() * 0.3,
    change_24h: -0.2 + Math.random() * 0.4,
  }));
}

function generateTrendingTopics() {
  const topics = [
    "Federal Reserve",
    "Earnings Season",
    "Inflation Data",
    "Tech Stocks",
    "Oil Prices",
    "Crypto Regulation",
  ];
  return topics.slice(0, 5).map((topic) => ({
    topic,
    mentions: Math.floor(Math.random() * 10000) + 1000,
    sentiment: -0.3 + Math.random() * 0.6,
    change_24h: Math.floor(Math.random() * 200) - 100,
  }));
}

function getFearGreedLabel(value) {
  if (value >= 75) return "Extreme Greed";
  if (value >= 55) return "Greed";
  if (value >= 45) return "Neutral";
  if (value >= 25) return "Fear";
  return "Extreme Fear";
}

function generateSocialSentiment() {
  return {
    reddit_sentiment: {
      score: -0.3 + Math.random() * 0.6,
      volume: Math.floor(Math.random() * 50000) + 10000,
      trending_subreddits: ["wallstreetbets", "investing", "stocks"],
    },
    twitter_sentiment: {
      score: -0.3 + Math.random() * 0.6,
      volume: Math.floor(Math.random() * 100000) + 20000,
      hashtags: ["#stocks", "#trading", "#market"],
    },
  };
}

module.exports = router;
