/**
 * Comprehensive Health Check System Unit Tests
 * Tests the restored comprehensive database health analysis system
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

describe('Comprehensive Health Check System', () => {
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

  describe('GET /api/health/ - Basic Health Check', () => {
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
        api: { version: '1.0.0' }
      });
    });

    it('should perform full health check with database connection', async () => {
      // Mock successful database initialization
      getPool.mockReturnValueOnce({}); // Pool exists
      
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

    it('should handle database initialization failure', async () => {
      // Mock pool not initialized
      getPool.mockImplementation(() => {
        throw new Error('Pool not initialized');
      });
      
      // Mock database initialization failure
      initializeDatabase.mockRejectedValueOnce(new Error('Connection refused'));

      const response = await request(app)
        .get('/api/health')
        .expect(503);

      expect(response.body).toMatchObject({
        status: 'unhealthy',
        healthy: false,
        service: 'Financial Dashboard API',
        database: {
          status: 'initialization_failed',
          error: 'Connection refused'
        }
      });
    });
  });

  describe('GET /api/health/database - Comprehensive Database Health', () => {
    it('should return comprehensive database analysis with multi-tier health checks', async () => {
      // Mock successful database connection
      healthCheck.mockResolvedValueOnce({
        status: 'healthy',
        timestamp: new Date().toISOString(),
        version: 'PostgreSQL 14.9'
      });

      // Mock comprehensive table analysis across all 12 categories
      const mockTables = [
        // Symbols category
        { table_name: 'symbols', estimated_rows: 5000, table_category: 'symbols' },
        { table_name: 'symbol_metadata', estimated_rows: 5000, table_category: 'symbols' },
        
        // Prices category  
        { table_name: 'stock_data', estimated_rows: 1500000, table_category: 'prices' },
        { table_name: 'price_daily', estimated_rows: 800000, table_category: 'prices' },
        
        // Technicals category
        { table_name: 'technicals_daily', estimated_rows: 600000, table_category: 'technicals' },
        { table_name: 'ma_signals', estimated_rows: 300000, table_category: 'technicals' },
        
        // Financials category
        { table_name: 'financial_statements', estimated_rows: 50000, table_category: 'financials' },
        { table_name: 'balance_sheets', estimated_rows: 25000, table_category: 'financials' },
        
        // Earnings category
        { table_name: 'earnings_estimates', estimated_rows: 12000, table_category: 'earnings' },
        { table_name: 'earnings_history', estimated_rows: 8000, table_category: 'earnings' },
        
        // Portfolio category
        { table_name: 'portfolio_holdings', estimated_rows: 150, table_category: 'portfolio' },
        { table_name: 'user_portfolios', estimated_rows: 50, table_category: 'portfolio' },
        
        // Market category
        { table_name: 'market_indices', estimated_rows: 500, table_category: 'market' },
        { table_name: 'sector_performance', estimated_rows: 200, table_category: 'market' },
        
        // News category
        { table_name: 'news_articles', estimated_rows: 10000, table_category: 'news' },
        { table_name: 'news_sentiment', estimated_rows: 8000, table_category: 'news' },
        
        // Analytics category
        { table_name: 'trading_signals', estimated_rows: 5000, table_category: 'analytics' },
        { table_name: 'pattern_matches', estimated_rows: 3000, table_category: 'analytics' },
        
        // Trading category
        { table_name: 'trade_history', estimated_rows: 1000, table_category: 'trading' },
        { table_name: 'trading_strategies', estimated_rows: 100, table_category: 'trading' },
        
        // System category
        { table_name: 'health_status', estimated_rows: 30, table_category: 'system' },
        { table_name: 'last_updated', estimated_rows: 15, table_category: 'system' },
        
        // Sentiment category
        { table_name: 'fear_greed_index', estimated_rows: 365, table_category: 'sentiment' }
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
            healthy_tables: mockTables.length,
            total_records: expect.any(Number)
          }),
          categories: expect.objectContaining({
            symbols: expect.any(Object),
            prices: expect.any(Object),
            technicals: expect.any(Object),
            financials: expect.any(Object),
            earnings: expect.any(Object),
            portfolio: expect.any(Object),
            market: expect.any(Object),
            news: expect.any(Object),
            analytics: expect.any(Object),
            trading: expect.any(Object),
            system: expect.any(Object),
            sentiment: expect.any(Object)
          })
        })
      });

      expect(healthCheck).toHaveBeenCalled();
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining('SELECT'),
        [],
        expect.any(Number)
      );
    });
  });

  describe('POST /api/health/update-status - Health Status Updates', () => {
    it('should successfully update health status with comprehensive database analysis', async () => {
      // Mock healthy database connection
      healthCheck.mockResolvedValueOnce({
        status: 'healthy',
        timestamp: new Date().toISOString(),
        version: 'PostgreSQL 14.9'
      });

      // Mock table information query
      query.mockResolvedValueOnce({
        rows: [
          {
            table_name: 'stock_symbols',
            table_type: 'BASE TABLE',
            estimated_rows: 5000,
            last_analyze: new Date().toISOString(),
            last_autovacuum: new Date().toISOString(),
            last_vacuum: new Date().toISOString(),
            last_autoanalyze: new Date().toISOString()
          },
          {
            table_name: 'portfolio_holdings',
            table_type: 'BASE TABLE',
            estimated_rows: 150,
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
        ]
      });

      // Mock health_status table existence check
      query.mockResolvedValueOnce({
        rows: [{ exists: 1 }]
      });

      // Mock health_status table insert/update operations
      query.mockResolvedValue({
        rows: [],
        rowCount: 1
      });

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
              total_tables: expect.any(Number),
              healthy_tables: expect.any(Number),
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
    });

    it('should handle database connection failure gracefully', async () => {
      // Mock database connection failure
      healthCheck.mockRejectedValueOnce(new Error('Connection refused'));

      const response = await request(app)
        .post('/api/health/update-status')
        .expect(200);

      expect(response.body).toMatchObject({
        status: 'success',
        message: 'Database health status updated successfully',
        data: expect.objectContaining({
          status: 'error',
          error: 'Connection refused',
          database: expect.objectContaining({
            status: 'error'
          })
        }),
        timestamp: expect.any(String)
      });

      expect(healthCheck).toHaveBeenCalled();
    });

    it('should measure all tables across database as requested by user', async () => {
      // Mock healthy database connection
      healthCheck.mockResolvedValueOnce({
        status: 'healthy',
        timestamp: new Date().toISOString(),
        version: 'PostgreSQL 14.9'
      });

      // Mock comprehensive table list with various table types
      const mockTables = [
        { table_name: 'stock_symbols', table_type: 'BASE TABLE', estimated_rows: 5000, last_analyze: new Date().toISOString() },
        { table_name: 'price_daily', table_type: 'BASE TABLE', estimated_rows: 1500000, last_analyze: new Date().toISOString() },
        { table_name: 'portfolio_holdings', table_type: 'BASE TABLE', estimated_rows: 150, last_analyze: new Date().toISOString() },
        { table_name: 'user_api_keys', table_type: 'BASE TABLE', estimated_rows: 25, last_analyze: new Date().toISOString() },
        { table_name: 'company_profiles', table_type: 'BASE TABLE', estimated_rows: 8000, last_analyze: new Date().toISOString() },
        { table_name: 'technicals_daily', table_type: 'BASE TABLE', estimated_rows: 800000, last_analyze: new Date().toISOString() },
        { table_name: 'earnings_estimates', table_type: 'BASE TABLE', estimated_rows: 12000, last_analyze: new Date().toISOString() },
        { table_name: 'fear_greed_index', table_type: 'BASE TABLE', estimated_rows: 365, last_analyze: new Date().toISOString() },
        { table_name: 'health_status', table_type: 'BASE TABLE', estimated_rows: 30, last_analyze: new Date().toISOString() },
        { table_name: 'last_updated', table_type: 'BASE TABLE', estimated_rows: 15, last_analyze: new Date().toISOString() }
      ];

      query.mockResolvedValueOnce({ rows: mockTables });

      // Mock health_status table existence check
      query.mockResolvedValueOnce({ rows: [{ exists: 1 }] });

      // Mock health_status table operations for each table
      for (let i = 0; i < mockTables.length; i++) {
        query.mockResolvedValueOnce({ rows: [], rowCount: 1 });
      }

      const response = await request(app)
        .post('/api/health/update-status')
        .expect(200);

      // Verify comprehensive analysis was performed
      expect(response.body.data.database.summary.total_tables).toBe(mockTables.length);
      expect(response.body.data.database.summary.total_records).toBeGreaterThan(0);
      
      // Verify all table categories are analyzed
      const tableNames = Object.keys(response.body.data.database.tables);
      expect(tableNames).toEqual(expect.arrayContaining([
        'stock_symbols', 'price_daily', 'portfolio_holdings', 'user_api_keys',
        'company_profiles', 'technicals_daily', 'earnings_estimates',
        'fear_greed_index', 'health_status', 'last_updated'
      ]));

      // Verify table categorization
      expect(response.body.data.database.tables.stock_symbols.table_category).toBe('symbols');
      expect(response.body.data.database.tables.price_daily.table_category).toBe('prices');
      expect(response.body.data.database.tables.portfolio_holdings.table_category).toBe('portfolio');
      expect(response.body.data.database.tables.earnings_estimates.table_category).toBe('earnings');
      expect(response.body.data.database.tables.fear_greed_index.table_category).toBe('sentiment');
      expect(response.body.data.database.tables.health_status.table_category).toBe('system');

      // Verify critical table marking
      expect(response.body.data.database.tables.stock_symbols.critical_table).toBe(true);
      expect(response.body.data.database.tables.portfolio_holdings.critical_table).toBe(true);
      expect(response.body.data.database.tables.health_status.critical_table).toBe(true);

      expect(console.log).toHaveBeenCalledWith(
        expect.stringMatching(/📋 Found \d+ tables in database/)
      );
    });

    it('should store health data in health_status table when it exists', async () => {
      // Mock healthy database
      healthCheck.mockResolvedValueOnce({
        status: 'healthy',
        timestamp: new Date().toISOString(),
        version: 'PostgreSQL 14.9'
      });

      // Mock table analysis
      query.mockResolvedValueOnce({
        rows: [
          { table_name: 'test_table', table_type: 'BASE TABLE', estimated_rows: 100, last_analyze: new Date().toISOString() }
        ]
      });

      // Mock health_status table exists
      query.mockResolvedValueOnce({ rows: [{ exists: 1 }] });

      // Mock successful insert/update
      query.mockResolvedValueOnce({ rows: [], rowCount: 1 });

      const response = await request(app)
        .post('/api/health/update-status')
        .expect(200);

      // Verify health_status table existence was checked
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining('SELECT COUNT(*) as exists')
      );

      // Verify health data was stored
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining('INSERT INTO health_status'),
        expect.any(Array)
      );

      expect(console.log).toHaveBeenCalledWith(
        expect.stringContaining('Health data stored in health_status table')
      );
    });

    it('should handle health_status table storage failure gracefully', async () => {
      // Mock healthy database
      healthCheck.mockResolvedValueOnce({
        status: 'healthy',
        timestamp: new Date().toISOString(),
        version: 'PostgreSQL 14.9'
      });

      // Mock table analysis
      query.mockResolvedValueOnce({
        rows: [
          { table_name: 'test_table', table_type: 'BASE TABLE', estimated_rows: 100, last_analyze: new Date().toISOString() }
        ]
      });

      // Mock health_status table exists
      query.mockResolvedValueOnce({ rows: [{ exists: 1 }] });

      // Mock storage failure
      query.mockRejectedValueOnce(new Error('Storage failed'));

      const response = await request(app)
        .post('/api/health/update-status')
        .expect(200); // Should still succeed despite storage failure

      expect(response.body.status).toBe('success');
      expect(console.warn).toHaveBeenCalledWith(
        expect.stringContaining('Failed to store health data'),
        expect.any(String)
      );
    });

    it('should skip storage when health_status table does not exist', async () => {
      // Mock healthy database
      healthCheck.mockResolvedValueOnce({
        status: 'healthy',
        timestamp: new Date().toISOString(),
        version: 'PostgreSQL 14.9'
      });

      // Mock table analysis
      query.mockResolvedValueOnce({
        rows: [
          { table_name: 'test_table', table_type: 'BASE TABLE', estimated_rows: 100, last_analyze: new Date().toISOString() }
        ]
      });

      // Mock health_status table does not exist
      query.mockResolvedValueOnce({ rows: [{ exists: 0 }] });

      const response = await request(app)
        .post('/api/health/update-status')
        .expect(200);

      expect(response.body.status).toBe('success');
      expect(console.log).toHaveBeenCalledWith(
        expect.stringContaining('health_status table does not exist - skipping storage')
      );
    });

    it('should provide performance information in response', async () => {
      // Mock healthy database with timing
      healthCheck.mockResolvedValueOnce({
        status: 'healthy',
        timestamp: new Date().toISOString(),
        version: 'PostgreSQL 14.9'
      });

      query.mockResolvedValueOnce({
        rows: [
          { table_name: 'test_table', table_type: 'BASE TABLE', estimated_rows: 100, last_analyze: new Date().toISOString() }
        ]
      });

      query.mockResolvedValueOnce({ rows: [{ exists: 0 }] });

      const response = await request(app)
        .post('/api/health/update-status')
        .expect(200);

      expect(response.body.data).toMatchObject({
        note: expect.stringContaining('Analyzed'),
        timestamp: expect.any(String)
      });

      expect(response.body.data.note).toMatch(/\d+ms$/); // Should end with timing in milliseconds
    });
  });
});