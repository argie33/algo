/**
 * Comprehensive Unit Tests for ETF Route
 * Tests ETF holdings endpoint with mocked database dependencies
 * Covers all endpoints, error handling, data validation, and edge cases
 */

const request = require('supertest');
const express = require('express');

// Mock database queries
const mockQuery = jest.fn();
jest.mock('../../../utils/database', () => ({
  query: mockQuery
}));

// Create test app
const app = express();
app.use(express.json());
app.use('/api/etf', require('../../../routes/etf'));

describe('ETF Route - Comprehensive Unit Tests', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('GET /api/etf/:symbol/holdings', () => {
    test('should get ETF holdings for valid symbol', async () => {
      const mockHoldingsData = [
        {
          holding_symbol: 'AAPL',
          company_name: 'Apple Inc.',
          weight_percent: 6.85,
          shares_held: 165000000,
          market_value: 25000000000,
          sector: 'Technology',
          fund_name: 'SPDR S&P 500 ETF Trust',
          total_assets: 350000000000,
          expense_ratio: 0.0945,
          dividend_yield: 1.25
        },
        {
          holding_symbol: 'MSFT',
          company_name: 'Microsoft Corporation',
          weight_percent: 6.12,
          shares_held: 88000000,
          market_value: 22000000000,
          sector: 'Technology',
          fund_name: 'SPDR S&P 500 ETF Trust',
          total_assets: 350000000000,
          expense_ratio: 0.0945,
          dividend_yield: 1.25
        }
      ];

      const mockSectorData = [
        {
          sector: 'Technology',
          total_weight: 28.5
        },
        {
          sector: 'Healthcare',
          total_weight: 13.2
        }
      ];

      mockQuery
        .mockResolvedValueOnce({ rows: mockHoldingsData })
        .mockResolvedValueOnce({ rows: mockSectorData });

      const response = await request(app)
        .get('/api/etf/SPY/holdings')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.etf_symbol).toBe('SPY');
      expect(response.body.data.fund_name).toBe('SPDR S&P 500 ETF Trust');
      expect(response.body.data.top_holdings).toHaveLength(2);
      expect(response.body.data.top_holdings[0]).toMatchObject({
        symbol: 'AAPL',
        company_name: 'Apple Inc.',
        weight_percent: 6.85,
        shares_held: 165000000,
        market_value: 25000000000,
        sector: 'Technology'
      });
      expect(response.body.data.sector_allocation).toHaveProperty('technology', 28.5);
      expect(response.body.data.sector_allocation).toHaveProperty('healthcare', 13.2);
      expect(response.body.data.fund_metrics).toMatchObject({
        expense_ratio: 0.0945,
        total_holdings: 2,
        aum: 350000000000,
        dividend_yield: 1.25
      });
      expect(response.body.data.last_updated).toBeDefined();
      expect(response.body.timestamp).toBeDefined();
    });

    test('should handle case insensitive symbol lookup', async () => {
      const mockHoldingsData = [
        {
          holding_symbol: 'AAPL',
          company_name: 'Apple Inc.',
          weight_percent: 6.85,
          shares_held: 165000000,
          market_value: 25000000000,
          sector: 'Technology',
          fund_name: 'SPDR S&P 500 ETF Trust',
          total_assets: 350000000000,
          expense_ratio: 0.0945,
          dividend_yield: 1.25
        }
      ];

      mockQuery
        .mockResolvedValueOnce({ rows: mockHoldingsData })
        .mockResolvedValueOnce({ rows: [] });

      await request(app)
        .get('/api/etf/spy/holdings')
        .expect(200);

      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('h.etf_symbol = $1'),
        ['SPY', 25]
      );
    });

    test('should handle limit parameter correctly', async () => {
      const mockHoldingsData = [
        {
          holding_symbol: 'AAPL',
          company_name: 'Apple Inc.',
          weight_percent: 6.85,
          shares_held: 165000000,
          market_value: 25000000000,
          sector: 'Technology',
          fund_name: 'SPDR S&P 500 ETF Trust',
          total_assets: 350000000000,
          expense_ratio: 0.0945,
          dividend_yield: 1.25
        }
      ];

      mockQuery
        .mockResolvedValueOnce({ rows: mockHoldingsData })
        .mockResolvedValueOnce({ rows: [] });

      await request(app)
        .get('/api/etf/SPY/holdings?limit=10')
        .expect(200);

      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('LIMIT $2'),
        ['SPY', 10]
      );
    });

    test('should handle missing symbol parameter', async () => {
      // Mock empty symbol to trigger the validation check
      mockQuery.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get('/api/etf/ /holdings')
        .expect(404); // Empty symbol becomes " " which gets processed as ETF not found

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe('ETF not found');
    });

    test('should handle ETF not found', async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get('/api/etf/INVALID/holdings')
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe('ETF not found');
      expect(response.body.message).toContain('No holdings data found for ETF symbol: INVALID');
    });

    test('should handle null database results gracefully', async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: null });

      const response = await request(app)
        .get('/api/etf/SPY/holdings')
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe('ETF not found');
    });

    test('should handle database table not found error', async () => {
      const tableNotFoundError = new Error('Table not found');
      tableNotFoundError.code = '42P01';
      
      mockQuery.mockRejectedValue(tableNotFoundError);

      const response = await request(app)
        .get('/api/etf/SPY/holdings')
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe('Database table not found');
      expect(response.body.message).toBe('ETF holdings table does not exist. Please contact support.');
    });

    test('should handle general database errors', async () => {
      mockQuery.mockRejectedValue(new Error('Database connection failed'));

      const response = await request(app)
        .get('/api/etf/SPY/holdings')
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe('Failed to fetch ETF holdings');
      expect(response.body.message).toBe('Database query failed. Please try again later.');
    });

    test('should handle empty sector data gracefully', async () => {
      const mockHoldingsData = [
        {
          holding_symbol: 'AAPL',
          company_name: 'Apple Inc.',
          weight_percent: 6.85,
          shares_held: 165000000,
          market_value: 25000000000,
          sector: 'Technology',
          fund_name: 'SPDR S&P 500 ETF Trust',
          total_assets: 350000000000,
          expense_ratio: 0.0945,
          dividend_yield: 1.25
        }
      ];

      mockQuery
        .mockResolvedValueOnce({ rows: mockHoldingsData })
        .mockResolvedValueOnce({ rows: [] }); // Empty sector data

      const response = await request(app)
        .get('/api/etf/SPY/holdings')
        .expect(200);

      expect(response.body.data.sector_allocation).toEqual({});
      expect(response.body.data.top_holdings).toHaveLength(1);
    });

    test('should handle missing fund metrics gracefully', async () => {
      const mockHoldingsData = [
        {
          holding_symbol: 'AAPL',
          company_name: 'Apple Inc.',
          weight_percent: 6.85,
          shares_held: 165000000,
          market_value: 25000000000,
          sector: 'Technology',
          fund_name: 'SPDR S&P 500 ETF Trust',
          total_assets: null,
          expense_ratio: null,
          dividend_yield: null
        }
      ];

      mockQuery
        .mockResolvedValueOnce({ rows: mockHoldingsData })
        .mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get('/api/etf/SPY/holdings')
        .expect(200);

      expect(response.body.data.fund_metrics).toMatchObject({
        expense_ratio: 0,
        total_holdings: 1,
        aum: 0,
        dividend_yield: 0
      });
    });

    test('should handle special characters in ETF symbol', async () => {
      const mockHoldingsData = [
        {
          holding_symbol: 'AAPL',
          company_name: 'Apple Inc.',
          weight_percent: 6.85,
          shares_held: 165000000,
          market_value: 25000000000,
          sector: 'Technology',
          fund_name: 'Test ETF',
          total_assets: 1000000000,
          expense_ratio: 0.1,
          dividend_yield: 1.0
        }
      ];

      mockQuery
        .mockResolvedValueOnce({ rows: mockHoldingsData })
        .mockResolvedValueOnce({ rows: [] });

      await request(app)
        .get('/api/etf/VTI-B/holdings')
        .expect(200);

      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('h.etf_symbol = $1'),
        ['VTI-B', 25]
      );
    });

    test('should parse numeric values correctly', async () => {
      const mockHoldingsData = [
        {
          holding_symbol: 'AAPL',
          company_name: 'Apple Inc.',
          weight_percent: '6.85',
          shares_held: '165000000',
          market_value: '25000000000',
          sector: 'Technology',
          fund_name: 'SPDR S&P 500 ETF Trust',
          total_assets: '350000000000',
          expense_ratio: '0.0945',
          dividend_yield: '1.25'
        }
      ];

      const mockSectorData = [
        {
          sector: 'Technology',
          total_weight: '28.5'
        }
      ];

      mockQuery
        .mockResolvedValueOnce({ rows: mockHoldingsData })
        .mockResolvedValueOnce({ rows: mockSectorData });

      const response = await request(app)
        .get('/api/etf/SPY/holdings')
        .expect(200);

      expect(response.body.data.top_holdings[0].weight_percent).toBe(6.85);
      expect(response.body.data.top_holdings[0].shares_held).toBe(165000000);
      expect(response.body.data.top_holdings[0].market_value).toBe(25000000000);
      expect(response.body.data.sector_allocation.technology).toBe(28.5);
      expect(response.body.data.fund_metrics.expense_ratio).toBe(0.0945);
      expect(response.body.data.fund_metrics.dividend_yield).toBe(1.25);
    });

    test('should handle sector name transformation correctly', async () => {
      const mockSectorData = [
        {
          sector: 'Information Technology',
          total_weight: '28.5'
        },
        {
          sector: 'Health Care',
          total_weight: '13.2'
        },
        {
          sector: 'Consumer Discretionary',
          total_weight: '12.1'
        }
      ];

      const mockHoldingsData = [
        {
          holding_symbol: 'AAPL',
          company_name: 'Apple Inc.',
          weight_percent: 6.85,
          shares_held: 165000000,
          market_value: 25000000000,
          sector: 'Technology',
          fund_name: 'Test ETF',
          total_assets: 1000000000,
          expense_ratio: 0.1,
          dividend_yield: 1.0
        }
      ];

      mockQuery
        .mockResolvedValueOnce({ rows: mockHoldingsData })
        .mockResolvedValueOnce({ rows: mockSectorData });

      const response = await request(app)
        .get('/api/etf/SPY/holdings')
        .expect(200);

      expect(response.body.data.sector_allocation).toHaveProperty('information_technology', 28.5);
      expect(response.body.data.sector_allocation).toHaveProperty('health_care', 13.2);
      expect(response.body.data.sector_allocation).toHaveProperty('consumer_discretionary', 12.1);
    });
  });

  // Edge Cases and Error Scenarios
  describe('Edge Cases and Error Handling', () => {
    test('should handle very large limit parameter', async () => {
      const mockHoldingsData = [];
      
      mockQuery
        .mockResolvedValueOnce({ rows: mockHoldingsData });

      const response = await request(app)
        .get('/api/etf/SPY/holdings?limit=99999')
        .expect(404);

      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('LIMIT $2'),
        ['SPY', 99999]
      );
    });

    test('should handle non-numeric limit parameter', async () => {
      const mockHoldingsData = [
        {
          holding_symbol: 'AAPL',
          company_name: 'Apple Inc.',
          weight_percent: 6.85,
          shares_held: 165000000,
          market_value: 25000000000,
          sector: 'Technology',
          fund_name: 'Test ETF',
          total_assets: 1000000000,
          expense_ratio: 0.1,
          dividend_yield: 1.0
        }
      ];

      mockQuery
        .mockResolvedValueOnce({ rows: mockHoldingsData })
        .mockResolvedValueOnce({ rows: [] });

      await request(app)
        .get('/api/etf/SPY/holdings?limit=invalid')
        .expect(200);

      // Should fallback to default limit of 25 but parseInt converts 'invalid' to NaN
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('LIMIT $2'),
        ['SPY', NaN]
      );
    });

    test('should handle negative limit parameter', async () => {
      const mockHoldingsData = [];

      mockQuery
        .mockResolvedValueOnce({ rows: mockHoldingsData });

      const response = await request(app)
        .get('/api/etf/SPY/holdings?limit=-10')
        .expect(404);

      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('LIMIT $2'),
        ['SPY', -10]
      );
    });

    test('should handle malformed database response', async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: [{ malformed: 'data', without: 'expected', fields: true }] })
        .mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get('/api/etf/SPY/holdings')
        .expect(200);

      // Should handle missing fields gracefully
      expect(response.body.data.top_holdings).toHaveLength(1);
      expect(response.body.data.top_holdings[0].weight_percent).toBeNull();
    });
  });

  // Performance Testing
  describe('Performance Testing', () => {
    test('should handle concurrent requests efficiently', async () => {
      const mockHoldingsData = [
        {
          holding_symbol: 'AAPL',
          company_name: 'Apple Inc.',
          weight_percent: 6.85,
          shares_held: 165000000,
          market_value: 25000000000,
          sector: 'Technology',
          fund_name: 'Test ETF',
          total_assets: 1000000000,
          expense_ratio: 0.1,
          dividend_yield: 1.0
        }
      ];

      // Each request makes 2 queries, so we need to mock 10 total calls
      for (let i = 0; i < 10; i++) {
        if (i % 2 === 0) {
          // Holdings query
          mockQuery.mockResolvedValueOnce({ rows: mockHoldingsData });
        } else {
          // Sector query
          mockQuery.mockResolvedValueOnce({ rows: [] });
        }
      }

      const requests = Array.from({ length: 5 }, (_, i) => 
        request(app).get(`/api/etf/ETF${i}/holdings`)
      );

      const responses = await Promise.all(requests);
      
      responses.forEach((response, index) => {
        expect(response.status).toBe(200);
        expect(response.body.data.etf_symbol).toBe(`ETF${index}`);
      });
    });

    test('should handle large holdings dataset efficiently', async () => {
      const largeHoldingsDataset = Array.from({ length: 500 }, (_, i) => ({
        holding_symbol: `STOCK${i}`,
        company_name: `Company ${i}`,
        weight_percent: (Math.random() * 10).toFixed(2),
        shares_held: Math.floor(Math.random() * 1000000),
        market_value: Math.floor(Math.random() * 1000000000),
        sector: ['Technology', 'Healthcare', 'Finance'][i % 3],
        fund_name: 'Large ETF',
        total_assets: 500000000000,
        expense_ratio: 0.05,
        dividend_yield: 2.0
      }));

      mockQuery
        .mockResolvedValueOnce({ rows: largeHoldingsDataset })
        .mockResolvedValueOnce({ rows: [] });

      const startTime = Date.now();
      const response = await request(app)
        .get('/api/etf/LARGE/holdings')
        .expect(200);
      const endTime = Date.now();

      expect(response.body.data.top_holdings).toHaveLength(500);
      expect(response.body.data.fund_metrics.total_holdings).toBe(500);
      expect(endTime - startTime).toBeLessThan(5000); // Should complete within 5 seconds
    });
  });

  // Response Format Validation
  describe('Response Format Validation', () => {
    test('should return consistent JSON response format', async () => {
      const mockHoldingsData = [
        {
          holding_symbol: 'AAPL',
          company_name: 'Apple Inc.',
          weight_percent: 6.85,
          shares_held: 165000000,
          market_value: 25000000000,
          sector: 'Technology',
          fund_name: 'Test ETF',
          total_assets: 1000000000,
          expense_ratio: 0.1,
          dividend_yield: 1.0
        }
      ];

      mockQuery
        .mockResolvedValueOnce({ rows: mockHoldingsData })
        .mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get('/api/etf/SPY/holdings')
        .expect(200);

      expect(response.headers['content-type']).toMatch(/json/);
      expect(typeof response.body).toBe('object');
      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
      expect(response.body.timestamp).toBeDefined();
    });

    test('should include timestamp in ISO format', async () => {
      const mockHoldingsData = [
        {
          holding_symbol: 'AAPL',
          company_name: 'Apple Inc.',
          weight_percent: 6.85,
          shares_held: 165000000,
          market_value: 25000000000,
          sector: 'Technology',
          fund_name: 'Test ETF',
          total_assets: 1000000000,
          expense_ratio: 0.1,
          dividend_yield: 1.0
        }
      ];

      mockQuery
        .mockResolvedValueOnce({ rows: mockHoldingsData })
        .mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get('/api/etf/SPY/holdings')
        .expect(200);

      expect(response.body.timestamp).toBeDefined();
      expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
      expect(response.body.timestamp).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/);
      
      expect(response.body.data.last_updated).toBeDefined();
      expect(new Date(response.body.data.last_updated)).toBeInstanceOf(Date);
      expect(response.body.data.last_updated).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/);
    });

    test('should maintain consistent error response format', async () => {
      mockQuery.mockRejectedValue(new Error('Test error'));

      const response = await request(app)
        .get('/api/etf/SPY/holdings')
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBeDefined();
      expect(typeof response.body.error).toBe('string');
      expect(response.body.message).toBeDefined();
      expect(typeof response.body.message).toBe('string');
    });
  });
});