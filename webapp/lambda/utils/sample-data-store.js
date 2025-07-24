/**
 * Sample Data Store for Local Development
 * Provides comprehensive sample data when database is not available
 */

const SAMPLE_STOCKS = [
  {
    symbol: 'AAPL',
    fullName: 'Apple Inc.',
    displayName: 'Apple Inc.',
    shortName: 'Apple Inc.',
    name: 'Apple Inc.',
    sector: 'Technology', 
    industry: 'Consumer Electronics',
    exchange: 'NASDAQ',
    marketCap: 2800000000000,
    volume: 45000000,
    price: {
      current: 175.50,
      previousClose: 173.73,
      dayLow: 172.11,
      dayHigh: 179.01,
      fiftyTwoWeekLow: 124.17,
      fiftyTwoWeekHigh: 182.00
    },
    financialMetrics: {
      marketCap: 2800000000000,
      trailingPE: 25.5,
      dividendYield: 0.0052,
      beta: 1.2
    },
    is_active: true
  },
  {
    symbol: 'MSFT',
    fullName: 'Microsoft Corporation',
    displayName: 'Microsoft Corporation',
    shortName: 'Microsoft Corporation', 
    name: 'Microsoft Corporation',
    sector: 'Technology',
    industry: 'Software',
    exchange: 'NASDAQ',
    marketCap: 2600000000000,
    volume: 28000000,
    price: {
      current: 350.25,
      previousClose: 346.75,
      dayLow: 343.24,
      dayHigh: 357.26,
      fiftyTwoWeekLow: 224.26,
      fiftyTwoWeekHigh: 384.52
    },
    financialMetrics: {
      marketCap: 2600000000000,
      trailingPE: 28.2,
      dividendYield: 0.0075,
      beta: 0.9
    },
    is_active: true
  },
  {
    symbol: 'GOOGL',
    fullName: 'Alphabet Inc.',
    displayName: 'Alphabet Inc.',
    shortName: 'Alphabet Inc.',
    name: 'Alphabet Inc.',
    sector: 'Technology',
    industry: 'Internet',
    exchange: 'NASDAQ',
    marketCap: 1800000000000,
    volume: 1200000,
    price: {
      current: 2750.00,
      previousClose: 2722.50,
      dayLow: 2695.00,
      dayHigh: 2805.00,
      fiftyTwoWeekLow: 2044.16,
      fiftyTwoWeekHigh: 3030.93
    },
    financialMetrics: {
      marketCap: 1800000000000,
      trailingPE: 22.8,
      dividendYield: 0.0,
      beta: 1.1
    },
    is_active: true
  },
  {
    symbol: 'TSLA',
    fullName: 'Tesla, Inc.',
    displayName: 'Tesla, Inc.',
    shortName: 'Tesla, Inc.',
    name: 'Tesla, Inc.',
    sector: 'Consumer Cyclical',
    industry: 'Auto Manufacturers',
    exchange: 'NASDAQ',
    marketCap: 800000000000,
    volume: 75000000,
    price: {
      current: 250.80,
      previousClose: 248.33,
      dayLow: 243.78,
      dayHigh: 255.82,
      fiftyTwoWeekLow: 101.81,
      fiftyTwoWeekHigh: 414.50
    },
    financialMetrics: {
      marketCap: 800000000000,
      trailingPE: 45.7,
      dividendYield: 0.0,
      beta: 2.1
    },
    is_active: true
  },
  {
    symbol: 'AMZN',
    fullName: 'Amazon.com, Inc.',
    displayName: 'Amazon.com, Inc.',
    shortName: 'Amazon.com, Inc.',
    name: 'Amazon.com, Inc.',
    sector: 'Consumer Cyclical',
    industry: 'Internet Retail',
    exchange: 'NASDAQ',
    marketCap: 1500000000000,
    volume: 35000000,
    price: {
      current: 145.25,
      previousClose: 143.80,
      dayLow: 142.32,
      dayHigh: 148.13,
      fiftyTwoWeekLow: 81.43,
      fiftyTwoWeekHigh: 188.11
    },
    financialMetrics: {
      marketCap: 1500000000000,
      trailingPE: 52.3,
      dividendYield: 0.0,
      beta: 1.3
    },
    is_active: true
  },
  {
    symbol: 'NVDA',
    fullName: 'NVIDIA Corporation',
    displayName: 'NVIDIA Corporation',
    shortName: 'NVIDIA Corporation',
    name: 'NVIDIA Corporation',
    sector: 'Technology',
    industry: 'Semiconductors',
    exchange: 'NASDAQ',
    marketCap: 1200000000000,
    volume: 45000000,
    price: {
      current: 485.60,
      previousClose: 479.34,
      dayLow: 476.73,
      dayHigh: 494.91,
      fiftyTwoWeekLow: 108.13,
      fiftyTwoWeekHigh: 502.66
    },
    financialMetrics: {
      marketCap: 1200000000000,
      trailingPE: 65.2,
      dividendYield: 0.0009,
      beta: 1.7
    },
    is_active: true
  },
  {
    symbol: 'META',
    fullName: 'Meta Platforms, Inc.',
    displayName: 'Meta Platforms, Inc.',
    shortName: 'Meta Platforms, Inc.',
    name: 'Meta Platforms, Inc.',
    sector: 'Communication Services',
    industry: 'Internet',
    exchange: 'NASDAQ',
    marketCap: 800000000000,
    volume: 22000000,
    price: {
      current: 315.40,
      previousClose: 312.05,
      dayLow: 308.22,
      dayHigh: 321.58,
      fiftyTwoWeekLow: 88.09,
      fiftyTwoWeekHigh: 384.33
    },
    financialMetrics: {
      marketCap: 800000000000,
      trailingPE: 23.1,
      dividendYield: 0.0044,
      beta: 1.3
    },
    is_active: true
  },
  {
    symbol: 'BRK.A',
    fullName: 'Berkshire Hathaway Inc.',
    displayName: 'Berkshire Hathaway Inc.',
    shortName: 'Berkshire Hathaway Inc.',
    name: 'Berkshire Hathaway Inc.',
    sector: 'Financial Services',
    industry: 'Insurance',
    exchange: 'NYSE',
    marketCap: 900000000000,
    volume: 8500,
    price: {
      current: 545000.00,
      previousClose: 539500.00,
      dayLow: 536100.00,
      dayHigh: 551900.00,
      fiftyTwoWeekLow: 394000.00,
      fiftyTwoWeekHigh: 571000.00
    },
    financialMetrics: {
      marketCap: 900000000000,
      trailingPE: 8.9,
      dividendYield: 0.0,
      beta: 0.9
    },
    is_active: true
  },
  {
    symbol: 'JNJ',
    fullName: 'Johnson & Johnson',
    displayName: 'Johnson & Johnson',
    shortName: 'Johnson & Johnson',
    name: 'Johnson & Johnson',
    sector: 'Healthcare',
    industry: 'Drug Manufacturers',
    exchange: 'NYSE',
    marketCap: 450000000000,
    volume: 12000000,
    price: {
      current: 170.25,
      previousClose: 168.55,
      dayLow: 167.05,
      dayHigh: 173.45,
      fiftyTwoWeekLow: 142.04,
      fiftyTwoWeekHigh: 178.84
    },
    financialMetrics: {
      marketCap: 450000000000,
      trailingPE: 15.7,
      dividendYield: 0.0295,
      beta: 0.7
    },
    is_active: true
  },
  {
    symbol: 'V',
    fullName: 'Visa Inc.',
    displayName: 'Visa Inc.',
    shortName: 'Visa Inc.',
    name: 'Visa Inc.',
    sector: 'Financial Services',
    industry: 'Credit Services',
    exchange: 'NYSE',
    marketCap: 520000000000,
    volume: 7500000,
    price: {
      current: 260.75,
      previousClose: 258.34,
      dayLow: 256.56,
      dayHigh: 265.94,
      fiftyTwoWeekLow: 184.60,
      fiftyTwoWeekHigh: 276.54
    },
    financialMetrics: {
      marketCap: 520000000000,
      trailingPE: 32.4,
      dividendYield: 0.0078,
      beta: 0.9
    },
    is_active: true
  }
];

const SAMPLE_PORTFOLIO = [
  {
    user_id: 'demo@example.com',
    symbol: 'AAPL',
    quantity: 100.00,
    avg_cost: 150.00,
    current_price: 175.50,
    market_value: 17550.00,
    unrealized_pl: 2550.00,
    sector: 'Technology',
    industry: 'Consumer Electronics',
    company: 'Apple Inc.'
  }
];

/**
 * Get paginated stock screening results
 */
function getScreenerResults(filters = {}, page = 1, limit = 25) {
  let filteredStocks = [...SAMPLE_STOCKS];
  
  // Apply search filter
  if (filters.search && filters.search.trim()) {
    const searchTerm = filters.search.trim().toUpperCase();
    filteredStocks = filteredStocks.filter(stock => 
      stock.symbol.toUpperCase().includes(searchTerm) ||
      stock.name.toUpperCase().includes(searchTerm)
    );
  }
  
  // Apply sector filter
  if (filters.sector && filters.sector !== 'all' && filters.sector !== '') {
    filteredStocks = filteredStocks.filter(stock => stock.sector === filters.sector);
  }
  
  // Apply exchange filter
  if (filters.exchange && filters.exchange !== 'all' && filters.exchange !== '') {
    filteredStocks = filteredStocks.filter(stock => stock.exchange === filters.exchange);
  }
  
  // Apply sorting
  const sortBy = filters.sortBy || 'symbol';
  const sortOrder = filters.sortOrder || 'asc';
  
  filteredStocks.sort((a, b) => {
    let aVal, bVal;
    
    switch (sortBy) {
      case 'symbol':
        aVal = a.symbol;
        bVal = b.symbol;
        break;
      case 'exchange':
        aVal = a.exchange;
        bVal = b.exchange;
        break;
      case 'marketCap':
        aVal = a.marketCap || 0;
        bVal = b.marketCap || 0;
        break;
      case 'currentPrice':
        aVal = a.price?.current || 0;
        bVal = b.price?.current || 0;
        break;
      case 'volume':
        aVal = a.volume || 0;
        bVal = b.volume || 0;
        break;
      default:
        aVal = a.symbol;
        bVal = b.symbol;
    }
    
    if (typeof aVal === 'string') {
      const comparison = aVal.localeCompare(bVal);
      return sortOrder.toLowerCase() === 'desc' ? -comparison : comparison;
    } else {
      const comparison = aVal - bVal;
      return sortOrder.toLowerCase() === 'desc' ? -comparison : comparison;
    }
  });
  
  // Apply pagination
  const startIndex = (parseInt(page) - 1) * parseInt(limit);
  const endIndex = startIndex + parseInt(limit);
  const paginatedStocks = filteredStocks.slice(startIndex, endIndex);
  
  return {
    success: true,
    data: paginatedStocks,
    total: filteredStocks.length,
    pagination: {
      page: parseInt(page),
      limit: parseInt(limit),
      total: filteredStocks.length,
      totalPages: Math.ceil(filteredStocks.length / parseInt(limit)),
      hasNext: parseInt(page) < Math.ceil(filteredStocks.length / parseInt(limit)),
      hasPrev: parseInt(page) > 1
    },
    metadata: {
      total_matching_stocks: filteredStocks.length,
      development_mode: true,
      data_source: 'sample_data_store'
    },
    timestamp: new Date().toISOString()
  };
}

module.exports = {
  SAMPLE_STOCKS,
  SAMPLE_PORTFOLIO,
  getScreenerResults
};