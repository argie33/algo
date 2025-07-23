/**
 * Health Update Status Endpoint Unit Tests
 * Tests the /update-status endpoint for comprehensive database health analysis
 */

const request = require('supertest');
const express = require('express');
const healthRouter = require('../../../routes/health');

// Mock all external dependencies
jest.mock('../../../utils/database', () => ({
  healthCheck: jest.fn(),
  query: jest.fn(),
  validateDatabaseSchema: jest.fn()
}));

const { healthCheck, query } = require('../../../utils/database');

describe('Health Update Status Endpoint', () => {
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
    
    app.use('/api/health-full', healthRouter);
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

  describe('POST /api/health-full/update-status', () => {
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
        .post('/api/health-full/update-status')
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
        .post('/api/health-full/update-status')
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
        .post('/api/health-full/update-status')
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
        .post('/api/health-full/update-status')
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
        .post('/api/health-full/update-status')
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
        .post('/api/health-full/update-status')
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
        .post('/api/health-full/update-status')
        .expect(200);

      expect(response.body.data).toMatchObject({
        note: expect.stringContaining('Analyzed'),
        timestamp: expect.any(String)
      });

      expect(response.body.data.note).toMatch(/\d+ms$/); // Should end with timing in milliseconds
    });
  });
});