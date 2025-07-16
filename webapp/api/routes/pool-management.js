const express = require('express');
const { getPoolStatus } = require('../utils/database');
const responseFormatter = require('../utils/responseFormatter');

const router = express.Router();

/**
 * Database Connection Pool Management API
 * 
 * Provides endpoints for monitoring and managing database connection pool
 * to handle concurrent users efficiently.
 */

/**
 * Get detailed pool status and metrics
 */
router.get('/status', async (req, res) => {
  try {
    const status = getPoolStatus();
    
    if (!status.initialized) {
      return res.status(503).json(responseFormatter.createErrorResponse('Database not initialized'));
    }

    // Add human-readable status
    const enhancedStatus = {
      ...status,
      health: getPoolHealth(status),
      recommendations: getPoolRecommendations(status),
      summary: {
        status: status.metrics.utilizationPercent > 90 ? 'critical' : 
                status.metrics.utilizationPercent > 70 ? 'warning' : 'healthy',
        message: getPoolStatusMessage(status)
      }
    };

    res.json(responseFormatter.createSuccessResponse(enhancedStatus));

  } catch (error) {
    console.error('Pool status error:', error);
    res.status(500).json(responseFormatter.createErrorResponse('Failed to get pool status'));
  }
});

/**
 * Get pool metrics for monitoring dashboard
 */
router.get('/metrics', async (req, res) => {
  try {
    const status = getPoolStatus();
    
    if (!status.initialized) {
      return res.status(503).json(responseFormatter.createErrorResponse('Database not initialized'));
    }

    // Return simplified metrics for monitoring
    const metrics = {
      utilization: {
        current: status.totalCount,
        max: status.max,
        percentage: status.metrics.utilizationPercent,
        waiting: status.waitingCount
      },
      performance: {
        acquiresPerSecond: status.metrics.acquiresPerSecond,
        errorRate: status.metrics.errorRate,
        uptimeSeconds: status.metrics.uptimeSeconds
      },
      scaling: {
        peakConnections: status.metrics.peakConnections,
        suggestions: status.recommendations
      },
      timestamp: new Date().toISOString()
    };

    res.json(responseFormatter.createSuccessResponse(metrics));

  } catch (error) {
    console.error('Pool metrics error:', error);
    res.status(500).json(responseFormatter.createErrorResponse('Failed to get pool metrics'));
  }
});

/**
 * Get scaling recommendations
 */
router.get('/recommendations', async (req, res) => {
  try {
    const status = getPoolStatus();
    
    if (!status.initialized) {
      return res.status(503).json(responseFormatter.createErrorResponse('Database not initialized'));
    }

    const recommendations = {
      current: {
        min: status.min,
        max: status.max,
        utilization: status.metrics.utilizationPercent
      },
      suggested: status.recommendations,
      rationale: getScalingRationale(status),
      priority: getRecommendationPriority(status)
    };

    res.json(responseFormatter.createSuccessResponse(recommendations));

  } catch (error) {
    console.error('Pool recommendations error:', error);
    res.status(500).json(responseFormatter.createErrorResponse('Failed to get recommendations'));
  }
});

/**
 * Health check specifically for pool management
 */
router.get('/health', async (req, res) => {
  try {
    const status = getPoolStatus();
    
    const health = {
      status: status.initialized ? 'healthy' : 'unhealthy',
      checks: {
        initialized: status.initialized,
        hasConnections: status.totalCount > 0,
        lowUtilization: status.metrics.utilizationPercent < 90,
        lowErrorRate: status.metrics.errorRate < 0.1,
        noWaiting: status.waitingCount < 5
      }
    };

    // Determine overall health
    const healthyChecks = Object.values(health.checks).filter(Boolean).length;
    const totalChecks = Object.keys(health.checks).length;
    
    if (healthyChecks === totalChecks) {
      health.status = 'healthy';
    } else if (healthyChecks >= totalChecks * 0.7) {
      health.status = 'degraded';
    } else {
      health.status = 'unhealthy';
    }

    const statusCode = health.status === 'healthy' ? 200 : 
                      health.status === 'degraded' ? 206 : 503;

    res.status(statusCode).json(responseFormatter.createSuccessResponse(health));

  } catch (error) {
    console.error('Pool health error:', error);
    res.status(503).json(responseFormatter.createErrorResponse('Pool health check failed'));
  }
});

// Helper functions

function getPoolHealth(status) {
  const { metrics } = status;
  
  return {
    overall: metrics.utilizationPercent < 80 && metrics.errorRate < 0.05 ? 'good' : 
             metrics.utilizationPercent < 95 && metrics.errorRate < 0.1 ? 'fair' : 'poor',
    utilization: metrics.utilizationPercent < 70 ? 'optimal' : 
                 metrics.utilizationPercent < 90 ? 'high' : 'critical',
    errorRate: metrics.errorRate < 0.01 ? 'excellent' : 
               metrics.errorRate < 0.05 ? 'good' : 
               metrics.errorRate < 0.1 ? 'fair' : 'poor',
    throughput: metrics.acquiresPerSecond > 1 ? 'high' : 
                metrics.acquiresPerSecond > 0.1 ? 'moderate' : 'low'
  };
}

function getPoolRecommendations(status) {
  const recommendations = [];
  const { metrics } = status;

  if (metrics.utilizationPercent > 90) {
    recommendations.push({
      type: 'scale_up',
      priority: 'high',
      action: 'Increase max pool size',
      reason: 'Pool utilization critically high'
    });
  }

  if (status.waitingCount > 5) {
    recommendations.push({
      type: 'scale_up',
      priority: 'medium',
      action: 'Increase pool size or optimize queries',
      reason: 'Too many connections waiting'
    });
  }

  if (metrics.errorRate > 0.1) {
    recommendations.push({
      type: 'investigate',
      priority: 'high',
      action: 'Investigate connection errors',
      reason: 'High error rate detected'
    });
  }

  if (metrics.utilizationPercent < 30 && status.max > 5) {
    recommendations.push({
      type: 'scale_down',
      priority: 'low',
      action: 'Consider reducing pool size',
      reason: 'Low utilization detected'
    });
  }

  return recommendations;
}

function getPoolStatusMessage(status) {
  const { metrics } = status;
  
  if (metrics.utilizationPercent > 95) {
    return 'Pool at maximum capacity - immediate scaling required';
  } else if (metrics.utilizationPercent > 80) {
    return 'Pool utilization high - consider scaling up';
  } else if (status.waitingCount > 10) {
    return 'Many connections waiting - pool may be undersized';
  } else if (metrics.errorRate > 0.1) {
    return 'High error rate - investigate connection issues';
  } else if (metrics.utilizationPercent < 20) {
    return 'Pool utilization low - running efficiently';
  } else {
    return 'Pool operating normally';
  }
}

function getScalingRationale(status) {
  const { metrics, recommendations } = status;
  
  return {
    currentLoad: `${metrics.utilizationPercent}% utilization with ${status.waitingCount} waiting`,
    trend: metrics.acquiresPerSecond > metrics.releaseRate ? 'increasing' : 'stable',
    bottlenecks: [
      ...(metrics.utilizationPercent > 80 ? ['High utilization'] : []),
      ...(status.waitingCount > 5 ? ['Connection queue'] : []),
      ...(metrics.errorRate > 0.05 ? ['Connection errors'] : [])
    ],
    benefits: recommendations.reason || 'Maintain current configuration'
  };
}

function getRecommendationPriority(status) {
  const { metrics } = status;
  
  if (metrics.utilizationPercent > 95 || status.waitingCount > 20) {
    return 'urgent';
  } else if (metrics.utilizationPercent > 80 || status.waitingCount > 10) {
    return 'high';
  } else if (metrics.utilizationPercent > 70 || metrics.errorRate > 0.05) {
    return 'medium';
  } else {
    return 'low';
  }
}

module.exports = router;