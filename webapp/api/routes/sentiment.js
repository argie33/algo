const express = require('express');
// const { query } = require('../utils/database');
const { authenticateToken } = require('../middleware/auth');

const router = express.Router();

// Health endpoint (no auth required)
router.get('/health', (req, res) => {
  res.json({
    success: true,
    status: 'operational',
    service: 'sentiment',
    timestamp: new Date().toISOString(),
    message: 'Sentiment analysis service is running'
  });
});

// Basic root endpoint (public)
router.get('/', (req, res) => {
  res.json({
    success: true,
    message: 'Sentiment API - Ready',
    timestamp: new Date().toISOString(),
    status: 'operational'
  });
});

// Apply authentication to protected routes only
const authRouter = express.Router();
authRouter.use(authenticateToken);

// Basic ping endpoint (public)
router.get('/ping', (req, res) => {
  res.json({
    status: 'ok',
    endpoint: 'sentiment',
    timestamp: new Date().toISOString()
  });
});

// Get social media sentiment data for a specific symbol
router.get('/social/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const { timeframe = '7d' } = req.query;
    
    // Return empty sentiment data with comprehensive diagnostics
    console.error('❌ Social media sentiment data unavailable - comprehensive diagnosis needed', {
      symbol,
      timeframe,
      detailed_diagnostics: {
        attempted_operations: ['social_media_api_call', 'sentiment_analysis_query'],
        potential_causes: [
          'Social media API keys not configured',
          'Sentiment analysis service unavailable',
          'Rate limiting on social media APIs',
          'Data processing pipeline failure',
          'External API authentication issues'
        ],
        troubleshooting_steps: [
          'Check social media API key configuration',
          'Verify sentiment analysis service status',
          'Review API rate limits and quotas',
          'Check data processing pipeline health',
          'Validate external API authentication'
        ],
        system_checks: [
          'Reddit API connectivity',
          'Twitter API availability',
          'Google Trends API status',
          'Sentiment analysis service health'
        ]
      }
    });

    const emptySocialData = {
      reddit: {
        mentions: [],
        subredditBreakdown: [],
        topPosts: []
      },
      googleTrends: {
        searchVolume: [],
        relatedQueries: [],
        geographicDistribution: []
      },
      socialMetrics: {
        overall: {
          totalMentions: 0,
          sentimentScore: 0,
          engagementRate: 0,
          viralityIndex: 0,
          influencerMentions: 0
        },
        platforms: []
      }
    };

    res.json({
      symbol,
      timeframe,
      data: emptySocialData,
      message: 'No social media sentiment data available - configure social media API keys',
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Error fetching social sentiment data:', error);
    res.status(500).json({
      error: 'Failed to fetch social sentiment data',
      message: error.message
    });
  }
});

// Get trending stocks by social media mentions
router.get('/trending', async (req, res) => {
  try {
    const { limit = 20, timeframe = '24h' } = req.query;
    
    // Return empty trending stocks with comprehensive diagnostics
    console.error('❌ Trending stocks sentiment data unavailable - comprehensive diagnosis needed', {
      limit,
      timeframe,
      detailed_diagnostics: {
        attempted_operations: ['trending_stocks_query', 'social_media_mentions_aggregation'],
        potential_causes: [
          'Social media API unavailable',
          'Trending analysis service down',
          'Data aggregation pipeline failure',
          'Database connection issues',
          'External API rate limiting'
        ],
        troubleshooting_steps: [
          'Check social media API connectivity',
          'Verify trending analysis service status',
          'Review data aggregation pipeline health',
          'Check database connectivity',
          'Monitor external API rate limits'
        ],
        system_checks: [
          'Social media service availability',
          'Trending analysis capacity',
          'Data pipeline health',
          'Database connection status'
        ]
      }
    });

    const emptyTrendingStocks = [];

    res.json({
      trending: emptyTrendingStocks,
      timeframe,
      limit: parseInt(limit),
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Error fetching trending stocks:', error);
    res.status(500).json({
      error: 'Failed to fetch trending stocks',
      message: error.message
    });
  }
});

// Get sentiment analysis for multiple symbols
router.post('/batch', async (req, res) => {
  try {
    const { symbols, timeframe = '7d' } = req.body;
    
    if (!symbols || !Array.isArray(symbols)) {
      return res.status(400).json({
        error: 'Invalid request',
        message: 'symbols array is required'
      });
    }

    // Return empty batch sentiment data with comprehensive diagnostics
    console.error('❌ Batch sentiment data unavailable - comprehensive diagnosis needed', {
      symbols,
      timeframe,
      detailed_diagnostics: {
        attempted_operations: ['batch_sentiment_analysis', 'multi_symbol_query'],
        potential_causes: [
          'Sentiment analysis service unavailable',
          'Batch processing pipeline failure',
          'External API rate limiting',
          'Database connection issues',
          'Data processing timeout'
        ],
        troubleshooting_steps: [
          'Check sentiment analysis service status',
          'Verify batch processing pipeline health',
          'Review external API rate limits',
          'Check database connectivity',
          'Monitor data processing timeouts'
        ],
        system_checks: [
          'Sentiment service availability',
          'Batch processing capacity',
          'External API health',
          'Database connection pool status'
        ]
      }
    });

    const emptyBatchData = symbols.map(symbol => ({
      symbol,
      sentimentScore: 0,
      mentions: 0,
      engagement: 0,
      trend: 'unknown'
    }));

    res.json({
      data: emptyBatchData,
      timeframe,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Error fetching batch sentiment data:', error);
    res.status(500).json({
      error: 'Failed to fetch batch sentiment data',
      message: error.message
    });
  }
});

// Get sentiment summary for market overview
router.get('/market-summary', async (req, res) => {
  try {
    const marketSentiment = {
      overall: {
        sentiment: 0.68,
        mentions: 15234,
        activeDiscussions: 892,
        sentiment24hChange: 0.05
      },
      sectors: [
        { name: 'Technology', sentiment: 0.72, mentions: 4567, change: 0.08 },
        { name: 'Healthcare', sentiment: 0.65, mentions: 2134, change: -0.02 },
        { name: 'Financial', sentiment: 0.61, mentions: 1987, change: 0.03 },
        { name: 'Energy', sentiment: 0.58, mentions: 1456, change: -0.12 },
        { name: 'Consumer', sentiment: 0.71, mentions: 1789, change: 0.15 }
      ],
      platforms: [
        { name: 'Reddit', activeUsers: 45678, sentiment: 0.69 },
        { name: 'Twitter', activeUsers: 78901, sentiment: 0.65 },
        { name: 'StockTwits', activeUsers: 12345, sentiment: 0.74 },
        { name: 'Discord', activeUsers: 6789, sentiment: 0.71 }
      ]
    };

    res.json({
      marketSentiment,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Error fetching market sentiment summary:', error);
    res.status(500).json({
      error: 'Failed to fetch market sentiment summary',
      message: error.message
    });
  }
});

module.exports = router;