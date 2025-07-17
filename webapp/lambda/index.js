// EMERGENCY CORS FIX - MINIMAL WORKING VERSION
console.log('🚀 CORS FIX LAMBDA STARTING...');

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

// Basic JSON middleware
app.use(express.json());

// Health endpoints
app.get('/health', (req, res) => {
  res.json({
    success: true,
    message: 'CORS fix is working',
    timestamp: new Date().toISOString()
  });
});

app.get('/api/health', (req, res) => {
  res.json({
    success: true,
    message: 'API health check with CORS working',
    timestamp: new Date().toISOString()
  });
});

// Handle all other routes
app.all('*', (req, res) => {
  res.json({
    success: false,
    message: 'Route not implemented, but CORS is working',
    path: req.path,
    method: req.method,
    timestamp: new Date().toISOString()
  });
});

// Error handler with CORS
app.use((error, req, res, next) => {
  console.error('Error:', error);
  
  // Ensure CORS headers even on error
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
  
  res.status(500).json({
    success: false,
    error: 'Internal Server Error',
    message: 'Error occurred but CORS headers are set',
    timestamp: new Date().toISOString()
  });
});

console.log('✅ CORS fix Lambda ready');
module.exports.handler = serverless(app);