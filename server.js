#!/usr/bin/env node
/**
 * Minimal Unified API Server
 * All endpoints return: { success: true/false, data: [...], timestamp: "..." }
 */

const express = require('express');
const cors = require('cors');
const path = require('path');
const { Pool } = require('pg');

// Load environment
require('dotenv').config({ path: path.join(__dirname, '.env.local') });

const app = express();
app.use(cors());
app.use(express.json());

// Database
const pool = new Pool({
  host: process.env.DB_HOST || 'localhost',
  port: parseInt(process.env.DB_PORT || 5432),
  user: process.env.DB_USER || 'stocks',
  password: process.env.DB_PASSWORD || 'bed0elAn',
  database: process.env.DB_NAME || 'stocks',
  ssl: false,
  max: 20,
});

// Helpers
const ok = (res, data) => res.json({ success: true, data, timestamp: new Date().toISOString() });
const err = (res, error, code = 500) => res.status(code).json({ success: false, error: error.message || error, timestamp: new Date().toISOString() });

// Health
app.get('/health', async (req, res) => {
  try {
    const result = await pool.query('SELECT NOW() as ts');
    ok(res, { status: 'ok', db: 'connected', timestamp: result.rows[0].ts });
  } catch (e) {
    err(res, e);
  }
});

// Stock scores
app.get('/api/stock-scores', async (req, res) => {
  try {
    const limit = parseInt(req.query.limit) || 100;
    const result = await pool.query(
      'SELECT symbol, company_name, composite_score FROM stock_scores ORDER BY composite_score DESC LIMIT $1',
      [limit]
    );
    ok(res, result.rows);
  } catch (e) {
    err(res, e);
  }
});

// Stocks
app.get('/api/stocks', async (req, res) => {
  try {
    const result = await pool.query('SELECT * FROM stock_symbols LIMIT 100');
    ok(res, result.rows);
  } catch (e) {
    err(res, e);
  }
});

// Stocks count
app.get('/api/stocks-count', async (req, res) => {
  try {
    const result = await pool.query('SELECT COUNT(DISTINCT symbol) as count FROM stock_symbols');
    ok(res, result.rows[0]);
  } catch (e) {
    err(res, e);
  }
});

// Market summary
app.get('/api/market/summary', async (req, res) => {
  try {
    const stocks = await pool.query('SELECT COUNT(*) as count FROM stock_symbols');
    const prices = await pool.query('SELECT COUNT(*) as count FROM price_daily');
    const scores = await pool.query('SELECT COUNT(*) as count FROM stock_scores');
    ok(res, {
      totalStocks: parseInt(stocks.rows[0].count),
      totalPrices: parseInt(prices.rows[0].count),
      totalScores: parseInt(scores.rows[0].count)
    });
  } catch (e) {
    err(res, e);
  }
});

// Sector ranking
app.get('/api/sector-ranking', async (req, res) => {
  try {
    const result = await pool.query('SELECT * FROM sector_ranking WHERE date_recorded = (SELECT MAX(date_recorded) FROM sector_ranking) ORDER BY current_rank LIMIT 20');
    ok(res, result.rows);
  } catch (e) {
    err(res, e);
  }
});

// Industry ranking
app.get('/api/industry-ranking', async (req, res) => {
  try {
    const result = await pool.query('SELECT * FROM industry_ranking WHERE date_recorded = (SELECT MAX(date_recorded) FROM industry_ranking) ORDER BY current_rank LIMIT 20');
    ok(res, result.rows);
  } catch (e) {
    err(res, e);
  }
});

// Static files
const frontendPath = path.join(__dirname, 'webapp/frontend-admin/dist-admin');
app.use(express.static(frontendPath, { index: false }));

// SPA fallback - must come last, use middleware not route
app.use((req, res) => {
  res.sendFile(path.join(frontendPath, 'index.html'));
});

// Start
const PORT = process.env.PORT || 3001;
app.listen(PORT, () => {
  console.log(`\n✅ Server running on http://localhost:${PORT}`);
  console.log(`📊 API: http://localhost:${PORT}/api/`);
  console.log(`🌐 Frontend: http://localhost:${PORT}/\n`);
});
