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

// Get COT (Commitment of Traders) data
router.get('/cot/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const { weeks = 26 } = req.query;
    
    const cotData = await getCOTData(symbol, parseInt(weeks));
    
    res.json({
      success: true,
      data: cotData,
      symbol: symbol
    });
  } catch (error) {
    console.error('Error fetching COT data:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch COT data',
      message: error.message
    });
  }
});

// Get seasonality data
router.get('/seasonality/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    
    const seasonalityData = await getSeasonalityData(symbol);
    
    res.json({
      success: true,
      data: seasonalityData,
      symbol: symbol
    });
  } catch (error) {
    console.error('Error fetching seasonality data:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch seasonality data',
      message: error.message
    });
  }
});

// Get supply/demand data
router.get('/supply-demand/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const { weeks = 12 } = req.query;
    
    const supplyDemandData = await getSupplyDemandData(symbol, parseInt(weeks));
    
    res.json({
      success: true,
      data: supplyDemandData,
      symbol: symbol
    });
  } catch (error) {
    console.error('Error fetching supply/demand data:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch supply/demand data',
      message: error.message
    });
  }
});

// Get trading signals based on COT and technical analysis
router.get('/signals/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    
    const signals = await generateTradingSignals(symbol);
    
    res.json({
      success: true,
      data: signals,
      symbol: symbol
    });
  } catch (error) {
    console.error('Error generating trading signals:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to generate trading signals',
      message: error.message
    });
  }
});

// Get commodity performance metrics
router.get('/metrics/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    
    const metrics = await getCommodityMetrics(symbol);
    
    res.json({
      success: true,
      data: metrics,
      symbol: symbol
    });
  } catch (error) {
    console.error('Error fetching commodity metrics:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch commodity metrics',
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

async function getCOTData(symbol, weeks) {
  try {
    const result = await query(`
      SELECT 
        report_date,
        commercial_long,
        commercial_short,
        commercial_net,
        non_commercial_long,
        non_commercial_short,
        non_commercial_net,
        open_interest
      FROM cot_data 
      WHERE symbol = $1
      ORDER BY report_date DESC
      LIMIT $2
    `, [symbol, weeks]);
    
    return result.rows.map(row => ({
      ...row,
      week: row.report_date,
      commercial_net_pct: row.open_interest > 0 ? (row.commercial_net / row.open_interest * 100) : 0,
      non_commercial_net_pct: row.open_interest > 0 ? (row.non_commercial_net / row.open_interest * 100) : 0
    }));
  } catch (error) {
    console.error('Error fetching COT data:', error);
    return [];
  }
}

async function getSeasonalityData(symbol) {
  try {
    const result = await query(`
      SELECT 
        month,
        avg_return,
        win_rate,
        volatility,
        years_data
      FROM commodity_seasonality 
      WHERE symbol = $1
      ORDER BY month
    `, [symbol]);
    
    // Add month names
    const monthNames = [
      'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
    ];
    
    return result.rows.map(row => ({
      ...row,
      month_name: monthNames[row.month - 1],
      avg_return_pct: row.avg_return * 100,
      strength: row.win_rate > 60 ? 'Strong' : row.win_rate > 40 ? 'Moderate' : 'Weak'
    }));
  } catch (error) {
    console.error('Error fetching seasonality data:', error);
    return [];
  }
}

async function getSupplyDemandData(symbol, weeks) {
  try {
    const result = await query(`
      SELECT 
        report_date,
        supply_level,
        demand_level,
        inventory_level,
        supply_change_weekly,
        demand_change_weekly,
        inventory_change_weekly
      FROM commodity_supply_demand 
      WHERE symbol = $1
      ORDER BY report_date DESC
      LIMIT $2
    `, [symbol, weeks]);
    
    return result.rows;
  } catch (error) {
    console.error('Error fetching supply/demand data:', error);
    // Return mock data for now
    return Array.from({ length: weeks }, (_, i) => {
      const date = new Date();
      date.setDate(date.getDate() - i * 7);
      return {
        report_date: date.toISOString().split('T')[0],
        supply_level: Math.random() * 1000000 + 500000,
        demand_level: Math.random() * 1000000 + 500000,
        inventory_level: Math.random() * 500000 + 200000,
        supply_change_weekly: (Math.random() - 0.5) * 50000,
        demand_change_weekly: (Math.random() - 0.5) * 50000,
        inventory_change_weekly: (Math.random() - 0.5) * 30000
      };
    });
  }
}

async function generateTradingSignals(symbol) {
  try {
    // Get recent COT data
    const cotData = await getCOTData(symbol, 4);
    
    // Get recent price data
    const priceData = await getCommodityHistoryFromDB(symbol, '1M');
    
    // Get seasonality data
    const seasonalityData = await getSeasonalityData(symbol);
    const currentMonth = new Date().getMonth() + 1;
    const currentSeasonality = seasonalityData.find(s => s.month === currentMonth);
    
    const signals = [];
    
    // COT-based signals
    if (cotData.length >= 2) {
      const latest = cotData[0];
      const previous = cotData[1];
      
      // Smart money signal
      if (latest.commercial_net > previous.commercial_net && latest.commercial_net > 0) {
        signals.push({
          type: 'COT_BULLISH',
          strength: 'Strong',
          signal: 'BUY',
          reason: 'Commercial traders (smart money) increasing long positions',
          confidence: 85,
          timeframe: 'Medium-term'
        });
      } else if (latest.commercial_net < previous.commercial_net && latest.commercial_net < 0) {
        signals.push({
          type: 'COT_BEARISH',
          strength: 'Strong',
          signal: 'SELL',
          reason: 'Commercial traders (smart money) increasing short positions',
          confidence: 85,
          timeframe: 'Medium-term'
        });
      }
      
      // Contrarian signal from non-commercial (speculative) positioning
      if (latest.non_commercial_net_pct > 20) {
        signals.push({
          type: 'CONTRARIAN_BEARISH',
          strength: 'Moderate',
          signal: 'SELL',
          reason: 'Excessive speculative long positioning - contrarian signal',
          confidence: 65,
          timeframe: 'Short-term'
        });
      } else if (latest.non_commercial_net_pct < -20) {
        signals.push({
          type: 'CONTRARIAN_BULLISH',
          strength: 'Moderate',
          signal: 'BUY',
          reason: 'Excessive speculative short positioning - contrarian signal',
          confidence: 65,
          timeframe: 'Short-term'
        });
      }
    }
    
    // Seasonal signal
    if (currentSeasonality) {
      if (currentSeasonality.win_rate > 60 && currentSeasonality.avg_return_pct > 1) {
        signals.push({
          type: 'SEASONAL_BULLISH',
          strength: 'Moderate',
          signal: 'BUY',
          reason: `Historically strong month (${currentSeasonality.win_rate}% win rate)`,
          confidence: 60,
          timeframe: 'Seasonal'
        });
      } else if (currentSeasonality.win_rate < 40 && currentSeasonality.avg_return_pct < -1) {
        signals.push({
          type: 'SEASONAL_BEARISH',
          strength: 'Moderate',
          signal: 'SELL',
          reason: `Historically weak month (${currentSeasonality.win_rate}% win rate)`,
          confidence: 60,
          timeframe: 'Seasonal'
        });
      }
    }
    
    // Technical signals (simplified)
    if (priceData.length >= 20) {
      const recent = priceData.slice(-20);
      const sma10 = recent.slice(-10).reduce((sum, d) => sum + d.close, 0) / 10;
      const sma20 = recent.reduce((sum, d) => sum + d.close, 0) / 20;
      const currentPrice = recent[recent.length - 1].close;
      
      if (sma10 > sma20 && currentPrice > sma10) {
        signals.push({
          type: 'TECHNICAL_BULLISH',
          strength: 'Moderate',
          signal: 'BUY',
          reason: 'Price above moving averages with bullish crossover',
          confidence: 70,
          timeframe: 'Short-term'
        });
      } else if (sma10 < sma20 && currentPrice < sma10) {
        signals.push({
          type: 'TECHNICAL_BEARISH',
          strength: 'Moderate',
          signal: 'SELL',
          reason: 'Price below moving averages with bearish crossover',
          confidence: 70,
          timeframe: 'Short-term'
        });
      }
    }
    
    return signals;
  } catch (error) {
    console.error('Error generating trading signals:', error);
    return [];
  }
}

async function getCommodityMetrics(symbol) {
  try {
    // Get current price data
    const currentPrice = await getCommodityPricesFromDB([symbol]);
    
    // Get historical data for calculations
    const historyData = await getCommodityHistoryFromDB(symbol, '1Y');
    
    // Get COT data
    const cotData = await getCOTData(symbol, 1);
    
    // Get seasonality data
    const seasonalityData = await getSeasonalityData(symbol);
    const currentMonth = new Date().getMonth() + 1;
    const currentSeasonality = seasonalityData.find(s => s.month === currentMonth);
    
    if (currentPrice.length === 0 || historyData.length === 0) {
      return null;
    }
    
    const price = currentPrice[0];
    const history = historyData;
    
    // Calculate metrics
    const prices = history.map(h => h.close);
    const returns = prices.slice(1).map((p, i) => (p - prices[i]) / prices[i]);
    
    const volatility = Math.sqrt(returns.reduce((sum, r) => sum + r * r, 0) / returns.length) * Math.sqrt(252);
    const sharpeRatio = returns.reduce((sum, r) => sum + r, 0) / returns.length / (volatility / Math.sqrt(252));
    
    // Support and resistance levels
    const high52w = Math.max(...prices);
    const low52w = Math.min(...prices);
    const currentPriceNum = parseFloat(price.price);
    const pricePosition = (currentPriceNum - low52w) / (high52w - low52w);
    
    // RSI calculation (simplified)
    const rsiPeriod = 14;
    const recentPrices = prices.slice(-rsiPeriod - 1);
    const gains = [];
    const losses = [];
    
    for (let i = 1; i < recentPrices.length; i++) {
      const change = recentPrices[i] - recentPrices[i - 1];
      if (change > 0) {
        gains.push(change);
        losses.push(0);
      } else {
        gains.push(0);
        losses.push(Math.abs(change));
      }
    }
    
    const avgGain = gains.reduce((sum, g) => sum + g, 0) / gains.length;
    const avgLoss = losses.reduce((sum, l) => sum + l, 0) / losses.length;
    const rs = avgGain / avgLoss;
    const rsi = 100 - (100 / (1 + rs));
    
    return {
      symbol,
      current_price: currentPriceNum,
      price_change_pct: price.change_percent,
      volatility_annual: volatility * 100,
      sharpe_ratio: sharpeRatio,
      rsi: rsi,
      price_position_52w: pricePosition,
      support_level: low52w,
      resistance_level: high52w,
      seasonal_strength: currentSeasonality ? currentSeasonality.strength : 'Unknown',
      seasonal_win_rate: currentSeasonality ? currentSeasonality.win_rate : null,
      cot_commercial_net: cotData.length > 0 ? cotData[0].commercial_net : null,
      cot_signal: cotData.length > 0 ? (cotData[0].commercial_net > 0 ? 'Bullish' : 'Bearish') : null,
      overall_score: calculateOverallScore(rsi, pricePosition, currentSeasonality, cotData),
      updated_at: new Date().toISOString()
    };
  } catch (error) {
    console.error('Error calculating commodity metrics:', error);
    return null;
  }
}

function calculateOverallScore(rsi, pricePosition, seasonality, cotData) {
  let score = 50; // Start neutral
  
  // RSI component
  if (rsi < 30) score += 15; // Oversold
  else if (rsi > 70) score -= 15; // Overbought
  
  // Price position component
  if (pricePosition < 0.3) score += 10; // Near lows
  else if (pricePosition > 0.7) score -= 10; // Near highs
  
  // Seasonal component
  if (seasonality && seasonality.win_rate > 60) score += 10;
  else if (seasonality && seasonality.win_rate < 40) score -= 10;
  
  // COT component
  if (cotData.length > 0) {
    if (cotData[0].commercial_net > 0) score += 15; // Smart money bullish
    else score -= 15; // Smart money bearish
  }
  
  return Math.max(0, Math.min(100, score));
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