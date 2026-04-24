const express = require('express');
const cors = require('cors');
const path = require('path');
const { Pool } = require('pg');

const app = express();
app.use(cors());
app.use(express.json());

const frontendPath = path.join(__dirname, 'webapp/frontend-admin/dist-admin');

// Database connection
const pool = new Pool({
  host: process.env.DB_HOST || 'localhost',
  port: process.env.DB_PORT || 5432,
  user: process.env.DB_USER || 'stocks',
  password: process.env.DB_PASSWORD || '',
  database: process.env.DB_NAME || 'stocks',
  ssl: false
});

// Health check
app.get('/health', async (req, res) => {
  try {
    const result = await pool.query('SELECT NOW()');
    res.json({ status: 'ok', timestamp: result.rows[0] });
  } catch (error) {
    res.status(500).json({ status: 'error', message: error.message });
  }
});

// API routes
app.get('/api/stocks', async (req, res) => {
  try {
    const result = await pool.query('SELECT * FROM stock_symbols LIMIT 100');
    res.json(result.rows);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.get('/api/stocks/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const result = await pool.query(
      'SELECT * FROM price_daily WHERE symbol = $1 ORDER BY date DESC LIMIT 30',
      [symbol]
    );
    res.json(result.rows);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Additional useful API endpoints
app.get('/api/stocks-count', async (req, res) => {
  try {
    const result = await pool.query('SELECT COUNT(DISTINCT symbol) as count FROM price_daily');
    res.json(result.rows[0]);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.get('/api/prices-count', async (req, res) => {
  try {
    const result = await pool.query('SELECT COUNT(*) as count FROM price_daily');
    res.json(result.rows[0]);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Key metrics endpoint
app.get('/api/key-metrics/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const result = await pool.query('SELECT * FROM key_metrics WHERE symbol = $1', [symbol]);
    res.json(result.rows[0] || {});
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Stock scores endpoint
app.get('/api/stock-scores', async (req, res) => {
  try {
    const result = await pool.query('SELECT * FROM stock_scores ORDER BY composite_score DESC LIMIT 100');
    res.json(result.rows);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.get('/api/stock-scores/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const result = await pool.query('SELECT * FROM stock_scores WHERE symbol = $1', [symbol]);
    res.json(result.rows[0] || {});
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Quality metrics
app.get('/api/quality-metrics/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const result = await pool.query('SELECT * FROM quality_metrics WHERE symbol = $1', [symbol]);
    res.json(result.rows[0] || {});
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Growth metrics
app.get('/api/growth-metrics/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const result = await pool.query('SELECT * FROM growth_metrics WHERE symbol = $1', [symbol]);
    res.json(result.rows[0] || {});
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Value metrics
app.get('/api/value-metrics/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const result = await pool.query('SELECT * FROM value_metrics WHERE symbol = $1', [symbol]);
    res.json(result.rows[0] || {});
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Stability metrics
app.get('/api/stability-metrics/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const result = await pool.query('SELECT * FROM stability_metrics WHERE symbol = $1 ORDER BY date DESC LIMIT 1', [symbol]);
    res.json(result.rows[0] || {});
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Momentum metrics
app.get('/api/momentum-metrics/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const result = await pool.query('SELECT * FROM momentum_metrics WHERE symbol = $1 ORDER BY date DESC LIMIT 1', [symbol]);
    res.json(result.rows[0] || {});
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Trading signals
app.get('/api/signals/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const result = await pool.query(
      'SELECT * FROM buy_sell_daily WHERE symbol = $1 ORDER BY date DESC LIMIT 10',
      [symbol]
    );
    res.json(result.rows);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Top stocks by composite score
app.get('/api/top-stocks', async (req, res) => {
  try {
    const limit = req.query.limit || 50;
    const result = await pool.query(
      'SELECT * FROM stock_scores ORDER BY composite_score DESC LIMIT $1',
      [limit]
    );
    res.json(result.rows);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Bottom stocks
app.get('/api/bottom-stocks', async (req, res) => {
  try {
    const limit = req.query.limit || 50;
    const result = await pool.query(
      'SELECT * FROM stock_scores ORDER BY composite_score ASC LIMIT $1',
      [limit]
    );
    res.json(result.rows);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Market summary endpoint
app.get('/api/market/summary', async (req, res) => {
  try {
    const stocks = await pool.query('SELECT COUNT(*) as count FROM stock_symbols');
    const prices = await pool.query('SELECT COUNT(*) as count FROM price_daily');
    const scores = await pool.query('SELECT COUNT(*) as count FROM stock_scores');

    res.json({
      success: true,
      totalStocks: stocks.rows[0].count,
      totalPrices: prices.rows[0].count,
      totalScores: scores.rows[0].count,
      lastUpdated: new Date().toISOString()
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// AAII Sentiment endpoint (placeholder)
app.get('/api/sentiment/aaii', async (req, res) => {
  try {
    const result = await pool.query('SELECT * FROM sentiment_data WHERE source = $1 LIMIT 1', ['aaii']);
    res.json(result.rows[0] || { message: 'No AAII data available' });
  } catch (error) {
    res.json({ message: 'No AAII data available' });
  }
});

// Fear & Greed endpoint (placeholder)
app.get('/api/sentiment/fear-greed', async (req, res) => {
  try {
    const result = await pool.query('SELECT * FROM fear_greed_index ORDER BY date DESC LIMIT 1');
    res.json(result.rows[0] || { message: 'No Fear & Greed data available' });
  } catch (error) {
    res.json({ message: 'No Fear & Greed data available' });
  }
});

// Commodity endpoints
app.get('/api/commodities/categories', async (req, res) => {
  try {
    const result = await pool.query('SELECT * FROM commodity_categories ORDER BY category, symbol');
    res.json({
      success: true,
      data: result.rows
    });
  } catch (error) {
    res.status(500).json({ success: false, error: error.message });
  }
});

app.get('/api/commodities/prices', async (req, res) => {
  try {
    const limit = req.query.limit || 100;
    const result = await pool.query(
      'SELECT * FROM commodity_prices ORDER BY updated_at DESC LIMIT $1',
      [limit]
    );
    res.json({
      success: true,
      data: result.rows
    });
  } catch (error) {
    res.status(500).json({ success: false, error: error.message });
  }
});

app.get('/api/commodities/market-summary', async (req, res) => {
  try {
    const prices = await pool.query('SELECT COUNT(*) as count FROM commodity_prices');
    const history = await pool.query('SELECT COUNT(*) as count FROM commodity_price_history');
    const correlations = await pool.query('SELECT COUNT(*) as count FROM commodity_correlations');

    res.json({
      success: true,
      data: {
        totalCommodities: prices.rows[0].count,
        totalHistoricalRecords: history.rows[0].count,
        totalCorrelations: correlations.rows[0].count,
        lastUpdated: new Date().toISOString()
      }
    });
  } catch (error) {
    res.status(500).json({ success: false, error: error.message });
  }
});

app.get('/api/commodities/correlations', async (req, res) => {
  try {
    const minCorrelation = parseFloat(req.query.minCorrelation) || 0.5;
    const result = await pool.query(
      `SELECT * FROM commodity_correlations
       WHERE ABS(correlation_30d) >= $1 OR ABS(correlation_90d) >= $1 OR ABS(correlation_1y) >= $1
       ORDER BY correlation_1y DESC`,
      [minCorrelation]
    );
    res.json({
      success: true,
      data: {
        minCorrelation,
        correlations: result.rows
      }
    });
  } catch (error) {
    res.status(500).json({ success: false, error: error.message });
  }
});

app.get('/api/commodities/cot/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const result = await pool.query(
      'SELECT * FROM cot_data WHERE symbol = $1 ORDER BY report_date DESC LIMIT 10',
      [symbol]
    );
    res.json({
      success: true,
      data: result.rows
    });
  } catch (error) {
    res.status(500).json({ success: false, error: error.message });
  }
});

app.get('/api/commodities/seasonality/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const result = await pool.query(
      'SELECT * FROM commodity_seasonality WHERE symbol = $1 ORDER BY month',
      [symbol]
    );
    res.json({
      success: true,
      data: result.rows
    });
  } catch (error) {
    res.status(500).json({ success: false, error: error.message });
  }
});

// Serve static frontend files - must be after API routes
app.use(express.static(frontendPath, {
  index: 'index.html',
  setHeaders: (res, filePath) => {
    if (filePath.endsWith('.html')) {
      res.setHeader('Cache-Control', 'no-cache');
    }
  }
}));

// SPA fallback - serve index.html for all non-API routes
app.use((req, res) => {
  res.sendFile(path.join(frontendPath, 'index.html'));
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`✅ Server running on http://localhost:${PORT}`);
  console.log(`📊 API: http://localhost:${PORT}/api/`);
  console.log(`🌐 Frontend: http://localhost:${PORT}/`);
});
