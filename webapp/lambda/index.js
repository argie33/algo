// FIXED FINANCIAL DASHBOARD API - Proper route mounting with CORS
console.log('🚀 Financial Dashboard API Lambda starting - FIXED VERSION...');

const serverless = require('serverless-http');
const express = require('express');
const { corsWithTimeoutHandling } = require('./cors-fix');

const app = express();

// CRITICAL: CORS must be first and always work
app.use(corsWithTimeoutHandling());

// Basic middleware
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));

// AWS Production Configuration - This is running in AWS Lambda
// Force production settings since this is deployed via IaC
const isRunningInAWS = !!(process.env.AWS_LAMBDA_FUNCTION_NAME || process.env.AWS_EXECUTION_ENV);

if (isRunningInAWS) {
  // Force production settings for AWS deployment
  process.env.NODE_ENV = 'production';
  process.env.ALLOW_DEV_BYPASS = 'false';
  console.log('🚀 AWS Lambda detected - forcing production authentication mode');
} else {
  // Local development configuration
  process.env.NODE_ENV = process.env.NODE_ENV || 'development';
  process.env.ALLOW_DEV_BYPASS = process.env.ALLOW_DEV_BYPASS || 'true';
  console.log('🔧 Local development mode detected');
}

// Check if Cognito is properly configured (for debugging only)
const hasCognitoConfig = !!(
  process.env.COGNITO_USER_POOL_ID && 
  process.env.COGNITO_CLIENT_ID
) || !!(
  process.env.COGNITO_SECRET_ARN
);

if (!hasCognitoConfig) {
  console.warn('⚠️ Cognito environment variables not found - may need to be set via CloudFormation/IaC');
}

console.log(`🔒 Security Configuration: NODE_ENV=${process.env.NODE_ENV}, ALLOW_DEV_BYPASS=${process.env.ALLOW_DEV_BYPASS}`);

// Add request logging for debugging
app.use((req, res, next) => {
  console.log(`📡 ${req.method} ${req.path} - Origin: ${req.headers.origin}`);
  next();
});

// ============================================================================
// ROUTE MOUNTING - Load all existing routes with proper error handling
// ============================================================================

// Enhanced route loader with detailed error diagnostics
const safeRouteLoader = (routePath, routeName, mountPath) => {
  try {
    // First check if the route file exists
    const fs = require('fs');
    const path = require('path');
    const fullPath = path.resolve(__dirname, routePath + '.js');
    
    if (!fs.existsSync(fullPath)) {
      throw new Error(`Route file not found: ${fullPath}`);
    }
    
    // Try to load the route
    const route = require(routePath);
    
    if (!route || typeof route !== 'function') {
      throw new Error(`Invalid route export: expected Express router, got ${typeof route}`);
    }
    
    app.use(mountPath, route);
    console.log(`✅ ${routeName} route loaded successfully at ${mountPath}`);
    return true;
    
  } catch (error) {
    console.error(`❌ Failed to load ${routeName} route from ${routePath}:`, error.message);
    console.error(`📍 Error stack: ${error.stack}`);
    
    // Create diagnostic error endpoint instead of fallback
    const express = require('express');
    const router = express.Router();
    
    // Provide detailed error diagnostics for all requests
    router.all('*', (req, res) => {
      res.status(503).json({
        success: false,
        error: `${routeName} route failed to load`,
        diagnostics: {
          routeName: routeName,
          routePath: routePath,
          mountPath: mountPath,
          fullPath: path.resolve(__dirname, routePath + '.js'),
          errorType: error.name,
          errorMessage: error.message,
          errorStack: error.stack,
          fileExists: fs.existsSync(path.resolve(__dirname, routePath + '.js')),
          timestamp: new Date().toISOString(),
          method: req.method,
          requestPath: req.path,
          requestUrl: req.url
        },
        troubleshooting: {
          possibleCauses: [
            'Route file missing or moved',
            'Syntax error in route file',
            'Missing dependencies in route file',
            'Invalid Express router export',
            'File permission issues'
          ],
          nextSteps: [
            `Check if file exists: ${routePath}.js`,
            'Verify route file syntax',
            'Check route file dependencies',
            'Verify Express router export'
          ]
        },
        message: `Route ${routeName} is unavailable due to loading error. See diagnostics for details.`,
        timestamp: new Date().toISOString()
      });
    });
    
    app.use(mountPath, router);
    console.log(`🔍 ${routeName} diagnostic error route created at ${mountPath}`);
    
    return false;
  }
};


// ============================================================================
// CONSISTENT ROUTE LOADING - Organized by category and priority
// ============================================================================

// 1. CRITICAL SYSTEM ROUTES - Must load first
console.log('📋 Loading critical system routes...');
safeRouteLoader('./routes/health', 'Health', '/api/health');
safeRouteLoader('./routes/health', 'Health Direct', '/health');
safeRouteLoader('./routes/auth', 'Authentication', '/api/auth');
safeRouteLoader('./routes/user', 'User Management', '/api/user');

// 2. CORE BUSINESS ROUTES - Portfolio and market data
console.log('📈 Loading core business routes...');
safeRouteLoader('./routes/portfolio', 'Portfolio (Consolidated)', '/api/portfolio');
// NOTE: portfolio-alpaca-integration.js and portfolio-api-keys.js consolidated into portfolio.js
// Enhanced Alpaca integration now available at /api/portfolio/enhanced/* endpoints
// API key management now available at /api/portfolio/api-keys/* endpoints
safeRouteLoader('./routes/dashboard', 'Dashboard', '/api/dashboard');
safeRouteLoader('./routes/stocks', 'Stocks', '/api/stocks');
safeRouteLoader('./routes/market', 'Market Data (Consolidated)', '/api/market');
// NOTE: market-data.js has been consolidated into market.js
// Real-time data capabilities now available at /api/market/data/* endpoints

// 3. FINANCIAL DATA ROUTES - Analysis and metrics
console.log('💰 Loading financial data routes...');
safeRouteLoader('./routes/financials', 'Financials', '/api/financials');
safeRouteLoader('./routes/technical', 'Technical Analysis', '/api/technical');
safeRouteLoader('./routes/metrics', 'Metrics', '/api/metrics');
safeRouteLoader('./routes/sectors', 'Sectors', '/api/sectors');
safeRouteLoader('./routes/scores', 'Stock Scores', '/api/scores');
safeRouteLoader('./routes/scoring', 'Scoring System', '/api/scoring');

// 4. TRADING ROUTES - Trading and risk management
console.log('📊 Loading trading routes...');
safeRouteLoader('./routes/trading', 'Trading (Consolidated)', '/api/trading');
// NOTE: trading-strategies.js has been consolidated into trading.js
// Strategy management now available at /api/trading/strategies/* endpoints
safeRouteLoader('./routes/trades', 'Trade History', '/api/trades');
safeRouteLoader('./routes/risk', 'Risk Management (Consolidated)', '/api/risk');
// NOTE: risk-management.js has been consolidated into risk.js
// Enhanced risk management now available at /api/risk/management/* endpoints
safeRouteLoader('./routes/backtest', 'Backtesting', '/api/backtest');

// 5. ADVANCED FEATURES - AI, algorithms, optimization
console.log('🤖 Loading advanced feature routes...');
safeRouteLoader('./routes/ai-assistant', 'AI Assistant', '/api/ai-assistant');
safeRouteLoader('./routes/algorithmicTrading', 'Algorithmic Trading', '/api/algorithmic-trading');
safeRouteLoader('./routes/portfolioOptimization', 'Portfolio Optimization', '/api/portfolio/optimization');
safeRouteLoader('./routes/signals', 'Trading Signals', '/api/signals');
safeRouteLoader('./routes/patterns', 'Pattern Recognition', '/api/patterns');

// 6. MARKET DATA SOURCES - External data integration
console.log('🌐 Loading market data sources...');
safeRouteLoader('./routes/commodities', 'Commodities', '/api/commodities');
safeRouteLoader('./routes/economic', 'Economic Data', '/api/economic');
safeRouteLoader('./routes/news', 'News', '/api/news');
safeRouteLoader('./routes/calendar', 'Economic Calendar', '/api/calendar');
safeRouteLoader('./routes/sentiment', 'Market Sentiment', '/api/sentiment');

// 7. CRYPTO ROUTES - Cryptocurrency features
console.log('₿ Loading cryptocurrency routes...');
safeRouteLoader('./routes/crypto', 'Crypto Base', '/api/crypto');
safeRouteLoader('./routes/crypto-portfolio', 'Crypto Portfolio', '/api/crypto/portfolio');
safeRouteLoader('./routes/crypto-analytics', 'Crypto Analytics', '/api/crypto/analytics');
safeRouteLoader('./routes/crypto-signals', 'Crypto Signals', '/api/crypto/signals');
safeRouteLoader('./routes/crypto-risk', 'Crypto Risk', '/api/crypto/risk');

// 8. PERFORMANCE & MONITORING - System performance
console.log('⚡ Loading performance routes...');
safeRouteLoader('./routes/performance', 'Performance (Consolidated)', '/api/performance');
// NOTE: performance-analytics.js has been consolidated into performance.js
// Advanced analytics now available at /api/performance/analytics/* endpoints
safeRouteLoader('./routes/hftTrading', 'HFT Trading', '/api/hft');
safeRouteLoader('./routes/enhancedHftApi', 'Enhanced HFT API', '/api/hft/enhanced');

// 9. CONFIGURATION & SETTINGS - User preferences and system config
console.log('⚙️ Loading configuration routes...');
safeRouteLoader('./routes/settings', 'Settings (Consolidated)', '/api/settings');
// NOTE: settings-api-keys.js was redundant - API keys already managed in settings.js
// API key management available at /api/settings/api-keys/* endpoints
safeRouteLoader('./routes/configuration', 'Configuration', '/api/config');
safeRouteLoader('./routes/user-profile', 'User Profile', '/api/user-profile');

// 10. REAL-TIME DATA - Live feeds and WebSocket
console.log('📡 Loading real-time data routes...');
safeRouteLoader('./routes/liveData', 'Live Data', '/api/live-data');
safeRouteLoader('./routes/realTimeData', 'Real-Time Data', '/api/realtime');
safeRouteLoader('./routes/websocket', 'WebSocket', '/api/websocket');

// 11. ADMIN & DIAGNOSTIC ROUTES - Administrative functions
console.log('👨‍💼 Loading admin routes...');
safeRouteLoader('./routes/admin', 'Admin', '/api/admin');
safeRouteLoader('./routes/adminLiveData', 'Admin Live Data', '/admin/live-data');
safeRouteLoader('./routes/diagnostics', 'Diagnostics', '/api/diagnostics');
safeRouteLoader('./routes/emergency', 'Emergency Controls', '/api/emergency');

// 12. UTILITY ROUTES - Supporting features
console.log('🔧 Loading utility routes...');
safeRouteLoader('./routes/watchlist', 'Watchlist', '/api/watchlist');
safeRouteLoader('./routes/alerts', 'Alerts', '/api/alerts');
safeRouteLoader('./routes/screener', 'Stock Screener', '/api/screener');
safeRouteLoader('./routes/analysts', 'Analyst Ratings', '/api/analysts');
safeRouteLoader('./routes/data', 'Data Management', '/api/data');
safeRouteLoader('./routes/validation', 'Data Validation', '/api/validation');

console.log('✅ All routes loaded with consistent organization');

// ============================================================================
// DIAGNOSTIC ENDPOINTS - For debugging and system health
// ============================================================================

// Dashboard endpoint is now properly loaded from ./routes/dashboard.js

// Authentication configuration diagnostic endpoint
app.get('/api/auth-status', (req, res) => {
  const authConfig = {
    success: true,
    awsLambdaDetected: !!(process.env.AWS_LAMBDA_FUNCTION_NAME || process.env.AWS_EXECUTION_ENV),
    environment: {
      NODE_ENV: process.env.NODE_ENV,
      ALLOW_DEV_BYPASS: process.env.ALLOW_DEV_BYPASS
    },
    cognitoConfiguration: {
      hasUserPoolId: !!process.env.COGNITO_USER_POOL_ID,
      hasClientId: !!process.env.COGNITO_CLIENT_ID,
      hasSecretArn: !!process.env.COGNITO_SECRET_ARN,
      userPoolId: process.env.COGNITO_USER_POOL_ID ? 'us-east-1_***' : 'NOT_SET',
      clientId: process.env.COGNITO_CLIENT_ID ? '***configured***' : 'NOT_SET'
    },
    requiredLambdaEnvironmentVariables: {
      COGNITO_USER_POOL_ID: 'us-east-1_ZqooNeQtV (from frontend logs)',
      COGNITO_CLIENT_ID: '243r98prucoickch12djkahrhk (from frontend logs)',
      COGNITO_DOMAIN: 'https://financial-dashboard-dev-626216981288.auth.us-east-1.amazoncognito.com'
    },
    message: process.env.COGNITO_USER_POOL_ID ? 
      'Cognito properly configured' : 
      'MISSING: Lambda needs Cognito environment variables set in IaC deployment'
  };

  const statusCode = authConfig.cognitoConfiguration.hasUserPoolId ? 200 : 500;
  res.status(statusCode).json(authConfig);
});

// Root endpoint
app.get('/', (req, res) => {
  res.json({
    success: true,
    service: 'Financial Dashboard API',
    version: '1.0.0-fixed',
    status: 'operational',
    developmentMode: process.env.ALLOW_DEV_BYPASS === 'true',
    timestamp: new Date().toISOString(),
    availableEndpoints: [
      // Critical System
      '/api/health', '/api/auth', '/api/user',
      // Core Business  
      '/api/portfolio', '/api/dashboard', '/api/stocks', '/api/market',
      // Financial Data
      '/api/financials', '/api/technical', '/api/metrics', '/api/sectors', '/api/scores',
      // Trading
      '/api/trading', '/api/trades', '/api/risk', '/api/backtest',
      // Advanced Features
      '/api/ai-assistant', '/api/algorithmic-trading', '/api/signals',
      // Market Data
      '/api/commodities', '/api/economic', '/api/news', '/api/calendar',
      // Configuration
      '/api/settings', '/api/config',
      // Real-time & Admin
      '/api/live-data', '/api/hft', '/admin/live-data'
    ]
  });
});

// ============================================================================
// ADDITIONAL API ENDPOINTS
// ============================================================================

// Generic /api endpoint for frontend health checks and API discovery
app.get('/api', (req, res) => {
  res.json({
    success: true,
    service: 'Financial Dashboard API',
    version: '1.0.0-fixed',
    status: 'operational',
    message: 'API is healthy and operational',
    developmentMode: process.env.ALLOW_DEV_BYPASS === 'true',
    timestamp: new Date().toISOString(),
    availableEndpoints: [
      // Critical System Routes
      '/api/health', '/api/auth', '/api/user',
      // Core Business Routes  
      '/api/portfolio', '/api/dashboard', '/api/stocks', '/api/market',
      // Financial Data Routes
      '/api/financials', '/api/technical', '/api/metrics', '/api/sectors', '/api/scores', '/api/scoring',
      // Trading Routes (Consolidated)
      '/api/trading', '/api/trading/strategies/*', '/api/trades', '/api/risk', '/api/risk/management/*', '/api/backtest',
      // Advanced Features
      '/api/ai-assistant', '/api/algorithmic-trading', '/api/portfolio/optimization', '/api/signals', '/api/patterns',
      // Market Data Sources
      '/api/commodities', '/api/economic', '/api/news', '/api/calendar', '/api/sentiment',
      // Crypto Routes
      '/api/crypto', '/api/crypto/portfolio', '/api/crypto/analytics', '/api/crypto/signals', '/api/crypto/risk',
      // Performance & Monitoring (Consolidated)
      '/api/performance', '/api/performance/analytics/*', '/api/hft',
      // Configuration & Settings (Consolidated)
      '/api/settings', '/api/settings/api-keys/*', '/api/config', '/api/user-profile',
      // Real-time Data
      '/api/live-data', '/api/realtime', '/api/websocket',
      // Admin & Diagnostics
      '/api/admin', '/admin/live-data', '/api/diagnostics', '/api/emergency',
      // Utilities
      '/api/watchlist', '/api/alerts', '/api/screener', '/api/analysts', '/api/data', '/api/validation'
    ],
    documentation: {
      health: 'GET /api/health - System health check',
      portfolio: 'GET /api/portfolio/* - Portfolio management',
      stocks: 'GET /api/stocks/* - Stock data and information',
      financials: 'GET /api/financials/* - Financial statements and data',
      technical: 'GET /api/technical/* - Technical analysis and indicators',
      metrics: 'GET /api/metrics/* - Market metrics and analytics',
      sectors: 'GET /api/sectors/* - Sector analysis and data',
      apiKeys: 'GET /api/api-keys/* - API key management',
      market: 'GET /api/market/* - Market data and analysis',
      commodities: 'GET /api/commodities/* - Commodities market data and analysis',
      economic: 'GET /api/economic/* - Economic indicators and data',
      user: 'POST /api/user/* - User management and authentication',
      settings: 'GET /api/settings/* - Application settings',
      adminLiveData: 'GET /admin/live-data/* - Admin live data management'
    }
  });
});

// ============================================================================
// ERROR HANDLING
// ============================================================================

// 404 handler with CORS
app.use('*', (req, res) => {
  res.status(404).json({
    success: false,
    error: 'Endpoint not found',
    path: req.path,
    method: req.method,
    message: 'This endpoint is not available',
    timestamp: new Date().toISOString(),
    availableEndpoints: [
      '/api/health', '/api/portfolio', '/api/dashboard', '/api/stocks',
      '/api/trading', '/api/risk', '/api/settings', '/api/market',
      '/api/commodities', '/api/economic', '/api/hft', '/admin/live-data'
    ]
  });
});

// Global error handler with CORS
app.use((error, req, res, next) => {
  console.error('❌ Global error handler:', error);
  
  // Ensure CORS headers are present on errors
  if (!res.headersSent) {
    res.status(500).json({
      success: false,
      error: 'Internal server error',
      message: 'An unexpected error occurred',
      developmentMode: process.env.ALLOW_DEV_BYPASS === 'true',
      timestamp: new Date().toISOString()
    });
  }
});

// Lambda timeout handler
process.on('SIGTERM', () => {
  console.log('⏰ Lambda timeout signal received');
});

console.log('✅ Fixed Financial Dashboard API handler initialized');
console.log('📡 CORS enabled for CloudFront origin');
console.log('🔓 Development authentication bypass enabled');
console.log('🛣️ All routes properly mounted with error handling');

// Export for Lambda
module.exports.handler = serverless(app);
module.exports.app = app;