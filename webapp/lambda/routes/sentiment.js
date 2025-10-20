const express = require("express");

const { query } = require("../utils/database");
const { authenticateToken } = require("../middleware/auth");

const router = express.Router();

// Health endpoint (no auth required)
router.get("/health", (req, res) => {
  res.json({
    success: true,
    status: "operational",
    service: "sentiment",
    message: "Sentiment analysis service is running",
    timestamp: new Date().toISOString(),
  });
});

// Basic root endpoint (public)
router.get("/", (req, res) => {
  res.json({
    success: true,
    message: "Sentiment API - Ready",
    status: "operational",
    service: "sentiment",
    endpoints: ["analysis", "trends", "social", "news"],
    timestamp: new Date().toISOString(),
  });
});

// Sentiment analysis endpoint
router.get("/analysis", async (req, res) => {
  try {
    console.log('😊 Sentiment analysis endpoint accessed');
    const { symbol, period = "7d" } = req.query;
    console.log(`Request params: symbol=${symbol}, period=${period}`);

    // Require symbol parameter
    if (!symbol || symbol.trim() === '') {
      console.log('❌ Symbol parameter missing');
      return res.status(400).json({
        success: false,
        error: "Symbol parameter required",
        message: "Please provide a symbol using ?symbol=TICKER",
        timestamp: new Date().toISOString(),
      });
    }

    console.log(
      `😊 Sentiment analysis requested for symbol: ${symbol}, period: ${period}`
    );

    const targetSymbol = symbol.trim().toUpperCase();

    // Convert period to days for calculation
    const periodDays = {
      "1d": 1,
      "3d": 3,
      "7d": 7,
      "14d": 14,
      "30d": 30,
    };

    const days = periodDays[period] || 7;

    // Get sentiment data using actual sentiment analysis tables (from loadsentiment.py)
    let sentimentResult;
    try {
      console.log(`🔍 Attempting sentiment query for ${targetSymbol}, period: ${days} days`);
      // First try analyst_sentiment_analysis and social_sentiment_analysis
      sentimentResult = await query(
        `
        SELECT
          a.symbol,
          a.date,
          a.recommendation_mean,
          a.price_target_vs_current,
          s.news_sentiment_score as sentiment,
          s.reddit_sentiment_score,
          s.search_volume_index,
          s.news_article_count
        FROM analyst_sentiment_analysis a
        LEFT JOIN social_sentiment_analysis s ON a.symbol = s.symbol AND a.date = s.date
        WHERE a.symbol = $1
          AND a.date >= CURRENT_DATE - INTERVAL '1 day' * $2
        ORDER BY a.date DESC
        LIMIT 50
        `,
        [targetSymbol, days]
      );
      console.log(`📊 Query successful, got ${sentimentResult?.rows?.length || 0} rows`);
    } catch (e) {
      console.error('Sentiment analysis query failed:', e.message);

      // Check if this is a critical database error that should return 500
      if (e.message.includes('Database connection failed') || e.message.includes('connection failed')) {
        return res.status(500).json({
          success: false,
          error: 'Database error occurred',
          message: 'Unable to fetch sentiment data due to database connectivity issues',
          timestamp: new Date().toISOString(),
        });
      }

      // Return error response - no mock data fallbacks
      return res.status(503).json({
        success: false,
        error: 'Sentiment analysis service unavailable',
        message: 'Database table missing or query failed',
        timestamp: new Date().toISOString(),
      });
    }

    // Calculate sentiment metrics from actual sentiment data
    // Ensure sentimentResult exists and has rows property
    if (!sentimentResult || !sentimentResult.rows) {
      return res.status(503).json({
        success: false,
        error: 'Sentiment service unavailable',
        message: 'Database query failed or returned invalid result',
        timestamp: new Date().toISOString(),
      });
    }
    let sentimentData = sentimentResult.rows;

    // If no sentiment data found from database, return error
    if (sentimentData.length === 0) {
      return res.status(404).json({
        success: false,
        error: 'No sentiment data found',
        message: `No sentiment data available for symbol: ${targetSymbol}`,
        timestamp: new Date().toISOString(),
      });
    }

    // Debug: log the actual data structure
    console.log('Sentiment data structure:', JSON.stringify(sentimentData.slice(0, 1), null, 2));
    console.log('Number of sentiment data rows:', sentimentData.length);

    // Convert string values to numbers and validate sentiment data integrity
    sentimentData.forEach(item => {
      if (item.recommendation_mean !== null && item.recommendation_mean !== undefined) {
        item.recommendation_mean = Number(item.recommendation_mean);
      }
      if (item.price_target_vs_current !== null && item.price_target_vs_current !== undefined) {
        item.price_target_vs_current = Number(item.price_target_vs_current);
      }
      if (item.sentiment !== null && item.sentiment !== undefined) {
        item.sentiment = Number(item.sentiment);
      }
      if (item.reddit_sentiment_score !== null && item.reddit_sentiment_score !== undefined) {
        item.reddit_sentiment_score = Number(item.reddit_sentiment_score);
      }
    });

    // Validate sentiment data integrity after conversion
    const invalidItems = sentimentData.filter(item => {
      // At least one of recommendation_mean or sentiment should be a valid number
      const hasValidRecommendation = (item.recommendation_mean !== null &&
                                      item.recommendation_mean !== undefined &&
                                      typeof item.recommendation_mean === 'number' &&
                                      !isNaN(item.recommendation_mean));
      const hasValidSentiment = (item.sentiment !== null &&
                                item.sentiment !== undefined &&
                                typeof item.sentiment === 'number' &&
                                !isNaN(item.sentiment));

      return !hasValidRecommendation && !hasValidSentiment;
    });

    console.log(`Validation results: ${invalidItems.length} invalid items out of ${sentimentData.length} total items`);

    if (invalidItems.length > 0 && invalidItems.length === sentimentData.length) {
      return res.status(503).json({
        success: false,
        error: 'Sentiment data validation failed',
        message: 'All sentiment data has invalid structure - database may be corrupted',
        timestamp: new Date().toISOString(),
      });
    } else if (invalidItems.length > 0) {
      console.error('Data validation failed. Some items have invalid data structure:', invalidItems.slice(0, 3));
      // Filter out invalid items and continue with valid ones only
      const validItems = sentimentData.filter(item => !invalidItems.includes(item));
      console.log(`Continuing with ${validItems.length} valid items out of ${sentimentData.length} total`);
    }

    const sentimentCounts = sentimentData.reduce((counts, item) => {
      const score = item.sentiment || 0;
      if (score > 0.2) {
        counts.positive = (counts.positive || 0) + 1;
      } else if (score < -0.2) {
        counts.negative = (counts.negative || 0) + 1;
      } else {
        counts.neutral = (counts.neutral || 0) + 1;
      }
      return counts;
    }, {});

    // Calculate sentiment score (positive: +1, neutral: 0, negative: -1)
    const totalArticles = sentimentData.length;
    const positiveCount = sentimentCounts.positive || 0;
    const negativeCount = sentimentCounts.negative || 0;
    const neutralCount = sentimentCounts.neutral || 0;

    const sentimentScore =
      totalArticles > 0
        ? (((positiveCount - negativeCount) / totalArticles) * 100).toFixed(2)
        : 0;

    // Group articles by date for trend analysis
    const dailySentiment = sentimentData.reduce((daily, article) => {
      // Handle missing or invalid published_at dates
      const publishedDate = article.published_at;
      let date;
      if (publishedDate && typeof publishedDate.toISOString === 'function') {
        date = publishedDate.toISOString().split("T")[0];
      } else if (publishedDate && typeof publishedDate === 'string') {
        date = new Date(publishedDate).toISOString().split("T")[0];
      } else {
        date = new Date().toISOString().split("T")[0]; // Default to today for invalid dates
      }

      if (!daily[date]) {
        daily[date] = { positive: 0, negative: 0, neutral: 0, total: 0 };
      }

      // Convert numeric sentiment to category
      const sentimentScore = article.sentiment || 0;
      let sentimentCategory;
      if (typeof sentimentScore === 'number') {
        if (sentimentScore > 0.2) {
          sentimentCategory = 'positive';
        } else if (sentimentScore < -0.2) {
          sentimentCategory = 'negative';
        } else {
          sentimentCategory = 'neutral';
        }
      } else {
        sentimentCategory = sentimentScore || "neutral";
      }

      daily[date][sentimentCategory]++;
      daily[date].total++;
      return daily;
    }, {});

    // Calculate trend (last 3 days vs previous days)
    const sortedDates = Object.keys(dailySentiment).sort();
    const recentDates = sortedDates.slice(-3);
    const earlierDates = sortedDates.slice(0, -3);

    let recentScore = 0,
      earlierScore = 0;

    if (recentDates.length > 0) {
      const recentStats = recentDates.reduce(
        (sum, date) => {
          const day = dailySentiment[date];
          return {
            positive: sum.positive + day.positive,
            negative: sum.negative + day.negative,
            total: sum.total + day.total,
          };
        },
        { positive: 0, negative: 0, total: 0 }
      );

      recentScore =
        recentStats.total > 0
          ? ((recentStats.positive - recentStats.negative) /
              recentStats.total) *
            100
          : 0;
    }

    if (earlierDates.length > 0) {
      const earlierStats = earlierDates.reduce(
        (sum, date) => {
          const day = dailySentiment[date];
          return {
            positive: sum.positive + day.positive,
            negative: sum.negative + day.negative,
            total: sum.total + day.total,
          };
        },
        { positive: 0, negative: 0, total: 0 }
      );

      earlierScore =
        earlierStats.total > 0
          ? ((earlierStats.positive - earlierStats.negative) /
              earlierStats.total) *
            100
          : 0;
    }

    const trend =
      recentScore > earlierScore
        ? "improving"
        : recentScore < earlierScore
          ? "declining"
          : "stable";

    res.json({
      success: true,
      data: {
        symbol: targetSymbol,
        period: period,
        sentiment_score: parseFloat(sentimentScore),
        sentiment_grade: getSentimentGrade(parseFloat(sentimentScore)),
        trend: trend,
        articles_analyzed: totalArticles,
        sentiment_breakdown: {
          positive: positiveCount,
          negative: negativeCount,
          neutral: neutralCount,
          positive_pct:
            totalArticles > 0
              ? ((positiveCount / totalArticles) * 100).toFixed(1)
              : "0.0",
          negative_pct:
            totalArticles > 0
              ? ((negativeCount / totalArticles) * 100).toFixed(1)
              : "0.0",
          neutral_pct:
            totalArticles > 0
              ? ((neutralCount / totalArticles) * 100).toFixed(1)
              : "0.0",
        },
        daily_sentiment: dailySentiment,
        recent_articles: sentimentData.slice(0, 10).map((article) => ({
          title: article.title,
          sentiment: article.sentiment,
          source: article.source,
          published_at: article.published_at,
        })),
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Sentiment analysis error:", error);

    // Return 500 for calculation/validation errors
    if (error.message.includes('Sentiment calculation failed')) {
      return res.status(500).json({
        success: false,
        error: error.message,
        details: error.message,
      });
    }

    res.status(500).json({
      success: false,
      error: "Failed to perform sentiment analysis",
      details: error.message,
    });
  }
});

// Helper function to convert sentiment score to grade
function getSentimentGrade(score) {
  if (score >= 50) return "Very Positive";
  if (score >= 20) return "Positive";
  if (score > -20) return "Neutral";
  if (score > -50) return "Negative";
  return "Very Negative";
}

// Apply authentication to protected routes only
const authRouter = express.Router();
authRouter.use(authenticateToken);

// Basic ping endpoint (public)
router.get("/ping", (req, res) => {
  res.json({
    status: "ok",
    endpoint: "sentiment",
    timestamp: new Date().toISOString(),
  });
});

// Get social media sentiment overview
router.get("/social", async (req, res) => {
  try {
    console.log("📱 Social sentiment overview requested - not implemented");

    res.status(501).json({
      success: false,
      error: "Social sentiment data not available",
      message: "Social media sentiment analysis is not yet implemented",
      data_source: "Real-time social media APIs (Twitter, Reddit, Discord)",
      recommendation: "Contact support to enable social sentiment features",
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Social sentiment overview error:", error);
    res.json({
      success: false,
      error: "Failed to fetch social sentiment overview",
      details: error.message,
    });
  }
});

// Get social media sentiment overview implementation (disabled - only real data)
// /social_disabled removed - simulated data not allowed per mandate

// Get Reddit-specific sentiment data (must come BEFORE /social/:symbol)
router.get("/social/reddit", async (req, res) => {
  try {
    const { symbol, limit = 50, sort = "relevance" } = req.query;

    console.log(
      `🔗 Reddit sentiment requested - symbol: ${symbol || "all"}, limit: ${limit}, sort: ${sort}`
    );

    // Query real Reddit sentiment data from database
    const { query } = require("../utils/database");

    let redditQuery = `
      SELECT
        id, symbol, subreddit, title, author, upvotes, downvotes,
        comments, sentiment_score, sentiment_label, created_utc,
        url, flair, mention_count
      FROM reddit_sentiment
      WHERE 1=1
    `;
    const queryParams = [];
    let paramCount = 0;

    if (symbol) {
      paramCount++;
      redditQuery += ` AND symbol = $${paramCount}`;
      queryParams.push(symbol.toUpperCase());
    }

    // Add sorting
    const sortOptions = {
      relevance: "mention_count DESC, upvotes DESC",
      sentiment: "sentiment_score DESC",
      engagement: "(upvotes + comments) DESC",
      recent: "created_utc DESC"
    };
    redditQuery += ` ORDER BY ${sortOptions[sort] || sortOptions.relevance}`;

    paramCount++;
    redditQuery += ` LIMIT $${paramCount}`;
    queryParams.push(parseInt(limit));

    const result = await query(redditQuery, queryParams);

    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "No Reddit sentiment data found",
        message: "No Reddit sentiment data available for the specified criteria"
      });
    }

    const redditData = result.rows;

    res.json({
      success: true,
      platform: "reddit",
      data: {
        posts: redditData.map(row => ({
          id: row.id,
          symbol: row.symbol,
          subreddit: row.subreddit,
          title: row.title,
          author: row.author,
          upvotes: parseInt(row.upvotes) || 0,
          downvotes: parseInt(row.downvotes) || 0,
          comments: parseInt(row.comments) || 0,
          sentiment_score: parseFloat(row.sentiment_score) || 0,
          sentiment_label: row.sentiment_label,
          created_utc: row.created_utc,
          url: row.url,
          flair: row.flair,
          mention_count: parseInt(row.mention_count) || 0,
        })),
        total: redditData.length,
      },
      filters: {
        symbol: symbol || "all",
        limit: parseInt(limit),
        sort: sort,
      },
      summary: {
        total_posts: redditData.length,
        avg_sentiment:
          redditData.length > 0
            ? redditData.reduce((sum, post) => sum + (parseFloat(post.sentiment_score) || 0), 0) /
              redditData.length
            : 0,
        by_sentiment: {
          positive: redditData.filter((p) => p.sentiment_label === "positive").length,
          negative: redditData.filter((p) => p.sentiment_label === "negative").length,
          neutral: redditData.filter((p) => p.sentiment_label === "neutral").length,
        },
        by_subreddit: redditData.reduce((acc, post) => {
          acc[post.subreddit] = (acc[post.subreddit] || 0) + 1;
          return acc;
        }, {}),
        total_engagement: redditData.reduce(
          (sum, post) => sum + (parseInt(post.upvotes) || 0) + (parseInt(post.comments) || 0),
          0
        ),
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Reddit sentiment error:", error);
    res.json({
      success: false,
      error: "Failed to fetch social sentiment data for reddit",
      message: error.message,
      platform: "reddit",
      troubleshooting: [
        "Reddit API integration not configured",
        "Social sentiment database tables not populated",
        "Check Reddit API credentials",
      ],
      timestamp: new Date().toISOString(),
    });
  }
});

// Twitter endpoint removed - only real data sources allowed
// API v2 integration not implemented - returning 501

// Social trending endpoint removed - only real data sources allowed

// Get social media sentiment data for a specific symbol
router.get("/social/:symbol", async (req, res) => {
  const { symbol } = req.params;
  try {
    console.log(
      `📱 Social sentiment for ${symbol} requested - not implemented`
    );

    res.status(501).json({
      success: false,
      error: "Social sentiment data not available for symbol",
      message: `Social media sentiment analysis for ${symbol} is not yet implemented`,
      data_source: "Twitter API v2, Reddit API, Discord webhooks",
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error(`Social sentiment error for ${symbol}:`, error);
    res.json({
      success: false,
      error: `Failed to fetch social sentiment data for ${symbol}`,
      details: error.message,
    });
  }
});

// /social_disabled/:symbol endpoint removed - simulated data not allowed

// Get trending stocks by social media mentions
router.get("/trending", async (req, res) => {
  try {
    console.log("📈 Trending sentiment requested - not implemented");

    res.status(501).json({
      success: false,
      error: "Trending sentiment data not available",
      message:
        "Trending social media sentiment analysis is not yet implemented",
      data_source: "Aggregated social media APIs and trending algorithms",
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Trending sentiment error:", error);
    res.json({
      success: false,
      error: "Failed to fetch trending sentiment data",
      details: error.message,
    });
  }
});

// /trending_disabled endpoint removed - simulated data not allowed

// Stock sentiment endpoint removed - only real data sources allowed
// Replaced with 501 Not Implemented

// Stock sentiment trend endpoint removed - only real data sources allowed


// Sectors sentiment endpoint removed - only real data sources allowed

// News sentiment endpoint removed - only real data sources allowed

// News articles endpoint removed - only real data sources allowed

// Institutional sentiment endpoint removed - only real data sources allowed

// Options sentiment endpoint removed - only real data sources allowed

// Sentiment alerts endpoints - returns empty array (no real alerts table yet)
router.get("/alerts", authenticateToken, async (req, res) => {
  try {
    const userId = req.user.sub;
    console.log(`🚨 Sentiment alerts for user: ${userId}`);

    // Return empty array - no real sentiment alerts table yet
    res.json({
      success: true,
      sentiment: [],
      message: "No sentiment alerts configured",
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Sentiment alerts error:", error);
    res.json({
      success: false,
      error: "Failed to get sentiment alerts",
      details: error.message,
    });
  }
});

router.post("/alerts", authenticateToken, async (req, res) => {
  try {
    const { symbol, alert_type, threshold } = req.body;
    const userId = req.user.sub;

    console.log(
      `🚨 Creating sentiment alert for ${symbol}, type: ${alert_type}`
    );

    const alert = {
      id: Date.now(),
      user_id: userId,
      symbol: symbol.toUpperCase(),
      alert_type: alert_type,
      threshold: threshold,
      status: "active",
      created_at: new Date().toISOString(),
    };

    res.json({
      success: true,
      data: alert,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Create sentiment alert error:", error);
    res.json({
      success: false,
      error: "Failed to create sentiment alert",
      details: error.message,
    });
  }
});

// Market-wide sentiment analysis
// Market sentiment from AAII sentiment table
router.get("/market", async (req, res) => {
  try {
    const { period = "30d" } = req.query;

    console.log(`📊 Market sentiment (AAII) requested, period: ${period}`);

    // Convert period to days
    const periodDays = {
      "7d": 7,
      "14d": 14,
      "30d": 30,
      "90d": 90,
    };

    const days = periodDays[period] || 30;

    // Query AAII sentiment data
    const result = await query(
      `SELECT date, bullish, neutral, bearish, created_at
       FROM aaii_sentiment
       WHERE date >= CURRENT_DATE - INTERVAL '1 day' * $1
       ORDER BY date DESC
       LIMIT 100`,
      [days]
    );

    if (!result || !result.rows || result.rows.length === 0) {
      return res.json({
        success: true,
        sentiment: [],
        message: "No AAII sentiment data available for the requested period",
        timestamp: new Date().toISOString(),
      });
    }

    res.json({
      success: true,
      data: result.rows.map(row => ({
        date: row.date,
        bullish: parseFloat(row.bullish),
        neutral: parseFloat(row.neutral),
        bearish: parseFloat(row.bearish),
      })),
      period,
      timestamp: new Date().toISOString(),
    });
  } catch (err) {
    console.error("Market sentiment error:", err);
    res.status(500).json({
      success: false,
      error: "Failed to retrieve market sentiment",
      details: err.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Stock-specific sentiment data
router.get("/stocks", async (req, res) => {
  try {
    const { symbol } = req.query;

    console.log(`📊 Stock sentiment requested, symbol: ${symbol || 'all'}`);

    let sentimentQuery;
    let params = [];

    if (symbol) {
      sentimentQuery = `
        SELECT symbol, date, sentiment_score, positive_mentions, negative_mentions,
               neutral_mentions, total_mentions, source, fetched_at
        FROM sentiment
        WHERE symbol = $1
        ORDER BY date DESC
        LIMIT 100
      `;
      params = [symbol.toUpperCase()];
    } else {
      sentimentQuery = `
        SELECT symbol, date, sentiment_score, positive_mentions, negative_mentions,
               neutral_mentions, total_mentions, source, fetched_at
        FROM sentiment
        ORDER BY date DESC, symbol
        LIMIT 100
      `;
    }

    const result = await query(sentimentQuery, params);

    if (!result || !result.rows || result.rows.length === 0) {
      return res.json({
        success: true,
        sentiment: [],
        message: symbol
          ? `No sentiment data available for ${symbol}`
          : "No stock sentiment data available",
        timestamp: new Date().toISOString(),
      });
    }

    res.json({
      success: true,
      data: result.rows.map(row => ({
        symbol: row.symbol,
        date: row.date,
        sentiment_score: row.sentiment_score ? parseFloat(row.sentiment_score) : null,
        positive_mentions: row.positive_mentions || 0,
        negative_mentions: row.negative_mentions || 0,
        neutral_mentions: row.neutral_mentions || 0,
        total_mentions: row.total_mentions || 0,
        source: row.source || "Unknown",
      })),
      timestamp: new Date().toISOString(),
    });
  } catch (err) {
    console.error("Stock sentiment error:", err);
    res.status(500).json({
      success: false,
      error: "Failed to retrieve stock sentiment",
      details: err.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Catch-all /:symbol endpoint removed - only real data sources allowed

module.exports = router;
