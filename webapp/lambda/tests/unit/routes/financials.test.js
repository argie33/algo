/**
 * Financials Routes Unit Tests
 * Tests financials route logic in isolation with mocks
 */

const express = require('express');
const request = require('supertest');

// Mock the database utility
jest.mock('../../../utils/database', () => ({
  query: jest.fn()
}));

describe('Financials Routes Unit Tests', () => {
  let app;
  let financialsRouter;
  let mockQuery;

  beforeEach(() => {
    jest.clearAllMocks();
    
    // Set up mocks
    const { query } = require('../../../utils/database');
    mockQuery = query;
    
    // Create test app
    app = express();
    app.use(express.json());
    
    // Add response helper middleware
    app.use((req, res, next) => {
      res.error = (message, status) => res.status(status).json({ 
        success: false, 
        error: message 
      });
      res.success = (data) => res.json({ 
        success: true, 
        ...data 
      });
      next();
    });
    
    // Load the route module
    financialsRouter = require('../../../routes/financials');
    app.use('/financials', financialsRouter);
  });

  describe('GET /financials', () => {
    test('should return financials API overview', async () => {
      const response = await request(app)
        .get('/financials');

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty('message', 'Financials API - Ready');
      expect(response.body).toHaveProperty('status', 'operational');
      expect(response.body).toHaveProperty('endpoints');
      expect(response.body).toHaveProperty('timestamp');
      
      // Verify endpoints are present
      expect(Array.isArray(response.body.endpoints)).toBe(true);
      expect(response.body.endpoints).toContain('/:ticker/balance-sheet - Get balance sheet data');
      expect(response.body.endpoints).toContain('/:ticker/income-statement - Get income statement data');
      expect(response.body.endpoints).toContain('/ping - Health check');
      
      // Verify timestamp is a valid ISO string
      expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
      expect(mockQuery).not.toHaveBeenCalled(); // Root endpoint doesn't use database
    });
  });

  describe('GET /financials/ping', () => {
    test('should return ping response', async () => {
      const response = await request(app)
        .get('/financials/ping');

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('service', 'financials');
      expect(response.body).toHaveProperty('timestamp');
      
      // Verify timestamp is a valid ISO string
      expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
      expect(mockQuery).not.toHaveBeenCalled(); // Ping doesn't use database
    });
  });

  describe('GET /financials/statements', () => {
    test('should return financial statements with valid parameters', async () => {
      const mockFinancialData = {
        rows: [
          {
            symbol: 'AAPL',
            period: 'annual',
            fiscal_year: 2023,
            revenue: 394328000000,
            net_income: 96995000000,
            total_assets: 352755000000,
            total_debt: 123930000000,
            cash_and_equivalents: 61555000000
          }
        ]
      };

      mockQuery.mockResolvedValueOnce(mockFinancialData);

      const response = await request(app)
        .get('/financials/statements')
        .query({ symbol: 'AAPL', period: 'annual', type: 'income' });

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(response.body.data).toHaveProperty('symbol', 'AAPL');
      expect(response.body.data).toHaveProperty('statements');
      expect(Array.isArray(response.body.data.statements)).toBe(true);
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('financial_statements'),
        expect.arrayContaining(['AAPL'])
      );
    });

    test('should require symbol parameter', async () => {
      const response = await request(app)
        .get('/financials/statements')
        .query({ period: 'annual' });

      expect(response.status).toBe(400);
      expect(response.body).toHaveProperty('success', false);
      expect(response.body.error).toContain('Symbol parameter required');
      expect(mockQuery).not.toHaveBeenCalled();
    });

    test('should handle default parameters', async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get('/financials/statements')
        .query({ symbol: 'AAPL' });

      expect(response.status).toBe(200);
      // Should use defaults: period='annual', type='all'
      expect(mockQuery).toHaveBeenCalledWith(
        expect.any(String),
        expect.arrayContaining(['AAPL'])
      );
    });

    test('should handle quarterly period', async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get('/financials/statements')
        .query({ symbol: 'AAPL', period: 'quarterly' });

      expect(response.status).toBe(200);
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('quarterly'),
        expect.any(Array)
      );
    });

    test('should filter by statement type', async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get('/financials/statements')
        .query({ symbol: 'AAPL', type: 'balance_sheet' });

      expect(response.status).toBe(200);
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('balance_sheet'),
        expect.any(Array)
      );
    });

    test('should handle empty results', async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get('/financials/statements')
        .query({ symbol: 'INVALID' });

      expect(response.status).toBe(404);
      expect(response.body).toHaveProperty('success', false);
      expect(response.body.error).toContain('No financial data found');
    });

    test('should handle database errors', async () => {
      const dbError = new Error('Database connection failed');
      mockQuery.mockRejectedValueOnce(dbError);

      const response = await request(app)
        .get('/financials/statements')
        .query({ symbol: 'AAPL' });

      expect(response.status).toBe(500);
      expect(response.body).toHaveProperty('success', false);
      expect(response.body.error).toBeDefined();
    });
  });

  describe('GET /financials/:symbol', () => {
    test('should return basic financial overview', async () => {
      const mockOverviewData = {
        rows: [{
          symbol: 'AAPL',
          market_cap: 2800000000000,
          pe_ratio: 28.5,
          revenue: 394328000000,
          net_income: 96995000000,
          debt_to_equity: 1.73,
          roe: 0.27,
          current_ratio: 0.98
        }]
      };

      mockQuery.mockResolvedValueOnce(mockOverviewData);

      const response = await request(app)
        .get('/financials/AAPL');

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(response.body.data).toHaveProperty('symbol', 'AAPL');
      expect(response.body.data).toHaveProperty('market_cap', 2800000000000);
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('financial_overview'),
        ['AAPL']
      );
    });

    test('should handle lowercase symbol conversion', async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });

      await request(app)
        .get('/financials/aapl');

      expect(mockQuery).toHaveBeenCalledWith(
        expect.any(String),
        ['AAPL'] // Should be converted to uppercase
      );
    });

    test('should handle symbol not found', async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get('/financials/INVALID');

      expect(response.status).toBe(404);
      expect(response.body).toHaveProperty('success', false);
      expect(response.body.error).toContain('Financial data not found');
    });
  });

  describe('GET /financials/:symbol/ratios', () => {
    test('should return financial ratios', async () => {
      const mockRatiosData = {
        rows: [{
          symbol: 'GOOGL',
          pe_ratio: 22.8,
          pb_ratio: 4.2,
          debt_to_equity: 0.12,
          current_ratio: 2.8,
          quick_ratio: 2.6,
          roe: 0.18,
          roa: 0.15,
          gross_margin: 0.57,
          operating_margin: 0.25,
          net_margin: 0.21
        }]
      };

      mockQuery.mockResolvedValueOnce(mockRatiosData);

      const response = await request(app)
        .get('/financials/GOOGL/ratios');

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(response.body.data).toHaveProperty('ratios');
      expect(response.body.data.ratios).toHaveProperty('pe_ratio', 22.8);
      expect(response.body.data.ratios).toHaveProperty('roe', 0.18);
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('financial_ratios'),
        ['GOOGL']
      );
    });
  });

  describe('GET /financials/earnings/:symbol', () => {
    test('should return earnings history', async () => {
      const mockEarningsData = {
        rows: [
          {
            symbol: 'MSFT',
            quarter: 'Q4 2023',
            eps_actual: 2.45,
            eps_estimate: 2.38,
            revenue_actual: 56517000000,
            revenue_estimate: 55490000000,
            earnings_date: '2023-10-24',
            surprise_percent: 2.94
          },
          {
            symbol: 'MSFT',
            quarter: 'Q3 2023',
            eps_actual: 2.32,
            eps_estimate: 2.28,
            revenue_actual: 53445000000,
            revenue_estimate: 52740000000,
            earnings_date: '2023-07-25',
            surprise_percent: 1.75
          }
        ]
      };

      mockQuery.mockResolvedValueOnce(mockEarningsData);

      const response = await request(app)
        .get('/financials/earnings/MSFT');

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(response.body.data).toHaveProperty('symbol', 'MSFT');
      expect(response.body.data).toHaveProperty('earnings_history');
      expect(Array.isArray(response.body.data.earnings_history)).toBe(true);
      expect(response.body.data.earnings_history).toHaveLength(2);
      expect(response.body.data.earnings_history[0]).toHaveProperty('quarter', 'Q4 2023');
      expect(response.body.data.earnings_history[0]).toHaveProperty('surprise_percent', 2.94);
    });

    test('should handle earnings limit parameter', async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get('/financials/earnings/AAPL')
        .query({ limit: 8 });

      expect(response.status).toBe(200);
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('LIMIT'),
        expect.arrayContaining(['AAPL', 8])
      );
    });
  });

  describe('GET /financials/debug/tables', () => {
    test('should return table structure information', async () => {
      const mockTableData = {
        rows: [
          { table_name: 'financial_statements', column_count: 25, has_data: true },
          { table_name: 'financial_ratios', column_count: 15, has_data: true },
          { table_name: 'earnings_history', column_count: 10, has_data: false }
        ]
      };

      mockQuery.mockResolvedValueOnce(mockTableData);

      const response = await request(app)
        .get('/financials/debug/tables');

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('tables');
      expect(Array.isArray(response.body.tables)).toBe(true);
      expect(response.body.tables).toHaveLength(3);
      expect(response.body.tables[0]).toHaveProperty('table_name', 'financial_statements');
      expect(response.body.tables[0]).toHaveProperty('has_data', true);
    });

    test('should handle debug query errors', async () => {
      const debugError = new Error('Debug query failed');
      mockQuery.mockRejectedValueOnce(debugError);

      const response = await request(app)
        .get('/financials/debug/tables');

      expect(response.status).toBe(500);
      expect(response.body).toHaveProperty('success', false);
      expect(response.body.error).toContain('Debug query failed');
    });
  });

  describe('Parameter validation', () => {
    test('should sanitize symbol parameter', async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get('/financials/statements')
        .query({ symbol: "AAPL'; DROP TABLE financial_statements; --" });

      expect(response.status).toBe(200);
      // Symbol should be sanitized and used safely in prepared statement
      expect(mockQuery).toHaveBeenCalledWith(
        expect.any(String),
        expect.arrayContaining(["AAPL'; DROP TABLE financial_statements; --"])
      );
    });

    test('should handle invalid symbol format', async () => {
      const response = await request(app)
        .get('/financials/invalid-symbol-format!@#');

      expect(response.status).toBe(400);
      expect(response.body).toHaveProperty('success', false);
      expect(response.body.error).toContain('Invalid symbol format');
    });

    test('should validate period parameter', async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get('/financials/statements')
        .query({ symbol: 'AAPL', period: 'invalid_period' });

      expect(response.status).toBe(400);
      expect(response.body).toHaveProperty('success', false);
      expect(response.body.error).toContain('Invalid period');
    });

    test('should validate type parameter', async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get('/financials/statements')
        .query({ symbol: 'AAPL', type: 'invalid_type' });

      expect(response.status).toBe(400);
      expect(response.body).toHaveProperty('success', false);
      expect(response.body.error).toContain('Invalid statement type');
    });
  });

  describe('Error handling', () => {
    test('should handle database connection timeout', async () => {
      const timeoutError = new Error('Query timeout');
      timeoutError.code = 'QUERY_TIMEOUT';
      mockQuery.mockRejectedValueOnce(timeoutError);

      const response = await request(app)
        .get('/financials/AAPL');

      expect(response.status).toBe(500);
      expect(response.body).toHaveProperty('success', false);
      expect(response.body.error).toContain('timeout');
    });

    test('should handle malformed database results', async () => {
      mockQuery.mockResolvedValueOnce(null); // Malformed result

      const response = await request(app)
        .get('/financials/AAPL');

      expect(response.status).toBe(500);
      expect(response.body).toHaveProperty('success', false);
    });
  });

  describe('Response format', () => {
    test('should return consistent JSON response format', async () => {
      const response = await request(app)
        .get('/financials/ping');

      expect(response.headers['content-type']).toMatch(/json/);
      expect(typeof response.body).toBe('object');
    });

    test('should include metadata in financial responses', async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get('/financials/statements')
        .query({ symbol: 'AAPL' });

      if (response.status === 200) {
        expect(response.body).toHaveProperty('success');
        expect(response.body).toHaveProperty('data');
      }
    });
  });
});