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
        symbol,
        company,
        from_grade,
        to_grade,
        action,
        firm,
        date
      FROM analyst_upgrade_downgrade 
      ORDER BY date DESC
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

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    res.json({
      data: upgradesResult.rows,
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
    res.status(500).json({ error: 'Failed to fetch analyst upgrades' });
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
      FROM earnings_estimate
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
        reported_date
      FROM revenue_estimate
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

module.exports = router;
