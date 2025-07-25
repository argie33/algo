const express = require('express');

const router = express.Router();

// Health endpoint (no auth required)
router.get('/health', (req, res) => {
  res.json({
    success: true,
    status: 'operational',
    service: 'commodities',
    timestamp: new Date().toISOString(),
    message: 'Commodities service is running'
  });
});

// Root commodities endpoint for health checks
router.get('/', (req, res) => {
  res.json({
    success: true,
    data: {
      system: 'Commodities API',
      version: '1.0.0',
      status: 'operational',
      available_endpoints: [
        'GET /commodities/categories - Commodity categories',
        'GET /commodities/prices - Current commodity prices',
        'GET /commodities/market-summary - Market overview',
        'GET /commodities/correlations - Price correlations',
        'GET /commodities/news - Latest commodity news'
      ],
      timestamp: new Date().toISOString()
    }
  });
});

// Get commodity categories
router.get('/categories', (req, res) => {
  try {
    const categories = [
      {
        id: 'energy',
        name: 'Energy',
        description: 'Oil, gas, and energy commodities',
        commodities: ['crude-oil', 'natural-gas', 'heating-oil', 'gasoline'],
        weight: 0.35,
        performance: {
          '1d': 0.5,
          '1w': -2.1,
          '1m': 4.3,
          '3m': -8.7,
          '1y': 12.4
        }
      },
      {
        id: 'precious-metals',
        name: 'Precious Metals',
        description: 'Gold, silver, platinum, and palladium',
        commodities: ['gold', 'silver', 'platinum', 'palladium'],
        weight: 0.25,
        performance: {
          '1d': -0.3,
          '1w': 1.8,
          '1m': -1.2,
          '3m': 5.6,
          '1y': 8.9
        }
      },
      {
        id: 'base-metals',
        name: 'Base Metals',
        description: 'Copper, aluminum, zinc, and industrial metals',
        commodities: ['copper', 'aluminum', 'zinc', 'nickel', 'lead'],
        weight: 0.20,
        performance: {
          '1d': 1.2,
          '1w': 3.4,
          '1m': 2.8,
          '3m': -4.2,
          '1y': 15.7
        }
      },
      {
        id: 'agriculture',
        name: 'Agriculture',
        description: 'Grains, livestock, and soft commodities',
        commodities: ['wheat', 'corn', 'soybeans', 'coffee', 'sugar', 'cotton'],
        weight: 0.15,
        performance: {
          '1d': -0.8,
          '1w': -1.5,
          '1m': 6.2,
          '3m': 12.1,
          '1y': -3.4
        }
      },
      {
        id: 'livestock',
        name: 'Livestock',
        description: 'Cattle, hogs, and feeder cattle',
        commodities: ['live-cattle', 'feeder-cattle', 'lean-hogs'],
        weight: 0.05,
        performance: {
          '1d': 0.2,
          '1w': 2.1,
          '1m': -1.8,
          '3m': 7.3,
          '1y': 11.2
        }
      }
    ];

    res.json({
      success: true,
      data: categories,
      metadata: {
        totalCategories: categories.length,
        lastUpdated: new Date().toISOString(),
        priceDate: new Date().toISOString()
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching commodity categories:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch commodity categories',
      details: error.message
    });
  }
});

// Get commodity prices
router.get('/prices', (req, res) => {
  try {
    const category = req.query.category;
    const symbol = req.query.symbol;

    let commodities = [
      {
        symbol: 'CL',
        name: 'Crude Oil',
        category: 'energy',
        price: 78.45,
        change: 0.67,
        changePercent: 0.86,
        unit: 'per barrel',
        currency: 'USD',
        volume: 245678,
        lastUpdated: new Date().toISOString()
      },
      {
        symbol: 'GC',
        name: 'Gold',
        category: 'precious-metals',
        price: 2034.20,
        change: -5.30,
        changePercent: -0.26,
        unit: 'per ounce',
        currency: 'USD',
        volume: 89432,
        lastUpdated: new Date().toISOString()
      },
      {
        symbol: 'SI',
        name: 'Silver',
        category: 'precious-metals',
        price: 24.67,
        change: 0.23,
        changePercent: 0.94,
        unit: 'per ounce',
        currency: 'USD',
        volume: 34567,
        lastUpdated: new Date().toISOString()
      },
      {
        symbol: 'HG',
        name: 'Copper',
        category: 'base-metals',
        price: 3.89,
        change: 0.045,
        changePercent: 1.17,
        unit: 'per pound',
        currency: 'USD',
        volume: 67890,
        lastUpdated: new Date().toISOString()
      },
      {
        symbol: 'NG',
        name: 'Natural Gas',
        category: 'energy',
        price: 2.87,
        change: -0.12,
        changePercent: -4.02,
        unit: 'per MMBtu',
        currency: 'USD',
        volume: 123456,
        lastUpdated: new Date().toISOString()
      },
      {
        symbol: 'ZW',
        name: 'Wheat',
        category: 'agriculture',
        price: 6.45,
        change: -0.08,
        changePercent: -1.22,
        unit: 'per bushel',
        currency: 'USD',
        volume: 45678,
        lastUpdated: new Date().toISOString()
      }
    ];

    // Filter by category if specified
    if (category) {
      commodities = commodities.filter(c => c.category === category);
    }

    // Filter by symbol if specified
    if (symbol) {
      commodities = commodities.filter(c => c.symbol === symbol);
    }

    res.json({
      success: true,
      data: commodities,
      filters: {
        category: category || null,
        symbol: symbol || null
      },
      metadata: {
        totalCount: commodities.length,
        priceDate: new Date().toISOString()
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching commodity prices:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch commodity prices',
      details: error.message
    });
  }
});

// Get market summary
router.get('/market-summary', (req, res) => {
  try {
    const summary = {
      overview: {
        totalMarketCap: 4.2e12,
        totalVolume: 1.8e9,
        activeContracts: 125847,
        tradingSession: 'open'
      },
      performance: {
        '1d': {
          gainers: 18,
          losers: 12,
          unchanged: 3,
          topGainer: { symbol: 'HG', name: 'Copper', change: 1.17 },
          topLoser: { symbol: 'NG', name: 'Natural Gas', change: -4.02 }
        }
      },
      sectors: [
        {
          name: 'Energy',
          weight: 0.35,
          change: 0.62,
          volume: 8.9e8
        },
        {
          name: 'Precious Metals',
          weight: 0.25,
          change: -0.15,
          volume: 3.2e8
        }
      ]
    };

    res.json({
      success: true,
      data: summary,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching market summary:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch market summary',
      details: error.message
    });
  }
});

// Get correlations
router.get('/correlations', (req, res) => {
  try {
    const correlations = {
      overview: {
        description: 'Correlation matrix for major commodity sectors',
        period: '90d',
        lastUpdated: new Date().toISOString()
      },
      matrix: {
        'energy': {
          'energy': 1.00,
          'precious-metals': -0.23,
          'base-metals': 0.47,
          'agriculture': 0.12,
          'livestock': 0.08
        },
        'precious-metals': {
          'energy': -0.23,
          'precious-metals': 1.00,
          'base-metals': 0.18,
          'agriculture': -0.05,
          'livestock': -0.02
        }
      }
    };

    res.json({
      success: true,
      data: correlations,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching correlations:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch correlations',
      details: error.message
    });
  }
});

// Get commodity history data for a specific symbol
router.get('/history/:symbol', (req, res) => {
  try {
    const { symbol } = req.params;
    const { period = '1d' } = req.query;

    // Mock historical data
    const periods = ['1d', '1w', '1m', '3m', '1y'];
    if (!periods.includes(period)) {
      return res.status(400).json({
        success: false,
        error: 'Invalid period',
        validPeriods: periods
      });
    }

    const dataPoints = period === '1d' ? 24 : period === '1w' ? 7 : period === '1m' ? 30 : 90;
    const basePrice = symbol === 'CL' ? 78.45 : symbol === 'GC' ? 2034.20 : 100;
    
    const history = Array.from({ length: dataPoints }, (_, i) => {
      const timestamp = Date.now() - (dataPoints - i) * (period === '1d' ? 3600000 : 86400000);
      const variation = (Math.random() - 0.5) * 0.1;
      
      return {
        timestamp,
        date: new Date(timestamp).toISOString(),
        price: basePrice * (1 + variation),
        volume: Math.floor(Math.random() * 100000) + 50000
      };
    });

    res.json({
      success: true,
      data: {
        symbol,
        period,
        history,
        summary: {
          firstPrice: history[0]?.price,
          lastPrice: history[history.length - 1]?.price,
          change: history[history.length - 1]?.price - history[0]?.price,
          changePercent: ((history[history.length - 1]?.price - history[0]?.price) / history[0]?.price) * 100,
          totalVolume: history.reduce((sum, point) => sum + point.volume, 0)
        }
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching history:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch commodity history',
      details: error.message
    });
  }
});

// Get commodity news
router.get('/news', (req, res) => {
  try {
    const { limit = 10, category } = req.query;
    const maxLimit = Math.min(parseInt(limit), 50);

    const newsItems = [
      {
        id: 'news-1',
        title: 'Oil Prices Surge on Supply Concerns',
        summary: 'Crude oil futures jumped 3% amid geopolitical tensions affecting global supply chains.',
        category: 'energy',
        source: 'Commodity News',
        publishedAt: new Date(Date.now() - 3600000).toISOString(),
        url: '#',
        symbols: ['CL', 'NG']
      },
      {
        id: 'news-2', 
        title: 'Gold Reaches New Monthly High',
        summary: 'Precious metals rally as investors seek safe-haven assets amid market volatility.',
        category: 'precious-metals',
        source: 'Market Watch',
        publishedAt: new Date(Date.now() - 7200000).toISOString(),
        url: '#',
        symbols: ['GC', 'SI']
      },
      {
        id: 'news-3',
        title: 'Copper Demand Rises with Infrastructure Spending',
        summary: 'Industrial metals see increased demand as global infrastructure projects accelerate.',
        category: 'base-metals',
        source: 'Industrial Today',
        publishedAt: new Date(Date.now() - 10800000).toISOString(),
        url: '#',
        symbols: ['HG']
      },
      {
        id: 'news-4',
        title: 'Agricultural Commodities Mixed on Weather Reports',
        summary: 'Wheat and corn prices fluctuate as weather patterns affect growing conditions.',
        category: 'agriculture',
        source: 'Farm News',
        publishedAt: new Date(Date.now() - 14400000).toISOString(),
        url: '#',
        symbols: ['ZW', 'ZC']
      },
      {
        id: 'news-5',
        title: 'Natural Gas Storage Levels Drop',
        summary: 'Weekly inventory data shows continued decline in natural gas storage capacity.',
        category: 'energy',
        source: 'Energy Report',
        publishedAt: new Date(Date.now() - 18000000).toISOString(),
        url: '#',
        symbols: ['NG']
      }
    ];

    let filteredNews = newsItems;
    if (category) {
      filteredNews = newsItems.filter(item => item.category === category);
    }

    const limitedNews = filteredNews.slice(0, maxLimit);

    res.json({
      success: true,
      data: limitedNews,
      pagination: {
        limit: maxLimit,
        total: filteredNews.length,
        hasMore: filteredNews.length > maxLimit
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching news:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch commodity news',
      details: error.message
    });
  }
});

module.exports = router;