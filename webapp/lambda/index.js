// EMERGENCY MINIMAL LAMBDA - CRITICAL SYSTEM RESTORE
console.log('🆘 EMERGENCY MINIMAL LAMBDA STARTING...');

const serverless = require('serverless-http');
const express = require('express');

const app = express();

console.log('✅ Express app created');

// CRITICAL: CORS must work immediately
app.use((req, res, next) => {
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
    console.log('🔧 CORS preflight for:', req.path);
    return res.status(200).end();
  }
  
  console.log(`📡 ${req.method} ${req.path}`);
  next();
});

console.log('✅ CORS configured');

// Basic middleware
app.use(express.json({ limit: '1mb' }));
app.use(express.urlencoded({ extended: true, limit: '1mb' }));

console.log('✅ Basic middleware configured');

// EMERGENCY HEALTH ENDPOINTS
app.get('/', (req, res) => {
  console.log('🏠 Root endpoint hit');
  res.json({
    success: true,
    message: 'EMERGENCY Lambda is alive',
    timestamp: new Date().toISOString(),
    version: 'emergency-minimal-1.0',
    status: 'responding'
  });
});

app.get('/health', (req, res) => {
  console.log('🏥 Health endpoint hit');
  res.json({
    success: true,
    message: 'EMERGENCY health check passed',
    timestamp: new Date().toISOString(),
    environment: process.env.NODE_ENV || 'unknown',
    lambda_info: {
      function_name: process.env.AWS_LAMBDA_FUNCTION_NAME,
      function_version: process.env.AWS_LAMBDA_FUNCTION_VERSION,
      memory_size: process.env.AWS_LAMBDA_FUNCTION_MEMORY_SIZE
    }
  });
});

app.get('/api/health', (req, res) => {
  console.log('🏥 API Health endpoint hit');
  res.json({
    success: true,
    message: 'EMERGENCY API health check passed',
    timestamp: new Date().toISOString(),
    environment_vars: {
      NODE_ENV: process.env.NODE_ENV,
      AWS_REGION: process.env.AWS_REGION || process.env.WEBAPP_AWS_REGION,
      DB_SECRET_ARN: !!process.env.DB_SECRET_ARN ? 'SET' : 'MISSING',
      DB_ENDPOINT: !!process.env.DB_ENDPOINT ? 'SET' : 'MISSING',
      API_KEY_ENCRYPTION_SECRET_ARN: !!process.env.API_KEY_ENCRYPTION_SECRET_ARN ? 'SET' : 'MISSING'
    }
  });
});

app.get('/emergency-health', (req, res) => {
  console.log('🆘 Emergency health endpoint hit');
  res.json({
    success: true,
    message: 'EMERGENCY Lambda responding successfully',
    timestamp: new Date().toISOString(),
    emergency_status: 'OPERATIONAL',
    all_environment_vars: Object.keys(process.env).filter(key => 
      !key.includes('SECRET') && !key.includes('PASSWORD')
    ).reduce((acc, key) => {
      acc[key] = process.env[key];
      return acc;
    }, {}),
    missing_critical_vars: [
      !process.env.DB_SECRET_ARN && 'DB_SECRET_ARN',
      !process.env.DB_ENDPOINT && 'DB_ENDPOINT', 
      !process.env.API_KEY_ENCRYPTION_SECRET_ARN && 'API_KEY_ENCRYPTION_SECRET_ARN'
    ].filter(Boolean)
  });
});

// Debug endpoints for troubleshooting
app.get('/debug', (req, res) => {
  console.log('🔍 Debug endpoint hit');
  res.json({
    success: true,
    message: 'Debug endpoint - Lambda is functional',
    request_info: {
      method: req.method,
      path: req.path,
      originalUrl: req.originalUrl,
      headers: req.headers,
      query: req.query
    },
    timestamp: new Date().toISOString()
  });
});

// Catch-all for other requests
app.use('*', (req, res) => {
  console.log(`🔍 Catch-all: ${req.method} ${req.originalUrl}`);
  res.json({
    success: false,
    message: 'EMERGENCY Lambda - Limited functionality',
    method: req.method,
    path: req.originalUrl,
    timestamp: new Date().toISOString(),
    note: 'This is an emergency Lambda with minimal endpoints. Full functionality being restored.'
  });
});

// Global error handler
app.use((error, req, res, next) => {
  console.error('🚨 Emergency Lambda Error:', error);
  res.status(500).json({
    success: false,
    error: 'Emergency Lambda Error',
    message: error.message,
    timestamp: new Date().toISOString()
  });
});

console.log('✅ EMERGENCY Lambda fully configured and ready');

// Export the handler
module.exports.handler = serverless(app);

console.log('✅ Handler exported successfully');