const express = require('express');
const router = express.Router();
const { authenticateToken } = require('../middleware/auth');
const { query } = require('../utils/database');
const NewsAnalyzer = require('../utils/newsAnalyzer');
const SentimentEngine = require('../utils/sentimentEngine');

// Health endpoint (no auth required)
router.get('/health', (req, res) => {
  res.json({
    success: true,
    status: 'operational',
    service: 'news',
    timestamp: new Date().toISOString(),
    message: 'News service is running'
  });
});

// Basic root endpoint (public)
router.get('/', (req, res) => {
  res.json({
    success: true,
    message: 'News API - Ready',
    timestamp: new Date().toISOString(),
    status: 'operational'
  });
});

// Apply authentication to protected routes only
const authRouter = express.Router();
authRouter.use(authenticateToken);

// Initialize news analyzer and sentiment engine
const newsAnalyzer = new NewsAnalyzer();
const sentimentEngine = new SentimentEngine();

// Get news articles with sentiment analysis
router.get('/articles', async (req, res) => {
  try {
    const { 
      symbol, 
      category, 
      sentiment, 
      limit = 50, 
      offset = 0, 
      timeframe = '24h' 
    } = req.query;
    
    let whereClause = 'WHERE 1=1';
    const params = [];
    let paramIndex = 1;
    
    // Parse timeframe
    const timeframeMap = {
      '1h': '1 hour',
      '6h': '6 hours',
      '24h': '24 hours',
      '3d': '3 days',
      '1w': '1 week',
      '1m': '1 month'
    };
    
    const intervalClause = timeframeMap[timeframe] || '24 hours';
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
    
    const result = await query(`
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
    `, [...params, parseInt(limit), parseInt(offset)]);
    
    // Get total count
    const countResult = await query(`
      SELECT COUNT(*) as total
      FROM news_articles na
      ${whereClause}
    `, params);
    
    const articles = result.rows.map(row => ({
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
        confidence: parseFloat(row.sentiment_confidence)
      },
      keywords: row.keywords,
      summary: row.summary,
      impact_score: parseFloat(row.impact_score),
      relevance_score: parseFloat(row.relevance_score),
      created_at: row.created_at
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
          timeframe
        }
      }
    });
  } catch (error) {
    console.error('Error fetching news articles:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch news articles',
      message: error.message
    });
  }
});

// Get sentiment analysis for a specific symbol
router.get('/sentiment/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const { timeframe = '24h' } = req.query;
    
    const timeframeMap = {
      '1h': '1 hour',
      '6h': '6 hours',
      '24h': '24 hours',
      '3d': '3 days',
      '1w': '1 week',
      '1m': '1 month'
    };
    
    const intervalClause = timeframeMap[timeframe] || '24 hours';
    
    // Get sentiment analysis
    const sentimentResult = await query(`
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
    `, [symbol]);
    
    // Get sentiment trend over time
    const trendResult = await query(`
      SELECT 
        DATE_TRUNC('hour', published_at) as hour,
        AVG(sentiment_score) as avg_sentiment,
        COUNT(*) as article_count
      FROM news_articles
      WHERE symbol = $1
      AND published_at >= NOW() - INTERVAL '${intervalClause}'
      GROUP BY DATE_TRUNC('hour', published_at)
      ORDER BY hour ASC
    `, [symbol]);
    
    // Get top keywords
    const keywordResult = await query(`
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
    `, [symbol]);
    
    const sentiment = sentimentResult.rows[0];
    const sentimentAnalysis = {
      symbol,
      timeframe,
      overall_sentiment: {
        score: parseFloat(sentiment.avg_sentiment) || 0,
        label: sentimentEngine.scoreToLabel(parseFloat(sentiment.avg_sentiment) || 0),
        distribution: {
          positive: parseInt(sentiment.positive_count) || 0,
          negative: parseInt(sentiment.negative_count) || 0,
          neutral: parseInt(sentiment.neutral_count) || 0
        },
        total_articles: parseInt(sentiment.total_articles) || 0,
        avg_impact: parseFloat(sentiment.avg_impact) || 0,
        avg_relevance: parseFloat(sentiment.avg_relevance) || 0
      },
      trend: trendResult.rows.map(row => ({
        hour: row.hour,
        sentiment: parseFloat(row.avg_sentiment),
        article_count: parseInt(row.article_count)
      })),
      keywords: keywordResult.rows.map(row => ({
        keyword: row.keyword,
        frequency: parseInt(row.frequency)
      }))
    };
    
    res.json({
      success: true,
      data: sentimentAnalysis
    });
  } catch (error) {
    console.error('Error fetching sentiment analysis:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch sentiment analysis',
      message: error.message
    });
  }
});

// Get market sentiment overview
router.get('/market-sentiment', async (req, res) => {
  try {
    const { timeframe = '24h' } = req.query;
    
    const timeframeMap = {
      '1h': '1 hour',
      '6h': '6 hours',
      '24h': '24 hours',
      '3d': '3 days',
      '1w': '1 week',
      '1m': '1 month'
    };
    
    const intervalClause = timeframeMap[timeframe] || '24 hours';
    
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
        label: sentimentEngine.scoreToLabel(parseFloat(market.avg_sentiment) || 0),
        distribution: {
          positive: parseInt(market.positive_count) || 0,
          negative: parseInt(market.negative_count) || 0,
          neutral: parseInt(market.neutral_count) || 0
        },
        total_articles: parseInt(market.total_articles) || 0
      },
      by_category: categoryResult.rows.map(row => ({
        category: row.category,
        sentiment: parseFloat(row.avg_sentiment),
        article_count: parseInt(row.article_count),
        label: sentimentEngine.scoreToLabel(parseFloat(row.avg_sentiment))
      })),
      top_symbols: symbolResult.rows.map(row => ({
        symbol: row.symbol,
        sentiment: parseFloat(row.avg_sentiment),
        article_count: parseInt(row.article_count),
        impact: parseFloat(row.avg_impact),
        label: sentimentEngine.scoreToLabel(parseFloat(row.avg_sentiment))
      })),
      trend: trendResult.rows.map(row => ({
        hour: row.hour,
        sentiment: parseFloat(row.avg_sentiment),
        article_count: parseInt(row.article_count)
      }))
    };
    
    res.json({
      success: true,
      data: marketSentiment
    });
  } catch (error) {
    console.error('Error fetching market sentiment:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch market sentiment',
      message: error.message
    });
  }
});

// Analyze sentiment for custom text
router.post('/analyze-sentiment', async (req, res) => {
  try {
    const { text, symbol } = req.body;
    
    if (!text) {
      return res.status(400).json({
        success: false,
        error: 'Text is required for sentiment analysis'
      });
    }
    
    const analysis = await sentimentEngine.analyzeSentiment(text, symbol);
    
    res.json({
      success: true,
      data: analysis
    });
  } catch (error) {
    console.error('Error analyzing sentiment:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to analyze sentiment',
      message: error.message
    });
  }
});

// Get news sources and their reliability scores
router.get('/sources', async (req, res) => {
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
    
    const sources = result.rows.map(row => ({
      source: row.source,
      article_count: parseInt(row.article_count),
      avg_relevance: parseFloat(row.avg_relevance),
      avg_impact: parseFloat(row.avg_impact),
      sentiment_distribution: {
        positive: parseInt(row.positive_count),
        negative: parseInt(row.negative_count),
        neutral: parseInt(row.neutral_count)
      },
      reliability_score: newsAnalyzer.calculateReliabilityScore(row.source)
    }));
    
    res.json({
      success: true,
      data: {
        sources,
        total: sources.length
      }
    });
  } catch (error) {
    console.error('Error fetching news sources:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch news sources',
      message: error.message
    });
  }
});

// Get news categories
router.get('/categories', async (req, res) => {
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
    
    const categories = result.rows.map(row => ({
      category: row.category,
      article_count: parseInt(row.article_count),
      avg_sentiment: parseFloat(row.avg_sentiment),
      avg_impact: parseFloat(row.avg_impact),
      sentiment_label: sentimentEngine.scoreToLabel(parseFloat(row.avg_sentiment))
    }));
    
    res.json({
      success: true,
      data: {
        categories,
        total: categories.length
      }
    });
  } catch (error) {
    console.error('Error fetching news categories:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch news categories',
      message: error.message
    });
  }
});

// Get trending topics
router.get('/trending', async (req, res) => {
  try {
    const { timeframe = '24h', limit = 10 } = req.query;
    
    const timeframeMap = {
      '1h': '1 hour',
      '6h': '6 hours',
      '24h': '24 hours',
      '3d': '3 days',
      '1w': '1 week'
    };
    
    const intervalClause = timeframeMap[timeframe] || '24 hours';
    
    // Get trending keywords
    const keywordResult = await query(`
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
    `, [parseInt(limit)]);
    
    // Get trending symbols
    const symbolResult = await query(`
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
    `, [parseInt(limit)]);
    
    const trending = {
      timeframe,
      keywords: keywordResult.rows.map(row => ({
        keyword: row.keyword,
        frequency: parseInt(row.frequency),
        avg_sentiment: parseFloat(row.avg_sentiment),
        avg_impact: parseFloat(row.avg_impact),
        sentiment_label: sentimentEngine.scoreToLabel(parseFloat(row.avg_sentiment))
      })),
      symbols: symbolResult.rows.map(row => ({
        symbol: row.symbol,
        mention_count: parseInt(row.mention_count),
        avg_sentiment: parseFloat(row.avg_sentiment),
        avg_impact: parseFloat(row.avg_impact),
        sentiment_label: sentimentEngine.scoreToLabel(parseFloat(row.avg_sentiment))
      }))
    };
    
    res.json({
      success: true,
      data: trending
    });
  } catch (error) {
    console.error('Error fetching trending topics:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch trending topics',
      message: error.message
    });
  }
});

module.exports = router;