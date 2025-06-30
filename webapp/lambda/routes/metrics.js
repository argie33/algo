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
        SUM(md.market_cap) as total_market_cap,
        COUNT(CASE WHEN (md.regular_market_price - md.regular_market_previous_close) > 0 THEN 1 END) as gainers,
        COUNT(CASE WHEN (md.regular_market_price - md.regular_market_previous_close) < 0 THEN 1 END) as losers
      FROM company_profile cp
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      LEFT JOIN key_metrics km ON cp.ticker = km.ticker
      WHERE md.market_cap IS NOT NULL
        AND md.regular_market_price IS NOT NULL 
        AND md.regular_market_previous_close IS NOT NULL 
        AND md.regular_market_previous_close > 0
    `;

    // Get top performers
    const topGainersQuery = `
      SELECT 
        cp.ticker, 
        cp.short_name, 
        CASE 
          WHEN md.regular_market_previous_close > 0 
          THEN ((md.regular_market_price - md.regular_market_previous_close) / md.regular_market_previous_close) * 100
          ELSE 0 
        END as regular_market_change_percent
      FROM company_profile cp
      JOIN market_data md ON cp.ticker = md.ticker
      WHERE md.regular_market_price IS NOT NULL 
        AND md.regular_market_previous_close IS NOT NULL
        AND md.regular_market_previous_close > 0
      ORDER BY regular_market_change_percent DESC
      LIMIT 10
    `;

    const topLosersQuery = `
      SELECT 
        cp.ticker, 
        cp.short_name, 
        CASE 
          WHEN md.regular_market_previous_close > 0 
          THEN ((md.regular_market_price - md.regular_market_previous_close) / md.regular_market_previous_close) * 100
          ELSE 0 
        END as regular_market_change_percent
      FROM company_profile cp
      JOIN market_data md ON cp.ticker = md.ticker
      WHERE md.regular_market_price IS NOT NULL 
        AND md.regular_market_previous_close IS NOT NULL
        AND md.regular_market_previous_close > 0
      ORDER BY regular_market_change_percent ASC
      LIMIT 10
    `;

    // Get sector performance
    const sectorQuery = `
      SELECT 
        cp.sector,
        COUNT(*) as stock_count,
        AVG(
          CASE 
            WHEN md.regular_market_previous_close > 0 
            THEN ((md.regular_market_price - md.regular_market_previous_close) / md.regular_market_previous_close) * 100
            ELSE 0 
          END
        ) as avg_change,
        SUM(md.market_cap) as sector_market_cap
      FROM company_profile cp
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      WHERE cp.sector IS NOT NULL AND md.market_cap IS NOT NULL
        AND md.regular_market_price IS NOT NULL 
        AND md.regular_market_previous_close IS NOT NULL
        AND md.regular_market_previous_close > 0
      GROUP BY cp.sector
      ORDER BY avg_change DESC
    `;

    const [overviewResult, gainersResult, losersResult, sectorResult] = await Promise.all([
      query(overviewQuery),
      query(topGainersQuery),
      query(topLosersQuery),
      query(sectorQuery)
    ]);

    if (!overviewResult || !Array.isArray(overviewResult.rows) || overviewResult.rows.length === 0) {
      return res.status(404).json({ error: 'No data found for this query' });
    }

    res.json({
      overview: overviewResult.rows[0],
      top_gainers: gainersResult.rows,
      top_losers: losersResult.rows,
      sector_performance: sectorResult.rows
    });
  } catch (error) {
    return res.status(500).json({ error: 'Database error', details: error.message });
  }
});

// Get valuation metrics with filtering
router.get('/valuation', async (req, res) => {
  try {
    const minMarketCap = req.query.minMarketCap || 0;
    const maxPE = req.query.maxPE || 50;
    const sector = req.query.sector || '';
    const limit = parseInt(req.query.limit) || 50;

    let whereClause = 'WHERE km.trailing_pe IS NOT NULL AND md.market_cap IS NOT NULL';
    const params = [];
    let paramCount = 0;

    if (parseFloat(minMarketCap) > 0) {
      paramCount++;
      whereClause += ` AND md.market_cap >= $${paramCount}`;
      params.push(parseFloat(minMarketCap) * 1000000000);
    }

    if (parseFloat(maxPE) < 50) {
      paramCount++;
      whereClause += ` AND km.trailing_pe <= $${paramCount}`;
      params.push(parseFloat(maxPE));
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
        md.market_cap,
        md.regular_market_price,
        km.trailing_pe,
        km.forward_pe,
        km.peg_ratio,
        km.price_to_book,
        km.price_to_sales_ttm,
        km.enterprise_value
      FROM company_profile cp
      JOIN key_metrics km ON cp.ticker = km.ticker
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      ${whereClause}
      ORDER BY km.trailing_pe ASC
      LIMIT $${paramCount + 1}
    `;

    params.push(limit);

    const result = await query(valuationQuery, params);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.status(404).json({ error: 'No data found for this query' });
    }

    res.json({
      filters: {
        minMarketCap: parseFloat(minMarketCap),
        maxPE: parseFloat(maxPE),
        sector: sector || 'all'
      },
      data: result.rows
    });
  } catch (error) {
    return res.status(500).json({ error: 'Database error', details: error.message });
  }
});

// Get growth metrics
router.get('/growth', async (req, res) => {
  try {
    const minGrowth = req.query.minGrowth || 0;
    const sector = req.query.sector || '';
    const limit = parseInt(req.query.limit) || 50;

    let whereClause = 'WHERE km.revenue_growth_pct IS NOT NULL';
    const params = [];
    let paramCount = 0;

    if (parseFloat(minGrowth) > 0) {
      paramCount++;
      whereClause += ` AND km.revenue_growth_pct >= $${paramCount}`;
      params.push(parseFloat(minGrowth) / 100);
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
        md.market_cap,
        km.revenue_growth_pct,
        km.earnings_growth_pct,
        km.quarterly_revenue_growth_pct,
        km.quarterly_earnings_growth_pct
      FROM company_profile cp
      JOIN key_metrics km ON cp.ticker = km.ticker
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      ${whereClause}
      ORDER BY km.revenue_growth_pct DESC NULLS LAST
      LIMIT $${paramCount + 1}
    `;

    params.push(limit);

    const result = await query(growthQuery, params);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.status(404).json({ error: 'No data found for this query' });
    }

    res.json({
      filters: {
        minGrowth,
        sector: sector || 'all'
      },
      data: result.rows
    });
  } catch (error) {
    return res.status(500).json({ error: 'Database error', details: error.message });
  }
});

// Get dividend metrics
router.get('/dividends', async (req, res) => {
  try {
    const minYield = req.query.minYield || 0;
    const sector = req.query.sector || '';
    const limit = parseInt(req.query.limit) || 50;

    let whereClause = 'WHERE km.dividend_yield IS NOT NULL AND km.dividend_yield > 0';
    const params = [];
    let paramCount = 0;

    if (parseFloat(minYield) > 0) {
      paramCount++;
      whereClause += ` AND km.dividend_yield >= $${paramCount}`;
      params.push(parseFloat(minYield) / 100);
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
        md.market_cap,
        km.dividend_yield,
        km.payout_ratio,
        km.dividend_date,
        km.ex_dividend_date
      FROM company_profile cp
      JOIN key_metrics km ON cp.ticker = km.ticker
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      ${whereClause}
      ORDER BY km.dividend_yield DESC
      LIMIT $${paramCount + 1}
    `;

    params.push(limit);

    const result = await query(dividendQuery, params);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.status(404).json({ error: 'No data found for this query' });
    }

    res.json({
      filters: {
        minYield,
        sector: sector || 'all'
      },
      data: result.rows
    });
  } catch (error) {
    return res.status(500).json({ error: 'Database error', details: error.message });
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

    if (minCurrentRatio > 1) {
      paramCount++;
      whereClause += ` AND km.current_ratio >= $${paramCount}`;
      params.push(minCurrentRatio);
    }

    if (maxDebtToEquity < 2) {
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
        md.market_cap,
        km.current_ratio,
        km.quick_ratio,
        km.debt_to_equity,
        km.total_debt,
        km.total_cash,
        km.operating_cashflow,
        km.return_on_equity_pct,
        km.return_on_assets_pct
      FROM company_profile cp
      JOIN key_metrics km ON cp.ticker = km.ticker
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      ${whereClause}
      ORDER BY km.current_ratio DESC, km.debt_to_equity ASC
      LIMIT $${paramCount + 1}
    `;

    params.push(limit);

    const result = await query(strengthQuery, params);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.status(404).json({ error: 'No data found for this query' });
    }

    res.json({
      filters: {
        minCurrentRatio,
        maxDebtToEquity,
        sector: sector || 'all'
      },
      data: result.rows
    });
  } catch (error) {
    return res.status(500).json({ error: 'Database error', details: error.message });
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
      limit = 50
    } = req.query;

    let whereClause = 'WHERE md.market_cap IS NOT NULL';
    const params = [];
    let paramCount = 0;

    if (parseFloat(minMarketCap) > 0) {
      paramCount++;
      whereClause += ` AND md.market_cap >= $${paramCount}`;
      params.push(parseFloat(minMarketCap) * 1000000000);
    }

    if (parseFloat(maxPE) < 50) {
      paramCount++;
      whereClause += ` AND km.trailing_pe <= $${paramCount}`;
      params.push(parseFloat(maxPE));
    }

    if (parseFloat(minDividendYield) > 0) {
      paramCount++;
      whereClause += ` AND km.dividend_yield >= $${paramCount}`;
      params.push(parseFloat(minDividendYield) / 100);
    }

    if (parseFloat(minROE) > 0) {
      paramCount++;
      whereClause += ` AND km.return_on_equity_pct >= $${paramCount}`;
      params.push(parseFloat(minROE) / 100);
    }

    if (parseFloat(maxDebtToEquity) < 2) {
      paramCount++;
      whereClause += ` AND km.debt_to_equity <= $${paramCount}`;
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
        md.market_cap,
        md.regular_market_price,
        km.trailing_pe,
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
      ORDER BY md.market_cap DESC
      LIMIT $${paramCount + 1}
    `;

    params.push(parseInt(limit));

    const result = await query(screenerQuery, params);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.status(404).json({ error: 'No data found for this query' });
    }

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
    return res.status(500).json({ error: 'Database error', details: error.message });
  }
});

module.exports = router;
