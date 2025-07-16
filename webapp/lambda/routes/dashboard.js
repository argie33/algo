const express = require('express');
const { success, error } = require('../utils/responseFormatter');

const router = express.Router();

// Basic health endpoint for dashboard service
router.get('/health', (req, res) => {
  res.json(success({
    status: 'operational',
    service: 'dashboard',
    timestamp: new Date().toISOString(),
    message: 'Dashboard service is running'
  }));
});

// Dashboard overview endpoint
router.get('/overview', (req, res) => {
  const dashboardData = {
    summary: {
      totalValue: 125000,
      dayChange: 2.34,
      dayChangePercent: 1.87,
      totalGainLoss: 15000,
      totalGainLossPercent: 13.6
    },
    quickStats: {
      positions: 12,
      watchlistItems: 25,
      alerts: 3,
      lastUpdate: new Date().toISOString()
    },
    status: 'operational'
  };

  res.json(success(dashboardData));
});

// Dashboard widgets endpoint
router.get('/widgets', (req, res) => {
  const widgets = [
    { id: 'portfolio', type: 'portfolio-summary', enabled: true },
    { id: 'watchlist', type: 'watchlist-preview', enabled: true },
    { id: 'news', type: 'market-news', enabled: true },
    { id: 'performance', type: 'performance-chart', enabled: true }
  ];

  res.json(success(widgets));
});

module.exports = router;