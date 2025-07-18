// Performance Monitoring Routes
// API endpoints for performance metrics, alerts, and optimization recommendations

const express = require('express');
const router = express.Router();
const PerformanceMonitoringService = require('../services/performanceMonitoringService');

// Initialize service
const performanceService = new PerformanceMonitoringService();

// Get performance dashboard
router.get('/dashboard', async (req, res) => {
  try {
    const dashboard = performanceService.getPerformanceDashboard();
    
    res.json({
      success: true,
      data: dashboard,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Performance dashboard failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get performance dashboard',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Record performance metric
router.post('/metrics', async (req, res) => {
  try {
    const { name, value, category = 'general', metadata = {} } = req.body;
    
    if (!name || value === undefined) {
      return res.status(400).json({
        success: false,
        error: 'Missing required fields',
        message: 'name and value are required'
      });
    }
    
    if (typeof value !== 'number') {
      return res.status(400).json({
        success: false,
        error: 'Invalid value type',
        message: 'value must be a number'
      });
    }
    
    const metric = performanceService.recordMetric(name, value, category, {
      ...metadata,
      source: 'api',
      userAgent: req.get('User-Agent'),
      endpoint: req.originalUrl
    });
    
    res.json({
      success: true,
      data: {
        metricId: metric.id,
        name: metric.name,
        value: metric.value,
        category: metric.category,
        timestamp: metric.timestamp
      },
      message: 'Performance metric recorded successfully',
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Metric recording failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to record performance metric',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get all alerts
router.get('/alerts', async (req, res) => {
  try {
    const { 
      severity, 
      status = 'all', 
      limit = 50, 
      acknowledged 
    } = req.query;
    
    let alerts = [...performanceService.alerts];
    
    // Filter by severity
    if (severity) {
      alerts = alerts.filter(alert => 
        alert.severity.toLowerCase() === severity.toLowerCase()
      );
    }
    
    // Filter by status
    if (status !== 'all') {
      alerts = alerts.filter(alert => 
        alert.status.toLowerCase() === status.toLowerCase()
      );
    }
    
    // Filter by acknowledgment
    if (acknowledged !== undefined) {
      const isAcknowledged = acknowledged === 'true';
      alerts = alerts.filter(alert => alert.acknowledged === isAcknowledged);
    }
    
    // Sort by most recent and limit
    alerts = alerts
      .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
      .slice(0, parseInt(limit));
    
    const summary = {
      total: alerts.length,
      critical: alerts.filter(a => a.severity === 'CRITICAL').length,
      warning: alerts.filter(a => a.severity === 'WARNING').length,
      active: alerts.filter(a => a.status === 'ACTIVE').length,
      acknowledged: alerts.filter(a => a.acknowledged).length
    };
    
    res.json({
      success: true,
      data: {
        alerts,
        summary,
        filters: { severity, status, acknowledged, limit }
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Alerts retrieval failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get alerts',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get optimization recommendations
router.get('/recommendations', async (req, res) => {
  try {
    const { 
      priority, 
      category, 
      implemented = 'false', 
      limit = 20 
    } = req.query;
    
    let recommendations = [...performanceService.recommendations];
    
    // Filter by implementation status
    const isImplemented = implemented === 'true';
    recommendations = recommendations.filter(rec => rec.implemented === isImplemented);
    
    // Filter by priority
    if (priority) {
      recommendations = recommendations.filter(rec => 
        rec.priority.toLowerCase() === priority.toLowerCase()
      );
    }
    
    // Filter by category
    if (category) {
      recommendations = recommendations.filter(rec => 
        rec.category.toLowerCase() === category.toLowerCase()
      );
    }
    
    // Sort by priority and timestamp
    const priorityOrder = { 'HIGH': 3, 'MEDIUM': 2, 'LOW': 1 };
    recommendations = recommendations
      .sort((a, b) => {
        const priorityDiff = priorityOrder[b.priority] - priorityOrder[a.priority];
        if (priorityDiff !== 0) return priorityDiff;
        return new Date(b.timestamp) - new Date(a.timestamp);
      })
      .slice(0, parseInt(limit));
    
    const summary = {
      total: recommendations.length,
      high: recommendations.filter(r => r.priority === 'HIGH').length,
      medium: recommendations.filter(r => r.priority === 'MEDIUM').length,
      low: recommendations.filter(r => r.priority === 'LOW').length
    };
    
    res.json({
      success: true,
      data: {
        recommendations,
        summary,
        filters: { priority, category, implemented, limit }
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Recommendations retrieval failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get recommendations',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Performance health check
router.get('/health', async (req, res) => {
  try {
    // Test performance monitoring functionality
    const testMetric = performanceService.recordMetric(
      'health_check_response_time', 
      Date.now() % 1000, 
      'api', 
      { test: true }
    );
    
    const dashboard = performanceService.getPerformanceDashboard();
    
    res.json({
      success: true,
      message: 'Performance monitoring services operational',
      services: {
        metricCollection: {
          status: testMetric ? 'operational' : 'error',
          totalMetrics: performanceService.metrics.size
        },
        alerting: {
          status: 'operational',
          totalAlerts: performanceService.alerts.length,
          activeAlerts: performanceService.alerts.filter(a => a.status === 'ACTIVE').length
        },
        recommendations: {
          status: 'operational',
          totalRecommendations: performanceService.recommendations.length,
          activeRecommendations: performanceService.recommendations.filter(r => !r.implemented).length
        },
        dashboard: {
          status: dashboard ? 'operational' : 'error',
          healthScore: dashboard.healthScore
        }
      },
      statistics: {
        metrics: performanceService.metrics.size,
        alerts: performanceService.alerts.length,
        recommendations: performanceService.recommendations.length,
        systemHealth: dashboard.summary.systemHealth
      },
      thresholds: performanceService.thresholds,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Performance monitoring health check failed:', error);
    res.status(503).json({
      success: false,
      error: 'Performance monitoring services unhealthy',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

module.exports = router;