const { Pool } = require('pg');
const { getDbConfig, initializeDatabase, query, healthCheck, cleanup } = require('../../utils/database');

// Mock the database module
jest.mock('../../utils/database', () => {
  const originalModule = jest.requireActual('../../utils/database');
  return {
    ...originalModule,
    getDbConfig: jest.fn(),
    initializeDatabase: jest.fn(),
    query: jest.fn(),
    healthCheck: jest.fn(),
    cleanup: jest.fn()
  };
});

describe('Database Service', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('getDbConfig', () => {
    it('should return database configuration from secrets manager', async () => {
      const mockConfig = {
        host: 'localhost',
        port: 5432,
        user: 'test_user',
        password: 'test_password',
        database: 'test_stocks'
      };
      
      getDbConfig.mockResolvedValue(mockConfig);
      
      const config = await getDbConfig();
      expect(config).toEqual(mockConfig);
      expect(getDbConfig).toHaveBeenCalledTimes(1);
    });

    it('should handle secrets manager errors gracefully', async () => {
      const error = new Error('Secrets manager error');
      getDbConfig.mockRejectedValue(error);
      
      await expect(getDbConfig()).rejects.toThrow('Secrets manager error');
    });
  });

  describe('initializeDatabase', () => {
    it('should initialize database connection pool', async () => {
      initializeDatabase.mockResolvedValue(true);
      
      const result = await initializeDatabase();
      expect(result).toBe(true);
      expect(initializeDatabase).toHaveBeenCalledTimes(1);
    });

    it('should handle initialization errors', async () => {
      const error = new Error('Database connection failed');
      initializeDatabase.mockRejectedValue(error);
      
      await expect(initializeDatabase()).rejects.toThrow('Database connection failed');
    });
  });

  describe('query', () => {
    it('should execute SQL queries successfully', async () => {
      const mockResult = { rows: [{ id: 1, name: 'test' }], rowCount: 1 };
      query.mockResolvedValue(mockResult);
      
      const result = await query('SELECT * FROM test_table WHERE id = $1', [1]);
      expect(result).toEqual(mockResult);
      expect(query).toHaveBeenCalledWith('SELECT * FROM test_table WHERE id = $1', [1]);
    });

    it('should handle query errors', async () => {
      const error = new Error('SQL syntax error');
      query.mockRejectedValue(error);
      
      await expect(query('INVALID SQL')).rejects.toThrow('SQL syntax error');
    });

    it('should handle connection timeout errors', async () => {
      const timeoutError = new Error('Connection timeout');
      timeoutError.code = 'ECONNRESET';
      query.mockRejectedValue(timeoutError);
      
      await expect(query('SELECT 1')).rejects.toThrow('Connection timeout');
    });
  });

  describe('healthCheck', () => {
    it('should return healthy status when database is accessible', async () => {
      const mockHealthy = { healthy: true, message: 'Database connection successful' };
      healthCheck.mockResolvedValue(mockHealthy);
      
      const result = await healthCheck();
      expect(result).toEqual(mockHealthy);
      expect(result.healthy).toBe(true);
    });

    it('should return unhealthy status on connection failure', async () => {
      const mockUnhealthy = { healthy: false, message: 'Database connection failed', error: 'Connection refused' };
      healthCheck.mockResolvedValue(mockUnhealthy);
      
      const result = await healthCheck();
      expect(result).toEqual(mockUnhealthy);
      expect(result.healthy).toBe(false);
    });
  });

  describe('cleanup', () => {
    it('should cleanup database connections', async () => {
      cleanup.mockResolvedValue();
      
      await cleanup();
      expect(cleanup).toHaveBeenCalledTimes(1);
    });

    it('should handle cleanup errors gracefully', async () => {
      const error = new Error('Cleanup failed');
      cleanup.mockRejectedValue(error);
      
      await expect(cleanup()).rejects.toThrow('Cleanup failed');
    });
  });
});