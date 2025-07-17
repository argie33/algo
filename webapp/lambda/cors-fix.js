// Emergency CORS fix that can be deployed immediately
const serverless = require('serverless-http');
const express = require('express');
const app = express();

// CORS middleware that works for ALL requests
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
    return res.status(200).end();
  }
  
  next();
});

// Simple health endpoint
app.get('/health', (req, res) => {
  res.json({
    success: true,
    message: 'CORS fix is working',
    timestamp: new Date().toISOString()
  });
});

// Handle all other routes with CORS
app.all('*', (req, res) => {
  res.json({
    success: false,
    message: 'Route not implemented, but CORS is working',
    path: req.path,
    method: req.method,
    timestamp: new Date().toISOString()
  });
});

module.exports.handler = serverless(app);