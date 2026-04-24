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

// ============================================================================
// UNIFIED RESPONSE FORMAT
// ============================================================================
// ALL endpoints return: { success: true/false, data: [...], timestamp: "...", error?: "..." }
// This ensures consistency across the entire API
// ============================================================================

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
    error: error.message || String(error),
    timestamp: new Date().toISOString()
  });
};

// ============================================================================
// HEALTH CHECK
// ============================================================================
app.get('/health', async (req, res) => {
  try {
    const result = await pool.query('SELECT NOW()');
    sendSuccess(res, { status: 'ok', timestamp: result.rows[0].now });
  } catch (error) {
    sendError(res, error);
  }
});

// ============================================================================
// STOCKS ENDPOINTS
// ============================================================================
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

app.get('/api/prices-count', async (req, res) => {
  try {
    const result = await pool.query('SELECT COUNT(*) as count FROM price_daily');
    sendSuccess(res, result.rows[0]);
  } catch (error) {
    sendError(res, error);
  }
});

// ============================================================================
// METRICS ENDPOINTS
// ============================================================================
app.get('/api/key-metrics/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const result = await pool.query('SELECT * FROM key_metrics WHERE symbol = $1', [symbol]);
    sendSuccess(res, result.rows[0] || {});
  } catch (error) {
    sendError(res, error);
  }
});

app.get('/api/stock-scores', async (req, res) => {
  try {
    const result = await pool.query('SELECT * FROM stock_scores ORDER BY composite_score DESC LIMIT 100');
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

app.get('/api/quality-metrics/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const result = await pool.query('SELECT * FROM quality_metrics WHERE symbol = $1', [symbol]);
    sendSuccess(res, result.rows[0] || {});
  } catch (error) {
    sendError(res, error);
  }
});

app.get('/api/growth-metrics/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const result = await pool.query('SELECT * FROM growth_metrics WHERE symbol = $1', [symbol]);
    sendSuccess(res, result.rows[0] || {});
  } catch (error) {
    sendError(res, error);
  }
});

app.get('/api/value-metrics/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const result = await pool.query('SELECT * FROM value_metrics WHERE symbol = $1', [symbol]);
    sendSuccess(res, result.rows[0] || {});
  } catch (error) {
    sendError(res, error);
  }
});

app.get('/api/stability-metrics/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const result = await pool.query('SELECT * FROM stability_metrics WHERE symbol = $1 ORDER BY date DESC LIMIT 1', [symbol]);
    sendSuccess(res, result.rows[0] || {});
  } catch (error) {
    sendError(res, error);
  }
});

app.get('/api/momentum-metrics/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const result = await pool.query('SELECT * FROM momentum_metrics WHERE symbol = $1 ORDER BY date DESC LIMIT 1', [symbol]);
    sendSuccess(res, result.rows[0] || {});
  } catch (error) {
    sendError(res, error);
  }
});

// ============================================================================
// TRADING SIGNALS ENDPOINTS
// ============================================================================
app.get('/api/signals/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const result = await pool.query(
      'SELECT * FROM buy_sell_daily WHERE symbol = $1 ORDER BY date DESC LIMIT 10',
      [symbol]
    );
    sendSuccess(res, result.rows);
  } catch (error) {
    sendError(res, error);
  }
});

// ============================================================================
// TOP/BOTTOM STOCKS
// ============================================================================
app.get('/api/top-stocks', async (req, res) => {
  try {
    const limit = req.query.limit || 50;
    const result = await pool.query(
      'SELECT * FROM stock_scores ORDER BY composite_score DESC LIMIT $1',
      [limit]
    );
    sendSuccess(res, result.rows);
  } catch (error) {
    sendError(res, error);
  }
});

app.get('/api/bottom-stocks', async (req, res) => {
  try {
    const limit = req.query.limit || 50;
    const result = await pool.query(
      'SELECT * FROM stock_scores ORDER BY composite_score ASC LIMIT $1',
      [limit]
    );
    sendSuccess(res, result.rows);
  } catch (error) {
    sendError(res, error);
  }
});

// ============================================================================
// MARKET SUMMARY
// ============================================================================
app.get('/api/market/summary', async (req, res) => {
  try {
    const stocks = await pool.query('SELECT COUNT(*) as count FROM stock_symbols');
    const prices = await pool.query('SELECT COUNT(*) as count FROM price_daily');
    const scores = await pool.query('SELECT COUNT(*) as count FROM stock_scores');

    sendSuccess(res, {
      totalStocks: stocks.rows[0].count,
      totalPrices: prices.rows[0].count,
      totalScores: scores.rows[0].count
    });
  } catch (error) {
    sendError(res, error);
  }
});

// ============================================================================
// SENTIMENT ENDPOINTS
// ============================================================================
app.get('/api/sentiment/aaii', async (req, res) => {
  try {
    const result = await pool.query('SELECT * FROM sentiment_data WHERE source = $1 LIMIT 1', ['aaii']);
    sendSuccess(res, result.rows[0] || { message: 'No AAII data available' });
  } catch (error) {
    sendSuccess(res, { message: 'No AAII data available' });
  }
});

app.get('/api/sentiment/fear-greed', async (req, res) => {
  try {
    const result = await pool.query('SELECT * FROM fear_greed_index ORDER BY date DESC LIMIT 1');
    sendSuccess(res, result.rows[0] || { message: 'No Fear & Greed data available' });
  } catch (error) {
    sendSuccess(res, { message: 'No Fear & Greed data available' });
  }
});

// ============================================================================
// COMMODITIES ENDPOINTS
// ============================================================================
app.get('/api/commodities/categories', async (req, res) => {
  try {
    const result = await pool.query('SELECT * FROM commodity_categories ORDER BY category, symbol');
    sendSuccess(res, result.rows);
  } catch (error) {
    sendError(res, error);
  }
});

app.get('/api/commodities/prices', async (req, res) => {
  try {
    const limit = req.query.limit || 100;
    const result = await pool.query(
      'SELECT * FROM commodity_prices ORDER BY updated_at DESC LIMIT $1',
      [limit]
    );
    sendSuccess(res, result.rows);
  } catch (error) {
    sendError(res, error);
  }
});

app.get('/api/commodities/market-summary', async (req, res) => {
  try {
    const prices = await pool.query('SELECT COUNT(*) as count FROM commodity_prices');
    const history = await pool.query('SELECT COUNT(*) as count FROM commodity_price_history');
    const correlations = await pool.query('SELECT COUNT(*) as count FROM commodity_correlations');

    sendSuccess(res, {
      totalCommodities: prices.rows[0].count,
      totalHistoricalRecords: history.rows[0].count,
      totalCorrelations: correlations.rows[0].count
    });
  } catch (error) {
    sendError(res, error);
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
    sendSuccess(res, result.rows);
  } catch (error) {
    sendError(res, error);
  }
});

app.get('/api/commodities/cot/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const result = await pool.query(
      'SELECT * FROM cot_data WHERE symbol = $1 ORDER BY report_date DESC LIMIT 10',
      [symbol]
    );
    sendSuccess(res, result.rows);
  } catch (error) {
    sendError(res, error);
  }
});

app.get('/api/commodities/seasonality/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const result = await pool.query(
      'SELECT * FROM commodity_seasonality WHERE symbol = $1 ORDER BY month',
      [symbol]
    );
    sendSuccess(res, result.rows);
  } catch (error) {
    sendError(res, error);
  }
});

// ============================================================================
// STATIC FILES & SPA FALLBACK
// ============================================================================
app.use(express.static(frontendPath, {
  index: 'index.html',
  setHeaders: (res, filePath) => {
    if (filePath.endsWith('.html')) {
      res.setHeader('Cache-Control', 'no-cache');
    }
  }
}));

app.use((req, res) => {
  res.sendFile(path.join(frontendPath, 'index.html'));
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`✅ Server running on http://localhost:${PORT}`);
  console.log(`📊 API: http://localhost:${PORT}/api/`);
  console.log(`🌐 Frontend: http://localhost:${PORT}/`);
  console.log(`\nUNIFIED RESPONSE FORMAT:`);
  console.log(`  All endpoints return: { success: true/false, data: [...], timestamp: "..." }`);
});
