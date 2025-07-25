/**
 * Economic Data Population Service
 * Fetches real economic data from FRED API and populates database
 */

const axios = require('axios');
const { query } = require('../utils/database');

class EconomicDataPopulationService {
  constructor() {
    // Use FRED API key from environment, with demo fallback
    this.fredApiKey = process.env.FRED_API_KEY || 'demo';
    this.fredBaseUrl = 'https://api.stlouisfed.org/fred';
    
    // Key economic indicators to fetch
    this.indicators = {
      // GDP & Growth
      'GDP': { category: 'GDP', name: 'Gross Domestic Product', units: 'billions', frequency: 'quarterly' },
      'A191RL1Q225SBEA': { category: 'GDP', name: 'GDP Growth Rate', units: 'percent', frequency: 'quarterly' },
      
      // Employment
      'UNRATE': { category: 'Employment', name: 'Unemployment Rate', units: 'percent', frequency: 'monthly' },
      'PAYEMS': { category: 'Employment', name: 'Nonfarm Payrolls', units: 'thousands', frequency: 'monthly' },
      'JTSJOL': { category: 'Employment', name: 'Job Openings', units: 'thousands', frequency: 'monthly' },
      
      // Inflation
      'CPIAUCSL': { category: 'Inflation', name: 'Consumer Price Index', units: 'index', frequency: 'monthly' },
      'CPILFESL': { category: 'Inflation', name: 'Core CPI', units: 'percent', frequency: 'monthly' },
      'PCEPI': { category: 'Inflation', name: 'PCE Price Index', units: 'index', frequency: 'monthly' },
      
      // Interest Rates
      'DFF': { category: 'Interest Rates', name: 'Federal Funds Rate', units: 'percent', frequency: 'daily' },
      'DGS10': { category: 'Interest Rates', name: '10-Year Treasury Rate', units: 'percent', frequency: 'daily' },
      'DGS2': { category: 'Interest Rates', name: '2-Year Treasury Rate', units: 'percent', frequency: 'daily' },
      'DGS3MO': { category: 'Interest Rates', name: '3-Month Treasury Rate', units: 'percent', frequency: 'daily' },
      'DGS1': { category: 'Interest Rates', name: '1-Year Treasury Rate', units: 'percent', frequency: 'daily' },
      'DGS5': { category: 'Interest Rates', name: '5-Year Treasury Rate', units: 'percent', frequency: 'daily' },
      'DGS30': { category: 'Interest Rates', name: '30-Year Treasury Rate', units: 'percent', frequency: 'daily' },
      
      // Consumer
      'RSXFS': { category: 'Consumer', name: 'Retail Sales', units: 'millions', frequency: 'monthly' },
      'UMCSENT': { category: 'Consumer', name: 'Consumer Sentiment', units: 'index', frequency: 'monthly' },
      
      // Housing
      'HOUST': { category: 'Housing', name: 'Housing Starts', units: 'thousands', frequency: 'monthly' },
      'CSUSHPISA': { category: 'Housing', name: 'Case-Shiller Home Price Index', units: 'index', frequency: 'monthly' },
      
      // Manufacturing
      'INDPRO': { category: 'Manufacturing', name: 'Industrial Production', units: 'index', frequency: 'monthly' },
      
      // Market
      'VIXCLS': { category: 'Market', name: 'VIX Volatility Index', units: 'index', frequency: 'daily' },
      'DTWEXBGS': { category: 'Market', name: 'US Dollar Index', units: 'index', frequency: 'daily' }
    };

    console.log(`🏗️ Economic Data Population Service initialized with ${Object.keys(this.indicators).length} indicators`);
  }

  /**
   * Populate all economic indicators from FRED API
   */
  async populateAllIndicators(lookbackMonths = 24) {
    console.log(`📊 Starting population of ${Object.keys(this.indicators).length} economic indicators...`);
    
    const results = {
      success: [],
      errors: [],
      total: Object.keys(this.indicators).length
    };

    // Calculate date range
    const endDate = new Date();
    const startDate = new Date();
    startDate.setMonth(endDate.getMonth() - lookbackMonths);
    
    const startDateStr = startDate.toISOString().split('T')[0];
    const endDateStr = endDate.toISOString().split('T')[0];

    console.log(`📅 Fetching data from ${startDateStr} to ${endDateStr}`);

    // Process indicators in batches to avoid rate limits
    const indicatorIds = Object.keys(this.indicators);
    const batchSize = 5;
    
    for (let i = 0; i < indicatorIds.length; i += batchSize) {
      const batch = indicatorIds.slice(i, i + batchSize);
      console.log(`⚡ Processing batch ${Math.floor(i/batchSize) + 1}/${Math.ceil(indicatorIds.length/batchSize)}: ${batch.join(', ')}`);
      
      await Promise.all(batch.map(async (indicatorId) => {
        try {
          const result = await this.fetchAndStoreIndicator(indicatorId, startDateStr, endDateStr);
          results.success.push({
            indicator: indicatorId,
            recordsInserted: result.recordsInserted,
            recordsUpdated: result.recordsUpdated
          });
          console.log(`✅ ${indicatorId}: ${result.recordsInserted} inserted, ${result.recordsUpdated} updated`);
        } catch (error) {
          console.error(`❌ ${indicatorId}: ${error.message}`);
          results.errors.push({
            indicator: indicatorId,
            error: error.message
          });
        }
      }));

      // Rate limit: 120 calls per minute for FRED API
      if (this.fredApiKey !== 'demo' && i + batchSize < indicatorIds.length) {
        await this.sleep(1000); // 1 second between batches
      }
    }

    console.log(`📊 Population complete: ${results.success.length} success, ${results.errors.length} errors`);
    return results;
  }

  /**
   * Fetch single indicator from FRED and store in database
   */
  async fetchAndStoreIndicator(indicatorId, startDate, endDate, limit = 1000) {
    const indicator = this.indicators[indicatorId];
    if (!indicator) {
      throw new Error(`Unknown indicator: ${indicatorId}`);
    }

    // Skip if using demo key (too limited for bulk operations)
    if (this.fredApiKey === 'demo') {
      console.log(`⚠️ Skipping ${indicatorId} - demo API key has limited access`);
      return { recordsInserted: 0, recordsUpdated: 0 };
    }

    try {
      // Fetch from FRED API
      const params = new URLSearchParams({
        series_id: indicatorId,
        api_key: this.fredApiKey,
        file_type: 'json',
        observation_start: startDate,
        observation_end: endDate,
        limit: limit.toString(),
        sort_order: 'desc' // Most recent first
      });

      const url = `${this.fredBaseUrl}/series/observations?${params}`;
      console.log(`🔍 Fetching ${indicatorId} from FRED...`);
      
      const response = await axios.get(url, { timeout: 10000 });
      
      if (!response.data || !response.data.observations) {
        throw new Error('Invalid FRED API response');
      }

      const observations = response.data.observations;
      console.log(`📈 ${indicatorId}: Received ${observations.length} observations`);

      // Filter out invalid observations
      const validObservations = observations.filter(obs => 
        obs.value !== '.' && 
        obs.value !== null && 
        obs.value !== undefined && 
        !isNaN(parseFloat(obs.value))
      );

      if (validObservations.length === 0) {
        console.log(`⚠️ ${indicatorId}: No valid observations found`);
        return { recordsInserted: 0, recordsUpdated: 0 };
      }

      // Insert/update records in database
      let recordsInserted = 0;
      let recordsUpdated = 0;

      for (const obs of validObservations) {
        try {
          const result = await query(
            `INSERT INTO economic_indicators 
             (indicator_id, indicator_name, category, value, date, units, frequency, source, description, last_updated)
             VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, CURRENT_TIMESTAMP)
             ON CONFLICT (indicator_id, date) 
             DO UPDATE SET 
               value = EXCLUDED.value,
               last_updated = CURRENT_TIMESTAMP
             RETURNING (xmax = 0) AS inserted`,
            [
              indicatorId,
              indicator.name,
              indicator.category,
              parseFloat(obs.value),
              obs.date,
              indicator.units,
              indicator.frequency,
              'FRED',
              `${indicator.name} from Federal Reserve Economic Data`
            ]
          );

          if (result.rows[0]?.inserted) {
            recordsInserted++;
          } else {
            recordsUpdated++;
          }
        } catch (dbError) {
          console.error(`💥 Database error for ${indicatorId} ${obs.date}:`, dbError.message);
        }
      }

      return { recordsInserted, recordsUpdated };

    } catch (error) {
      if (error.code === 'ECONNABORTED') {
        throw new Error(`FRED API timeout for ${indicatorId}`);
      } else if (error.response?.status === 429) {
        throw new Error(`FRED API rate limit exceeded for ${indicatorId}`);
      } else if (error.response?.status === 400) {
        throw new Error(`Invalid FRED API request for ${indicatorId}: ${error.response.data?.error_message || 'Bad request'}`);
      } else {
        throw new Error(`FRED API error for ${indicatorId}: ${error.message}`);
      }
    }
  }

  /**
   * Update only the most recent data for all indicators
   */
  async updateRecentData(days = 30) {
    console.log(`🔄 Updating recent data for last ${days} days...`);
    
    const endDate = new Date();
    const startDate = new Date();
    startDate.setDate(endDate.getDate() - days);
    
    const startDateStr = startDate.toISOString().split('T')[0];
    const endDateStr = endDate.toISOString().split('T')[0];

    return await this.populateAllIndicators(Math.ceil(days / 30));
  }

  /**
   * Get indicators that need updating (older than X hours)
   */
  async getStaleIndicators(hoursThreshold = 24) {
    try {
      const result = await query(
        `SELECT DISTINCT indicator_id, indicator_name, category, 
                MAX(last_updated) as last_updated,
                COUNT(*) as total_records
         FROM economic_indicators 
         WHERE last_updated < NOW() - INTERVAL '${hoursThreshold} hours'
         GROUP BY indicator_id, indicator_name, category
         ORDER BY last_updated ASC`,
        []
      );

      return result.rows;
    } catch (error) {
      console.error('Error checking stale indicators:', error);
      return [];
    }
  }

  /**
   * Get population statistics
   */
  async getPopulationStats() {
    try {
      const result = await query(
        `SELECT 
           COUNT(DISTINCT indicator_id) as total_indicators,
           COUNT(*) as total_records,
           MIN(date) as earliest_date,
           MAX(date) as latest_date,
           MAX(last_updated) as last_updated
         FROM economic_indicators`,
        []
      );

      const categoryResult = await query(
        `SELECT category, COUNT(DISTINCT indicator_id) as indicator_count,
                COUNT(*) as record_count
         FROM economic_indicators 
         GROUP BY category 
         ORDER BY record_count DESC`,
        []
      );

      return {
        overall: result.rows[0],
        byCategory: categoryResult.rows
      };
    } catch (error) {
      console.error('Error getting population stats:', error);
      return null;
    }
  }

  /**
   * Populate economic calendar events (placeholder - would integrate with real calendar API)
   */
  async populateEconomicCalendar() {
    console.log('📅 Populating economic calendar events...');
    
    // For now, we'll use the seed data from the schema
    // In production, this would integrate with APIs like:
    // - Investing.com Economic Calendar API
    // - MarketWatch Calendar API  
    // - FMP Economic Calendar API
    
    const now = new Date();
    const futureEvents = [
      {
        event_id: `FOMC_${now.getFullYear()}_${String(now.getMonth() + 1).padStart(2, '0')}`,
        event_name: 'FOMC Meeting',
        event_date: this.getNextBusinessDay(now, 14),
        event_time: '14:00',
        importance: 'High',
        category: 'Monetary Policy',
        forecast_value: '5.25%',
        previous_value: '5.25%',
        description: 'Federal Open Market Committee interest rate decision'
      },
      {
        event_id: `CPI_${now.getFullYear()}_${String(now.getMonth() + 1).padStart(2, '0')}`,
        event_name: 'Consumer Price Index',
        event_date: this.getNextBusinessDay(now, 7),
        event_time: '08:30',
        importance: 'High',
        category: 'Inflation',
        forecast_value: '3.1% Y/Y',
        previous_value: '3.2% Y/Y',
        description: 'Monthly CPI inflation report'
      },
      {
        event_id: `NFP_${now.getFullYear()}_${String(now.getMonth() + 1).padStart(2, '0')}`,
        event_name: 'Nonfarm Payrolls',
        event_date: this.getFirstFridayOfMonth(now.getFullYear(), now.getMonth() + 1),
        event_time: '08:30',
        importance: 'High',
        category: 'Employment',
        forecast_value: '200K',
        previous_value: '275K',
        description: 'Monthly employment report'
      }
    ];

    let inserted = 0;
    for (const event of futureEvents) {
      try {
        await query(
          `INSERT INTO economic_calendar 
           (event_id, event_name, event_date, event_time, importance, category, 
            forecast_value, previous_value, description)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
           ON CONFLICT (event_id, event_date) DO NOTHING`,
          [
            event.event_id,
            event.event_name,
            event.event_date,
            event.event_time,
            event.importance,
            event.category,
            event.forecast_value,
            event.previous_value,
            event.description
          ]
        );
        inserted++;
      } catch (error) {
        console.error(`Error inserting calendar event ${event.event_id}:`, error.message);
      }
    }

    console.log(`📅 Calendar populated: ${inserted} events added`);
    return { eventsInserted: inserted };
  }

  // Helper methods
  sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  getNextBusinessDay(date, daysFromNow) {
    const future = new Date(date);
    future.setDate(future.getDate() + daysFromNow);
    
    // Skip weekends
    while (future.getDay() === 0 || future.getDay() === 6) {
      future.setDate(future.getDate() + 1);
    }
    
    return future.toISOString().split('T')[0];
  }

  getFirstFridayOfMonth(year, month) {
    const firstDay = new Date(year, month - 1, 1);
    const firstFriday = new Date(firstDay);
    
    // Find first Friday
    while (firstFriday.getDay() !== 5) {
      firstFriday.setDate(firstFriday.getDate() + 1);
    }
    
    return firstFriday.toISOString().split('T')[0];
  }
}

module.exports = EconomicDataPopulationService;