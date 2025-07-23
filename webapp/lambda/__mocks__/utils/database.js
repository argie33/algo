/**
 * Mock Database Module for Unit Tests
 * Provides mock implementations for all database functions
 */

// Mock portfolio data
const mockPortfolioData = [
  {
    symbol: 'AAPL',
    quantity: 100,
    market_value: 15000,
    avg_cost: 150,
    cost_basis: 15000,
    unrealized_pnl: 500,
    sector: 'Technology'
  },
  {
    symbol: 'MSFT', 
    quantity: 50,
    market_value: 12500,
    avg_cost: 250,
    cost_basis: 12500,
    unrealized_pnl: 1000,
    sector: 'Technology'
  }
];

const mockUserData = {
  id: 'user-123',
  email: 'test@example.com',
  created_at: new Date(),
  updated_at: new Date()
};

// Mock query function
const mockQuery = jest.fn().mockImplementation((query, params) => {
  console.log('🔍 [MOCK] Database query:', query.substring(0, 100) + '...');
  console.log('🔍 [MOCK] Params:', params);
  
  // Return different mock data based on query patterns
  if (query.includes('portfolio_holdings')) {
    return Promise.resolve({ rows: mockPortfolioData });
  }
  
  if (query.includes('users')) {
    return Promise.resolve({ rows: [mockUserData] });
  }
  
  if (query.includes('api_keys')) {
    return Promise.resolve({ rows: [] });
  }
  
  // Default empty result
  return Promise.resolve({ rows: [] });
});

// Mock database connection
const mockConnection = {
  query: mockQuery,
  end: jest.fn(),
  release: jest.fn()
};

// Mock pool
const mockPool = {
  query: mockQuery,
  connect: jest.fn().mockResolvedValue(mockConnection),
  end: jest.fn(),
  totalCount: 10,
  idleCount: 5,
  waitingCount: 0
};

// Mock database functions
const database = {
  query: mockQuery,
  getConnection: jest.fn().mockResolvedValue(mockConnection),
  pool: mockPool,
  resetDatabaseState: jest.fn().mockResolvedValue(true),
  healthCheck: jest.fn().mockResolvedValue({ status: 'healthy', pool: mockPool }),
  close: jest.fn().mockResolvedValue(true),
  
  // Mock circuit breaker functions
  circuitBreaker: {
    isOpen: false,
    failures: 0,
    execute: jest.fn().mockImplementation((fn) => fn()),
    recordSuccess: jest.fn(),
    recordFailure: jest.fn(),
    getStats: jest.fn().mockReturnValue({ failures: 0, isOpen: false })
  }
};

module.exports = database;