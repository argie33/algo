// Emergency Lambda Handler - Minimal Dependencies
// Load environment variables first
require('dotenv').config();

const serverless = require('serverless-http');
const express = require('express');
const cors = require('cors');

const app = express();

// Emergency CORS configuration
const corsOptions = {
  origin: [
    'https://d1zb7knau41vl9.cloudfront.net',
    'http://localhost:3000',
    'http://localhost:5173'
  ],
  credentials: true,
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'HEAD', 'PATCH'],
  allowedHeaders: [
    'Content-Type', 
    'Authorization', 
    'X-Requested-With', 
    'X-Session-ID', 
    'Accept', 
    'Origin', 
    'Cache-Control', 
    'Pragma'
  ],
  exposedHeaders: ['Content-Length', 'Content-Type', 'X-Request-ID']
};

// Apply CORS globally
app.use(cors(corsOptions));
app.options('*', cors(corsOptions));

// Basic JSON middleware
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));

// Emergency health check endpoint
app.get('/health', (req, res) => {
  console.log('🏥 Emergency health check hit');
  res.json({
    success: true,
    message: 'Emergency Lambda is alive',
    timestamp: new Date().toISOString(),
    environment: process.env.NODE_ENV,
    version: 'emergency-1.0'
  });
});

// Emergency API health check
app.get('/api/health', (req, res) => {
  console.log('🏥 Emergency API health check hit');
  res.json({
    success: true,
    message: 'Emergency API is functional',
    timestamp: new Date().toISOString(),
    cors: 'enabled',
    endpoints: ['health', 'api/health'],
    environment_check: {
      DB_SECRET_ARN: !!process.env.DB_SECRET_ARN,
      DB_ENDPOINT: !!process.env.DB_ENDPOINT,
      API_KEY_ENCRYPTION_SECRET_ARN: !!process.env.API_KEY_ENCRYPTION_SECRET_ARN,
      NODE_ENV: process.env.NODE_ENV,
      AWS_REGION: process.env.AWS_REGION || process.env.WEBAPP_AWS_REGION
    }
  });
});

// Emergency catch-all route
app.use('*', (req, res) => {
  console.log(`🚨 Emergency catch-all: ${req.method} ${req.originalUrl}`);
  res.json({
    success: false,
    message: 'Emergency Lambda - Limited functionality',
    method: req.method,
    path: req.originalUrl,
    timestamp: new Date().toISOString(),
    note: 'Full Lambda functionality being restored'
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

// Export the serverless handler
module.exports.handler = serverless(app);

console.log('🚑 Emergency Lambda initialized - Minimal functionality active');