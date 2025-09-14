/**
 * Economic Routes Unit Tests
 * Tests economic route logic in isolation with mocks
 */

const express = require('express');
const request = require('supertest');

// Mock the database utility
jest.mock('../../../utils/database', () => ({
  query: jest.fn()
}));

describe('Economic Routes Unit Tests', () => {
  let app;
  let economicRouter;
  let mockQuery;

  beforeEach(() => {
    jest.clearAllMocks();
    
    // Set up mocks
    const { query } = require('../../../utils/database');
    mockQuery = query;
    
    // Create test app
    app = express();
    app.use(express.json());
    
    // Load the route module
    economicRouter = require('../../../routes/economic');
    app.use('/economic', economicRouter);
  });

  describe('GET /economic', () => {
    test('should return economic data with pagination', async () => {
      const mockEconomicData = [
        {
          series_id: 'GDP',
          date: '2024-01-01',
          value: 25000000000
        },
        {
          series_id: 'CPI',
          date: '2024-01-01',
          value: 310.5
        }
      ];

      const mockCount = [{ total: '150' }];

      mockQuery
        .mockResolvedValueOnce({ rows: mockEconomicData })
        .mockResolvedValueOnce({ rows: mockCount });

      const response = await request(app)
        .get('/economic');

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty('data', mockEconomicData);
      expect(response.body).toHaveProperty('pagination');
      expect(response.body.pagination).toMatchObject({
        page: 1,
        limit: 25,
        total: 150,
        totalPages: 6,
        hasNext: true,
        hasPrev: false
      });

      expect(mockQuery).toHaveBeenCalledTimes(2);
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('FROM economic_data'),
        [25, 0]
      );
    });

    test('should handle pagination parameters', async () => {
      const mockData = [{ series_id: 'GDP', date: '2024-01-01', value: 25000000000 }];
      const mockCount = [{ total: '100' }];

      mockQuery
        .mockResolvedValueOnce({ rows: mockData })
        .mockResolvedValueOnce({ rows: mockCount });

      const response = await request(app)
        .get('/economic?page=3&limit=10');

      expect(response.body.pagination).toMatchObject({
        page: 3,
        limit: 10,
        total: 100,
        totalPages: 10,
        hasNext: true,
        hasPrev: true
      });

      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('LIMIT $1 OFFSET $2'),
        [10, 20]
      );
    });

    test('should filter by series parameter', async () => {
      const mockData = [{ series_id: 'GDP', date: '2024-01-01', value: 25000000000 }];
      const mockCount = [{ total: '25' }];

      mockQuery
        .mockResolvedValueOnce({ rows: mockData })
        .mockResolvedValueOnce({ rows: mockCount });

      const response = await request(app)
        .get('/economic?series=GDP&page=1&limit=50');

      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('WHERE series_id = $1'),
        ['GDP', 50, 0]
      );

      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('WHERE series_id = $1'),
        ['GDP']
      );
    });

    test('should handle database unavailable gracefully', async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce(null);

      const response = await request(app)
        .get('/economic');

      expect(response.status).toBe(503);
      expect(response.body).toHaveProperty('success', false);
      expect(response.body).toHaveProperty('error', 'Database temporarily unavailable');
      expect(response.body).toHaveProperty('data', []);
      expect(response.body.pagination).toMatchObject({
        page: 1,
        limit: 25,
        total: 0,
        totalPages: 0,
        hasNext: false,
        hasPrev: false
      });
    });

    test('should return 404 when no economic data found', async () => {
      const mockCount = [{ total: '0' }];

      mockQuery
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: mockCount });

      const response = await request(app)
        .get('/economic');

      expect(response.status).toBe(404);
      expect(response.body).toHaveProperty('success', false);
      expect(response.body).toHaveProperty('error', 'No data found for this query');
    });

    test('should return 404 when null economic data result', async () => {
      const mockCount = [{ total: '5' }];

      mockQuery
        .mockResolvedValueOnce(null)
        .mockResolvedValueOnce({ rows: mockCount });

      const response = await request(app)
        .get('/economic');

      expect(response.status).toBe(404);
      expect(response.body).toHaveProperty('error', 'No data found for this query');
    });

    test('should handle database errors', async () => {
      mockQuery.mockRejectedValue(new Error('Database connection failed'));

      const response = await request(app)
        .get('/economic');

      expect(response.status).toBe(500);
      expect(response.body).toHaveProperty('success', false);
      expect(response.body).toHaveProperty('error', 'Database error');
      expect(response.body).toHaveProperty('message', 'Database connection failed');
    });

    test('should handle count query returning empty result', async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get('/economic');

      expect(response.status).toBe(503);
      expect(response.body).toHaveProperty('error', 'Database temporarily unavailable');
    });
  });

  describe('GET /economic/data', () => {
    test('should return economic data for DataValidation page', async () => {
      const mockEconomicData = [
        {
          series_id: 'GDP',
          date: '2024-01-01',
          value: 25000000000
        },
        {
          series_id: 'CPI',
          date: '2023-12-01',
          value: 310.2
        },
        {
          series_id: 'UNEMPLOYMENT',
          date: '2023-12-01',
          value: 3.7
        }
      ];

      mockQuery.mockResolvedValue({ rows: mockEconomicData });

      const response = await request(app)
        .get('/economic/data');

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty('data', mockEconomicData);
      expect(response.body).toHaveProperty('count', 3);
      expect(response.body).toHaveProperty('limit', 50);
      expect(response.body).toHaveProperty('timestamp');

      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('ORDER BY date DESC, series_id ASC'),
        [50]
      );
    });

    test('should handle limit parameter with maximum cap', async () => {
      const mockData = [{ series_id: 'GDP', date: '2024-01-01', value: 25000000000 }];

      mockQuery.mockResolvedValue({ rows: mockData });

      const response = await request(app)
        .get('/economic/data?limit=200');

      expect(response.body.limit).toBe(100); // Capped at 100
      expect(mockQuery).toHaveBeenCalledWith(expect.any(String), [100]);
    });

    test('should handle small limit parameter', async () => {
      const mockData = [{ series_id: 'GDP', date: '2024-01-01', value: 25000000000 }];

      mockQuery.mockResolvedValue({ rows: mockData });

      const response = await request(app)
        .get('/economic/data?limit=10');

      expect(response.body.limit).toBe(10);
      expect(mockQuery).toHaveBeenCalledWith(expect.any(String), [10]);
    });

    test('should use default limit when not provided', async () => {
      const mockData = [{ series_id: 'GDP', date: '2024-01-01', value: 25000000000 }];

      mockQuery.mockResolvedValue({ rows: mockData });

      const response = await request(app)
        .get('/economic/data');

      expect(response.body.limit).toBe(50);
      expect(mockQuery).toHaveBeenCalledWith(expect.any(String), [50]);
    });

    test('should return 404 when no data found', async () => {
      mockQuery.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get('/economic/data');

      expect(response.status).toBe(404);
      expect(response.body).toHaveProperty('success', false);
      expect(response.body).toHaveProperty('error', 'No data found for this query');
    });

    test('should return 404 when null result', async () => {
      mockQuery.mockResolvedValue(null);

      const response = await request(app)
        .get('/economic/data');

      expect(response.status).toBe(404);
      expect(response.body).toHaveProperty('error', 'No data found for this query');
    });

    test('should return 404 when undefined rows', async () => {
      mockQuery.mockResolvedValue({ rows: undefined });

      const response = await request(app)
        .get('/economic/data');

      expect(response.status).toBe(404);
      expect(response.body).toHaveProperty('error', 'No data found for this query');
    });

    test('should handle database errors', async () => {
      mockQuery.mockRejectedValue(new Error('Query timeout'));

      const response = await request(app)
        .get('/economic/data');

      expect(response.status).toBe(500);
      expect(response.body).toHaveProperty('success', false);
      expect(response.body).toHaveProperty('error', 'Database error');
      expect(response.body).toHaveProperty('message', 'Query timeout');
    });

    test('should include timestamp in ISO format', async () => {
      const mockData = [{ series_id: 'GDP', date: '2024-01-01', value: 25000000000 }];

      mockQuery.mockResolvedValue({ rows: mockData });

      const response = await request(app)
        .get('/economic/data');

      expect(response.body.timestamp).toBeDefined();
      expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
      expect(response.body.timestamp).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/);
    });
  });

  describe('Edge cases and error handling', () => {
    test('should handle invalid page numbers', async () => {
      const mockData = [{ series_id: 'GDP', date: '2024-01-01', value: 25000000000 }];
      const mockCount = [{ total: '50' }];

      mockQuery
        .mockResolvedValueOnce({ rows: mockData })
        .mockResolvedValueOnce({ rows: mockCount });

      const response = await request(app)
        .get('/economic?page=invalid&limit=notanumber');

      expect(response.body.pagination.page).toBe(1); // Default page
      expect(response.body.pagination.limit).toBe(25); // Default limit
    });

    test('should handle negative page and limit', async () => {
      const mockData = [{ series_id: 'GDP', date: '2024-01-01', value: 25000000000 }];
      const mockCount = [{ total: '50' }];

      mockQuery
        .mockResolvedValueOnce({ rows: mockData })
        .mockResolvedValueOnce({ rows: mockCount });

      const response = await request(app)
        .get('/economic?page=-5&limit=-10');

      expect(response.body.pagination.page).toBe(1); // Defaults to 1
      expect(response.body.pagination.limit).toBe(25); // Defaults to 25
    });

    test('should handle very large page numbers', async () => {
      const mockData = [{ series_id: 'GDP', date: '2024-01-01', value: 25000000000 }];
      const mockCount = [{ total: '10' }];

      mockQuery
        .mockResolvedValueOnce({ rows: mockData })
        .mockResolvedValueOnce({ rows: mockCount });

      const response = await request(app)
        .get('/economic?page=999&limit=25');

      expect(response.body.pagination).toMatchObject({
        page: 999,
        limit: 25,
        total: 10,
        totalPages: 1,
        hasNext: false,
        hasPrev: true
      });
    });

    test('should handle special characters in series parameter', async () => {
      const mockData = [{ series_id: "GDP'; DROP TABLE economic_data; --", date: '2024-01-01', value: 25000000000 }];
      const mockCount = [{ total: '1' }];

      mockQuery
        .mockResolvedValueOnce({ rows: mockData })
        .mockResolvedValueOnce({ rows: mockCount });

      const response = await request(app)
        .get('/economic?series=GDP\'; DROP TABLE economic_data; --');

      // Should still process safely due to parameterized queries
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('WHERE series_id = $1'),
        ["GDP'; DROP TABLE economic_data; --", 25, 0]
      );
    });

    test('should handle empty series parameter', async () => {
      const mockData = [{ series_id: '', date: '2024-01-01', value: 0 }];
      const mockCount = [{ total: '1' }];

      mockQuery
        .mockResolvedValueOnce({ rows: mockData })
        .mockResolvedValueOnce({ rows: mockCount });

      const response = await request(app)
        .get('/economic?series=');

      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('WHERE series_id = $1'),
        ['', 25, 0]
      );
    });

    test('should handle invalid limit in data endpoint', async () => {
      const mockData = [{ series_id: 'GDP', date: '2024-01-01', value: 25000000000 }];

      mockQuery.mockResolvedValue({ rows: mockData });

      const response = await request(app)
        .get('/economic/data?limit=invalid');

      expect(response.body.limit).toBe(50); // Falls back to default
      expect(mockQuery).toHaveBeenCalledWith(expect.any(String), [50]);
    });
  });

  describe('Response format validation', () => {
    test('should return consistent JSON response format', async () => {
      const mockData = [{ series_id: 'GDP', date: '2024-01-01', value: 25000000000 }];
      const mockCount = [{ total: '1' }];

      mockQuery
        .mockResolvedValueOnce({ rows: mockData })
        .mockResolvedValueOnce({ rows: mockCount });

      const response = await request(app)
        .get('/economic');

      expect(response.headers['content-type']).toMatch(/json/);
      expect(typeof response.body).toBe('object');
      expect(response.body).toHaveProperty('data');
      expect(response.body).toHaveProperty('pagination');
    });

    test('should maintain consistent error response format', async () => {
      mockQuery.mockRejectedValue(new Error('Test error'));

      const response = await request(app)
        .get('/economic');

      expect(response.body).toHaveProperty('success', false);
      expect(response.body).toHaveProperty('error');
      expect(response.body).toHaveProperty('message');
      expect(typeof response.body.error).toBe('string');
    });

    test('should return proper data structure', async () => {
      const mockData = [
        { series_id: 'GDP', date: '2024-01-01', value: 25000000000 },
        { series_id: 'CPI', date: '2024-01-01', value: 310.5 }
      ];

      mockQuery.mockResolvedValue({ rows: mockData });

      const response = await request(app)
        .get('/economic/data');

      expect(Array.isArray(response.body.data)).toBe(true);
      expect(response.body.data).toHaveLength(2);
      expect(response.body.data[0]).toHaveProperty('series_id');
      expect(response.body.data[0]).toHaveProperty('date');
      expect(response.body.data[0]).toHaveProperty('value');
    });
  });

  describe('Data integrity tests', () => {
    test('should preserve numeric values correctly', async () => {
      const mockData = [
        { series_id: 'GDP', date: '2024-01-01', value: 25000000000.50 },
        { series_id: 'CPI', date: '2024-01-01', value: 310.125 }
      ];

      mockQuery.mockResolvedValue({ rows: mockData });

      const response = await request(app)
        .get('/economic/data');

      expect(response.body.data[0].value).toBe(25000000000.50);
      expect(response.body.data[1].value).toBe(310.125);
    });

    test('should handle large datasets', async () => {
      const largeDataset = Array.from({ length: 100 }, (_, i) => ({
        series_id: `SERIES_${i}`,
        date: '2024-01-01',
        value: i * 1000
      }));

      mockQuery.mockResolvedValue({ rows: largeDataset });

      const response = await request(app)
        .get('/economic/data?limit=100');

      expect(response.status).toBe(200);
      expect(response.body.data).toHaveLength(100);
      expect(response.body.count).toBe(100);
    });

    test('should calculate pagination correctly', async () => {
      const mockData = [{ series_id: 'GDP', date: '2024-01-01', value: 25000000000 }];
      const mockCount = [{ total: '157' }]; // Prime number for testing

      mockQuery
        .mockResolvedValueOnce({ rows: mockData })
        .mockResolvedValueOnce({ rows: mockCount });

      const response = await request(app)
        .get('/economic?page=5&limit=20');

      expect(response.body.pagination).toMatchObject({
        page: 5,
        limit: 20,
        total: 157,
        totalPages: 8, // Math.ceil(157/20) = 8
        hasNext: true, // page 5 < totalPages 8
        hasPrev: true  // page 5 > 1
      });
    });
  });
});