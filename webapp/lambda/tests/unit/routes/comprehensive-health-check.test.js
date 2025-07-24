/**
 * Comprehensive Health Check System Tests
 * Tests for the restored comprehensive database monitoring system
 * This system provides detailed monitoring of 50+ database tables across 12 categories
 */

const request = require('supertest');
const express = require('express');
const healthRouter = require('../../../routes/health');

// Mock all external dependencies
jest.mock('../../../utils/database', () => ({
  healthCheck: jest.fn(),
  query: jest.fn(),
  validateDatabaseSchema: jest.fn(),
  initializeDatabase: jest.fn(),
  getPool: jest.fn()
}));

jest.mock('@aws-sdk/client-secrets-manager');

const { healthCheck, query, initializeDatabase, getPool } = require('../../../utils/database');

describe('Comprehensive Health Check System - RESTORED', () => {
  let app;

  beforeAll(() => {
    app = express();
    app.use(express.json());
    
    // Add response helper methods
    app.use((req, res, next) => {
      res.success = (data) => res.json({ success: true, ...data });
      res.serviceUnavailable = (msg, data) => res.status(503).json({ success: false, message: msg, ...data });
      res.serverError = (msg, details) => res.status(500).json({ success: false, message: msg, details });
      next();
    });
    
    app.use('/api/health', healthRouter);
  });

  beforeEach(() => {
    jest.clearAllMocks();
    
    // Mock console methods to avoid noise in tests
    jest.spyOn(console, 'log').mockImplementation(() => {});
    jest.spyOn(console, 'error').mockImplementation(() => {});
    jest.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe('Basic Health Check (GET /)', () => {
    it('should return quick health check without database when quick=true', async () => {
      const response = await request(app)
        .get('/api/health?quick=true')
        .expect(200);

      expect(response.body).toMatchObject({
        status: 'healthy',
        healthy: true,
        service: 'Financial Dashboard API',
        timestamp: expect.any(String),
        database: { status: 'not_tested' },
        api: { version: '1.0.0' },
        note: 'Quick health check - database not tested'
      });
    });

    it('should perform comprehensive health check with database connection', async () => {
      // Mock successful database initialization
      getPool.mockReturnValueOnce({}); // Pool exists
      
      // Mock AWS Secrets Manager
      const mockSecretsManager = {
        send: jest.fn().mockResolvedValue({
          SecretString: JSON.stringify({
            host: 'test-host',
            port: 5432,
            database: 'test_db',
            username: 'test_user'
          })
        })
      };
      
      // Mock successful health check
      healthCheck.mockResolvedValueOnce({
        status: 'healthy',
        timestamp: new Date().toISOString(),
        version: 'PostgreSQL 14.9'
      });

      const response = await request(app)
        .get('/api/health')
        .expect(200);

      expect(response.body).toMatchObject({
        status: 'healthy',
        healthy: true,
        service: 'Financial Dashboard API',
        timestamp: expect.any(String)
      });

      expect(healthCheck).toHaveBeenCalled();
    });
  });

  describe('Database Health Check (GET /database)', () => {
    it('should return comprehensive database analysis with table categorization', async () => {
      // Mock successful database connection
      healthCheck.mockResolvedValueOnce({
        status: 'healthy',
        timestamp: new Date().toISOString(),
        version: 'PostgreSQL 14.9'
      });

      // Mock comprehensive table analysis across all 12 categories
      const mockTables = [
        // Symbols category (5000+ records each)
        { table_name: 'symbols', estimated_rows: 5000, last_analyze: new Date().toISOString() },
        { table_name: 'symbol_metadata', estimated_rows: 5000, last_analyze: new Date().toISOString() },
        
        // Prices category (massive datasets)
        { table_name: 'stock_data', estimated_rows: 1500000, last_analyze: new Date().toISOString() },
        { table_name: 'price_daily', estimated_rows: 800000, last_analyze: new Date().toISOString() },
        
        // Technicals category (large datasets)
        { table_name: 'technicals_daily', estimated_rows: 600000, last_analyze: new Date().toISOString() },
        { table_name: 'ma_signals', estimated_rows: 300000, last_analyze: new Date().toISOString() },
        
        // Financials category
        { table_name: 'financial_statements', estimated_rows: 50000, last_analyze: new Date().toISOString() },
        { table_name: 'balance_sheets', estimated_rows: 25000, last_analyze: new Date().toISOString() },
        
        // Earnings category
        { table_name: 'earnings_estimates', estimated_rows: 12000, last_analyze: new Date().toISOString() },
        { table_name: 'earnings_history', estimated_rows: 8000, last_analyze: new Date().toISOString() },
        
        // Portfolio category
        { table_name: 'portfolio_holdings', estimated_rows: 150, last_analyze: new Date().toISOString() },
        { table_name: 'user_portfolios', estimated_rows: 50, last_analyze: new Date().toISOString() },
        
        // System category
        { table_name: 'health_status', estimated_rows: 30, last_analyze: new Date().toISOString() },
        { table_name: 'last_updated', estimated_rows: 15, last_analyze: new Date().toISOString() }
      ];

      query.mockResolvedValueOnce({ rows: mockTables });

      const response = await request(app)
        .get('/api/health/database')
        .expect(200);

      expect(response.body).toMatchObject({
        status: 'healthy',
        healthy: true,
        service: 'Financial Dashboard API',
        database: expect.objectContaining({
          status: 'connected',
          summary: expect.objectContaining({
            total_tables: mockTables.length,
            total_records: expect.any(Number)
          })
        }),
        timestamp: expect.any(String)
      });

      expect(healthCheck).toHaveBeenCalled();
      expect(query).toHaveBeenCalled();
    });

    it('should handle database connection failure gracefully', async () => {
      // Mock database connection failure
      healthCheck.mockRejectedValueOnce(new Error('Connection refused'));

      const response = await request(app)
        .get('/api/health/database')
        .expect(503);

      expect(response.body).toMatchObject({
        status: 'unhealthy',
        healthy: false,
        service: 'Financial Dashboard API',
        database: expect.objectContaining({
          status: 'error',
          error: 'Connection refused'
        })
      });

      expect(healthCheck).toHaveBeenCalled();
    });
  });

  describe('Health Status Update (POST /update-status)', () => {
    it('should successfully update health status with comprehensive analysis', async () => {
      // Mock healthy database connection
      healthCheck.mockResolvedValueOnce({
        status: 'healthy',
        timestamp: new Date().toISOString(),
        version: 'PostgreSQL 14.9'
      });

      // Mock table information query with comprehensive data
      const mockTables = [
        {
          table_name: 'symbols',
          table_type: 'BASE TABLE',
          estimated_rows: 5000,
          last_analyze: new Date().toISOString(),
          last_autovacuum: new Date().toISOString(),
          last_vacuum: new Date().toISOString(),
          last_autoanalyze: new Date().toISOString()
        },
        {
          table_name: 'stock_data',
          table_type: 'BASE TABLE',
          estimated_rows: 1500000,
          last_analyze: new Date().toISOString(),
          last_autovacuum: new Date().toISOString(),
          last_vacuum: new Date().toISOString(),
          last_autoanalyze: new Date().toISOString()
        },
        {
          table_name: 'health_status',
          table_type: 'BASE TABLE',
          estimated_rows: 25,
          last_analyze: new Date().toISOString(),
          last_autovacuum: new Date().toISOString(),
          last_vacuum: new Date().toISOString(),
          last_autoanalyze: new Date().toISOString()
        }
      ];

      query.mockResolvedValueOnce({ rows: mockTables });

      // Mock health_status table existence check
      query.mockResolvedValueOnce({ rows: [{ exists: 1 }] });

      // Mock health_status table insert/update operations for each table
      for (let i = 0; i < mockTables.length; i++) {
        query.mockResolvedValueOnce({ rows: [], rowCount: 1 });
      }

      const response = await request(app)
        .post('/api/health/update-status')
        .expect(200);

      expect(response.body).toMatchObject({
        status: 'success',
        message: 'Database health status updated successfully',
        data: expect.objectContaining({
          status: 'connected',
          database: expect.objectContaining({
            status: 'connected',
            summary: expect.objectContaining({
              total_tables: mockTables.length,
              healthy_tables: mockTables.length,
              total_records: expect.any(Number)
            })
          })
        }),
        timestamp: expect.any(String)
      });

      // Verify health check was called
      expect(healthCheck).toHaveBeenCalled();
      
      // Verify table query was called
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining('SELECT'),
        [],
        15000
      );

      // Verify health_status table operations
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining('SELECT COUNT(*) as exists')
      );
    });

    it('should categorize tables according to the comprehensive system', async () => {
      // Mock healthy database
      healthCheck.mockResolvedValueOnce({
        status: 'healthy',
        timestamp: new Date().toISOString(),
        version: 'PostgreSQL 14.9'
      });

      // Mock comprehensive table list across all 12 categories
      const mockTables = [
        // Test each category
        { table_name: 'symbols', table_type: 'BASE TABLE', estimated_rows: 5000, last_analyze: new Date().toISOString() },
        { table_name: 'stock_data', table_type: 'BASE TABLE', estimated_rows: 1500000, last_analyze: new Date().toISOString() },
        { table_name: 'technicals_daily', table_type: 'BASE TABLE', estimated_rows: 600000, last_analyze: new Date().toISOString() },
        { table_name: 'financial_statements', table_type: 'BASE TABLE', estimated_rows: 50000, last_analyze: new Date().toISOString() },
        { table_name: 'earnings_estimates', table_type: 'BASE TABLE', estimated_rows: 12000, last_analyze: new Date().toISOString() },
        { table_name: 'portfolio_holdings', table_type: 'BASE TABLE', estimated_rows: 150, last_analyze: new Date().toISOString() },
        { table_name: 'market_indices', table_type: 'BASE TABLE', estimated_rows: 500, last_analyze: new Date().toISOString() },
        { table_name: 'news_articles', table_type: 'BASE TABLE', estimated_rows: 10000, last_analyze: new Date().toISOString() },
        { table_name: 'trading_signals', table_type: 'BASE TABLE', estimated_rows: 5000, last_analyze: new Date().toISOString() },
        { table_name: 'trade_history', table_type: 'BASE TABLE', estimated_rows: 1000, last_analyze: new Date().toISOString() },
        { table_name: 'health_status', table_type: 'BASE TABLE', estimated_rows: 30, last_analyze: new Date().toISOString() },
        { table_name: 'fear_greed_index', table_type: 'BASE TABLE', estimated_rows: 365, last_analyze: new Date().toISOString() }
      ];

      query.mockResolvedValueOnce({ rows: mockTables });

      // Mock health_status table exists
      query.mockResolvedValueOnce({ rows: [{ exists: 1 }] });

      // Mock successful insert/update for each table
      for (let i = 0; i < mockTables.length; i++) {
        query.mockResolvedValueOnce({ rows: [], rowCount: 1 });
      }

      const response = await request(app)
        .post('/api/health/update-status')
        .expect(200);

      // Verify comprehensive analysis was performed
      expect(response.body.data.database.summary.total_tables).toBe(mockTables.length);
      expect(response.body.data.database.summary.total_records).toBeGreaterThan(0);
      
      // Verify table categorization exists in response
      const tableNames = Object.keys(response.body.data.database.tables);
      expect(tableNames).toEqual(expect.arrayContaining([
        'symbols', 'stock_data', 'technicals_daily', 'financial_statements',
        'earnings_estimates', 'portfolio_holdings', 'market_indices', 
        'news_articles', 'trading_signals', 'trade_history', 
        'health_status', 'fear_greed_index'
      ]));

      // Verify critical table marking exists
      expect(response.body.data.database.tables.symbols.critical_table).toBe(true);
      expect(response.body.data.database.tables.portfolio_holdings.critical_table).toBe(true);
      expect(response.body.data.database.tables.health_status.critical_table).toBe(true);

      expect(console.log).toHaveBeenCalledWith(
        expect.stringMatching(/📋 Found \d+ tables in database/)
      );
    });
  });

  describe('Additional Endpoints', () => {
    it('should provide database diagnostics endpoint', async () => {
      // Mock successful health check
      healthCheck.mockResolvedValueOnce({
        status: 'healthy',
        timestamp: new Date().toISOString(),
        version: 'PostgreSQL 14.9'
      });

      const response = await request(app)
        .get('/api/health/database/diagnostics')
        .expect(200);

      expect(response.body).toMatchObject({
        status: 'healthy',
        service: 'Financial Dashboard API',
        timestamp: expect.any(String)
      });

      expect(healthCheck).toHaveBeenCalled();
    });

    it('should provide status summary endpoint', async () => {
      const response = await request(app)
        .get('/api/health/status-summary')
        .expect(200);

      expect(response.body).toMatchObject({
        status: 'healthy',
        service: 'Financial Dashboard API',
        timestamp: expect.any(String),
        summary: expect.any(Object)
      });
    });
  });
});