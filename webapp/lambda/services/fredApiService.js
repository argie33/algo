/**
 * Federal Reserve Economic Data (FRED) API Service
 * Real implementation to replace mock data fallbacks
 * Provides economic indicators from the Federal Reserve Bank of St. Louis
 */

const axios = require('axios');
const { getTimeout } = require('../utils/timeoutManager');

class FREDApiService {
    constructor(apiKey = null) {
        this.apiKey = apiKey || process.env.FRED_API_KEY;
        this.baseUrl = 'https://api.stlouisfed.org/fred';
        this.retryCount = 3;
        this.retryDelay = 1000;
        
        if (!this.apiKey) {
            console.warn('⚠️ FRED API key not provided, will use mock data');
        } else {
            console.log('📊 FRED API Service initialized with API key');
        }
    }

    /**
     * Make API request to FRED with retry logic
     */
    async makeRequest(endpoint, params = {}) {
        if (!this.apiKey) {
            throw new Error('FRED API key not configured');
        }

        const requestParams = {
            api_key: this.apiKey,
            file_type: 'json',
            ...params
        };

        const queryString = new URLSearchParams(requestParams).toString();
        const url = `${this.baseUrl}${endpoint}?${queryString}`;

        let lastError;
        for (let attempt = 1; attempt <= this.retryCount; attempt++) {
            try {
                console.log(`📡 Making FRED API request (attempt ${attempt}): ${endpoint}`);
                
                const response = await axios.get(url, {
                    timeout: getTimeout('market_data', 'historical')
                });

                if (response.status === 200 && response.data) {
                    console.log('✅ FRED API request successful');
                    return response.data;
                }

                throw new Error(`Invalid response: ${response.status}`);
            } catch (error) {
                lastError = error;
                console.warn(`⚠️ FRED API request failed (attempt ${attempt}): ${error.message}`);
                
                if (attempt < this.retryCount) {
                    await new Promise(resolve => setTimeout(resolve, this.retryDelay * attempt));
                }
            }
        }

        throw new Error(`FRED API request failed after ${this.retryCount} attempts: ${lastError.message}`);
    }

    /**
     * Get economic series data
     */
    async getSeries(seriesId, limit = 100) {
        try {
            const data = await this.makeRequest('/series/observations', {
                series_id: seriesId,
                limit: limit,
                sort_order: 'desc'
            });

            if (!data.observations || !Array.isArray(data.observations)) {
                throw new Error('Invalid data format from FRED API');
            }

            return data.observations
                .filter(obs => obs.value !== '.')  // Filter out missing values
                .map(obs => ({
                    date: obs.date,
                    value: parseFloat(obs.value),
                    seriesId: seriesId
                }))
                .reverse(); // Return in chronological order
        } catch (error) {
            console.error(`❌ Failed to get FRED series ${seriesId}:`, error.message);
            throw error;
        }
    }

    /**
     * Get multiple economic indicators at once
     */
    async getEconomicIndicators() {
        try {
            console.log('📈 Fetching key economic indicators from FRED...');

            // Key economic indicators with their FRED series IDs
            const indicators = {
                gdp: 'GDP',                    // Gross Domestic Product
                unemployment: 'UNRATE',        // Unemployment Rate
                inflation: 'CPIAUCSL',         // Consumer Price Index
                federalFunds: 'FEDFUNDS',      // Federal Funds Rate
                treasury10y: 'GS10',          // 10-Year Treasury Rate
                treasury2y: 'GS2',           // 2-Year Treasury Rate
                consumerSentiment: 'UMCSENT', // University of Michigan Consumer Sentiment
                industrialProduction: 'INDPRO', // Industrial Production Index
                retailSales: 'RSXFS',         // Retail Sales
                housingStarts: 'HOUST'        // Housing Starts
            };

            const promises = Object.entries(indicators).map(async ([key, seriesId]) => {
                try {
                    const data = await this.getSeries(seriesId, 24); // Last 2 years of monthly data
                    return { key, data, seriesId };
                } catch (error) {
                    console.warn(`⚠️ Failed to get ${key} (${seriesId}):`, error.message);
                    return { key, data: [], seriesId, error: error.message };
                }
            });

            const results = await Promise.allSettled(promises);
            
            const economicData = {};
            let successCount = 0;
            let errorCount = 0;

            results.forEach((result, index) => {
                if (result.status === 'fulfilled') {
                    const { key, data, seriesId, error } = result.value;
                    economicData[key] = {
                        seriesId,
                        data,
                        error,
                        current: data.length > 0 ? data[data.length - 1] : null,
                        previous: data.length > 1 ? data[data.length - 2] : null,
                        change: null,
                        changePercent: null
                    };

                    if (!error && data.length >= 2) {
                        const current = data[data.length - 1].value;
                        const previous = data[data.length - 2].value;
                        economicData[key].change = current - previous;
                        economicData[key].changePercent = ((current - previous) / previous) * 100;
                        successCount++;
                    } else if (error) {
                        errorCount++;
                    }
                } else {
                    errorCount++;
                }
            });

            console.log(`📊 FRED data retrieval complete: ${successCount} successful, ${errorCount} failed`);

            return {
                indicators: economicData,
                summary: {
                    totalIndicators: Object.keys(indicators).length,
                    successfulIndicators: successCount,
                    failedIndicators: errorCount,
                    dataSource: 'FRED',
                    timestamp: new Date().toISOString()
                }
            };
        } catch (error) {
            console.error('❌ Failed to get economic indicators:', error.message);
            throw new Error(`Failed to fetch economic indicators: ${error.message}`);
        }
    }

    /**
     * Get specific economic indicator with metadata
     */
    async getIndicator(indicatorName) {
        const indicatorMap = {
            gdp: { seriesId: 'GDP', name: 'Gross Domestic Product', units: 'Billions of Dollars' },
            unemployment: { seriesId: 'UNRATE', name: 'Unemployment Rate', units: 'Percent' },
            inflation: { seriesId: 'CPIAUCSL', name: 'Consumer Price Index', units: 'Index 1982-1984=100' },
            federalFunds: { seriesId: 'FEDFUNDS', name: 'Federal Funds Rate', units: 'Percent' },
            treasury10y: { seriesId: 'GS10', name: '10-Year Treasury Rate', units: 'Percent' },
            consumerSentiment: { seriesId: 'UMCSENT', name: 'Consumer Sentiment', units: 'Index 1966:Q1=100' }
        };

        const indicator = indicatorMap[indicatorName.toLowerCase()];
        if (!indicator) {
            throw new Error(`Unknown indicator: ${indicatorName}`);
        }

        try {
            const data = await this.getSeries(indicator.seriesId, 60); // Last 5 years
            
            return {
                name: indicator.name,
                seriesId: indicator.seriesId,
                units: indicator.units,
                data,
                current: data.length > 0 ? data[data.length - 1] : null,
                historical: data,
                metadata: {
                    dataPoints: data.length,
                    dateRange: {
                        start: data.length > 0 ? data[0].date : null,
                        end: data.length > 0 ? data[data.length - 1].date : null
                    }
                }
            };
        } catch (error) {
            console.error(`❌ Failed to get indicator ${indicatorName}:`, error.message);
            throw error;
        }
    }

    /**
     * Generate mock data when FRED API is unavailable
     * This maintains the existing interface while providing fallback data
     */
    static generateMockData() {
        console.log('🎭 Generating mock economic data (FRED API unavailable)');
        
        const mockData = {
            indicators: {
                gdp: {
                    seriesId: 'GDP',
                    data: this.generateMockSeries(22000, 500, 12), // GDP in billions
                    current: { date: '2024-06-01', value: 22500 },
                    previous: { date: '2024-03-01', value: 22300 },
                    change: 200,
                    changePercent: 0.9
                },
                unemployment: {
                    seriesId: 'UNRATE',
                    data: this.generateMockSeries(3.8, 0.3, 12), // Unemployment rate
                    current: { date: '2024-06-01', value: 3.7 },
                    previous: { date: '2024-05-01', value: 3.9 },
                    change: -0.2,
                    changePercent: -5.1
                },
                inflation: {
                    seriesId: 'CPIAUCSL',
                    data: this.generateMockSeries(310, 5, 12), // CPI
                    current: { date: '2024-06-01', value: 314.2 },
                    previous: { date: '2024-05-01', value: 313.5 },
                    change: 0.7,
                    changePercent: 0.22
                },
                federalFunds: {
                    seriesId: 'FEDFUNDS',
                    data: this.generateMockSeries(5.25, 0.25, 12), // Fed funds rate
                    current: { date: '2024-06-01', value: 5.25 },
                    previous: { date: '2024-05-01', value: 5.25 },
                    change: 0,
                    changePercent: 0
                },
                treasury10y: {
                    seriesId: 'GS10',
                    data: this.generateMockSeries(4.3, 0.2, 12), // 10-year treasury
                    current: { date: '2024-06-01', value: 4.35 },
                    previous: { date: '2024-05-01', value: 4.28 },
                    change: 0.07,
                    changePercent: 1.64
                }
            },
            summary: {
                totalIndicators: 5,
                successfulIndicators: 5,
                failedIndicators: 0,
                dataSource: 'MOCK_DATA',
                timestamp: new Date().toISOString()
            }
        };

        return mockData;
    }

    /**
     * Generate mock time series data
     */
    static generateMockSeries(baseValue, volatility, periods) {
        const data = [];
        let currentValue = baseValue;
        const startDate = new Date();
        startDate.setMonth(startDate.getMonth() - periods);

        for (let i = 0; i < periods; i++) {
            const date = new Date(startDate);
            date.setMonth(date.getMonth() + i);
            
            // Add some realistic variation
            const change = (Math.random() - 0.5) * volatility;
            currentValue += change;
            
            data.push({
                date: date.toISOString().split('T')[0],
                value: Math.round(currentValue * 100) / 100,
                seriesId: 'MOCK'
            });
        }

        return data;
    }

    /**
     * Validate API configuration
     */
    async validateApiKey() {
        if (!this.apiKey) {
            return { valid: false, message: 'FRED API key not configured' };
        }

        try {
            // Test with a simple series request
            await this.makeRequest('/series', { series_id: 'GDP', limit: 1 });
            return { valid: true, message: 'FRED API key validated successfully' };
        } catch (error) {
            return { valid: false, message: `FRED API validation failed: ${error.message}` };
        }
    }
}

module.exports = FREDApiService;