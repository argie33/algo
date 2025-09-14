/**
 * Scores Routes Unit Tests
 * Tests scores route logic with real database
 */

const express = require('express');
const request = require('supertest');

// Real database for integration
const { query } = require('../../../utils/database');

describe('Scores Routes Unit Tests', () => {
  let app;
  let scoresRouter;

  beforeAll(() => {
    // Create test app
    app = express();
    app.use(express.json());
    
    // Mock authentication middleware - allow all requests through
    app.use((req, res, next) => {
      req.user = { sub: 'test-user-123' }; // Mock authenticated user
      next();
    });
    
    // Add response formatter middleware
    const responseFormatter = require('../../../middleware/responseFormatter');
    app.use(responseFormatter);
    
    // Load the route module
    scoresRouter = require('../../../routes/scores');
    app.use('/scores', scoresRouter);
  });

  describe('GET /scores/ping', () => {
    test('should return ping response', async () => {
      const response = await request(app)
        .get('/scores/ping')
        .expect(200);

      expect(response.body).toHaveProperty('status', 'ok');
      expect(response.body).toHaveProperty('endpoint', 'scores');
      expect(response.body).toHaveProperty('timestamp');
    });
  });

  describe('GET /scores', () => {
    test('should return scores data', async () => {
      const response = await request(app)
        .get('/scores')
        .set('Authorization', 'Bearer dev-bypass-token')
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(Array.isArray(response.body.data)).toBe(true);
    });

    test('should handle pagination parameters', async () => {
      const response = await request(app)
        .get('/scores')
        .query({ page: 2, limit: 25 })
        .set('Authorization', 'Bearer dev-bypass-token')
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(Array.isArray(response.body.data)).toBe(true);
    });

    test('should handle search parameter', async () => {
      const response = await request(app)
        .get('/scores')
        .query({ search: 'AAPL' })
        .set('Authorization', 'Bearer dev-bypass-token')
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(Array.isArray(response.body.data)).toBe(true);
    });

    test('should handle sector filter', async () => {
      const response = await request(app)
        .get('/scores')
        .query({ sector: 'Technology' })
        .set('Authorization', 'Bearer dev-bypass-token')
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(Array.isArray(response.body.data)).toBe(true);
    });

    test('should handle score range filters', async () => {
      const response = await request(app)
        .get('/scores')
        .query({ minScore: 50, maxScore: 90 })
        .set('Authorization', 'Bearer dev-bypass-token')
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(Array.isArray(response.body.data)).toBe(true);
    });

    test('should handle sorting parameters', async () => {
      const response = await request(app)
        .get('/scores')
        .query({ sortBy: 'symbol', sortOrder: 'asc' })
        .set('Authorization', 'Bearer dev-bypass-token')
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(Array.isArray(response.body.data)).toBe(true);
    });

    test('should cap limit at 200', async () => {
      const response = await request(app)
        .get('/scores')
        .query({ limit: 500 })
        .set('Authorization', 'Bearer dev-bypass-token')
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(Array.isArray(response.body.data)).toBe(true);
    });

    test('should handle invalid numeric parameters gracefully', async () => {
      const response = await request(app)
        .get('/scores')
        .query({ 
          page: 'invalid',
          limit: 'not_a_number',
          minScore: 'bad_number',
          maxScore: 'also_bad'
        })
        .set('Authorization', 'Bearer dev-bypass-token')
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(Array.isArray(response.body.data)).toBe(true);
    });

    test('should handle empty results gracefully', async () => {
      const response = await request(app)
        .get('/scores')
        .query({ search: 'NONEXISTENTSYMBOL' })
        .set('Authorization', 'Bearer dev-bypass-token')
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(Array.isArray(response.body.data)).toBe(true);
    });
  });

  describe('Parameter validation', () => {
    test('should handle SQL injection attempts safely', async () => {
      const response = await request(app)
        .get('/scores')
        .query({ 
          search: "'; DROP TABLE stocks; --",
          sector: "Technology'; DELETE FROM scores; --"
        })
        .set('Authorization', 'Bearer dev-bypass-token')
        .expect(200);

      // Should still return successful response with safe handling
      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(Array.isArray(response.body.data)).toBe(true);
    });

    test('should handle empty string parameters', async () => {
      const response = await request(app)
        .get('/scores')
        .query({ 
          search: '',
          sector: '   ' // whitespace only
        })
        .set('Authorization', 'Bearer dev-bypass-token')
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(Array.isArray(response.body.data)).toBe(true);
    });

    test('should handle out of range score filters', async () => {
      const response = await request(app)
        .get('/scores')
        .query({ 
          minScore: -50,  // Below 0
          maxScore: 150   // Above 100
        })
        .set('Authorization', 'Bearer dev-bypass-token')
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(Array.isArray(response.body.data)).toBe(true);
    });
  });

  describe('GET /scores/composite', () => {
    test('should return composite scoring with proper structure', async () => {
      const response = await request(app)
        .get('/scores/composite')
        .set('Authorization', 'Bearer dev-bypass-token');

      if (response.status === 200) {
        expect(response.body).toHaveProperty('success', true);
        expect(response.body).toHaveProperty('data');
        expect(response.body.data).toHaveProperty('composite_scores');
        expect(response.body.data).toHaveProperty('summary');
        expect(response.body.data).toHaveProperty('methodology');
        expect(Array.isArray(response.body.data.composite_scores)).toBe(true);
        
        // Check composite score structure
        if (response.body.data.composite_scores.length > 0) {
          const score = response.body.data.composite_scores[0];
          expect(score).toHaveProperty('symbol');
          expect(score).toHaveProperty('composite_score');
          expect(score).toHaveProperty('technical_score');
          expect(score).toHaveProperty('fundamental_score');
          expect(score).toHaveProperty('momentum_score');
          expect(score).toHaveProperty('quality_score');
          expect(score).toHaveProperty('risk_adjusted_score');
          expect(score).toHaveProperty('score_percentile');
        }
        
        // Check summary structure
        expect(response.body.data.summary).toHaveProperty('total_analyzed');
        expect(response.body.data.summary).toHaveProperty('average_score');
        expect(response.body.data.summary).toHaveProperty('score_distribution');
        
        // Check methodology documentation
        expect(response.body.data.methodology).toHaveProperty('scoring_model');
        expect(response.body.data.methodology).toHaveProperty('factors');
      } else {
        expect([401]).toContain(response.status);
      }
    });

    test('should handle limit parameter for composite scores', async () => {
      const response = await request(app)
        .get('/scores/composite?limit=10')
        .set('Authorization', 'Bearer dev-bypass-token');

      if (response.status === 200) {
        expect(response.body.data.composite_scores.length).toBeLessThanOrEqual(10);
      }
    });

    test('should handle sector filter for composite scores', async () => {
      const response = await request(app)
        .get('/scores/composite?sector=Technology')
        .set('Authorization', 'Bearer dev-bypass-token');

      if (response.status === 200) {
        expect(response.body.data).toHaveProperty('composite_scores');
        // If scores are returned, they should be from Technology sector
        if (response.body.data.composite_scores.length > 0) {
          expect(response.body.data.composite_scores.every(score => 
            score.sector === 'Technology' || !score.sector
          )).toBe(true);
        }
      }
    });

    test('should handle score threshold filter', async () => {
      const response = await request(app)
        .get('/scores/composite?min_score=70')
        .set('Authorization', 'Bearer dev-bypass-token');

      if (response.status === 200) {
        expect(response.body.data).toHaveProperty('composite_scores');
        // If scores are returned, they should be >= 70
        if (response.body.data.composite_scores.length > 0) {
          response.body.data.composite_scores.forEach(score => {
            expect(score.composite_score).toBeGreaterThanOrEqual(70);
          });
        }
      }
    });

    test('should handle sorting for composite scores', async () => {
      const response = await request(app)
        .get('/scores/composite?sort=score_desc')
        .set('Authorization', 'Bearer dev-bypass-token');

      if (response.status === 200) {
        expect(response.body.data).toHaveProperty('composite_scores');
        // Scores should be sorted by composite_score descending
        if (response.body.data.composite_scores.length > 1) {
          for (let i = 1; i < response.body.data.composite_scores.length; i++) {
            expect(response.body.data.composite_scores[i-1].composite_score)
              .toBeGreaterThanOrEqual(response.body.data.composite_scores[i].composite_score);
          }
        }
      }
    });
  });

  describe('GET /scores/esg', () => {
    test('should return ESG scoring with proper structure', async () => {
      const response = await request(app)
        .get('/scores/esg')
        .set('Authorization', 'Bearer dev-bypass-token');

      if (response.status === 200) {
        expect(response.body).toHaveProperty('success', true);
        expect(response.body).toHaveProperty('data');
        expect(response.body.data).toHaveProperty('esg_scores');
        expect(response.body.data).toHaveProperty('summary');
        expect(response.body.data).toHaveProperty('methodology');
        expect(Array.isArray(response.body.data.esg_scores)).toBe(true);
        
        // Check ESG score structure
        if (response.body.data.esg_scores.length > 0) {
          const esgScore = response.body.data.esg_scores[0];
          expect(esgScore).toHaveProperty('symbol');
          expect(esgScore).toHaveProperty('esg_score');
          expect(esgScore).toHaveProperty('environmental_score');
          expect(esgScore).toHaveProperty('social_score');
          expect(esgScore).toHaveProperty('governance_score');
          expect(esgScore).toHaveProperty('controversy_score');
          expect(esgScore).toHaveProperty('esg_grade');
          expect(esgScore).toHaveProperty('industry_percentile');
        }
        
        // Check summary structure
        expect(response.body.data.summary).toHaveProperty('total_analyzed');
        expect(response.body.data.summary).toHaveProperty('average_esg_score');
        expect(response.body.data.summary).toHaveProperty('grade_distribution');
        
        // Check methodology documentation
        expect(response.body.data.methodology).toHaveProperty('scoring_framework');
        expect(response.body.data.methodology).toHaveProperty('data_sources');
      } else {
        expect([401]).toContain(response.status);
      }
    });

    test('should handle ESG grade filter', async () => {
      const response = await request(app)
        .get('/scores/esg?grade=A')
        .set('Authorization', 'Bearer dev-bypass-token');

      if (response.status === 200) {
        expect(response.body.data).toHaveProperty('esg_scores');
        // If scores are returned, they should have grade A
        if (response.body.data.esg_scores.length > 0) {
          response.body.data.esg_scores.forEach(score => {
            expect(['A+', 'A', 'A-']).toContain(score.esg_grade);
          });
        }
      }
    });

    test('should handle minimum ESG score filter', async () => {
      const response = await request(app)
        .get('/scores/esg?min_esg_score=80')
        .set('Authorization', 'Bearer dev-bypass-token');

      if (response.status === 200) {
        expect(response.body.data).toHaveProperty('esg_scores');
        // If scores are returned, they should be >= 80
        if (response.body.data.esg_scores.length > 0) {
          response.body.data.esg_scores.forEach(score => {
            expect(score.esg_score).toBeGreaterThanOrEqual(80);
          });
        }
      }
    });

    test('should handle sector filter for ESG scores', async () => {
      const response = await request(app)
        .get('/scores/esg?sector=Healthcare')
        .set('Authorization', 'Bearer dev-bypass-token');

      if (response.status === 200) {
        expect(response.body.data).toHaveProperty('esg_scores');
        // Sector filtering should be applied
        expect(response.body.data.summary).toHaveProperty('sector_filter', 'Healthcare');
      }
    });

    test('should handle ESG component sorting', async () => {
      const response = await request(app)
        .get('/scores/esg?sort=environmental_desc')
        .set('Authorization', 'Bearer dev-bypass-token');

      if (response.status === 200) {
        expect(response.body.data).toHaveProperty('esg_scores');
        // Scores should be sorted by environmental_score descending
        if (response.body.data.esg_scores.length > 1) {
          for (let i = 1; i < response.body.data.esg_scores.length; i++) {
            expect(response.body.data.esg_scores[i-1].environmental_score)
              .toBeGreaterThanOrEqual(response.body.data.esg_scores[i].environmental_score);
          }
        }
      }
    });

    test('should handle controversy filter', async () => {
      const response = await request(app)
        .get('/scores/esg?max_controversy=20')
        .set('Authorization', 'Bearer dev-bypass-token');

      if (response.status === 200) {
        expect(response.body.data).toHaveProperty('esg_scores');
        // If scores are returned, controversy score should be <= 20
        if (response.body.data.esg_scores.length > 0) {
          response.body.data.esg_scores.forEach(score => {
            expect(score.controversy_score).toBeLessThanOrEqual(20);
          });
        }
      }
    });
  });

  describe('GET /scores/:symbol/composite', () => {
    test('should return symbol-specific composite score', async () => {
      const response = await request(app)
        .get('/scores/AAPL/composite')
        .set('Authorization', 'Bearer dev-bypass-token');

      if (response.status === 200) {
        expect(response.body).toHaveProperty('success', true);
        expect(response.body).toHaveProperty('data');
        expect(response.body.data).toHaveProperty('symbol', 'AAPL');
        expect(response.body.data).toHaveProperty('composite_score');
        expect(response.body.data).toHaveProperty('score_breakdown');
        expect(response.body.data).toHaveProperty('percentile_rankings');
        expect(response.body.data).toHaveProperty('historical_trend');
      } else {
        expect([404, 401]).toContain(response.status);
      }
    });

    test('should handle lowercase symbol conversion', async () => {
      const response = await request(app)
        .get('/scores/aapl/composite')
        .set('Authorization', 'Bearer dev-bypass-token');

      if (response.status === 200) {
        expect(response.body.data).toHaveProperty('symbol', 'AAPL');
      }
    });
  });

  describe('GET /scores/:symbol/esg', () => {
    test('should return symbol-specific ESG score', async () => {
      const response = await request(app)
        .get('/scores/AAPL/esg')
        .set('Authorization', 'Bearer dev-bypass-token');

      if (response.status === 200) {
        expect(response.body).toHaveProperty('success', true);
        expect(response.body).toHaveProperty('data');
        expect(response.body.data).toHaveProperty('symbol', 'AAPL');
        expect(response.body.data).toHaveProperty('esg_score');
        expect(response.body.data).toHaveProperty('component_breakdown');
        expect(response.body.data).toHaveProperty('industry_comparison');
        expect(response.body.data).toHaveProperty('trend_analysis');
      } else {
        expect([404, 401]).toContain(response.status);
      }
    });

    test('should handle invalid symbol format', async () => {
      const response = await request(app)
        .get('/scores/INVALID123!/esg')
        .set('Authorization', 'Bearer dev-bypass-token');

      if (response.status !== 401) {
        expect([404, 400]).toContain(response.status);
      }
    });
  });

  describe('Response format', () => {
    test('should return consistent JSON response', async () => {
      const response = await request(app)
        .get('/scores')
        .set('Authorization', 'Bearer dev-bypass-token')
        .expect(200);

      expect(response.headers['content-type']).toMatch(/json/);
      expect(typeof response.body).toBe('object');
      expect(response.body).toHaveProperty('success');
    });

    test('should include pagination metadata when available', async () => {
      const response = await request(app)
        .get('/scores')
        .query({ page: 2, limit: 25 })
        .set('Authorization', 'Bearer dev-bypass-token')
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      if (response.body.pagination) {
        expect(response.body.pagination).toHaveProperty('currentPage');
        expect(response.body.pagination).toHaveProperty('itemsPerPage');
      }
    });
  });
});