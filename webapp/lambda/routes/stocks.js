const express = require('express');
const { query } = require('../utils/database');

const router = express.Router();

// Basic ping endpoint
router.get('/ping', (req, res) => {
  res.json({
    status: 'ok',
    endpoint: 'stocks',
    timestamp: new Date().toISOString()
  });
});

// OPTIMIZED: Main stocks endpoint with fast queries and all data visible
router.get('/', async (req, res) => {
  try {
    console.log('OPTIMIZED Stocks main endpoint called with params:', req.query);
    
    const page = parseInt(req.query.page) || 1;
    const limit = Math.min(parseInt(req.query.limit) || 50, 200); // Increased limit
    const offset = (page - 1) * limit;
    const search = req.query.search || '';
    const sector = req.query.sector || '';
    const exchange = req.query.exchange || '';
    const sortBy = req.query.sortBy || 'symbol';
    const sortOrder = req.query.sortOrder || 'asc';
    
    let whereClause = 'WHERE 1=1';
    const params = [];
    let paramCount = 0;

    // Add search filter
    if (search) {
      paramCount++;
      whereClause += ` AND (ss.symbol ILIKE $${paramCount} OR ss.security_name ILIKE $${paramCount})`;
      params.push(`%${search}%`);
    }

    // Add sector filter (on cp.sector)
    if (sector && sector.trim() !== '') {
      paramCount++;
      whereClause += ` AND cp.sector = $${paramCount}`;
      params.push(sector);
    }

    // Add exchange filter (on ss.exchange)
    if (exchange && exchange.trim() !== '') {
      paramCount++;
      whereClause += ` AND ss.exchange = $${paramCount}`;
      params.push(exchange);
    }

    // FAST sort columns
    const validSortColumns = {
      'ticker': 'ss.symbol',
      'symbol': 'ss.symbol', 
      'name': 'ss.security_name',
      'exchange': 'ss.exchange',
      'market_category': 'ss.market_category'
    };

    const sortColumn = validSortColumns[sortBy] || 'ss.symbol';
    const sortDirection = sortOrder.toLowerCase() === 'desc' ? 'DESC' : 'ASC';

    console.log('OPTIMIZED query params:', { whereClause, params, limit, offset });

    // COMPREHENSIVE QUERY: Include ALL data from loadinfo script
    const stocksQuery = `
      SELECT 
        -- Stock symbols data
        ss.symbol,
        ss.security_name,
        ss.exchange,
        ss.market_category,
        ss.cqs_symbol,
        ss.financial_status,
        ss.round_lot_size,
        ss.etf,
        ss.secondary_symbol,
        ss.test_issue,
        
        -- Company profile data from loadinfo
        cp.short_name,
        cp.long_name,
        cp.display_name,
        cp.quote_type,
        cp.sector,
        cp.sector_disp,
        cp.industry,
        cp.industry_disp,
        cp.business_summary,
        cp.employee_count,
        cp.website_url,
        cp.ir_website_url,
        cp.address1,
        cp.city,
        cp.state,
        cp.postal_code,
        cp.country,
        cp.phone_number,
        cp.currency,
        cp.market,
        cp.full_exchange_name,
        
        -- Market data from loadinfo
        md.current_price,
        md.previous_close,
        md.open_price,
        md.day_low,
        md.day_high,
        md.volume,
        md.average_volume,
        md.market_cap,
        md.fifty_two_week_low,
        md.fifty_two_week_high,
        md.fifty_day_avg,
        md.two_hundred_day_avg,
        md.bid_price,
        md.ask_price,
        md.market_state,
        
        -- Key financial metrics from loadinfo
        km.trailing_pe,
        km.forward_pe,
        km.price_to_sales_ttm,
        km.price_to_book,
        km.book_value,
        km.peg_ratio,
        km.enterprise_value,
        km.ev_to_revenue,
        km.ev_to_ebitda,
        km.total_revenue,
        km.net_income,
        km.ebitda,
        km.gross_profit,
        km.eps_trailing,
        km.eps_forward,
        km.eps_current_year,
        km.price_eps_current_year,
        km.earnings_q_growth_pct,
        km.total_cash,
        km.cash_per_share,
        km.operating_cashflow,
        km.free_cashflow,
        km.total_debt,
        km.debt_to_equity,
        km.quick_ratio,
        km.current_ratio,
        km.profit_margin_pct,
        km.gross_margin_pct,
        km.ebitda_margin_pct,
        km.operating_margin_pct,
        km.return_on_assets_pct,
        km.return_on_equity_pct,
        km.revenue_growth_pct,
        km.earnings_growth_pct,
        km.dividend_rate,
        km.dividend_yield,
        km.five_year_avg_dividend_yield,
        km.payout_ratio,
        
        -- Analyst estimates from loadinfo
        ae.target_high_price,
        ae.target_low_price,
        ae.target_mean_price,
        ae.target_median_price,
        ae.recommendation_key,
        ae.recommendation_mean,
        ae.analyst_opinion_count,
        ae.average_analyst_rating,
        
        -- Governance scores from loadinfo
        gs.audit_risk,
        gs.board_risk,
        gs.compensation_risk,
        gs.shareholder_rights_risk,
        gs.overall_risk,
        
        -- Leadership team count (subquery)
        COALESCE(lt_count.executive_count, 0) as leadership_count
        
      FROM stock_symbols ss
      LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
      LEFT JOIN market_data md ON ss.symbol = md.ticker
      LEFT JOIN key_metrics km ON ss.symbol = km.ticker
      LEFT JOIN analyst_estimates ae ON ss.symbol = ae.ticker
      LEFT JOIN governance_scores gs ON ss.symbol = gs.ticker
      LEFT JOIN (
        SELECT ticker, COUNT(*) as executive_count 
        FROM leadership_team 
        GROUP BY ticker
      ) lt_count ON ss.symbol = lt_count.ticker
      ${whereClause}
      ORDER BY ${sortColumn} ${sortDirection}
      LIMIT $${paramCount + 1} OFFSET $${paramCount + 2}
    `;

    params.push(limit, offset);

    // Count query - also fast
    const countQuery = `
      SELECT COUNT(*) as total
      FROM stock_symbols ss
      ${whereClause}
    `;

    console.log('Executing FAST queries...');

    const [stocksResult, countResult] = await Promise.all([
      query(stocksQuery, params),
      query(countQuery, params.slice(0, -2))
    ]);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    console.log(`FAST query results: ${stocksResult.rows.length} stocks, ${total} total`);

    // Professional formatting with ALL comprehensive data from loadinfo
    const formattedStocks = stocksResult.rows.map(stock => ({
      // Core identification
      ticker: stock.symbol,
      symbol: stock.symbol,
      name: stock.security_name,
      fullName: stock.long_name || stock.security_name,
      shortName: stock.short_name,
      displayName: stock.display_name,
      
      // Exchange & categorization 
      exchange: stock.exchange,
      fullExchangeName: stock.full_exchange_name,
      marketCategory: stock.market_category,
      market: stock.market,
      
      // Business information
      sector: stock.sector,
      sectorDisplay: stock.sector_disp,
      industry: stock.industry,
      industryDisplay: stock.industry_disp,
      businessSummary: stock.business_summary,
      employeeCount: stock.employee_count,
      
      // Contact information
      website: stock.website_url,
      investorRelationsWebsite: stock.ir_website_url,
      address: {
        street: stock.address1,
        city: stock.city,
        state: stock.state,
        postalCode: stock.postal_code,
        country: stock.country
      },
      phoneNumber: stock.phone_number,
      
      // Financial details
      currency: stock.currency,
      quoteType: stock.quote_type,
      
      // Current market data
      price: {
        current: stock.current_price,
        previousClose: stock.previous_close,
        open: stock.open_price,
        dayLow: stock.day_low,
        dayHigh: stock.day_high,
        fiftyTwoWeekLow: stock.fifty_two_week_low,
        fiftyTwoWeekHigh: stock.fifty_two_week_high,
        fiftyDayAverage: stock.fifty_day_avg,
        twoHundredDayAverage: stock.two_hundred_day_avg,
        bid: stock.bid_price,
        ask: stock.ask_price,
        marketState: stock.market_state
      },
      
      // Volume data
      volume: stock.volume,
      averageVolume: stock.average_volume,
      marketCap: stock.market_cap,
      
      // Comprehensive financial metrics
      financialMetrics: {
        // Valuation ratios
        trailingPE: stock.trailing_pe,
        forwardPE: stock.forward_pe,
        priceToSales: stock.price_to_sales_ttm,
        priceToBook: stock.price_to_book,
        pegRatio: stock.peg_ratio,
        bookValue: stock.book_value,
        
        // Enterprise metrics
        enterpriseValue: stock.enterprise_value,
        evToRevenue: stock.ev_to_revenue,
        evToEbitda: stock.ev_to_ebitda,
        
        // Financial results
        totalRevenue: stock.total_revenue,
        netIncome: stock.net_income,
        ebitda: stock.ebitda,
        grossProfit: stock.gross_profit,
        
        // Earnings per share
        epsTrailing: stock.eps_trailing,
        epsForward: stock.eps_forward,
        epsCurrent: stock.eps_current_year,
        priceEpsCurrent: stock.price_eps_current_year,
        
        // Growth metrics
        earningsGrowthQuarterly: stock.earnings_q_growth_pct,
        revenueGrowth: stock.revenue_growth_pct,
        earningsGrowth: stock.earnings_growth_pct,
        
        // Cash & debt
        totalCash: stock.total_cash,
        cashPerShare: stock.cash_per_share,
        operatingCashflow: stock.operating_cashflow,
        freeCashflow: stock.free_cashflow,
        totalDebt: stock.total_debt,
        debtToEquity: stock.debt_to_equity,
        
        // Liquidity ratios
        quickRatio: stock.quick_ratio,
        currentRatio: stock.current_ratio,
        
        // Profitability margins
        profitMargin: stock.profit_margin_pct,
        grossMargin: stock.gross_margin_pct,
        ebitdaMargin: stock.ebitda_margin_pct,
        operatingMargin: stock.operating_margin_pct,
        
        // Return metrics
        returnOnAssets: stock.return_on_assets_pct,
        returnOnEquity: stock.return_on_equity_pct,
        
        // Dividend information
        dividendRate: stock.dividend_rate,
        dividendYield: stock.dividend_yield,
        fiveYearAvgDividendYield: stock.five_year_avg_dividend_yield,
        payoutRatio: stock.payout_ratio
      },
      
      // Analyst estimates and recommendations
      analystData: {
        targetPrices: {
          high: stock.target_high_price,
          low: stock.target_low_price,
          mean: stock.target_mean_price,
          median: stock.target_median_price
        },
        recommendation: {
          key: stock.recommendation_key,
          mean: stock.recommendation_mean,
          rating: stock.average_analyst_rating
        },
        analystCount: stock.analyst_opinion_count
      },
      
      // Governance data
      governance: {
        auditRisk: stock.audit_risk,
        boardRisk: stock.board_risk,
        compensationRisk: stock.compensation_risk,
        shareholderRightsRisk: stock.shareholder_rights_risk,
        overallRisk: stock.overall_risk
      },
      
      // Leadership team summary
      leadership: {
        executiveCount: stock.leadership_count,
        hasLeadershipData: stock.leadership_count > 0,
        // Full leadership data available via /leadership/:ticker endpoint
        detailsAvailable: true
      },
      
      // Additional identifiers
      cqsSymbol: stock.cqs_symbol,
      secondarySymbol: stock.secondary_symbol,
      
      // Status & type
      financialStatus: stock.financial_status,
      isEtf: stock.etf === 'Y',
      testIssue: stock.test_issue === 'Y',
      roundLotSize: stock.round_lot_size,
      
      // Comprehensive data availability indicators
      hasData: true,
      dataSource: 'comprehensive_loadinfo_query',
      hasCompanyProfile: !!stock.long_name,
      hasMarketData: !!stock.current_price,
      hasFinancialMetrics: !!stock.trailing_pe || !!stock.total_revenue,
      hasAnalystData: !!stock.target_mean_price || !!stock.recommendation_key,
      hasGovernanceData: !!stock.overall_risk,
      hasLeadershipData: stock.leadership_count > 0,
      
      // Professional presentation with rich data
      displayData: {
        primaryExchange: stock.full_exchange_name || stock.exchange || 'Unknown',
        category: stock.market_category || 'Standard',
        type: stock.etf === 'Y' ? 'ETF' : 'Stock',
        tradeable: stock.financial_status !== 'D' && stock.test_issue !== 'Y',
        sector: stock.sector_disp || stock.sector || 'Unknown',
        industry: stock.industry_disp || stock.industry || 'Unknown',
        
        // Key financial highlights for quick view
        keyMetrics: {
          pe: stock.trailing_pe,
          marketCap: stock.market_cap,
          revenue: stock.total_revenue,
          profitMargin: stock.profit_margin_pct,
          dividendYield: stock.dividend_yield,
          analystRating: stock.recommendation_key,
          targetPrice: stock.target_mean_price
        },
        
        // Risk summary
        riskProfile: {
          overall: stock.overall_risk,
          hasHighRisk: (stock.overall_risk && stock.overall_risk >= 8),
          hasModerateRisk: (stock.overall_risk && stock.overall_risk >= 5 && stock.overall_risk < 8),
          hasLowRisk: (stock.overall_risk && stock.overall_risk < 5)
        }
      }
    }));

    res.json({
      success: true,
      performance: 'COMPREHENSIVE LOADINFO DATA - All company profiles, market data, financial metrics, analyst estimates, and governance scores from loadinfo tables',
      data: formattedStocks,
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1
      },
      filters: {
        search: search || null,
        exchange: exchange || null,
        sortBy,
        sortOrder
      },
      metadata: {
        totalStocks: total,
        currentPage: page,
        showingRecords: stocksResult.rows.length,
        dataFields: [
          // Basic stock symbol data
          'symbol', 'security_name', 'exchange', 'market_category',
          'cqs_symbol', 'financial_status', 'etf', 'round_lot_size', 
          'test_issue', 'secondary_symbol',
          
          // Company profile data
          'short_name', 'long_name', 'display_name', 'quote_type',
          'sector', 'sector_disp', 'industry', 'industry_disp',
          'business_summary', 'employee_count', 'website_url', 
          'ir_website_url', 'address1', 'city', 'state', 'postal_code',
          'country', 'phone_number', 'currency', 'market', 'full_exchange_name',
          
          // Market data
          'current_price', 'previous_close', 'open_price', 'day_low', 'day_high',
          'volume', 'average_volume', 'market_cap', 'fifty_two_week_low',
          'fifty_two_week_high', 'fifty_day_avg', 'two_hundred_day_avg',
          'bid_price', 'ask_price', 'market_state',
          
          // Financial metrics
          'trailing_pe', 'forward_pe', 'price_to_sales_ttm', 'price_to_book',
          'book_value', 'peg_ratio', 'enterprise_value', 'ev_to_revenue',
          'ev_to_ebitda', 'total_revenue', 'net_income', 'ebitda', 'gross_profit',
          'eps_trailing', 'eps_forward', 'eps_current_year', 'earnings_q_growth_pct',
          'total_cash', 'cash_per_share', 'operating_cashflow', 'free_cashflow',
          'total_debt', 'debt_to_equity', 'quick_ratio', 'current_ratio',
          'profit_margin_pct', 'gross_margin_pct', 'ebitda_margin_pct',
          'operating_margin_pct', 'return_on_assets_pct', 'return_on_equity_pct',
          'revenue_growth_pct', 'earnings_growth_pct', 'dividend_rate',
          'dividend_yield', 'five_year_avg_dividend_yield', 'payout_ratio',
          
          // Analyst estimates
          'target_high_price', 'target_low_price', 'target_mean_price',
          'target_median_price', 'recommendation_key', 'recommendation_mean',
          'analyst_opinion_count', 'average_analyst_rating',
          
          // Governance data
          'audit_risk', 'board_risk', 'compensation_risk', 'shareholder_rights_risk',
          'overall_risk'
        ],
        dataSources: [
          'stock_symbols', 'company_profile', 'market_data', 'key_metrics',
          'analyst_estimates', 'governance_scores', 'leadership_team'
        ],
        comprehensiveData: {
          includesCompanyProfiles: true,
          includesMarketData: true,
          includesFinancialMetrics: true,
          includesAnalystEstimates: true,
          includesGovernanceScores: true,
          includesLeadershipTeam: true // Count included, details via /leadership/:ticker
        },
        endpoints: {
          leadershipDetails: '/api/stocks/leadership/:ticker',
          leadershipSummary: '/api/stocks/leadership'
        }
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('OPTIMIZED endpoint error:', error);
    res.status(500).json({ 
      error: 'Optimized query failed',
      details: error.message,
      data: [], // Always return data as an array for frontend safety
      timestamp: new Date().toISOString()
    });
  }
});

// SIMPLIFIED Individual Stock Endpoint - Fast and reliable
router.get('/:ticker', async (req, res) => {
  try {
    const { ticker } = req.params;
    const tickerUpper = ticker.toUpperCase();
    
    console.log(`SIMPLIFIED stock endpoint called for: ${tickerUpper}`);
    
    // SINGLE OPTIMIZED QUERY - Get everything we need in one go
    const stockQuery = `
      SELECT 
        ss.symbol,
        ss.security_name,
        ss.exchange,
        ss.market_category,
        ss.financial_status,
        ss.etf,
        pd.date as latest_date,
        pd.open,
        pd.high,
        pd.low,
        pd.close,
        pd.volume,
        pd.adj_close
      FROM stock_symbols ss
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) 
          symbol, date, open, high, low, close, volume, adj_close
        FROM price_daily
        WHERE symbol = $1
        ORDER BY symbol, date DESC
      ) pd ON ss.symbol = pd.symbol
      WHERE ss.symbol = $1
    `;
    
    const result = await query(stockQuery, [tickerUpper]);
    
    if (result.rows.length === 0) {
      return res.status(404).json({
        error: 'Stock not found',
        symbol: tickerUpper,
        message: `Symbol '${tickerUpper}' not found in database`,
        timestamp: new Date().toISOString()
      });
    }
    
    const stock = result.rows[0];
    
    // SIMPLE RESPONSE - Just the essential data
    const response = {
      symbol: tickerUpper,
      ticker: tickerUpper,
      companyInfo: {
        name: stock.security_name,
        exchange: stock.exchange,
        marketCategory: stock.market_category,
        financialStatus: stock.financial_status,
        isETF: stock.etf === 't' || stock.etf === true
      },
      currentPrice: stock.close ? {
        date: stock.latest_date,
        open: parseFloat(stock.open || 0),
        high: parseFloat(stock.high || 0),
        low: parseFloat(stock.low || 0),
        close: parseFloat(stock.close || 0),
        adjClose: parseFloat(stock.adj_close || stock.close || 0),
        volume: parseInt(stock.volume || 0)
      } : null,
      metadata: {
        requestedSymbol: ticker,
        resolvedSymbol: tickerUpper,
        dataAvailability: {
          basicInfo: true,
          priceData: stock.close !== null,
          technicalIndicators: false, // Disabled for speed
          fundamentals: false // Disabled for speed
        },
        timestamp: new Date().toISOString()
      }
    };
    
    console.log(`✅ SIMPLIFIED: Successfully returned basic data for ${tickerUpper}`);
    
    res.json(response);
    
  } catch (error) {
    console.error('Error in simplified stock endpoint:', error);
    res.status(500).json({ 
      error: 'Failed to fetch stock data', 
      symbol: req.params.ticker,
      message: error.message,
      data: [], // Always return data as an array for frontend safety
      timestamp: new Date().toISOString()
    });
  }
});

// Get stock price history 
router.get('/:ticker/prices', async (req, res) => {
  try {
    const { ticker } = req.params;
    const limit = Math.min(parseInt(req.query.limit) || 30, 90); // Max 90 days for performance
    
    console.log(`SIMPLIFIED prices endpoint called for ticker: ${ticker}, limit: ${limit}`);
    
    const pricesQuery = `
      SELECT date, open, high, low, close, adj_close, volume
      FROM price_daily
      WHERE UPPER(symbol) = UPPER($1)
      ORDER BY date DESC
      LIMIT $2
    `;
    
    const result = await query(pricesQuery, [ticker, limit]);
    
    if (result.rows.length === 0) {
      return res.status(404).json({
        error: 'No price data found',
        ticker: ticker.toUpperCase(),
        message: 'Price data not available for this symbol',
        timestamp: new Date().toISOString()
      });
    }
    
    // Simple response
    const prices = result.rows;
    const latest = prices[0];
    const oldest = prices[prices.length - 1];

    const periodReturn = oldest.close > 0 ? 
      ((latest.close - oldest.close) / oldest.close * 100) : 0;

    // Add priceChange and priceChangePct to each record
    const pricesWithChange = prices.map((price, idx) => {
      let priceChange = null, priceChangePct = null;
      if (idx < prices.length - 1) {
        const prev = prices[idx + 1];
        priceChange = price.close - prev.close;
        priceChangePct = prev.close !== 0 ? priceChange / prev.close : null;
      }
      return {
        date: price.date,
        open: parseFloat(price.open),
        high: parseFloat(price.high),
        low: parseFloat(price.low),
        close: parseFloat(price.close),
        adjClose: parseFloat(price.adj_close),
        volume: parseInt(price.volume) || 0,
        priceChange,
        priceChangePct
      };
    });

    res.json({
      success: true,
      ticker: ticker.toUpperCase(),
      dataPoints: result.rows.length,
      data: pricesWithChange,
      summary: {
        latestPrice: parseFloat(latest.close),
        latestDate: latest.date,
        periodReturn: parseFloat(periodReturn.toFixed(2)),
        latestVolume: parseInt(latest.volume) || 0
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error fetching stock prices:', error);
    res.status(500).json({ 
      error: 'Failed to fetch stock prices', 
      details: error.message,
      data: [], // Always return data as an array for frontend safety
      ticker: req.params.ticker,
      timestamp: new Date().toISOString()
    });
  }
});

// Get available filters - exchanges instead of sectors
router.get('/filters/sectors', async (req, res) => {
  try {
    console.log('Stock filters/sectors (exchanges) endpoint called');
    
    const sectorsQuery = `
      SELECT exchange, COUNT(*) as count
      FROM stock_symbols
      WHERE exchange IS NOT NULL
      GROUP BY exchange
      ORDER BY count DESC, exchange ASC
    `;
    
    const result = await query(sectorsQuery);
    
    res.json({
      data: result.rows.map(row => ({
        name: row.exchange,
        value: row.exchange,
        count: parseInt(row.count)
      })),
      total: result.rows.length,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error fetching stock exchanges:', error);
    res.status(500).json({ 
      error: 'Failed to fetch stock exchanges', 
      details: error.message,
      data: [], // Always return data as an array for frontend safety
      timestamp: new Date().toISOString()
    });
  }
});

// Screen stocks with advanced filtering - THE KEY ENDPOINT THE FRONTEND USES
router.get('/screen', async (req, res) => {
  try {
    console.log('Screen endpoint called with params:', req.query);
    
    const page = parseInt(req.query.page) || 1;
    const limit = Math.min(parseInt(req.query.limit) || 25, 100);
    const offset = (page - 1) * limit;
    const search = req.query.search || '';
    const sector = req.query.sector || '';
    const exchange = req.query.exchange || '';
    const sortBy = req.query.sortBy || 'symbol';
    const sortOrder = req.query.sortOrder || 'asc';
    
    let whereClause = 'WHERE 1=1';
    const params = [];
    let paramCount = 0;

    // Add search filter
    if (search) {
      paramCount++;
      whereClause += ` AND (ss.symbol ILIKE $${paramCount} OR ss.security_name ILIKE $${paramCount})`;
      params.push(`%${search}%`);
    }

    // Add sector filter (on cp.sector)
    if (sector && sector.trim() !== '') {
      paramCount++;
      whereClause += ` AND cp.sector = $${paramCount}`;
      params.push(sector);
    }

    // Add exchange filter (on ss.exchange)
    if (exchange && exchange.trim() !== '') {
      paramCount++;
      whereClause += ` AND ss.exchange = $${paramCount}`;
      params.push(exchange);
    }

    // FAST sort columns
    const validSortColumns = {
      'ticker': 'ss.symbol',
      'symbol': 'ss.symbol', 
      'name': 'ss.security_name',
      'exchange': 'ss.exchange',
      'market_category': 'ss.market_category'
    };

    const sortColumn = validSortColumns[sortBy] || 'ss.symbol';
    const sortDirection = sortOrder.toLowerCase() === 'desc' ? 'DESC' : 'ASC';

    console.log('Screen query params:', { whereClause, params, limit, offset });

    // Use the same comprehensive query as the main endpoint but for screening
    const stocksQuery = `
      SELECT 
        -- Stock symbols data
        ss.symbol,
        ss.security_name,
        ss.exchange,
        ss.market_category,
        ss.cqs_symbol,
        ss.financial_status,
        ss.round_lot_size,
        ss.etf,
        ss.secondary_symbol,
        ss.test_issue,
        
        -- Company profile data from loadinfo
        cp.short_name,
        cp.long_name,
        cp.display_name,
        cp.quote_type,
        cp.sector,
        cp.sector_disp,
        cp.industry,
        cp.industry_disp,
        cp.business_summary,
        cp.employee_count,
        cp.website_url,
        cp.ir_website_url,
        cp.address1,
        cp.city,
        cp.state,
        cp.postal_code,
        cp.country,
        cp.phone_number,
        cp.currency,
        cp.market,
        cp.full_exchange_name,
        
        -- Market data from loadinfo
        md.current_price,
        md.previous_close,
        md.open_price,
        md.day_low,
        md.day_high,
        md.volume,
        md.average_volume,
        md.market_cap,
        md.fifty_two_week_low,
        md.fifty_two_week_high,
        md.fifty_day_avg,
        md.two_hundred_day_avg,
        md.bid_price,
        md.ask_price,
        md.market_state,
        
        -- Key financial metrics from loadinfo
        km.trailing_pe,
        km.forward_pe,
        km.price_to_sales_ttm,
        km.price_to_book,
        km.book_value,
        km.peg_ratio,
        km.enterprise_value,
        km.ev_to_revenue,
        km.ev_to_ebitda,
        km.total_revenue,
        km.net_income,
        km.ebitda,
        km.gross_profit,
        km.eps_trailing,
        km.eps_forward,
        km.eps_current_year,
        km.price_eps_current_year,
        km.earnings_q_growth_pct,
        km.total_cash,
        km.cash_per_share,
        km.operating_cashflow,
        km.free_cashflow,
        km.total_debt,
        km.debt_to_equity,
        km.quick_ratio,
        km.current_ratio,
        km.profit_margin_pct,
        km.gross_margin_pct,
        km.ebitda_margin_pct,
        km.operating_margin_pct,
        km.return_on_assets_pct,
        km.return_on_equity_pct,
        km.revenue_growth_pct,
        km.earnings_growth_pct,
        km.dividend_rate,
        km.dividend_yield,
        km.five_year_avg_dividend_yield,
        km.payout_ratio,
        
        -- Analyst estimates from loadinfo
        ae.target_high_price,
        ae.target_low_price,
        ae.target_mean_price,
        ae.target_median_price,
        ae.recommendation_key,
        ae.recommendation_mean,
        ae.analyst_opinion_count,
        ae.average_analyst_rating,
        
        -- Governance scores from loadinfo
        gs.audit_risk,
        gs.board_risk,
        gs.compensation_risk,
        gs.shareholder_rights_risk,
        gs.overall_risk,
        
        -- Leadership team count (subquery)
        COALESCE(lt_count.executive_count, 0) as leadership_count
        
      FROM stock_symbols ss
      LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
      LEFT JOIN market_data md ON ss.symbol = md.ticker
      LEFT JOIN key_metrics km ON ss.symbol = km.ticker
      LEFT JOIN analyst_estimates ae ON ss.symbol = ae.ticker
      LEFT JOIN governance_scores gs ON ss.symbol = gs.ticker
      LEFT JOIN (
        SELECT ticker, COUNT(*) as executive_count 
        FROM leadership_team 
        GROUP BY ticker
      ) lt_count ON ss.symbol = lt_count.ticker
      ${whereClause}
      ORDER BY ${sortColumn} ${sortDirection}
      LIMIT $${paramCount + 1} OFFSET $${paramCount + 2}
    `;

    params.push(limit, offset);

    // Count query
    const countQuery = `
      SELECT COUNT(*) as total
      FROM stock_symbols ss
      LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
      ${whereClause}
    `;

    console.log('Executing screen queries...');

    const [stocksResult, countResult] = await Promise.all([
      query(stocksQuery, params),
      query(countQuery, params.slice(0, -2))
    ]);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    console.log(`Screen query results: ${stocksResult.rows.length} stocks, ${total} total`);

    // Use the same formatting as the main endpoint
    const formattedStocks = stocksResult.rows.map(stock => ({
      // Core identification
      ticker: stock.symbol,
      symbol: stock.symbol,
      name: stock.security_name,
      fullName: stock.long_name || stock.security_name,
      shortName: stock.short_name,
      displayName: stock.display_name,
      
      // Exchange & categorization 
      exchange: stock.exchange,
      fullExchangeName: stock.full_exchange_name,
      marketCategory: stock.market_category,
      market: stock.market,
      
      // Business information
      sector: stock.sector,
      sectorDisplay: stock.sector_disp,
      industry: stock.industry,
      industryDisplay: stock.industry_disp,
      businessSummary: stock.business_summary,
      employeeCount: stock.employee_count,
      
      // Contact information
      website: stock.website_url,
      investorRelationsWebsite: stock.ir_website_url,
      address: {
        street: stock.address1,
        city: stock.city,
        state: stock.state,
        postalCode: stock.postal_code,
        country: stock.country
      },
      phoneNumber: stock.phone_number,
      
      // Financial details
      currency: stock.currency,
      quoteType: stock.quote_type,
      
      // Current market data
      price: {
        current: stock.current_price,
        previousClose: stock.previous_close,
        open: stock.open_price,
        dayLow: stock.day_low,
        dayHigh: stock.day_high,
        fiftyTwoWeekLow: stock.fifty_two_week_low,
        fiftyTwoWeekHigh: stock.fifty_two_week_high,
        fiftyDayAverage: stock.fifty_day_avg,
        twoHundredDayAverage: stock.two_hundred_day_avg,
        bid: stock.bid_price,
        ask: stock.ask_price,
        marketState: stock.market_state
      },
      
      // Volume data
      volume: stock.volume,
      averageVolume: stock.average_volume,
      marketCap: stock.market_cap,
      
      // Comprehensive financial metrics
      financialMetrics: {
        // Valuation ratios
        trailingPE: stock.trailing_pe,
        forwardPE: stock.forward_pe,
        priceToSales: stock.price_to_sales_ttm,
        priceToBook: stock.price_to_book,
        pegRatio: stock.peg_ratio,
        bookValue: stock.book_value,
        
        // Enterprise metrics
        enterpriseValue: stock.enterprise_value,
        evToRevenue: stock.ev_to_revenue,
        evToEbitda: stock.ev_to_ebitda,
        
        // Financial results
        totalRevenue: stock.total_revenue,
        netIncome: stock.net_income,
        ebitda: stock.ebitda,
        grossProfit: stock.gross_profit,
        
        // Earnings per share
        epsTrailing: stock.eps_trailing,
        epsForward: stock.eps_forward,
        epsCurrent: stock.eps_current_year,
        priceEpsCurrent: stock.price_eps_current_year,
        
        // Growth metrics
        earningsGrowthQuarterly: stock.earnings_q_growth_pct,
        revenueGrowth: stock.revenue_growth_pct,
        earningsGrowth: stock.earnings_growth_pct,
        
        // Cash & debt
        totalCash: stock.total_cash,
        cashPerShare: stock.cash_per_share,
        operatingCashflow: stock.operating_cashflow,
        freeCashflow: stock.free_cashflow,
        totalDebt: stock.total_debt,
        debtToEquity: stock.debt_to_equity,
        
        // Liquidity ratios
        quickRatio: stock.quick_ratio,
        currentRatio: stock.current_ratio,
        
        // Profitability margins
        profitMargin: stock.profit_margin_pct,
        grossMargin: stock.gross_margin_pct,
        ebitdaMargin: stock.ebitda_margin_pct,
        operatingMargin: stock.operating_margin_pct,
        
        // Return metrics
        returnOnAssets: stock.return_on_assets_pct,
        returnOnEquity: stock.return_on_equity_pct,
        
        // Dividend information
        dividendRate: stock.dividend_rate,
        dividendYield: stock.dividend_yield,
        fiveYearAvgDividendYield: stock.five_year_avg_dividend_yield,
        payoutRatio: stock.payout_ratio
      },
      
      // Analyst estimates and recommendations
      analystData: {
        targetPrices: {
          high: stock.target_high_price,
          low: stock.target_low_price,
          mean: stock.target_mean_price,
          median: stock.target_median_price
        },
        recommendation: {
          key: stock.recommendation_key,
          mean: stock.recommendation_mean,
          rating: stock.average_analyst_rating
        },
        analystCount: stock.analyst_opinion_count
      },
      
      // Governance data
      governance: {
        auditRisk: stock.audit_risk,
        boardRisk: stock.board_risk,
        compensationRisk: stock.compensation_risk,
        shareholderRightsRisk: stock.shareholder_rights_risk,
        overallRisk: stock.overall_risk
      },
      
      // Leadership team summary
      leadership: {
        executiveCount: stock.leadership_count,
        hasLeadershipData: stock.leadership_count > 0,
        detailsAvailable: true
      },
      
      // Additional identifiers
      cqsSymbol: stock.cqs_symbol,
      secondarySymbol: stock.secondary_symbol,
      
      // Status & type
      financialStatus: stock.financial_status,
      isEtf: stock.etf === 'Y',
      testIssue: stock.test_issue === 'Y',
      roundLotSize: stock.round_lot_size,
      
      // Comprehensive data availability indicators
      hasData: true,
      dataSource: 'comprehensive_loadinfo_query',
      hasCompanyProfile: !!stock.long_name,
      hasMarketData: !!stock.current_price,
      hasFinancialMetrics: !!stock.trailing_pe || !!stock.total_revenue,
      hasAnalystData: !!stock.target_mean_price || !!stock.recommendation_key,
      hasGovernanceData: !!stock.overall_risk,
      hasLeadershipData: stock.leadership_count > 0,
      
      // Professional presentation with rich data
      displayData: {
        primaryExchange: stock.full_exchange_name || stock.exchange || 'Unknown',
        category: stock.market_category || 'Standard',
        type: stock.etf === 'Y' ? 'ETF' : 'Stock',
        tradeable: stock.financial_status !== 'D' && stock.test_issue !== 'Y',
        sector: stock.sector_disp || stock.sector || 'Unknown',
        industry: stock.industry_disp || stock.industry || 'Unknown',
        
        // Key financial highlights for quick view
        keyMetrics: {
          pe: stock.trailing_pe,
          marketCap: stock.market_cap,
          revenue: stock.total_revenue,
          profitMargin: stock.profit_margin_pct,
          dividendYield: stock.dividend_yield,
          analystRating: stock.recommendation_key,
          targetPrice: stock.target_mean_price
        },
        
        // Risk summary
        riskProfile: {
          overall: stock.overall_risk,
          hasHighRisk: (stock.overall_risk && stock.overall_risk >= 8),
          hasModerateRisk: (stock.overall_risk && stock.overall_risk >= 5 && stock.overall_risk < 8),
          hasLowRisk: (stock.overall_risk && stock.overall_risk < 5)
        }
      }
    }));

    res.json({
      success: true,
      data: formattedStocks,
      total: total,
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1
      },
      filters: {
        search: search || null,
        sector: sector || null,
        exchange: exchange || null,
        sortBy,
        sortOrder
      },
      metadata: {
        totalStocks: total,
        currentPage: page,
        showingRecords: stocksResult.rows.length
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Screen endpoint error:', error);
    res.status(500).json({ 
      success: false,
      error: 'Screen query failed',
      details: error.message,
      data: [], // Always return data as an array for frontend safety
      timestamp: new Date().toISOString()
    });
  }
});

module.exports = router;
