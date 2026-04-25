#!/usr/bin/env node

// Set development mode to enable auth bypass and dev-friendly behavior
process.env.NODE_ENV = process.env.NODE_ENV || 'development';

require('dotenv').config({ path: require('path').join(__dirname, '.env.local') });

const express = require('express');
const cors = require('cors');
const path = require('path');

const app = express();
app.use(cors());
app.use(express.json());

const frontendPath = path.join(__dirname, 'webapp/frontend-admin/dist-admin');

console.log('🚀 Starting Stock Analysis API Server');
console.log(`📋 Environment: ${process.env.NODE_ENV}`);
console.log(`📍 Frontend path: ${frontendPath}`);

// ============================================================================
// HEALTH CHECK
// ============================================================================
app.get('/health', (req, res) => {
  res.json({
    success: true,
    status: 'ok',
    timestamp: new Date().toISOString(),
    environment: process.env.NODE_ENV,
    nodeVersion: process.version
  });
});

// ============================================================================
// API ROUTES - Mount all modular routers
// ============================================================================

const routeModules = [
  ['earnings', 'earnings'],
  ['health', 'health'],
  ['auth', 'auth'],
  ['user', 'user'],
  ['stocks', 'stocks'],
  ['portfolio', 'portfolio'],
  ['trades', 'trades'],
  ['manual-trades', 'manual-trades'],
  ['commodities', 'commodities'],
  ['market', 'market'],
  ['contact', 'contact'],
  ['community', 'community'],
  ['financials', 'financials'],
  ['optimization', 'optimization'],
  ['options', 'options'],
  ['strategies', 'strategies'],
  ['analysts', 'analysts'],
  ['signals', 'signals'],
  ['technicals', 'technicals'],
  ['metrics', 'metrics'],
  ['sentiment', 'sentiment'],
  ['industries', 'industries'],
  ['economic', 'economic'],
  ['scores', 'scores'],
  ['price', 'price'],
  ['sectors', 'sectors'],
  ['world-etfs', 'world-etfs']
];

let loadedRoutes = 0;
let failedRoutes = [];

routeModules.forEach(([moduleName, pathName]) => {
  try {
    const router = require(`./webapp/lambda/routes/${moduleName}`);
    app.use(`/api/${pathName}`, router);
    console.log(`✅ Mounted /api/${pathName}`);
    loadedRoutes++;
  } catch (error) {
    console.warn(`⚠️  Failed to load /api/${pathName}:`, error.message.split('\n')[0]);
    failedRoutes.push(pathName);
  }
});

console.log(`\n✨ API Routes Summary: ${loadedRoutes}/${routeModules.length} mounted successfully`);
if (failedRoutes.length > 0) {
  console.warn(`⚠️  Failed routes: ${failedRoutes.join(', ')}`);
}

// ============================================================================
// FALLBACK - Index of available routes
// ============================================================================
app.get('/api', (req, res) => {
  res.json({
    success: true,
    message: 'Stock Analysis API',
    environment: process.env.NODE_ENV,
    endpoints: {
      health: '/health',
      earnings: '/api/earnings',
      stocks: '/api/stocks',
      portfolio: '/api/portfolio',
      trades: '/api/trades',
      commodities: '/api/commodities',
      market: '/api/market',
      financials: '/api/financials',
      optimization: '/api/optimization',
      signals: '/api/signals',
      sentiment: '/api/sentiment',
      sectors: '/api/sectors',
      industries: '/api/industries',
      economic: '/api/economic',
      scores: '/api/scores',
      price: '/api/price',
      metrics: '/api/metrics',
      analysts: '/api/analysts'
    },
    timestamp: new Date().toISOString()
  });
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

// ============================================================================
// ERROR HANDLING
// ============================================================================
app.use((err, req, res, next) => {
  console.error('❌ Unhandled error:', err);
  res.status(500).json({
    success: false,
    error: 'Internal server error',
    message: process.env.NODE_ENV === 'development' ? err.message : undefined,
    timestamp: new Date().toISOString()
  });
});

// ============================================================================
// START SERVER
// ============================================================================
const PORT = process.env.PORT || 3001;
const server = app.listen(PORT, () => {
  console.log(`\n✅ Server running on http://localhost:${PORT}`);
  console.log(`📊 API: http://localhost:${PORT}/api/`);
  console.log(`🌐 Frontend: http://localhost:${PORT}/`);
  console.log(`💚 Health: http://localhost:${PORT}/health`);
  console.log(`\n🔐 Development mode: Auth bypassed for localhost`);
  console.log(`📝 All API responses include: { success, data/error, timestamp }\n`);
});

// Graceful shutdown
process.on('SIGTERM', () => {
  console.log('SIGTERM received, shutting down gracefully...');
  server.close(() => {
    console.log('Server closed');
    process.exit(0);
  });
});

process.on('SIGINT', () => {
  console.log('\nSIGINT received, shutting down gracefully...');
  server.close(() => {
    console.log('Server closed');
    process.exit(0);
  });
});
