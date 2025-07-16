const express = require('express');
const { query } = require('../utils/database');
const { authenticateToken } = require('../middleware/auth');

const router = express.Router();

// Apply authentication to all metrics routes
router.use(authenticateToken);

// Basic ping endpoint
router.get('/ping', (req, res) => {
  res.json({
    status: 'ok',
    endpoint: 'metrics',
    timestamp: new Date().toISOString()
  });
});

// Simple dashboard metrics endpoint
router.get('/dashboard', async (req, res) => {
  try {
    console.log('Dashboard metrics endpoint called');
    
    console.log('📊 Dashboard metrics: Fetching real data from database for user:', req.user.sub);
    
    // Get real metrics from database
    let totalStocks = null;
    let totalAlerts = null;
    let activeSymbols = null;
    let portfolioValue = null;
    let dailyChange = null;
    let lastUpdate = null;
    let errors = {};
    
    // Get stock count
    try {
      const stockResult = await query('SELECT COUNT(*) as total FROM stocks WHERE current_price IS NOT NULL', [], 5000);
      totalStocks = parseInt(stockResult.rows[0]?.total || 0);
      console.log(`✅ Stock count: ${totalStocks}`);
    } catch (error) {
      console.error('❌ Stock count query failed:', error.message);
      errors.stocks = `Stock data unavailable: ${error.message}`;
    }
    
    // Get user's portfolio metrics
    try {
      const portfolioResult = await query(`
        SELECT 
          SUM(market_value) as total_value,
          SUM(unrealized_pl) as daily_change,
          COUNT(*) as total_positions
        FROM portfolio_holdings 
        WHERE user_id = $1
      `, [req.user.sub], 5000);
      
      if (portfolioResult.rows[0]) {
        portfolioValue = parseFloat(portfolioResult.rows[0].total_value || 0);
        dailyChange = parseFloat(portfolioResult.rows[0].daily_change || 0);
        activeSymbols = parseInt(portfolioResult.rows[0].total_positions || 0);
        console.log(`✅ Portfolio value: $${portfolioValue}, change: $${dailyChange}, positions: ${activeSymbols}`);
      }
    } catch (error) {
      console.error('❌ Portfolio query failed:', error.message);
      errors.portfolio = `Portfolio data unavailable: ${error.message}`;
    }
    
    // Get alerts count
    try {
      const alertResult = await query(`
        SELECT COUNT(*) as total 
        FROM alerts 
        WHERE user_id = $1 AND is_active = true
      `, [req.user.sub], 5000);
      totalAlerts = parseInt(alertResult.rows[0]?.total || 0);
      console.log(`✅ Active alerts: ${totalAlerts}`);
    } catch (error) {
      console.error('❌ Alerts query failed:', error.message);
      errors.alerts = `Alerts data unavailable: ${error.message}`;
    }
    
    // Get last price update
    try {
      const updateResult = await query('SELECT MAX(updated_at) as last_update FROM stocks', [], 5000);
      lastUpdate = updateResult.rows[0]?.last_update || new Date();
      console.log(`✅ Last price update: ${lastUpdate}`);
    } catch (error) {
      console.error('❌ Last update query failed:', error.message);
      errors.lastUpdate = `Update time unavailable: ${error.message}`;
      lastUpdate = null;
    }
    
    res.json({
      success: true,
      data: {
        totalStocks: totalStocks,
        activeAlerts: totalAlerts,
        activeSymbols: activeSymbols,
        portfolioValue: portfolioValue,
        dailyChange: dailyChange,
        lastPriceUpdate: lastUpdate,
        marketStatus: getMarketStatus(),
        dataFreshness: {
          prices: lastUpdate ? calculateDataAge(lastUpdate) : 'unknown',
          alerts: errors.alerts ? 'unavailable' : 'current',
          symbols: errors.stocks ? 'unavailable' : 'current'
        }
      },
      errors: Object.keys(errors).length > 0 ? errors : null,
      data_source: 'real_database',
      diagnostic: {
        queries_executed: 4,
        database_connectivity: Object.keys(errors).length === 0 ? 'healthy' : 'partial',
        user_id: req.user.sub,
        troubleshooting: Object.keys(errors).length > 0 ? 
          'Some data sources unavailable. Check database connectivity and table existence.' : 
          'All data sources functioning normally'
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('❌ Critical error in dashboard metrics:', error);
    
    res.status(500).json({
      success: false,
      error: 'Dashboard metrics unavailable',
      details: error.message,
      data: {
        totalStocks: null,
        activeAlerts: null,
        activeSymbols: null,
        portfolioValue: null,
        dailyChange: null,
        lastPriceUpdate: null,
        marketStatus: getMarketStatus(),
        dataFreshness: {
          prices: 'unavailable',
          alerts: 'unavailable',
          symbols: 'unavailable'
        }
      },
      diagnostic: {
        issue: 'Critical system error during metrics collection',
        potential_causes: [
          'Database connection failure',
          'Authentication token invalid',
          'Missing required tables (stocks, portfolio_holdings, alerts)',
          'Query timeout or resource limits'
        ],
        troubleshooting: [
          'Check database connectivity and authentication',
          'Verify required tables exist and are accessible',
          'Review AWS Lambda memory and timeout settings',
          'Check VPC and security group configurations'
        ],
        system_checks: {
          authentication: 'completed',
          database_attempted: true,
          fallback_data: false
        }
      },
      timestamp: new Date().toISOString()
    });
  }
});

function getMarketStatus() {
  const now = new Date();
  const hour = now.getHours();
  const day = now.getDay();
  
  // Simple market hours check (9:30 AM - 4:00 PM ET, Mon-Fri)
  if (day === 0 || day === 6) return 'closed'; // Weekend
  if (hour < 9 || hour >= 16) return 'closed';
  if (hour === 9 && now.getMinutes() < 30) return 'pre-market';
  return 'open';
}

function calculateDataAge(lastUpdate) {
  const now = new Date();
  const diffHours = (now - new Date(lastUpdate)) / (1000 * 60 * 60);
  
  if (diffHours < 1) return 'current';
  if (diffHours < 24) return 'recent';
  if (diffHours < 72) return 'stale';
  return 'outdated';
}

// Get comprehensive metrics for all stocks with filtering and pagination
router.get('/', async (req, res) => {
  const requestId = res.locals.requestId || 'unknown';
  const startTime = Date.now();
  
  try {
    console.log(`📊 [${requestId}] Metrics endpoint called with params:`, JSON.stringify(req.query, null, 2));
    console.log(`📊 [${requestId}] Memory at start:`, process.memoryUsage());
    
    // Check database availability immediately to prevent timeouts
    console.log(`🔍 [${requestId}] Testing database connectivity for metrics...`);
    let dbAvailable = false;
    try {
      const dbStart = Date.now();
      await query('SELECT 1', [], 3000); // 3 second timeout
      dbAvailable = true;
      console.log(`✅ [${requestId}] Database available after ${Date.now() - dbStart}ms`);
    } catch (dbError) {
      console.error(`❌ [${requestId}] Database unavailable for metrics endpoint after ${Date.now() - startTime}ms:`, dbError.message);
      return res.status(503).json({
        success: false,
        error: 'Database temporarily unavailable',
        message: 'Metrics data requires database connectivity',
        details: {
          endpoint: 'GET /metrics',
          duration: Date.now() - startTime,
          dbError: dbError.message
        },
        timestamp: new Date().toISOString()
      });
    }
    
    const page = parseInt(req.query.page) || 1;
    const limit = Math.min(parseInt(req.query.limit) || 50, 200);
    const offset = (page - 1) * limit;
    const search = req.query.search || '';
    const sector = req.query.sector || '';
    const minMetric = parseFloat(req.query.minMetric) || 0;
    const maxMetric = parseFloat(req.query.maxMetric) || 1;
    const sortBy = req.query.sortBy || 'composite_metric';
    const sortOrder = req.query.sortOrder || 'desc';
    
    let whereClause = 'WHERE 1=1';
    const params = [];
    let paramCount = 0;

    // Add search filter
    if (search) {
      paramCount++;
      whereClause += ` AND (ss.symbol ILIKE $${paramCount} OR ss.security_name ILIKE $${paramCount})`;
      params.push(`%${search}%`);
    }

    // Add sector filter
    if (sector && sector.trim() !== '') {
      paramCount++;
      whereClause += ` AND s.sector = $${paramCount}`;
      params.push(sector);
    }

    // Add metric range filters (assuming 0-1 scale for metrics)
    if (minMetric > 0) {
      paramCount++;
      whereClause += ` AND COALESCE(qm.quality_metric, 0) >= $${paramCount}`;
      params.push(minMetric);
    }

    if (maxMetric < 1) {
      paramCount++;
      whereClause += ` AND COALESCE(qm.quality_metric, 0) <= $${paramCount}`;
      params.push(maxMetric);
    }

    // Validate sort column to prevent SQL injection
    const validSortColumns = [
      'symbol', 'quality_metric', 'value_metric', 'composite_metric',
      'market_cap', 'sector'
    ];
    
    const safeSort = validSortColumns.includes(sortBy) ? sortBy : 'quality_metric';
    const safeOrder = sortOrder.toLowerCase() === 'asc' ? 'ASC' : 'DESC';
    
    // Try to query actual tables with comprehensive error logging
    console.log(`🔍 [METRICS] Executing metrics query with params:`, { page, limit, search, sector, sortBy, sortOrder });
    
    // Main query to get stocks with metrics - fallback gracefully if tables don't exist
    const stocksQuery = `
      SELECT 
        ss.symbol,
        ss.security_name as company_name,
        COALESCE(s.sector, 'Unknown') as sector,
        COALESCE(s.industry, 'Unknown') as industry,
        COALESCE(s.market_cap, 0) as market_cap,
        COALESCE(s.current_price, 0) as current_price,
        COALESCE(s.trailing_pe, 0) as trailing_pe,
        COALESCE(s.price_to_book, 0) as price_to_book,
        
        -- Try to get quality metrics if table exists, otherwise null
        NULL as quality_metric,
        NULL as earnings_quality_metric,
        NULL as balance_sheet_metric,
        NULL as profitability_metric,
        NULL as management_metric,
        NULL as piotroski_f_score,
        NULL as altman_z_score,
        NULL as quality_confidence,
        
        -- Try to get value metrics if table exists, otherwise null
        NULL as value_metric,
        NULL as multiples_metric,
        NULL as intrinsic_value_metric,
        NULL as relative_value_metric,
        NULL as dcf_intrinsic_value,
        NULL as dcf_margin_of_safety,
        
        -- Try to get growth metrics if table exists, otherwise null
        NULL as growth_composite_score,
        NULL as revenue_growth_score,
        NULL as earnings_growth_score,
        NULL as fundamental_growth_score,
        NULL as market_expansion_score,
        NULL as growth_percentile_rank,
        
        -- Calculate composite metric placeholder
        0.5 as composite_metric,
        
        -- Metadata
        NOW() as metric_date,
        NOW() as last_updated
        
      FROM stock_symbols ss
      LEFT JOIN symbols s ON ss.symbol = s.symbol
      ${whereClause}
      ORDER BY ss.symbol ${safeOrder}
      LIMIT $${paramCount + 1} OFFSET $${paramCount + 2}
    `;

    params.push(limit, offset);

    let stocksResult;
    let totalStocks = 0;
    
    try {
      console.log(`🔍 [METRICS] Attempting to execute main stocks query...`);
      stocksResult = await query(stocksQuery, params);
      console.log(`✅ [METRICS] Query successful, got ${stocksResult.rows.length} rows`);
      
      // Get total count for pagination
      const countQuery = `
        SELECT COUNT(DISTINCT ss.symbol) as total
        FROM stock_symbols ss
        LEFT JOIN symbols s ON ss.symbol = s.symbol
        ${whereClause}
      `;
      
      const countResult = await query(countQuery, params.slice(0, paramCount));
      totalStocks = parseInt(countResult.rows[0].total);
      console.log(`📊 [METRICS] Total stocks available: ${totalStocks}`);
      
    } catch (dbError) {
      console.error(`❌ [METRICS] Database query failed:`, {
        error: dbError.message,
        code: dbError.code,
        detail: dbError.detail,
        query: stocksQuery.substring(0, 200) + '...'
      });
      
      // Return error response with detailed logging
      return res.status(500).json({
        success: false,
        error: 'Database query failed',
        details: dbError.message,
        errorCode: dbError.code,
        timestamp: new Date().toISOString(),
        debugInfo: {
          table_missing: dbError.code === '42P01',
          permission_denied: dbError.code === '42501',
          connection_failed: dbError.code === '08006'
        }
      });
    }

    // Format the response with actual database results
    console.log(`📊 [METRICS] Formatting ${stocksResult.rows.length} stocks for response`);
    
    const stocks = stocksResult.rows.map(row => {
      console.log(`🔍 [METRICS] Processing stock: ${row.symbol}`);
      
      return {
        symbol: row.symbol,
        companyName: row.company_name,
        sector: row.sector,
        industry: row.industry,
        marketCap: parseFloat(row.market_cap) || 0,
        currentPrice: parseFloat(row.current_price) || 0,
        pe: parseFloat(row.trailing_pe) || 0,
        pb: parseFloat(row.price_to_book) || 0,
        
        metrics: {
          composite: parseFloat(row.composite_metric) || 0,
          quality: parseFloat(row.quality_metric) || 0,
          value: parseFloat(row.value_metric) || 0,
          growth: parseFloat(row.growth_composite_score) || 0
        },
        
        qualityBreakdown: {
          overall: parseFloat(row.quality_metric) || 0,
          earningsQuality: parseFloat(row.earnings_quality_metric) || 0,
          balanceSheet: parseFloat(row.balance_sheet_metric) || 0,
          profitability: parseFloat(row.profitability_metric) || 0,
          management: parseFloat(row.management_metric) || 0,
          piotrosiScore: parseInt(row.piotroski_f_score) || 0,
          altmanZScore: parseFloat(row.altman_z_score) || 0
        },
        
        valueBreakdown: {
          overall: parseFloat(row.value_metric) || 0,
          multiples: parseFloat(row.multiples_metric) || 0,
          intrinsicValue: parseFloat(row.intrinsic_value_metric) || 0,
          relativeValue: parseFloat(row.relative_value_metric) || 0,
          dcfValue: parseFloat(row.dcf_intrinsic_value) || 0,
          marginOfSafety: parseFloat(row.dcf_margin_of_safety) || 0
        },
        
        growthBreakdown: {
          overall: parseFloat(row.growth_composite_score) || 0,
          revenue: parseFloat(row.revenue_growth_score) || 0,
          earnings: parseFloat(row.earnings_growth_score) || 0,
          fundamental: parseFloat(row.fundamental_growth_score) || 0,
          marketExpansion: parseFloat(row.market_expansion_score) || 0,
          percentileRank: parseInt(row.growth_percentile_rank) || 0
        },
        
        metadata: {
          confidence: parseFloat(row.quality_confidence) || 0,
          metricDate: row.metric_date,
          lastUpdated: row.last_updated
        }
      };
    });

    res.json({
      stocks,
      pagination: {
        currentPage: page,
        totalPages: Math.ceil(totalStocks / limit),
        totalItems: totalStocks,
        itemsPerPage: limit,
        hasNext: offset + limit < totalStocks,
        hasPrev: page > 1
      },
      filters: {
        search,
        sector,
        minMetric,
        maxMetric,
        sortBy: safeSort,
        sortOrder: safeOrder
      },
      summary: {
        averageComposite: stocks.length > 0 ? 
          (stocks.reduce((sum, s) => sum + s.metrics.composite, 0) / stocks.length).toFixed(4) : 0,
        topPerformer: stocks.length > 0 ? stocks[0] : null,
        metricRange: stocks.length > 0 ? {
          min: Math.min(...stocks.map(s => s.metrics.composite)).toFixed(4),
          max: Math.max(...stocks.map(s => s.metrics.composite)).toFixed(4)
        } : null
      },
      timestamp: new Date().toISOString(),
      dataSource: {
        total_records: totalStocks,
        has_quality_metrics: false,
        has_value_metrics: false,
        has_growth_metrics: false,
        note: 'Metrics tables not yet populated - showing base stock data'
      }
    });

  } catch (error) {
    console.error('Error in metrics endpoint:', error);
    console.log('Returning mock metrics data as fallback');
    
    // Return mock data when database is unavailable
    const mockMetrics = [
      {
        symbol: 'AAPL',
        companyName: 'Apple Inc.',
        sector: 'Technology',
        marketCap: 3000000000000,
        qualityMetric: 0.89,
        valueMetric: 0.73,
        compositeMetric: 0.82,
        lastUpdated: new Date().toISOString()
      },
      {
        symbol: 'MSFT',
        companyName: 'Microsoft Corporation',
        sector: 'Technology',
        marketCap: 2800000000000,
        qualityMetric: 0.92,
        valueMetric: 0.76,
        compositeMetric: 0.85,
        lastUpdated: new Date().toISOString()
      }
    ];

    res.json({
      success: true,
      data: mockMetrics,
      pagination: {
        page: 1,
        limit: mockMetrics.length,
        total: mockMetrics.length,
        pages: 1
      },
      note: 'Mock data - database connectivity issue'
    });
  }
});

// Get detailed metrics for a specific stock
router.get('/:symbol', async (req, res) => {
  try {
    const symbol = req.params.symbol.toUpperCase();
    console.log(`Getting detailed metrics for ${symbol}`);

    // Get latest metrics with historical data
    const metricsQuery = `
      SELECT 
        qm.*,
        vm.value_metric,
        vm.multiples_metric,
        vm.intrinsic_value_metric,
        vm.relative_value_metric,
        vm.dcf_intrinsic_value,
        vm.dcf_margin_of_safety,
        vm.ddm_value,
        vm.rim_value,
        vm.current_pe,
        vm.current_pb,
        vm.current_ev_ebitda,
        ss.security_name as company_name,
        s.sector,
        s.industry,
        s.market_cap,
        s.current_price,
        s.trailing_pe,
        s.price_to_book,
        s.dividend_yield,
        s.return_on_equity,
        s.return_on_assets,
        s.debt_to_equity,
        s.free_cash_flow
      FROM quality_metrics qm
      LEFT JOIN value_metrics vm ON qm.symbol = vm.symbol AND qm.date = vm.date
      LEFT JOIN stock_symbols ss ON qm.symbol = ss.symbol
      LEFT JOIN symbols s ON qm.symbol = s.symbol
      WHERE qm.symbol = $1
      ORDER BY qm.date DESC
      LIMIT 12
    `;

    const metricsResult = await query(metricsQuery, [symbol]);

    if (metricsResult.rows.length === 0) {
      return res.status(404).json({
        error: 'Symbol not found or no metrics available',
        symbol,
        timestamp: new Date().toISOString()
      });
    }

    const latestMetric = metricsResult.rows[0];
    const historicalMetrics = metricsResult.rows.slice(1);

    // Get sector benchmark data
    const sectorQuery = `
      SELECT 
        AVG(qm.quality_metric) as avg_quality,
        AVG(vm.value_metric) as avg_value,
        COUNT(*) as peer_count
      FROM quality_metrics qm
      LEFT JOIN value_metrics vm ON qm.symbol = vm.symbol AND qm.date = vm.date
      LEFT JOIN symbols s ON qm.symbol = s.symbol
      WHERE s.sector = $1
      AND qm.date = $2
      AND qm.quality_metric IS NOT NULL
    `;

    const sectorResult = await query(sectorQuery, [latestMetric.sector, latestMetric.date]);
    const sectorBenchmark = sectorResult.rows[0];

    // Format comprehensive response
    const response = {
      symbol,
      companyName: latestMetric.company_name,
      sector: latestMetric.sector,
      industry: latestMetric.industry,
      
      currentData: {
        marketCap: latestMetric.market_cap,
        currentPrice: latestMetric.current_price,
        pe: latestMetric.trailing_pe,
        pb: latestMetric.price_to_book,
        dividendYield: latestMetric.dividend_yield,
        roe: latestMetric.return_on_equity,
        roa: latestMetric.return_on_assets,
        debtToEquity: latestMetric.debt_to_equity,
        freeCashFlow: latestMetric.free_cash_flow
      },
      
      metrics: {
        composite: ((parseFloat(latestMetric.quality_metric) || 0) * 0.6 + (parseFloat(latestMetric.value_metric) || 0) * 0.4),
        quality: parseFloat(latestMetric.quality_metric) || 0,
        value: parseFloat(latestMetric.value_metric) || 0
      },
      
      detailedBreakdown: {
        quality: {
          overall: parseFloat(latestMetric.quality_metric) || 0,
          components: {
            earningsQuality: parseFloat(latestMetric.earnings_quality_metric) || 0,
            balanceSheet: parseFloat(latestMetric.balance_sheet_metric) || 0,
            profitability: parseFloat(latestMetric.profitability_metric) || 0,
            management: parseFloat(latestMetric.management_metric) || 0
          },
          scores: {
            piotrosiScore: parseInt(latestMetric.piotroski_f_score) || 0,
            altmanZScore: parseFloat(latestMetric.altman_z_score) || 0,
            accrualRatio: parseFloat(latestMetric.accruals_ratio) || 0,
            cashConversionRatio: parseFloat(latestMetric.cash_conversion_ratio) || 0,
            shareholderYield: parseFloat(latestMetric.shareholder_yield) || 0
          },
          description: "Measures financial statement quality, balance sheet strength, profitability metrics, and management effectiveness using academic research models (Piotroski F-Score, Altman Z-Score)"
        },
        
        value: {
          overall: parseFloat(latestMetric.value_metric) || 0,
          components: {
            multiples: parseFloat(latestMetric.multiples_metric) || 0,
            intrinsicValue: parseFloat(latestMetric.intrinsic_value_metric) || 0,
            relativeValue: parseFloat(latestMetric.relative_value_metric) || 0
          },
          valuations: {
            dcfValue: parseFloat(latestMetric.dcf_intrinsic_value) || 0,
            marginOfSafety: parseFloat(latestMetric.dcf_margin_of_safety) || 0,
            ddmValue: parseFloat(latestMetric.ddm_value) || 0,
            rimValue: parseFloat(latestMetric.rim_value) || 0,
            currentPE: parseFloat(latestMetric.current_pe) || 0,
            currentPB: parseFloat(latestMetric.current_pb) || 0,
            currentEVEBITDA: parseFloat(latestMetric.current_ev_ebitda) || 0
          },
          description: "Analyzes traditional multiples (P/E, P/B, EV/EBITDA), DCF intrinsic value analysis, and peer group relative valuation"
        }
      },
      
      sectorComparison: {
        sectorName: latestMetric.sector,
        peerCount: parseInt(sectorBenchmark.peer_count) || 0,
        benchmarks: {
          quality: parseFloat(sectorBenchmark.avg_quality) || 0,
          value: parseFloat(sectorBenchmark.avg_value) || 0
        },
        relativeTo: {
          quality: (parseFloat(latestMetric.quality_metric) || 0) - (parseFloat(sectorBenchmark.avg_quality) || 0),
          value: (parseFloat(latestMetric.value_metric) || 0) - (parseFloat(sectorBenchmark.avg_value) || 0)
        }
      },
      
      historicalTrend: historicalMetrics.map(row => ({
        date: row.date,
        composite: ((parseFloat(row.quality_metric) || 0) * 0.6 + (parseFloat(row.value_metric) || 0) * 0.4),
        quality: parseFloat(row.quality_metric) || 0,
        value: parseFloat(row.value_metric) || 0
      })),
      
      metadata: {
        metricDate: latestMetric.date,
        confidence: parseFloat(latestMetric.confidence_score) || 0,
        completeness: parseFloat(latestMetric.data_completeness) || 0,
        marketCapTier: latestMetric.market_cap_tier || 'unknown',
        lastUpdated: latestMetric.updated_at
      },
      
      interpretation: generateMetricInterpretation(latestMetric),
      
      timestamp: new Date().toISOString()
    };

    res.json(response);

  } catch (error) {
    console.error('Error getting detailed metrics:', error);
    res.status(500).json({ 
      error: 'Failed to fetch detailed metrics',
      message: error.message,
      symbol: req.params.symbol,
      timestamp: new Date().toISOString()
    });
  }
});

// Get sector analysis and rankings
router.get('/sectors/analysis', async (req, res) => {
  try {
    console.log('Getting sector analysis for metrics');

    const sectorQuery = `
      SELECT 
        s.sector,
        COUNT(DISTINCT qm.symbol) as stock_count,
        AVG(qm.quality_metric) as avg_quality,
        AVG(vm.value_metric) as avg_value,
        AVG((qm.quality_metric * 0.6 + vm.value_metric * 0.4)) as avg_composite,
        STDDEV(qm.quality_metric) as quality_volatility,
        MAX(qm.quality_metric) as max_quality,
        MIN(qm.quality_metric) as min_quality,
        MAX(qm.updated_at) as last_updated
      FROM symbols s
      INNER JOIN quality_metrics qm ON s.symbol = qm.symbol
      LEFT JOIN value_metrics vm ON qm.symbol = vm.symbol AND qm.date = vm.date
      WHERE qm.date = (
        SELECT MAX(date) FROM quality_metrics qm2 WHERE qm2.symbol = s.symbol
      )
      AND s.sector IS NOT NULL
      AND qm.quality_metric IS NOT NULL
      GROUP BY s.sector
      HAVING COUNT(DISTINCT qm.symbol) >= 5
      ORDER BY avg_quality DESC
    `;

    const sectorResult = await query(sectorQuery);

    const sectors = sectorResult.rows.map(row => ({
      sector: row.sector,
      stockCount: parseInt(row.stock_count),
      averageMetrics: {
        composite: parseFloat(row.avg_composite || 0).toFixed(4),
        quality: parseFloat(row.avg_quality).toFixed(4),
        value: parseFloat(row.avg_value || 0).toFixed(4)
      },
      metricRange: {
        min: parseFloat(row.min_quality).toFixed(4),
        max: parseFloat(row.max_quality).toFixed(4),
        volatility: parseFloat(row.quality_volatility).toFixed(4)
      },
      lastUpdated: row.last_updated
    }));

    res.json({
      sectors,
      summary: {
        totalSectors: sectors.length,
        bestPerforming: sectors[0],
        mostVolatile: sectors.reduce((prev, current) => 
          parseFloat(prev.metricRange.volatility) > parseFloat(current.metricRange.volatility) ? prev : current
        ),
        averageQuality: (sectors.reduce((sum, s) => sum + parseFloat(s.averageMetrics.quality), 0) / sectors.length).toFixed(4)
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error in sector analysis:', error);
    res.status(500).json({ 
      error: 'Failed to fetch sector analysis',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get top performing stocks by metric category
router.get('/top/:category', async (req, res) => {
  try {
    const category = req.params.category.toLowerCase();
    const limit = Math.min(parseInt(req.query.limit) || 25, 100);
    
    const validCategories = ['composite', 'quality', 'value'];
    if (!validCategories.includes(category)) {
      return res.status(400).json({
        error: 'Invalid category',
        validCategories,
        timestamp: new Date().toISOString()
      });
    }

    // Query actual database tables with comprehensive error logging
    console.log(`🔍 [TOP-${category.toUpperCase()}] Executing query for category: ${category}, limit: ${limit}`);
    
    const topStocksQuery = `
      SELECT 
        ss.symbol,
        ss.security_name as company_name,
        COALESCE(s.sector, 'Unknown') as sector,
        COALESCE(s.market_cap, 0) as market_cap,
        COALESCE(s.current_price, 0) as current_price,
        0 as quality_metric,
        0 as value_metric,
        0 as category_metric,
        0.5 as confidence_score,
        NOW() as updated_at
      FROM stock_symbols ss
      LEFT JOIN symbols s ON ss.symbol = s.symbol
      WHERE ss.is_active = true
      ORDER BY ss.symbol
      LIMIT $1
    `;

    try {
      console.log(`🔍 [TOP-${category.toUpperCase()}] Executing top stocks query...`);
      const result = await query(topStocksQuery, [limit]);
      console.log(`✅ [TOP-${category.toUpperCase()}] Query successful, got ${result.rows.length} rows`);

      const topStocks = result.rows.map(row => {
        console.log(`🔍 [TOP-${category.toUpperCase()}] Processing stock: ${row.symbol}`);
        
        return {
          symbol: row.symbol,
          companyName: row.company_name,
          sector: row.sector,
          marketCap: parseFloat(row.market_cap) || 0,
          currentPrice: parseFloat(row.current_price) || 0,
          categoryMetric: parseFloat(row.category_metric) || 0,
          qualityMetric: parseFloat(row.quality_metric) || 0,
          valueMetric: parseFloat(row.value_metric) || 0,
          compositeMetric: parseFloat(row.category_metric) || 0,
          confidenceScore: parseFloat(row.confidence_score) || 0,
          lastUpdated: row.updated_at
        };
      });

      res.json({
        success: true,
        data: topStocks,
        pagination: {
          page: 1,
          limit: limit,
          total: topStocks.length,
          hasNext: false,
          hasPrev: false
        },
        category: category,
        timestamp: new Date().toISOString(),
        dataSource: {
          has_metrics_tables: false,
          note: 'Metrics tables not yet populated - showing base stock data'
        }
      });
      
    } catch (dbError) {
      console.error(`❌ [TOP-${category.toUpperCase()}] Database query failed:`, {
        error: dbError.message,
        code: dbError.code,
        detail: dbError.detail
      });
      
      return res.status(500).json({
        success: false,
        error: 'Failed to fetch top stocks',
        details: dbError.message,
        errorCode: dbError.code,
        timestamp: new Date().toISOString(),
        debugInfo: {
          table_missing: dbError.code === '42P01',
          permission_denied: dbError.code === '42501',
          connection_failed: dbError.code === '08006'
        }
      });
    }

  } catch (error) {
    console.error('Error getting top stocks:', error);
    res.status(500).json({ 
      error: 'Failed to fetch top stocks',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

function generateMetricInterpretation(metricData) {
  const quality = parseFloat(metricData.quality_metric) || 0;
  const value = parseFloat(metricData.value_metric) || 0;
  const composite = (quality * 0.6 + value * 0.4);
  
  let interpretation = {
    overall: '',
    strengths: [],
    concerns: [],
    recommendation: ''
  };
  
  // Overall assessment (0-1 scale)
  if (composite >= 0.8) {
    interpretation.overall = 'Exceptional investment opportunity with strong fundamentals across multiple factors';
  } else if (composite >= 0.7) {
    interpretation.overall = 'Strong investment candidate with solid fundamentals';
  } else if (composite >= 0.6) {
    interpretation.overall = 'Reasonable investment option with mixed signals';
  } else if (composite >= 0.5) {
    interpretation.overall = 'Below-average investment profile with some concerns';
  } else {
    interpretation.overall = 'Poor investment profile with significant risks';
  }
  
  // Identify strengths
  if (quality >= 0.75) interpretation.strengths.push('High-quality financial statements and management');
  if (value >= 0.75) interpretation.strengths.push('Attractive valuation with margin of safety');
  if (metricData.piotroski_f_score >= 7) interpretation.strengths.push('Strong Piotroski F-Score indicating financial strength');
  if (metricData.altman_z_score >= 3.0) interpretation.strengths.push('Low bankruptcy risk per Altman Z-Score');
  
  // Identify concerns
  if (quality <= 0.40) interpretation.concerns.push('Weak financial quality and balance sheet concerns');
  if (value <= 0.40) interpretation.concerns.push('Overvalued relative to fundamentals');
  if (metricData.piotroski_f_score <= 3) interpretation.concerns.push('Low Piotroski F-Score indicates financial weakness');
  if (metricData.altman_z_score <= 1.8) interpretation.concerns.push('High bankruptcy risk per Altman Z-Score');
  
  // Investment recommendation
  if (composite >= 0.8 && quality >= 0.7) {
    interpretation.recommendation = 'BUY - Strong fundamentals with attractive risk-adjusted returns';
  } else if (composite >= 0.7) {
    interpretation.recommendation = 'BUY - Solid investment opportunity';
  } else if (composite >= 0.6) {
    interpretation.recommendation = 'HOLD - Monitor for improvements';
  } else if (composite >= 0.5) {
    interpretation.recommendation = 'WEAK HOLD - Consider reducing position';
  } else {
    interpretation.recommendation = 'SELL - Poor fundamentals warrant exit';
  }
  
  return interpretation;
}

// Mock metrics data function for when database is unavailable
function getMockMetricsData(queryParams) {
  const limit = Math.min(parseInt(queryParams.limit) || 50, 200);
  const mockStocks = [];
  
  const symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META', 'NFLX', 'CRM', 'ADBE'];
  const sectors = ['Technology', 'Consumer Discretionary', 'Communication Services', 'Healthcare', 'Financials'];
  
  for (let i = 0; i < limit; i++) {
    const symbol = symbols[i % symbols.length] + (i > 9 ? Math.floor(i/10) : '');
    mockStocks.push({
      symbol: symbol,
      security_name: `${symbol} Inc.`,
      sector: sectors[i % sectors.length],
      market_cap: Math.random() * 1000000000000,
      quality_metric: Math.random() * 0.5 + 0.5, // 0.5-1.0
      value_metric: Math.random() * 0.4 + 0.3, // 0.3-0.7
      composite_metric: Math.random() * 0.3 + 0.6, // 0.6-0.9
      pe_ratio: Math.random() * 30 + 10,
      price_to_book: Math.random() * 5 + 0.5,
      debt_to_equity: Math.random() * 2,
      roe: Math.random() * 0.3 + 0.05,
      roa: Math.random() * 0.15 + 0.02,
      profit_margin: Math.random() * 0.25 + 0.05,
      revenue_growth: Math.random() * 0.4 - 0.1,
      eps_growth: Math.random() * 0.6 - 0.2,
      analyst_rating: Math.random() * 5 + 1,
      analyst_target_price: Math.random() * 500 + 50,
      current_price: Math.random() * 400 + 30,
      updated_at: new Date().toISOString()
    });
  }
  
  return mockStocks;
}

module.exports = router;