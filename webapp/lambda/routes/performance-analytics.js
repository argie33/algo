/**
 * Performance Analytics API Routes
 * Advanced performance metrics and analytics endpoints
 */

const express = require('express');
const router = express.Router();
const { authenticateToken } = require('../middleware/auth');
const { validateInput } = require('../middleware/validation');
const { getDatabase } = require('../utils/database');
const { AdvancedPerformanceAnalytics } = require('../utils/advancedPerformanceAnalytics');
const { createRequestLogger } = require('../utils/logger');
const { formatResponse } = require('../utils/responseFormatter');

const logger = createRequestLogger('performance-analytics-routes');

// Input validation schemas
const performanceAnalysisSchema = {
  startDate: {
    type: 'string',
    required: true,
    pattern: /^\d{4}-\d{2}-\d{2}$/,
    message: 'Start date must be in YYYY-MM-DD format'
  },
  endDate: {
    type: 'string',
    required: true,
    pattern: /^\d{4}-\d{2}-\d{2}$/,
    message: 'End date must be in YYYY-MM-DD format'
  },
  format: {
    type: 'string',
    required: false,
    enum: ['basic', 'detailed'],
    default: 'detailed'
  },
  includeBenchmarks: {
    type: 'boolean',
    required: false,
    default: true
  }
};

const performanceReportSchema = {
  ...performanceAnalysisSchema,
  reportType: {
    type: 'string',
    required: false,
    enum: ['summary', 'detailed', 'executive'],
    default: 'detailed'
  }
};

/**
 * GET /performance-analytics/portfolio
 * Get comprehensive portfolio performance analysis
 */
router.get('/portfolio', authenticateToken, validateInput(performanceAnalysisSchema), async (req, res) => {
  const requestId = req.requestId;
  const userId = req.user.userId;
  const { startDate, endDate, format, includeBenchmarks } = req.query;
  
  try {
    logger.info('Portfolio performance analysis requested', {
      requestId,
      userId: `${userId.substring(0, 8)}...`,
      period: `${startDate} to ${endDate}`,
      format
    });
    
    const db = await getDatabase();
    const analytics = new AdvancedPerformanceAnalytics(db);
    
    // Calculate comprehensive performance metrics
    const performanceMetrics = await analytics.calculatePortfolioPerformance(
      userId,
      startDate,
      endDate,
      { includeBenchmarks }
    );
    
    // Format response based on requested format
    const response = format === 'basic' ? 
      analytics.getBasicMetrics(performanceMetrics) : 
      performanceMetrics;
    
    logger.info('Portfolio performance analysis completed', {
      requestId,
      userId: `${userId.substring(0, 8)}...`,
      calculationTime: performanceMetrics.metadata.calculationTime,
      dataPoints: performanceMetrics.metadata.dataPoints
    });
    
    res.json(formatResponse(response, 'Portfolio performance analysis completed successfully'));
    
  } catch (error) {
    logger.error('Error in portfolio performance analysis', {
      requestId,
      userId: `${userId.substring(0, 8)}...`,
      error: error.message,
      stack: error.stack
    });
    
    res.status(500).json(formatResponse(null, 'Error calculating portfolio performance', error.message));
  }
});

/**
 * GET /performance-analytics/report
 * Generate comprehensive performance report
 */
router.get('/report', authenticateToken, validateInput(performanceReportSchema), async (req, res) => {
  const requestId = req.requestId;
  const userId = req.user.userId;
  const { startDate, endDate, reportType } = req.query;
  
  try {
    logger.info('Performance report requested', {
      requestId,
      userId: `${userId.substring(0, 8)}...`,
      period: `${startDate} to ${endDate}`,
      reportType
    });
    
    const db = await getDatabase();
    const analytics = new AdvancedPerformanceAnalytics(db);
    
    // Generate performance report
    const report = await analytics.generatePerformanceReport(
      userId,
      startDate,
      endDate,
      reportType
    );
    
    logger.info('Performance report generated', {
      requestId,
      userId: `${userId.substring(0, 8)}...`,
      reportId: report.reportId,
      generationTime: report.generationTime
    });
    
    res.json(formatResponse(report, 'Performance report generated successfully'));
    
  } catch (error) {
    logger.error('Error generating performance report', {
      requestId,
      userId: `${userId.substring(0, 8)}...`,
      error: error.message,
      stack: error.stack
    });
    
    res.status(500).json(formatResponse(null, 'Error generating performance report', error.message));
  }
});

/**
 * GET /performance-analytics/attribution
 * Get performance attribution analysis
 */
router.get('/attribution', authenticateToken, validateInput(performanceAnalysisSchema), async (req, res) => {
  const requestId = req.requestId;
  const userId = req.user.userId;
  const { startDate, endDate } = req.query;
  
  try {
    logger.info('Attribution analysis requested', {
      requestId,
      userId: `${userId.substring(0, 8)}...`,
      period: `${startDate} to ${endDate}`
    });
    
    const db = await getDatabase();
    const analytics = new AdvancedPerformanceAnalytics(db);
    
    // Calculate attribution analysis
    const attributionAnalysis = await analytics.calculateAttributionAnalysis(
      userId,
      startDate,
      endDate
    );
    
    logger.info('Attribution analysis completed', {
      requestId,
      userId: `${userId.substring(0, 8)}...`,
      holdings: attributionAnalysis.numberOfHoldings,
      totalValue: attributionAnalysis.totalPortfolioValue
    });
    
    res.json(formatResponse(attributionAnalysis, 'Attribution analysis completed successfully'));
    
  } catch (error) {
    logger.error('Error in attribution analysis', {
      requestId,
      userId: `${userId.substring(0, 8)}...`,
      error: error.message,
      stack: error.stack
    });
    
    res.status(500).json(formatResponse(null, 'Error calculating attribution analysis', error.message));
  }
});

/**
 * GET /performance-analytics/risk-metrics
 * Get comprehensive risk metrics
 */
router.get('/risk-metrics', authenticateToken, validateInput(performanceAnalysisSchema), async (req, res) => {
  const requestId = req.requestId;
  const userId = req.user.userId;
  const { startDate, endDate } = req.query;
  
  try {
    logger.info('Risk metrics analysis requested', {
      requestId,
      userId: `${userId.substring(0, 8)}...`,
      period: `${startDate} to ${endDate}`
    });
    
    const db = await getDatabase();
    const analytics = new AdvancedPerformanceAnalytics(db);
    
    // Get portfolio history for risk calculations
    const portfolioHistory = await analytics.getPortfolioHistory(userId, startDate, endDate);
    
    // Calculate risk metrics
    const riskMetrics = await analytics.calculateRiskMetrics(portfolioHistory);
    
    // Calculate factor exposure for additional risk insights
    const factorExposure = await analytics.calculateFactorExposure(userId, startDate, endDate);
    
    const response = {
      riskMetrics,
      factorExposure,
      riskAssessment: {
        overallRisk: analytics.assessRiskProfile(riskMetrics),
        riskRecommendations: analytics.generateRecommendations({ riskMetrics, factorExposure })
      },
      metadata: {
        dataPoints: portfolioHistory.length,
        calculationDate: new Date().toISOString()
      }
    };
    
    logger.info('Risk metrics analysis completed', {
      requestId,
      userId: `${userId.substring(0, 8)}...`,
      volatility: riskMetrics.volatility,
      maxDrawdown: riskMetrics.maxDrawdown
    });
    
    res.json(formatResponse(response, 'Risk metrics analysis completed successfully'));
    
  } catch (error) {
    logger.error('Error in risk metrics analysis', {
      requestId,
      userId: `${userId.substring(0, 8)}...`,
      error: error.message,
      stack: error.stack
    });
    
    res.status(500).json(formatResponse(null, 'Error calculating risk metrics', error.message));
  }
});

/**
 * GET /performance-analytics/sector-analysis
 * Get sector allocation and performance analysis
 */
router.get('/sector-analysis', authenticateToken, validateInput(performanceAnalysisSchema), async (req, res) => {
  const requestId = req.requestId;
  const userId = req.user.userId;
  const { startDate, endDate } = req.query;
  
  try {
    logger.info('Sector analysis requested', {
      requestId,
      userId: `${userId.substring(0, 8)}...`,
      period: `${startDate} to ${endDate}`
    });
    
    const db = await getDatabase();
    const analytics = new AdvancedPerformanceAnalytics(db);
    
    // Calculate sector analysis
    const sectorAnalysis = await analytics.calculateSectorAnalysis(userId, startDate, endDate);
    
    logger.info('Sector analysis completed', {
      requestId,
      userId: `${userId.substring(0, 8)}...`,
      sectorCount: sectorAnalysis.sectorCount,
      diversificationScore: sectorAnalysis.diversificationScore.diversificationScore
    });
    
    res.json(formatResponse(sectorAnalysis, 'Sector analysis completed successfully'));
    
  } catch (error) {
    logger.error('Error in sector analysis', {
      requestId,
      userId: `${userId.substring(0, 8)}...`,
      error: error.message,
      stack: error.stack
    });
    
    res.status(500).json(formatResponse(null, 'Error calculating sector analysis', error.message));
  }
});

/**
 * GET /performance-analytics/factor-exposure
 * Get factor exposure analysis
 */
router.get('/factor-exposure', authenticateToken, validateInput(performanceAnalysisSchema), async (req, res) => {
  const requestId = req.requestId;
  const userId = req.user.userId;
  const { startDate, endDate } = req.query;
  
  try {
    logger.info('Factor exposure analysis requested', {
      requestId,
      userId: `${userId.substring(0, 8)}...`,
      period: `${startDate} to ${endDate}`
    });
    
    const db = await getDatabase();
    const analytics = new AdvancedPerformanceAnalytics(db);
    
    // Calculate factor exposure
    const factorExposure = await analytics.calculateFactorExposure(userId, startDate, endDate);
    
    logger.info('Factor exposure analysis completed', {
      requestId,
      userId: `${userId.substring(0, 8)}...`,
      totalHoldings: factorExposure.totalHoldings,
      totalValue: factorExposure.totalValue
    });
    
    res.json(formatResponse(factorExposure, 'Factor exposure analysis completed successfully'));
    
  } catch (error) {
    logger.error('Error in factor exposure analysis', {
      requestId,
      userId: `${userId.substring(0, 8)}...`,
      error: error.message,
      stack: error.stack
    });
    
    res.status(500).json(formatResponse(null, 'Error calculating factor exposure', error.message));
  }
});

/**
 * GET /performance-analytics/benchmarks
 * Get benchmark comparison analysis
 */
router.get('/benchmarks', authenticateToken, validateInput(performanceAnalysisSchema), async (req, res) => {
  const requestId = req.requestId;
  const userId = req.user.userId;
  const { startDate, endDate } = req.query;
  
  try {
    logger.info('Benchmark analysis requested', {
      requestId,
      userId: `${userId.substring(0, 8)}...`,
      period: `${startDate} to ${endDate}`
    });
    
    const db = await getDatabase();
    const analytics = new AdvancedPerformanceAnalytics(db);
    
    // Get portfolio history for benchmark comparison
    const portfolioHistory = await analytics.getPortfolioHistory(userId, startDate, endDate);
    
    // Calculate benchmark metrics
    const benchmarkMetrics = await analytics.calculateBenchmarkMetrics(portfolioHistory, startDate, endDate);
    
    logger.info('Benchmark analysis completed', {
      requestId,
      userId: `${userId.substring(0, 8)}...`,
      alpha: benchmarkMetrics.alpha,
      beta: benchmarkMetrics.beta
    });
    
    res.json(formatResponse(benchmarkMetrics, 'Benchmark analysis completed successfully'));
    
  } catch (error) {
    logger.error('Error in benchmark analysis', {
      requestId,
      userId: `${userId.substring(0, 8)}...`,
      error: error.message,
      stack: error.stack
    });
    
    res.status(500).json(formatResponse(null, 'Error calculating benchmark analysis', error.message));
  }
});

/**
 * GET /performance-analytics/health
 * Performance analytics service health check
 */
router.get('/health', async (req, res) => {
  try {
    const db = await getDatabase();
    
    // Test database connectivity
    const testQuery = 'SELECT 1 as test';
    await db.query(testQuery);
    
    const health = {
      status: 'healthy',
      service: 'performance-analytics',
      timestamp: new Date().toISOString(),
      version: '1.0.0',
      capabilities: [
        'portfolio-analysis',
        'risk-metrics',
        'attribution-analysis',
        'sector-analysis',
        'factor-exposure',
        'benchmark-comparison',
        'performance-reporting'
      ]
    };
    
    res.json(formatResponse(health, 'Performance analytics service is healthy'));
    
  } catch (error) {
    logger.error('Performance analytics health check failed', {
      error: error.message,
      stack: error.stack
    });
    
    res.status(500).json(formatResponse(null, 'Performance analytics service health check failed', error.message));
  }
});

module.exports = router;