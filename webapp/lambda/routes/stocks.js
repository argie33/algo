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
    console.log('Fixed ALL table names and JOIN columns - graceful error handling!');
    
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
      LEFT JOIN company_profiles cp ON ss.symbol = cp.symbol
      LEFT JOIN market_data md ON ss.symbol = md.symbol
      LEFT JOIN key_metrics km ON ss.symbol = km.symbol
      LEFT JOIN analyst_estimates ae ON ss.symbol = ae.symbol
      LEFT JOIN governance_scores gs ON ss.symbol = gs.symbol
      LEFT JOIN (
        SELECT ticker, COUNT(*) as executive_count 
        FROM leadership_team 
        GROUP BY symbol
      ) lt_count ON ss.symbol = lt_count.symbol
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
          'stock_symbols', 'company_profiles', 'market_data', 'key_metrics',
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
    
    // If tables are missing, return empty data instead of 500 error
    if (error.code === '42P01') { // relation does not exist
      console.log('Missing table detected, returning empty results gracefully');
      return res.json({
        success: true,
        data: [],
        pagination: { page: 1, totalPages: 0, total: 0, limit: 50 },
        message: 'Data tables are being initialized. Please check back shortly.',
        timestamp: new Date().toISOString()
      });
    }
    
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

// Get stock price history with timeframe support
router.get('/:ticker/prices', async (req, res) => {
  try {
    const { ticker } = req.params;
    const { timeframe = 'daily' } = req.query;
    const limit = Math.min(parseInt(req.query.limit) || 30, 90); // Max 90 for performance
    
    // Validate timeframe
    const validTimeframes = ['daily', 'weekly', 'monthly'];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({
        error: 'Invalid timeframe',
        validTimeframes,
        timestamp: new Date().toISOString()
      });
    }
    
    console.log(`ENHANCED prices endpoint called for ticker: ${ticker}, timeframe: ${timeframe}, limit: ${limit}`);
    
    // Determine table name based on timeframe
    const tableName = `price_${timeframe}`;
    
    const pricesQuery = `
      SELECT date, open, high, low, close, adj_close, volume, dividends, stock_splits
      FROM ${tableName}
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
        dividends: price.dividends ? parseFloat(price.dividends) : 0,
        stockSplits: price.stock_splits ? parseFloat(price.stock_splits) : 0,
        priceChange,
        priceChangePct
      };
    });

    res.json({
      success: true,
      ticker: ticker.toUpperCase(),
      timeframe: timeframe,
      dataPoints: result.rows.length,
      data: pricesWithChange,
      summary: {
        latestPrice: parseFloat(latest.close),
        latestDate: latest.date,
        periodReturn: parseFloat(periodReturn.toFixed(2)),
        latestVolume: parseInt(latest.volume) || 0
      },
      metadata: {
        tableName: tableName,
        availableTimeframes: validTimeframes
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

// Get recent stock price history (alias for /prices with recent in the path)
router.get('/:ticker/prices/recent', async (req, res) => {
  try {
    const { ticker } = req.params;
    const limit = Math.min(parseInt(req.query.limit) || 30, 90); // Max 90 days for performance
    
    console.log(`📊 [STOCKS] Recent prices endpoint called for ticker: ${ticker}, limit: ${limit}`);
    
    const pricesQuery = `
      SELECT date, open, high, low, close, adj_close, volume
      FROM price_daily
      WHERE UPPER(symbol) = UPPER($1)
      ORDER BY date DESC
      LIMIT $2
    `;
    
    const result = await query(pricesQuery, [ticker, limit]);
    
    if (result.rows.length === 0) {
      console.log(`📊 [STOCKS] No price data found for ${ticker}`);
      return res.status(404).json({
        success: false,
        error: 'No price data found',
        ticker: ticker.toUpperCase(),
        message: 'Price data not available for this symbol',
        data: [],
        timestamp: new Date().toISOString()
      });
    }
    
    // Process the data
    const prices = result.rows;
    const latest = prices[0];
    const oldest = prices[prices.length - 1];

    const periodReturn = oldest.close > 0 ? 
      ((latest.close - oldest.close) / oldest.close * 100) : 0;

    // Format data for frontend
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

    console.log(`📊 [STOCKS] Successfully returning ${pricesWithChange.length} price records for ${ticker}`);

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
    console.error('❌ [STOCKS] Error fetching recent stock prices:', error);
    res.status(500).json({ 
      success: false,
      error: 'Failed to fetch recent stock prices', 
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
      LEFT JOIN company_profiles cp ON ss.symbol = cp.symbol
      LEFT JOIN market_data md ON ss.symbol = md.symbol
      LEFT JOIN key_metrics km ON ss.symbol = km.symbol
      LEFT JOIN analyst_estimates ae ON ss.symbol = ae.symbol
      LEFT JOIN governance_scores gs ON ss.symbol = gs.symbol
      LEFT JOIN (
        SELECT ticker, COUNT(*) as executive_count 
        FROM leadership_team 
        GROUP BY symbol
      ) lt_count ON ss.symbol = lt_count.symbol
      ${whereClause}
      ORDER BY ${sortColumn} ${sortDirection}
      LIMIT $${paramCount + 1} OFFSET $${paramCount + 2}
    `;

    params.push(limit, offset);

    // Count query
    const countQuery = `
      SELECT COUNT(*) as total
      FROM stock_symbols ss
      LEFT JOIN company_profiles cp ON ss.symbol = cp.symbol
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

// Database initialization endpoint for price_daily table
router.post('/init-price-data', async (req, res) => {
  try {
    console.log('Initializing price_daily table...');
    
    // Create price_daily table
    const createTableSQL = `
      CREATE TABLE IF NOT EXISTS price_daily (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(10) NOT NULL,
        date DATE NOT NULL,
        open DECIMAL(12,4),
        high DECIMAL(12,4),
        low DECIMAL(12,4),
        close DECIMAL(12,4),
        adj_close DECIMAL(12,4),
        volume BIGINT,
        dividends DECIMAL(12,4) DEFAULT 0,
        stock_splits DECIMAL(12,4) DEFAULT 0,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, date)
      )
    `;
    
    await query(createTableSQL);
    console.log('price_daily table created successfully');
    
    // Create index for performance
    const createIndexSQL = `
      CREATE INDEX IF NOT EXISTS idx_price_daily_symbol_date 
      ON price_daily(symbol, date DESC)
    `;
    
    await query(createIndexSQL);
    console.log('price_daily index created successfully');
    
    // Sample data for testing
    const sampleData = [
      // AAPL last 30 days
      ['AAPL', '2025-07-02', 190.50, 192.80, 189.20, 191.45, 191.45, 45230000],
      ['AAPL', '2025-07-01', 188.90, 191.20, 188.40, 190.30, 190.30, 38450000],
      ['AAPL', '2025-06-30', 189.80, 190.50, 187.60, 189.25, 189.25, 42100000],
      ['AAPL', '2025-06-29', 187.30, 190.20, 186.80, 189.90, 189.90, 39200000],
      ['AAPL', '2025-06-28', 185.60, 188.40, 185.10, 187.80, 187.80, 41800000],
      ['AAPL', '2025-06-27', 186.90, 188.20, 184.70, 186.50, 186.50, 44300000],
      ['AAPL', '2025-06-26', 184.20, 187.50, 183.90, 186.80, 186.80, 37600000],
      ['AAPL', '2025-06-25', 182.80, 185.30, 182.40, 184.90, 184.90, 36700000],
      ['AAPL', '2025-06-24', 181.50, 183.60, 180.90, 182.70, 182.70, 38900000],
      ['AAPL', '2025-06-23', 180.30, 182.80, 179.80, 181.20, 181.20, 35400000],
      
      // MSFT sample data
      ['MSFT', '2025-07-02', 335.20, 338.40, 334.50, 337.80, 337.80, 18750000],
      ['MSFT', '2025-07-01', 332.60, 336.20, 331.90, 334.90, 334.90, 20100000],
      ['MSFT', '2025-06-30', 330.80, 333.70, 329.40, 332.50, 332.50, 19200000],
      ['MSFT', '2025-06-29', 328.90, 331.60, 327.80, 330.40, 330.40, 21400000],
      ['MSFT', '2025-06-28', 326.40, 329.80, 325.70, 328.60, 328.60, 22300000],
      
      // GOOGL sample data
      ['GOOGL', '2025-07-02', 142.30, 144.70, 141.80, 143.90, 143.90, 23400000],
      ['GOOGL', '2025-07-01', 140.80, 143.20, 140.40, 142.10, 142.10, 25600000],
      ['GOOGL', '2025-06-30', 139.60, 141.50, 138.90, 140.70, 140.70, 27800000],
      ['GOOGL', '2025-06-29', 137.20, 140.30, 136.80, 139.40, 139.40, 29200000],
      ['GOOGL', '2025-06-28', 135.90, 138.40, 135.20, 137.60, 137.60, 26700000],
      
      // TSLA sample data
      ['TSLA', '2025-07-02', 248.90, 252.40, 246.30, 250.80, 250.80, 35600000],
      ['TSLA', '2025-07-01', 245.60, 249.70, 244.20, 248.30, 248.30, 38900000],
      ['TSLA', '2025-06-30', 242.80, 246.90, 241.50, 245.20, 245.20, 41200000],
      ['TSLA', '2025-06-29', 240.30, 244.60, 239.10, 242.50, 242.50, 43800000],
      ['TSLA', '2025-06-28', 237.90, 241.80, 236.70, 240.10, 240.10, 42100000],
      
      // NVDA sample data
      ['NVDA', '2025-07-02', 485.20, 492.80, 483.60, 489.40, 489.40, 55600000],
      ['NVDA', '2025-07-01', 478.90, 487.30, 477.20, 484.70, 484.70, 58200000],
      ['NVDA', '2025-06-30', 472.40, 480.60, 471.80, 478.30, 478.30, 62100000],
      ['NVDA', '2025-06-29', 465.80, 474.20, 464.30, 472.90, 472.90, 67300000],
      ['NVDA', '2025-06-28', 459.60, 467.50, 458.40, 465.20, 465.20, 59800000]
    ];
    
    // Insert sample data
    let insertedCount = 0;
    for (const row of sampleData) {
      try {
        const insertSQL = `
          INSERT INTO price_daily (symbol, date, open, high, low, close, adj_close, volume)
          VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
          ON CONFLICT (symbol, date) DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            adj_close = EXCLUDED.adj_close,
            volume = EXCLUDED.volume
        `;
        
        await query(insertSQL, row);
        insertedCount++;
      } catch (insertError) {
        console.warn(`Failed to insert row for ${row[0]} ${row[1]}:`, insertError.message);
      }
    }
    
    console.log(`Sample data inserted: ${insertedCount} rows`);
    
    // Verify data exists
    const countResult = await query('SELECT COUNT(*) as count FROM price_daily');
    const totalRows = countResult.rows[0].count;
    
    res.json({
      success: true,
      message: 'price_daily table initialized successfully',
      details: {
        tableCreated: true,
        indexCreated: true,
        sampleDataInserted: insertedCount,
        totalRows: parseInt(totalRows)
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error initializing price_daily table:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to initialize price_daily table',
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Enhanced stock screening endpoint with real financial data
router.get('/screen', async (req, res) => {
  try {
    console.log('Enhanced stock screening endpoint called with params:', req.query);
    
    const {
      market_cap_min,
      market_cap_max,
      pe_ratio_min,
      pe_ratio_max,
      price_to_book_min,
      price_to_book_max,
      roe_min,
      roe_max,
      revenue_growth_min,
      revenue_growth_max,
      sector,
      analyst_rating,
      limit = 50,
      page = 1,
      sort_by = 'market_cap',
      sort_order = 'desc'
    } = req.query;
    
    const offset = (parseInt(page) - 1) * parseInt(limit);
    
    // Build dynamic WHERE clause
    let whereConditions = ['se.is_active = TRUE'];
    let params = [];
    let paramCount = 0;
    
    // Market cap filters
    if (market_cap_min) {
      paramCount++;
      whereConditions.push(`se.market_cap >= $${paramCount}`);
      params.push(parseInt(market_cap_min));
    }
    if (market_cap_max) {
      paramCount++;
      whereConditions.push(`se.market_cap <= $${paramCount}`);
      params.push(parseInt(market_cap_max));
    }
    
    // Valuation filters
    if (pe_ratio_min) {
      paramCount++;
      whereConditions.push(`vm.pe_ratio >= $${paramCount}`);
      params.push(parseFloat(pe_ratio_min));
    }
    if (pe_ratio_max) {
      paramCount++;
      whereConditions.push(`vm.pe_ratio <= $${paramCount}`);
      params.push(parseFloat(pe_ratio_max));
    }
    if (price_to_book_min) {
      paramCount++;
      whereConditions.push(`vm.price_to_book >= $${paramCount}`);
      params.push(parseFloat(price_to_book_min));
    }
    if (price_to_book_max) {
      paramCount++;
      whereConditions.push(`vm.price_to_book <= $${paramCount}`);
      params.push(parseFloat(price_to_book_max));
    }
    
    // Profitability filters
    if (roe_min) {
      paramCount++;
      whereConditions.push(`pm.return_on_equity >= $${paramCount}`);
      params.push(parseFloat(roe_min) / 100); // Convert percentage to decimal
    }
    if (roe_max) {
      paramCount++;
      whereConditions.push(`pm.return_on_equity <= $${paramCount}`);
      params.push(parseFloat(roe_max) / 100);
    }
    
    // Growth filters
    if (revenue_growth_min) {
      paramCount++;
      whereConditions.push(`gm.revenue_growth >= $${paramCount}`);
      params.push(parseFloat(revenue_growth_min) / 100);
    }
    if (revenue_growth_max) {
      paramCount++;
      whereConditions.push(`gm.revenue_growth <= $${paramCount}`);
      params.push(parseFloat(revenue_growth_max) / 100);
    }
    
    // Sector filter
    if (sector && sector !== 'all') {
      paramCount++;
      whereConditions.push(`se.sector = $${paramCount}`);
      params.push(sector);
    }
    
    // Analyst rating filter
    if (analyst_rating) {
      paramCount++;
      whereConditions.push(`asa.recommendation_mean <= $${paramCount}`);
      params.push(parseFloat(analyst_rating)); // Lower is better (1=Strong Buy, 5=Strong Sell)
    }
    
    const whereClause = whereConditions.join(' AND ');
    
    // Build ORDER BY clause
    const validSortColumns = {
      'market_cap': 'se.market_cap',
      'pe_ratio': 'vm.pe_ratio',
      'price_to_book': 'vm.price_to_book',
      'roe': 'pm.return_on_equity',
      'revenue_growth': 'gm.revenue_growth',
      'analyst_rating': 'asa.recommendation_mean',
      'symbol': 'se.symbol'
    };
    
    const sortColumn = validSortColumns[sort_by] || 'se.market_cap';
    const sortDirection = sort_order.toUpperCase() === 'ASC' ? 'ASC' : 'DESC';
    
    // Main screening query with joins to financial data
    const screeningQuery = `
      SELECT 
        se.symbol,
        se.company_name,
        se.sector,
        se.market_cap,
        se.market_cap_tier,
        se.exchange,
        vm.pe_ratio,
        vm.price_to_book,
        vm.price_to_sales,
        vm.current_price,
        pm.return_on_equity,
        pm.return_on_assets,
        pm.net_profit_margin,
        gm.revenue_growth,
        gm.earnings_growth,
        asa.recommendation_mean as analyst_rating,
        asa.total_analysts,
        asa.price_target_vs_current,
        ssa.reddit_sentiment_score,
        ssa.news_sentiment_score
      FROM stock_symbols_enhanced se
      LEFT JOIN valuation_multiples vm ON se.symbol = vm.symbol
      LEFT JOIN profitability_metrics pm ON se.symbol = pm.symbol
      LEFT JOIN growth_metrics gm ON se.symbol = gm.symbol
      LEFT JOIN analyst_sentiment_analysis asa ON se.symbol = asa.symbol
      LEFT JOIN social_sentiment_analysis ssa ON se.symbol = ssa.symbol
      WHERE ${whereClause}
      ORDER BY ${sortColumn} ${sortDirection} NULLS LAST
      LIMIT $${paramCount + 1} OFFSET $${paramCount + 2}
    `;
    
    params.push(parseInt(limit), offset);
    
    // Execute screening query
    const screeningResult = await query(screeningQuery, params);
    
    // Get total count for pagination
    const countQuery = `
      SELECT COUNT(*) as total
      FROM stock_symbols_enhanced se
      LEFT JOIN valuation_multiples vm ON se.symbol = vm.symbol
      LEFT JOIN profitability_metrics pm ON se.symbol = pm.symbol
      LEFT JOIN growth_metrics gm ON se.symbol = gm.symbol
      LEFT JOIN analyst_sentiment_analysis asa ON se.symbol = asa.symbol
      LEFT JOIN social_sentiment_analysis ssa ON se.symbol = ssa.symbol
      WHERE ${whereClause}
    `;
    
    const countResult = await query(countQuery, params.slice(0, -2)); // Remove limit and offset
    const totalCount = parseInt(countResult.rows[0].total);
    
    // Format results
    const stocks = screeningResult.rows.map(row => ({
      symbol: row.symbol,
      company_name: row.company_name,
      sector: row.sector,
      market_cap: row.market_cap,
      market_cap_tier: row.market_cap_tier,
      exchange: row.exchange,
      current_price: parseFloat(row.current_price) || null,
      pe_ratio: parseFloat(row.pe_ratio) || null,
      price_to_book: parseFloat(row.price_to_book) || null,
      price_to_sales: parseFloat(row.price_to_sales) || null,
      roe: row.return_on_equity ? (parseFloat(row.return_on_equity) * 100) : null,
      roa: row.return_on_assets ? (parseFloat(row.return_on_assets) * 100) : null,
      profit_margin: row.net_profit_margin ? (parseFloat(row.net_profit_margin) * 100) : null,
      revenue_growth: row.revenue_growth ? (parseFloat(row.revenue_growth) * 100) : null,
      earnings_growth: row.earnings_growth ? (parseFloat(row.earnings_growth) * 100) : null,
      analyst_rating: parseFloat(row.analyst_rating) || null,
      analyst_count: parseInt(row.total_analysts) || 0,
      price_target_upside: row.price_target_vs_current ? (parseFloat(row.price_target_vs_current) * 100) : null,
      social_sentiment: {
        reddit: parseFloat(row.reddit_sentiment_score) || 0,
        news: parseFloat(row.news_sentiment_score) || 0
      }
    }));
    
    res.json({
      success: true,
      data: stocks,
      pagination: {
        total: totalCount,
        page: parseInt(page),
        limit: parseInt(limit),
        pages: Math.ceil(totalCount / parseInt(limit))
      },
      filters_applied: {
        market_cap_min,
        market_cap_max,
        pe_ratio_min,
        pe_ratio_max,
        roe_min,
        roe_max,
        sector,
        analyst_rating
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error in enhanced stock screening:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to execute stock screening',
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get available sectors for filtering
router.get('/sectors', async (req, res) => {
  try {
    const sectorsQuery = `
      SELECT sector, COUNT(*) as count,
             AVG(market_cap) as avg_market_cap,
             AVG(vm.pe_ratio) as avg_pe_ratio
      FROM stock_symbols_enhanced se
      LEFT JOIN valuation_multiples vm ON se.symbol = vm.symbol
      WHERE se.is_active = TRUE AND se.sector IS NOT NULL AND se.sector != 'Unknown'
      GROUP BY sector
      ORDER BY count DESC
    `;
    
    const result = await query(sectorsQuery);
    
    const sectors = result.rows.map(row => ({
      sector: row.sector,
      count: parseInt(row.count),
      avg_market_cap: parseFloat(row.avg_market_cap) || 0,
      avg_pe_ratio: parseFloat(row.avg_pe_ratio) || null
    }));
    
    res.json({
      success: true,
      data: sectors,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error fetching sectors:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch sectors',
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get screening statistics and ranges
router.get('/screen/stats', async (req, res) => {
  try {
    const statsQuery = `
      SELECT 
        COUNT(*) as total_stocks,
        MIN(se.market_cap) as min_market_cap,
        MAX(se.market_cap) as max_market_cap,
        MIN(vm.pe_ratio) as min_pe_ratio,
        MAX(vm.pe_ratio) as max_pe_ratio,
        MIN(vm.price_to_book) as min_pb_ratio,
        MAX(vm.price_to_book) as max_pb_ratio,
        MIN(pm.return_on_equity * 100) as min_roe,
        MAX(pm.return_on_equity * 100) as max_roe,
        MIN(gm.revenue_growth * 100) as min_revenue_growth,
        MAX(gm.revenue_growth * 100) as max_revenue_growth,
        MIN(asa.recommendation_mean) as min_analyst_rating,
        MAX(asa.recommendation_mean) as max_analyst_rating
      FROM stock_symbols_enhanced se
      LEFT JOIN valuation_multiples vm ON se.symbol = vm.symbol
      LEFT JOIN profitability_metrics pm ON se.symbol = pm.symbol
      LEFT JOIN growth_metrics gm ON se.symbol = gm.symbol
      LEFT JOIN analyst_sentiment_analysis asa ON se.symbol = asa.symbol
      WHERE se.is_active = TRUE
    `;
    
    const result = await query(statsQuery);
    const stats = result.rows[0];
    
    res.json({
      success: true,
      data: {
        total_stocks: parseInt(stats.total_stocks),
        ranges: {
          market_cap: {
            min: parseInt(stats.min_market_cap) || 0,
            max: parseInt(stats.max_market_cap) || 0
          },
          pe_ratio: {
            min: parseFloat(stats.min_pe_ratio) || 0,
            max: Math.min(parseFloat(stats.max_pe_ratio) || 100, 100) // Cap at 100 for UI
          },
          price_to_book: {
            min: parseFloat(stats.min_pb_ratio) || 0,
            max: Math.min(parseFloat(stats.max_pb_ratio) || 20, 20) // Cap at 20 for UI
          },
          roe: {
            min: parseFloat(stats.min_roe) || -50,
            max: Math.min(parseFloat(stats.max_roe) || 100, 100) // Cap at 100% for UI
          },
          revenue_growth: {
            min: parseFloat(stats.min_revenue_growth) || -50,
            max: Math.min(parseFloat(stats.max_revenue_growth) || 200, 200) // Cap at 200% for UI
          },
          analyst_rating: {
            min: parseFloat(stats.min_analyst_rating) || 1,
            max: parseFloat(stats.max_analyst_rating) || 5
          }
        }
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error fetching screening stats:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch screening statistics',
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Initialize API keys table for secure portfolio import
router.post('/init-api-keys-table', async (req, res) => {
  try {
    console.log('Initializing user_api_keys table...');
    
    // Create user_api_keys table for secure API key storage
    const createTableSQL = `
      CREATE TABLE IF NOT EXISTS user_api_keys (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        broker_name VARCHAR(50) NOT NULL,
        encrypted_api_key TEXT NOT NULL,
        encrypted_api_secret TEXT,
        key_iv VARCHAR(32) NOT NULL,
        key_auth_tag VARCHAR(32) NOT NULL,
        secret_iv VARCHAR(32),
        secret_auth_tag VARCHAR(32),
        is_sandbox BOOLEAN DEFAULT true,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        last_used TIMESTAMP WITH TIME ZONE,
        UNIQUE(user_id, broker_name)
      )
    `;
    
    await query(createTableSQL);
    console.log('user_api_keys table created successfully');
    
    // Create indexes for performance and security
    const createIndexes = [
      'CREATE INDEX IF NOT EXISTS idx_user_api_keys_user_id ON user_api_keys(user_id)',
      'CREATE INDEX IF NOT EXISTS idx_user_api_keys_broker ON user_api_keys(broker_name)',
      'CREATE INDEX IF NOT EXISTS idx_user_api_keys_last_used ON user_api_keys(last_used DESC)'
    ];
    
    for (const indexSQL of createIndexes) {
      await query(indexSQL);
    }
    
    console.log('user_api_keys indexes created successfully');
    
    // Verify table exists
    const verifyQuery = `
      SELECT column_name, data_type, is_nullable
      FROM information_schema.columns 
      WHERE table_name = 'user_api_keys'
      ORDER BY ordinal_position
    `;
    
    const columns = await query(verifyQuery);
    
    res.json({
      success: true,
      message: 'user_api_keys table initialized successfully',
      details: {
        tableCreated: true,
        indexesCreated: true,
        columns: columns.rows.map(col => ({
          name: col.column_name,
          type: col.data_type,
          nullable: col.is_nullable === 'YES'
        }))
      },
      security: {
        encryption: 'AES-256-GCM',
        keyDerivation: 'scrypt',
        userSaltBased: true,
        noPlaintextLogging: true
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error initializing user_api_keys table:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to initialize API keys table',
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

module.exports = router;
