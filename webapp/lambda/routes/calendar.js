const express = require('express');
const { query } = require('../utils/database');

const router = express.Router();

// Debug endpoint to check calendar table status
router.get('/debug', async (req, res) => {
  try {
    console.log('Calendar debug endpoint called');
    
    // Check if table exists
    const tableExistsQuery = `
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'calendar_events'
      );
    `;
    
    const tableExists = await query(tableExistsQuery);
    console.log('Table exists check:', tableExists.rows[0]);
    
    if (tableExists.rows[0].exists) {
      // Count total records
      const countQuery = `SELECT COUNT(*) as total FROM calendar_events`;
      const countResult = await query(countQuery);
      console.log('Total calendar events:', countResult.rows[0]);
      
      // Get sample records
      const sampleQuery = `
        SELECT symbol, event_type, start_date, title, fetched_at
        FROM calendar_events 
        ORDER BY fetched_at DESC 
        LIMIT 5
      `;
      const sampleResult = await query(sampleQuery);
      console.log('Sample records:', sampleResult.rows);
      
      res.json({
        tableExists: true,
        totalRecords: parseInt(countResult.rows[0].total),
        sampleRecords: sampleResult.rows,
        timestamp: new Date().toISOString()
      });
    } else {
      res.json({
        tableExists: false,
        message: 'calendar_events table does not exist',
        timestamp: new Date().toISOString()
      });
    }
    
  } catch (error) {
    console.error('Error in calendar debug:', error);
    res.status(500).json({ 
      error: 'Debug check failed', 
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Simple test endpoint that returns raw data
router.get('/test', async (req, res) => {
  try {
    console.log('Calendar test endpoint called');
    
    const testQuery = `
      SELECT 
        symbol,
        event_type,
        start_date,
        end_date,
        title
      FROM calendar_events
      ORDER BY start_date ASC
      LIMIT 10
    `;
    
    const result = await query(testQuery);
    
    res.json({
      success: true,
      count: result.rows.length,
      data: result.rows,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error in calendar test:', error);
    res.status(500).json({ 
      error: 'Test failed', 
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get calendar events (earnings, dividends, splits, etc.)
router.get('/events', async (req, res) => {
  try {
    console.log('Calendar events endpoint called with params:', req.query);
    
    const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 25;
    const offset = (page - 1) * limit;
    const timeFilter = req.query.type || 'upcoming';

    let whereClause = 'WHERE 1=1';
    const params = [];    // Apply time filters (convert CURRENT_DATE to timestamp for proper comparison)
    switch (timeFilter) {
      case 'this_week':
        whereClause += ` AND start_date >= CURRENT_DATE::timestamp AND start_date < (CURRENT_DATE + INTERVAL '7 days')::timestamp`;
        break;
      case 'next_week':
        whereClause += ` AND start_date >= (CURRENT_DATE + INTERVAL '7 days')::timestamp AND start_date < (CURRENT_DATE + INTERVAL '14 days')::timestamp`;
        break;
      case 'this_month':
        whereClause += ` AND start_date >= CURRENT_DATE::timestamp AND start_date < (CURRENT_DATE + INTERVAL '30 days')::timestamp`;
        break;
      case 'upcoming':
      default:
        whereClause += ` AND start_date >= CURRENT_DATE::timestamp`;
        break;
    }

    console.log('Using whereClause:', whereClause);

    const eventsQuery = `
      SELECT 
        ce.symbol,
        ce.event_type,
        ce.start_date,
        ce.end_date,
        ce.title,
        cp.short_name as company_name
      FROM calendar_events ce
      LEFT JOIN company_profile cp ON ce.symbol = cp.ticker
      ${whereClause}
      ORDER BY ce.start_date ASC
      LIMIT $1 OFFSET $2
    `;

    const countQuery = `
      SELECT COUNT(*) as total
      FROM calendar_events ce
      ${whereClause}
    `;    console.log('Executing queries with limit:', limit, 'offset:', offset);

    const [eventsResult, countResult] = await Promise.all([
      query(eventsQuery, [limit, offset]),
      query(countQuery, [])
    ]);

    console.log('Query results - events:', eventsResult.rows.length, 'total:', countResult.rows[0].total);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    res.json({
      data: eventsResult.rows,
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1
      },
      summary: {
        upcoming_events: total,
        this_week: 0, // Would need separate query
        filter: timeFilter
      }
    });
  } catch (error) {
    console.error('Error fetching calendar events:', error);
    console.error('Error stack:', error.stack);
    res.status(500).json({ 
      error: 'Failed to fetch calendar events', 
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get earnings calendar summary
router.get('/summary', async (req, res) => {
  try {
    const summaryQuery = `
      SELECT 
        COUNT(CASE WHEN start_date >= CURRENT_DATE AND start_date < CURRENT_DATE + INTERVAL '7 days' THEN 1 END) as this_week,
        COUNT(CASE WHEN start_date >= CURRENT_DATE + INTERVAL '7 days' AND start_date < CURRENT_DATE + INTERVAL '14 days' THEN 1 END) as next_week,
        COUNT(CASE WHEN start_date >= CURRENT_DATE AND start_date < CURRENT_DATE + INTERVAL '30 days' THEN 1 END) as this_month,
        COUNT(CASE WHEN event_type = 'earnings' AND start_date >= CURRENT_DATE THEN 1 END) as upcoming_earnings,
        COUNT(CASE WHEN event_type = 'dividend' AND start_date >= CURRENT_DATE THEN 1 END) as upcoming_dividends
      FROM calendar_events
    `;

    const result = await query(summaryQuery);

    res.json({
      summary: result.rows[0],
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching calendar summary:', error);
    res.status(500).json({ error: 'Failed to fetch calendar summary' });
  }
});

// Get earnings estimates for all companies
router.get('/earnings-estimates', async (req, res) => {
  try {
    const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 25;
    const offset = (page - 1) * limit;

    const estimatesQuery = `
      SELECT 
        ee.symbol,
        ee.period,
        ee.avg_estimate,
        ee.low_estimate,
        ee.high_estimate,
        ee.number_of_analysts,
        ee.growth,
        cp.short_name as company_name
      FROM earnings_estimates ee
      LEFT JOIN company_profile cp ON ee.symbol = cp.ticker
      ORDER BY ee.avg_estimate DESC NULLS LAST
      LIMIT $1 OFFSET $2
    `;

    const countQuery = `
      SELECT COUNT(*) as total
      FROM earnings_estimates
    `;

    const [estimatesResult, countResult] = await Promise.all([
      query(estimatesQuery, [limit, offset]),
      query(countQuery)
    ]);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    res.json({
      data: estimatesResult.rows,
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1
      },
      summary: {
        recent_updates: 0 // Would need separate query for recent updates
      }
    });

  } catch (error) {
    console.error('Error fetching earnings estimates:', error);
    res.status(500).json({ error: 'Failed to fetch earnings estimates' });
  }
});

// Get earnings history for all companies
router.get('/earnings-history', async (req, res) => {
  try {
    const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 25;
    const offset = (page - 1) * limit;

    const historyQuery = `
      SELECT 
        eh.symbol,
        eh.quarter,
        eh.eps_actual,
        eh.eps_estimate,
        eh.eps_difference,
        eh.surprise_percent,
        cp.short_name as company_name
      FROM earnings_history eh
      LEFT JOIN company_profile cp ON eh.symbol = cp.ticker
      ORDER BY eh.quarter DESC
      LIMIT $1 OFFSET $2
    `;

    const countQuery = `
      SELECT COUNT(*) as total
      FROM earnings_history
    `;

    const summaryQuery = `
      SELECT 
        COUNT(CASE WHEN surprise_percent > 0 THEN 1 END) as positive_surprises,
        COUNT(CASE WHEN surprise_percent < 0 THEN 1 END) as negative_surprises,
        AVG(surprise_percent) as avg_surprise
      FROM earnings_history
      WHERE quarter >= CURRENT_DATE - INTERVAL '3 months'
    `;

    const [historyResult, countResult, summaryResult] = await Promise.all([
      query(historyQuery, [limit, offset]),
      query(countQuery),
      query(summaryQuery)
    ]);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    res.json({
      data: historyResult.rows,
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1
      },
      summary: summaryResult.rows[0]
    });

  } catch (error) {
    console.error('Error fetching earnings history:', error);
    res.status(500).json({ error: 'Failed to fetch earnings history' });
  }
});

module.exports = router;
