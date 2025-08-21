// Jest globals are automatically available

// Mock AWS SDK
jest.mock('@aws-sdk/client-secrets-manager', () => ({
  SecretsManagerClient: jest.fn().mockImplementation(() => ({
    send: jest.fn()
  })),
  GetSecretValueCommand: jest.fn()
}));

// Mock pg
jest.mock('pg', () => ({
  Pool: jest.fn().mockImplementation(() => ({
    connect: jest.fn(),
    query: jest.fn(),
    end: jest.fn(),
    totalCount: 10,
    idleCount: 8,
    waitingCount: 0
  }))
}));

const { Pool } = require('pg');

describe('Database Service - Core Functions', () => {
  let mockPool;
  let database;

  beforeEach(() => {
    jest.clearAllMocks();
    
    // Clear module cache
    delete require.cache[require.resolve('../../utils/database')];
    
    mockPool = {
      connect: jest.fn(),
      query: jest.fn(),
      end: jest.fn(),
      totalCount: 10,
      idleCount: 8,
      waitingCount: 0
    };
    Pool.mockImplementation(() => mockPool);
    
    // Set test environment variables
    process.env.DB_HOST = 'localhost';
    process.env.DB_USER = 'testuser';
    process.env.DB_PASSWORD = 'testpass';
    process.env.DB_NAME = 'testdb';
    process.env.DB_PORT = '5432';
    
    // Import database module
    database = require('../../utils/database');
  });

  afterEach(() => {
    // Clean up environment variables
    delete process.env.DB_HOST;
    delete process.env.DB_USER;
    delete process.env.DB_PASSWORD;
    delete process.env.DB_NAME;
    delete process.env.DB_PORT;
    delete process.env.DB_SECRET_ARN;
  });

  describe('module exports', () => {
    test('should export required functions', () => {
      expect(typeof database.initializeDatabase).toBe('function');
      expect(typeof database.query).toBe('function');
      expect(typeof database.healthCheck).toBe('function');
      expect(typeof database.getPool).toBe('function');
      expect(typeof database.closeDatabase).toBe('function');
      expect(typeof database.transaction).toBe('function');
    });
  });

  describe('getPool', () => {
    test('should return null when pool is not initialized', () => {
      const pool = database.getPool();
      expect(pool).toBeNull();
    });
  });

  describe('initializeDatabase', () => {
    test('should initialize database connection', async () => {
      // Mock successful connection
      const mockClient = { release: jest.fn() };
      mockPool.connect.mockResolvedValue(mockClient);

      const result = await database.initializeDatabase();

      expect(Pool).toHaveBeenCalledWith(expect.objectContaining({
        host: 'localhost',
        user: 'testuser',
        password: 'testpass',
        database: 'testdb',
        port: 5432
      }));
      expect(mockPool.connect).toHaveBeenCalled();
      expect(mockClient.release).toHaveBeenCalled();
      expect(result).toBe(mockPool);
    });

    test('should handle connection errors gracefully', async () => {
      mockPool.connect.mockRejectedValue(new Error('Connection failed'));

      const result = await database.initializeDatabase();

      expect(result).toBeNull();
    });
  });

  describe('closeDatabase', () => {
    test('should close database connections', async () => {
      // Initialize first
      const mockClient = { release: jest.fn() };
      mockPool.connect.mockResolvedValue(mockClient);
      await database.initializeDatabase();

      // Then close
      await database.closeDatabase();

      expect(mockPool.end).toHaveBeenCalled();
    });
  });

  describe('query', () => {
    test('should execute query when database is initialized', async () => {
      // Initialize database first
      const mockClient = { release: jest.fn() };
      mockPool.connect.mockResolvedValue(mockClient);
      await database.initializeDatabase();

      const mockResult = { rows: [{ id: 1, name: 'test' }], rowCount: 1 };
      mockPool.query.mockResolvedValue(mockResult);

      const result = await database.query('SELECT * FROM test', []);

      expect(mockPool.query).toHaveBeenCalledWith('SELECT * FROM test', []);
      expect(result).toBe(mockResult);
    });

    test('should handle query when database is not initialized', async () => {
      // Don't initialize database
      const mockResult = { rows: [], rowCount: 0 };
      mockPool.query.mockResolvedValue(mockResult);

      await expect(database.query('SELECT * FROM test', [])).rejects.toThrow('Database not available');
    });
  });

  describe('healthCheck', () => {
    test('should return unhealthy status when database is not available', async () => {
      // Don't initialize database
      const health = await database.healthCheck();

      expect(health.status).toBe('unhealthy');
      expect(health.error).toBeDefined();
    });

    test('should return healthy status when database is working', async () => {
      // Initialize database
      const mockClient = { release: jest.fn() };
      mockPool.connect.mockResolvedValue(mockClient);
      await database.initializeDatabase();

      // Mock successful health check query
      const mockResult = {
        rows: [{
          timestamp: '2024-01-01T00:00:00.000Z',
          db_version: 'PostgreSQL 14.0'
        }]
      };
      mockPool.query.mockResolvedValue(mockResult);

      const health = await database.healthCheck();

      expect(health.status).toBe('healthy');
      expect(health.timestamp).toBe('2024-01-01T00:00:00.000Z');
      expect(health.version).toBe('PostgreSQL 14.0');
      expect(health.connections).toBe(10);
    });
  });

  describe('transaction', () => {
    test('should execute transaction callback', async () => {
      // Initialize database
      const mockClient = { 
        release: jest.fn(),
        query: jest.fn()
      };
      mockPool.connect.mockResolvedValue(mockClient);
      await database.initializeDatabase();

      const mockCallback = jest.fn().mockResolvedValue('callback result');

      const result = await database.transaction(mockCallback);

      expect(mockCallback).toHaveBeenCalledWith(mockClient);
      expect(result).toBe('callback result');
      expect(mockClient.query).toHaveBeenCalledWith('BEGIN');
      expect(mockClient.query).toHaveBeenCalledWith('COMMIT');
      expect(mockClient.release).toHaveBeenCalled();
    });

    test('should rollback transaction on error', async () => {
      // Initialize database
      const mockClient = { 
        release: jest.fn(),
        query: jest.fn()
      };
      mockPool.connect.mockResolvedValue(mockClient);
      await database.initializeDatabase();

      const mockCallback = jest.fn().mockRejectedValue(new Error('Transaction failed'));

      await expect(database.transaction(mockCallback)).rejects.toThrow('Transaction failed');

      expect(mockClient.query).toHaveBeenCalledWith('BEGIN');
      expect(mockClient.query).toHaveBeenCalledWith('ROLLBACK');
      expect(mockClient.release).toHaveBeenCalled();
    });
  });
});