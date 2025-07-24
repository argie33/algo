// Minimal Lambda handler to test CORS and basic functionality
const serverless = require('serverless-http');
const express = require('express');

const app = express();

// CORS middleware - MUST be first
app.use((req, res, next) => {
  console.log(`📡 ${req.method} ${req.path} - Origin: ${req.headers.origin}`);
  
  const origin = req.headers.origin;
  const allowedOrigins = [
    'https://d1zb7knau41vl9.cloudfront.net',
    'http://localhost:3000',
    'http://localhost:5173'
  ];
  
  if (!origin || allowedOrigins.includes(origin)) {
    res.header('Access-Control-Allow-Origin', origin || 'https://d1zb7knau41vl9.cloudfront.net');
  }
  
  res.header('Access-Control-Allow-Credentials', 'true');
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH');
  res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, X-Session-ID, Accept, Origin, Cache-Control, Pragma');
  res.header('Access-Control-Expose-Headers', 'Content-Length, Content-Type, X-Request-ID');
  
  if (req.method === 'OPTIONS') {
    console.log('🔧 CORS preflight handled');
    return res.status(200).end();
  }
  
  next();
});

app.use(express.json({ limit: '2mb' }));

// Test endpoints
app.get('/api/health', (req, res) => {
  res.json({
    success: true,
    status: 'healthy',
    timestamp: new Date().toISOString(),
    message: 'Minimal test handler working'
  });
});

app.get('/api/test', (req, res) => {
  res.json({
    success: true,
    message: 'Test endpoint working',
    cors: 'enabled',
    timestamp: new Date().toISOString()
  });
});

// Basic portfolio endpoint
app.get('/api/portfolio/holdings', (req, res) => {
  res.json({
    success: true,
    data: {
      holdings: [
        {
          symbol: 'AAPL',
          quantity: 10,
          marketValue: 1500,
          currentPrice: 150
        }
      ],
      accountType: req.query.accountType || 'paper',
      dataSource: 'test'
    },
    message: 'Test portfolio data'
  });
});

// Basic stocks endpoint  
app.get('/api/stocks', (req, res) => {
  const limit = parseInt(req.query.limit) || 10;
  const stocks = Array.from({ length: limit }, (_, i) => ({
    symbol: `TEST${i + 1}`,
    price: 100 + i,
    change: Math.random() * 10 - 5
  }));
  
  res.json({
    success: true,
    data: stocks,
    count: stocks.length,
    message: 'Test stocks data'
  });
});

// Basic metrics endpoint
app.get('/api/metrics', (req, res) => {
  res.json({
    success: true,
    data: {
      totalStocks: 100,
      marketCap: 50000000000,
      avgVolume: 1000000
    },
    message: 'Test metrics data'
  });
});

// Catch all for unhandled routes
app.use('*', (req, res) => {
  res.status(404).json({
    success: false,
    error: 'Endpoint not found',
    path: req.path,
    method: req.method,
    timestamp: new Date().toISOString()
  });
});

// Error handler
app.use((error, req, res, next) => {
  console.error('Error:', error);
  res.status(500).json({
    success: false,
    error: 'Internal server error',
    message: error.message,
    timestamp: new Date().toISOString()
  });
});

console.log('✅ Minimal test handler initialized');

// Export the handler for AWS Lambda
module.exports.handler = serverless(app);
module.exports.app = app;