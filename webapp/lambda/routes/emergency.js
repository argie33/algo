/**
 * Emergency Database Recovery Endpoints
 */
const express = require('express');
const router = express.Router();

// Emergency circuit breaker reset endpoint
router.post('/emergency/reset-circuit-breaker', async (req, res) => {
  try {
    console.log('🚨 EMERGENCY: Circuit breaker reset requested');
    
    const databaseManager = require('../utils/databaseConnectionManager');
    const beforeStatus = databaseManager.getStatus();
    
    console.log('📊 Circuit breaker status before reset:', beforeStatus.circuitBreaker);
    
    // Force reset the circuit breaker and connection
    await databaseManager.forceReset();
    
    const afterStatus = databaseManager.getStatus();
    console.log('📊 Circuit breaker status after reset:', afterStatus.circuitBreaker);
    
    // Test the connection
    let testResult;
    try {
      await databaseManager.query('SELECT 1 as test');
      testResult = { success: true, message: 'Database connection restored' };
    } catch (error) {
      testResult = { success: false, error: error.message };
    }
    
    res.json({
      status: 'success',
      message: 'Circuit breaker emergency reset completed',
      beforeStatus: beforeStatus.circuitBreaker,
      afterStatus: afterStatus.circuitBreaker,
      connectionTest: testResult,
      timestamp: new Date().toISOString(),
      warning: 'This is an emergency procedure. Monitor the system closely.'
    });
    
  } catch (error) {
    console.error('❌ Emergency reset failed:', error);
    res.status(500).json({
      status: 'error',
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Circuit breaker status monitoring endpoint
router.get('/circuit-breaker-status', async (req, res) => {
  try {
    const databaseManager = require('../utils/databaseConnectionManager');
    const status = databaseManager.getStatus();
    
    const circuitBreakerStatus = status.circuitBreaker;
    const isHealthy = circuitBreakerStatus.state === 'closed' && circuitBreakerStatus.isHealthy;
    
    res.json({
      status: isHealthy ? 'healthy' : 'degraded',
      circuitBreaker: circuitBreakerStatus,
      pool: status.pool,
      recommendations: generateCircuitBreakerRecommendations(circuitBreakerStatus),
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('❌ Circuit breaker status check failed:', error);
    res.status(500).json({
      status: 'error',
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Emergency CloudFormation config endpoint - DEPRECATED
router.get('/config/cloudformation', async (req, res) => {
  console.log('🚨 DEPRECATED: Emergency CloudFormation config endpoint called');
  
  // Return proper error - no hardcoded configuration values
  res.status(501).json({
    success: false,
    error: 'Emergency CloudFormation Configuration Deprecated',
    details: {
      type: 'ENDPOINT_DEPRECATED',
      message: 'Hardcoded configuration values have been removed for security',
      reason: 'Emergency fallback configurations contained sensitive hardcoded values',
      alternatives: {
        primary: 'Use /api/cloudformation endpoint with proper AWS parameter retrieval',
        backup: 'Configure CloudFormation outputs through AWS Parameter Store',
        manual: 'Set configuration values through environment variables'
      },
      migration_required: {
        environment_variables: [
          'AWS_REGION - AWS region for resource discovery',
          'CLOUDFORMATION_STACK_NAME - Stack name for parameter retrieval',
          'API_GATEWAY_URL - Dynamic API Gateway URL from CloudFormation'
        ],
        aws_integration: [
          'CloudFormation stack outputs',
          'AWS Parameter Store configuration',
          'AWS Systems Manager integration'
        ]
      },
      security_improvement: 'Removed hardcoded API Gateway URLs and resource identifiers'
    }
  } catch (error) {
    console.error('❌ Emergency CloudFormation config error:', error);
    res.status(500).json({
      success: false,
      error: 'Emergency CloudFormation configuration service error',
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Emergency update-status endpoint - temporary workaround for health route loading issue
router.post('/update-status', async (req, res) => {
  try {
    console.log('🔄 Emergency health status update requested');
    
    const databaseManager = require('../utils/databaseConnectionManager');
    
    // Perform a basic health check using the database manager
    let healthData;
    try {
      // Test basic connectivity
      const testResult = await databaseManager.query('SELECT NOW() as current_time, current_database() as db_name');
      
      // Simple health data structure
      healthData = {
        status: 'connected',
        database: {
          status: 'connected',
          currentTime: testResult.rows[0].current_time,
          dbName: testResult.rows[0].db_name,
          tables: {}, // Simplified - no table analysis for emergency endpoint
          summary: {
            total_tables: 'unknown',
            healthy_tables: 'unknown', 
            stale_tables: 0,
            error_tables: 0,
            empty_tables: 0,
            missing_tables: 0,
            total_records: 'unknown',
            total_missing_data: 0
          }
        },
        timestamp: new Date().toISOString(),
        note: 'Emergency endpoint - simplified health check'
      };
    } catch (error) {
      healthData = {
        status: 'error',
        error: error.message,
        database: {
          status: 'error',
          tables: {},
          summary: {
            total_tables: 0,
            healthy_tables: 0,
            stale_tables: 0,
            error_tables: 0,
            empty_tables: 0,
            missing_tables: 0,
            total_records: 0,
            total_missing_data: 0
          }
        },
        timestamp: new Date().toISOString()
      };
    }
    
    res.json({
      status: 'success',
      message: 'Database health status updated successfully (emergency endpoint)',
      data: healthData,
      timestamp: new Date().toISOString(),
      note: 'This is an emergency endpoint. The main health endpoint is temporarily unavailable.'
    });
    
  } catch (error) {
    console.error('❌ Failed to update health status (emergency endpoint):', error);
    res.status(500).json({
      status: 'error',
      error: 'Failed to update health status',
      details: error.message,
      timestamp: new Date().toISOString(),
      note: 'Emergency endpoint error'
    });
  }
});

function generateCircuitBreakerRecommendations(status) {
  const recommendations = [];
  
  if (status.state === 'open') {
    recommendations.push({
      level: 'critical',
      message: 'Circuit breaker is OPEN. Database access blocked for ' + Math.ceil(status.timeToRecovery/1000) + ' more seconds.',
      action: 'Wait for automatic recovery or use emergency reset endpoint: POST /api/health/emergency/reset-circuit-breaker'
    });
  }
  
  if (status.state === 'half-open') {
    recommendations.push({
      level: 'warning',
      message: 'Circuit breaker is testing recovery. Avoid heavy database operations.',
      action: 'Monitor closely and allow time for recovery validation'
    });
  }
  
  if (status.failures > 7) { // 70% of 10 threshold
    recommendations.push({
      level: 'warning',
      message: 'High failure rate detected (' + status.failures + ' failures). Circuit breaker may open soon.',
      action: 'Investigate database connectivity and consider scaling down operations'
    });
  }
  
  if (parseFloat(status.successRate) < 80) {
    recommendations.push({
      level: 'warning',
      message: 'Low success rate (' + status.successRate + '). Database performance issues detected.',
      action: 'Check database performance metrics and connection configuration'
    });
  }
  
  return recommendations;
}

// Emergency lightweight stocks endpoint - minimal data for data cache service
router.get('/stocks', async (req, res) => {
  try {
    console.log('🔄 Emergency stocks endpoint requested');
    
    const limit = parseInt(req.query.limit) || 10;
    const search = req.query.search || '';
    
    const databaseManager = require('../utils/databaseConnectionManager');
    
    // Ultra-lightweight query - only stock_symbols table, essential fields only
    let stocksQuery = `
      SELECT 
        symbol,
        security_name as name,
        exchange,
        market_category,
        financial_status
      FROM stock_symbols 
      WHERE 1=1
    `;
    
    const params = [];
    
    // Add search filter if provided
    if (search) {
      stocksQuery += ` AND (symbol ILIKE $1 OR security_name ILIKE $1)`;
      params.push(`%${search}%`);
      stocksQuery += ` ORDER BY symbol LIMIT $2`;
      params.push(limit);
    } else {
      stocksQuery += ` ORDER BY symbol LIMIT $1`;
      params.push(limit);
    }
    
    console.log('🔍 Executing lightweight stocks query:', stocksQuery);
    
    let result;
    try {
      result = await databaseManager.query(stocksQuery, params);
      console.log(`✅ Emergency stocks query successful: ${result.rows.length} stocks found`);
      
      // Transform to expected format
      const stocks = result.rows.map(row => ({
        symbol: row.symbol,
        name: row.name,
        exchange: row.exchange,
        market_category: row.market_category,
        financial_status: row.financial_status,
        // Minimal mock data for cache compatibility
        current_price: null,
        previous_close: null,
        market_cap: null,
        sector: 'Unknown',
        industry: 'Unknown'
      }));
      
      res.json({
        success: true,
        data: stocks,
        total: stocks.length,
        page: 1,
        limit: limit,
        source: 'emergency_stocks',
        note: 'Emergency endpoint - minimal stock data only',
        timestamp: new Date().toISOString()
      });
      
    } catch (dbError) {
      console.error('❌ Emergency stocks query failed:', dbError.message);
      
      // Return mock data if database fails
      const mockStocks = [
        { symbol: 'AAPL', name: 'Apple Inc', exchange: 'NASDAQ', market_category: 'Q', financial_status: 'N', current_price: null, previous_close: null, market_cap: null, sector: 'Technology', industry: 'Consumer Electronics' },
        { symbol: 'GOOGL', name: 'Alphabet Inc', exchange: 'NASDAQ', market_category: 'Q', financial_status: 'N', current_price: null, previous_close: null, market_cap: null, sector: 'Technology', industry: 'Internet Services' },
        { symbol: 'MSFT', name: 'Microsoft Corporation', exchange: 'NASDAQ', market_category: 'Q', financial_status: 'N', current_price: null, previous_close: null, market_cap: null, sector: 'Technology', industry: 'Software' },
        { symbol: 'AMZN', name: 'Amazon.com Inc', exchange: 'NASDAQ', market_category: 'Q', financial_status: 'N', current_price: null, previous_close: null, market_cap: null, sector: 'Consumer Cyclical', industry: 'Internet Retail' },
        { symbol: 'TSLA', name: 'Tesla Inc', exchange: 'NASDAQ', market_category: 'Q', financial_status: 'N', current_price: null, previous_close: null, market_cap: null, sector: 'Consumer Cyclical', industry: 'Auto Manufacturers' }
      ].slice(0, limit);
      
      res.json({
        success: true,
        data: mockStocks,
        total: mockStocks.length,
        page: 1,
        limit: limit,
        source: 'emergency_mock',
        note: 'Emergency mock data - database unavailable',
        error: dbError.message,
        timestamp: new Date().toISOString()
      });
    }
    
  } catch (error) {
    console.error('❌ Emergency stocks endpoint failed:', error);
    res.status(500).json({
      success: false,
      error: 'Emergency stocks endpoint failed',
      details: error.message,
      timestamp: new Date().toISOString(),
      note: 'Emergency stocks endpoint error'
    });
  }
});

module.exports = router;