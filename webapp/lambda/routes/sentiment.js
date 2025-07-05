const express = require('express');
const { query } = require('../utils/database');

const router = express.Router();

// Basic ping endpoint
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
    
    // Mock data for now - replace with real social media sentiment analysis
    const mockSocialData = {
      reddit: {
        mentions: [
          { date: '2025-07-01', mentions: 156, sentiment: 0.65 },
          { date: '2025-07-02', mentions: 234, sentiment: 0.72 },
          { date: '2025-07-03', mentions: 189, sentiment: 0.58 },
          { date: '2025-07-04', mentions: 298, sentiment: 0.81 },
          { date: '2025-07-05', mentions: 267, sentiment: 0.76 }
        ],
        subredditBreakdown: [
          { name: 'r/investing', value: 35, sentiment: 0.72 },
          { name: 'r/stocks', value: 28, sentiment: 0.68 },
          { name: 'r/SecurityAnalysis', value: 18, sentiment: 0.75 },
          { name: 'r/ValueInvesting', value: 12, sentiment: 0.71 },
          { name: 'r/wallstreetbets', value: 7, sentiment: 0.85 }
        ],
        topPosts: [
          {
            id: 1,
            title: `${symbol} Q4 earnings analysis - bullish indicators`,
            subreddit: 'r/investing',
            score: 1245,
            comments: 189,
            sentiment: 0.82,
            author: 'u/InvestorAnalyst',
            timestamp: '2 hours ago'
          },
          {
            id: 2,
            title: `Technical analysis: ${symbol} breaking resistance`,
            subreddit: 'r/stocks',
            score: 892,
            comments: 156,
            sentiment: 0.75,
            author: 'u/TechTrader',
            timestamp: '4 hours ago'
          }
        ]
      },
      googleTrends: {
        searchVolume: [
          { date: '2025-07-01', volume: 82, relativeInterest: 0.82 },
          { date: '2025-07-02', volume: 95, relativeInterest: 0.95 },
          { date: '2025-07-03', volume: 78, relativeInterest: 0.78 },
          { date: '2025-07-04', volume: 100, relativeInterest: 1.0 },
          { date: '2025-07-05', volume: 91, relativeInterest: 0.91 }
        ],
        relatedQueries: [
          { query: `${symbol} stock price`, volume: 100, trend: 'rising' },
          { query: `${symbol} earnings 2025`, volume: 85, trend: 'rising' },
          { query: `${symbol} dividend`, volume: 72, trend: 'stable' },
          { query: `${symbol} technical analysis`, volume: 55, trend: 'rising' }
        ],
        geographicDistribution: [
          { region: 'United States', interest: 100, sentiment: 0.74 },
          { region: 'Canada', interest: 45, sentiment: 0.71 },
          { region: 'United Kingdom', interest: 38, sentiment: 0.69 },
          { region: 'Germany', interest: 35, sentiment: 0.67 },
          { region: 'Australia', interest: 32, sentiment: 0.73 }
        ]
      },
      socialMetrics: {
        overall: {
          totalMentions: 1234,
          sentimentScore: 0.73,
          engagementRate: 0.15,
          viralityIndex: 0.28,
          influencerMentions: 45
        },
        platforms: [
          { name: 'Reddit', mentions: 567, sentiment: 0.71, engagement: 0.18 },
          { name: 'Twitter', mentions: 423, sentiment: 0.68, engagement: 0.12 },
          { name: 'StockTwits', mentions: 189, sentiment: 0.82, engagement: 0.22 },
          { name: 'Discord', mentions: 55, sentiment: 0.75, engagement: 0.31 }
        ]
      }
    };

    res.json({
      symbol,
      timeframe,
      data: mockSocialData,
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
    
    // Mock trending stocks data
    const trendingStocks = [
      { symbol: 'AAPL', mentions: 1234, sentiment: 0.73, change: 0.15 },
      { symbol: 'TSLA', mentions: 1089, sentiment: 0.68, change: -0.08 },
      { symbol: 'NVDA', mentions: 892, sentiment: 0.81, change: 0.22 },
      { symbol: 'MSFT', mentions: 756, sentiment: 0.69, change: 0.05 },
      { symbol: 'GOOGL', mentions: 634, sentiment: 0.72, change: 0.12 },
      { symbol: 'AMZN', mentions: 567, sentiment: 0.65, change: -0.03 },
      { symbol: 'META', mentions: 456, sentiment: 0.58, change: 0.18 },
      { symbol: 'NFLX', mentions: 389, sentiment: 0.62, change: 0.09 },
      { symbol: 'AMD', mentions: 321, sentiment: 0.77, change: 0.14 },
      { symbol: 'INTC', mentions: 298, sentiment: 0.54, change: -0.12 }
    ].slice(0, parseInt(limit));

    res.json({
      trending: trendingStocks,
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

    // Mock batch sentiment data
    const batchData = symbols.map(symbol => ({
      symbol,
      sentimentScore: Math.random() * 0.4 + 0.5, // Random between 0.5-0.9
      mentions: Math.floor(Math.random() * 1000) + 100,
      engagement: Math.random() * 0.3 + 0.1,
      trend: Math.random() > 0.5 ? 'rising' : 'falling'
    }));

    res.json({
      data: batchData,
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