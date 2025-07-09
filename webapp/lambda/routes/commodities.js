const express = require('express');
const router = express.Router();
const { authenticateToken } = require('../middleware/auth');
const { query } = require('../utils/database');
const apiKeyService = require('../utils/apiKeyService');

// Apply authentication to all routes
router.use(authenticateToken);

// Commodity categories and their symbols
const COMMODITY_CATEGORIES = {
  energy: {
    name: 'Energy',
    commodities: {
      'CL=F': { name: 'Crude Oil', unit: 'per barrel' },
      'NG=F': { name: 'Natural Gas', unit: 'per MMBtu' },
      'BZ=F': { name: 'Brent Crude', unit: 'per barrel' },
      'RB=F': { name: 'RBOB Gasoline', unit: 'per gallon' },
      'HO=F': { name: 'Heating Oil', unit: 'per gallon' }
    }
  },
  metals: {
    name: 'Precious Metals',
    commodities: {
      'GC=F': { name: 'Gold', unit: 'per troy oz' },
      'SI=F': { name: 'Silver', unit: 'per troy oz' },
      'PL=F': { name: 'Platinum', unit: 'per troy oz' },
      'PA=F': { name: 'Palladium', unit: 'per troy oz' },
      'HG=F': { name: 'Copper', unit: 'per pound' }
    }
  },
  agriculture: {
    name: 'Agriculture',
    commodities: {
      'ZC=F': { name: 'Corn', unit: 'per bushel' },
      'ZS=F': { name: 'Soybeans', unit: 'per bushel' },
      'ZW=F': { name: 'Wheat', unit: 'per bushel' },
      'KC=F': { name: 'Coffee', unit: 'per pound' },
      'SB=F': { name: 'Sugar', unit: 'per pound' },
      'CC=F': { name: 'Cocoa', unit: 'per metric ton' },
      'CT=F': { name: 'Cotton', unit: 'per pound' }
    }
  },
  livestock: {
    name: 'Livestock',
    commodities: {
      'LE=F': { name: 'Live Cattle', unit: 'per pound' },
      'GF=F': { name: 'Feeder Cattle', unit: 'per pound' },
      'HE=F': { name: 'Lean Hogs', unit: 'per pound' }
    }
  },
  forex: {
    name: 'Currencies',
    commodities: {
      'DX-Y.NYB': { name: 'US Dollar Index', unit: 'index' },
      'EURUSD=X': { name: 'EUR/USD', unit: 'exchange rate' },
      'GBPUSD=X': { name: 'GBP/USD', unit: 'exchange rate' },
      'USDJPY=X': { name: 'USD/JPY', unit: 'exchange rate' },
      'USDCAD=X': { name: 'USD/CAD', unit: 'exchange rate' }
    }
  }
};

// Get all commodity categories and symbols
router.get('/categories', (req, res) => {
  try {
    res.json({
      success: true,
      data: COMMODITY_CATEGORIES
    });
  } catch (error) {
    console.error('Error fetching commodity categories:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch commodity categories'
    });
  }
});

// Get current commodity prices
router.get('/prices', async (req, res) => {
  try {
    const { category, symbols } = req.query;
    
    // Get symbols to fetch
    let symbolsToFetch = [];
    if (symbols) {
      symbolsToFetch = symbols.split(',');
    } else if (category && COMMODITY_CATEGORIES[category]) {
      symbolsToFetch = Object.keys(COMMODITY_CATEGORIES[category].commodities);
    } else {
      // Get all symbols
      symbolsToFetch = Object.values(COMMODITY_CATEGORIES)
        .flatMap(cat => Object.keys(cat.commodities));
    }

    // Try to get from database first
    const dbPrices = await getCommodityPricesFromDB(symbolsToFetch);
    
    // If no recent data, fetch from external API
    const prices = dbPrices.length > 0 ? dbPrices : await fetchCommodityPricesExternal(symbolsToFetch);
    
    res.json({
      success: true,
      data: prices,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Error fetching commodity prices:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch commodity prices',
      message: error.message
    });
  }
});

// Get historical commodity prices
router.get('/history/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const { period = '1Y', interval = '1d' } = req.query;
    
    // Try database first
    const dbHistory = await getCommodityHistoryFromDB(symbol, period);
    
    if (dbHistory.length > 0) {
      res.json({
        success: true,
        data: dbHistory,
        source: 'database'
      });
    } else {
      // Fetch from external API
      const history = await fetchCommodityHistoryExternal(symbol, period, interval);
      res.json({
        success: true,
        data: history,
        source: 'external'
      });
    }
  } catch (error) {
    console.error('Error fetching commodity history:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch commodity history',
      message: error.message
    });
  }
});

// Get commodity market summary
router.get('/market-summary', async (req, res) => {
  try {
    // Get summary data for each category
    const summary = {};
    
    for (const [categoryKey, categoryData] of Object.entries(COMMODITY_CATEGORIES)) {
      const symbols = Object.keys(categoryData.commodities);
      const categoryPrices = await getCommodityPricesFromDB(symbols);
      
      if (categoryPrices.length > 0) {
        const gainers = categoryPrices.filter(p => p.change_percent > 0).length;
        const losers = categoryPrices.filter(p => p.change_percent < 0).length;
        const avgChange = categoryPrices.reduce((sum, p) => sum + (p.change_percent || 0), 0) / categoryPrices.length;
        
        summary[categoryKey] = {
          name: categoryData.name,
          total_symbols: symbols.length,
          gainers,
          losers,
          unchanged: categoryPrices.length - gainers - losers,
          avg_change_percent: avgChange,
          top_gainer: categoryPrices.reduce((max, p) => 
            (p.change_percent || 0) > (max.change_percent || 0) ? p : max, categoryPrices[0]),
          top_loser: categoryPrices.reduce((min, p) => 
            (p.change_percent || 0) < (min.change_percent || 0) ? p : min, categoryPrices[0])
        };
      }
    }
    
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
      message: error.message
    });
  }
});

// Get commodity correlations
router.get('/correlations', async (req, res) => {
  try {
    const { symbols, period = '30' } = req.query;
    const symbolList = symbols ? symbols.split(',') : ['GC=F', 'SI=F', 'CL=F', 'DX-Y.NYB'];
    
    // Calculate correlations between commodities
    const correlations = await calculateCommodityCorrelations(symbolList, parseInt(period));
    
    res.json({
      success: true,
      data: correlations
    });
  } catch (error) {
    console.error('Error calculating correlations:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to calculate correlations',
      message: error.message
    });
  }
});

// Get commodity news and analysis
router.get('/news', async (req, res) => {
  try {
    const { category, limit = 20 } = req.query;
    
    // Get commodity-related news
    const news = await getCommodityNews(category, parseInt(limit));
    
    res.json({
      success: true,
      data: news
    });
  } catch (error) {
    console.error('Error fetching commodity news:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch commodity news',
      message: error.message
    });
  }
});

// Helper functions
async function getCommodityPricesFromDB(symbols) {
  try {
    const placeholders = symbols.map((_, i) => `$${i + 1}`).join(',');
    const result = await query(`
      SELECT 
        symbol,
        price,
        change_amount,
        change_percent,
        volume,
        high_52w,
        low_52w,
        updated_at
      FROM commodity_prices 
      WHERE symbol IN (${placeholders})
      AND updated_at > NOW() - INTERVAL '1 hour'
      ORDER BY updated_at DESC
    `, symbols);
    
    return result.rows.map(row => ({
      ...row,
      name: getCommodityName(row.symbol),
      unit: getCommodityUnit(row.symbol)
    }));
  } catch (error) {
    console.error('Error fetching from DB:', error);
    return [];
  }
}

async function getCommodityHistoryFromDB(symbol, period) {
  try {
    const periodMap = {
      '1D': '1 day',
      '1W': '1 week', 
      '1M': '1 month',
      '3M': '3 months',
      '6M': '6 months',
      '1Y': '1 year',
      '2Y': '2 years'
    };
    
    const interval = periodMap[period] || '1 year';
    
    const result = await query(`
      SELECT 
        date,
        open,
        high,
        low,
        close,
        volume
      FROM commodity_price_history 
      WHERE symbol = $1
      AND date > NOW() - INTERVAL '${interval}'
      ORDER BY date ASC
    `, [symbol]);
    
    return result.rows;
  } catch (error) {
    console.error('Error fetching history from DB:', error);
    return [];
  }
}

async function fetchCommodityPricesExternal(symbols) {
  // This would integrate with Yahoo Finance, Alpha Vantage, or other commodity data providers
  // For now, return mock data with realistic structure
  return symbols.map(symbol => ({
    symbol,
    name: getCommodityName(symbol),
    unit: getCommodityUnit(symbol),
    price: Math.random() * 100 + 50,
    change_amount: (Math.random() - 0.5) * 5,
    change_percent: (Math.random() - 0.5) * 10,
    volume: Math.floor(Math.random() * 1000000),
    high_52w: Math.random() * 120 + 80,
    low_52w: Math.random() * 60 + 20,
    updated_at: new Date().toISOString()
  }));
}

async function fetchCommodityHistoryExternal(symbol, period, interval) {
  // Mock historical data
  const days = period === '1Y' ? 365 : period === '6M' ? 180 : 30;
  const data = [];
  let price = 75;
  
  for (let i = days; i >= 0; i--) {
    const date = new Date();
    date.setDate(date.getDate() - i);
    
    const change = (Math.random() - 0.5) * 4;
    price += change;
    const high = price + Math.random() * 2;
    const low = price - Math.random() * 2;
    
    data.push({
      date: date.toISOString().split('T')[0],
      open: price - change,
      high,
      low,
      close: price,
      volume: Math.floor(Math.random() * 1000000)
    });
  }
  
  return data;
}

async function calculateCommodityCorrelations(symbols, days) {
  // Mock correlation matrix
  const correlations = {};
  
  for (const symbol1 of symbols) {
    correlations[symbol1] = {};
    for (const symbol2 of symbols) {
      if (symbol1 === symbol2) {
        correlations[symbol1][symbol2] = 1.0;
      } else {
        correlations[symbol1][symbol2] = (Math.random() - 0.5) * 2;
      }
    }
  }
  
  return correlations;
}

async function getCommodityNews(category, limit) {
  // Mock news data - in production, integrate with news APIs
  const newsItems = [
    {
      id: 1,
      title: "Oil Prices Rise on Supply Concerns",
      summary: "Crude oil futures gained as supply disruptions and strong demand outlook support prices.",
      category: "energy",
      source: "Reuters",
      published_at: new Date(Date.now() - 3600000).toISOString(),
      sentiment: "bullish",
      impact_score: 7.5
    },
    {
      id: 2,
      title: "Gold Holds Steady Amid Dollar Strength", 
      summary: "Gold prices remained relatively stable despite a stronger US dollar as investors await Fed signals.",
      category: "metals",
      source: "Bloomberg",
      published_at: new Date(Date.now() - 7200000).toISOString(),
      sentiment: "neutral",
      impact_score: 5.0
    },
    {
      id: 3,
      title: "Corn Futures Jump on Weather Concerns",
      summary: "Drought conditions in key growing regions boost corn prices as harvest estimates decline.",
      category: "agriculture", 
      source: "AgWeb",
      published_at: new Date(Date.now() - 10800000).toISOString(),
      sentiment: "bullish",
      impact_score: 8.2
    }
  ];
  
  let filtered = newsItems;
  if (category) {
    filtered = newsItems.filter(item => item.category === category);
  }
  
  return filtered.slice(0, limit);
}

function getCommodityName(symbol) {
  for (const category of Object.values(COMMODITY_CATEGORIES)) {
    if (category.commodities[symbol]) {
      return category.commodities[symbol].name;
    }
  }
  return symbol;
}

function getCommodityUnit(symbol) {
  for (const category of Object.values(COMMODITY_CATEGORIES)) {
    if (category.commodities[symbol]) {
      return category.commodities[symbol].unit;
    }
  }
  return 'per unit';
}

module.exports = router;