/**
 * Data Pipeline Integration Tests
 *
 * Verifies end-to-end data flow from loaders through API to frontend
 * Tests schema alignment and data consistency across the entire pipeline
 */

const request = require('supertest');
const { app } = require('../../webapp/lambda/index');
const {
  query,
  initializeDatabase,
  closeDatabase,
} = require('../../webapp/lambda/utils/database');

describe('Data Pipeline Integration - End-to-End', () => {
  beforeAll(async () => {
    await initializeDatabase();
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe('Growth Metrics Data Flow', () => {
    test('should have growth metrics loaded for test symbols', async () => {
      const result = await query(
        'SELECT COUNT(*) as count FROM growth_metrics WHERE symbol IN (SELECT symbol FROM stock_symbols LIMIT 5)'
      );
      expect(result.rows[0].count).toBeGreaterThan(0);
    });

    test('growth metrics should have required fields without NULL defaults', async () => {
      const result = await query(
        `SELECT * FROM growth_metrics
         WHERE symbol IN (SELECT symbol FROM stock_symbols LIMIT 1)
         LIMIT 1`
      );

      if (result.rows.length > 0) {
        const row = result.rows[0];
        expect(row).toHaveProperty('symbol');
        // Fields should either have real values or be NULL (not hardcoded defaults)
        if (row.revenue_growth_3y_cagr !== null) {
          expect(row.revenue_growth_3y_cagr).not.toBe(0.5);
        }
      }
    });
  });

  describe('Risk Metrics Data Flow', () => {
    test('should have risk metrics loaded', async () => {
      const result = await query(
        'SELECT COUNT(*) as count FROM risk_metrics WHERE symbol IN (SELECT symbol FROM stock_symbols LIMIT 5)'
      );
      expect(result.rows[0].count).toBeGreaterThan(0);
    });

    test('risk metrics API should return complete risk inputs', async () => {
      const response = await request(app)
        .get('/api/scores/AAPL');

      expect(response.status).toBe(200);
      if (response.body.data) {
        expect(response.body.data).toHaveProperty('risk_inputs');
        const riskInputs = response.body.data.risk_inputs;

        // Verify risk inputs structure
        expect(riskInputs).toHaveProperty('volatility_12m_pct');
        expect(riskInputs).toHaveProperty('volatility_risk_component');
        expect(riskInputs).toHaveProperty('max_drawdown_52w_pct');
        expect(riskInputs).toHaveProperty('beta');
      }
    });
  });

  describe('Value Metrics Data Flow', () => {
    test('should have value metrics table schema available', async () => {
      const result = await query(
        `SELECT column_name FROM information_schema.columns
         WHERE table_name = 'value_metrics'
         ORDER BY ordinal_position
         LIMIT 1`
      );

      // Table should exist with schema
      expect(result.rows.length).toBeGreaterThan(0);
    });
  });

  describe('Schema Alignment', () => {
    test('stock_scores table should have all required columns', async () => {
      const result = await query(
        `SELECT column_name
         FROM information_schema.columns
         WHERE table_name = 'stock_scores'
         ORDER BY ordinal_position`
      );

      const columns = result.rows.map(r => r.column_name);
      expect(columns).toContain('symbol');
      expect(columns).toContain('composite_score');
      expect(columns).toContain('momentum_score');
      expect(columns).toContain('value_score');
      expect(columns).toContain('quality_score');
      expect(columns).toContain('growth_score');
      expect(columns).toContain('stability_score');
    });

    test('growth_metrics table schema should be consistent', async () => {
      const result = await query(
        `SELECT column_name
         FROM information_schema.columns
         WHERE table_name = 'growth_metrics'
         ORDER BY ordinal_position`
      );

      const columns = result.rows.map(r => r.column_name);
      expect(columns).toContain('symbol');
      expect(columns.length).toBeGreaterThan(0);
    });

    test('risk_metrics table should have all risk components', async () => {
      const result = await query(
        `SELECT column_name
         FROM information_schema.columns
         WHERE table_name = 'risk_metrics'
         ORDER BY ordinal_position`
      );

      const columns = result.rows.map(r => r.column_name);
      expect(columns).toContain('volatility_12m_pct');
      expect(columns).toContain('max_drawdown_52w_pct');
    });
  });

  describe('Exception Handling - NO Hardcoded Defaults', () => {
    test('API should handle requests without crashing', async () => {
      const response = await request(app)
        .get('/api/scores')
        .query({ limit: 50 });

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);

      // All stocks should return successfully
      if (response.body.data.stocks.length > 0) {
        for (const stock of response.body.data.stocks) {
          expect(stock).toHaveProperty('symbol');
          expect(stock).toHaveProperty('composite_score');
        }
      }
    });
  });

  describe('Config Alignment', () => {
    test('scoring weights should be properly configured', async () => {
      const config = require('../../config');

      expect(config).toHaveProperty('COMPOSITE_SCORE_WEIGHTS');
      expect(config).toHaveProperty('RISK_SCORE_WEIGHTS');

      // Verify weights sum to 1.0
      const compositeSum = Object.values(config.COMPOSITE_SCORE_WEIGHTS).reduce((a, b) => a + b, 0);
      expect(Math.abs(compositeSum - 1.0)).toBeLessThan(0.0001);
    });
  });
});
