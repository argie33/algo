// Minimal Lambda for testing CORS - bypassing all route imports
const serverless = require('serverless-http');
const express = require('express');

const app = express();

// Trust proxy
app.set('trust proxy', true);

// Emergency CORS middleware first
app.use((req, res, next) => {
  console.log(`🆘 EMERGENCY CORS: ${req.method} ${req.path}`);
  
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH');
  res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, X-Session-ID, Accept, Origin');
  res.header('Access-Control-Allow-Credentials', 'true');
  
  if (req.method === 'OPTIONS') {
    console.log(`🆘 OPTIONS handled for ${req.path}`);
    res.status(200).end();
    return;
  }
  
  next();
});

// Simple test routes
app.get('/', (req, res) => {
  res.json({
    status: 'ok',
    message: 'Minimal Lambda working',
    timestamp: new Date().toISOString(),
    cors_test: 'CORS headers should be present'
  });
});

app.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    message: 'Health check working',
    timestamp: new Date().toISOString(),
    cors_test: 'CORS headers should be present'
  });
});

app.get('/api/health', (req, res) => {
  res.json({
    status: 'ok',
    message: 'API Health check working',
    timestamp: new Date().toISOString(),
    cors_test: 'CORS headers should be present'
  });
});

app.get('/cors-test', (req, res) => {
  res.json({
    message: 'CORS test endpoint working',
    origin: req.headers.origin || 'no-origin',
    timestamp: new Date().toISOString()
  });
});

// Export with simplified handler
module.exports.handler = serverless(app, {
  request: (request, event, context) => {
    console.log(`📥 Request: ${event.httpMethod} ${event.path}`);
  },
  response: (response, event, context) => {
    if (!response.headers) response.headers = {};
    response.headers['Access-Control-Allow-Origin'] = '*';
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS';
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization';
    console.log(`📤 Response: ${response.statusCode} with CORS`);
  }
});