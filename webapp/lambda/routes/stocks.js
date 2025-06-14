const express = require('express');
const { query } = require('../utils/database');

const router = express.Router();

// Get all stocks with basic info and pagination
router.get('/', async (req, res) => {
  try {
    const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 50;
    const offset = (page - 1) * limit;
    const search = req.query.search || '';
    const sector = req.query.sector || '';
    
    let whereClause = 'WHERE 1=1';
    const params = [];
    let paramCount = 0;

    if (search) {
      paramCount++;
      whereClause += ` AND (cp.ticker ILIKE $${paramCount} OR cp.short_name ILIKE $${paramCount} OR cp.long_name ILIKE $${paramCount})`;
      params.push(`%${search}%`);
    }

    if (sector) {
      paramCount++;
      whereClause += ` AND cp.sector = $${paramCount}`;
      params.push(sector);
    }    const stocksQuery = `
      SELECT        cp.ticker,
        cp.short_name,
        cp.long_name,
        cp.sector,
        cp.industry,
        md.market_cap,
        cp.currency,
        cp.exchange,
        md.regular_market_price,
        (md.regular_market_price - md.regular_market_previous_close) as regular_market_change,
        ((md.regular_market_price - md.regular_market_previous_close) / md.regular_market_previous_close * 100) as regular_market_change_percent,
        md.fifty_two_week_high,
        md.fifty_two_week_low,
        km.trailing_pe,
        km.forward_pe,
        km.price_to_book,
        km.dividend_yield
      FROM company_profile cp
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      LEFT JOIN key_metrics km ON cp.ticker = km.ticker
      ${whereClause}
      ORDER BY md.market_cap DESC NULLS LAST
      LIMIT $${paramCount + 1} OFFSET $${paramCount + 2}
    `;

    params.push(limit, offset);

    const countQuery = `
      SELECT COUNT(*) as total
      FROM company_profile cp
      ${whereClause}
    `;

    const [stocksResult, countResult] = await Promise.all([
      query(stocksQuery, params),
      query(countQuery, params.slice(0, -2)) // Remove limit and offset for count
    ]);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    res.json({
      data: stocksResult.rows,
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1
      }
    });
  } catch (error) {
    console.error('Error fetching stocks:', error);
    res.status(500).json({ error: 'Failed to fetch stocks data' });
  }
});

// Stock screening endpoint - MUST be before /:ticker route
router.get('/screen', async (req, res) => {
  try {
    const page = parseInt(req.query.page) || 1;
    const limit = Math.min(parseInt(req.query.limit) || 25, 100); // Cap at 100 for performance
    const offset = (page - 1) * limit;
    const sortBy = req.query.sortBy || 'market_cap';
    const sortOrder = req.query.sortOrder || 'desc';

    // Build WHERE clause based on filters
    let whereClause = 'WHERE 1=1';
    const params = [];
    let paramCount = 0;

    // Search filter (most common)
    if (req.query.search) {
      paramCount++;
      whereClause += ` AND (cp.ticker ILIKE $${paramCount} OR cp.short_name ILIKE $${paramCount})`;
      params.push(`%${req.query.search}%`);
    }

    // Basic filters (most performant)
    if (req.query.sector) {
      paramCount++;
      whereClause += ` AND cp.sector = $${paramCount}`;
      params.push(req.query.sector);
    }

    if (req.query.exchange) {
      paramCount++;
      whereClause += ` AND cp.exchange = $${paramCount}`;
      params.push(req.query.exchange);
    }

    // Price filters (with NULL checks for performance)
    if (req.query.priceMin) {
      paramCount++;
      whereClause += ` AND md.regular_market_price >= $${paramCount} AND md.regular_market_price IS NOT NULL`;
      params.push(parseFloat(req.query.priceMin));
    }
    if (req.query.priceMax) {
      paramCount++;
      whereClause += ` AND md.regular_market_price <= $${paramCount} AND md.regular_market_price IS NOT NULL`;
      params.push(parseFloat(req.query.priceMax));
    }

    // Market cap filters (convert billions to actual values)
    if (req.query.marketCapMin) {
      paramCount++;
      whereClause += ` AND md.market_cap >= $${paramCount} AND md.market_cap IS NOT NULL`;
      params.push(parseFloat(req.query.marketCapMin) * 1000000000);
    }
    if (req.query.marketCapMax) {
      paramCount++;
      whereClause += ` AND md.market_cap <= $${paramCount} AND md.market_cap IS NOT NULL`;
      params.push(parseFloat(req.query.marketCapMax) * 1000000000);
    }

    // Only add complex filters if they're actually requested (performance optimization)
    const hasComplexFilters = req.query.peRatioMin || req.query.peRatioMax || 
                             req.query.roeMin || req.query.roeMax || 
                             req.query.dividendYieldMin || req.query.dividendYieldMax ||
                             req.query.paysDividends === 'true' || 
                             req.query.hasEarningsGrowth === 'true';

    // PE Ratio filters
    if (req.query.peRatioMin) {
      paramCount++;
      whereClause += ` AND km.trailing_pe >= $${paramCount} AND km.trailing_pe IS NOT NULL`;
      params.push(parseFloat(req.query.peRatioMin));
    }
    if (req.query.peRatioMax) {
      paramCount++;
      whereClause += ` AND km.trailing_pe <= $${paramCount} AND km.trailing_pe IS NOT NULL`;
      params.push(parseFloat(req.query.peRatioMax));
    }

    // ROE filters
    if (req.query.roeMin) {
      paramCount++;
      whereClause += ` AND km.return_on_equity_pct >= $${paramCount} AND km.return_on_equity_pct IS NOT NULL`;
      params.push(parseFloat(req.query.roeMin) / 100);
    }
    if (req.query.roeMax) {
      paramCount++;
      whereClause += ` AND km.return_on_equity_pct <= $${paramCount} AND km.return_on_equity_pct IS NOT NULL`;
      params.push(parseFloat(req.query.roeMax) / 100);
    }

    // Dividend filters
    if (req.query.dividendYieldMin) {
      paramCount++;
      whereClause += ` AND km.dividend_yield >= $${paramCount} AND km.dividend_yield IS NOT NULL`;
      params.push(parseFloat(req.query.dividendYieldMin) / 100);
    }
    if (req.query.dividendYieldMax) {
      paramCount++;
      whereClause += ` AND km.dividend_yield <= $${paramCount} AND km.dividend_yield IS NOT NULL`;
      params.push(parseFloat(req.query.dividendYieldMax) / 100);
    }

    // Boolean filters (simplified for performance)
    if (req.query.paysDividends === 'true') {
      whereClause += ` AND km.dividend_yield > 0`;
    }
    if (req.query.hasEarningsGrowth === 'true') {
      whereClause += ` AND km.earnings_growth_pct > 0`;
    }

    // Build ORDER BY clause
    const validSortColumns = {
      'market_capitalization': 'md.market_cap',
      'market_cap': 'md.market_cap',
      'price': 'md.regular_market_price',
      'pe_ratio': 'km.trailing_pe',
      'dividend_yield': 'km.dividend_yield',
      'return_on_equity': 'km.return_on_equity_pct',
      'revenue_growth': 'km.revenue_growth_pct',
      'symbol': 'cp.ticker',
      'company_name': 'cp.short_name',
      'sector': 'cp.sector'
    };

    const orderColumn = validSortColumns[sortBy] || 'md.market_cap';
    const orderClause = `ORDER BY ${orderColumn} ${sortOrder.toUpperCase()} NULLS LAST`;

    // Optimized query - only select essential columns for performance
    const screenQuery = `
      SELECT 
        cp.ticker as symbol,
        cp.short_name as company_name,
        cp.sector,
        cp.industry,
        cp.country,
        cp.exchange,
        md.market_cap as market_capitalization,
        md.regular_market_price as price,
        (md.regular_market_price - md.regular_market_previous_close) as regular_market_change,
        ((md.regular_market_price - md.regular_market_previous_close) / md.regular_market_previous_close * 100) as regular_market_change_percent,
        km.trailing_pe as pe_ratio,
        km.peg_ratio,
        km.price_to_book as pb_ratio,
        km.dividend_yield,
        km.return_on_equity_pct as return_on_equity,
        km.return_on_assets_pct as return_on_assets,
        km.profit_margin_pct as net_margin,
        km.revenue_growth_pct as revenue_growth,
        km.earnings_growth_pct as earnings_growth,
        km.current_ratio,
        km.debt_to_equity
      FROM company_profile cp
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      ${hasComplexFilters ? 'LEFT JOIN key_metrics km ON cp.ticker = km.ticker' : 'LEFT JOIN key_metrics km ON cp.ticker = km.ticker'}
      ${whereClause}
      ${orderClause}
      LIMIT $${paramCount + 1} OFFSET $${paramCount + 2}
    `;

    params.push(limit, offset);

    // Simplified count query for better performance
    const countQuery = `
      SELECT COUNT(*) as total
      FROM company_profile cp
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      ${hasComplexFilters ? 'LEFT JOIN key_metrics km ON cp.ticker = km.ticker' : ''}
      ${whereClause}
    `;

    const [screenResult, countResult] = await Promise.all([
      query(screenQuery, params),
      query(countQuery, params.slice(0, -2))
    ]);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    res.json({
      data: screenResult.rows,
      total,
      page,
      limit,
      totalPages,
      hasNext: page < totalPages,
      hasPrev: page > 1,
      filters: req.query,
      performance: {
        hasComplexFilters,
        resultCount: screenResult.rows.length
      }
    });
  } catch (error) {
    console.error('Error screening stocks:', error);
    res.status(500).json({ 
      error: 'Failed to screen stocks',
      message: error.message
    });
  }
});

// Get detailed stock information by ticker
router.get('/:ticker', async (req, res) => {
  try {
    const { ticker } = req.params;

    const stockQuery = `
      SELECT 
        cp.*,
        md.*,
        km.*,
        gs.audit_risk,
        gs.board_risk,
        gs.compensation_risk,
        gs.shareholder_rights_risk,
        gs.overall_risk
      FROM company_profile cp
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      LEFT JOIN key_metrics km ON cp.ticker = km.ticker
      LEFT JOIN governance_scores gs ON cp.ticker = gs.ticker
      WHERE cp.ticker = $1
    `;

    const result = await query(stockQuery, [ticker.toUpperCase()]);

    if (result.rows.length === 0) {
      return res.status(404).json({ error: 'Stock not found' });
    }

    // Get leadership team
    const leadershipQuery = `
      SELECT person_name, title, age, total_pay, fiscal_year
      FROM leadership_team
      WHERE ticker = $1
      ORDER BY total_pay DESC NULLS LAST
    `;

    const leadershipResult = await query(leadershipQuery, [ticker.toUpperCase()]);

    const stockData = {
      ...result.rows[0],
      leadership_team: leadershipResult.rows
    };

    res.json(stockData);
  } catch (error) {
    console.error('Error fetching stock details:', error);
    res.status(500).json({ error: 'Failed to fetch stock details' });
  }
});

// Get stock price history
router.get('/:ticker/prices', async (req, res) => {
  try {
    const { ticker } = req.params;
    const timeframe = req.query.timeframe || 'daily'; // daily, weekly, monthly
    const limit = parseInt(req.query.limit) || 100;

    let tableName = 'price_daily';
    if (timeframe === 'weekly') tableName = 'price_weekly';
    if (timeframe === 'monthly') tableName = 'price_monthly';

    const priceQuery = `
      SELECT date, open, high, low, close, volume, adj_close
      FROM ${tableName}
      WHERE symbol = $1
      ORDER BY date DESC
      LIMIT $2
    `;

    const result = await query(priceQuery, [ticker.toUpperCase(), limit]);

    res.json({
      ticker: ticker.toUpperCase(),
      timeframe,
      data: result.rows.reverse() // Return in chronological order
    });
  } catch (error) {
    console.error('Error fetching price history:', error);
    res.status(500).json({ error: 'Failed to fetch price history' });
  }
});

// Get financial statements
router.get('/:ticker/financials', async (req, res) => {
  try {
    const { ticker } = req.params;
    const type = req.query.type || 'income'; // income, cash_flow, balance_sheet, quarterly_income, quarterly_cash_flow, quarterly_balance

    let tableName = '';
    
    switch (type) {
      case 'income':
        tableName = 'ttm_income_stmt';
        break;
      case 'cash_flow':
        tableName = 'ttm_cashflow';
        break;
      case 'balance_sheet':
        tableName = 'balance_sheet';
        break;
      case 'quarterly_income':
        tableName = 'quarterly_income_stmt';
        break;
      case 'quarterly_cash_flow':
        tableName = 'quarterly_cashflow';
        break;
      case 'quarterly_balance':
        tableName = 'quarterly_balance_sheet';
        break;
      case 'annual_income':
        tableName = 'income_stmt';
        break;
      case 'annual_cash_flow':
        tableName = 'cash_flow';
        break;
      default:
        return res.status(400).json({ error: 'Invalid financial statement type. Valid types: income, cash_flow, balance_sheet, quarterly_income, quarterly_cash_flow, quarterly_balance, annual_income, annual_cash_flow' });
    }

    // Query using the normalized structure with item_name and value
    const query_text = `
      SELECT symbol, date, item_name, value
      FROM ${tableName}
      WHERE symbol = $1
      ORDER BY date DESC, item_name
    `;

    const result = await query(query_text, [ticker.toUpperCase()]);

    // Transform the normalized data into a more usable structure
    const transformedData = {};
    
    result.rows.forEach(row => {
      const dateKey = row.date;
      if (!transformedData[dateKey]) {
        transformedData[dateKey] = {
          symbol: row.symbol,
          date: row.date,
          items: {}
        };
      }
      transformedData[dateKey].items[row.item_name] = row.value;
    });

    // Convert to array sorted by date (newest first)
    const dataArray = Object.values(transformedData)
      .sort((a, b) => new Date(b.date) - new Date(a.date));

    res.json({
      ticker: ticker.toUpperCase(),
      type,
      table: tableName,
      data: dataArray,
      count: dataArray.length
    });
  } catch (error) {
    console.error('Error fetching financial data:', error);
    res.status(500).json({ error: 'Failed to fetch financial data' });
  }
});

// Get analyst recommendations
router.get('/:ticker/recommendations', async (req, res) => {
  try {
    const { ticker } = req.params;

    const recQuery = `
      SELECT period, strong_buy, buy, hold, sell, strong_sell, collected_date
      FROM analyst_recommendations
      WHERE symbol = $1
      ORDER BY collected_date DESC
      LIMIT 12
    `;

    const result = await query(recQuery, [ticker.toUpperCase()]);

    res.json({
      ticker: ticker.toUpperCase(),
      recommendations: result.rows
    });
  } catch (error) {
    console.error('Error fetching recommendations:', error);
    res.status(500).json({ error: 'Failed to fetch analyst recommendations' });
  }
});

// Get available sectors for filtering
router.get('/filters/sectors', async (req, res) => {
  try {
    const sectorsQuery = `
      SELECT DISTINCT sector, COUNT(*) as count
      FROM company_profile 
      WHERE sector IS NOT NULL
      GROUP BY sector
      ORDER BY count DESC, sector
    `;

    const result = await query(sectorsQuery);

    res.json({
      sectors: result.rows
    });
  } catch (error) {
    console.error('Error fetching sectors:', error);
    res.status(500).json({ error: 'Failed to fetch sectors' });
  }
});

// Get stock profile data for detail page
router.get('/:ticker/profile', async (req, res) => {
  try {
    const { ticker } = req.params;

    const profileQuery = `
      SELECT 
        ticker as symbol,
        short_name as company_name,
        long_name as full_name,
        sector,
        industry,
        country,
        exchange,
        currency,        website,        business_summary as description,
        md.market_cap as market_capitalization,
        md.regular_market_price as price,
        md.regular_market_previous_close as previous_close,
        (md.regular_market_price - md.regular_market_previous_close) as regular_market_change,
        ((md.regular_market_price - md.regular_market_previous_close) / md.regular_market_previous_close * 100) as regular_market_change_percent,
        md.fifty_two_week_high,
        md.fifty_two_week_low
      FROM company_profile cp
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      WHERE cp.ticker = $1
    `;

    const result = await query(profileQuery, [ticker.toUpperCase()]);

    if (result.rows.length === 0) {
      return res.status(404).json({ error: 'Stock not found' });
    }

    res.json(result.rows);
  } catch (error) {
    console.error('Error fetching stock profile:', error);
    res.status(500).json({ error: 'Failed to fetch stock profile' });
  }
});

// Get stock metrics for detail page
router.get('/:ticker/metrics', async (req, res) => {
  try {
    const { ticker } = req.params;

    const metricsQuery = `
      SELECT 
        ticker as symbol,
        market_cap as market_capitalization,
        trailing_pe as pe_ratio,
        peg_ratio,
        price_to_book as pb_ratio,
        enterprise_value,
        dividend_yield,
        book_value,
        earnings_per_share,
        current_ratio,
        debt_to_equity,
        return_on_equity_pct as return_on_equity,
        return_on_assets_pct as return_on_assets,
        gross_margin_pct as gross_margin,
        operating_margin_pct as operating_margin,
        profit_margin_pct as net_margin,
        asset_turnover,
        revenue_growth_pct as revenue_growth,
        earnings_growth_pct as earnings_growth,
        collected_date
      FROM key_metrics
      WHERE ticker = $1
      ORDER BY collected_date DESC
      LIMIT 1
    `;

    const result = await query(metricsQuery, [ticker.toUpperCase()]);

    res.json(result.rows);
  } catch (error) {
    console.error('Error fetching stock metrics:', error);
    res.status(500).json({ error: 'Failed to fetch stock metrics' });
  }
});

module.exports = router;
