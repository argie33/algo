const express = require('express');
const { query } = require('../utils/database');
const { authenticateToken } = require('../middleware/auth');
const logger = require('../utils/logger');
const { createValidationMiddleware, validationSchemas /*, sanitizers */ } = require('../middleware/validation');

const router = express.Router();

// Add request logging middleware to this router
router.use(logger.requestLoggingMiddleware);

// Health endpoint with comprehensive logging
router.get('/health', (req, res) => {
  req.logger.info('Stocks health check initiated');
  
  res.json({
    success: true,
    status: 'operational',
    service: 'Stocks Enhanced',
    timestamp: new Date().toISOString(),
    message: 'Stocks service with full functionality is running',
    features: ['sectors', 'search', 'profile', 'public-sample'],
    logging: 'comprehensive'
  });
});

// Root endpoint with enhanced information
router.get('/', (req, res) => {
  req.logger.info('Stocks root endpoint accessed');
  
  res.json({
    success: true,
    message: 'Enhanced Stocks API - Full Functionality',
    timestamp: new Date().toISOString(),
    status: 'operational',
    available_endpoints: [
      '/sectors',
      '/search', 
      '/profile/:symbol',
      '/public/sample',
      '/health',
      '/status'
    ],
    service: 'Stocks Enhanced',
    authentication: {
      public_endpoints: ['/health', '/', '/status', '/sectors', '/public/sample'],
      protected_endpoints: ['/search', '/profile/:symbol']
    },
    logging: 'comprehensive'
  });
});

// Status endpoint with enhanced monitoring
router.get('/status', (req, res) => {
  req.logger.info('Stocks status check initiated');
  
  const performance = req.logger.getPerformanceSummary();
  
  res.json({
    success: true,
    service: 'Stocks Enhanced',
    status: 'operational',
    uptime: process.uptime(),
    memory: {
      used: Math.round(process.memoryUsage().heapUsed / 1024 / 1024),
      total: Math.round(process.memoryUsage().heapTotal / 1024 / 1024)
    },
    performance,
    timestamp: new Date().toISOString(),
    features: {
      database_integration: true,
      authentication: true,
      validation: true,
      logging: true,
      error_handling: 'comprehensive'
    }
  });
});

// PUBLIC ENDPOINTS (no authentication required)

// Get available sectors for filtering - public endpoint with comprehensive logging
router.get('/sectors', async (req, res) => {
  req.logger.info('Sectors endpoint initiated (public access)');
  req.logger.mark('sectors_query_start');
  
  try {
    req.logger.info('Starting sectors database query');
    
    // Use robust query with proper error handling
    const sectorsQuery = `
      SELECT 
        COALESCE(s.sector, 'Unknown') as sector, 
        COUNT(*) as count,
        AVG(CASE WHEN s.market_cap > 0 THEN s.market_cap END) as avg_market_cap,
        AVG(CASE WHEN s.pe_ratio > 0 THEN s.pe_ratio END) as avg_pe_ratio
      FROM stock_symbols s
      WHERE s.is_active = TRUE AND s.sector IS NOT NULL AND s.sector != 'Unknown'
      GROUP BY s.sector
      ORDER BY count DESC
    `;
    
    let result;
    try {
      req.logger.dbOperation('SELECT', 'stock_symbols', null, {
        operation_type: 'sectors_aggregation',
        query_complexity: 'medium'
      });
      
      const startTime = Date.now();
      result = await query(sectorsQuery);
      const duration = Date.now() - startTime;
      
      req.logger.info(`Sectors query successful: ${result.rows.length} sectors found`, {
        duration_ms: duration,
        rows_returned: result.rows.length,
        query_type: 'sectors_aggregation'
      });
      
      req.logger.mark('sectors_query_complete');
      
    } catch (dbError) {
      req.logger.error('Sectors query failed - comprehensive database diagnosis', {
        query_type: 'sectors_aggregation',
        error_message: dbError.message,
        error_code: dbError.code,
        error_severity: dbError.severity,
        detailed_diagnostics: {
          attempted_operations: ['stock_symbols_query', 'sector_aggregation'],
          potential_causes: [
            'stock_symbols table missing',
            'Database connection failure',
            'Schema validation error',
            'Data type mismatch',
            'Insufficient database permissions',
            'Query timeout'
          ],
          troubleshooting_steps: [
            'Check if stock_symbols table exists',
            'Verify database connection health',
            'Validate table schema structure',
            'Check database permissions',
            'Review query syntax and data types',
            'Monitor database performance'
          ],
          system_checks: [
            'Database health status',
            'Table existence validation',
            'Schema integrity check',
            'Connection pool availability'
          ]
        },
        error: dbError
      });
      throw dbError; // Re-throw to trigger proper error handling
    }
    
    // Transform data with logging
    req.logger.mark('data_transformation_start');
    
    const sectors = result.rows.map(row => ({
      sector: row.sector,
      count: parseInt(row.count),
      avg_market_cap: parseFloat(row.avg_market_cap) || 0,
      avg_pe_ratio: parseFloat(row.avg_pe_ratio) || null
    }));
    
    req.logger.mark('data_transformation_complete');
    req.logger.info('Sectors data transformation completed', {
      transformed_records: sectors.length,
      data_quality: {
        sectors_with_market_cap: sectors.filter(s => s.avg_market_cap > 0).length,
        sectors_with_pe_ratio: sectors.filter(s => s.avg_pe_ratio !== null).length
      }
    });
    
    res.json({
      success: true,
      data: sectors,
      count: sectors.length,
      timestamp: new Date().toISOString(),
      data_source: 'database',
      performance: req.logger.getPerformanceSummary()
    });
    
  } catch (error) {
    req.logger.error('Sectors endpoint failed - returning empty result with diagnostics', {
      error_type: 'database_query_failure',
      error_message: error.message,
      fallback_strategy: 'empty_sectors_with_diagnostics',
      error: error
    });
    
    // Return empty sectors with comprehensive diagnostics
    res.json({
      success: true,
      data: [],
      count: 0,
      message: 'No sectors data available - check data loading process',
      timestamp: new Date().toISOString(),
      data_source: 'fallback',
      diagnostics: {
        database_query_failed: true,
        potential_causes: [
          'Database connection failure',
          'stock_symbols table missing',
          'Data loading scripts not executed',
          'Database tables corrupted or empty'
        ],
        troubleshooting_steps: [
          'Check database connectivity',
          'Verify stock_symbols table exists',
          'Check data loading process status',
          'Review table structure and data integrity'
        ]
      },
      performance: req.logger.getPerformanceSummary()
    });
  }
});

// Public endpoint for monitoring purposes - basic stock data without authentication
router.get('/public/sample', async (req, res) => {
  req.logger.info('Public stocks sample endpoint initiated for monitoring');
  req.logger.mark('public_sample_start');
  
  try {
    const limit = parseInt(req.query.limit) || 5;
    req.logger.info('Processing public sample request', { limit });
    
    // Validate limit parameter
    if (limit < 1 || limit > 50) {
      req.logger.warn('Invalid limit parameter provided', { 
        provided_limit: limit, 
        valid_range: '1-50' 
      });
      return res.status(400).json({
        success: false,
        error: 'Limit must be between 1 and 50',
        provided_limit: limit,
        timestamp: new Date().toISOString()
      });
    }
    
    // Use robust query with proper error handling
    const stocksQuery = `
      SELECT symbol, name as company_name, sector, exchange, market_cap
      FROM stock_symbols
      WHERE is_active = TRUE
      ORDER BY market_cap DESC NULLS LAST
      LIMIT $1
    `;
    
    let result;
    try {
      req.logger.dbOperation('SELECT', 'stock_symbols', null, {
        operation_type: 'public_sample',
        limit,
        query_complexity: 'simple'
      });
      
      const startTime = Date.now();
      result = await query(stocksQuery, [limit]);
      const duration = Date.now() - startTime;
      
      req.logger.info(`Public stocks sample query successful: ${result.rows.length} stocks found`, {
        duration_ms: duration,
        rows_returned: result.rows.length,
        requested_limit: limit
      });
      
      req.logger.mark('public_sample_query_complete');
      
    } catch (dbError) {
      req.logger.error('Public stocks sample query failed - comprehensive diagnosis', {
        query_type: 'public_stocks_sample',
        limit,
        error_message: dbError.message,
        error_code: dbError.code,
        detailed_diagnostics: {
          attempted_operations: ['stock_symbols_query', 'market_cap_ordering'],
          potential_causes: [
            'stock_symbols table missing',
            'Database connection failure',
            'Schema validation error',
            'Data type mismatch in market_cap column',
            'Insufficient database permissions',
            'Query timeout'
          ]
        },
        error: dbError
      });
      throw dbError;
    }
    
    req.logger.mark('public_sample_complete');
    
    res.json({
      success: true,
      data: result.rows,
      count: result.rows.length,
      requested_limit: limit,
      endpoint: 'public-sample',
      timestamp: new Date().toISOString(),
      data_source: 'database',
      performance: req.logger.getPerformanceSummary()
    });
    
  } catch (error) {
    req.logger.error('Public stocks sample endpoint failed', {
      error_message: error.message,
      error_type: 'database_query_failure',
      error: error
    });
    
    res.status(500).json({
      success: false,
      error: 'Failed to fetch stock data',
      endpoint: 'public-sample',
      timestamp: new Date().toISOString(),
      diagnostics: {
        database_connection_failed: true,
        suggested_actions: [
          'Check database connectivity',
          'Verify stock_symbols table exists',
          'Review data loading process'
        ]
      },
      performance: req.logger.getPerformanceSummary()
    });
  }
});

// PROTECTED ENDPOINTS (authentication required)

// Apply authentication to protected routes
router.use(authenticateToken);

// Search stocks endpoint with comprehensive logging
router.get('/search', 
  createValidationMiddleware(validationSchemas.stockSearch), 
  async (req, res) => {
    req.logger.info('Stock search endpoint initiated (authenticated)', {
      user_id: req.user?.sub?.substring(0, 8) + '...',
      search_params: req.query
    });
    req.logger.authEvent('search_request', req.user?.sub);
    req.logger.mark('search_start');
    
    try {
      const { q: searchTerm, limit = 10, sector, exchange } = req.query;
      
      if (!searchTerm || searchTerm.length < 1) {
        req.logger.warn('Search request with invalid search term', { 
          search_term: searchTerm 
        });
        return res.status(400).json({
          success: false,
          error: 'Search term is required and must be at least 1 character',
          timestamp: new Date().toISOString()
        });
      }
      
      req.logger.info('Processing stock search', {
        search_term: searchTerm,
        limit: parseInt(limit),
        filters: { sector, exchange }
      });
      
      // Build dynamic query with filters
      const whereConditions = ['s.is_active = TRUE'];
      const queryParams = [];
      let paramIndex = 1;
      
      // Add search term condition
      whereConditions.push(`(s.symbol ILIKE $${paramIndex} OR s.name ILIKE $${paramIndex})`);
      queryParams.push(`%${searchTerm}%`);
      paramIndex++;
      
      // Add sector filter if provided
      if (sector) {
        whereConditions.push(`s.sector = $${paramIndex}`);
        queryParams.push(sector);
        paramIndex++;
      }
      
      // Add exchange filter if provided
      if (exchange) {
        whereConditions.push(`s.exchange = $${paramIndex}`);
        queryParams.push(exchange);
        paramIndex++;
      }
      
      // Add limit parameter
      queryParams.push(parseInt(limit));
      
      const searchQuery = `
        SELECT 
          s.symbol, 
          s.name as company_name, 
          s.sector, 
          s.exchange, 
          s.market_cap,
          s.pe_ratio,
          s.dividend_yield
        FROM stock_symbols s
        WHERE ${whereConditions.join(' AND ')}
        ORDER BY 
          CASE WHEN s.symbol ILIKE $1 THEN 0 ELSE 1 END,
          s.market_cap DESC NULLS LAST
        LIMIT $${paramIndex}
      `;
      
      req.logger.dbOperation('SELECT', 'stock_symbols', null, {
        operation_type: 'stock_search',
        search_term: searchTerm,
        filters_applied: { sector: !!sector, exchange: !!exchange },
        query_complexity: 'complex'
      });
      
      const startTime = Date.now();
      const result = await query(searchQuery, queryParams);
      const duration = Date.now() - startTime;
      
      req.logger.info(`Stock search completed successfully`, {
        duration_ms: duration,
        results_found: result.rows.length,
        search_term: searchTerm,
        filters_applied: Object.keys(req.query).length - 1
      });
      
      req.logger.mark('search_complete');
      
      res.json({
        success: true,
        data: result.rows,
        count: result.rows.length,
        search_term: searchTerm,
        filters: { sector, exchange },
        timestamp: new Date().toISOString(),
        performance: req.logger.getPerformanceSummary()
      });
      
    } catch (error) {
      req.logger.error('Stock search failed', {
        search_term: req.query.q,
        error_message: error.message,
        user_id: req.user?.sub?.substring(0, 8) + '...',
        error: error
      });
      
      res.status(500).json({
        success: false,
        error: 'Search operation failed',
        timestamp: new Date().toISOString(),
        performance: req.logger.getPerformanceSummary()
      });
    }
  }
);

// Get stock profile endpoint with comprehensive logging
router.get('/profile/:symbol', 
  createValidationMiddleware(validationSchemas.stockSymbol), 
  async (req, res) => {
    const { symbol } = req.params;
    
    req.logger.info('Stock profile endpoint initiated (authenticated)', {
      symbol,
      user_id: req.user?.sub?.substring(0, 8) + '...'
    });
    req.logger.authEvent('profile_request', req.user?.sub, { symbol });
    req.logger.mark('profile_start');
    
    try {
      req.logger.info('Fetching stock profile data', { symbol });
      
      const profileQuery = `
        SELECT 
          s.symbol,
          s.name as company_name,
          s.sector,
          s.industry,
          s.exchange,
          s.market_cap,
          s.pe_ratio,
          s.dividend_yield,
          s.beta,
          s.fifty_two_week_high,
          s.fifty_two_week_low,
          s.description,
          s.website,
          s.headquarters,
          s.employees,
          s.founded_year
        FROM stock_symbols s
        WHERE s.symbol = $1 AND s.is_active = TRUE
      `;
      
      req.logger.dbOperation('SELECT', 'stock_symbols', null, {
        operation_type: 'stock_profile',
        symbol,
        query_complexity: 'medium'
      });
      
      const startTime = Date.now();
      const result = await query(profileQuery, [symbol.toUpperCase()]);
      const duration = Date.now() - startTime;
      
      if (result.rows.length === 0) {
        req.logger.warn('Stock profile not found', { 
          symbol,
          searched_symbol: symbol.toUpperCase()
        });
        
        return res.status(404).json({
          success: false,
          error: 'Stock not found',
          symbol,
          timestamp: new Date().toISOString(),
          performance: req.logger.getPerformanceSummary()
        });
      }
      
      req.logger.info(`Stock profile retrieved successfully`, {
        duration_ms: duration,
        symbol,
        profile_completeness: Object.keys(result.rows[0]).filter(key => result.rows[0][key] !== null).length
      });
      
      req.logger.mark('profile_complete');
      
      res.json({
        success: true,
        data: result.rows[0],
        symbol,
        timestamp: new Date().toISOString(),
        performance: req.logger.getPerformanceSummary()
      });
      
    } catch (error) {
      req.logger.error('Stock profile retrieval failed', {
        symbol,
        error_message: error.message,
        user_id: req.user?.sub?.substring(0, 8) + '...',
        error: error
      });
      
      res.status(500).json({
        success: false,
        error: 'Failed to fetch stock profile',
        symbol,
        timestamp: new Date().toISOString(),
        performance: req.logger.getPerformanceSummary()
      });
    }
  }
);

module.exports = router;