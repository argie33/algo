// FINANCIAL DASHBOARD API - PARAMETER STORE ONLY VERSION
console.log('🚀 Financial Dashboard API Lambda starting - PARAMETER STORE ONLY...');

const serverless = require('serverless-http');
const express = require('express');
const { 
    globalErrorHandler, 
    asyncErrorHandler, 
    errorMonitoringMiddleware
} = require('./middleware/comprehensiveErrorMiddleware');

const app = express();

// Initialize enhanced error tracking
app.use(errorMonitoringMiddleware);

// Trust proxy configuration for AWS
app.set('trust proxy', (ip) => {
  return ip === '127.0.0.1' || 
         ip.startsWith('10.') || 
         ip.startsWith('172.') || 
         ip.startsWith('192.168.') ||
         ip.startsWith('169.254.') ||
         ip === '::1' || 
         ip.startsWith('fe80:');
});

// CORS middleware - must be first
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
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS, PATCH');
  res.header('Access-Control-Allow-Headers', 'Origin, X-Requested-With, Content-Type, Accept, Authorization, Cache-Control, x-request-id, x-use-enhanced-service');
  res.header('Access-Control-Max-Age', '86400');
  
  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }
  
  next();
});

// Request logging with enhanced tracking
app.use((req, res, next) => {
  const requestId = req.headers['x-request-id'] || 'req_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
  req.requestId = requestId;
  res.set('x-request-id', requestId);
  
  const startTime = Date.now();
  console.log(`🔍 [${requestId}] ${req.method} ${req.path} - API`);
  
  // Log response time on finish
  res.on('finish', () => {
    const duration = Date.now() - startTime;
    console.log(`✅ [${requestId}] ${res.statusCode} ${req.method} ${req.path} - ${duration}ms`);
  });
  
  next();
});

// middleware
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    service: 'Financial Dashboard API',
    version: '2.0',
    architecture: 'Parameter Store Only',
    timestamp: new Date().toISOString(),
    features: [
      'enhanced-api-keys',
      'user-aware-circuit-breaker', 
      'cloudwatch-monitoring',
      'intelligent-caching'
    ]
  });
});

// Root endpoint
app.get('/', (req, res) => {
  res.json({
    message: 'Financial Dashboard API',
    version: '2.0',
    architecture: 'Parameter Store Only',
    status: 'operational',
    timestamp: new Date().toISOString(),
    endpoints: {
      health: '/health',
      enhancedSettings: '/api/settings/enhanced/*',
      integratedSettings: '/api/settings/integrated/*',
      legacySettings: '/api/settings/*'
    }
  });
});

// Import routes with enhanced error handling
const asyncHandler = (fn) => (req, res, next) => {
  Promise.resolve(fn(req, res, next)).catch(next);
};

// API Key Service Routes (Primary)
try {
  const settingsV2Router = require('./routes/settings-v2');
  app.use('/api/settings/v2', asyncHandler(settingsV2Router));
  console.log('✅ settings routes loaded');
} catch (error) {
  console.error('❌ Failed to load enhanced settings routes:', error.message);
}

// Integration Layer Routes (Migration Support)
try {
  const hybridRouter = require('./routes/settings-hybrid');
  app.use('/api/settings/hybrid', asyncHandler(hybridRouter));
  console.log('✅ Integration routes loaded');
} catch (error) {
  console.error('❌ Failed to load integration routes:', error.message);
}

// Legacy Routes (Fallback)
try {
  const settingsRouter = require('./routes/settings');
  app.use('/api/settings', asyncHandler(settingsRouter));
  console.log('✅ Legacy settings routes loaded');
} catch (error) {
  console.error('❌ Failed to load legacy settings routes:', error.message);
}

// Other existing routes
const routeConfigs = [
  { path: '/api/portfolio', module: './routes/portfolio' },
  { path: '/api/stocks', module: './routes/stocks' },
  { path: '/api/trades', module: './routes/trades' },
  { path: '/api/health', module: './routes/health' }
];

routeConfigs.forEach(({ path, module }) => {
  try {
    const router = require(module);
    app.use(path, asyncHandler(router));
    console.log(`✅ Route ${path} loaded`);
  } catch (error) {
    console.warn(`⚠️ Route ${path} not available: ${error.message}`);
  }
});

// error handling middleware
app.use((error, req, res, next) => {
  const requestId = req.requestId || 'unknown';
  console.error(`❌ [${requestId}] API Error:`, {
    message: error.message,
    stack: error.stack,
    url: req.url,
    method: req.method,
    timestamp: new Date().toISOString()
  });

  // error response with service information
  const errorResponse = {
    success: false,
    error: 'Internal server error',
    message: process.env.NODE_ENV === 'development' ? error.message : 'An error occurred',
    requestId,
    service: 'Financial Dashboard API',
    version: '2.0',
    timestamp: new Date().toISOString()
  };

  // Circuit breaker specific errors
  if (error.message.includes('Circuit breaker is OPEN')) {
    errorResponse.error = 'Service temporarily unavailable';
    errorResponse.message = 'The service is experiencing high error rates and has been temporarily disabled';
    errorResponse.retryAfter = '30 seconds';
    return res.status(503).json(errorResponse);
  }

  // Parameter Store specific errors
  if (error.message.includes('ParameterNotFound')) {
    errorResponse.error = 'Resource not found';
    errorResponse.message = 'The requested resource was not found';
    return res.status(404).json(errorResponse);
  }

  // AWS permission errors
  if (error.message.includes('AccessDenied') || error.message.includes('UnauthorizedOperation')) {
    errorResponse.error = 'Access denied';
    errorResponse.message = 'Insufficient permissions to access the requested resource';
    return res.status(403).json(errorResponse);
  }

  res.status(500).json(errorResponse);
});

// 404 handler
app.use('*', (req, res) => {
  const requestId = req.requestId || 'unknown';
  res.status(404).json({
    success: false,
    error: 'Not found',
    message: `Endpoint ${req.method} ${req.originalUrl} not found`,
    requestId,
    service: 'Financial Dashboard API',
    version: '2.0',
    availableEndpoints: [
      '/health',
      '/api/settings/enhanced/*',
      '/api/settings/integrated/*', 
      '/api/settings/*'
    ],
    timestamp: new Date().toISOString()
  });
});

// Start server
const port = process.env.PORT || 3000;
if (process.env.NODE_ENV !== 'production') {
  app.listen(port, () => {
    console.log(`✅ Financial Dashboard API running on port ${port}`);
    console.log(`🏗️ Architecture: Parameter Store Only`);
    console.log(`📊 Features: Circuit Breaker, Caching, Monitoring`);
  });
}

// Lambda handler with better error handling
const handler = serverless(app, {
  request: (request, event, context) => {
    // Add AWS context to request
    request.awsEvent = event;
    request.awsContext = context;
    request.isLambda = true;
  },
  response: (response, event, context) => {
    // Add enhanced headers
    response.headers = {
      ...response.headers,
      'x-service-version': '2.0',
      'x-architecture': 'parameter-store-only',
      'x-aws-request-id': context.awsRequestId
    };
  }
});

module.exports.handler = handler;