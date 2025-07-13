// MINIMAL WORKING LAMBDA - Emergency CORS fix
const express = require('express');
const serverless = require('serverless-http');

const app = express();

// Trust proxy
app.set('trust proxy', true);

// CORS middleware - FIRST thing
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With');
  res.header('Access-Control-Allow-Credentials', 'true');
  
  console.log(`CORS set for ${req.method} ${req.path}`);
  
  if (req.method === 'OPTIONS') {
    res.status(200).end();
    return;
  }
  next();
});

// Basic routes
app.get('/', (req, res) => {
  res.json({
    status: 'ok',
    message: 'Minimal Lambda working',
    timestamp: new Date().toISOString()
  });
});

app.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    message: 'Health check working',
    timestamp: new Date().toISOString()
  });
});

app.get('/api/health', (req, res) => {
  res.json({
    status: 'ok',
    message: 'API Health working',
    timestamp: new Date().toISOString()
  });
});

// Settings endpoint (what your frontend is calling)
app.get('/settings/api-keys', (req, res) => {
  res.json({
    status: 'ok',
    message: 'API Keys endpoint working (mock data)',
    data: [],
    timestamp: new Date().toISOString()
  });
});

app.get('/api/settings/api-keys', (req, res) => {
  res.json({
    status: 'ok',
    message: 'API Settings endpoint working (mock data)',
    data: [],
    timestamp: new Date().toISOString()
  });
});

// Catch all
app.use('*', (req, res) => {
  res.json({
    status: 'ok',
    message: `Endpoint ${req.path} not implemented yet`,
    method: req.method,
    timestamp: new Date().toISOString()
  });
});

// Export handler
module.exports.handler = serverless(app);