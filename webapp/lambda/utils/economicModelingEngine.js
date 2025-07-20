const { query } = require('./database');

class EconomicModelingEngine {
  constructor() {
    this.models = {
      gdp: this.createGDPModel(),
      inflation: this.createInflationModel(),
      employment: this.createEmploymentModel(),
      yield_curve: this.createYieldCurveModel(),
      recession: this.createRecessionModel()
    };
  }

  async getEconomicModels(modelType, horizon) {
    try {
      const availableModels = {
        gdp: {
          name: 'GDP Growth Model',
          description: 'Forecasts GDP growth based on leading indicators',
          inputs: ['employment', 'consumer_spending', 'business_investment', 'government_spending'],
          outputs: ['gdp_growth_forecast', 'confidence_intervals'],
          horizon_options: ['3M', '6M', '1Y', '2Y']
        },
        inflation: {
          name: 'Inflation Forecasting Model',
          description: 'Predicts inflation trends using multiple economic factors',
          inputs: ['money_supply', 'commodity_prices', 'wage_growth', 'capacity_utilization'],
          outputs: ['inflation_forecast', 'core_inflation_forecast'],
          horizon_options: ['1M', '3M', '6M', '1Y']
        },
        employment: {
          name: 'Employment Analysis Model',
          description: 'Analyzes labor market conditions and forecasts employment trends',
          inputs: ['jobless_claims', 'job_openings', 'labor_participation', 'wage_growth'],
          outputs: ['unemployment_forecast', 'job_growth_forecast'],
          horizon_options: ['1M', '3M', '6M', '1Y']
        },
        yield_curve: {
          name: 'Yield Curve Analysis Model',
          description: 'Analyzes yield curve shape and predicts interest rate movements',
          inputs: ['fed_funds_rate', 'treasury_yields', 'credit_spreads', 'inflation_expectations'],
          outputs: ['yield_curve_forecast', 'inversion_probability'],
          horizon_options: ['1M', '3M', '6M', '1Y']
        },
        recession: {
          name: 'Recession Probability Model',
          description: 'Estimates probability of recession using leading indicators',
          inputs: ['yield_curve', 'unemployment', 'consumer_confidence', 'leading_indicators'],
          outputs: ['recession_probability', 'risk_factors'],
          horizon_options: ['3M', '6M', '1Y', '2Y']
        }
      };

      if (modelType && availableModels[modelType]) {
        const model = availableModels[modelType];
        const forecast = await this.runModel(modelType, horizon);
        return {
          model: model,
          forecast: forecast
        };
      }

      return {
        available_models: availableModels,
        count: Object.keys(availableModels).length
      };
    } catch (error) {
      console.error('Error getting economic models:', error);
      throw error;
    }
  }

  async runScenarioAnalysis({ base_scenario, shock_scenarios, indicators, time_horizon, confidence_level }) {
    try {
      const analysis = {
        base_scenario: await this.analyzeBaseScenario(base_scenario, indicators, time_horizon),
        shock_scenarios: [],
        summary: null
      };

      // Run shock scenarios
      for (const shock of shock_scenarios) {
        const shockAnalysis = await this.analyzeShockScenario(shock, indicators, time_horizon);
        analysis.shock_scenarios.push(shockAnalysis);
      }

      // Generate summary
      analysis.summary = this.generateScenarioSummary(analysis, confidence_level);

      return analysis;
    } catch (error) {
      console.error('Error running scenario analysis:', error);
      throw error;
    }
  }

  async calculateCorrelations(indicators, period, method) {
    try {
      const correlationMatrix = {};
      
      // Get data for all indicators
      const indicatorData = {};
      for (const indicator of indicators) {
        const data = await this.getIndicatorData(indicator, period);
        indicatorData[indicator] = data;
      }

      // Calculate correlations
      for (const indicator1 of indicators) {
        correlationMatrix[indicator1] = {};
        for (const indicator2 of indicators) {
          if (indicator1 === indicator2) {
            correlationMatrix[indicator1][indicator2] = 1.0;
          } else {
            const correlation = this.calculateCorrelation(
              indicatorData[indicator1],
              indicatorData[indicator2],
              method
            );
            correlationMatrix[indicator1][indicator2] = correlation;
          }
        }
      }

      return correlationMatrix;
    } catch (error) {
      console.error('Error calculating correlations:', error);
      throw error;
    }
  }

  async generateForecast(indicatorId, horizon, modelType) {
    try {
      // Get historical data
      const historicalData = await this.getIndicatorData(indicatorId, '5Y');
      
      // Generate forecast based on model type
      let forecast;
      switch (modelType) {
        case 'arima':
          forecast = await this.generateARIMAForecast(historicalData, horizon);
          break;
        case 'linear':
          forecast = await this.generateLinearForecast(historicalData, horizon);
          break;
        case 'exponential':
          forecast = await this.generateExponentialForecast(historicalData, horizon);
          break;
        default:
          forecast = await this.generateARIMAForecast(historicalData, horizon);
      }

      return {
        indicator_id: indicatorId,
        horizon,
        model_type: modelType,
        forecast: forecast,
        confidence_intervals: this.calculateConfidenceIntervals(forecast),
        generated_at: new Date().toISOString()
      };
    } catch (error) {
      console.error('Error generating forecast:', error);
      throw error;
    }
  }

  async analyzeEconomicImpact({ economic_event, affected_sectors, time_horizon, analysis_type }) {
    try {
      const impact = {
        event: economic_event,
        sectors: [],
        overall_impact: null,
        timeline: null,
        confidence: null
      };

      // Analyze impact on each sector
      for (const sector of affected_sectors) {
        const sectorImpact = await this.analyzeSectorImpact(economic_event, sector, time_horizon);
        impact.sectors.push(sectorImpact);
      }

      // Calculate overall impact
      impact.overall_impact = this.calculateOverallImpact(impact.sectors);
      impact.timeline = this.generateImpactTimeline(economic_event, time_horizon);
      impact.confidence = this.assessAnalysisConfidence(impact);

      return impact;
    } catch (error) {
      console.error('Error analyzing economic impact:', error);
      throw error;
    }
  }

  async getYieldCurveAnalysis(date, analysisType) {
    try {
      const yieldCurveData = await this.getYieldCurveData(date);
      
      const analysis = {
        date: date || new Date().toISOString().split('T')[0],
        curve_data: yieldCurveData,
        shape: this.analyzeYieldCurveShape(yieldCurveData),
        inversion_status: this.checkYieldCurveInversion(yieldCurveData),
        historical_comparison: null,
        risk_assessment: null
      };

      if (analysisType === 'comprehensive') {
        analysis.historical_comparison = await this.compareToHistoricalCurves(yieldCurveData);
        analysis.risk_assessment = this.assessYieldCurveRisk(analysis);
      }

      return analysis;
    } catch (error) {
      console.error('Error getting yield curve analysis:', error);
      throw error;
    }
  }

  async getInflationAnalysis(period, components) {
    try {
      const inflationData = await this.getInflationData(period);
      
      const analysis = {
        period,
        current_inflation: inflationData.current,
        trend: this.analyzeInflationTrend(inflationData.historical),
        components: components ? await this.getInflationComponents(period) : null,
        forecast: await this.generateInflationForecast(inflationData),
        fed_target_comparison: this.compareToFedTarget(inflationData.current)
      };

      return analysis;
    } catch (error) {
      console.error('Error getting inflation analysis:', error);
      throw error;
    }
  }

  async getEmploymentAnalysis(period, detailed) {
    try {
      const employmentData = await this.getEmploymentData(period);
      
      const analysis = {
        period,
        unemployment_rate: employmentData.unemployment_rate,
        employment_change: employmentData.employment_change,
        labor_participation: employmentData.labor_participation,
        wage_growth: employmentData.wage_growth,
        trend: this.analyzeEmploymentTrend(employmentData),
        sectors: detailed ? await this.getEmploymentBySector(period) : null,
        forecast: await this.generateEmploymentForecast(employmentData)
      };

      return analysis;
    } catch (error) {
      console.error('Error getting employment analysis:', error);
      throw error;
    }
  }

  async getGDPAnalysis(period, components) {
    try {
      const gdpData = await this.getGDPData(period);
      
      const analysis = {
        period,
        current_gdp: gdpData.current,
        growth_rate: gdpData.growth_rate,
        trend: this.analyzeGDPTrend(gdpData.historical),
        components: components ? await this.getGDPComponents(period) : null,
        forecast: await this.generateGDPForecast(gdpData),
        recession_risk: this.assessRecessionRisk(gdpData)
      };

      return analysis;
    } catch (error) {
      console.error('Error getting GDP analysis:', error);
      throw error;
    }
  }

  // Helper methods
  async getIndicatorData(indicatorId, period) {
    try {
      const result = await query(`
        SELECT date, value
        FROM economic_indicators
        WHERE indicator_id = $1
        AND date >= NOW() - INTERVAL '${period}'
        ORDER BY date ASC
      `, [indicatorId]);

      return result.rows.map(row => ({
        date: row.date,
        value: parseFloat(row.value)
      }));
    } catch (error) {
      console.error('Error getting indicator data:', error);
      return [];
    }
  }

  calculateCorrelation(data1, data2, method) {
    if (data1.length !== data2.length || data1.length < 2) return 0;

    const values1 = data1.map(d => d.value);
    const values2 = data2.map(d => d.value);

    if (method === 'pearson') {
      return this.calculatePearsonCorrelation(values1, values2);
    } else if (method === 'spearman') {
      return this.calculateSpearmanCorrelation(values1, values2);
    }

    return this.calculatePearsonCorrelation(values1, values2);
  }

  calculatePearsonCorrelation(x, y) {
    const n = x.length;
    if (n === 0) return 0;

    const sumX = x.reduce((a, b) => a + b, 0);
    const sumY = y.reduce((a, b) => a + b, 0);
    const sumXY = x.reduce((sum, xi, i) => sum + xi * y[i], 0);
    const sumX2 = x.reduce((sum, xi) => sum + xi * xi, 0);
    const sumY2 = y.reduce((sum, yi) => sum + yi * yi, 0);

    const numerator = n * sumXY - sumX * sumY;
    const denominator = Math.sqrt((n * sumX2 - sumX * sumX) * (n * sumY2 - sumY * sumY));

    return denominator === 0 ? 0 : numerator / denominator;
  }

  async generateARIMAForecast(data, horizon) {
    // Simplified ARIMA implementation
    if (data.length < 10) return [];

    const values = data.map(d => d.value);
    const trend = this.calculateTrend(values);
    const forecast = [];

    const periods = this.parseHorizon(horizon);
    let lastValue = values[values.length - 1];

    for (let i = 0; i < periods; i++) {
      const forecastValue = lastValue + trend + (Math.random() - 0.5) * 0.1;
      forecast.push({
        period: i + 1,
        value: forecastValue,
        confidence: Math.max(0.95 - i * 0.05, 0.5)
      });
      lastValue = forecastValue;
    }

    return forecast;
  }

  calculateTrend(values) {
    if (values.length < 2) return 0;

    const n = values.length;
    const x = Array.from({ length: n }, (_, i) => i);
    const y = values;

    const sumX = x.reduce((a, b) => a + b, 0);
    const sumY = y.reduce((a, b) => a + b, 0);
    const sumXY = x.reduce((sum, xi, i) => sum + xi * y[i], 0);
    const sumX2 = x.reduce((sum, xi) => sum + xi * xi, 0);

    const slope = (n * sumXY - sumX * sumY) / (n * sumX2 - sumX * sumX);
    return slope;
  }

  compareToFedTarget(currentInflation) {
    const fedTarget = 2.0; // Fed's inflation target is 2%
    const deviation = currentInflation - fedTarget;
    
    return {
      target: fedTarget,
      current: currentInflation,
      deviation: deviation,
      deviationPercent: (deviation / fedTarget) * 100,
      status: Math.abs(deviation) <= 0.5 ? 'within_target' : 
              deviation > 0.5 ? 'above_target' : 'below_target',
      message: Math.abs(deviation) <= 0.5 ? 'Inflation is within Fed target range' :
               deviation > 0.5 ? 'Inflation is above Fed target' : 'Inflation is below Fed target'
    };
  }

  parseHorizon(horizon) {
    const match = horizon.match(/(\d+)([MYD])/);
    if (!match) return 12;

    const [, num, unit] = match;
    const number = parseInt(num);

    switch (unit) {
      case 'D': return number;
      case 'M': return number;
      case 'Y': return number * 12;
      default: return 12;
    }
  }

  calculateConfidenceIntervals(forecast) {
    return forecast.map(point => ({
      period: point.period,
      lower_bound: point.value - (point.value * 0.1),
      upper_bound: point.value + (point.value * 0.1),
      confidence_level: point.confidence
    }));
  }

  // Mock implementations for complex economic data
  async getYieldCurveData(date) {
    // Mock yield curve data
    return {
      '1M': 2.1,
      '3M': 2.3,
      '6M': 2.5,
      '1Y': 2.8,
      '2Y': 3.1,
      '5Y': 3.5,
      '10Y': 3.8,
      '30Y': 4.0
    };
  }

  async getInflationData(period) {
    // Mock inflation data
    return {
      current: 3.2,
      historical: Array.from({ length: 24 }, (_, i) => ({
        date: new Date(Date.now() - i * 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
        value: 3.2 + (Math.random() - 0.5) * 2
      }))
    };
  }

  async getEmploymentData(period) {
    return {
      unemployment_rate: 3.7,
      employment_change: 180000,
      labor_participation: 63.2,
      wage_growth: 4.1
    };
  }

  async getGDPData(period) {
    return {
      current: 21.43,
      growth_rate: 2.1,
      historical: Array.from({ length: 20 }, (_, i) => ({
        date: new Date(Date.now() - i * 90 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
        value: 21.43 + (Math.random() - 0.5) * 2
      }))
    };
  }

  // Create model templates
  createGDPModel() {
    return {
      name: 'GDP Growth Model',
      variables: ['employment', 'investment', 'consumption', 'government_spending'],
      equation: 'GDP = C + I + G + (X - M)',
      parameters: {},
      forecast_horizon: 12
    };
  }

  createInflationModel() {
    return {
      name: 'Inflation Model',
      variables: ['money_supply', 'velocity', 'output', 'expectations'],
      equation: 'π = f(M, V, Y, πe)',
      parameters: {},
      forecast_horizon: 12
    };
  }

  createEmploymentModel() {
    return {
      name: 'Employment Model',
      variables: ['gdp_growth', 'productivity', 'labor_force'],
      equation: 'Employment = f(GDP, Productivity, Labor Force)',
      parameters: {},
      forecast_horizon: 12
    };
  }

  createYieldCurveModel() {
    return {
      name: 'Yield Curve Model',
      variables: ['fed_funds', 'inflation_expectations', 'term_premium'],
      equation: 'Yield = Short Rate + Term Premium + Risk Premium',
      parameters: {},
      forecast_horizon: 12
    };
  }

  createRecessionModel() {
    return {
      name: 'Recession Probability Model',
      variables: ['yield_curve', 'unemployment', 'consumer_confidence'],
      equation: 'P(Recession) = f(Yield Curve, Unemployment, Confidence)',
      parameters: {},
      forecast_horizon: 12
    };
  }

  // Analysis helper methods
  analyzeBaseScenario(scenario, indicators, horizon) {
    return {
      scenario_name: scenario.name,
      assumptions: scenario.assumptions,
      forecast: this.generateScenarioForecast(scenario, indicators, horizon),
      probability: 0.6 // Base scenario probability
    };
  }

  analyzeShockScenario(shock, indicators, horizon) {
    return {
      shock_name: shock.name,
      shock_magnitude: shock.magnitude,
      affected_variables: shock.affected_variables,
      forecast: this.generateShockForecast(shock, indicators, horizon),
      probability: shock.probability || 0.2
    };
  }

  generateScenarioSummary(analysis, confidence_level) {
    return {
      base_outcome: analysis.base_scenario.forecast,
      risk_scenarios: analysis.shock_scenarios.map(s => s.forecast),
      confidence_level,
      key_risks: this.identifyKeyRisks(analysis),
      recommendations: this.generateRecommendations(analysis)
    };
  }

  identifyKeyRisks(analysis) {
    return [
      'Interest rate volatility',
      'Inflation persistence',
      'Geopolitical tensions',
      'Supply chain disruptions'
    ];
  }

  generateRecommendations(analysis) {
    return [
      'Monitor yield curve inversion signals',
      'Track inflation expectations',
      'Watch employment trends',
      'Assess consumer confidence'
    ];
  }
}

module.exports = EconomicModelingEngine;