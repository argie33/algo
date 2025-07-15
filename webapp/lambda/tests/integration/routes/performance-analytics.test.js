/**
 * Integration tests for Performance Analytics API Routes
 * Test-driven development approach - testing as we build
 */

const request = require('supertest');
const app = require('../../../index');

describe('Performance Analytics API Routes', () => {
  let authToken;
  
  beforeAll(async () => {
    // Mock authentication for testing
    authToken = 'mock-jwt-token';
  });

  describe('GET /api/performance-analytics/health', () => {
    test('returns health status', async () => {
      const response = await request(app)
        .get('/api/performance-analytics/health')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.status).toBe('healthy');
      expect(response.body.data.service).toBe('performance-analytics');
      expect(response.body.data.capabilities).toContain('portfolio-analysis');
    });
  });

  describe('GET /api/performance-analytics/portfolio', () => {
    test('requires authentication', async () => {
      const response = await request(app)
        .get('/api/performance-analytics/portfolio')
        .query({
          startDate: '2024-01-01',
          endDate: '2024-12-31'
        })
        .expect(401);

      expect(response.body.error).toContain('authentication');
    });

    test('validates date parameters', async () => {
      const response = await request(app)
        .get('/api/performance-analytics/portfolio')
        .set('Authorization', `Bearer ${authToken}`)
        .query({
          startDate: 'invalid-date',
          endDate: '2024-12-31'
        })
        .expect(400);

      expect(response.body.error).toContain('validation');
    });

    test('returns portfolio performance metrics', async () => {
      const response = await request(app)
        .get('/api/performance-analytics/portfolio')
        .set('Authorization', `Bearer ${authToken}`)
        .query({
          startDate: '2024-01-01',
          endDate: '2024-12-31',
          format: 'detailed'
        })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty('baseMetrics');
      expect(response.body.data).toHaveProperty('riskMetrics');
      expect(response.body.data).toHaveProperty('attributionAnalysis');
    });

    test('returns basic format when requested', async () => {
      const response = await request(app)
        .get('/api/performance-analytics/portfolio')
        .set('Authorization', `Bearer ${authToken}`)
        .query({
          startDate: '2024-01-01',
          endDate: '2024-12-31',
          format: 'basic'
        })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty('totalReturn');
      expect(response.body.data).toHaveProperty('volatility');
      expect(response.body.data).toHaveProperty('maxDrawdown');
    });
  });

  describe('GET /api/performance-analytics/report', () => {
    test('generates performance report', async () => {
      const response = await request(app)
        .get('/api/performance-analytics/report')
        .set('Authorization', `Bearer ${authToken}`)
        .query({
          startDate: '2024-01-01',
          endDate: '2024-12-31',
          reportType: 'detailed'
        })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty('reportId');
      expect(response.body.data).toHaveProperty('summary');
      expect(response.body.data).toHaveProperty('metrics');
      expect(response.body.data).toHaveProperty('recommendations');
    });
  });

  describe('GET /api/performance-analytics/attribution', () => {
    test('returns attribution analysis', async () => {
      const response = await request(app)
        .get('/api/performance-analytics/attribution')
        .set('Authorization', `Bearer ${authToken}`)
        .query({
          startDate: '2024-01-01',
          endDate: '2024-12-31'
        })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty('securityAttribution');
      expect(response.body.data).toHaveProperty('sectorAttribution');
      expect(response.body.data).toHaveProperty('totalPortfolioValue');
    });
  });

  describe('GET /api/performance-analytics/risk-metrics', () => {
    test('returns comprehensive risk metrics', async () => {
      const response = await request(app)
        .get('/api/performance-analytics/risk-metrics')
        .set('Authorization', `Bearer ${authToken}`)
        .query({
          startDate: '2024-01-01',
          endDate: '2024-12-31'
        })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty('riskMetrics');
      expect(response.body.data).toHaveProperty('factorExposure');
      expect(response.body.data).toHaveProperty('riskAssessment');
      expect(response.body.data.riskMetrics).toHaveProperty('volatility');
      expect(response.body.data.riskMetrics).toHaveProperty('maxDrawdown');
      expect(response.body.data.riskMetrics).toHaveProperty('valueAtRisk');
    });
  });

  describe('GET /api/performance-analytics/sector-analysis', () => {
    test('returns sector analysis', async () => {
      const response = await request(app)
        .get('/api/performance-analytics/sector-analysis')
        .set('Authorization', `Bearer ${authToken}`)
        .query({
          startDate: '2024-01-01',
          endDate: '2024-12-31'
        })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty('sectorBreakdown');
      expect(response.body.data).toHaveProperty('diversificationScore');
      expect(response.body.data).toHaveProperty('sectorCount');
    });
  });

  describe('GET /api/performance-analytics/factor-exposure', () => {
    test('returns factor exposure analysis', async () => {
      const response = await request(app)
        .get('/api/performance-analytics/factor-exposure')
        .set('Authorization', `Bearer ${authToken}`)
        .query({
          startDate: '2024-01-01',
          endDate: '2024-12-31'
        })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty('factorExposures');
      expect(response.body.data).toHaveProperty('riskFactors');
      expect(response.body.data).toHaveProperty('styleFactors');
    });
  });

  describe('Error Handling', () => {
    test('handles invalid date ranges', async () => {
      const response = await request(app)
        .get('/api/performance-analytics/portfolio')
        .set('Authorization', `Bearer ${authToken}`)
        .query({
          startDate: '2024-12-31',
          endDate: '2024-01-01' // End date before start date
        })
        .expect(400);

      expect(response.body.error).toContain('invalid date range');
    });

    test('handles missing required parameters', async () => {
      const response = await request(app)
        .get('/api/performance-analytics/portfolio')
        .set('Authorization', `Bearer ${authToken}`)
        .expect(400);

      expect(response.body.error).toContain('required');
    });
  });
});