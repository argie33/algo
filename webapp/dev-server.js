const express = require('express');
const cors = require('cors');

const app = express();
const PORT = 3001;

// Middleware
app.use(cors({
  origin: ['http://localhost:3000', 'http://127.0.0.1:3000'],
  credentials: true
}));

app.use(express.json());

// Health check
app.get('/health', (req, res) => {
  res.json({ 
    status: 'healthy',
    timestamp: new Date().toISOString(),
    environment: 'development',
    service: 'Financial Dashboard API',
    version: '1.0.0'
  });
});

// Mock endpoints
app.get('/api/stocks', (req, res) => {
  res.json({
    success: true,
    data: [
      { symbol: 'AAPL', name: 'Apple Inc.', price: 150.00 },
      { symbol: 'GOOGL', name: 'Alphabet Inc.', price: 2800.00 },
      { symbol: 'MSFT', name: 'Microsoft Corporation', price: 300.00 }
    ]
  });
});

app.get('/api/market', (req, res) => {
  res.json({
    success: true,
    data: {
      sp500: { value: 4500, change: 25.5, changePercent: 0.57 },
      nasdaq: { value: 14000, change: -50.2, changePercent: -0.36 },
      dow: { value: 35000, change: 100.0, changePercent: 0.29 }
    }
  });
});

app.get('/', (req, res) => {
  res.json({
    message: 'Financial Dashboard API - Development Server',
    version: '1.0.0',
    status: 'operational',
    timestamp: new Date().toISOString(),
    environment: 'development'
  });
});

app.listen(PORT, () => {
  console.log(`🚀 Development API server running on http://localhost:${PORT}`);
  console.log(`📊 Health check: http://localhost:${PORT}/health`);
}); 