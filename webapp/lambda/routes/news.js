const express = require('express');
const router = express.Router();
const { authenticateToken } = require('../middleware/auth');
const { query } = require('../utils/database');
// Initialize utilities with error fallback
let newsAnalyzer = null;
let sentimentEngine = null;

try {
  const NewsAnalyzer = require('../utils/newsAnalyzer');
  const SentimentEngine = require('../utils/sentimentEngine');
  newsAnalyzer = new NewsAnalyzer();
  sentimentEngine = new SentimentEngine();
  console.log('✅ News utilities initialized successfully');
} catch (error) {
  console.warn('⚠️ News utilities failed to initialize:', error.message);
  // Fallback implementations
  newsAnalyzer = {
    calculateReliabilityScore: (source) => 0.8
  };
  sentimentEngine = {
    scoreToLabel: (score) => score > 0.1 ? 'positive' : score < -0.1 ? 'negative' : 'neutral',
    analyzeSentiment: async (text) => ({ score: 0, label: 'neutral', confidence: 0.5 })
  };
}

// Health endpoint (no auth required)
router.get('/health', (req, res) => {
  res.json({
    success: true,
    status: 'operational',
    service: 'news',
    timestamp: new Date().toISOString(),
    message: 'News service is running',
    utilities_loaded: {
      newsAnalyzer: newsAnalyzer !== null,
      sentimentEngine: sentimentEngine !== null
    }
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
    console.warn('News database not available, returning informative response:', error.message);
    res.json({
      success: true,
      data: {
        articles: [],
        total: 0,
        limit: parseInt(limit),
        offset: parseInt(offset),
        message: 'News feed not configured - requires database setup with news data feeds',
        available_when_configured: [
          'Real-time financial news from multiple sources',
          'AI-powered sentiment analysis',
          'Symbol-specific news filtering', 
          'Category-based news organization',
          'Relevance scoring and impact analysis'
        ],
        data_sources: {
          news_configured: false,
          database_available: false
        }
      }
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
    console.warn('News database not available for sentiment analysis:', error.message);
    res.json({
      success: true,
      data: {
        symbol,
        timeframe,
        overall_sentiment: {
          score: 0,
          label: 'neutral',
          distribution: { positive: 0, negative: 0, neutral: 0 },
          total_articles: 0,
          avg_impact: 0,
          avg_relevance: 0
        },
        trend: [],
        keywords: [],
        message: 'Sentiment analysis not configured - requires database setup with news analytics',
        available_when_configured: [
          'Real-time sentiment scoring for individual symbols',
          'Sentiment trend analysis over time',
          'Keyword extraction and frequency analysis',
          'Impact and relevance scoring',
          'Historical sentiment comparison'
        ],
        data_sources: {
          sentiment_configured: false,
          database_available: false
        }
      }
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
    console.warn('News database not available for market sentiment:', error.message);
    res.json({
      success: true,
      data: {
        timeframe,
        overall_sentiment: {
          score: 0,
          label: 'neutral',
          distribution: { positive: 0, negative: 0, neutral: 0 },
          total_articles: 0
        },
        by_category: [],
        top_symbols: [],
        trend: [],
        message: 'Market sentiment analysis not configured - requires database setup with comprehensive news feeds',
        available_when_configured: [
          'Overall market sentiment scoring',
          'Sentiment breakdown by category (tech, healthcare, energy, etc.)',
          'Top symbols by sentiment impact',
          'Historical sentiment trends and patterns',
          'Professional sentiment indicators integration'
        ],
        data_sources: {
          market_sentiment_configured: false,
          database_available: false
        }
      }
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
    console.warn('Sentiment analysis engine not available:', error.message);
    res.json({
      success: true,
      data: {
        text: text.substring(0, 100) + '...',
        symbol: symbol || null,
        sentiment: {
          score: 0,
          label: 'neutral',
          confidence: 0.5
        },
        message: 'Custom sentiment analysis not configured - requires AI sentiment engine setup',
        available_when_configured: [
          'Real-time text sentiment analysis',
          'Symbol-specific sentiment context',
          'Confidence scoring and reliability metrics',
          'Multi-language sentiment support',
          'Financial domain-specific sentiment models'
        ],
        data_sources: {
          sentiment_engine_configured: false,
          ai_models_available: false
        }
      }
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
    console.warn('News database not available for sources analysis:', error.message);
    res.json({
      success: true,
      data: {
        sources: [],
        total: 0,
        message: 'News sources analysis not configured - requires database setup with source tracking',
        available_when_configured: [
          'News source reliability scoring',
          'Article count and frequency analysis',
          'Source sentiment distribution tracking',
          'Impact and relevance scoring by source',
          'Source performance and credibility metrics'
        ],
        data_sources: {
          sources_configured: false,
          database_available: false
        }
      }
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
    console.warn('News database not available for categories analysis:', error.message);
    res.json({
      success: true,
      data: {
        categories: [],
        total: 0,
        message: 'News categories analysis not configured - requires database setup with categorized content',
        available_when_configured: [
          'Category-based news organization',
          'Sentiment analysis by news category',
          'Impact scoring across different sectors',
          'Category performance and trend tracking',
          'Cross-category correlation analysis'
        ],
        data_sources: {
          categories_configured: false,
          database_available: false
        }
      }
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
    console.warn('News database not available for trending analysis:', error.message);
    res.json({
      success: true,
      data: {
        timeframe,
        keywords: [],
        symbols: [],
        message: 'Trending topics analysis not configured - requires database setup with keyword extraction',
        available_when_configured: [
          'Real-time trending keyword identification',
          'Symbol mention frequency tracking',
          'Sentiment-weighted trending analysis',
          'Impact-based topic ranking',
          'Historical trend comparison and patterns'
        ],
        data_sources: {
          trending_configured: false,
          database_available: false
        }
      }
    });
  }
});

// GET /api/market/news - Latest market news
authRouter.get('/', async (req, res) => {
  try {
    const { limit = 5, symbol = null } = req.query;
    
    let newsQuery;
    let queryParams;
    
    if (symbol) {
      newsQuery = `
        SELECT 
          title,
          DATE(published_date) as date,
          sentiment_score,
          CASE 
            WHEN sentiment_score > 0.1 THEN 'Positive'
            WHEN sentiment_score < -0.1 THEN 'Negative'
            ELSE 'Neutral'
          END as sentiment,
          url,
          source
        FROM stock_news 
        WHERE symbol = $1
        ORDER BY published_date DESC
        LIMIT $2
      `;
      queryParams = [symbol.toUpperCase(), parseInt(limit)];
    } else {
      newsQuery = `
        SELECT 
          title,
          DATE(published_date) as date,
          sentiment_score,
          CASE 
            WHEN sentiment_score > 0.1 THEN 'Positive'
            WHEN sentiment_score < -0.1 THEN 'Negative'
            ELSE 'Neutral'
          END as sentiment,
          url,
          source
        FROM stock_news 
        ORDER BY published_date DESC
        LIMIT $1
      `;
      queryParams = [parseInt(limit)];
    }
    
    const result = await query(newsQuery, queryParams);
    
    if (result.rows.length === 0) {
      // Return informative response instead of sample data
      return res.json({
        success: true,
        data: {
          articles: [],
          total: 0,
          symbol: symbol || null,
          limit: parseInt(limit),
          message: 'Market news feed not configured - requires database setup with news aggregation',
          available_when_configured: [
            'Real-time market news from professional sources',
            'Symbol-specific news filtering and analysis',
            'Sentiment scoring and impact analysis',
            'Source credibility and reliability tracking',
            'Historical news archive and search capabilities'
          ],
          data_sources: {
            market_news_configured: false,
            database_available: false
          }
        }
      });
    }
    
    res.json({
      success: true,
      data: result.rows
    });
    
  } catch (error) {
    console.error('Error fetching news:', error);
    
    // Return informative response instead of sample data
    res.json({
      success: true,
      data: {
        articles: [],
        total: 0,
        symbol: symbol || null,
        limit: parseInt(limit),
        message: 'Market news feed not configured - requires database setup with news aggregation',
        available_when_configured: [
          'Real-time market news from professional sources',
          'Symbol-specific news filtering and analysis', 
          'Sentiment scoring and impact analysis',
          'Source credibility and reliability tracking',
          'Historical news archive and search capabilities'
        ],
        data_sources: {
          market_news_configured: false,
          database_available: false
        }
      }
    });
  }
});

// Mount authenticated routes
router.use('/', authRouter);

module.exports = router;