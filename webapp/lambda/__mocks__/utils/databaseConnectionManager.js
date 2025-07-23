/**
 * Mock Database Connection Manager for Unit Tests
 */

const mockConnectionManager = {
  initialized: true,
  pool: {
    query: jest.fn().mockResolvedValue({ rows: [] }),
    connect: jest.fn().mockResolvedValue({
      query: jest.fn().mockResolvedValue({ rows: [] }),
      release: jest.fn()
    }),
    end: jest.fn(),
    totalCount: 10,
    idleCount: 5,
    waitingCount: 0
  },
  
  initialize: jest.fn().mockResolvedValue(true),
  query: jest.fn().mockResolvedValue({ rows: [] }),
  getConnection: jest.fn().mockResolvedValue({
    query: jest.fn().mockResolvedValue({ rows: [] }),
    release: jest.fn()
  }),
  healthCheck: jest.fn().mockResolvedValue({ status: 'healthy' }),
  close: jest.fn().mockResolvedValue(true),
  getStats: jest.fn().mockReturnValue({
    totalConnections: 10,
    idleConnections: 5,
    waitingClients: 0
  })
};

module.exports = mockConnectionManager;