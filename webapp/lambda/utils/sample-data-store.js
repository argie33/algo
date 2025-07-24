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
  return {
    success: true,
    data: SAMPLE_STOCKS.slice(0, limit),
    pagination: {
      page: parseInt(page),
      limit: parseInt(limit),
      total: SAMPLE_STOCKS.length,
      totalPages: Math.ceil(SAMPLE_STOCKS.length / limit),
      hasNext: page < Math.ceil(SAMPLE_STOCKS.length / limit),
      hasPrev: page > 1
    },
    metadata: {
      total_matching_stocks: SAMPLE_STOCKS.length,
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