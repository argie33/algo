// Minimal Lambda test to diagnose 502 errors
const express = require('express');
const serverless = require('serverless-http');

const app = express();

// Emergency CORS middleware
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  
  if (req.method === 'OPTIONS') {
    res.status(200).end();
    return;
  }
  next();
});

// Minimal test endpoint
app.get('/test-minimal', (req, res) => {
  res.json({
    status: 'ok',
    message: 'Minimal test working',
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

// Simple handler without complex wrapper
module.exports.handler = serverless(app);