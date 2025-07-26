/**
 * Database Optimization API Routes
 * Provides endpoints for database performance analysis and optimization
 */

const express = require('express');
const { authenticateToken } = require('../middleware/auth');
const { createValidationMiddleware, sanitizers } = require('../middleware/validation');
const { DatabaseOptimizer } = require('../utils/databaseOptimizer');
const crypto = require('crypto');

const router = express.Router();

// Apply authentication to all routes (admin-level functionality)
router.use(authenticateToken);

// Validation schemas
const optimizationValidationSchemas = {
  analysis: {
    includeSlowQueries: {
      type: 'boolean',
      sanitizer: (value) => sanitizers.boolean(value, { defaultValue: true }),
      validator: (value) => typeof value === 'boolean',
      errorMessage: 'includeSlowQueries must be true or false'
    },
    includeIndexAnalysis: {
      type: 'boolean',
      sanitizer: (value) => sanitizers.boolean(value, { defaultValue: true }),
      validator: (value) => typeof value === 'boolean',
      errorMessage: 'includeIndexAnalysis must be true or false'
    },
    includeTableStats: {
      type: 'boolean',
      sanitizer: (value) => sanitizers.boolean(value, { defaultValue: true }),
      validator: (value) => typeof value === 'boolean',
      errorMessage: 'includeTableStats must be true or false'
    }
  },

  optimize: {
    dryRun: {
      type: 'boolean',
      sanitizer: (value) => sanitizers.boolean(value, { defaultValue: true }),
      validator: (value) => typeof value === 'boolean',
      errorMessage: 'dryRun must be true or false'
    },
    maxIndexes: {
      type: 'integer',
      sanitizer: (value) => sanitizers.integer(value, { min: 1, max: 20, defaultValue: 5 }),
      validator: (value) => value >= 1 && value <= 20,
      errorMessage: 'maxIndexes must be between 1 and 20'
    },
    applyRecommendations: {
      type: 'array',
      validator: (value) => Array.isArray(value) && value.every(id => typeof id === 'string'),
      errorMessage: 'applyRecommendations must be an array of recommendation IDs'
    }
  }
};

/**
 * Analyze database performance
 */
router.post('/analyze', createValidationMiddleware(optimizationValidationSchemas.analysis), async (req, res) => {
  const requestId = crypto.randomUUID().split('-')[0];
  const requestStart = Date.now();

  try {
    const { includeSlowQueries, includeIndexAnalysis, includeTableStats } = req.body;

    console.log(`🔍 [${requestId}] Database performance analysis initiated`, {
      userId: req.user?.sub ? `${req.user.sub.substring(0, 8)}...` : 'undefined',
      options: { includeSlowQueries, includeIndexAnalysis, includeTableStats },
      userAgent: req.headers['user-agent'],
      ip: req.ip
    });

    // Initialize optimizer
    const optimizer = new DatabaseOptimizer({
      slowQueryThreshold: 1000,
      enableAutoIndexing: false,
      maxAnalysisQueries: 50
    });

    // Perform analysis
    const analysis = await optimizer.analyzePerformance();

    // Filter results based on request options
    if (!includeSlowQueries) {
      analysis.slowQueries = [];
    }
    if (!includeIndexAnalysis) {
      analysis.missingIndexes = [];
    }
    if (!includeTableStats) {
      analysis.tableStatistics = { tableStats: [], tableSizes: [], indexUsage: [] };
    }

    // Add recommendation IDs for tracking
    analysis.recommendations = analysis.recommendations.map((rec, index) => ({
      ...rec,
      id: `rec_${analysis.id}_${index}`,
      analysisId: analysis.id
    }));

    const totalDuration = Date.now() - requestStart;

    console.log(`✅ [${requestId}] Database analysis completed in ${totalDuration}ms`, {
      analysisId: analysis.id,
      slowQueries: analysis.slowQueries.length,
      missingIndexes: analysis.missingIndexes.length,
      recommendations: analysis.recommendations.length
    });

    res.success({
      analysis: {
        id: analysis.id,
        timestamp: analysis.timestamp,
        summary: {
          slowQueriesFound: analysis.slowQueries.length,
          missingIndexesFound: analysis.missingIndexes.length,
          recommendationsGenerated: analysis.recommendations.length,
          highPriorityRecommendations: analysis.recommendations.filter(r => r.priority === 'high').length
        },
        slowQueries: analysis.slowQueries.slice(0, 20), // Limit for response size
        missingIndexes: analysis.missingIndexes,
        recommendations: analysis.recommendations,
        performance: analysis.performance
      }
    }, {
      requestId,
      analysisDuration: `${totalDuration}ms`
    });

  } catch (error) {
    const errorDuration = Date.now() - requestStart;
    console.error(`❌ [${requestId}] Database analysis FAILED after ${errorDuration}ms:`, {
      error: error.message,
      errorStack: error.stack
    });

    res.serverError('Database performance analysis failed', {
      requestId,
      duration: `${errorDuration}ms`,
      originalError: process.env.NODE_ENV === 'development' ? error.message : undefined
    });
  }
});

/**
 * Apply database optimizations
 */
router.post('/optimize', createValidationMiddleware(optimizationValidationSchemas.optimize), async (req, res) => {
  const requestId = crypto.randomUUID().split('-')[0];
  const requestStart = Date.now();

  try {
    const { dryRun, maxIndexes, applyRecommendations } = req.body;

    console.log(`🔧 [${requestId}] Database optimization initiated`, {
      userId: req.user?.sub ? `${req.user.sub.substring(0, 8)}...` : 'undefined',
      dryRun,
      maxIndexes,
      recommendationsToApply: applyRecommendations?.length || 0
    });

    // For production safety, always require explicit recommendations
    if (!applyRecommendations || applyRecommendations.length === 0) {
      return res.badRequest('No recommendations specified for optimization', {
        requestId,
        message: 'You must specify which recommendations to apply for safety'
      });
    }

    // Initialize optimizer
    const optimizer = new DatabaseOptimizer({
      enableAutoIndexing: !dryRun,
      maxAnalysisQueries: 50
    });

    // Get fresh analysis to ensure recommendations are current
    const analysis = await optimizer.analyzePerformance();

    // Filter recommendations to only those requested
    const requestedRecommendations = analysis.recommendations.filter(rec => {
      const recId = `rec_${analysis.id}_${analysis.recommendations.indexOf(rec)}`;
      return applyRecommendations.includes(recId);
    });

    if (requestedRecommendations.length === 0) {
      return res.badRequest('No valid recommendations found to apply', {
        requestId,
        availableRecommendations: analysis.recommendations.length
      });
    }

    // Apply optimizations
    const optimizationResults = await optimizer.applyOptimizations(requestedRecommendations, {
      dryRun,
      maxIndexes
    });

    const totalDuration = Date.now() - requestStart;

    console.log(`✅ [${requestId}] Database optimization completed in ${totalDuration}ms`, {
      dryRun,
      applied: optimizationResults.applied.length,
      failed: optimizationResults.failed.length,
      skipped: optimizationResults.skipped.length
    });

    res.success({
      optimization: {
        dryRun,
        requestedRecommendations: requestedRecommendations.length,
        results: {
          applied: optimizationResults.applied.length,
          failed: optimizationResults.failed.length,
          skipped: optimizationResults.skipped.length
        },
        details: optimizationResults,
        warnings: dryRun ? ['This was a dry run - no actual changes were made'] : []
      }
    }, {
      requestId,
      optimizationDuration: `${totalDuration}ms`
    });

  } catch (error) {
    const errorDuration = Date.now() - requestStart;
    console.error(`❌ [${requestId}] Database optimization FAILED after ${errorDuration}ms:`, {
      error: error.message,
      errorStack: error.stack
    });

    res.serverError('Database optimization failed', {
      requestId,
      duration: `${errorDuration}ms`,
      originalError: process.env.NODE_ENV === 'development' ? error.message : undefined
    });
  }
});

/**
 * Get database performance metrics and status
 */
router.get('/metrics', async (req, res) => {
  const requestId = crypto.randomUUID().split('-')[0];

  try {
    console.log(`📊 [${requestId}] Database metrics request`, {
      userId: req.user?.sub ? `${req.user.sub.substring(0, 8)}...` : 'undefined'
    });

    const optimizer = new DatabaseOptimizer();
    const performanceMetrics = await optimizer.calculatePerformanceMetrics();
    const optimizerStatus = optimizer.getStatus();

    res.success({
      metrics: performanceMetrics,
      optimizer: optimizerStatus,
      timestamp: new Date().toISOString()
    }, {
      requestId
    });

  } catch (error) {
    console.error(`❌ [${requestId}] Database metrics request failed:`, {
      error: error.message
    });

    res.serverError('Failed to get database metrics', {
      requestId,
      originalError: process.env.NODE_ENV === 'development' ? error.message : undefined
    });
  }
});

/**
 * Get current database schema information
 */
router.get('/schema', async (req, res) => {
  const requestId = crypto.randomUUID().split('-')[0];

  try {
    console.log(`📋 [${requestId}] Database schema request`, {
      userId: req.user?.sub ? `${req.user.sub.substring(0, 8)}...` : 'undefined'
    });

    // Import database utility
    const { validateDatabaseSchema } = require('../utils/database');
    
    // Get comprehensive schema validation
    const schemaValidation = await validateDatabaseSchema(requestId);

    res.success({
      schema: schemaValidation,
      summary: {
        valid: schemaValidation.valid,
        healthPercentage: schemaValidation.healthPercentage,
        totalRequired: schemaValidation.totalRequired,
        totalExisting: schemaValidation.totalExisting,
        criticalMissing: schemaValidation.criticalMissing?.length || 0
      }
    }, {
      requestId
    });

  } catch (error) {
    console.error(`❌ [${requestId}] Database schema request failed:`, {
      error: error.message
    });

    res.serverError('Failed to get database schema information', {
      requestId,
      originalError: process.env.NODE_ENV === 'development' ? error.message : undefined
    });
  }
});

/**
 * Database health check with performance indicators
 */
router.get('/health', async (req, res) => {
  const requestId = crypto.randomUUID().split('-')[0];

  try {
    const { healthCheck } = require('../utils/database');
    
    const healthResult = await healthCheck();
    const optimizer = new DatabaseOptimizer();
    const metrics = await optimizer.calculatePerformanceMetrics();

    const healthStatus = {
      database: healthResult,
      performance: {
        cacheHitRatio: parseFloat(metrics.cacheHitRatio),
        connectionCount: metrics.connectionStates?.reduce((sum, state) => sum + state.count, 0) || 0,
        databaseSize: metrics.databaseSize
      },
      status: healthResult.status === 'healthy' && 
              parseFloat(metrics.cacheHitRatio) > 90 ? 'healthy' : 'degraded',
      timestamp: new Date().toISOString()
    };

    res.success(healthStatus, { requestId });

  } catch (error) {
    console.error(`❌ [${requestId}] Database health check failed:`, {
      error: error.message
    });

    res.serverError('Database health check failed', {
      requestId,
      originalError: process.env.NODE_ENV === 'development' ? error.message : undefined
    });
  }
});

module.exports = router;