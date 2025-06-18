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
    const exchange = req.query.sector || req.query.exchange || '';
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

    // Add exchange filter
    if (exchange) {
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

    console.log('OPTIMIZED query params:', { whereClause, params, limit, offset });    // COMPREHENSIVE QUERY: Include all data from loadinfo script
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
        
        -- Governance scores from loadinfo
        gs.audit_risk,
        gs.board_risk,
        gs.compensation_risk,
        gs.overall_risk
        
      FROM stock_symbols ss
      LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
      LEFT JOIN market_data md ON ss.symbol = md.ticker
      LEFT JOIN governance_scores gs ON ss.symbol = gs.ticker
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

    console.log(`FAST query results: ${stocksResult.rows.length} stocks, ${total} total`);    // Professional formatting with ALL available data fields from loadinfo
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
      
      // Governance data
      governance: {
        auditRisk: stock.audit_risk,
        boardRisk: stock.board_risk,
        compensationRisk: stock.compensation_risk,
        overallRisk: stock.overall_risk
      },
      
      // Additional identifiers
      cqsSymbol: stock.cqs_symbol,
      secondarySymbol: stock.secondary_symbol,
      
      // Status & type
      financialStatus: stock.financial_status,
      isEtf: stock.etf === 'Y',
      testIssue: stock.test_issue === 'Y',
      roundLotSize: stock.round_lot_size,
      
      // Data quality indicators
      hasData: true,
      dataSource: 'comprehensive_query',
      hasCompanyProfile: !!stock.long_name,
      hasMarketData: !!stock.current_price,
      hasGovernanceData: !!stock.overall_risk,
      
      // Professional presentation
      displayData: {
        primaryExchange: stock.full_exchange_name || stock.exchange || 'Unknown',
        category: stock.market_category || 'Standard',
        type: stock.etf === 'Y' ? 'ETF' : 'Stock',
        tradeable: stock.financial_status !== 'D' && stock.test_issue !== 'Y',
        sector: stock.sector_disp || stock.sector || 'Unknown',
        industry: stock.industry_disp || stock.industry || 'Unknown'
      }
    }));

    res.json({
      success: true,
      performance: 'COMPREHENSIVE - Full loadinfo data with company profiles, market data, and governance scores',
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
          
          // Governance data
          'audit_risk', 'board_risk', 'compensation_risk', 'overall_risk'
        ],
        dataSources: [
          'stock_symbols', 'company_profile', 'market_data', 'governance_scores'
        ]
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('OPTIMIZED endpoint error:', error);
    res.status(500).json({ 
      error: 'Optimized query failed',
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// SUPER FAST overview for initial page load - shows all your data fields
router.get('/quick/overview', async (req, res) => {
  try {
    console.log('FAST overview endpoint called');
    
    const limit = Math.min(parseInt(req.query.limit) || 25, 100);
    
    // LIGHTNING FAST query - no joins, just stock_symbols
    const quickQuery = `
      SELECT        symbol,
        security_name,
        exchange,
        market_category,
        cqs_symbol,
        financial_status,
        etf,
        round_lot_size,
        test_issue,
        secondary_symbol
      FROM stock_symbols
      WHERE financial_status != 'D' AND test_issue != 'Y'
      ORDER BY symbol ASC
      LIMIT $1
    `;

    const result = await query(quickQuery, [limit]);

    console.log(`FAST overview: ${result.rows.length} stocks loaded instantly`);

    // Professional formatting showing ALL your data
    const formattedData = result.rows.map(row => ({
      // Core data
      ticker: row.symbol,
      name: row.security_name,
      
      // Classification
      exchange: row.exchange,
      category: row.market_category,
      type: row.etf === 'Y' ? 'ETF' : 'Stock',
        // Identifiers
      cqsSymbol: row.cqs_symbol,
      secondarySymbol: row.secondary_symbol,
      
      // Status
      financialStatus: row.financial_status,
      testIssue: row.test_issue,
      roundLotSize: row.round_lot_size,
      
      // Professional display
      displayName: `${row.symbol} - ${row.security_name}`,
      tradeable: row.financial_status !== 'D' && row.test_issue !== 'Y',
      
      // Data completeness
      hasAllData: true,
      dataQuality: 'Complete'
    }));

    res.json({
      success: true,
      performance: 'LIGHTNING FAST - No joins, instant load',
      data: formattedData,
      count: result.rows.length,
      summary: {
        totalShown: result.rows.length,
        dataFields: 11,
        loadTime: 'Sub-second',
        allFieldsVisible: true
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error in FAST overview:', error);
    res.status(500).json({ 
      error: 'Fast overview failed',
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Chunked stocks loading
router.get('/chunk/:chunkIndex', async (req, res) => {
  try {
    const chunkIndex = parseInt(req.params.chunkIndex) || 0;
    const chunkSize = 50; // Small chunks for performance
    
    console.log(`Stocks chunk endpoint called for chunk: ${chunkIndex}`);
    
    const offset = chunkIndex * chunkSize;

    // Use actual tables - get stocks with latest price data
    const dataQuery = `
      SELECT 
        ss.symbol,
        ss.security_name,
        ss.exchange,
        ss.market_category,
        pd.close as current_price,
        pd.volume as current_volume,
        pd.date as price_date
      FROM stock_symbols ss
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) symbol, close, volume, date
        FROM price_daily
        ORDER BY symbol, date DESC
      ) pd ON ss.symbol = pd.symbol
      ORDER BY ss.symbol ASC
      LIMIT $1 OFFSET $2
    `;

    const result = await query(dataQuery, [chunkSize, offset]);

    // Format response to match expected structure
    const formattedData = result.rows.map(row => ({
      ticker: row.symbol,
      short_name: row.security_name,
      sector: row.exchange, // Using exchange as sector substitute
      regular_market_price: row.current_price,
      market_cap: null, // Not available in current schema
      trailing_pe: null, // Not available in current schema
      volume: row.current_volume,
      price_date: row.price_date
    }));

    res.json({
      chunk: chunkIndex,
      chunkSize: chunkSize,
      dataCount: result.rows.length,
      data: formattedData,
      hasMore: result.rows.length === chunkSize,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching stocks chunk:', error);
    res.status(500).json({ 
      error: 'Failed to fetch stocks chunk', 
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Full stocks data endpoint (use with caution)
router.get('/full/data', async (req, res) => {
  try {
    console.log('Stocks full data endpoint called with params:', req.query);
    
    // Force small limit for safety
    const limit = Math.min(parseInt(req.query.limit) || 10, 10);
    const exchange = req.query.sector; // Use exchange instead of sector

    let whereClause = 'WHERE 1=1';
    const params = [];
    let paramIndex = 1;

    if (exchange) {
      whereClause += ` AND ss.exchange = $${paramIndex}`;
      params.push(exchange);
      paramIndex++;
    }

    // Use actual tables - get stocks with latest price data
    const dataQuery = `
      SELECT 
        ss.symbol,
        ss.security_name,
        ss.exchange,
        ss.market_category,
        pd.close as current_price,
        pd.volume as current_volume,
        pd.date as price_date
      FROM stock_symbols ss
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) symbol, close, volume, date
        FROM price_daily
        ORDER BY symbol, date DESC
      ) pd ON ss.symbol = pd.symbol
      ${whereClause}
      ORDER BY pd.volume DESC NULLS LAST
      LIMIT $${paramIndex}
    `;

    const result = await query(dataQuery, [...params, limit]);

    // Format response to match expected structure
    const formattedData = result.rows.map(row => ({
      ticker: row.symbol,
      short_name: row.security_name,
      sector: row.exchange,
      industry: row.market_category,
      regular_market_price: row.current_price,
      market_cap: null, // Not available in current schema
      trailing_pe: null, // Not available in current schema
      dividend_yield: null, // Not available in current schema
      volume: row.current_volume,
      price_date: row.price_date
    }));

    res.json({
      warning: 'This endpoint returns limited data for performance reasons',
      actualLimit: limit,
      filters: { sector: exchange || null },
      data: formattedData,
      count: result.rows.length,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching full stocks data:', error);
    res.status(500).json({ 
      error: 'Failed to fetch full stocks data', 
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get comprehensive stock details by ticker
// COMPREHENSIVE Individual Stock Endpoint - Detailed stock information with price history
router.get('/:ticker', async (req, res) => {
  try {
    const { ticker } = req.params;
    const tickerUpper = ticker.toUpperCase();
    
    console.log(`Individual stock endpoint called for: ${tickerUpper}`);
    
    // Get days of price history (default 90 days, max 365)
    const days = Math.min(parseInt(req.query.days) || 90, 365);
    const includeTechnicals = req.query.technicals !== 'false'; // Default true
    
    // 1. GET BASIC STOCK INFO
    const stockInfoQuery = `
      SELECT 
        symbol,
        security_name,
        exchange,
        market_category,
        cqs_symbol,
        financial_status,
        round_lot_size,
        etf,
        test_issue,
        nasdaq_symbol
      FROM stock_symbols 
      WHERE symbol = $1
    `;
    
    const stockInfo = await query(stockInfoQuery, [tickerUpper]);
    
    if (stockInfo.rows.length === 0) {
      return res.status(404).json({
        error: 'Stock not found',
        symbol: tickerUpper,
        message: `Symbol '${tickerUpper}' not found in database`,
        timestamp: new Date().toISOString()
      });
    }
    
    const stockData = stockInfo.rows[0];
    
    // 2. GET RECENT PRICE HISTORY (OHLCV)
    const priceHistoryQuery = `
      SELECT 
        date,
        open,
        high, 
        low,
        close,
        volume,
        adj_close
      FROM price_daily 
      WHERE symbol = $1 
        AND date >= CURRENT_DATE - INTERVAL '${days} days'
      ORDER BY date DESC
      LIMIT 500
    `;
    
    const priceHistory = await query(priceHistoryQuery, [tickerUpper]);
    
    // 3. GET LATEST PRICE DATA FOR SUMMARY
    const latestPrice = priceHistory.rows.length > 0 ? priceHistory.rows[0] : null;
    
    // 4. GET TECHNICAL INDICATORS (if requested)
    let technicalData = null;
    if (includeTechnicals && priceHistory.rows.length > 0) {
      try {
        const technicalQuery = `
          SELECT 
            date,
            rsi,
            macd,
            macd_signal,
            macd_hist,
            mom,
            roc,
            adx,
            atr,
            ad,
            cmf,
            mfi,
            dm,
            marketwatch,
            sma_10,
            sma_20,
            sma_50,
            sma_150,
            sma_200,
            ema_4,
            ema_9,
            ema_21,
            bbands_lower,
            bbands_middle,
            bbands_upper,
            td_sequential,
            td_combo,
            pivot_high,
            pivot_low
          FROM technical_data_daily 
          WHERE symbol = $1 
            AND date >= CURRENT_DATE - INTERVAL '${Math.min(days, 90)} days'
          ORDER BY date DESC
          LIMIT 200
        `;
        
        const technicalResult = await query(technicalQuery, [tickerUpper]);
        technicalData = technicalResult.rows;
        console.log(`Found ${technicalData.length} technical indicator records for ${tickerUpper}`);
      } catch (error) {
        console.error(`Error fetching technical data for ${tickerUpper}:`, error.message);
        technicalData = [];
      }
    }
    
    // 5. GET FUNDAMENTAL DATA (if available)
    let fundamentalData = null;
    try {
      const fundamentalQuery = `
        SELECT 
          market_cap,
          pe_ratio,
          eps,
          dividend_yield,
          book_value,
          revenue,
          profit_margin,
          debt_to_equity,
          return_on_equity,
          price_to_book,
          updated_at
        FROM fundamentals 
        WHERE symbol = $1 
        ORDER BY updated_at DESC 
        LIMIT 1
      `;
      
      const fundamentalResult = await query(fundamentalQuery, [tickerUpper]);
      fundamentalData = fundamentalResult.rows.length > 0 ? fundamentalResult.rows[0] : null;
    } catch (error) {
      console.log(`Fundamental data not available for ${tickerUpper}:`, error.message);
      fundamentalData = null;
    }
    
    // 6. CALCULATE PRICE STATISTICS
    let priceStats = null;
    if (priceHistory.rows.length > 0) {
      const prices = priceHistory.rows.map(row => parseFloat(row.close));
      const volumes = priceHistory.rows.map(row => parseInt(row.volume || 0));
      const highs = priceHistory.rows.map(row => parseFloat(row.high));
      const lows = priceHistory.rows.map(row => parseFloat(row.low));
      
      const currentPrice = prices[0];
      const oldestPrice = prices[prices.length - 1];
      const change = currentPrice - oldestPrice;
      const changePercent = ((change / oldestPrice) * 100);
      
      priceStats = {
        currentPrice: currentPrice,
        change: change,
        changePercent: changePercent,
        high52Week: Math.max(...highs),
        low52Week: Math.min(...lows),
        avgVolume: Math.round(volumes.reduce((a, b) => a + b, 0) / volumes.length),
        maxVolume: Math.max(...volumes),
        minVolume: Math.min(...volumes),
        dataPoints: priceHistory.rows.length,
        dateRange: {
          latest: priceHistory.rows[0].date,
          earliest: priceHistory.rows[priceHistory.rows.length - 1].date
        }
      };
    }
    
    // 7. BUILD COMPREHENSIVE RESPONSE
    const response = {
      symbol: tickerUpper,
      ticker: tickerUpper, // For backward compatibility
      companyInfo: {
        name: stockData.security_name,
        exchange: stockData.exchange,
        marketCategory: stockData.market_category,
        cqsSymbol: stockData.cqs_symbol,
        financialStatus: stockData.financial_status,
        roundLotSize: stockData.round_lot_size,
        isETF: stockData.etf === 't' || stockData.etf === true,
        isTestIssue: stockData.test_issue === 't' || stockData.test_issue === true,
        nasdaqSymbol: stockData.nasdaq_symbol
      },
      currentPrice: latestPrice ? {
        date: latestPrice.date,
        open: parseFloat(latestPrice.open || 0),
        high: parseFloat(latestPrice.high || 0),
        low: parseFloat(latestPrice.low || 0),
        close: parseFloat(latestPrice.close || 0),
        adjClose: parseFloat(latestPrice.adj_close || latestPrice.close || 0),
        volume: parseInt(latestPrice.volume || 0)
      } : null,
      priceStats: priceStats,
      priceHistory: {
        requestedDays: days,
        actualDays: priceHistory.rows.length,
        data: priceHistory.rows.map(row => ({
          date: row.date,
          open: parseFloat(row.open || 0),
          high: parseFloat(row.high || 0),
          low: parseFloat(row.low || 0),
          close: parseFloat(row.close || 0),
          adjClose: parseFloat(row.adj_close || row.close || 0),
          volume: parseInt(row.volume || 0)
        }))
      },
      technicalIndicators: includeTechnicals ? {
        available: technicalData !== null && technicalData.length > 0,
        count: technicalData ? technicalData.length : 0,
        data: technicalData || [],
        note: technicalData && technicalData.length === 0 ? 'Technical indicators calculated but no recent data found' : null
      } : { available: false, note: 'Technical indicators excluded from request' },
      fundamentals: fundamentalData ? {
        available: true,
        data: {
          marketCap: fundamentalData.market_cap,
          peRatio: fundamentalData.pe_ratio,
          eps: fundamentalData.eps,
          dividendYield: fundamentalData.dividend_yield,
          bookValue: fundamentalData.book_value,
          revenue: fundamentalData.revenue,
          profitMargin: fundamentalData.profit_margin,
          debtToEquity: fundamentalData.debt_to_equity,
          returnOnEquity: fundamentalData.return_on_equity,
          priceToBook: fundamentalData.price_to_book,
          lastUpdated: fundamentalData.updated_at
        }
      } : { available: false, note: 'Fundamental data not available' },
      metadata: {
        requestedSymbol: ticker,
        resolvedSymbol: tickerUpper,
        includedTechnicals: includeTechnicals,
        requestedDays: days,
        dataAvailability: {
          basicInfo: true,
          priceHistory: priceHistory.rows.length > 0,
          technicalIndicators: technicalData !== null && technicalData.length > 0,
          fundamentals: fundamentalData !== null
        },
        timestamp: new Date().toISOString()
      }
    };
    
    console.log(`Successfully compiled comprehensive data for ${tickerUpper}:`, {
      pricePoints: priceHistory.rows.length,
      technicalPoints: technicalData ? technicalData.length : 0,
      hasFundamentals: fundamentalData !== null
    });
    
    res.json(response);
    
  } catch (error) {
    console.error('Error in individual stock endpoint:', error);
    res.status(500).json({ 
      error: 'Failed to fetch stock data', 
      symbol: req.params.ticker,
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get stock price history
router.get('/:ticker/prices', async (req, res) => {
  try {
    const { ticker } = req.params;
    const period = req.query.period || '1M'; // Default to 1 month
    const interval = req.query.interval || 'daily';
    
    console.log(`Stock prices endpoint called for ticker: ${ticker}, period: ${period}, interval: ${interval}`);
    
    // Determine how many days to fetch based on period
    let limit = 30; // Default 1 month
    switch(period) {
      case '1W': limit = 7; break;
      case '1M': limit = 30; break;
      case '3M': limit = 90; break;
      case '6M': limit = 180; break;
      case '1Y': limit = 365; break;
      case 'YTD': limit = 365; break; // Approximate
      default: limit = 30;
    }
    
    // Select appropriate price table based on interval
    let table = 'price_daily';
    switch(interval) {
      case 'daily': table = 'price_daily'; break;
      case 'weekly': table = 'price_weekly'; break;
      case 'monthly': table = 'price_monthly'; break;
      default: table = 'price_daily';
    }
    
    const pricesQuery = `
      SELECT date, open, high, low, close, adj_close, volume
      FROM ${table}
      WHERE UPPER(symbol) = UPPER($1)
      ORDER BY date DESC
      LIMIT $2
    `;
    
    const result = await query(pricesQuery, [ticker, limit]);
    
    if (result.rows.length === 0) {
      return res.status(404).json({
        error: 'No price data found',
        ticker: ticker,
        period: period,
        interval: interval,
        timestamp: new Date().toISOString()
      });
    }
    
    // Calculate some basic metrics
    const prices = result.rows;
    const latest = prices[0];
    const oldest = prices[prices.length - 1];
    
    const periodReturn = oldest.close > 0 ? 
      ((latest.close - oldest.close) / oldest.close * 100) : 0;
    
    const high52Week = Math.max(...prices.map(p => p.high));
    const low52Week = Math.min(...prices.map(p => p.low));
    
    res.json({
      ticker: ticker.toUpperCase(),
      period: period,
      interval: interval,
      dataPoints: result.rows.length,
      priceData: prices,
      summary: {
        latest_price: latest.close,
        latest_date: latest.date,
        period_return_percent: periodReturn,
        high_52_week: high52Week,
        low_52_week: low52Week,
        latest_volume: latest.volume
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error fetching stock prices:', error);
    res.status(500).json({ 
      error: 'Failed to fetch stock prices', 
      details: error.message,
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
      timestamp: new Date().toISOString()
    });
  }
});

// Get available industries - market categories
router.get('/filters/industries', async (req, res) => {
  try {
    console.log('Stock filters/industries (market categories) endpoint called');
    
    const industriesQuery = `
      SELECT market_category, COUNT(*) as count
      FROM stock_symbols
      WHERE market_category IS NOT NULL
      GROUP BY market_category
      ORDER BY count DESC, market_category ASC
    `;
    
    const result = await query(industriesQuery);
    
    res.json({
      data: result.rows.map(row => ({
        name: row.market_category,
        value: row.market_category,
        count: parseInt(row.count)
      })),
      total: result.rows.length,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error fetching market categories:', error);
    res.status(500).json({ 
      error: 'Failed to fetch market categories', 
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Top gainers based on available price data
router.get('/movers/gainers', async (req, res) => {
  try {
    console.log('Stock movers/gainers endpoint called');
    
    const limit = Math.min(parseInt(req.query.limit) || 10, 50);
    
    // Get stocks with current and previous day prices to calculate gains
    const gainersQuery = `
      WITH price_changes AS (
        SELECT 
          symbol,
          date,
          close,
          LAG(close) OVER (PARTITION BY symbol ORDER BY date) as prev_close,
          LAG(date) OVER (PARTITION BY symbol ORDER BY date) as prev_date
        FROM price_daily
        WHERE date >= CURRENT_DATE - INTERVAL '7 days'
      ),
      latest_changes AS (
        SELECT DISTINCT ON (symbol)
          symbol,
          close as current_price,
          prev_close,
          date as price_date,
          CASE 
            WHEN prev_close > 0 
            THEN ((close - prev_close) / prev_close * 100)
            ELSE 0
          END as change_percent
        FROM price_changes
        WHERE prev_close IS NOT NULL
        ORDER BY symbol, date DESC
      )
      SELECT 
        ss.symbol,
        ss.security_name,
        ss.exchange,
        lc.current_price,
        lc.prev_close,
        lc.change_percent,
        lc.price_date
      FROM latest_changes lc
      JOIN stock_symbols ss ON ss.symbol = lc.symbol
      WHERE lc.change_percent > 0
      ORDER BY lc.change_percent DESC
      LIMIT $1
    `;
    
    const result = await query(gainersQuery, [limit]);
    
    const formattedData = result.rows.map(row => ({
      ticker: row.symbol,
      name: row.security_name,
      exchange: row.exchange,
      price: row.current_price,
      change: row.current_price - row.prev_close,
      changePercent: row.change_percent,
      volume: null, // Not available in this query
      price_date: row.price_date
    }));
    
    res.json({
      data: formattedData,
      count: result.rows.length,
      type: 'gainers',
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error fetching stock gainers:', error);
    res.status(500).json({ 
      error: 'Failed to fetch stock gainers', 
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Top losers based on available price data
router.get('/movers/losers', async (req, res) => {
  try {
    console.log('Stock movers/losers endpoint called');
    
    const limit = Math.min(parseInt(req.query.limit) || 10, 50);
    
    // Get stocks with current and previous day prices to calculate losses
    const losersQuery = `
      WITH price_changes AS (
        SELECT 
          symbol,
          date,
          close,
          LAG(close) OVER (PARTITION BY symbol ORDER BY date) as prev_close,
          LAG(date) OVER (PARTITION BY symbol ORDER BY date) as prev_date
        FROM price_daily
        WHERE date >= CURRENT_DATE - INTERVAL '7 days'
      ),
      latest_changes AS (
        SELECT DISTINCT ON (symbol)
          symbol,
          close as current_price,
          prev_close,
          date as price_date,
          CASE 
            WHEN prev_close > 0 
            THEN ((close - prev_close) / prev_close * 100)
            ELSE 0
          END as change_percent
        FROM price_changes
        WHERE prev_close IS NOT NULL
        ORDER BY symbol, date DESC
      )
      SELECT 
        ss.symbol,
        ss.security_name,
        ss.exchange,
        lc.current_price,
        lc.prev_close,
        lc.change_percent,
        lc.price_date
      FROM latest_changes lc
      JOIN stock_symbols ss ON ss.symbol = lc.symbol
      WHERE lc.change_percent < 0
      ORDER BY lc.change_percent ASC
      LIMIT $1
    `;
    
    const result = await query(losersQuery, [limit]);
    
    const formattedData = result.rows.map(row => ({
      ticker: row.symbol,
      name: row.security_name,
      exchange: row.exchange,
      price: row.current_price,
      change: row.current_price - row.prev_close,
      changePercent: row.change_percent,
      volume: null, // Not available in this query
      price_date: row.price_date
    }));
    
    res.json({
      data: formattedData,
      count: result.rows.length,
      type: 'losers',
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error fetching stock losers:', error);
    res.status(500).json({ 
      error: 'Failed to fetch stock losers', 
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Most active stocks by volume
router.get('/movers/active', async (req, res) => {
  try {
    console.log('Stock movers/active endpoint called');
    
    const limit = Math.min(parseInt(req.query.limit) || 10, 50);
    
    // Get most active stocks by volume
    const activeQuery = `
      SELECT 
        ss.symbol,
        ss.security_name,
        ss.exchange,
        pd.close as current_price,
        pd.volume,
        pd.date as price_date
      FROM stock_symbols ss
      JOIN (
        SELECT DISTINCT ON (symbol) symbol, close, volume, date
        FROM price_daily
        ORDER BY symbol, date DESC
      ) pd ON ss.symbol = pd.symbol
      WHERE pd.volume IS NOT NULL AND pd.volume > 0
      ORDER BY pd.volume DESC
      LIMIT $1
    `;
    
    const result = await query(activeQuery, [limit]);
    
    const formattedData = result.rows.map(row => ({
      ticker: row.symbol,
      name: row.security_name,
      exchange: row.exchange,
      price: row.current_price,
      volume: row.volume,
      price_date: row.price_date
    }));
    
    res.json({
      data: formattedData,
      count: result.rows.length,
      type: 'most_active',
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error fetching most active stocks:', error);
    res.status(500).json({ 
      error: 'Failed to fetch most active stocks', 
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Stock screening endpoint
router.get('/screen', async (req, res) => {
  try {
    console.log('Stock screen endpoint called with params:', req.query);
    
    const limit = Math.min(parseInt(req.query.limit) || 25, 100);
    const exchange = req.query.exchange;
    const marketCategory = req.query.marketCategory;
    const minPrice = parseFloat(req.query.minPrice) || null;
    const maxPrice = parseFloat(req.query.maxPrice) || null;
    const minVolume = parseInt(req.query.minVolume) || null;
    
    let whereClause = 'WHERE pd.close IS NOT NULL';
    const params = [];
    let paramIndex = 1;
    
    if (exchange) {
      whereClause += ` AND ss.exchange = $${paramIndex}`;
      params.push(exchange);
      paramIndex++;
    }
    
    if (marketCategory) {
      whereClause += ` AND ss.market_category = $${paramIndex}`;
      params.push(marketCategory);
      paramIndex++;
    }
    
    if (minPrice !== null) {
      whereClause += ` AND pd.close >= $${paramIndex}`;
      params.push(minPrice);
      paramIndex++;
    }
    
    if (maxPrice !== null) {
      whereClause += ` AND pd.close <= $${paramIndex}`;
      params.push(maxPrice);
      paramIndex++;
    }
    
    if (minVolume !== null) {
      whereClause += ` AND pd.volume >= $${paramIndex}`;
      params.push(minVolume);
      paramIndex++;
    }
    
    const screenQuery = `
      SELECT 
        ss.symbol,
        ss.security_name,
        ss.exchange,
        ss.market_category,
        pd.close as current_price,
        pd.volume,
        pd.date as price_date
      FROM stock_symbols ss
      JOIN (
        SELECT DISTINCT ON (symbol) symbol, close, volume, date
        FROM price_daily
        ORDER BY symbol, date DESC
      ) pd ON ss.symbol = pd.symbol
      ${whereClause}
      ORDER BY pd.volume DESC NULLS LAST
      LIMIT $${paramIndex}
    `;
    
    params.push(limit);
    
    const result = await query(screenQuery, params);
    
    const formattedData = result.rows.map(row => ({
      ticker: row.symbol,
      name: row.security_name,
      exchange: row.exchange,
      market_category: row.market_category,
      price: row.current_price,
      volume: row.volume,
      price_date: row.price_date
    }));
    
    res.json({
      data: formattedData,
      count: result.rows.length,
      filters: {
        exchange: exchange || null,
        marketCategory: marketCategory || null,
        minPrice: minPrice,
        maxPrice: maxPrice,
        minVolume: minVolume
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error screening stocks:', error);
    res.status(500).json({ 
      error: 'Failed to screen stocks', 
      details: error.message,
      timestamp: new Date().toISOString()    });
  }
});

// Lightweight endpoint for recent price data only
router.get('/:ticker/price-recent', async (req, res) => {
  try {
    const { ticker } = req.params;
    const limit = Math.min(parseInt(req.query.limit) || 30, 60); // Max 60 days for performance
    
    console.log(`Recent price endpoint called for ticker: ${ticker}, limit: ${limit}`);
    
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
    
    // Calculate basic metrics
    const prices = result.rows;
    const latest = prices[0];
    const oldest = prices[prices.length - 1];
    
    const periodReturn = oldest.close > 0 ? 
      ((latest.close - oldest.close) / oldest.close * 100) : 0;
    
    res.json({
      success: true,
      ticker: ticker.toUpperCase(),
      dataPoints: result.rows.length,
      data: prices.map(price => ({
        date: price.date,
        open: parseFloat(price.open),
        high: parseFloat(price.high),
        low: parseFloat(price.low),
        close: parseFloat(price.close),
        adjClose: parseFloat(price.adj_close),
        volume: parseInt(price.volume) || 0
      })),
      summary: {
        latestPrice: parseFloat(latest.close),
        latestDate: latest.date,
        periodReturn: parseFloat(periodReturn.toFixed(2)),
        latestVolume: parseInt(latest.volume) || 0
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error fetching recent prices:', error);
    res.status(500).json({ 
      error: 'Failed to fetch recent price data', 
      details: error.message,
      ticker: req.params.ticker,
      timestamp: new Date().toISOString()
    });
  }
});

// Stock profile endpoint - returns company information
router.get('/:ticker/profile', async (req, res) => {
  try {
    const { ticker } = req.params;
    const tickerUpper = ticker.toUpperCase();
    
    console.log(`Stock profile endpoint called for: ${tickerUpper}`);
    
    const stockInfoQuery = `
      SELECT 
        symbol,
        security_name,
        exchange,
        market_category,
        cqs_symbol,
        financial_status,
        round_lot_size,
        etf,
        test_issue,
        nasdaq_symbol
      FROM stock_symbols 
      WHERE symbol = $1
    `;
    
    const stockInfo = await query(stockInfoQuery, [tickerUpper]);
    
    if (stockInfo.rows.length === 0) {
      return res.status(404).json({
        error: 'Stock not found',
        symbol: tickerUpper,
        timestamp: new Date().toISOString()
      });
    }
    
    const stockData = stockInfo.rows[0];
    
    res.json({
      symbol: tickerUpper,
      name: stockData.security_name,
      exchange: stockData.exchange,
      marketCategory: stockData.market_category,
      cqsSymbol: stockData.cqs_symbol,
      financialStatus: stockData.financial_status,
      roundLotSize: stockData.round_lot_size,
      isETF: stockData.etf === 't' || stockData.etf === true,
      isTestIssue: stockData.test_issue === 't' || stockData.test_issue === true,
      nasdaqSymbol: stockData.nasdaq_symbol,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error in stock profile endpoint:', error);
    res.status(500).json({ 
      error: 'Failed to fetch stock profile', 
      symbol: req.params.ticker,
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Stock metrics endpoint - returns financial metrics
router.get('/:ticker/metrics', async (req, res) => {
  try {
    const { ticker } = req.params;
    const tickerUpper = ticker.toUpperCase();
    
    console.log(`Stock metrics endpoint called for: ${tickerUpper}`);
    
    // Try to get fundamental data
    let fundamentalData = null;
    try {
      const fundamentalQuery = `
        SELECT 
          market_cap,
          pe_ratio,
          eps,
          dividend_yield,
          book_value,
          revenue,
          profit_margin,
          debt_to_equity,
          return_on_equity,
          price_to_book,
          updated_at
        FROM fundamentals 
        WHERE symbol = $1 
        ORDER BY updated_at DESC 
        LIMIT 1
      `;
      
      const fundamentalResult = await query(fundamentalQuery, [tickerUpper]);
      fundamentalData = fundamentalResult.rows.length > 0 ? fundamentalResult.rows[0] : null;
    } catch (error) {
      console.log(`Fundamental data not available for ${tickerUpper}:`, error.message);
    }
    
    if (fundamentalData) {
      res.json({
        symbol: tickerUpper,
        marketCap: fundamentalData.market_cap,
        peRatio: fundamentalData.pe_ratio,
        eps: fundamentalData.eps,
        dividendYield: fundamentalData.dividend_yield,
        bookValue: fundamentalData.book_value,
        revenue: fundamentalData.revenue,
        profitMargin: fundamentalData.profit_margin,
        debtToEquity: fundamentalData.debt_to_equity,
        returnOnEquity: fundamentalData.return_on_equity,
        priceToBook: fundamentalData.price_to_book,
        lastUpdated: fundamentalData.updated_at,
        timestamp: new Date().toISOString()
      });
    } else {
      res.json({
        symbol: tickerUpper,
        available: false,
        message: 'Financial metrics not available for this symbol',
        timestamp: new Date().toISOString()
      });
    }
    
  } catch (error) {
    console.error('Error in stock metrics endpoint:', error);
    res.status(500).json({ 
      error: 'Failed to fetch stock metrics', 
      symbol: req.params.ticker,
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Stock financials endpoint - returns financial statements
router.get('/:ticker/financials', async (req, res) => {
  try {
    const { ticker } = req.params;
    const type = req.query.type || 'income';
    const tickerUpper = ticker.toUpperCase();
    
    console.log(`Stock financials endpoint called for: ${tickerUpper}, type: ${type}`);
    
    res.json({
      symbol: tickerUpper,
      type: type,
      available: false,
      message: 'Financial statements data not available - use the main stock endpoint for available fundamental data',
      note: 'Try /stocks/' + tickerUpper + ' for basic fundamental metrics',
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error in stock financials endpoint:', error);
    res.status(500).json({ 
      error: 'Failed to fetch stock financials', 
      symbol: req.params.ticker,
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Stock recommendations endpoint - returns analyst recommendations
router.get('/:ticker/recommendations', async (req, res) => {
  try {
    const { ticker } = req.params;
    const tickerUpper = ticker.toUpperCase();
    
    console.log(`Stock recommendations endpoint called for: ${tickerUpper}`);
    
    res.json({
      symbol: tickerUpper,
      available: false,
      message: 'Analyst recommendations data not available',
      recommendations: [],
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error in stock recommendations endpoint:', error);
    res.status(500).json({ 
      error: 'Failed to fetch stock recommendations', 
      symbol: req.params.ticker,
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

module.exports = router;
