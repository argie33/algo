/**
 * Benchmarks API Route
 * Provides 3-tier benchmark data for stock metrics
 *
 * Tiers:
 * 1. Sector benchmarks - median values for stocks in the same sector
 * 2. Historical benchmarks - stock's own historical averages (1yr, 3yr, 5yr)
 * 3. Market benchmarks - overall market averages from large-cap stocks
 */

const express = require('express');

const router = express.Router();
const { query } = require('../utils/database');

/**
 * GET /api/benchmarks/:symbol
 * Get 3-tier benchmarks for a specific stock
 *
 * Returns:
 * {
 *   success: true,
 *   data: {
 *     symbol: "AAPL",
 *     sector: "Technology",
 *     benchmarks: {
 *       roe: {
 *         sector: 23.1,
 *         historical_1yr: 25.3,
 *         historical_3yr: 24.8,
 *         historical_5yr: 24.2,
 *         market: 20.2
 *       },
 *       gross_margin: { ... },
 *       ... other metrics
 *     }
 *   }
 * }
 */
router.get('/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;

    if (!symbol || !/^[A-Z]{1,5}$/.test(symbol)) {
      return res.error('Invalid symbol format', 400);
    }

    // Get company sector
    const sectorResult = await query(
      `SELECT sector FROM company_profile WHERE ticker = $1`,
      [symbol]
    );

    if (!sectorResult.rows.length) {
      return res.error(`Stock ${symbol} not found`, 404);
    }

    const sector = sectorResult.rows[0].sector;

    // Get sector benchmarks
    const sectorBenchmarks = await query(
      `SELECT
        roe, roa, gross_margin, operating_margin, profit_margin,
        pe_ratio, price_to_book, ev_to_ebitda,
        debt_to_equity, current_ratio
      FROM sector_benchmarks
      WHERE sector = $1`,
      [sector]
    );

    // Get market benchmarks
    const marketBenchmarks = await query(
      `SELECT
        roe, roa, gross_margin, operating_margin, profit_margin,
        pe_ratio, price_to_book, ev_to_ebitda,
        debt_to_equity, current_ratio
      FROM sector_benchmarks
      WHERE sector = 'MARKET'`
    );

    // Get historical benchmarks for the symbol
    const historicalBenchmarks = await query(
      `SELECT
        metric_name,
        avg_1yr,
        avg_3yr,
        avg_5yr,
        percentile_25,
        percentile_75
      FROM historical_benchmarks
      WHERE symbol = $1`,
      [symbol]
    );

    // Build response
    const sectorData = sectorBenchmarks.rows[0] || {};
    const marketData = marketBenchmarks.rows[0] || {};
    const historicalData = {};

    // Convert historical data array to object by metric_name
    historicalBenchmarks.rows.forEach(row => {
      historicalData[row.metric_name] = {
        avg_1yr: row.avg_1yr,
        avg_3yr: row.avg_3yr,
        avg_5yr: row.avg_5yr,
        percentile_25: row.percentile_25,
        percentile_75: row.percentile_75,
      };
    });

    // Helper function to build metric benchmark object
    const buildMetricBenchmark = (metricName) => {
      const historical = historicalData[metricName] || {};
      return {
        sector: sectorData[metricName] || null,
        historical_1yr: historical.avg_1yr || null,
        historical_3yr: historical.avg_3yr || null,
        historical_5yr: historical.avg_5yr || null,
        market: marketData[metricName] || null,
      };
    };

    const benchmarks = {
      roe: buildMetricBenchmark('roe'),
      roa: buildMetricBenchmark('roa'),
      gross_margin: buildMetricBenchmark('gross_margin'),
      operating_margin: buildMetricBenchmark('operating_margin'),
      profit_margin: buildMetricBenchmark('profit_margin'),
      pe_ratio: buildMetricBenchmark('pe_ratio'),
      price_to_book: buildMetricBenchmark('price_to_book'),
      ev_to_ebitda: buildMetricBenchmark('ev_to_ebitda'),
      debt_to_equity: buildMetricBenchmark('debt_to_equity'),
      current_ratio: buildMetricBenchmark('current_ratio'),
    };

    return res.success({
      symbol,
      sector,
      benchmarks,
    });

  } catch (error) {
    console.error('Benchmarks API error:', error);
    return res.error('Failed to fetch benchmarks', 500);
  }
});

/**
 * GET /api/benchmarks/
 * API overview
 */
router.get('/', (req, res) => {
  res.success({
    message: 'Benchmarks API - Ready',
    description: '3-tier benchmark system (Sector, Historical, Market)',
    endpoints: [
      { path: '/api/benchmarks/:symbol', method: 'GET', description: 'Get benchmarks for a stock' }
    ],
    timestamp: new Date().toISOString(),
  });
});

module.exports = router;
