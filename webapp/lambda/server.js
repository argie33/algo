// Load environment variables first
require('dotenv').config();

const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const morgan = require('morgan');
const { initializeDatabase } = require('./utils/database');
const errorHandler = require('./middleware/errorHandler');

// Import routes
const stockRoutes = require('./routes/stocks');
const metricsRoutes = require('./routes/metrics');
const healthRoutes = require('./routes/health');
const marketRoutes = require('./routes/market');
const analystRoutes = require('./routes/analysts');
const financialRoutes = require('./routes/financials');
const tradingRoutes = require('./routes/trading');
const technicalRoutes = require('./routes/technical');
const calendarRoutes = require('./routes/calendar');
const signalsRoutes = require('./routes/signals');
const dataRoutes = require('./routes/data');

const app = express();

// Security middleware
app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      styleSrc: ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],
      fontSrc: ["'self'", "https://fonts.gstatic.com"],
      imgSrc: ["'self'", "data:", "https:"],
      scriptSrc: ["'self'"],
      connectSrc: ["'self'"],
    },
  },
}));

// CORS configuration
app.use(cors({
  origin: true,
  credentials: true,
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization', 'x-api-key'],
}));

// Middleware
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));
app.use(morgan('combined'));

// Initialize database connection
initializeDatabase();

// Routes
app.use('/api/stocks', stockRoutes);
app.use('/api/metrics', metricsRoutes);
app.use('/api/health', healthRoutes);
app.use('/api/market', marketRoutes);
app.use('/api/analysts', analystRoutes);
app.use('/api/financials', financialRoutes);
app.use('/api/trading', tradingRoutes);
app.use('/api/technical', technicalRoutes);
app.use('/api/calendar', calendarRoutes);
app.use('/api/signals', signalsRoutes);
app.use('/api/data', dataRoutes);

// API info endpoint
app.get('/api', (req, res) => {
  res.json({
    name: 'LoadFundamentals API',
    version: '1.0.0',
    endpoints: {
      stocks: '/api/stocks',
      metrics: '/api/metrics', 
      health: '/api/health',
      market: '/api/market',
      analysts: '/api/analysts',
      financials: '/api/financials',
      trading: '/api/trading',
      technical: '/api/technical',
      calendar: '/api/calendar',
      signals: '/api/signals',
      data: '/api/data'
    },
    timestamp: new Date().toISOString()
  });
});

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({ 
    status: 'healthy',
    timestamp: new Date().toISOString(),
    environment: process.env.NODE_ENV || 'development'
  });
});

// 404 handler
app.use('*', (req, res) => {
  res.status(404).json({
    error: 'Route not found',
    path: req.originalUrl,
    timestamp: new Date().toISOString()
  });
});

// Error handler
app.use(errorHandler);

// Start server
const port = process.env.PORT || 3000;
app.listen(port, () => {
  console.log(`\n🚀 LoadFundamentals API Server running on port ${port}`);
  console.log(`📊 Health check: http://localhost:${port}/health`);
  console.log(`📈 Stocks API: http://localhost:${port}/api/stocks`);
  console.log(`🔍 API Info: http://localhost:${port}/api`);
  console.log(`⚡ Quick Overview: http://localhost:${port}/api/stocks/quick/overview`);
});

module.exports = app;
