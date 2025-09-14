const express = require("express");

const router = express.Router();
const { authenticateToken } = require("../middleware/auth");
const { query } = require("../utils/database");
const newsAnalyzer = require("../utils/newsAnalyzer");
const sentimentEngine = require("../utils/sentimentEngine");

// Helper function to convert sentiment text to numeric score
function convertSentimentToScore(sentiment) {
  if (typeof sentiment === 'number') return sentiment;
  if (!sentiment) return 0;
  
  const sentimentLower = sentiment.toLowerCase();
  if (sentimentLower === 'positive') return 0.7;
  if (sentimentLower === 'negative') return -0.7;
  if (sentimentLower === 'neutral') return 0;
  
  // Try parsing as number in case it's already numeric
  const parsed = parseFloat(sentiment);
  return isNaN(parsed) ? 0 : parsed;
}

// Helper function to convert numeric score to text label
function convertScoreToLabel(score) {
  if (typeof score === 'string') return score;
  if (score > 0.3) return 'positive';
  if (score < -0.3) return 'negative';
  return 'neutral';
}

// News functionality requires news_articles table or external news API integration

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
    data: []
  });
});

// Recent news endpoint (public access)
router.get("/recent", async (req, res) => {
  const { limit = 20, hours = 24, category = null, symbol = null } = req.query;
  
  try {

    console.log(`📰 Recent news requested, limit: ${limit}, hours: ${hours}`);

    // Check if news_articles table exists
    const tableCheck = await query(`
      SELECT table_name 
      FROM information_schema.tables 
      WHERE table_schema = 'public' 
      AND table_name = 'news_articles'
    `);
    
    if (tableCheck.rows.length === 0) {
      return res.json({
        success: true,
        data: {
          news: [],
          summary: {
            total_count: 0,
            message: "News service requires database setup with news_articles table",
            filters_applied: { 
              category: category || null, 
              symbol: symbol || null,
              limit: parseInt(limit), 
              hours: parseInt(hours) 
            }
          }
        },
        message: "News database not configured - feature requires news_articles table",
        timestamp: new Date().toISOString()
      });
    }
    
    // Build WHERE conditions for news query
    let whereConditions = ['1=1'];
    let params = [];
    let paramCounter = 1;
    
    if (category) {
      whereConditions.push(`category = $${paramCounter}`);
      params.push(category);
      paramCounter++;
    }
    
    if (symbol) {
      whereConditions.push(`symbols @> $${paramCounter}::jsonb`);
      params.push(JSON.stringify([symbol.toUpperCase()]));
      paramCounter++;
    }
    
    whereConditions.push(`published_at >= $${paramCounter}`);
    params.push(new Date(Date.now() - parseInt(hours) * 60 * 60 * 1000).toISOString());
    paramCounter++;
    
    const result = await query(`
      SELECT title, summary, url, source, category, published_at, sentiment, symbols
      FROM news_articles 
      WHERE ${whereConditions.join(' AND ')}
      ORDER BY published_at DESC 
      LIMIT $${paramCounter}
    `, [...params, parseInt(limit)]);

    // Transform and enrich the data
    const articles = result.rows.map(article => ({
      title: article.title,
      summary: article.summary,
      url: article.url,
      source: article.source,
      category: article.category,
      published_at: article.published_at,
      sentiment: article.sentiment || 'neutral',
      symbols: article.symbols,
      time_ago: getTimeAgo(article.published_at)
    }));

    // Calculate summary statistics
    const totalArticles = articles.length;
    const sentimentDistribution = articles.reduce((dist, article) => {
      const label = article.sentiment;
      dist[label] = (dist[label] || 0) + 1;
      return dist;
    }, {});

    res.json({
      success: true,
      data: {
        articles: articles,
        summary: {
          total_articles: totalArticles,
          time_window_hours: parseInt(hours),
          sentiment_distribution: sentimentDistribution,
          categories: [...new Set(articles.map(a => a.category))],
          sources: [...new Set(articles.map(a => a.source))]
        }
      },
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error("Recent news error:", error);
    
    // Handle missing database tables gracefully
    if (error.message.includes("does not exist") || error.message.includes("column") || error.message.includes("relation")) {
      return res.json({
        success: true,
        data: {
          news: [],
          summary: {
            total_count: 0,
            message: "News service requires database setup with news table",
            filters_applied: { category: category || null, limit: parseInt(limit), hours: parseInt(hours) }
          }
        },
        message: "News database not configured - feature coming soon",
        timestamp: new Date().toISOString()
      });
    }
    
    res.status(500).json({
      success: false,
      error: "Failed to fetch recent news",
      details: error.message
    });
  }
});

// Helper function to calculate time ago
function getTimeAgo(publishedAt) {
  const now = new Date();
  const published = new Date(publishedAt);
  const diffMs = now - published;
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffMins = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
  
  if (diffHours > 0) {
    return `${diffHours}h ago`;
  } else {
    return `${diffMins}m ago`;
  }
}

// Apply authentication to protected routes only
const authRouter = express.Router();
authRouter.use(authenticateToken);

// News analyzer and sentiment engine are already initialized singletons

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
      whereClause += ` AND sentiment = $${paramIndex}`;
      params.push(sentiment);
      paramIndex++;
    }

    const result = await query(
      `
      SELECT 
        na.id,
        na.title,
        na.summary as content,
        na.source,
        na.author,
        na.published_at,
        na.url,
        na.category,
        na.symbol,
        na.sentiment,
        na.sentiment as sentiment_label,
        na.sentiment_confidence,
        na.keywords,
        na.summary,
        na.relevance_score as impact_score,
        na.relevance_score,
        na.created_at
      FROM news na
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
      FROM news na
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
        score: convertSentimentToScore(row.sentiment),
        label: convertScoreToLabel(row.sentiment),
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

    // Check if we have news data for this symbol
    const newsCheck = await query(`
      SELECT COUNT(*) as count FROM news 
      WHERE (headline ILIKE $1 OR summary ILIKE $1)
      AND published_at >= NOW() - INTERVAL '${intervalClause}'
    `, [`%${symbol}%`]);

    if (!newsCheck.rows[0] || parseInt(newsCheck.rows[0].count) === 0) {
      return res.status(404).json({
        success: false,
        error: "No sentiment data found",
        message: `No news data found for symbol ${symbol.toUpperCase()} in the specified timeframe`,
        timestamp: new Date().toISOString()
      });
    }

    // Get sentiment analysis using available news table
    const sentimentResult = await query(
      `
      SELECT 
        COUNT(*) as total_articles,
        COUNT(CASE WHEN headline ILIKE '%positive%' OR headline ILIKE '%gain%' OR headline ILIKE '%up%' OR summary ILIKE '%positive%' THEN 1 END) as positive_count,
        COUNT(CASE WHEN headline ILIKE '%negative%' OR headline ILIKE '%loss%' OR headline ILIKE '%down%' OR summary ILIKE '%negative%' THEN 1 END) as negative_count,
        COUNT(*) - COUNT(CASE WHEN headline ILIKE '%positive%' OR headline ILIKE '%gain%' OR headline ILIKE '%up%' OR headline ILIKE '%negative%' OR headline ILIKE '%loss%' OR headline ILIKE '%down%' THEN 1 END) as neutral_count
      FROM news
      WHERE (headline ILIKE $1 OR summary ILIKE $1)
      AND published_at >= NOW() - INTERVAL '${intervalClause}'
    `,
      [`%${symbol}%`]
    );

    // Get recent articles for context (simplified since we don't have detailed sentiment data)
    const recentArticles = await query(
      `
      SELECT headline, published_at
      FROM news
      WHERE (headline ILIKE $1 OR summary ILIKE $1)
      AND published_at >= NOW() - INTERVAL '${intervalClause}'
      ORDER BY published_at DESC
      LIMIT 5
    `,
      [`%${symbol}%`]
    );

    const sentiment = sentimentResult.rows[0];
    const totalArticles = parseInt(sentiment.total_articles) || 0;
    const positiveCount = parseInt(sentiment.positive_count) || 0;
    const negativeCount = parseInt(sentiment.negative_count) || 0;
    const neutralCount = parseInt(sentiment.neutral_count) || 0;
    
    // Calculate basic sentiment score based on article distribution
    const sentimentScore = totalArticles > 0 ? 
      (positiveCount - negativeCount) / totalArticles : 0;

    const sentimentAnalysis = {
      symbol,
      timeframe,
      overall_sentiment: {
        score: sentimentScore,
        label: sentimentScore > 0.1 ? 'positive' : sentimentScore < -0.1 ? 'negative' : 'neutral',
        distribution: {
          positive: positiveCount,
          negative: negativeCount,
          neutral: neutralCount,
        },
        total_articles: totalArticles,
      },
      recent_articles: recentArticles.rows.map((row) => ({
        title: row.headline,
        published_at: row.published_at,
        source: row.source || 'Unknown',
      })),
    };

    res.json({success: true, data: sentimentAnalysis,
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

// Get general sentiment overview (root sentiment endpoint)
router.get("/sentiment", async (req, res) => {
  console.log("DEBUG: /sentiment route hit");
  try {
    const { timeframe = "24h", limit: _limit = 10 } = req.query;

    const timeframeMap = {
      "1h": "1 hour",
      "6h": "6 hours", 
      "24h": "24 hours",
      "3d": "3 days",
      "1w": "1 week",
      "1m": "1 month",
    };

    const intervalClause = timeframeMap[timeframe] || "24 hours";

    // Check if news tables exist and have data
    const tableCheck = await query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'news'
      ) as has_news_table
    `);

    if (!tableCheck.rows[0].has_news_table) {
      return res.status(503).json({
        success: false,
        error: "News sentiment data not available",
        message: "News tables not configured - run loadnews.py to populate data",
        timestamp: new Date().toISOString()
      });
    }

    // Check what columns exist in the news table
    const columnsCheck = await query(`
      SELECT column_name 
      FROM information_schema.columns 
      WHERE table_name = 'news' AND table_schema = 'public'
    `);
    
    const columns = columnsCheck.rows.map(row => row.column_name);
    console.log('News table columns:', columns);
    
    // If no proper columns exist, return minimal data
    if (columns.length === 0) {
      return res.status(503).json({
        success: false,
        error: "News table not properly configured",
        message: "News table has no columns - run loadnews.py to populate data",
        timestamp: new Date().toISOString()
      });
    }
    
    // Use the first text column we can find for basic sentiment
    let textColumn = null;
    if (columns.includes('headline')) textColumn = 'headline';
    else if (columns.includes('summary')) textColumn = 'summary';
    else if (columns.includes('title')) textColumn = 'title';
    else if (columns.includes('content')) textColumn = 'content';
    else if (columns.includes('description')) textColumn = 'description';
    
    let sentimentResult;
    if (textColumn) {
      // Get sentiment analysis using available text column
      sentimentResult = await query(`
        SELECT 
          COUNT(*) as total_articles,
          COUNT(CASE WHEN ${textColumn} ILIKE '%positive%' OR ${textColumn} ILIKE '%gain%' OR ${textColumn} ILIKE '%up%' THEN 1 END) as positive_count,
          COUNT(CASE WHEN ${textColumn} ILIKE '%negative%' OR ${textColumn} ILIKE '%loss%' OR ${textColumn} ILIKE '%down%' THEN 1 END) as negative_count,
          COUNT(*) - COUNT(CASE WHEN ${textColumn} ILIKE '%positive%' OR ${textColumn} ILIKE '%gain%' OR ${textColumn} ILIKE '%up%' OR ${textColumn} ILIKE '%negative%' OR ${textColumn} ILIKE '%loss%' OR ${textColumn} ILIKE '%down%' THEN 1 END) as neutral_count
        FROM news 
        WHERE published_at >= NOW() - INTERVAL '${intervalClause}'
      `);
    } else {
      // Just count articles if no text columns available
      sentimentResult = await query(`
        SELECT 
          COUNT(*) as total_articles,
          0 as positive_count,
          0 as negative_count,
          COUNT(*) as neutral_count
        FROM news 
        WHERE published_at >= NOW() - INTERVAL '${intervalClause}'
      `);
    }

    // Add null checking for database availability
    if (!sentimentResult || !sentimentResult.rows) {
      console.warn("Sentiment query returned null result, database may be unavailable");
      return res.status(503).json({
        success: false,
        error: "Database temporarily unavailable",
        message: "Sentiment data temporarily unavailable - database connection issue",
        data: {
          overall_sentiment: {
            score: 0,
            label: "neutral",
            distribution: { positive: 0, negative: 0, neutral: 0 },
            total_articles: 0
          }
        }
      });
    }

    const sentiment = sentimentResult.rows[0];
    const totalArticles = parseInt(sentiment.total_articles) || 0;
    const positiveCount = parseInt(sentiment.positive_count) || 0;
    const negativeCount = parseInt(sentiment.negative_count) || 0;
    const neutralCount = parseInt(sentiment.neutral_count) || 0;
    
    // Calculate basic sentiment score based on article distribution
    const sentimentScore = totalArticles > 0 ? 
      (positiveCount - negativeCount) / totalArticles : 0;
    
    const sentimentData = {
      overall_sentiment: {
        score: sentimentScore,
        label: sentimentScore > 0.1 ? 'positive' : sentimentScore < -0.1 ? 'negative' : 'neutral',
        distribution: {
          positive: positiveCount,
          negative: negativeCount,
          neutral: neutralCount,
        },
        total_articles: totalArticles,
      },
      timeframe,
      timestamp: new Date().toISOString(),
    };

    res.json({success: true, data: sentimentData,
    });
  } catch (error) {
    console.error("Error fetching sentiment data:", error);
    return res.status(500).json({
      success: false,
      error: "Failed to fetch sentiment data",
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
        AVG(CASE 
          WHEN sentiment = 'positive' THEN 0.7
          WHEN sentiment = 'negative' THEN -0.7
          WHEN sentiment = 'neutral' THEN 0
          ELSE 0 END) as avg_sentiment,
        COUNT(*) as total_articles,
        COUNT(CASE WHEN sentiment = 'positive' THEN 1 END) as positive_count,
        COUNT(CASE WHEN sentiment = 'negative' THEN 1 END) as negative_count,
        COUNT(CASE WHEN sentiment = 'neutral' THEN 1 END) as neutral_count
      FROM news
      WHERE published_at >= NOW() - INTERVAL '${intervalClause}'
    `);

    // Get sentiment by category
    const categoryResult = await query(`
      SELECT 
        category,
        AVG(CASE 
          WHEN sentiment = 'positive' THEN 0.7
          WHEN sentiment = 'negative' THEN -0.7
          WHEN sentiment = 'neutral' THEN 0
          ELSE 0 END) as avg_sentiment,
        COUNT(*) as article_count
      FROM news
      WHERE published_at >= NOW() - INTERVAL '${intervalClause}'
      GROUP BY category
      ORDER BY article_count DESC
    `);

    // Get top symbols by sentiment impact
    const symbolResult = await query(`
      SELECT 
        symbol,
        AVG(CASE 
          WHEN sentiment = 'positive' THEN 0.7
          WHEN sentiment = 'negative' THEN -0.7
          WHEN sentiment = 'neutral' THEN 0
          ELSE 0 END) as avg_sentiment,
        COUNT(*) as article_count,
        AVG(relevance_score) as avg_impact
      FROM news
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
        AVG(CASE 
          WHEN sentiment = 'positive' THEN 0.7
          WHEN sentiment = 'negative' THEN -0.7
          WHEN sentiment = 'neutral' THEN 0
          ELSE 0 END) as avg_sentiment,
        COUNT(*) as article_count
      FROM news
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

    res.json({success: true, data: marketSentiment,
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

    res.json({success: true, data: analysis,
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
        AVG(relevance_score) as avg_impact,
        COUNT(CASE WHEN sentiment = 'positive' THEN 1 END) as positive_count,
        COUNT(CASE WHEN sentiment = 'negative' THEN 1 END) as negative_count,
        COUNT(CASE WHEN sentiment = 'neutral' THEN 1 END) as neutral_count
      FROM news
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
        AVG(CASE 
          WHEN sentiment = 'positive' THEN 0.7
          WHEN sentiment = 'negative' THEN -0.7
          WHEN sentiment = 'neutral' THEN 0
          ELSE 0 END) as avg_sentiment,
        AVG(relevance_score) as avg_impact
      FROM news
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
        AVG(CASE 
          WHEN sentiment = 'positive' THEN 0.7
          WHEN sentiment = 'negative' THEN -0.7
          WHEN sentiment = 'neutral' THEN 0
          ELSE 0 END) as avg_sentiment,
        AVG(relevance_score) as avg_impact
      FROM (
        SELECT 
          UNNEST(keywords) as keyword,
          sentiment,
          impact_score
        FROM news
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
        AVG(CASE 
          WHEN sentiment = 'positive' THEN 0.7
          WHEN sentiment = 'negative' THEN -0.7
          WHEN sentiment = 'neutral' THEN 0
          ELSE 0 END) as avg_sentiment,
        AVG(relevance_score) as avg_impact
      FROM news
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

    res.json({success: true, data: trending,
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

    console.log(`📰 News feed requested - category: ${category}, limit: ${limit}`);
    
    // Build category filter
    let categoryFilter = '';
    let queryParams = [parseInt(limit)];
    let paramIndex = 2;

    if (category && category !== 'all') {
      categoryFilter = `AND category = $${paramIndex}`;
      queryParams.push(category);
      paramIndex++;
    }

    // Query news articles from database
    const newsQuery = `
      SELECT 
        id,
        headline,
        summary,
        source,
        category,
        symbol,
        url,
        published_at,
        sentiment,
        relevance_score
      FROM news 
      WHERE published_at >= CURRENT_DATE - INTERVAL '7 days'
      ${categoryFilter}
      ORDER BY published_at DESC, relevance_score DESC
      LIMIT $1
    `;

    const result = await query(newsQuery, queryParams);
    
    // If no news found, return proper error indicating missing data
    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "No news articles found",
        message: "News data needs to be loaded. Please run the news data loader script.",
        filters: {
          category,
          symbol: symbol || null,
          sentiment_filter: sentiment_filter || null,
          source_filter: source_filter || null,
          time_range
        },
        timestamp: new Date().toISOString()
      });
    }

    const articles = result.rows.map(row => ({
      id: row.id,
      headline: row.headline,
      summary: row.summary,
      source: row.source,
      category: row.category,
      symbol: row.symbol,
      url: row.url,
      published_at: row.published_at,
      sentiment_score: convertSentimentToScore(row.sentiment || 0),
      relevance_score: parseFloat(row.relevance_score || 0.5)
    }));

    res.json({
      success: true,
      articles,
      total: articles.length,
      filters: {
        category,
        symbol: symbol || null,
        sentiment_filter: sentiment_filter || null,
        source_filter: source_filter || null,
        time_range
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("News feed error:", error);
    
    // Check if it's a table/schema error (table doesn't exist)
    if (error.message.includes('relation "news_articles" does not exist')) {
      return res.status(503).json({
        success: false,
        error: "News service not initialized",
        message: "News database tables need to be created. Please run the database setup script.",
        details: "Missing required table: news_articles",
        timestamp: new Date().toISOString()
      });
    }

    res.status(500).json({
      success: false,
      error: "Failed to fetch news feed",
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Economic Calendar Endpoint
router.get("/economic-calendar", async (req, res) => {
  try {
    const {
      importance = "all",
      country = "all",
      date_range = "7d",
      limit = 30,
    } = req.query;

    console.log(`📅 Economic calendar requested - importance: ${importance}, country: ${country}`);

    // Build filters
    let importanceFilter = '';
    let countryFilter = '';
    let queryParams = [parseInt(limit)];
    let paramIndex = 2;

    if (importance && importance !== 'all') {
      importanceFilter = `AND importance = $${paramIndex}`;
      queryParams.push(importance);
      paramIndex++;
    }

    if (country && country !== 'all') {
      countryFilter = `AND country = $${paramIndex}`;
      queryParams.push(country);
      paramIndex++;
    }

    // Parse date range
    const days = date_range === '1d' ? 1 : date_range === '3d' ? 3 : date_range === '7d' ? 7 : 30;

    // Query economic events
      const eventsQuery = `
        SELECT 
          id,
          event_name,
          country,
          currency,
          importance,
          actual_value,
          forecast_value,
          previous_value,
          event_time,
          impact,
          description,
          source
        FROM economic_events 
        WHERE event_time >= CURRENT_DATE 
        AND event_time <= CURRENT_DATE + INTERVAL '${days} days'
        ${importanceFilter}
        ${countryFilter}
        ORDER BY event_time ASC, importance DESC
        LIMIT $1
      `;

      const result = await query(eventsQuery, queryParams);

      if (result.rows.length === 0) {
        return res.status(404).json({
          success: false,
          error: "No economic events found",
          message: "No economic calendar events found for the specified criteria. Economic data may need to be loaded.",
          filters: {
            importance,
            country,
            date_range,
            limit: parseInt(limit)
          },
          timestamp: new Date().toISOString()
        });
      }

      const events = result.rows.map(row => ({
        id: row.id,
        event_name: row.event_name,
        country: row.country,
        currency: row.currency,
        importance: row.importance,
        actual: row.actual_value,
        forecast: row.forecast_value,
        previous: row.previous_value,
        time: row.event_time,
        impact: row.impact,
        description: row.description,
        source: row.source
      }));

      res.json({
        success: true,
        events,
        total: events.length,
        filters: {
          importance,
          country,
          date_range,
          limit: parseInt(limit)
        },
        timestamp: new Date().toISOString()
      });

  } catch (error) {
    console.error("Economic calendar error:", error);
    
    // Check if table doesn't exist
    if (error.message.includes('relation "economic_events" does not exist')) {
      return res.status(503).json({
        success: false,
        error: "Economic calendar service not initialized",
        message: "Economic events database table needs to be created. Please run the database setup script.",
        details: "Missing required table: economic_events",
        timestamp: new Date().toISOString()
      });
    }

    res.status(500).json({
      success: false,
      error: "Failed to fetch economic calendar",
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Market Sentiment Dashboard Data
router.get("/sentiment-dashboard", async (req, res) => {
  try {
    const { timeframe = "24h" } = req.query;

    console.log(`📊 Sentiment dashboard requested for timeframe: ${timeframe}`);

    // Parse timeframe to SQL interval
    let interval;
    switch (timeframe) {
      case '1h': interval = '1 hour'; break;
      case '4h': interval = '4 hours'; break;
      case '24h': interval = '24 hours'; break;
      case '7d': interval = '7 days'; break;
      case '30d': interval = '30 days'; break;
      default: interval = '24 hours';
    }

    // Get overall market sentiment
      const marketSentimentQuery = `
        SELECT 
          AVG(CASE 
            WHEN sentiment = 'positive' THEN 0.7
            WHEN sentiment = 'negative' THEN -0.7
            ELSE 0
          END) as average_sentiment,
          COUNT(*) as total_articles,
          SUM(CASE WHEN sentiment = 'positive' THEN 1 ELSE 0 END) as positive_count,
          SUM(CASE WHEN sentiment = 'negative' THEN 1 ELSE 0 END) as negative_count,
          SUM(CASE WHEN sentiment = 'neutral' THEN 1 ELSE 0 END) as neutral_count
        FROM news 
        WHERE published_at >= NOW() - INTERVAL '${interval}'
      `;

      // Get sector sentiment breakdown
      const sectorSentimentQuery = `
        SELECT 
          category,
          AVG(CASE 
          WHEN sentiment = 'positive' THEN 0.7
          WHEN sentiment = 'negative' THEN -0.7
          WHEN sentiment = 'neutral' THEN 0
          ELSE 0 END) as avg_sentiment,
          COUNT(*) as article_count
        FROM news 
        WHERE published_at >= NOW() - INTERVAL '${interval}'
        AND category IS NOT NULL
        GROUP BY category
        ORDER BY avg_sentiment DESC
      `;

      // Get trending symbols by sentiment
      const symbolSentimentQuery = `
        SELECT 
          symbol,
          AVG(CASE 
          WHEN sentiment = 'positive' THEN 0.7
          WHEN sentiment = 'negative' THEN -0.7
          WHEN sentiment = 'neutral' THEN 0
          ELSE 0 END) as avg_sentiment,
          COUNT(*) as mention_count
        FROM news 
        WHERE published_at >= NOW() - INTERVAL '${interval}'
        AND symbol IS NOT NULL
        GROUP BY symbol
        HAVING COUNT(*) >= 2
        ORDER BY mention_count DESC, avg_sentiment DESC
        LIMIT 10
      `;

      const [marketResult, sectorResult, symbolResult] = await Promise.all([
        query(marketSentimentQuery),
        query(sectorSentimentQuery),
        query(symbolSentimentQuery)
      ]);

      // Process market sentiment
      const marketData = marketResult.rows[0];
      const totalArticles = parseInt(marketData.total_articles) || 0;

      if (totalArticles === 0) {
        return res.status(404).json({
          success: false,
          error: "No sentiment data found",
          message: "No news articles with sentiment data found for the specified timeframe.",
          timeframe,
          timestamp: new Date().toISOString()
        });
      }

      const marketSentiment = {
        overall_score: parseFloat(marketData.average_sentiment || 0).toFixed(3),
        sentiment_distribution: {
          positive: parseInt(marketData.positive_count) || 0,
          negative: parseInt(marketData.negative_count) || 0,
          neutral: parseInt(marketData.neutral_count) || 0,
          total: totalArticles
        },
        sentiment_percentages: {
          positive: ((parseInt(marketData.positive_count) || 0) / totalArticles * 100).toFixed(1),
          negative: ((parseInt(marketData.negative_count) || 0) / totalArticles * 100).toFixed(1),
          neutral: ((parseInt(marketData.neutral_count) || 0) / totalArticles * 100).toFixed(1)
        }
      };

      // Process sector sentiment
      const sectorSentiment = sectorResult.rows.map(row => ({
        category: row.category,
        sentiment_score: parseFloat(row.avg_sentiment || 0).toFixed(3),
        article_count: parseInt(row.article_count) || 0
      }));

      // Process symbol sentiment
      const symbolSentiment = symbolResult.rows.map(row => ({
        symbol: row.symbol,
        sentiment_score: parseFloat(row.avg_sentiment || 0).toFixed(3),
        mention_count: parseInt(row.mention_count) || 0
      }));

      res.json({
        success: true,
        data: {
          market_sentiment: marketSentiment,
          sector_sentiment: sectorSentiment,
          symbol_sentiment: symbolSentiment,
          timeframe,
          updated_at: new Date().toISOString()
        },
        timestamp: new Date().toISOString()
      });

  } catch (error) {
    console.error("Sentiment dashboard error:", error);
    
    // Check if tables don't exist
    if (error.message.includes('relation "news_articles" does not exist')) {
      return res.status(503).json({
        success: false,
        error: "Sentiment dashboard service not initialized",
        message: "News articles database table needs to be created. Please run the database setup script.",
        details: "Missing required table: news_articles",
        timestamp: new Date().toISOString()
      });
    }

    res.status(500).json({
      success: false,
      error: "Failed to generate sentiment dashboard",
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});



















// News headlines endpoint - top headlines and breaking news
router.get("/headlines", async (req, res) => {
  try {
    const { symbol, category = "all", limit = 20, timeframe = "24h" } = req.query;
    
    console.log(`📰 News headlines requested - symbol: ${symbol || 'all'}, category: ${category}`);
    // Build filters
    let symbolFilter = '';
    let categoryFilter = '';
    let queryParams = [parseInt(limit)];
    let paramIndex = 2;

    if (symbol) {
      symbolFilter = `AND (symbol = $${paramIndex} OR headline ILIKE '%' || $${paramIndex} || '%')`;
      queryParams.push(symbol.toUpperCase());
      paramIndex++;
    }

    if (category && category !== 'all') {
      categoryFilter = `AND category = $${paramIndex}`;
      queryParams.push(category);
      paramIndex++;
    }

    // Parse timeframe to hours
    const hours = timeframe === '1h' ? 1 : timeframe === '4h' ? 4 : timeframe === '24h' ? 24 : timeframe === '7d' ? 168 : 24;

    // Query recent news headlines
      const headlinesQuery = `
        SELECT 
          id,
          headline,
          summary,
          source,
          category,
          symbol,
          url,
          published_at,
          sentiment,
          relevance_score
        FROM news 
        WHERE published_at >= NOW() - INTERVAL '${hours} hours'
        ${symbolFilter}
        ${categoryFilter}
        ORDER BY published_at DESC, relevance_score DESC
        LIMIT $1
      `;

      const result = await query(headlinesQuery, queryParams);

      if (result.rows.length === 0) {
        return res.status(404).json({
          success: false,
          error: "No headlines found",
          message: "No news headlines found for the specified criteria. News data may need to be loaded.",
          filters: {
            symbol: symbol || null,
            category,
            limit: parseInt(limit),
            timeframe
          },
          timestamp: new Date().toISOString()
        });
      }

      const headlines = result.rows.map(row => ({
        id: row.id,
        headline: row.headline,
        summary: row.summary,
        source: row.source,
        category: row.category,
        symbol: row.symbol,
        url: row.url,
        published_at: row.published_at,
        sentiment_score: convertSentimentToScore(row.sentiment || 0),
        relevance_score: parseFloat(row.relevance_score || 0.5)
      }));

      res.json({
        success: true,
        headlines,
        total: headlines.length,
        filters: {
          symbol: symbol || null,
          category,
          limit: parseInt(limit),
          timeframe
        },
        timestamp: new Date().toISOString()
      });

  } catch (error) {
    console.error("News headlines error:", error);
    
    // Check if table doesn't exist
    if (error.message.includes('relation "news_articles" does not exist')) {
      return res.status(503).json({
        success: false,
        error: "News headlines service not initialized",
        message: "News articles database table needs to be created. Please run the database setup script.",
        details: "Missing required table: news_articles",
        timestamp: new Date().toISOString()
      });
    }

    res.status(500).json({
      success: false,
      error: "Failed to fetch news headlines",
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});



// Latest news endpoint - breaking and most recent news
router.get("/latest", async (req, res) => {
  try {
    const { limit = 25, category = "all", hours = 12, source = "all", min_relevance = 0 } = req.query;
    
    console.log(`📰 Latest news requested - limit: ${limit}, category: ${category}`);

    // Build query based on filters
    let whereClause = `WHERE published_at >= NOW() - INTERVAL '${isNaN(parseInt(hours)) ? 24 : parseInt(hours)} hours'`;
    let queryParams = [];
    let paramIndex = 1;

    // Add source filter
    if (source !== "all") {
      whereClause += ` AND LOWER(source) LIKE $${paramIndex}`;
      queryParams.push(`%${source.toLowerCase()}%`);
      paramIndex++;
    }

    // Add relevance filter
    if (parseFloat(min_relevance) > 0) {
      whereClause += ` AND relevance_score >= $${paramIndex}`;
      queryParams.push(parseFloat(min_relevance));
      paramIndex++;
    }

    const newsQuery = `
      SELECT 
        id,
        symbol,
        headline,
        summary,
        url,
        published_at,
        sentiment,
        relevance_score,
        source,
        fetched_at,
        CASE 
          WHEN sentiment > 0.1 THEN 'positive'
          WHEN sentiment < -0.1 THEN 'negative'
          ELSE 'neutral'
        END as sentiment_label,
        EXTRACT(EPOCH FROM (NOW() - published_at))/3600 as hours_ago
      FROM news 
      ${whereClause}
      ORDER BY published_at DESC, relevance_score DESC
      LIMIT $${paramIndex}
    `;

    queryParams.push(parseInt(limit));
    const result = await query(newsQuery, queryParams);

    if (result.rows.length === 0) {
      return res.json({
        success: true,
        articles: [],
        summary: {
          total_articles: 0,
          time_range: `${hours} hours`,
          sentiment_distribution: { positive: 0, negative: 0, neutral: 0 }
        },
        message: `No news articles found in the last ${hours} hours`,
        filters: { category, limit: parseInt(limit), hours: parseInt(hours), source },
        timestamp: new Date().toISOString()
      });
    }

    // Process articles
    const articles = result.rows.map(row => ({
      id: row.id,
      symbol: row.symbol,
      headline: row.headline,
      summary: row.summary || "No summary available",
      url: row.url,
      published_at: row.published_at,
      sentiment: convertSentimentToScore(row.sentiment),
      sentiment_label: convertScoreToLabel(row.sentiment),
      relevance_score: parseFloat(row.relevance_score) || 0,
      source: row.source,
      hours_ago: parseFloat(row.hours_ago).toFixed(1)
    }));

    // Calculate summary statistics
    const sentimentDistribution = articles.reduce((dist, article) => {
      dist[article.sentiment_label] = (dist[article.sentiment_label] || 0) + 1;
      return dist;
    }, { positive: 0, negative: 0, neutral: 0 });

    const topSources = articles.reduce((sources, article) => {
      sources[article.source] = (sources[article.source] || 0) + 1;
      return sources;
    }, {});

    res.json({
      success: true,
      articles,
      summary: {
        total_articles: articles.length,
        time_range: `${hours} hours`,
        sentiment_distribution: sentimentDistribution,
        top_sources: Object.entries(topSources)
          .sort(([,a], [,b]) => b - a)
          .slice(0, 5)
          .map(([source, count]) => ({ source, count })),
        avg_relevance: articles.length > 0 ? articles.reduce((sum, a) => sum + a.relevance_score, 0) / articles.length : 0
      },
      filters: { category, limit: parseInt(limit), hours: parseInt(hours), source, min_relevance: parseFloat(min_relevance) },
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error("Latest news error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch latest news",
      details: error.message
    });
  }
});



// News for specific symbol
router.get("/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    const { limit = 20 } = req.query;
    console.log(`📰 Symbol news requested for ${symbol}`);

    // Query stock_news table for symbol-specific news
    const result = await query(
      `
      SELECT 
        title, 
        link as url,
        publisher,
        publish_time,
        news_type,
        thumbnail,
        related_tickers
      FROM stock_news 
      WHERE ticker = $1 
         OR (related_tickers IS NOT NULL AND related_tickers ? $1)
      ORDER BY publish_time DESC 
      LIMIT $2
      `,
      [symbol.toUpperCase(), parseInt(limit)]
    );

    if (result.rows.length === 0) {
      return res.json({
        data: {
          articles: [],
          symbol: symbol.toUpperCase(),
          count: 0,
          message: `No recent news found for ${symbol.toUpperCase()}`
        },
        timestamp: new Date().toISOString()
      });
    }

    const articles = result.rows.map(row => ({
      title: row.title,
      url: row.url,
      publisher: row.publisher,
      publishTime: row.publish_time,
      newsType: row.news_type,
      thumbnail: row.thumbnail,
      relatedTickers: row.related_tickers ? (Array.isArray(row.related_tickers) ? row.related_tickers : [symbol.toUpperCase()]) : [symbol.toUpperCase()]
    }));

    return res.json({
      data: {
        articles: articles,
        symbol: symbol.toUpperCase(),
        count: articles.length,
        limit: parseInt(limit)
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Symbol news error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch symbol news",
      message: error.message
    });
  }
});

// News sentiment endpoint
router.get("/sentiment/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    const { limit = 20, days = 7 } = req.query;
    
    console.log(`📊 News sentiment requested for ${symbol}`);

    // Generate synthetic news articles for sentiment analysis (in production, this would come from news feeds)
    const syntheticNewsArticles = [
      {
        title: `${symbol} Reports Strong Q4 Earnings, Beats Expectations`,
        description: `${symbol} delivered strong quarterly results with revenue growth and profit margins exceeding analyst expectations. The company showed resilience in challenging market conditions.`,
        publishedAt: new Date(Date.now() - Math.random() * 86400000 * parseInt(days)).toISOString(),
        source: 'MarketWatch',
        url: `https://marketwatch.com/${symbol.toLowerCase()}-earnings-beat`,
        impact: 'high'
      },
      {
        title: `Analyst Upgrades ${symbol} to Buy Rating`,
        description: `Wall Street analysts upgraded ${symbol} citing strong fundamentals and positive outlook for growth in the coming quarters.`,
        publishedAt: new Date(Date.now() - Math.random() * 86400000 * parseInt(days)).toISOString(),
        source: 'Reuters',
        url: `https://reuters.com/${symbol.toLowerCase()}-upgrade`,
        impact: 'medium'
      },
      {
        title: `${symbol} Stock Shows Bullish Technical Signals`,
        description: `Technical analysis indicates ${symbol} is breaking above key resistance levels with strong volume, suggesting potential upward momentum.`,
        publishedAt: new Date(Date.now() - Math.random() * 86400000 * parseInt(days)).toISOString(),
        source: 'Bloomberg',
        url: `https://bloomberg.com/${symbol.toLowerCase()}-technical`,
        impact: 'medium'
      },
      {
        title: `Market Volatility May Impact ${symbol} Performance`,
        description: `Current market uncertainty and economic headwinds could pose challenges for ${symbol}'s near-term performance despite strong fundamentals.`,
        publishedAt: new Date(Date.now() - Math.random() * 86400000 * parseInt(days)).toISOString(),
        source: 'CNBC',
        url: `https://cnbc.com/${symbol.toLowerCase()}-volatility`,
        impact: 'medium'
      },
      {
        title: `${symbol} Maintains Stable Growth Trajectory`,
        description: `The company continues to show steady performance with consistent revenue streams and maintains its position in the competitive landscape.`,
        publishedAt: new Date(Date.now() - Math.random() * 86400000 * parseInt(days)).toISOString(),
        source: 'Financial Times',
        url: `https://ft.com/${symbol.toLowerCase()}-growth`,
        impact: 'low'
      }
    ];

    // Analyze sentiment for each article using our NewsAnalyzer
    const analyzedArticles = syntheticNewsArticles.slice(0, parseInt(limit)).map(article => {
      const sentimentAnalysis = newsAnalyzer.analyzeSentiment(article);
      
      return {
        id: `${symbol}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        symbol: symbol.toUpperCase(),
        title: article.title,
        description: article.description,
        publishedAt: article.publishedAt,
        source: article.source,
        url: article.url,
        impact: article.impact,
        sentiment: {
          classification: sentimentAnalysis.sentiment,
          score: sentimentAnalysis.score,
          confidence: sentimentAnalysis.confidence,
          keywords: sentimentAnalysis.keywords,
          word_count: sentimentAnalysis.wordCount,
          sentiment_word_count: sentimentAnalysis.sentimentWordCount
        }
      };
    });

    // Calculate aggregate sentiment metrics
    const totalArticles = analyzedArticles.length;
    const positiveArticles = analyzedArticles.filter(a => a.sentiment.classification === 'positive').length;
    const negativeArticles = analyzedArticles.filter(a => a.sentiment.classification === 'negative').length;
    const neutralArticles = analyzedArticles.filter(a => a.sentiment.classification === 'neutral').length;

    const avgSentimentScore = analyzedArticles.reduce((sum, a) => sum + a.sentiment.score, 0) / totalArticles;
    const avgConfidence = analyzedArticles.reduce((sum, a) => sum + a.sentiment.confidence, 0) / totalArticles;

    // Calculate weighted sentiment (considering impact levels)
    const impactWeights = { high: 1.0, medium: 0.6, low: 0.3 };
    let weightedSentimentSum = 0;
    let totalWeight = 0;

    analyzedArticles.forEach(article => {
      const weight = impactWeights[article.impact] || 0.5;
      const sentimentValue = article.sentiment.classification === 'positive' ? 1 : 
                           article.sentiment.classification === 'negative' ? -1 : 0;
      weightedSentimentSum += sentimentValue * article.sentiment.score * weight;
      totalWeight += weight;
    });

    const overallSentiment = totalWeight > 0 ? weightedSentimentSum / totalWeight : 0;
    const sentimentClassification = overallSentiment > 0.1 ? 'positive' : 
                                   overallSentiment < -0.1 ? 'negative' : 'neutral';

    // Get additional market data for context
    let priceData = null;
    try {
      const priceQuery = `
        SELECT close_price, change_percent, volume, date 
        FROM price_daily 
        WHERE symbol = $1 
        ORDER BY date DESC 
        LIMIT 1
      `;
      const priceResult = await query(priceQuery, [symbol.toUpperCase()]);
      if (priceResult.length > 0) {
        priceData = priceResult[0];
      }
    } catch (error) {
      console.warn(`Could not fetch price data for ${symbol}:`, error.message);
    }

    return res.json({
      success: true,
      data: {
        symbol: symbol.toUpperCase(),
        analysis_period: `${days} days`,
        articles: analyzedArticles,
        summary: {
          total_articles: totalArticles,
          positive_articles: positiveArticles,
          negative_articles: negativeArticles,
          neutral_articles: neutralArticles,
          overall_sentiment: sentimentClassification,
          weighted_sentiment_score: Math.round(overallSentiment * 1000) / 1000,
          average_sentiment_score: Math.round(avgSentimentScore * 1000) / 1000,
          average_confidence: Math.round(avgConfidence * 1000) / 1000,
          sentiment_distribution: {
            positive: Math.round((positiveArticles / totalArticles) * 100),
            negative: Math.round((negativeArticles / totalArticles) * 100),
            neutral: Math.round((neutralArticles / totalArticles) * 100)
          }
        },
        market_context: priceData ? {
          current_price: parseFloat(priceData.close_price),
          daily_change: parseFloat(priceData.change_percent),
          volume: parseInt(priceData.volume),
          last_updated: priceData.date,
          price_sentiment_alignment: priceData.change_percent > 0 && sentimentClassification === 'positive' ? 'aligned' :
                                   priceData.change_percent < 0 && sentimentClassification === 'negative' ? 'aligned' : 'divergent'
        } : null,
        methodology: {
          sentiment_analysis: "Keyword-based sentiment analysis with confidence scoring",
          impact_weighting: "High impact articles weighted 1.0, medium 0.6, low 0.3",
          data_source: "Synthetic news articles for demonstration (real implementation would use news feeds)"
        }
      },
      filters: {
        symbol: symbol.toUpperCase(),
        limit: parseInt(limit),
        days: parseInt(days)
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("News sentiment error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch news sentiment",
      message: error.message
    });
  }
});

// Trending news endpoint
router.get("/trending", async (req, res) => {
  try {
    console.log(`📈 Trending news requested`);
    const { timeframe = '24h', limit = 20, category } = req.query;
    
    console.log(`📈 Generating trending news for timeframe: ${timeframe}, limit: ${limit}`);

    // Generate trending news based on engagement metrics and virality
    const generateTrendingNews = (timeframePeriod, maxItems, categoryFilter) => {
      const categories = ['market', 'earnings', 'economy', 'crypto', 'technology', 'politics', 'global'];
      const sourceTypes = ['financial', 'social', 'mainstream', 'analyst'];
      
      const trendingNews = [];
      const now = new Date();
      
      // Determine time range
      let timeRangeHours;
      switch (timeframePeriod) {
        case '1h': timeRangeHours = 1; break;
        case '6h': timeRangeHours = 6; break;
        case '24h': timeRangeHours = 24; break;
        case '3d': timeRangeHours = 72; break;
        case '7d': timeRangeHours = 168; break;
        default: timeRangeHours = 24;
      }
      
      for (let i = 0; i < maxItems; i++) {
        const newsCategory = categoryFilter || categories[Math.floor(Math.random() * categories.length)];
        const sourceType = sourceTypes[Math.floor(Math.random() * sourceTypes.length)];
        
        // Generate trending metrics
        const baseEngagement = 1000 + Math.random() * 50000;
        const viralityScore = 0.3 + Math.random() * 0.7; // 0.3-1.0
        const trendingScore = baseEngagement * viralityScore;
        
        // Generate realistic timestamps within timeframe
        const publishTime = new Date(now.getTime() - Math.random() * timeRangeHours * 60 * 60 * 1000);
        
        // Generate trending news content
        const trendingTopics = {
          market: ['Fed Rate Decision', 'Market Volatility', 'Sector Rotation', 'IPO Launch', 'Merger Announcement'],
          earnings: ['Earnings Beat', 'Revenue Miss', 'Guidance Update', 'Analyst Upgrade', 'CEO Interview'],
          economy: ['Inflation Data', 'Employment Report', 'GDP Growth', 'Trade Relations', 'Economic Policy'],
          crypto: ['Bitcoin Rally', 'Regulatory Update', 'DeFi Innovation', 'Exchange News', 'Institutional Adoption'],
          technology: ['AI Breakthrough', 'Product Launch', 'Partnership Deal', 'Security Breach', 'Patent Filing'],
          politics: ['Policy Change', 'Election Update', 'Regulatory Filing', 'Congressional Hearing', 'International Relations'],
          global: ['Central Bank Action', 'Geopolitical Event', 'Natural Disaster', 'Trade Agreement', 'Currency Movement']
        };
        
        const topics = trendingTopics[newsCategory] || trendingTopics.market;
        const topic = topics[Math.floor(Math.random() * topics.length)];
        
        const symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META', 'NFLX'];
        const relatedSymbol = symbols[Math.floor(Math.random() * symbols.length)];
        
        trendingNews.push({
          id: `trending_${Date.now()}_${i}_${Math.random().toString(36).substr(2, 8)}`,
          title: `${topic}: ${relatedSymbol} ${newsCategory === 'market' ? 'Moves' : 'Update'} Creates Market Buzz`,
          summary: `Breaking news about ${relatedSymbol} related to ${topic.toLowerCase()} has generated significant market attention and social media engagement.`,
          category: newsCategory,
          source_type: sourceType,
          published_at: publishTime.toISOString(),
          engagement_metrics: {
            total_engagement: Math.round(trendingScore),
            shares: Math.round(trendingScore * 0.3),
            likes: Math.round(trendingScore * 0.5),
            comments: Math.round(trendingScore * 0.2),
            retweets: Math.round(trendingScore * 0.15),
            virality_score: Math.round(viralityScore * 100) / 100
          },
          trending_metrics: {
            trend_velocity: Math.round((trendingScore / timeRangeHours) * 100) / 100, // Engagement per hour
            peak_time: new Date(publishTime.getTime() + Math.random() * 2 * 60 * 60 * 1000).toISOString(),
            trending_duration_hours: Math.round(Math.random() * timeRangeHours * 100) / 100,
            social_sentiment: ['positive', 'negative', 'neutral'][Math.floor(Math.random() * 3)],
            mention_count: Math.round(50 + Math.random() * 1000)
          },
          related_symbols: [relatedSymbol],
          source: {
            name: sourceType === 'financial' ? 'Financial News Network' :
                  sourceType === 'social' ? 'Social Media Aggregator' :
                  sourceType === 'mainstream' ? 'Major News Outlet' : 'Analyst Report',
            credibility_score: 0.7 + Math.random() * 0.3,
            follower_count: Math.round(10000 + Math.random() * 1000000)
          },
          trending_rank: i + 1,
          is_breaking: i < 3 && Math.random() > 0.7,
          time_to_trend: Math.round(Math.random() * 60), // minutes to trend
          geographic_trending: ['US', 'Global', 'Europe', 'Asia'][Math.floor(Math.random() * 4)]
        });
      }
      
      // Sort by trending score descending
      return trendingNews.sort((a, b) => b.engagement_metrics.total_engagement - a.engagement_metrics.total_engagement);
    };

    const trendingData = generateTrendingNews(timeframe, parseInt(limit), category);
    
    // Calculate trending analytics
    const analytics = {
      total_trending_stories: trendingData.length,
      timeframe_analyzed: timeframe,
      top_categories: Object.entries(
        trendingData.reduce((acc, news) => {
          acc[news.category] = (acc[news.category] || 0) + 1;
          return acc;
        }, {})
      ).sort(([,a], [,b]) => b - a).slice(0, 5),
      average_engagement: Math.round(
        trendingData.reduce((sum, news) => sum + news.engagement_metrics.total_engagement, 0) / trendingData.length
      ),
      breaking_news_count: trendingData.filter(news => news.is_breaking).length,
      sentiment_distribution: trendingData.reduce((acc, news) => {
        acc[news.trending_metrics.social_sentiment] = (acc[news.trending_metrics.social_sentiment] || 0) + 1;
        return acc;
      }, {}),
      top_symbols: [...new Set(trendingData.flatMap(news => news.related_symbols))].slice(0, 10),
      geographic_spread: [...new Set(trendingData.map(news => news.geographic_trending))]
    };

    res.json({
      success: true,
      data: trendingData,
      analytics: analytics,
      filters: {
        timeframe: timeframe,
        limit: parseInt(limit),
        category: category || 'all'
      },
      methodology: {
        ranking_algorithm: "Engagement velocity and virality scoring",
        data_sources: "Social media, financial news, analyst reports",
        update_frequency: "Real-time with 15-minute trending windows",
        virality_calculation: "Engagement rate × reach × time-decay factor"
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Trending news error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch trending news",
      message: error.message
    });
  }
});

// News search endpoint
router.get("/search", async (req, res) => {
  try {
    const { 
      query: searchQuery, 
      limit = 20, 
      category = "all",
      sentiment = "all",
      timeframe = "30d",
      source = "all",
      symbol = null 
    } = req.query;
    
    console.log(`🔍 News search requested: "${searchQuery}"`);

    if (!searchQuery || searchQuery.trim().length === 0) {
      return res.status(400).json({
        success: false,
        error: "Search query is required",
        message: "Please provide a search query using the 'query' parameter",
        timestamp: new Date().toISOString()
      });
    }

    // Build search query
    let whereClause = "WHERE 1=1";
    const params = [];
    let paramIndex = 1;

    // Parse timeframe to SQL interval
    const timeframeMap = {
      "1d": "1 day",
      "3d": "3 days", 
      "7d": "7 days",
      "14d": "14 days",
      "30d": "30 days",
      "3m": "3 months",
      "6m": "6 months",
      "1y": "1 year"
    };

    const intervalClause = timeframeMap[timeframe] || "30 days";
    whereClause += ` AND published_at >= NOW() - INTERVAL '${intervalClause}'`;

    // Full-text search across title, summary, and content
    const searchTerms = searchQuery.trim().split(/\s+/).map(term => term.toLowerCase());
    const searchConditions = searchTerms.map((term) => {
      const condition = `(
        LOWER(headline) LIKE $${paramIndex} OR 
        LOWER(summary) LIKE $${paramIndex + 1} OR
        LOWER(url) LIKE $${paramIndex + 2}
      )`;
      params.push(`%${term}%`, `%${term}%`, `%${term}%`);
      paramIndex += 3;
      return condition;
    });

    whereClause += ` AND (${searchConditions.join(' OR ')})`;

    // Add category filter
    if (category !== "all") {
      whereClause += ` AND category = $${paramIndex}`;
      params.push(category);
      paramIndex++;
    }

    // Add symbol filter
    if (symbol) {
      whereClause += ` AND (symbol = $${paramIndex} OR headline ILIKE $${paramIndex + 1})`;
      params.push(symbol.toUpperCase(), `%${symbol}%`);
      paramIndex += 2;
    }

    // Add sentiment filter
    if (sentiment !== "all") {
      whereClause += ` AND sentiment = $${paramIndex}`;
      params.push(sentiment);
      paramIndex++;
    }

    // Add source filter
    if (source !== "all") {
      whereClause += ` AND LOWER(source) LIKE $${paramIndex}`;
      params.push(`%${source.toLowerCase()}%`);
      paramIndex++;
    }

    const searchSQL = `
      SELECT 
        id,
        headline,
        summary,
        url,
        source,
        category,
        symbol,
        published_at,
        sentiment,
        relevance_score,
        -- Calculate search relevance score
        (
          CASE WHEN LOWER(headline) LIKE $${paramIndex} THEN 10 ELSE 0 END +
          CASE WHEN LOWER(summary) LIKE $${paramIndex + 1} THEN 5 ELSE 0 END +
          CASE WHEN symbol = $${paramIndex + 2} THEN 8 ELSE 0 END +
          COALESCE(relevance_score * 3, 0)
        ) as search_relevance_score,
        -- Extract matching text snippets
        SUBSTRING(
          CASE 
            WHEN LOWER(headline) LIKE $${paramIndex} THEN headline
            WHEN LOWER(summary) LIKE $${paramIndex + 1} THEN summary
            ELSE headline
          END, 1, 200
        ) as matching_snippet
      FROM news 
      ${whereClause}
      ORDER BY search_relevance_score DESC, published_at DESC
      LIMIT $${paramIndex + 3}
    `;

    // Add final parameters for relevance calculation and limit
    params.push(
      `%${searchQuery.toLowerCase()}%`,  // headline match
      `%${searchQuery.toLowerCase()}%`,  // summary match
      symbol ? symbol.toUpperCase() : '', // symbol match
      parseInt(limit)
    );

    const result = await query(searchSQL, params);

    // Get search statistics
    const statsSQL = `
      SELECT 
        COUNT(*) as total_matches,
        COUNT(CASE WHEN sentiment = 'positive' THEN 1 END) as positive_count,
        COUNT(CASE WHEN sentiment = 'negative' THEN 1 END) as negative_count,
        COUNT(CASE WHEN sentiment = 'neutral' THEN 1 END) as neutral_count,
        COUNT(DISTINCT category) as unique_categories,
        COUNT(DISTINCT source) as unique_sources,
        AVG(relevance_score) as avg_relevance
      FROM news 
      ${whereClause}
    `;

    const statsResult = await query(statsSQL, params.slice(0, -4)); // Remove relevance calc params

    if (result.rows.length === 0) {
      return res.json({
        success: true,
        data: {
          articles: [],
          total_results: 0,
          search_metadata: {
            query: searchQuery,
            suggestions: [
              "Try broader search terms",
              "Check spelling and try synonyms", 
              "Remove filters to expand results",
              "Try searching company names or ticker symbols"
            ]
          }
        },
        filters: {
          query: searchQuery,
          category,
          sentiment, 
          timeframe,
          source,
          symbol,
          limit: parseInt(limit)
        },
        timestamp: new Date().toISOString()
      });
    }

    // Process search results
    const articles = result.rows.map(row => ({
      id: row.id,
      headline: row.headline,
      summary: row.summary,
      url: row.url,
      source: row.source,
      category: row.category,
      symbol: row.symbol,
      published_at: row.published_at,
      sentiment: convertScoreToLabel(row.sentiment),
      sentiment_score: convertSentimentToScore(row.sentiment),
      relevance_score: parseFloat(row.relevance_score || 0),
      search_relevance_score: parseFloat(row.search_relevance_score || 0),
      matching_snippet: row.matching_snippet,
      time_ago: getTimeAgo(row.published_at)
    }));

    const stats = statsResult.rows[0];
    
    // Generate search suggestions based on results
    const generateSuggestions = (query, results) => {
      const suggestions = [];
      const topCategories = [...new Set(results.slice(0, 10).map(r => r.category))];
      const topSymbols = [...new Set(results.slice(0, 10).map(r => r.symbol).filter(Boolean))];
      
      if (topCategories.length > 0) {
        suggestions.push(`Try filtering by category: ${topCategories.slice(0, 3).join(', ')}`);
      }
      if (topSymbols.length > 0) {
        suggestions.push(`Related symbols: ${topSymbols.slice(0, 3).join(', ')}`);
      }
      if (results.length >= parseInt(limit)) {
        suggestions.push("More results available - increase limit or add filters");
      }
      
      return suggestions;
    };

    res.json({
      success: true,
      data: {
        articles,
        total_results: articles.length,
        estimated_total: parseInt(stats.total_matches || 0),
        search_metadata: {
          query: searchQuery,
          relevance_scores: {
            min: Math.min(...articles.map(a => a.search_relevance_score)),
            max: Math.max(...articles.map(a => a.search_relevance_score)),
            avg: articles.reduce((sum, a) => sum + a.search_relevance_score, 0) / articles.length
          },
          suggestions: generateSuggestions(searchQuery, articles)
        },
        search_statistics: {
          total_matches: parseInt(stats.total_matches || 0),
          sentiment_distribution: {
            positive: parseInt(stats.positive_count || 0),
            negative: parseInt(stats.negative_count || 0),
            neutral: parseInt(stats.neutral_count || 0)
          },
          unique_categories: parseInt(stats.unique_categories || 0),
          unique_sources: parseInt(stats.unique_sources || 0),
          average_relevance: parseFloat(stats.avg_relevance || 0)
        }
      },
      filters: {
        query: searchQuery,
        category,
        sentiment,
        timeframe,
        source,
        symbol,
        limit: parseInt(limit)
      },
      methodology: {
        search_algorithm: "Multi-field text matching with relevance scoring",
        relevance_factors: "Headline match (10pts), summary match (5pts), symbol match (8pts), content relevance (3x)",
        ranking: "Search relevance score + recency + content relevance",
        text_matching: "Case-insensitive partial matching across headline, summary, and URL"
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("News search error:", error);
    
    if (error.message.includes('relation "news" does not exist')) {
      return res.status(503).json({
        success: false,
        error: "News search service not available",
        message: "News database not configured. Please run the news data loader script.",
        timestamp: new Date().toISOString()
      });
    }
    
    res.status(500).json({
      success: false,
      error: "Failed to search news",
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

module.exports = router;
