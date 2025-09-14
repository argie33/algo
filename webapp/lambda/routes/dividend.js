const express = require("express");
const { query } = require("../utils/database");
const router = express.Router();

// Root endpoint - API info
router.get("/", async (req, res) => {
  res.json({
    message: "Dividend API - Ready",
    status: "operational", 
    endpoints: [
      "GET /history/:symbol - Get dividend history for a symbol",
      "GET /upcoming - Get upcoming dividend payments",
      "GET /yield/:symbol - Get dividend yield information"
    ],
    timestamp: new Date().toISOString()
  });
});

// Dividend history endpoint
router.get("/history/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    // Extract query params for future use when implemented
    const { limit: _limit = 20, years: _years = 5 } = req.query;
    console.log(`💰 Dividend history requested for ${symbol.toUpperCase()}`);

    // Query dividend history from database
    const dividendQuery = `
      SELECT 
        symbol,
        ex_dividend_date,
        record_date,
        payment_date,
        dividend_amount,
        dividend_type,
        frequency,
        currency
      FROM dividend_history 
      WHERE UPPER(symbol) = UPPER($1)
      ORDER BY payment_date DESC
      LIMIT $2
    `;

    const result = await query(dividendQuery, [symbol.toUpperCase(), parseInt(_limit)]);
    
    if (!result.rows || result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Dividend history not found",
        message: `No dividend history found for ${symbol}. Please ensure the dividend_history table is populated.`,
        symbol: symbol.toUpperCase(),
        timestamp: new Date().toISOString()
      });
    }

    const dividendHistory = result.rows;

    // Calculate summary statistics
    const totalDividends = dividendHistory.reduce((sum, div) => sum + div.dividend_amount, 0);
    const avgDividend = dividendHistory.length > 0 ? totalDividends / dividendHistory.length : 0;
    const currentYearDividends = dividendHistory.filter(
      div => new Date(div.payment_date).getFullYear() === new Date().getFullYear()
    );
    const annualizedDividend = currentYearDividends.reduce((sum, div) => sum + div.dividend_amount, 0);

    res.json({
      success: true,
      data: {
        symbol: symbol.toUpperCase(),
        company_name: dividendHistory[0]?.company_name || symbol.toUpperCase(),
        dividend_history: dividendHistory,
        summary: {
          total_dividends_paid: Math.round(totalDividends * 100) / 100,
          average_dividend: Math.round(avgDividend * 100) / 100,
          total_payments: dividendHistory.length,
          years_of_data: parseInt(_years),
          current_year_total: Math.round(annualizedDividend * 100) / 100,
          payment_frequency: dividendHistory.length > 0 ? dividendHistory[0].frequency : 'Quarterly',
          dividend_growth_rate: dividendHistory.length > 8 ? 
            Math.round(((dividendHistory[0].dividend_amount - dividendHistory[7].dividend_amount) / dividendHistory[7].dividend_amount) * 100 * 100) / 100 : 0
        },
        filters: {
          symbol: symbol.toUpperCase(),
          years: parseInt(_years),
          limit: parseInt(_limit)
        }
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Dividend history error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch dividend history",
      details: error.message,
      symbol: req.params.symbol?.toUpperCase() || null,
      timestamp: new Date().toISOString()
    });
  }
});

// Dividend calendar endpoint - upcoming dividend dates and events
router.get("/calendar", async (req, res) => {
  try {
    const { 
      days = 30,
      event_type = "all", // all, ex_dividend, payment, announcement
      symbol,
      min_yield,
      max_yield,
      limit = 50,
      sort_by = "date" // date, yield, amount, symbol
    } = req.query;

    console.log(`📅 Dividend calendar requested for next ${days} days, type: ${event_type}, symbol: ${symbol || 'all'}`);

    // Try to get dividend calendar from database, but fall back to generated data on any error
    let dividendEvents = [];
    let dataSource = 'generated';
    
    try {
      console.log('🔍 Attempting to query dividend_calendar database...');
      const { query } = require('../utils/database');
      
      // Try to query with database - use generated query if database fails
      let calendarQuery = `
        SELECT 
          symbol, 
          company_name,
          ex_dividend_date,
          payment_date,
          record_date,
          dividend_amount,
          dividend_yield,
          frequency,
          dividend_type,
          announcement_date
        FROM dividend_calendar 
        WHERE ex_dividend_date IS NOT NULL 
          AND ex_dividend_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '${isNaN(parseInt(days)) ? 30 : parseInt(days)} days'`;

      let paramCount = 0;
      const queryParams = [];

      if (symbol) {
        queryParams.push(symbol.toUpperCase());
        calendarQuery += ` AND symbol = $${++paramCount}`;
      }

      if (min_yield) {
        queryParams.push(parseFloat(min_yield));
        calendarQuery += ` AND dividend_yield >= $${++paramCount}`;
      }

      if (max_yield) {
        queryParams.push(parseFloat(max_yield));
        calendarQuery += ` AND dividend_yield <= $${++paramCount}`;
      }

      // Add ordering
      const sortOptions = {
        "date": "ex_dividend_date ASC",
        "yield": "dividend_yield DESC",
        "amount": "dividend_amount DESC", 
        "symbol": "symbol ASC"
      };
      calendarQuery += ` ORDER BY ${sortOptions[sort_by] || sortOptions["date"]}`;

      queryParams.push(parseInt(limit));
      calendarQuery += ` LIMIT $${++paramCount}`;

      console.log('📊 Executing dividend calendar query...');
      const result = await query(calendarQuery, queryParams);
      
      if (result.rows && result.rows.length > 0) {
        console.log(`✅ Found ${result.rows.length} dividend events from database`);
        dividendEvents = result.rows.map(row => ({
          id: `div_db_${row.symbol}_${row.ex_dividend_date}`,
          symbol: row.symbol,
          company_name: row.company_name,
          event_type: 'ex_dividend',
          event_title: `${row.company_name} Ex-Dividend Date`,
          event_date: row.ex_dividend_date,
          ex_dividend_date: row.ex_dividend_date,
          record_date: row.record_date,
          payment_date: row.payment_date,
          dividend_amount: parseFloat(row.dividend_amount) || 0,
          dividend_yield: parseFloat(row.dividend_yield) || 0,
          frequency: row.frequency || 'Quarterly',
          dividend_type: row.dividend_type || 'Regular Cash',
          currency: 'USD',
          market_impact: 'Medium',
          days_until_event: Math.ceil((new Date(row.ex_dividend_date) - new Date()) / (1000 * 60 * 60 * 24))
        }));
        dataSource = 'database';
      } else {
        console.log('ℹ️ No dividend events found in database, generating sample data...');
        throw new Error('No data in database, using generated data');
      }

    } catch (dbError) {
      console.log('⚠️ Database query failed, using generated data:', dbError.message);
      dataSource = 'generated';
    }

    // If database failed, return error instead of generating data
    if (dataSource === 'generated') {
      return res.status(503).json({
        success: false,
        error: "Dividend calendar data unavailable",
        message: "Database query failed and no sample data will be provided. Please ensure the dividend_calendar table is populated.",
        details: "The dividend calendar requires real dividend data to function properly.",
        timestamp: new Date().toISOString()
      });
    }

    // Calculate summary statistics
    const eventTypes = dividendEvents.reduce((acc, event) => {
      acc[event.event_type] = (acc[event.event_type] || 0) + 1;
      return acc;
    }, {});
    
    const totalDividendAmount = dividendEvents
      .filter(event => event.event_type === 'payment')
      .reduce((sum, event) => sum + event.dividend_amount, 0);
    
    const avgYield = dividendEvents.length > 0 ?
      dividendEvents.reduce((sum, event) => sum + event.dividend_yield, 0) / dividendEvents.length : 0;

    // Calculate summary statistics
    const summary = {
      total_events: dividendEvents.length,
      by_event_type: {},
      by_frequency: {},
      by_sector: {},
      date_range: {
        from: new Date().toISOString().split('T')[0],
        to: new Date(Date.now() + parseInt(days) * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
        days_covered: parseInt(days)
      },
      dividend_stats: {
        avg_yield: dividendEvents.length > 0 ? parseFloat((dividendEvents.reduce((sum, e) => sum + e.dividend_yield, 0) / dividendEvents.length).toFixed(2)) : 0,
        avg_amount: dividendEvents.length > 0 ? parseFloat((dividendEvents.reduce((sum, e) => sum + e.dividend_amount, 0) / dividendEvents.length).toFixed(3)) : 0,
        highest_yield: dividendEvents.length > 0 ? Math.max(...dividendEvents.map(e => e.dividend_yield)) : 0,
        lowest_yield: dividendEvents.length > 0 ? Math.min(...dividendEvents.map(e => e.dividend_yield)) : 0,
        total_dividend_value: dividendEvents.reduce((sum, e) => sum + e.dividend_amount, 0).toFixed(2)
      },
      this_week: dividendEvents.filter(e => new Date(e.ex_dividend_date) <= new Date(Date.now() + 7 * 24 * 60 * 60 * 1000)).length,
      next_week: dividendEvents.filter(e => {
        const eventDate = new Date(e.ex_dividend_date);
        const nextWeekStart = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000);
        const nextWeekEnd = new Date(Date.now() + 14 * 24 * 60 * 60 * 1000);
        return eventDate > nextWeekStart && eventDate <= nextWeekEnd;
      }).length
    };

    // Calculate breakdowns
    const eventTypesUnique = [...new Set(dividendEvents.map(e => e.dividend_type || 'Regular'))];
    const frequenciesUnique = [...new Set(dividendEvents.map(e => e.frequency))];
    const sectorsUnique = [...new Set(dividendEvents.map(e => e.sector))];

    eventTypesUnique.forEach(type => {
      summary.by_event_type[type] = dividendEvents.filter(e => (e.dividend_type || 'Regular') === type).length;
    });

    frequenciesUnique.forEach(freq => {
      summary.by_frequency[freq] = dividendEvents.filter(e => e.frequency === freq).length;
    });

    sectorsUnique.forEach(sector => {
      summary.by_sector[sector] = dividendEvents.filter(e => e.sector === sector).length;
    });

    res.json({
      success: true,
      data: {
        dividend_calendar: dividendEvents,
        summary: summary,
        filters: {
          days: parseInt(days),
          event_type: event_type,
          symbol: symbol || null,
          yield_range: min_yield || max_yield ? {
            min: min_yield ? parseFloat(min_yield) : null,
            max: max_yield ? parseFloat(max_yield) : null
          } : null,
          limit: parseInt(limit),
          sort_by: sort_by
        },
        available_filters: {
          event_types: ["all", "ex_dividend", "payment", "announcement"],
          frequencies: frequenciesUnique,
          sort_options: ["date", "yield", "amount", "symbol"]
        }
      },
      metadata: {
        total_returned: dividendEvents.length,
        data_source: dataSource,
        generated_at: new Date().toISOString()
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Dividend calendar error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch dividend calendar",
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Helper functions removed - not needed for not implemented endpoints

module.exports = router;