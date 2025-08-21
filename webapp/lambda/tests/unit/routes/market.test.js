const request = require('supertest');
const express = require('express');
const marketRouter = require('../../../routes/market');

// Mock dependencies
jest.mock('../../../utils/database');
const { query } = require('../../../utils/database');

describe('Market Routes', () => {
  let app;

  beforeEach(() => {
    app = express();
    app.use(express.json());
    app.use('/market', marketRouter);
    jest.clearAllMocks();
  });

  describe('GET /market/', () => {
    test('should return available routes and status', async () => {
      const response = await request(app)
        .get('/market/')
        .expect(200);

      expect(response.body).toEqual({
        status: 'ok',
        endpoint: 'market',
        available_routes: [
          '/overview',
          '/sentiment/history',
          '/sectors/performance',
          '/breadth',
          '/economic',
          '/naaim',
          '/fear-greed',
          '/indices',
          '/sectors',
          '/volatility',
          '/calendar',
          '/indicators',
          '/sentiment'
        ],
        timestamp: expect.any(String)
      });

      // Validate timestamp format
      expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
    });

    test('should be a public endpoint', async () => {
      // Should work without authentication
      await request(app)
        .get('/market/')
        .expect(200);
    });
  });

  describe('GET /market/debug', () => {
    const mockTablesExist = {
      rows: [{ exists: true }]
    };

    const mockTablesNotExist = {
      rows: [{ exists: false }]
    };

    test('should return debug information when all tables exist', async () => {
      query.mockResolvedValue(mockTablesExist);

      const response = await request(app)
        .get('/market/debug')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.tables).toBeDefined();

      // Check that expected market tables are checked
      const expectedTables = [
        'market_data',
        'economic_data'
      ];

      expectedTables.forEach(tableName => {
        expect(response.body.tables[tableName]).toBe(true);
      });
    });

    test('should handle missing tables gracefully', async () => {
      query.mockResolvedValue(mockTablesNotExist);

      const response = await request(app)
        .get('/market/debug')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.tables).toBeDefined();
    });

    test('should handle database errors', async () => {
      query.mockRejectedValue(new Error('Database connection failed'));

      const response = await request(app)
        .get('/market/debug')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.tables).toBeDefined();
    });
  });

  describe('GET /market/overview', () => {
    const mockOverviewData = {
      rows: [{
        sp500_price: 4500.25,
        sp500_change: 1.25,
        sp500_change_pct: 0.028,
        nasdaq_price: 15200.50,
        nasdaq_change: -15.30,
        nasdaq_change_pct: -0.001,
        dow_price: 35000.75,
        dow_change: 50.25,
        dow_change_pct: 0.0014,
        vix: 18.50,
        volume_nyse: 3500000000,
        volume_nasdaq: 4200000000,
        advancing: 1850,
        declining: 1425,
        unchanged: 225,
        new_highs: 125,
        new_lows: 45,
        updated_at: '2023-01-01T15:30:00Z'
      }]
    };

    test('should return market overview data', async () => {
      query.mockResolvedValue(mockOverviewData);

      const response = await request(app)
        .get('/market/overview')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toEqual(mockOverviewData.rows[0]);
      expect(response.body.data.sp500_price).toBe(4500.25);
      expect(response.body.data.vix).toBe(18.50);
    });

    test('should handle empty overview data', async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get('/market/overview')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBe(null);
    });

    test('should handle database errors', async () => {
      query.mockRejectedValue(new Error('Database query failed'));

      const response = await request(app)
        .get('/market/overview')
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('Database query failed');
    });
  });

  describe('GET /market/indices', () => {
    const mockIndicesData = {
      rows: [
        {
          symbol: 'SPY',
          name: 'SPDR S&P 500 ETF',
          price: 450.25,
          change: 2.50,
          change_pct: 0.56,
          volume: 75000000,
          updated_at: '2023-01-01T20:00:00Z'
        },
        {
          symbol: 'QQQ',
          name: 'Invesco QQQ Trust',
          price: 380.75,
          change: -1.25,
          change_pct: -0.33,
          volume: 42000000,
          updated_at: '2023-01-01T20:00:00Z'
        }
      ]
    };

    test('should return market indices data', async () => {
      query.mockResolvedValue(mockIndicesData);

      const response = await request(app)
        .get('/market/indices')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveLength(2);
      expect(response.body.data[0].symbol).toBe('SPY');
      expect(response.body.data[1].symbol).toBe('QQQ');
    });

    test('should filter indices by symbol', async () => {
      query.mockResolvedValue({
        rows: [mockIndicesData.rows[0]] // Only SPY
      });

      const response = await request(app)
        .get('/market/indices?symbol=SPY')
        .expect(200);

      expect(response.body.data).toHaveLength(1);
      expect(response.body.data[0].symbol).toBe('SPY');
    });

    test('should handle empty indices data', async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get('/market/indices')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toEqual([]);
    });
  });

  describe('GET /market/sectors', () => {
    const mockSectorsData = {
      rows: [
        {
          sector: 'Technology',
          performance_1d: 1.25,
          performance_1w: 3.75,
          performance_1m: 8.50,
          performance_3m: 15.25,
          performance_ytd: 22.75,
          market_cap: 12500000000000,
          pe_ratio: 25.50,
          updated_at: '2023-01-01T20:00:00Z'
        },
        {
          sector: 'Healthcare',
          performance_1d: -0.50,
          performance_1w: 1.25,
          performance_1m: 2.75,
          performance_3m: 5.50,
          performance_ytd: 8.25,
          market_cap: 8200000000000,
          pe_ratio: 18.75,
          updated_at: '2023-01-01T20:00:00Z'
        }
      ]
    };

    test('should return sector performance data', async () => {
      query.mockResolvedValue(mockSectorsData);

      const response = await request(app)
        .get('/market/sectors')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveLength(2);
      expect(response.body.data[0].sector).toBe('Technology');
      expect(response.body.data[0].performance_ytd).toBe(22.75);
    });

    test('should sort sectors by performance', async () => {
      query.mockResolvedValue(mockSectorsData);

      const response = await request(app)
        .get('/market/sectors?sort_by=performance_1d')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining('ORDER BY performance_1d DESC'),
        []
      );
    });

    test('should handle invalid sort parameter', async () => {
      query.mockResolvedValue(mockSectorsData);

      const response = await request(app)
        .get('/market/sectors?sort_by=invalid_field')
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('Invalid sort field');
    });
  });

  describe('GET /market/sentiment', () => {
    const mockSentimentData = {
      rows: [{
        sentiment_score: 0.65,
        fear_greed_index: 58,
        vix_level: 18.25,
        put_call_ratio: 0.85,
        margin_debt: 750000000000,
        insider_buying: 0.15,
        insider_selling: 0.35,
        analyst_sentiment: 'BULLISH',
        retail_sentiment: 'NEUTRAL',
        institutional_flows: 2500000000,
        updated_at: '2023-01-01T20:00:00Z'
      }]
    };

    test('should return market sentiment data', async () => {
      query.mockResolvedValue(mockSentimentData);

      const response = await request(app)
        .get('/market/sentiment')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toEqual(mockSentimentData.rows[0]);
      expect(response.body.data.fear_greed_index).toBe(58);
      expect(response.body.data.analyst_sentiment).toBe('BULLISH');
    });

    test('should handle missing sentiment data', async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get('/market/sentiment')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBe(null);
    });
  });

  describe('GET /market/economic', () => {
    const mockEconomicData = {
      rows: [
        {
          indicator: 'GDP',
          value: 21500000000000,
          previous_value: 21200000000000,
          change_pct: 1.42,
          period: '2023-Q4',
          release_date: '2024-01-30',
          next_release: '2024-04-30'
        },
        {
          indicator: 'UNEMPLOYMENT_RATE',
          value: 3.5,
          previous_value: 3.7,
          change_pct: -5.41,
          period: '2023-12',
          release_date: '2024-01-05',
          next_release: '2024-02-02'
        }
      ]
    };

    test('should return economic indicators', async () => {
      query.mockResolvedValue(mockEconomicData);

      const response = await request(app)
        .get('/market/economic')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveLength(2);
      expect(response.body.data[0].indicator).toBe('GDP');
      expect(response.body.data[1].indicator).toBe('UNEMPLOYMENT_RATE');
    });

    test('should filter by specific indicator', async () => {
      query.mockResolvedValue({
        rows: [mockEconomicData.rows[0]]
      });

      const response = await request(app)
        .get('/market/economic?indicator=GDP')
        .expect(200);

      expect(response.body.data).toHaveLength(1);
      expect(response.body.data[0].indicator).toBe('GDP');
    });
  });

  describe('GET /market/volatility', () => {
    const mockVolatilityData = {
      rows: [{
        vix: 18.25,
        vvix: 95.50,
        term_structure_1m: 17.50,
        term_structure_2m: 19.25,
        term_structure_3m: 20.75,
        term_structure_6m: 22.50,
        skew_spy: 115.25,
        skew_qqq: 108.75,
        gex_gamma: -2500000000,
        dex_delta: 0.35,
        updated_at: '2023-01-01T20:00:00Z'
      }]
    };

    test('should return volatility data', async () => {
      query.mockResolvedValue(mockVolatilityData);

      const response = await request(app)
        .get('/market/volatility')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toEqual(mockVolatilityData.rows[0]);
      expect(response.body.data.vix).toBe(18.25);
      expect(response.body.data.gex_gamma).toBe(-2500000000);
    });
  });

  describe('Parameter validation', () => {
    test('should validate date parameters', async () => {
      const response = await request(app)
        .get('/market/overview?date=invalid-date')
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('Invalid date format');
    });

    test('should validate limit parameter', async () => {
      const response = await request(app)
        .get('/market/indices?limit=invalid')
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('Limit must be a positive number');
    });

    test('should enforce maximum limit', async () => {
      const response = await request(app)
        .get('/market/indices?limit=1000')
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('Limit cannot exceed 500');
    });
  });

  describe('Error handling', () => {
    test('should handle SQL injection attempts', async () => {
      const maliciousSymbol = "'; DROP TABLE market_data; --";
      
      // Mock the query to simulate protection
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get(`/market/indices?symbol=${encodeURIComponent(maliciousSymbol)}`)
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('Invalid symbol format');
    });

    test('should handle database timeouts', async () => {
      const timeoutError = new Error('Query timeout');
      timeoutError.code = 'QUERY_TIMEOUT';
      query.mockRejectedValue(timeoutError);

      const response = await request(app)
        .get('/market/overview')
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('Query timeout');
    });

    test('should handle missing route gracefully', async () => {
      const response = await request(app)
        .get('/market/nonexistent')
        .expect(404);

      expect(response.text).toContain('Cannot GET /market/nonexistent');
    });
  });
});