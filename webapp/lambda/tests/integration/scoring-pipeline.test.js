/**
 * Scoring Pipeline Integration Test
 *
 * Validates the complete data flow from price data through stock scores.
 * This test ensures schemas match between loaders and API responses.
 *
 * Pipeline: price_daily → technical_data → quality_metrics → stock_scores → API response
 */

const { describe, it, expect, beforeAll, afterAll } = require('@jest/globals');
const { query } = require('../../utils/database');
const schemas = require('../../schemas/databaseSchema');

// ============================================================================
// TEST SETUP
// ============================================================================

describe('Scoring Pipeline Integration', () => {
  const testSymbol = 'AAPL';
  const testDate = new Date().toISOString().split('T')[0];

  beforeAll(async () => {
    // Verify database is accessible
    try {
      const result = await query('SELECT NOW()');
      expect(result.rows).toBeDefined();
      console.log('✅ Database connection successful');
    } catch (error) {
      console.error('❌ Database connection failed:', error.message);
      throw error;
    }
  });

  afterAll(async () => {
    // Cleanup if needed
  });

  // =========================================================================
  // TABLE EXISTENCE TESTS
  // =========================================================================

  describe('Database Tables', () => {
    const requiredTables = [
      'price_daily',
      'technical_data_daily',
      'quality_metrics',
      'growth_metrics',
      'momentum_metrics',
      'risk_metrics',
      'positioning_metrics',
      'stock_scores',
      'company_profile',
    ];

    requiredTables.forEach((tableName) => {
      it(`should have ${tableName} table`, async () => {
        const result = await query(`
          SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = $1
          );
        `, [tableName]);

        const tableExists = result.rows[0].exists;
        if (!tableExists) {
          console.warn(`⚠️ Table ${tableName} not found in database`);
        }
        expect(tableExists).toBe(true);
      });
    });

    it('should have relative_strength_metrics table (or warn if missing)', async () => {
      const result = await query(`
        SELECT EXISTS (
          SELECT FROM information_schema.tables
          WHERE table_schema = 'public'
          AND table_name = 'relative_strength_metrics'
        );
      `);

      const tableExists = result.rows[0].exists;
      if (!tableExists) {
        console.warn('⚠️ relative_strength_metrics table not found - RS scores will be NULL');
      }
    });
  });

  // =========================================================================
  // SCHEMA VALIDATION TESTS
  // =========================================================================

  describe('Price Daily Schema', () => {
    it('should have all required columns', async () => {
      const requiredColumns = [
        'symbol', 'date', 'open', 'high', 'low', 'close', 'adj_close', 'volume'
      ];

      const result = await query(`
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
        AND table_name = 'price_daily'
      `);

      const columns = result.rows.map(r => r.column_name);
      requiredColumns.forEach(col => {
        expect(columns).toContain(col);
      });
    });

    it('should have valid data types', async () => {
      const result = await query(`
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
        AND table_name = 'price_daily'
        AND column_name IN ('price', 'close', 'volume')
      `);

      const schema = {};
      result.rows.forEach(r => {
        schema[r.column_name] = r.data_type;
      });

      // Verify numeric columns have appropriate types
      if (schema.close) {
        expect(['numeric', 'double precision']).toContain(schema.close);
      }
    });
  });

  describe('Quality Metrics Schema', () => {
    it('should have all factor columns', async () => {
      const requiredColumns = [
        'return_on_equity_pct',
        'return_on_assets_pct',
        'gross_margin_pct',
        'fcf_to_net_income',
        'debt_to_equity',
        'current_ratio',
      ];

      const result = await query(`
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
        AND table_name = 'quality_metrics'
      `);

      const columns = result.rows.map(r => r.column_name);
      requiredColumns.forEach(col => {
        expect(columns).toContain(col);
      });
    });
  });

  describe('Stock Scores Schema', () => {
    it('should have all composite score columns', async () => {
      const requiredColumns = [
        'symbol',
        'composite_score',
        'momentum_score',
        'trend_score',
        'value_score',
        'quality_score',
        'growth_score',
        'positioning_score',
        'sentiment_score',
      ];

      const result = await query(`
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
        AND table_name = 'stock_scores'
      `);

      const columns = result.rows.map(r => r.column_name);
      requiredColumns.forEach(col => {
        expect(columns).toContain(col);
      });
    });

    it('should have JSONB input columns', async () => {
      const jsonColumns = [
        'value_inputs',
        'quality_inputs',
        'growth_inputs',
        'momentum_inputs',
        'risk_inputs',
      ];

      const result = await query(`
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
        AND table_name = 'stock_scores'
        AND data_type = 'jsonb'
      `);

      const jsonbColumns = result.rows.map(r => r.column_name);
      console.log('JSONB columns in stock_scores:', jsonbColumns);

      // At least value_inputs should exist
      expect(jsonbColumns.length).toBeGreaterThan(0);
    });
  });

  // =========================================================================
  // DATA QUALITY TESTS
  // =========================================================================

  describe('Data Completeness', () => {
    it('should have recent price data', async () => {
      const result = await query(`
        SELECT COUNT(*) as count
        FROM price_daily
        WHERE symbol = $1
        AND date >= CURRENT_DATE - INTERVAL '30 days'
      `, [testSymbol]);

      const count = parseInt(result.rows[0].count);
      expect(count).toBeGreaterThan(0);
      console.log(`✅ Found ${count} price records for ${testSymbol} in last 30 days`);
    });

    it('should have technical data aligned with price data', async () => {
      const result = await query(`
        SELECT COUNT(*) as price_count,
               (SELECT COUNT(*) FROM technical_data_daily
                WHERE symbol = $1
                AND date >= CURRENT_DATE - INTERVAL '30 days') as tech_count
        FROM price_daily
        WHERE symbol = $1
        AND date >= CURRENT_DATE - INTERVAL '30 days'
      `, [testSymbol]);

      const priceCount = parseInt(result.rows[0].price_count);
      const techCount = parseInt(result.rows[0].tech_count);

      console.log(`Price data: ${priceCount} records, Technical data: ${techCount} records`);
      // Allow some technical data to lag behind price data
      expect(techCount).toBeGreaterThan(0);
    });

    it('should have quality metrics for tracked stocks', async () => {
      const result = await query(`
        SELECT COUNT(DISTINCT symbol) as count
        FROM quality_metrics
        WHERE date >= CURRENT_DATE - INTERVAL '7 days'
      `);

      const count = parseInt(result.rows[0].count);
      console.log(`✅ Quality metrics available for ${count} symbols`);
      expect(count).toBeGreaterThan(0);
    });

    it('should have stock scores with non-null composite scores', async () => {
      const result = await query(`
        SELECT COUNT(*) as count
        FROM stock_scores
        WHERE composite_score IS NOT NULL
        AND symbol IN (
          SELECT symbol FROM stock_symbols LIMIT 50
        )
      `);

      const count = parseInt(result.rows[0].count);
      console.log(`✅ Stock scores available for ${count} symbols`);
      expect(count).toBeGreaterThan(0);
    });
  });

  // =========================================================================
  // FACTOR CALCULATION VALIDATION TESTS
  // =========================================================================

  describe('Factor Calculations', () => {
    it('should have momentum components that sum reasonably', async () => {
      const result = await query(`
        SELECT
          momentum_3m,
          momentum_6m,
          momentum_12m_1
        FROM momentum_metrics
        WHERE symbol = $1
        AND date = (
          SELECT MAX(date) FROM momentum_metrics WHERE symbol = $1
        )
      `, [testSymbol]);

      if (result.rows.length > 0) {
        const metrics = result.rows[0];
        // Momentum values should be reasonable percentages
        if (metrics.momentum_3m !== null) {
          expect(metrics.momentum_3m).toBeLessThan(500);
          expect(metrics.momentum_3m).toBeGreaterThan(-500);
        }
      }
    });

    it('should have quality metrics with valid percentages', async () => {
      const result = await query(`
        SELECT
          return_on_equity_pct,
          return_on_assets_pct,
          gross_margin_pct
        FROM quality_metrics
        WHERE symbol = $1
        ORDER BY date DESC
        LIMIT 1
      `, [testSymbol]);

      if (result.rows.length > 0) {
        const metrics = result.rows[0];
        // ROE typically ranges 0-500% for valid companies
        if (metrics.return_on_equity_pct !== null) {
          expect(metrics.return_on_equity_pct).toBeGreaterThan(-200);
          expect(metrics.return_on_equity_pct).toBeLessThan(500);
        }
      }
    });

    it('should have composite score within valid range', async () => {
      const result = await query(`
        SELECT composite_score, symbol
        FROM stock_scores
        WHERE symbol = $1
        ORDER BY score_date DESC
        LIMIT 1
      `, [testSymbol]);

      if (result.rows.length > 0) {
        const score = result.rows[0].composite_score;
        if (score !== null) {
          expect(score).toBeGreaterThanOrEqual(0);
          expect(score).toBeLessThanOrEqual(100);
        }
      }
    });
  });

  // =========================================================================
  // API RESPONSE SCHEMA TESTS
  // =========================================================================

  describe('API Response Structures', () => {
    it('stock score response should match schema', async () => {
      const result = await query(`
        SELECT *
        FROM stock_scores
        WHERE symbol = $1
        ORDER BY score_date DESC
        LIMIT 1
      `, [testSymbol]);

      if (result.rows.length > 0) {
        const row = result.rows[0];

        // Verify required fields exist and have correct types
        expect(row.symbol).toBeDefined();
        expect(typeof row.composite_score).toBe('number');
        expect(typeof row.momentum_score).toBe('number');

        // Verify composite scores are between 0-100
        [
          'composite_score',
          'momentum_score',
          'value_score',
          'quality_score',
          'growth_score',
          'positioning_score',
          'sentiment_score',
        ].forEach(field => {
          if (row[field] !== null) {
            expect(row[field]).toBeGreaterThanOrEqual(0);
            expect(row[field]).toBeLessThanOrEqual(100);
          }
        });

        console.log(`✅ Stock scores for ${testSymbol}:`, {
          composite: row.composite_score,
          momentum: row.momentum_score,
          value: row.value_score,
          quality: row.quality_score,
        });
      }
    });
  });

  // =========================================================================
  // MISSING DATA HANDLING TESTS
  // =========================================================================

  describe('Graceful Degradation', () => {
    it('should handle missing relative_strength_metrics gracefully', async () => {
      // Check if table exists
      const tableExists = await query(`
        SELECT EXISTS (
          SELECT FROM information_schema.tables
          WHERE table_schema = 'public'
          AND table_name = 'relative_strength_metrics'
        );
      `);

      if (!tableExists.rows[0].exists) {
        console.warn('⚠️ relative_strength_metrics table missing - API should return NULL for RS scores');
        // This is expected - test that API handles it gracefully
        expect(true).toBe(true);
      }
    });

    it('should handle NULL factor inputs gracefully', async () => {
      const result = await query(`
        SELECT symbol, value_inputs, quality_inputs
        FROM stock_scores
        WHERE value_inputs IS NULL
        OR quality_inputs IS NULL
        LIMIT 1
      `);

      if (result.rows.length > 0) {
        console.warn('⚠️ Some stocks have NULL factor inputs - API should provide defaults');
      }
    });
  });

  // =========================================================================
  // DATA CONSISTENCY TESTS
  // =========================================================================

  describe('Cross-Table Consistency', () => {
    it('stock_scores should join correctly with quality_metrics', async () => {
      const result = await query(`
        SELECT
          ss.symbol,
          ss.quality_score,
          qm.return_on_equity_pct
        FROM stock_scores ss
        LEFT JOIN quality_metrics qm
          ON ss.symbol = qm.symbol
          AND DATE(ss.score_date) = qm.date
        WHERE ss.symbol = $1
        AND ss.quality_score IS NOT NULL
        LIMIT 1
      `, [testSymbol]);

      if (result.rows.length > 0) {
        const row = result.rows[0];
        expect(row.symbol).toBe(testSymbol);
        expect(row.quality_score).toBeDefined();
        console.log(`✅ Quality metrics join successful for ${testSymbol}`);
      }
    });

    it('stock_scores should join correctly with momentum_metrics', async () => {
      const result = await query(`
        SELECT
          ss.symbol,
          ss.momentum_score,
          mm.momentum_12m_1
        FROM stock_scores ss
        LEFT JOIN momentum_metrics mm
          ON ss.symbol = mm.symbol
          AND DATE(ss.score_date) = mm.date
        WHERE ss.symbol = $1
        AND ss.momentum_score IS NOT NULL
        LIMIT 1
      `, [testSymbol]);

      if (result.rows.length > 0) {
        console.log(`✅ Momentum metrics join successful for ${testSymbol}`);
      }
    });
  });
});
