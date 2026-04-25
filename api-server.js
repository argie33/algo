#!/usr/bin/env node
/**
 * Unified API Server - Single source of truth for all API endpoints
 * All endpoints return: { success: true/false, data: [...], timestamp: "..." }
 */

require('dotenv').config({ path: require('path').join(__dirname, '.env.local') });

const express = require('express');
const cors = require('cors');
const path = require('path');
const { Pool } = require('pg');

const app = express();
app.use(cors());
app.use(express.json());

const frontendPath = path.join(__dirname, 'webapp/frontend-admin/dist-admin');

const dbConfig = {
  host: process.env.DB_HOST || 'localhost',
  port: parseInt(process.env.DB_PORT || '5432'),
  user: process.env.DB_USER || 'stocks',
  password: process.env.DB_PASSWORD || 'bed0elAn',
  database: process.env.DB_NAME || 'stocks',
  ssl: false,
  max: 20,
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 2000,
};

const pool = new Pool(dbConfig);

pool.on('error', (err) => {
  console.error('Unexpected error on idle client', err);
});

// Response helpers
const sendSuccess = (res, data, statusCode = 200) => {
  res.status(statusCode).json({
    success: true,
    data: data,
    timestamp: new Date().toISOString()
  });
};

const sendError = (res, error, statusCode = 500) => {
  res.status(statusCode).json({
    success: false,
    error: typeof error === 'string' ? error : (error.message || 'Unknown error'),
    timestamp: new Date().toISOString()
  });
};

// ============================================================================
// API ROUTES - DEFINED BEFORE STATIC FILES
// ============================================================================

// Health check
app.get('/health', async (req, res) => {
  try {
    const result = await pool.query('SELECT NOW() as timestamp');
    sendSuccess(res, {
      status: 'ok',
      database: 'connected',
      timestamp: result.rows[0].timestamp
    });
  } catch (error) {
    sendError(res, error);
  }
});

// Stock symbols
app.get('/api/stocks', async (req, res) => {
  try {
    const result = await pool.query('SELECT * FROM stock_symbols LIMIT 100');
    sendSuccess(res, result.rows);
  } catch (error) {
    sendError(res, error);
  }
});

app.get('/api/stocks/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const result = await pool.query(
      'SELECT * FROM price_daily WHERE symbol = $1 ORDER BY date DESC LIMIT 30',
      [symbol]
    );
    sendSuccess(res, result.rows);
  } catch (error) {
    sendError(res, error);
  }
});

app.get('/api/stocks-count', async (req, res) => {
  try {
    const result = await pool.query('SELECT COUNT(DISTINCT symbol) as count FROM price_daily');
    sendSuccess(res, result.rows[0]);
  } catch (error) {
    sendError(res, error);
  }
});

// Stock scores (rankings)
app.get('/api/stock-scores', async (req, res) => {
  try {
    const limit = parseInt(req.query.limit) || 100;
    const result = await pool.query(
      'SELECT symbol, company_name, composite_score, growth_score, momentum_score, created_at FROM stock_scores ORDER BY composite_score DESC LIMIT $1',
      [limit]
    );
    sendSuccess(res, result.rows);
  } catch (error) {
    sendError(res, error);
  }
});

app.get('/api/stock-scores/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const result = await pool.query('SELECT * FROM stock_scores WHERE symbol = $1', [symbol]);
    sendSuccess(res, result.rows[0] || {});
  } catch (error) {
    sendError(res, error);
  }
});

// Key metrics
app.get('/api/key-metrics/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const result = await pool.query('SELECT * FROM key_metrics WHERE symbol = $1', [symbol]);
    sendSuccess(res, result.rows[0] || {});
  } catch (error) {
    sendError(res, error);
  }
});

// Sector/Industry data
app.get('/api/sector-ranking', async (req, res) => {
  try {
    const result = await pool.query(
      'SELECT * FROM sector_ranking WHERE date_recorded = (SELECT MAX(date_recorded) FROM sector_ranking) ORDER BY current_rank'
    );
    sendSuccess(res, result.rows);
  } catch (error) {
    sendError(res, error);
  }
});

app.get('/api/industry-ranking', async (req, res) => {
  try {
    const result = await pool.query(
      'SELECT * FROM industry_ranking WHERE date_recorded = (SELECT MAX(date_recorded) FROM industry_ranking) ORDER BY current_rank LIMIT 50'
    );
    sendSuccess(res, result.rows);
  } catch (error) {
    sendError(res, error);
  }
});

// Market summary
app.get('/api/market/summary', async (req, res) => {
  try {
    const stocks = await pool.query('SELECT COUNT(*) as count FROM stock_symbols');
    const prices = await pool.query('SELECT COUNT(*) as count FROM price_daily');
    const scores = await pool.query('SELECT COUNT(*) as count FROM stock_scores WHERE composite_score IS NOT NULL');

    sendSuccess(res, {
      totalStocks: parseInt(stocks.rows[0].count),
      totalPriceRecords: parseInt(prices.rows[0].count),
      stocksWithScores: parseInt(scores.rows[0].count)
    });
  } catch (error) {
    sendError(res, error);
  }
});

// Commodities
app.get('/api/commodities/categories', async (req, res) => {
  try {
    const result = await pool.query('SELECT DISTINCT category FROM commodity_categories ORDER BY category');
    sendSuccess(res, result.rows);
  } catch (error) {
    sendError(res, error);
  }
});

app.get('/api/commodities/prices', async (req, res) => {
  try {
    const limit = req.query.limit || 50;
    const result = await pool.query(
      'SELECT * FROM commodity_prices ORDER BY updated_at DESC LIMIT $1',
      [limit]
    );
    sendSuccess(res, result.rows);
  } catch (error) {
    sendError(res, error);
  }
});

// Earnings
app.get('/api/earnings/history/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const result = await pool.query(
      'SELECT * FROM earnings_history WHERE symbol = $1 ORDER BY fiscal_date DESC LIMIT 10',
      [symbol]
    );
    sendSuccess(res, result.rows);
  } catch (error) {
    sendError(res, error);
  }
});

// ============================================================================
// STATIC FILES & SPA FALLBACK (AFTER API ROUTES)
// ============================================================================

// Serve static assets
app.use(express.static(frontendPath, {
  index: false, // Don't auto-serve index.html
  setHeaders: (res, filePath) => {
    if (filePath.endsWith('.html')) {
      res.setHeader('Cache-Control', 'no-cache');
    }
  }
}));

// SPA fallback - only for non-API routes
app.use((req, res) => {
  // Don't send SPA for API routes
  if (req.path.startsWith('/api/') || req.path === '/health') {
    return sendError(res, 'Not Found', 404);
  }
  // Send SPA for everything else
  res.sendFile(path.join(frontendPath, 'index.html'));
});

// ============================================================================
// START SERVER
// ============================================================================

const PORT = process.env.PORT || 3001;

app.listen(PORT, () => {
  console.log(`
╔════════════════════════════════════════════════════════════╗
║         🚀 UNIFIED API SERVER - READY TO USE               ║
╚════════════════════════════════════════════════════════════╝

  Server:    http://localhost:${PORT}
  API Base:  http://localhost:${PORT}/api/
  Health:    http://localhost:${PORT}/health
  Frontend:  http://localhost:${PORT}/

  Database:  ${dbConfig.host}:${dbConfig.port}/${dbConfig.database}

  All endpoints return consistent JSON:
    { success: true/false, data: {...}, timestamp: "..." }

✓ Stock data & rankings
✓ Financial metrics
✓ Sector & Industry analysis
✓ Commodities & Market data
✓ Earnings history

  Ready to serve requests!
`);
});
