const express = require('express');
const { query } = require('../utils/database');

const router = express.Router();

// Get market overview metrics
router.get('/overview', async (req, res) => {
  try {
    // Get market summary statistics
    const overviewQuery = `
      SELECT 
        COUNT(*) as total_stocks,
        AVG(md.regular_market_price) as avg_price,
        AVG(km.trailing_pe) as avg_pe,
        AVG(km.price_to_book) as avg_pb,
        AVG(km.dividend_yield) as avg_dividend_yield,
        SUM(cp.market_cap) as total_market_cap,
        COUNT(CASE WHEN md.regular_market_change_percent > 0 THEN 1 END) as gainers,
        COUNT(CASE WHEN md.regular_market_change_percent < 0 THEN 1 END) as losers
      FROM company_profile cp
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      LEFT JOIN key_metrics km ON cp.ticker = km.ticker
      WHERE cp.market_cap IS NOT NULL
    `;

    // Get top performers
    const topGainersQuery = `
      SELECT cp.ticker, cp.short_name, md.regular_market_change_percent
      FROM company_profile cp
      JOIN market_data md ON cp.ticker = md.ticker
      WHERE md.regular_market_change_percent IS NOT NULL
      ORDER BY md.regular_market_change_percent DESC
      LIMIT 10
    `;

    const topLosersQuery = `
      SELECT cp.ticker, cp.short_name, md.regular_market_change_percent
      FROM company_profile cp
      JOIN market_data md ON cp.ticker = md.ticker
      WHERE md.regular_market_change_percent IS NOT NULL
      ORDER BY md.regular_market_change_percent ASC
      LIMIT 10
    `;

    // Get sector performance
    const sectorQuery = `
      SELECT 
        cp.sector,
        COUNT(*) as stock_count,
        AVG(md.regular_market_change_percent) as avg_change,
        SUM(cp.market_cap) as sector_market_cap
      FROM company_profile cp
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      WHERE cp.sector IS NOT NULL AND cp.market_cap IS NOT NULL
      GROUP BY cp.sector
      ORDER BY avg_change DESC
    `;

    const [overviewResult, gainersResult, losersResult, sectorResult] = await Promise.all([
      query(overviewQuery),
      query(topGainersQuery),
      query(topLosersQuery),
      query(sectorQuery)
    ]);

    res.json({
      overview: overviewResult.rows[0],
      top_gainers: gainersResult.rows,
      top_losers: losersResult.rows,
      sector_performance: sectorResult.rows
    });
  } catch (error) {
    console.error('Error fetching market overview:', error);
    res.status(500).json({ error: 'Failed to fetch market overview' });
  }
});

// Get valuation metrics with filtering
router.get('/valuation', async (req, res) => {
  try {
    const minMarketCap = req.query.minMarketCap || 0;
    const maxPE = req.query.maxPE || 100;
    const sector = req.query.sector || '';
    const limit = parseInt(req.query.limit) || 50;

    let whereClause = 'WHERE km.trailing_pe IS NOT NULL AND km.trailing_pe > 0';
    const params = [];
    let paramCount = 0;

    if (minMarketCap > 0) {
      paramCount++;
      whereClause += ` AND cp.market_cap >= $${paramCount}`;
      params.push(minMarketCap);
    }

    if (maxPE < 100) {
      paramCount++;
      whereClause += ` AND km.trailing_pe <= $${paramCount}`;
      params.push(maxPE);
    }

    if (sector) {
      paramCount++;
      whereClause += ` AND cp.sector = $${paramCount}`;
      params.push(sector);
    }

    const valuationQuery = `
      SELECT 
        cp.ticker,
        cp.short_name,
        cp.sector,
        cp.market_cap,
        km.trailing_pe,
        km.forward_pe,
        km.price_to_book,
        km.price_to_sales_ttm,
        km.peg_ratio,
        km.ev_to_revenue,
        km.ev_to_ebitda,
        km.dividend_yield,
        md.regular_market_price
      FROM company_profile cp
      JOIN key_metrics km ON cp.ticker = km.ticker
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      ${whereClause}
      ORDER BY km.trailing_pe ASC
      LIMIT $${paramCount + 1}
    `;

    params.push(limit);

    const result = await query(valuationQuery, params);

    res.json({
      filters: {
        minMarketCap: parseInt(minMarketCap),
        maxPE: parseFloat(maxPE),
        sector: sector || 'all'
      },
      data: result.rows
    });
  } catch (error) {
    console.error('Error fetching valuation metrics:', error);
    res.status(500).json({ error: 'Failed to fetch valuation metrics' });
  }
});

// Get growth metrics
router.get('/growth', async (req, res) => {
  try {
    const minGrowth = parseFloat(req.query.minGrowth) || 0;
    const sector = req.query.sector || '';
    const limit = parseInt(req.query.limit) || 50;

    let whereClause = 'WHERE km.revenue_growth_pct IS NOT NULL';
    const params = [];
    let paramCount = 0;

    if (minGrowth > 0) {
      paramCount++;
      whereClause += ` AND km.revenue_growth_pct >= $${paramCount}`;
      params.push(minGrowth);
    }

    if (sector) {
      paramCount++;
      whereClause += ` AND cp.sector = $${paramCount}`;
      params.push(sector);
    }

    const growthQuery = `
      SELECT 
        cp.ticker,
        cp.short_name,
        cp.sector,
        cp.market_cap,
        km.revenue_growth_pct,
        km.earnings_growth_pct,
        km.earnings_q_growth_pct,
        km.total_revenue,
        km.net_income,
        km.operating_margin_pct,
        km.profit_margin_pct,
        km.return_on_equity_pct,
        km.return_on_assets_pct
      FROM company_profile cp
      JOIN key_metrics km ON cp.ticker = km.ticker
      ${whereClause}
      ORDER BY km.revenue_growth_pct DESC NULLS LAST
      LIMIT $${paramCount + 1}
    `;

    params.push(limit);

    const result = await query(growthQuery, params);

    res.json({
      filters: {
        minGrowth,
        sector: sector || 'all'
      },
      data: result.rows
    });
  } catch (error) {
    console.error('Error fetching growth metrics:', error);
    res.status(500).json({ error: 'Failed to fetch growth metrics' });
  }
});

// Get dividend-focused metrics
router.get('/dividends', async (req, res) => {
  try {
    const minYield = parseFloat(req.query.minYield) || 0;
    const sector = req.query.sector || '';
    const limit = parseInt(req.query.limit) || 50;

    let whereClause = 'WHERE km.dividend_yield IS NOT NULL AND km.dividend_yield > 0';
    const params = [];
    let paramCount = 0;

    if (minYield > 0) {
      paramCount++;
      whereClause += ` AND km.dividend_yield >= $${paramCount}`;
      params.push(minYield);
    }

    if (sector) {
      paramCount++;
      whereClause += ` AND cp.sector = $${paramCount}`;
      params.push(sector);
    }

    const dividendQuery = `
      SELECT 
        cp.ticker,
        cp.short_name,
        cp.sector,
        cp.market_cap,
        km.dividend_yield,
        km.dividend_rate,
        km.five_year_avg_dividend_yield,
        km.last_annual_dividend_amt,
        km.trailing_pe,
        km.current_ratio,
        km.debt_to_equity,
        md.regular_market_price
      FROM company_profile cp
      JOIN key_metrics km ON cp.ticker = km.ticker
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      ${whereClause}
      ORDER BY km.dividend_yield DESC
      LIMIT $${paramCount + 1}
    `;

    params.push(limit);

    const result = await query(dividendQuery, params);

    res.json({
      filters: {
        minYield,
        sector: sector || 'all'
      },
      data: result.rows
    });
  } catch (error) {
    console.error('Error fetching dividend metrics:', error);
    res.status(500).json({ error: 'Failed to fetch dividend metrics' });
  }
});

// Get financial strength metrics
router.get('/financial-strength', async (req, res) => {
  try {
    const minCurrentRatio = parseFloat(req.query.minCurrentRatio) || 1;
    const maxDebtToEquity = parseFloat(req.query.maxDebtToEquity) || 2;
    const sector = req.query.sector || '';
    const limit = parseInt(req.query.limit) || 50;

    let whereClause = 'WHERE km.current_ratio IS NOT NULL AND km.debt_to_equity IS NOT NULL';
    const params = [];
    let paramCount = 0;

    if (minCurrentRatio > 0) {
      paramCount++;
      whereClause += ` AND km.current_ratio >= $${paramCount}`;
      params.push(minCurrentRatio);
    }

    if (maxDebtToEquity > 0) {
      paramCount++;
      whereClause += ` AND km.debt_to_equity <= $${paramCount}`;
      params.push(maxDebtToEquity);
    }

    if (sector) {
      paramCount++;
      whereClause += ` AND cp.sector = $${paramCount}`;
      params.push(sector);
    }

    const strengthQuery = `
      SELECT 
        cp.ticker,
        cp.short_name,
        cp.sector,
        cp.market_cap,
        km.current_ratio,
        km.quick_ratio,
        km.debt_to_equity,
        km.total_cash,
        km.cash_per_share,
        km.free_cashflow,
        km.operating_cashflow,
        km.return_on_equity_pct,
        km.return_on_assets_pct
      FROM company_profile cp
      JOIN key_metrics km ON cp.ticker = km.ticker
      ${whereClause}
      ORDER BY km.current_ratio DESC, km.debt_to_equity ASC
      LIMIT $${paramCount + 1}
    `;

    params.push(limit);

    const result = await query(strengthQuery, params);

    res.json({
      filters: {
        minCurrentRatio,
        maxDebtToEquity,
        sector: sector || 'all'
      },
      data: result.rows
    });
  } catch (error) {
    console.error('Error fetching financial strength metrics:', error);
    res.status(500).json({ error: 'Failed to fetch financial strength metrics' });
  }
});

// Get screener with multiple criteria
router.get('/screener', async (req, res) => {
  try {
    const {
      minMarketCap = 0,
      maxPE = 50,
      minDividendYield = 0,
      minROE = 0,
      maxDebtToEquity = 2,
      sector = '',
      limit = 100
    } = req.query;

    let whereClause = `WHERE cp.market_cap IS NOT NULL 
                       AND km.trailing_pe IS NOT NULL 
                       AND km.trailing_pe > 0`;
    const params = [];
    let paramCount = 0;

    // Apply filters
    if (parseFloat(minMarketCap) > 0) {
      paramCount++;
      whereClause += ` AND cp.market_cap >= $${paramCount}`;
      params.push(parseFloat(minMarketCap));
    }

    if (parseFloat(maxPE) < 100) {
      paramCount++;
      whereClause += ` AND km.trailing_pe <= $${paramCount}`;
      params.push(parseFloat(maxPE));
    }

    if (parseFloat(minDividendYield) > 0) {
      paramCount++;
      whereClause += ` AND km.dividend_yield >= $${paramCount}`;
      params.push(parseFloat(minDividendYield));
    }

    if (parseFloat(minROE) > 0) {
      paramCount++;
      whereClause += ` AND km.return_on_equity_pct >= $${paramCount}`;
      params.push(parseFloat(minROE));
    }

    if (parseFloat(maxDebtToEquity) < 10) {
      paramCount++;
      whereClause += ` AND (km.debt_to_equity <= $${paramCount} OR km.debt_to_equity IS NULL)`;
      params.push(parseFloat(maxDebtToEquity));
    }

    if (sector) {
      paramCount++;
      whereClause += ` AND cp.sector = $${paramCount}`;
      params.push(sector);
    }

    const screenerQuery = `
      SELECT 
        cp.ticker,
        cp.short_name,
        cp.sector,
        cp.market_cap,
        md.regular_market_price,
        md.regular_market_change_percent,
        km.trailing_pe,
        km.forward_pe,
        km.price_to_book,
        km.dividend_yield,
        km.return_on_equity_pct,
        km.debt_to_equity,
        km.current_ratio,
        km.revenue_growth_pct,
        km.earnings_growth_pct
      FROM company_profile cp
      JOIN key_metrics km ON cp.ticker = km.ticker
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      ${whereClause}
      ORDER BY cp.market_cap DESC
      LIMIT $${paramCount + 1}
    `;

    params.push(parseInt(limit));

    const result = await query(screenerQuery, params);

    res.json({
      filters: {
        minMarketCap: parseFloat(minMarketCap),
        maxPE: parseFloat(maxPE),
        minDividendYield: parseFloat(minDividendYield),
        minROE: parseFloat(minROE),
        maxDebtToEquity: parseFloat(maxDebtToEquity),
        sector: sector || 'all',
        limit: parseInt(limit)
      },
      count: result.rows.length,
      data: result.rows
    });
  } catch (error) {
    console.error('Error running stock screener:', error);
    res.status(500).json({ error: 'Failed to run stock screener' });
  }
});

module.exports = router;
