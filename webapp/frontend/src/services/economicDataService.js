// Economic Data Service - Integrates economic indicators and macro data
// Supports FRED API, custom indicators, and real-time updates

import axios from 'axios';
import cacheService, { CacheConfigs } from './cacheService';

class EconomicDataService {
  constructor() {
    this.fredApiKey = process.env.REACT_APP_FRED_API_KEY || 'demo';
    this.fredBaseUrl = 'https://api.stlouisfed.org/fred';
    
    // Key economic indicators with FRED series IDs
    this.indicators = {
      // GDP & Growth
      gdp: { 
        id: 'GDP', 
        name: 'Gross Domestic Product', 
        frequency: 'quarterly',
        unit: 'billions'
      },
      gdpGrowth: { 
        id: 'A191RL1Q225SBEA', 
        name: 'GDP Growth Rate', 
        frequency: 'quarterly',
        unit: 'percent'
      },
      
      // Inflation
      cpi: { 
        id: 'CPIAUCSL', 
        name: 'Consumer Price Index', 
        frequency: 'monthly',
        unit: 'index'
      },
      cpiYoY: { 
        id: 'CPILFESL', 
        name: 'Core CPI YoY', 
        frequency: 'monthly',
        unit: 'percent'
      },
      pce: { 
        id: 'PCEPI', 
        name: 'PCE Price Index', 
        frequency: 'monthly',
        unit: 'index'
      },
      
      // Employment
      unemployment: { 
        id: 'UNRATE', 
        name: 'Unemployment Rate', 
        frequency: 'monthly',
        unit: 'percent'
      },
      nonfarmPayrolls: { 
        id: 'PAYEMS', 
        name: 'Nonfarm Payrolls', 
        frequency: 'monthly',
        unit: 'thousands'
      },
      jobOpenings: { 
        id: 'JTSJOL', 
        name: 'Job Openings', 
        frequency: 'monthly',
        unit: 'thousands'
      },
      
      // Interest Rates
      fedFunds: { 
        id: 'DFF', 
        name: 'Federal Funds Rate', 
        frequency: 'daily',
        unit: 'percent'
      },
      treasury10Y: { 
        id: 'DGS10', 
        name: '10-Year Treasury Rate', 
        frequency: 'daily',
        unit: 'percent'
      },
      treasury2Y: { 
        id: 'DGS2', 
        name: '2-Year Treasury Rate', 
        frequency: 'daily',
        unit: 'percent'
      },
      
      // Consumer
      retailSales: { 
        id: 'RSXFS', 
        name: 'Retail Sales', 
        frequency: 'monthly',
        unit: 'millions'
      },
      consumerSentiment: { 
        id: 'UMCSENT', 
        name: 'Consumer Sentiment', 
        frequency: 'monthly',
        unit: 'index'
      },
      
      // Housing
      housingStarts: { 
        id: 'HOUST', 
        name: 'Housing Starts', 
        frequency: 'monthly',
        unit: 'thousands'
      },
      caseShiller: { 
        id: 'CSUSHPISA', 
        name: 'Case-Shiller Home Price Index', 
        frequency: 'monthly',
        unit: 'index'
      },
      
      // Manufacturing
      ism: { 
        id: 'MANEMP', 
        name: 'ISM Manufacturing Index', 
        frequency: 'monthly',
        unit: 'index'
      },
      industrialProduction: { 
        id: 'INDPRO', 
        name: 'Industrial Production', 
        frequency: 'monthly',
        unit: 'index'
      },
      
      // Market Indicators
      vix: { 
        id: 'VIXCLS', 
        name: 'VIX Volatility Index', 
        frequency: 'daily',
        unit: 'index'
      },
      dollarIndex: { 
        id: 'DTWEXBGS', 
        name: 'US Dollar Index', 
        frequency: 'daily',
        unit: 'index'
      }
    };
    
    // Economic calendar events
    this.calendarEvents = [
      { name: 'FOMC Meeting', frequency: '8 times/year', impact: 'high' },
      { name: 'Nonfarm Payrolls', frequency: 'monthly', impact: 'high' },
      { name: 'CPI Release', frequency: 'monthly', impact: 'high' },
      { name: 'GDP Release', frequency: 'quarterly', impact: 'high' },
      { name: 'Retail Sales', frequency: 'monthly', impact: 'medium' },
      { name: 'ISM Manufacturing', frequency: 'monthly', impact: 'medium' }
    ];
  }

  // Get multiple indicators
  async getIndicators(indicatorKeys = [], options = {}) {
    const results = {};
    
    // Use Promise.all for parallel fetching
    await Promise.all(
      indicatorKeys.map(async (key) => {
        try {
          const data = await this.getIndicator(key, options);
          results[key] = data;
        } catch (error) {
          console.error(`Failed to fetch ${key}:`, error);
          results[key] = this.getMockIndicatorData(key);
        }
      })
    );
    
    return results;
  }

  // Get single indicator
  async getIndicator(indicatorKey, options = {}) {
    const indicator = this.indicators[indicatorKey];
    if (!indicator) {
      throw new Error(`Unknown indicator: ${indicatorKey}`);
    }

    const cacheKey = cacheService.generateKey('economic_indicator', {
      indicator: indicatorKey,
      ...options
    });

    return cacheService.cacheApiCall(
      cacheKey,
      async () => {
        if (this.fredApiKey === 'demo') {
          return this.getMockIndicatorData(indicatorKey);
        }

        const { start, end, limit = 100 } = options;
        const params = new URLSearchParams({
          series_id: indicator.id,
          api_key: this.fredApiKey,
          file_type: 'json',
          limit: limit.toString()
        });

        if (start) params.append('observation_start', start);
        if (end) params.append('observation_end', end);

        const response = await axios.get(
          `${this.fredBaseUrl}/series/observations?${params}`
        );

        const observations = response.data.observations || [];
        
        return {
          indicator: indicatorKey,
          name: indicator.name,
          unit: indicator.unit,
          frequency: indicator.frequency,
          data: observations.map(obs => ({
            date: obs.date,
            value: parseFloat(obs.value),
            timestamp: new Date(obs.date).getTime()
          })),
          lastUpdated: new Date().toISOString(),
          source: 'FRED'
        };
      },
      300000, // 5 minutes cache
      true // persist
    );
  }

  // Get economic dashboard data
  async getDashboardData() {
    const cacheKey = 'economic_dashboard';
    
    return cacheService.cacheApiCall(
      cacheKey,
      async () => {
        // Key indicators for dashboard
        const keyIndicators = [
          'gdpGrowth',
          'cpiYoY',
          'unemployment',
          'fedFunds',
          'treasury10Y',
          'vix'
        ];

        const data = await this.getIndicators(keyIndicators, { limit: 10 });
        
        // Calculate trends and changes
        const dashboard = {};
        
        for (const [key, indicatorData] of Object.entries(data)) {
          const latest = indicatorData.data[indicatorData.data.length - 1];
          const previous = indicatorData.data[indicatorData.data.length - 2];
          
          dashboard[key] = {
            name: indicatorData.name,
            value: latest?.value || 0,
            previousValue: previous?.value || 0,
            change: latest && previous ? latest.value - previous.value : 0,
            changePercent: latest && previous && previous.value !== 0 
              ? ((latest.value - previous.value) / previous.value) * 100 
              : 0,
            trend: this.calculateTrend(indicatorData.data),
            lastUpdated: latest?.date || new Date().toISOString(),
            unit: indicatorData.unit
          };
        }
        
        return dashboard;
      },
      300000 // 5 minutes
    );
  }

  // Calculate trend from data points
  calculateTrend(data) {
    if (!data || data.length < 2) return 'stable';
    
    const recent = data.slice(-5); // Last 5 data points
    let upCount = 0;
    let downCount = 0;
    
    for (let i = 1; i < recent.length; i++) {
      if (recent[i].value > recent[i-1].value) upCount++;
      else if (recent[i].value < recent[i-1].value) downCount++;
    }
    
    if (upCount > downCount * 1.5) return 'up';
    if (downCount > upCount * 1.5) return 'down';
    return 'stable';
  }

  // Get yield curve data
  async getYieldCurve() {
    const cacheKey = 'yield_curve';
    
    return cacheService.cacheApiCall(
      cacheKey,
      async () => {
        const maturities = [
          { key: 'DGS1MO', name: '1 Month', months: 1 },
          { key: 'DGS3MO', name: '3 Month', months: 3 },
          { key: 'DGS6MO', name: '6 Month', months: 6 },
          { key: 'DGS1', name: '1 Year', months: 12 },
          { key: 'DGS2', name: '2 Year', months: 24 },
          { key: 'DGS5', name: '5 Year', months: 60 },
          { key: 'DGS10', name: '10 Year', months: 120 },
          { key: 'DGS30', name: '30 Year', months: 360 }
        ];
        
        const yieldData = [];
        
        for (const maturity of maturities) {
          try {
            const data = await this.getIndicator(maturity.key, { limit: 1 });
            const latest = data.data[data.data.length - 1];
            
            yieldData.push({
              maturity: maturity.name,
              months: maturity.months,
              yield: latest?.value || 0,
              date: latest?.date || new Date().toISOString()
            });
          } catch (error) {
            // Use mock data if fetch fails
            yieldData.push({
              maturity: maturity.name,
              months: maturity.months,
              yield: 3.5 + (maturity.months / 120), // Simple mock curve
              date: new Date().toISOString()
            });
          }
        }
        
        // Calculate spread (10Y - 2Y)
        const twoYear = yieldData.find(y => y.maturity === '2 Year');
        const tenYear = yieldData.find(y => y.maturity === '10 Year');
        const spread = tenYear && twoYear ? tenYear.yield - twoYear.yield : 0;
        
        return {
          curve: yieldData,
          spread,
          isInverted: spread < 0,
          lastUpdated: new Date().toISOString()
        };
      },
      600000 // 10 minutes
    );
  }

  // Get economic calendar
  async getEconomicCalendar(days = 7) {
    // For now, return mock calendar data
    // In production, this would fetch from an economic calendar API
    const events = [];
    const now = new Date();
    
    for (let i = 0; i < days; i++) {
      const date = new Date(now);
      date.setDate(date.getDate() + i);
      
      // Add some random events
      if (i === 0 || i === 3) {
        events.push({
          date: date.toISOString(),
          time: '08:30',
          event: 'Initial Jobless Claims',
          actual: null,
          forecast: '215K',
          previous: '220K',
          impact: 'medium'
        });
      }
      
      if (i === 5) {
        events.push({
          date: date.toISOString(),
          time: '10:00',
          event: 'Consumer Sentiment',
          actual: null,
          forecast: '69.5',
          previous: '68.1',
          impact: 'medium'
        });
      }
    }
    
    return events;
  }

  // Get market correlations with economic data
  async getMarketCorrelations() {
    // This would calculate correlations between economic indicators and market indices
    // For now, return mock correlations
    return {
      'S&P 500': {
        gdp: 0.75,
        unemployment: -0.68,
        fedFunds: -0.45,
        vix: -0.82
      },
      'US Dollar': {
        fedFunds: 0.72,
        treasury10Y: 0.65,
        cpi: 0.38
      },
      'Gold': {
        fedFunds: -0.58,
        dollarIndex: -0.71,
        vix: 0.45
      }
    };
  }

  // Mock data for development/demo
  getMockIndicatorData(indicatorKey) {
    const indicator = this.indicators[indicatorKey];
    const data = [];
    const now = new Date();
    
    // Generate mock historical data
    for (let i = 30; i >= 0; i--) {
      const date = new Date(now);
      date.setDate(date.getDate() - i);
      
      let baseValue;
      switch (indicatorKey) {
        case 'gdpGrowth': baseValue = 2.5; break;
        case 'unemployment': baseValue = 3.8; break;
        case 'cpiYoY': baseValue = 3.2; break;
        case 'fedFunds': baseValue = 5.25; break;
        case 'treasury10Y': baseValue = 4.5; break;
        case 'vix': baseValue = 18; break;
        default: baseValue = 100;
      }
      
      // Add some random variation
      const value = baseValue + (Math.random() - 0.5) * baseValue * 0.1;
      
      data.push({
        date: date.toISOString().split('T')[0],
        value: parseFloat(value.toFixed(2)),
        timestamp: date.getTime()
      });
    }
    
    return {
      indicator: indicatorKey,
      name: indicator.name,
      unit: indicator.unit,
      frequency: indicator.frequency,
      data,
      lastUpdated: new Date().toISOString(),
      source: 'mock'
    };
  }

  // Get recession probability model
  async getRecessionProbability() {
    // Simplified model based on yield curve and other indicators
    const yieldCurve = await this.getYieldCurve();
    const dashboard = await this.getDashboardData();
    
    let probability = 0;
    
    // Yield curve inversion is a strong indicator
    if (yieldCurve.isInverted) probability += 40;
    
    // High unemployment
    if (dashboard.unemployment?.value > 4.5) probability += 20;
    
    // Slowing GDP
    if (dashboard.gdpGrowth?.value < 1.5) probability += 20;
    
    // High VIX
    if (dashboard.vix?.value > 25) probability += 10;
    
    // Declining consumer sentiment
    if (dashboard.consumerSentiment?.trend === 'down') probability += 10;
    
    return {
      probability: Math.min(probability, 90),
      factors: {
        yieldCurveInverted: yieldCurve.isInverted,
        spread: yieldCurve.spread,
        unemployment: dashboard.unemployment?.value,
        gdpGrowth: dashboard.gdpGrowth?.value,
        vix: dashboard.vix?.value
      },
      lastUpdated: new Date().toISOString()
    };
  }
}

// Create singleton instance
const economicDataService = new EconomicDataService();

export default economicDataService;