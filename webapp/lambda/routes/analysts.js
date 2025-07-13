const express = require('express');
const { query } = require('../utils/database');

const router = express.Router();

// Get analyst upgrades/downgrades
router.get('/upgrades', async (req, res) => {
  try {
    const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 25;
    const offset = (page - 1) * limit;
      const upgradesQuery = `
      SELECT 
        aud.symbol,
        s.short_name AS company_name,
        aud.from_grade,
        aud.to_grade,
        aud.action,
        aud.firm,
        aud.date,
        aud.details
      FROM analyst_upgrade_downgrade aud
      LEFT JOIN symbols s ON aud.symbol = s.symbol
      ORDER BY aud.date DESC
      LIMIT $1 OFFSET $2
    `;

    const countQuery = `
      SELECT COUNT(*) as total
      FROM analyst_upgrade_downgrade
    `;

    const [upgradesResult, countResult] = await Promise.all([
      query(upgradesQuery, [limit, offset]),
      query(countQuery)
    ]);

    if (!upgradesResult || !Array.isArray(upgradesResult.rows)) {
      throw new Error('No rows returned from analyst_upgrade_downgrade query');
    }
    if (!countResult || !Array.isArray(countResult.rows) || countResult.rows.length === 0) {
      throw new Error('No count returned from analyst_upgrade_downgrade query');
    }

    // Map company_name to company for frontend compatibility
    const mappedRows = upgradesResult.rows.map(row => ({
      ...row,
      company: row.company_name
    }));

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    res.json({
      data: mappedRows,
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
    console.error('Error fetching analyst upgrades:', error);
    res.status(500).json({ 
      error: 'Failed to fetch analyst upgrades',
      message: error.message 
    });
  }
});

// Get recommendations for specific stock
router.get('/:ticker/recommendations', async (req, res) => {
  try {
    const { ticker } = req.params;

    const recQuery = `
      SELECT 
        period,
        strong_buy,
        buy,
        hold,
        sell,
        strong_sell,
        collected_date
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
    res.status(500).json({ error: 'Failed to fetch recommendations' });
  }
});

// Get earnings estimates
router.get('/:ticker/earnings-estimates', async (req, res) => {
  try {
    const { ticker } = req.params;

    const estimatesQuery = `
      SELECT 
        period,
        estimate,
        actual,
        difference,
        surprise_percent,
        reported_date
        FROM earnings_estimates
      WHERE symbol = $1
      ORDER BY reported_date DESC
      LIMIT 8
    `;

    const result = await query(estimatesQuery, [ticker.toUpperCase()]);

    res.json({
      ticker: ticker.toUpperCase(),
      estimates: result.rows
    });

  } catch (error) {
    console.error('Error fetching earnings estimates:', error);
    res.status(500).json({ error: 'Failed to fetch earnings estimates' });
  }
});

// Get revenue estimates
router.get('/:ticker/revenue-estimates', async (req, res) => {
  try {
    const { ticker } = req.params;

    const revenueQuery = `
      SELECT 
        period,
        estimate,
        actual,
        difference,
        surprise_percent,
        reported_date      FROM revenue_estimates
      WHERE symbol = $1
      ORDER BY reported_date DESC
      LIMIT 8
    `;

    const result = await query(revenueQuery, [ticker.toUpperCase()]);

    res.json({
      ticker: ticker.toUpperCase(),
      estimates: result.rows
    });

  } catch (error) {
    console.error('Error fetching revenue estimates:', error);
    res.status(500).json({ error: 'Failed to fetch revenue estimates' });
  }
});

// Get earnings history
router.get('/:ticker/earnings-history', async (req, res) => {
  try {
    const { ticker } = req.params;

    const historyQuery = `
      SELECT 
        quarter,
        estimate,
        actual,
        difference,
        surprise_percent,
        earnings_date
      FROM earnings_history
      WHERE symbol = $1
      ORDER BY earnings_date DESC
      LIMIT 12
    `;

    const result = await query(historyQuery, [ticker.toUpperCase()]);

    res.json({
      ticker: ticker.toUpperCase(),
      history: result.rows
    });

  } catch (error) {
    console.error('Error fetching earnings history:', error);
    res.status(500).json({ error: 'Failed to fetch earnings history' });
  }
});

// Get EPS revisions for a ticker
router.get('/:ticker/eps-revisions', async (req, res) => {
  try {
    const { ticker } = req.params;
    
    const revisionsQuery = `
      SELECT 
        symbol,
        period,
        up_last7days,
        up_last30days,
        down_last30days,
        down_last7days,
        fetched_at
      FROM eps_revisions
      WHERE UPPER(symbol) = UPPER($1)
      ORDER BY 
        CASE 
          WHEN period = '0q' THEN 1
          WHEN period = '+1q' THEN 2
          WHEN period = '0y' THEN 3
          WHEN period = '+1y' THEN 4
          ELSE 5
        END
    `;
    
    const result = await query(revisionsQuery, [ticker]);
    
    res.json({
      success: true,
      ticker: ticker.toUpperCase(),
      data: result.rows,
      metadata: {
        count: result.rows.length,
        timestamp: new Date().toISOString()
      }
    });
    
  } catch (error) {
    console.error('EPS revisions fetch error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch EPS revisions',
      message: error.message
    });
  }
});

// Get EPS trend for a ticker
router.get('/:ticker/eps-trend', async (req, res) => {
  try {
    const { ticker } = req.params;
    
    const trendQuery = `
      SELECT 
        symbol,
        period,
        current,
        days7ago,
        days30ago,
        days60ago,
        days90ago,
        fetched_at
      FROM eps_trend
      WHERE UPPER(symbol) = UPPER($1)
      ORDER BY 
        CASE 
          WHEN period = '0q' THEN 1
          WHEN period = '+1q' THEN 2
          WHEN period = '0y' THEN 3
          WHEN period = '+1y' THEN 4
          ELSE 5
        END
    `;
    
    const result = await query(trendQuery, [ticker]);
    
    res.json({
      success: true,
      ticker: ticker.toUpperCase(),
      data: result.rows,
      metadata: {
        count: result.rows.length,
        timestamp: new Date().toISOString()
      }  
    });
    
  } catch (error) {
    console.error('EPS trend fetch error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch EPS trend',
      message: error.message
    });
  }
});

// Get growth estimates for a ticker
router.get('/:ticker/growth-estimates', async (req, res) => {
  try {
    const { ticker } = req.params;
    
    const growthQuery = `
      SELECT 
        symbol,
        period,
        stock_trend,
        index_trend,
        fetched_at
      FROM growth_estimates
      WHERE UPPER(symbol) = UPPER($1)
      ORDER BY 
        CASE 
          WHEN period = '0q' THEN 1 
          WHEN period = '+1q' THEN 2
          WHEN period = '0y' THEN 3
          WHEN period = '+1y' THEN 4
          WHEN period = '+5y' THEN 5
          ELSE 6
        END
    `;
    
    const result = await query(growthQuery, [ticker]);
    
    res.json({
      success: true,
      ticker: ticker.toUpperCase(),
      data: result.rows,
      metadata: {
        count: result.rows.length,
        timestamp: new Date().toISOString()
      }
    });
    
  } catch (error) {
    console.error('Growth estimates fetch error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch growth estimates',
      message: error.message
    });
  }
});

// Get analyst recommendations for a ticker
router.get('/:ticker/recommendations', async (req, res) => {
  try {
    const { ticker } = req.params;
    
    const recommendationsQuery = `
      SELECT 
        symbol,
        period,
        strong_buy,
        buy,
        hold,
        sell,
        strong_sell,
        collected_date,
        created_at
      FROM analyst_recommendations
      WHERE UPPER(symbol) = UPPER($1)
      ORDER BY collected_date DESC, period
      LIMIT 10
    `;
    
    const result = await query(recommendationsQuery, [ticker]);
    
    res.json({
      success: true,
      ticker: ticker.toUpperCase(),
      data: result.rows,
      metadata: {
        count: result.rows.length,
        timestamp: new Date().toISOString()
      }
    });
    
  } catch (error) {
    console.error('Analyst recommendations fetch error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch analyst recommendations',
      message: error.message
    });
  }
});

// Get comprehensive analyst overview for a ticker
router.get('/:ticker/overview', async (req, res) => {
  try {
    const { ticker } = req.params;
    
    // Get all analyst data in parallel
    const [
      earningsEstimates,
      revenueEstimates,
      earningsHistory,
      epsRevisions,
      epsTrend,
      growthEstimates,
      recommendations
    ] = await Promise.all([
      query(`SELECT * FROM earnings_estimates WHERE UPPER(symbol) = UPPER($1) ORDER BY fetched_at DESC`, [ticker]),
      query(`SELECT * FROM revenue_estimates WHERE UPPER(symbol) = UPPER($1) ORDER BY fetched_at DESC`, [ticker]),
      query(`SELECT * FROM earnings_history WHERE UPPER(symbol) = UPPER($1) ORDER BY quarter DESC LIMIT 20`, [ticker]),
      query(`SELECT * FROM eps_revisions WHERE UPPER(symbol) = UPPER($1) ORDER BY fetched_at DESC`, [ticker]),
      query(`SELECT * FROM eps_trend WHERE UPPER(symbol) = UPPER($1) ORDER BY fetched_at DESC`, [ticker]),
      query(`SELECT * FROM growth_estimates WHERE UPPER(symbol) = UPPER($1) ORDER BY fetched_at DESC`, [ticker]),
      query(`SELECT * FROM analyst_recommendations WHERE UPPER(symbol) = UPPER($1) ORDER BY collected_date DESC LIMIT 10`, [ticker])
    ]);
    
    res.json({
      success: true,
      ticker: ticker.toUpperCase(),
      data: {
        earnings_estimates: earningsEstimates.rows,
        revenue_estimates: revenueEstimates.rows,
        earnings_history: earningsHistory.rows,
        eps_revisions: epsRevisions.rows,
        eps_trend: epsTrend.rows,
        growth_estimates: growthEstimates.rows,
        recommendations: recommendations.rows
      },
      metadata: {
        timestamp: new Date().toISOString()
      }
    });
    
  } catch (error) {
    console.error('Analyst overview fetch error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch analyst overview',
      message: error.message
    });
  }
});

// Get recent analyst actions (upgrades/downgrades) for the most recent day
router.get('/recent-actions', async (req, res) => {
  try {
    const limit = parseInt(req.query.limit) || 10;
    
    // Get the most recent date with analyst actions
    const recentDateQuery = `
      SELECT DISTINCT date 
      FROM analyst_upgrade_downgrade 
      ORDER BY date DESC 
      LIMIT 1
    `;
    
    const recentDateResult = await query(recentDateQuery);
    
    if (!recentDateResult.rows || recentDateResult.rows.length === 0) {
      return res.json({
        data: [],
        summary: {
          date: null,
          total_actions: 0,
          upgrades: 0,
          downgrades: 0
        },
        message: 'No analyst actions found'
      });
    }
    
    const mostRecentDate = recentDateResult.rows[0].date;
    
    // Get all actions for the most recent date
    const recentActionsQuery = `
      SELECT 
        aud.symbol,
        s.short_name AS company_name,
        aud.from_grade,
        aud.to_grade,
        aud.action,
        aud.firm,
        aud.date,
        aud.details,
        CASE 
          WHEN LOWER(aud.action) LIKE '%up%' OR LOWER(aud.action) LIKE '%buy%' OR LOWER(aud.action) LIKE '%positive%' THEN 'upgrade'
          WHEN LOWER(aud.action) LIKE '%down%' OR LOWER(aud.action) LIKE '%sell%' OR LOWER(aud.action) LIKE '%negative%' THEN 'downgrade'
          ELSE 'neutral'
        END as action_type
      FROM analyst_upgrade_downgrade aud
      LEFT JOIN symbols s ON aud.symbol = s.symbol
      WHERE aud.date = $1
      ORDER BY aud.date DESC, aud.symbol ASC
      LIMIT $2
    `;
    
    const actionsResult = await query(recentActionsQuery, [mostRecentDate, limit]);
    
    // Count action types
    const actions = actionsResult.rows || [];
    const upgrades = actions.filter(action => action.action_type === 'upgrade');
    const downgrades = actions.filter(action => action.action_type === 'downgrade');
    const neutrals = actions.filter(action => action.action_type === 'neutral');
    
    res.json({
      data: actions,
      summary: {
        date: mostRecentDate,
        total_actions: actions.length,
        upgrades: upgrades.length,
        downgrades: downgrades.length,
        neutrals: neutrals.length
      },
      metadata: {
        timestamp: new Date().toISOString()
      }
    });
    
  } catch (error) {
    console.error('Error fetching recent analyst actions:', error);
    res.status(500).json({ 
      error: 'Failed to fetch recent analyst actions',
      message: error.message 
    });
  }
});

module.exports = router;
