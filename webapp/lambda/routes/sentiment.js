const express = require("express");

const { _query } = require("../utils/database");
const { authenticateToken } = require("../middleware/auth");

const router = express.Router();

// Health endpoint (no auth required)
router.get("/health", (req, res) => {
  res.success({status: "operational",
    service: "sentiment",
    timestamp: new Date().toISOString(),
    message: "Sentiment analysis service is running",
  });
});

// Basic root endpoint (public)
router.get("/", (req, res) => {
  res.success({message: "Sentiment API - Ready",
    timestamp: new Date().toISOString(),
    status: "operational",
  });
});

// Sentiment analysis endpoint
router.get("/analysis", async (req, res) => {
  try {
    const { symbol, period = "7d" } = req.query;

    console.log(`😊 Sentiment analysis requested for symbol: ${symbol || 'market'}, period: ${period}`);

    if (!symbol) {
      return res.status(400).json({
        success: false,
        error: "Symbol parameter required",
        message: "Please provide a symbol using ?symbol=TICKER"
      });
    }

    // Convert period to days for calculation
    const periodDays = {
      "1d": 1,
      "3d": 3,
      "7d": 7,
      "14d": 14,
      "30d": 30
    };

    const days = periodDays[period] || 7;

    // Get sentiment data from news articles
    const newsResult = await _query(
      `
      SELECT 
        sentiment,
        published_at,
        title,
        source,
        symbols
      FROM news_articles 
      WHERE sentiment IS NOT NULL 
        AND (symbols @> ARRAY[$1] OR $1 = ANY(symbols))
        AND published_at >= NOW() - INTERVAL '${days} days'
      ORDER BY published_at DESC
      LIMIT 100
      `,
      [symbol.toUpperCase()]
    ).catch(() => ({ rows: [] }));

    // Calculate sentiment metrics
    const articles = newsResult.rows;
    const sentimentCounts = articles.reduce((counts, article) => {
      const sentiment = article.sentiment || 'neutral';
      counts[sentiment] = (counts[sentiment] || 0) + 1;
      return counts;
    }, {});

    // Calculate sentiment score (positive: +1, neutral: 0, negative: -1)
    const totalArticles = articles.length;
    const positiveCount = sentimentCounts.positive || 0;
    const negativeCount = sentimentCounts.negative || 0;
    const neutralCount = sentimentCounts.neutral || 0;

    const sentimentScore = totalArticles > 0 
      ? ((positiveCount - negativeCount) / totalArticles * 100).toFixed(2)
      : 0;

    // Group articles by date for trend analysis
    const dailySentiment = articles.reduce((daily, article) => {
      const date = article.published_at.toISOString().split('T')[0];
      if (!daily[date]) {
        daily[date] = { positive: 0, negative: 0, neutral: 0, total: 0 };
      }
      const sentiment = article.sentiment || 'neutral';
      daily[date][sentiment]++;
      daily[date].total++;
      return daily;
    }, {});

    // Calculate trend (last 3 days vs previous days)
    const sortedDates = Object.keys(dailySentiment).sort();
    const recentDates = sortedDates.slice(-3);
    const earlierDates = sortedDates.slice(0, -3);

    let recentScore = 0, earlierScore = 0;
    
    if (recentDates.length > 0) {
      const recentStats = recentDates.reduce((sum, date) => {
        const day = dailySentiment[date];
        return {
          positive: sum.positive + day.positive,
          negative: sum.negative + day.negative,
          total: sum.total + day.total
        };
      }, { positive: 0, negative: 0, total: 0 });
      
      recentScore = recentStats.total > 0 
        ? (recentStats.positive - recentStats.negative) / recentStats.total * 100
        : 0;
    }

    if (earlierDates.length > 0) {
      const earlierStats = earlierDates.reduce((sum, date) => {
        const day = dailySentiment[date];
        return {
          positive: sum.positive + day.positive,
          negative: sum.negative + day.negative,
          total: sum.total + day.total
        };
      }, { positive: 0, negative: 0, total: 0 });
      
      earlierScore = earlierStats.total > 0 
        ? (earlierStats.positive - earlierStats.negative) / earlierStats.total * 100
        : 0;
    }

    const trend = recentScore > earlierScore ? 'improving' : 
                  recentScore < earlierScore ? 'declining' : 'stable';

    res.json({
      success: true,
      data: {
        symbol: symbol.toUpperCase(),
        period: period,
        sentiment_score: parseFloat(sentimentScore),
        sentiment_grade: getSentimentGrade(parseFloat(sentimentScore)),
        trend: trend,
        articles_analyzed: totalArticles,
        sentiment_breakdown: {
          positive: positiveCount,
          negative: negativeCount,
          neutral: neutralCount,
          positive_pct: totalArticles > 0 ? (positiveCount / totalArticles * 100).toFixed(1) : "0.0",
          negative_pct: totalArticles > 0 ? (negativeCount / totalArticles * 100).toFixed(1) : "0.0",
          neutral_pct: totalArticles > 0 ? (neutralCount / totalArticles * 100).toFixed(1) : "0.0"
        },
        daily_sentiment: dailySentiment,
        recent_articles: articles.slice(0, 10).map(article => ({
          title: article.title,
          sentiment: article.sentiment,
          source: article.source,
          published_at: article.published_at
        }))
      },
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error("Sentiment analysis error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to perform sentiment analysis",
      details: error.message
    });
  }
});

// Helper function to convert sentiment score to grade
function getSentimentGrade(score) {
  if (score >= 50) return 'Very Positive';
  if (score >= 20) return 'Positive';
  if (score > -20) return 'Neutral';
  if (score > -50) return 'Negative';
  return 'Very Negative';
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
  return res.status(501).json({
    success: false,
    error: "Social sentiment data not available",
    message: "Social media sentiment analysis requires integration with social data providers",
    data_source: "database_query_required",
    recommendation: "Configure social media APIs and populate social_sentiment table"
  });
});

// Get social media sentiment data for a specific symbol
router.get("/social/:symbol", async (req, res) => {
  const { symbol } = req.params;
  return res.status(501).json({
    success: false,
    error: "Social sentiment data not available for symbol",
    message: `Social sentiment analysis for ${symbol} requires social media data integration`,
    data_source: "database_query_required"
  });
});

// Get trending stocks by social media mentions
router.get("/trending", async (req, res) => {
  return res.status(501).json({
    success: false,
    error: "Trending sentiment data not available",
    message: "Trending stocks analysis requires social media data integration",
    data_source: "database_query_required"
  });
});

module.exports = router;
