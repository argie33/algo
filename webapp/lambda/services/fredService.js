const axios = require('axios');
const { query } = require('../utils/database');

class FREDService {
  constructor() {
    this.baseURL = 'https://api.stlouisfed.org/fred';
    this.apiKey = process.env.FRED_API_KEY || 'demo_key';
    this.client = axios.create({
      baseURL: this.baseURL,
      timeout: 30000,
      params: {
        api_key: this.apiKey,
        file_type: 'json'
      }
    });
  }

  // Core FRED series that we want to track
  static get CORE_SERIES() {
    return {
      // GDP and Growth
      GDP: {
        id: 'GDP',
        title: 'Gross Domestic Product',
        units: 'Billions of Dollars',
        frequency: 'Quarterly'
      },
      GDPC1: {
        id: 'GDPC1',
        title: 'Real GDP',
        units: 'Billions of Chained 2012 Dollars',
        frequency: 'Quarterly'
      },
      
      // Employment
      UNRATE: {
        id: 'UNRATE',
        title: 'Unemployment Rate',
        units: 'Percent',
        frequency: 'Monthly'
      },
      PAYEMS: {
        id: 'PAYEMS',
        title: 'Nonfarm Payrolls',
        units: 'Thousands of Persons',
        frequency: 'Monthly'
      },
      
      // Inflation
      CPIAUCSL: {
        id: 'CPIAUCSL',
        title: 'Consumer Price Index for All Urban Consumers: All Items',
        units: 'Index 1982-84=100',
        frequency: 'Monthly'
      },
      CPILFESL: {
        id: 'CPILFESL',
        title: 'Core CPI (Less Food & Energy)',
        units: 'Index 1982-84=100',
        frequency: 'Monthly'
      },
      
      // Interest Rates
      FEDFUNDS: {
        id: 'FEDFUNDS',
        title: 'Federal Funds Rate',
        units: 'Percent',
        frequency: 'Monthly'
      },
      DGS10: {
        id: 'DGS10',
        title: '10-Year Treasury Constant Maturity Rate',
        units: 'Percent',
        frequency: 'Daily'
      },
      DGS2: {
        id: 'DGS2',
        title: '2-Year Treasury Constant Maturity Rate',
        units: 'Percent',
        frequency: 'Daily'
      },
      DGS3MO: {
        id: 'DGS3MO',
        title: '3-Month Treasury Bill',
        units: 'Percent',
        frequency: 'Daily'
      },
      
      // Consumer Sentiment
      UMCSENT: {
        id: 'UMCSENT',
        title: 'University of Michigan Consumer Sentiment',
        units: 'Index 1966:Q1=100',
        frequency: 'Monthly'
      },
      
      // Industrial Production
      INDPRO: {
        id: 'INDPRO',
        title: 'Industrial Production Index',
        units: 'Index 2017=100',
        frequency: 'Monthly'
      },
      
      // Housing
      HOUST: {
        id: 'HOUST',
        title: 'Housing Starts',
        units: 'Thousands of Units',
        frequency: 'Monthly'
      },
      
      // Market Indicators
      VIXCLS: {
        id: 'VIXCLS',
        title: 'CBOE Volatility Index',
        units: 'Index',
        frequency: 'Daily'
      }
    };
  }

  async getSeries(seriesId, options = {}) {
    try {
      const {
        startDate = '2020-01-01',
        endDate = new Date().toISOString().split('T')[0],
        limit = 1000
      } = options;

      console.log(`Fetching FRED series ${seriesId} from ${startDate} to ${endDate}`);

      const response = await this.client.get(`/series/observations`, {
        params: {
          series_id: seriesId,
          observation_start: startDate,
          observation_end: endDate,
          limit: limit,
          sort_order: 'desc'
        }
      });

      if (!response.data || !response.data.observations) {
        throw new Error(`No data returned for series ${seriesId}`);
      }

      const observations = response.data.observations
        .filter(obs => obs.value !== '.')  // Filter out missing values
        .map(obs => ({
          date: obs.date,
          value: parseFloat(obs.value),
          series_id: seriesId
        }));

      console.log(`Successfully fetched ${observations.length} observations for ${seriesId}`);
      return observations;

    } catch (error) {
      console.error(`Error fetching FRED series ${seriesId}:`, error.message);
      throw error;
    }
  }

  async getSeriesInfo(seriesId) {
    try {
      const response = await this.client.get(`/series`, {
        params: { series_id: seriesId }
      });

      if (!response.data || !response.data.seriess || response.data.seriess.length === 0) {
        throw new Error(`No series info found for ${seriesId}`);
      }

      const series = response.data.seriess[0];
      return {
        id: series.id,
        title: series.title,
        units: series.units,
        frequency: series.frequency,
        last_updated: series.last_updated,
        notes: series.notes
      };

    } catch (error) {
      console.error(`Error fetching series info for ${seriesId}:`, error.message);
      throw error;
    }
  }

  async updateDatabaseSeries(seriesId, options = {}) {
    try {
      // Get series info
      const seriesInfo = await this.getSeriesInfo(seriesId);
      
      // Get latest data
      const observations = await this.getSeries(seriesId, options);

      if (observations.length === 0) {
        console.log(`No new data to update for series ${seriesId}`);
        return { updated: 0, series: seriesId };
      }

      // Insert/update data in database
      let updatedCount = 0;
      for (const obs of observations) {
        try {
          const result = await query(`
            INSERT INTO economic_data (
              series_id, date, value, title, units, frequency, last_updated
            ) VALUES ($1, $2, $3, $4, $5, $6, NOW())
            ON CONFLICT (series_id, date) 
            DO UPDATE SET
              value = EXCLUDED.value,
              title = EXCLUDED.title,
              units = EXCLUDED.units,
              frequency = EXCLUDED.frequency,
              last_updated = NOW()
          `, [
            obs.series_id,
            obs.date,
            obs.value,
            seriesInfo.title,
            seriesInfo.units,
            seriesInfo.frequency
          ]);

          if (result.rowCount > 0) {
            updatedCount++;
          }
        } catch (dbError) {
          console.error(`Error inserting observation for ${seriesId} on ${obs.date}:`, dbError.message);
        }
      }

      console.log(`Updated ${updatedCount} observations for series ${seriesId}`);
      return { updated: updatedCount, series: seriesId, latest_date: observations[0]?.date };

    } catch (error) {
      console.error(`Error updating database for series ${seriesId}:`, error.message);
      throw error;
    }
  }

  async updateAllCoreSeries() {
    const results = [];
    const coreSeries = Object.keys(FREDService.CORE_SERIES);

    console.log(`Starting update of ${coreSeries.length} core FRED series...`);

    for (const seriesId of coreSeries) {
      try {
        const result = await this.updateDatabaseSeries(seriesId, {
          startDate: '2020-01-01'  // Get data from 2020 onwards
        });
        results.push(result);
        
        // Rate limiting - FRED allows 120 requests per minute
        await new Promise(resolve => setTimeout(resolve, 1000));
        
      } catch (error) {
        console.error(`Failed to update series ${seriesId}:`, error.message);
        results.push({ 
          series: seriesId, 
          error: error.message, 
          updated: 0 
        });
      }
    }

    const totalUpdated = results.reduce((sum, r) => sum + (r.updated || 0), 0);
    console.log(`Completed FRED update: ${totalUpdated} total observations updated`);

    return {
      success: true,
      summary: {
        total_series: coreSeries.length,
        successful_updates: results.filter(r => !r.error).length,
        total_observations: totalUpdated,
        timestamp: new Date().toISOString()
      },
      details: results
    };
  }

  async getLatestIndicators() {
    try {
      // Get the most recent values for key indicators
      const indicators = await query(`
        SELECT DISTINCT ON (series_id) 
          series_id,
          date,
          value,
          title,
          units,
          last_updated
        FROM economic_data 
        WHERE series_id IN ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        ORDER BY series_id, date DESC
      `, [
        'GDP', 'UNRATE', 'CPIAUCSL', 'FEDFUNDS', 'DGS10', 
        'DGS2', 'UMCSENT', 'INDPRO', 'HOUST', 'VIXCLS'
      ]);

      // Calculate derived metrics
      const indicatorMap = {};
      indicators.rows.forEach(row => {
        indicatorMap[row.series_id] = row;
      });

      // Calculate yield curve spread (10Y - 2Y)
      const yieldSpread = indicatorMap.DGS10 && indicatorMap.DGS2 
        ? indicatorMap.DGS10.value - indicatorMap.DGS2.value 
        : null;

      return {
        indicators: indicatorMap,
        derived_metrics: {
          yield_curve_spread: yieldSpread,
          yield_curve_inverted: yieldSpread !== null && yieldSpread < 0,
          last_updated: new Date().toISOString()
        }
      };

    } catch (error) {
      console.error('Error getting latest indicators:', error.message);
      throw error;
    }
  }

  async searchSeries(searchText, limit = 20) {
    try {
      const response = await this.client.get(`/series/search`, {
        params: {
          search_text: searchText,
          limit: limit,
          order_by: 'popularity',
          sort_order: 'desc'
        }
      });

      if (!response.data || !response.data.seriess) {
        return [];
      }

      return response.data.seriess.map(series => ({
        id: series.id,
        title: series.title,
        units: series.units,
        frequency: series.frequency,
        popularity: series.popularity,
        last_updated: series.last_updated
      }));

    } catch (error) {
      console.error('Error searching FRED series:', error.message);
      throw error;
    }
  }

  // Generate mock data when FRED is unavailable
  static generateMockData() {
    const mockData = {};
    const coreSeries = FREDService.CORE_SERIES;
    
    Object.keys(coreSeries).forEach(seriesId => {
      const series = coreSeries[seriesId];
      mockData[seriesId] = {
        series_id: seriesId,
        title: series.title,
        units: series.units,
        frequency: series.frequency,
        value: FREDService.getMockValue(seriesId),
        date: new Date().toISOString().split('T')[0],
        last_updated: new Date().toISOString()
      };
    });

    return {
      indicators: mockData,
      derived_metrics: {
        yield_curve_spread: 1.2,
        yield_curve_inverted: false,
        last_updated: new Date().toISOString()
      }
    };
  }

  static getMockValue(seriesId) {
    const mockValues = {
      GDP: 26900,
      GDPC1: 22996,
      UNRATE: 4.1,
      PAYEMS: 155000,
      CPIAUCSL: 310.5,
      CPILFESL: 315.2,
      FEDFUNDS: 5.25,
      DGS10: 4.2,
      DGS2: 3.0,
      DGS3MO: 2.8,
      UMCSENT: 78.5,
      INDPRO: 103.2,
      HOUST: 1420,
      VIXCLS: 18.5
    };
    return mockValues[seriesId] || 100;
  }
}

module.exports = FREDService;