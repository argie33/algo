/**
 * Sample Data Store for Local Development
 * Provides comprehensive sample data when database is not available
 */

const SAMPLE_STOCKS = [
  {
    symbol: 'AAPL',
    company_name: 'Apple Inc.',
    sector: 'Technology', 
    industry: 'Consumer Electronics',
    exchange: 'NASDAQ',
    price: 175.50,
    volume: 45000000,
    market_cap: 2800000000000,
    pe_ratio: 25.5,
    dividend_yield: 0.52,
    beta: 1.2,
    fifty_two_week_high: 182.00,
    fifty_two_week_low: 124.17,
    is_active: true
  },
  {
    symbol: 'MSFT',
    company_name: 'Microsoft Corporation', 
    sector: 'Technology',
    industry: 'Software',
    exchange: 'NASDAQ',
    price: 350.25,
    volume: 28000000,
    market_cap: 2600000000000,
    pe_ratio: 28.2,
    dividend_yield: 0.75,
    beta: 0.9,
    fifty_two_week_high: 384.52,
    fifty_two_week_low: 224.26,
    is_active: true
  },
  {
    symbol: 'GOOGL',
    company_name: 'Alphabet Inc.',
    sector: 'Technology',
    industry: 'Internet',
    exchange: 'NASDAQ', 
    price: 2750.00,
    volume: 1200000,
    market_cap: 1800000000000,
    pe_ratio: 22.8,
    dividend_yield: 0.00,
    beta: 1.1,
    fifty_two_week_high: 3030.93,
    fifty_two_week_low: 2044.16,
    is_active: true
  },
  {
    symbol: 'TSLA',
    company_name: 'Tesla Inc.',
    sector: 'Consumer Cyclical',
    industry: 'Auto Manufacturers', 
    exchange: 'NASDAQ',
    price: 750.00,
    volume: 25000000,
    market_cap: 750000000000,
    pe_ratio: 45.2,
    dividend_yield: 0.00,
    beta: 2.1,
    fifty_two_week_high: 1243.49,
    fifty_two_week_low: 138.80,
    is_active: true
  },
  {
    symbol: 'AMZN',
    company_name: 'Amazon.com Inc.',
    sector: 'Consumer Cyclical',
    industry: 'Internet Retail',
    exchange: 'NASDAQ',
    price: 3200.00,
    volume: 3500000,
    market_cap: 1600000000000,
    pe_ratio: 52.1,
    dividend_yield: 0.00,
    beta: 1.3,
    fifty_two_week_high: 3773.08,
    fifty_two_week_low: 2671.45,
    is_active: true
  },
  {
    symbol: 'NVDA',
    company_name: 'NVIDIA Corporation',
    sector: 'Technology',
    industry: 'Semiconductors',
    exchange: 'NASDAQ',
    price: 850.00,
    volume: 18000000,
    market_cap: 2100000000000,
    pe_ratio: 68.5,
    dividend_yield: 0.14,
    beta: 1.8,
    fifty_two_week_high: 1037.99,
    fifty_two_week_low: 180.68,
    is_active: true
  },
  {
    symbol: 'JPM',
    company_name: 'JPMorgan Chase & Co.',
    sector: 'Financial Services',
    industry: 'Banks',
    exchange: 'NYSE',
    price: 155.00,
    volume: 12000000,
    market_cap: 450000000000,
    pe_ratio: 11.2,
    dividend_yield: 2.8,
    beta: 1.1,
    fifty_two_week_high: 172.96,
    fifty_two_week_low: 126.06,
    is_active: true
  },
  {
    symbol: 'JNJ',
    company_name: 'Johnson & Johnson',
    sector: 'Healthcare',
    industry: 'Drug Manufacturers',
    exchange: 'NYSE',
    price: 165.00,
    volume: 8000000,
    market_cap: 430000000000,
    pe_ratio: 15.8,
    dividend_yield: 2.9,
    beta: 0.7,
    fifty_two_week_high: 186.69,
    fifty_two_week_low: 143.83,
    is_active: true
  },
  {
    symbol: 'SPY',
    company_name: 'SPDR S&P 500 ETF',
    sector: 'ETF',
    industry: 'Index Fund',
    exchange: 'NYSE',
    price: 420.00,
    volume: 85000000,
    market_cap: 380000000000,
    pe_ratio: 0.0,
    dividend_yield: 1.3,
    beta: 1.0,
    fifty_two_week_high: 459.44,
    fifty_two_week_low: 348.11,
    is_active: true
  },
  {
    symbol: 'QQQ',
    company_name: 'Invesco QQQ Trust',
    sector: 'ETF',
    industry: 'Technology',
    exchange: 'NASDAQ',
    price: 375.00,
    volume: 42000000,
    market_cap: 180000000000,
    pe_ratio: 0.0,
    dividend_yield: 0.5,
    beta: 1.1,
    fifty_two_week_high: 408.71,
    fifty_two_week_low: 284.91,
    is_active: true
  },
  {
    symbol: 'META',
    company_name: 'Meta Platforms Inc.',
    sector: 'Technology',
    industry: 'Internet',
    exchange: 'NASDAQ',
    price: 485.00,
    volume: 15000000,
    market_cap: 800000000000,
    pe_ratio: 24.5,
    dividend_yield: 0.00,
    beta: 1.4,
    fifty_two_week_high: 531.49,
    fifty_two_week_low: 88.09,
    is_active: true
  },
  {
    symbol: 'BRK.B',
    company_name: 'Berkshire Hathaway Inc.',
    sector: 'Financial Services',
    industry: 'Conglomerates', 
    exchange: 'NYSE',
    price: 340.00,
    volume: 3200000,
    market_cap: 750000000000,
    pe_ratio: 8.2,
    dividend_yield: 0.00,
    beta: 0.8,
    fifty_two_week_high: 365.00,
    fifty_two_week_low: 279.00,
    is_active: true
  },
  {
    symbol: 'V',
    company_name: 'Visa Inc.',
    sector: 'Financial Services',
    industry: 'Credit Services',
    exchange: 'NYSE', 
    price: 240.00,
    volume: 6500000,
    market_cap: 500000000000,
    pe_ratio: 32.1,
    dividend_yield: 0.7,
    beta: 0.9,
    fifty_two_week_high: 252.67,
    fifty_two_week_low: 184.60,
    is_active: true
  },
  {
    symbol: 'UNH',
    company_name: 'UnitedHealth Group Inc.',
    sector: 'Healthcare',
    industry: 'Healthcare Plans',
    exchange: 'NYSE',
    price: 520.00,
    volume: 2800000,
    market_cap: 480000000000,
    pe_ratio: 25.3,
    dividend_yield: 1.3,
    beta: 0.7,
    fifty_two_week_high: 553.29,
    fifty_two_week_low: 445.68,
    is_active: true
  },
  {
    symbol: 'HD',
    company_name: 'The Home Depot Inc.',
    sector: 'Consumer Cyclical',
    industry: 'Home Improvement Retail',
    exchange: 'NYSE',
    price: 315.00,
    volume: 4200000,
    market_cap: 350000000000,
    pe_ratio: 19.8,
    dividend_yield: 2.4,
    beta: 1.0,
    fifty_two_week_high: 345.69,
    fifty_two_week_low: 264.51,
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
  },
  {
    user_id: 'demo@example.com', 
    symbol: 'MSFT',
    quantity: 50.00,
    avg_cost: 300.00,
    current_price: 350.25,
    market_value: 17512.50,
    unrealized_pl: 2512.50,
    sector: 'Technology',
    industry: 'Software',
    company: 'Microsoft Corporation'
  },
  {
    user_id: 'demo@example.com',
    symbol: 'GOOGL', 
    quantity: 10.00,
    avg_cost: 2500.00,
    current_price: 2750.00,
    market_value: 27500.00,
    unrealized_pl: 2500.00,
    sector: 'Technology',
    industry: 'Internet',
    company: 'Alphabet Inc.'
  },
  {
    user_id: 'demo@example.com',
    symbol: 'TSLA',
    quantity: 25.00,
    avg_cost: 800.00,
    current_price: 750.00,
    market_value: 18750.00,
    unrealized_pl: -1250.00,
    sector: 'Consumer Cyclical',
    industry: 'Auto Manufacturers',
    company: 'Tesla Inc.'
  },
  {
    user_id: 'demo@example.com',
    symbol: 'AMZN',
    quantity: 15.00,
    avg_cost: 3000.00,
    current_price: 3200.00,
    market_value: 48000.00,
    unrealized_pl: 3000.00,
    sector: 'Consumer Cyclical',
    industry: 'Internet Retail',
    company: 'Amazon.com Inc.'
  }
];

const SAMPLE_PORTFOLIO_METADATA = {
  user_id: 'demo@example.com',
  total_equity: 162562.50,
  total_market_value: 156962.50,
  buying_power: 50000.00,
  cash: 5600.00,
  account_type: 'paper'
};

/**
 * Filter stocks based on screening criteria
 */
function filterStocks(stocks, filters = {}) {
  let filtered = [...stocks];
  
  // Search filter
  if (filters.search) {
    const searchTerm = filters.search.toLowerCase();
    filtered = filtered.filter(stock => 
      stock.symbol.toLowerCase().includes(searchTerm) ||
      stock.company_name.toLowerCase().includes(searchTerm)
    );
  }
  
  // Sector filter
  if (filters.sector && filters.sector !== 'all') {
    filtered = filtered.filter(stock => stock.sector === filters.sector);
  }
  
  // Industry filter
  if (filters.industry) {
    filtered = filtered.filter(stock => stock.industry === filters.industry);
  }
  
  // Exchange filter
  if (filters.exchange) {
    filtered = filtered.filter(stock => stock.exchange === filters.exchange);
  }
  
  // Price range filters
  if (filters.priceMin) {
    filtered = filtered.filter(stock => stock.price >= parseFloat(filters.priceMin));
  }
  if (filters.priceMax) {
    filtered = filtered.filter(stock => stock.price <= parseFloat(filters.priceMax));
  }
  
  // Market cap filters  
  if (filters.marketCapMin) {
    filtered = filtered.filter(stock => stock.market_cap >= parseInt(filters.marketCapMin));
  }
  if (filters.marketCapMax) {
    filtered = filtered.filter(stock => stock.market_cap <= parseInt(filters.marketCapMax));
  }
  
  // PE ratio filters
  if (filters.peRatioMin) {
    filtered = filtered.filter(stock => stock.pe_ratio >= parseFloat(filters.peRatioMin));
  }
  if (filters.peRatioMax) {
    filtered = filtered.filter(stock => stock.pe_ratio <= parseFloat(filters.peRatioMax));
  }
  
  // Dividend yield filters
  if (filters.dividendYieldMin) {
    filtered = filtered.filter(stock => stock.dividend_yield >= parseFloat(filters.dividendYieldMin));
  }
  if (filters.dividendYieldMax) {
    filtered = filtered.filter(stock => stock.dividend_yield <= parseFloat(filters.dividendYieldMax));
  }
  
  return filtered;
}

/**
 * Sort stocks based on criteria
 */
function sortStocks(stocks, sortBy = 'market_cap', sortOrder = 'desc') {
  const sorted = [...stocks];
  
  sorted.sort((a, b) => {
    let aVal = a[sortBy];
    let bVal = b[sortBy];
    
    // Handle numeric sorting
    if (typeof aVal === 'number' && typeof bVal === 'number') {
      return sortOrder.toLowerCase() === 'desc' ? bVal - aVal : aVal - bVal;
    }
    
    // Handle string sorting
    if (typeof aVal === 'string' && typeof bVal === 'string') {
      aVal = aVal.toLowerCase();
      bVal = bVal.toLowerCase();
      if (sortOrder.toLowerCase() === 'desc') {
        return bVal.localeCompare(aVal);
      } else {
        return aVal.localeCompare(bVal);
      }
    }
    
    return 0;
  });
  
  return sorted;
}

/**
 * Get paginated stock screening results
 */
function getScreenerResults(filters = {}, page = 1, limit = 25) {
  // Apply filters
  let filtered = filterStocks(SAMPLE_STOCKS, filters);
  
  // Apply sorting
  const sortBy = filters.sortBy || 'market_cap';
  const sortOrder = filters.sortOrder || 'desc';
  filtered = sortStocks(filtered, sortBy, sortOrder);
  
  // Calculate pagination
  const total = filtered.length;
  const totalPages = Math.ceil(total / limit);
  const offset = (page - 1) * limit;
  const paginatedResults = filtered.slice(offset, offset + limit);
  
  return {
    success: true,
    data: paginatedResults,
    pagination: {
      page: parseInt(page),
      limit: parseInt(limit),
      total: total,
      totalPages: totalPages,
      hasNext: page < totalPages,
      hasPrev: page > 1
    },
    metadata: {
      total_matching_stocks: total,
      development_mode: true,
      data_source: 'sample_data_store'
    },
    timestamp: new Date().toISOString()
  };
}

/**
 * Get portfolio data
 */
function getPortfolioData(userId = 'demo@example.com') {
  const holdings = SAMPLE_PORTFOLIO.filter(h => h.user_id === userId);
  
  return {
    success: true,
    data: {
      holdings: holdings,
      metadata: SAMPLE_PORTFOLIO_METADATA,
      total_holdings: holdings.length
    }
  };
}

/**
 * Get market overview data
 */
function getMarketOverview(limit = 20) {
  const sortedStocks = sortStocks(SAMPLE_STOCKS, 'market_cap', 'desc');
  const topStocks = sortedStocks.slice(0, limit);
  
  return {
    success: true,
    data: topStocks,
    count: topStocks.length
  };
}

module.exports = {
  SAMPLE_STOCKS,
  SAMPLE_PORTFOLIO,
  SAMPLE_PORTFOLIO_METADATA,
  getScreenerResults,
  getPortfolioData,
  getMarketOverview,
  filterStocks,
  sortStocks
};