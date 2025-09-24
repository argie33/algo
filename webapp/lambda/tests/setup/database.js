/**
 * Test database configuration and mock setup
 * Uses actual loader table schemas without requiring real database connection
 */

const { Pool } = require('pg');

// Mock database responses based on actual loader schemas
const mockData = {
  // fundamental_metrics table (from loadfundamentalmetrics.py)
  fundamental_metrics: [
    {
      symbol: 'AAPL',
      market_cap: 3000000000000,
      pe_ratio: 28.5,
      forward_pe: 26.2,
      price_to_book: 45.8,
      price_to_sales: 7.2,
      dividend_yield: 0.44,
      beta: 1.2,
      sector: 'Technology',
      industry: 'Consumer Electronics',
      revenue: 394328000000,
      net_income: 99803000000,
      earnings_per_share: 6.05,
      current_ratio: 1.1,
      return_on_equity: 0.26,
      updated_at: new Date()
    },
    {
      symbol: 'MSFT',
      market_cap: 2800000000000,
      pe_ratio: 32.1,
      forward_pe: 29.8,
      price_to_book: 12.9,
      price_to_sales: 12.8,
      dividend_yield: 0.68,
      beta: 0.9,
      sector: 'Technology',
      industry: 'Software—Infrastructure',
      revenue: 211915000000,
      net_income: 72361000000,
      earnings_per_share: 9.65,
      current_ratio: 1.4,
      return_on_equity: 0.45,
      updated_at: new Date()
    }
  ],

  // price_daily table (from loadpricedaily.py)
  price_daily: [
    {
      symbol: 'AAPL',
      date: new Date(),
      open: 174.0,
      high: 176.5,
      low: 173.2,
      close: 175.8,
      adj_close: 175.8,
      volume: 55000000,
      dividends: 0,
      splits: 0,
      fetched_at: new Date()
    },
    {
      symbol: 'MSFT',
      date: new Date(),
      open: 415.2,
      high: 418.9,
      low: 412.1,
      close: 416.8,
      adj_close: 416.8,
      volume: 22000000,
      dividends: 0,
      splits: 0,
      fetched_at: new Date()
    }
  ],

  // positioning_metrics table (from loadpositioning.py)
  positioning_metrics: [
    {
      symbol: 'AAPL',
      date: new Date(),
      institutional_ownership_pct: 0.6234,
      smart_money_score: 0.7821,
      insider_sentiment_score: 0.2341,
      options_sentiment: 0.1234,
      short_squeeze_score: 0.3456,
      composite_positioning_score: 0.4567,
      created_at: new Date(),
      updated_at: new Date()
    }
  ],

  // retail_sentiment table (from loadsentiment.py)
  retail_sentiment: [
    {
      symbol: 'AAPL',
      date: new Date(),
      bullish_percentage: 65.2,
      bearish_percentage: 20.8,
      neutral_percentage: 14.0,
      net_sentiment: 44.4,
      source: 'retail_tracker',
      created_at: new Date()
    }
  ],

  // market_data table (from loadmarket.py)
  market_data: [
    {
      ticker: 'AAPL',
      current_price: 175.8,
      regular_market_price: 175.8,
      volume: 55000000,
      regular_market_volume: 55000000,
      market_cap: 3000000000000,
      fifty_two_week_high: 199.62,
      fifty_two_week_low: 164.08,
      updated_at: new Date()
    }
  ],

  // stock_news table (from loadnews.py)
  stock_news: [
    {
      ticker: 'AAPL',
      title: 'Apple Reports Strong Q4 Earnings',
      summary: 'Apple Inc. reported better than expected earnings for Q4',
      publish_time: new Date(Date.now() - 2 * 60 * 60 * 1000), // 2 hours ago
      provider: 'Financial News',
      sentiment_score: 0.75,
      created_at: new Date()
    }
  ],

  // analyst_sentiment_analysis table (from loadsentiment.py)
  analyst_sentiment_analysis: [
    {
      symbol: 'AAPL',
      date: new Date(),
      analyst_count: 25,
      strong_buy_count: 8,
      buy_count: 12,
      hold_count: 4,
      sell_count: 1,
      strong_sell_count: 0,
      average_rating: 2.1,
      target_price: 185.50,
      sentiment_score: 0.72,
      created_at: new Date(),
      updated_at: new Date()
    }
  ]
};

// Mock query function that returns data based on SQL patterns
function mockQuery(sql, params = []) {
  const query = sql.toLowerCase();

  // Handle JOIN queries from stocks route
  if (query.includes('fundamental_metrics f') && query.includes('left join price_daily pd')) {
    // Simulate JOIN result with both fundamental_metrics and price_daily columns
    // Match the expected structure from stocks.js route
    return Promise.resolve({
      rows: [
        {
          symbol: 'AAPL',
          name: 'AAPL', // API uses symbol as name fallback
          company_name: 'Apple Inc.',
          security_name: 'Apple Inc.',
          short_name: 'Apple',
          long_name: 'Apple Inc.',
          display_name: 'Apple Inc.',
          sector: 'Technology',
          industry: 'Consumer Electronics',
          market_cap: 3000000000000,
          current_price: 175.8,
          volume: 55000000,
          pe_ratio: 28.5,
          dividend_yield: 0.44,
          beta: 1.2,
          exchange: 'NASDAQ',
          earnings_per_share: 6.05,
          previous_close: 174.0,

          // Price data from LEFT JOIN
          open: 174.0,
          high: 176.5,
          low: 173.2,
          close: 175.8,
          adj_close: 175.8,
          price_date: new Date(),

          // Additional fields expected by the API transformation
          market_category: 'Standard',
          etf: 'N',
          quote_type: 'EQUITY',

          // Financial metrics fields (mapped from fundamental_metrics schema)
          trailing_pe: 28.5, // pe_ratio
          forward_pe: 26.2, // forward_pe
          price_to_sales_ttm: 7.2, // price_to_sales
          price_to_book: 45.8, // price_to_book
          peg_ratio: 2.1,
          book_value: 3.84,

          // Enterprise metrics
          enterprise_value: 3050000000000,
          ev_to_revenue: 7.7,
          ev_to_ebitda: 26.5,

          // Financial results
          total_revenue: 394328000000, // revenue
          net_income: 99803000000, // net_income
          ebitda: 123136000000,
          gross_profit: 182790000000,

          // EPS fields
          eps_trailing: 6.05, // earnings_per_share
          eps_forward: 6.45,
          eps_current_year: 6.05,
          price_eps_current_year: 29.0,

          // Growth metrics
          earnings_q_growth_pct: 0.08,
          revenue_growth_pct: 0.02,
          earnings_growth_pct: 0.05,

          // Cash & debt
          total_cash: 67155000000,
          cash_per_share: 4.28,
          operating_cashflow: 122151000000,
          free_cashflow: 99584000000,
          total_debt: 123930000000,
          debt_to_equity: 1.73,

          // Liquidity ratios
          quick_ratio: 1.05,
          // current_ratio already exists from fundamental_metrics

          // Profitability margins
          profit_margin_pct: 0.253,
          gross_margin_pct: 0.463,
          ebitda_margin_pct: 0.312,
          operating_margin_pct: 0.307,

          // Return metrics
          return_on_assets_pct: 0.223,
          // return_on_equity already exists from fundamental_metrics

          // Dividend information
          dividend_rate: 0.96,
          // dividend_yield already exists from fundamental_metrics
          five_year_avg_dividend_yield: 1.12,
          payout_ratio: 0.159
        },
        {
          symbol: 'MSFT',
          name: 'MSFT', // API uses symbol as name fallback
          company_name: 'Microsoft Corporation',
          security_name: 'Microsoft Corporation',
          short_name: 'Microsoft',
          long_name: 'Microsoft Corporation',
          display_name: 'Microsoft Corporation',
          sector: 'Technology',
          industry: 'Software—Infrastructure',
          market_cap: 2800000000000,
          current_price: 416.8,
          volume: 22000000,
          pe_ratio: 32.1,
          dividend_yield: 0.68,
          beta: 0.9,
          exchange: 'NASDAQ',
          earnings_per_share: 9.65,
          previous_close: 415.2,

          // Price data from LEFT JOIN
          open: 415.2,
          high: 418.9,
          low: 412.1,
          close: 416.8,
          adj_close: 416.8,
          price_date: new Date(),

          // Additional fields expected by the API transformation
          market_category: 'Standard',
          etf: 'N',
          quote_type: 'EQUITY',

          // Financial metrics fields (mapped from fundamental_metrics schema)
          trailing_pe: 32.1, // pe_ratio
          forward_pe: 29.8, // forward_pe
          price_to_sales_ttm: 12.8, // price_to_sales
          price_to_book: 12.9, // price_to_book
          peg_ratio: 2.8,
          book_value: 32.3,

          // Enterprise metrics
          enterprise_value: 2850000000000,
          ev_to_revenue: 13.4,
          ev_to_ebitda: 24.8,

          // Financial results
          total_revenue: 211915000000, // revenue
          net_income: 72361000000, // net_income
          ebitda: 114867000000,
          gross_profit: 146052000000,

          // EPS fields
          eps_trailing: 9.65, // earnings_per_share
          eps_forward: 10.12,
          eps_current_year: 9.65,
          price_eps_current_year: 43.2,

          // Growth metrics
          earnings_q_growth_pct: 0.11,
          revenue_growth_pct: 0.07,
          earnings_growth_pct: 0.09,

          // Cash & debt
          total_cash: 104749000000,
          cash_per_share: 14.1,
          operating_cashflow: 87582000000,
          free_cashflow: 65149000000,
          total_debt: 97718000000,
          debt_to_equity: 0.35,

          // Liquidity ratios
          quick_ratio: 1.32,
          // current_ratio already exists from fundamental_metrics

          // Profitability margins
          profit_margin_pct: 0.342,
          gross_margin_pct: 0.689,
          ebitda_margin_pct: 0.542,
          operating_margin_pct: 0.417,

          // Return metrics
          return_on_assets_pct: 0.185,
          // return_on_equity already exists from fundamental_metrics

          // Dividend information
          dividend_rate: 3.0,
          // dividend_yield already exists from fundamental_metrics
          five_year_avg_dividend_yield: 1.05,
          payout_ratio: 0.31
        }
      ],
      rowCount: 2
    });
  }

  // Handle fundamental_metrics queries
  if (query.includes('fundamental_metrics')) {
    return Promise.resolve({
      rows: mockData.fundamental_metrics,
      rowCount: mockData.fundamental_metrics.length
    });
  }

  // Handle price_daily queries
  if (query.includes('price_daily')) {
    return Promise.resolve({
      rows: mockData.price_daily,
      rowCount: mockData.price_daily.length
    });
  }

  // Handle positioning_metrics queries
  if (query.includes('positioning_metrics')) {
    return Promise.resolve({
      rows: mockData.positioning_metrics,
      rowCount: mockData.positioning_metrics.length
    });
  }

  // Handle retail_sentiment queries
  if (query.includes('retail_sentiment')) {
    return Promise.resolve({
      rows: mockData.retail_sentiment,
      rowCount: mockData.retail_sentiment.length
    });
  }

  // Handle market_data queries
  if (query.includes('market_data')) {
    return Promise.resolve({
      rows: mockData.market_data,
      rowCount: mockData.market_data.length
    });
  }

  // Handle stock_news queries
  if (query.includes('stock_news')) {
    return Promise.resolve({
      rows: mockData.stock_news,
      rowCount: mockData.stock_news.length
    });
  }

  // Handle analyst_sentiment_analysis queries
  if (query.includes('analyst_sentiment_analysis')) {
    return Promise.resolve({
      rows: mockData.analyst_sentiment_analysis,
      rowCount: mockData.analyst_sentiment_analysis.length
    });
  }

  // Default empty result
  return Promise.resolve({
    rows: [],
    rowCount: 0
  });
}

// Mock database module for tests
const mockDatabaseModule = {
  query: mockQuery,
  cachedQuery: mockQuery,
  initializeDatabase: () => Promise.resolve(true),
  getPool: () => ({
    query: mockQuery,
    connect: () => Promise.resolve({
      query: mockQuery,
      release: () => {}
    })
  }),
  closeDatabase: () => Promise.resolve(),
  healthCheck: () => Promise.resolve({ status: 'healthy' }),
  transaction: (callback) => callback({ query: mockQuery }),
  clearQueryCache: () => {}
};

module.exports = {
  mockDatabaseModule,
  mockData,
  mockQuery
};