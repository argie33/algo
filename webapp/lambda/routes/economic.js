const express = require("express");

const { query } = require("../utils/database");

const router = express.Router();

// Get economic data
router.get("/", async (req, res) => {
  try {
    const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 25;
    const offset = (page - 1) * limit;
    const series = req.query.series;

    let whereClause = "";
    const queryParams = [];
    let paramCount = 0;

    if (series) {
      paramCount++;
      whereClause = `WHERE series_id = $${paramCount}`;
      queryParams.push(series);
    }

    const economicQuery = `
      SELECT 
        series_id,
        date,
        value
      FROM economic_data
      ${whereClause}
      ORDER BY series_id, date DESC
      LIMIT $${paramCount + 1} OFFSET $${paramCount + 2}
    `;

    const countQuery = `
      SELECT COUNT(*) as total FROM economic_data ${whereClause}
    `;

    queryParams.push(limit, offset);

    const [economicResult, countResult] = await Promise.all([
      query(economicQuery, queryParams),
      query(countQuery, queryParams.slice(0, paramCount)),
    ]);

    // Add null safety check
    if (!countResult || !countResult.rows || countResult.rows.length === 0) {
      console.warn("Economic data count query returned null result, database may be unavailable");
      return res.status(503).json({
        success: false,
        error: "Database temporarily unavailable",
        message: "Economic data temporarily unavailable - database connection issue",
        data: [],
        pagination: {
          page: page,
          limit: limit,
          total: 0,
          totalPages: 0,
          hasNext: false,
          hasPrev: false
        }
      });
    }
    
    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    if (
      !economicResult ||
      !Array.isArray(economicResult.rows) ||
      economicResult.rows.length === 0
    ) {
      return res.status(404).json({
        success: false,
        error: "No data found for this query"
      });
    }

    res.json({
      success: true,
      data: economicResult.rows,
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1,
      },
    });
  } catch (error) {
    console.error("Error fetching economic data:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch economic data",
      message: error.message,
      details: "Economic data is not available. Please ensure the economic_data table exists and is populated."
    });
  }
});

// Get economic data (for DataValidation page - matches frontend expectation)
router.get("/data", async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 50, 100);
    console.log(`Economic data endpoint called with limit: ${limit}`);

    const economicQuery = `
      SELECT series_id, date, value
      FROM economic_data 
      ORDER BY date DESC, series_id ASC
      LIMIT $1
    `;

    const result = await query(economicQuery, [limit]);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "No data found for this query"
      });
    }

    res.json({
      data: result.rows,
      count: result.rows.length,
      limit: limit,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching economic data:", error);
    res.status(500).json({
      success: false,
      error: "Database error",
      message: error.message
    });
  }
});

// Economic indicators endpoint
router.get("/indicators", async (req, res) => {
  try {
    const category = req.query.category;
    console.log(`📊 Economic indicators requested, category: ${category || 'all'}`);

    let whereClause = "";
    const queryParams = [];
    
    if (category) {
      whereClause = "WHERE category = $1";
      queryParams.push(category);
    }

    const indicatorsResult = await query(`
      SELECT DISTINCT 
        series_id,
        'Economic Indicator' as name,
        'economic' as category,
        'Monthly' as frequency,
        'Bureau of Labor Statistics' as source,
        MAX(date) as last_updated
      FROM economic_data 
      ${whereClause}
      GROUP BY series_id
      ORDER BY series_id
      LIMIT 50
    `, queryParams);

    if (!indicatorsResult.rows || indicatorsResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "No economic indicators found",
        message: "No economic indicators available. Please check if economic data tables exist.",
        details: {
          category: category || "all",
          suggestion: "Ensure economic data has been loaded into the database"
        }
      });
    }

    res.json({
      success: true,
      data: {
        indicators: indicatorsResult.rows,
        count: indicatorsResult.rows.length,
        category: category || "all"
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Economic indicators error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch economic indicators",
      message: error.message,
      details: "Economic indicators data is not available. Please ensure the economic_data table exists and is populated."
    });
  }
});

// Economic calendar endpoint
router.get("/calendar", async (req, res) => {
  try {
    const { start_date, end_date, importance, country } = req.query;
    console.log(`📅 Economic calendar requested - start: ${start_date}, end: ${end_date}, importance: ${importance}, country: ${country}`);

    // Since we don't have a dedicated calendar table, simulate with economic data releases
    const calendarResult = await query(`
      SELECT 
        series_id as event_name,
        date as event_date,
        value as forecast_value,
        'Medium' as importance,
        'US' as country,
        'Data Release' as event_type
      FROM economic_data 
      WHERE date >= COALESCE($1::date, CURRENT_DATE - INTERVAL '30 days')
        AND date <= COALESCE($2::date, CURRENT_DATE + INTERVAL '30 days')
      ORDER BY date DESC
      LIMIT 100
    `, [start_date, end_date]);

    res.json({
      success: true,
      data: {
        events: calendarResult.rows || [],
        count: calendarResult.rows ? calendarResult.rows.length : 0,
        filters: {
          start_date: start_date || 'auto',
          end_date: end_date || 'auto',
          importance: importance || 'all',
          country: country || 'all'
        }
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Economic calendar error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch economic calendar data",
      message: error.message,
      details: "Economic calendar data is not available. Please ensure the economic_data table exists and is populated."
    });
  }
});

// Economic series endpoint
router.get("/series/:seriesId", async (req, res) => {
  try {
    const { seriesId } = req.params;
    const { timeframe, frequency, limit = 100 } = req.query;
    console.log(`📈 Economic series requested - series: ${seriesId}, timeframe: ${timeframe}`);

    const seriesResult = await query(`
      SELECT 
        series_id,
        date,
        value,
        LAG(value) OVER (ORDER BY date) as previous_value
      FROM economic_data 
      WHERE series_id = $1
      ORDER BY date DESC
      LIMIT $2
    `, [seriesId.toUpperCase(), parseInt(limit)]);

    if (!seriesResult.rows || seriesResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Economic series not found",
        message: `No data found for economic series: ${seriesId}. Please verify the series ID is correct.`,
        details: {
          requested_series: seriesId,
          available_series_sample: ["GDP", "CPI", "UNEMPLOYMENT", "FEDERAL_FUNDS"],
          suggestion: "Use /api/economic/indicators to see available economic series"
        }
      });
    }

    // Calculate basic statistics
    const values = seriesResult.rows.map(row => parseFloat(row.value)).filter(v => !isNaN(v));
    const latestValue = values[0];
    const previousValue = values[1];
    const changePercent = previousValue ? ((latestValue - previousValue) / previousValue * 100) : 0;

    res.json({
      success: true,
      data: {
        series_info: {
          series_id: seriesId.toUpperCase(),
          name: `${seriesId} Economic Series`,
          frequency: frequency || "auto-detected",
          timeframe: timeframe || "all-available"
        },
        data_points: seriesResult.rows,
        statistics: {
          latest_value: latestValue,
          previous_value: previousValue,
          change_percent: changePercent.toFixed(2) + "%",
          data_points: seriesResult.rows.length,
          date_range: {
            latest: seriesResult.rows[0]?.date,
            earliest: seriesResult.rows[seriesResult.rows.length - 1]?.date
          }
        }
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error(`Economic series error for ${req.params.seriesId}:`, error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch economic series data",
      message: error.message
    });
  }
});

// Economic forecast endpoint
router.get("/forecast", async (req, res) => {
  try {
    const { series, horizon, confidence } = req.query;
    console.log(`🔮 Economic forecast requested - series: ${series}, horizon: ${horizon}`);

    if (!series) {
      return res.status(400).json({
        success: false,
        error: "Missing required parameter",
        message: "Series parameter is required for economic forecasts",
        details: {
          required_parameters: ["series"],
          optional_parameters: ["horizon", "confidence"],
          example: "/api/economic/forecast?series=GDP&horizon=1Q&confidence=0.95"
        }
      });
    }

    // Get recent historical data for the series
    const historicalResult = await query(`
      SELECT date, value
      FROM economic_data 
      WHERE series_id = $1
      ORDER BY date DESC
      LIMIT 12
    `, [series.toUpperCase()]);

    if (!historicalResult.rows || historicalResult.rows.length < 3) {
      return res.status(404).json({
        success: false,
        error: "Insufficient historical data",
        message: `Not enough historical data for series: ${series} to generate forecasts`,
        details: {
          data_points_found: historicalResult.rows ? historicalResult.rows.length : 0,
          minimum_required: 3,
          suggestion: "Ensure sufficient historical data exists for the requested series"
        }
      });
    }

    // Simple forecast calculation (moving average with trend)
    const values = historicalResult.rows.map(row => parseFloat(row.value));
    const recentAvg = values.slice(0, 3).reduce((a, b) => a + b, 0) / 3;
    const olderAvg = values.slice(3, 6).reduce((a, b) => a + b, 0) / Math.min(3, values.length - 3);
    const trendRate = olderAvg > 0 ? (recentAvg - olderAvg) / olderAvg : 0;
    
    const horizonPeriods = horizon === "1Q" ? 3 : horizon === "1Y" ? 12 : 1;
    const forecastValue = recentAvg * (1 + trendRate * horizonPeriods);
    const confidenceInterval = parseFloat(confidence || 0.95);
    const margin = Math.abs(forecastValue * 0.1); // 10% margin for uncertainty

    res.json({
      success: true,
      data: {
        series: series.toUpperCase(),
        forecast: {
          value: forecastValue.toFixed(2),
          horizon: horizon || "1 period",
          confidence_level: `${(confidenceInterval * 100).toFixed(0)}%`,
          confidence_interval: {
            lower_bound: (forecastValue - margin).toFixed(2),
            upper_bound: (forecastValue + margin).toFixed(2)
          }
        },
        methodology: {
          type: "Trend-adjusted Moving Average",
          historical_periods: values.length,
          trend_rate: `${(trendRate * 100).toFixed(2)}%`
        },
        disclaimer: "This is a simplified forecast. Professional economic forecasting requires sophisticated econometric models."
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Economic forecast error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to generate economic forecast",
      message: error.message
    });
  }
});

// Economic correlations endpoint
router.get("/correlations", async (req, res) => {
  try {
    const { series, timeframe } = req.query;
    console.log(`🔗 Economic correlations requested - series: ${series}, timeframe: ${timeframe}`);

    if (!series) {
      return res.status(400).json({
        success: false,
        error: "Missing required parameter",
        message: "Series parameter is required for correlation analysis"
      });
    }

    // Get data for the target series and other available series
    const timeframeDays = timeframe === "5Y" ? 1825 : timeframe === "1Y" ? 365 : 730;
    
    const correlationData = await query(`
      WITH target_series AS (
        SELECT date, value as target_value
        FROM economic_data 
        WHERE series_id = $1 
          AND date >= CURRENT_DATE - INTERVAL '${timeframeDays} days'
      ),
      other_series AS (
        SELECT series_id, date, value
        FROM economic_data 
        WHERE series_id != $1 
          AND date >= CURRENT_DATE - INTERVAL '${timeframeDays} days'
      )
      SELECT 
        o.series_id,
        COUNT(*) as data_points,
        CORR(t.target_value, o.value) as correlation
      FROM target_series t
      JOIN other_series o ON t.date = o.date
      GROUP BY o.series_id
      HAVING COUNT(*) >= 10
      ORDER BY ABS(CORR(t.target_value, o.value)) DESC
      LIMIT 20
    `, [series.toUpperCase()]);

    res.json({
      success: true,
      data: {
        target_series: series.toUpperCase(),
        timeframe: timeframe || "2Y",
        correlations: (correlationData.rows || []).map(row => ({
          series: row.series_id,
          correlation: parseFloat(row.correlation || 0).toFixed(3),
          strength: Math.abs(parseFloat(row.correlation || 0)) > 0.7 ? "Strong" : 
                   Math.abs(parseFloat(row.correlation || 0)) > 0.3 ? "Moderate" : "Weak",
          data_points: parseInt(row.data_points)
        })),
        analysis_period: {
          timeframe: timeframe || "2Y",
          minimum_data_points: 10
        }
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Economic correlations error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to calculate economic correlations",
      message: error.message
    });
  }
});

// Economic comparison endpoint
router.get("/compare", async (req, res) => {
  try {
    const { series, normalize, align_period } = req.query;
    console.log(`⚖️ Economic comparison requested - series: ${series}`);

    if (!series) {
      return res.status(400).json({
        success: false,
        error: "Missing required parameter",
        message: "Series parameter is required for comparison"
      });
    }

    const seriesList = series.split(',').map(s => s.trim().toUpperCase());
    
    if (seriesList.length < 2) {
      return res.status(400).json({
        success: false,
        error: "Insufficient series for comparison",
        message: "At least 2 series are required for comparison"
      });
    }

    const comparisonData = await query(`
      SELECT 
        series_id,
        date,
        value,
        COUNT(*) OVER (PARTITION BY series_id) as data_points
      FROM economic_data 
      WHERE series_id = ANY($1)
      ORDER BY series_id, date DESC
    `, [seriesList]);

    // Group data by series
    const seriesData = {};
    (comparisonData.rows || []).forEach(row => {
      if (!seriesData[row.series_id]) {
        seriesData[row.series_id] = [];
      }
      seriesData[row.series_id].push({
        date: row.date,
        value: parseFloat(row.value),
        data_points: parseInt(row.data_points)
      });
    });

    res.json({
      success: true,
      data: {
        comparison: {
          series_compared: seriesList,
          normalize: normalize === "true",
          align_period: align_period || "none"
        },
        series_data: seriesData,
        summary: {
          series_count: Object.keys(seriesData).length,
          total_data_points: Object.values(seriesData).reduce((sum, data) => sum + data.length, 0),
          missing_series: seriesList.filter(s => !seriesData[s])
        }
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Economic comparison error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to compare economic series",
      message: error.message
    });
  }
});

module.exports = router;