// Jest setup file - runs before each test file

// Set test environment
process.env.NODE_ENV = "test";

// Mock the database module before any tests run
jest.mock('../utils/database', () => ({
  query: jest.fn(),
  initializeDatabase: jest.fn(),
  healthCheck: jest.fn(),
  getPool: jest.fn(),
  closeDatabase: jest.fn(),
  transaction: jest.fn(),
}));

// Mock the apiKeyService module
jest.mock('../utils/apiKeyService', () => ({
  isEnabled: true,
  isLocalMode: false,
  getApiKey: jest.fn().mockResolvedValue({
    apiKey: "test-key",
    apiSecret: "test-secret", 
    isSandbox: true
  }),
  getDecryptedApiKey: jest.fn().mockResolvedValue({
    apiKey: "test-key",
    apiSecret: "test-secret",
    isSandbox: true
  }),
  storeApiKey: jest.fn().mockResolvedValue(true),
  deleteApiKey: jest.fn().mockResolvedValue(true),
  listApiKeys: jest.fn().mockResolvedValue([]),
  listProviders: jest.fn().mockResolvedValue([]),
  validateApiKey: jest.fn().mockResolvedValue(true),
  validateJwtToken: jest.fn().mockResolvedValue({ sub: "test-user-id" }),
  getHealthStatus: jest.fn().mockResolvedValue({ status: "healthy" }),
}));

// Setup in-memory test database using pg-mem
const { createTestDatabase } = require('./testDatabase');
let testDatabase = null;

beforeAll(async () => {
  // Create in-memory PostgreSQL database for all tests
  try {
    testDatabase = createTestDatabase();
    console.log('✅ In-memory PostgreSQL test database created');
    
    // Make it available globally
    global.TEST_DATABASE = testDatabase;
    global.DATABASE_AVAILABLE = () => true;
    
    // Set up the mocked database methods
    const db = require('../utils/database');
    
    // Ensure mock functions exist before setting implementations
    if (db.query && db.query.mockImplementation) {
      // Mock implementation with actual pg-mem database
      db.query.mockImplementation(async (text, params) => {
        try {
          // Handle health check queries specifically
          if (text.includes("SELECT 1 as ok")) {
            return {
              rows: [{ ok: 1 }],
              rowCount: 1
            };
          }
          
          // For other queries, try to use pg-mem database if available
          if (testDatabase && testDatabase.query) {
            const result = await testDatabase.query(text, params || []);
            // pg-mem returns results differently, normalize to pg format
            return {
              rows: result.rows || result || [],
              rowCount: result.rowCount || (result && result.length) || 0
            };
          }
          
          // Fallback for when pg-mem is not available
          return {
            rows: [],
            rowCount: 0
          };
        } catch (error) {
          // For health checks, return a successful response to avoid 503 errors
          if (text.includes("SELECT 1 as ok")) {
            return {
              rows: [{ ok: 1 }],
              rowCount: 1
            };
          }
          throw error;
        }
      });
    }
    
    // Mock other database methods to return successful responses
    if (db.initializeDatabase && db.initializeDatabase.mockResolvedValue) {
      db.initializeDatabase.mockResolvedValue(testDatabase);
    }
    if (db.healthCheck && db.healthCheck.mockResolvedValue) {
      db.healthCheck.mockResolvedValue({ healthy: true, database: 'connected', tables: ['user_portfolio'] });
    }
    if (db.getPool && db.getPool.mockReturnValue) {
      db.getPool.mockReturnValue({ 
        query: db.query,
        totalCount: 1,
        idleCount: 0,
        waitingCount: 0,
        connect: jest.fn().mockResolvedValue({}),
        end: jest.fn().mockResolvedValue({})
      });
    }
    if (db.closeDatabase && db.closeDatabase.mockResolvedValue) {
      db.closeDatabase.mockResolvedValue(undefined);
    }
    
  } catch (error) {
    console.error('❌ Failed to create test database:', error);
    global.DATABASE_AVAILABLE = () => false;
  }
});

afterAll(async () => {
  if (testDatabase && testDatabase.end) {
    await testDatabase.end();
  }
});

// Mock console methods to reduce noise
const originalConsole = { ...console };

beforeAll(() => {
  // Mock console methods to reduce noise in tests
  console.log = jest.fn();
  console.info = jest.fn();
  console.warn = jest.fn();
  console.error = jest.fn();
  console.debug = jest.fn();
});

afterAll(() => {
  // Restore console
  Object.assign(console, originalConsole);
});

// Global test timeout
jest.setTimeout(30000);

// Mock timers by default
beforeEach(() => {
  jest.clearAllMocks();
  jest.clearAllTimers();
});

afterEach(() => {
  jest.runOnlyPendingTimers();
  jest.useRealTimers();
});
