const express = require('express');
const router = express.Router();
const { authenticateToken } = require('../middleware/auth');
const { query } = require('../utils/database');

// Apply authentication to all routes
router.use(authenticateToken);

// Try to initialize economic modeling engine with fallback
let economicEngine = null;
try {
  const EconomicModelingEngine = require('../utils/economicModelingEngine');
  economicEngine = new EconomicModelingEngine();
} catch (error) {
  console.log('EconomicModelingEngine not available, using fallback methods:', error.message);
}

// Get economic indicators
router.get('/indicators', async (req, res) => {
  try {
    const { category, period = '1Y', limit = 100 } = req.query;
    
    let whereClause = 'WHERE 1=1';
    const params = [];
    let paramIndex = 1;
    
    if (category) {
      whereClause += ` AND category = $${paramIndex}`;
      params.push(category);
      paramIndex++;
    }
    
    // Parse period
    const periodMap = {
      '1M': '1 month',
      '3M': '3 months',
      '6M': '6 months',
      '1Y': '1 year',
      '2Y': '2 years',
      '5Y': '5 years'
    };
    
    const intervalClause = periodMap[period] || '1 year';
    whereClause += ` AND date >= NOW() - INTERVAL '${intervalClause}'`;
    
    const result = await query(`
      SELECT 
        indicator_id,
        indicator_name,
        category,
        value,
        date,
        units,
        frequency,
        last_updated
      FROM economic_indicators
      ${whereClause}
      ORDER BY date DESC, indicator_name
      LIMIT $${paramIndex}
    `, [...params, parseInt(limit)]);
    
    // Group by indicator for better structure
    const indicators = {};
    result.rows.forEach(row => {
      if (!indicators[row.indicator_id]) {
        indicators[row.indicator_id] = {
          id: row.indicator_id,
          name: row.indicator_name,
          category: row.category,
          units: row.units,
          frequency: row.frequency,
          data: []
        };
      }
      indicators[row.indicator_id].data.push({
        date: row.date,
        value: parseFloat(row.value),
        last_updated: row.last_updated
      });
    });
    
    res.json({
      success: true,
      data: {
        indicators: Object.values(indicators),
        period,
        count: Object.keys(indicators).length
      }
    });
  } catch (error) {
    console.error('Error fetching economic indicators:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch economic indicators',
      message: error.message
    });
  }
});

// Get economic calendar
router.get('/calendar', async (req, res) => {
  try {
    const { from_date, to_date, importance, country = 'US' } = req.query;
    
    let whereClause = 'WHERE country = $1';
    const params = [country];
    let paramIndex = 2;
    
    if (from_date) {
      whereClause += ` AND event_date >= $${paramIndex}`;
      params.push(from_date);
      paramIndex++;
    }
    
    if (to_date) {
      whereClause += ` AND event_date <= $${paramIndex}`;
      params.push(to_date);
      paramIndex++;
    }
    
    if (importance) {
      whereClause += ` AND importance = $${paramIndex}`;
      params.push(importance);
      paramIndex++;
    }
    
    const result = await query(`
      SELECT 
        event_id,
        event_name,
        event_date,
        event_time,
        country,
        importance,
        forecast_value,
        previous_value,
        actual_value,
        currency,
        category,
        source,
        description,
        impact_score
      FROM economic_calendar
      ${whereClause}
      ORDER BY event_date ASC, event_time ASC
    `, params);
    
    res.json({
      success: true,
      data: {
        events: result.rows,
        count: result.rows.length,
        filters: {
          from_date,
          to_date,
          importance,
          country
        }
      }
    });
  } catch (error) {
    console.error('Error fetching economic calendar:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch economic calendar',
      message: error.message
    });
  }
});

// Get economic models and forecasts
router.get('/models', async (req, res) => {
  try {
    const { model_type, horizon = '12M' } = req.query;
    
    if (economicEngine) {
      const models = await economicEngine.getEconomicModels(model_type, horizon);
      res.json({
        success: true,
        data: models
      });
    } else {
      // Fallback mock data
      const mockModels = [
        {
          id: 'arima_gdp',
          name: 'ARIMA GDP Model',
          type: 'arima',
          target: 'GDP Growth',
          accuracy: 0.85,
          horizon: horizon,
          last_updated: new Date().toISOString(),
          parameters: { p: 2, d: 1, q: 2 }
        },
        {
          id: 'var_inflation',
          name: 'VAR Inflation Model',
          type: 'var',
          target: 'Core CPI',
          accuracy: 0.78,
          horizon: horizon,
          last_updated: new Date().toISOString(),
          parameters: { lags: 4, variables: ['cpi', 'unemployment', 'fed_rate'] }
        }
      ];

      res.json({
        success: true,
        data: mockModels,
        note: 'Mock economic models - modeling engine not available'
      });
    }
  } catch (error) {
    console.error('Error fetching economic models:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch economic models',
      message: error.message
    });
  }
});

// Run economic scenario analysis
router.post('/scenario-analysis', async (req, res) => {
  try {
    const { 
      base_scenario,
      shock_scenarios = [],
      indicators = [],
      time_horizon = 12,
      confidence_level = 0.95 
    } = req.body;
    
    if (!base_scenario || !indicators || indicators.length === 0) {
      return res.status(400).json({
        success: false,
        error: 'Base scenario and indicators are required'
      });
    }
    
    const analysis = await economicEngine.runScenarioAnalysis({
      base_scenario,
      shock_scenarios,
      indicators,
      time_horizon,
      confidence_level
    });
    
    res.json({
      success: true,
      data: analysis
    });
  } catch (error) {
    console.error('Error running scenario analysis:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to run scenario analysis',
      message: error.message
    });
  }
});

// Get economic correlations
router.get('/correlations', async (req, res) => {
  try {
    const { indicators, period = '2Y', method = 'pearson' } = req.query;
    
    if (economicEngine && indicators) {
      const indicatorList = indicators.split(',');
      const correlations = await economicEngine.calculateCorrelations(indicatorList, period, method);
      
      res.json({
        success: true,
        data: {
          correlations,
          indicators: indicatorList,
          period,
          method
        }
      });
    } else {
      // Fallback mock correlations
      const mockCorrelations = {
        matrix: {
          'GDP': { 'GDP': 1.0, 'CPI': 0.23, 'UNEMPLOYMENT': -0.67, 'FED_RATE': 0.45 },
          'CPI': { 'GDP': 0.23, 'CPI': 1.0, 'UNEMPLOYMENT': -0.12, 'FED_RATE': 0.78 },
          'UNEMPLOYMENT': { 'GDP': -0.67, 'CPI': -0.12, 'UNEMPLOYMENT': 1.0, 'FED_RATE': -0.34 },
          'FED_RATE': { 'GDP': 0.45, 'CPI': 0.78, 'UNEMPLOYMENT': -0.34, 'FED_RATE': 1.0 }
        },
        period: period,
        method: method,
        last_updated: new Date().toISOString()
      };

      res.json({
        success: true,
        data: mockCorrelations,
        note: 'Mock correlations - modeling engine not available'
      });
    }
  } catch (error) {
    console.error('Error calculating correlations:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to calculate correlations',
      message: error.message
    });
  }
});

// Get economic forecasts
router.get('/forecasts', async (req, res) => {
  try {
    const { indicator_id, horizon = '12M', model_type = 'arima' } = req.query;
    
    if (!indicator_id) {
      return res.status(400).json({
        success: false,
        error: 'Indicator ID is required'
      });
    }
    
    const forecast = await economicEngine.generateForecast(indicator_id, horizon, model_type);
    
    res.json({
      success: true,
      data: forecast
    });
  } catch (error) {
    console.error('Error generating forecast:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to generate forecast',
      message: error.message
    });
  }
});

// Get economic impact analysis
router.post('/impact-analysis', async (req, res) => {
  try {
    const { 
      economic_event,
      affected_sectors = [],
      time_horizon = 90,
      analysis_type = 'comprehensive'
    } = req.body;
    
    if (!economic_event) {
      return res.status(400).json({
        success: false,
        error: 'Economic event is required'
      });
    }
    
    const analysis = await economicEngine.analyzeEconomicImpact({
      economic_event,
      affected_sectors,
      time_horizon,
      analysis_type
    });
    
    res.json({
      success: true,
      data: analysis
    });
  } catch (error) {
    console.error('Error analyzing economic impact:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to analyze economic impact',
      message: error.message
    });
  }
});

// Get yield curve analysis
router.get('/yield-curve', async (req, res) => {
  try {
    const { date, analysis_type = 'current' } = req.query;
    
    const yieldCurve = await economicEngine.getYieldCurveAnalysis(date, analysis_type);
    
    res.json({
      success: true,
      data: yieldCurve
    });
  } catch (error) {
    console.error('Error fetching yield curve:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch yield curve analysis',
      message: error.message
    });
  }
});

// Get inflation analysis
router.get('/inflation', async (req, res) => {
  try {
    const { period = '5Y', components = true } = req.query;
    
    const inflationAnalysis = await economicEngine.getInflationAnalysis(period, components);
    
    res.json({
      success: true,
      data: inflationAnalysis
    });
  } catch (error) {
    console.error('Error fetching inflation analysis:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch inflation analysis',
      message: error.message
    });
  }
});

// Get employment analysis
router.get('/employment', async (req, res) => {
  try {
    const { period = '2Y', detailed = false } = req.query;
    
    const employmentAnalysis = await economicEngine.getEmploymentAnalysis(period, detailed);
    
    res.json({
      success: true,
      data: employmentAnalysis
    });
  } catch (error) {
    console.error('Error fetching employment analysis:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch employment analysis',
      message: error.message
    });
  }
});

// Get GDP analysis
router.get('/gdp', async (req, res) => {
  try {
    const { period = '5Y', components = true } = req.query;
    
    const gdpAnalysis = await economicEngine.getGDPAnalysis(period, components);
    
    res.json({
      success: true,
      data: gdpAnalysis
    });
  } catch (error) {
    console.error('Error fetching GDP analysis:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch GDP analysis',
      message: error.message
    });
  }
});

// Get available economic indicators list
router.get('/indicators/list', async (req, res) => {
  try {
    const result = await query(`
      SELECT DISTINCT
        indicator_id,
        indicator_name,
        category,
        units,
        frequency,
        description,
        source,
        last_updated,
        COUNT(*) as data_points
      FROM economic_indicators
      GROUP BY indicator_id, indicator_name, category, units, frequency, description, source, last_updated
      ORDER BY category, indicator_name
    `);
    
    const indicators = result.rows.map(row => ({
      id: row.indicator_id,
      name: row.indicator_name,
      category: row.category,
      units: row.units,
      frequency: row.frequency,
      description: row.description,
      source: row.source,
      last_updated: row.last_updated,
      data_points: parseInt(row.data_points)
    }));
    
    // Group by category
    const categorized = {};
    indicators.forEach(indicator => {
      if (!categorized[indicator.category]) {
        categorized[indicator.category] = [];
      }
      categorized[indicator.category].push(indicator);
    });
    
    res.json({
      success: true,
      data: {
        indicators,
        categorized,
        total_count: indicators.length
      }
    });
  } catch (error) {
    console.error('Error fetching indicators list:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch indicators list',
      message: error.message
    });
  }
});

module.exports = router;