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
  try {\n    const { \n      economic_event,\n      affected_sectors = [],\n      time_horizon = 90,\n      analysis_type = 'comprehensive'\n    } = req.body;\n    \n    if (!economic_event) {\n      return res.status(400).json({\n        success: false,\n        error: 'Economic event is required'\n      });\n    }\n    \n    const analysis = await economicEngine.analyzeEconomicImpact({\n      economic_event,\n      affected_sectors,\n      time_horizon,\n      analysis_type\n    });\n    \n    res.json({\n      success: true,\n      data: analysis\n    });\n  } catch (error) {\n    console.error('Error analyzing economic impact:', error);\n    res.status(500).json({\n      success: false,\n      error: 'Failed to analyze economic impact',\n      message: error.message\n    });\n  }\n});\n\n// Get yield curve analysis\nrouter.get('/yield-curve', async (req, res) => {\n  try {\n    const { date, analysis_type = 'current' } = req.query;\n    \n    const yieldCurve = await economicEngine.getYieldCurveAnalysis(date, analysis_type);\n    \n    res.json({\n      success: true,\n      data: yieldCurve\n    });\n  } catch (error) {\n    console.error('Error fetching yield curve:', error);\n    res.status(500).json({\n      success: false,\n      error: 'Failed to fetch yield curve analysis',\n      message: error.message\n    });\n  }\n});\n\n// Get inflation analysis\nrouter.get('/inflation', async (req, res) => {\n  try {\n    const { period = '5Y', components = true } = req.query;\n    \n    const inflationAnalysis = await economicEngine.getInflationAnalysis(period, components);\n    \n    res.json({\n      success: true,\n      data: inflationAnalysis\n    });\n  } catch (error) {\n    console.error('Error fetching inflation analysis:', error);\n    res.status(500).json({\n      success: false,\n      error: 'Failed to fetch inflation analysis',\n      message: error.message\n    });\n  }\n});\n\n// Get employment analysis\nrouter.get('/employment', async (req, res) => {\n  try {\n    const { period = '2Y', detailed = false } = req.query;\n    \n    const employmentAnalysis = await economicEngine.getEmploymentAnalysis(period, detailed);\n    \n    res.json({\n      success: true,\n      data: employmentAnalysis\n    });\n  } catch (error) {\n    console.error('Error fetching employment analysis:', error);\n    res.status(500).json({\n      success: false,\n      error: 'Failed to fetch employment analysis',\n      message: error.message\n    });\n  }\n});\n\n// Get GDP analysis\nrouter.get('/gdp', async (req, res) => {\n  try {\n    const { period = '5Y', components = true } = req.query;\n    \n    const gdpAnalysis = await economicEngine.getGDPAnalysis(period, components);\n    \n    res.json({\n      success: true,\n      data: gdpAnalysis\n    });\n  } catch (error) {\n    console.error('Error fetching GDP analysis:', error);\n    res.status(500).json({\n      success: false,\n      error: 'Failed to fetch GDP analysis',\n      message: error.message\n    });\n  }\n});\n\n// Get available economic indicators list\nrouter.get('/indicators/list', async (req, res) => {\n  try {\n    const result = await query(`\n      SELECT DISTINCT\n        indicator_id,\n        indicator_name,\n        category,\n        units,\n        frequency,\n        description,\n        source,\n        last_updated,\n        COUNT(*) as data_points\n      FROM economic_indicators\n      GROUP BY indicator_id, indicator_name, category, units, frequency, description, source, last_updated\n      ORDER BY category, indicator_name\n    `);\n    \n    const indicators = result.rows.map(row => ({\n      id: row.indicator_id,\n      name: row.indicator_name,\n      category: row.category,\n      units: row.units,\n      frequency: row.frequency,\n      description: row.description,\n      source: row.source,\n      last_updated: row.last_updated,\n      data_points: parseInt(row.data_points)\n    }));\n    \n    // Group by category\n    const categorized = {};\n    indicators.forEach(indicator => {\n      if (!categorized[indicator.category]) {\n        categorized[indicator.category] = [];\n      }\n      categorized[indicator.category].push(indicator);\n    });\n    \n    res.json({\n      success: true,\n      data: {\n        indicators,\n        categorized,\n        total_count: indicators.length\n      }\n    });\n  } catch (error) {\n    console.error('Error fetching indicators list:', error);\n    res.status(500).json({\n      success: false,\n      error: 'Failed to fetch indicators list',\n      message: error.message\n    });\n  }\n});\n\nmodule.exports = router;"