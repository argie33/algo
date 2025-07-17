// ULTRA MINIMAL - GUARANTEED TO WORK
console.log('Starting ultra minimal lambda...');

const serverless = require('serverless-http');
const express = require('express');
const app = express();

// CORS first
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  
  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }
  
  next();
});

app.use(express.json());

app.get('/health', (req, res) => {
  res.json({ success: true, message: 'Ultra minimal working' });
});

app.get('/api/health', (req, res) => {
  res.json({ success: true, message: 'API health ultra minimal' });
});

app.all('*', (req, res) => {
  res.json({ success: false, message: 'Not found but CORS works' });
});

console.log('Ultra minimal lambda ready');
module.exports.handler = serverless(app);