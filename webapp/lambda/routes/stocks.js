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
      SELECT 
        cp.ticker,
        cp.short_name,
        cp.long_name,
        cp.sector,
        cp.industry,
        md.market_cap,
        cp.currency,
        cp.exchange,
        md.regular_market_price,
        md.regular_market_change,
        md.regular_market_change_percent,
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
    const limit = parseInt(req.query.limit) || 50;
    const offset = (page - 1) * limit;
    const sortBy = req.query.sortBy || 'market_cap';
    const sortOrder = req.query.sortOrder || 'desc';

    // Build WHERE clause based on filters
    let whereClause = 'WHERE 1=1';
    const params = [];
    let paramCount = 0;

    // Price filters
    if (req.query.priceMin) {
      paramCount++;
      whereClause += ` AND md.regular_market_price >= $${paramCount}`;
      params.push(parseFloat(req.query.priceMin));
    }
    if (req.query.priceMax) {
      paramCount++;
      whereClause += ` AND md.regular_market_price <= $${paramCount}`;
      params.push(parseFloat(req.query.priceMax));
    }    // Market cap filters (convert billions to actual values)
    if (req.query.marketCapMin) {
      paramCount++;
      whereClause += ` AND md.market_cap >= $${paramCount}`;
      params.push(parseFloat(req.query.marketCapMin) * 1000000000);
    }
    if (req.query.marketCapMax) {
      paramCount++;
      whereClause += ` AND md.market_cap <= $${paramCount}`;
      params.push(parseFloat(req.query.marketCapMax) * 1000000000);
    }

    // Valuation filters
    if (req.query.peRatioMin) {
      paramCount++;
      whereClause += ` AND km.trailing_pe >= $${paramCount}`;
      params.push(parseFloat(req.query.peRatioMin));
    }
    if (req.query.peRatioMax) {
      paramCount++;
      whereClause += ` AND km.trailing_pe <= $${paramCount}`;
      params.push(parseFloat(req.query.peRatioMax));
    }

    // Profitability filters
    if (req.query.roeMin) {
      paramCount++;
      whereClause += ` AND km.return_on_equity >= $${paramCount}`;
      params.push(parseFloat(req.query.roeMin) / 100);
    }
    if (req.query.roeMax) {
      paramCount++;
      whereClause += ` AND km.return_on_equity <= $${paramCount}`;
      params.push(parseFloat(req.query.roeMax) / 100);
    }

    // Dividend filters
    if (req.query.dividendYieldMin) {
      paramCount++;
      whereClause += ` AND km.dividend_yield >= $${paramCount}`;
      params.push(parseFloat(req.query.dividendYieldMin) / 100);
    }
    if (req.query.dividendYieldMax) {
      paramCount++;
      whereClause += ` AND km.dividend_yield <= $${paramCount}`;
      params.push(parseFloat(req.query.dividendYieldMax) / 100);
    }

    // Sector and industry filters
    if (req.query.sector) {
      paramCount++;
      whereClause += ` AND cp.sector = $${paramCount}`;
      params.push(req.query.sector);
    }
    if (req.query.country) {
      paramCount++;
      whereClause += ` AND cp.country ILIKE $${paramCount}`;
      params.push(`%${req.query.country}%`);
    }
    if (req.query.exchange) {
      paramCount++;
      whereClause += ` AND cp.exchange = $${paramCount}`;
      params.push(req.query.exchange);
    }

    // Boolean filters
    if (req.query.paysDividends === 'true') {
      whereClause += ` AND km.dividend_yield > 0`;
    }
    if (req.query.hasPositiveCashFlow === 'true') {
      whereClause += ` AND EXISTS (SELECT 1 FROM ttm_cash_flow tcf WHERE tcf.symbol = cp.ticker AND tcf.free_cash_flow > 0)`;
    }
    if (req.query.hasEarningsGrowth === 'true') {
      whereClause += ` AND km.earnings_growth > 0`;
    }

    // Build ORDER BY clause
    let orderClause = '';    const validSortColumns = {
      'market_capitalization': 'md.market_cap',
      'price': 'md.regular_market_price',
      'pe_ratio': 'km.trailing_pe',
      'dividend_yield': 'km.dividend_yield',
      'return_on_equity': 'km.return_on_equity',
      'revenue_growth': 'km.revenue_growth',
      'symbol': 'cp.ticker',
      'company_name': 'cp.short_name',
      'sector': 'cp.sector'
    };

    if (validSortColumns[sortBy]) {
      orderClause = `ORDER BY ${validSortColumns[sortBy]} ${sortOrder.toUpperCase()} NULLS LAST`;
    } else {
      orderClause = 'ORDER BY md.market_cap DESC NULLS LAST';
    }    const screenQuery = `
      SELECT 
        cp.ticker as symbol,
        cp.short_name as company_name,
        cp.sector,
        cp.industry,
        cp.country,
        cp.exchange,
        md.market_cap as market_capitalization,
        md.regular_market_price as price,
        md.regular_market_change,
        md.regular_market_change_percent,
        km.trailing_pe as pe_ratio,
        km.peg_ratio,
        km.price_to_book as pb_ratio,
        km.dividend_yield,
        km.return_on_equity,
        km.return_on_assets,
        km.net_margin,
        km.revenue_growth,
        km.earnings_growth,
        km.current_ratio,
        km.debt_to_equity
      FROM company_profile cp
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      LEFT JOIN key_metrics km ON cp.ticker = km.ticker
      ${whereClause}
      ${orderClause}
      LIMIT $${paramCount + 1} OFFSET $${paramCount + 2}
    `;

    params.push(limit, offset);

    // Count query for pagination
    const countQuery = `
      SELECT COUNT(*) as total
      FROM company_profile cp
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      LEFT JOIN key_metrics km ON cp.ticker = km.ticker
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
      filters: req.query
    });
  } catch (error) {
    console.error('Error screening stocks:', error);
    res.status(500).json({ error: 'Failed to screen stocks' });
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
    const type = req.query.type || 'income'; // income, cash_flow, balance_sheet

    let query_text = '';
    let tableName = '';

    switch (type) {
      case 'income':
        tableName = 'ttm_income_stmt';
        query_text = `
          SELECT symbol, date, revenue, gross_profit, operating_income, net_income,
                 ebit, basic_eps, diluted_eps, operating_expense
          FROM ${tableName}
          WHERE symbol = $1
          ORDER BY date DESC
        `;
        break;
      case 'cash_flow':
        tableName = 'ttm_cash_flow';
        query_text = `
          SELECT symbol, date, operating_cash_flow, free_cash_flow, 
                 capital_expenditure, financing_cash_flow, investing_cash_flow
          FROM ${tableName}
          WHERE symbol = $1
          ORDER BY date DESC
        `;
        break;
      default:
        return res.status(400).json({ error: 'Invalid financial statement type' });
    }

    const result = await query(query_text, [ticker.toUpperCase()]);

    res.json({
      ticker: ticker.toUpperCase(),
      type,
      data: result.rows
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
        currency,        website,
        business_summary as description,
        md.market_cap as market_capitalization,
        md.regular_market_price as price,
        md.regular_market_previous_close as previous_close,
        md.regular_market_change,
        md.regular_market_change_percent,
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
        return_on_equity,
        return_on_assets,
        gross_margin,
        operating_margin,
        net_margin,
        asset_turnover,
        revenue_growth,
        earnings_growth,
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
