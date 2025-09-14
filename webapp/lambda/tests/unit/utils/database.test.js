/**
 * Database Utility Unit Tests
 * Tests business logic and internal functionality with mocked dependencies
 * These tests focus on our code logic, not external database connections
 */

// Mock external dependencies
const mockPool = {
  query: jest.fn(),
  end: jest.fn(),
  connect: jest.fn(),
  on: jest.fn(),
  totalCount: 5,
  idleCount: 3,
  waitingCount: 0
};

const mockClient = {
  query: jest.fn(),
  release: jest.fn()
};

jest.mock('pg', () => ({
  Pool: jest.fn(() => mockPool)
}));

jest.mock('@aws-sdk/client-secrets-manager', () => ({
  SecretsManagerClient: jest.fn(),
  GetSecretValueCommand: jest.fn()
}));

// Mock schema validator
jest.mock('../../../utils/schemaValidator', () => ({
  generateCreateTableSQL: jest.fn(() => 'CREATE TABLE test (id INTEGER)'),
  listTables: jest.fn(() => ['stock_symbols', 'market_data'])
}));

// Mock logger
jest.mock('../../../utils/logger', () => ({
  error: jest.fn(),
  info: jest.fn(),
  warn: jest.fn()
}));

const {
  query,
  initializeDatabase,
  closeDatabase,
  healthCheck,
  transaction,
  getPool
} = require('../../../utils/database');

const { Pool } = require('pg');

describe('Database Utilities - Unit Tests', () => {
  let originalEnv;

  beforeEach(() => {
    jest.clearAllMocks();
    originalEnv = { ...process.env };
    mockPool.connect.mockResolvedValue(mockClient);
    mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  describe('Database Module Export Tests', () => {
    test('should export required functions', () => {
      expect(typeof initializeDatabase).toBe('function');
      expect(typeof query).toBe('function');
      expect(typeof transaction).toBe('function');
      expect(typeof healthCheck).toBe('function');
      expect(typeof closeDatabase).toBe('function');
      expect(typeof getPool).toBe('function');
    });
  });

  describe('Connection Pool Management', () => {
    test('should initialize database and return pool object', async () => {
      process.env.DB_HOST = 'localhost';
      process.env.DB_USER = 'postgres';
      process.env.DB_PASSWORD = 'password';
      process.env.DB_NAME = 'stocks';

      const result = await initializeDatabase();

      expect(Pool).toHaveBeenCalled();
      expect(result).toBeDefined();
      expect(typeof result).toBe('object');
    });

    test('should handle initialization with environment variables', async () => {
      process.env.DB_HOST = 'localhost';
      process.env.DB_USER = 'test';
      process.env.DB_PASSWORD = 'test';
      process.env.DB_NAME = 'test';

      const result = await initializeDatabase();

      expect(result).toBeDefined();
      expect(mockPool.on).toHaveBeenCalled();
    });
  });

  describe('Query Execution', () => {
    test('should execute queries through connection pool', async () => {
      const mockResult = { rows: [{ id: 1, name: 'test' }], rowCount: 1 };
      mockPool.query.mockResolvedValue(mockResult);

      process.env.DB_HOST = 'localhost';
      process.env.DB_USER = 'test';
      process.env.DB_PASSWORD = 'test';
      process.env.DB_NAME = 'test';

      const result = await query('SELECT * FROM test WHERE id = $1', [1]);

      expect(mockPool.query).toHaveBeenCalledWith('SELECT * FROM test WHERE id = $1', [1]);
      expect(result).toEqual(mockResult);
    });

    test('should return null when database is not initialized', async () => {
      delete process.env.DB_HOST;
      delete process.env.DB_SECRET_ARN;

      const result = await query('SELECT 1');

      expect(result).toBeNull();
    });

    test('should handle connection errors gracefully', async () => {
      mockPool.query.mockRejectedValue(new Error('ECONNREFUSED'));
      
      process.env.DB_HOST = 'localhost';
      process.env.DB_USER = 'test';
      process.env.DB_PASSWORD = 'test';
      process.env.DB_NAME = 'test';

      const result = await query('SELECT 1');

      expect(result).toBeNull();
    });

    test('should handle non-connection errors by throwing', async () => {
      mockPool.query.mockRejectedValue(new Error('syntax error'));
      
      process.env.DB_HOST = 'localhost';
      process.env.DB_USER = 'test';
      process.env.DB_PASSWORD = 'test';
      process.env.DB_NAME = 'test';

      await expect(query('INVALID SQL')).rejects.toThrow('syntax error');
    });

    test('should handle pool exhaustion errors', async () => {
      mockPool.query.mockRejectedValue(new Error('Pool exhausted'));
      
      process.env.DB_HOST = 'localhost';
      process.env.DB_USER = 'test';
      process.env.DB_PASSWORD = 'test';
      process.env.DB_NAME = 'test';

      await expect(query('SELECT 1')).rejects.toThrow('Pool exhausted');
    });
  });

  describe('Transaction Management', () => {
    test('should execute transaction with proper BEGIN/COMMIT', async () => {
      process.env.DB_HOST = 'localhost';
      process.env.DB_USER = 'test';
      process.env.DB_PASSWORD = 'test';
      process.env.DB_NAME = 'test';

      const transactionCallback = jest.fn(async (client) => {
        await client.query('INSERT INTO test VALUES ($1)', [1]);
        return 'success';
      });

      mockClient.query
        .mockResolvedValueOnce() // BEGIN
        .mockResolvedValueOnce({ rows: [], rowCount: 1 }) // INSERT
        .mockResolvedValueOnce(); // COMMIT

      const result = await transaction(transactionCallback);

      expect(mockClient.query).toHaveBeenCalledWith('BEGIN');
      expect(mockClient.query).toHaveBeenCalledWith('COMMIT');
      expect(mockClient.release).toHaveBeenCalled();
      expect(result).toBe('success');
    });

    test('should rollback transaction on error', async () => {
      process.env.DB_HOST = 'localhost';
      process.env.DB_USER = 'test';
      process.env.DB_PASSWORD = 'test';
      process.env.DB_NAME = 'test';

      const transactionError = new Error('Transaction failed');
      const transactionCallback = jest.fn(async () => {
        throw transactionError;
      });

      mockClient.query
        .mockResolvedValueOnce() // BEGIN
        .mockResolvedValueOnce(); // ROLLBACK

      await expect(transaction(transactionCallback)).rejects.toThrow('Transaction failed');

      expect(mockClient.query).toHaveBeenCalledWith('BEGIN');
      expect(mockClient.query).toHaveBeenCalledWith('ROLLBACK');
      expect(mockClient.release).toHaveBeenCalled();
    });

    test('should handle transaction when database not initialized', async () => {
      delete process.env.DB_HOST;
      delete process.env.DB_SECRET_ARN;

      const transactionCallback = jest.fn();

      await expect(transaction(transactionCallback)).rejects.toThrow('Database not initialized');
    });
  });

  describe('Health Check', () => {
    test('should return health status object', async () => {
      mockPool.query.mockResolvedValue({ rows: [{ now: new Date() }] });
      
      process.env.DB_HOST = 'localhost';
      process.env.DB_USER = 'test';
      process.env.DB_PASSWORD = 'test';
      process.env.DB_NAME = 'test';

      const result = await healthCheck();

      expect(result).toBeDefined();
      expect(typeof result).toBe('object');
    });

    test('should handle database errors gracefully', async () => {
      mockPool.query.mockRejectedValue(new Error('Connection failed'));
      
      const result = await healthCheck();

      expect(result).toBeDefined();
      expect(result.status).toBe('unhealthy');
      expect(result.error).toBe('Connection failed');
    });
  });


  describe('Connection Cleanup', () => {
    test('should close database connections', async () => {
      process.env.DB_HOST = 'localhost';
      process.env.DB_USER = 'test';
      process.env.DB_PASSWORD = 'test';
      process.env.DB_NAME = 'test';

      await initializeDatabase();
      await closeDatabase();

      expect(mockPool.end).toHaveBeenCalled();
    });

    test('should handle cleanup when no pool exists', async () => {
      await closeDatabase();

      // Should not throw error
      expect(mockPool.end).not.toHaveBeenCalled();
    });
  });

  describe('Pool Access', () => {
    test('should throw error when pool not initialized', () => {
      expect(() => getPool()).toThrow('Database not initialized');
    });

    test('should return connection pool when initialized', async () => {
      process.env.DB_HOST = 'localhost';
      process.env.DB_USER = 'test';
      process.env.DB_PASSWORD = 'test';
      process.env.DB_NAME = 'test';

      await initializeDatabase();
      const pool = getPool();

      expect(pool).toBeDefined();
      expect(typeof pool).toBe('object');
    });
  });

  describe('Error Handling Edge Cases', () => {
    test('should handle database connection timeout errors', async () => {
      mockPool.query.mockRejectedValue(new Error('connection timeout'));
      
      process.env.DB_HOST = 'localhost';
      process.env.DB_USER = 'test';
      process.env.DB_PASSWORD = 'test';
      process.env.DB_NAME = 'test';

      const result = await query('SELECT 1');

      expect(result).toBeNull();
    });

    test('should handle unexpected error formats', async () => {
      mockPool.query.mockRejectedValue({ message: 'connection timeout' });
      
      process.env.DB_HOST = 'localhost';
      process.env.DB_USER = 'test';
      process.env.DB_PASSWORD = 'test';
      process.env.DB_NAME = 'test';

      const result = await query('SELECT 1');

      expect(result).toBeNull();
    });

    test('should handle query logging for slow queries', async () => {
      const slowQuery = new Promise(resolve => 
        setTimeout(() => resolve({ rows: [], rowCount: 0 }), 100)
      );
      mockPool.query.mockImplementation(() => slowQuery);
      
      process.env.DB_HOST = 'localhost';
      process.env.DB_USER = 'test';
      process.env.DB_PASSWORD = 'test';
      process.env.DB_NAME = 'test';

      const result = await query('SELECT * FROM slow_table');

      expect(result).toEqual({ rows: [], rowCount: 0 });
    });
  });
});