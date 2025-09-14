/**
 * Comprehensive Unit Tests for Analysts Route
 * Tests all analyst endpoints with mocked database dependencies
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

// Add response helper middleware to match the actual implementation
app.use((req, res, next) => {
  res.error = (message, status, details) => res.status(status || 500).json({
    success: false,
    error: message,
    ...(details && details)
  });
  res.success = (data, status = 200) => res.status(status).json({
    success: true,
    ...data
  });
  next();
});

app.use('/api/analysts', require('../../../routes/analysts'));

describe('Analysts Route - Comprehensive Unit Tests', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('GET /api/analysts/', () => {
    test('should return API overview with all endpoints', async () => {
      const response = await request(app)
        .get('/api/analysts/')
        .expect(200);

      expect(response.body.message).toBe('Analysts API - Ready');
      expect(response.body.status).toBe('operational');
      expect(response.body.timestamp).toBeDefined();
      expect(Array.isArray(response.body.endpoints)).toBe(true);
      expect(response.body.endpoints.length).toBe(10);
      expect(response.body.endpoints).toContain('/upgrades - Get analyst upgrades/downgrades');
      expect(response.body.endpoints).toContain('/:ticker/overview - Get comprehensive analyst overview');
    });
  });

  describe('GET /api/analysts/upgrades', () => {
    test('should get paginated analyst upgrades with valid data', async () => {
      const mockUpgradesData = [
        {
          symbol: 'AAPL',
          company_name: 'Apple Inc.',
          upgrades_last_30d: 3,
          downgrades_last_30d: 1,
          date: '2024-01-15',
          action: 'Upgrade',
          firm: 'Analyst Consensus',
          details: 'Recent activity: 3 upgrades, 1 downgrades'
        }
      ];
      const mockCountData = [{ total: '25' }];

      mockQuery
        .mockResolvedValueOnce({ rows: mockUpgradesData })
        .mockResolvedValueOnce({ rows: mockCountData });

      const response = await request(app)
        .get('/api/analysts/upgrades')
        .expect(200);

      expect(response.body.data).toHaveLength(1);
      expect(response.body.data[0].symbol).toBe('AAPL');
      expect(response.body.data[0].company).toBe('Apple Inc.');
      expect(response.body.data[0].action).toBe('Upgrade');
      expect(response.body.pagination).toMatchObject({
        page: 1,
        limit: 25,
        total: 25,
        totalPages: 1,
        hasNext: false,
        hasPrev: false
      });
    });

    test('should handle pagination parameters correctly', async () => {
      const mockUpgradesData = [];
      const mockCountData = [{ total: '100' }];

      mockQuery
        .mockResolvedValueOnce({ rows: mockUpgradesData })
        .mockResolvedValueOnce({ rows: mockCountData });

      const response = await request(app)
        .get('/api/analysts/upgrades?page=3&limit=10')
        .expect(200);

      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('LIMIT $1 OFFSET $2'),
        [10, 20]
      );
      expect(response.body.pagination).toMatchObject({
        page: 3,
        limit: 10,
        total: 100,
        totalPages: 10,
        hasNext: true,
        hasPrev: true
      });
    });

    test('should handle database unavailability gracefully', async () => {
      mockQuery
        .mockResolvedValueOnce(null)
        .mockResolvedValueOnce({ rows: [{ total: '0' }] });

      const response = await request(app)
        .get('/api/analysts/upgrades')
        .expect(503);

      expect(response.body.message).toContain('database connection issue');
      expect(response.body.data).toEqual([]);
      expect(response.body.pagination.total).toBe(0);
    });

    test('should handle database errors', async () => {
      mockQuery.mockRejectedValue(new Error('Database connection failed'));

      const response = await request(app)
        .get('/api/analysts/upgrades')
        .expect(500);

      expect(response.body.success).toBe(false);
    });
  });

  describe('GET /api/analysts/:ticker/earnings-estimates', () => {
    test('should get earnings estimates for valid ticker', async () => {
      const mockEarningsData = [
        {
          period: 'Q4 2023',
          estimate: 1.25,
          actual: 1.30,
          difference: 0.05,
          surprise_percent: 4.0,
          reported_date: '2024-01-15'
        }
      ];

      mockQuery.mockResolvedValue({ rows: mockEarningsData });

      const response = await request(app)
        .get('/api/analysts/AAPL/earnings-estimates')
        .expect(200);

      expect(response.body.ticker).toBe('AAPL');
      expect(response.body.estimates).toHaveLength(1);
      expect(response.body.estimates[0].period).toBe('Q4 2023');
      expect(response.body.estimates[0].estimate).toBe(1.25);
      expect(response.body.estimates[0].actual).toBe(1.30);
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('FROM earnings_reports'),
        ['AAPL']
      );
    });

    test('should handle case insensitive ticker symbols', async () => {
      mockQuery.mockResolvedValue({ rows: [] });

      await request(app)
        .get('/api/analysts/aapl/earnings-estimates')
        .expect(200);

      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('UPPER($1)'),
        ['AAPL']
      );
    });

    test('should handle database errors for earnings estimates', async () => {
      mockQuery.mockRejectedValue(new Error('Database error'));

      const response = await request(app)
        .get('/api/analysts/AAPL/earnings-estimates')
        .expect(500);

      expect(response.body.success).toBe(false);
    });
  });

  describe('GET /api/analysts/:ticker/revenue-estimates', () => {
    test('should get revenue estimates for valid ticker', async () => {
      const mockRevenueData = [
        {
          period: 'Q4 2023',
          estimate: null,
          actual: 119300000000,
          difference: null,
          surprise_percent: null,
          reported_date: '2024-01-15'
        }
      ];

      mockQuery.mockResolvedValue({ rows: mockRevenueData });

      const response = await request(app)
        .get('/api/analysts/AAPL/revenue-estimates')
        .expect(200);

      expect(response.body.ticker).toBe('AAPL');
      expect(response.body.estimates).toHaveLength(1);
      expect(response.body.estimates[0].actual).toBe(119300000000);
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('er.revenue as actual'),
        ['AAPL']
      );
    });
  });

  describe('GET /api/analysts/:ticker/earnings-history', () => {
    test('should get earnings history for valid ticker', async () => {
      const mockHistoryData = [
        {
          quarter: 'Q4 2023',
          estimate: 1.25,
          actual: 1.30,
          difference: 0.05,
          surprise_percent: 4.0,
          earnings_date: '2024-01-15'
        },
        {
          quarter: 'Q3 2023',
          estimate: 1.15,
          actual: 1.20,
          difference: 0.05,
          surprise_percent: 4.35,
          earnings_date: '2023-10-15'
        }
      ];

      mockQuery.mockResolvedValue({ rows: mockHistoryData });

      const response = await request(app)
        .get('/api/analysts/AAPL/earnings-history')
        .expect(200);

      expect(response.body.ticker).toBe('AAPL');
      expect(response.body.history).toHaveLength(2);
      expect(response.body.history[0].quarter).toBe('Q4 2023');
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('LIMIT 12'),
        ['AAPL']
      );
    });
  });

  describe('GET /api/analysts/:ticker/eps-revisions', () => {
    test('should get EPS revisions for valid ticker', async () => {
      const mockRevisionsData = [
        {
          symbol: 'AAPL',
          period: '0q',
          up_last7days: 0,
          up_last30days: 3,
          down_last30days: 1,
          down_last7days: 0,
          fetched_at: '2024-01-15'
        }
      ];

      mockQuery.mockResolvedValue({ rows: mockRevisionsData });

      const response = await request(app)
        .get('/api/analysts/AAPL/eps-revisions')
        .expect(200);

      expect(response.body.ticker).toBe('AAPL');
      expect(response.body.data).toHaveLength(1);
      expect(response.body.data[0].up_last30days).toBe(3);
      expect(response.body.metadata.count).toBe(1);
      expect(response.body.metadata.timestamp).toBeDefined();
    });

    test('should handle database errors for EPS revisions', async () => {
      mockQuery.mockRejectedValue(new Error('Database connection failed'));

      const response = await request(app)
        .get('/api/analysts/AAPL/eps-revisions')
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('Failed to fetch EPS revisions');
      expect(response.body.message).toBeDefined();
    });
  });

  describe('GET /api/analysts/:ticker/eps-trend', () => {
    test('should get EPS trend for valid ticker', async () => {
      const mockTrendData = [
        {
          symbol: 'AAPL',
          period: '0q',
          current: 1.30,
          days7ago: null,
          days30ago: null,
          days60ago: null,
          days90ago: null,
          fetched_at: '2024-01-15'
        }
      ];

      mockQuery.mockResolvedValue({ rows: mockTrendData });

      const response = await request(app)
        .get('/api/analysts/AAPL/eps-trend')
        .expect(200);

      expect(response.body.ticker).toBe('AAPL');
      expect(response.body.data).toHaveLength(1);
      expect(response.body.data[0].current).toBe(1.30);
      expect(response.body.metadata.count).toBe(1);
    });
  });

  describe('GET /api/analysts/:ticker/growth-estimates', () => {
    test('should get growth estimates for valid ticker', async () => {
      const mockGrowthData = [
        {
          symbol: 'AAPL',
          period: '0q',
          stock_trend: 'N/A',
          index_trend: 'N/A',
          fetched_at: '2024-01-15'
        }
      ];

      mockQuery.mockResolvedValue({ rows: mockGrowthData });

      const response = await request(app)
        .get('/api/analysts/AAPL/growth-estimates')
        .expect(200);

      expect(response.body.ticker).toBe('AAPL');
      expect(response.body.data).toHaveLength(1);
      expect(response.body.metadata.note).toContain('Growth estimates not available');
    });
  });

  describe('GET /api/analysts/:ticker/overview', () => {
    test('should get comprehensive analyst overview', async () => {
      const mockEarningsData = [
        {
          period: 'Q4 2023',
          estimate: 1.25,
          actual: 1.30,
          difference: 0.05,
          surprise_percent: 4.0,
          reported_date: '2024-01-15'
        }
      ];

      const mockRevenueData = [
        {
          period: 'Q4 2023',
          estimate: null,
          actual: 119300000000,
          difference: null,
          surprise_percent: null,
          reported_date: '2024-01-15'
        }
      ];

      const mockAnalystData = [
        {
          period: 'current',
          strong_buy: 5,
          buy: 10,
          hold: 8,
          sell: 2,
          strong_sell: 0,
          collected_date: '2024-01-15',
          recommendation_mean: 2.2,
          total_analysts: 25,
          avg_price_target: 180.50,
          high_price_target: 200.00,
          low_price_target: 160.00,
          price_target_vs_current: 5.2,
          eps_revisions_up_last_30d: 3,
          eps_revisions_down_last_30d: 1
        }
      ];

      mockQuery
        .mockResolvedValueOnce({ rows: mockEarningsData })
        .mockResolvedValueOnce({ rows: mockRevenueData })
        .mockResolvedValueOnce({ rows: mockAnalystData });

      const response = await request(app)
        .get('/api/analysts/AAPL/overview')
        .expect(200);

      expect(response.body.ticker).toBe('AAPL');
      expect(response.body.data.earnings_estimates).toHaveLength(1);
      expect(response.body.data.revenue_estimates).toHaveLength(1);
      expect(response.body.data.earnings_history).toHaveLength(1);
      expect(response.body.data.eps_revisions).toHaveLength(1);
      expect(response.body.data.eps_trend).toHaveLength(1);
      expect(response.body.data.growth_estimates).toHaveLength(1);
      expect(response.body.data.recommendations).toHaveLength(1);
      expect(response.body.metadata.timestamp).toBeDefined();
    });

    test('should handle database errors for overview', async () => {
      mockQuery.mockRejectedValue(new Error('Database connection failed'));

      const response = await request(app)
        .get('/api/analysts/AAPL/overview')
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('Failed to fetch analyst overview');
      expect(response.body.message).toBeDefined();
    });
  });

  describe('GET /api/analysts/recent-actions', () => {
    test('should get recent analyst actions', async () => {
      const mockRecentDateData = [{ date: '2024-01-15' }];
      const mockActionsData = [
        {
          symbol: 'AAPL',
          company_name: 'Apple Inc.',
          from_grade: null,
          to_grade: null,
          action: 'Upgrade',
          firm: 'Analyst Consensus',
          date: '2024-01-15',
          details: 'Recent activity: 3 upgrades, 1 downgrades',
          action_type: 'upgrade'
        }
      ];

      mockQuery
        .mockResolvedValueOnce({ rows: mockRecentDateData })
        .mockResolvedValueOnce({ rows: mockActionsData });

      const response = await request(app)
        .get('/api/analysts/recent-actions')
        .expect(200);

      expect(response.body.data).toHaveLength(1);
      expect(response.body.data[0].action).toBe('Upgrade');
      expect(response.body.summary.date).toBe('2024-01-15');
      expect(response.body.summary.total_actions).toBe(1);
      expect(response.body.summary.upgrades).toBe(1);
      expect(response.body.summary.downgrades).toBe(0);
    });

    test('should handle no recent actions found', async () => {
      mockQuery.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get('/api/analysts/recent-actions')
        .expect(200);

      expect(response.body.data).toEqual([]);
      expect(response.body.message).toBe('No analyst actions found');
      expect(response.body.summary.total_actions).toBe(0);
    });

    test('should handle limit parameter', async () => {
      const mockRecentDateData = [{ date: '2024-01-15' }];
      const mockActionsData = [];

      mockQuery
        .mockResolvedValueOnce({ rows: mockRecentDateData })
        .mockResolvedValueOnce({ rows: mockActionsData });

      await request(app)
        .get('/api/analysts/recent-actions?limit=5')
        .expect(200);

      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('LIMIT $2'),
        ['2024-01-15', 5]
      );
    });
  });

  describe('GET /api/analysts/recommendations/:symbol', () => {
    test('should get analyst recommendations for valid symbol', async () => {
      const mockRecommendationsData = [
        {
          rating: 'BUY',
          price_target: 180.50,
          date_published: '2024-01-15',
          firm_name: 'Morgan Stanley',
          analyst_name: 'John Doe'
        },
        {
          rating: 'STRONG_BUY',
          price_target: 190.00,
          date_published: '2024-01-10',
          firm_name: 'Goldman Sachs',
          analyst_name: 'Jane Smith'
        }
      ];

      mockQuery.mockResolvedValue({ rows: mockRecommendationsData });

      const response = await request(app)
        .get('/api/analysts/recommendations/AAPL')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.symbol).toBe('AAPL');
      expect(response.body.data.total_analysts).toBe(2);
      expect(response.body.data.rating_distribution.buy).toBe(1);
      expect(response.body.data.rating_distribution.strong_buy).toBe(1);
      expect(response.body.data.consensus_rating).toBe('4.50');
      expect(response.body.data.average_price_target).toBe(185.25);
      expect(response.body.data.recent_changes).toHaveLength(0);
    });

    test('should handle no recommendations found', async () => {
      mockQuery.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get('/api/analysts/recommendations/INVALID')
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe('No analyst recommendations found');
      expect(response.body.symbol).toBe('INVALID');
    });

    test('should handle database errors for recommendations', async () => {
      mockQuery.mockRejectedValue(new Error('Database connection failed'));

      const response = await request(app)
        .get('/api/analysts/recommendations/AAPL')
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe('Failed to fetch analyst recommendations');
    });
  });

  describe('GET /api/analysts/targets/:symbol', () => {
    test('should get price targets (placeholder implementation)', async () => {
      const response = await request(app)
        .get('/api/analysts/targets/AAPL')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.symbol).toBe('AAPL');
      expect(response.body.data.price_targets).toBeDefined();
      expect(response.body.data.recent_targets).toBeDefined();
    });
  });

  describe('GET /api/analysts/downgrades', () => {
    test('should return analyst downgrades with default parameters', async () => {
      const response = await request(app)
        .get('/api/analysts/downgrades')
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          downgrades: expect.any(Array),
          analytics: expect.objectContaining({
            total_downgrades: expect.any(Number),
            timeframe_analyzed: '30d',
            severity_distribution: expect.any(Object),
            top_firms: expect.any(Array),
            average_price_impact: expect.any(Number),
            most_downgraded_symbols: expect.any(Array),
            market_cap_impact_total: expect.any(Number)
          }),
          summary: expect.objectContaining({
            total_downgrades: expect.any(Number),
            average_severity: expect.any(String),
            market_sentiment: expect.any(String),
            total_market_impact: expect.any(String)
          })
        }),
        filters: expect.objectContaining({
          limit: 50,
          timeframe: '30d',
          symbol: 'all',
          analyst_firm: 'all',
          severity: 'all',
          min_price_impact: 0
        }),
        methodology: expect.any(Object)
      });

      // Verify downgrades structure
      if (response.body.data.downgrades.length > 0) {
        const downgrade = response.body.data.downgrades[0];
        expect(downgrade).toMatchObject({
          id: expect.any(String),
          symbol: expect.any(String),
          company_name: expect.any(String),
          analyst_firm: expect.any(String),
          analyst_name: expect.any(String),
          downgrade_date: expect.any(String),
          previous_rating: expect.any(String),
          new_rating: expect.any(String),
          rating_change: expect.any(String),
          severity: expect.stringMatching(/^(mild|moderate|severe)$/),
          reason: expect.any(String),
          detailed_rationale: expect.any(String),
          price_targets: expect.objectContaining({
            previous_target: expect.any(Number),
            new_target: expect.any(Number),
            target_change: expect.any(Number),
            target_change_percent: expect.any(Number)
          }),
          market_impact: expect.objectContaining({
            expected_price_impact_percent: expect.any(Number),
            actual_price_impact_percent: expect.any(Number),
            volume_impact: expect.any(Number),
            market_cap_impact_millions: expect.any(Number)
          }),
          timing: expect.objectContaining({
            hours_since_downgrade: expect.any(Number),
            market_hours: expect.any(Boolean),
            earnings_related: expect.any(Boolean),
            days_until_earnings: expect.any(Number)
          }),
          confidence_metrics: expect.objectContaining({
            analyst_accuracy_12m: expect.any(Number),
            firm_reputation_score: expect.any(Number),
            consensus_alignment: expect.stringMatching(/^(Aligned|Contrarian)$/)
          })
        });
      }
    });

    test('should support filtering by symbol', async () => {
      const response = await request(app)
        .get('/api/analysts/downgrades?symbol=AAPL&limit=10')
        .expect(200);

      expect(response.body.filters).toMatchObject({
        symbol: 'AAPL',
        limit: 10
      });

      // All downgrades should be for AAPL if any are returned
      if (response.body.data.downgrades.length > 0) {
        response.body.data.downgrades.forEach(downgrade => {
          expect(downgrade.symbol).toBe('AAPL');
        });
      }
    });

    test('should support filtering by analyst firm', async () => {
      const response = await request(app)
        .get('/api/analysts/downgrades?analyst_firm=Goldman Sachs&timeframe=7d')
        .expect(200);

      expect(response.body.filters).toMatchObject({
        analyst_firm: 'Goldman Sachs',
        timeframe: '7d'
      });

      // All downgrades should be from Goldman Sachs if any are returned
      if (response.body.data.downgrades.length > 0) {
        response.body.data.downgrades.forEach(downgrade => {
          expect(downgrade.analyst_firm).toBe('Goldman Sachs');
        });
      }
    });

    test('should support filtering by severity', async () => {
      const response = await request(app)
        .get('/api/analysts/downgrades?severity=severe&limit=20')
        .expect(200);

      expect(response.body.filters).toMatchObject({
        severity: 'severe',
        limit: 20
      });

      // All downgrades should have severe severity if any are returned
      if (response.body.data.downgrades.length > 0) {
        response.body.data.downgrades.forEach(downgrade => {
          expect(downgrade.severity).toBe('severe');
        });
      }
    });

    test('should support minimum price impact filtering', async () => {
      const response = await request(app)
        .get('/api/analysts/downgrades?min_price_impact=0.05')
        .expect(200);

      expect(response.body.filters).toMatchObject({
        min_price_impact: 0.05
      });

      // All downgrades should meet minimum price impact if any are returned
      if (response.body.data.downgrades.length > 0) {
        response.body.data.downgrades.forEach(downgrade => {
          expect(Math.abs(downgrade.market_impact.actual_price_impact_percent)).toBeGreaterThanOrEqual(5);
        });
      }
    });

    test('should support different timeframe options', async () => {
      const timeframes = ['7d', '30d', '90d'];
      
      for (const timeframe of timeframes) {
        const response = await request(app)
          .get(`/api/analysts/downgrades?timeframe=${timeframe}&limit=5`)
          .expect(200);

        expect(response.body.filters.timeframe).toBe(timeframe);
        expect(response.body.data.analytics.timeframe_analyzed).toBe(timeframe);
      }
    });

    test('should handle errors gracefully', async () => {
      // Test with invalid parameters that might cause issues
      const response = await request(app)
        .get('/api/analysts/downgrades?limit=invalid')
        .expect(200); // Our implementation handles invalid limit gracefully

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
    });
  });

  describe('GET /api/analysts/consensus/:symbol', () => {
    test('should get consensus analysis (placeholder implementation)', async () => {
      const response = await request(app)
        .get('/api/analysts/consensus/AAPL')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.symbol).toBe('AAPL');
      expect(response.body.data.consensus_metrics).toBeDefined();
      expect(response.body.data.estimate_revisions).toBeDefined();
    });
  });

  // Edge Cases and Error Scenarios
  describe('Edge Cases and Error Handling', () => {
    test('should handle invalid ticker symbols gracefully', async () => {
      mockQuery.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get('/api/analysts/INVALID123/earnings-estimates')
        .expect(200);

      expect(response.body.ticker).toBe('INVALID123');
      expect(response.body.estimates).toHaveLength(0);
    });

    test('should handle special characters in ticker symbols', async () => {
      mockQuery.mockResolvedValue({ rows: [] });

      await request(app)
        .get('/api/analysts/BRK.B/earnings-estimates')
        .expect(200);

      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('UPPER($1)'),
        ['BRK.B']
      );
    });

    test('should handle very large page numbers', async () => {
      const mockUpgradesData = [];
      const mockCountData = [{ total: '10' }];

      mockQuery
        .mockResolvedValueOnce({ rows: mockUpgradesData })
        .mockResolvedValueOnce({ rows: mockCountData });

      const response = await request(app)
        .get('/api/analysts/upgrades?page=999999&limit=25')
        .expect(200);

      expect(response.body.pagination.page).toBe(999999);
      expect(response.body.pagination.hasNext).toBe(false);
      expect(response.body.pagination.hasPrev).toBe(true);
    });

    test('should handle zero or negative page numbers', async () => {
      const mockUpgradesData = [];
      const mockCountData = [{ total: '10' }];

      mockQuery
        .mockResolvedValueOnce({ rows: mockUpgradesData })
        .mockResolvedValueOnce({ rows: mockCountData });

      const response = await request(app)
        .get('/api/analysts/upgrades?page=0&limit=25')
        .expect(200);

      expect(response.body.pagination.page).toBe(1);
    });

    test('should handle null database results gracefully', async () => {
      mockQuery.mockResolvedValue({ rows: [{ malformed: 'data' }] });

      const response = await request(app)
        .get('/api/analysts/AAPL/earnings-estimates')
        .expect(200);

      expect(response.body.ticker).toBe('AAPL');
      expect(Array.isArray(response.body.estimates)).toBe(true);
    });
  });

  // Performance and Load Testing
  describe('Performance Testing', () => {
    test('should handle multiple concurrent requests', async () => {
      mockQuery.mockResolvedValue({ rows: [] });

      const requests = Array.from({ length: 10 }, (_, i) => 
        request(app).get(`/api/analysts/AAPL${i}/earnings-estimates`)
      );

      const responses = await Promise.all(requests);
      
      responses.forEach((response, index) => {
        expect(response.status).toBe(200);
        expect(response.body.ticker).toBe(`AAPL${index}`);
      });
    });

    test('should handle large dataset responses efficiently', async () => {
      const largeDataset = Array.from({ length: 1000 }, (_, i) => ({
        period: `Q${i % 4 + 1} ${2020 + Math.floor(i / 4)}`,
        estimate: 1.25 + (i * 0.01),
        actual: 1.30 + (i * 0.01),
        difference: 0.05,
        surprise_percent: 4.0 + (i * 0.1),
        reported_date: '2024-01-15'
      }));

      mockQuery.mockResolvedValue({ rows: largeDataset });

      const startTime = Date.now();
      const response = await request(app)
        .get('/api/analysts/AAPL/earnings-estimates')
        .expect(200);
      const endTime = Date.now();

      expect(response.body.estimates).toHaveLength(1000);
      expect(endTime - startTime).toBeLessThan(5000); // Should complete within 5 seconds
    });
  });

  // Response Format Validation
  describe('Response Format Validation', () => {
    test('should return consistent JSON response format', async () => {
      const response = await request(app)
        .get('/api/analysts/')
        .expect(200);

      expect(response.headers['content-type']).toMatch(/json/);
      expect(typeof response.body).toBe('object');
      expect(response.body.timestamp).toBeDefined();
    });

    test('should include timestamp in ISO format', async () => {
      const response = await request(app)
        .get('/api/analysts/')
        .expect(200);

      expect(response.body.timestamp).toBeDefined();
      expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
      expect(response.body.timestamp).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/);
    });

    test('should maintain consistent error response format', async () => {
      mockQuery.mockRejectedValue(new Error('Test error'));

      const response = await request(app)
        .get('/api/analysts/upgrades')
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBeDefined();
      expect(typeof response.body.error).toBe('string');
    });
  });
});